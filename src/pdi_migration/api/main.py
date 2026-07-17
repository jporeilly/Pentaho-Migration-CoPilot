"""FastAPI layer — a thin wrapper over the core package.

Run with:  uvicorn pdi_migration.api.main:app --reload
Requires the [api] extra:  pip install -e ".[api]"

Serves the Phase 0 review UI at / and the API under /parse, /convert.
Interactive API docs at /docs.
"""

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

logger = logging.getLogger("pdi_migration.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # generous: largest real export seen is ~7 MB


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional shared-secret auth: set PDI_MIGRATION_API_KEY to enforce it on
    mutating endpoints. Unset (the default) keeps local single-user use frictionless."""
    expected = os.environ.get("PDI_MIGRATION_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key header")

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
from pdi_migration.project import (
    STATUSES,
    MappingRecord,
    get_mapping,
    list_mappings,
    set_status,
)
from pdi_migration.sandbox import SandboxKit, build_sandbox_kit
from pdi_migration.validator.diff import DiffError, DiffReport, compare_csv
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

app = FastAPI(
    title="Migration Copilot",
    version=__version__,
    description=(
        "**[← Back to Migration Copilot](/)**\n\n"
        "REST API behind the review UI: convert PowerCenter exports, translate "
        "expressions, generate sandbox kits, diff outputs, and track the migration project."
    ),
)


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
    rules_meta = RulesMapper().meta
    return {
        "status": "ok",
        "version": __version__,
        "rules_version": str(rules_meta.get("version", "?")),
        "rules_updated": str(rules_meta.get("updated", "?")),
    }


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


@app.post("/parse", response_model=list[Pipeline], dependencies=[Depends(require_api_key)])
async def parse(export: UploadFile) -> list[Pipeline]:
    """Parse a PowerCenter XML export into the normalized IR."""
    pipelines, _ = _parse_upload(await export.read())
    return pipelines


@app.post("/convert", response_model=ConversionResponse, dependencies=[Depends(require_api_key)])
async def convert(export: UploadFile) -> ConversionResponse:
    """Full conversion: source analysis + parse -> map -> generate per mapping."""
    started = time.monotonic()
    mapper = RulesMapper()
    generator = KtrGenerator()
    data = await export.read()
    pipelines, source = _parse_upload(data)
    results = []
    for pipeline in pipelines:
        mapper.apply(pipeline)
        results.append(_build_result(pipeline, generator))
    assess_source(source, pipelines)
    logger.info(
        "convert file=%s bytes=%d mappings=%d elapsed_ms=%d",
        export.filename, len(data), len(results), (time.monotonic() - started) * 1000,
    )
    return ConversionResponse(source=source, results=results)


class PdfRequest(BaseModel):
    source: SourceInfo | None = None
    result: "ConversionResult"


@app.post("/report/pdf", dependencies=[Depends(require_api_key)])
def report_pdf(payload: PdfRequest) -> Response:
    """Branded PDF migration report for one mapping."""
    from pdi_migration.report_pdf import build_pdf_report

    result = payload.result
    pdf_bytes = build_pdf_report(
        payload.source, result.pipeline, result.report, result.score, result.impact,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="{result.pipeline.name}.report.pdf"',
        },
    )


@app.post("/sandbox", response_model=SandboxKit, dependencies=[Depends(require_api_key)])
def sandbox(pipeline: Pipeline) -> SandboxKit:
    """Sandbox test kit for a mapped pipeline: setup guide, DDL, synthetic CSVs."""
    return build_sandbox_kit(pipeline)


@app.post("/diff", response_model=DiffReport, dependencies=[Depends(require_api_key)])
async def diff(
    expected: UploadFile, actual: UploadFile, key: str | None = None
) -> DiffReport:
    """Measured output parity: diff the original pipeline's CSV output against
    the converted pipeline's CSV output (optionally matching rows by KEY column)."""
    try:
        return compare_csv(
            (await expected.read()).decode("utf-8-sig"),
            (await actual.read()).decode("utf-8-sig"),
            key=key or None,
        )
    except DiffError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/project/open", response_model=ConversionResponse)
def project_open(file: str, mapping: str) -> ConversionResponse:
    """Re-open a batch-converted mapping in the full workflow: re-parses its
    source export and returns the same shape as /convert (source + results,
    with the requested mapping first)."""
    record = get_mapping(file, mapping)
    if record is None:
        raise HTTPException(status_code=404, detail="mapping not found in project store")
    source_path = Path(record.source_path)
    if not record.source_path or not source_path.exists():
        raise HTTPException(
            status_code=410,
            detail=f"source export not found at '{record.source_path}' — "
                   "it may have moved; re-run `pdi-migrate batch`",
        )
    mapper = RulesMapper()
    generator = KtrGenerator()
    parser = PowerCenterParser()
    pipelines = [mapper.apply(p) for p in parser.parse_file(source_path)]
    source = assess_source(parser.analyze_export(source_path), pipelines)
    results = sorted(
        (_build_result(p, generator) for p in pipelines),
        key=lambda r: r.pipeline.name != mapping,  # requested mapping first
    )
    return ConversionResponse(source=source, results=results)


class StatusUpdate(BaseModel):
    file: str
    mapping: str
    status: str


@app.get("/project", response_model=list[MappingRecord])
def project() -> list[MappingRecord]:
    """The migration project: every batch-converted mapping with its status."""
    return list_mappings()


@app.post("/project/status", dependencies=[Depends(require_api_key)])
def project_status(update: StatusUpdate) -> dict[str, bool]:
    if update.status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {STATUSES}")
    if not set_status(update.file, update.mapping, update.status):
        raise HTTPException(status_code=404, detail="mapping not found in project store")
    return {"ok": True}


@app.post("/translate", response_model=ConversionResult, dependencies=[Depends(require_api_key)])
def translate(pipeline: Pipeline) -> ConversionResult:
    """Translate all untranslated expressions synchronously (small mappings /
    scripting). The UI uses the /translate/start job flow instead — a browser
    fetch times out on long translations."""
    try:
        ExpressionTranslator().translate_pipeline(pipeline)
    except TranslationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _build_result(pipeline, KtrGenerator())


# Long translations run as background jobs the UI polls — one browser request
# per poll, so no fetch ever outlives the browser's timeout.
_translate_jobs: dict[str, dict] = {}


@app.post("/translate/start", dependencies=[Depends(require_api_key)])
def translate_start(pipeline: Pipeline) -> dict[str, str]:
    """Start translating in the background; returns a job id to poll."""
    try:
        translator = ExpressionTranslator()
        translator._check_provider()
    except TranslationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex[:12]
    job: dict = {"status": "running", "done": 0, "total": 0, "detail": "", "result": None}
    _translate_jobs[job_id] = job

    def run() -> None:
        try:
            def progress(done: int, total: int) -> None:
                job["done"], job["total"] = done, total

            translator.translate_pipeline(pipeline, progress=progress)
            job["result"] = _build_result(pipeline, KtrGenerator()).model_dump()
            job["status"] = "done"
        except Exception as exc:
            job["status"] = "error"
            job["detail"] = str(exc)
            logger.exception("translate job %s failed", job_id)

    threading.Thread(target=run, daemon=True).start()
    return {"job": job_id}


@app.get("/translate/status")
def translate_status(job: str) -> dict:
    """Progress of a translation job; includes the full result when done."""
    state = _translate_jobs.get(job)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown translation job")
    return state


class SettingsResponse(BaseModel):
    settings: LLMSettings
    detection: DetectionReport


@app.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Saved LLM settings plus a live detection report (hardware, env, Ollama)."""
    return SettingsResponse(settings=load_settings(), detection=detection_report())


@app.put("/settings", response_model=LLMSettings, dependencies=[Depends(require_api_key)])
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


@app.post("/settings/ollama/pull", dependencies=[Depends(require_api_key)])
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
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
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
