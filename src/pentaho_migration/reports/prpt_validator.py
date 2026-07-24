"""Round-trip validation of generated .prpt bundles through the REAL Pentaho
Reporting engine (tools/PrptValidator.java via the JDK single-file source
launcher — no compile step, no extra dependencies).

This is the reports family's diff harness: "the report opens in PRD" as a
measured fact. Requires a local PRD install and Java (see environment.py);
callers should check `validator_available()` first.
"""

import subprocess
from pathlib import Path

from pydantic import BaseModel

from pentaho_migration.reports.environment import REPO_ROOT, find_java, find_prd_home

VALIDATOR_SOURCE = REPO_ROOT / "tools" / "PrptValidator.java"


class PrptValidation(BaseModel):
    path: str
    ok: bool
    detail: str = ""


def validator_available() -> bool:
    prd = find_prd_home()
    return prd is not None and find_java(prd) is not None


def validate_prpts(paths: list[Path | str], timeout: float = 300.0) -> list[PrptValidation]:
    """Load every bundle with the real engine. Raises RuntimeError when the
    environment lacks PRD or Java — check validator_available() first."""
    prd = find_prd_home()
    java = find_java(prd)
    if prd is None or java is None:
        raise RuntimeError(
            "round-trip validation needs Pentaho Report Designer and Java — "
            "run `pentaho-migrate report-env` for setup hints")

    completed = subprocess.run(
        [str(java), "-cp", str(prd / "lib" / "*"), str(VALIDATOR_SOURCE),
         *[str(Path(p).resolve()) for p in paths]],
        capture_output=True, text=True, timeout=timeout,
    )
    results: list[PrptValidation] = []
    for line in completed.stdout.splitlines():
        if line.startswith("OK "):
            body = line[3:]
            path, _, detail = body.partition(" :: ")
            results.append(PrptValidation(path=path, ok=True, detail=detail))
        elif line.startswith("FAIL "):
            body = line[5:]
            path, _, detail = body.partition(" :: ")
            results.append(PrptValidation(path=path, ok=False, detail=detail))
    if not results:
        raise RuntimeError(
            "validator produced no verdicts - stderr: " + completed.stderr[-800:])
    return results


RENDERER_SOURCE = REPO_ROOT / "tools" / "PrptRenderer.java"


def render_prpt_pdf(prpt_path: Path | str, timeout: float = 300.0) -> bytes:
    """Design-time PDF preview of a .prpt through the real engine: the data
    factory is swapped for an empty table, so layout/labels/bands render
    without any database. Raises RuntimeError when PRD/Java are missing or
    the render fails."""
    import tempfile

    prd = find_prd_home()
    java = find_java(prd)
    if prd is None or java is None:
        raise RuntimeError(
            "PDF preview needs Pentaho Report Designer and Java - "
            "run `pentaho-migrate report-env` for setup hints")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "preview.pdf"
        completed = subprocess.run(
            [str(java), "-cp", str(prd / "lib" / "*"), str(RENDERER_SOURCE),
             str(Path(prpt_path).resolve()), str(out)],
            capture_output=True, text=True, timeout=timeout,
        )
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(
                "PDF preview failed - stderr: " + completed.stderr[-800:])
        return out.read_bytes()
