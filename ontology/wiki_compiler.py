#!/usr/bin/env python3
"""
Contextual Memory Compiler (CMC) — Karpathy-style wiki that synthesizes
raw knowledge from OpenClaw ontology into structured wiki articles.

Usage:
    python3 wiki_compiler.py build                          # full rebuild
    python3 wiki_compiler.py build --topic "Trading System" # rebuild one topic
    python3 wiki_compiler.py list                           # list all articles
    python3 wiki_compiler.py stats                          # entry counts per topic
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OPENCLAW_ROOT = Path(os.path.expanduser("~/.openclaw"))
ONTOLOGY_DIR = OPENCLAW_ROOT / "ontology"
WIKI_DIR = OPENCLAW_ROOT / "wiki"
INDEX_PATH = WIKI_DIR / "index.json"
FABRIC_DIR = OPENCLAW_ROOT / "fabric"
MEMORY_DB = OPENCLAW_ROOT / "memory" / "main.sqlite"
LCM_DB = OPENCLAW_ROOT / "lcm.db"
UNIFIED_DB = OPENCLAW_ROOT / "ontology" / "unified_index.db"

GODMODE_URL = "http://localhost:7860"

# ---------------------------------------------------------------------------
# Topic rules: (regex_pattern, topic_name)
# ---------------------------------------------------------------------------
TOPIC_RULES: list[tuple[str, str]] = [
    (r"dscr|lead.?gen|lead.?pipeline|skip.?trace|outreach|motivated.?seller|propstream|activecampaign|batchdata", "DSCR Lead Pipeline"),
    (r"openclaw\.json|config.?drift|config.?reload|config.?corrupt|config.?writer", "OpenClaw Configuration"),
    (r"mission.?control|port.?3000", "Mission Control Service"),
    (r"trading|kalshi|polymarket|glint|memecoin|paper.?trad|whale.?track|arbitrage", "Trading System"),
    (r"nexus|coordinator|handoff|pheromone|circadian|self.?heal", "Nexus Coordinator"),
    (r"hermes|research.?agent|quant.?research", "Hermes Research Agent"),
    (r"gateway|telegram|channel|messaging", "Gateway & Messaging"),
    (r"memory|fabric|brain|knowledge|total.?recall|lcm|recall.?observer|recall.?reflector", "Memory & Knowledge"),
    (r"cron|schedule|job.?health|cron.?ledger|concurrency|session.?limit", "Cron Job Health"),
    (r"auth|credential|api.?key|secret|token", "Authentication & Config"),
    (r"log.?rotat|watchdog|resource|contention|ram|disk|port.?conflict", "Resource Management"),
    (r"proxy|tunnel|forbidden|connection.?block", "Proxy & Network Issues"),
    (r"model.?deprecat|model.?not.?allowed|fallback|claude.?haiku|gemini", "Model Configuration"),
    (r"parse\.?bot|scraper|scraping", "Web Scraping & Parse.bot"),
    (r"rate.?limit|cooldown|cascade|concurrent|burst", "Rate Limiting & Cascades"),
    (r"ontology|compiler|risk.?score|bottleneck|enhancement|correlation", "System Ontology"),
    (r"dashboard|report|briefing|evening|morning|situation", "Reporting & Dashboards"),
    (r"agent.?memory|embedding|vector|chunk|fts", "Agent Memory Server"),
    (r"improvement|feedback|outcome|signal|score", "Feedback & Outcomes"),
]

# ---------------------------------------------------------------------------
# Knowledge entry — normalised intermediate representation
# ---------------------------------------------------------------------------
class KnowledgeEntry:
    """A single piece of knowledge extracted from any source."""
    __slots__ = (
        "id", "source_file", "source_type", "entry_type", "title",
        "content", "components", "severity", "confidence",
        "timestamp", "tags", "raw",
    )

    def __init__(self, **kw: Any):
        for s in self.__slots__:
            setattr(self, s, kw.get(s))

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===================================================================
# Source readers — extract KnowledgeEntry lists from each data source
# ===================================================================

def _read_json(path: Path) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _ts(raw: Any) -> Optional[str]:
    """Best-effort timestamp extraction."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float)):
        # epoch ms
        if raw > 1e12:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
    return None


