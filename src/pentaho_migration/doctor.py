"""The dependency doctor: every moving part of the Copilot, one table.

The product touches a lot of third-party ground - the Pentaho design
tools, the SAP Crystal runtime, local and cloud LLMs, Docker, Airflow,
sample databases. The POLICY (encoded here, enforced by the installer):

  * INSTALL only what we own end to end and can do idempotently and
    licence-free: the venv, the package, the web UI build, JDBC jars
    (SHA-verified gap-fill), the RptViewer build.
  * CHECK AND SAY for licensed or system-level third parties - the
    Pentaho suite, the SAP Crystal runtime, Docker Desktop, Airflow -
    with the exact next action per item. Installing those silently
    would accept licences on the user's behalf; we never do.
  * The app DEGRADES HONESTLY: every check names what stops working
    without it, because most estates need only a subset.

`pentaho-migrate doctor` prints the table; the installer runs it as its
closing step so a fresh box ends with its own readiness report.
"""

import os
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path

OK, WARN, MISSING, INFO = "OK", "WARN", "--", "info"

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Check:
    lane: str          # Core | Pentaho | Crystal | LLM | Airflow | Databases
    name: str
    status: str        # OK | WARN | -- | info
    detail: str        # what was found
    needed_for: str    # what stops working without it
    action: str = ""   # the exact next step when not OK


def _port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        import httpx

        return httpx.get(url, timeout=timeout).status_code < 500
    except Exception:
        return False


def _docker_state() -> tuple[str, str]:
    """(status, detail) for Docker Desktop: distinguish 'not installed'
    from 'installed but not running' - the action differs."""
    exe = shutil.which("docker")
    if not exe:
        return MISSING, "docker CLI not on PATH"
    import subprocess

    try:
        proc = subprocess.run([exe, "info", "--format", "{{.ServerVersion}}"],
                              capture_output=True, text=True, timeout=6)
    except Exception as exc:
        return WARN, f"docker CLI present but not answering ({exc})"
    if proc.returncode == 0 and proc.stdout.strip():
        return OK, f"engine {proc.stdout.strip()}"
    return WARN, "installed but the engine is not running"


