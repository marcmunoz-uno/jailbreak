#!/usr/bin/env python3
"""
causal_inference_engine.py — Structural causal reasoning for the multi-agent system.

Goes beyond the ontology_reasoner's temporal correlation detection to actual
causal inference: A happens, B follows BECAUSE OF C (the mechanism).

This implements a Structural Causal Model (SCM) on top of the ontology graph:
  - Causal paths: paths through the graph with mechanism labels
  - Root cause analysis: given an effect, trace back to originating causes
  - Counterfactual queries: "if X were fixed, would Y have occurred?"
  - Cascade prediction: given A failing, predict what will fail next and when

The key difference from ontology_reasoner's abductive scan:
  - abductive_scan asks "what might explain this?" (LLM guesses)
  - causal_inference_engine says "this IS the cause because the mechanism is M"
    (derived from observed co-occurrence + graph structure)

Data sources:
  - ontology.db (entity/relationship graph)
  - contextual_memories.db (temporal context + entity links)
  - ~/.openclaw/ontology/causal_engine.py (Jailbreak's causal graph)
  - system_brain corrections (confirmed cause→fix pairs)

Storage: writes inferences to ontology.db's inferences table
         maintains own causal_model.db for SCM state

Usage:
    python3 causal_inference_engine.py root_cause <effect>  # diagnose
    python3 causal_inference_engine.py predict <entity>     # cascade forecast
    python3 causal_inference_engine.py counterfactual <e1> <e2>  # if e1 fixed, does e2 still fail?
    python3 causal_inference_engine.py run               # full reasoning pass
    python3 causal_inference_engine.py stats             # model statistics

Cron: */15 * * * * (light pass, updates model with new evidence)
"""
import sqlite3
import json
import os
import sys
import math
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ONTOLOGY_DB = "/Users/marcmunoz/.openclaw/data/ontology.db"
CAUSAL_DB = "/Users/marcmunoz/.openclaw/data/causal_model.db"
Path(os.path.dirname(CAUSAL_DB)).mkdir(parents=True, exist_ok=True)


# ============================================================
# DB Init
# ============================================================

