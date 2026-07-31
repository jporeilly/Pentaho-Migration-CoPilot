"""Schema-aware SQL agent: validate and repair report SQL against the real
target database before the .prpt ever opens in PRD.

Three layers, deterministic first per the product's design principle:

1. resolve_jndi()  - read the JNDI connection exactly the way the reporting
   engine does: simple-jndi default.properties in the user's ~/.pentaho and
   the PRD install's resources folder.
2. probe_schema() / validate_sql() - deterministic ground truth: introspect
   information_schema and EXPLAIN the report's query (parameters substituted
   with their defaults) against the live database. No LLM involved.
3. SqlAssistant   - the chat layer: the LLM sees the real schema, the report
   SQL, and the validation verdict, and proposes corrected SQL. Proposals are
   advisory - the UI shows them as a reviewable diff, never auto-applied.

Dialects: PostgreSQL (live-verified), MySQL, SQL Server, and Oracle via
db_dialects.py adapters; anything else gets an honest "introspection not
available" instead of a guess.
"""

import os
import re
from pathlib import Path

from pentaho_migration.llm.settings import LLMSettings, load_settings
from pentaho_migration.llm.translate import chat_json, check_provider
from pentaho_migration.reports.environment import find_prd_home

_JDBC_PG_RE = re.compile(
    r"^jdbc:postgresql://(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<db>[^?]+)")


def _jndi_files() -> list[Path]:
    files = [Path.home() / ".pentaho" / "simple-jndi" / "default.properties"]
    prd = find_prd_home()
    if prd is not None:
        files.append(prd / "resources" / "simple-jndi" / "default.properties")
    extra = os.environ.get("SIMPLE_JNDI_PROPERTIES")
    if extra:
        files.insert(0, Path(extra))
    return files


def list_jndi_connections() -> list[dict]:
    """Every JNDI connection defined in the simple-jndi properties files the
    reporting engine reads: [{'name', 'url', 'driver', 'introspectable'}].
    First definition of a name wins (same precedence as resolve_jndi)."""
    connections: dict[str, dict] = {}
    for path in _jndi_files():
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            prefix, _, prop = key.strip().partition("/")
            if not prefix or not prop:
                continue
            entry = connections.setdefault(prefix, {"name": prefix})
            # user travels to the UI so an edit pre-fills it; the password
            # NEVER leaves the server
            if prop in ("url", "driver", "user") and prop not in entry:
                entry[prop] = value.strip()
    from pentaho_migration.reports.db_dialects import dialect_for

    out = []
    for entry in connections.values():
        url = entry.get("url", "")
        if not url:
            continue
        dialect = dialect_for(url)
        entry["introspectable"] = dialect is not None
        entry["dialect"] = dialect.name if dialect else ""
        out.append(entry)
    return sorted(out, key=lambda e: e["name"].lower())


def _user_jndi_file() -> Path:
    """The user's own simple-jndi properties file - the one connection
    save/edit/delete manages (the PRD install's copy stays untouched)."""
    extra = os.environ.get("SIMPLE_JNDI_PROPERTIES")
    if extra:
        return Path(extra)
    return Path.home() / ".pentaho" / "simple-jndi" / "default.properties"


_DRIVER_BY_URL = [
    ("jdbc:postgresql:", "org.postgresql.Driver"),
    ("jdbc:mysql:", "com.mysql.cj.jdbc.Driver"),
    ("jdbc:sqlserver:", "com.microsoft.sqlserver.jdbc.SQLServerDriver"),
    ("jdbc:oracle:", "oracle.jdbc.OracleDriver"),
    ("jdbc:hsqldb:", "org.hsqldb.jdbcDriver"),
]


