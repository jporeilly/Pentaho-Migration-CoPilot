import java.io.File;
import java.io.FileOutputStream;
import org.pentaho.reporting.engine.classic.core.ClassicEngineBoot;
import org.pentaho.reporting.engine.classic.core.MasterReport;
import org.pentaho.reporting.engine.classic.core.modules.output.pageable.pdf.PdfReportUtil;
import org.pentaho.reporting.libraries.resourceloader.Resource;
import org.pentaho.reporting.libraries.resourceloader.ResourceManager;

public class PrptDataRender {
    public static void main(String[] args) throws Exception {
        ClassicEngineBoot.getInstance().start();
        ResourceManager m = new ResourceManager();
        Resource r = m.createDirectly(new File(args[0]).getAbsoluteFile(), MasterReport.class);
        MasterReport report = (MasterReport) r.getResource();
        try (FileOutputStream out = new FileOutputStream(args[1])) {
            PdfReportUtil.createPDF(report, out);
        }
        System.out.println("OK");
    }
}
