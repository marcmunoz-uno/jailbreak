#!/usr/bin/env python3
"""
bootstrap_layers.py -- Populate L1/L2/L3 from existing ontology JSON files.

Reads the 12 ontology JSON files at ~/.openclaw/ontology/ and populates:
  - dependency_graph.json      -> L1 nodes + edges
  - failure_cascades.json      -> L1 patterns
  - correlations.json          -> L1 patterns
  - recovery_patterns.json     -> L1 patterns
  - risk_scores.json           -> L2 entity_state
  - cron_health_timeline.json  -> L2 entity_state + L3 timeseries seed
  - data_freshness.json        -> L2 entity_state
  - config_drift.json          -> L2 entity_state
  - error_taxonomy.json        -> L2 entity_state
  - agent_interactions.json    -> L1 nodes + edges
  - enhancement_opportunities.json -> L2 active_predictions

Usage:
    python3 bootstrap_layers.py
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ontology_api import OntologyStack, _connect, L1_DB, L2_DB, L3_DB, _now

ONTOLOGY_DIR = "/Users/marcmunoz/.openclaw/ontology"


def _load_json(filename):
    path = os.path.join(ONTOLOGY_DIR, filename)
    if not os.path.exists(path):
        print(f"  [SKIP] {filename} not found")
        return None
    with open(path, "r") as f:
        return json.load(f)


def bootstrap_dependency_graph(conn_l1):
    """dependency_graph.json -> L1 nodes + edges"""
    data = _load_json("dependency_graph.json")
    if not data:
        return

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    count_n = 0
    for node in nodes:
        nid = node["id"]
        ntype = node.get("type", "unknown")
        name = node.get("name", nid)
        critical = 1 if node.get("critical", False) else 0

        # Everything except id/type/name/critical goes to properties
        props = {k: v for k, v in node.items() if k not in ("id", "type", "name", "critical")}

        conn_l1.execute("""
            INSERT OR REPLACE INTO nodes (id, type, name, properties, critical)
            VALUES (?, ?, ?, ?, ?)
        """, (nid, ntype, name, json.dumps(props) if props else None, critical))
        count_n += 1

    count_e = 0
    for edge in edges:
        from_id = edge["from"]
        to_id = edge["to"]
        edge_type = edge["type"]
        metadata = {k: v for k, v in edge.items() if k not in ("from", "to", "type")}

        conn_l1.execute("""
            INSERT OR REPLACE INTO edges (from_id, to_id, edge_type, metadata)
            VALUES (?, ?, ?, ?)
        """, (from_id, to_id, edge_type, json.dumps(metadata) if metadata else None))
        count_e += 1

    conn_l1.commit()
    print(f"  [OK] dependency_graph.json -> {count_n} nodes, {count_e} edges")


def bootstrap_failure_cascades(conn_l1):
    """failure_cascades.json -> L1 patterns"""
    data = _load_json("failure_cascades.json")
    if not data:
        return

    cascades = data.get("cascades", [])
    count = 0
    for c in cascades:
        trigger = c.get("trigger", "unknown")
        affected = c.get("downstream_failures", [])
        desc = c.get("description", "")
        metadata = {
            "frequency": c.get("frequency"),
            "severity": c.get("severity"),
            "time_to_cascade_minutes": c.get("time_to_cascade_minutes"),
            "pattern": c.get("pattern"),
            "example_timestamps": c.get("example_timestamps", []),
        }
        last_obs = c.get("example_timestamps", [None])[-1]

        conn_l1.execute("""
            INSERT INTO patterns (pattern_type, trigger_entity, affected_entities, description, metadata, last_observed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("cascade", trigger, json.dumps(affected), desc,
              json.dumps(metadata), last_obs))
        count += 1

    conn_l1.commit()
    print(f"  [OK] failure_cascades.json -> {count} cascade patterns")


