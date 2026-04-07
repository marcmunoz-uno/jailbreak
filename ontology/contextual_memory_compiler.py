#!/usr/bin/env python3
"""
contextual_memory_compiler.py — Semantic memory compilation for the multi-agent system.

Unlike wiki_compiler.py (which makes human-readable articles), this compiler
produces machine-queryable structured memories with:
  - Full semantic context window (what happened before/after)
  - Causal links (what triggered this memory, what it caused)
  - Semantic neighbors (similar memories by TF-IDF)
  - Entity references (which agents/services/pipelines are involved)

These compiled memories are the input layer for the Causal Inference Engine
and the Semantic Link Graph.

Storage: contextual_memories.db
Sources: system_brain, event_bus, fabric, shared_memory log, corrections

Usage:
    python3 contextual_memory_compiler.py compile     # full compile pass
    python3 contextual_memory_compiler.py search <q>  # semantic search
    python3 contextual_memory_compiler.py stats        # counts
    python3 contextual_memory_compiler.py context <id> # full context for a memory

Cron: */30 * * * * (incremental, idempotent)
"""
import sqlite3
import json
import os
import sys
import re
import math
import hashlib
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = "/Users/marcmunoz/.openclaw/data/contextual_memories.db"
Path(os.path.dirname(DB_PATH)).mkdir(parents=True, exist_ok=True)

# Context window: events within this many minutes are "related"
CONTEXT_WINDOW_MINUTES = 30
# Max neighbors returned by semantic search
MAX_NEIGHBORS = 10
# Min TF-IDF cosine similarity to create a semantic link
SIMILARITY_THRESHOLD = 0.15


# ============================================================
# DB Init
# ============================================================

def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def _init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL,
            entity_refs TEXT,        -- JSON list of entities mentioned
            timestamp TEXT NOT NULL,
            compiled_at TEXT NOT NULL,
            tags TEXT,               -- JSON list
            severity TEXT DEFAULT 'info',
            raw_data TEXT            -- original JSON from source
        );
        CREATE INDEX IF NOT EXISTS idx_mem_source ON memories(source_type, source);
        CREATE INDEX IF NOT EXISTS idx_mem_ts ON memories(timestamp);
        CREATE INDEX IF NOT EXISTS idx_mem_severity ON memories(severity);

        CREATE TABLE IF NOT EXISTS memory_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id TEXT NOT NULL REFERENCES memories(id),
            to_id TEXT NOT NULL REFERENCES memories(id),
            link_type TEXT NOT NULL,   -- 'semantic', 'causal', 'temporal', 'entity'
            weight REAL DEFAULT 1.0,
            evidence TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_links_from ON memory_links(from_id, link_type);
        CREATE INDEX IF NOT EXISTS idx_links_to ON memory_links(to_id, link_type);

        CREATE TABLE IF NOT EXISTS memory_tfidf (
            memory_id TEXT NOT NULL,
            term TEXT NOT NULL,
            tfidf REAL NOT NULL,
            PRIMARY KEY (memory_id, term)
        );
        CREATE INDEX IF NOT EXISTS idx_tfidf_term ON memory_tfidf(term, tfidf DESC);

        CREATE TABLE IF NOT EXISTS compile_state (
            source TEXT PRIMARY KEY,
            last_compiled_at TEXT,
            memories_compiled INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


_init_db()


# ============================================================
# Entity extraction (fast keyword-based, no LLM)
# ============================================================

KNOWN_ENTITIES = [
    "nexus", "scout", "claude_code", "openclaw", "hermes", "jailbreak",
    "dscr_pipeline", "trading_pipeline", "outreach_pipeline",
    "batchdata", "activecampaign", "kalshi", "polymarket", "openrouter",
    "godmode", "blooio", "zillow", "conway",
    "system_brain", "event_bus", "task_dispatcher", "pheromone_system",
    "ontology", "ontology_reasoner", "predictor", "causal_engine",
    "houston", "miami", "austin", "dallas", "atlanta", "phoenix",
    "mission_control", "hermes_gateway", "agent_memory_server",
]

ENTITY_ALIASES = {
    "mission control": "mission_control",
    "hermes gateway": "hermes_gateway",
    "agent memory": "agent_memory_server",
    "task dispatcher": "task_dispatcher",
    "batch data": "batchdata",
    "active campaign": "activecampaign",
    "event bus": "event_bus",
}


def extract_entities(text: str) -> list:
    """Extract known entity references from text."""
    text_lower = text.lower()
    found = set()
    for ent in KNOWN_ENTITIES:
        if ent.replace("_", " ") in text_lower or ent in text_lower:
            found.add(ent)
    for alias, canonical in ENTITY_ALIASES.items():
        if alias in text_lower:
            found.add(canonical)
    return sorted(found)


def infer_severity(text: str, tags: list = None) -> str:
    """Infer severity from content."""
    text_lower = text.lower()
    tags_str = " ".join(tags or []).lower()
    combined = text_lower + " " + tags_str
    if any(w in combined for w in ["critical", "crash", "failed", "error", "down", "corrupt"]):
        return "critical"
    if any(w in combined for w in ["warning", "slow", "degraded", "stale", "miss"]):
        return "warning"
    if any(w in combined for w in ["fixed", "resolved", "restored", "success", "ok"]):
        return "resolved"
    return "info"


# ============================================================
# TF-IDF computation
# ============================================================

def _tokenize(text: str) -> list:
    """Simple word tokenizer, removes stop words."""
    stop = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "has", "have",
            "had", "do", "does", "did", "will", "would", "could", "should", "may", "might",
            "of", "in", "on", "at", "to", "for", "with", "by", "from", "up", "about",
            "it", "its", "this", "that", "they", "them", "their", "and", "or", "but",
            "not", "no", "so", "if", "as", "into", "than", "then", "when", "where",
            "how", "all", "each", "both", "any", "very", "just", "also", "more"}
    tokens = re.findall(r'\b[a-z][a-z0-9_]{2,}\b', text.lower())
    return [t for t in tokens if t not in stop]


