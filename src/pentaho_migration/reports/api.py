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

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pentaho_migration.api.security import require_api_key
from pentaho_migration.jobs import JobStore
from pentaho_migration.llm import ExpressionTranslator, TranslationError
from pentaho_migration.reports import build_conversion_report, load_report_model, write_prpt
from pentaho_migration.reports.effort import build_report_effort
from pentaho_migration.reports.todo_kinds import APPLIED, INFO, MANUAL, split_todos
from pentaho_migration.reports.llm_assist import translate_manual_formulas
from pentaho_migration.reports.schema_agent import (
    SqlAssistant, probe_schema, schema_context, validate_sql)
from pentaho_migration.validator.effort import EffortEstimate

logger = logging.getLogger("pentaho_migration.api.reports")

REPO_ROOT = Path(__file__).resolve().parents[3]
# The "Try Crystal Reports" scenario. A REAL harvested report, not an authored
# dump, so the demo runs end to end: open the original .rpt in the Crystal
# viewer - it carries its own saved rows, so it renders with no database -
# then convert it and open the .prpt in Report Designer.
#
# Chosen for being substantial AND landing clean: a real account statement -
# letterhead, watermark, scanned signature, two nested groups, running totals,
# 74 pages of saved rows - that converts with three honest TODOs, all of them
# the same thing (Crystal suppresses sections conditionally; PRD merges
# sections into one band). Feature density alone was the wrong instinct: the
# densest report in the corpus is a drill-down report, and drill-down has no
# PRD equivalent, so it arrives with a page of TODOs. True, and a bad opening.
SAMPLE_NAME = "Statement_of_Account.xml"
DEMO_DIR = REPO_ROOT / "samples" / "crystal" / "demo"
SAMPLE_FILE = DEMO_DIR / SAMPLE_NAME
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# The reports the "Try Crystal Reports" picker offers, in demo order. `jndi`
# is the datasource each one's generated SQL binds to. A dump in the demo
# folder without an entry here still appears, labelled by its stem and bound
# to the default datasource - the list is the folder, not this table.
_DEMO_META = {
    "Statement_of_Account": {
        "label": "Account statement",
        "description": "Letterhead, watermark, scanned signature, 74 pages of "
                       "saved data — the main flow.",
        "jndi": "Xtreme",
    },
    "AdventureWorks-TotalSalesByYear": {
        "label": "AdventureWorks — total sales by year",
        "description": "Saved 2026, converts with zero manual work, a clean "
                       "bar chart. Renders from its own embedded data.",
        "jndi": "AdventureWorks",
    },
    "ComparativeIncomeStatement": {
        "label": "Comparative income statement",
        "description": "A 2016 SAP income statement whose cross-tab renders a "
                       "populated pivot against boe_samples — start that "
                       "MySQL database first.",
        "jndi": "BOE_Samples",
    },
    "WorldSalesReport": {
        "label": "World sales report",
        "description": "The honesty demo — a drill-down / Top-N design that "
                       "comes back ⚠ REVIEW with named blockers.",
        "jndi": "BOE_Samples",
    },
    "Customer_Profile_Report": {
        "label": "Customer profile — sub-report + drill-down",
        "description": "Exercises both: a nested PRD sub-report and Crystal "
                       "drill-down, on Xtreme with 292 saved rows. The "
                       "sub-report link is a parameter, so it renders in "
                       "Report Designer rather than the headless preview.",
        "jndi": "Xtreme",
    },
}


def _demo_dumps() -> list:
    """The demo reports available to the Try picker: every .xml in the demo
    folder that has its .rpt beside it, curated ones first in demo order."""
    have = {p.stem for p in DEMO_DIR.glob("*.xml")
            if p.with_suffix(".rpt").is_file()}
    ordered = [s for s in _DEMO_META if s in have]
    ordered += sorted(have - set(_DEMO_META))
    out = []
    for stem in ordered:
        meta = _DEMO_META.get(stem, {})
        out.append({"name": stem,
                    "label": meta.get("label", stem.replace("_", " ")),
                    "description": meta.get("description", ""),
                    "jndi": meta.get("jndi", "SampleData")})
    return out


def _demo_file(name: str) -> Path:
    """The demo dump for a requested name, or the default. Guards against
    path traversal: only a plain stem that resolves to a real pair inside
    the demo folder is honoured, anything else falls back to the sample."""
    stem = (name or "").strip()
    if stem and "/" not in stem and "\\" not in stem and ".." not in stem:
        target = DEMO_DIR / f"{stem}.xml"
        if target.is_file() and target.with_suffix(".rpt").is_file():
            return target
    return SAMPLE_FILE

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportFormula(BaseModel):
    name: str
    status: str            # auto | review | manual
    translation: str = ""
    prd: str = ""          # PRD-side artifact: translation or generated function
    source: str = "rules"  # rules | llm
    llm_confidence: str = ""
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


class ReportElementInfo(BaseModel):
    """Geometry + identity of one placed element — enough for the UI's
    layout wireframe (positions are points, straight from the .rpt)."""

    kind: str
    x: float
    y: float
    width: float
    height: float
    label: str = ""   # label text, field/expression name, or TODO text
    layered: bool = False  # visibility-conditioned: stacks with siblings by
                           # design, one prints per row


class ReportSection(BaseModel):
    area: str
    group: int | None = None
    height: float
    elements: int
    suppressed: bool = False
    items: list[ReportElementInfo] = []


