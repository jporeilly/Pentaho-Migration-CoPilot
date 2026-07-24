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

PostgreSQL only for now (the JDBC url is parsed; other drivers get an honest
"introspection not available" instead of a guess).
"""

import json
import os
import re
from pathlib import Path

import httpx

from pentaho_migration.llm import TranslationError
from pentaho_migration.llm.settings import LLMSettings, load_settings
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


def _connect(jndi_entry: dict):
    """psycopg2 connection for a resolved JNDI entry (PostgreSQL only)."""
    m = _JDBC_PG_RE.match(jndi_entry.get("url", ""))
    if not m:
        raise RuntimeError(
            "schema introspection currently supports PostgreSQL JNDI "
            f"connections only (url: {jndi_entry.get('url', '<none>')})")
    try:
        import psycopg2
    except ImportError:
        raise RuntimeError(
            "psycopg2 is not installed - `pip install psycopg2-binary` "
            "to enable schema introspection")
    try:
        return psycopg2.connect(
            host=m.group("host"), port=int(m.group("port") or 5432),
            dbname=m.group("db"),
            user=jndi_entry.get("user", ""), password=jndi_entry.get("password", ""),
            connect_timeout=5)
    except Exception as exc:
        raise RuntimeError(
            f"cannot connect to {jndi_entry['url']}: {str(exc).strip()}")


def probe_schema(jndi: str) -> dict:
    """Introspect the JNDI target: every user table with its columns/types.
    Raises RuntimeError with an actionable message on any failure."""
    entry = resolve_jndi(jndi)
    if entry is None:
        raise RuntimeError(
            f"JNDI connection {jndi!r} not found in simple-jndi "
            "(~/.pentaho/simple-jndi or the PRD install)")
    conn = _connect(entry)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_schema, table_name, column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name, ordinal_position")
        tables: dict[tuple, list] = {}
        for schema, table, column, dtype in cur.fetchall():
            tables.setdefault((schema, table), []).append(
                {"name": column, "type": dtype})
    finally:
        conn.close()
    return {
        "jndi": jndi,
        "url": entry["url"],
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
        conn = _connect(entry)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc), "checked_sql": ""}
    try:
        cur = conn.cursor()
        try:
            cur.execute("EXPLAIN " + checked)
            return {"ok": True, "error": "", "checked_sql": checked}
        except Exception as exc:
            return {"ok": False,
                    "error": str(exc).strip().splitlines()[0],
                    "checked_sql": checked}
    finally:
        conn.rollback()
        conn.close()


def schema_context(schema: dict, max_chars: int = 6000) -> str:
    """Compact schema text for the LLM prompt: one line per table."""
    lines = []
    for t in schema.get("tables", []):
        cols = ", ".join(f"{c['name']} {c['type']}" for c in t["columns"])
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
    """Schema-grounded SQL chat via the configured LLM provider (Ollama)."""

    def __init__(self, settings: LLMSettings | None = None, timeout: float = 120.0):
        self.settings = settings or load_settings()
        self.timeout = timeout

    def check_provider(self) -> None:
        if self.settings.provider == "none":
            raise TranslationError(
                "The SQL assistant needs an LLM - choose a provider in Settings.")
        if self.settings.provider == "anthropic":
            raise TranslationError(
                "The Anthropic provider is not implemented yet - use Ollama.")
        if not self.settings.model:
            raise TranslationError(
                "No Ollama model configured - open Settings and apply the recommendation.")

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
        response = httpx.post(
            f"{self.settings.base_url}/api/chat",
            json={"model": self.settings.model, "messages": messages,
                  "stream": False, "format": SQL_ASSIST_SCHEMA,
                  "options": {"temperature": 0}},
            timeout=self.timeout)
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])
