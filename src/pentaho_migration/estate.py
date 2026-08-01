"""Estate mode: the whole engagement through the web app.

Two halves, both driven from the Project page as staged jobs:

  * batch_convert_files - the CLI `batch` / `report-batch` loops for a
    LIST OF UPLOADS: every file routes by CONTENT (an ETL export, a
    Talend item, an RptToXml dump, an .rpt binary, an .xaction, a
    solution-folder zip), the source is saved under config/estate/ so
    sweeps and re-opens keep working after the browser closes, and the
    result lands in the project store exactly as the CLI records it.

  * build_deliverable_pack - the engagement hand-over as ONE zip:
    every stored source re-converted (deterministic - conversion needs
    no JVM render), each artifact beside its per-migration consultant
    report, both portfolio reports, and a manifest. What fails to
    convert is listed in the manifest rather than silently dropped.
"""

import io
import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path

from pentaho_migration.project import (
    REPO_ROOT, MappingRecord, ReportRecord, list_mappings, list_reports,
    record_mapping, record_report, resolve_source_path,
)

logger = logging.getLogger("pentaho_migration.estate")

ESTATE_DIR = REPO_ROOT / "config" / "estate"

ETL_MARKERS = (b"<POWERMART", b"<REPOSITORY", b"talendfile:", b"<talendfile")
REPORT_MARKERS = (b"<Report", b"<action-sequence")


def _classify(name: str, data: bytes) -> str:
    """etl | report | unknown - by CONTENT, never extension (the same
    contract as the upload endpoints)."""
    head = data[:8192]
    if head.startswith(b"\xd0\xcf\x11\xe0"):          # OLE2 = .rpt binary
        return "report"
    if head[:2] == b"PK":                             # solution-folder zip
        return "report"
    if any(m in head for m in ETL_MARKERS):
        return "etl"
    if any(m in head for m in REPORT_MARKERS):
        return "report"
    if name.lower().endswith(".item"):
        return "etl"
    return "unknown"


def _save_source(name: str, data: bytes) -> Path:
    """Persist an uploaded source under config/estate/ (gitignored with
    the rest of config/) so the store's source_path outlives the upload.
    Name collisions overwrite - re-uploading an export IS the refresh."""
    ESTATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = Path(name).name or "upload"
    target = ESTATE_DIR / safe
    target.write_bytes(data)
    return target


def _convert_etl(path: Path) -> tuple[int, list[str]]:
    """One ETL export into the store - the CLI `batch` loop."""
    from pentaho_migration.mapper import RulesMapper
    from pentaho_migration.parser import detect_parser
    from pentaho_migration.validator import (
        build_impact_analysis, build_report, build_score)

    parser = detect_parser(path)
    pipelines = [RulesMapper.for_pipeline(p).apply(p)
                 for p in parser.parse_file(path)]
    names = []
    for pipeline in pipelines:
        report = build_report(pipeline)
        score = build_score(pipeline, build_impact_analysis(pipeline))
        record_mapping(MappingRecord(
            mapping=pipeline.name, file=path.name,
            source_path=str(path.resolve()), steps=report.total_steps,
            auto=report.auto, review=report.review, manual=report.manual,
            expressions=report.untranslated_expressions,
            score=score.score, grade=score.grade,
            status="converted", updated_at=""))
        names.append(pipeline.name)
    return len(names), names


def _convert_report(path: Path, data: bytes, jndi: str) -> str:
    """One report source into the store - the CLI `report-batch` loop,
    through the SAME content-routing choke point the upload flow uses
    (.rpt extraction, zip solution folders, xactions, dumps)."""
    from pentaho_migration.reports.api import _load_upload
    from pentaho_migration.reports.effort import (
        build_report_effort, count_todos)

    model = _load_upload(data, path.name, jndi)
    counts = {"auto": 0, "review": 0, "manual": 0}
    for formula in model.formulas.values():
        counts[formula.status] += 1
    effort = build_report_effort(model)
    record_report(ReportRecord(
        file=path.name, name=model.name, source_path=str(path.resolve()),
        formulas_auto=counts["auto"], formulas_review=counts["review"],
        formulas_manual=counts["manual"], todos=count_todos(model),
        copilot_hours=effort.copilot_hours,
        manual_hours=effort.manual_hours,
        status="converted", updated_at=""))
    return model.name


