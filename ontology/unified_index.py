#!/usr/bin/env python3
"""Unified Knowledge Index (UKI) — Foundation layer for OpenClaw knowledge graph.

Indexes fabric entries, system_brain learnings/corrections/health, and ontology
JSON files into a single SQLite FTS5 full-text search database.

Usage:
    python3 unified_index.py build
    python3 unified_index.py search "dscr pipeline failures"
    python3 unified_index.py component "service:mission-control"
    python3 unified_index.py related <entry_id>
    python3 unified_index.py stats
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = Path(os.path.expanduser("~/.openclaw/data/unified_index.db"))
BRAIN_DB = Path(os.path.expanduser("~/.openclaw/data/system_brain.db"))
FABRIC_DIR = Path(os.path.expanduser("~/fabric"))
ONTOLOGY_DIR = Path(os.path.expanduser("~/.openclaw/ontology"))
META_TABLE = "index_meta"

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_path TEXT,
    source_key TEXT,
    category TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    components TEXT,
    timestamp TEXT,
    confidence REAL DEFAULT 1.0,
    entry_type TEXT,
    tags TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    title, body, category, components, tags,
    content=knowledge_entries, content_rowid=rowid
);

CREATE TABLE IF NOT EXISTS entry_links (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id, link_type)
);

CREATE TABLE IF NOT EXISTS index_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- FTS triggers for keeping the index in sync
CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge_entries BEGIN
    INSERT INTO knowledge_fts(rowid, title, body, category, components, tags)
    VALUES (new.rowid, new.title, new.body, new.category, new.components, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge_entries BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, body, category, components, tags)
    VALUES ('delete', old.rowid, old.title, old.body, old.category, old.components, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge_entries BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, body, category, components, tags)
    VALUES ('delete', old.rowid, old.title, old.body, old.category, old.components, old.tags);
    INSERT INTO knowledge_fts(rowid, title, body, category, components, tags)
    VALUES (new.rowid, new.title, new.body, new.category, new.components, new.tags);
END;
"""


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db(conn):
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _make_id(*parts):
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12]
    return h


# ---------------------------------------------------------------------------
# Fabric parser
# ---------------------------------------------------------------------------

def _parse_yaml_frontmatter(text):
    """Minimal YAML-ish frontmatter parser (no PyYAML dependency)."""
    meta = {}
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return meta, text
    end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end < 0:
        return meta, text
    body = "\n".join(lines[end + 1:]).strip()
    for line in lines[1:end]:
        m = re.match(r"^(\w[\w_-]*)\s*:\s*(.+)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            # Parse inline YAML arrays: [a, b, c]
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
            meta[key] = val
    return meta, body


def _index_fabric(conn):
    """Index fabric markdown files. Returns (count, filename_to_id map)."""
    entries = []
    links = []
    # Map filename -> entry_id so other indexers can resolve fabric_refs
    filename_to_id = {}
    dirs = [FABRIC_DIR]
    cold = FABRIC_DIR / "cold"
    if cold.exists():
        dirs.append(cold)

    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if not f.name.endswith(".md"):
                continue
            try:
                text = f.read_text(errors="replace")
            except Exception:
                continue
            meta, body = _parse_yaml_frontmatter(text)
            entry_id = meta.get("id", _make_id("fabric", f.name))
            filename_to_id[f.name] = str(entry_id)
            etype_raw = meta.get("type", "unknown")
            tags = meta.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]
            summary = meta.get("summary", "")
            title = summary if summary else f.stem
            if len(title) > 200:
                title = title[:200]

            components = []
            # Extract component references from body
            for cm in re.findall(r"Component:\s*(\S+)", body):
                components.append(cm)

            entries.append({
                "id": str(entry_id),
                "source": "fabric",
                "source_path": str(f),
                "source_key": f.name,
                "category": meta.get("type", "fabric"),
                "title": title,
                "body": body,
                "components": json.dumps(components) if components else None,
                "timestamp": meta.get("timestamp"),
                "confidence": 1.0,
                "entry_type": etype_raw,
                "tags": json.dumps(tags) if tags else None,
            })

            # Map refs to entry_links
            refs = meta.get("refs", [])
            if isinstance(refs, str):
                refs = [refs]
            for ref in refs:
                links.append((str(entry_id), str(ref), "references"))

    _upsert_entries(conn, entries)
    _upsert_links(conn, links)
    return len(entries), filename_to_id


