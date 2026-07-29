"""What databases can a converted report actually reach?

A .prpt references a JNDI datasource by name; whether it connects at render
time depends on two things being present on the machine running Report
Designer or the Pentaho Server:

  * the JDBC DRIVER jar for that database, in PRD's `lib/jdbc`, and
  * a JNDI entry naming the connection, in the simple-jndi properties.

Both are invisible until something fails, so the Settings page surfaces
them: which drivers are installed, and which datasource names are wired.
Read-only - this reports the environment, it does not change it.
"""

from pathlib import Path

from pentaho_migration.reports.environment import find_prd_home

# Match a driver jar to its database by the jar's name, and name the JDBC
# driver class a JNDI entry would use. Ordered longest-hint-first so
# "mysql-connector" is tried before a bare "mysql" substring elsewhere.
_DRIVER_HINTS = [
    ("mariadb", "MariaDB", "org.mariadb.jdbc.Driver"),
    ("mysql", "MySQL", "com.mysql.cj.jdbc.Driver"),
    ("postgresql", "PostgreSQL", "org.postgresql.Driver"),
    ("hsqldb", "HSQLDB", "org.hsqldb.jdbcDriver"),
    ("h2", "H2", "org.h2.Driver"),
    ("ojdbc", "Oracle", "oracle.jdbc.OracleDriver"),
    ("oracle", "Oracle", "oracle.jdbc.OracleDriver"),
    ("mssql", "SQL Server", "com.microsoft.sqlserver.jdbc.SQLServerDriver"),
    ("sqljdbc", "SQL Server", "com.microsoft.sqlserver.jdbc.SQLServerDriver"),
    ("sqlserver", "SQL Server", "com.microsoft.sqlserver.jdbc.SQLServerDriver"),
    ("db2", "IBM DB2", "com.ibm.db2.jcc.DB2Driver"),
    ("jcc", "IBM DB2", "com.ibm.db2.jcc.DB2Driver"),
    ("sqlite", "SQLite", "org.sqlite.JDBC"),
    ("snowflake", "Snowflake", "net.snowflake.client.jdbc.SnowflakeDriver"),
    ("vertica", "Vertica", "com.vertica.jdbc.Driver"),
]

# Where PRD resolves JNDI names at design time (the file we register demo
# datasources in). PRD also ships template copies; this is the live one.
_JNDI_PROPERTIES = Path.home() / ".pentaho" / "simple-jndi" / "default.properties"


def _identify(jar_name: str):
    low = jar_name.lower()
    for hint, database, driver_class in _DRIVER_HINTS:
        if hint in low:
            return database, driver_class
    return None, None


def _scan_jdbc(prd: Path) -> list:
    jdbc = prd / "lib" / "jdbc"
    if not jdbc.is_dir():
        return []
    out = []
    for jar in sorted(jdbc.glob("*.jar")):
        database, driver_class = _identify(jar.name)
        out.append({
            "jar": jar.name,
            "database": database or "unknown",
            "driver_class": driver_class or "",
            "recognised": database is not None,
        })
    return out


def _parse_jndi() -> list:
    """simple-jndi default.properties -> [{name, driver, url}]. The file uses
    `Name/key=value` lines, so entries are grouped by the prefix."""
    if not _JNDI_PROPERTIES.is_file():
        return []
    entries: dict = {}
    for line in _JNDI_PROPERTIES.read_text(encoding="utf-8",
                                           errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "/" not in line or "=" not in line:
            continue
        left, value = line.split("=", 1)
        name, _, key = left.partition("/")
        if not key:
            continue
        entries.setdefault(name.strip(), {})[key.strip()] = value.strip()
    out = []
    for name, kv in entries.items():
        out.append({"name": name,
                    "driver": kv.get("driver", ""),
                    "url": kv.get("url", "")})
    return sorted(out, key=lambda e: e["name"].lower())


def scan_db_drivers() -> dict:
    """{'prd', 'jdbc_dir', 'drivers', 'jndi'} - what databases a converted
    report can reach on this machine. `prd` is None when no Report Designer
    is installed, and both lists come back empty."""
    prd = find_prd_home()
    if prd is None:
        return {"prd": None, "jdbc_dir": "", "drivers": [], "jndi": _parse_jndi()}
    prd = Path(prd)
    return {
        "prd": str(prd),
        "jdbc_dir": str(prd / "lib" / "jdbc"),
        "drivers": _scan_jdbc(prd),
        "jndi": _parse_jndi(),
    }