def read_error_taxonomy() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "error_taxonomy.json")
    if not data:
        return []
    entries = []
    ts = data.get("generated_at")
    for ec in data.get("error_classes", []):
        entries.append(KnowledgeEntry(
            id=f"err-{slugify(ec.get('class', 'unknown'))}",
            source_file="ontology/error_taxonomy.json",
            source_type="ontology",
            entry_type="error_class",
            title=ec.get("class", "unknown"),
            content=ec.get("root_cause", "") + "\n\n" + ec.get("remediation", ""),
            components=ec.get("affected_components", []),
            severity="high" if ec.get("recurrence_risk") == "high" else "medium",
            confidence=0.9,
            timestamp=ts,
            tags=["error", ec.get("class", "")],
            raw=ec,
        ))
    return entries


def read_correlations() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "correlations.json")
    if not data:
        return []
    entries = []
    ts = data.get("timestamp")
    for c in data.get("correlations", []):
        comps = []
        for k in ("component_a", "component_b"):
            v = c.get(k, "")
            comps.append(v.split(":")[-1] if ":" in v else v)
        entries.append(KnowledgeEntry(
            id=f"corr-{slugify(comps[0])}-{slugify(comps[1])}",
            source_file="ontology/correlations.json",
            source_type="ontology",
            entry_type="correlation",
            title=f"Correlation: {c.get('component_a')} <-> {c.get('component_b')}",
            content=c.get("explanation", ""),
            components=comps,
            severity="high" if c.get("correlation", 0) > 0.8 else "medium",
            confidence=c.get("correlation", 0.5),
            timestamp=ts,
            tags=["correlation", c.get("type", "")],
            raw=c,
        ))
    return entries


def read_recovery_patterns() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "recovery_patterns.json")
    if not data:
        return []
    entries = []
    ts = data.get("generated_at")
    for p in data.get("patterns", []):
        entries.append(KnowledgeEntry(
            id=f"recov-{slugify(p.get('problem', 'unknown')[:60])}",
            source_file="ontology/recovery_patterns.json",
            source_type="ontology",
            entry_type="correction",
            title=p.get("problem", "unknown"),
            content=p.get("fix", ""),
            components=p.get("applicable_to", []),
            severity=p.get("severity", "medium"),
            confidence=1.0 if p.get("confidence") == "high" else 0.7,
            timestamp=p.get("date", ts),
            tags=["recovery", "correction"],
            raw=p,
        ))
    return entries


def read_failure_cascades() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "failure_cascades.json")
    if not data:
        return []
    entries = []
    ts = data.get("analysis_timestamp")
    for c in data.get("cascades", []):
        entries.append(KnowledgeEntry(
            id=f"cascade-{slugify(c.get('trigger', 'unknown'))}",
            source_file="ontology/failure_cascades.json",
            source_type="ontology",
            entry_type="cascade",
            title=f"Cascade: {c.get('trigger')}",
            content=c.get("pattern", "") + "\n\n" + c.get("description", ""),
            components=[c.get("trigger", "")] + c.get("downstream_failures", []),
            severity=c.get("severity", "medium"),
            confidence=0.85,
            timestamp=ts,
            tags=["cascade", "failure"],
            raw=c,
        ))
    return entries


def read_risk_scores() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "risk_scores.json")
    if not data:
        return []
    entries = []
    ts = data.get("timestamp")
    for comp in data.get("components", []):
        sev = "critical" if comp.get("risk_score", 0) >= 70 else "medium" if comp.get("risk_score", 0) >= 40 else "low"
        entries.append(KnowledgeEntry(
            id=f"risk-{slugify(comp.get('id', 'unknown'))}",
            source_file="ontology/risk_scores.json",
            source_type="ontology",
            entry_type="risk",
            title=f"Risk: {comp.get('id')} (score {comp.get('risk_score')})",
            content="\n".join(comp.get("factors", [])) + "\n\n" + comp.get("predicted_failure", ""),
            components=[comp.get("id", "").split(":")[-1]],
            severity=sev,
            confidence=comp.get("risk_score", 50) / 100.0,
            timestamp=ts,
            tags=["risk", comp.get("trend", "")],
            raw=comp,
        ))
    return entries