def bootstrap_correlations(conn_l1):
    """correlations.json -> L1 patterns"""
    data = _load_json("correlations.json")
    if not data:
        return

    correlations = data.get("correlations", [])
    count = 0
    for c in correlations:
        trigger = c.get("component_a", "unknown")
        affected = [c.get("component_b", "unknown")]
        desc = c.get("explanation", "")
        metadata = {
            "correlation": c.get("correlation"),
            "type": c.get("type"),
            "lag_minutes": c.get("lag_minutes"),
            "evidence": c.get("evidence"),
        }

        conn_l1.execute("""
            INSERT INTO patterns (pattern_type, trigger_entity, affected_entities, description, metadata, last_observed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("correlation", trigger, json.dumps(affected), desc,
              json.dumps(metadata), data.get("timestamp")))
        count += 1

    conn_l1.commit()
    print(f"  [OK] correlations.json -> {count} correlation patterns")


def bootstrap_recovery_patterns(conn_l1):
    """recovery_patterns.json -> L1 patterns"""
    data = _load_json("recovery_patterns.json")
    if not data:
        return

    patterns = data.get("patterns", [])
    count = 0
    for p in patterns:
        trigger = p.get("applicable_to", ["unknown"])[0] if p.get("applicable_to") else "unknown"
        affected = p.get("applicable_to", [])
        desc = f"Problem: {p.get('problem', '')} | Fix: {p.get('fix', '')}"
        metadata = {
            "severity": p.get("severity"),
            "confidence": p.get("confidence"),
            "recurred": p.get("recurred"),
            "recurrence_details": p.get("recurrence_details"),
            "fabric_refs": p.get("fabric_refs", []),
        }

        conn_l1.execute("""
            INSERT INTO patterns (pattern_type, trigger_entity, affected_entities, description, metadata, last_observed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("recovery", trigger, json.dumps(affected), desc,
              json.dumps(metadata), p.get("date")))
        count += 1

    conn_l1.commit()
    print(f"  [OK] recovery_patterns.json -> {count} recovery patterns")


def bootstrap_risk_scores(conn_l2):
    """risk_scores.json -> L2 entity_state"""
    data = _load_json("risk_scores.json")
    if not data:
        return

    components = data.get("components", [])
    now = _now()
    count = 0
    for c in components:
        eid = c.get("id", "unknown")

        # Risk score
        conn_l2.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (eid, "risk_score", str(c.get("risk_score", 0)), "risk_scores.json", 1.0, now))

        # Trend
        conn_l2.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (eid, "trend", c.get("trend", "unknown"), "risk_scores.json", 1.0, now))

        # Predicted failure
        if c.get("predicted_failure"):
            conn_l2.execute("""
                INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, "predicted_failure", c["predicted_failure"], "risk_scores.json", 0.8, now))

        # Store factors as combined state
        if c.get("factors"):
            conn_l2.execute("""
                INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, "risk_factors", json.dumps(c["factors"]), "risk_scores.json", 1.0, now))

        count += 1

    conn_l2.commit()
    print(f"  [OK] risk_scores.json -> {count} entities with risk scores")


def bootstrap_cron_health(conn_l2, conn_l3):
    """cron_health_timeline.json -> L2 entity_state + L3 timeseries seed"""
    data = _load_json("cron_health_timeline.json")
    if not data:
        return

    jobs = data.get("jobs", [])
    now = _now()
    count_l2 = 0
    count_l3 = 0

    for job in jobs:
        name = job.get("name", "unknown")
        job_id = job.get("job_id", "unknown")
        # Try to match to a cron: entity ID
        eid = _job_name_to_entity_id(name)

        # L2: entity state
        for key in ("error_rate", "health_score", "avg_duration_seconds"):
            val = job.get(key)
            if val is not None:
                conn_l2.execute("""
                    INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (eid, key, str(val), "cron_health_timeline.json", 1.0, now))
                count_l2 += 1

        for key in ("duration_trend", "error_trend", "prediction"):
            val = job.get(key)
            if val is not None:
                conn_l2.execute("""
                    INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (eid, key, str(val), "cron_health_timeline.json", 1.0, now))

        # L3: timeseries seed from current snapshot values
        for metric in ("error_rate", "health_score", "avg_duration_seconds"):
            val = job.get(metric)
            if val is not None:
                try:
                    numeric = float(val)
                    conn_l3.execute("""
                        INSERT INTO timeseries (entity_id, metric, value, recorded_at)
                        VALUES (?, ?, ?, ?)
                    """, (eid, metric, numeric, now))
                    count_l3 += 1
                except (ValueError, TypeError):
                    pass

    conn_l2.commit()
    conn_l3.commit()
    print(f"  [OK] cron_health_timeline.json -> {count_l2} L2 states, {count_l3} L3 timeseries points")


