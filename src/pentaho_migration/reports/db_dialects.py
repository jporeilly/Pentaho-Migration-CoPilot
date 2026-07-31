"""Database dialect adapters for the schema agent: one entry per mainstream
JDBC URL family, each knowing how to (1) parse its JDBC URL, (2) connect via
a pip-installable Python driver, (3) list tables/columns, and (4) validate a
query without executing it.

PostgreSQL is live-verified against the CSCU demo database; the MySQL,
SQL Server, and Oracle adapters use each vendor's standard mechanisms
(information_schema / INFORMATION_SCHEMA / ALL_TAB_COLUMNS, EXPLAIN /
sp_describe_first_result_set / EXPLAIN PLAN FOR) and report an actionable
"pip install <driver>" message when the driver is absent. A URL no adapter
matches gets an honest "not supported" instead of a guess.
"""

import re


class Dialect:
    def __init__(self, name, url_re, driver_pkg, import_name):
        self.name = name
        self.url_re = url_re
        self.driver_pkg = driver_pkg      # pip package to suggest
        self.import_name = import_name    # module to import

    def match(self, url):
        return self.url_re.match(url or "")

    def _import(self):
        try:
            return __import__(self.import_name)
        except ImportError:
            raise RuntimeError(
                f"{self.name} introspection needs the '{self.driver_pkg}' "
                f"driver - `pip install {self.driver_pkg}`")


class _Postgres(Dialect):
    def __init__(self):
        super().__init__(
            "PostgreSQL",
            re.compile(r"^jdbc:postgresql://(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<db>[^?;]+)"),
            "psycopg2-binary", "psycopg2")

    def connect(self, url, user, password):
        m = self.match(url)
        return self._import().connect(
            host=m.group("host"), port=int(m.group("port") or 5432),
            dbname=m.group("db"), user=user, password=password,
            connect_timeout=5)

    columns_sql = (
        "SELECT table_schema, table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
        "ORDER BY table_schema, table_name, ordinal_position")

    # rows: schema, table, column, PRIMARY KEY|FOREIGN KEY, ref_schema, ref_table, ref_column
    # Uses pg_catalog, not information_schema: information_schema.table_constraints
    # is privilege-filtered (a read-only report user sees NONE of its own
    # constraints), while pg_catalog is visible to every role. Column position
    # is paired via WITH ORDINALITY so composite foreign keys line up.
    keys_sql = (
        "SELECT n.nspname, cl.relname, att.attname, "
        "       CASE con.contype WHEN 'p' THEN 'PRIMARY KEY' ELSE 'FOREIGN KEY' END, "
        "       fn.nspname, fcl.relname, fatt.attname "
        "FROM pg_constraint con "
        "JOIN pg_class cl ON cl.oid = con.conrelid "
        "JOIN pg_namespace n ON n.oid = cl.relnamespace "
        "JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
        "JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.attnum "
        "LEFT JOIN pg_class fcl ON fcl.oid = con.confrelid "
        "LEFT JOIN pg_namespace fn ON fn.oid = fcl.relnamespace "
        "LEFT JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord) "
        "  ON con.contype = 'f' AND fk.ord = k.ord "
        "LEFT JOIN pg_attribute fatt ON fatt.attrelid = con.confrelid AND fatt.attnum = fk.attnum "
        "WHERE con.contype IN ('p', 'f') "
        "  AND n.nspname NOT IN ('pg_catalog', 'information_schema')")

    def validate(self, cursor, sql):
        cursor.execute("EXPLAIN " + sql)


class _MySql(Dialect):
    def __init__(self):
        super().__init__(
            "MySQL",
            re.compile(r"^jdbc:mysql://(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<db>[^?;]+)"),
            "pymysql", "pymysql")

    def connect(self, url, user, password):
        m = self.match(url)
        return self._import().connect(
            host=m.group("host"), port=int(m.group("port") or 3306),
            database=m.group("db"), user=user, password=password,
            connect_timeout=5)

    columns_sql = (
        "SELECT table_schema, table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema = DATABASE() "
        "ORDER BY table_schema, table_name, ordinal_position")

    keys_sql = (
        "SELECT table_schema, table_name, column_name, "
        "       IF(constraint_name = 'PRIMARY', 'PRIMARY KEY', 'FOREIGN KEY'), "
        "       referenced_table_schema, referenced_table_name, referenced_column_name "
        "FROM information_schema.key_column_usage "
        "WHERE table_schema = DATABASE() "
        "  AND (constraint_name = 'PRIMARY' OR referenced_table_name IS NOT NULL)")

    def validate(self, cursor, sql):
        cursor.execute("EXPLAIN " + sql)


