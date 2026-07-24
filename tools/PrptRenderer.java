/*
 * Headless .prpt -> PDF layout preview via the REAL Pentaho Reporting engine.
 *
 * The report's data factory is swapped for an empty table with the same query
 * name, so the render needs no database: page setup, headers/footers, labels,
 * group scaffolding and band layout all render exactly as Report Designer
 * would show them — detail rows are simply empty. A design-time preview,
 * not a data render.
 *
 * Run via the JDK single-file source launcher:
 *   java -cp "<report-designer>/lib/*" tools/PrptRenderer.java in.prpt out.pdf
 */

import java.io.File;
import java.io.FileOutputStream;

import org.pentaho.reporting.engine.classic.core.ClassicEngineBoot;
import org.pentaho.reporting.engine.classic.core.MasterReport;
import org.pentaho.reporting.engine.classic.core.TableDataFactory;
import org.pentaho.reporting.engine.classic.core.modules.output.pageable.pdf.PdfReportUtil;
import org.pentaho.reporting.libraries.resourceloader.Resource;
import org.pentaho.reporting.libraries.resourceloader.ResourceManager;

import javax.swing.table.DefaultTableModel;

public class PrptRenderer {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: PrptRenderer <in.prpt> <out.pdf>");
            System.exit(2);
        }
        ClassicEngineBoot.getInstance().start();
        ResourceManager manager = new ResourceManager();
        Resource resource = manager.createDirectly(
                new File(args[0]).getAbsoluteFile(), MasterReport.class);
        MasterReport report = (MasterReport) resource.getResource();

        String query = report.getQuery() == null ? "default" : report.getQuery();
        report.setDataFactory(new TableDataFactory(query, new DefaultTableModel()));

        try (FileOutputStream out = new FileOutputStream(args[1])) {
            PdfReportUtil.createPDF(report, out);
        }
        System.out.println("OK " + args[1]);
    }
}