def bootstrap_data_freshness(conn_l2):
    """data_freshness.json -> L2 entity_state"""
    data = _load_json("data_freshness.json")
    if not data:
        return

    sources = data.get("data_sources", [])
    now = _now()
    count = 0
    for s in sources:
        path = s.get("path", "unknown")
        # Derive entity_id from path or use data: prefix
        eid = _path_to_entity_id(path)

        conn_l2.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (eid, "freshness_status", s.get("status", "unknown"), "data_freshness.json", 1.0, now))

        conn_l2.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (eid, "actual_age_hours", str(s.get("actual_age_hours", 0)), "data_freshness.json", 1.0, now))

        conn_l2.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (eid, "expected_freshness_hours", str(s.get("expected_freshness_hours", 24)), "data_freshness.json", 1.0, now))

        if s.get("producer"):
            conn_l2.execute("""
                INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, "producer", s["producer"], "data_freshness.json", 1.0, now))

        if s.get("note"):
            conn_l2.execute("""
                INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, "freshness_note", s["note"], "data_freshness.json", 1.0, now))

        count += 1

    conn_l2.commit()
    print(f"  [OK] data_freshness.json -> {count} data sources with freshness state")


def bootstrap_config_drift(conn_l2):
    """config_drift.json -> L2 entity_state"""
    data = _load_json("config_drift.json")
    if not data:
        return

    configs = data.get("configs", [])
    now = _now()
    count = 0
    for c in configs:
        path = c.get("path", "unknown")
        eid = _path_to_entity_id(path)

        conn_l2.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (eid, "drift_detected", str(c.get("drift_detected", False)), "config_drift.json", 1.0, now))

        risk = c.get("overall_risk") or c.get("risk", "unknown")
        conn_l2.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (eid, "config_risk", risk, "config_drift.json", 1.0, now))

        conn_l2.execute("""
            INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (eid, "backup_count", str(c.get("backup_count", 0)), "config_drift.json", 1.0, now))

        if c.get("summary"):
            conn_l2.execute("""
                INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, "drift_summary", c["summary"], "config_drift.json", 1.0, now))
        elif c.get("notes"):
            conn_l2.execute("""
                INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, "drift_summary", c["notes"], "config_drift.json", 1.0, now))

        count += 1

    conn_l2.commit()
    print(f"  [OK] config_drift.json -> {count} configs with drift state")


def bootstrap_error_taxonomy(conn_l2):
    """error_taxonomy.json -> L2 entity_state"""
    data = _load_json("error_taxonomy.json")
    if not data:
        return

    error_classes = data.get("error_classes", [])
    now = _now()
    count = 0
    for ec in error_classes:
        error_class = ec.get("class", "unknown")
        affected = ec.get("affected_components", [])

        # Store each error class as state on each affected component
        for comp in affected:
            # Normalize component name to entity_id format
            eid = _component_to_entity_id(comp)

            conn_l2.execute("""
                INSERT OR REPLACE INTO entity_state (entity_id, key, value, source, confidence, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, f"error:{error_class}",
                  json.dumps({
                      "occurrences": ec.get("occurrences", 0),
                      "fix_applied": ec.get("fix_applied", False),
                      "recurrence_risk": ec.get("recurrence_risk", "unknown"),
                      "remediation": ec.get("remediation", ""),
                  }),
                  "error_taxonomy.json", 1.0, now))
            count += 1

    conn_l2.commit()
    print(f"  [OK] error_taxonomy.json -> {count} error states across components")


