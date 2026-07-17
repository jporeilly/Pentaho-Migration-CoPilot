"""Command-line interface for the services team (Phase 0).

    pdi-migrate parse   <export.xml>            # inspect what the parser sees
    pdi-migrate convert <export.xml> -o out/    # full parse -> map -> generate
"""

from pathlib import Path

import typer

from pdi_migration.generator import KjbGenerator, KtrGenerator
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import detect_parser
from pdi_migration.validator import (
    assess_source,
    build_gap_report,
    build_impact_analysis,
    build_report,
    build_score,
)

app = typer.Typer(help="Migration Copilot: legacy ETL -> Pentaho Data Integration.")


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
) -> None:
    """Convert a source export (PowerCenter/Talend) to PDI .ktr + migration report."""
    parser = detect_parser(export)
    generator = KtrGenerator()
    pipelines = [
        RulesMapper.for_pipeline(p).apply(p) for p in parser.parse_file(export)
    ]

    if translate:
        from pdi_migration.llm import ExpressionTranslator, TranslationError

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
    from pdi_migration.sandbox import build_sandbox_kit, write_kit

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
    from pdi_migration.project import MappingRecord, record_mapping

    generator = KtrGenerator()
    kjb_generator = KjbGenerator()
    translator = None
    if translate:
        from pdi_migration.llm import ExpressionTranslator, TranslationError

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
        f"see `pdi-migrate project` or the Project page"
    )


@app.command()
def run(
    artifact: Path = typer.Argument(..., help="A generated .ktr or .kjb file"),
    timeout: int = typer.Option(600, "--timeout", help="Seconds before aborting"),
) -> None:
    """Execute a generated .ktr (Pan) or .kjb (Kitchen) in the local PDI install."""
    from pdi_migration.pdi_runner import find_pdi_home, run_artifact

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
    from pdi_migration.validator.diff import DiffError, compare_csv

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
    from pdi_migration.project import list_mappings

    records = list_mappings()
    if not records:
        typer.echo("project store is empty — run `pdi-migrate batch <dir>` first")
        return
    by_status: dict[str, int] = {}
    for r in records:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    typer.echo(f"{len(records)} mappings — " + "  ".join(f"{k}: {v}" for k, v in by_status.items()))
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


if __name__ == "__main__":
    app()