def _build_tfidf(memories: list) -> dict:
    """
    Compute TF-IDF for all memories.
    Returns: {memory_id: {term: tfidf_score}}
    """
    N = len(memories)
    if N == 0:
        return {}

    # TF: term frequency per document
    tf: dict = {}
    for mem in memories:
        mid = mem["id"]
        tokens = _tokenize(mem["content"])
        counts = Counter(tokens)
        total = sum(counts.values()) or 1
        tf[mid] = {t: c / total for t, c in counts.items()}

    # DF: document frequency per term
    df: Counter = Counter()
    for mid, term_tf in tf.items():
        for term in term_tf:
            df[term] += 1

    # TF-IDF
    tfidf: dict = {}
    for mid, term_tf in tf.items():
        tfidf[mid] = {}
        for term, freq in term_tf.items():
            idf = math.log((N + 1) / (df[term] + 1)) + 1.0
            tfidf[mid][term] = round(freq * idf, 6)

    return tfidf


def _cosine_similarity(vec_a: dict, vec_b: dict) -> float:
    """Cosine similarity between two TF-IDF dicts."""
    common_terms = set(vec_a) & set(vec_b)
    if not common_terms:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] for t in common_terms)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ============================================================
# Source readers
# ============================================================

def _read_system_brain(since: datetime = None) -> list:
    """Read learnings and corrections from system_brain."""
    memories = []
    try:
        conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/system_brain.db", timeout=3)
        conn.row_factory = sqlite3.Row

        # Learnings
        q = "SELECT * FROM learnings ORDER BY created_at DESC LIMIT 500"
        params = []
        if since:
            q = "SELECT * FROM learnings WHERE created_at >= ? ORDER BY created_at DESC LIMIT 500"
            params = [since.isoformat()]

        rows = conn.execute(q, params).fetchall()
        for r in rows:
            rd = dict(r)
            mid = f"brain:learning:{rd['id']}"
            content = f"[learning:{rd.get('category','general')}] {rd.get('insight', rd.get('content', ''))}"
            memories.append({
                "id": hashlib.md5(mid.encode()).hexdigest()[:16],
                "content": content,
                "source": "system_brain.learnings",
                "source_type": "learning",
                "timestamp": rd.get("created_at", _now()),
                "tags": json.dumps([rd.get("category", "general")]),
                "raw_data": json.dumps(rd),
            })

        # Corrections
        q2 = "SELECT * FROM corrections ORDER BY created_at DESC LIMIT 500"
        params2 = []
        if since:
            q2 = "SELECT * FROM corrections WHERE created_at >= ? ORDER BY created_at DESC LIMIT 500"
            params2 = [since.isoformat()]

        rows2 = conn.execute(q2, params2).fetchall()
        for r in rows2:
            rd = dict(r)
            mid = f"brain:correction:{rd['id']}"
            ts = rd.get("last_seen") or rd.get("first_seen") or rd.get("created_at") or _now()
            content = (f"[correction:{rd.get('component','?')}] "
                       f"Problem: {rd.get('problem', '')} | Fix: {rd.get('fix', '')}")
            memories.append({
                "id": hashlib.md5(mid.encode()).hexdigest()[:16],
                "content": content,
                "source": "system_brain.corrections",
                "source_type": "correction",
                "timestamp": ts,
                "tags": json.dumps([rd.get("component", "unknown"), "correction"]),
                "raw_data": json.dumps(rd),
            })

        conn.close()
    except Exception as e:
        pass

    return memories


