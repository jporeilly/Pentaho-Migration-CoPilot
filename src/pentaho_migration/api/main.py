"""FastAPI layer — a thin wrapper over the core package.

Run with:  uvicorn pentaho_migration.api.main:app --reload
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
from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

logger = logging.getLogger("pentaho_migration.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # generous: largest real export seen is ~7 MB


from pentaho_migration.api.security import require_api_key

from pentaho_migration import __version__
from pentaho_migration.generator import KtrGenerator
from pentaho_migration.ir import Pipeline, SourceInfo
from pentaho_migration.llm import (
    ExpressionTranslator,
    LLMSettings,
    TranslationError,
    load_settings,
    save_settings,
)
from pentaho_migration.llm.detect import DetectionReport, detection_report
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import ParseError, detect_parser
from pentaho_migration.project import (
    STATUSES,
    MappingRecord,
    get_mapping,
    list_mappings,
    set_status,
)
from pentaho_migration.sandbox import SandboxKit, build_sandbox_kit
from pentaho_migration.validator.diff import DiffError, DiffReport, compare_csv
from pentaho_migration.validator import (
    EffortEstimate,
    ImpactAnalysis,
    MigrationReport,
    MigrationScore,
    assess_source,
    build_effort,
    build_impact_analysis,
    build_report,
    build_score,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
UI_DIST = REPO_ROOT / "frontend" / "dist"
SAMPLE_FILE = REPO_ROOT / "samples" / "m_load_sales.xml"

app = FastAPI(
    title="Pentaho Migration Copilot",
    version=__version__,
    description=(
        "**[← Back to Pentaho Migration Copilot](/)**\n\n"
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
    effort: EffortEstimate | None = None


def _build_result(pipeline: Pipeline, generator: KtrGenerator) -> "ConversionResult":
    impact = build_impact_analysis(pipeline)
    report = build_report(pipeline)
    return ConversionResult(
        pipeline=pipeline,
        report=report,
        ktr=generator.generate(pipeline),
        impact=impact,
        score=build_score(pipeline, impact),
        effort=build_effort(pipeline, report),
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
    pipelines, _ = _parse_upload(await export.read(), export.filename)
    return pipelines


@app.post("/convert", response_model=ConversionResponse, dependencies=[Depends(require_api_key)])
async def convert(export: UploadFile) -> ConversionResponse:
    """Full conversion: source analysis + parse -> map -> generate per mapping."""
    started = time.monotonic()
    generator = KtrGenerator()
    data = await export.read()
    pipelines, source = _parse_upload(data, export.filename)
    results = []
    for pipeline in pipelines:
        RulesMapper.for_pipeline(pipeline).apply(pipeline)
        results.append(_build_result(pipeline, generator))
    assess_source(source, pipelines)
    logger.info(
        "convert file=%s bytes=%d mappings=%d elapsed_ms=%d",
        export.filename, len(data), len(results), (time.monotonic() - started) * 1000,
    )
    return ConversionResponse(source=source, results=results)


class SuggestRequest(BaseModel):
    pipeline: Pipeline
    step: str
    impact_entry: dict | None = None


@app.post("/suggest", dependencies=[Depends(require_api_key)])
def suggest(payload: SuggestRequest) -> dict[str, str]:
    """AI-proposed PDI solution for one step (advisory markdown, human-reviewed)."""
    from pentaho_migration.llm.suggest import SolutionSuggester

    try:
        suggester = SolutionSuggester()
        text = suggester.suggest(payload.pipeline, payload.step, payload.impact_entry)
    except TranslationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"suggestion": text, "model": suggester.settings.model or ""}


class PdfRequest(BaseModel):
    source: SourceInfo | None = None
    result: "ConversionResult"
    rate: float = 150.0


@app.post("/report/pdf", dependencies=[Depends(require_api_key)])
def report_pdf(payload: PdfRequest) -> Response:
    """Branded PDF migration report for one mapping."""
    from pentaho_migration.report_pdf import build_pdf_report

    result = payload.result
    pdf_bytes = build_pdf_report(
        payload.source, result.pipeline, result.report, result.score, result.impact,
        effort=result.effort, rate=payload.rate,
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
                   "it may have moved; re-run `pentaho-migrate batch`",
        )
    generator = KtrGenerator()
    parser = detect_parser(source_path)
    pipelines = [
        RulesMapper.for_pipeline(p).apply(p) for p in parser.parse_file(source_path)
    ]
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


class ProjectRow(MappingRecord):
    """A stored mapping plus its effort estimate (computed at read time from
    the stored counts, so pre-existing project databases need no migration)."""

    copilot_hours: float = 0.0
    manual_hours: float = 0.0
    saved_hours: float = 0.0


def _project_row(record: MappingRecord) -> ProjectRow:
    from pentaho_migration.validator.effort import effort_from_counts

    effort = effort_from_counts(
        steps=record.steps, auto=record.auto, review=record.review,
        manual=record.manual, untranslated_exprs=record.expressions)
    return ProjectRow(
        **record.model_dump(),
        copilot_hours=effort.copilot_hours,
        manual_hours=effort.manual_hours,
        saved_hours=effort.saved_hours,
    )


@app.get("/project", response_model=list[ProjectRow])
def project() -> list[ProjectRow]:
    """The migration project: every batch-converted mapping with its status
    and per-mapping effort estimate."""
    return [_project_row(r) for r in list_mappings()]


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


def _parse_upload(data: bytes, filename: str | None = None) -> tuple[list[Pipeline], SourceInfo]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    # keep the ORIGINAL filename on disk — Talend job names derive from it
    safe_name = Path(filename or "export.xml").name or "export.xml"
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / safe_name
        tmp_path.write_bytes(data)
        try:
            parser = detect_parser(tmp_path)
            return parser.parse_file(tmp_path), parser.analyze_export(tmp_path)
        except (ParseError, SyntaxError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


from pentaho_migration.reports.api import router as reports_router

app.include_router(reports_router)

# Serve the built React UI for every non-API path. Mounted last so the API
# routes above always win. Requires `npm run build` in frontend/ (see
# scripts/dev.ps1 ui-build); without a build, only the API + /docs exist.
if UI_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
