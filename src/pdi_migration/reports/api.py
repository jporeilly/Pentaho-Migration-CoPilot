"""FastAPI router for the reports pipeline, mounted under /reports.

Stateless like /convert: every call re-derives everything from the uploaded
RptToXml dump. The .prpt bundle (a small ZIP) travels base64-encoded in the
JSON response; the UI turns it into a Blob download.
"""

import base64
import logging
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pdi_migration.api.security import require_api_key
from pdi_migration.llm import ExpressionTranslator, TranslationError
from pdi_migration.reports import build_conversion_report, load_report_model, write_prpt
from pdi_migration.reports.llm_assist import translate_manual_formulas

logger = logging.getLogger("pdi_migration.api.reports")

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_FILE = REPO_ROOT / "samples" / "crystal" / "branch_transactions.xml"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportFormula(BaseModel):
    name: str
    status: str            # auto | review | manual
    translation: str = ""
    original: str = ""
    notes: list[str] = []


class ReportParameter(BaseModel):
    name: str
    type: str
    prompt: str = ""
    default: str = ""


class ReportSummaryField(BaseModel):
    name: str
    operation: str
    field: str
    group: str = ""
    expression: str


class ReportSection(BaseModel):
    area: str
    group: int | None = None
    height: float
    elements: int


class ReportCounts(BaseModel):
    sections: int
    elements: int
    groups: int
    parameters: int
    summaries: int
    auto: int
    review: int
    manual: int


class ReportSummary(BaseModel):
    """Parsed + translated view of one Crystal report."""

    source: str
    name: str
    jndi: str
    sql: str
    sql_generated: bool
    record_selection: str = ""
    tables: list[str]
    groups: list[str]
    parameters: list[ReportParameter]
    summaries: list[ReportSummaryField]
    sections: list[ReportSection]
    formulas: list[ReportFormula]
    todos: list[str]
    counts: ReportCounts


class ReportConversionResponse(BaseModel):
    summary: ReportSummary
    report_markdown: str
    prpt_base64: str
    filename: str


def _summarize(model, source_name: str) -> ReportSummary:
    todos: list[str] = []
    for s in model.sections:
        for el in s.elements:
            if el.kind in ("subreport", "image", "unknown"):
                todos.append(f"{s.area_kind}: {el.kind} '{el.text or el.name}'")
            todos.extend(el.notes)
    todos.extend(model.issues)
    return ReportSummary(
        source=source_name,
        name=model.name,
        jndi=model.jndi,
        sql=model.sql,
        sql_generated=model.sql_generated,
        record_selection=model.record_selection,
        tables=list(model.tables),
        groups=[g.column for g in model.groups],
        parameters=[ReportParameter(name=p.name, type=p.value_type,
                                    prompt=p.prompt, default=p.default)
                    for p in model.parameters],
        summaries=[ReportSummaryField(name=s.name, operation=s.operation,
                                      field=s.field_ref, group=s.group_field,
                                      expression=s.expression_name)
                   for s in model.summaries],
        sections=[ReportSection(area=s.area_kind,
                                group=s.group_index if s.group_index >= 0 else None,
                                height=round(s.height, 1), elements=len(s.elements))
                  for s in model.sections],
        formulas=[ReportFormula(name=f.name, status=f.status, translation=f.translation,
                                original=f.text, notes=f.notes)
                  for f in model.formulas.values()],
        todos=todos,
        counts=ReportCounts(
            sections=len(model.sections),
            elements=sum(len(s.elements) for s in model.sections),
            groups=len(model.groups),
            parameters=len(model.parameters),
            summaries=len(model.summaries),
            auto=sum(1 for f in model.formulas.values() if f.status == "auto"),
            review=sum(1 for f in model.formulas.values() if f.status == "review"),
            manual=sum(1 for f in model.formulas.values() if f.status == "manual"),
        ),
    )


def _load_upload(data: bytes, filename: str, jndi: str):
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload exceeds the 50MB limit")
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        tf.write(data)
        tmp = Path(tf.name)
    try:
        return load_report_model(tmp, jndi or None)
    except Exception as exc:
        raise HTTPException(status_code=422,
                            detail=f"could not parse RptToXml file: {exc}")
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/sample", include_in_schema=False)
def sample() -> FileResponse:
    """The bundled Crystal demo dump, used by the UI's 'Try the sample' button."""
    return FileResponse(SAMPLE_FILE, media_type="text/xml")


@router.post("/inspect", response_model=ReportSummary,
             dependencies=[Depends(require_api_key)])
async def inspect(dump: UploadFile, jndi: str = "") -> ReportSummary:
    """Parse an RptToXml dump and translate its formulas, without converting."""
    model = _load_upload(await dump.read(), dump.filename or "upload.xml", jndi)
    return _summarize(model, dump.filename or "upload.xml")


def _build_response(model, source_name: str) -> ReportConversionResponse:
    safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in model.name).strip() or "report"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"{safe}.prpt"
        write_prpt(model, out)
        prpt_bytes = out.read_bytes()
    markdown = build_conversion_report(model, source_name, f"{safe}.prpt")
    return ReportConversionResponse(
        summary=_summarize(model, source_name),
        report_markdown=markdown,
        prpt_base64=base64.b64encode(prpt_bytes).decode("ascii"),
        filename=f"{safe}.prpt",
    )


@router.post("/convert", response_model=ReportConversionResponse,
             dependencies=[Depends(require_api_key)])
async def convert(dump: UploadFile, jndi: str = "") -> ReportConversionResponse:
    """Full conversion: parse -> translate -> .prpt bundle + conversion report."""
    started = time.monotonic()
    data = await dump.read()
    source_name = dump.filename or "upload.xml"
    model = _load_upload(data, source_name, jndi)
    response = _build_response(model, source_name)
    logger.info("reports/convert file=%s bytes=%d formulas=%d elapsed_ms=%d",
                source_name, len(data), len(model.formulas),
                (time.monotonic() - started) * 1000)
    return response


_assist_jobs: dict[str, dict] = {}


@router.post("/translate/start", dependencies=[Depends(require_api_key)])
async def translate_start(dump: UploadFile, jndi: str = "") -> dict[str, str]:
    """LLM-assist the formulas the deterministic translator flagged manual.

    Runs in the background (local models can take minutes); poll
    /reports/translate/status. The finished job carries a full conversion
    response with the assisted formulas baked into the .prpt."""
    try:
        translator = ExpressionTranslator()
        translator._check_provider()
    except TranslationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    data = await dump.read()
    source_name = dump.filename or "upload.xml"
    model = _load_upload(data, source_name, jndi)

    job_id = uuid.uuid4().hex[:12]
    job: dict = {"status": "running", "done": 0, "total": 0,
                 "translated": 0, "detail": "", "result": None}
    _assist_jobs[job_id] = job

    def run() -> None:
        try:
            def progress(done: int, total: int) -> None:
                job["done"], job["total"] = done, total

            job["translated"] = translate_manual_formulas(
                model, translator=translator, progress=progress)
            job["result"] = _build_response(model, source_name).model_dump()
            job["status"] = "done"
        except Exception as exc:
            job["status"] = "error"
            job["detail"] = str(exc)
            logger.exception("reports translate job %s failed", job_id)

    threading.Thread(target=run, daemon=True).start()
    return {"job": job_id}


@router.get("/translate/status")
def translate_status(job: str) -> dict:
    """Progress of a formula-assist job; includes the full result when done."""
    state = _assist_jobs.get(job)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown translation job")
    return state
