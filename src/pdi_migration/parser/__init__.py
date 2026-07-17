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
    return PowerCenterParser()
