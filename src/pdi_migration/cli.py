"""Command-line interface for the services team (Phase 0).

    pdi-migrate parse   <export.xml>            # inspect what the parser sees
    pdi-migrate convert <export.xml> -o out/    # full parse -> map -> generate
"""

from pathlib import Path

import typer

from pdi_migration.generator import KtrGenerator
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
from pdi_migration.validator import build_gap_report, build_report

app = typer.Typer(help="Migration Copilot: legacy ETL -> Pentaho Data Integration.")


@app.command()
def parse(export: Path) -> None:
    """Parse a PowerCenter export and print the extracted pipelines."""
    for pipeline in PowerCenterParser().parse_file(export):
        typer.echo(pipeline.model_dump_json(indent=2))


@app.command()
def convert(
    export: Path,
    out_dir: Path = typer.Option(Path("output"), "--out", "-o", help="Directory for .ktr files"),
) -> None:
    """Convert a PowerCenter export to PDI .ktr skeletons + migration report."""
    mapper = RulesMapper()
    generator = KtrGenerator()
    for pipeline in PowerCenterParser().parse_file(export):
        mapper.apply(pipeline)
        out_path = generator.write(pipeline, out_dir)
        report = build_report(pipeline)
        typer.echo(f"{pipeline.name} -> {out_path}")
        typer.echo(
            f"  steps: {report.total_steps}  auto: {report.auto}  "
            f"review: {report.review}  manual: {report.manual}  "
            f"expressions to translate: {report.untranslated_expressions}"
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
    typer.echo(f"files: {len(files)}  parsed: {len(files) - len(failures)}  failed: {len(failures)}")
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
