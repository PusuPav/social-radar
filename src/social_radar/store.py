"""SQLite store so each mention is alerted once, plus a history you can query."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Mention, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS mentions (
    uid TEXT PRIMARY KEY,
    watch TEXT, source TEXT, url TEXT, author TEXT, snippet TEXT,
    relevance REAL, sentiment TEXT, summary TEXT,
    notified INTEGER DEFAULT 0,
    seen_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_watch ON mentions(watch, seen_at);
"""


class Store:
    def __init__(self, path: str | Path = "radar.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def is_new(self, m: Mention) -> bool:
        cur = self.conn.execute("SELECT 1 FROM mentions WHERE uid = ?", (m.uid,))
        return cur.fetchone() is None

    def save(self, m: Mention, notified: bool) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO mentions
               (uid, watch, source, url, author, snippet, relevance, sentiment, summary, notified, seen_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (m.uid, m.watch, m.source, m.url, m.author, m.snippet(500), m.relevance,
             m.sentiment, m.summary, int(notified), utcnow().isoformat()),
        )
        self.conn.commit()

    def recent(self, limit: int = 50) -> list[tuple]:
        return self.conn.execute(
            "SELECT seen_at, watch, source, relevance, url FROM mentions "
            "WHERE notified = 1 ORDER BY seen_at DESC LIMIT ?", (limit,)
        ).fetchall()

    def close(self) -> None:
        self.conn.close()