class ReportSubLayout(BaseModel):
    """A converted subreport's own bands, for the tabbed layout preview."""

    name: str
    linked: bool = False           # has parent->child parameter links
    sections: list[ReportSection] = []


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
    """Parsed + translated view of one converted report."""

    source_family: str = "crystal"   # crystal | xaction - drives the badge

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
    subreports: list[ReportSubLayout] = []
    formulas: list[ReportFormula]
    todos: list[str]           # everything, unchanged - existing callers
    todos_manual: list[str] = []   # the real backlog: a human must decide
    todos_applied: list[str] = []  # the pipeline already did it - verify
    todos_info: list[str] = []     # provenance, no action
    counts: ReportCounts
    effort: EffortEstimate | None = None


class ReportConversionResponse(BaseModel):
    summary: ReportSummary
    report_markdown: str
    prpt_base64: str
    filename: str


def _source_family(source_name: str) -> str:
    """Which migration family an upload belongs to, from its artifact:
    an action sequence or a zipped solution folder is the old Pentaho
    BI platform; everything else on this page is Crystal."""
    name = (source_name or "").lower()
    return "xaction" if name.endswith((".xaction", ".zip")) else "crystal"


def _summarize(model, source_name: str) -> ReportSummary:
    from pentaho_migration.reports.model import is_todo_element

    def _sections(sections):
        return [ReportSection(
            area=s.area_kind,
            group=s.group_index if s.group_index >= 0 else None,
            height=round(s.height, 1), elements=len(s.elements),
            suppressed=s.suppressed,
            items=[ReportElementInfo(
                kind=el.kind, x=round(el.x, 1), y=round(el.y, 1),
                width=round(el.width, 1), height=round(el.height, 1),
                label=(el.text or el.column or el.field_ref or "")[:60],
                layered=any(k == "visible" for k, _ in el.style_expressions)
                or bool(el.condition_formulas))
                for el in s.elements])
            for s in sections]

    # converted subreports, in the order they appear, for the tabbed preview
    sublayouts: list[ReportSubLayout] = []
    for s in model.sections:
        for el in s.elements:
            if el.kind == "subreport" and el.subreport is not None:
                sublayouts.append(ReportSubLayout(
                    name=el.subreport.name,
                    linked=bool(el.subreport_links),
                    sections=_sections(el.subreport.sections)))

    todos: list[str] = []
    for s in model.sections:
        for el in s.elements:
            if is_todo_element(el):
                todos.append(f"{s.area_kind}: {el.kind} '{el.text or el.name}'")
            todos.extend(el.notes)
    todos.extend(model.issues)
    split = split_todos(todos)
    return ReportSummary(
        source=source_name,
        source_family=_source_family(source_name),
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
        sections=_sections(model.sections),
        subreports=sublayouts,
        formulas=[ReportFormula(name=f.name, status=f.status, translation=f.translation,
                                prd=f.prd_target(), source=f.source,
                                llm_confidence=f.llm_confidence,
                                original=f.text, notes=f.notes)
                  for f in model.formulas.values()],
        todos=todos,
        todos_manual=split[MANUAL],
        todos_applied=split[APPLIED],
        todos_info=split[INFO],
        effort=build_report_effort(model),
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


def _check_upload_size(data: bytes) -> None:
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload exceeds the 50MB limit")


def _load_rpt_upload(data: bytes, filename: str, jndi: str):
    """A customer's file is the .rpt itself - run the same extraction chain
    the corpus scripts use (RptToXml + credential scrub + cross-tab
    recovery), then parse the dump exactly as if it had been uploaded.

    Two extras only the binary makes possible: the SAVED ROWS are recovered
    and embedded so the converted .prpt opens in PRD showing real data with
    no database, and the .rpt is kept in the viewer cache so the "View
    original" button works for uploads too."""
    from pentaho_migration.reports.rpt_extract import extract_rpt
    from pentaho_migration.reports.rpt_saved import load_saved_rows
    from pentaho_migration.reports.rpt_viewer import cache_uploaded_rpt

    with tempfile.TemporaryDirectory() as workdir:
        rpt = Path(workdir) / (Path(filename).stem + ".rpt")
        rpt.write_bytes(data)
        try:
            dump = extract_rpt(rpt, rpt.with_suffix(".xml"))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        try:
            model = load_report_model(dump, jndi or None)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"extracted, but could not parse the dump: {exc}")
        model.saved_rows = load_saved_rows(rpt)
        if model.saved_rows is not None:
            model.issues.append(
                f"{len(model.saved_rows.rows):,} saved data row(s) recovered "
                "from the .rpt and embedded as the report's dataset - PRD "
                "shows them with no database; switch to the 'source-sql' "
                "query to go live against the real datasource")
            model.issues.extend(model.saved_rows.notes)
        cache_uploaded_rpt(rpt)
        return model


def _load_dump_upload(data: bytes, filename: str, jndi: str):
    """An RptToXml dump uploaded directly. When the ORIGINAL .rpt is known
    (same stem in the samples tree or the upload cache - the corpus/demo pair
    convention), its saved rows are recovered and embedded, so the Try-button
    demo ships real data exactly like a raw .rpt drop does."""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        tf.write(data)
        tmp = Path(tf.name)
    try:
        model = load_report_model(tmp, jndi or None)
    except Exception as exc:
        raise HTTPException(status_code=422,
                            detail=f"could not parse RptToXml file: {exc}")
    finally:
        tmp.unlink(missing_ok=True)

    from pentaho_migration.reports.rpt_saved import load_saved_rows
    from pentaho_migration.reports.rpt_viewer import find_original

    original = find_original(filename)
    if original is not None:
        model.saved_rows = load_saved_rows(original)
        if model.saved_rows is not None:
            model.issues.append(
                f"{len(model.saved_rows.rows):,} saved data row(s) recovered "
                "from the .rpt and embedded as the report's dataset - PRD "
                "shows them with no database; switch to the 'source-sql' "
                "query to go live against the real datasource")
            model.issues.extend(model.saved_rows.notes)
    return model


