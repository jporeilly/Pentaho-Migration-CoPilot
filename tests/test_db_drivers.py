"""What databases can a converted report reach - the Settings panel's data.

The value is in recognising a driver jar by name (so the panel can say
"MySQL" not just the filename) and in reading the JNDI connections from the
same properties file Report Designer uses.
"""

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
