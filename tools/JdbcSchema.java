// Schema introspection through the same JDBC drivers the reporting engine
// uses - the universal fallback for databases with no Python adapter
// (HSQLDB, DB2, MariaDB, ... anything in PRD's lib/jdbc).
//
// Run as a single-file source program with lib/jdbc on the classpath:
//   java -cp "<PRD>/lib/jdbc/*" JdbcSchema.java <mode> <url> [driver] [user]
// The password comes from the JDBC_PW environment variable. Modes:
//   columns   one line per column:  schema TAB table TAB column TAB type
//   keys      one line per key col: schema TAB table TAB column TAB
//             PRIMARY KEY|FOREIGN KEY TAB refschema TAB reftable TAB refcol
//   validate  reads the SQL from stdin, prepares it WITHOUT executing;
//             prints "VALID" or "ERR <message>" - most engines (HSQLDB
//             included) resolve tables/columns at prepare time.
// Called by reports/db_dialects.py (_Jdbc); the caller reads stdout.

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

public class JdbcSchema {
    static String nz(String s) { return s == null ? "" : s; }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.out.println("ERR IllegalArgument: mode and url required");
            return;
        }
        String mode = args[0], url = args[1];
        String driver = args.length > 2 ? args[2] : "";
        String user = args.length > 3 ? args[3] : "";
        String pw = System.getenv("JDBC_PW");
        if (pw == null) pw = "";
        try {
            if (!driver.isEmpty()) Class.forName(driver);
            Properties props = new Properties();
            if (!user.isEmpty()) props.setProperty("user", user);
            props.setProperty("password", pw);
            DriverManager.setLoginTimeout(15);
            try (Connection c = DriverManager.getConnection(url, props)) {
                if (mode.equals("validate")) {
                    StringBuilder sql = new StringBuilder();
                    BufferedReader in = new BufferedReader(
                        new InputStreamReader(System.in, StandardCharsets.UTF_8));
                    String line;
                    while ((line = in.readLine()) != null) sql.append(line).append('\n');
                    try {
                        c.prepareStatement(sql.toString()).close();
                        System.out.println("VALID");
                    } catch (Exception e) {
                        System.out.println("ERR " + nz(e.getMessage()).replace('\n', ' '));
                    }
                    return;
                }
                if (mode.equals("query")) {
                    // First 50-ish rows of a SELECT, for the dataset preview.
                    // executeQuery refuses non-queries; the row cap is hard.
                    StringBuilder sql = new StringBuilder();
                    BufferedReader in = new BufferedReader(
                        new InputStreamReader(System.in, StandardCharsets.UTF_8));
                    String line;
                    while ((line = in.readLine()) != null) sql.append(line).append('\n');
                    try (java.sql.Statement st = c.createStatement()) {
                        st.setMaxRows(200);
                        try (ResultSet rs = st.executeQuery(sql.toString())) {
                            java.sql.ResultSetMetaData rm = rs.getMetaData();
                            int n = rm.getColumnCount();
                            StringBuilder head = new StringBuilder("HDR");
                            for (int i = 1; i <= n; i++)
                                head.append('\t').append(nz(rm.getColumnLabel(i)));
                            System.out.println(head);
                            while (rs.next()) {
                                StringBuilder row = new StringBuilder("ROW");
                                for (int i = 1; i <= n; i++) {
                                    String v = rs.getString(i);
                                    row.append('\t').append(v == null ? "" :
                                        v.replace('\t', ' ').replace('\n', ' ')
                                         .replace('\r', ' '));
                                }
                                System.out.println(row);
                            }
                        }
                    } catch (Exception e) {
                        System.out.println("ERR " + nz(e.getMessage()).replace('\n', ' '));
                    }
                    return;
                }
                DatabaseMetaData md = c.getMetaData();
                if (mode.equals("columns")) {
                    try (ResultSet rs = md.getColumns(null, null, "%", "%")) {
                        while (rs.next()) {
                            String schema = nz(rs.getString("TABLE_SCHEM"));
                            if (schema.startsWith("INFORMATION_SCHEMA")
                                    || schema.startsWith("SYSTEM_")
                                    || schema.equals("SYS")) continue;
                            System.out.println(schema + "\t"
                                + nz(rs.getString("TABLE_NAME")) + "\t"
                                + nz(rs.getString("COLUMN_NAME")) + "\t"
                                + nz(rs.getString("TYPE_NAME")));
                        }
                    }
                    return;
                }
                if (mode.equals("keys")) {
                    List<String[]> tables = new ArrayList<>();
                    try (ResultSet rs = md.getTables(null, null, "%",
                            new String[]{"TABLE"})) {
                        while (rs.next()) {
                            String schema = nz(rs.getString("TABLE_SCHEM"));
                            if (schema.startsWith("INFORMATION_SCHEMA")
                                    || schema.startsWith("SYSTEM_")
                                    || schema.equals("SYS")) continue;
                            tables.add(new String[]{schema, rs.getString("TABLE_NAME")});
                        }
                    }
                    for (String[] t : tables) {
                        try (ResultSet rs = md.getPrimaryKeys(null, t[0], t[1])) {
                            while (rs.next())
                                System.out.println(t[0] + "\t" + t[1] + "\t"
                                    + nz(rs.getString("COLUMN_NAME"))
                                    + "\tPRIMARY KEY\t\t\t");
                        } catch (Exception ignored) { }
                        try (ResultSet rs = md.getImportedKeys(null, t[0], t[1])) {
                            while (rs.next())
                                System.out.println(t[0] + "\t" + t[1] + "\t"
                                    + nz(rs.getString("FKCOLUMN_NAME"))
                                    + "\tFOREIGN KEY\t"
                                    + nz(rs.getString("PKTABLE_SCHEM")) + "\t"
                                    + nz(rs.getString("PKTABLE_NAME")) + "\t"
                                    + nz(rs.getString("PKCOLUMN_NAME")));
                        } catch (Exception ignored) { }
                    }
                    return;
                }
                System.out.println("ERR IllegalArgument: unknown mode " + mode);
            }
        } catch (Exception e) {
            System.out.println("ERR " + e.getClass().getSimpleName() + ": "
                + nz(e.getMessage()).replace('\n', ' '));
        }
    }
}