XACTION_DIR = REPO_ROOT / "samples" / "xactions"


def _xaction_resource_resolver(location: str) -> bytes:
    """Resolve an xaction's report-definition by NAME within the xactions
    samples tree - the demo/corpus convention, mirroring find_original for
    .rpt pairs. Path components are stripped, so a hostile location cannot
    escape the tree."""
    name = Path(location).name
    for hit in XACTION_DIR.rglob(name):
        if hit.is_file():
            return hit.read_bytes()
    raise FileNotFoundError(location)


def _load_xaction_upload(data: bytes, filename: str, jndi: str):
    """An uploaded action sequence. The paired report definition resolves
    from the samples tree (the demo convention); a customer's own xaction
    without its definition converts the query/parameters and says exactly
    what to upload next - or they zip the solution folder instead."""
    from pentaho_migration.reports.xaction_parser import build_report_model

    try:
        model = build_report_model(data, resolver=_xaction_resource_resolver)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if jndi:
        model.jndi = jndi
    if not model.name or model.name == "Converted xaction report":
        model.name = Path(filename).stem
    return model


def _load_xaction_zip_upload(data: bytes, filename: str, jndi: str):
    """A zipped solution folder: the first .xaction member is the report,
    and every other member is a resolvable resource - so the xaction + its
    old report definition travel together in one upload."""
    import io as _io
    import zipfile

    from pentaho_migration.reports.xaction_parser import build_report_model

    try:
        zf = zipfile.ZipFile(_io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=422, detail="not a readable .zip")
    members = {Path(n).name: n for n in zf.namelist() if not n.endswith("/")}
    xaction_name = next((n for n in members
                         if n.lower().endswith(".xaction")), None)
    if xaction_name is None:
        raise HTTPException(
            status_code=422,
            detail="the .zip holds no .xaction - zip the solution folder "
                   "with the action sequence and its report definition")

    def resolver(location: str) -> bytes:
        member = members.get(Path(location).name)
        if member is None:
            raise FileNotFoundError(location)
        return zf.read(member)

    model = build_report_model(zf.read(members[xaction_name]),
                               resolver=resolver)
    if jndi:
        model.jndi = jndi
    if not model.name or model.name == "Converted xaction report":
        model.name = Path(xaction_name).stem
    return model


def _fill_lov_defaults(model) -> None:
    """Give each no-default query-backed prompt its first available value,
    read from the live connection - the converted report then opens WITH
    data. API-layer only (a convert already runs the JVM); parsing stays
    database-free, and an unreachable connection just leaves the
    dropdown unselected."""
    from pentaho_migration.reports.prpt_writer import _lov_sql
    from pentaho_migration.reports.schema_agent import preview_query

    for prm in model.parameters:
        column = model.param_sql_columns.get(prm.name)
        if not column or prm.default or prm.default_values:
            continue
        try:
            got = preview_query(model.jndi, _lov_sql(model, column), limit=1)
            rows = got.get("rows") if isinstance(got, dict) else got
            if rows:
                prm.default = str(rows[0][0])
                model.issues.append(
                    f"parameter '{prm.name}': first available value "
                    f"'{prm.default}' pre-selected from the live "
                    "connection, so the report opens with data")
        except Exception:
            continue


def _widen_empty_date_window(model) -> None:
    """When the authored defaults return NO rows on the live connection,
    repoint the date window at the data's own span.

    The order_detail case: the xaction authors customer 103 with a
    2005-01-01..2005-01-05 window - authored against the ORIGINAL
    estate's database. On this connection customer 103's orders all live
    in 2003-2004, so every default is set and the report still opens
    empty. The defaults exist to open the report WITH data (the same
    contract as the pick-list pre-select), so: probe the query with all
    defaults substituted; if it returns nothing and the date parameters
    bound a single column, ask the data for MIN/MAX of that column with
    the date conditions lifted, and make THAT the window - noted, and
    flagged for review."""
    import re as _re

    from pentaho_migration.reports.schema_agent import (
        preview_query, substitute_params)

    date_prms = [p for p in model.parameters
                 if p.value_type == "DateField" and p.default]
    if not (model.sql and model.jndi and date_prms):
        return
    params = [{"name": p.name, "default": p.default}
              for p in model.parameters]
    try:
        got = preview_query(model.jndi,
                            substitute_params(model.sql, params), limit=1)
        if got.get("rows") if isinstance(got, dict) else got:
            return                       # the authored window has data
    except Exception:
        return                           # unreachable/unqueryable - leave it

    # which column do the date parameters constrain?
    bounds = {}
    for prm in date_prms:
        m = _re.search(r"([\w.]+)\s*(>=|<=|>|<)\s*\$\{"
                       + _re.escape(prm.name) + r"\}", model.sql)
        if m:
            bounds[prm.name] = (m.group(1), m.group(2))
    columns = {c for c, _op in bounds.values()}
    if len(columns) != 1:
        return                           # zero or several date columns - stay out
    column = columns.pop()

    probe = model.sql
    for name, (col, op) in bounds.items():
        probe = _re.sub(_re.escape(col) + r"\s*" + _re.escape(op)
                        + r"\s*\$\{" + _re.escape(name) + r"\}",
                        "1=1", probe)
    probe = substitute_params(probe, params)
    probe = _re.sub(r"\bORDER\s+BY\b.*$", "", probe,
                    flags=_re.S | _re.I)
    short = column.split(".")[-1]
    try:
        got = preview_query(
            model.jndi,
            f"SELECT MIN({short}), MAX({short}) FROM ({probe}) PROBE_T",
            limit=1)
        rows = got.get("rows") if isinstance(got, dict) else got
    except Exception:
        return
    if not rows or rows[0][0] is None:
        return                           # no rows at ALL for these defaults
    span = {"start": str(rows[0][0])[:10], "end": str(rows[0][1])[:10]}
    authored = {}
    for prm in date_prms:
        col_op = bounds.get(prm.name)
        if not col_op:
            continue
        authored[prm.name] = prm.default
        edge = "start" if col_op[1] in (">=", ">") else "end"
        prm.default = f"{span[edge]} 00:00:00"
    if authored:
        was = ", ".join(f"{n}={v}" for n, v in authored.items())
        model.issues.append(
            "the authored date window returns NO rows on this connection "
            f"({was} - authored against the original estate's database); "
            f"the window is repointed to the data's own span for the "
            f"selected defaults ({span['start']}..{span['end']}) so the "
            "report opens with data - review the window before publishing")


