// RptViewer - open a Crystal Reports .rpt and look at it, using only the free
// SAP Crystal .NET RUNTIME (no designer, no Visual Studio integration, no
// Crystal Reports licence). The runtime MSIs put CrystalDecisions.Windows.Forms
// (the CrystalReportViewer control) in the GAC; this is a thin host around it.
//
// Why it exists: during a migration you want the ORIGINAL report on screen next
// to the converted .prpt. Nothing in the conversion pipeline needs this — it is
// purely for review and customer demos.
//
//   RptViewer.exe                          file-open dialog
//   RptViewer.exe report.rpt               view it
//   RptViewer.exe report.rpt --export out.pdf     headless export, no window
//   RptViewer.exe report.rpt --server S --db D --user U --password P
//
// A report saved WITH data renders immediately. One saved without data needs
// its database — supply credentials, or you get a plain message saying so
// rather than a raw Crystal logon exception.

using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

using CrystalDecisions.CrystalReports.Engine;
using CrystalDecisions.Shared;

namespace RptViewer
{
    internal static class Program
    {
        private sealed class Options
        {
            public string Path;
            public string Export;
            public string Server, Database, User, Password;
            public bool HasCredentials =>
                !string.IsNullOrEmpty(Server) || !string.IsNullOrEmpty(User);
        }

        [STAThread]
        private static int Main(string[] args)
        {
            var o = Parse(args);
            if (o == null) { Console.WriteLine(Usage); return 2; }

            if (string.IsNullOrEmpty(o.Path))
            {
                Application.EnableVisualStyles();
                using (var dlg = new OpenFileDialog
                {
                    Filter = "Crystal Reports (*.rpt)|*.rpt|All files (*.*)|*.*",
                    Title = "Open a Crystal report",
                })
                {
                    if (dlg.ShowDialog() != DialogResult.OK) return 0;
                    o.Path = dlg.FileName;
                }
            }
            if (!File.Exists(o.Path))
            {
                Console.WriteLine("not found: " + o.Path);
                return 2;
            }

            var doc = new ReportDocument();
            try
            {
                doc.Load(o.Path, OpenReportMethod.OpenReportByTempCopy);
            }
            catch (Exception ex)
            {
                Console.WriteLine("could not open the report: " + Flatten(ex));
                return 1;
            }

            if (o.HasCredentials) ApplyCredentials(doc, o);

            if (!string.IsNullOrEmpty(o.Export)) return Export(doc, o.Export);

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new ViewerForm(doc, o.Path));
            return 0;
        }

        private const string Usage =
            "RptViewer - view a Crystal Reports .rpt with the free SAP runtime\n\n" +
            "  RptViewer.exe [report.rpt] [--export out.pdf]\n" +
            "                [--server S --db D --user U --password P]\n\n" +
            "  no arguments      open a file dialog\n" +
            "  --export PATH     write PDF and exit (no window)\n" +
            "  credentials       only needed when the report was saved without data\n";

        private static Options Parse(string[] args)
        {
            var o = new Options();
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                bool last = i == args.Length - 1;
                switch (a)
                {
                    case "-h": case "--help": case "/?": return null;
                    case "--export": if (last) return null; o.Export = args[++i]; break;
                    case "--server": if (last) return null; o.Server = args[++i]; break;
                    case "--db": case "--database": if (last) return null; o.Database = args[++i]; break;
                    case "--user": if (last) return null; o.User = args[++i]; break;
                    case "--password": if (last) return null; o.Password = args[++i]; break;
                    default:
                        if (a.StartsWith("-")) return null;
                        if (o.Path != null) return null;
                        o.Path = a;
                        break;
                }
            }
            return o;
        }

        /// Apply the same logon to every table in the report and its subreports.
        private static void ApplyCredentials(ReportDocument doc, Options o)
        {
            var logon = new TableLogOnInfo();
            Action<Tables> apply = tables =>
            {
                foreach (Table table in tables)
                {
                    logon = table.LogOnInfo;
                    if (!string.IsNullOrEmpty(o.Server)) logon.ConnectionInfo.ServerName = o.Server;
                    if (!string.IsNullOrEmpty(o.Database)) logon.ConnectionInfo.DatabaseName = o.Database;
                    if (!string.IsNullOrEmpty(o.User)) logon.ConnectionInfo.UserID = o.User;
                    if (!string.IsNullOrEmpty(o.Password)) logon.ConnectionInfo.Password = o.Password;
                    table.ApplyLogOnInfo(logon);
                }
            };
            apply(doc.Database.Tables);
            foreach (ReportDocument sub in doc.Subreports) apply(sub.Database.Tables);
        }

        private static int Export(ReportDocument doc, string target)
        {
            try
            {
                doc.ExportToDisk(ExportFormatType.PortableDocFormat, target);
                Console.WriteLine("wrote " + target);
                return 0;
            }
            catch (Exception ex)
            {
                Console.WriteLine("export failed: " + Explain(ex));
                return 1;
            }
        }

        /// Crystal wraps the real cause several layers deep; surface all of it.
        internal static string Flatten(Exception ex)
        {
            string text = ex.Message;
            for (var inner = ex.InnerException; inner != null; inner = inner.InnerException)
                text += " -> " + inner.Message;
            return text;
        }

        /// Turn the usual "logon failed" wall of text into one actionable line.
        internal static string Explain(Exception ex)
        {
            string text = Flatten(ex);
            if (text.IndexOf("logon", StringComparison.OrdinalIgnoreCase) >= 0 ||
                text.IndexOf("database", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return text + "\n\nThis report was saved WITHOUT data, so it needs its "
                     + "database to render. Pass --server/--db/--user/--password, or open "
                     + "a copy that was saved with data.";
            }
            return text;
        }
    }

    internal sealed class ViewerForm : Form
    {
        internal ViewerForm(ReportDocument doc, string path)
        {
            Text = "RptViewer - " + Path.GetFileName(path);
            Width = 1100;
            Height = 800;
            StartPosition = FormStartPosition.CenterScreen;

            // Launched from the review app's web server, the window opens
            // BEHIND the browser (Windows denies foreground to background
            // processes). The TopMost flash is the sanctioned workaround:
            // the window comes to the front once, then behaves normally.
            Shown += (s, e) =>
            {
                TopMost = true;
                Activate();
                TopMost = false;
            };

            var viewer = new CrystalDecisions.Windows.Forms.CrystalReportViewer
            {
                Dock = DockStyle.Fill,
                ShowCloseButton = false,
                ShowGroupTreeButton = true,
                ToolPanelView = CrystalDecisions.Windows.Forms.ToolPanelViewType.GroupTree,
            };
            Controls.Add(viewer);

            try
            {
                viewer.ReportSource = doc;
            }
            catch (Exception ex)
            {
                Controls.Remove(viewer);
                Controls.Add(new Label
                {
                    Dock = DockStyle.Fill,
                    Padding = new Padding(24),
                    Font = new Font(FontFamily.GenericSansSerif, 10),
                    Text = "Could not render this report.\n\n" + Program.Explain(ex),
                });
            }
        }
    }
}
