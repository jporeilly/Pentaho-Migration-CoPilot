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
