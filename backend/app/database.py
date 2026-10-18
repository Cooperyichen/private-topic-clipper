from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'INBOX',
    raw_text TEXT,
    editable_text TEXT,
    note TEXT,
    source_url TEXT,
    source_title TEXT,
    video_start_seconds REAL,
    video_end_seconds REAL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(clip_id, checksum_sha256)
);

CREATE TABLE IF NOT EXISTS extraction_jobs (
    id TEXT PRIMARY KEY,
    clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'PENDING',
    mineru_version TEXT NOT NULL DEFAULT '4.0.9',
    tier TEXT NOT NULL DEFAULT 'basic',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    output_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS clip_search USING fts5(
    clip_id UNINDEXED,
    raw_text,
    editable_text,
    note,
    source_title,
    tokenize = 'unicode61'
);

INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