def save_jndi_connection(name: str, url: str, driver: str = "",
                         user: str = "", password: str = "") -> Path:
    """Create or update a JNDI connection in the user's simple-jndi file.
    The block format matches what the reporting engine reads. Returns the
    file written."""
    if not re.fullmatch(r"\w+", name or ""):
        raise ValueError("connection name must be a plain identifier (letters/digits/_)")
    if not url.startswith("jdbc:"):
        raise ValueError("url must be a jdbc: URL")
    if not driver:
        driver = next((d for prefix, d in _DRIVER_BY_URL if url.startswith(prefix)), "")
    if not driver:
        raise ValueError("driver class is required for this jdbc URL type")

    path = _user_jndi_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (path.read_text(encoding="utf-8", errors="replace").splitlines()
             if path.is_file() else [])
    lines = [ln for ln in lines if not ln.strip().startswith(f"{name}/")]
    while lines and not lines[-1].strip():
        lines.pop()
    lines += ["", f"{name}/type=javax.sql.DataSource", f"{name}/driver={driver}",
              f"{name}/user={user}", f"{name}/password={password}",
              f"{name}/url={url}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def delete_jndi_connection(name: str) -> bool:
    """Remove a connection from the user's simple-jndi file. Returns True
    when something was removed. A connection defined only in the PRD
    install's copy is not touched (and will still resolve)."""
    path = _user_jndi_file()
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [ln for ln in lines if not ln.strip().startswith(f"{name}/")]
    if len(kept) == len(lines):
        return False
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return True


def resolve_jndi(name: str) -> dict | None:
    """{'url', 'driver', 'user', 'password', 'source'} for a JNDI name, read
    from the same simple-jndi properties files the engine uses."""
    for path in _jndi_files():
        if not path.is_file():
            continue
        entry: dict = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            prefix, _, prop = key.strip().partition("/")
            if prefix == name and prop:
                entry[prop] = value.strip()
        if entry.get("url"):
            entry["source"] = str(path)
            return entry
    return None


def _dialect_and_connection(jndi_entry: dict):
    """(dialect, open connection) for a resolved JNDI entry, via the adapter
    matching its JDBC URL family (PostgreSQL, MySQL, SQL Server, Oracle)."""
    from pentaho_migration.reports.db_dialects import dialect_for

    url = jndi_entry.get("url", "")
    dialect = dialect_for(url)
    if dialect is None:
        raise RuntimeError(
            "schema introspection supports PostgreSQL, MySQL, SQL Server and "
            f"Oracle JNDI connections - this url is none of those: {url or '<none>'}")
    try:
        conn = dialect.connect(url, jndi_entry.get("user", ""),
                               jndi_entry.get("password", ""))
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"cannot connect to {url}: {str(exc).strip()}")
    return dialect, conn


def _connect(jndi_entry: dict):
    """Back-compat shim: connection only (PostgreSQL tests monkeypatch this)."""
    return _dialect_and_connection(jndi_entry)[1]


def probe_schema(jndi: str) -> dict:
    """Introspect the JNDI target: every user table with its columns/types.
    Raises RuntimeError with an actionable message on any failure."""
    entry = resolve_jndi(jndi)
    if entry is None:
        raise RuntimeError(
            f"JNDI connection {jndi!r} not found in simple-jndi "
            "(~/.pentaho/simple-jndi or the PRD install)")
    dialect, conn = _dialect_and_connection(entry)
    try:
        cur = conn.cursor()
        cur.execute(dialect.columns_sql)
        tables: dict[tuple, list] = {}
        for schema, table, column, dtype in cur.fetchall():
            tables.setdefault((schema, table), []).append(
                {"name": column, "type": dtype})
        # PK/FK decoration - an enhancement, never fatal to introspection
        try:
            cur.execute(dialect.keys_sql)
            key_rows = cur.fetchall()
        except Exception:
            key_rows = []
        for schema, table, column, ctype, rs, rt, rcol in key_rows:
            for col in tables.get((schema, table), []):
                if col["name"] != column:
                    continue
                kind = "PK" if str(ctype).startswith("PRIMARY") else "FK"
                keys = set((col.get("key") or "").split(",")) - {""}
                keys.add(kind)
                col["key"] = ",".join(sorted(keys))
                if kind == "FK" and rt and rcol:
                    col["references"] = f"{rs}.{rt}.{rcol}" if rs else f"{rt}.{rcol}"
    finally:
        conn.close()
    return {
        "jndi": jndi,
        "url": entry["url"],
        "dialect": dialect.name,
        "tables": [{"schema": s, "name": t, "columns": cols}
                   for (s, t), cols in tables.items()],
    }


def substitute_params(sql: str, parameters: list[dict]) -> str:
    """Replace ${Param} placeholders with the parameter's default (or NULL)
    so the query becomes EXPLAIN-able. Defaults are quoted as string
    literals - Postgres casts them where the comparison needs it."""
    defaults = {p.get("name", ""): p.get("default", "") for p in parameters}

    def _sub(m: re.Match) -> str:
        value = defaults.get(m.group(1), "")
        if value == "":
            return "NULL"
        return "'" + str(value).replace("'", "''") + "'"

    return re.sub(r"\$\{(\w+)\}", _sub, sql)


def validate_sql(jndi: str, sql: str, parameters: list[dict] | None = None) -> dict:
    """Deterministic ground truth: EXPLAIN the (parameter-substituted) query
    against the live database. {'ok', 'error', 'checked_sql'}; connection or
    resolution failures land in 'error' with ok=False and checked_sql=''."""
    checked = substitute_params(sql, parameters or [])
    try:
        entry = resolve_jndi(jndi)
        if entry is None:
            raise RuntimeError(
                f"JNDI connection {jndi!r} not found in simple-jndi")
        from pentaho_migration.reports.db_dialects import dialect_for
        dialect = dialect_for(entry.get("url", ""))
        conn = _connect(entry)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc), "checked_sql": ""}
    try:
        cur = conn.cursor()
        try:
            if dialect is not None:
                dialect.validate(cur, checked)
            else:  # only reachable when tests monkeypatch _connect
                cur.execute("EXPLAIN " + checked)
            return {"ok": True, "error": "", "checked_sql": checked}
        except Exception as exc:
            return {"ok": False,
                    "error": str(exc).strip().splitlines()[0],
                    "checked_sql": checked}
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


