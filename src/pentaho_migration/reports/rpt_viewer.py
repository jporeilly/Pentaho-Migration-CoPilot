"""Open a customer's ORIGINAL .rpt in the local Crystal viewer.

The review UI runs on the consultant's own machine, so it can put the original
report on screen next to the converted .prpt — but "an HTTP endpoint that
starts a process" needs tight bounds. Those bounds live here:

* only ONE executable is ever launched (tools/RptViewer/RptViewer.exe), never
  anything named by the caller;
* the argument must be an existing **.rpt** file inside an allowed root
  (the repo's sample folders, or ORIGINAL_RPT_DIRS), resolved and re-checked
  after symlinks;
* the API layer additionally refuses non-local callers.

A dump is matched to its binary by stem: `samples/crystal/corpus/Foo.xml` ->
`samples/crystal/corpus/Foo.rpt`. Authored dumps (samples/cr_demo) have no
binary — the caller is told so plainly instead of getting an error.
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

VIEWER = REPO_ROOT / "tools" / "RptViewer" / "RptViewer.exe"
BUILD_SCRIPT = "tools/RptViewer/build.ps1"


# Uploaded .rpt binaries are kept here (name-sanitized) so the "View original"
# button works for drag-and-dropped files too, not just the samples tree.
UPLOAD_CACHE = REPO_ROOT / "output" / "uploaded-rpt"


def cache_uploaded_rpt(rpt_path: Path) -> Path | None:
    """Keep a copy of an uploaded .rpt inside the viewer's allowed roots.
    Best-effort: a failure only means the button stays absent."""
    import re
    import shutil

    try:
        stem = re.sub(r"[^\w.\- ]+", "_", Path(rpt_path).stem).strip() or "upload"
        UPLOAD_CACHE.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_CACHE / f"{stem}.rpt"
        shutil.copy2(rpt_path, target)
        return target
    except OSError:
        return None


def _allowed_roots() -> list[Path]:
    """Folders a .rpt may be opened from. ORIGINAL_RPT_DIRS (os.pathsep-
    separated) adds the customer's own extraction folder."""
    roots = [REPO_ROOT / "samples", UPLOAD_CACHE]
    for extra in os.environ.get("ORIGINAL_RPT_DIRS", "").split(os.pathsep):
        if extra.strip():
            roots.append(Path(extra.strip()))
    resolved = []
    for root in roots:
        try:
            resolved.append(root.resolve(strict=True))
        except OSError:
            continue
    return resolved


def viewer_available() -> bool:
    return VIEWER.is_file()


def find_original(dump_name: str) -> Path | None:
    """The .rpt that a dump came from, matched by file stem inside the
    allowed roots. None when there is no binary (e.g. authored dumps)."""
    stem = Path(dump_name).stem
    if not stem or stem in (".", ".."):
        return None
    for root in _allowed_roots():
        for candidate in root.rglob(f"{stem}.rpt"):
            if candidate.is_file():
                return candidate
    return None


def _is_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    if resolved.suffix.lower() != ".rpt" or not resolved.is_file():
        return False
    return any(resolved.is_relative_to(root) for root in _allowed_roots())


def open_original(rpt_path: Path) -> None:
    """Launch the viewer on a validated .rpt. Raises ValueError for anything
    outside the allowed roots and RuntimeError when the viewer is not built."""
    if not viewer_available():
        raise RuntimeError(
            "the Crystal viewer is not built - run "
            f"`{BUILD_SCRIPT}` (needs the free SAP Crystal .NET runtime)")
    if not _is_allowed(rpt_path):
        raise ValueError(
            f"refusing to open {rpt_path} - only .rpt files inside the sample "
            "folders (or ORIGINAL_RPT_DIRS) may be opened")
    # Fixed executable, single validated argument, no shell - and DETACHED,
    # so the window survives app restarts (side-by-side demos depend on it).
    from pentaho_migration.reports.proc import popen_detached
    popen_detached([str(VIEWER), str(rpt_path.resolve())], shell=False,
                   cwd=str(REPO_ROOT))


def describe(dump_name: str) -> dict:
    """What the UI needs to decide whether to offer the button, and what to
    say when it cannot."""
    original = find_original(dump_name)
    if not viewer_available():
        return {"available": False, "original": None,
                "reason": f"the Crystal viewer is not built - run {BUILD_SCRIPT}"}
    if original is None:
        return {"available": False, "original": None,
                "reason": "no .rpt binary for this report - authored dumps "
                          "(samples/cr_demo) have no Crystal original; only "
                          "extracted reports can be opened"}
    return {"available": True, "original": str(original), "reason": ""}