class _SqlServer(Dialect):
    def __init__(self):
        # jdbc:sqlserver://host:port;databaseName=db;... (semicolon properties)
        super().__init__(
            "SQL Server",
            re.compile(r"^jdbc:sqlserver://(?P<host>[^:;/]+)(?::(?P<port>\d+))?"
                       r"(?:;.*?databaseName=(?P<db>[^;]+))?", re.IGNORECASE),
            "python-tds", "pytds")

    def connect(self, url, user, password):
        m = self.match(url)
        return self._import().connect(
            server=m.group("host"), port=int(m.group("port") or 1433),
            database=m.group("db") or "master", user=user, password=password,
            login_timeout=5)

    columns_sql = (
        "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION")

    keys_sql = (
        "SELECT tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.COLUMN_NAME, tc.CONSTRAINT_TYPE, "
        "       ccu.TABLE_SCHEMA, ccu.TABLE_NAME, ccu.COLUMN_NAME "
        "FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc "
        "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu "
        "  ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME "
        "LEFT JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc "
        "  ON rc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME "
        "LEFT JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu "
        "  ON ccu.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME "
        "WHERE tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'FOREIGN KEY')")

    def validate(self, cursor, sql):
        # parses + binds the statement without executing it
        cursor.execute("EXEC sp_describe_first_result_set @tsql = %s", (sql,))


class _Oracle(Dialect):
    def __init__(self):
        # jdbc:oracle:thin:@//host:port/service  or  @host:port:sid
        super().__init__(
            "Oracle",
            re.compile(r"^jdbc:oracle:thin:@(?://)?(?P<host>[^:/]+)"
                       r"(?::(?P<port>\d+))?[:/](?P<db>[^?;]+)", re.IGNORECASE),
            "oracledb", "oracledb")

    def connect(self, url, user, password):
        m = self.match(url)
        mod = self._import()
        dsn = f"{m.group('host')}:{m.group('port') or 1521}/{m.group('db')}"
        return mod.connect(user=user, password=password, dsn=dsn)

    columns_sql = (
        "SELECT owner, table_name, column_name, data_type "
        "FROM all_tab_columns "
        "WHERE owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'MDSYS', 'CTXSYS') "
        "ORDER BY owner, table_name, column_id")

    keys_sql = (
        "SELECT c.owner, c.table_name, cc.column_name, "
        "       DECODE(c.constraint_type, 'P', 'PRIMARY KEY', 'FOREIGN KEY'), "
        "       rc.owner, rc.table_name, rcc.column_name "
        "FROM all_constraints c "
        "JOIN all_cons_columns cc ON cc.constraint_name = c.constraint_name "
        "  AND cc.owner = c.owner "
        "LEFT JOIN all_constraints rc ON rc.constraint_name = c.r_constraint_name "
        "  AND rc.owner = c.r_owner "
        "LEFT JOIN all_cons_columns rcc ON rcc.constraint_name = rc.constraint_name "
        "  AND rcc.owner = rc.owner AND rcc.position = cc.position "
        "WHERE c.constraint_type IN ('P', 'R') "
        "  AND c.owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'MDSYS', 'CTXSYS')")

    def validate(self, cursor, sql):
        cursor.execute("EXPLAIN PLAN FOR " + sql)