def bootstrap_agent_interactions(conn_l1):
    """agent_interactions.json -> L1 nodes + edges"""
    data = _load_json("agent_interactions.json")
    if not data:
        return

    agents = data.get("agents", [])
    channels = data.get("channels", [])
    now = _now()

    count_n = 0
    count_e = 0

    # Add agent nodes
    for agent in agents:
        aid = f"agent:{agent['id']}"
        props = {
            "role": agent.get("role"),
            "frequency": agent.get("frequency"),
            "model": agent.get("model"),
        }
        if agent.get("max_actions_per_cycle"):
            props["max_actions_per_cycle"] = agent["max_actions_per_cycle"]
        if agent.get("max_tasks_per_day"):
            props["max_tasks_per_day"] = agent["max_tasks_per_day"]

        conn_l1.execute("""
            INSERT OR REPLACE INTO nodes (id, type, name, properties, critical)
            VALUES (?, ?, ?, ?, ?)
        """, (aid, "agent", agent.get("id"), json.dumps(props), 1))
        count_n += 1

        # Parse talks_to for edges
        for talk in agent.get("talks_to", []):
            # Extract the target name (before parenthesis)
            target = talk.split("(")[0].strip().split(" ")[0].strip()
            target_id = f"channel:{target}"

            conn_l1.execute("""
                INSERT OR REPLACE INTO edges (from_id, to_id, edge_type, metadata)
                VALUES (?, ?, ?, ?)
            """, (aid, target_id, "communicates", json.dumps({"detail": talk})))
            count_e += 1

    # Add channel nodes
    for ch in channels:
        cid = f"channel:{ch['id']}"
        props = {
            "type": ch.get("type"),
            "protocol": ch.get("protocol"),
        }
        if ch.get("path"):
            props["path"] = ch["path"]

        conn_l1.execute("""
            INSERT OR REPLACE INTO nodes (id, type, name, properties, critical)
            VALUES (?, ?, ?, ?, ?)
        """, (cid, "channel", ch.get("id"), json.dumps(props), 1))
        count_n += 1

        # Add producer/consumer edges
        for producer in ch.get("producers", []):
            pid = f"agent:{producer}" if not producer.startswith("agent:") else producer
            conn_l1.execute("""
                INSERT OR REPLACE INTO edges (from_id, to_id, edge_type, metadata)
                VALUES (?, ?, ?, ?)
            """, (pid, cid, "produces_to", None))
            count_e += 1

        for consumer in ch.get("consumers", []):
            coid = f"agent:{consumer}" if not consumer.startswith("agent:") else consumer
            conn_l1.execute("""
                INSERT OR REPLACE INTO edges (from_id, to_id, edge_type, metadata)
                VALUES (?, ?, ?, ?)
            """, (coid, cid, "consumes_from", None))
            count_e += 1

    conn_l1.commit()
    print(f"  [OK] agent_interactions.json -> {count_n} nodes, {count_e} edges")


