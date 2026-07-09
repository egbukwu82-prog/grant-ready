"""Crawl history persistence behind a repository interface.

SQLite tonight; the interface mirrors app.repository's pattern so Postgres
can replace it later as a config change, not a rewrite. Two stores:
- snapshots: one raw snapshot per source (most recent fetch), for audit
- change_log: append-only — rows are inserted, never updated or deleted
  by the crawler (a human review step may later set status)
"""

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

from .sources import FetchResult


class CrawlHistoryRepository(ABC):
    @abstractmethod
    def save_snapshot(self, program_id: str, result: FetchResult) -> None:
        ...

    @abstractmethod
    def get_snapshot(self, program_id: str) -> Optional[Dict]:
        ...

    @abstractmethod
    def append_change(self, program_id: str, entry: Dict) -> None:
        ...

    @abstractmethod
    def list_changes(
        self, program_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict]:
        ...


class SqliteCrawlHistoryRepository(CrawlHistoryRepository):
    def __init__(self, db_path: Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                program_id   TEXT PRIMARY KEY,
                source_url   TEXT NOT NULL,
                fetched_at   TEXT NOT NULL,
                http_status  INTEGER,
                content_hash TEXT,
                raw_text     TEXT,
                error        TEXT
            );
            CREATE TABLE IF NOT EXISTS change_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                program_id TEXT NOT NULL,
                timestamp  TEXT NOT NULL,
                field      TEXT NOT NULL,
                old_value  TEXT,
                new_value  TEXT,
                status     TEXT NOT NULL DEFAULT 'pending_review'
            );
            """
        )
        self._conn.commit()

    def save_snapshot(self, program_id: str, result: FetchResult) -> None:
        self._conn.execute(
            """
            INSERT INTO snapshots
                (program_id, source_url, fetched_at, http_status, content_hash, raw_text, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(program_id) DO UPDATE SET
                source_url = excluded.source_url,
                fetched_at = excluded.fetched_at,
                http_status = excluded.http_status,
                content_hash = excluded.content_hash,
                raw_text = excluded.raw_text,
                error = excluded.error
            """,
            (
                program_id,
                result.url,
                result.fetched_at,
                result.http_status,
                result.content_hash,
                result.text,
                result.error,
            ),
        )
        self._conn.commit()

    def get_snapshot(self, program_id: str) -> Optional[Dict]:
        row = self._conn.execute(
            "SELECT * FROM snapshots WHERE program_id = ?", (program_id,)
        ).fetchone()
        return dict(row) if row else None

    def append_change(self, program_id: str, entry: Dict) -> None:
        self._conn.execute(
            """
            INSERT INTO change_log (program_id, timestamp, field, old_value, new_value, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                program_id,
                entry["timestamp"],
                entry["field"],
                entry.get("old_value"),
                entry.get("new_value"),
                entry.get("status", "pending_review"),
            ),
        )
        self._conn.commit()

    def list_changes(
        self, program_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict]:
        query = "SELECT * FROM change_log WHERE 1=1"
        params = []
        if program_id is not None:
            query += " AND program_id = ?"
            params.append(program_id)
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id"
        return [dict(r) for r in self._conn.execute(query, params).fetchall()]