def _read_event_bus(since: datetime = None, limit: int = 1000) -> list:
    """Read significant events from event_bus."""
    memories = []
    try:
        conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/events.db", timeout=3)
        conn.row_factory = sqlite3.Row

        # Only keep high-signal event types
        signal_types = [
            "critical_signal", "memory:published", "circadian:phase_change",
            "task:assigned", "trade_resolved", "scan_complete",
            "health_score_updated", "pheromone:cluster_triggered",
            "self_healer.escalation", "self_healer.rollback",
        ]
        placeholders = ",".join("?" * len(signal_types))
        q = f"""
            SELECT * FROM events
            WHERE event_type IN ({placeholders})
            ORDER BY id DESC LIMIT {limit}
        """
        params = signal_types

        if since:
            q = f"""
                SELECT * FROM events
                WHERE event_type IN ({placeholders}) AND created_at >= ?
                ORDER BY id DESC LIMIT {limit}
            """
            params = signal_types + [since.isoformat()]

        rows = conn.execute(q, params).fetchall()
        for r in rows:
            rd = dict(r)
            mid = f"event:{rd['id']}"
            data = {}
            try:
                data = json.loads(rd.get("data") or "{}")
            except Exception:
                pass
            content = f"[event:{rd['event_type']}] source={rd['source']} " + (
                data.get("content") or data.get("description") or str(data)[:200]
            )
            memories.append({
                "id": hashlib.md5(mid.encode()).hexdigest()[:16],
                "content": content,
                "source": f"event_bus.{rd['event_type']}",
                "source_type": "event",
                "timestamp": rd.get("created_at", _now()),
                "tags": json.dumps([rd["event_type"], rd["source"]]),
                "raw_data": json.dumps(rd),
            })

        conn.close()
    except Exception:
        pass

    return memories


def _read_shared_memory_log(since: datetime = None) -> list:
    """Read from shared_memory JSONL log."""
    memories = []
    log_path = Path("/Users/marcmunoz/.openclaw/data/shared_memory.jsonl")
    if not log_path.exists():
        return []

    try:
        with open(log_path) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except Exception:
                    continue
                ts = entry.get("timestamp") or entry.get("created_at") or _now()
                if since:
                    try:
                        entry_dt = datetime.fromisoformat(ts)
                        if entry_dt.tzinfo is None:
                            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                        if entry_dt < since:
                            continue
                    except Exception:
                        pass

                content = entry.get("content") or entry.get("message") or str(entry)[:300]
                topic = entry.get("topic") or entry.get("source") or "shared_memory"
                mid = f"shm:{entry.get('id', hashlib.md5(content.encode()).hexdigest()[:8])}"
                memories.append({
                    "id": hashlib.md5(mid.encode()).hexdigest()[:16],
                    "content": f"[shared_memory:{topic}] {content}",
                    "source": f"shared_memory.{topic}",
                    "source_type": "shared_memory",
                    "timestamp": ts,
                    "tags": json.dumps(entry.get("tags", [topic])),
                    "raw_data": line.strip(),
                })
    except Exception:
        pass

    return memories


# ============================================================
# Link builders
# ============================================================

