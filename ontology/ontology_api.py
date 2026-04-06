#!/usr/bin/env python3
"""
ontology_api.py -- Unified query interface across 3 ontology layers.

L1: Static Structure (dependency graph, patterns) -- updated weekly
L2: Dynamic State (entity state, predictions, handoffs) -- updated every 5 min
L3: Temporal Intelligence (timeseries, baselines, anomalies, forecasts) -- hourly snapshots

Usage:
    from ontology_api import OntologyStack
    stack = OntologyStack()
    print(stack.get_entity("service:mission-control"))
    print(stack.blast_radius("config:openclaw.json"))
    print(stack.get_system_summary())
"""
import sqlite3
import json
import math
import os
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

L1_DB = "/Users/marcmunoz/.openclaw/data/L1_structure.db"
L2_DB = "/Users/marcmunoz/.openclaw/data/L2_state.db"
L3_DB = "/Users/marcmunoz/.openclaw/data/L3_temporal.db"

# ---------- Schema DDL ----------

L1_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT,
    properties TEXT,
    critical INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS edges (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    metadata TEXT,
    PRIMARY KEY (from_id, to_id, edge_type)
);
CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT,
    trigger_entity TEXT,
    affected_entities TEXT,
    description TEXT,
    metadata TEXT,
    last_observed TEXT
);
"""

L2_SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_state (
    entity_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (entity_id, key)
);
CREATE TABLE IF NOT EXISTS active_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    prediction TEXT NOT NULL,
    confidence REAL,
    severity TEXT,
    evidence TEXT,
    recommended_action TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS active_handoffs (
    id TEXT PRIMARY KEY,
    from_agent TEXT,
    to_agent TEXT,
    entity_id TEXT,
    action TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    context TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""

L3_SCHEMA = """
CREATE TABLE IF NOT EXISTS timeseries (
    entity_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ts ON timeseries(entity_id, metric, recorded_at);

CREATE TABLE IF NOT EXISTS baselines (
    entity_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    mean REAL,
    stddev REAL,
    p95 REAL,
    samples INTEGER,
    computed_over_days INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (entity_id, metric)
);
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    expected_value REAL,
    actual_value REAL,
    deviation_sigma REAL,
    detected_at TEXT NOT NULL,
    acknowledged INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS forecasts (
    entity_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    horizon_hours INTEGER,
    predicted_value REAL,
    confidence_low REAL,
    confidence_high REAL,
    model TEXT,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (entity_id, metric, horizon_hours)
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _connect(path):
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(path, schema):
    conn = _connect(path)
    conn.executescript(schema)
    conn.commit()
    conn.close()


# ---------- Tracked metrics for L2 -> L3 snapshotting ----------
TRACKED_METRICS = {
    "risk_score", "error_rate", "health_score", "avg_duration_seconds",
    "actual_age_hours", "ram_free_mb", "confidence",
}


class OntologyStack:
    """Unified query interface across L1 / L2 / L3."""

    def __init__(self):
        _init_db(L1_DB, L1_SCHEMA)
        _init_db(L2_DB, L2_SCHEMA)
        _init_db(L3_DB, L3_SCHEMA)

    # ---- connections (short-lived per call) ----

    def _l1(self):
        return _connect(L1_DB)

    def _l2(self):
        return _connect(L2_DB)

    def _l3(self):
        return _connect(L3_DB)

    # ================================================================
    # get_entity -- full picture across all layers
    # ================================================================

    def get_entity(self, entity_id: str) -> dict:
        """Full picture: L1 structure + L2 state + L3 trends + anomalies."""
        result = {"entity_id": entity_id}

        # L1: node info
        conn = self._l1()
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (entity_id,)).fetchone()
        if row:
            result["l1_node"] = {
                "type": row["type"],
                "name": row["name"],
                "properties": json.loads(row["properties"]) if row["properties"] else {},
                "critical": bool(row["critical"]),
            }
        # L1: edges
        edges_out = conn.execute(
            "SELECT to_id, edge_type, metadata FROM edges WHERE from_id = ?", (entity_id,)
        ).fetchall()
        edges_in = conn.execute(
            "SELECT from_id, edge_type, metadata FROM edges WHERE to_id = ?", (entity_id,)
        ).fetchall()
        result["l1_edges_out"] = [
            {"to": r["to_id"], "type": r["edge_type"],
             "metadata": json.loads(r["metadata"]) if r["metadata"] else None}
            for r in edges_out
        ]
        result["l1_edges_in"] = [
            {"from": r["from_id"], "type": r["edge_type"],
             "metadata": json.loads(r["metadata"]) if r["metadata"] else None}
            for r in edges_in
        ]
        # L1: patterns involving this entity
        patterns = conn.execute(
            "SELECT * FROM patterns WHERE trigger_entity = ? OR affected_entities LIKE ?",
            (entity_id, f'%"{entity_id}"%')
        ).fetchall()
        result["l1_patterns"] = [
            {
                "pattern_type": p["pattern_type"],
                "trigger": p["trigger_entity"],
                "affected": json.loads(p["affected_entities"]) if p["affected_entities"] else [],
                "description": p["description"],
                "last_observed": p["last_observed"],
            }
            for p in patterns
        ]
        conn.close()

        # L2: entity state
        conn = self._l2()
        state_rows = conn.execute(
            "SELECT key, value, source, confidence, updated_at FROM entity_state WHERE entity_id = ?",
            (entity_id,)
        ).fetchall()
        result["l2_state"] = {
            r["key"]: {
                "value": r["value"], "source": r["source"],
                "confidence": r["confidence"], "updated_at": r["updated_at"],
            }
            for r in state_rows
        }
        # L2: predictions
        preds = conn.execute(
            "SELECT * FROM active_predictions WHERE entity_id = ? ORDER BY created_at DESC LIMIT 10",
            (entity_id,)
        ).fetchall()
        result["l2_predictions"] = [
            {
                "prediction": p["prediction"], "confidence": p["confidence"],
                "severity": p["severity"], "recommended_action": p["recommended_action"],
                "source": p["source"], "created_at": p["created_at"],
            }
            for p in preds
        ]
        # L2: handoffs
        handoffs = conn.execute(
            "SELECT * FROM active_handoffs WHERE entity_id = ? ORDER BY created_at DESC LIMIT 5",
            (entity_id,)
        ).fetchall()
        result["l2_handoffs"] = [dict(h) for h in handoffs]
        conn.close()

        # L3: recent anomalies
        conn = self._l3()
        anomalies = conn.execute(
            "SELECT * FROM anomalies WHERE entity_id = ? ORDER BY detected_at DESC LIMIT 10",
            (entity_id,)
        ).fetchall()
        result["l3_anomalies"] = [
            {
                "metric": a["metric"], "expected": a["expected_value"],
                "actual": a["actual_value"], "sigma": a["deviation_sigma"],
                "detected_at": a["detected_at"], "acknowledged": bool(a["acknowledged"]),
            }
            for a in anomalies
        ]
        # L3: baselines
        baselines = conn.execute(
            "SELECT * FROM baselines WHERE entity_id = ?", (entity_id,)
        ).fetchall()
        result["l3_baselines"] = {
            b["metric"]: {
                "mean": b["mean"], "stddev": b["stddev"], "p95": b["p95"],
                "samples": b["samples"],
            }
            for b in baselines
        }
        # L3: latest forecasts
        forecasts = conn.execute(
            "SELECT * FROM forecasts WHERE entity_id = ? ORDER BY horizon_hours",
            (entity_id,)
        ).fetchall()
        result["l3_forecasts"] = [
            {
                "metric": f["metric"], "horizon_hours": f["horizon_hours"],
                "predicted": f["predicted_value"],
                "range": [f["confidence_low"], f["confidence_high"]],
                "model": f["model"],
            }
            for f in forecasts
        ]
        conn.close()

        return result

    # ================================================================
    # blast_radius -- BFS on L1 edges, enriched with L2 risk
    # ================================================================

    def blast_radius(self, entity_id: str, max_depth: int = 3) -> list:
        """BFS on L1 edges, enriched with L2 risk scores."""
        conn_l1 = self._l1()
        conn_l2 = self._l2()

        visited = set()
        queue = deque()
        queue.append((entity_id, 0))
        visited.add(entity_id)
        results = []

        while queue:
            current, depth = queue.popleft()
            if depth > max_depth:
                continue

            # Get risk score from L2
            risk_row = conn_l2.execute(
                "SELECT value FROM entity_state WHERE entity_id = ? AND key = 'risk_score'",
                (current,)
            ).fetchone()
            risk_score = float(risk_row["value"]) if risk_row else None

            # Get node info from L1
            node = conn_l1.execute("SELECT * FROM nodes WHERE id = ?", (current,)).fetchone()
            node_name = node["name"] if node else current
            critical = bool(node["critical"]) if node else False

            results.append({
                "entity_id": current,
                "name": node_name,
                "depth": depth,
                "risk_score": risk_score,
                "critical": critical,
            })

            # Traverse outgoing edges (things this entity depends on / affects)
            neighbors = conn_l1.execute(
                "SELECT to_id, edge_type FROM edges WHERE from_id = ?", (current,)
            ).fetchall()
            # Also traverse incoming edges (things that depend on this entity)
            neighbors_in = conn_l1.execute(
                "SELECT from_id, edge_type FROM edges WHERE to_id = ?", (current,)
            ).fetchall()

            for row in neighbors:
                nid = row["to_id"]
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, depth + 1))
            for row in neighbors_in:
                nid = row["from_id"]
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, depth + 1))

        conn_l1.close()
        conn_l2.close()

        # Sort by depth then risk descending
        results.sort(key=lambda r: (r["depth"], -(r["risk_score"] or 0)))
        return results

    # ================================================================
    # update_state -- write to L2, snapshot to L3 if tracked metric
    # ================================================================

    def update_state(self, entity_id: str, key: str, value, source: str,
                     confidence: float = 1.0):
        """Write to L2. If key is a tracked metric, also snapshot to L3."""
        now = _now()
        str_value = str(value)
        conn = self._l2()
        conn.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (entity_id, key, str_value, source, confidence, now))
        conn.commit()
        conn.close()

        # Snapshot numeric tracked metrics to L3 timeseries
        if key in TRACKED_METRICS:
            try:
                numeric = float(value)
                conn = self._l3()
                conn.execute("""
                    INSERT INTO timeseries (entity_id, metric, value, recorded_at)
                    VALUES (?, ?, ?, ?)
                """, (entity_id, key, numeric, now))
                conn.commit()
                conn.close()
            except (ValueError, TypeError):
                pass

    # ================================================================
    # is_anomalous -- compare L2 current vs L3 baseline
    # ================================================================

    def is_anomalous(self, entity_id: str, metric: str) -> tuple:
        """Compare L2 current vs L3 baseline. Returns (anomalous, sigma)."""
        # Get current value from L2
        conn = self._l2()
        row = conn.execute(
            "SELECT value FROM entity_state WHERE entity_id = ? AND key = ?",
            (entity_id, metric)
        ).fetchone()
        conn.close()
        if not row:
            return (False, 0.0)

        try:
            current = float(row["value"])
        except (ValueError, TypeError):
            return (False, 0.0)

        # Get baseline from L3
        conn = self._l3()
        bl = conn.execute(
            "SELECT mean, stddev FROM baselines WHERE entity_id = ? AND metric = ?",
            (entity_id, metric)
        ).fetchone()
        conn.close()
        if not bl or bl["stddev"] is None or bl["stddev"] == 0:
            return (False, 0.0)

        sigma = abs(current - bl["mean"]) / bl["stddev"]
        anomalous = sigma >= 2.0
        return (anomalous, round(sigma, 2))

    # ================================================================
    # forecast -- EWMA forecast from L3 timeseries
    # ================================================================

    def forecast(self, entity_id: str, metric: str, hours: int = 24) -> dict:
        """EWMA forecast from L3 timeseries."""
        conn = self._l3()
        rows = conn.execute("""
            SELECT value, recorded_at FROM timeseries
            WHERE entity_id = ? AND metric = ?
            ORDER BY recorded_at DESC LIMIT 100
        """, (entity_id, metric)).fetchall()
        conn.close()

        if len(rows) < 3:
            return {"entity_id": entity_id, "metric": metric, "error": "insufficient_data"}

        values = [r["value"] for r in reversed(rows)]

        # EWMA with alpha=0.3
        alpha = 0.3
        ewma = values[0]
        for v in values[1:]:
            ewma = alpha * v + (1 - alpha) * ewma

        # Compute variance for confidence interval
        diffs = [abs(v - ewma) for v in values[-10:]]
        avg_diff = sum(diffs) / len(diffs) if diffs else 0

        now = _now()
        result = {
            "entity_id": entity_id,
            "metric": metric,
            "horizon_hours": hours,
            "predicted_value": round(ewma, 4),
            "confidence_low": round(ewma - 2 * avg_diff, 4),
            "confidence_high": round(ewma + 2 * avg_diff, 4),
            "model": "ewma_alpha_0.3",
            "computed_at": now,
            "data_points": len(values),
        }

        # Store forecast in L3
        conn = self._l3()
        conn.execute("""
            INSERT OR REPLACE INTO forecasts
            (entity_id, metric, horizon_hours, predicted_value, confidence_low, confidence_high, model, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_id, metric, hours, result["predicted_value"],
              result["confidence_low"], result["confidence_high"],
              result["model"], now))
        conn.commit()
        conn.close()

        return result

    # ================================================================
    # get_system_summary -- replaces nexus _gather_context()
    # ================================================================

    def get_system_summary(self) -> dict:
        """Replacement for nexus _gather_context(). One call gets everything."""
        summary = {"generated_at": _now()}

        # L1: node counts by type
        conn = self._l1()
        type_counts = conn.execute(
            "SELECT type, COUNT(*) as cnt FROM nodes GROUP BY type ORDER BY cnt DESC"
        ).fetchall()
        summary["l1_topology"] = {
            "node_counts": {r["type"]: r["cnt"] for r in type_counts},
            "total_nodes": sum(r["cnt"] for r in type_counts),
        }
        edge_count = conn.execute("SELECT COUNT(*) as cnt FROM edges").fetchone()["cnt"]
        summary["l1_topology"]["total_edges"] = edge_count

        critical = conn.execute(
            "SELECT id, type, name FROM nodes WHERE critical = 1"
        ).fetchall()
        summary["l1_critical_entities"] = [
            {"id": r["id"], "type": r["type"], "name": r["name"]} for r in critical
        ]

        pattern_count = conn.execute("SELECT COUNT(*) as cnt FROM patterns").fetchone()["cnt"]
        summary["l1_topology"]["total_patterns"] = pattern_count
        conn.close()

        # L2: high-risk entities
        conn = self._l2()
        high_risk = conn.execute("""
            SELECT entity_id, value, source, updated_at
            FROM entity_state WHERE key = 'risk_score' AND CAST(value AS REAL) >= 50
            ORDER BY CAST(value AS REAL) DESC
        """).fetchall()
        summary["l2_high_risk"] = [
            {"entity_id": r["entity_id"], "risk_score": float(r["value"]),
             "source": r["source"], "updated_at": r["updated_at"]}
            for r in high_risk
        ]

        # L2: active predictions
        preds = conn.execute("""
            SELECT entity_id, prediction, confidence, severity, source, created_at
            FROM active_predictions ORDER BY created_at DESC LIMIT 20
        """).fetchall()
        summary["l2_predictions"] = [dict(p) for p in preds]

        # L2: pending handoffs
        handoffs = conn.execute("""
            SELECT * FROM active_handoffs WHERE status = 'pending' ORDER BY created_at DESC
        """).fetchall()
        summary["l2_pending_handoffs"] = [dict(h) for h in handoffs]

        # L2: overall entity state count
        state_count = conn.execute(
            "SELECT COUNT(DISTINCT entity_id) as cnt FROM entity_state"
        ).fetchone()["cnt"]
        summary["l2_tracked_entities"] = state_count
        conn.close()

        # L3: unacknowledged anomalies
        conn = self._l3()
        anomalies = conn.execute("""
            SELECT entity_id, metric, expected_value, actual_value, deviation_sigma, detected_at
            FROM anomalies WHERE acknowledged = 0
            ORDER BY deviation_sigma DESC LIMIT 20
        """).fetchall()
        summary["l3_active_anomalies"] = [
            {
                "entity_id": a["entity_id"], "metric": a["metric"],
                "expected": a["expected_value"], "actual": a["actual_value"],
                "sigma": a["deviation_sigma"], "detected_at": a["detected_at"],
            }
            for a in anomalies
        ]

        # L3: timeseries coverage
        ts_stats = conn.execute("""
            SELECT COUNT(DISTINCT entity_id || '::' || metric) as series_count,
                   COUNT(*) as total_points,
                   MIN(recorded_at) as earliest,
                   MAX(recorded_at) as latest
            FROM timeseries
        """).fetchone()
        summary["l3_timeseries"] = {
            "series_count": ts_stats["series_count"],
            "total_points": ts_stats["total_points"],
            "range": [ts_stats["earliest"], ts_stats["latest"]],
        }

        baseline_count = conn.execute("SELECT COUNT(*) as cnt FROM baselines").fetchone()["cnt"]
        summary["l3_baselines_computed"] = baseline_count
        conn.close()

        return summary

    # ================================================================
    # compute_baselines -- recompute L3 baselines from timeseries data
    # ================================================================

    def compute_baselines(self, days: int = 30):
        """Recompute L3 baselines from timeseries data."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = self._l3()

        # Get all distinct entity/metric pairs
        pairs = conn.execute("""
            SELECT DISTINCT entity_id, metric FROM timeseries
            WHERE recorded_at >= ?
        """, (cutoff,)).fetchall()

        now = _now()
        count = 0
        for pair in pairs:
            eid, metric = pair["entity_id"], pair["metric"]
            rows = conn.execute("""
                SELECT value FROM timeseries
                WHERE entity_id = ? AND metric = ? AND recorded_at >= ?
                ORDER BY value
            """, (eid, metric, cutoff)).fetchall()

            values = [r["value"] for r in rows]
            n = len(values)
            if n < 3:
                continue

            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / n
            stddev = math.sqrt(variance) if variance > 0 else 0.0
            p95_idx = int(n * 0.95)
            p95 = values[min(p95_idx, n - 1)]

            conn.execute("""
                INSERT OR REPLACE INTO baselines
                (entity_id, metric, mean, stddev, p95, samples, computed_over_days, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (eid, metric, round(mean, 4), round(stddev, 4), round(p95, 4),
                  n, days, now))
            count += 1

        conn.commit()
        conn.close()
        return count

    # ================================================================
    # detect_anomalies -- compare all L2 state against L3 baselines
    # ================================================================

    def detect_anomalies(self) -> int:
        """Compare all L2 state against L3 baselines, write anomalies."""
        conn_l2 = self._l2()
        conn_l3 = self._l3()
        now = _now()

        # Get all entity states that have tracked metric keys
        metric_keys_sql = ",".join(f"'{m}'" for m in TRACKED_METRICS)
        states = conn_l2.execute(f"""
            SELECT entity_id, key, value FROM entity_state
            WHERE key IN ({metric_keys_sql})
        """).fetchall()

        count = 0
        for s in states:
            try:
                current = float(s["value"])
            except (ValueError, TypeError):
                continue

            bl = conn_l3.execute(
                "SELECT mean, stddev FROM baselines WHERE entity_id = ? AND metric = ?",
                (s["entity_id"], s["key"])
            ).fetchone()

            if not bl or bl["stddev"] is None or bl["stddev"] == 0:
                continue

            sigma = abs(current - bl["mean"]) / bl["stddev"]
            if sigma >= 2.0:
                conn_l3.execute("""
                    INSERT INTO anomalies
                    (entity_id, metric, expected_value, actual_value, deviation_sigma, detected_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (s["entity_id"], s["key"], bl["mean"], current, round(sigma, 2), now))
                count += 1

        conn_l2.close()
        conn_l3.commit()
        conn_l3.close()
        return count

    # ================================================================
    # snapshot_state -- copy L2 entity_state values into L3 timeseries
    # ================================================================

    def snapshot_state(self) -> int:
        """Copy all L2 entity_state values into L3 timeseries."""
        conn_l2 = self._l2()
        conn_l3 = self._l3()
        now = _now()

        metric_keys_sql = ",".join(f"'{m}'" for m in TRACKED_METRICS)
        states = conn_l2.execute(f"""
            SELECT entity_id, key, value FROM entity_state
            WHERE key IN ({metric_keys_sql})
        """).fetchall()

        count = 0
        for s in states:
            try:
                numeric = float(s["value"])
            except (ValueError, TypeError):
                continue
            conn_l3.execute("""
                INSERT INTO timeseries (entity_id, metric, value, recorded_at)
                VALUES (?, ?, ?, ?)
            """, (s["entity_id"], s["key"], numeric, now))
            count += 1

        conn_l2.close()
        conn_l3.commit()
        conn_l3.close()
        return count


# ================================================================
# CLI self-test
# ================================================================
if __name__ == "__main__":
    stack = OntologyStack()
    print("=== get_entity('service:mission-control') ===")
    print(json.dumps(stack.get_entity("service:mission-control"), indent=2, default=str))
    print()
    print("=== blast_radius('config:openclaw.json') ===")
    for item in stack.blast_radius("config:openclaw.json"):
        print(f"  depth={item['depth']} risk={item['risk_score']} critical={item['critical']} {item['entity_id']}")
    print()
    print("=== get_system_summary() ===")
    print(json.dumps(stack.get_system_summary(), indent=2, default=str))