# ---------------------------------------------------------------------------
# system_brain indexing
# ---------------------------------------------------------------------------

def _index_learnings(conn):
    if not BRAIN_DB.exists():
        return 0
    brain = sqlite3.connect(str(BRAIN_DB))
    brain.row_factory = sqlite3.Row
    rows = brain.execute(
        "SELECT id, category, insight, evidence, confidence, source, created_at FROM learnings"
    ).fetchall()
    brain.close()

    entries = []
    for r in rows:
        insight = r["insight"] or ""
        evidence = r["evidence"] or ""
        title = insight[:100].replace("\n", " ")
        body = insight
        if evidence:
            body += "\n\nEvidence: " + evidence
        entries.append({
            "id": f"learning-{r['id']}",
            "source": "learning",
            "source_path": str(BRAIN_DB),
            "source_key": str(r["id"]),
            "category": r["category"],
            "title": title,
            "body": body,
            "components": None,
            "timestamp": r["created_at"],
            "confidence": r["confidence"] or 0.5,
            "entry_type": "learning",
            "tags": json.dumps([r["category"]]) if r["category"] else None,
        })
    _upsert_entries(conn, entries)
    return len(entries)


def _index_corrections(conn):
    if not BRAIN_DB.exists():
        return 0
    brain = sqlite3.connect(str(BRAIN_DB))
    brain.row_factory = sqlite3.Row
    rows = brain.execute(
        "SELECT id, component, problem, root_cause, fix, first_seen, tags FROM corrections"
    ).fetchall()
    brain.close()

    entries = []
    for r in rows:
        problem = r["problem"] or ""
        fix = r["fix"] or ""
        root_cause = r["root_cause"] or ""
        title = problem[:100].replace("\n", " ")
        body = f"Problem: {problem}\n"
        if root_cause:
            body += f"Root cause: {root_cause}\n"
        body += f"Fix: {fix}"
        comp = r["component"] or ""
        tags_raw = r["tags"]
        tags = None
        if tags_raw:
            try:
                tags = tags_raw  # already stored as text
            except Exception:
                pass
        entries.append({
            "id": f"correction-{r['id']}",
            "source": "correction",
            "source_path": str(BRAIN_DB),
            "source_key": str(r["id"]),
            "category": "correction",
            "title": title,
            "body": body,
            "components": json.dumps([comp]) if comp else None,
            "timestamp": r["first_seen"],
            "confidence": 1.0,
            "entry_type": "correction",
            "tags": tags,
        })
    _upsert_entries(conn, entries)
    return len(entries)


def _index_health(conn):
    if not BRAIN_DB.exists():
        return 0
    brain = sqlite3.connect(str(BRAIN_DB))
    brain.row_factory = sqlite3.Row
    rows = brain.execute(
        "SELECT component, status, last_error, consecutive_failures, checked_at FROM health"
    ).fetchall()
    brain.close()

    entries = []
    for r in rows:
        comp = r["component"] or "unknown"
        status = r["status"] or "unknown"
        last_err = r["last_error"] or ""
        failures = r["consecutive_failures"] or 0
        title = f"Health: {comp} [{status}]"
        body = f"Component: {comp}\nStatus: {status}\nConsecutive failures: {failures}"
        if last_err:
            body += f"\nLast error: {last_err}"
        entries.append({
            "id": f"health-{_make_id('health', comp)}",
            "source": "health",
            "source_path": str(BRAIN_DB),
            "source_key": comp,
            "category": "health",
            "title": title,
            "body": body,
            "components": json.dumps([comp]),
            "timestamp": r["checked_at"],
            "confidence": 1.0,
            "entry_type": "health",
            "tags": json.dumps([status]),
        })
    _upsert_entries(conn, entries)
    return len(entries)


# ---------------------------------------------------------------------------
# Ontology JSON indexing
# ---------------------------------------------------------------------------

def _load_json(name):
    p = ONTOLOGY_DIR / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(errors="replace"))
    except Exception:
        return {}


