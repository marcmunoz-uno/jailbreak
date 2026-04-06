#!/usr/bin/env python3
"""
Semantic Link Graph (SLG) — causal reasoning edges on top of the Unified Knowledge Index.

Builds a knowledge graph from:
  - system_brain.db (health, corrections, learnings)
  - ontology JSON files (correlations, dependency_graph, error_taxonomy,
    recovery_patterns, failure_cascades)
  - fabric entries (~/fabric/ and ~/fabric/cold/)

Usage:
  python3 knowledge_graph.py build
  python3 knowledge_graph.py diagnose "cron:tranchi-upload"
  python3 knowledge_graph.py traverse "config:openclaw.json" --depth 2
  python3 knowledge_graph.py search "dscr pipeline"
  python3 knowledge_graph.py stats
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Set

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DB_PATH = Path(os.path.expanduser("~/.openclaw/data/knowledge_graph.db"))
BRAIN_DB = Path(os.path.expanduser("~/.openclaw/data/system_brain.db"))
ONTOLOGY_DIR = Path(os.path.expanduser("~/.openclaw/ontology"))
FABRIC_DIR = Path(os.path.expanduser("~/fabric"))
FABRIC_COLD_DIR = FABRIC_DIR / "cold"

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_path TEXT,
    label TEXT NOT NULL,
    body TEXT,
    timestamp TEXT,
    metadata TEXT
);
CREATE TABLE IF NOT EXISTS edges (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    evidence TEXT,
    created_at TEXT,
    PRIMARY KEY (from_id, to_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
"""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Node / edge insertion helpers
# ---------------------------------------------------------------------------

def _upsert_node(conn: sqlite3.Connection, node_id: str, source: str,
                 label: str, body: str | None = None,
                 source_path: str | None = None,
                 timestamp: str | None = None,
                 metadata: dict | None = None):
    meta_json = json.dumps(metadata) if metadata else None
    conn.execute(
        """INSERT INTO nodes (id, source, source_path, label, body, timestamp, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             source=excluded.source,
             source_path=COALESCE(excluded.source_path, nodes.source_path),
             label=excluded.label,
             body=COALESCE(excluded.body, nodes.body),
             timestamp=COALESCE(excluded.timestamp, nodes.timestamp),
             metadata=COALESCE(excluded.metadata, nodes.metadata)
        """,
        (node_id, source, source_path, label, body, timestamp, meta_json),
    )


def _upsert_edge(conn: sqlite3.Connection, from_id: str, to_id: str,
                  relation: str, weight: float = 1.0,
                  evidence: str | None = None):
    conn.execute(
        """INSERT INTO edges (from_id, to_id, relation, weight, evidence, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(from_id, to_id, relation) DO UPDATE SET
             weight=MAX(edges.weight, excluded.weight),
             evidence=COALESCE(excluded.evidence, edges.evidence),
             created_at=COALESCE(excluded.created_at, edges.created_at)
        """,
        (from_id, to_id, relation, weight, evidence, _now_iso()),
    )


# ---------------------------------------------------------------------------
# Normalise component IDs
# ---------------------------------------------------------------------------

