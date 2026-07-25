"""Command-line interface for the services team (Phase 0).

    pentaho-migrate parse   <export.xml>            # inspect what the parser sees
    pentaho-migrate convert <export.xml> -o out/    # full parse -> map -> generate
"""

from pathlib import Path

import typer

from pentaho_migration.generator import KjbGenerator, KtrGenerator
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import detect_parser
from pentaho_migration.validator import (
    assess_source,
    build_effort,
    build_gap_report,
    build_impact_analysis,
    build_report,
    build_score,
)

app = typer.Typer(help="Pentaho Migration Copilot: legacy ETL and BI reports -> Pentaho.")


@app.command()
def parse(export: Path) -> None:
    """Parse a source export (PowerCenter .xml or Talend .item) and print the IR."""
    for pipeline in detect_parser(export).parse_file(export):
        typer.echo(pipeline.model_dump_json(indent=2))


@app.command()
def convert(
    export: Path,
    out_dir: Path = typer.Option(
        Path("output/informatica"), "--out", "-o",
        help="Directory for .ktr files (each named after its source mapping)",
    ),
    translate: bool = typer.Option(
        False, "--translate", "-t",
        help="Translate expressions via the configured LLM provider (see Settings)",
    ),
    rate: float = typer.Option(
        150.0, "--rate", help="Consultant rate per hour, for the effort estimate",
    ),
) -> None:
    """Convert a source export (PowerCenter/Talend) to PDI .ktr + migration report."""
    parser = detect_parser(export)
    generator = KtrGenerator()
    pipelines = [
        RulesMapper.for_pipeline(p).apply(p) for p in parser.parse_file(export)
    ]

    if translate:
        from pentaho_migration.llm import ExpressionTranslator, TranslationError

        try:
            translator = ExpressionTranslator()
            for pipeline in pipelines:
                count = translator.translate_pipeline(pipeline)
                typer.echo(f"translated {count} expression(s) in {pipeline.name}")
        except TranslationError as exc:
            typer.echo(f"translation unavailable: {exc}", err=True)

    source = assess_source(parser.analyze_export(export), pipelines)
    typer.echo(
        f"source: {source.tool} {source.product_version or '?'} "
        f"(repository {source.repository_version or '?'}), "
        f"{source.database_type or 'unknown db'}, exported {source.creation_date or '?'}"
    )
    for warning in source.warnings:
        typer.echo(f"  [{warning.level.value}] {warning.text}")

    for pipeline in pipelines:
        out_path = generator.write(pipeline, out_dir)
        report = build_report(pipeline)
        score = build_score(pipeline, build_impact_analysis(pipeline))
        typer.echo(f"{pipeline.name} -> {out_path}")
        typer.echo(
            f"  steps: {report.total_steps}  auto: {report.auto}  "
            f"review: {report.review}  manual: {report.manual}  "
            f"expressions to translate: {report.untranslated_expressions}"
        )
        typer.echo(
            f"  confidence: {score.score}/100 ({score.grade}, static) — {score.verdict}"
        )
        effort = build_effort(pipeline, report)
        typer.echo(
            f"  effort: ~{effort.copilot_hours:g}h with Copilot vs "
            f"~{effort.manual_hours:g}h manual rebuild — saves "
            f"{effort.saved_hours:g}h ({effort.saved_pct}%, ~${effort.saved_hours * rate:,.0f} at ${rate:g}/h)"
        )

    kjb_generator = KjbGenerator()
    for job in (parser.parse_workflows(export) if hasattr(parser, "parse_workflows") else []):
        kjb_path = kjb_generator.write(job, out_dir)
        sessions = sum(1 for e in job.entries if e.task_type == "Session")
        placeholders = sum(
            1 for e in job.entries if e.task_type not in ("Session", "Start")
        )
        typer.echo(
            f"{job.name} -> {kjb_path}  "
            f"({sessions} session(s) wired to .ktr files, {placeholders} placeholder(s) to review)"
        )


