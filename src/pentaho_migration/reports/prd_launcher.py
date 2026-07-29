"""Open a converted .prpt directly in the local Pentaho Report Designer.

Same bounds as the Crystal viewer launcher (rpt_viewer.py): this is an HTTP
endpoint that starts a desktop process, so the executable is fixed (the PRD
install's own launcher, discovered the same way the validator finds it), the
bundle is written only into OUR output folder, and the API layer refuses
non-local callers. The bytes are produced server-side by the same conversion
the download button uses - nothing the client sends is executed.
"""

import re
import subprocess
from pathlib import Path

from pentaho_migration.reports.environment import find_prd_home

REPO_ROOT = Path(__file__).resolve().parents[3]
OPEN_DIR = REPO_ROOT / "output" / "prd-open"


def prd_available() -> str:
    """Empty when PRD can launch, else the reason it cannot."""
    prd = find_prd_home()
    if prd is None:
        return ("no local Pentaho Report Designer found - install it at "
                "C:\\Pentaho\\design-tools\\report-designer or set PRD_HOME")
    if not (Path(prd) / "report-designer.bat").is_file():
        return f"report-designer.bat missing under {prd}"
    return ""


def open_in_prd(prpt_bytes: bytes, name: str) -> Path:
    """Write the bundle into output/prd-open/ and launch Report Designer on
    it. Raises RuntimeError with one actionable sentence when PRD is absent."""
    reason = prd_available()
    if reason:
        raise RuntimeError(reason)
    prd = Path(find_prd_home())
    OPEN_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\- ]+", "_", Path(name).stem).strip() or "converted"
    target = OPEN_DIR / f"{safe}.prpt"
    target.write_bytes(prpt_bytes)
    # report-designer.bat launches PRD through `start`, which needs a console.
    # popen_gui_via_batch gives cmd a hidden one; the old detached launch left
    # it with none, so `start` silently no-op'd and PRD never opened. The
    # command list stays fixed - only the bundle path we just wrote varies.
    from pentaho_migration.reports.proc import popen_gui_via_batch
    popen_gui_via_batch(
        ["cmd.exe", "/c", str(prd / "report-designer.bat"), str(target)],
        cwd=str(prd), shell=False)
    return target