def _build_temporal_links(memories: list, conn) -> int:
    """Link memories that happened within the context window."""
    count = 0
    now_dt = datetime.now(timezone.utc)
    window = timedelta(minutes=CONTEXT_WINDOW_MINUTES)

    # Parse timestamps
    timed = []
    for m in memories:
        try:
            ts = datetime.fromisoformat(m["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            timed.append((ts, m["id"]))
        except Exception:
            continue

    timed.sort(key=lambda x: x[0])

    for i, (ts_a, id_a) in enumerate(timed):
        for j in range(i + 1, len(timed)):
            ts_b, id_b = timed[j]
            if ts_b - ts_a > window:
                break
            gap_min = (ts_b - ts_a).total_seconds() / 60
            weight = max(0.1, 1.0 - (gap_min / CONTEXT_WINDOW_MINUTES))
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO memory_links
                    (from_id, to_id, link_type, weight, evidence, created_at)
                    VALUES (?, ?, 'temporal', ?, ?, ?)
                """, (id_a, id_b, round(weight, 3),
                      json.dumps({"gap_minutes": round(gap_min, 1)}), _now()))
                count += 1
            except Exception:
                pass

    conn.commit()
    return count


def _build_entity_links(memories: list, conn) -> int:
    """Link memories that share entity references."""
    entity_to_memories: dict = defaultdict(list)
    for m in memories:
        for ent in extract_entities(m["content"]):
            entity_to_memories[ent].append(m["id"])

    count = 0
    for ent, mids in entity_to_memories.items():
        for i in range(len(mids)):
            for j in range(i + 1, min(len(mids), i + 20)):
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO memory_links
                        (from_id, to_id, link_type, weight, evidence, created_at)
                        VALUES (?, ?, 'entity', 1.0, ?, ?)
                    """, (mids[i], mids[j],
                          json.dumps({"shared_entity": ent}), _now()))
                    count += 1
                except Exception:
                    pass

    conn.commit()
    return count


def _build_semantic_links(memories: list, conn) -> int:
    """Compute TF-IDF similarity and link semantically related memories."""
    if len(memories) < 2:
        return 0

    tfidf = _build_tfidf(memories)

    # Store TF-IDF vectors
    for mid, terms in tfidf.items():
        # Keep top 50 terms per memory
        top_terms = sorted(terms.items(), key=lambda x: x[1], reverse=True)[:50]
        for term, score in top_terms:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO memory_tfidf (memory_id, term, tfidf)
                    VALUES (?, ?, ?)
                """, (mid, term, score))
            except Exception:
                pass
    conn.commit()

    # Find similar pairs (limit to avoid O(N^2) explosion)
    mids = list(tfidf.keys())
    count = 0
    sample = mids[:500]  # cap at 500 to keep compile fast

    for i in range(len(sample)):
        for j in range(i + 1, len(sample)):
            sim = _cosine_similarity(tfidf[sample[i]], tfidf[sample[j]])
            if sim >= SIMILARITY_THRESHOLD:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO memory_links
                        (from_id, to_id, link_type, weight, evidence, created_at)
                        VALUES (?, ?, 'semantic', ?, ?, ?)
                    """, (sample[i], sample[j], round(sim, 4),
                          json.dumps({"cosine_similarity": round(sim, 4)}), _now()))
                    count += 1
                except Exception:
                    pass

    conn.commit()
    return count


# ============================================================
# Main compile pass
# ============================================================