@app.command()
def sandbox(
    export: Path,
    out_dir: Path = typer.Option(
        Path("output/informatica"), "--out", "-o",
        help="Kits are written to <out>/sandbox/<mapping>/",
    ),
    rows: int = typer.Option(25, "--rows", help="Synthetic rows per source CSV"),
) -> None:
    """Generate sandbox test kits: setup guide, CREATE TABLE DDL, synthetic CSVs."""
    from pentaho_migration.sandbox import build_sandbox_kit, write_kit

    for pipeline in detect_parser(export).parse_file(export):
        RulesMapper.for_pipeline(pipeline).apply(pipeline)
        kit = build_sandbox_kit(pipeline, rows=rows)
        kit_dir = write_kit(kit, out_dir)
        typer.echo(
            f"{pipeline.name} -> {kit_dir}  "
            f"(setup.md, setup.sql, {len(kit.data)} data file(s))"
        )


@app.command()
def batch(
    directory: Path = typer.Argument(Path("samples/informatica")),
    out_dir: Path = typer.Option(Path("output/informatica"), "--out", "-o"),
    translate: bool = typer.Option(
        False, "--translate", "-t",
        help="Also translate expressions via the configured LLM (slow: one call "
             "per non-trivial expression — plan hours for a large corpus)",
    ),
) -> None:
    """Convert every export in DIRECTORY (one subfolder per export file) and
    record each mapping in the migration project store."""
    from pentaho_migration.project import MappingRecord, record_mapping

    generator = KtrGenerator()
    kjb_generator = KjbGenerator()
    translator = None
    if translate:
        from pentaho_migration.llm import ExpressionTranslator, TranslationError

        try:
            translator = ExpressionTranslator()
            translator._check_provider()
        except TranslationError as exc:
            typer.echo(f"translation unavailable: {exc}", err=True)
            raise typer.Exit(code=2)

    total = failures = 0
    scores: list[int] = []

    files = sorted([*directory.glob("*.xml"), *directory.glob("*.item")])
    for xml in files:
        try:
            parser = detect_parser(xml)
            pipelines = [
                RulesMapper.for_pipeline(p).apply(p) for p in parser.parse_file(xml)
            ]
        except Exception as exc:
            failures += 1
            typer.echo(f"{xml.name}: PARSE FAILED — {exc}", err=True)
            continue
        for pipeline in pipelines:
            if translator is not None:
                translated = translator.translate_pipeline(pipeline)
                typer.echo(f"  {pipeline.name}: translated {translated} expression(s)")
            generator.write(pipeline, out_dir / xml.stem)
            report = build_report(pipeline)
            score = build_score(pipeline, build_impact_analysis(pipeline))
            record_mapping(MappingRecord(
                mapping=pipeline.name, file=xml.name,
                source_path=str(xml.resolve()), steps=report.total_steps,
                auto=report.auto, review=report.review, manual=report.manual,
                expressions=report.untranslated_expressions,
                score=score.score, grade=score.grade,
                status="converted", updated_at="",
            ))
            scores.append(score.score)
            total += 1
        for job in (parser.parse_workflows(xml) if hasattr(parser, "parse_workflows") else []):
            kjb_generator.write(job, out_dir / xml.stem)
    avg = round(sum(scores) / len(scores)) if scores else 0
    typer.echo(
        f"batch complete: {total} mappings converted "
        f"({failures} file failures), avg confidence {avg}/100 — "
        f"see `pentaho-migrate project` or the Project page"
    )


