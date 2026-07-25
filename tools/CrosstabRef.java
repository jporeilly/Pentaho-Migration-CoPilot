// Build a reference crosstab .prpt through the REAL Pentaho Reporting engine's
// CrosstabBuilder, write it with the bundle writer, and render it to PDF.
// The produced bundle is the authoritative layout.xml shape our prpt_writer
// must emit for Crystal cross-tab conversions.
//
// Run (JDK single-file launcher, same pattern as PrptValidator.java):
//   java -cp "<prd>/lib/*" tools/CrosstabRef.java <out.prpt> [out.pdf]
//
// Exit codes: 0 = written (+rendered), 1 = failure.

package tools;

import java.io.File;

import org.pentaho.reporting.engine.classic.core.ClassicEngineBoot;
import org.pentaho.reporting.engine.classic.core.MasterReport;
import org.pentaho.reporting.engine.classic.core.TableDataFactory;
import org.pentaho.reporting.engine.classic.core.designtime.DesignTimeDataSchemaModel;
import org.pentaho.reporting.engine.classic.core.elementfactory.CrosstabBuilder;
import org.pentaho.reporting.engine.classic.core.elementfactory.CrosstabDetail;
import org.pentaho.reporting.engine.classic.core.function.AggregationFunction;
import org.pentaho.reporting.engine.classic.core.function.ItemSumFunction;
import org.pentaho.reporting.engine.classic.core.modules.output.pageable.pdf.PdfReportUtil;
import org.pentaho.reporting.engine.classic.core.util.TypedTableModel;
import org.pentaho.reporting.libraries.docbundle.WriteableDocumentBundle;
import org.pentaho.reporting.engine.classic.core.modules.parser.bundle.writer.BundleWriter;

public final class CrosstabRef {
  private CrosstabRef() {
  }

  public static void main(final String[] args) throws Exception {
    if (args.length < 1) {
      System.err.println("usage: CrosstabRef <out.prpt> [out.pdf]");
      System.exit(1);
    }
    ClassicEngineBoot.getInstance().start();

    // Synthetic data shaped like a Crystal cross-tab source: row dim, column
    // dim, measure.
    final TypedTableModel model = new TypedTableModel();
    model.addColumn("BR_NAME", String.class);
    model.addColumn("TXN_TYPE", String.class);
    model.addColumn("TXN_AMT", Double.class);
    final String[] branches = { "Camelback", "Mesa", "Tempe" };
    final String[] types = { "DEPOSIT", "WITHDRAWAL" };
    double v = 100;
    for (final String b : branches) {
      for (final String t : types) {
        // two rows per combination so the cell must AGGREGATE (2v), not echo
        model.addRow(b, t, v);
        model.addRow(b, t, v);
        v += 25;
      }
    }

    final MasterReport report = new MasterReport();
    report.setDataFactory(new TableDataFactory("query", model));
    report.setQuery("query");

    // Optional 3rd arg: aggregation class simple name (ItemSumFunction,
    // ItemCountFunction, ItemAvgFunction, ItemMaxFunction, ItemMinFunction) —
    // used to discover the wizard:aggregation-type strings the engine writes.
    Class<? extends AggregationFunction> agg = ItemSumFunction.class;
    if (args.length > 2) {
      agg = Class.forName("org.pentaho.reporting.engine.classic.core.function." + args[2])
          .asSubclass(AggregationFunction.class);
    }

    final CrosstabBuilder builder =
        new CrosstabBuilder(new DesignTimeDataSchemaModel(report));
    builder.addRowDimension("BR_NAME");
    builder.addColumnDimension("TXN_TYPE");
    builder.addDetails(new CrosstabDetail("TXN_AMT", "Amount", agg));
    report.setRootGroup(builder.create());

    final File out = new File(args[0]);
    BundleWriter.writeReportToZipFile(report, out);
    System.out.println("WROTE " + out.getAbsolutePath());

    if (args.length > 1) {
      PdfReportUtil.createPDF(report, new File(args[1]));
      System.out.println("RENDERED " + args[1]);
    }
    System.out.println("OK");
  }
}
