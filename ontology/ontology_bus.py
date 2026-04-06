#!/usr/bin/env python3
"""
ontology_bus.py -- Event-driven change propagation for the Ontology Stack.

Extends the concept from n8n-workflows/event_bus.py but operates at the ontology
layer -- events carry graph context (blast radius), support pattern-based subscriptions,
and auto-enrich with L1 structure data.

Usage:
    from ontology_bus import OntologyBus
    bus = OntologyBus()
    bus.subscribe("watchdog", "detection.*")
    bus.publish("detection", "anomaly_detected", "watchdog", "service:mission-control",
                {"metric": "risk_score", "sigma": 3.5})
    events = bus.consume("watchdog")
"""
import sqlite3
import json
import os
import fnmatch
from datetime import datetime, timezone
from pathlib import Path

BUS_DB = os.path.expanduser("~/.openclaw/data/ontology_bus.db")

BUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ontology_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    entity_id TEXT,
    payload TEXT,
    graph_context TEXT,
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oe_domain ON ontology_events(domain, event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_oe_entity ON ontology_events(entity_id, created_at);

CREATE TABLE IF NOT EXISTS subscriptions (
    subscriber TEXT NOT NULL,
    event_pattern TEXT NOT NULL,
    last_processed_id INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (subscriber, event_pattern)
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _connect(path):
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class OntologyBus:
    """Event-driven change propagation across the ontology stack."""

    def __init__(self, db_path: str = BUS_DB):
        self._db_path = db_path
        conn = _connect(self._db_path)
        conn.executescript(BUS_SCHEMA)
        conn.commit()
        conn.close()

    def _conn(self):
        return _connect(self._db_path)

    # ----------------------------------------------------------------
    # Publish
    # ----------------------------------------------------------------

    def publish(self, domain: str, event_type: str, source: str,
                entity_id: str = None, payload: dict = None,
                priority: int = 0) -> int:
        """Publish event. Auto-enriches with blast_radius from L1 if entity_id given."""
        graph_context = None

        if entity_id:
            try:
                from ontology_api import OntologyStack
                stack = OntologyStack()
                blast = stack.blast_radius(entity_id, max_depth=2)
                graph_context = {
                    "blast_radius_count": len(blast),
                    "critical_affected": [
                        b["entity_id"] for b in blast if b["critical"] and b["depth"] > 0
                    ],
                    "max_risk_in_radius": max(
                        (b["risk_score"] for b in blast if b["risk_score"] is not None),
                        default=None,
                    ),
                    "entities": [
                        {"id": b["entity_id"], "depth": b["depth"], "risk": b["risk_score"]}
                        for b in blast[:20]  # cap at 20 to keep payload manageable
                    ],
                }
            except Exception:
                # Graceful degradation -- publish without graph context
                graph_context = {"error": "blast_radius_unavailable"}

        now = _now()
        conn = self._conn()
        cursor = conn.execute("""
            INSERT INTO ontology_events
            (domain, event_type, source, entity_id, payload, graph_context, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            domain, event_type, source, entity_id,
            json.dumps(payload) if payload else None,
            json.dumps(graph_context) if graph_context else None,
            priority, now
        ))
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return event_id

    # ----------------------------------------------------------------
    # Subscribe
    # ----------------------------------------------------------------

    def subscribe(self, subscriber: str, event_pattern: str):
        """Register interest. Pattern like 'detection.*' or 'handoff.task_created'.

        Pattern format: 'domain.event_type' with * wildcards.
        Examples:
            'detection.*'         -- all detection events
            '*.anomaly_detected'  -- anomaly events from any domain
            'handoff.task_created' -- specific event
            '*'                   -- everything
        """
        now = _now()
        conn = self._conn()
        # Get current max id so subscriber only sees future events
        max_id = conn.execute("SELECT COALESCE(MAX(id), 0) as mid FROM ontology_events").fetchone()["mid"]
        conn.execute("""
            INSERT OR REPLACE INTO subscriptions (subscriber, event_pattern, last_processed_id, created_at)
            VALUES (?, ?, ?, ?)
        """, (subscriber, event_pattern, max_id, now))
        conn.commit()
        conn.close()

    # ----------------------------------------------------------------
    # Consume
    # ----------------------------------------------------------------

    def consume(self, subscriber: str) -> list:
        """Get unprocessed events for this subscriber since last_processed_id."""
        conn = self._conn()

        # Get all subscription patterns for this subscriber
        subs = conn.execute(
            "SELECT event_pattern, last_processed_id FROM subscriptions WHERE subscriber = ?",
            (subscriber,)
        ).fetchall()

        if not subs:
            conn.close()
            return []

        # Find the minimum last_processed_id across all patterns
        min_last_id = min(s["last_processed_id"] for s in subs)
        patterns = [s["event_pattern"] for s in subs]

        # Fetch all events after min_last_id
        rows = conn.execute("""
            SELECT * FROM ontology_events WHERE id > ?
            ORDER BY priority DESC, created_at ASC
        """, (min_last_id,)).fetchall()
        conn.close()

        # Filter by patterns
        matched = []
        for row in rows:
            event_key = f"{row['domain']}.{row['event_type']}"
            for pattern in patterns:
                if _pattern_matches(pattern, event_key):
                    event = dict(row)
                    if event.get("payload"):
                        try:
                            event["payload"] = json.loads(event["payload"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    if event.get("graph_context"):
                        try:
                            event["graph_context"] = json.loads(event["graph_context"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    matched.append(event)
                    break  # avoid duplicates if multiple patterns match

        return matched

    # ----------------------------------------------------------------
    # Acknowledge
    # ----------------------------------------------------------------

    def ack(self, subscriber: str, event_id: int):
        """Mark event as processed by this subscriber (advance cursor)."""
        conn = self._conn()
        # Advance last_processed_id for all patterns of this subscriber
        conn.execute("""
            UPDATE subscriptions SET last_processed_id = MAX(last_processed_id, ?)
            WHERE subscriber = ?
        """, (event_id, subscriber))
        conn.commit()
        conn.close()

    # ----------------------------------------------------------------
    # Utilities
    # ----------------------------------------------------------------

    def get_recent(self, limit: int = 20) -> list:
        """Peek at recent events without consuming."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM ontology_events ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        events = []
        for row in rows:
            event = dict(row)
            for field in ("payload", "graph_context"):
                if event.get(field):
                    try:
                        event[field] = json.loads(event[field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            events.append(event)
        return events

    def get_stats(self) -> dict:
        """Get bus statistics."""
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*) as cnt FROM ontology_events").fetchone()["cnt"]
        by_domain = conn.execute("""
            SELECT domain, COUNT(*) as cnt FROM ontology_events
            GROUP BY domain ORDER BY cnt DESC
        """).fetchall()
        subs = conn.execute("SELECT * FROM subscriptions").fetchall()
        conn.close()
        return {
            "total_events": total,
            "events_by_domain": {r["domain"]: r["cnt"] for r in by_domain},
            "subscribers": [
                {"subscriber": s["subscriber"], "pattern": s["event_pattern"],
                 "last_processed_id": s["last_processed_id"]}
                for s in subs
            ],
        }

    def cleanup(self, keep_last: int = 1000):
        """Remove old events, keeping the most recent N."""
        conn = self._conn()
        conn.execute("""
            DELETE FROM ontology_events WHERE id NOT IN (
                SELECT id FROM ontology_events ORDER BY id DESC LIMIT ?
            )
        """, (keep_last,))
        conn.commit()
        conn.close()


def _pattern_matches(pattern: str, event_key: str) -> bool:
    """Match event_key (domain.event_type) against a subscription pattern.

    Supports * wildcards via fnmatch:
        'detection.*' matches 'detection.anomaly_detected'
        '*.anomaly_detected' matches 'detection.anomaly_detected'
        '*' matches everything
    """
    if pattern == "*":
        return True
    return fnmatch.fnmatch(event_key, pattern)


# ================================================================
# CLI
# ================================================================
if __name__ == "__main__":
    import sys

    bus = OntologyBus()

    if len(sys.argv) < 2:
        print("Usage: ontology_bus.py [stats|recent|publish|subscribe|consume]")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "stats":
        print(json.dumps(bus.get_stats(), indent=2))
    elif cmd == "recent":
        for e in bus.get_recent():
            print(f"[{e['id']}] {e['domain']}.{e['event_type']} from {e['source']}"
                  f" entity={e.get('entity_id')} @ {e['created_at']}")
    elif cmd == "publish" and len(sys.argv) >= 5:
        eid = bus.publish(sys.argv[2], sys.argv[3], sys.argv[4],
                          entity_id=sys.argv[5] if len(sys.argv) > 5 else None)
        print(f"Published event #{eid}")
    elif cmd == "subscribe" and len(sys.argv) >= 4:
        bus.subscribe(sys.argv[2], sys.argv[3])
        print(f"Subscribed {sys.argv[2]} to {sys.argv[3]}")
    elif cmd == "consume" and len(sys.argv) >= 3:
        events = bus.consume(sys.argv[2])
        for e in events:
            print(f"[{e['id']}] {e['domain']}.{e['event_type']} entity={e.get('entity_id')}")
    else:
        print("Usage: ontology_bus.py [stats|recent|publish <dom> <type> <src> [entity]|subscribe <sub> <pat>|consume <sub>]")