def _fill_and_load(data, source_name, jndi=""):
    model = _load_upload(data, source_name, jndi)
    _fill_lov_defaults(model)
    _widen_empty_date_window(model)
    return model


def _looks_like_xaction(data: bytes) -> bool:
    return b"<action-sequence" in data[:4096]


def _load_upload(data: bytes, filename: str, jndi: str):
    """Size gate, then route by CONTENT: an OLE header means the .rpt binary,
    a zip is an xaction solution folder, an <action-sequence> root is an
    xaction, anything else is treated as a dump. Never by file extension."""
    from pentaho_migration.reports.rpt_extract import looks_like_rpt

    _check_upload_size(data)
    if looks_like_rpt(data[:8]):
        return _load_rpt_upload(data, filename, jndi)
    if data[:2] == b"PK":
        return _load_xaction_zip_upload(data, filename, jndi)
    if _looks_like_xaction(data):
        return _load_xaction_upload(data, filename, jndi)
    return _load_dump_upload(data, filename, jndi)


@router.post("/open-prd", dependencies=[Depends(require_api_key)])
def open_in_report_designer(dump: UploadFile, request: Request,
                                  jndi: str = "") -> dict:
    """Convert and open the result straight in the local Pentaho Report
    Designer - the demo's closing beat, one click instead of download +
    file-open. Starts a desktop process, so the same bounds as the Crystal
    viewer launcher apply: LOCAL callers only, a fixed executable, and the
    bundle is produced server-side by the same conversion the download uses."""
    import io as _io

    from pentaho_migration.reports.prd_launcher import open_in_prd, prd_available

    host = (request.client.host if request.client else "") or ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=403,
            detail="Report Designer can only be opened from the machine "
                   "running the app")
    reason = prd_available()
    if reason:
        raise HTTPException(status_code=503, detail=reason)
    data = dump.file.read()
    source_name = dump.filename or "upload.xml"
    model = _fill_and_load(data, source_name, jndi)
    buf = _io.BytesIO()
    with tempfile.NamedTemporaryFile(suffix=".prpt", delete=False) as tf:
        prpt_tmp = Path(tf.name)
    try:
        write_prpt(model, prpt_tmp, saved_rows=model.saved_rows)
        target = open_in_prd(prpt_tmp.read_bytes(), model.name)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        prpt_tmp.unlink(missing_ok=True)
    return {"opened": str(target),
            "embedded_rows": len(model.saved_rows.rows) if model.saved_rows else 0}


_gate_jobs = JobStore()

# the gate's stages, in order - the UI turns these into a progress bar
_GATE_STAGES = ["extracting", "rendering original", "rendering conversion",
                "comparing", "annotating", "done"]



@router.post("/consultant-report", include_in_schema=False)
def consultant_report(dump: UploadFile, jndi: str = "",
                      rate: float = 150.0) -> dict:
    """The single-report consultant report WITHOUT the release gate -
    the xaction family has no original render to compare against, and a
    Crystal report's consultant view should not be hostage to one
    either. Action plan + costed effort from the conversion itself."""
    from pentaho_migration.reports.consultant_report import (
        build_consultant_report, build_consultant_report_html)

    data = dump.file.read()
    source_name = dump.filename or "upload.xml"
    model = _fill_and_load(data, source_name, jndi)
    html = build_consultant_report_html(model, None, rate)
    markdown = build_consultant_report(
        model, source_name, f"{model.name}.prpt", None)
    return {
        "consultant_report_html": html,
        "consultant_report_markdown": markdown,
        "consultant_report_pdf": _consultant_pdf_base64(model, None, rate),
    }

def _no_original_detail(source_name: str) -> str:
    """The release check needs the ORIGINAL's render to compare against.
    What that means differs by family - say it in the family's own
    artifacts, not Crystal's."""
    name = (source_name or "").lower()
    if name.endswith((".xaction", ".zip")):
        return ("release check compares the converted output against the "
                "ORIGINAL's render. This report came from an .xaction + "
                ".report definition - rendering the original needs the old "
                "BI platform, which is not installed here, so there is "
                "nothing to compare against yet. The conversion itself is "
                "unaffected: review via PDF preview and the conversion "
                "report - downloads stay unlocked. (Zip the solution "
                "folder when uploading so the .xaction, its .report/.xml "
                "definition and .properties bundles stay together.)")
    return ("no original .rpt known for this report - drop the .rpt "
            "itself (or keep it beside the dump) so the release check "
            "has something to compare against")


