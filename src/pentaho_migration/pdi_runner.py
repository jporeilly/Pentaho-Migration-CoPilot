"""Execute generated artifacts in a real PDI installation via pan/kitchen.

Closes the validation loop: a .ktr that runs (or fails) under Pan is ground
truth, not a prediction. PDI_HOME is discovered automatically from common
install locations or the PDI_HOME environment variable.
"""

import os
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel

COMMON_PDI_PATHS = (
    r"C:\Pentaho\design-tools\data-integration",
    r"C:\pentaho\data-integration",
    r"C:\pdi\data-integration",
    r"C:\Program Files\Pentaho\data-integration",
    "/opt/pentaho/data-integration",
)

# Pan/Kitchen exit codes, per Pentaho documentation.
EXIT_CODES = {
    0: "success",
    1: "errors during processing",
    2: "unexpected error during loading/running",
    3: "unable to prepare/initialize",
    7: "couldn't load from XML or repository",
    8: "error loading steps/plugins",
    9: "command-line usage error",
}


class RunResult(BaseModel):
    ok: bool
    exit_code: int
    meaning: str
    command: str
    log_tail: str


def find_pdi_home() -> Path | None:
    candidates = [os.environ.get("PDI_HOME", "")] + list(COMMON_PDI_PATHS)
    for candidate in candidates:
        if candidate and (Path(candidate) / "Spoon.bat").exists():
            return Path(candidate)
        if candidate and (Path(candidate) / "spoon.sh").exists():
            return Path(candidate)
    return None


def _tool(pdi_home: Path, name: str) -> Path:
    windows = (pdi_home / f"{name.capitalize()}.bat")
    return windows if windows.exists() else pdi_home / f"{name}.sh"


def run_artifact(path: str | Path, pdi_home: Path | None = None, timeout: int = 600) -> RunResult:
    """Run a .ktr through Pan or a .kjb through Kitchen; returns the verdict
    with the log tail (last lines carry the errors that matter)."""
    path = Path(path).resolve()
    pdi_home = pdi_home or find_pdi_home()
    if pdi_home is None:
        raise FileNotFoundError(
            "No PDI installation found — set PDI_HOME or install to a standard location."
        )
    tool = _tool(pdi_home, "pan" if path.suffix.lower() == ".ktr" else "kitchen")
    command = [str(tool), f"/file:{path}", "/level:Minimal"]
    # Pan/Kitchen .bat files invoke Spoon.bat by bare name; Windows may not
    # resolve batch files from the working directory, so put PDI on PATH.
    env = {**os.environ, "PATH": f"{pdi_home}{os.pathsep}{os.environ.get('PATH', '')}"}
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, cwd=pdi_home, env=env,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    tail = "\n".join(output.strip().splitlines()[-25:])
    # Windows .bat wrappers don't always propagate Java's exit code — trust the
    # log over a zero exit when PDI itself reports failure.
    log_failed = bool(re.search(r"Finished with errors|A serious error occurred", output))
    ok = completed.returncode == 0 and not log_failed
    meaning = EXIT_CODES.get(completed.returncode, "unknown exit code")
    if completed.returncode == 0 and log_failed:
        meaning = "exit 0 but the log reports errors (bat wrapper swallowed the exit code)"
    return RunResult(
        ok=ok,
        exit_code=completed.returncode,
        meaning=meaning,
        command=" ".join(command),
        log_tail=tail,
    )
