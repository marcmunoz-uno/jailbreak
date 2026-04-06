#!/usr/bin/env python3
"""
Causal Inference Engine — predicts downstream failures with countdowns
when a component degrades.

Reads from L1_structure.db / L2_state.db if available, otherwise falls back
to the raw JSON ontology files.

stdlib only: json, sqlite3, os, pathlib, datetime, collections
"""

import json
import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque

ONTOLOGY_DIR = Path(__file__).resolve().parent
L1_DB = ONTOLOGY_DIR / "L1_structure.db"
L2_DB = ONTOLOGY_DIR / "L2_state.db"
CASCADES_JSON = ONTOLOGY_DIR / "failure_cascades.json"
CORRELATIONS_JSON = ONTOLOGY_DIR / "correlations.json"
DEPGRAPH_JSON = ONTOLOGY_DIR / "dependency_graph.json"

# Edge types that imply causal propagation (A fails -> B likely fails)
CAUSAL_EDGE_TYPES = {"depends_on", "reads", "reads_writes", "executes", "calls", "exposes"}
# Edge directions: in dependency_graph.json, "from" depends_on "to" means
# if "to" fails, "from" is affected.  So causal direction is to -> from.
# For "reads": "from" reads "to", so if "to" is corrupted, "from" is affected.


class CausalEngine:
    """Predicts downstream failures given a degraded component."""

    def __init__(self):
        # adjacency list: {node: [(target, delay_min, confidence, mechanism)]}
        self.graph = defaultdict(list)
        # reverse graph for root-cause analysis
        self.reverse_graph = defaultdict(list)
        # known cascade patterns keyed by trigger
        self.cascade_patterns = {}
        # node metadata
        self.nodes = {}
        # timing observations for EWMA updates
        self._timing_observations = defaultdict(list)

        self._load_data()
        self._expand_wildcards()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self):
        """Load from L1/L2 databases if they exist, otherwise JSON."""
        if L1_DB.exists():
            self._load_from_l1_db()
        else:
            self._load_from_cascades()
            self._load_from_correlations()
            self._load_from_dependency_graph()

    def _expand_wildcards(self):
        """Expand wildcard targets like 'cron:*' into concrete edges."""
        all_nodes = self._all_nodes()
        expansions = []
        removals = []
        for source, edges in list(self.graph.items()):
            for target, delay, conf, mechanism in edges:
                if target.endswith(":*"):
                    prefix = target[:-1]  # e.g. "cron:"
                    removals.append((source, target))
                    for node in all_nodes:
                        if node.startswith(prefix) and node != source:
                            expansions.append((source, node, delay, conf * 0.9, mechanism))
        # Remove wildcard edges and add expanded ones
        for source, wc_target in removals:
            self.graph[source] = [
                e for e in self.graph[source] if e[0] != wc_target
            ]
            # Clean up the wildcard node entirely
            if wc_target in self.reverse_graph:
                del self.reverse_graph[wc_target]
            if wc_target in self.graph:
                del self.graph[wc_target]
        for source, target, delay, conf, mechanism in expansions:
            if not self._find_edge(source, target):
                self._add_edge(source, target, delay, conf, mechanism)

    def _load_from_l1_db(self):
        """Load edges and patterns from L1_structure.db."""
        conn = sqlite3.connect(str(L1_DB))
        conn.row_factory = sqlite3.Row
        try:
            for row in conn.execute("SELECT * FROM edges"):
                self._add_edge(
                    row["source"], row["target"],
                    row["delay_min"], row["confidence"],
                    row["mechanism"],
                )
            for row in conn.execute("SELECT * FROM patterns"):
                data = json.loads(row["data"])
                self.cascade_patterns[row["trigger"]] = data
        except sqlite3.OperationalError:
            # Tables don't exist yet — fall back to JSON
            self._load_from_cascades()
            self._load_from_correlations()
            self._load_from_dependency_graph()
        finally:
            conn.close()

    def _load_from_cascades(self):
        """Build edges from failure_cascades.json."""
        if not CASCADES_JSON.exists():
            return
        data = json.loads(CASCADES_JSON.read_text())
        for cascade in data.get("cascades", []):
            trigger = cascade["trigger"]
            self.cascade_patterns[trigger] = cascade
            delay = cascade.get("time_to_cascade_minutes", 0)
            freq = cascade.get("frequency", 1)
            severity = cascade.get("severity", "medium")
            # confidence derived from frequency relative to total records
            total = data.get("total_failure_records_analyzed", 1390)
            confidence = min(0.99, 0.5 + (freq / total) * 5)
            for i, downstream in enumerate(cascade.get("downstream_failures", [])):
                # Stage offset: if multiple downstream, small stagger
                stage_delay = delay + i * 0.5 if delay == 0 else delay
                self._add_edge(
                    trigger, downstream,
                    stage_delay, confidence,
                    cascade.get("description", "cascade propagation"),
                )

    def _load_from_correlations(self):
        """Build edges from correlations.json."""
        if not CORRELATIONS_JSON.exists():
            return
        data = json.loads(CORRELATIONS_JSON.read_text())
        for corr in data.get("correlations", []):
            ctype = corr.get("type", "")
            comp_a = corr["component_a"]
            comp_b = corr["component_b"]
            lag = corr.get("lag_minutes", 15)
            base_corr = corr.get("correlation", 0.5)

            if ctype == "causal":
                # Directed: A causes B
                self._add_edge(
                    comp_a, comp_b, lag, base_corr,
                    corr.get("explanation", "causal correlation"),
                )
            elif ctype in ("resource_contention", "data_dependency",
                           "pipeline_dependency", "functional_dependency"):
                # Lower confidence, directed A -> B
                confidence = base_corr * 0.8
                self._add_edge(
                    comp_a, comp_b, lag, confidence,
                    corr.get("explanation", f"{ctype} correlation"),
                )
            elif ctype == "self_cascading":
                # Self-loop — record but don't traverse
                self._add_edge(
                    comp_a, comp_b, lag, base_corr,
                    corr.get("explanation", "self-cascading"),
                )

    def _load_from_dependency_graph(self):
        """Build edges from dependency_graph.json structural edges."""
        if not DEPGRAPH_JSON.exists():
            return
        data = json.loads(DEPGRAPH_JSON.read_text())

        # Store node metadata
        for node in data.get("nodes", []):
            self.nodes[node["id"]] = node

        for edge in data.get("edges", []):
            etype = edge.get("type", "")
            src = edge["from"]
            tgt = edge["to"]

            if etype in ("depends_on", "reads", "executes", "calls"):
                # src depends on tgt => if tgt fails, src is affected
                # Causal direction: tgt -> src
                existing = self._find_edge(tgt, src)
                if not existing:
                    reason = edge.get("reason", f"structural {etype} dependency")
                    self._add_edge(tgt, src, 15, 0.6, reason)
            elif etype == "reads_writes":
                # Bidirectional dependency — if either side corrupts, the other sees it
                if not self._find_edge(tgt, src):
                    self._add_edge(tgt, src, 15, 0.55, f"reads_writes dependency")
                if not self._find_edge(src, tgt):
                    self._add_edge(src, tgt, 15, 0.45, f"reads_writes reverse")
            elif etype == "produces":
                # src produces tgt data => if src fails, tgt data is stale
                # downstream readers of tgt will be affected (they have their own edges)
                if not self._find_edge(src, tgt):
                    self._add_edge(src, tgt, 5, 0.7, "produces data")
            elif etype in ("monitors", "validates"):
                # Monitor/validate: if target fails, monitor detects it (not a failure propagation)
                pass
            elif etype == "orchestrates":
                # Orchestrator failing affects orchestrated jobs
                if not self._find_edge(src, tgt):
                    self._add_edge(src, tgt, 5, 0.5, "orchestration dependency")
            elif etype == "sends_to":
                if not self._find_edge(tgt, src):
                    self._add_edge(tgt, src, 10, 0.5, "delivery dependency")

    def _add_edge(self, source: str, target: str, delay_min: float,
                  confidence: float, mechanism: str):
        """Add a directed edge to both forward and reverse graphs."""
        entry = (target, delay_min, confidence, mechanism)
        # Avoid exact duplicates
        if entry not in self.graph[source]:
            self.graph[source].append(entry)
        rev_entry = (source, delay_min, confidence, mechanism)
        if rev_entry not in self.reverse_graph[target]:
            self.reverse_graph[target].append(rev_entry)

    def _find_edge(self, source: str, target: str):
        """Check if an edge already exists between source and target."""
        return any(t == target for t, _, _, _ in self.graph.get(source, []))

    # ------------------------------------------------------------------
    # Fuzzy component matching
    # ------------------------------------------------------------------

    def _resolve_component(self, name: str) -> list[str]:
        """Resolve a component name, supporting wildcards and fuzzy matching."""
        all_nodes = self._all_nodes()
        if name.endswith(":*"):
            prefix = name[:-1]  # e.g. "cron:"
            matches = [n for n in all_nodes if n.startswith(prefix)]
            return matches if matches else [name]
        # Exact match
        if name in all_nodes:
            return [name]
        # Try matching the suffix after the colon
        if ":" in name:
            prefix, suffix = name.split(":", 1)
            # Check if suffix is contained in any node of same type
            matches = [n for n in all_nodes
                       if n.startswith(prefix + ":") and suffix in n]
            if matches:
                return matches
        # General fuzzy: check if name is a substring of any node
        matches = [n for n in all_nodes if name in n]
        return matches if matches else [name]

    def _all_nodes(self) -> set:
        """All known node IDs."""
        nodes = set(self.graph.keys())
        for targets in self.graph.values():
            for t, _, _, _ in targets:
                nodes.add(t)
        for targets in self.reverse_graph.values():
            for t, _, _, _ in targets:
                nodes.add(t)
        nodes.update(self.nodes.keys())
        return nodes

    # ------------------------------------------------------------------
    # Core predictions
    # ------------------------------------------------------------------

    def predict_downstream(self, failed_component: str,
                           severity: str = "degraded",
                           min_confidence: float = 0.3) -> list[dict]:
        """
        Given a failing/degraded component, predict what will fail next.
        BFS through the causal graph, accumulating propagation delays.
        """
        severity_multiplier = {
            "degraded": 0.7,
            "failing": 0.85,
            "down": 1.0,
        }.get(severity, 0.8)

        predictions = []
        visited = set()
        # (component, cumulative_delay, cumulative_confidence, path)
        queue = deque()

        resolved = self._resolve_component(failed_component)
        for comp in resolved:
            queue.append((comp, 0.0, 1.0, [comp]))
            visited.add(comp)

        while queue:
            current, cum_delay, cum_conf, path = queue.popleft()
            for target, delay, conf, mechanism in self.graph.get(current, []):
                if target in visited:
                    continue
                visited.add(target)

                new_delay = cum_delay + delay
                new_conf = cum_conf * conf * severity_multiplier
                new_path = path + [target]

                if new_conf >= min_confidence:
                    # Determine severity based on confidence and node criticality
                    node_info = self.nodes.get(target, {})
                    is_critical = node_info.get("critical", False)
                    if new_conf >= 0.7 and is_critical:
                        pred_severity = "critical"
                    elif new_conf >= 0.5:
                        pred_severity = "high"
                    elif new_conf >= 0.3:
                        pred_severity = "medium"
                    else:
                        pred_severity = "low"

                    predictions.append({
                        "component": target,
                        "expected_failure_in_minutes": round(new_delay, 1),
                        "confidence": round(new_conf, 3),
                        "mechanism": mechanism,
                        "path": new_path,
                        "severity": pred_severity,
                    })

                    # Continue BFS from this node
                    queue.append((target, new_delay, new_conf, new_path))

        predictions.sort(key=lambda p: p["expected_failure_in_minutes"])
        return predictions

    def predict_cascade(self, trigger_event: str) -> dict:
        """
        Match trigger against known cascade patterns.
        Returns the full cascade timeline if matched.
        """
        # Direct match
        if trigger_event in self.cascade_patterns:
            pattern = self.cascade_patterns[trigger_event]
            return self._build_cascade_timeline(pattern)

        # Fuzzy match
        for key, pattern in self.cascade_patterns.items():
            if trigger_event in key or key in trigger_event:
                return self._build_cascade_timeline(pattern)

        # No known pattern — use predict_downstream instead
        predictions = self.predict_downstream(trigger_event, severity="down")
        if predictions:
            return {
                "trigger": trigger_event,
                "matched_pattern": None,
                "message": "No known cascade pattern — showing predicted propagation",
                "timeline": [
                    {
                        "component": p["component"],
                        "minutes_from_trigger": p["expected_failure_in_minutes"],
                        "confidence": p["confidence"],
                    }
                    for p in predictions[:15]
                ],
            }
        return {"trigger": trigger_event, "matched_pattern": None, "timeline": []}

    def _build_cascade_timeline(self, pattern: dict) -> dict:
        """Build a structured timeline from a cascade pattern."""
        base_delay = pattern.get("time_to_cascade_minutes", 0)
        downstream = pattern.get("downstream_failures", [])
        timeline = []
        for i, comp in enumerate(downstream):
            # Stagger within the cascade window
            offset = base_delay + (i * 0.5 if base_delay == 0 else i * (base_delay / max(len(downstream), 1)))
            timeline.append({
                "component": comp,
                "minutes_from_trigger": round(offset, 1),
                "confidence": 0.9,
            })
        return {
            "trigger": pattern.get("trigger", "unknown"),
            "matched_pattern": pattern.get("description", ""),
            "severity": pattern.get("severity", "unknown"),
            "frequency": pattern.get("frequency", 0),
            "total_cascade_minutes": base_delay,
            "timeline": timeline,
        }

    def get_root_causes(self, failed_component: str,
                        min_confidence: float = 0.3) -> list[dict]:
        """
        Reverse traversal: what UPSTREAM components could have caused this?
        """
        results = []
        visited = set()
        queue = deque()

        resolved = self._resolve_component(failed_component)
        for comp in resolved:
            queue.append((comp, 0.0, 1.0, [comp]))
            visited.add(comp)

        while queue:
            current, cum_delay, cum_conf, path = queue.popleft()
            for upstream, delay, conf, mechanism in self.reverse_graph.get(current, []):
                if upstream in visited:
                    continue
                visited.add(upstream)

                new_delay = cum_delay + delay
                new_conf = cum_conf * conf
                new_path = [upstream] + path

                if new_conf >= min_confidence:
                    node_info = self.nodes.get(upstream, {})
                    results.append({
                        "component": upstream,
                        "propagation_delay_minutes": round(new_delay, 1),
                        "confidence": round(new_conf, 3),
                        "mechanism": mechanism,
                        "path": new_path,
                        "critical": node_info.get("critical", False),
                    })
                    queue.append((upstream, new_delay, new_conf, new_path))

        results.sort(key=lambda r: -r["confidence"])
        return results

    def score_blast_radius(self, component: str) -> dict:
        """
        How many downstream components would be affected if this component fails?
        """
        predictions = self.predict_downstream(component, severity="down",
                                              min_confidence=0.2)
        critical = [p for p in predictions if p["severity"] in ("critical", "high")]
        all_downstream = [p["component"] for p in predictions]

        return {
            "component": component,
            "blast_radius": len(all_downstream),
            "critical_downstream": [
                {"component": p["component"], "confidence": p["confidence"]}
                for p in critical
            ],
            "total_downstream": all_downstream,
            "risk_score": round(
                sum(p["confidence"] for p in predictions) / max(len(predictions), 1), 3
            ),
        }

    def get_cascade_breaker_actions(self, trigger: str) -> list[dict]:
        """
        Given a cascade trigger, return recommended actions to prevent propagation.
        """
        predictions = self.predict_downstream(trigger, severity="down")
        actions = []
        seen_actions = set()

        for pred in predictions:
            comp = pred["component"]
            comp_type = comp.split(":")[0] if ":" in comp else "unknown"
            delay = pred["expected_failure_in_minutes"]

            if comp_type == "cron" and "pause_crons" not in seen_actions:
                cron_targets = [p["component"] for p in predictions
                                if p["component"].startswith("cron:")]
                actions.append({
                    "action": "pause_downstream_cron_jobs",
                    "targets": cron_targets,
                    "urgency_minutes": delay,
                    "reason": f"Pause {len(cron_targets)} cron jobs before cascade reaches them",
                    "command_hint": "openclaw cron pause " + " ".join(
                        c.split(":", 1)[1] for c in cron_targets[:5]
                    ),
                })
                seen_actions.add("pause_crons")

            if comp_type == "service" and f"restart_{comp}" not in seen_actions:
                actions.append({
                    "action": "restart_service",
                    "targets": [comp],
                    "urgency_minutes": delay,
                    "reason": f"Restart {comp} to clear corrupted state before cascade",
                    "command_hint": f"launchctl kickstart -k gui/$(id -u)/com.openclaw.{comp.split(':')[1]}",
                })
                seen_actions.add(f"restart_{comp}")

        # Generic actions based on trigger type
        trigger_type = trigger.split(":")[0] if ":" in trigger else ""
        if trigger_type == "config":
            actions.insert(0, {
                "action": "restore_config_backup",
                "targets": [trigger],
                "urgency_minutes": 0,
                "reason": f"Restore last known good version of {trigger}",
                "command_hint": f"cp {trigger}.bak {trigger}",
            })
        elif "rate_limit" in trigger:
            actions.insert(0, {
                "action": "switch_provider_fallback",
                "targets": [trigger],
                "urgency_minutes": 0,
                "reason": "Switch to fallback LLM provider to avoid rate limit cascade",
                "command_hint": "openclaw config set provider.fallback openrouter",
            })
        elif "auth" in trigger:
            actions.insert(0, {
                "action": "refresh_auth_credentials",
                "targets": [trigger],
                "urgency_minutes": 0,
                "reason": "Re-inject API keys from secure store",
                "command_hint": "openclaw auth refresh --all",
            })

        actions.sort(key=lambda a: a["urgency_minutes"])
        return actions

    def update_timing(self, from_component: str, to_component: str,
                      observed_delay_minutes: float, alpha: float = 0.3):
        """
        Update propagation timing with new observation using EWMA.
        alpha: smoothing factor (higher = more weight on recent observation)
        """
        updated = False
        new_edges = []
        for target, delay, conf, mechanism in self.graph.get(from_component, []):
            if target == to_component:
                new_delay = alpha * observed_delay_minutes + (1 - alpha) * delay
                new_conf = min(0.99, conf + 0.01)  # Slightly increase confidence
                new_edges.append((target, round(new_delay, 2), round(new_conf, 4), mechanism))
                updated = True
            else:
                new_edges.append((target, delay, conf, mechanism))

        if updated:
            self.graph[from_component] = new_edges
            # Update reverse graph too
            rev_edges = []
            for source, delay, conf, mechanism in self.reverse_graph.get(to_component, []):
                if source == from_component:
                    new_delay = alpha * observed_delay_minutes + (1 - alpha) * delay
                    new_conf = min(0.99, conf + 0.01)
                    rev_edges.append((source, round(new_delay, 2), round(new_conf, 4), mechanism))
                else:
                    rev_edges.append((source, delay, conf, mechanism))
            self.reverse_graph[to_component] = rev_edges

        self._timing_observations[(from_component, to_component)].append({
            "delay": observed_delay_minutes,
            "timestamp": datetime.utcnow().isoformat(),
        })
        return updated

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return engine statistics."""
        all_edges = sum(len(v) for v in self.graph.values())
        all_nodes = self._all_nodes()
        return {
            "total_nodes": len(all_nodes),
            "total_edges": all_edges,
            "cascade_patterns": len(self.cascade_patterns),
            "node_types": dict(sorted(
                defaultdict(int, {
                    t: sum(1 for n in all_nodes if n.startswith(t + ":"))
                    for t in {n.split(":")[0] for n in all_nodes if ":" in n}
                }).items(),
                key=lambda x: -x[1],
            )),
        }


# ======================================================================
# CLI
# ======================================================================

def _format_predictions(predictions: list[dict], label: str = "Predictions") -> str:
    """Format predictions for terminal output."""
    if not predictions:
        return f"  No {label.lower()} found.\n"
    lines = []
    for i, p in enumerate(predictions, 1):
        comp = p["component"]
        sev = p.get("severity", "?")
        sev_icon = {"critical": "!!!", "high": "!! ", "medium": "!  ", "low": ".  "}.get(sev, "   ")
        conf = p.get("confidence", 0)
        delay = p.get("expected_failure_in_minutes",
                       p.get("propagation_delay_minutes", "?"))
        mechanism = p.get("mechanism", "")
        if len(mechanism) > 80:
            mechanism = mechanism[:77] + "..."
        path = " -> ".join(p.get("path", []))
        lines.append(
            f"  {i:2d}. [{sev_icon}] {comp}\n"
            f"      ETA: {delay} min | confidence: {conf:.1%} | severity: {sev}\n"
            f"      mechanism: {mechanism}\n"
            f"      path: {path}"
        )
    return "\n".join(lines)


def _format_root_causes(causes: list[dict]) -> str:
    if not causes:
        return "  No root causes found.\n"
    lines = []
    for i, c in enumerate(causes, 1):
        comp = c["component"]
        crit = " [CRITICAL]" if c.get("critical") else ""
        conf = c.get("confidence", 0)
        delay = c.get("propagation_delay_minutes", "?")
        mechanism = c.get("mechanism", "")
        if len(mechanism) > 80:
            mechanism = mechanism[:77] + "..."
        path = " -> ".join(c.get("path", []))
        lines.append(
            f"  {i:2d}. {comp}{crit}\n"
            f"      propagation delay: {delay} min | confidence: {conf:.1%}\n"
            f"      mechanism: {mechanism}\n"
            f"      path: {path}"
        )
    return "\n".join(lines)


def _format_blast_radius(result: dict) -> str:
    lines = [
        f"  Component: {result['component']}",
        f"  Blast Radius: {result['blast_radius']} downstream components",
        f"  Risk Score: {result['risk_score']:.3f}",
        f"",
        f"  Critical/High downstream ({len(result['critical_downstream'])}):",
    ]
    for c in result["critical_downstream"][:20]:
        lines.append(f"    - {c['component']} (confidence: {c['confidence']:.1%})")
    if len(result["total_downstream"]) > 0:
        lines.append(f"")
        lines.append(f"  All downstream ({len(result['total_downstream'])}):")
        for comp in result["total_downstream"][:30]:
            lines.append(f"    - {comp}")
        remaining = len(result["total_downstream"]) - 30
        if remaining > 0:
            lines.append(f"    ... and {remaining} more")
    return "\n".join(lines)


def _format_cascade(result: dict) -> str:
    lines = []
    if result.get("matched_pattern"):
        lines.append(f"  Matched Pattern: {result['matched_pattern']}")
        lines.append(f"  Severity: {result.get('severity', '?')}")
        lines.append(f"  Historical Frequency: {result.get('frequency', '?')} occurrences")
        lines.append(f"  Total Cascade Window: {result.get('total_cascade_minutes', '?')} min")
    elif result.get("message"):
        lines.append(f"  {result['message']}")
    lines.append(f"")
    lines.append(f"  Timeline:")
    for entry in result.get("timeline", []):
        lines.append(
            f"    T+{entry['minutes_from_trigger']:5.1f} min | "
            f"{entry['component']} (conf: {entry['confidence']:.0%})"
        )
    return "\n".join(lines)


def _format_actions(actions: list[dict]) -> str:
    if not actions:
        return "  No recommended actions.\n"
    lines = []
    for i, a in enumerate(actions, 1):
        lines.append(f"  {i}. [{a['action']}]")
        lines.append(f"     Urgency: within {a['urgency_minutes']} min")
        lines.append(f"     Reason: {a['reason']}")
        lines.append(f"     Targets: {', '.join(a['targets'][:5])}")
        if a.get("command_hint"):
            lines.append(f"     Hint: {a['command_hint']}")
        lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 causal_engine.py predict <component> [severity]")
        print("  python3 causal_engine.py root-cause <component>")
        print("  python3 causal_engine.py blast-radius <component>")
        print("  python3 causal_engine.py cascade <trigger>")
        print("  python3 causal_engine.py actions <trigger>")
        print("  python3 causal_engine.py stats")
        sys.exit(1)

    engine = CausalEngine()
    command = sys.argv[1]

    if command == "predict":
        if len(sys.argv) < 3:
            print("Error: specify a component. E.g.: predict \"config:openclaw.json\"")
            sys.exit(1)
        component = sys.argv[2]
        severity = sys.argv[3] if len(sys.argv) > 3 else "degraded"
        predictions = engine.predict_downstream(component, severity)
        print(f"\n=== Downstream Failure Predictions for {component} ({severity}) ===\n")
        print(_format_predictions(predictions))
        print(f"\n  Total: {len(predictions)} predicted failures\n")

    elif command == "root-cause":
        if len(sys.argv) < 3:
            print("Error: specify a component.")
            sys.exit(1)
        component = sys.argv[2]
        causes = engine.get_root_causes(component)
        print(f"\n=== Root Cause Analysis for {component} ===\n")
        print(_format_root_causes(causes))
        print(f"\n  Total: {len(causes)} potential root causes\n")

    elif command == "blast-radius":
        if len(sys.argv) < 3:
            print("Error: specify a component.")
            sys.exit(1)
        component = sys.argv[2]
        result = engine.score_blast_radius(component)
        print(f"\n=== Blast Radius for {component} ===\n")
        print(_format_blast_radius(result))
        print()

    elif command == "cascade":
        if len(sys.argv) < 3:
            print("Error: specify a trigger event.")
            sys.exit(1)
        trigger = sys.argv[2]
        result = engine.predict_cascade(trigger)
        print(f"\n=== Cascade Analysis for {trigger} ===\n")
        print(_format_cascade(result))
        print()

    elif command == "actions":
        if len(sys.argv) < 3:
            print("Error: specify a trigger.")
            sys.exit(1)
        trigger = sys.argv[2]
        actions = engine.get_cascade_breaker_actions(trigger)
        print(f"\n=== Cascade Breaker Actions for {trigger} ===\n")
        print(_format_actions(actions))

    elif command == "stats":
        s = engine.stats()
        print(f"\n=== Causal Engine Stats ===\n")
        print(f"  Nodes: {s['total_nodes']}")
        print(f"  Edges: {s['total_edges']}")
        print(f"  Cascade Patterns: {s['cascade_patterns']}")
        print(f"  Node types:")
        for t, count in s["node_types"].items():
            print(f"    {t}: {count}")
        print()

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
