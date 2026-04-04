#!/usr/bin/env python3
"""
Predictive Maintenance Engine for OpenClaw.

Reads ontology files, computes real-time system health, predicts failures,
and generates actionable predictions as JSON.

Usage:
    python3 predictor.py              # Full prediction report (JSON)
    python3 predictor.py --summary    # One-line health summary
    python3 predictor.py --risks      # Top 5 risks only
    python3 predictor.py --predict    # Predictions only
"""

import json
import os
import sys
import socket
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ONTOLOGY_DIR = Path(__file__).parent
NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Ontology Loader
# ---------------------------------------------------------------------------

def load_json(filename):
    """Load a JSON ontology file, returning None on failure."""
    path = ONTOLOGY_DIR / filename
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def load_ontology():
    """Load all ontology files into a dict."""
    files = {
        "dependency_graph": "dependency_graph.json",
        "failure_cascades": "failure_cascades.json",
        "config_drift": "config_drift.json",
        "resource_contention": "resource_contention.json",
        "cron_health": "cron_health_timeline.json",
        "data_freshness": "data_freshness.json",
        "error_taxonomy": "error_taxonomy.json",
        "agent_interactions": "agent_interactions.json",
        "recovery_patterns": "recovery_patterns.json",
        "pipeline_bottlenecks": "pipeline_bottlenecks.json",
        "risk_scores": "risk_scores.json",
        "correlations": "correlations.json",
        "enhancements": "enhancement_opportunities.json",
    }
    ont = {}
    for key, fname in files.items():
        ont[key] = load_json(fname)
    return ont


# ---------------------------------------------------------------------------
# Dependency Graph Helpers
# ---------------------------------------------------------------------------

def build_dependents_map(graph):
    """Map each node id -> number of other nodes that depend on it."""
    if not graph:
        return {}
    counts = {}
    for node in graph.get("nodes", []):
        counts[node["id"]] = 0
    for edge in graph.get("edges", []):
        target = edge.get("to", "")
        if target in counts:
            counts[target] += 1
        else:
            counts[target] = 1
    return counts


def get_node_map(graph):
    """Map node id -> node dict."""
    if not graph:
        return {}
    return {n["id"]: n for n in graph.get("nodes", [])}


def criticality_weight(node, dep_count):
    """Compute a weight 0-1 for a node based on criticality and dependents."""
    base = 0.7 if node.get("critical") else 0.3
    dep_factor = min(dep_count / 20.0, 0.3)  # cap at 0.3 bonus
    return min(base + dep_factor, 1.0)


# ---------------------------------------------------------------------------
# Health Check Functions
# ---------------------------------------------------------------------------