def read_cron_health() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "cron_health_timeline.json")
    if not data:
        return []
    entries = []
    ts = data.get("generated_at")
    for job in data.get("jobs", []):
        health = job.get("health_score", 10)
        sev = "critical" if health <= 5 else "medium" if health <= 7 else "low"
        entries.append(KnowledgeEntry(
            id=f"cron-{slugify(job.get('name', 'unknown'))}",
            source_file="ontology/cron_health_timeline.json",
            source_type="ontology",
            entry_type="health",
            title=f"Cron: {job.get('name')} (health {health})",
            content=f"Error rate: {job.get('error_rate', 0)*100:.0f}%, Avg duration: {job.get('avg_duration_seconds', 0):.0f}s, Prediction: {job.get('prediction', 'N/A')}",
            components=[job.get("name", "")],
            severity=sev,
            confidence=0.8,
            timestamp=ts,
            tags=["cron", "health"],
            raw=job,
        ))
    return entries


def read_pipeline_bottlenecks() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "pipeline_bottlenecks.json")
    if not data:
        return []
    entries = []
    ts = data.get("generated_at")
    for b in data.get("bottlenecks", []):
        entries.append(KnowledgeEntry(
            id=f"bottleneck-{slugify(b.get('stage', 'unknown'))}",
            source_file="ontology/pipeline_bottlenecks.json",
            source_type="ontology",
            entry_type="bottleneck",
            title=f"Bottleneck: {b.get('stage')}",
            content=b.get("reason", "") + "\n\nOptimization: " + b.get("optimization", ""),
            components=[b.get("pipeline", ""), b.get("stage", "")],
            severity="high" if b.get("is_bottleneck") else "medium",
            confidence=0.85,
            timestamp=ts,
            tags=["bottleneck", b.get("pipeline", "")],
            raw=b,
        ))
    return entries


def read_enhancement_opportunities() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "enhancement_opportunities.json")
    if not data:
        return []
    entries = []
    ts = data.get("timestamp")
    for opp in data.get("opportunities", []):
        entries.append(KnowledgeEntry(
            id=f"enhance-{slugify(opp.get('component', 'unknown'))}",
            source_file="ontology/enhancement_opportunities.json",
            source_type="ontology",
            entry_type="learning",
            title=f"Enhancement: {opp.get('component')}",
            content=opp.get("observation", "") + "\n\nRecommendation: " + opp.get("recommendation", ""),
            components=[opp.get("component", "")],
            severity=opp.get("priority", "medium"),
            confidence=0.75,
            timestamp=ts,
            tags=["enhancement", opp.get("category", "")],
            raw=opp,
        ))
    return entries


def read_agent_interactions() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "agent_interactions.json")
    if not data:
        return []
    entries = []
    ts = data.get("generated_at")
    for agent in data.get("agents", []):
        entries.append(KnowledgeEntry(
            id=f"agent-{slugify(agent.get('id', 'unknown'))}",
            source_file="ontology/agent_interactions.json",
            source_type="ontology",
            entry_type="pattern",
            title=f"Agent: {agent.get('id')} ({agent.get('role', '')})",
            content=f"Model: {agent.get('model', 'N/A')}\nFrequency: {agent.get('frequency', 'N/A')}\nTalks to: {', '.join(agent.get('talks_to', [])[:5])}",
            components=[agent.get("id", "")],
            severity="low",
            confidence=0.9,
            timestamp=ts,
            tags=["agent", "interaction"],
            raw=agent,
        ))
    return entries


def read_config_drift() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "config_drift.json")
    if not data:
        return []
    entries = []
    ts = data.get("analysis_timestamp")
    for cfg in data.get("configs", []):
        if not cfg.get("drift_detected"):
            continue
        details = cfg.get("drift_details", {})
        content_parts = []
        if isinstance(details, str):
            content_parts.append(details[:500])
            details = {}
        for k, v in details.items():
            if isinstance(v, dict):
                changes = v.get("changes", "")
                risk = v.get("risk", "")
                added = v.get("keys_added", [])
                removed = v.get("keys_removed", [])
                changed = v.get("values_changed", [])
                parts = []
                if changes:
                    parts.append(changes)
                if added:
                    parts.append(f"Added: {', '.join(added[:5])}")
                if removed:
                    parts.append(f"Removed: {', '.join(removed[:5])}")
                if changed:
                    parts.append(f"Changed: {', '.join(str(c)[:80] for c in changed[:5])}")
                risk_str = f" (risk: {risk})" if risk else ""
                content_parts.append(f"**{k}**: {'; '.join(parts)}{risk_str}")
            elif isinstance(v, str):
                content_parts.append(f"**{k}**: {v}")
            else:
                content_parts.append(f"**{k}**: {str(v)[:200]}")
        entries.append(KnowledgeEntry(
            id=f"drift-{slugify(cfg.get('path', 'unknown'))}",
            source_file="ontology/config_drift.json",
            source_type="ontology",
            entry_type="drift",
            title=f"Config drift: {Path(cfg.get('path', '')).name}",
            content="\n".join(content_parts),
            components=[Path(cfg.get("path", "")).name],
            severity="medium",
            confidence=0.9,
            timestamp=ts,
            tags=["config", "drift"],
            raw=cfg,
        ))
    return entries


