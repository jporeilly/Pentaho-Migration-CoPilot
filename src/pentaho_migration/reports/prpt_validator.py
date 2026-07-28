"""Round-trip validation of generated .prpt bundles through the REAL Pentaho
Reporting engine (tools/PrptValidator.java via the JDK single-file source
launcher — no compile step, no extra dependencies).

This is the reports family's diff harness: "the report opens in PRD" as a
measured fact. Requires a local PRD install and Java (see environment.py);
callers should check `validator_available()` first.
"""

import subprocess

from pentaho_migration.reports.proc import run_nice
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

    completed = run_nice(
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
DATA_RENDERER_SOURCE = REPO_ROOT / "tools" / "PrptDataRender.java"


def render_prpt_pdf_live(prpt_path: Path | str, timeout: float = 300.0) -> bytes:
    """Render a .prpt WITH its own JNDI datasource (real rows from the live
    database) - the parity harness's side of the comparison. Needs PRD, Java,
    the JDBC driver, and a reachable database."""
    import tempfile

    prd = find_prd_home()
    java = find_java(prd)
    if prd is None or java is None:
        raise RuntimeError(
            "live rendering needs Pentaho Report Designer and Java - "
            "run `pentaho-migrate report-env` for setup hints")
    cp = ";".join([str(prd / "lib" / "*"), str(prd / "lib" / "jdbc" / "*"),
                   str(prd / "resources")])
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "live.pdf"
        completed = run_nice(
            [str(java), "-cp", cp, str(DATA_RENDERER_SOURCE),
             str(Path(prpt_path).resolve()), str(out)],
            capture_output=True, text=True, timeout=timeout,
        )
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(_render_failure(prpt_path, completed.stderr))
        return out.read_bytes()


def _render_failure(prpt_path, stderr: str) -> str:
    """Turn the engine's stack trace into one sentence a consultant can act
    on. The common case is a report the conversion got RIGHT: Crystal
    prompted for parameters, so PRD prompts too, and a headless render has
    nobody to ask - which arrives as a wall of Java unless it is named."""
    stderr = stderr or ""
    if "ReportParameterValidationException" in stderr:
        names = _mandatory_parameters(prpt_path)
        listed = ", ".join(names) if names else "its prompts"
        return (f"the report prompts for {listed} - Crystal asked for these "
                "too, so a headless render has no values to use; open it in "
                "Report Designer and supply them, or give the parameters "
                "default values")
    return "live render failed - stderr: " + stderr[-800:]


def _mandatory_parameters(prpt_path) -> list:
    """Names of parameters the bundle marks mandatory with no default."""
    import zipfile
    from xml.etree import ElementTree as ET

    try:
        with zipfile.ZipFile(prpt_path) as z:
            root = ET.fromstring(z.read("datadefinition.xml"))
    except Exception:
        return []
    out = []
    for node in root.iter():
        if not node.tag.split("}")[-1].endswith("parameter"):
            continue
        if node.get("mandatory") == "true" and not node.get("default-value"):
            name = node.get("name")
            if name:
                out.append(name)
    return out


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
        completed = run_nice(
            [str(java), "-cp", str(prd / "lib" / "*"), str(RENDERER_SOURCE),
             str(Path(prpt_path).resolve()), str(out)],
            capture_output=True, text=True, timeout=timeout,
        )
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(
                "PDF preview failed - stderr: " + completed.stderr[-800:])
        return out.read_bytes()
