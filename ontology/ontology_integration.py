#!/usr/bin/env python3
"""
ontology_integration.py — Layered Stack integration + Ontology Bus wiring.

This is the glue layer that connects the new intelligence stack to the
production system. It fixes two critical gaps:

  GAP 1: predictor.py writes to stdout/file but Nexus never reads it.
         → Fix: sync latest_prediction.json to shared_memory + event_bus
           so Nexus receives health briefing on every start.

  GAP 2: event_bus subscriptions table has 0 active subscribers.
         → Fix: bootstrap real subscriptions for nexus, openclaw, and
           the ontology_reasoner so the event bus actually routes work.

It also:
  - Wires the new intelligence stack (contextual_memory_compiler,
    causal_inference_engine, semantic_link_graph) into the daily schedule
  - Provides get_health_briefing() for Nexus to call at startup
  - Provides get_impact_context(entity) for any agent needing blast radius

Usage:
    python3 ontology_integration.py wire         # bootstrap subscriptions
    python3 ontology_integration.py sync         # sync predictor → shared_memory
    python3 ontology_integration.py briefing     # print full health briefing
    python3 ontology_integration.py run          # wire + sync + check
    python3 ontology_integration.py status       # show integration health

Runs as part of Nexus startup sequence.
"""
import sqlite3
import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ONTOLOGY_DB = "/Users/marcmunoz/.openclaw/data/ontology.db"
EVENTS_DB = "/Users/marcmunoz/.openclaw/data/events.db"
PREDICTION_FILE = Path.home() / ".openclaw" / "ontology" / "latest_prediction.json"

