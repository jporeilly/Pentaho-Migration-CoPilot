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
    keys_sql = (
        "SELECT tc.table_schema, tc.table_name, kcu.column_name, tc.constraint_type, "
        "       ccu.table_schema, ccu.table_name, ccu.column_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON kcu.constraint_name = tc.constraint_name "
        " AND kcu.constraint_schema = tc.constraint_schema "
        "LEFT JOIN information_schema.constraint_column_usage ccu "
        "  ON ccu.constraint_name = tc.constraint_name "
        " AND ccu.constraint_schema = tc.constraint_schema "
        " AND tc.constraint_type = 'FOREIGN KEY' "
        "WHERE tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY') "
        "  AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')")

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


DIALECTS = [_Postgres(), _MySql(), _SqlServer(), _Oracle()]


def dialect_for(url: str):
    """The matching dialect adapter, or None when no adapter covers the URL
    (hsqldb, DB2, Access, ...)."""
    for d in DIALECTS:
        if d.match(url):
            return d
    return None