def batch_convert_files(uploads: list[tuple[str, bytes]], jndi: str = "",
                        progress=None) -> dict:
    """Convert every (name, bytes) upload into the project store.
    Returns the summary the UI shows; per-file failures are findings in
    the summary, never a crash that loses the rest of the estate."""
    done = {"etl_mappings": 0, "reports": 0, "failed": [], "skipped": []}
    for i, (name, data) in enumerate(uploads):
        if progress:
            progress(i, len(uploads), name)
        kind = _classify(name, data)
        try:
            if kind == "etl":
                path = _save_source(name, data)
                n, _names = _convert_etl(path)
                done["etl_mappings"] += n
            elif kind == "report":
                path = _save_source(name, data)
                _convert_report(path, data, jndi)
                done["reports"] += 1
            else:
                done["skipped"].append(
                    f"{name}: not a recognised export "
                    "(PowerCenter/Talend/RptToXml/.rpt/.xaction/zip)")
        except Exception as exc:
            logger.exception("estate convert failed for %s", name)
            done["failed"].append(f"{name}: {str(exc)[:160]}")
    if progress:
        progress(len(uploads), len(uploads), "")
    return done


# ------------------------------------------------------------------ pack

def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in " ._-" else "_"
                   for c in name).strip() or "unnamed"


def _pack_etl(zf: zipfile.ZipFile, rate: float, progress, offset: int,
              total: int) -> tuple[int, list[str]]:
    from pentaho_migration.etl_consultant import (
        build_etl_consultant_report_html, build_etl_consultant_report_markdown)
    from pentaho_migration.generator import KtrGenerator
    from pentaho_migration.mapper import RulesMapper
    from pentaho_migration.parser import detect_parser
    from pentaho_migration.validator import (
        build_effort, build_impact_analysis, build_report, build_score)
    from pentaho_migration.validator.review import review_pipeline

    generator = KtrGenerator()
    packed, failures = 0, []
    by_source: dict = {}
    records = list_mappings()
    for i, record in enumerate(records):
        if progress:
            progress(offset + i, total, f"{record.file} · {record.mapping}")
        source = resolve_source_path(record.source_path)
        if source is None:
            failures.append(f"{record.file}/{record.mapping}: source export "
                            "not found")
            continue
        try:
            if source not in by_source:
                parser = detect_parser(source)
                pipelines = [RulesMapper.for_pipeline(p).apply(p)
                             for p in parser.parse_file(source)]
                by_source[source] = {p.name: p for p in pipelines}
            pipeline = by_source[source].get(record.mapping)
            if pipeline is None:
                failures.append(f"{record.file}/{record.mapping}: mapping no "
                                "longer present in the export")
                continue
            ktr = generator.generate(pipeline)
            check = review_pipeline(pipeline, ktr=ktr)
            report = build_report(pipeline)
            impact = build_impact_analysis(pipeline)
            score = build_score(pipeline, impact)
            effort = build_effort(pipeline, report)
            base = f"etl/{_safe(Path(record.file).stem)}/{_safe(record.mapping)}"
            zf.writestr(f"{base}.ktr", ktr)
            zf.writestr(f"{base}.consultant.html",
                        build_etl_consultant_report_html(
                            pipeline, report, score, effort, check,
                            rate=rate, impact=impact))
            zf.writestr(f"{base}.consultant.md",
                        build_etl_consultant_report_markdown(
                            pipeline, report, score, effort, check,
                            rate=rate))
            packed += 1
        except Exception as exc:
            logger.exception("pack failed for %s/%s", record.file,
                             record.mapping)
            failures.append(f"{record.file}/{record.mapping}: {str(exc)[:120]}")
    return packed, failures