class _JdbcCursor:
    """DB-API-shaped cursor over the JdbcSchema helper: each execute() is one
    probe run through PRD's own Java, so the agent's cursor-based flow works
    unchanged for any driver in lib/jdbc. Arbitrary statements are limited to
    SELECT/WITH (the preview path); the Java side uses executeQuery with a
    hard row cap, so nothing can mutate the database."""

    def __init__(self, dialect, url, user, password):
        self._d = dialect
        self._args = (url, user, password)
        self._rows = []
        self.description = None

    def execute(self, sql):
        self.description = None
        if sql == _Jdbc.columns_sql:
            self._rows = self._d._run("columns", *self._args, want_cols=4)
        elif sql == _Jdbc.keys_sql:
            self._rows = self._d._run("keys", *self._args, want_cols=7)
        elif re.match(r"(?is)^\s*(SELECT|WITH)\b", sql or ""):
            raw = self._d._run("query", *self._args, want_cols=None, stdin=sql)
            self._rows = []
            for parts in raw:
                if parts and parts[0] == "HDR":
                    self.description = [(name,) for name in parts[1:]]
                elif parts and parts[0] == "ROW":
                    self._rows.append(tuple(parts[1:]))
        else:
            raise RuntimeError(
                "the JDBC adapter runs SELECT queries and metadata probes only")

    def fetchall(self):
        return self._rows

    def fetchmany(self, n):
        return self._rows[:n]

    def close(self):
        pass


class _JdbcConnection:
    def __init__(self, dialect, url, user, password):
        self._cursor = _JdbcCursor(dialect, url, user, password)

    def cursor(self):
        return self._cursor

    def rollback(self):
        pass

    def close(self):
        pass


class _Jdbc(Dialect):
    """Universal fallback: introspect through the SAME JDBC drivers the
    reporting engine uses (tools/JdbcSchema.java run with PRD's own Java and
    lib/jdbc on the classpath). Covers HSQLDB, DB2, MariaDB - anything with a
    driver jar - where no Python adapter exists. Validation prepares the
    statement without executing it; most engines (HSQLDB included) resolve
    tables and columns at prepare time."""

    # sentinels the shim cursor interprets - the agent's flow stays unchanged
    columns_sql = "__JDBC_COLUMNS__"
    keys_sql = "__JDBC_KEYS__"

    def __init__(self):
        super().__init__("JDBC", re.compile(r"^jdbc:(?P<sub>[^:]+):"), "", "")

    def _tooling(self):
        from pathlib import Path

        from pentaho_migration.reports.environment import find_prd_home
        from pentaho_migration.reports.prpt_validator import find_java

        prd = find_prd_home()
        if prd is None:
            raise RuntimeError(
                "JDBC introspection borrows Report Designer's Java and "
                "drivers - no local Report Designer install was found")
        java = find_java(Path(prd))
        if java is None:
            raise RuntimeError("no Java found under Report Designer")
        probe = Path(__file__).resolve().parents[3] / "tools" / "JdbcSchema.java"
        if not probe.is_file():
            raise RuntimeError(f"probe missing: {probe}")
        return java, str(Path(prd) / "lib" / "jdbc" / "*"), probe

    def _run(self, mode, url, user, password, want_cols, stdin=None,
             timeout=60.0):
        import os
        import subprocess

        java, cp, probe = self._tooling()
        env = dict(os.environ, JDBC_PW=password or "")
        proc = subprocess.run(
            [str(java), "-cp", cp, str(probe), mode, url, "", user or ""],
            input=stdin, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=env)
        lines = [l for l in (proc.stdout or "").splitlines() if l.strip()]
        if lines and lines[-1].startswith("ERR "):
            raise RuntimeError(lines[-1][4:])
        rows = []
        for line in lines:
            parts = line.split("\t")
            if want_cols is None or len(parts) == want_cols:
                rows.append(tuple(parts))
        return rows

    def connect(self, url, user, password):
        self._tooling()   # fail fast with the actionable message
        return _JdbcConnection(self, url, user, password)

    def validate(self, cursor, sql):
        out = self._run("validate", *cursor._args, want_cols=1, stdin=sql)
        flat = [r[0] for r in out]
        if "VALID" not in flat:
            raise RuntimeError(flat[-1] if flat else "validation failed")

    def match(self, url):
        m = self.url_re.match(url or "")
        if m:
            self.name = f"JDBC ({m.group('sub')})"
        return m


DIALECTS = [_Postgres(), _MySql(), _SqlServer(), _Oracle(), _Jdbc()]


def dialect_for(url: str):
    """The matching dialect adapter. Native Python adapters first; any other
    jdbc: URL falls back to introspection through PRD's own Java and JDBC
    drivers (HSQLDB, DB2, MariaDB, ...). None only for a non-JDBC URL."""
    for d in DIALECTS:
        if d.match(url):
            return d
    return None