def read_data_freshness() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "data_freshness.json")
    if not data:
        return []
    entries = []
    ts = data.get("generated_at")
    for ds in data.get("data_sources", []):
        status = ds.get("status", "unknown")
        sev = "critical" if status == "stale" else "medium" if status == "warning" else "low"
        entries.append(KnowledgeEntry(
            id=f"fresh-{slugify(Path(ds.get('path', '')).name)}",
            source_file="ontology/data_freshness.json",
            source_type="ontology",
            entry_type="freshness",
            title=f"Data: {Path(ds.get('path', '')).name} ({status})",
            content=f"Expected: {ds.get('expected_freshness_hours')}h, Actual age: {ds.get('actual_age_hours')}h\nProducer: {ds.get('producer')}\nConsumers: {', '.join(ds.get('consumers', []))}",
            components=[ds.get("producer", "")] + ds.get("consumers", []),
            severity=sev,
            confidence=0.95,
            timestamp=ts,
            tags=["freshness", status],
            raw=ds,
        ))
    return entries


def read_resource_contention() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "resource_contention.json")
    if not data:
        return []
    entries = []
    ts = data.get("analysis_timestamp")
    for col in data.get("collisions", []):
        entries.append(KnowledgeEntry(
            id=f"contention-{slugify(col.get('time', 'unknown')[:30])}",
            source_file="ontology/resource_contention.json",
            source_type="ontology",
            entry_type="contention",
            title=f"Resource contention at {col.get('time')}",
            content=col.get("reason", ""),
            components=col.get("jobs", []),
            severity="critical" if col.get("risk") == "critical" else "high",
            confidence=0.9,
            timestamp=ts,
            tags=["contention", "scheduling"],
            raw=col,
        ))
    return entries


def read_dependency_graph() -> list[KnowledgeEntry]:
    data = _read_json(ONTOLOGY_DIR / "dependency_graph.json")
    if not data:
        return []
    entries = []
    ts = data.get("meta", {}).get("generated_at") if isinstance(data.get("meta"), dict) else None
    for node in data.get("nodes", []):
        entries.append(KnowledgeEntry(
            id=f"dep-{slugify(node.get('id', 'unknown'))}",
            source_file="ontology/dependency_graph.json",
            source_type="ontology",
            entry_type="pattern",
            title=f"Component: {node.get('id', '')}",
            content=f"Type: {node.get('type', 'unknown')}, Status: {node.get('status', 'unknown')}",
            components=[node.get("id", "").split(":")[-1]],
            severity="low",
            confidence=0.8,
            timestamp=ts,
            tags=["dependency", node.get("type", "")],
            raw=node,
        ))
    return entries


def read_memory_cron_ledger() -> list[KnowledgeEntry]:
    """Read the cron ledger JSONL from memory dir."""
    ledger_path = OPENCLAW_ROOT / "memory" / "cron-ledger.jsonl"
    if not ledger_path.exists():
        return []
    entries = []
    try:
        with open(ledger_path) as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = rec.get("status", "unknown")
                sev = "high" if status in ("error", "failed") else "low"
                entries.append(KnowledgeEntry(
                    id=f"ledger-{i}",
                    source_file="memory/cron-ledger.jsonl",
                    source_type="cron_ledger",
                    entry_type="health" if status == "success" else "error_class",
                    title=f"Cron run: {rec.get('job_name', rec.get('name', 'unknown'))} [{status}]",
                    content=json.dumps(rec, indent=2)[:500],
                    components=[rec.get("job_name", rec.get("name", ""))],
                    severity=sev,
                    confidence=0.95,
                    timestamp=rec.get("timestamp", rec.get("started_at")),
                    tags=["cron", "ledger", status],
                    raw=rec,
                ))
    except Exception:
        pass
    return entries