def _pack_reports(zf: zipfile.ZipFile, jndi: str, rate: float, progress,
                  offset: int, total: int) -> tuple[int, list[str]]:
    from pentaho_migration.reports import build_conversion_report, write_prpt
    from pentaho_migration.reports.api import _load_upload
    from pentaho_migration.reports.consultant_report import (
        build_consultant_report_html)

    packed, failures = 0, []
    records = list_reports()
    for i, record in enumerate(records):
        if progress:
            progress(offset + i, total, record.file)
        source = (Path(record.source_path)
                  if record.source_path else None)
        if source is None or not source.is_file():
            failures.append(f"{record.file}: source dump not found")
            continue
        try:
            # the SAME content router the upload flow uses - dumps, .rpt
            # binaries, xactions and solution-folder zips all pack
            model = _load_upload(source.read_bytes(), source.name, jndi)
            base = f"reports/{_safe(model.name)}"
            buffer = io.BytesIO()
            write_prpt(model, buffer, saved_rows=model.saved_rows)
            zf.writestr(f"{base}.prpt", buffer.getvalue())
            zf.writestr(f"{base}.consultant.html",
                        build_consultant_report_html(model, None, rate))
            zf.writestr(f"{base}.conversion.md",
                        build_conversion_report(model, source,
                                                f"{model.name}.prpt"))
            packed += 1
        except Exception as exc:
            logger.exception("pack failed for report %s", record.file)
            failures.append(f"{record.file}: {str(exc)[:120]}")
    return packed, failures


def build_deliverable_pack(out_path: Path, jndi: str = "",
                           rate: float = 150.0, progress=None) -> dict:
    """The engagement hand-over: one zip with every converted artifact,
    its consultant report beside it, the portfolio reports, and a
    manifest that says exactly what is inside and what failed."""
    from pentaho_migration import __version__

    mappings = list_mappings()
    reports = list_reports()
    total = len(mappings) + len(reports)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        etl_packed, etl_failures = _pack_etl(zf, rate, progress, 0, total)
        rep_packed, rep_failures = _pack_reports(
            zf, jndi, rate, progress, len(mappings), total)

        # portfolio reports - one per family that has content
        try:
            from types import SimpleNamespace

            from pentaho_migration.etl_portfolio import (
                build_etl_portfolio_report_html)
            from pentaho_migration.validator.effort import effort_from_counts

            def _with_effort(r):
                effort = effort_from_counts(
                    steps=r.steps, auto=r.auto, review=r.review,
                    manual=r.manual, untranslated_exprs=r.expressions)
                return SimpleNamespace(**r.model_dump(),
                                       copilot_hours=effort.copilot_hours,
                                       manual_hours=effort.manual_hours,
                                       saved_hours=effort.saved_hours)

            for family in ("informatica", "talend"):
                rows = [_with_effort(r) for r in mappings
                        if (r.file.lower().endswith(".item"))
                        == (family == "talend")]
                if rows:
                    zf.writestr(
                        f"portfolio/{family}_portfolio.html",
                        build_etl_portfolio_report_html(
                            rows, family=family, rate=rate))
        except Exception:
            logger.exception("etl portfolio failed for the pack")
        if reports:
            try:
                from pentaho_migration.reports.portfolio_report import (
                    build_portfolio_report_html)
                from pentaho_migration.reports.triage import triage_one
                results = [triage_one(Path(r.source_path), jndi=jndi,
                                      check_sql=False)
                           for r in reports
                           if r.source_path and Path(r.source_path).is_file()]
                if results:
                    zf.writestr("portfolio/reports_portfolio.html",
                                build_portfolio_report_html(
                                    results, rate=rate, jndi=jndi))
            except Exception:
                logger.exception("reports portfolio failed for the pack")

        failures = etl_failures + rep_failures
        manifest = {
            "generated": datetime.now().isoformat(timespec="seconds"),
            "copilot_version": __version__,
            "etl_mappings_packed": etl_packed,
            "reports_packed": rep_packed,
            "failures": failures,
            "rate_per_hour": rate,
        }
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
        zf.writestr("README.txt", (
            "Pentaho Migration Copilot - engagement deliverable pack\n"
            f"Generated {manifest['generated']} by Copilot v{__version__}\n\n"
            f"etl/       {etl_packed} converted mapping(s): .ktr beside its "
            "consultant report (.html prints to PDF)\n"
            f"reports/   {rep_packed} converted report(s): .prpt beside its "
            "consultant report and conversion work-list\n"
            "portfolio/ the estate-level consultant reports\n"
            "MANIFEST.json lists counts and anything that failed to "
            "convert - failures are findings, not omissions.\n"))
    if progress:
        progress(total, total, "")
    return {"etl_mappings_packed": etl_packed, "reports_packed": rep_packed,
            "failures": failures, "bytes": out_path.stat().st_size}
