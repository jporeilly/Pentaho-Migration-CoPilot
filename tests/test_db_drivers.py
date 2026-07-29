"""What databases can a converted report reach - the Settings panel's data.

The value is in recognising a driver jar by name (so the panel can say
"MySQL" not just the filename) and in reading the JNDI connections from the
same properties file Report Designer uses.
"""

import hashlib
import subprocess
from types import SimpleNamespace

from pentaho_migration.reports import db_drivers


class TestDriverIdentification:
    def test_the_mainstream_databases_are_recognised(self):
        cases = {
            "mysql-connector-j-8.4.0.jar": "MySQL",
            "postgresql-42.5.6.jar": "PostgreSQL",
            "ojdbc11-23.5.0.24.07.jar": "Oracle",
            "mssql-jdbc-12.8.1.jre11.jar": "SQL Server",
            "mariadb-java-client-3.4.1.jar": "MariaDB",
            "jcc-11.5.9.0.jar": "IBM DB2",
            "hsqldb-2.3.2.jar": "HSQLDB",
        }
        for jar, expected in cases.items():
            database, driver_class = db_drivers._identify(jar)
            assert database == expected, f"{jar} -> {database}, expected {expected}"
            assert driver_class, f"{jar} has no driver class"

    def test_an_unknown_jar_is_not_guessed(self):
        database, driver_class = db_drivers._identify("some-random-lib-1.0.jar")
        assert database is None and driver_class is None

    def test_mysql_connector_is_not_mistaken_for_mariadb(self):
        # both are MySQL-protocol; the jar name must win cleanly
        assert db_drivers._identify("mysql-connector-j-8.4.0.jar")[0] == "MySQL"
        assert db_drivers._identify("mariadb-java-client-3.4.1.jar")[0] == "MariaDB"


class TestScanningAJdbcDir:
    def test_recognised_and_unrecognised_jars_are_both_listed(self, tmp_path):
        jdbc = tmp_path / "lib" / "jdbc"
        jdbc.mkdir(parents=True)
        (jdbc / "ojdbc11-23.5.0.24.07.jar").write_bytes(b"x")
        (jdbc / "mystery-2.0.jar").write_bytes(b"x")
        found = db_drivers._scan_jdbc(tmp_path)
        by_jar = {d["jar"]: d for d in found}
        assert by_jar["ojdbc11-23.5.0.24.07.jar"]["database"] == "Oracle"
        assert by_jar["ojdbc11-23.5.0.24.07.jar"]["recognised"] is True
        assert by_jar["mystery-2.0.jar"]["recognised"] is False

    def test_a_missing_jdbc_dir_is_empty_not_an_error(self, tmp_path):
        assert db_drivers._scan_jdbc(tmp_path) == []


class TestJndiParsing:
    def test_connections_are_grouped_by_name(self, tmp_path, monkeypatch):
        props = tmp_path / "default.properties"
        props.write_text(
            "# a comment\n"
            "Xtreme/type=javax.sql.DataSource\n"
            "Xtreme/driver=com.mysql.cj.jdbc.Driver\n"
            "Xtreme/url=jdbc:mysql://localhost:3306/xtreme\n"
            "\n"
            "CSCU/driver=org.postgresql.Driver\n"
            "CSCU/url=jdbc:postgresql://host:5433/cscu\n",
            encoding="utf-8")
        monkeypatch.setattr(db_drivers, "_JNDI_PROPERTIES", props)
        conns = {c["name"]: c for c in db_drivers._parse_jndi()}
        assert set(conns) == {"Xtreme", "CSCU"}
        assert conns["Xtreme"]["url"] == "jdbc:mysql://localhost:3306/xtreme"
        assert conns["Xtreme"]["driver"] == "com.mysql.cj.jdbc.Driver"

    def test_no_properties_file_is_empty_not_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db_drivers, "_JNDI_PROPERTIES", tmp_path / "absent.properties")
        assert db_drivers._parse_jndi() == []


def test_scan_shape_is_always_complete(monkeypatch):
    """The endpoint's callers destructure prd/jdbc_dir/drivers/jndi - all
    four keys must exist even with no Report Designer installed."""
    monkeypatch.setattr(db_drivers, "find_prd_home", lambda: None)
    out = db_drivers.scan_db_drivers()
    assert set(out) == {"prd", "jdbc_dir", "drivers", "jndi"}
    assert out["prd"] is None and out["drivers"] == []


def _fake_fetch(jar_bytes):
    """A _fetch stand-in: the .sha1 sibling returns the checksum of whatever
    the jar fetch returned, so the happy path verifies by construction. Pass a
    wrong-length blob for the jar to force a mismatch."""
    def fetch(url, timeout):
        if url.endswith(".sha1"):
            return (hashlib.sha1(jar_bytes).hexdigest() + "  the.jar").encode()
        return jar_bytes
    return fetch