# ===================================================================
# Gather all entries
# ===================================================================

ALL_READERS = [
    read_error_taxonomy,
    read_correlations,
    read_recovery_patterns,
    read_failure_cascades,
    read_risk_scores,
    read_cron_health,
    read_pipeline_bottlenecks,
    read_enhancement_opportunities,
    read_agent_interactions,
    read_config_drift,
    read_data_freshness,
    read_resource_contention,
    read_dependency_graph,
    read_memory_cron_ledger,
]


def gather_all_entries() -> list[KnowledgeEntry]:
    entries: list[KnowledgeEntry] = []
    for reader in ALL_READERS:
        try:
            entries.extend(reader())
        except Exception as e:
            print(f"  [warn] reader {reader.__name__} failed: {e}", file=sys.stderr)
    return entries


# ===================================================================
# Topic classification
# ===================================================================

def classify_entry(entry: KnowledgeEntry) -> list[str]:
    """Return list of topic names this entry belongs to."""
    searchable = " ".join(filter(None, [
        entry.title or "",
        entry.content or "",
        " ".join(entry.components or []),
        " ".join(entry.tags or []),
    ])).lower()

    topics = []
    for pattern, topic_name in TOPIC_RULES:
        if re.search(pattern, searchable):
            topics.append(topic_name)
    if not topics:
        topics.append("Uncategorized")
    return topics


def group_by_topic(entries: list[KnowledgeEntry]) -> dict[str, list[KnowledgeEntry]]:
    groups: dict[str, list[KnowledgeEntry]] = defaultdict(list)
    for entry in entries:
        for topic in classify_entry(entry):
            groups[topic].append(entry)
    return dict(groups)


# ===================================================================
# Article generation — template-based (no LLM required)
# ===================================================================

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _severity_key(e: KnowledgeEntry) -> int:
    return SEVERITY_ORDER.get(e.severity or "medium", 2)


def _recency_key(e: KnowledgeEntry) -> str:
    return e.timestamp or "1970-01-01"


def _find_related_topics(topic: str, all_topics: dict[str, list[KnowledgeEntry]]) -> list[str]:
    """Topics sharing components with this one."""
    my_components = set()
    for entry in all_topics.get(topic, []):
        for c in (entry.components or []):
            my_components.add(c.lower())

    related = []
    for other_topic, other_entries in all_topics.items():
        if other_topic == topic:
            continue
        other_components = set()
        for e in other_entries:
            for c in (e.components or []):
                other_components.add(c.lower())
        if my_components & other_components:
            related.append(other_topic)
    return sorted(related)


