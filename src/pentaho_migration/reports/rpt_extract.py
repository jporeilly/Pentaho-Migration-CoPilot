"""Turn an uploaded .rpt binary into the RptToXml dump the pipeline reads.

The app's Crystal flow starts from a dump, but a customer's file is the .rpt
itself — asking them to run a command-line extractor first is a step that
loses people. So the upload path accepts the binary and runs the same chain
the corpus scripts run, on this machine, per file:

    RptToXml (fork: per-field formats, image bytes, redaction)
      -> credential scrub          (RptToXml copies logons out of the .rpt)
      -> cross-tab recovery        (rpt-rs, when available - optional)

Extraction needs the SAP Crystal .NET runtime + RptToXml.exe (Windows), the
same prerequisites `pentaho-migrate report-env` checks. When they are missing
the caller gets one actionable sentence, not a stack trace.
"""

import os
import subprocess
from pathlib import Path

from pentaho_migration.reports.environment import find_rpttoxml
from pentaho_migration.reports.sanitize import scrub_dump

# every OLE compound file (which is what an .rpt is) starts with this
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

EXTRACT_TIMEOUT = 180.0  # seconds - big subreport-heavy files are slow


def looks_like_rpt(head: bytes) -> bool:
    """True when the bytes open an OLE compound file — the .rpt container.
    (Office binaries share the magic, but nothing else arrives on this
    endpoint; RptToXml itself rejects non-Crystal OLE files cleanly.)"""
    return head.startswith(OLE_MAGIC)


def extraction_available() -> str:
    """Empty string when extraction can run, else the reason it cannot."""
    if find_rpttoxml() is None:
        return ("RptToXml.exe not found - install the free SAP Crystal .NET "
                "runtime and place RptToXml in tools/RptToXml/ (or set "
                "RPTTOXML_PATH); check with `pentaho-migrate report-env`")
    return ""


def extract_rpt(rpt_path: Path, out_xml: Path) -> Path:
    """Extract one .rpt to a scrubbed, enriched dump. Raises RuntimeError with
    an actionable message when the environment or the file is not right."""
    reason = extraction_available()
    if reason:
        raise RuntimeError(reason)
    exe = find_rpttoxml()

    env = dict(os.environ, RPTTOXML_REDACT="1")
    try:
        proc = subprocess.run(
            [str(exe), str(rpt_path), str(out_xml)],
            capture_output=True, text=True, timeout=EXTRACT_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"RptToXml did not finish within {EXTRACT_TIMEOUT:.0f}s - the "
            ".rpt may be corrupt or enormous; extract it manually with "
            "scripts/extract-rpt.ps1")
    if proc.returncode != 0 or not out_xml.exists():
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise RuntimeError(
            "RptToXml could not read this file"
            + (f": {detail[-1][:200]}" if detail else "")
            + " - is it a Crystal Reports .rpt?")

    scrub_dump(out_xml)   # logons RptToXml copies out of the .rpt

    # cross-tab grids live only in the binary; recover them while we have it
    try:
        from pentaho_migration.reports.rpt_crosstabs import enrich_dump, find_rpt_rs
        if find_rpt_rs() is not None:
            enrich_dump(out_xml, rpt_path)
    except Exception:
        pass  # optional enrichment - the dump is complete without it

    return out_xml
