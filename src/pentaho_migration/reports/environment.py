"""Crystal-migration environment detection: what a fresh install needs.

Four external pieces, each detected here so `pentaho-migrate report-env` (and a
future Settings panel) can tell the user exactly what is missing:

1. Pentaho Report Designer  — supplies the real reporting engine used by the
   round-trip validator (PRD_HOME env or common install paths).
2. Java (JDK 11+)           — runs the validator (Pentaho installs ship one).
3. SAP Crystal .NET runtime — needed by RptToXml to open .rpt files.
   Free download: https://pages.community.sap.com/topics/crystal-reports/visual-studio
   (latest support pack, 64-bit runtime MSI). Detected via the registry keys
   the MSI writes and the GAC assemblies it installs.
4. RptToXml.exe             — dumps .rpt to XML (github.com/ajryan/RptToXml).
   Detected via RPTTOXML_PATH env, tools/RptToXml/, or PATH.
"""

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

PRD_CANDIDATES = [
    r"C:\Pentaho\design-tools\report-designer",
    r"C:\Program Files\Pentaho\design-tools\report-designer",
    "/opt/pentaho/design-tools/report-designer",
]

CRYSTAL_REGISTRY_KEYS = [
    # (hive path, value name) written by the CR for .NET runtime MSI
    (r"SOFTWARE\SAP BusinessObjects\Crystal Reports for .NET Framework 4.0\Crystal Reports",
     "CRRuntime64Version"),
    (r"SOFTWARE\WOW6432Node\SAP BusinessObjects\Crystal Reports for .NET Framework 4.0\Crystal Reports",
     "CRRuntime32Version"),
]


def find_prd_home() -> Path | None:
    env = os.environ.get("PRD_HOME")
    candidates = ([env] if env else []) + PRD_CANDIDATES
    for candidate in candidates:
        path = Path(candidate)
        if path.is_dir() and any(path.glob("lib/classic-core-*.jar")):
            return path
    return None


def find_java(prd_home: Path | None = None) -> Path | None:
    """Prefer the JDK a Pentaho suite install ships (…/Pentaho/java)."""
    exe = "java.exe" if sys.platform == "win32" else "java"
    if prd_home is not None:
        bundled = prd_home.parent.parent / "java" / "bin" / exe
        if bundled.exists():
            return bundled
    java_home = os.environ.get("JAVA_HOME")
    if java_home and (Path(java_home) / "bin" / exe).exists():
        return Path(java_home) / "bin" / exe
    on_path = shutil.which("java")
    return Path(on_path) if on_path else None


def crystal_runtime_version() -> str | None:
    """Version of the installed SAP Crystal .NET runtime, or None."""
    if sys.platform != "win32":
        return None
    import winreg

    for key_path, value_name in CRYSTAL_REGISTRY_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                if value:
                    return str(value)
        except OSError:
            continue
    # fallback: the GAC assemblies the MSI installs
    windir = os.environ.get("WINDIR", r"C:\Windows")
    gac = Path(windir) / "Microsoft.NET" / "assembly" / "GAC_MSIL" / "CrystalDecisions.CrystalReports.Engine"
    if gac.is_dir():
        return "installed (GAC; version key not found)"
    return None


def find_rpttoxml() -> Path | None:
    env = os.environ.get("RPTTOXML_PATH")
    candidates = [env] if env else []
    candidates += [
        str(REPO_ROOT / "tools" / "RptToXml" / "RptToXml.exe"),
        r"C:\Tools\RptToXml\RptToXml.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    on_path = shutil.which("RptToXml")
    return Path(on_path) if on_path else None


def environment_report() -> dict:
    """One dict describing the whole extraction/validation environment —
    the fresh-install preflight."""
    prd = find_prd_home()
    java = find_java(prd)
    runtime = crystal_runtime_version()
    rpttoxml = find_rpttoxml()
    return {
        "prd_home": str(prd) if prd else None,
        "java": str(java) if java else None,
        "crystal_runtime": runtime,
        "rpttoxml": str(rpttoxml) if rpttoxml else None,
        "validator_ready": prd is not None and java is not None,
        "extraction_ready": runtime is not None and rpttoxml is not None,
        "hints": _hints(prd, java, runtime, rpttoxml),
    }


def _hints(prd, java, runtime, rpttoxml) -> list[str]:
    hints = []
    if prd is None:
        hints.append("Install Pentaho Report Designer (or set PRD_HOME) to enable "
                     "round-trip validation of generated .prpt bundles.")
    if java is None:
        hints.append("No Java found — install a JDK 11+ or set JAVA_HOME "
                     "(Pentaho suite installs ship one under <suite>/java).")
    if runtime is None:
        hints.append("SAP Crystal Reports .NET runtime not detected - free download "
                     "(latest support pack, 64-bit runtime MSI): "
                     "https://pages.community.sap.com/topics/crystal-reports/visual-studio")
    if rpttoxml is None:
        hints.append("RptToXml.exe not found - place it in tools/RptToXml/ or set "
                     "RPTTOXML_PATH (binaries: github.com/ajryan/RptToXml/releases).")
    return hints
