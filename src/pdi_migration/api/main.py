"""FastAPI layer — a thin wrapper over the core package.

Run with:  uvicorn pdi_migration.api.main:app --reload
Requires the [api] extra:  pip install -e ".[api]"

Serves the Phase 0 review UI at / and the API under /parse, /convert.
Interactive API docs at /docs.
"""

import json
import tempfile
import threading
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from pdi_migration import __version__
from pdi_migration.generator import KtrGenerator
from pdi_migration.ir import Pipeline, SourceInfo
from pdi_migration.llm import (
    ExpressionTranslator,
    LLMSettings,
    TranslationError,
    load_settings,
    save_settings,
)
from pdi_migration.llm.detect import DetectionReport, detection_report
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
from pdi_migration.parser.powercenter import PowerCenterParseError
from pdi_migration.sandbox import SandboxKit, build_sandbox_kit
from pdi_migration.validator import (
    ImpactAnalysis,
    MigrationReport,
    MigrationScore,
    assess_source,
    build_impact_analysis,
    build_report,
    build_score,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
UI_DIST = REPO_ROOT / "frontend" / "dist"
SAMPLE_FILE = REPO_ROOT / "samples" / "m_load_sales.xml"

app = FastAPI(title="Migration Copilot", version=__version__)


class ConversionResult(BaseModel):
    pipeline: Pipeline
    report: MigrationReport
    ktr: str
    impact: ImpactAnalysis
    score: MigrationScore


def _build_result(pipeline: Pipeline, generator: KtrGenerator) -> "ConversionResult":
    impact = build_impact_analysis(pipeline)
    return ConversionResult(
        pipeline=pipeline,
        report=build_report(pipeline),
        ktr=generator.generate(pipeline),
        impact=impact,
        score=build_score(pipeline, impact),
    )


class ConversionResponse(BaseModel):
    source: SourceInfo
    results: list[ConversionResult]


@app.get("/sample", include_in_schema=False)
def sample() -> FileResponse:
    """The bundled demo export, used by the UI's 'Try the sample' button."""
    return FileResponse(SAMPLE_FILE, media_type="text/xml")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/changelog", response_class=PlainTextResponse)
def changelog() -> str:
    """CHANGELOG.md content, shown by the UI's version popup."""
    path = REPO_ROOT / "CHANGELOG.md"
    return path.read_text(encoding="utf-8") if path.exists() else "No changelog available."


@app.get("/best-practices", response_class=PlainTextResponse)
def best_practices() -> str:
    """docs/BEST_PRACTICES.md, shown by the UI's Best practices popup."""
    path = REPO_ROOT / "docs" / "BEST_PRACTICES.md"
    return path.read_text(encoding="utf-8") if path.exists() else "No guide available."


@app.get("/brief", include_in_schema=False)
def technical_brief() -> FileResponse:
    """The technical product brief PDF, linked from the UI masthead."""
    path = REPO_ROOT / "docs" / "Migration_Copilot_Technical_Brief.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Technical brief not found in docs/.")
    return FileResponse(path, media_type="application/pdf")


@app.post("/parse", response_model=list[Pipeline])
async def parse(export: UploadFile) -> list[Pipeline]:
    """Parse a PowerCenter XML export into the normalized IR."""
    pipelines, _ = _parse_upload(await export.read())
    return pipelines


@app.post("/convert", response_model=ConversionResponse)
async def convert(export: UploadFile) -> ConversionResponse:
    """Full conversion: source analysis + parse -> map -> generate per mapping."""
    mapper = RulesMapper()
    generator = KtrGenerator()
    pipelines, source = _parse_upload(await export.read())
    results = []
    for pipeline in pipelines:
        mapper.apply(pipeline)
        results.append(_build_result(pipeline, generator))
    assess_source(source, pipelines)
    return ConversionResponse(source=source, results=results)


@app.post("/sandbox", response_model=SandboxKit)
def sandbox(pipeline: Pipeline) -> SandboxKit:
    """Sandbox test kit for a mapped pipeline: setup guide, DDL, synthetic CSVs."""
    return build_sandbox_kit(pipeline)


@app.post("/translate", response_model=ConversionResult)
def translate(pipeline: Pipeline) -> ConversionResult:
    """Translate all untranslated expressions in a mapped pipeline via the
    configured LLM provider, then regenerate report + .ktr."""
    try:
        ExpressionTranslator().translate_pipeline(pipeline)
    except TranslationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _build_result(pipeline, KtrGenerator())


class SettingsResponse(BaseModel):
    settings: LLMSettings
    detection: DetectionReport


@app.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Saved LLM settings plus a live detection report (hardware, env, Ollama)."""
    return SettingsResponse(settings=load_settings(), detection=detection_report())


@app.put("/settings", response_model=LLMSettings)
def put_settings(settings: LLMSettings) -> LLMSettings:
    save_settings(settings)
    return settings


# One pull at a time is plenty for a single-user internal tool.
_pull_state: dict[str, str] = {"status": "idle", "model": "", "detail": ""}


def _run_pull(base_url: str, model: str) -> None:
    try:
        with httpx.stream(
            "POST", f"{base_url}/api/pull", json={"name": model}, timeout=None
        ) as response:
            for line in response.iter_lines():
                if not line:
                    continue
                event = json.loads(line)
                if error := event.get("error"):
                    _pull_state.update(status="error", detail=error)
                    return
                detail = event.get("status", "")
                if total := event.get("total"):
                    done = event.get("completed", 0)
                    detail += f" {done / total:.0%}"
                _pull_state.update(status="pulling", detail=detail)
        _pull_state.update(status="done", detail="model ready")
    except Exception as exc:
        _pull_state.update(status="error", detail=str(exc))


@app.post("/settings/ollama/pull")
def pull_model(model: str) -> dict[str, str]:
    """Start pulling MODEL on the configured Ollama server (non-blocking)."""
    if _pull_state["status"] == "pulling":
        raise HTTPException(status_code=409, detail=f"already pulling {_pull_state['model']}")
    base_url = load_settings().base_url
    _pull_state.update(status="pulling", model=model, detail="starting")
    threading.Thread(target=_run_pull, args=(base_url, model), daemon=True).start()
    return _pull_state


@app.get("/settings/ollama/pull")
def pull_status() -> dict[str, str]:
    return _pull_state


def _parse_upload(data: bytes) -> tuple[list[Pipeline], SourceInfo]:
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        parser = PowerCenterParser()
        return parser.parse_file(tmp_path), parser.analyze_export(tmp_path)
    except (PowerCenterParseError, SyntaxError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


# Serve the built React UI for every non-API path. Mounted last so the API
# routes above always win. Requires `npm run build` in frontend/ (see
# scripts/dev.ps1 ui-build); without a build, only the API + /docs exist.
if UI_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
