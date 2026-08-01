"""Migration project store: persistent per-mapping status across a corpus.

SQLite (stdlib) under config/ (gitignored). `pentaho-migrate batch` populates it;
the UI's Project page and `pentaho-migrate project` read and update it. Statuses
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
    source_path TEXT NOT NULL DEFAULT '',
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
    source_path: str = ""
    steps: int
    auto: int
    review: int
    manual: int
    expressions: int
    score: int
    grade: str
    status: str
    review_verdict: str = ""   # SHIP | REVIEW | '' (agent never run)
    review_json: str = ""      # EtlReviewCheck summary as JSON
    updated_at: str


def resolve_source_path(raw: str) -> Path | None:
    """Find a recorded source file even after the repo moved or was renamed
    (the store predating the PDI-Migration -> Pentaho-Migration rename held
    dead absolute paths). Strategy: exact path, then rebase everything from
    the 'samples' segment onto the current repo root, then a basename search
    across the standard sample directories."""
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p
    # the store may carry Windows-style paths while the server runs on
    # POSIX (an engagement store moved between machines) - backslashes
    # never appear in the repo's own relative segments, so normalising
    # them is safe and makes the rebase/basename fallbacks portable
    if "\\" in raw:
        p = Path(raw.replace("\\", "/"))
    parts = p.parts
    if "samples" in parts:
        candidate = REPO_ROOT.joinpath(*parts[parts.index("samples"):])
        if candidate.is_file():
            return candidate
    for base in ("samples/informatica", "samples/talend", "samples/talend_demo",
                 "samples/crystal/corpus", "samples/cr_demo", "samples/crystal"):
        candidate = REPO_ROOT / base / p.name
        if candidate.is_file():
            return candidate
    return None


def _repair_paths(conn, table: str) -> int:
    """Heal stale source_path values in place (runs lazily on list reads)."""
    fixed = 0
    for row in conn.execute(
            f"SELECT rowid, source_path FROM {table} WHERE source_path != ''").fetchall():
        raw = row["source_path"]
        if Path(raw).is_file():
            continue
        resolved = resolve_source_path(raw)
        if resolved is not None:
            conn.execute(f"UPDATE {table} SET source_path=? WHERE rowid=?",
                         (str(resolved), row["rowid"]))
            fixed += 1
    return fixed


def _db_path() -> Path:
    config_dir = Path(os.environ.get("PENTAHO_MIGRATION_CONFIG_DIR")
                      or os.environ.get("PDI_MIGRATION_CONFIG_DIR")  # pre-rename fallback
                      or REPO_ROOT / "config")
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "project.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    # migrate stores created before these columns existed
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(mappings)")}
    for col in ("source_path", "review_verdict", "review_json"):
        if col not in columns:
            conn.execute(
                f"ALTER TABLE mappings ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    return conn


def record_mapping(record: MappingRecord) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO mappings
               (mapping, file, source_path, steps, auto, review, manual, expressions, score, grade, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(file, mapping) DO UPDATE SET
                 source_path=excluded.source_path,
                 steps=excluded.steps, auto=excluded.auto, review=excluded.review,
                 manual=excluded.manual, expressions=excluded.expressions,
                 score=excluded.score, grade=excluded.grade,
                 updated_at=datetime('now')""",
            (record.mapping, record.file, record.source_path, record.steps, record.auto,
             record.review, record.manual, record.expressions, record.score, record.grade,
             record.status),
        )


def get_mapping(file: str, mapping: str) -> MappingRecord | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM mappings WHERE file=? AND mapping=?", (file, mapping)
        ).fetchone()
    return MappingRecord(**dict(row)) if row else None


def list_mappings() -> list[MappingRecord]:
    with _connect() as conn:
        _repair_paths(conn, "mappings")  # heal paths from before a repo move/rename
        rows = conn.execute(
            "SELECT * FROM mappings ORDER BY score ASC, file, mapping"
        ).fetchall()
    return [MappingRecord(**dict(row)) for row in rows]