def check_port(port, host="127.0.0.1", timeout=1.0):
    """Return True if a TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def check_file_exists(path):
    """Return True if a file exists and is non-empty."""
    try:
        p = Path(path)
        return p.exists() and p.stat().st_size > 0
    except (OSError, PermissionError):
        return False


def check_json_valid(path):
    """Return True if a file contains valid JSON."""
    try:
        with open(path, "r") as f:
            json.load(f)
        return True
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return False


def file_age_hours(path):
    """Return the age of a file in hours, or None if missing."""
    try:
        mtime = os.path.getmtime(path)
        age = (time.time() - mtime) / 3600.0
        return round(age, 1)
    except (FileNotFoundError, OSError):
        return None


# ---------------------------------------------------------------------------
# Service Health Scoring
# ---------------------------------------------------------------------------

def score_services(graph, dep_map):
    """Check each service node and return (score 0-100, details list)."""
    if not graph:
        return 100, []
    nodes = [n for n in graph.get("nodes", []) if n["type"] == "service"]
    if not nodes:
        return 100, []

    total_weight = 0.0
    weighted_score = 0.0
    details = []

    for node in nodes:
        nid = node["id"]
        port = node.get("port")
        w = criticality_weight(node, dep_map.get(nid, 0))
        total_weight += w

        up = False
        if port:
            up = check_port(port)

        if up:
            weighted_score += w
            details.append({"id": nid, "status": "up", "port": port})
        else:
            details.append({"id": nid, "status": "down", "port": port})

    if total_weight == 0:
        return 100, details
    return round(100 * weighted_score / total_weight), details


# ---------------------------------------------------------------------------
# Config Health Scoring
# ---------------------------------------------------------------------------

def score_configs(graph, dep_map, drift_data):
    """Check each config node: file exists, valid JSON, drift risk."""
    if not graph:
        return 100, []

    nodes = [n for n in graph.get("nodes", []) if n["type"] == "config"]
    if not nodes:
        return 100, []

    drift_lookup = {}
    if drift_data:
        for cfg in drift_data.get("configs", []):
            drift_lookup[cfg["path"]] = cfg

    total_weight = 0.0
    weighted_score = 0.0
    details = []

    for node in nodes:
        nid = node["id"]
        path = node.get("path", "")
        w = criticality_weight(node, dep_map.get(nid, 0))
        total_weight += w

        exists = check_file_exists(path)
        valid = check_json_valid(path) if exists else False
        drift_info = drift_lookup.get(path, {})
        drift_risk = drift_info.get("overall_risk", drift_info.get("risk", "none"))

        score = 0.0
        if exists:
            score += 0.4
        if valid:
            score += 0.4
        if drift_risk in ("none", "low"):
            score += 0.2
        elif drift_risk == "medium":
            score += 0.1

        weighted_score += w * score
        details.append({
            "id": nid,
            "exists": exists,
            "valid_json": valid,
            "drift_risk": drift_risk,
        })

    if total_weight == 0:
        return 100, details
    return round(100 * weighted_score / total_weight), details


# ---------------------------------------------------------------------------
# Cron Health Scoring
# ---------------------------------------------------------------------------

def score_cron_health(cron_data):
    """Score cron job health from cron_health_timeline."""
    if not cron_data:
        return 100, []

    jobs = cron_data.get("jobs", [])
    if not jobs:
        return 100, []

    total = 0
    total_score = 0.0
    details = []

    for job in jobs:
        hs = job.get("health_score", 10)
        total += 1
        total_score += hs
        if hs < 7:
            details.append({
                "name": job["name"],
                "health_score": hs,
                "error_rate": job.get("error_rate", 0),
                "prediction": job.get("prediction", ""),
                "duration_trend": job.get("duration_trend", "unknown"),
            })

    if total == 0:
        return 100, details
    avg = total_score / total
    return round(avg * 10), details  # scale 0-10 -> 0-100


# ---------------------------------------------------------------------------
# Data Freshness Scoring
# ---------------------------------------------------------------------------

def score_data_freshness(freshness_data, graph, dep_map):
    """Score data freshness, weighted by criticality."""
    if not freshness_data:
        return 100, []

    sources = freshness_data.get("data_sources", [])
    if not sources:
        return 100, []

    # Build a quick lookup from data path -> graph node for weighting
    node_by_path = {}
    if graph:
        for n in graph.get("nodes", []):
            p = n.get("path", "")
            if p:
                node_by_path[p] = n

    fresh_count = 0
    stale_items = []

    for src in sources:
        status = src.get("status", "fresh")
        if status == "fresh":
            fresh_count += 1
        else:
            stale_items.append({
                "path": src.get("path", "?"),
                "expected_hours": src.get("expected_freshness_hours"),
                "actual_hours": src.get("actual_age_hours"),
                "producer": src.get("producer", "unknown"),
            })

    total = len(sources)
    if total == 0:
        return 100, stale_items
    return round(100 * fresh_count / total), stale_items


# ---------------------------------------------------------------------------
# Composite System Health
# ---------------------------------------------------------------------------

def compute_health(ont):
    """Compute overall system health 0-100 from all sub-scores."""
    graph = ont.get("dependency_graph")
    dep_map = build_dependents_map(graph)

    svc_score, svc_details = score_services(graph, dep_map)
    cfg_score, cfg_details = score_configs(graph, dep_map, ont.get("config_drift"))
    cron_score, cron_details = score_cron_health(ont.get("cron_health"))
    data_score, data_details = score_data_freshness(ont.get("data_freshness"), graph, dep_map)

    # Also incorporate ontology risk score if available
    risk_data = ont.get("risk_scores")
    ont_health = risk_data.get("system_health", 58) if risk_data else 58

    # Weighted composite: services 30%, configs 15%, cron 25%, data 15%, ontology risk 15%
    composite = round(
        svc_score * 0.30
        + cfg_score * 0.15
        + cron_score * 0.25
        + data_score * 0.15
        + ont_health * 0.15
    )

    breakdown = {
        "services": {"score": svc_score, "details": svc_details},
        "configs": {"score": cfg_score, "details": cfg_details},
        "cron_jobs": {"score": cron_score, "unhealthy": cron_details},
        "data_freshness": {"score": data_score, "stale": data_details},
        "ontology_risk_score": ont_health,
    }

    return composite, breakdown


# ---------------------------------------------------------------------------
# Failure Prediction Engine
# ---------------------------------------------------------------------------

def predict_failures(ont):
    """Generate failure predictions from ontology knowledge."""
    predictions = []
    graph = ont.get("dependency_graph")
    dep_map = build_dependents_map(graph)
    node_map = get_node_map(graph)
    cascades = ont.get("failure_cascades")
    contention = ont.get("resource_contention")
    cron_data = ont.get("cron_health")
    risk_data = ont.get("risk_scores")
    correlations = ont.get("correlations")
    config_drift = ont.get("config_drift")
    bottlenecks = ont.get("pipeline_bottlenecks")
    error_tax = ont.get("error_taxonomy")

    # --- 1. Cascade predictions based on risk + known patterns ---
    if cascades and risk_data:
        risk_lookup = {}
        if risk_data:
            for comp in risk_data.get("components", []):
                risk_lookup[comp["id"]] = comp

        for cascade in cascades.get("cascades", []):
            trigger = cascade.get("trigger", "")
            severity = cascade.get("severity", "medium")
            freq = cascade.get("frequency", 0)
            downstream = cascade.get("downstream_failures", [])

            # Check if trigger conditions exist now
            confidence = min(0.3 + (freq / 200.0), 0.9)

            if freq > 20:  # Recurring pattern
                predictions.append({
                    "component": f"cascade:{trigger}",
                    "prediction": f"cascade risk: {cascade.get('description', trigger)[:80]}",
                    "confidence": round(confidence, 2),
                    "evidence": [
                        f"observed {freq} times historically",
                        f"affects {len(downstream)} downstream components",
                        cascade.get("pattern", "")[:100],
                    ],
                    "recommended_action": f"stagger jobs to avoid simultaneous trigger; monitor {trigger}",
                    "severity": severity,
                })

    # --- 2. Resource contention window warnings ---
    if contention:
        current_hour = NOW.hour
        for collision in contention.get("collisions", []):
            risk = collision.get("risk", "low")
            if risk in ("critical", "high"):
                time_str = collision.get("time", "")
                jobs = collision.get("jobs", [])
                predictions.append({
                    "component": f"contention:{time_str[:20]}",
                    "prediction": f"resource collision window: {len(jobs)} jobs compete",
                    "confidence": 0.8 if risk == "critical" else 0.6,
                    "evidence": [
                        f"time window: {time_str}",
                        f"resources: {', '.join(collision.get('resource_type', []))}",
                        collision.get("reason", "")[:120],
                    ],
                    "recommended_action": collision.get("reason", "stagger jobs")[-60:],
                    "severity": "high" if risk == "critical" else "medium",
                })

    # --- 3. Config drift risks ---
    if config_drift:
        for cfg in config_drift.get("configs", []):
            overall_risk = cfg.get("overall_risk", cfg.get("risk", "low"))
            if overall_risk in ("high", "medium"):
                predictions.append({
                    "component": f"config:{Path(cfg['path']).name}",
                    "prediction": f"config drift risk ({overall_risk})",
                    "confidence": 0.7 if overall_risk == "high" else 0.5,
                    "evidence": [
                        cfg.get("summary", cfg.get("notes", ""))[:150],
                        f"backup count: {cfg.get('backup_count', 0)}",
                    ],
                    "recommended_action": "validate config, create backup, review recent changes",
                    "severity": "high" if overall_risk == "high" else "medium",
                })

    # --- 4. Cron duration trending up -> predict timeout ---
    if cron_data:
        for job in cron_data.get("jobs", []):
            dur_trend = job.get("duration_trend", "stable")
            err_trend = job.get("error_trend", "stable")
            avg_dur = job.get("avg_duration_seconds", 0)
            name = job.get("name", "?")
            hs = job.get("health_score", 10)

            if dur_trend == "increasing" and avg_dur > 60:
                predictions.append({
                    "component": f"cron:{name}",
                    "prediction": "timeout risk: duration trending up",
                    "confidence": round(0.5 + (1 - hs / 10) * 0.3, 2),
                    "evidence": [
                        f"avg duration: {avg_dur}s",
                        f"duration trend: {dur_trend}",
                        f"health score: {hs}/10",
                    ],
                    "recommended_action": "investigate increasing duration; add timeout or optimize",
                    "severity": "high" if avg_dur > 300 else "medium",
                })

            if err_trend == "increasing":
                predictions.append({
                    "component": f"cron:{name}",
                    "prediction": "failure risk: error rate increasing",
                    "confidence": round(0.6 + (1 - hs / 10) * 0.3, 2),
                    "evidence": [
                        f"error rate: {job.get('error_rate', 0)}",
                        f"error trend: {err_trend}",
                        f"health score: {hs}/10",
                    ],
                    "recommended_action": "investigate root cause of increasing errors",
                    "severity": "high" if hs < 6 else "medium",
                })

    # --- 5. Correlated component stress -> cascade prediction ---
    if correlations:
        for corr in correlations.get("correlations", []):
            corr_val = corr.get("correlation", 0)
            corr_type = corr.get("type", "")
            if corr_val >= 0.8 and corr_type in ("causal", "data_dependency", "self_cascading"):
                comp_a = corr.get("component_a", "?")
                comp_b = corr.get("component_b", "?")

                # Check if either component is currently high risk
                a_risk = 0
                b_risk = 0
                if risk_data:
                    for comp in risk_data.get("components", []):
                        if comp["id"] == comp_a:
                            a_risk = comp.get("risk_score", 0)
                        if comp["id"] == comp_b:
                            b_risk = comp.get("risk_score", 0)

                if a_risk >= 50 or b_risk >= 50:
                    predictions.append({
                        "component": f"correlation:{comp_a} <-> {comp_b}",
                        "prediction": f"correlated cascade risk ({corr_type})",
                        "confidence": round(corr_val * 0.8, 2),
                        "evidence": [
                            f"correlation: {corr_val}",
                            f"type: {corr_type}",
                            corr.get("explanation", "")[:120],
                        ],
                        "recommended_action": corr.get("explanation", "monitor both components")[-80:],
                        "severity": "high" if max(a_risk, b_risk) >= 70 else "medium",
                    })

    # --- 6. Pipeline bottleneck predictions ---
    if bottlenecks:
        for bn in bottlenecks.get("bottlenecks", []):
            if bn.get("is_bottleneck") and bn.get("failure_rate_pct", 0) >= 50:
                predictions.append({
                    "component": f"pipeline:{bn.get('stage', '?')}",
                    "prediction": f"pipeline bottleneck: {bn.get('failure_rate_pct')}% failure rate",
                    "confidence": round(min(0.5 + bn.get("failure_rate_pct", 0) / 200.0, 0.95), 2),
                    "evidence": [
                        f"avg duration: {bn.get('avg_duration_seconds', 0)}s",
                        f"failure rate: {bn.get('failure_rate_pct')}%",
                        bn.get("reason", "")[:120],
                    ],
                    "recommended_action": bn.get("optimization", "investigate bottleneck"),
                    "severity": "critical" if bn.get("failure_rate_pct", 0) >= 80 else "high",
                })

    # --- 7. Error taxonomy systemic predictions ---
    if error_tax:
        for ec in error_tax.get("error_classes", []):
            occ = ec.get("occurrences", 0)
            risk = ec.get("recurrence_risk", "low")
            if occ > 100 and risk == "high" and not ec.get("fix_applied"):
                predictions.append({
                    "component": f"error:{ec.get('class', '?')}",
                    "prediction": f"systemic error: {occ} occurrences, unfixed",
                    "confidence": 0.9,
                    "evidence": [
                        f"{occ} occurrences across {', '.join(ec.get('affected_components', [])[:3])}",
                        ec.get("root_cause", "")[:120],
                    ],
                    "recommended_action": ec.get("remediation", "investigate and fix")[:150],
                    "severity": "high",
                })

    # Sort by confidence descending
    predictions.sort(key=lambda p: p["confidence"], reverse=True)
    return predictions


# ---------------------------------------------------------------------------
# Active Risks (from risk_scores)
# ---------------------------------------------------------------------------

def get_active_risks(ont, top_n=10):
    """Extract the top N active risks from risk_scores ontology."""
    risk_data = ont.get("risk_scores")
    if not risk_data:
        return []

    components = risk_data.get("components", [])
    # Sort by risk_score descending
    ranked = sorted(components, key=lambda c: c.get("risk_score", 0), reverse=True)

    risks = []
    for comp in ranked[:top_n]:
        risks.append({
            "component": comp["id"],
            "risk_score": comp.get("risk_score", 0),
            "trend": comp.get("trend", "unknown"),
            "predicted_failure": comp.get("predicted_failure", ""),
            "factors": comp.get("factors", [])[:3],
        })
    return risks


# ---------------------------------------------------------------------------
# Enhancement Queue
# ---------------------------------------------------------------------------

def get_enhancement_queue(ont, top_n=10):
    """Extract top enhancement opportunities sorted by priority."""
    enh_data = ont.get("enhancements")
    if not enh_data:
        return []

    opps = enh_data.get("opportunities", [])
    # Sort: high first, then medium, then low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    ranked = sorted(opps, key=lambda o: priority_order.get(o.get("priority", "low"), 3))

    queue = []
    for opp in ranked[:top_n]:
        queue.append({
            "category": opp.get("category", "?"),
            "component": opp.get("component", "?"),
            "recommendation": opp.get("recommendation", "")[:150],
            "priority": opp.get("priority", "low"),
            "effort": opp.get("effort", "unknown"),
        })
    return queue


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_report(ont):
    """Generate the full prediction report."""
    health, breakdown = compute_health(ont)
    predictions = predict_failures(ont)
    active_risks = get_active_risks(ont)
    enhancements = get_enhancement_queue(ont)

    report = {
        "timestamp": NOW.isoformat(),
        "system_health": health,
        "health_breakdown": breakdown,
        "predictions": predictions,
        "prediction_count": len(predictions),
        "active_risks": active_risks,
        "enhancement_queue": enhancements,
    }
    return report


def summary_line(report):
    """Generate a one-line health summary."""
    h = report["system_health"]
    n_pred = report["prediction_count"]
    n_risks = len([r for r in report["active_risks"] if r["risk_score"] >= 60])

    status = "HEALTHY" if h >= 75 else "DEGRADED" if h >= 50 else "CRITICAL"
    return f"[{status}] System health: {h}/100 | {n_pred} predictions | {n_risks} high-risk components | {report['timestamp']}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ont = load_ontology()
    report = generate_report(ont)

    if "--summary" in sys.argv:
        print(summary_line(report))
    elif "--risks" in sys.argv:
        top5 = report["active_risks"][:5]
        print(json.dumps(top5, indent=2))
    elif "--predict" in sys.argv:
        print(json.dumps(report["predictions"], indent=2))
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