def generate_article_template(
    topic: str,
    entries: list[KnowledgeEntry],
    all_topics: dict[str, list[KnowledgeEntry]],
) -> str:
    """Generate a structured markdown article without an LLM."""
    slug = slugify(topic)
    sources = sorted(set(e.source_file or "unknown" for e in entries))
    related = _find_related_topics(topic, all_topics)
    all_components = sorted(set(
        c for e in entries for c in (e.components or []) if c
    ))
    tags = sorted(set(
        t for e in entries for t in (e.tags or []) if t
    ))

    # Categorize entries
    issues = sorted(
        [e for e in entries if e.entry_type in ("error_class", "cascade", "correlation", "risk", "contention", "drift")],
        key=_severity_key,
    )
    recoveries = sorted(
        [e for e in entries if e.entry_type in ("correction", "pattern")],
        key=_recency_key, reverse=True,
    )
    learnings = sorted(
        [e for e in entries if e.entry_type in ("learning", "enhancement", "bottleneck")],
        key=lambda e: e.confidence or 0, reverse=True,
    )
    health_entries = sorted(
        [e for e in entries if e.entry_type in ("health", "freshness")],
        key=_recency_key, reverse=True,
    )
    recent = sorted(entries, key=_recency_key, reverse=True)[:5]

    lines = []
    lines.append("---")
    lines.append(f"topic: {topic}")
    lines.append(f"slug: {slug}")
    lines.append(f"last_compiled: {now_iso()}")
    lines.append(f"sources: {json.dumps(sources)}")
    lines.append(f"backlinks: {json.dumps([slugify(r) for r in related])}")
    lines.append(f"tags: {json.dumps(tags[:20])}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {topic}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append(f"{len(entries)} knowledge entries across {len(sources)} sources.")
    lines.append("")

    # Components
    if all_components:
        lines.append("## Components")
        for c in all_components[:30]:
            lines.append(f"- `{c}`")
        lines.append("")

    # Known Issues
    if issues:
        lines.append("## Known Issues")
        for e in issues[:15]:
            sev_badge = f"[{(e.severity or 'medium').upper()}]"
            lines.append(f"### {sev_badge} {e.title}")
            if e.content:
                lines.append(e.content.strip()[:500])
            lines.append("")

    # Health Status
    if health_entries:
        lines.append("## Health Status")
        for e in health_entries[:10]:
            lines.append(f"### {e.title}")
            if e.content:
                lines.append(e.content.strip()[:300])
            lines.append("")

    # Recovery Patterns
    if recoveries:
        lines.append("## Recovery Patterns")
        for e in recoveries[:10]:
            lines.append(f"### {e.title}")
            if e.content:
                lines.append(e.content.strip()[:500])
            lines.append("")

    # Learnings
    if learnings:
        lines.append("## Learnings")
        for e in learnings[:10]:
            conf = f" (confidence: {e.confidence:.0%})" if e.confidence else ""
            lines.append(f"### {e.title}{conf}")
            if e.content:
                lines.append(e.content.strip()[:500])
            lines.append("")

    # Recent Activity
    lines.append("## Recent Activity")
    for e in recent:
        ts_str = e.timestamp[:19] if e.timestamp else "unknown"
        lines.append(f"- **{ts_str}** — {e.title}")
    lines.append("")

    # Related Topics
    if related:
        lines.append("## Related Topics")
        for r in related:
            lines.append(f"- [{r}]({slugify(r)}.md)")
        lines.append("")

    return "\n".join(lines)


# ===================================================================
# LLM-enhanced article generation (optional)
# ===================================================================

def _try_llm_article(topic: str, entries: list[KnowledgeEntry], all_topics: dict) -> Optional[str]:
    """Attempt to generate an LLM-enhanced article. Returns None on failure."""
    # Prepare entry summaries for LLM
    entry_texts = []
    for e in entries[:40]:  # limit context
        entry_texts.append(f"- [{e.entry_type}] {e.title}: {(e.content or '')[:200]}")
    entry_block = "\n".join(entry_texts)

    related = _find_related_topics(topic, all_topics)
    sources = sorted(set(e.source_file or "unknown" for e in entries))
    tags = sorted(set(t for e in entries for t in (e.tags or []) if t))[:20]
    slug = slugify(topic)

    prompt = f"""You are a technical wiki compiler. Synthesize the following knowledge entries into a coherent wiki article about "{topic}".

The article should have these sections: Overview, Components, Known Issues (sorted by severity), Recovery Patterns, Learnings, Recent Activity, and Related Topics.

Use markdown. Start with YAML frontmatter:
---
topic: {topic}
slug: {slug}
last_compiled: {now_iso()}
sources: {json.dumps(sources)}
backlinks: {json.dumps([slugify(r) for r in related])}
tags: {json.dumps(tags)}
---

Knowledge entries:
{entry_block}

Related topics: {', '.join(related)}

Write a clear, concise article. Focus on actionable insights."""

    # Try godmode first
    try:
        import urllib.request
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }).encode()
        req = urllib.request.Request(
            f"{GODMODE_URL}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"]
            return content
    except Exception:
        pass

    # Try direct Anthropic API
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import urllib.request
            payload = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                content = result["content"][0]["text"]
                return content
        except Exception:
            pass

    return None


# ===================================================================
# Build pipeline
# ===================================================================

def build_article(
    topic: str,
    entries: list[KnowledgeEntry],
    all_topics: dict[str, list[KnowledgeEntry]],
    use_llm: bool = True,
) -> str:
    """Build a wiki article for a topic."""
    article = None
    if use_llm:
        article = _try_llm_article(topic, entries, all_topics)
    if article is None:
        article = generate_article_template(topic, entries, all_topics)
    return article