def set_mapping_review(file: str, mapping: str, verdict: str,
                       detail_json: str) -> bool:
    """Persist the ETL review agent's verdict (SHIP/REVIEW + detail)."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE mappings SET review_verdict=?, review_json=?, "
            "updated_at=datetime('now') WHERE file=? AND mapping=?",
            (verdict, detail_json, file, mapping),
        )
    return cursor.rowcount > 0


def export_store() -> Path:
    """A consistent snapshot of the live store (sqlite backup API - safe
    while the app is writing), left under config/ for download."""
    dst_path = _db_path().with_name("project_export.db")
    src, dst = _connect(), sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        # sqlite3's context manager scopes TRANSACTIONS, not the handle -
        # close explicitly or Windows keeps the files locked
        src.close()
        dst.close()
    return dst_path


def import_store(data: bytes) -> dict:
    """Replace the store's CONTENT with an exported snapshot, through the
    sqlite backup API - a file rename would fight Windows over handles
    other connections still hold. The current store is snapshotted to a
    .bak first; the upload must BE a sqlite file."""
    if not data.startswith(b"SQLite format 3\x00"):
        raise ValueError("that file is not a sqlite database - export the "
                         "store from the other machine's Project page")
    import shutil
    import time

    db = _db_path()
    if db.is_file():
        shutil.copy2(db, db.with_name(
            f"project.db.bak-{time.strftime('%Y%m%d-%H%M%S')}"))
    tmp = db.with_name("project_import_tmp.db")
    tmp.write_bytes(data)
    src, dst = sqlite3.connect(tmp), sqlite3.connect(db)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
        try:
            tmp.unlink()
        except OSError:
            pass
    return {"mappings": len(list_mappings()), "reports": len(list_reports())}


def set_status(file: str, mapping: str, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE mappings SET status=?, updated_at=datetime('now') WHERE file=? AND mapping=?",
            (status, file, mapping),
        )
    return cursor.rowcount > 0


# ---------------------------------------------------------------- reports

REPORTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    file            TEXT NOT NULL PRIMARY KEY,
    name            TEXT NOT NULL,
    source_path     TEXT NOT NULL DEFAULT '',
    formulas_auto   INTEGER NOT NULL,
    formulas_review INTEGER NOT NULL,
    formulas_manual INTEGER NOT NULL,
    todos           INTEGER NOT NULL,
    copilot_hours   REAL NOT NULL,
    manual_hours    REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'converted',
    triage_verdict  TEXT NOT NULL DEFAULT '',
    triage_json     TEXT NOT NULL DEFAULT '',
    parity_verdict  TEXT NOT NULL DEFAULT '',
    parity_note     TEXT NOT NULL DEFAULT '',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# agent-result columns added after the table first shipped (auto-migrated)
_REPORTS_AGENT_COLUMNS = ("triage_verdict", "triage_json",
                          "parity_verdict", "parity_note",
                          "gate_verdict", "gate_json")


def _ensure_reports(conn) -> None:
    conn.execute(REPORTS_SCHEMA)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(reports)")}
    for col in _REPORTS_AGENT_COLUMNS:
        if col not in columns:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")


class ReportRecord(BaseModel):
    file: str
    name: str
    source_path: str = ""
    formulas_auto: int
    formulas_review: int
    formulas_manual: int
    todos: int
    copilot_hours: float
    manual_hours: float
    status: str = "converted"
    triage_verdict: str = ""   # READY | REVIEW | BLOCKED | '' (never triaged)
    triage_json: str = ""      # TriageResult detail as JSON (reasons, sql, layout)
    parity_verdict: str = ""   # PASS | NEAR | FAIL | '' (never checked)
    parity_note: str = ""
    gate_verdict: str = ""     # SHIP | REVIEW | '' (release gate never run)
    gate_json: str = ""        # gate summary: pages, findings, groups
    updated_at: str = ""


def record_report(record: ReportRecord) -> None:
    with _connect() as conn:
        _ensure_reports(conn)
        conn.execute(
            """INSERT INTO reports
               (file, name, source_path, formulas_auto, formulas_review,
                formulas_manual, todos, copilot_hours, manual_hours, status)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(file) DO UPDATE SET
                 name=excluded.name, source_path=excluded.source_path,
                 formulas_auto=excluded.formulas_auto,
                 formulas_review=excluded.formulas_review,
                 formulas_manual=excluded.formulas_manual,
                 todos=excluded.todos, copilot_hours=excluded.copilot_hours,
                 manual_hours=excluded.manual_hours,
                 updated_at=datetime('now')""",
            (record.file, record.name, record.source_path, record.formulas_auto,
             record.formulas_review, record.formulas_manual, record.todos,
             record.copilot_hours, record.manual_hours, record.status),
        )


def list_reports() -> list[ReportRecord]:
    with _connect() as conn:
        _ensure_reports(conn)
        _repair_paths(conn, "reports")  # heal paths from before a repo move/rename
        rows = conn.execute(
            "SELECT * FROM reports ORDER BY formulas_manual DESC, file"
        ).fetchall()
    return [ReportRecord(**dict(row)) for row in rows]


def set_report_status(file: str, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with _connect() as conn:
        _ensure_reports(conn)
        cursor = conn.execute(
            "UPDATE reports SET status=?, updated_at=datetime('now') WHERE file=?",
            (status, file),
        )
    return cursor.rowcount > 0


def set_report_triage(file: str, verdict: str, detail_json: str) -> bool:
    """Persist a batch-triage verdict (READY/REVIEW/BLOCKED + detail JSON)."""
    with _connect() as conn:
        _ensure_reports(conn)
        cursor = conn.execute(
            "UPDATE reports SET triage_verdict=?, triage_json=?, "
            "updated_at=datetime('now') WHERE file=?",
            (verdict, detail_json, file),
        )
    return cursor.rowcount > 0


def set_report_gate(file: str, verdict: str, detail_json: str) -> bool:
    """Persist a release-gate verdict (SHIP/REVIEW + summary JSON) so the
    Project page carries the estate's gate state, not just the upload
    session that happened to run it."""
    with _connect() as conn:
        _ensure_reports(conn)
        cursor = conn.execute(
            "UPDATE reports SET gate_verdict=?, gate_json=?, "
            "updated_at=datetime('now') WHERE file=?",
            (verdict, detail_json, file),
        )
    return cursor.rowcount > 0


def find_report_for_source(source_name: str) -> "ReportRecord | None":
    """The stored report an UPLOADED source corresponds to, matched by
    file name, then by stem (the upload may be 'x.rpt' where the store
    holds the 'x.xml' dump, or vice versa)."""
    from pathlib import Path as _P

    name = _P(source_name or "").name
    stem = _P(name).stem.lower()
    if not stem:
        return None
    records = list_reports()
    for r in records:
        if r.file == name:
            return r
    for r in records:
        if _P(r.file).stem.lower() == stem                 or _P(r.source_path or "").stem.lower() == stem:
            return r
    return None


def set_report_parity(file: str, verdict: str, note: str) -> bool:
    """Persist an output-parity verdict (PASS/NEAR/FAIL + note)."""
    with _connect() as conn:
        _ensure_reports(conn)
        cursor = conn.execute(
            "UPDATE reports SET parity_verdict=?, parity_note=?, "
            "updated_at=datetime('now') WHERE file=?",
            (verdict, note, file),
        )
    return cursor.rowcount > 0
