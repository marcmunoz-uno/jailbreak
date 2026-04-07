#!/usr/bin/env python3
"""
semantic_link_graph.py — Weighted semantic graph over system knowledge.

A richer relationship layer than the ontology's typed edges. Edges here have:
  - semantic_weight: TF-IDF cosine similarity between entity descriptions
  - causal_weight: causal edge strength from causal_inference_engine
  - temporal_weight: how often these entities appear in the same time window
  - ontology_weight: existing ontology relationship confidence
  - composite_score: weighted combination of all above

This graph is used for:
  1. Context augmentation: when nexus asks about entity X, find semantically
     related entities to include in the briefing
  2. Impact estimation: entities with high composite score to a failing entity
     are more likely to be affected
  3. Knowledge routing: route tasks to agents with high semantic relevance
  4. Anomaly detection: entity pairs that suddenly diverge in state despite
     high semantic similarity → likely correlated problem

Storage: semantic_graph.db
Sources: ontology.db, causal_model.db, contextual_memories.db

Usage:
    python3 semantic_link_graph.py build         # full graph build
    python3 semantic_link_graph.py related <e>   # top-K related entities
    python3 semantic_link_graph.py cluster        # entity clusters
    python3 semantic_link_graph.py diverge        # find diverging entity pairs
    python3 semantic_link_graph.py stats          # graph statistics

Cron: 0 * * * * (hourly rebuild)
"""
import sqlite3
import json
import os
import sys
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEMANTIC_DB = "/Users/marcmunoz/.openclaw/data/semantic_graph.db"
Path(os.path.dirname(SEMANTIC_DB)).mkdir(parents=True, exist_ok=True)

# Edge weight components
W_SEMANTIC = 0.30
W_CAUSAL = 0.35
W_TEMPORAL = 0.20
W_ONTOLOGY = 0.15


# ============================================================
# DB Init
# ============================================================

