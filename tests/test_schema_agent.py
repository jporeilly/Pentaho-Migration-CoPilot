"""Schema-aware SQL agent: JNDI resolution from simple-jndi properties,
parameter substitution, deterministic EXPLAIN validation (mocked connection),
the schema-grounded chat (mocked LLM), and the /reports/schema|sql/* API.
Live-database assertions are opt-in via CSCU_LIVE=1."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.llm import TranslationError
from pentaho_migration.llm.settings import LLMSettings
from pentaho_migration.reports import schema_agent
from pentaho_migration.reports.schema_agent import (
    SqlAssistant, resolve_jndi, schema_context, substitute_params, validate_sql)

client = TestClient(app)

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "branch_transactions.xml"


# ------------------------------------------------------------ JNDI resolution

def test_resolve_jndi_from_properties(tmp_path, monkeypatch):
    props = tmp_path / "default.properties"
    props.write_text(
        "# comment\n"
        "CSCU/type=javax.sql.DataSource\n"
        "CSCU/driver=org.postgresql.Driver\n"
        "CSCU/user=pdc_user\n"
        "CSCU/password=secret\n"
        "CSCU/url=jdbc:postgresql://db.example:5433/cscu_core\n",
        encoding="utf-8")
    monkeypatch.setenv("SIMPLE_JNDI_PROPERTIES", str(props))
    entry = resolve_jndi("CSCU")
    assert entry["url"] == "jdbc:postgresql://db.example:5433/cscu_core"
    assert entry["user"] == "pdc_user"
    assert entry["source"] == str(props)
    assert resolve_jndi("Nope") is None or "url" in (resolve_jndi("Nope") or {})


def test_non_postgres_url_is_an_honest_error(tmp_path, monkeypatch):
    props = tmp_path / "default.properties"
    props.write_text("H2/url=jdbc:hsqldb:mem:sample\n", encoding="utf-8")
    monkeypatch.setenv("SIMPLE_JNDI_PROPERTIES", str(props))
    result = validate_sql("H2", "SELECT 1", [])
    assert not result["ok"]
    assert "PostgreSQL" in result["error"]


def test_list_jndi_connections(tmp_path, monkeypatch):
    props = tmp_path / "default.properties"
    props.write_text(
        "CSCU/driver=org.postgresql.Driver\n"
        "CSCU/url=jdbc:postgresql://db:5433/cscu_core\n"
        "SampleData/driver=org.hsqldb.jdbcDriver\n"
        "SampleData/url=jdbc:hsqldb:file:/x/sampledata\n",
        encoding="utf-8")
    monkeypatch.setenv("SIMPLE_JNDI_PROPERTIES", str(props))
    from pentaho_migration.reports.schema_agent import list_jndi_connections
    conns = {c["name"]: c for c in list_jndi_connections()}
    assert conns["CSCU"]["introspectable"] is True
    assert conns["SampleData"]["introspectable"] is False


def test_api_connections_endpoint():
    res = client.get("/reports/connections")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_connection_crud(tmp_path, monkeypatch):
    props = tmp_path / "default.properties"
    monkeypatch.setenv("SIMPLE_JNDI_PROPERTIES", str(props))
    from pentaho_migration.reports.schema_agent import (
        delete_jndi_connection, list_jndi_connections, save_jndi_connection)

    save_jndi_connection("TESTDB", "jdbc:postgresql://h:5432/d", user="u", password="p")
    text = props.read_text(encoding="utf-8")
    assert "TESTDB/driver=org.postgresql.Driver" in text   # inferred from url
    assert "TESTDB/url=jdbc:postgresql://h:5432/d" in text
    assert any(c["name"] == "TESTDB" for c in list_jndi_connections())

    # update replaces the block, never duplicates it
    save_jndi_connection("TESTDB", "jdbc:postgresql://h2:5432/d2")
    text = props.read_text(encoding="utf-8")
    assert text.count("TESTDB/url=") == 1
    assert "h2:5432/d2" in text

    assert delete_jndi_connection("TESTDB") is True
    assert "TESTDB/" not in props.read_text(encoding="utf-8")
    assert delete_jndi_connection("TESTDB") is False

    with pytest.raises(ValueError):
        save_jndi_connection("bad name", "jdbc:postgresql://h/d")
    with pytest.raises(ValueError):
        save_jndi_connection("X", "not-a-jdbc-url")


def test_api_connection_save_and_delete(tmp_path, monkeypatch):
    props = tmp_path / "default.properties"
    monkeypatch.setenv("SIMPLE_JNDI_PROPERTIES", str(props))
    res = client.post("/reports/connections", json={
        "name": "APITEST", "url": "jdbc:postgresql://h:5432/d",
        "user": "u", "password": "p"})
    assert res.status_code == 200
    assert any(c["name"] == "APITEST" for c in res.json()["connections"])
    # passwords never come back in the listing
    assert all("password" not in c for c in res.json()["connections"])

    res = client.delete("/reports/connections/APITEST")
    assert res.status_code == 200
    res = client.delete("/reports/connections/APITEST")
    assert res.status_code == 404


# ------------------------------------------------------ parameter substitution

def test_substitute_params_defaults_and_null():
    sql = "SELECT a FROM t WHERE b = ${Branch} AND c = ${Missing}"
    out = substitute_params(sql, [{"name": "Branch", "default": "O'Hare"}])
    assert "b = 'O''Hare'" in out          # quoted + escaped
    assert "c = NULL" in out               # no default -> NULL


# ----------------------------------------------- validation (mock connection)

class _FakeCursor:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)
        if self.fail_with:
            raise Exception(self.fail_with)


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def rollback(self):
        pass

    def close(self):
        pass


def _fake_jndi(monkeypatch):
    monkeypatch.setattr(schema_agent, "resolve_jndi",
                        lambda name: {"url": "jdbc:postgresql://x/db"})


def test_validate_sql_ok(monkeypatch):
    _fake_jndi(monkeypatch)
    cur = _FakeCursor()
    monkeypatch.setattr(schema_agent, "_connect", lambda entry: _FakeConn(cur))
    result = validate_sql("CSCU", "SELECT a FROM t WHERE b = ${P}",
                          [{"name": "P", "default": "x"}])
    assert result["ok"]
    assert cur.executed == ["EXPLAIN SELECT a FROM t WHERE b = 'x'"]


def test_validate_sql_reports_db_error(monkeypatch):
    _fake_jndi(monkeypatch)
    cur = _FakeCursor(fail_with='ERROR: column "nope" does not exist\nLINE 1: ...')
    monkeypatch.setattr(schema_agent, "_connect", lambda entry: _FakeConn(cur))
    result = validate_sql("CSCU", "SELECT nope FROM t", [])
    assert not result["ok"]
    assert 'column "nope" does not exist' in result["error"]
    assert "LINE 1" not in result["error"]  # first line only


# ------------------------------------------------------------------ chat layer

def test_schema_context_is_compact():
    text = schema_context({"tables": [
        {"schema": "cscu_core", "name": "members",
         "columns": [{"name": "mbr_id", "type": "integer"},
                     {"name": "mbr_no", "type": "text"}]}]})
    assert text == "cscu_core.members(mbr_id integer, mbr_no text)"


class _FakeAssistant(SqlAssistant):
    def _chat(self, messages):
        self.messages = messages
        return {"reply": "MBR_ID does not exist on transactions - join via accounts.",
                "sql": "SELECT 1"}


def test_assistant_grounds_the_chat_in_schema_and_validation():
    a = _FakeAssistant(LLMSettings(provider="ollama", model="test"))
    out = a.ask("why does my query fail?", "SELECT x", "cscu_core.t(a integer)",
                validation={"ok": False, "error": "column x does not exist"},
                history=[{"role": "user", "content": "earlier question"}])
    assert out["sql"] == "SELECT 1"
    context = a.messages[1]["content"]
    assert "cscu_core.t(a integer)" in context
    assert "INVALID - column x does not exist" in context
    assert a.messages[2] == {"role": "user", "content": "earlier question"}
    assert a.messages[-1]["content"] == "why does my query fail?"


def test_assistant_provider_gating():
    with pytest.raises(TranslationError):
        SqlAssistant(LLMSettings(provider="none")).check_provider()


def test_assistant_shares_cloud_providers_with_translation(monkeypatch):
    """The SQL assistant uses the same provider dispatch as expression/formula
    translation, so a cloud provider (with a key) is accepted here too."""
    import sys

    fake = type(sys)("anthropic")
    fake.APIError = Exception
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    # anthropic without a key is rejected, with a key is accepted - no longer
    # the old hard-coded "not implemented yet"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(TranslationError):
        SqlAssistant(LLMSettings(provider="anthropic", api_key="")).check_provider()
    SqlAssistant(LLMSettings(provider="anthropic", api_key="sk-x")).check_provider()


# ------------------------------------------------------------------------ API

def test_api_schema_unavailable_is_503(monkeypatch):
    def boom(jndi):
        raise RuntimeError("JNDI connection 'X' not found in simple-jndi")
    monkeypatch.setattr("pentaho_migration.reports.api.probe_schema", boom)
    res = client.get("/reports/schema?jndi=X")
    assert res.status_code == 503
    assert "not found" in res.json()["detail"]


def test_api_sql_check(monkeypatch):
    monkeypatch.setattr(
        "pentaho_migration.reports.api.validate_sql",
        lambda jndi, sql, params: {"ok": True, "error": "", "checked_sql": sql})
    res = client.post("/reports/sql/check", json={
        "jndi": "CSCU", "sql": "SELECT 1",
        "parameters": [{"name": "P", "default": "x"}]})
    assert res.status_code == 200
    assert res.json()["ok"]


def test_api_sql_chat_requires_provider(monkeypatch):
    import pentaho_migration.reports.schema_agent as mod
    monkeypatch.setattr(mod, "load_settings", lambda: LLMSettings(provider="none"))
    res = client.post("/reports/sql/chat", json={
        "jndi": "CSCU", "sql": "SELECT 1", "question": "hi"})
    assert res.status_code == 503


def test_api_sql_chat_happy_path(monkeypatch):
    monkeypatch.setattr(SqlAssistant, "check_provider", lambda self: None)
    monkeypatch.setattr(
        SqlAssistant, "_chat",
        lambda self, messages: {"reply": "fixed", "sql": "SELECT fixed"})
    monkeypatch.setattr(
        "pentaho_migration.reports.api.probe_schema",
        lambda jndi: {"tables": [{"schema": "s", "name": "t",
                                  "columns": [{"name": "a", "type": "int"}]}]})
    monkeypatch.setattr(
        "pentaho_migration.reports.api.validate_sql",
        lambda jndi, sql, params: {"ok": False, "error": "bad", "checked_sql": sql})
    res = client.post("/reports/sql/chat", json={
        "jndi": "CSCU", "sql": "SELECT x", "question": "fix it"})
    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "fixed"
    assert body["sql"] == "SELECT fixed"
    assert body["validation"]["ok"] is False


def test_api_convert_sql_override():
    res = client.post(
        "/reports/convert?jndi=CSCU",
        files={"dump": ("branch.xml", SAMPLE.read_bytes(), "text/xml")},
        data={"sql_override": "SELECT 1 AS \"BRANCH_NAME\""})
    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["sql"] == 'SELECT 1 AS "BRANCH_NAME"'
    assert any("schema assistant" in t for t in body["summary"]["todos"])


# ------------------------------------------------------------------- live DB

@pytest.mark.skipif(os.environ.get("CSCU_LIVE") != "1",
                    reason="set CSCU_LIVE=1 to validate against the live CSCU database")
def test_live_flagship_sql_validates():
    from pentaho_migration.reports import load_report_model
    from pentaho_migration.reports.schema_agent import probe_schema

    schema = probe_schema("CSCU")
    names = {t["name"] for t in schema["tables"]}
    assert {"members", "accounts", "transactions", "branches"} <= names

    model = load_report_model(SAMPLE, jndi="CSCU")
    params = [{"name": p.name, "default": p.default} for p in model.parameters]
    assert validate_sql("CSCU", model.sql, params)["ok"]
    bad = validate_sql("CSCU", "SELECT nope FROM cscu_core.transactions", [])
    assert not bad["ok"] and "nope" in bad["error"]


# ------------------------------------------------------------- db dialects

def test_dialect_url_parsing():
    from pentaho_migration.reports.db_dialects import dialect_for

    cases = {
        "jdbc:postgresql://h:5433/db": ("PostgreSQL", "h", "5433", "db"),
        "jdbc:mysql://h/db": ("MySQL", "h", None, "db"),
        "jdbc:sqlserver://h:1433;databaseName=db;encrypt=false": ("SQL Server", "h", "1433", "db"),
        "jdbc:oracle:thin:@//h:1521/svc": ("Oracle", "h", "1521", "svc"),
        "jdbc:oracle:thin:@h:1521:sid": ("Oracle", "h", "1521", "sid"),
    }
    for url, (name, host, port, db) in cases.items():
        d = dialect_for(url)
        assert d is not None and d.name == name, url
        m = d.match(url)
        assert m.group("host") == host
        assert m.group("port") == port
        assert m.group("db") == db

    assert dialect_for("jdbc:hsqldb:file:/x/sample") is None
    assert dialect_for("") is None


def test_dialect_missing_driver_message(monkeypatch, tmp_path):
    props = tmp_path / "default.properties"
    props.write_text("MY/url=jdbc:mysql://h/db\nMY/user=u\nMY/password=p\n",
                     encoding="utf-8")
    monkeypatch.setenv("SIMPLE_JNDI_PROPERTIES", str(props))
    import builtins
    real_import = builtins.__import__

    def no_pymysql(name, *a, **k):
        if name == "pymysql":
            raise ImportError(name)
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_pymysql)
    result = validate_sql("MY", "SELECT 1", [])
    assert not result["ok"]
    assert "pip install pymysql" in result["error"]


def test_preview_rejects_non_select(tmp_path, monkeypatch):
    props = tmp_path / "default.properties"
    props.write_text("PG/url=jdbc:postgresql://h/d\n", encoding="utf-8")
    monkeypatch.setenv("SIMPLE_JNDI_PROPERTIES", str(props))
    from pentaho_migration.reports.schema_agent import preview_query
    with pytest.raises(RuntimeError, match="only SELECT"):
        preview_query("PG", "DELETE FROM members")


@pytest.mark.skipif(os.environ.get("CSCU_LIVE") != "1",
                    reason="set CSCU_LIVE=1 for the live dataset preview")
def test_live_preview_returns_rows():
    from pentaho_migration.reports.schema_agent import preview_query
    result = preview_query(
        "CSCU", "SELECT br_name FROM cscu_core.branches ORDER BY br_name")
    assert result["columns"] == ["br_name"]
    assert len(result["rows"]) >= 4
    assert not result["truncated"]


def test_postgres_keys_use_pg_catalog_not_information_schema():
    """information_schema.table_constraints is privilege-filtered - a read-only
    report user sees NONE of the constraints. The keys query must use
    pg_catalog so the app (connecting as that user) can read PK/FK."""
    from pentaho_migration.reports.db_dialects import dialect_for
    pg = dialect_for("jdbc:postgresql://h/d")
    assert "pg_constraint" in pg.keys_sql
    # must not READ FROM information_schema (excluding it in a WHERE is fine)
    assert "information_schema.table_constraints" not in pg.keys_sql
    assert "FROM information_schema" not in pg.keys_sql


@pytest.mark.skipif(os.environ.get("CSCU_LIVE") != "1",
                    reason="set CSCU_LIVE=1 for live PK/FK badge introspection")
def test_live_pk_fk_visible_to_report_user():
    """The whole point: probe_schema connects as the app's (read-only) user
    and must still surface PK/FK from pg_catalog."""
    from pentaho_migration.reports.schema_agent import probe_schema
    s = probe_schema("CSCU")
    accounts = next(t for t in s["tables"] if t["name"] == "accounts")
    by_name = {c["name"]: c for c in accounts["columns"]}
    assert by_name["acct_id"]["key"] == "PK"
    assert "FK" in by_name["mbr_id"]["key"]
    assert by_name["mbr_id"]["references"].endswith("members.mbr_id")