def _get_causal_conn():
    conn = sqlite3.connect(CAUSAL_DB, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _get_ontology_conn():
    conn = sqlite3.connect(ONTOLOGY_DB, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def _init_db():
    conn = _get_causal_conn()
    conn.executescript("""
        -- Causal edges in the SCM (separate from ontology relationships)
        CREATE TABLE IF NOT EXISTS causal_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cause TEXT NOT NULL,          -- entity id
            effect TEXT NOT NULL,         -- entity id
            mechanism TEXT NOT NULL,      -- WHY: e.g. "port_dependency", "config_shared", "cron_sequence"
            strength REAL DEFAULT 0.5,    -- 0-1, how reliably this cause produces this effect
            lag_minutes REAL DEFAULT 0,   -- typical delay between cause and effect
            evidence_count INTEGER DEFAULT 1,
            last_observed TEXT,
            confirmed INTEGER DEFAULT 0,  -- 1 = confirmed by system_brain correction
            source TEXT DEFAULT 'inferred',
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_causal_pair ON causal_edges(cause, effect, mechanism);
        CREATE INDEX IF NOT EXISTS idx_causal_cause ON causal_edges(cause);
        CREATE INDEX IF NOT EXISTS idx_causal_effect ON causal_edges(effect);

        -- Observed causal incidents (cause was followed by effect)
        CREATE TABLE IF NOT EXISTS causal_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cause TEXT NOT NULL,
            effect TEXT NOT NULL,
            mechanism TEXT,
            cause_ts TEXT NOT NULL,
            effect_ts TEXT,
            lag_minutes REAL,
            resolved INTEGER DEFAULT 0,
            resolution TEXT,
            source TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_inc_cause ON causal_incidents(cause, cause_ts);

        -- Active causal predictions (what is predicted to fail next)
        CREATE TABLE IF NOT EXISTS causal_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_entity TEXT NOT NULL,
            predicted_entity TEXT NOT NULL,
            mechanism TEXT NOT NULL,
            predicted_at TEXT NOT NULL,
            expected_failure_at TEXT,
            confidence REAL,
            lag_minutes REAL,
            cascade_depth INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',  -- pending, confirmed, invalidated
            confirmed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pred_trigger ON causal_predictions(trigger_entity, status);

        -- Root cause analysis results cache
        CREATE TABLE IF NOT EXISTS rca_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            effect TEXT NOT NULL,
            root_causes TEXT NOT NULL,   -- JSON list of {cause, path, confidence, mechanism}
            computed_at TEXT NOT NULL,
            valid_until TEXT            -- invalidated when new evidence arrives
        );
        CREATE INDEX IF NOT EXISTS idx_rca_effect ON rca_results(effect, computed_at DESC);
    """)
    conn.commit()
    conn.close()


_init_db()


# ============================================================
# Load Jailbreak causal graph (if available)
# ============================================================

def _load_jailbreak_causal() -> dict:
    """
    Load causal data from ~/.openclaw/ontology/ JSON models.
    Returns {(cause, effect): {mechanism, lag_minutes, strength}}
    """
    causal_data = {}
    jb_dir = Path.home() / ".openclaw" / "ontology"

    # failure_cascades.json
    try:
        data = json.loads((jb_dir / "failure_cascades.json").read_text())
        for cascade in data.get("cascades", []):
            trigger = cascade.get("trigger", "").lower().replace(" ", "_")
            for step in cascade.get("steps", []):
                effect = step.get("node", "").lower().replace(" ", "_")
                if trigger and effect and trigger != effect:
                    causal_data[(trigger, effect)] = {
                        "mechanism": cascade.get("type", "failure_cascade"),
                        "lag_minutes": step.get("lag_minutes", step.get("delay_minutes", 5)),
                        "strength": step.get("probability", 0.7),
                    }
    except Exception:
        pass

    # correlations.json → treat high correlations (>0.8) as causal candidates
    try:
        data = json.loads((jb_dir / "correlations.json").read_text())
        for corr in data.get("correlations", []):
            a = corr.get("entity_a", "").lower().replace(" ", "_")
            b = corr.get("entity_b", "").lower().replace(" ", "_")
            strength = corr.get("correlation", corr.get("strength", 0))
            if a and b and strength >= 0.7:
                causal_data[(a, b)] = {
                    "mechanism": "statistical_correlation",
                    "lag_minutes": corr.get("lag_minutes", 0),
                    "strength": min(strength, 0.85),  # correlation ≠ causation, cap at 0.85
                }
    except Exception:
        pass

    return causal_data


# ============================================================
# Bootstrap causal edges from sources
# ============================================================

def bootstrap_from_ontology() -> int:
    """
    Seed causal edges from ontology relationships.
    'depends_on' → causal edge with mechanism 'dependency'
    'feeds_into' → causal edge with mechanism 'data_flow'
    'produces' → causal edge with mechanism 'produces'
    """
    ont_conn = _get_ontology_conn()
    causal_conn = _get_causal_conn()
    count = 0
    now_ts = _now()

    CAUSAL_REL_MAP = {
        "depends_on": ("dependency", 5.0, 0.8),
        "feeds_into": ("data_flow", 10.0, 0.6),
        "produces": ("produces", 0.0, 0.7),
        "triggered_by": ("trigger", 1.0, 0.9),
        "monitors": ("monitoring", 0.0, 0.4),
    }

    rows = ont_conn.execute("SELECT * FROM relationships").fetchall()
    for r in rows:
        rel_type = r["relation_type"]
        if rel_type not in CAUSAL_REL_MAP:
            continue
        mechanism, lag, strength = CAUSAL_REL_MAP[rel_type]
        # depends_on: if target fails, source is blocked (reverse causal direction)
        if rel_type == "depends_on":
            cause = r["target_id"]  # target going down causes source to fail
            effect = r["source_id"]
        else:
            cause = r["source_id"]
            effect = r["target_id"]

        try:
            causal_conn.execute("""
                INSERT OR IGNORE INTO causal_edges
                (cause, effect, mechanism, strength, lag_minutes, source, last_observed, created_at)
                VALUES (?, ?, ?, ?, ?, 'ontology', ?, ?)
            """, (cause, effect, mechanism, strength, lag, now_ts, now_ts))
            count += 1
        except Exception:
            pass

    # Also seed from Jailbreak causal data
    jb_causal = _load_jailbreak_causal()
    for (cause, effect), meta in jb_causal.items():
        try:
            causal_conn.execute("""
                INSERT OR IGNORE INTO causal_edges
                (cause, effect, mechanism, strength, lag_minutes, source, last_observed, created_at)
                VALUES (?, ?, ?, ?, ?, 'jailbreak_ontology', ?, ?)
            """, (cause, effect, meta["mechanism"], meta["strength"],
                  meta["lag_minutes"], now_ts, now_ts))
            count += 1
        except Exception:
            pass

    # Seed from confirmed corrections in system_brain
    try:
        conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/system_brain.db", timeout=3)
        conn.row_factory = sqlite3.Row
        corrections = conn.execute("SELECT * FROM corrections LIMIT 200").fetchall()
        conn.close()

        for c in corrections:
            component = (c.get("component") or "").lower().replace(" ", "_")
            cause_hint = (c.get("problem") or "").lower()
            if not component:
                continue

            # Extract what caused the problem (heuristic: look for "because", "due to", "caused by")
            import re
            cause_match = re.search(
                r'(?:because|due to|caused by|from)\s+([a-z_\s]{3,30})', cause_hint
            )
            if cause_match:
                cause_entity = cause_match.group(1).strip().replace(" ", "_")[:30]
                try:
                    causal_conn.execute("""
                        INSERT OR IGNORE INTO causal_edges
                        (cause, effect, mechanism, strength, lag_minutes, confirmed, source, last_observed, created_at)
                        VALUES (?, ?, 'system_correction', 0.9, 0.0, 1, 'system_brain', ?, ?)
                    """, (cause_entity, component, now_ts, now_ts))
                    count += 1
                except Exception:
                    pass
    except Exception:
        pass

    causal_conn.commit()
    ont_conn.close()
    causal_conn.close()
    return count


# ============================================================
# Strengthen edges from observed co-occurrence
# ============================================================

def update_from_incidents() -> int:
    """
    Scan contextual_memories.db for temporal memory_links and use them to
    strengthen or weaken causal edges.
    """
    updated = 0
    try:
        mem_conn = sqlite3.connect(
            "/Users/marcmunoz/.openclaw/data/contextual_memories.db", timeout=3
        )
        mem_conn.row_factory = sqlite3.Row
    except Exception:
        return 0

    causal_conn = _get_causal_conn()

    try:
        # Get temporal links between critical/warning memories
        rows = mem_conn.execute("""
            SELECT ml.from_id, ml.to_id, ml.weight,
                   m1.content as c1, m1.entity_refs as e1, m1.timestamp as t1, m1.severity as s1,
                   m2.content as c2, m2.entity_refs as e2, m2.timestamp as t2, m2.severity as s2
            FROM memory_links ml
            JOIN memories m1 ON ml.from_id = m1.id
            JOIN memories m2 ON ml.to_id = m2.id
            WHERE ml.link_type = 'temporal'
            AND (m1.severity IN ('critical', 'warning') OR m2.severity IN ('critical', 'warning'))
            ORDER BY t1 DESC LIMIT 2000
        """).fetchall()

        for r in rows:
            try:
                e1_list = json.loads(r["e1"] or "[]")
                e2_list = json.loads(r["e2"] or "[]")
            except Exception:
                continue

            # If memory 1 (earlier) contains entity A critical, and memory 2 contains entity B
            # that A depends on, strengthen the A→B causal edge
            if r["s1"] in ("critical", "warning") and e1_list and e2_list:
                for cause in e1_list[:3]:
                    for effect in e2_list[:3]:
                        if cause == effect:
                            continue
                        # Compute lag
                        try:
                            t1 = datetime.fromisoformat(r["t1"])
                            t2 = datetime.fromisoformat(r["t2"])
                            if t1.tzinfo is None:
                                t1 = t1.replace(tzinfo=timezone.utc)
                            if t2.tzinfo is None:
                                t2 = t2.replace(tzinfo=timezone.utc)
                            lag = max(0.0, (t2 - t1).total_seconds() / 60)
                        except Exception:
                            lag = 5.0

                        # Update or insert causal edge
                        existing = causal_conn.execute("""
                            SELECT id, strength, evidence_count, lag_minutes
                            FROM causal_edges WHERE cause = ? AND effect = ?
                        """, (cause, effect)).fetchone()

                        if existing:
                            # Bayesian update: new_strength = (strength * n + 0.6) / (n + 1)
                            n = existing["evidence_count"]
                            new_strength = min(0.95, (existing["strength"] * n + 0.6) / (n + 1))
                            new_lag = (existing["lag_minutes"] * n + lag) / (n + 1)
                            causal_conn.execute("""
                                UPDATE causal_edges
                                SET strength=?, lag_minutes=?, evidence_count=?, last_observed=?
                                WHERE id=?
                            """, (round(new_strength, 4), round(new_lag, 1),
                                  n + 1, _now(), existing["id"]))
                        else:
                            causal_conn.execute("""
                                INSERT OR IGNORE INTO causal_edges
                                (cause, effect, mechanism, strength, lag_minutes,
                                 evidence_count, source, last_observed, created_at)
                                VALUES (?, ?, 'co_occurrence', 0.4, ?, 1, 'memory_compiler', ?, ?)
                            """, (cause, effect, round(lag, 1), _now(), _now()))

                        updated += 1

        causal_conn.commit()

    finally:
        mem_conn.close()
        causal_conn.close()

    return updated


# ============================================================
# Root Cause Analysis
# ============================================================

def root_cause_analysis(effect: str, max_depth: int = 5) -> list:
    """
    Given an observed effect (failing entity), trace back through causal
    edges to find probable root causes.

    Returns list of {cause, path, confidence, mechanism, lag_total_minutes}
    sorted by confidence descending.
    """
    causal_conn = _get_causal_conn()

    # Build reverse graph: effect → possible causes
    all_edges = causal_conn.execute(
        "SELECT cause, effect, mechanism, strength, lag_minutes FROM causal_edges WHERE strength >= 0.3"
    ).fetchall()
    causal_conn.close()

    reverse_graph: dict = defaultdict(list)
    for e in all_edges:
        reverse_graph[e["effect"]].append({
            "cause": e["cause"],
            "mechanism": e["mechanism"],
            "strength": e["strength"],
            "lag_minutes": e["lag_minutes"],
        })

    # BFS backwards from effect
    results = []
    queue = deque([{
        "node": effect.lower().replace(" ", "_"),
        "path": [effect],
        "confidence": 1.0,
        "lag_total": 0.0,
        "mechanisms": [],
        "depth": 0,
    }])
    visited = set()

    while queue:
        state = queue.popleft()
        node = state["node"]

        if state["depth"] >= max_depth:
            continue

        causes = reverse_graph.get(node, [])
        if not causes:
            # This node has no known causes → it's a potential root cause
            if state["depth"] > 0:
                results.append({
                    "cause": node,
                    "path": state["path"],
                    "confidence": round(state["confidence"], 4),
                    "mechanism": " → ".join(state["mechanisms"]),
                    "lag_total_minutes": round(state["lag_total"], 1),
                    "is_root": True,
                })
            continue

        for edge in causes:
            cause = edge["cause"]
            key = (cause, node)
            if key in visited:
                continue
            visited.add(key)

            new_conf = state["confidence"] * edge["strength"]
            if new_conf < 0.05:
                continue

            new_state = {
                "node": cause,
                "path": state["path"] + [f"[{edge['mechanism']}]", cause],
                "confidence": new_conf,
                "lag_total": state["lag_total"] + edge["lag_minutes"],
                "mechanisms": state["mechanisms"] + [edge["mechanism"]],
                "depth": state["depth"] + 1,
            }
            queue.append(new_state)
            results.append({
                "cause": cause,
                "path": state["path"] + [cause],
                "confidence": round(new_conf, 4),
                "mechanism": edge["mechanism"],
                "lag_total_minutes": round(state["lag_total"] + edge["lag_minutes"], 1),
                "is_root": len(reverse_graph.get(cause, [])) == 0,
            })

    # Deduplicate by cause, keep highest confidence
    best: dict = {}
    for r in results:
        c = r["cause"]
        if c not in best or r["confidence"] > best[c]["confidence"]:
            best[c] = r

    return sorted(best.values(), key=lambda x: x["confidence"], reverse=True)[:10]


# ============================================================
# Cascade Prediction
# ============================================================

def predict_cascade(entity: str, confidence_threshold: float = 0.2) -> list:
    """
    Given an entity that is failing, predict what will fail next (cascade).
    Returns list of {entity, mechanism, confidence, expected_lag_minutes, cascade_depth}
    """
    causal_conn = _get_causal_conn()

    all_edges = causal_conn.execute(
        "SELECT cause, effect, mechanism, strength, lag_minutes FROM causal_edges WHERE strength >= 0.2"
    ).fetchall()

    # Write active predictions
    predictions = []
    visited = set()
    queue = deque([{
        "node": entity.lower().replace(" ", "_"),
        "confidence": 1.0,
        "lag_total": 0.0,
        "depth": 0,
    }])
    forward_graph: dict = defaultdict(list)
    for e in all_edges:
        forward_graph[e["cause"]].append({
            "effect": e["effect"],
            "mechanism": e["mechanism"],
            "strength": e["strength"],
            "lag": e["lag_minutes"],
        })

    now_ts = datetime.now(timezone.utc)

    while queue:
        state = queue.popleft()
        if state["depth"] >= 5:
            continue

        for edge in forward_graph.get(state["node"], []):
            eff = edge["effect"]
            key = (state["node"], eff)
            if key in visited:
                continue
            visited.add(key)

            new_conf = state["confidence"] * edge["strength"]
            new_lag = state["lag_total"] + edge["lag"]
            if new_conf < confidence_threshold:
                continue

            predicted_at = (now_ts + timedelta(minutes=new_lag)).isoformat()
            pred = {
                "entity": eff,
                "mechanism": edge["mechanism"],
                "confidence": round(new_conf, 4),
                "expected_lag_minutes": round(new_lag, 1),
                "cascade_depth": state["depth"] + 1,
                "predicted_failure_at": predicted_at,
            }
            predictions.append(pred)

            # Store in DB
            try:
                causal_conn.execute("""
                    INSERT INTO causal_predictions
                    (trigger_entity, predicted_entity, mechanism, predicted_at,
                     expected_failure_at, confidence, lag_minutes, cascade_depth)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (entity, eff, edge["mechanism"], _now(),
                      predicted_at, round(new_conf, 4), round(new_lag, 1),
                      state["depth"] + 1))
            except Exception:
                pass

            queue.append({
                "node": eff,
                "confidence": new_conf,
                "lag_total": new_lag,
                "depth": state["depth"] + 1,
            })

    causal_conn.commit()
    causal_conn.close()
    return sorted(predictions, key=lambda x: (x["cascade_depth"], -x["confidence"]))


# ============================================================
# Counterfactual reasoning
# ============================================================

def counterfactual(fixed_entity: str, query_entity: str) -> dict:
    """
    "If fixed_entity were not failing, would query_entity still fail?"

    Returns: {
        "would_still_fail": bool,
        "confidence": float,
        "explanation": str,
        "residual_causes": list  # causes of query_entity that don't go through fixed_entity
    }
    """
    # All paths from any entity to query_entity
    all_rca = root_cause_analysis(query_entity, max_depth=6)

    # Find paths that go through fixed_entity
    paths_through_fixed = [r for r in all_rca if fixed_entity in r["path"]]
    paths_not_through_fixed = [r for r in all_rca if fixed_entity not in r["path"]]

    if not all_rca:
        return {
            "would_still_fail": True,
            "confidence": 0.3,
            "explanation": f"No causal model found for {query_entity}",
            "residual_causes": [],
        }

    # Confidence that fixing fixed_entity prevents query_entity failure
    conf_prevented = sum(r["confidence"] for r in paths_through_fixed)
    conf_residual = sum(r["confidence"] for r in paths_not_through_fixed)
    total = conf_prevented + conf_residual

    if total == 0:
        return {
            "would_still_fail": True,
            "confidence": 0.5,
            "explanation": "Could not determine causal contribution",
            "residual_causes": [],
        }

    pct_prevented = conf_prevented / total
    would_still_fail = pct_prevented < 0.7  # if >70% of cause mass goes through fixed_entity, fixing it helps

    return {
        "would_still_fail": would_still_fail,
        "confidence": round(abs(pct_prevented - 0.5) * 2, 3),  # distance from 50/50
        "explanation": (
            f"Fixing '{fixed_entity}' prevents {pct_prevented:.0%} of the causal mass leading to "
            f"'{query_entity}'. {'Other causes remain.' if would_still_fail else 'This would likely resolve the issue.'}"
        ),
        "residual_causes": [r["cause"] for r in paths_not_through_fixed[:5]],
        "pct_prevented": round(pct_prevented, 3),
    }


# ============================================================
# Write causal inferences to ontology.db
# ============================================================

def publish_to_ontology(top_n: int = 20) -> int:
    """
    Write the strongest causal edges as inferences in ontology.db.
    This makes them visible to the ontology_reasoner and nexus.
    """
    causal_conn = _get_causal_conn()
    try:
        top_edges = causal_conn.execute("""
            SELECT * FROM causal_edges
            WHERE strength >= 0.5
            ORDER BY strength DESC, evidence_count DESC
            LIMIT ?
        """, (top_n,)).fetchall()
    finally:
        causal_conn.close()

    try:
        ont_conn = _get_ontology_conn()
        now_ts = _now()
        count = 0
        for e in top_edges:
            description = (
                f"Causal: '{e['cause']}' → '{e['effect']}' "
                f"via {e['mechanism']} "
                f"(strength={e['strength']:.2f}, lag={e['lag_minutes']:.0f}min)"
            )
            entities_key = json.dumps(sorted([e["cause"], e["effect"]]))
            existing = ont_conn.execute("""
                SELECT id FROM inferences
                WHERE inference_type = 'causal' AND entities_involved = ? AND status = 'active'
            """, (entities_key,)).fetchone()

            if not existing:
                ont_conn.execute("""
                    INSERT INTO inferences
                    (inference_type, description, entities_involved, evidence, confidence, status, created_at)
                    VALUES ('causal', ?, ?, ?, ?, 'active', ?)
                """, (
                    description,
                    entities_key,
                    json.dumps({
                        "mechanism": e["mechanism"],
                        "lag_minutes": e["lag_minutes"],
                        "evidence_count": e["evidence_count"],
                        "confirmed": e["confirmed"],
                    }),
                    min(1.0, e["strength"]),
                    now_ts,
                ))
                count += 1

        ont_conn.commit()
        ont_conn.close()
        return count
    except Exception:
        return 0


# ============================================================
# Full reasoning pass
# ============================================================

def run(bootstrap: bool = False) -> dict:
    """Full causal reasoning pass."""
    results = {}

    if bootstrap:
        n = bootstrap_from_ontology()
        results["bootstrapped_edges"] = n

    n = update_from_incidents()
    results["updated_from_incidents"] = n

    n = publish_to_ontology()
    results["published_to_ontology"] = n

    # Compute cascade predictions for any currently unhealthy entities
    unhealthy = []
    try:
        conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/system_brain.db", timeout=3)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT component FROM health WHERE status = 'unhealthy' LIMIT 10").fetchall()
        unhealthy = [r["component"] for r in rows]
        conn.close()
    except Exception:
        pass

    cascade_predictions = []
    for entity in unhealthy[:5]:
        preds = predict_cascade(entity)
        cascade_predictions.extend(preds[:3])

    results["active_unhealthy"] = len(unhealthy)
    results["cascade_predictions"] = len(cascade_predictions)
    results["top_cascades"] = cascade_predictions[:5]

    return results


def get_stats() -> dict:
    conn = _get_causal_conn()
    total_edges = conn.execute("SELECT COUNT(*) FROM causal_edges").fetchone()[0]
    confirmed = conn.execute("SELECT COUNT(*) FROM causal_edges WHERE confirmed=1").fetchone()[0]
    by_mechanism = {r["mechanism"]: r["cnt"] for r in conn.execute(
        "SELECT mechanism, COUNT(*) as cnt FROM causal_edges GROUP BY mechanism ORDER BY cnt DESC"
    ).fetchall()}
    active_preds = conn.execute(
        "SELECT COUNT(*) FROM causal_predictions WHERE status='pending'"
    ).fetchone()[0]
    incidents = conn.execute("SELECT COUNT(*) FROM causal_incidents").fetchone()[0]
    conn.close()
    return {
        "total_causal_edges": total_edges,
        "confirmed_edges": confirmed,
        "by_mechanism": by_mechanism,
        "active_predictions": active_preds,
        "incidents_recorded": incidents,
    }


# ============================================================
# CLI
# ============================================================

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "run":
        bootstrap = "--bootstrap" in sys.argv
        print(f"Running causal inference pass{' (with bootstrap)' if bootstrap else ''}...")
        result = run(bootstrap=bootstrap)
        for k, v in result.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)}")
                for item in v[:3]:
                    print(f"    {item}")
            else:
                print(f"  {k}: {v}")

    elif cmd == "root_cause" and len(sys.argv) > 2:
        effect = " ".join(sys.argv[2:])
        print(f"Root cause analysis for: {effect}")
        print("=" * 60)
        results = root_cause_analysis(effect)
        if not results:
            print("  No causal paths found. Run with --bootstrap first.")
        for r in results[:8]:
            root_label = "[ROOT]" if r.get("is_root") else ""
            print(f"  {root_label} {r['cause']:<30} conf={r['confidence']:.3f} "
                  f"lag={r['lag_total_minutes']:.0f}m  via={r['mechanism']}")
            print(f"    Path: {' → '.join(r['path'][:8])}")

    elif cmd == "predict" and len(sys.argv) > 2:
        entity = sys.argv[2]
        print(f"Cascade prediction for failing entity: {entity}")
        print("=" * 60)
        preds = predict_cascade(entity)
        if not preds:
            print("  No cascade predictions. Run with --bootstrap first.")
        for p in preds[:10]:
            print(f"  Depth {p['cascade_depth']}: {p['entity']:<30} "
                  f"conf={p['confidence']:.3f} "
                  f"in ~{p['expected_lag_minutes']:.0f}min "
                  f"via {p['mechanism']}")

    elif cmd == "counterfactual" and len(sys.argv) > 3:
        fixed = sys.argv[2]
        query = sys.argv[3]
        print(f"Counterfactual: If '{fixed}' were fixed, would '{query}' still fail?")
        print("=" * 60)
        result = counterfactual(fixed, query)
        print(f"  Would still fail: {result['would_still_fail']}")
        print(f"  Confidence:       {result['confidence']:.3f}")
        print(f"  Explanation:      {result['explanation']}")
        if result.get("residual_causes"):
            print(f"  Residual causes:  {', '.join(result['residual_causes'])}")

    elif cmd == "stats":
        stats = get_stats()
        print("Causal Model Statistics")
        print("=" * 40)
        print(f"  Total causal edges: {stats['total_causal_edges']}")
        print(f"  Confirmed edges:    {stats['confirmed_edges']}")
        print(f"  Active predictions: {stats['active_predictions']}")
        print(f"  Incidents logged:   {stats['incidents_recorded']}")
        print(f"\n  By mechanism:")
        for m, c in sorted(stats["by_mechanism"].items(), key=lambda x: -x[1]):
            print(f"    {m:<30} {c}")

    elif cmd == "bootstrap":
        print("Bootstrapping causal edges from ontology + Jailbreak data...")
        n = bootstrap_from_ontology()
        print(f"  Created {n} causal edges")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