INTEGRATION_STATE_FILE = Path.home() / ".openclaw" / "data" / "integration_state.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load_integration_state() -> dict:
    try:
        return json.loads(INTEGRATION_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_integration_state(state: dict):
    INTEGRATION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    INTEGRATION_STATE_FILE.write_text(json.dumps(state, indent=2))


# ============================================================
# GAP 2 FIX: Bootstrap event_bus subscriptions
# ============================================================

# Subscriptions to create: (event_type, consumer, action)
# action is a hint for what the consumer should do when it receives this event
REQUIRED_SUBSCRIPTIONS = [
    # Nexus reads all critical events for decision-making
    ("critical_signal",       "nexus",            "evaluate_for_trade"),
    ("service_down",          "nexus",            "log_and_brief_claude"),
    ("cron_failed",           "nexus",            "check_recovery"),
    ("task_completed",        "nexus",            "update_work_queue"),
    ("task_failed",           "nexus",            "retry_or_escalate"),
    ("agent_error",           "nexus",            "diagnose_and_fix"),
    ("pipeline_blocked",      "nexus",            "alert_and_reroute"),
    ("health_score_updated",  "nexus",            "refresh_briefing"),
    ("circadian:phase_change","nexus",            "adjust_strategy"),

    # openclaw (cron executor) handles task-level events
    ("task_completed",        "openclaw",         "update_job_state"),
    ("task_failed",           "openclaw",         "mark_job_failed"),
    ("config_updated",        "openclaw",         "reload_config"),
    ("service_down",          "openclaw",         "skip_dependent_jobs"),

    # ontology_reasoner triggers on health changes
    ("service_down",          "ontology_reasoner","run_reasoning_cycle"),
    ("agent_error",           "ontology_reasoner","update_confidence"),
    ("pipeline_blocked",      "ontology_reasoner","trace_impact"),
    ("health_score_updated",  "ontology_reasoner","sync_entity_states"),

    # causal_inference_engine responds to failures
    ("service_down",          "causal_inference_engine", "predict_cascade"),
    ("cron_failed",           "causal_inference_engine", "root_cause_analysis"),
    ("agent_error",           "causal_inference_engine", "update_causal_model"),

    # Memory compiler captures all events
    ("memory:published",      "contextual_memory_compiler", "compile_incremental"),
    ("task_completed",        "contextual_memory_compiler", "compile_incremental"),
    ("task_failed",           "contextual_memory_compiler", "compile_incremental"),
]


def bootstrap_subscriptions() -> dict:
    """Create all required subscriptions in event_bus if they don't exist."""
    try:
        conn = sqlite3.connect(EVENTS_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception as e:
        return {"error": str(e), "created": 0}

    now_ts = _now()
    created = 0
    skipped = 0

    for event_type, consumer, action in REQUIRED_SUBSCRIPTIONS:
        existing = conn.execute("""
            SELECT id FROM subscriptions
            WHERE event_type = ? AND consumer = ?
        """, (event_type, consumer)).fetchone()

        if existing:
            # Ensure it's active
            conn.execute(
                "UPDATE subscriptions SET active = 1 WHERE id = ?",
                (existing["id"],)
            )
            skipped += 1
        else:
            conn.execute("""
                INSERT INTO subscriptions (event_type, consumer, action, active, created_at)
                VALUES (?, ?, ?, 1, ?)
            """, (event_type, consumer, action, now_ts))
            created += 1

    conn.commit()
    conn.close()

    state = _load_integration_state()
    state["subscriptions_bootstrapped_at"] = now_ts
    state["subscription_count"] = created + skipped
    _save_integration_state(state)

    return {"created": created, "skipped": skipped, "total": created + skipped}


# ============================================================
# GAP 1 FIX: Sync predictor output → shared_memory + event_bus
# ============================================================

def sync_prediction_to_nexus() -> dict:
    """
    Read latest_prediction.json from Jailbreak predictor.
    Publish to shared_memory and event_bus so Nexus can read it.
    """
    if not PREDICTION_FILE.exists():
        return {"error": f"Prediction file not found: {PREDICTION_FILE}"}

    try:
        prediction = json.loads(PREDICTION_FILE.read_text())
    except Exception as e:
        return {"error": f"Failed to parse prediction file: {e}"}

    # Support both field name conventions
    health_score = (prediction.get("health_score") or
                    prediction.get("system_health") or
                    prediction.get("score") or 0)
    if isinstance(health_score, dict):
        health_score = health_score.get("score", 0)
    predictions = prediction.get("predictions", [])
    risks = [p for p in predictions
             if (p.get("severity") or "").lower() in ("high", "critical")]
    timestamp = prediction.get("generated_at", _now())

    # Build compact briefing
    briefing = f"System Health: {health_score}/100"
    if risks:
        briefing += f" | {len(risks)} HIGH/CRITICAL risks"
        for r in risks[:3]:
            briefing += f"\n  [{r.get('severity','?')}] {r.get('prediction','')[:100]}"

    # Publish to event_bus
    try:
        conn = sqlite3.connect(EVENTS_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        conn.execute("""
            INSERT INTO events (event_type, source, data, priority, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "health_score_updated",
            "ontology_integration",
            json.dumps({
                "health_score": health_score,
                "risk_count": len(risks),
                "prediction_count": len(predictions),
                "briefing": briefing,
                "generated_at": timestamp,
            }),
            2,  # high priority
            _now(),
            expires_at,
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        return {"error": f"Failed to publish to event_bus: {e}"}

    # Write to shared_memory log
    try:
        import hashlib
        log_path = Path("/Users/marcmunoz/.openclaw/data/shared_memory.jsonl")
        entry = {
            "id": hashlib.md5(f"health:{timestamp}".encode()).hexdigest()[:12],
            "topic": "system_health",
            "content": briefing,
            "source": "ontology_integration",
            "tags": ["health", "prediction", "system"],
            "timestamp": _now(),
            "health_score": health_score,
        }
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        pass  # Non-fatal

    # Also update entity states in ontology.db for the top risky components
    try:
        ont_conn = sqlite3.connect(ONTOLOGY_DB, timeout=5)
        ont_conn.row_factory = sqlite3.Row
        ont_conn.execute("PRAGMA journal_mode=WAL")
        now_ts = _now()

        # Ensure entity_state table exists
        ont_conn.execute("""
            CREATE TABLE IF NOT EXISTS entity_state (
                entity_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (entity_id, key)
            )
        """)
        ont_conn.execute("""
            CREATE TABLE IF NOT EXISTS active_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT,
                prediction TEXT,
                confidence REAL,
                severity TEXT,
                evidence TEXT,
                recommended_action TEXT,
                source TEXT,
                created_at TEXT,
                expires_at TEXT
            )
        """)
        ont_conn.commit()

        # Write system-level health state
        ont_conn.execute("""
            INSERT OR REPLACE INTO entity_state
            (entity_id, key, value, source, confidence, updated_at)
            VALUES ('system', 'health_score', ?, 'predictor', ?, ?)
        """, (str(health_score), health_score / 100, now_ts))

        # Write top predictions
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        for pred in risks[:10]:
            component = pred.get("component", "system")
            entity_id = component.lower().replace(" ", "_").replace("-", "_")
            ont_conn.execute("""
                INSERT INTO active_predictions
                (entity_id, prediction, confidence, severity, evidence, recommended_action,
                 source, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, 'predictor', ?, ?)
            """, (
                entity_id,
                pred.get("prediction", "")[:500],
                pred.get("confidence", 0.5),
                pred.get("severity", "WARNING"),
                json.dumps(pred.get("evidence", {})),
                pred.get("recommendation", "")[:300],
                now_ts, expires_at,
            ))

        ont_conn.commit()
        ont_conn.close()
    except Exception as e:
        pass  # Non-fatal

    state = _load_integration_state()
    state["last_prediction_sync"] = _now()
    state["last_health_score"] = health_score
    _save_integration_state(state)

    return {
        "health_score": health_score,
        "predictions_synced": len(predictions),
        "risks_synced": len(risks),
        "briefing": briefing,
    }


# ============================================================
# Health briefing for Nexus startup
# ============================================================

def get_health_briefing() -> dict:
    """
    Returns a structured health briefing for Nexus to use at startup.
    Aggregates: predictor health score, active predictions, causal predictions,
    divergent entity pairs, and recent critical events.
    """
    briefing = {
        "generated_at": _now(),
        "health_score": None,
        "active_predictions": [],
        "causal_risks": [],
        "divergent_pairs": [],
        "recent_critical_events": [],
        "subscriptions_active": 0,
    }

    # Health score from latest prediction
    try:
        prediction = json.loads(PREDICTION_FILE.read_text())
        hs = (prediction.get("health_score") or prediction.get("system_health") or
              prediction.get("score") or 0)
        briefing["health_score"] = hs.get("score", 0) if isinstance(hs, dict) else hs
        preds = prediction.get("predictions", [])
        high_risk = [p for p in preds if p.get("severity") in ("HIGH", "CRITICAL")]
        briefing["active_predictions"] = high_risk[:10]
    except Exception:
        pass

    # Active predictions from ontology.db
    try:
        ont_conn = sqlite3.connect(ONTOLOGY_DB, timeout=3)
        ont_conn.row_factory = sqlite3.Row
        rows = ont_conn.execute("""
            SELECT * FROM active_predictions
            WHERE expires_at > ? AND LOWER(severity) IN ('high', 'critical', 'warning')
            ORDER BY confidence DESC LIMIT 10
        """, (_now(),)).fetchall()
        ont_conn.close()
        for r in rows:
            briefing["active_predictions"].append({
                "entity": r["entity_id"],
                "prediction": r["prediction"],
                "confidence": r["confidence"],
                "severity": r["severity"],
                "action": r["recommended_action"],
            })
    except Exception:
        pass

    # Causal cascade predictions
    try:
        causal_conn = sqlite3.connect(
            "/Users/marcmunoz/.openclaw/data/causal_model.db", timeout=3
        )
        causal_conn.row_factory = sqlite3.Row
        rows = causal_conn.execute("""
            SELECT * FROM causal_predictions
            WHERE status = 'pending' AND confidence >= 0.4
            ORDER BY confidence DESC LIMIT 5
        """).fetchall()
        causal_conn.close()
        briefing["causal_risks"] = [dict(r) for r in rows]
    except Exception:
        pass

    # Divergent entity pairs
    try:
        sem_conn = sqlite3.connect(
            "/Users/marcmunoz/.openclaw/data/semantic_graph.db", timeout=3
        )
        sem_conn.row_factory = sqlite3.Row
        rows = sem_conn.execute("""
            SELECT * FROM divergence_alerts
            WHERE resolved_at IS NULL
            ORDER BY divergence_score DESC LIMIT 5
        """).fetchall()
        sem_conn.close()
        briefing["divergent_pairs"] = [dict(r) for r in rows]
    except Exception:
        pass

    # Recent critical events
    try:
        ev_conn = sqlite3.connect(EVENTS_DB, timeout=3)
        ev_conn.row_factory = sqlite3.Row
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        rows = ev_conn.execute("""
            SELECT event_type, source, data, created_at FROM events
            WHERE created_at >= ? AND priority >= 2
            ORDER BY created_at DESC LIMIT 10
        """, (cutoff,)).fetchall()
        ev_conn.close()
        briefing["recent_critical_events"] = [dict(r) for r in rows]
    except Exception:
        pass

    # Subscription count
    try:
        ev_conn = sqlite3.connect(EVENTS_DB, timeout=3)
        ev_conn.row_factory = sqlite3.Row
        count = ev_conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE active = 1"
        ).fetchone()[0]
        ev_conn.close()
        briefing["subscriptions_active"] = count
    except Exception:
        pass

    return briefing


def get_impact_context(entity: str) -> dict:
    """
    For a given entity, return full impact context:
    - Ontology blast radius (trace_impact)
    - Causal cascade predictions
    - Semantically related entities
    - Root cause analysis
    """
    context = {"entity": entity}

    # Ontology blast radius
    try:
        sys.path.insert(0, "/Users/marcmunoz/n8n-workflows")
        from ontology import trace_impact
        chains = trace_impact(entity, max_depth=4)
        context["blast_radius"] = chains[:10]
    except Exception as e:
        context["blast_radius"] = []

    # Causal cascade
    try:
        from causal_inference_engine import predict_cascade
        preds = predict_cascade(entity)
        context["causal_cascade"] = preds[:5]
    except Exception:
        context["causal_cascade"] = []

    # Semantic neighbors
    try:
        from semantic_link_graph import get_related
        related = get_related(entity, top_k=5)
        context["semantic_neighbors"] = related
    except Exception:
        context["semantic_neighbors"] = []

    # Root causes
    try:
        from causal_inference_engine import root_cause_analysis
        causes = root_cause_analysis(entity)
        context["root_causes"] = causes[:5]
    except Exception:
        context["root_causes"] = []

    return context


# ============================================================
# Daily intelligence stack run
# ============================================================

def run_intelligence_stack() -> dict:
    """
    Run the full intelligence stack in dependency order:
    1. contextual_memory_compiler (needs: system_brain, event_bus)
    2. causal_inference_engine (needs: contextual_memories, ontology)
    3. semantic_link_graph (needs: ontology, causal_model)
    4. sync predictor → nexus
    """
    results = {}
    base = "/Users/marcmunoz/n8n-workflows"

    # 1. Memory compiler
    try:
        from contextual_memory_compiler import compile as mem_compile
        r = mem_compile(incremental=True)
        results["memory_compiler"] = r
    except Exception as e:
        results["memory_compiler"] = {"error": str(e)}

    # 2. Causal inference
    try:
        from causal_inference_engine import run as causal_run
        r = causal_run(bootstrap=False)
        results["causal_engine"] = r
    except Exception as e:
        results["causal_engine"] = {"error": str(e)}

    # 3. Semantic graph
    try:
        from semantic_link_graph import build as sem_build
        r = sem_build()
        results["semantic_graph"] = r
    except Exception as e:
        results["semantic_graph"] = {"error": str(e)}

    # 4. Sync predictor
    r = sync_prediction_to_nexus()
    results["predictor_sync"] = r

    return results


# ============================================================
# Status check
# ============================================================

def status() -> dict:
    result = {}

    # Subscriptions
    try:
        conn = sqlite3.connect(EVENTS_DB, timeout=3)
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE active=1").fetchone()[0]
        by_consumer = {r["consumer"]: r["cnt"] for r in conn.execute(
            "SELECT consumer, COUNT(*) as cnt FROM subscriptions WHERE active=1 GROUP BY consumer"
        ).fetchall()}
        conn.close()
        result["subscriptions"] = {
            "total": total,
            "active": active,
            "gap_fixed": active > 0,
            "by_consumer": by_consumer,
        }
    except Exception as e:
        result["subscriptions"] = {"error": str(e)}

    # Predictor sync
    state = _load_integration_state()
    last_sync = state.get("last_prediction_sync")
    last_score = state.get("last_health_score")
    result["predictor_sync"] = {
        "last_synced": last_sync,
        "last_health_score": last_score,
        "gap_fixed": last_sync is not None,
        "prediction_file_exists": PREDICTION_FILE.exists(),
    }

    # L2 entity_state in ontology.db
    try:
        ont_conn = sqlite3.connect(ONTOLOGY_DB, timeout=3)
        ont_conn.row_factory = sqlite3.Row
        tables = [r[0] for r in ont_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        has_state = "entity_state" in tables
        has_preds = "active_predictions" in tables
        state_count = ont_conn.execute("SELECT COUNT(*) FROM entity_state").fetchone()[0] if has_state else 0
        pred_count = ont_conn.execute("SELECT COUNT(*) FROM active_predictions").fetchone()[0] if has_preds else 0
        ont_conn.close()
        result["ontology_l2"] = {
            "entity_state_table": has_state,
            "active_predictions_table": has_preds,
            "state_entries": state_count,
            "active_predictions": pred_count,
        }
    except Exception as e:
        result["ontology_l2"] = {"error": str(e)}

    # New module DBs
    for name, db_path in [
        ("contextual_memories", "/Users/marcmunoz/.openclaw/data/contextual_memories.db"),
        ("causal_model", "/Users/marcmunoz/.openclaw/data/causal_model.db"),
        ("semantic_graph", "/Users/marcmunoz/.openclaw/data/semantic_graph.db"),
    ]:
        try:
            if Path(db_path).exists():
                size_kb = Path(db_path).stat().st_size // 1024
                result[name] = {"exists": True, "size_kb": size_kb}
            else:
                result[name] = {"exists": False}
        except Exception:
            result[name] = {"exists": False}

    return result


# ============================================================
# CLI
# ============================================================

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"

    if cmd == "wire":
        print("Bootstrapping event_bus subscriptions...")
        result = bootstrap_subscriptions()
        print(f"  Created: {result['created']}")
        print(f"  Skipped (already active): {result['skipped']}")
        print(f"  Total active: {result['total']}")

    elif cmd == "sync":
        print("Syncing predictor output to Nexus...")
        result = sync_prediction_to_nexus()
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  Health score: {result['health_score']}/100")
            print(f"  Predictions synced: {result['predictions_synced']}")
            print(f"  High/critical risks: {result['risks_synced']}")
            print(f"\n  Briefing:")
            for line in result['briefing'].split('\n'):
                print(f"  {line}")

    elif cmd == "briefing":
        briefing = get_health_briefing()
        print(f"System Health Briefing — {briefing['generated_at'][:19]}")
        print("=" * 60)
        print(f"  Health Score: {briefing['health_score']}/100")
        print(f"  Active Subscriptions: {briefing['subscriptions_active']}")

        if briefing["active_predictions"]:
            print(f"\n  Active Predictions ({len(briefing['active_predictions'])}):")
            for p in briefing["active_predictions"][:5]:
                pred_text = p.get("prediction") or p.get("prediction", "")
                sev = p.get("severity", "?")
                print(f"    [{sev}] {pred_text[:120]}")

        if briefing["causal_risks"]:
            print(f"\n  Causal Cascade Risks ({len(briefing['causal_risks'])}):")
            for r in briefing["causal_risks"][:3]:
                print(f"    {r.get('trigger_entity','?')} → {r.get('predicted_entity','?')} "
                      f"(conf={r.get('confidence',0):.2f})")

        if briefing["divergent_pairs"]:
            print(f"\n  Divergent Entity Pairs ({len(briefing['divergent_pairs'])}):")
            for d in briefing["divergent_pairs"][:3]:
                print(f"    {d.get('entity_a')} ({d.get('state_a')}) ↔ "
                      f"{d.get('entity_b')} ({d.get('state_b')})")

    elif cmd == "run":
        print("Wiring subscriptions...")
        sub_result = bootstrap_subscriptions()
        print(f"  Subscriptions: {sub_result['created']} created, {sub_result['skipped']} active")

        print("Syncing predictor output...")
        sync_result = sync_prediction_to_nexus()
        if "error" in sync_result:
            print(f"  Sync error: {sync_result['error']}")
        else:
            print(f"  Health: {sync_result['health_score']}/100 | "
                  f"Risks: {sync_result['risks_synced']}")

        print("Running intelligence stack...")
        stack_result = run_intelligence_stack()
        for component, r in stack_result.items():
            if "error" in (r or {}):
                print(f"  {component}: ERROR - {r['error']}")
            else:
                print(f"  {component}: OK")

    elif cmd == "status":
        s = status()
        print("Integration Status")
        print("=" * 50)

        sub = s.get("subscriptions", {})
        sub_fixed = sub.get("gap_fixed", False)
        print(f"  [{'OK' if sub_fixed else 'GAP'}] Event bus subscriptions: "
              f"{sub.get('active', 0)} active")
        if sub.get("by_consumer"):
            for consumer, cnt in sub["by_consumer"].items():
                print(f"       {consumer}: {cnt} subscriptions")

        pred = s.get("predictor_sync", {})
        pred_fixed = pred.get("gap_fixed", False)
        print(f"  [{'OK' if pred_fixed else 'GAP'}] Predictor → Nexus sync: "
              f"last={pred.get('last_synced', 'never')[:19] if pred.get('last_synced') else 'never'} "
              f"score={pred.get('last_health_score', '?')}")

        l2 = s.get("ontology_l2", {})
        print(f"  [{'OK' if l2.get('entity_state_table') else 'MISSING'}] L2 entity_state: "
              f"{l2.get('state_entries', 0)} entries | "
              f"{l2.get('active_predictions', 0)} predictions")

        for name in ["contextual_memories", "causal_model", "semantic_graph"]:
            info = s.get(name, {})
            exists = info.get("exists", False)
            print(f"  [{'OK' if exists else 'MISSING'}] {name}: "
                  f"{info.get('size_kb', 0)}KB" if exists else f"  [MISSING] {name}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