def _get_conn():
    conn = sqlite3.connect(SEMANTIC_DB, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def _init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type TEXT,
            description TEXT,
            embedding_terms TEXT,   -- JSON: top TF-IDF terms for this entity
            state TEXT DEFAULT 'unknown',
            last_seen TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ent_type ON entities(entity_type);

        CREATE TABLE IF NOT EXISTS semantic_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a TEXT NOT NULL,
            entity_b TEXT NOT NULL,
            semantic_weight REAL DEFAULT 0.0,
            causal_weight REAL DEFAULT 0.0,
            temporal_weight REAL DEFAULT 0.0,
            ontology_weight REAL DEFAULT 0.0,
            composite_score REAL DEFAULT 0.0,
            edge_metadata TEXT,         -- JSON: breakdown + evidence
            computed_at TEXT NOT NULL,
            UNIQUE(entity_a, entity_b)
        );
        CREATE INDEX IF NOT EXISTS idx_edge_a ON semantic_edges(entity_a, composite_score DESC);
        CREATE INDEX IF NOT EXISTS idx_edge_b ON semantic_edges(entity_b, composite_score DESC);
        CREATE INDEX IF NOT EXISTS idx_edge_score ON semantic_edges(composite_score DESC);

        CREATE TABLE IF NOT EXISTS entity_clusters (
            cluster_id INTEGER NOT NULL,
            entity_id TEXT NOT NULL,
            cluster_label TEXT,
            cohesion REAL,
            assigned_at TEXT,
            PRIMARY KEY (cluster_id, entity_id)
        );

        CREATE TABLE IF NOT EXISTS divergence_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a TEXT NOT NULL,
            entity_b TEXT NOT NULL,
            semantic_similarity REAL,
            state_a TEXT,
            state_b TEXT,
            divergence_score REAL,
            detected_at TEXT NOT NULL,
            resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_div_detected ON divergence_alerts(detected_at DESC);
    """)
    conn.commit()
    conn.close()


_init_db()


# ============================================================
# Entity description builder
# ============================================================

def _build_entity_description(entity_id: str, entity_type: str, properties: dict) -> str:
    """Build a text description for TF-IDF from ontology properties."""
    parts = [entity_id.replace("_", " "), entity_type or ""]
    for k, v in (properties or {}).items():
        if isinstance(v, str):
            parts.append(f"{k} {v}")
        elif isinstance(v, list):
            parts.extend(str(x) for x in v[:5])
        elif isinstance(v, (int, float)):
            parts.append(f"{k}")
    return " ".join(parts)


def _tokenize(text: str) -> list:
    import re
    stop = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "has", "have",
            "of", "in", "on", "at", "to", "for", "with", "by", "from", "and", "or"}
    tokens = re.findall(r'\b[a-z][a-z0-9_]{1,}\b', text.lower())
    return [t for t in tokens if t not in stop]


def _cosine(vec_a: dict, vec_b: dict) -> float:
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] for t in common)
    na = math.sqrt(sum(v * v for v in vec_a.values()))
    nb = math.sqrt(sum(v * v for v in vec_b.values()))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


# ============================================================
# Load entity corpus
# ============================================================

def _load_entities_from_ontology() -> list:
    """Load entities from ontology.db with descriptions."""
    entities = []
    try:
        conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/ontology.db", timeout=3)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM entities").fetchall()
        conn.close()
        for r in rows:
            rd = dict(r)
            props = {}
            try:
                props = json.loads(rd.get("properties") or "{}")
            except Exception:
                pass
            desc = _build_entity_description(rd["id"], rd["entity_type"], props)
            entities.append({
                "id": rd["id"],
                "name": rd["name"],
                "entity_type": rd["entity_type"],
                "description": desc,
                "confidence": rd.get("confidence", 1.0),
            })
    except Exception:
        pass
    return entities


# ============================================================
# Semantic weight computation
# ============================================================

def _compute_semantic_weights(entities: list) -> dict:
    """
    Compute TF-IDF cosine similarity between all entity pairs.
    Returns {(a, b): similarity} for pairs above threshold.
    """
    from collections import Counter
    N = len(entities)
    if N < 2:
        return {}

    # TF per entity
    tf = {}
    for e in entities:
        tokens = _tokenize(e["description"])
        counts = Counter(tokens)
        total = sum(counts.values()) or 1
        tf[e["id"]] = {t: c / total for t, c in counts.items()}

    # DF
    from collections import Counter as Counter2
    df = Counter2()
    for eid, terms in tf.items():
        for t in terms:
            df[t] += 1

    # TF-IDF
    tfidf = {}
    for eid, terms in tf.items():
        tfidf[eid] = {}
        for term, freq in terms.items():
            idf = math.log((N + 1) / (df[term] + 1)) + 1.0
            tfidf[eid][term] = freq * idf

    # Pairwise cosine
    eids = [e["id"] for e in entities]
    weights = {}
    for i in range(len(eids)):
        for j in range(i + 1, len(eids)):
            sim = _cosine(tfidf[eids[i]], tfidf[eids[j]])
            if sim >= 0.1:  # Only keep non-trivial similarities
                weights[(eids[i], eids[j])] = round(sim, 4)

    return weights


# ============================================================
# Causal weight loading
# ============================================================

def _load_causal_weights() -> dict:
    """Load causal edge strengths from causal_model.db."""
    weights = {}
    try:
        conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/causal_model.db", timeout=3)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT cause, effect, strength FROM causal_edges WHERE strength >= 0.2"
        ).fetchall()
        conn.close()
        for r in rows:
            a, b = sorted([r["cause"], r["effect"]])
            weights[(a, b)] = max(weights.get((a, b), 0), r["strength"])
    except Exception:
        pass
    return weights


# ============================================================
# Temporal weight from memory compiler
# ============================================================

def _load_temporal_weights() -> dict:
    """
    Load temporal co-occurrence weights from contextual_memories.db.
    Entity pairs that frequently appear in the same context window get higher weight.
    """
    weights = {}
    try:
        conn = sqlite3.connect(
            "/Users/marcmunoz/.openclaw/data/contextual_memories.db", timeout=3
        )
        conn.row_factory = sqlite3.Row

        # Count entity link pairs
        rows = conn.execute("""
            SELECT m1.entity_refs as e1, m2.entity_refs as e2, ml.weight
            FROM memory_links ml
            JOIN memories m1 ON ml.from_id = m1.id
            JOIN memories m2 ON ml.to_id = m2.id
            WHERE ml.link_type = 'temporal' AND ml.weight >= 0.3
            ORDER BY ml.weight DESC LIMIT 5000
        """).fetchall()
        conn.close()

        pair_counts = defaultdict(float)
        for r in rows:
            try:
                e1_list = json.loads(r["e1"] or "[]")
                e2_list = json.loads(r["e2"] or "[]")
            except Exception:
                continue
            for ea in e1_list[:3]:
                for eb in e2_list[:3]:
                    if ea != eb:
                        key = tuple(sorted([ea, eb]))
                        pair_counts[key] += r["weight"]

        if pair_counts:
            max_count = max(pair_counts.values())
            for pair, count in pair_counts.items():
                weights[pair] = round(min(1.0, count / max_count), 4)

    except Exception:
        pass

    return weights


# ============================================================
# Ontology weight (existing relationship confidence)
# ============================================================

def _load_ontology_weights() -> dict:
    """Load existing ontology relationship confidences."""
    weights = {}
    try:
        conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/ontology.db", timeout=3)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT source_id, target_id, confidence FROM relationships"
        ).fetchall()
        conn.close()
        for r in rows:
            key = tuple(sorted([r["source_id"], r["target_id"]]))
            weights[key] = max(weights.get(key, 0), r["confidence"] or 0.5)
    except Exception:
        pass
    return weights


# ============================================================
# Main graph build
# ============================================================

def build() -> dict:
    """
    Build/rebuild the full semantic graph.
    Computes all 4 weight components and composite score for each entity pair.
    """
    results = {"entities": 0, "edges": 0, "clusters": 0}

    # Load entities
    entities = _load_entities_from_ontology()
    if not entities:
        return results

    # Also add entities from causal_model that may not be in ontology
    try:
        causal_conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/causal_model.db", timeout=3)
        causal_conn.row_factory = sqlite3.Row
        extra_entities = set()
        for r in causal_conn.execute("SELECT DISTINCT cause, effect FROM causal_edges").fetchall():
            extra_entities.add(r["cause"])
            extra_entities.add(r["effect"])
        causal_conn.close()
        existing_ids = {e["id"] for e in entities}
        for eid in extra_entities:
            if eid not in existing_ids:
                entities.append({
                    "id": eid,
                    "name": eid.replace("_", " "),
                    "entity_type": "inferred",
                    "description": eid.replace("_", " "),
                    "confidence": 0.5,
                })
    except Exception:
        pass

    conn = _get_conn()
    now_ts = _now()

    # Upsert entities
    for e in entities:
        tokens = _tokenize(e["description"])
        from collections import Counter
        top_terms = json.dumps([t for t, _ in Counter(tokens).most_common(20)])
        try:
            conn.execute("""
                INSERT OR REPLACE INTO entities
                (id, name, entity_type, description, embedding_terms, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (e["id"], e["name"], e["entity_type"], e["description"], top_terms, now_ts))
        except Exception:
            pass
    conn.commit()
    results["entities"] = len(entities)

    # Load all weight components
    semantic_w = _compute_semantic_weights(entities)
    causal_w = _load_causal_weights()
    temporal_w = _load_temporal_weights()
    ontology_w = _load_ontology_weights()

    # Merge all pairs
    all_pairs = set(semantic_w.keys()) | set(causal_w.keys()) | \
                set(temporal_w.keys()) | set(ontology_w.keys())

    edge_count = 0
    for pair in all_pairs:
        a, b = pair
        if a == b:
            continue

        sw = semantic_w.get(pair, 0.0)
        cw = causal_w.get(pair, 0.0)
        tw = temporal_w.get(pair, 0.0)
        ow = ontology_w.get(pair, 0.0)

        composite = (W_SEMANTIC * sw + W_CAUSAL * cw +
                     W_TEMPORAL * tw + W_ONTOLOGY * ow)

        if composite < 0.05:
            continue

        metadata = {
            "semantic": round(sw, 4),
            "causal": round(cw, 4),
            "temporal": round(tw, 4),
            "ontology": round(ow, 4),
        }

        try:
            conn.execute("""
                INSERT OR REPLACE INTO semantic_edges
                (entity_a, entity_b, semantic_weight, causal_weight, temporal_weight,
                 ontology_weight, composite_score, edge_metadata, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (a, b, round(sw, 4), round(cw, 4), round(tw, 4),
                  round(ow, 4), round(composite, 4),
                  json.dumps(metadata), now_ts))
            edge_count += 1
        except Exception:
            pass

    conn.commit()
    results["edges"] = edge_count

    # Simple clustering: greedy community detection by composite score
    clusters = _compute_clusters(conn)
    results["clusters"] = len(clusters)

    conn.close()
    return results


# ============================================================
# Clustering (greedy label propagation)
# ============================================================

def _compute_clusters(conn, min_score: float = 0.3) -> dict:
    """
    Simple greedy clustering: assign each entity to its highest-scoring neighbor's cluster.
    Returns {cluster_id: [entity_ids]}
    """
    rows = conn.execute("""
        SELECT entity_a, entity_b, composite_score FROM semantic_edges
        WHERE composite_score >= ?
        ORDER BY composite_score DESC
    """, (min_score,)).fetchall()

    # Union-Find
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for r in rows:
        union(r["entity_a"], r["entity_b"])

    # Group by root
    clusters: dict = defaultdict(list)
    for entity in parent:
        clusters[find(entity)].append(entity)

    # Assign cluster IDs
    conn.execute("DELETE FROM entity_clusters")
    now_ts = _now()
    cluster_map = {}
    for cid, (root, members) in enumerate(
        sorted(clusters.items(), key=lambda x: -len(x[1]))
    ):
        # Compute cohesion: avg score within cluster
        if len(members) > 1:
            scores = conn.execute("""
                SELECT AVG(composite_score) FROM semantic_edges
                WHERE entity_a IN ({0}) AND entity_b IN ({0})
            """.format(",".join("?" * len(members))),
                members + members
            ).fetchone()[0] or 0.0
        else:
            scores = 1.0

        for entity in members:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO entity_clusters
                    (cluster_id, entity_id, cohesion, assigned_at)
                    VALUES (?, ?, ?, ?)
                """, (cid, entity, round(scores, 4), now_ts))
            except Exception:
                pass
        cluster_map[cid] = members

    conn.commit()
    return cluster_map