def build_wiki(topic_filter: Optional[str] = None, use_llm: bool = True) -> dict:
    """Main build pipeline. Returns index data."""
    print("Scanning knowledge sources...")
    entries = gather_all_entries()
    print(f"  Found {len(entries)} total entries")

    print("Grouping by topic...")
    all_topics = group_by_topic(entries)
    print(f"  Found {len(all_topics)} topics")

    WIKI_DIR.mkdir(parents=True, exist_ok=True)

    index: dict[str, Any] = {
        "compiled_at": now_iso(),
        "total_entries": len(entries),
        "total_topics": 0,
        "articles": [],
    }

    topics_to_build = all_topics
    if topic_filter:
        topics_to_build = {
            k: v for k, v in all_topics.items()
            if k.lower() == topic_filter.lower()
        }
        if not topics_to_build:
            print(f"  [error] Topic '{topic_filter}' not found. Available: {', '.join(sorted(all_topics.keys()))}")
            return index

    for topic, topic_entries in sorted(topics_to_build.items()):
        slug = slugify(topic)
        print(f"  Building: {topic} ({len(topic_entries)} entries) -> {slug}.md")
        article = build_article(topic, topic_entries, all_topics, use_llm=use_llm)
        out_path = WIKI_DIR / f"{slug}.md"
        with open(out_path, "w") as f:
            f.write(article)

        related = _find_related_topics(topic, all_topics)
        tags = sorted(set(t for e in topic_entries for t in (e.tags or []) if t))[:20]
        sources = sorted(set(e.source_file or "unknown" for e in topic_entries))

        index["articles"].append({
            "topic": topic,
            "slug": slug,
            "path": str(out_path),
            "entry_count": len(topic_entries),
            "sources": sources,
            "tags": tags,
            "backlinks": [slugify(r) for r in related],
            "compiled_at": now_iso(),
        })

    index["total_topics"] = len(index["articles"])

    # Write index
    with open(INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)
    print(f"\nWrote {len(index['articles'])} articles to {WIKI_DIR}")
    print(f"Index: {INDEX_PATH}")
    return index


def list_articles() -> None:
    """List all compiled articles."""
    if not INDEX_PATH.exists():
        print("No index found. Run 'build' first.")
        return
    with open(INDEX_PATH) as f:
        index = json.load(f)
    print(f"Wiki compiled at: {index.get('compiled_at', 'unknown')}")
    print(f"Total entries: {index.get('total_entries', 0)}")
    print(f"Total topics: {index.get('total_topics', 0)}")
    print()
    for a in sorted(index.get("articles", []), key=lambda x: x.get("entry_count", 0), reverse=True):
        print(f"  {a['entry_count']:3d} entries | {a['slug']:<40s} | {a['topic']}")


def show_stats() -> None:
    """Show entry counts per topic."""
    entries = gather_all_entries()
    all_topics = group_by_topic(entries)

    print(f"Total entries: {len(entries)}")
    print(f"Total topics:  {len(all_topics)}")
    print()
    print(f"{'Topic':<40s} {'Entries':>8s} {'Sources':>8s}")
    print("-" * 60)
    for topic in sorted(all_topics, key=lambda t: len(all_topics[t]), reverse=True):
        topic_entries = all_topics[topic]
        sources = len(set(e.source_file for e in topic_entries))
        print(f"{topic:<40s} {len(topic_entries):>8d} {sources:>8d}")


# ===================================================================
# CLI
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Contextual Memory Compiler — wiki builder")
    sub = parser.add_subparsers(dest="command")

    build_p = sub.add_parser("build", help="Build wiki articles")
    build_p.add_argument("--topic", type=str, default=None, help="Build only this topic")
    build_p.add_argument("--no-llm", action="store_true", help="Skip LLM, use templates only")

    sub.add_parser("list", help="List all articles")
    sub.add_parser("stats", help="Show entry counts per topic")

    args = parser.parse_args()
    if args.command == "build":
        build_wiki(topic_filter=args.topic, use_llm=not args.no_llm)
    elif args.command == "list":
        list_articles()
    elif args.command == "stats":
        show_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
