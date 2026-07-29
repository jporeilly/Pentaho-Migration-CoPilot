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

import hashlib
import urllib.request
from pathlib import Path

from pentaho_migration.reports.environment import find_prd_home

# The mainstream JDBC drivers, fetched from Maven Central. Each is a
# database a converted Crystal report is likely to have come from; PostgreSQL
# and HSQLDB usually ship with Report Designer already, so the installer
# skips whatever is present. Versions are pinned so the SHA-1 published
# beside the jar can be checked - a driver jar is code the engine will run.
_MAVEN = "https://repo1.maven.org/maven2"
INSTALLABLE_DRIVERS = [
    {"database": "MySQL",
     "path": "com/mysql/mysql-connector-j/8.4.0/mysql-connector-j-8.4.0.jar"},
    {"database": "PostgreSQL",
     "path": "org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar"},
    {"database": "Oracle",
     "path": "com/oracle/database/jdbc/ojdbc11/23.5.0.24.07/ojdbc11-23.5.0.24.07.jar"},
    {"database": "SQL Server",
     "path": "com/microsoft/sqlserver/mssql-jdbc/12.8.1.jre11/mssql-jdbc-12.8.1.jre11.jar"},
    {"database": "MariaDB",
     "path": "org/mariadb/jdbc/mariadb-java-client/3.4.1/mariadb-java-client-3.4.1.jar"},
    {"database": "IBM DB2",
     "path": "com/ibm/db2/jcc/11.5.9.0/jcc-11.5.9.0.jar"},
]

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


def _fetch(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "pentaho-migrate"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def install_drivers(prd, only=None, force=False, progress=None,
                    timeout: float = 120.0) -> list:
    """Download the mainstream JDBC drivers into PRD's lib/jdbc.

    A driver already present for a database is left alone unless `force` -
    the point is to fill gaps, not churn versions. Each jar is verified
    against the SHA-1 Maven publishes beside it before it is written, because
    the engine will load and run it. `only` limits to named databases.
    Returns one record per driver: installed / present / skipped / failed."""
    jdbc = Path(prd) / "lib" / "jdbc"
    jdbc.mkdir(parents=True, exist_ok=True)
    present = {d["database"] for d in _scan_jdbc(Path(prd)) if d["recognised"]}
    wanted = {o.lower() for o in only} if only else None
    results = []
    for drv in INSTALLABLE_DRIVERS:
        db = drv["database"]
        jar = drv["path"].rsplit("/", 1)[-1]
        if wanted is not None and db.lower() not in wanted:
            continue
        if db in present and not force:
            results.append({"database": db, "jar": jar, "status": "present"})
            continue
        url = f"{_MAVEN}/{drv['path']}"
        if progress:
            progress(db)
        try:
            data = _fetch(url, timeout)
            published = _fetch(url + ".sha1", timeout).decode().split()[0].strip()
            if hashlib.sha1(data).hexdigest() != published:
                raise ValueError("SHA-1 does not match the published checksum")
            (jdbc / jar).write_bytes(data)
            results.append({"database": db, "jar": jar, "status": "installed",
                            "bytes": len(data)})
        except Exception as exc:                      # network / checksum
            results.append({"database": db, "jar": jar, "status": "failed",
                            "detail": str(exc)})
    return results


# The probe lives beside the other Java helpers the validator runs.
_PROBE = Path(__file__).resolve().parents[3] / "tools" / "JdbcProbe.java"


def test_connection(url: str, driver: str = "", user: str = "",
                    password: str = "", timeout: float = 25.0) -> dict:
    """Actually open the connection, through PRD's own Java and JDBC drivers.

    A JNDI entry can name a driver that is not installed, or a URL that does
    not resolve, and nothing says so until a report render fails deep in the
    engine. This runs a tiny JDBC probe with the same lib/jdbc classpath the
    engine uses and reports {ok, detail} - the database's own error message
    when it cannot connect, not a Java stack trace."""
    import subprocess

    from pentaho_migration.reports.prpt_validator import find_java

    prd = find_prd_home()
    if prd is None:
        return {"ok": False, "detail": "no local Report Designer to borrow "
                                       "Java and the JDBC drivers from"}
    java = find_java(Path(prd))
    if java is None:
        return {"ok": False, "detail": "no Java found under Report Designer"}
    if not _PROBE.is_file():
        return {"ok": False, "detail": f"probe missing: {_PROBE}"}
    cp = str(Path(prd) / "lib" / "jdbc" / "*")
    import os
    env = dict(os.environ, JDBC_PW=password or "")
    try:
        proc = subprocess.run(
            [str(java), "-cp", cp, str(_PROBE), url, driver or "", user or ""],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": f"timed out after {int(timeout)}s"}
    out = (proc.stdout or "").strip().splitlines()
    line = out[-1] if out else (proc.stderr or "").strip()[:200]
    if line.startswith("OK"):
        return {"ok": True, "detail": line[3:].strip() or "connected"}
    return {"ok": False, "detail": line[4:].strip() if line.startswith("ERR ")
            else (line or "connection failed")}


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