@router.post("/release-check/start", dependencies=[Depends(require_api_key)])
def release_check_start(dump: UploadFile, jndi: str = "",
                              llm: bool = True, rate: float = 150.0) -> dict:
    """Start the release gate in the background: two full renders plus
    optional LLM annotation take minutes; poll /release-check/status for the
    staged progress the UI shows as a bar."""
    from pentaho_migration.reports.consultant_report import (
        build_consultant_report, build_consultant_report_html)
    from pentaho_migration.reports.release_check import (
        annotate_findings_with_llm, compare_renders, render_original_pdf)
    from pentaho_migration.reports.prpt_validator import (
        render_prpt_pdf, render_prpt_pdf_live, validator_available)
    from pentaho_migration.reports.rpt_viewer import find_original

    if not validator_available():
        raise HTTPException(status_code=503,
                            detail="no local PRD install to render the .prpt")
    data = dump.file.read()
    source_name = dump.filename or "upload.xml"
    original = find_original(source_name)
    if original is None:
        raise HTTPException(
            status_code=404,
            detail=_no_original_detail(source_name))

    job_id, job = _gate_jobs.start(stages=_GATE_STAGES)

    def run() -> None:
        try:
            model = _fill_and_load(data, source_name, jndi)
            job["stage"] = "rendering original"
            original_pdf = render_original_pdf(original)
            job["stage"] = "rendering conversion"
            with tempfile.TemporaryDirectory() as td:
                prpt = Path(td) / "converted.prpt"
                write_prpt(model, prpt, saved_rows=model.saved_rows)
                converted_pdf = (render_prpt_pdf_live(prpt)
                                 if model.saved_rows is not None
                                 else render_prpt_pdf(prpt))
            job["stage"] = "comparing"
            from pentaho_migration.reports.release_check import (
                _innermost_group_values)
            check = compare_renders(
                original_pdf, converted_pdf,
                group_values=_innermost_group_values(model))
            annotated = 0
            if llm and check.findings:
                job["stage"] = "annotating"
                annotated = annotate_findings_with_llm(check, model)
            markdown = build_consultant_report(
                model, source_name, f"{model.name}.prpt", check)
            job["result"] = {
                "verdict": check.verdict,
                "original_pages": check.original_pages,
                "converted_pages": check.converted_pages,
                "groups_checked": check.groups_checked,
                "groups_matching": check.groups_matching,
                "findings": [{"severity": f.severity, "code": f.code,
                              "message": f.message, "evidence": f.evidence,
                              "resolution": f.resolution}
                             for f in check.findings],
                "llm_annotated": annotated,
                "consultant_report_markdown": markdown,
                "consultant_report_html": build_consultant_report_html(
                    model, check, rate=rate),
                "consultant_report_pdf": _consultant_pdf_base64(
                    model, check, rate),
            }
            _persist_gate_verdict(source_name, check)
            job["stage"] = "done"
            job["status"] = "done"
        except Exception as exc:
            job["status"] = "error"
            job["detail"] = str(exc)
            logger.exception("release-check job %s failed", job_id)

    _gate_jobs.run(job, run)
    return {"job": job_id}


def _persist_gate_verdict(source_name: str, check) -> None:
    """Stamp the gate's SHIP/REVIEW into the project store when the
    uploaded source matches a batch-recorded report - the Project page
    then shows the estate's gate state, not just this session's. A
    report that was never batch-recorded simply isn't stamped."""
    import json as _json

    from pentaho_migration.project import (
        find_report_for_source, set_report_gate)

    try:
        record = find_report_for_source(source_name)
        if record is None:
            return
        set_report_gate(record.file, check.verdict, _json.dumps({
            "original_pages": check.original_pages,
            "converted_pages": check.converted_pages,
            "groups_checked": check.groups_checked,
            "groups_matching": check.groups_matching,
            "findings": [{"severity": f.severity, "code": f.code,
                          "message": f.message} for f in check.findings],
        }))
    except Exception:                      # persistence must never fail a gate
        logger.exception("gate verdict persistence failed for %s", source_name)


def _consultant_pdf_base64(model, check, rate) -> str:
    """The consultant report as a base64 PDF, ready for a download button.
    The whole document is a few kilobytes, so it rides in the job result
    beside the HTML rather than needing a second request - and a failure to
    build it must not lose the report formats that DID build."""
    import base64

    from pentaho_migration.reports.consultant_pdf import (
        build_consultant_report_pdf)
    try:
        return base64.b64encode(
            build_consultant_report_pdf(model, check, rate=rate)).decode()
    except Exception:
        logger.exception("consultant PDF failed for %s", model.name)
        return ""


@router.get("/release-check/status")
def release_check_status(job: str) -> dict:
    state = _gate_jobs.get(job)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown job - jobs live in memory, so a server restart forgets them; run the check again")
    return state


@router.post("/release-check", dependencies=[Depends(require_api_key)])
def release_check(dump: UploadFile, jndi: str = "",
                        llm: bool = True) -> dict:
    """The release gate: render the ORIGINAL .rpt (viewer, saved data) and
    the CONVERTED .prpt (engine, embedded data), compare deterministically,
    and annotate each finding with an LLM resolution-or-guidance note. The
    response carries the verdict, the findings, and the full consultant
    report (one document per migration). 503 when either side cannot render
    on this machine."""
    from pentaho_migration.reports.consultant_report import build_consultant_report
    from pentaho_migration.reports.release_check import (
        annotate_findings_with_llm, run_release_check)
    from pentaho_migration.reports.rpt_viewer import find_original

    data = dump.file.read()
    source_name = dump.filename or "upload.xml"
    model = _fill_and_load(data, source_name, jndi)
    original = find_original(source_name)
    if original is None:
        raise HTTPException(
            status_code=404,
            detail=_no_original_detail(source_name))
    check = run_release_check(model, original)
    if check.verdict == "UNAVAILABLE":
        raise HTTPException(status_code=503, detail=check.reason)
    annotated = annotate_findings_with_llm(check, model) if llm else 0
    markdown = build_consultant_report(
        model, source_name, f"{model.name}.prpt", check)
    return {
        "verdict": check.verdict,
        "original_pages": check.original_pages,
        "converted_pages": check.converted_pages,
        "findings": [{"severity": f.severity, "code": f.code,
                      "message": f.message, "evidence": f.evidence,
                      "resolution": f.resolution}
                     for f in check.findings],
        "llm_annotated": annotated,
        "consultant_report_markdown": markdown,
        "consultant_report_pdf": _consultant_pdf_base64(model, check, 150.0),
    }


