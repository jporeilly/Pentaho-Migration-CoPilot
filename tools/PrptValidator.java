/*
 * Headless .prpt round-trip validator: loads each bundle through the REAL
 * Pentaho Reporting engine (the same code path Report Designer and the
 * Pentaho Server use), so "the generated report opens in PRD" is a measured
 * guarantee, not a hope.
 *
 * Run via the JDK single-file source launcher (no compile step):
 *   java -cp "<report-designer>/lib/*" tools/PrptValidator.java file1.prpt [file2.prpt ...]
 *
 * Output, one line per file:  OK <path> :: <facts>   |   FAIL <path> :: <error>
 * Exit code: 0 when every file loads, 1 otherwise.
 */

import java.io.File;

import org.pentaho.reporting.engine.classic.core.ClassicEngineBoot;
import org.pentaho.reporting.engine.classic.core.MasterReport;
import org.pentaho.reporting.libraries.resourceloader.Resource;
import org.pentaho.reporting.libraries.resourceloader.ResourceManager;

public class PrptValidator {
    public static void main(String[] args) {
        if (args.length == 0) {
            System.err.println("usage: PrptValidator <file.prpt> [more.prpt ...]");
            System.exit(2);
        }
        ClassicEngineBoot.getInstance().start();
        int failures = 0;
        for (String path : args) {
            try {
                ResourceManager manager = new ResourceManager();
                Resource resource = manager.createDirectly(
                        new File(path).getAbsoluteFile(), MasterReport.class);
                MasterReport report = (MasterReport) resource.getResource();
                // touch the parsed model so lazy pieces materialize
                int groups = report.getGroupCount();
                int params = report.getParameterDefinition().getParameterCount();
                String query = String.valueOf(report.getQuery());
                boolean hasDataFactory = report.getDataFactory() != null;
                System.out.println("OK " + path
                        + " :: query=" + query
                        + " groups=" + groups
                        + " parameters=" + params
                        + " dataFactory=" + hasDataFactory);
            } catch (Throwable t) {
                failures++;
                StringBuilder message = new StringBuilder(String.valueOf(t));
                for (Throwable cause = t.getCause(); cause != null; cause = cause.getCause()) {
                    message.append(" <- ").append(cause);
                }
                System.out.println("FAIL " + path + " :: " + message);
            }
        }
        System.exit(failures == 0 ? 0 : 1);
    }
}