def _index_error_taxonomy(conn):
    data = _load_json("error_taxonomy.json")
    classes = data.get("error_classes", [])
    entries = []
    for ec in classes:
        cls = ec.get("class", "unknown")
        eid = f"errclass-{_make_id('errclass', cls)}"
        title = f"Error class: {cls}"
        body_parts = [
            f"Pattern: {ec.get('pattern', '')}",
            f"Occurrences: {ec.get('occurrences', 0)}",
            f"Root cause: {ec.get('root_cause', '')}",
            f"Recommendation: {ec.get('recommendation', '')}",
        ]
        affected = ec.get("affected_components", [])
        entries.append({
            "id": eid,
            "source": "ontology",
            "source_path": str(ONTOLOGY_DIR / "error_taxonomy.json"),
            "source_key": cls,
            "category": "error_class",
            "title": title,
            "body": "\n".join(body_parts),
            "components": json.dumps(affected) if affected else None,
            "timestamp": data.get("generated_at"),
            "confidence": 1.0,
            "entry_type": "error_class",
            "tags": json.dumps(["error", cls]),
        })
    _upsert_entries(conn, entries)
    return len(entries)


def _index_recovery_patterns(conn, fabric_name_map=None):
    data = _load_json("recovery_patterns.json")
    patterns = data.get("patterns", [])
    entries = []
    links = []
    fabric_name_map = fabric_name_map or {}
    for i, p in enumerate(patterns):
        pid = f"recpat-{_make_id('recpat', p.get('problem', str(i)))}"
        title = f"Recovery: {(p.get('problem', '') or '')[:100]}"
        body = f"Problem: {p.get('problem', '')}\nFix: {p.get('fix', '')}"
        if p.get("recurrence_details"):
            body += f"\nRecurrence: {p['recurrence_details']}"
        if p.get("severity"):
            body += f"\nSeverity: {p['severity']}"
        entries.append({
            "id": pid,
            "source": "ontology",
            "source_path": str(ONTOLOGY_DIR / "recovery_patterns.json"),
            "source_key": str(i),
            "category": "recovery",
            "title": title,
            "body": body,
            "components": None,
            "timestamp": p.get("date"),
            "confidence": 1.0 if p.get("confidence") == "high" else 0.7,
            "entry_type": "pattern",
            "tags": json.dumps(["recovery"]),
        })
        for ref in p.get("fabric_refs", []):
            # Resolve filename refs to actual entry IDs
            target_id = fabric_name_map.get(str(ref), str(ref))
            links.append((pid, target_id, "references"))
    _upsert_entries(conn, entries)
    _upsert_links(conn, links)
    return len(entries)


def _index_correlations(conn):
    data = _load_json("correlations.json")
    corrs = data.get("correlations", [])
    entries = []
    for i, c in enumerate(corrs):
        a = c.get("component_a", "")
        b = c.get("component_b", "")
        cid = f"corr-{_make_id('corr', a, b)}"
        title = f"Correlation: {a} <-> {b}"
        body = f"Type: {c.get('type', '')}\nCorrelation: {c.get('correlation', '')}\nExplanation: {c.get('explanation', '')}"
        if c.get("lag_minutes"):
            body += f"\nLag: {c['lag_minutes']} minutes"
        if c.get("evidence"):
            body += f"\nEvidence: {c['evidence']}"
        comps = [x for x in [a, b] if x]
        entries.append({
            "id": cid,
            "source": "ontology",
            "source_path": str(ONTOLOGY_DIR / "correlations.json"),
            "source_key": f"{a}:{b}",
            "category": "correlation",
            "title": title,
            "body": body,
            "components": json.dumps(comps) if comps else None,
            "timestamp": data.get("timestamp"),
            "confidence": abs(float(c.get("correlation", 0))) if c.get("correlation") else 0.5,
            "entry_type": "correlation",
            "tags": json.dumps(["correlation", c.get("type", "")]),
        })
    _upsert_entries(conn, entries)
    return len(entries)