@app.command()
def run(
    artifact: Path = typer.Argument(..., help="A generated .ktr or .kjb file"),
    timeout: int = typer.Option(600, "--timeout", help="Seconds before aborting"),
) -> None:
    """Execute a generated .ktr (Pan) or .kjb (Kitchen) in the local PDI install."""
    from pentaho_migration.pdi_runner import find_pdi_home, run_artifact

    pdi_home = find_pdi_home()
    if pdi_home is None:
        typer.echo(
            "no PDI installation found — set PDI_HOME or install to a standard location",
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo(f"using PDI at {pdi_home}")
    result = run_artifact(artifact, pdi_home, timeout=timeout)
    typer.echo(f"exit {result.exit_code} ({result.meaning})")
    typer.echo(result.log_tail)
    raise typer.Exit(code=0 if result.ok else 1)


@app.command()
def diff(
    expected: Path = typer.Argument(..., help="CSV output of the ORIGINAL pipeline"),
    actual: Path = typer.Argument(..., help="CSV output of the CONVERTED pipeline"),
    key: str = typer.Option(None, "--key", "-k", help="Column to match rows by"),
) -> None:
    """Measured output parity: diff original vs converted pipeline output."""
    from pentaho_migration.validator.diff import DiffError, compare_csv

    try:
        report = compare_csv(
            expected.read_text(encoding="utf-8-sig"),
            actual.read_text(encoding="utf-8-sig"),
            key=key,
        )
    except DiffError as exc:
        typer.echo(f"cannot compare: {exc}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"{report.verdict}")
    typer.echo(
        f"parity: {report.parity:.1%}  rows: {report.expected_rows}/{report.actual_rows}  "
        f"matching: {report.matching_rows}  mismatched: {report.mismatched_rows}  "
        f"missing: {report.missing_rows}  extra: {report.extra_rows}"
    )
    for column in report.columns:
        typer.echo(f"  column {column.column}: {column.mismatches} mismatch(es)")
    for sample in report.samples[:10]:
        typer.echo(f"  row {sample.row} [{sample.column}]: '{sample.expected}' != '{sample.actual}'")
    raise typer.Exit(code=0 if report.parity >= 0.999 else 1)


@app.command()
def project() -> None:
    """Show the migration project: every batch-converted mapping and its status."""
    from pentaho_migration.project import list_mappings

    records = list_mappings()
    if not records:
        typer.echo("project store is empty — run `pentaho-migrate batch <dir>` first")
        return
    by_status: dict[str, int] = {}
    for r in records:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    typer.echo(f"{len(records)} mappings — " + "  ".join(f"{k}: {v}" for k, v in by_status.items()))

    from pentaho_migration.validator.effort import effort_from_counts

    copilot_total = manual_total = 0.0
    for r in records:
        effort = effort_from_counts(
            steps=r.steps, auto=r.auto, review=r.review,
            manual=r.manual, untranslated_exprs=r.expressions)
        copilot_total += effort.copilot_hours
        manual_total += effort.manual_hours
    saved = manual_total - copilot_total
    pct = round(saved / manual_total * 100) if manual_total else 0
    rate = 150.0
    typer.echo(
        f"portfolio effort: ~{copilot_total:,.0f}h with Copilot vs ~{manual_total:,.0f}h "
        f"manual rebuild - saves {saved:,.0f}h ({pct}%, ~${saved * rate:,.0f} at ${rate:g}/h)"
    )
    typer.echo("")
    for r in records:
        typer.echo(
            f"  {r.score:>3}/100 {r.grade}  [{r.status:<10}] {r.mapping:<40} ({r.file})"
        )


@app.command()
def gaps(directory: Path = typer.Argument(Path("samples/informatica"))) -> None:
    """Batch-analyze every export in DIRECTORY: mapper coverage + gap list."""
    pipelines = []
    failures: list[tuple[str, str]] = []
    files = sorted([*directory.glob("*.xml"), *directory.glob("*.item")])
    for xml in files:
        try:
            for pipeline in detect_parser(xml).parse_file(xml):
                pipelines.append(RulesMapper.for_pipeline(pipeline).apply(pipeline))
        except Exception as exc:  # a parse failure is a finding, not a crash
            failures.append((xml.name, str(exc)))

    report = build_gap_report(pipelines)
    scores = [build_score(p, build_impact_analysis(p)).score for p in pipelines]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    typer.echo(f"files: {len(files)}  parsed: {len(files) - len(failures)}  failed: {len(failures)}")
    typer.echo(
        f"avg migration confidence: {avg_score}/100 (static) — "
        f"range {min(scores, default=0)}..{max(scores, default=0)}"
    )
    typer.echo(
        f"mappings: {report.mappings}  steps: {report.steps}  "
        f"auto: {report.auto} ({report.auto_rate:.0%})  "
        f"review: {report.review}  manual: {report.manual}  "
        f"expressions: {report.expressions}"
    )
    typer.echo("\nsource type coverage (gaps first):")
    for tc in report.types:
        target = tc.pdi_type or "-- UNMAPPED --"
        typer.echo(f"  {tc.count:>5}  {tc.source_type:<32} -> {target}  [{tc.confidence.value}]")
    if failures:
        typer.echo("\nparse failures:")
        for name, error in failures:
            typer.echo(f"  {name}: {error}")


@app.command()
def report(
    dump: Path,
    out_dir: Path = typer.Option(
        Path("output/crystal"), "--out", "-o",
        help="Directory for the .prpt bundle and its conversion report",
    ),
    jndi: str = typer.Option(
        "", "--jndi", help="JNDI datasource name on the Pentaho server",
    ),
    translate: bool = typer.Option(
        False, "--translate", "-t",
        help="LLM-assist formulas the deterministic translator flagged manual",
    ),
    rate: float = typer.Option(
        150.0, "--rate", help="Consultant rate per hour, for the effort estimate",
    ),
    validate: bool = typer.Option(
        False, "--validate",
        help="Load the generated .prpt through the real Pentaho Reporting engine "
             "(needs a local PRD install + Java; see `pentaho-migrate report-env`)",
    ),
) -> None:
    """Convert a Crystal Reports RptToXml dump to a Pentaho .prpt bundle."""
    from pentaho_migration.reports import (
        build_conversion_report,
        load_report_model,
        write_prpt,
    )

    model = load_report_model(dump, jndi or None)
    if translate:
        from pentaho_migration.llm import TranslationError
        from pentaho_migration.reports.llm_assist import translate_manual_formulas

        try:
            count = translate_manual_formulas(model)
            typer.echo(f"AI-assisted {count} manual formula(s) — all flagged review")
        except TranslationError as exc:
            typer.echo(f"translation unavailable: {exc}", err=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in model.name).strip() or "report"
    out_path = out_dir / f"{safe}.prpt"
    write_prpt(model, out_path)
    report_path = out_path.with_suffix(".conversion.md")
    report_path.write_text(
        build_conversion_report(model, dump, out_path), encoding="utf-8"
    )

    counts = {"auto": 0, "review": 0, "manual": 0}
    for formula in model.formulas.values():
        counts[formula.status] += 1
    typer.echo(f"{model.name} -> {out_path}")
    typer.echo(
        f"  formulas: {counts['auto']} auto, {counts['review']} review, "
        f"{counts['manual']} manual  |  report: {report_path}"
    )
    if counts["manual"]:
        typer.echo("  manual formulas need hand conversion - see the report.")

    from pentaho_migration.reports.effort import build_report_effort

    effort = build_report_effort(model)
    typer.echo(
        f"  effort: ~{effort.copilot_hours:g}h with Copilot vs "
        f"~{effort.manual_hours:g}h manual rebuild - saves "
        f"{effort.saved_hours:g}h ({effort.saved_pct}%, ~${effort.saved_hours * rate:,.0f} at ${rate:g}/h)"
    )

    if validate:
        from pentaho_migration.reports.prpt_validator import validate_prpts, validator_available

        if not validator_available():
            typer.echo("validator unavailable - run `pentaho-migrate report-env` for setup hints", err=True)
            raise typer.Exit(code=2)
        typer.echo("  validating through the Pentaho Reporting engine...")
        (result,) = validate_prpts([out_path])
        if result.ok:
            typer.echo(f"  VALIDATED: loads in the real engine ({result.detail})")
        else:
            typer.echo(f"  VALIDATION FAILED: {result.detail}", err=True)
            raise typer.Exit(code=1)


@app.command("report-sql")
def report_sql(
    dump: Path,
    jndi: str = typer.Option(..., "--jndi", help="JNDI connection to validate against"),
) -> None:
    """Validate a Crystal report's SQL against the live JNDI target database
    (schema-aware: EXPLAIN with parameter defaults substituted)."""
    from pentaho_migration.reports import load_report_model
    from pentaho_migration.reports.schema_agent import probe_schema, validate_sql

    model = load_report_model(dump, jndi)
    params = [{"name": p.name, "default": p.default} for p in model.parameters]
    try:
        schema = probe_schema(jndi)
        typer.echo(f"schema: {len(schema['tables'])} tables introspected from {schema['url']}")
    except RuntimeError as exc:
        typer.echo(f"schema introspection unavailable: {exc}", err=True)
        raise typer.Exit(code=2)
    result = validate_sql(jndi, model.sql, params)
    if result["ok"]:
        typer.echo(f"SQL VALID: EXPLAIN passed against {jndi} ({model.name})")
    else:
        typer.echo(f"SQL INVALID: {result['error']}", err=True)
        typer.echo("checked SQL (parameters substituted):", err=True)
        typer.echo(result["checked_sql"], err=True)
        raise typer.Exit(code=1)


@app.command("report-qa")
def report_qa(
    dump: Path,
    jndi: str = typer.Option("", "--jndi", help="JNDI name baked into the bundle"),
    render: bool = typer.Option(
        False, "--render",
        help="Also render the design-time PDF through the real engine and "
             "verify every label appears (needs a local PRD install + pypdf)"),
) -> None:
    """Layout QA agent: geometry lint (page overflow, collisions, clipped
    fonts, TODO placeholders) and optional engine render verification."""
    from pentaho_migration.reports import load_report_model, write_prpt
    from pentaho_migration.reports.layout_qa import lint_layout, render_qa

    model = load_report_model(dump, jndi or None)
    qa = lint_layout(model)
    findings = list(qa.findings)

    if render:
        import tempfile

        from pentaho_migration.reports.layout_qa import LayoutQA  # noqa: F401
        with tempfile.TemporaryDirectory() as td:
            prpt = Path(td) / "qa.prpt"
            write_prpt(model, prpt)
            try:
                findings.extend(render_qa(model, prpt).findings)
                typer.echo("render check: engine PDF produced and scanned")
            except RuntimeError as exc:
                typer.echo(f"render check skipped: {exc}", err=True)

    if not findings:
        typer.echo(f"CLEAN: no layout findings for {model.name}")
        return
    icons = {"error": "E", "warning": "W", "info": "i"}
    for f in sorted(findings, key=lambda f: ("EWi".index(icons[f.severity]))):
        where = " / ".join(x for x in (f.band, f.element) if x)
        typer.echo(f"[{icons[f.severity]}] {f.code:16} {where}: {f.message}")
    errors = sum(1 for f in findings if f.severity == "error")
    typer.echo(f"{len(findings)} finding(s), {errors} error(s) - {model.name}")
    if errors:
        raise typer.Exit(code=1)


@app.command("report-triage")
def report_triage(
    directory: Path = typer.Argument(Path("samples/cr_demo")),
    jndi: str = typer.Option("", "--jndi", help="Validate each report's SQL against this JNDI target"),
    out: Path = typer.Option(
        Path("output/triage.md"), "--out", "-o", help="Where to write the triage report"),
    llm: bool = typer.Option(
        False, "--llm", "-t",
        help="Add an LLM 'what to check first' brief to every non-READY report"),
) -> None:
    """Batch triage agent: verdict (READY/REVIEW/BLOCKED) + reasons for every
    report in DIRECTORY, so the consultant reviews a summary, not 150 reports."""
    from pentaho_migration.reports.triage import (
        build_triage_report, llm_brief, triage_corpus)

    def progress(done: int, total: int) -> None:
        typer.echo(f"  triaged {done}/{total}", err=True)

    results = triage_corpus(directory, jndi, progress=progress)
    if not results:
        typer.echo(f"no RptToXml dumps found in {directory}")
        raise typer.Exit(code=1)

    if llm:
        pending = [r for r in results if r.verdict != "READY"]
        for i, r in enumerate(pending):
            try:
                r.brief = llm_brief(r)
            except Exception as exc:
                typer.echo(f"  brief failed for {r.file}: {exc}", err=True)
            typer.echo(f"  briefs {i + 1}/{len(pending)}", err=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_triage_report(results, jndi), encoding="utf-8")

    counts = {"READY": 0, "REVIEW": 0, "BLOCKED": 0}
    for r in results:
        counts[r.verdict] += 1
    typer.echo(f"{len(results)} reports: READY {counts['READY']} | "
               f"REVIEW {counts['REVIEW']} | BLOCKED {counts['BLOCKED']}")
    typer.echo(f"triage report: {out}")
    if counts["BLOCKED"]:
        raise typer.Exit(code=1)


@app.command("report-parity")
def report_parity(
    prpt: Path = typer.Argument(..., help=".prpt bundle, or an RptToXml dump to convert first"),
    reference: Path = typer.Argument(..., help="The Crystal report exported as PDF, or its data as CSV"),
    jndi: str = typer.Option("", "--jndi", help="JNDI connection (when converting a dump)"),
) -> None:
    """Measured output parity: render the converted report against the live
    database and diff its NUMBERS against the customer's Crystal export."""
    import tempfile

    from pentaho_migration.reports.parity import run_report_parity

    target = prpt
    if prpt.suffix.lower() == ".xml":
        from pentaho_migration.reports import load_report_model, write_prpt

        model = load_report_model(prpt, jndi or None)
        td = tempfile.mkdtemp()
        target = Path(td) / "parity.prpt"
        write_prpt(model, target)
        typer.echo(f"converted {prpt.name} -> {model.name}")

    try:
        result = run_report_parity(target, reference)
    except RuntimeError as exc:
        typer.echo(f"parity unavailable: {exc}", err=True)
        raise typer.Exit(code=2)

    typer.echo(f"{result.verdict}: {result.note}")
    typer.echo(f"  reference numbers: {result.reference_total}  "
               f"rendered numbers: {result.rendered_total}  matched: {result.matched}")
    if result.missing:
        typer.echo(f"  missing from the converted report: {', '.join(result.missing)}")
    if result.extra:
        typer.echo(f"  extra in the converted report: {', '.join(result.extra)}")
    if result.verdict == "FAIL":
        raise typer.Exit(code=1)


@app.command("report-classify")
def report_classify(
    src: Path = typer.Argument(Path("samples/crystal/real")),
    dest: Path = typer.Option(
        Path("samples/crystal/by-feature"), "--out", "-o",
        help="Destination for the by-feature folder tree"),
) -> None:
    """Classify a Crystal corpus by migration feature: each report is copied
    into a folder per feature it demonstrates (sub-reports/, charts/, ...)
    plus a generated README index - pick real-world demo reports by feature."""
    from pentaho_migration.reports.classify import classify_corpus

    def progress(done: int, total: int) -> None:
        if done % 25 == 0 or done == total:
            typer.echo(f"  scanned {done}/{total}", err=True)

    results = classify_corpus(src, dest, progress=progress)
    counts: dict[str, int] = {}
    for feats in results.values():
        for f in feats:
            counts[f] = counts.get(f, 0) + 1
    typer.echo(f"{len(results)} reports classified into {dest}")
    for feature, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        typer.echo(f"  {feature:24} {n}")
    typer.echo(f"index: {dest / 'README.md'}")


@app.command("report-gaps")
def report_gaps(
    directory: Path = typer.Argument(Path("samples/crystal/real")),
    rate: float = typer.Option(150.0, "--rate", help="Consultant rate per hour"),
) -> None:
    """Batch-analyze every RptToXml dump in DIRECTORY: parse coverage, formula
    translation rates, and portfolio effort - the Crystal counterpart of `gaps`."""
    from pentaho_migration.reports import load_report_model
    from pentaho_migration.reports.effort import build_report_effort

    files = sorted(directory.glob("*.xml"))
    if not files:
        typer.echo(f"no RptToXml dumps found in {directory} - run scripts/extract-rpt.ps1 first")
        raise typer.Exit(code=1)

    failures: list[tuple[str, str]] = []
    reports = 0
    counts = {"auto": 0, "review": 0, "manual": 0}
    todos = elements = params = summaries = 0
    copilot_h = manual_h = 0.0

    for xml in files:
        try:
            model = load_report_model(xml)
        except Exception as exc:  # a parse failure is a finding, not a crash
            failures.append((xml.name, str(exc)[:160]))
            continue
        reports += 1
        for formula in model.formulas.values():
            counts[formula.status] += 1
        elements += sum(len(s.elements) for s in model.sections)
        params += len(model.parameters)
        summaries += len(model.summaries)
        from pentaho_migration.reports.model import is_todo_element

        for section in model.sections:
            for el in section.elements:
                if is_todo_element(el):
                    todos += 1
        effort = build_report_effort(model)
        copilot_h += effort.copilot_hours
        manual_h += effort.manual_hours

    total_f = sum(counts.values())
    auto_rate = counts["auto"] / total_f if total_f else 0.0
    typer.echo(f"files: {len(files)}  parsed: {reports}  failed: {len(failures)}")
    typer.echo(
        f"elements: {elements}  parameters: {params}  summaries: {summaries}  "
        f"todo-placeholders: {todos}"
    )
    typer.echo(
        f"formulas: {total_f}  auto: {counts['auto']} ({auto_rate:.0%})  "
        f"review: {counts['review']}  manual: {counts['manual']}"
    )
    saved = manual_h - copilot_h
    pct = round(saved / manual_h * 100) if manual_h else 0
    typer.echo(
        f"portfolio effort: ~{copilot_h:,.0f}h with Copilot vs ~{manual_h:,.0f}h manual "
        f"rebuild - saves {saved:,.0f}h ({pct}%, ~${saved * rate:,.0f} at ${rate:g}/h)"
    )
    if failures:
        typer.echo("")
        typer.echo("parse failures:")
        for name, error in failures:
            typer.echo(f"  {name}: {error}")


@app.command("report-batch")
def report_batch(
    directory: Path = typer.Argument(Path("samples/crystal/real")),
    out_dir: Path = typer.Option(Path("output/crystal"), "--out", "-o"),
    jndi: str = typer.Option("", "--jndi", help="JNDI datasource for every report"),
    translate: bool = typer.Option(
        False, "--translate", "-t",
        help="LLM-assist manual formulas via the configured provider (slow: one "
             "call per formula - plan an hour+ for a large corpus)",
    ),
) -> None:
    """Convert every RptToXml dump in DIRECTORY and record each report in the
    migration project store (Crystal counterpart of `batch`)."""
    from pentaho_migration.project import ReportRecord, record_report
    from pentaho_migration.reports import (
        build_conversion_report, load_report_model, write_prpt,
    )
    from pentaho_migration.reports.effort import build_report_effort, count_todos

    files = sorted(directory.glob("*.xml"))
    if not files:
        typer.echo(f"no RptToXml dumps found in {directory}")
        raise typer.Exit(code=1)
    out_dir.mkdir(parents=True, exist_ok=True)

    translator = None
    if translate:
        from pentaho_migration.llm import ExpressionTranslator, TranslationError

        try:
            translator = ExpressionTranslator()
            translator._check_provider()
        except TranslationError as exc:
            typer.echo(f"translation unavailable: {exc}", err=True)
            raise typer.Exit(code=2)

    total = failures = 0
    assisted = still_manual = 0
    copilot_h = manual_h = 0.0
    for xml in files:
        try:
            model = load_report_model(xml, jndi or None)
            if translator is not None:
                from pentaho_migration.reports.llm_assist import translate_manual_formulas

                flipped = translate_manual_formulas(model, translator=translator)
                remaining = sum(1 for f in model.formulas.values() if f.status == "manual")
                assisted += flipped
                still_manual += remaining
                if flipped or remaining:
                    typer.echo(f"  {xml.name}: AI-assisted {flipped}, still manual {remaining}")
            safe = "".join(c if c.isalnum() or c in " ._-" else "_" for c in model.name).strip() or xml.stem
            out_path = out_dir / f"{safe}.prpt"
            write_prpt(model, out_path)
            out_path.with_suffix(".conversion.md").write_text(
                build_conversion_report(model, xml, out_path), encoding="utf-8")
        except Exception as exc:  # a conversion failure is a finding, not a crash
            failures += 1
            typer.echo(f"{xml.name}: FAILED - {str(exc)[:140]}", err=True)
            continue
        counts = {"auto": 0, "review": 0, "manual": 0}
        for formula in model.formulas.values():
            counts[formula.status] += 1
        effort = build_report_effort(model)
        record_report(ReportRecord(
            file=xml.name, name=model.name, source_path=str(xml.resolve()),
            formulas_auto=counts["auto"], formulas_review=counts["review"],
            formulas_manual=counts["manual"], todos=count_todos(model),
            copilot_hours=effort.copilot_hours, manual_hours=effort.manual_hours,
            status="converted", updated_at="",
        ))
        copilot_h += effort.copilot_hours
        manual_h += effort.manual_hours
        total += 1
    saved = manual_h - copilot_h
    pct = round(saved / manual_h * 100) if manual_h else 0
    typer.echo(
        f"converted {total} report(s), {failures} failed -> {out_dir} "
        f"(recorded in the project store)")
    typer.echo(
        f"reports effort: ~{copilot_h:,.0f}h with Copilot vs ~{manual_h:,.0f}h "
        f"manual - saves {saved:,.0f}h ({pct}%)")
    if translate:
        typer.echo(
            f"LLM assist: {assisted} formula(s) flipped manual -> review, "
            f"{still_manual} remain manual")


@app.command("report-scrub")
def report_scrub(directory: Path = typer.Argument(Path("samples/crystal/real"))) -> None:
    """Blank credentials (UserName/Password/logon properties) that RptToXml
    copies out of .rpt files into dumps. Run before committing or sharing."""
    from pentaho_migration.reports.sanitize import scrub_directory

    files_changed, attrs = scrub_directory(directory)
    typer.echo(f"scrubbed {attrs} credential attribute(s) in {files_changed} file(s)")


@app.command("report-images")
def report_images(
    dump: Path = typer.Argument(..., help="RptToXml dump (.xml) to enrich"),
    rpt: Path = typer.Argument(None, help=".rpt binary (default: same stem in samples/crystal-rpt)"),
    out: Path = typer.Option(None, "-o", help="write enriched dump here (default: in place)"),
) -> None:
    """Carve embedded pictures out of the .rpt binary and inject them into the
    dump's PictureObjects as base64 <ImageData> (the free SAP SDK cannot read
    picture bytes - PictureData returns null in the embedded RAS). Carved
    images are decode-proven and matched by aspect ratio; each carries a
    verify note through conversion."""
    from pentaho_migration.reports.rpt_images import enrich_dump

    if rpt is None:
        rpt = Path("samples/crystal-rpt") / (dump.stem + ".rpt")
    if not rpt.is_file():
        typer.echo(f"no .rpt found at {rpt}")
        raise typer.Exit(code=2)
    injected = enrich_dump(dump, rpt, out)
    typer.echo(f"{dump.name}: injected {injected} image(s) from {rpt.name}"
               + (f" -> {out}" if out else " (in place)"))
    if injected == 0:
        raise typer.Exit(code=1)


@app.command("report-portfolio")
def report_portfolio(
    directory: Path = typer.Argument(Path("samples/crystal/real")),
    jndi: str = typer.Option("", help="validate each report's SQL against this live JNDI target"),
    rate: float = typer.Option(150.0, help="consultant rate $/h for the cost figures"),
    out: Path = typer.Option(None, "-o", help="output HTML (default: <dir>/portfolio-report.html)"),
) -> None:
    """The consultant's portfolio report: one self-contained HTML page with
    verdict charts, TODO breakdown by category, review-load distribution,
    formula success rates, the 10 heaviest reports, and $ figures at your
    rate. Prints straight to PDF for the customer meeting."""
    from pentaho_migration.reports.portfolio_report import build_portfolio_report_html
    from pentaho_migration.reports.triage import triage_corpus

    results = triage_corpus(directory, jndi=jndi, check_sql=bool(jndi))
    if not results:
        typer.echo(f"no RptToXml dumps found in {directory}")
        raise typer.Exit(code=1)
    html = build_portfolio_report_html(results, rate=rate, jndi=jndi)
    target = out or (directory / "portfolio-report.html")
    target.write_text(html, encoding="utf-8")
    ready = sum(1 for r in results if r.verdict == "READY")
    typer.echo(f"{len(results)} report(s) triaged ({ready} READY) -> {target}")


@app.command("report-env")
def report_env() -> None:
    """Preflight for the Crystal pipeline: is everything installed?"""
    from pentaho_migration.reports.environment import environment_report

    env = environment_report()
    def line(label: str, value, ok: bool) -> None:
        typer.echo(f"  [{'OK' if ok else '--'}] {label}: {value or 'not found'}")

    typer.echo("Crystal migration environment:")
    line("Pentaho Report Designer", env["prd_home"], env["prd_home"] is not None)
    line("Java", env["java"], env["java"] is not None)
    line("SAP Crystal .NET runtime", env["crystal_runtime"], env["crystal_runtime"] is not None)
    line("RptToXml.exe", env["rpttoxml"], env["rpttoxml"] is not None)
    typer.echo(f"  round-trip validation: {'READY' if env['validator_ready'] else 'NOT READY'}")
    typer.echo(f"  .rpt extraction:       {'READY' if env['extraction_ready'] else 'NOT READY'}")
    for hint in env["hints"]:
        typer.echo(f"  hint: {hint}")


if __name__ == "__main__":
    app()