@router.post("/preview", dependencies=[Depends(require_api_key)])
def preview(dump: UploadFile, jndi: str = "", format: str = "pdf"):
    """Preview through the real Pentaho Reporting engine. With embedded saved
    data the render is LIVE (real rows, no database); otherwise design-time
    (layout only). `format=pages` returns the pages as PNG images in JSON -
    browsers without an inline PDF plugin (embedded panes) show them anyway.
    503 when no local PRD install exists."""
    from fastapi.responses import Response as RawResponse

    from pentaho_migration.reports.prpt_validator import (
        render_prpt_pdf, render_prpt_pdf_live, validator_available)

    if not validator_available():
        raise HTTPException(
            status_code=503,
            detail="PDF preview needs a local Pentaho Report Designer + Java - "
                   "see `pentaho-migrate report-env`")
    data = dump.file.read()
    source_name = dump.filename or "upload.xml"
    model = _fill_and_load(data, source_name, jndi)
    safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in model.name).strip() or "report"
    with tempfile.TemporaryDirectory() as td:
        prpt = Path(td) / f"{safe}.prpt"
        write_prpt(model, prpt, saved_rows=model.saved_rows)
        try:
            # embedded rows make the live render self-sufficient - the preview
            # should show what PRD will show, which is the data
            pdf = (render_prpt_pdf_live(prpt) if model.saved_rows is not None
                   else render_prpt_pdf(prpt))
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
    # The group tree is no longer bolted on here: every group header carries
    # a `bookmark` band style, so the outline is INSIDE the bundle and shows
    # up wherever the report is rendered - Report Designer, the server, this
    # preview. Post-processing one on as well produced two of every entry.

    if format == "pages":
        return {"pages": _pdf_to_page_images(pdf),
                "embedded_rows": len(model.saved_rows.rows) if model.saved_rows else 0}
    return RawResponse(pdf, media_type="application/pdf",
                       headers={"Content-Disposition": f'inline; filename="{safe}.preview.pdf"'})


MAX_PREVIEW_PAGES = 12