# ============================================================
# Query interface
# ============================================================

def get_related(entity: str, top_k: int = 10) -> list:
    """
    Find entities most semantically related to the given entity.
    Returns list of {entity, composite_score, breakdown}.
    """
    entity_id = entity.lower().replace(" ", "_")
    conn = _get_conn()

    rows = conn.execute("""
        SELECT
            CASE WHEN entity_a = ? THEN entity_b ELSE entity_a END as related_entity,
            composite_score,
            semantic_weight,
            causal_weight,
            temporal_weight,
            ontology_weight,
            edge_metadata
        FROM semantic_edges
        WHERE entity_a = ? OR entity_b = ?
        ORDER BY composite_score DESC
        LIMIT ?
    """, (entity_id, entity_id, entity_id, top_k)).fetchall()

    conn.close()
    results = []
    for r in rows:
        try:
            meta = json.loads(r["edge_metadata"] or "{}")
        except Exception:
            meta = {}
        results.append({
            "entity": r["related_entity"],
            "composite_score": r["composite_score"],
            "breakdown": {
                "semantic": r["semantic_weight"],
                "causal": r["causal_weight"],
                "temporal": r["temporal_weight"],
                "ontology": r["ontology_weight"],
            },
        })

    return results


def get_clusters(top_n: int = 10) -> list:
    """Return the top N clusters with their members."""
    conn = _get_conn()
    cluster_ids = conn.execute("""
        SELECT cluster_id, COUNT(*) as size, AVG(cohesion) as avg_cohesion
        FROM entity_clusters
        GROUP BY cluster_id
        ORDER BY size DESC LIMIT ?
    """, (top_n,)).fetchall()

    results = []
    for c in cluster_ids:
        members = conn.execute(
            "SELECT entity_id FROM entity_clusters WHERE cluster_id = ?",
            (c["cluster_id"],)
        ).fetchall()
        results.append({
            "cluster_id": c["cluster_id"],
            "size": c["size"],
            "cohesion": round(c["avg_cohesion"], 4),
            "members": [r["entity_id"] for r in members],
        })

    conn.close()
    return results


