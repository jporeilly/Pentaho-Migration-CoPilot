from pathlib import Path

from pdi_migration.parser.errors import ParseError
from pdi_migration.parser.powercenter import PowerCenterParser
from pdi_migration.parser.talend import TalendParser

__all__ = ["ParseError", "PowerCenterParser", "TalendParser", "detect_parser"]


def detect_parser(path: str | Path):
    """Pick the right parser by sniffing the file, not the extension —
    exports get renamed and mailed around."""
    head = Path(path).read_bytes()[:4096].decode("utf-8", errors="replace")
    if "talendfile:ProcessType" in head or "<talendfile:" in head:
        return TalendParser()
    if "<Report" in head and (".rpt" in head or "RptToXml" in head or "<ReportDefinition" in head):
        raise ParseError(
            "This looks like a Crystal Reports RptToXml dump — a report, not an "
            "ETL pipeline. Use the Reports pipeline instead: POST /reports/convert "
            "or `pdi-migrate report <file>`."
        )
    return PowerCenterParser()