def preview_query(jndi: str, sql: str, parameters: list[dict] | None = None,
                  limit: int = 50) -> dict:
    """Execute the (parameter-substituted) SELECT and return the first rows -
    the Inspect page's dataset preview. Read-only by construction: anything
    that is not a SELECT/WITH is refused, and only `limit` rows are fetched."""
    checked = substitute_params(sql, parameters or [])
    if not re.match(r"(?is)^\s*(SELECT|WITH)\b", checked):
        raise RuntimeError("only SELECT queries can be previewed")
    entry = resolve_jndi(jndi)
    if entry is None:
        raise RuntimeError(f"JNDI connection {jndi!r} not found in simple-jndi")
    dialect, conn = _dialect_and_connection(entry)
    try:
        cur = conn.cursor()
        cur.execute(checked)
        columns = [d[0] for d in (cur.description or [])]
        raw = cur.fetchmany(limit + 1)
        truncated = len(raw) > limit
        rows = [["" if v is None else str(v) for v in row] for row in raw[:limit]]
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
    return {"dialect": dialect.name, "columns": columns, "rows": rows,
            "truncated": truncated}


def schema_context(schema: dict, max_chars: int = 6000) -> str:
    """Compact schema text for the LLM prompt: one line per table, with
    PK/FK markers so join advice follows the real relationships."""
    def _col(c):
        out = f"{c['name']} {c['type']}"
        if c.get("key"):
            out += f" [{c['key']}"
            if c.get("references"):
                out += f" -> {c['references']}"
            out += "]"
        return out

    lines = []
    for t in schema.get("tables", []):
        cols = ", ".join(_col(c) for c in t["columns"])
        lines.append(f"{t['schema']}.{t['name']}({cols})")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (schema truncated)"
    return text


SQL_ASSIST_PROMPT = """\
You are the schema assistant inside Pentaho Migration Copilot. A SAP Crystal
report has been converted to Pentaho Report Designer, and its SQL must run
against the migration target database. You are given the REAL schema of that
database, the report's current SQL, and the result of validating that SQL
against the database. Answer the user's question about the schema or the SQL.

Rules:
- The schema provided is the ground truth. Never invent tables or columns.
- Preserve the SELECT-list aliases exactly (quoted "ALIAS" names): the report
  layout binds to those alias names, so changing them breaks the report.
- Keep ${Param} placeholders exactly as written - they are PRD parameters.
- When the fix is a SQL change, put the complete corrected statement in the
  "sql" field (not a fragment); otherwise leave "sql" empty.
- Reply with JSON only: {"reply": "<answer for the user>", "sql": "<full corrected SQL or empty>"}
- Be concise. If the validation error already names the problem, explain it
  in one sentence and fix it.
"""

SQL_ASSIST_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "sql": {"type": "string"},
    },
    "required": ["reply"],
}


class SqlAssistant:
    """Schema-grounded SQL chat via the configured LLM provider (Ollama,
    Anthropic, OpenAI, Google Gemini, or Azure OpenAI — same provider dispatch
    as expression/formula translation)."""

    def __init__(self, settings: LLMSettings | None = None, timeout: float = 120.0):
        self.settings = settings or load_settings()
        self.timeout = timeout

    def check_provider(self) -> None:
        check_provider(self.settings)

    def ask(self, question: str, sql: str, schema_text: str,
            validation: dict | None = None,
            history: list[dict] | None = None) -> dict:
        """One question -> {'reply', 'sql'}. history is prior chat turns as
        [{'role': 'user'|'assistant', 'content': ...}]."""
        context = (f"Target database schema (ground truth):\n{schema_text}\n\n"
                   f"Report SQL:\n{sql}\n")
        if validation is not None:
            verdict = ("VALID - EXPLAIN passed" if validation.get("ok")
                       else f"INVALID - {validation.get('error', 'unknown error')}")
            context += f"\nValidation against the live database: {verdict}\n"
        messages = [{"role": "system", "content": SQL_ASSIST_PROMPT},
                    {"role": "user", "content": context}]
        for turn in history or []:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": question})
        result = self._chat(messages)
        return {"reply": result.get("reply", ""), "sql": result.get("sql", "")}

    def _chat(self, messages: list[dict]) -> dict:
        return chat_json(self.settings, messages, SQL_ASSIST_SCHEMA, self.timeout)