def detect_divergence() -> list:
    """
    Find entity pairs with high semantic similarity but diverging state.
    These are likely experiencing correlated but undetected problems.
    """
    conn = _get_conn()

    # Get high-similarity pairs
    high_sim_pairs = conn.execute("""
        SELECT entity_a, entity_b, semantic_weight, composite_score
        FROM semantic_edges
        WHERE semantic_weight >= 0.6
        ORDER BY semantic_weight DESC LIMIT 200
    """).fetchall()

    divergent = []
    now_ts = _now()

    try:
        ont_conn = sqlite3.connect("/Users/marcmunoz/.openclaw/data/ontology.db", timeout=3)
        ont_conn.row_factory = sqlite3.Row

        for pair in high_sim_pairs:
            a, b = pair["entity_a"], pair["entity_b"]
            # Get entity states (confidence as proxy for health)
            ea = ont_conn.execute("SELECT confidence FROM entities WHERE id = ?", (a,)).fetchone()
            eb = ont_conn.execute("SELECT confidence FROM entities WHERE id = ?", (b,)).fetchone()
            if not ea or not eb:
                continue

            conf_a = ea["confidence"] or 0.5
            conf_b = eb["confidence"] or 0.5
            divergence = abs(conf_a - conf_b)

            # If semantically similar but one healthy and other unhealthy → alert
            if divergence >= 0.3:
                state_a = "healthy" if conf_a >= 0.7 else "degraded"
                state_b = "healthy" if conf_b >= 0.7 else "degraded"
                div_score = divergence * pair["semantic_weight"]
                divergent.append({
                    "entity_a": a,
                    "entity_b": b,
                    "semantic_similarity": pair["semantic_weight"],
                    "state_a": state_a,
                    "state_b": state_b,
                    "divergence_score": round(div_score, 4),
                })

                # Record alert
                try:
                    conn.execute("""
                        INSERT INTO divergence_alerts
                        (entity_a, entity_b, semantic_similarity, state_a, state_b,
                         divergence_score, detected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (a, b, pair["semantic_weight"], state_a, state_b,
                          round(div_score, 4), now_ts))
                except Exception:
                    pass

        ont_conn.close()
    except Exception:
        pass

    conn.commit()
    conn.close()
    return sorted(divergent, key=lambda x: -x["divergence_score"])


def get_stats() -> dict:
    conn = _get_conn()
    total_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    total_edges = conn.execute("SELECT COUNT(*) FROM semantic_edges").fetchone()[0]
    avg_score = conn.execute("SELECT AVG(composite_score) FROM semantic_edges").fetchone()[0] or 0
    top_pairs = conn.execute("""
        SELECT entity_a, entity_b, composite_score FROM semantic_edges
        ORDER BY composite_score DESC LIMIT 5
    """).fetchall()
    total_clusters = conn.execute(
        "SELECT COUNT(DISTINCT cluster_id) FROM entity_clusters"
    ).fetchone()[0]
    conn.close()
    return {
        "total_entities": total_entities,
        "total_edges": total_edges,
        "avg_composite_score": round(avg_score, 4),
        "clusters": total_clusters,
        "top_pairs": [dict(r) for r in top_pairs],
    }


# ============================================================
# CLI
# ============================================================

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"

    if cmd == "build":
        print("Building semantic link graph...")
        result = build()
        print(f"  Entities: {result['entities']}")
        print(f"  Edges:    {result['edges']}")
        print(f"  Clusters: {result['clusters']}")

    elif cmd == "related" and len(sys.argv) > 2:
        entity = sys.argv[2]
        k = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        print(f"Related entities for: {entity}")
        print("=" * 60)
        results = get_related(entity, top_k=k)
        if not results:
            print("  No relationships found. Run 'build' first.")
        for r in results:
            b = r["breakdown"]
            print(f"  {r['entity']:<30} score={r['composite_score']:.3f} "
                  f"[sem={b['semantic']:.2f} cau={b['causal']:.2f} "
                  f"tmp={b['temporal']:.2f} ont={b['ontology']:.2f}]")

    elif cmd == "cluster":
        clusters = get_clusters(top_n=15)
        print(f"Entity clusters ({len(clusters)} found):")
        print("=" * 60)
        for c in clusters:
            print(f"\n  Cluster {c['cluster_id']} (size={c['size']}, cohesion={c['cohesion']:.3f}):")
            print(f"    {', '.join(c['members'][:10])}")

    elif cmd == "diverge":
        print("Scanning for diverging entity pairs...")
        alerts = detect_divergence()
        if not alerts:
            print("  No divergent pairs found.")
        for a in alerts[:10]:
            print(f"  {a['entity_a']} ({a['state_a']}) ↔ {a['entity_b']} ({a['state_b']})"
                  f"  sim={a['semantic_similarity']:.2f}  div={a['divergence_score']:.3f}")

    elif cmd == "stats":
        stats = get_stats()
        print("Semantic Graph Statistics")
        print("=" * 40)
        print(f"  Entities:     {stats['total_entities']}")
        print(f"  Edges:        {stats['total_edges']}")
        print(f"  Avg score:    {stats['avg_composite_score']:.4f}")
        print(f"  Clusters:     {stats['clusters']}")
        if stats["top_pairs"]:
            print(f"\n  Top pairs:")
            for p in stats["top_pairs"]:
                print(f"    {p['entity_a']:<25} ↔ {p['entity_b']:<25} {p['composite_score']:.4f}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
