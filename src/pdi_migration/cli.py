"""Command-line interface for the services team (Phase 0).

    pdi-migrate parse   <export.xml>            # inspect what the parser sees
    pdi-migrate convert <export.xml> -o out/    # full parse -> map -> generate
"""

from pathlib import Path

import typer

from pdi_migration.generator import KtrGenerator
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
from pdi_migration.validator import build_report

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


if __name__ == "__main__":
    app()