def _index_failure_cascades(conn):
    data = _load_json("failure_cascades.json")
    cascades = data.get("cascades", [])
    entries = []
    for i, c in enumerate(cascades):
        trigger = c.get("trigger", str(i))
        cid = f"cascade-{_make_id('cascade', trigger)}"
        title = f"Cascade: {trigger}"
        downstream = c.get("downstream_failures", [])
        body = f"Trigger: {trigger}\nDescription: {c.get('description', '')}\nSeverity: {c.get('severity', '')}"
        body += f"\nDownstream: {', '.join(downstream)}"
        body += f"\nTime to cascade: {c.get('time_to_cascade_minutes', '?')} min"
        comps = [trigger] + downstream
        entries.append({
            "id": cid,
            "source": "ontology",
            "source_path": str(ONTOLOGY_DIR / "failure_cascades.json"),
            "source_key": trigger,
            "category": "cascade",
            "title": title,
            "body": body,
            "components": json.dumps(comps),
            "timestamp": data.get("analysis_timestamp"),
            "confidence": 1.0,
            "entry_type": "cascade",
            "tags": json.dumps(["cascade", c.get("severity", "")]),
        })
    _upsert_entries(conn, entries)
    return len(entries)


def _index_enhancement_opportunities(conn):
    data = _load_json("enhancement_opportunities.json")
    opps = data.get("opportunities", [])
    entries = []
    for i, o in enumerate(opps):
        comp = o.get("component", "")
        cat = o.get("category", "")
        eid = f"enhance-{_make_id('enhance', comp, cat, str(i))}"
        title = f"Enhancement: {comp} — {cat}"
        body = f"Observation: {o.get('observation', '')}\nRecommendation: {o.get('recommendation', '')}\nPriority: {o.get('priority', '')}\nEffort: {o.get('effort', '')}"
        entries.append({
            "id": eid,
            "source": "ontology",
            "source_path": str(ONTOLOGY_DIR / "enhancement_opportunities.json"),
            "source_key": f"{comp}:{cat}",
            "category": "enhancement",
            "title": title,
            "body": body,
            "components": json.dumps([comp]) if comp else None,
            "timestamp": data.get("timestamp"),
            "confidence": 1.0,
            "entry_type": "enhancement",
            "tags": json.dumps(["enhancement", o.get("priority", "")]),
        })
    _upsert_entries(conn, entries)
    return len(entries)


def _index_pipeline_bottlenecks(conn):
    data = _load_json("pipeline_bottlenecks.json")
    bottlenecks = data.get("bottlenecks", [])
    entries = []
    for i, b in enumerate(bottlenecks):
        pipeline = b.get("pipeline", "")
        stage = b.get("stage", "")
        bid = f"bottleneck-{_make_id('bottleneck', pipeline, stage, str(i))}"
        title = f"Bottleneck: {pipeline} / {stage}"
        body = (
            f"Pipeline: {pipeline}\nStage: {stage}\n"
            f"Avg duration: {b.get('avg_duration_seconds', '')}s\n"
            f"Max duration: {b.get('max_duration_seconds', '')}s\n"
            f"Failure rate: {b.get('failure_rate_pct', '')}%\n"
            f"Runs: {b.get('runs', '')}"
        )
        entries.append({
            "id": bid,
            "source": "ontology",
            "source_path": str(ONTOLOGY_DIR / "pipeline_bottlenecks.json"),
            "source_key": f"{pipeline}:{stage}",
            "category": "bottleneck",
            "title": title,
            "body": body,
            "components": json.dumps([pipeline]) if pipeline else None,
            "timestamp": data.get("generated_at"),
            "confidence": 1.0,
            "entry_type": "bottleneck",
            "tags": json.dumps(["bottleneck", pipeline]),
        })
    _upsert_entries(conn, entries)
    return len(entries)