def _pdf_to_page_images(pdf: bytes) -> list:
    """First pages of a PDF as base64 PNG data URLs (pypdfium2, permissive
    license). Raises 503 when the rasterizer is unavailable - the UI then
    falls back to the browser's own PDF display."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="page-image preview needs pypdfium2 (pip install pypdfium2)")
    import io as _io

    doc = pdfium.PdfDocument(pdf)
    pages = []
    try:
        total = len(doc)
        for i in range(min(total, MAX_PREVIEW_PAGES)):
            import time as _time
            _time.sleep(0)   # yield the GIL between pages - keep the app painting
            bitmap = doc[i].render(scale=1.4)
            buf = _io.BytesIO()
            bitmap.to_pil().save(buf, format="PNG")
            pages.append("data:image/png;base64,"
                         + base64.b64encode(buf.getvalue()).decode("ascii"))
    finally:
        doc.close()
    return pages


@router.get("/samples", include_in_schema=False)
def samples() -> list:
    """The demo reports the Try picker offers - name, label, description and
    the datasource each binds to."""
    return _demo_dumps()


@router.get("/sample", include_in_schema=False)
def sample(name: str = "") -> FileResponse:
    """A Crystal demo dump for the Try button. `name` selects one of the demo
    reports (see /samples); omitted or unknown, it returns the default."""
    return FileResponse(_demo_file(name), media_type="text/xml")


# The xactions the "Try Xactions" picker offers - each a MEASURED story from
# the steel-wheels corpus, spanning the complexity ladder the T&M model uses.
_XACTION_DEMO_META = [
    {"name": "order_detail",
     "label": "Order details — the walkthrough",
     "description": "One SQL query straight into the old JFreeReport "
                    "definition: groups, formats and $() messages carry over. "
                    "Complexity: Low."},
    {"name": "Income Statement",
     "label": "Income statement — implicit wiring",
     "description": "The report definition binds by the platform's naming "
                    "convention, not an explicit resource. Complexity: Low."},
    {"name": "Sales_by_Supplier",
     "label": "Sales by supplier — static pick-lists",
     "description": "Prompts whose pick-lists are hardcoded property-map "
                    "lists — they become PRD list parameters. Complexity: "
                    "Medium."},
    {"name": "Sales_by_Customer",
     "label": "Sales by customer — query pick-lists",
     "description": "Prompts fed by their own SQL lookups, plus JavaScript "
                    "glue — query-backed parameters with the SQL carried in "
                    "the notes. Complexity: Medium."},
    {"name": "BurstSales",
     "label": "Burst sales — the honesty demo",
     "description": "A bursting pipeline: template, JavaScript, a report "
                    "render and an EMAIL per row — the render converts, the "
                    "distribution becomes a suggested PDI job. Complexity: "
                    "High."},
    {"name": "Inventory List",
     "label": "Inventory list — the legacy-EXT format",
     "description": "The OTHER old definition dialect (report-definition "
                    "root): styled object graphs, traffic-light stock "
                    "formatting, HASCHANGED vendor grouping — all translated. "
                    "Complexity: Medium."},
    {"name": "Variance Report",
     "label": "Variance report — the full works",
     "description": "Legacy-EXT with everything: JavaScript-computed years "
                    "evaluated at conversion, SQL fragments substituted, a "
                    "multi-select territory prompt, trend arrows as stacked "
                    "conditional images, ported row banding and a "
                    "three-series chart. Complexity: Medium."},
]


def _xaction_file(name: str) -> Path:
    """The corpus .xaction for a picker name. Traversal-guarded: only a plain
    stem that resolves inside the xactions tree is honoured."""
    stem = (name or "").strip()
    if stem and "/" not in stem and "\\" not in stem and ".." not in stem:
        for hit in XACTION_DIR.rglob(f"{stem}.xaction"):
            return hit
    for hit in XACTION_DIR.rglob("order_detail.xaction"):
        return hit
    raise HTTPException(status_code=404, detail="no xaction samples on disk")


@router.get("/xaction-samples", include_in_schema=False)
def xaction_samples() -> list:
    """The demo xactions the Try picker offers."""
    return [m for m in _XACTION_DEMO_META
            if next(XACTION_DIR.rglob(f"{m['name']}.xaction"), None)]


@router.get("/xaction-sample", include_in_schema=False)
def xaction_sample(name: str = "") -> FileResponse:
    """A demo .xaction for the Try button; its report definition resolves
    server-side from the same corpus tree."""
    path = _xaction_file(name)
    return FileResponse(path, media_type="text/xml", filename=path.name)


@router.post("/inspect", response_model=ReportSummary,
             dependencies=[Depends(require_api_key)])
def inspect(dump: UploadFile, jndi: str = "") -> ReportSummary:
    """Parse an RptToXml dump and translate its formulas, without converting."""
    model = _fill_and_load(dump.file.read(), dump.filename or "upload.xml", jndi)
    return _summarize(model, dump.filename or "upload.xml")


def _build_response(model, source_name: str) -> ReportConversionResponse:
    safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in model.name).strip() or "report"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"{safe}.prpt"
        write_prpt(model, out, saved_rows=model.saved_rows)
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
def convert(dump: UploadFile, jndi: str = "",
                  sql_override: str = Form("")) -> ReportConversionResponse:
    """Full conversion: parse -> translate -> .prpt bundle + conversion report.

    `sql_override` replaces the report SQL (used by the schema assistant's
    reviewed proposals); the substitution is recorded as a review item."""
    started = time.monotonic()
    data = dump.file.read()
    source_name = dump.filename or "upload.xml"
    model = _fill_and_load(data, source_name, jndi)
    if sql_override.strip():
        model.sql = sql_override.strip()
        model.issues.append(
            "report SQL replaced via the schema assistant - review the query")
    response = _build_response(model, source_name)
    logger.info("reports/convert file=%s bytes=%d formulas=%d elapsed_ms=%d",
                source_name, len(data), len(model.formulas),
                (time.monotonic() - started) * 1000)
    return response


# ----------------------------------------------------- schema-aware SQL agent

class SqlParameterInfo(BaseModel):
    name: str
    default: str = ""


class SqlCheckRequest(BaseModel):
    jndi: str
    sql: str
    parameters: list[SqlParameterInfo] = []


class SqlChatTurn(BaseModel):
    role: str              # user | assistant
    content: str


class SqlChatRequest(BaseModel):
    jndi: str
    sql: str
    question: str
    parameters: list[SqlParameterInfo] = []
    history: list[SqlChatTurn] = []


@router.get("/connections", dependencies=[Depends(require_api_key)])
def connections() -> list[dict]:
    """The JNDI connections defined in the simple-jndi config the reporting
    engine reads - what the Inspect page's connection picker offers."""
    from pentaho_migration.reports.schema_agent import list_jndi_connections

    return list_jndi_connections()


class ConnectionRequest(BaseModel):
    name: str
    url: str
    driver: str = ""
    user: str = ""
    password: str = ""


@router.post("/connections", dependencies=[Depends(require_api_key)])
def save_connection(req: ConnectionRequest) -> dict:
    """Create or update a JNDI connection in the user's simple-jndi file
    (~/.pentaho/simple-jndi) - the same file the reporting engine reads."""
    from pentaho_migration.reports.schema_agent import (
        list_jndi_connections, save_jndi_connection)

    try:
        save_jndi_connection(req.name, req.url, req.driver, req.user, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"saved": req.name, "connections": list_jndi_connections()}


@router.delete("/connections/{name}", dependencies=[Depends(require_api_key)])
def delete_connection(name: str) -> dict:
    """Delete a JNDI connection from the user's simple-jndi file. A name
    defined in the PRD install's own config is not touched."""
    from pentaho_migration.reports.schema_agent import (
        delete_jndi_connection, list_jndi_connections, resolve_jndi)

    removed = delete_jndi_connection(name)
    if not removed:
        detail = ("connection not found in the user's simple-jndi file"
                  + (" (it is defined in the PRD install's config - edit that "
                     "file directly)" if resolve_jndi(name) else ""))
        raise HTTPException(status_code=404, detail=detail)
    return {"deleted": name, "connections": list_jndi_connections()}


@router.get("/schema", dependencies=[Depends(require_api_key)])
def schema(jndi: str) -> dict:
    """Introspect the JNDI target database (tables + columns). Deterministic:
    reads the same simple-jndi config the reporting engine uses."""
    try:
        return probe_schema(jndi)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/sql/check", dependencies=[Depends(require_api_key)])
def sql_check(req: SqlCheckRequest) -> dict:
    """Deterministic SQL validation: EXPLAIN the query (parameters
    substituted with their defaults) against the live JNDI target."""
    return validate_sql(req.jndi, req.sql,
                        [p.model_dump() for p in req.parameters])


