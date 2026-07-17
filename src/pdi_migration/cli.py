"""Command-line interface for the services team (Phase 0).

    pdi-migrate parse   <export.xml>            # inspect what the parser sees
    pdi-migrate convert <export.xml> -o out/    # full parse -> map -> generate
"""

from pathlib import Path

import typer

from pdi_migration.generator import KtrGenerator
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
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
    """Parse a PowerCenter export and print the extracted pipelines."""
    for pipeline in PowerCenterParser().parse_file(export):
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
    """Convert a PowerCenter export to PDI .ktr skeletons + migration report."""
    parser = PowerCenterParser()
    mapper = RulesMapper()
    generator = KtrGenerator()
    pipelines = [mapper.apply(p) for p in parser.parse_file(export)]

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

    mapper = RulesMapper()
    for pipeline in PowerCenterParser().parse_file(export):
        mapper.apply(pipeline)
        kit = build_sandbox_kit(pipeline, rows=rows)
        kit_dir = write_kit(kit, out_dir)
        typer.echo(
            f"{pipeline.name} -> {kit_dir}  "
            f"(setup.md, setup.sql, {len(kit.data)} data file(s))"
        )


@app.command()
def gaps(directory: Path = typer.Argument(Path("samples/informatica"))) -> None:
    """Batch-analyze every export in DIRECTORY: mapper coverage + gap list."""
    parser = PowerCenterParser()
    mapper = RulesMapper()
    pipelines = []
    failures: list[tuple[str, str]] = []
    files = sorted(directory.glob("*.xml"))
    for xml in files:
        try:
            for pipeline in parser.parse_file(xml):
                pipelines.append(mapper.apply(pipeline))
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