def bootstrap_enhancement_opportunities(conn_l2):
    """enhancement_opportunities.json -> L2 active_predictions"""
    data = _load_json("enhancement_opportunities.json")
    if not data:
        return

    opportunities = data.get("opportunities", [])
    now = _now()
    count = 0
    for opp in opportunities:
        comp = opp.get("component", "system:unknown")
        # Normalize to entity_id
        eid = _component_to_entity_id(comp)

        conn_l2.execute("""
            INSERT INTO active_predictions
            (entity_id, prediction, confidence, severity, evidence, recommended_action, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            eid,
            opp.get("observation", ""),
            0.8 if opp.get("priority") == "high" else 0.6 if opp.get("priority") == "medium" else 0.4,
            opp.get("priority", "medium"),
            json.dumps({"category": opp.get("category"), "effort": opp.get("effort")}),
            opp.get("recommendation", ""),
            "enhancement_opportunities.json",
            now,
        ))
        count += 1

    conn_l2.commit()
    print(f"  [OK] enhancement_opportunities.json -> {count} active predictions")


# ================================================================
# Entity ID normalization helpers
# ================================================================

# Map common cron job names to dependency_graph entity IDs
_CRON_NAME_MAP = {
    "daily motivated seller pipeline": "cron:motivated-seller",
    "generate parse.bot api key": "cron:parsebot-scraper",
    "seller financing outreach agent": "cron:seller-financing-outreach",
    "twitter auto-post (midday)": "cron:twitter-midday",
    "twitter auto-post (morning)": "cron:twitter-morning",
    "enhanced knowledge graph maintenance": "cron:knowledge-graph",
    "dashboard data refresh": "cron:daily-dashboard-refresh",
    "daily tranchi property upload": "cron:daily-tranchi-upload",
    "escalation alerter": "cron:escalation-alerter",
    "pattern detection scanner": "cron:pattern-detection",
    "total recall reflector": "cron:total-recall-reflector",
    "daily cash-flowing deals email (25%+ coc)": "cron:daily-deal-email",
    "dscr multi-touch outreach sequence": "cron:dscr-multi-touch",
    "memory maintenance": "cron:memory-maintenance",
    "morning briefing": "cron:morning-briefing",
    "daily dscr lead generation": "cron:dscr-lead-gen",
    "dscr lead outreach - pilot (25/day)": "cron:dscr-outreach-pilot",
    "glint market monitor": "cron:glint-monitor",
    "dscr lead pipeline (daily)": "cron:dscr-lead-pipeline",
    "evening revenue report": "cron:evening-revenue-report",
    "daily lead csv for propstream skip trace": "cron:daily-lead-csv",
    "kalshi arbitrage scanner": "cron:kalshi-scanner",
    "paper trading monitor": "cron:paper-trading",
    "situation monitor - geopolitical edge scanner": "cron:situation-monitor",
    "memecoin scanner": "cron:memecoin-scanner",
    "polymarket scanner": "cron:polymarket-scanner",
    "total recall observer": "cron:total-recall-observer",
    "quantitative trading research agent": "cron:quant-research",
    "nexus - autonomous coordinator": "cron:nexus-coordinator",
    "scout - proactive improvement finder": "cron:scout-loop",
    "memory server health monitor": "cron:memory-health",
    "fix verification checker": "cron:fix-verifier",
    "mirofish simulation engine": "cron:mirofish",
    "trading system watchdog": "cron:trading-watchdog",
    "trade resolution pipeline": "cron:trade-resolution",
    "critical job health monitor": "cron:critical-health",
    "daily-dashboard-refresh": "cron:daily-dashboard-refresh",
}


def _job_name_to_entity_id(name):
    """Convert a cron job name to a cron: entity ID."""
    lower = name.lower().strip()
    if lower in _CRON_NAME_MAP:
        return _CRON_NAME_MAP[lower]
    # Fallback: slugify
    slug = lower.replace(" ", "-").replace("(", "").replace(")", "").replace("/", "-")
    return f"cron:{slug}"


def _path_to_entity_id(path):
    """Convert a file path to a data: or config: entity ID."""
    # Check if it matches known config entities
    known_configs = {
        "/Users/marcmunoz/.openclaw/openclaw.json": "config:openclaw.json",
        "/Users/marcmunoz/.openclaw/cron/jobs.json": "config:jobs.json",
        "/Users/marcmunoz/.mcp.json": "config:mcp.json",
        "/Users/marcmunoz/n8n-workflows/outcome_config.json": "config:outcome_config.json",
    }
    if path in known_configs:
        return known_configs[path]

    # Check known data entities
    known_data = {
        "glint_latest": "data:glint_latest",
        "kalshi_scan": "data:kalshi_scan",
        "dscr_leads": "data:dscr_leads",
        "dscr_traced": "data:dscr_traced",
        "dscr_emails": "data:dscr_emails",
        "cron-ledger": "data:cron_ledger",
        "observations": "data:observations",
        "shared_memory": "data:shared_memory_log",
        "unified_portfolio": "data:unified_portfolio",
        "unified_scorecard": "data:unified_scorecard",
        "paper_portfolio": "data:paper_portfolio",
    }
    basename = os.path.basename(path).split(".")[0] if "(" not in path else path.split("/")[-1].split(".")[0]
    for key, eid in known_data.items():
        if key in path.lower():
            return eid

    # Fallback
    return f"data:{basename}"


def _component_to_entity_id(comp):
    """Normalize a component name to an entity ID."""
    # Already looks like an entity_id
    if ":" in comp and not comp.startswith("/"):
        return comp

    # Map common component names
    comp_map = {
        "glint-monitor": "cron:glint-monitor",
        "kalshi-resolver": "cron:kalshi-scanner",
        "mirofish": "cron:mirofish",
        "quant-research": "cron:quant-research",
        "trade-engine": "cron:paper-trading",
        "cron-scheduler": "service:openclaw-gateway",
        "telegram": "plugin:telegram",
        "session-manager": "service:openclaw-gateway",
        "agent-embedded": "service:openclaw-gateway",
        "tools": "service:openclaw-gateway",
        "config-reloader": "config:openclaw.json",
        "observer": "cron:total-recall-observer",
        "reflector": "cron:total-recall-reflector",
        "gov-tax-deed-scraper": "cron:tax-deed-scanner",
        "quant-research-trade-engine": "cron:quant-research",
    }
    lower = comp.lower().strip()
    if lower in comp_map:
        return comp_map[lower]

    # Handle enhancement_opportunities component format like "logs:agent-memory-server.log"
    if comp.startswith("logs:"):
        return f"data:{comp}"
    if comp.startswith("data:"):
        return comp
    if comp.startswith("cron:"):
        return comp
    if comp.startswith("service:"):
        return comp
    if comp.startswith("config:"):
        return comp
    if comp.startswith("system:"):
        return comp
    if comp.startswith("workspace:"):
        return comp

    return f"component:{lower}"


# ================================================================
# Main bootstrap
# ================================================================

def main():
    print("=" * 60)
    print("Ontology Bootstrap: Populating L1/L2/L3 from JSON files")
    print("=" * 60)

    # Initialize the stack (creates DBs and tables)
    stack = OntologyStack()

    # Open connections
    conn_l1 = _connect(L1_DB)
    conn_l2 = _connect(L2_DB)
    conn_l3 = _connect(L3_DB)

    print("\n--- L1: Static Structure ---")
    bootstrap_dependency_graph(conn_l1)
    bootstrap_failure_cascades(conn_l1)
    bootstrap_correlations(conn_l1)
    bootstrap_recovery_patterns(conn_l1)
    bootstrap_agent_interactions(conn_l1)

    print("\n--- L2: Dynamic State ---")
    bootstrap_risk_scores(conn_l2)
    bootstrap_cron_health(conn_l2, conn_l3)
    bootstrap_data_freshness(conn_l2)
    bootstrap_config_drift(conn_l2)
    bootstrap_error_taxonomy(conn_l2)
    bootstrap_enhancement_opportunities(conn_l2)

    # Close connections
    conn_l1.close()
    conn_l2.close()
    conn_l3.close()

    print("\n--- Verification ---")
    # Compute baselines from seeded L3 data
    baseline_count = stack.compute_baselines(days=30)
    print(f"  Computed {baseline_count} baselines")

    # Detect any anomalies
    anomaly_count = stack.detect_anomalies()
    print(f"  Detected {anomaly_count} anomalies")

    # Snapshot current state to L3
    snapshot_count = stack.snapshot_state()
    print(f"  Snapshotted {snapshot_count} metrics to L3 timeseries")

    print("\n--- Summary ---")
    summary = stack.get_system_summary()
    print(f"  L1: {summary['l1_topology']['total_nodes']} nodes, "
          f"{summary['l1_topology']['total_edges']} edges, "
          f"{summary['l1_topology']['total_patterns']} patterns")
    print(f"  L2: {summary['l2_tracked_entities']} entities tracked, "
          f"{len(summary['l2_high_risk'])} high-risk, "
          f"{len(summary['l2_predictions'])} predictions")
    print(f"  L3: {summary['l3_timeseries']['series_count']} time series, "
          f"{summary['l3_timeseries']['total_points']} data points, "
          f"{summary['l3_baselines_computed']} baselines")
    print(f"  Active anomalies: {len(summary['l3_active_anomalies'])}")

    print("\n  High-risk entities:")
    for hr in summary["l2_high_risk"][:10]:
        print(f"    {hr['entity_id']}: risk={hr['risk_score']}")

    print("\n" + "=" * 60)
    print("Bootstrap complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