@router.post("/sql/preview", dependencies=[Depends(require_api_key)])
def sql_preview(req: SqlCheckRequest) -> dict:
    """Execute the report's SELECT against the live JNDI target and return
    the first 50 rows - the Inspect page's dataset preview. SELECT-only."""
    from pentaho_migration.reports.schema_agent import preview_query

    try:
        return preview_query(req.jndi, req.sql,
                             [p.model_dump() for p in req.parameters])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc).splitlines()[0])


@router.post("/sql/chat", dependencies=[Depends(require_api_key)])
def sql_chat(req: SqlChatRequest) -> dict:
    """Schema-grounded SQL chat: the LLM sees the real schema, the report
    SQL, and the deterministic validation verdict; proposed SQL comes back
    for review, never auto-applied."""
    assistant = SqlAssistant()
    try:
        assistant.check_provider()
    except TranslationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    parameters = [p.model_dump() for p in req.parameters]
    try:
        schema_text = schema_context(probe_schema(req.jndi))
        validation = validate_sql(req.jndi, req.sql, parameters)
    except RuntimeError as exc:
        schema_text = f"(schema unavailable: {exc})"
        validation = None
    try:
        result = assistant.ask(req.question, req.sql, schema_text,
                               validation=validation,
                               history=[t.model_dump() for t in req.history])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}")
    result["validation"] = validation
    return result


@router.post("/parity", dependencies=[Depends(require_api_key)])
def parity(dump: UploadFile, reference: UploadFile, jndi: str = "") -> dict:
    """Measured output parity: convert the dump, render it against the live
    JNDI database, and diff its numbers against the customer's Crystal export
    (PDF or CSV). 503 when the environment cannot render."""
    from pentaho_migration.reports.parity import (
        compare_numbers, numbers_from_csv, numbers_from_pdf)
    from pentaho_migration.reports.prpt_validator import (
        render_prpt_pdf_live, validator_available)

    if not validator_available():
        raise HTTPException(status_code=503,
                            detail="parity needs a local PRD install + Java")
    model = _fill_and_load(dump.file.read(), dump.filename or "upload.xml", jndi)
    ref_data = reference.file.read()
    ref_name = (reference.filename or "").lower()
    try:
        ref_numbers = (numbers_from_csv(ref_data) if ref_name.endswith(".csv")
                       else numbers_from_pdf(ref_data))
        with tempfile.TemporaryDirectory() as td:
            prpt = Path(td) / "parity.prpt"
            write_prpt(model, prpt, saved_rows=model.saved_rows)
            rendered = numbers_from_pdf(render_prpt_pdf_live(prpt))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    result = compare_numbers(ref_numbers, rendered)
    return {"verdict": result.verdict, "note": result.note,
            "matched": result.matched, "reference_total": result.reference_total,
            "rendered_total": result.rendered_total,
            "missing": result.missing, "extra": result.extra}


_assist_jobs = JobStore()


@router.post("/translate/start", dependencies=[Depends(require_api_key)])
def translate_start(dump: UploadFile, jndi: str = "") -> dict[str, str]:
    """LLM-assist the formulas the deterministic translator flagged manual.

    Runs in the background (local models can take minutes); poll
    /reports/translate/status. The finished job carries a full conversion
    response with the assisted formulas baked into the .prpt."""
    try:
        translator = ExpressionTranslator()
        translator._check_provider()
    except TranslationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    data = dump.file.read()
    source_name = dump.filename or "upload.xml"
    model = _fill_and_load(data, source_name, jndi)

    job_id, job = _assist_jobs.start(
        stages=["translating", "rebuilding bundle", "done"],
        done=0, total=0, translated=0)

    def run() -> None:
        def progress(done: int, total: int) -> None:
            job["done"], job["total"] = done, total

        job["translated"] = translate_manual_formulas(
            model, translator=translator, progress=progress)
        job["stage"] = "rebuilding bundle"
        job["result"] = _build_response(model, source_name).model_dump()

    _assist_jobs.run(job, run)
    return {"job": job_id}


@router.get("/translate/status")
def translate_status(job: str) -> dict:
    """Progress of a formula-assist job; includes the full result when done."""
    state = _assist_jobs.get(job)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown translation job - jobs live in memory, so a server restart forgets them; start it again")
    return state


# --------------------------------------------------------- original .rpt viewer

class ViewOriginalRequest(BaseModel):
    dump: str          # the dump's file name; the .rpt is matched by stem


@router.get("/original")
def original_status(dump: str) -> dict:
    """Can the ORIGINAL Crystal report for this dump be opened locally?
    Drives the Inspect page's 'view original' button."""
    from pentaho_migration.reports.rpt_viewer import describe

    return describe(dump)


@router.post("/original/open", dependencies=[Depends(require_api_key)])
def open_original_report(req: ViewOriginalRequest, request: Request) -> dict:
    """Launch the local Crystal viewer on the original .rpt.

    This starts a desktop process, so it is deliberately narrow: LOCAL callers
    only (the review UI runs on the consultant's own machine), a fixed viewer
    executable, and a path that must resolve to a .rpt inside the allowed
    sample roots — see reports/rpt_viewer.py."""
    from pentaho_migration.reports.rpt_viewer import find_original, open_original

    host = (request.client.host if request.client else "") or ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=403,
            detail="the report viewer can only be opened from the machine "
                   "running the app")
    original = find_original(req.dump)
    if original is None:
        raise HTTPException(
            status_code=404,
            detail="no .rpt binary for this report — authored dumps have no "
                   "Crystal original; only extracted reports can be opened")
    try:
        open_original(original)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"opened": str(original)}
