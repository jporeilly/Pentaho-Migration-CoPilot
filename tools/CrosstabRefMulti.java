// Multi-dimension variant of CrosstabRef: 2 row dims x 2 column dims x 2
// details, to capture how the engine nests crosstab-row/column-group bodies
// in layout.xml. Run once, inspect, keep for regeneration.
//   java -cp "<prd>/lib/*" tools/CrosstabRefMulti.java <out.prpt> [out.pdf]

package tools;

import java.io.File;

import org.pentaho.reporting.engine.classic.core.ClassicEngineBoot;
import org.pentaho.reporting.engine.classic.core.MasterReport;
import org.pentaho.reporting.engine.classic.core.TableDataFactory;
import org.pentaho.reporting.engine.classic.core.designtime.DesignTimeDataSchemaModel;
import org.pentaho.reporting.engine.classic.core.elementfactory.CrosstabBuilder;
import org.pentaho.reporting.engine.classic.core.elementfactory.CrosstabDetail;
import org.pentaho.reporting.engine.classic.core.function.ItemAvgFunction;
import org.pentaho.reporting.engine.classic.core.function.ItemSumFunction;
import org.pentaho.reporting.engine.classic.core.modules.output.pageable.pdf.PdfReportUtil;
import org.pentaho.reporting.engine.classic.core.util.TypedTableModel;
import org.pentaho.reporting.engine.classic.core.modules.parser.bundle.writer.BundleWriter;

public final class CrosstabRefMulti {
  private CrosstabRefMulti() {
  }

  public static void main(final String[] args) throws Exception {
    ClassicEngineBoot.getInstance().start();

    final TypedTableModel model = new TypedTableModel();
    model.addColumn("REGION", String.class);
    model.addColumn("BR_NAME", String.class);
    model.addColumn("YEAR", String.class);
    model.addColumn("TXN_TYPE", String.class);
    model.addColumn("TXN_AMT", Double.class);
    double v = 10;
    for (final String r : new String[] { "North", "South" }) {
      for (final String b : new String[] { "B1", "B2" }) {
        for (final String y : new String[] { "2025", "2026" }) {
          for (final String t : new String[] { "DEP", "WDL" }) {
            model.addRow(r, b, y, t, v);
            v += 5;
          }
        }
      }
    }

    final MasterReport report = new MasterReport();
    report.setDataFactory(new TableDataFactory("query", model));
    report.setQuery("query");

    final CrosstabBuilder builder =
        new CrosstabBuilder(new DesignTimeDataSchemaModel(report));
    builder.addRowDimension("REGION");
    builder.addRowDimension("BR_NAME");
    builder.addColumnDimension("YEAR");
    builder.addColumnDimension("TXN_TYPE");
    builder.addDetails(new CrosstabDetail("TXN_AMT", "Total", ItemSumFunction.class));
    builder.addDetails(new CrosstabDetail("TXN_AMT", "Avg", ItemAvgFunction.class));
    report.setRootGroup(builder.create());

    BundleWriter.writeReportToZipFile(report, new File(args[0]));
    if (args.length > 1) {
      PdfReportUtil.createPDF(report, new File(args[1]));
    }
    System.out.println("OK");
  }
}