class TestInstallingDrivers:
    def test_a_gap_is_filled_and_the_jar_is_written(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db_drivers, "_fetch", _fake_fetch(b"a real jar"))
        results = db_drivers.install_drivers(tmp_path, only=["MySQL"])
        assert len(results) == 1
        assert results[0]["status"] == "installed"
        jar = tmp_path / "lib" / "jdbc" / results[0]["jar"]
        assert jar.read_bytes() == b"a real jar"

    def test_only_limits_to_the_named_databases(self, tmp_path, monkeypatch):
        monkeypatch.setattr(db_drivers, "_fetch", _fake_fetch(b"x"))
        results = db_drivers.install_drivers(tmp_path, only=["Oracle", "PostgreSQL"])
        assert {r["database"] for r in results} == {"Oracle", "PostgreSQL"}

    def test_a_driver_already_present_is_left_alone(self, tmp_path, monkeypatch):
        jdbc = tmp_path / "lib" / "jdbc"
        jdbc.mkdir(parents=True)
        (jdbc / "mysql-connector-j-8.4.0.jar").write_bytes(b"already here")
        monkeypatch.setattr(db_drivers, "_fetch", _fake_fetch(b"downloaded"))
        results = db_drivers.install_drivers(tmp_path, only=["MySQL"])
        assert results[0]["status"] == "present"
        # the existing jar is untouched, not overwritten with the download
        assert (jdbc / "mysql-connector-j-8.4.0.jar").read_bytes() == b"already here"

    def test_force_reinstalls_over_a_present_driver(self, tmp_path, monkeypatch):
        jdbc = tmp_path / "lib" / "jdbc"
        jdbc.mkdir(parents=True)
        (jdbc / "mysql-connector-j-8.4.0.jar").write_bytes(b"old")
        monkeypatch.setattr(db_drivers, "_fetch", _fake_fetch(b"fresh"))
        results = db_drivers.install_drivers(tmp_path, only=["MySQL"], force=True)
        assert results[0]["status"] == "installed"

    def test_a_bad_checksum_fails_without_writing_the_jar(self, tmp_path, monkeypatch):
        # the .sha1 sibling won't match a jar whose bytes we swap after hashing
        def lying_fetch(url, timeout):
            if url.endswith(".sha1"):
                return (hashlib.sha1(b"expected").hexdigest() + "  x").encode()
            return b"tampered"
        monkeypatch.setattr(db_drivers, "_fetch", lying_fetch)
        results = db_drivers.install_drivers(tmp_path, only=["MySQL"])
        assert results[0]["status"] == "failed"
        assert "SHA-1" in results[0]["detail"]
        assert not list((tmp_path / "lib" / "jdbc").glob("*.jar"))


class TestTestingAConnection:
    def _wire(self, monkeypatch, tmp_path, run):
        """Point test_connection at a fake PRD/Java and a scripted probe run."""
        (tmp_path / "lib" / "jdbc").mkdir(parents=True)
        monkeypatch.setattr(db_drivers, "find_prd_home", lambda: str(tmp_path))
        import pentaho_migration.reports.prpt_validator as validator
        monkeypatch.setattr(validator, "find_java", lambda prd: tmp_path / "java")
        monkeypatch.setattr(subprocess, "run", run)

    def test_a_good_connection_reports_the_product_name(self, tmp_path, monkeypatch):
        self._wire(monkeypatch, tmp_path,
                   lambda *a, **k: SimpleNamespace(stdout="OK MySQL\n", stderr=""))
        assert db_drivers.test_connection("jdbc:mysql://h/db") == {
            "ok": True, "detail": "MySQL"}

    def test_a_refused_connection_reports_the_databases_own_message(self, tmp_path, monkeypatch):
        self._wire(monkeypatch, tmp_path, lambda *a, **k: SimpleNamespace(
            stdout="ERR SQLException: Access denied for user 'x'\n", stderr=""))
        out = db_drivers.test_connection("jdbc:mysql://h/db", user="x")
        assert out["ok"] is False
        assert "Access denied" in out["detail"]

    def test_a_hang_times_out_rather_than_blocking(self, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="java", timeout=25)
        self._wire(monkeypatch, tmp_path, boom)
        out = db_drivers.test_connection("jdbc:mysql://unreachable/db")
        assert out["ok"] is False and "timed out" in out["detail"]

    def test_no_report_designer_is_a_clear_reason_not_a_crash(self, monkeypatch):
        monkeypatch.setattr(db_drivers, "find_prd_home", lambda: None)
        out = db_drivers.test_connection("jdbc:mysql://h/db")
        assert out["ok"] is False and "Report Designer" in out["detail"]
