// Test a JDBC connection through the same drivers the reporting engine uses.
//
// Run as a single-file source program with lib/jdbc on the classpath:
//   java -cp "<PRD>/lib/jdbc/*" JdbcProbe.java <url> [driverClass] [user]
// The password comes from the JDBC_PW environment variable, so it never
// appears in the process's command line. Prints one line:
//   OK <database product name>          - connected and the link is valid
//   ERR <ExceptionType>: <message>      - could not connect (the DB's reason)
//
// Called by reports/db_drivers.py test_connection(); the caller reads the
// last stdout line.

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public class JdbcProbe {
    public static void main(String[] args) {
        if (args.length < 1) {
            System.out.println("ERR IllegalArgument: no JDBC url given");
            return;
        }
        String url = args[0];
        String driver = args.length > 1 ? args[1] : "";
        String user = args.length > 2 ? args[2] : "";
        String pw = System.getenv("JDBC_PW");
        if (pw == null) pw = "";

        try {
            // Modern drivers auto-register, but naming one is harmless and
            // gives a clear error when that exact driver is not installed.
            if (!driver.isEmpty()) {
                Class.forName(driver);
            }
            Properties props = new Properties();
            if (!user.isEmpty()) props.setProperty("user", user);
            props.setProperty("password", pw);
            // Fail fast rather than hang on an unreachable host.
            DriverManager.setLoginTimeout(15);
            try (Connection c = DriverManager.getConnection(url, props)) {
                boolean valid = c.isValid(10);
                String name = c.getMetaData().getDatabaseProductName();
                if (valid) {
                    System.out.println("OK " + name);
                } else {
                    System.out.println("ERR InvalidConnection: connected but the "
                                       + "link did not validate");
                }
            }
        } catch (ClassNotFoundException e) {
            System.out.println("ERR DriverNotInstalled: " + e.getMessage());
        } catch (SQLException e) {
            System.out.println("ERR " + e.getClass().getSimpleName() + ": "
                               + e.getMessage());
        } catch (Throwable t) {
            System.out.println("ERR " + t.getClass().getSimpleName() + ": "
                               + t.getMessage());
        }
    }
}