def _index_risk_scores(conn):
    data = _load_json("risk_scores.json")
    components = data.get("components", [])
    entries = []
    for c in components:
        cid_val = c.get("id", "")
        rid = f"risk-{_make_id('risk', cid_val)}"
        title = f"Risk: {cid_val} (score={c.get('risk_score', '?')})"
        factors = c.get("factors", {})
        body = f"Component: {cid_val}\nType: {c.get('type', '')}\nRisk score: {c.get('risk_score', '')}\nTrend: {c.get('trend', '')}"
        if isinstance(factors, dict):
            body += "\nFactors: " + ", ".join(f"{k}={v}" for k, v in factors.items())
        if c.get("predicted_failure"):
            body += f"\nPredicted failure: {c['predicted_failure']}"
        entries.append({
            "id": rid,
            "source": "ontology",
            "source_path": str(ONTOLOGY_DIR / "risk_scores.json"),
            "source_key": cid_val,
            "category": "risk",
            "title": title,
            "body": body,
            "components": json.dumps([cid_val]) if cid_val else None,
            "timestamp": data.get("timestamp"),
            "confidence": 1.0,
            "entry_type": "risk",
            "tags": json.dumps(["risk", c.get("trend", "")]),
        })
    _upsert_entries(conn, entries)
    return len(entries)


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def _upsert_entries(conn, entries):
    for e in entries:
        conn.execute(
            """INSERT OR REPLACE INTO knowledge_entries
               (id, source, source_path, source_key, category, title, body,
                components, timestamp, confidence, entry_type, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                e["id"], e["source"], e["source_path"], e["source_key"],
                e["category"], e["title"], e["body"], e["components"],
                e["timestamp"], e["confidence"], e["entry_type"], e["tags"],
            ),
        )
    conn.commit()


def _upsert_links(conn, links):
    for from_id, to_id, link_type in links:
        conn.execute(
            "INSERT OR IGNORE INTO entry_links (from_id, to_id, link_type) VALUES (?, ?, ?)",
            (from_id, to_id, link_type),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Query interface
# ---------------------------------------------------------------------------

def search(query: str, limit: int = 10, source: str = None, entry_type: str = None) -> list:
    """FTS5 BM25 search across all knowledge. Returns ranked results."""
    conn = _connect()
    # Build FTS query - escape special chars
    fts_query = re.sub(r'[^\w\s]', ' ', query).strip()
    # Turn words into OR query for broader matching
    words = fts_query.split()
    if not words:
        return []
    fts_expr = " OR ".join(words)

    sql = """
        SELECT ke.*, bm25(knowledge_fts) as rank
        FROM knowledge_fts
        JOIN knowledge_entries ke ON knowledge_fts.rowid = ke.rowid
        WHERE knowledge_fts MATCH ?
    """
    params = [fts_expr]

    if source:
        sql += " AND ke.source = ?"
        params.append(source)
    if entry_type:
        sql += " AND ke.entry_type = ?"
        params.append(entry_type)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    return [dict(r) for r in rows]


def get_related(entry_id: str, depth: int = 1) -> list:
    """Follow entry_links from a given entry."""
    conn = _connect()
    visited = set()
    frontier = {entry_id}
    results = []

    for _ in range(depth):
        if not frontier:
            break
        next_frontier = set()
        for eid in frontier:
            if eid in visited:
                continue
            visited.add(eid)
            rows = conn.execute(
                """SELECT el.to_id, el.link_type, ke.*
                   FROM entry_links el
                   LEFT JOIN knowledge_entries ke ON ke.id = el.to_id
                   WHERE el.from_id = ?""",
                (eid,),
            ).fetchall()
            for r in rows:
                results.append(dict(r))
                if r["to_id"] not in visited:
                    next_frontier.add(r["to_id"])
            # Also reverse links
            rows2 = conn.execute(
                """SELECT el.from_id as related_id, el.link_type, ke.*
                   FROM entry_links el
                   LEFT JOIN knowledge_entries ke ON ke.id = el.from_id
                   WHERE el.to_id = ?""",
                (eid,),
            ).fetchall()
            for r in rows2:
                results.append(dict(r))
                if r["related_id"] not in visited:
                    next_frontier.add(r["related_id"])
        frontier = next_frontier

    conn.close()
    return results


def get_by_component(component: str) -> list:
    """Find all entries mentioning a component."""
    conn = _connect()
    # Search in the components JSON field and in body text
    rows = conn.execute(
        """SELECT * FROM knowledge_entries
           WHERE components LIKE ? OR body LIKE ?
           ORDER BY timestamp DESC""",
        (f"%{component}%", f"%{component}%"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """Count entries by source and type."""
    conn = _connect()
    stats = {}
    stats["total"] = conn.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0]
    stats["by_source"] = {}
    for row in conn.execute(
        "SELECT source, COUNT(*) as cnt FROM knowledge_entries GROUP BY source ORDER BY cnt DESC"
    ).fetchall():
        stats["by_source"][row["source"]] = row["cnt"]
    stats["by_type"] = {}
    for row in conn.execute(
        "SELECT entry_type, COUNT(*) as cnt FROM knowledge_entries GROUP BY entry_type ORDER BY cnt DESC"
    ).fetchall():
        stats["by_type"][row["entry_type"]] = row["cnt"]
    stats["links"] = conn.execute("SELECT COUNT(*) FROM entry_links").fetchone()[0]
    conn.close()
    return stats


# ---------------------------------------------------------------------------
# Build / incremental
# ---------------------------------------------------------------------------

def build_index():
    """Full rebuild from all sources."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = _connect()
    _init_db(conn)

    counts = {}
    t0 = time.time()
    fabric_count, fabric_name_map = _index_fabric(conn)
    counts["fabric"] = fabric_count
    counts["learnings"] = _index_learnings(conn)
    counts["corrections"] = _index_corrections(conn)
    counts["health"] = _index_health(conn)
    counts["error_taxonomy"] = _index_error_taxonomy(conn)
    counts["recovery_patterns"] = _index_recovery_patterns(conn, fabric_name_map)
    counts["correlations"] = _index_correlations(conn)
    counts["failure_cascades"] = _index_failure_cascades(conn)
    counts["enhancements"] = _index_enhancement_opportunities(conn)
    counts["bottlenecks"] = _index_pipeline_bottlenecks(conn)
    counts["risk_scores"] = _index_risk_scores(conn)

    elapsed = time.time() - t0
    conn.execute(
        "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
        ("last_build", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )
    conn.commit()
    conn.close()

    total = sum(counts.values())
    print(f"Index built in {elapsed:.2f}s — {total} entries indexed")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    return counts


def incremental_update():
    """Check mtimes, only re-index changed sources."""
    conn = _connect()
    _init_db(conn)

    last_build_row = conn.execute(
        "SELECT value FROM index_meta WHERE key = 'last_build'"
    ).fetchone()

    if not last_build_row:
        conn.close()
        return build_index()

    # For simplicity, just rebuild everything (mtime tracking adds complexity
    # for marginal gain on a small corpus). Full build is fast enough (<1s).
    conn.close()
    return build_index()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_results(results):
    if not results:
        print("No results found.")
        return
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        src = r.get("source", "")
        etype = r.get("entry_type", "")
        eid = r.get("id", "")
        conf = r.get("confidence", "")
        print(f"\n[{i}] {title}")
        print(f"    id={eid}  source={src}  type={etype}  confidence={conf}")
        body = r.get("body", "")
        if body:
            preview = body[:200].replace("\n", " ")
            if len(body) > 200:
                preview += "..."
            print(f"    {preview}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "build":
        build_index()

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: unified_index.py search <query> [--source X] [--type Y] [--limit N]")
            sys.exit(1)
        query = sys.argv[2]
        source = None
        etype = None
        limit = 10
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--source" and i + 1 < len(sys.argv):
                source = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--type" and i + 1 < len(sys.argv):
                etype = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1
        results = search(query, limit=limit, source=source, entry_type=etype)
        _print_results(results)

    elif cmd == "component":
        if len(sys.argv) < 3:
            print("Usage: unified_index.py component <component_name>")
            sys.exit(1)
        results = get_by_component(sys.argv[2])
        _print_results(results)

    elif cmd == "related":
        if len(sys.argv) < 3:
            print("Usage: unified_index.py related <entry_id> [--depth N]")
            sys.exit(1)
        entry_id = sys.argv[2]
        depth = 1
        if len(sys.argv) > 3 and sys.argv[3] == "--depth" and len(sys.argv) > 4:
            depth = int(sys.argv[4])
        results = get_related(entry_id, depth=depth)
        _print_results(results)

    elif cmd == "stats":
        stats = get_stats()
        print(f"Total entries: {stats['total']}")
        print(f"Entry links:   {stats['links']}")
        print("\nBy source:")
        for k, v in stats["by_source"].items():
            print(f"  {k}: {v}")
        print("\nBy type:")
        for k, v in stats["by_type"].items():
            print(f"  {k}: {v}")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
