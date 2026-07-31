"""The universal JDBC fallback dialect: schema introspection through PRD's
own Java and lib/jdbc drivers for every URL family with no Python adapter
(HSQLDB, DB2, MariaDB, ...). Native adapters still win for their own URLs.
"""

import pytest

from pentaho_migration.reports.db_dialects import _Jdbc, dialect_for


class TestDialectRouting:
    def test_native_adapters_still_win(self):
        assert dialect_for("jdbc:mysql://h:3306/db").name == "MySQL"
        assert dialect_for("jdbc:postgresql://h:5432/db").name == "PostgreSQL"

    def test_any_other_jdbc_url_gets_the_fallback(self):
        d = dialect_for("jdbc:hsqldb:file:C:/somewhere/sampledata")
        assert isinstance(d, _Jdbc)
        assert d.name == "JDBC (hsqldb)"
        assert isinstance(dialect_for("jdbc:db2://h:50000/x"), _Jdbc)

    def test_a_non_jdbc_url_is_still_unsupported(self):
        assert dialect_for("mongodb://h/db") is None
        assert dialect_for("") is None


class TestShimContract:
    """The agent drives connect() -> cursor().execute(columns_sql) ->
    fetchall(); the shim must honour that contract over the subprocess."""

    def _dialect(self, monkeypatch, rows_by_mode):
        d = _Jdbc()
        monkeypatch.setattr(d, "_tooling", lambda: ("java", "cp", "probe"))
        monkeypatch.setattr(
            d, "_run",
            lambda mode, url, user, pw, want_cols, stdin=None, timeout=60.0:
            rows_by_mode[mode])
        return d

    def test_columns_flow_through_the_cursor(self, monkeypatch):
        d = self._dialect(monkeypatch, {
            "columns": [("PUBLIC", "CUSTOMERS", "CUSTOMERNAME", "VARCHAR")]})
        cur = d.connect("jdbc:hsqldb:mem:x", "u", "p").cursor()
        cur.execute(d.columns_sql)
        assert cur.fetchall() == [("PUBLIC", "CUSTOMERS", "CUSTOMERNAME",
                                   "VARCHAR")]

    def test_validate_raises_the_databases_own_message(self, monkeypatch):
        d = self._dialect(monkeypatch, {"validate": [("ERR user lacks privilege",)]})
        cur = d.connect("jdbc:hsqldb:mem:x", "u", "p").cursor()
        with pytest.raises(RuntimeError):
            d.validate(cur, "SELECT NOPE FROM CUSTOMERS")

    def test_arbitrary_sql_is_refused_by_the_cursor(self, monkeypatch):
        d = self._dialect(monkeypatch, {"columns": []})
        cur = d.connect("jdbc:hsqldb:mem:x", "u", "p").cursor()
        with pytest.raises(RuntimeError):
            cur.execute("DROP TABLE CUSTOMERS")