def compile(incremental: bool = True) -> dict:
    """
    Full compilation pass.
    incremental=True: only process sources newer than last compile.
    Returns: {"memories_written": N, "links_written": N, "sources": {...}}
    """
    conn = _get_conn()
    results = {"memories_written": 0, "links_written": 0, "sources": {}}

    # Determine since cutoff
    since = None
    if incremental:
        row = conn.execute(
            "SELECT MIN(last_compiled_at) FROM compile_state"
        ).fetchone()
        if row and row[0]:
            try:
                since = datetime.fromisoformat(row[0])
                if since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)
                # Back off by 5 minutes to catch edge cases
                since = since - timedelta(minutes=5)
            except Exception:
                since = None

    # Collect from all sources
    all_memories = []
    for source_name, reader_fn in [
        ("system_brain", lambda: _read_system_brain(since)),
        ("event_bus", lambda: _read_event_bus(since)),
        ("shared_memory", lambda: _read_shared_memory_log(since)),
    ]:
        try:
            mems = reader_fn()
            results["sources"][source_name] = len(mems)
            all_memories.extend(mems)
        except Exception as e:
            results["sources"][source_name] = f"error: {e}"

    if not all_memories:
        conn.close()
        return results

    # Deduplicate by id
    seen_ids = set()
    unique_memories = []
    for m in all_memories:
        if m["id"] not in seen_ids:
            seen_ids.add(m["id"])
            unique_memories.append(m)

    # Write memories
    compile_ts = _now()
    for m in unique_memories:
        entities = extract_entities(m["content"])
        severity = infer_severity(m["content"], json.loads(m.get("tags") or "[]"))
        try:
            conn.execute("""
                INSERT OR IGNORE INTO memories
                (id, content, source, source_type, entity_refs, timestamp,
                 compiled_at, tags, severity, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                m["id"], m["content"], m["source"], m["source_type"],
                json.dumps(entities), m["timestamp"], compile_ts,
                m.get("tags", "[]"), severity, m.get("raw_data", "")
            ))
            results["memories_written"] += 1
        except Exception:
            pass

    conn.commit()

    # Build links on the new batch
    temporal = _build_temporal_links(unique_memories, conn)
    entity = _build_entity_links(unique_memories, conn)

    # For semantic links, use full set (need IDF across corpus)
    all_stored = [dict(r) for r in conn.execute(
        "SELECT id, content FROM memories ORDER BY timestamp DESC LIMIT 2000"
    ).fetchall()]
    semantic = _build_semantic_links(all_stored, conn)

    results["links_written"] = temporal + entity + semantic

    # Update compile state
    for source_name in results["sources"]:
        conn.execute("""
            INSERT OR REPLACE INTO compile_state
            (source, last_compiled_at, memories_compiled)
            VALUES (?, ?, COALESCE((SELECT memories_compiled FROM compile_state WHERE source=?), 0) + ?)
        """, (source_name, compile_ts, source_name, results["sources"].get(source_name, 0)
              if isinstance(results["sources"].get(source_name), int) else 0))

    conn.commit()
    conn.close()
    return results


# ============================================================
# Query interface
# ============================================================

def search(query: str, top_k: int = 10, source_type: str = None) -> list:
    """
    Semantic + keyword search over compiled memories.
    Returns list of {id, content, source_type, timestamp, score, links}.
    """
    conn = _get_conn()
    tokens = _tokenize(query)
    if not tokens:
        conn.close()
        return []

    # Score memories by TF-IDF term overlap
    placeholders = ",".join("?" * len(tokens))
    rows = conn.execute(f"""
        SELECT memory_id, SUM(tfidf) as score
        FROM memory_tfidf
        WHERE term IN ({placeholders})
        GROUP BY memory_id
        ORDER BY score DESC
        LIMIT {top_k * 3}
    """, tokens).fetchall()

    if not rows:
        conn.close()
        return []

    # Fetch memory details
    scored_mids = [(r["memory_id"], r["score"]) for r in rows]
    results = []
    for mid, score in scored_mids[:top_k * 2]:
        q = "SELECT * FROM memories WHERE id = ?"
        params = [mid]
        if source_type:
            q = "SELECT * FROM memories WHERE id = ? AND source_type = ?"
            params = [mid, source_type]
        mem = conn.execute(q, params).fetchone()
        if not mem:
            continue
        m = dict(mem)
        m["score"] = round(score, 4)
        m["entity_refs"] = json.loads(m.get("entity_refs") or "[]")
        m["tags"] = json.loads(m.get("tags") or "[]")

        # Fetch link counts
        link_counts = conn.execute("""
            SELECT link_type, COUNT(*) as cnt FROM memory_links
            WHERE from_id = ? OR to_id = ?
            GROUP BY link_type
        """, (mid, mid)).fetchall()
        m["links"] = {r["link_type"]: r["cnt"] for r in link_counts}
        results.append(m)

    conn.close()
    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]


def get_context(memory_id: str, window_type: str = "all") -> dict:
    """
    Get the full context window around a memory.
    window_type: 'temporal', 'semantic', 'entity', 'causal', 'all'
    """
    conn = _get_conn()
    mem = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    if not mem:
        conn.close()
        return {}

    result = dict(mem)
    result["entity_refs"] = json.loads(result.get("entity_refs") or "[]")
    result["tags"] = json.loads(result.get("tags") or "[]")
    result["context"] = {}

    # Fetch neighbors per link type
    types_to_fetch = ["temporal", "semantic", "entity", "causal"] if window_type == "all" else [window_type]
    for ltype in types_to_fetch:
        rows = conn.execute("""
            SELECT
                CASE WHEN from_id = ? THEN to_id ELSE from_id END as neighbor_id,
                weight, evidence
            FROM memory_links
            WHERE (from_id = ? OR to_id = ?) AND link_type = ?
            ORDER BY weight DESC LIMIT 10
        """, (memory_id, memory_id, memory_id, ltype)).fetchall()

        neighbors = []
        for r in rows:
            n = conn.execute("SELECT id, content, source_type, timestamp, severity FROM memories WHERE id = ?",
                             (r["neighbor_id"],)).fetchone()
            if n:
                neighbors.append({
                    "id": r["neighbor_id"],
                    "content": dict(n)["content"][:200],
                    "source_type": dict(n)["source_type"],
                    "timestamp": dict(n)["timestamp"],
                    "severity": dict(n)["severity"],
                    "weight": r["weight"],
                    "evidence": json.loads(r["evidence"] or "{}"),
                })

        result["context"][ltype] = neighbors

    conn.close()
    return result


def get_stats() -> dict:
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    by_type = {r["source_type"]: r["cnt"] for r in conn.execute(
        "SELECT source_type, COUNT(*) as cnt FROM memories GROUP BY source_type"
    ).fetchall()}
    by_severity = {r["severity"]: r["cnt"] for r in conn.execute(
        "SELECT severity, COUNT(*) as cnt FROM memories GROUP BY severity"
    ).fetchall()}
    total_links = conn.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0]
    by_link = {r["link_type"]: r["cnt"] for r in conn.execute(
        "SELECT link_type, COUNT(*) as cnt FROM memory_links GROUP BY link_type"
    ).fetchall()}
    conn.close()
    return {
        "total_memories": total,
        "by_source_type": by_type,
        "by_severity": by_severity,
        "total_links": total_links,
        "by_link_type": by_link,
    }


# ============================================================
# CLI
# ============================================================

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "compile"

    if cmd == "compile":
        incremental = "--full" not in sys.argv
        mode = "incremental" if incremental else "full"
        print(f"Compiling contextual memories ({mode})...")
        result = compile(incremental=incremental)
        print(f"  Memories written: {result['memories_written']}")
        print(f"  Links written:    {result['links_written']}")
        print(f"  Sources:")
        for src, count in result["sources"].items():
            print(f"    {src:<30} {count}")

    elif cmd == "search" and len(sys.argv) > 2:
        query = " ".join(sys.argv[2:])
        print(f"Searching: {query}")
        print("=" * 60)
        results = search(query)
        for r in results:
            print(f"\n[{r['severity'].upper()}] {r['source_type']} | {r['timestamp'][:19]}")
            print(f"  {r['content'][:200]}")
            print(f"  Score: {r['score']:.4f} | Links: {r['links']}")

    elif cmd == "stats":
        stats = get_stats()
        print("Contextual Memory Statistics")
        print("=" * 40)
        print(f"  Total memories: {stats['total_memories']}")
        print(f"  Total links:    {stats['total_links']}")
        print(f"\n  By source type:")
        for t, c in sorted(stats["by_source_type"].items()):
            print(f"    {t:<25} {c}")
        print(f"\n  By severity:")
        for s, c in sorted(stats["by_severity"].items()):
            print(f"    {s:<25} {c}")
        print(f"\n  By link type:")
        for lt, c in sorted(stats["by_link_type"].items()):
            print(f"    {lt:<25} {c}")

    elif cmd == "context" and len(sys.argv) > 2:
        mid = sys.argv[2]
        ctx = get_context(mid)
        if not ctx:
            print(f"Memory '{mid}' not found.")
            return
        print(f"Memory: {ctx['id']}")
        print(f"  Content:   {ctx['content'][:300]}")
        print(f"  Severity:  {ctx['severity']}")
        print(f"  Entities:  {ctx['entity_refs']}")
        for ltype, neighbors in ctx.get("context", {}).items():
            if neighbors:
                print(f"\n  {ltype.upper()} context ({len(neighbors)}):")
                for n in neighbors[:5]:
                    print(f"    [{n['severity']}] {n['content'][:120]} (w={n['weight']:.3f})")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