def _norm_id(raw: str) -> str:
    """Normalise a string into a graph node id."""
    s = raw.strip().lower()
    # already looks like a qualified id
    if ":" in s and not s.startswith("http"):
        return s
    # common transformations
    s = re.sub(r"[^a-z0-9_:/-]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _build_components_from_brain(conn: sqlite3.Connection):
    """Create component nodes from system_brain.db health + corrections tables."""
    if not BRAIN_DB.exists():
        return
    brain = _connect(BRAIN_DB)
    try:
        for row in brain.execute("SELECT * FROM health"):
            cid = _norm_id(row["component"])
            _upsert_node(conn, cid, "component", row["component"],
                         body=row["last_error"],
                         timestamp=row["checked_at"],
                         metadata={
                             "status": row["status"],
                             "consecutive_failures": row["consecutive_failures"],
                         })
        for row in brain.execute("SELECT DISTINCT component FROM corrections"):
            cid = _norm_id(row["component"])
            _upsert_node(conn, cid, "component", row["component"])
    finally:
        brain.close()


def _build_components_from_ontology(conn: sqlite3.Connection):
    """Create component nodes from ontology JSON files."""
    # dependency_graph nodes
    dep = _load_json(ONTOLOGY_DIR / "dependency_graph.json")
    if dep:
        for node in dep.get("nodes", []):
            nid = node.get("id", "")
            label = node.get("name") or node.get("id", "")
            _upsert_node(conn, nid, "component", label,
                         metadata={k: v for k, v in node.items()
                                   if k not in ("id", "name")})

    # error_taxonomy affected_components
    tax = _load_json(ONTOLOGY_DIR / "error_taxonomy.json")
    if tax:
        for ec in tax.get("error_classes", []):
            for comp in ec.get("affected_components", []):
                cid = _norm_id(comp)
                _upsert_node(conn, cid, "component", comp)

    # correlations components
    corr = _load_json(ONTOLOGY_DIR / "correlations.json")
    if corr:
        for c in corr.get("correlations", []):
            for key in ("component_a", "component_b"):
                raw = c.get(key, "")
                if raw:
                    cid = _norm_id(raw)
                    _upsert_node(conn, cid, "component", raw)

    # failure_cascades trigger_entity and downstream
    fc = _load_json(ONTOLOGY_DIR / "failure_cascades.json")
    if fc:
        for cas in fc.get("cascades", []):
            trigger = cas.get("trigger", "")
            if trigger:
                tid = _norm_id(trigger)
                _upsert_node(conn, tid, "component", trigger)
            for df in cas.get("downstream_failures", []):
                did = _norm_id(df)
                _upsert_node(conn, did, "component", df)


def _build_knowledge_from_brain(conn: sqlite3.Connection):
    """Create knowledge nodes from system_brain.db learnings + corrections."""
    if not BRAIN_DB.exists():
        return
    brain = _connect(BRAIN_DB)
    try:
        for row in brain.execute("SELECT * FROM learnings"):
            nid = f"learning:{row['id']}"
            _upsert_node(conn, nid, "learning", row["insight"][:120],
                         body=row["insight"],
                         timestamp=row["created_at"],
                         metadata={
                             "category": row["category"],
                             "confidence": row["confidence"],
                             "source": row["source"],
                             "actionable": bool(row["actionable"]),
                         })
            # affects_component edge: category -> component
            cat = row["category"]
            if cat:
                cat_id = _norm_id(cat)
                _upsert_edge(conn, nid, cat_id, "affects_component",
                             weight=row["confidence"] or 0.5,
                             evidence=row["evidence"] if "evidence" in row.keys() else None)

        for row in brain.execute("SELECT * FROM corrections"):
            nid = f"correction:{row['id']}"
            _upsert_node(conn, nid, "correction",
                         f"Fix: {row['problem'][:100]}",
                         body=f"Problem: {row['problem']}\nRoot cause: {row['root_cause']}\nFix: {row['fix']}",
                         timestamp=row["last_seen"],
                         metadata={
                             "component": row["component"],
                             "occurrences": row["occurrences"],
                             "verified": bool(row["fix_verified"]),
                             "fixed_by": row["fixed_by"],
                         })
            cid = _norm_id(row["component"])
            _upsert_edge(conn, nid, cid, "affects_component",
                         evidence=row["problem"])
            # correction fixes the problem
            _upsert_edge(conn, nid, cid, "fixes",
                         evidence=row["fix"])
    finally:
        brain.close()


def _parse_fabric_frontmatter(text: str) -> dict:
    """Parse YAML-ish frontmatter between --- delimiters."""
    fm: dict = {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return fm
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # simple list
        if val.startswith("[") and val.endswith("]"):
            val = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        fm[key] = val
    return fm


def _build_fabric_nodes(conn: sqlite3.Connection):
    """Create nodes for every fabric entry."""
    dirs = []
    if FABRIC_DIR.exists():
        dirs.append(("fabric", FABRIC_DIR))
    if FABRIC_COLD_DIR.exists():
        dirs.append(("fabric", FABRIC_COLD_DIR))

    for source_tag, d in dirs:
        for fp in sorted(d.glob("*.md")):
            text = fp.read_text(errors="replace")
            fm = _parse_fabric_frontmatter(text)
            fid = fm.get("id", fp.stem)
            nid = f"fabric:{fid}"
            label = fm.get("summary") or fm.get("action_needed") or fp.stem
            if isinstance(label, list):
                label = " ".join(label)
            label = str(label)[:200]

            _upsert_node(conn, nid, source_tag, label,
                         body=text[:2000],
                         source_path=str(fp),
                         timestamp=fm.get("timestamp"),
                         metadata={k: v for k, v in fm.items()
                                   if k not in ("id",)})

            # refs -> references edges
            refs = fm.get("refs")
            if isinstance(refs, list):
                for ref in refs:
                    ref_id = f"fabric:{ref.replace('.md', '')}"
                    _upsert_edge(conn, nid, ref_id, "references")
            elif isinstance(refs, str) and refs:
                ref_id = f"fabric:{refs.replace('.md', '')}"
                _upsert_edge(conn, nid, ref_id, "references")

            # assigned_to -> escalated_to
            assigned = fm.get("assigned_to")
            agent = fm.get("agent")
            if assigned and agent and assigned != agent:
                _upsert_edge(conn, nid, f"agent:{assigned}", "escalated_to",
                             evidence=f"from {agent}")


def _build_error_taxonomy_nodes(conn: sqlite3.Connection):
    """Create nodes for each error class from error_taxonomy.json."""
    tax = _load_json(ONTOLOGY_DIR / "error_taxonomy.json")
    if not tax:
        return
    for ec in tax.get("error_classes", []):
        cls = ec["class"]
        nid = f"error_class:{cls}"
        _upsert_node(conn, nid, "ontology", cls,
                     body=ec.get("root_cause"),
                     metadata={
                         "pattern": ec.get("pattern"),
                         "occurrences": ec.get("occurrences"),
                         "fix_applied": ec.get("fix_applied"),
                         "recurrence_risk": ec.get("recurrence_risk"),
                     })
        for comp in ec.get("affected_components", []):
            cid = _norm_id(comp)
            _upsert_edge(conn, nid, cid, "affects_component",
                         weight=min(1.0, (ec.get("occurrences", 1) / 1000)),
                         evidence=ec.get("pattern"))


def _build_recovery_pattern_nodes(conn: sqlite3.Connection):
    """Create nodes for each recovery pattern."""
    rec = _load_json(ONTOLOGY_DIR / "recovery_patterns.json")
    if not rec:
        return
    for i, pat in enumerate(rec.get("patterns", [])):
        nid = f"recovery:{i}"
        problem_label = pat["problem"][:120]
        _upsert_node(conn, nid, "ontology", f"Recovery: {problem_label}",
                     body=f"Problem: {pat['problem']}\nFix: {pat['fix']}",
                     timestamp=pat.get("date"),
                     metadata={
                         "severity": pat.get("severity"),
                         "confidence": pat.get("confidence"),
                         "recurred": pat.get("recurred"),
                     })
        # problem -> fixes -> applicable components
        for comp in pat.get("applicable_to", []):
            cid = _norm_id(comp)
            _upsert_edge(conn, nid, cid, "fixes",
                         evidence=pat["fix"])
        # references to fabric entries
        for ref in pat.get("fabric_refs", []):
            ref_id = f"fabric:{ref.replace('.md', '')}"
            _upsert_edge(conn, nid, ref_id, "references",
                         evidence="recovery pattern fabric ref")


def _build_correlation_edges(conn: sqlite3.Connection):
    """Create edges from correlations.json."""
    corr = _load_json(ONTOLOGY_DIR / "correlations.json")
    if not corr:
        return
    type_map = {
        "causal": "causes",
        "resource_contention": "co_occurs_with",
        "data_dependency": "depends_on",
        "functional_dependency": "depends_on",
        "pipeline_dependency": "depends_on",
        "self_cascading": "causes",
    }
    for c in corr.get("correlations", []):
        a = _norm_id(c["component_a"])
        b = _norm_id(c["component_b"])
        ctype = c.get("type", "")
        relation = type_map.get(ctype, "co_occurs_with")
        weight = c.get("correlation", 0.5)
        _upsert_edge(conn, a, b, relation,
                     weight=weight,
                     evidence=c.get("explanation"))
        # Create a correlation node too
        corr_id = f"correlation:{a}--{b}"
        _upsert_node(conn, corr_id, "ontology",
                     f"Correlation: {c['component_a']} <-> {c['component_b']}",
                     body=c.get("explanation"),
                     metadata={
                         "type": ctype,
                         "correlation": weight,
                         "lag_minutes": c.get("lag_minutes"),
                     })
        _upsert_edge(conn, corr_id, a, "affects_component")
        _upsert_edge(conn, corr_id, b, "affects_component")


def _build_dependency_edges(conn: sqlite3.Connection):
    """Create depends_on edges from dependency_graph.json."""
    dep = _load_json(ONTOLOGY_DIR / "dependency_graph.json")
    if not dep:
        return
    for edge in dep.get("edges", []):
        from_id = edge["from"]
        to_id = edge["to"]
        etype = edge.get("type", "depends_on")
        relation = "depends_on"
        if etype in ("monitors", "validates"):
            relation = "references"
        elif etype in ("orchestrates",):
            relation = "depends_on"
        elif etype in ("reads", "reads_writes"):
            relation = "depends_on"
        elif etype in ("produces", "writes"):
            relation = "depends_on"  # producer depends on nothing, consumer depends on producer
        elif etype == "depends_on":
            relation = "depends_on"

        _upsert_edge(conn, from_id, to_id, relation,
                     evidence=edge.get("reason") or etype)


def _build_cascade_nodes(conn: sqlite3.Connection):
    """Create nodes + edges from failure_cascades.json."""
    fc = _load_json(ONTOLOGY_DIR / "failure_cascades.json")
    if not fc:
        return
    for i, cas in enumerate(fc.get("cascades", [])):
        trigger = cas.get("trigger", f"cascade_trigger_{i}")
        nid = f"cascade:{_norm_id(trigger)}"
        _upsert_node(conn, nid, "ontology",
                     f"Cascade: {cas.get('description', trigger)[:150]}",
                     body=cas.get("pattern"),
                     metadata={
                         "frequency": cas.get("frequency"),
                         "severity": cas.get("severity"),
                         "time_to_cascade_minutes": cas.get("time_to_cascade_minutes"),
                     })
        # trigger causes downstream failures
        tid = _norm_id(trigger)
        _upsert_edge(conn, nid, tid, "causes",
                     evidence=cas.get("pattern"))
        for df in cas.get("downstream_failures", []):
            did = _norm_id(df)
            _upsert_edge(conn, tid, did, "causes",
                         weight=min(1.0, cas.get("frequency", 1) / 100),
                         evidence=cas.get("pattern"))


# ---------------------------------------------------------------------------
# Full build
# ---------------------------------------------------------------------------

def build_graph():
    """Full rebuild from all sources."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = _connect()
    _init_db(conn)

    print("  [1/8] Components from system_brain.db ...")
    _build_components_from_brain(conn)
    conn.commit()

    print("  [2/8] Components from ontology JSONs ...")
    _build_components_from_ontology(conn)
    conn.commit()

    print("  [3/8] Knowledge nodes from system_brain.db ...")
    _build_knowledge_from_brain(conn)
    conn.commit()

    print("  [4/8] Fabric entry nodes ...")
    _build_fabric_nodes(conn)
    conn.commit()

    print("  [5/8] Error taxonomy nodes ...")
    _build_error_taxonomy_nodes(conn)
    conn.commit()

    print("  [6/8] Recovery pattern nodes ...")
    _build_recovery_pattern_nodes(conn)
    conn.commit()

    print("  [7/8] Correlation + dependency edges ...")
    _build_correlation_edges(conn)
    _build_dependency_edges(conn)
    conn.commit()

    print("  [8/8] Failure cascade nodes ...")
    _build_cascade_nodes(conn)
    conn.commit()

    s = stats(conn)
    conn.close()
    print(f"  Done. {s['node_count']} nodes, {s['edge_count']} edges.")
    return s


# ---------------------------------------------------------------------------
# Query interface
# ---------------------------------------------------------------------------

def search(query: str, limit: int = 10) -> list[dict]:
    """Text search on node labels/bodies."""
    conn = _connect()
    terms = query.strip().split()
    # Build LIKE clauses for each term
    where_parts = []
    params: list = []
    for t in terms:
        where_parts.append("(label LIKE ? OR body LIKE ? OR id LIKE ?)")
        p = f"%{t}%"
        params.extend([p, p, p])
    where = " AND ".join(where_parts) if where_parts else "1=1"
    rows = conn.execute(
        f"SELECT * FROM nodes WHERE {where} ORDER BY timestamp DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def traverse(node_id: str, relation: str | None = None, depth: int = 2) -> list[dict]:
    """BFS from a node. Optionally filter by relation type."""
    conn = _connect()
    visited: set[str] = set()
    results: list[dict] = []
    queue: deque[tuple[str, int]] = deque()
    queue.append((node_id, 0))
    visited.add(node_id)

    while queue:
        current, d = queue.popleft()
        if d > depth:
            continue

        # Get outgoing edges
        if relation:
            edges = conn.execute(
                "SELECT * FROM edges WHERE from_id=? AND relation=?",
                (current, relation),
            ).fetchall()
        else:
            edges = conn.execute(
                "SELECT * FROM edges WHERE from_id=?", (current,),
            ).fetchall()

        for e in edges:
            edge_dict = dict(e)
            edge_dict["depth"] = d
            # Attach target node info
            node = conn.execute("SELECT * FROM nodes WHERE id=?",
                                (e["to_id"],)).fetchone()
            if node:
                edge_dict["target_node"] = dict(node)
            results.append(edge_dict)
            if e["to_id"] not in visited:
                visited.add(e["to_id"])
                queue.append((e["to_id"], d + 1))

        # Also get incoming edges
        if relation:
            in_edges = conn.execute(
                "SELECT * FROM edges WHERE to_id=? AND relation=?",
                (current, relation),
            ).fetchall()
        else:
            in_edges = conn.execute(
                "SELECT * FROM edges WHERE to_id=?", (current,),
            ).fetchall()

        for e in in_edges:
            edge_dict = dict(e)
            edge_dict["depth"] = d
            edge_dict["direction"] = "incoming"
            node = conn.execute("SELECT * FROM nodes WHERE id=?",
                                (e["from_id"],)).fetchone()
            if node:
                edge_dict["source_node"] = dict(node)
            results.append(edge_dict)
            if e["from_id"] not in visited:
                visited.add(e["from_id"])
                queue.append((e["from_id"], d + 1))

    conn.close()
    return results


def _traverse_directed(conn: sqlite3.Connection, node_id: str,
                       relation: str, direction: str = "forward",
                       depth: int = 5) -> list[dict]:
    """Internal directed BFS. direction='forward' follows from_id->to_id,
    'backward' follows to_id->from_id."""
    visited: set[str] = set()
    results: list[dict] = []
    queue: deque[tuple[str, int]] = deque()
    queue.append((node_id, 0))
    visited.add(node_id)

    while queue:
        current, d = queue.popleft()
        if d >= depth:
            continue
        if direction == "forward":
            edges = conn.execute(
                "SELECT * FROM edges WHERE from_id=? AND relation=?",
                (current, relation),
            ).fetchall()
            next_field = "to_id"
        else:
            edges = conn.execute(
                "SELECT * FROM edges WHERE to_id=? AND relation=?",
                (current, relation),
            ).fetchall()
            next_field = "from_id"

        for e in edges:
            nxt = e[next_field]
            node = conn.execute("SELECT * FROM nodes WHERE id=?",
                                (nxt,)).fetchone()
            entry = dict(e)
            entry["depth"] = d + 1
            if node:
                entry["node"] = dict(node)
            results.append(entry)
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, d + 1))

    return results


def diagnose(component: str) -> dict:
    """
    The killer query. Given a component, return:
    - All upstream causes (traverse 'causes' edges backward)
    - All downstream effects (traverse 'causes' edges forward)
    - All known fixes (traverse 'fixes' edges)
    - All related learnings (traverse 'affects_component' + 'learned_from')
    - Recent handoffs about this component
    Returns a structured diagnosis.
    """
    conn = _connect()
    cid = _norm_id(component)

    # Check if node exists; try fuzzy match if not
    node_row = conn.execute("SELECT * FROM nodes WHERE id=?", (cid,)).fetchone()
    if not node_row:
        # Fuzzy: find nodes whose id contains the component string
        candidates = conn.execute(
            "SELECT * FROM nodes WHERE id LIKE ?", (f"%{cid}%",)
        ).fetchall()
        if candidates:
            node_row = candidates[0]
            cid = node_row["id"]

    # 1. Upstream causes
    upstream = _traverse_directed(conn, cid, "causes", "backward", depth=4)

    # 2. Downstream effects
    downstream = _traverse_directed(conn, cid, "causes", "forward", depth=4)

    # 3. Known fixes: edges where to_id=cid and relation='fixes'
    fix_edges = conn.execute(
        "SELECT e.*, n.label, n.body FROM edges e "
        "JOIN nodes n ON n.id = e.from_id "
        "WHERE e.to_id=? AND e.relation='fixes'", (cid,)
    ).fetchall()
    fixes = [dict(f) for f in fix_edges]

    # Also find fixes from upstream causes
    upstream_ids = {e.get("node", {}).get("id") or e.get("from_id", "")
                    for e in upstream}
    for uid in upstream_ids:
        if uid:
            more_fixes = conn.execute(
                "SELECT e.*, n.label, n.body FROM edges e "
                "JOIN nodes n ON n.id = e.from_id "
                "WHERE e.to_id=? AND e.relation='fixes'", (uid,)
            ).fetchall()
            fixes.extend(dict(f) for f in more_fixes)

    # 4. Learnings: edges where to_id = cid and relation = 'affects_component'
    #    but from a learning node
    learning_edges = conn.execute(
        "SELECT e.*, n.label, n.body, n.metadata FROM edges e "
        "JOIN nodes n ON n.id = e.from_id "
        "WHERE e.to_id=? AND e.relation='affects_component' "
        "AND n.source IN ('learning', 'ontology')", (cid,)
    ).fetchall()
    learnings = [dict(le) for le in learning_edges]

    # Also search learnings by text match on component name
    comp_terms = cid.split(":")
    for term in comp_terms:
        if len(term) > 2:
            text_learnings = conn.execute(
                "SELECT * FROM nodes WHERE source='learning' AND "
                "(body LIKE ? OR label LIKE ?) LIMIT 10",
                (f"%{term}%", f"%{term}%"),
            ).fetchall()
            for tl in text_learnings:
                learnings.append(dict(tl))

    # 5. Handoffs: fabric entries that mention this component
    handoff_search = cid.replace(":", " ")
    handoffs_rows = conn.execute(
        "SELECT * FROM nodes WHERE source='fabric' AND "
        "(body LIKE ? OR label LIKE ? OR id LIKE ?) "
        "ORDER BY timestamp DESC LIMIT 10",
        (f"%{component}%", f"%{component}%", f"%{cid}%"),
    ).fetchall()
    handoffs = [dict(h) for h in handoffs_rows]

    # Build summary
    summary_parts = []
    if node_row:
        summary_parts.append(f"{cid} — status: {dict(node_row).get('metadata', 'unknown')}")

    if upstream:
        causes_list = []
        for u in upstream[:3]:
            n = u.get("node", {})
            causes_list.append(f"{n.get('id', u.get('from_id', '?'))} "
                             f"(weight {u.get('weight', '?')})")
        summary_parts.append(f"Upstream causes: {', '.join(causes_list)}")

    if fixes:
        fix_summaries = []
        for f in fixes[:3]:
            fix_summaries.append(f.get("label", f.get("evidence", "?"))[:80])
        summary_parts.append(f"Known fixes: {'; '.join(fix_summaries)}")

    if not summary_parts:
        summary_parts.append(f"No direct graph data found for {cid}.")

    conn.close()

    return {
        "component": cid,
        "upstream_causes": upstream,
        "downstream_effects": downstream,
        "known_fixes": fixes,
        "learnings": learnings,
        "handoffs": handoffs,
        "diagnosis_summary": " | ".join(summary_parts),
    }


def find_path(from_id: str, to_id: str) -> list:
    """Find shortest path between two nodes using BFS on all edges."""
    conn = _connect()
    fid = _norm_id(from_id)
    tid = _norm_id(to_id)

    visited: set[str] = set()
    queue: deque[list[str]] = deque()
    queue.append([fid])
    visited.add(fid)

    while queue:
        path = queue.popleft()
        current = path[-1]
        if current == tid:
            # Enrich path with node/edge info
            enriched = []
            for i, nid in enumerate(path):
                node = conn.execute("SELECT * FROM nodes WHERE id=?",
                                    (nid,)).fetchone()
                entry: dict = {"id": nid, "node": dict(node) if node else None}
                if i > 0:
                    edge = conn.execute(
                        "SELECT * FROM edges WHERE "
                        "(from_id=? AND to_id=?) OR (from_id=? AND to_id=?)",
                        (path[i - 1], nid, nid, path[i - 1]),
                    ).fetchone()
                    if edge:
                        entry["edge"] = dict(edge)
                enriched.append(entry)
            conn.close()
            return enriched

        if len(path) > 10:
            continue

        # All neighbors (both directions)
        out_edges = conn.execute(
            "SELECT to_id FROM edges WHERE from_id=?", (current,)
        ).fetchall()
        in_edges = conn.execute(
            "SELECT from_id FROM edges WHERE to_id=?", (current,)
        ).fetchall()
        neighbors = [r["to_id"] for r in out_edges] + [r["from_id"] for r in in_edges]

        for nb in neighbors:
            if nb not in visited:
                visited.add(nb)
                queue.append(path + [nb])

    conn.close()
    return []


def stats(conn: sqlite3.Connection | None = None) -> dict:
    """Node count, edge count, top connected nodes."""
    own = conn is None
    if own:
        conn = _connect()
    nc = conn.execute("SELECT COUNT(*) c FROM nodes").fetchone()["c"]
    ec = conn.execute("SELECT COUNT(*) c FROM edges").fetchone()["c"]

    # Source distribution
    sources = conn.execute(
        "SELECT source, COUNT(*) c FROM nodes GROUP BY source ORDER BY c DESC"
    ).fetchall()

    # Top connected (out-degree)
    top_out = conn.execute(
        "SELECT from_id, COUNT(*) c FROM edges GROUP BY from_id ORDER BY c DESC LIMIT 10"
    ).fetchall()

    # Top connected (in-degree)
    top_in = conn.execute(
        "SELECT to_id, COUNT(*) c FROM edges GROUP BY to_id ORDER BY c DESC LIMIT 10"
    ).fetchall()

    # Relation distribution
    rels = conn.execute(
        "SELECT relation, COUNT(*) c FROM edges GROUP BY relation ORDER BY c DESC"
    ).fetchall()

    if own:
        conn.close()

    return {
        "node_count": nc,
        "edge_count": ec,
        "sources": {r["source"]: r["c"] for r in sources},
        "relation_types": {r["relation"]: r["c"] for r in rels},
        "top_out_degree": [(r["from_id"], r["c"]) for r in top_out],
        "top_in_degree": [(r["to_id"], r["c"]) for r in top_in],
    }


# ---------------------------------------------------------------------------
# Pretty printers
# ---------------------------------------------------------------------------

def _pp_diagnose(result: dict):
    print(f"\n{'='*70}")
    print(f"DIAGNOSIS: {result['component']}")
    print(f"{'='*70}")
    print(f"\nSummary: {result['diagnosis_summary']}")

    if result["upstream_causes"]:
        print(f"\n--- Upstream Causes ({len(result['upstream_causes'])}) ---")
        for u in result["upstream_causes"][:10]:
            n = u.get("node", {})
            nid = n.get("id", u.get("from_id", "?"))
            w = u.get("weight", "?")
            ev = (u.get("evidence") or "")[:100]
            print(f"  <- {nid}  (weight={w})  {ev}")

    if result["downstream_effects"]:
        print(f"\n--- Downstream Effects ({len(result['downstream_effects'])}) ---")
        for d in result["downstream_effects"][:10]:
            n = d.get("node", {})
            nid = n.get("id", d.get("to_id", "?"))
            w = d.get("weight", "?")
            print(f"  -> {nid}  (weight={w})")

    if result["known_fixes"]:
        print(f"\n--- Known Fixes ({len(result['known_fixes'])}) ---")
        seen = set()
        for f in result["known_fixes"][:10]:
            label = f.get("label", f.get("evidence", "?"))[:120]
            if label not in seen:
                seen.add(label)
                print(f"  * {label}")

    if result["learnings"]:
        print(f"\n--- Learnings ({len(result['learnings'])}) ---")
        seen = set()
        for le in result["learnings"][:10]:
            label = le.get("label") or le.get("body", "?")
            label = str(label)[:120]
            if label not in seen:
                seen.add(label)
                print(f"  ~ {label}")

    if result["handoffs"]:
        print(f"\n--- Handoffs ({len(result['handoffs'])}) ---")
        for h in result["handoffs"][:5]:
            ts = h.get("timestamp", "?")
            label = str(h.get("label", "?"))[:100]
            print(f"  [{ts}] {label}")

    print()


def _pp_traverse(results: list[dict], node_id: str):
    print(f"\n--- Traverse from {node_id} ({len(results)} edges) ---")
    for r in results[:30]:
        direction = r.get("direction", "outgoing")
        rel = r.get("relation", "?")
        depth = r.get("depth", "?")
        if direction == "incoming":
            n = r.get("source_node", {})
            nid = n.get("id", r.get("from_id", "?"))
            label = n.get("label", "")[:80]
            print(f"  [d={depth}] {nid} --{rel}--> [{node_id}]  {label}")
        else:
            n = r.get("target_node", {})
            nid = n.get("id", r.get("to_id", "?"))
            label = n.get("label", "")[:80]
            print(f"  [d={depth}] [{node_id}] --{rel}--> {nid}  {label}")
    print()


def _pp_search(results: list[dict]):
    print(f"\n--- Search Results ({len(results)}) ---")
    for r in results:
        print(f"  [{r['source']}] {r['id']}: {str(r['label'])[:100]}")
    print()


def _pp_stats(s: dict):
    print(f"\n{'='*50}")
    print(f"Knowledge Graph Stats")
    print(f"{'='*50}")
    print(f"  Nodes: {s['node_count']}")
    print(f"  Edges: {s['edge_count']}")
    print(f"\n  Node sources:")
    for k, v in s.get("sources", {}).items():
        print(f"    {k}: {v}")
    print(f"\n  Relation types:")
    for k, v in s.get("relation_types", {}).items():
        print(f"    {k}: {v}")
    print(f"\n  Top out-degree:")
    for nid, c in s.get("top_out_degree", [])[:5]:
        print(f"    {nid}: {c}")
    print(f"\n  Top in-degree:")
    for nid, c in s.get("top_in_degree", [])[:5]:
        print(f"    {nid}: {c}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "build":
        print("Building Semantic Link Graph ...")
        build_graph()

    elif cmd == "diagnose":
        if len(sys.argv) < 3:
            print("Usage: knowledge_graph.py diagnose <component>")
            sys.exit(1)
        result = diagnose(sys.argv[2])
        _pp_diagnose(result)

    elif cmd == "traverse":
        if len(sys.argv) < 3:
            print("Usage: knowledge_graph.py traverse <node_id> [--depth N]")
            sys.exit(1)
        node_id = sys.argv[2]
        depth = 2
        if "--depth" in sys.argv:
            idx = sys.argv.index("--depth")
            if idx + 1 < len(sys.argv):
                depth = int(sys.argv[idx + 1])
        results = traverse(node_id, depth=depth)
        _pp_traverse(results, node_id)

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: knowledge_graph.py search <query>")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        results = search(query)
        _pp_search(results)

    elif cmd == "stats":
        s = stats()
        _pp_stats(s)

    elif cmd == "path":
        if len(sys.argv) < 4:
            print("Usage: knowledge_graph.py path <from_id> <to_id>")
            sys.exit(1)
        path = find_path(sys.argv[2], sys.argv[3])
        if path:
            print(f"\nPath ({len(path)} hops):")
            for i, step in enumerate(path):
                edge_info = ""
                if "edge" in step and step["edge"]:
                    edge_info = f" --[{step['edge'].get('relation', '?')}]-->"
                print(f"  {i}. {step['id']}{edge_info}")
        else:
            print("No path found.")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
