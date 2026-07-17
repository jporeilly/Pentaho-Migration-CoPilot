"""Migration project store: persistent per-mapping status across a corpus.

SQLite (stdlib) under config/ (gitignored). `pdi-migrate batch` populates it;
the UI's Project page and `pdi-migrate project` read and update it. Statuses
follow the review workflow: converted -> in_review -> verified (or failed).
"""

import os
import sqlite3
from pathlib import Path

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUSES = ("converted", "in_review", "verified", "failed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS mappings (
    mapping     TEXT NOT NULL,
    file        TEXT NOT NULL,
    steps       INTEGER NOT NULL,
    auto        INTEGER NOT NULL,
    review      INTEGER NOT NULL,
    manual      INTEGER NOT NULL,
    expressions INTEGER NOT NULL,
    score       INTEGER NOT NULL,
    grade       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'converted',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (file, mapping)
);
"""


class MappingRecord(BaseModel):
    mapping: str
    file: str
    steps: int
    auto: int
    review: int
    manual: int
    expressions: int
    score: int
    grade: str
    status: str
    updated_at: str


def _db_path() -> Path:
    config_dir = Path(os.environ.get("PDI_MIGRATION_CONFIG_DIR", REPO_ROOT / "config"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "project.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def record_mapping(record: MappingRecord) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO mappings
               (mapping, file, steps, auto, review, manual, expressions, score, grade, status)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(file, mapping) DO UPDATE SET
                 steps=excluded.steps, auto=excluded.auto, review=excluded.review,
                 manual=excluded.manual, expressions=excluded.expressions,
                 score=excluded.score, grade=excluded.grade,
                 updated_at=datetime('now')""",
            (record.mapping, record.file, record.steps, record.auto, record.review,
             record.manual, record.expressions, record.score, record.grade, record.status),
        )


def list_mappings() -> list[MappingRecord]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM mappings ORDER BY score ASC, file, mapping"
        ).fetchall()
    return [MappingRecord(**dict(row)) for row in rows]


def set_status(file: str, mapping: str, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE mappings SET status=?, updated_at=datetime('now') WHERE file=? AND mapping=?",
            (status, file, mapping),
        )
    return cursor.rowcount > 0
