"""Reports migration: SAP Crystal Reports -> Pentaho Report Designer (.prpt).

A second artifact family alongside ETL migration. Crystal reports are
documents (bands, elements, formulas), not dataflows, so this subpackage has
its own pipeline instead of the ETL IR: RptToXml dump -> ReportModel ->
deterministic formula translation (auto/review/manual, never guessed) ->
native .prpt bundle + markdown conversion report.

Folded in from the standalone CR-PRPT-Migration prototype (v0.2.0).
"""

from pathlib import Path

from pentaho_migration.reports.conversion_report import build_conversion_report
from pentaho_migration.reports.formula_translator import translate_all, translate_formula
from pentaho_migration.reports.model import ReportModel
from pentaho_migration.reports.prpt_writer import write_prpt
from pentaho_migration.reports.rpt_parser import generate_sql, parse_rpttoxml

__all__ = [
    "ReportModel",
    "build_conversion_report",
    "load_report_model",
    "parse_rpttoxml",
    "translate_all",
    "translate_formula",
    "write_prpt",
]


def load_report_model(source: str | Path, jndi: str | None = None) -> ReportModel:
    """Parse an RptToXml dump and run formula translation — the full read side."""
    model = parse_rpttoxml(source)
    if jndi:
        model.jndi = jndi
    translate_all(model)
    if not model.sql:
        model.sql = generate_sql(model)
        model.sql_generated = True
    from pentaho_migration.reports.record_selection import try_fold_record_selection
    try_fold_record_selection(model)
    return model