def run_doctor() -> list[Check]:
    checks: list[Check] = []

    # ---- Core --------------------------------------------------------
    import sys

    checks.append(Check(
        "Core", "Python", OK,
        f"{sys.version.split()[0]} ({sys.executable})",
        "everything"))
    try:
        import fastapi  # noqa: F401

        checks.append(Check("Core", "API extras", OK, "fastapi installed",
                            "the web app"))
    except ImportError:
        checks.append(Check(
            "Core", "API extras", MISSING, "fastapi not importable",
            "the web app", 'pip install -e ".[api,schema]"'))
    dist = REPO_ROOT / "frontend" / "dist" / "index.html"
    if dist.is_file():
        checks.append(Check("Core", "Web UI", OK, "frontend/dist built",
                            "the browser UI"))
    else:
        node = shutil.which("npm")
        checks.append(Check(
            "Core", "Web UI", MISSING,
            "frontend/dist not built"
            + ("" if node else "; Node.js also missing"),
            "the browser UI (API + CLI work without it)",
            "install Node.js 18+ then: cd frontend && npm ci && npm run build"
            if not node else "cd frontend && npm ci && npm run build"))

    # ---- Pentaho -----------------------------------------------------
    from pentaho_migration.pdi_runner import find_pdi_home
    from pentaho_migration.reports.environment import find_java, find_prd_home

    prd = find_prd_home()
    if prd:
        checks.append(Check("Pentaho", "Report Designer", OK, str(prd),
                            "PDF preview, release gate, engine validation, "
                            "Open in Report Designer"))
        java = find_java(prd)
        checks.append(Check(
            "Pentaho", "Java (bundled)", OK if java else WARN,
            str(java) if java else "no java beside the Pentaho install",
            "every engine render",
            "" if java else "install a JRE 11+ or use the suite's bundled "
                            "java"))
        jdbc = prd / "lib" / "jdbc"
        n = len(list(jdbc.glob("*.jar"))) if jdbc.is_dir() else 0
        checks.append(Check(
            "Pentaho", "JDBC drivers", OK if n else WARN,
            f"{n} driver jar(s) in lib/jdbc",
            "live-database renders and the schema assistant",
            "" if n else "pentaho-migrate report-install-drivers"))
    else:
        checks.append(Check(
            "Pentaho", "Report Designer", MISSING,
            "no install detected (looked at C:\\Pentaho\\design-tools and "
            "PRD_HOME)",
            "PDF preview, release gate, engine validation - conversion "
            "itself still works",
            "install the Pentaho design tools (standard path "
            "C:\\Pentaho\\design-tools\\report-designer) or set PRD_HOME"))
    pdi = find_pdi_home()
    checks.append(Check(
        "Pentaho", "Data Integration", OK if pdi else MISSING,
        str(pdi) if pdi else "no install detected (PDI_HOME or standard "
                             "paths)",
        "the review agent's Pan run and opening .ktr output in Spoon",
        "" if pdi else "install PDI (standard path C:\\Pentaho\\"
                       "design-tools\\data-integration) or set PDI_HOME"))
    server = Path("C:/Pentaho/server/pentaho-server")
    checks.append(Check(
        "Pentaho", "Pentaho Server", OK if server.is_dir() else INFO,
        str(server) if server.is_dir() else "not present",
        "xaction image resolution from webapps; publishing targets",
        "" if server.is_dir() else "optional - only estates with "
                                   "server-hosted images need it"))

    # ---- Crystal -----------------------------------------------------
    from pentaho_migration.reports.environment import (
        crystal_runtime_version, find_rpttoxml)

    runtime = crystal_runtime_version()
    checks.append(Check(
        "Crystal", "SAP Crystal runtime", OK if runtime else MISSING,
        runtime or "not detected",
        ".rpt extraction and the release gate's original render "
        "(dumps and every other family work without it)",
        "" if runtime else "install the free 'SAP Crystal Reports runtime "
        "engine for .NET' (64-bit) from the SAP download page - licence "
        "accepted by you, so never auto-installed"))
    rpttoxml = find_rpttoxml()
    checks.append(Check(
        "Crystal", "RptToXml extractor", OK if rpttoxml else MISSING,
        str(rpttoxml) if rpttoxml else "tools/RptToXml not built",
        "dropping raw .rpt binaries into the app",
        "" if rpttoxml else "build tools/RptToXml (needs the runtime "
                            "above)"))
    viewer = REPO_ROOT / "tools" / "RptViewer" / "RptViewer.exe"
    checks.append(Check(
        "Crystal", "RptViewer", OK if viewer.is_file() else MISSING,
        str(viewer) if viewer.is_file() else "tools/RptViewer not built",
        "the release gate's original render and 'View original'",
        "" if viewer.is_file() else "tools/RptViewer/build.ps1 (needs the "
                                    "runtime above)"))

    # ---- LLM ---------------------------------------------------------
    ollama = _http_ok("http://localhost:11434/api/tags") \
        or bool(shutil.which("ollama"))
    keys = [k for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
            if os.environ.get(k)]
    provider = ""
    try:
        from pentaho_migration.llm.settings import load_settings

        provider = load_settings().provider or ""
    except Exception:
        pass
    checks.append(Check(
        "LLM", "Ollama (local)", OK if ollama else INFO,
        "responding on :11434" if ollama else "not detected",
        "free local expression translation and finding annotation",
        "" if ollama else "optional - winget install Ollama.Ollama, then "
                          "pick a model on the Settings page"))
    checks.append(Check(
        "LLM", "Cloud provider", OK if (keys or provider) else INFO,
        (f"configured: {provider or ', '.join(keys)}"
         if (keys or provider) else "no key configured"),
        "cloud translation/annotation (alternative to Ollama)",
        "" if (keys or provider) else "optional - set a key on the "
                                      "Settings page"))
    if not ollama and not keys and not provider:
        checks.append(Check(
            "LLM", "No provider at all", INFO,
            "deterministic conversion is unaffected",
            "only ✨ translation and finding annotation are off", ""))

    # ---- Airflow lane ------------------------------------------------
    dstatus, ddetail = _docker_state()
    checks.append(Check(
        "Airflow", "Docker Desktop", dstatus, ddetail,
        "the demo-box image, sample databases, and Airflow itself",
        {MISSING: "install Docker Desktop (licence terms apply to larger "
                  "companies - your call, never auto-installed)",
         WARN: "start Docker Desktop, then re-run doctor"}.get(dstatus, "")))
    airflow = _http_ok("http://localhost:8088/health")
    checks.append(Check(
        "Airflow", "Airflow webserver", OK if airflow else INFO,
        "responding on :8088" if airflow else "not detected on :8088",
        "scheduling converted DAGs from the PDI -> Airflow studio",
        "" if airflow else "optional - bring up the PDI-AirFlow lab "
                           "compose (needs Docker running)"))
    marquez = _port_open("localhost", 3000) or _port_open("localhost", 5000)
    checks.append(Check(
        "Airflow", "Marquez lineage", OK if marquez else INFO,
        "responding" if marquez else "not detected on :3000",
        "per-run lineage from scheduled DAGs",
        "" if marquez else "optional - part of the PDI-AirFlow lab "
                           "compose"))

    # ---- Databases ---------------------------------------------------
    hsql = _port_open("localhost", 9001)
    checks.append(Check(
        "Databases", "SampleData HSQLDB", OK if hsql else INFO,
        "server mode on :9001" if hsql else "not running on :9001",
        "live SampleData renders for the Steel Wheels / xaction demos",
        "" if hsql else "start it: C:\\Pentaho\\server\\pentaho-server\\"
                        "data\\hsqldb via start_hypersonic.bat"))
    mysql = _port_open("localhost", 3306) or _port_open("localhost", 3307)
    checks.append(Check(
        "Databases", "MySQL samples", OK if mysql else INFO,
        "responding on 3306/3307" if mysql else "not running",
        "Xtreme / BOE sample schemas for Crystal SQL demos",
        "" if mysql else "optional - docker compose --profile samples up "
                         "(needs Docker running)"))

    return checks


def format_doctor(checks: list[Check]) -> str:
    lines = []
    lane = None
    for c in checks:
        if c.lane != lane:
            lane = c.lane
            lines.append(f"\n{lane}")
    # rebuild with rows under lanes
    lines = []
    lane = None
    for c in checks:
        if c.lane != lane:
            lane = c.lane
            lines.append("")
            lines.append(f"  {lane}:")
        badge = {OK: "[OK]  ", WARN: "[!!]  ", MISSING: "[--]  ",
                 INFO: "[..]  "}[c.status]
        lines.append(f"    {badge}{c.name}: {c.detail}")
        if c.status != OK:
            lines.append(f"           needed for: {c.needed_for}")
            if c.action:
                lines.append(f"           next step:  {c.action}")
    missing = sum(1 for c in checks if c.status == MISSING)
    warns = sum(1 for c in checks if c.status == WARN)
    lines.append("")
    lines.append(f"  {sum(1 for c in checks if c.status == OK)} ready, "
                 f"{warns} warning(s), {missing} missing, "
                 f"{sum(1 for c in checks if c.status == INFO)} optional "
                 "and absent")
    lines.append("  [OK] ready   [!!] present but not usable   "
                 "[--] missing   [..] optional")
    return "\n".join(lines)
