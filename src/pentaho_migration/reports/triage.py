"""Batch triage agent: sweep a converted corpus and draft the review verdict
per report, so a consultant reviews summaries instead of opening every report.

Deterministic signals per report (no LLM required):
  - parse result and formula counts (auto / review / manual)
  - idiom rewrites present (running totals etc. - review-flagged functions)
  - SQL validation against the live JNDI target (schema agent, when reachable)
  - layout QA lint findings (page overflow, collisions, TODO placeholders)
  - effort estimate

Verdicts:
  BLOCKED - the SQL fails against the live target, or the report failed to
            parse: the .prpt cannot work as generated.
  REVIEW  - converts, but a human must look: manual formulas, TODO
            placeholders, idiom rewrites to verify, or layout findings.
  READY   - clean conversion, SQL proven against the target, nothing manual.

An optional LLM pass (same Ollama provider as everything else) turns each
non-READY report's signals into a two-sentence "what to check first" brief -
advisory text in the triage report, never a gate.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


from pentaho_migration.llm.settings import LLMSettings, load_settings
from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.effort import build_report_effort
from pentaho_migration.reports.layout_qa import lint_layout
from pentaho_migration.reports.schema_agent import validate_sql


@dataclass
class TriageResult:
    file: str
    name: str = ""
    verdict: str = "REVIEW"        # READY | REVIEW | BLOCKED
    reasons: list = field(default_factory=list)
    auto: int = 0
    review: int = 0
    manual: int = 0
    rewrites: int = 0
    todos: int = 0
    layout_errors: int = 0
    layout_warnings: int = 0
    sql_status: str = "unchecked"  # valid | invalid | unchecked
    sql_error: str = ""
    copilot_hours: float = 0.0
    manual_hours: float = 0.0
    brief: str = ""                # optional LLM "what to check first"
    parse_error: str = ""


def triage_one(dump: Path, jndi: str = "", check_sql: bool = True) -> TriageResult:
    """All deterministic signals for one RptToXml dump."""
    result = TriageResult(file=dump.name)
    try:
        model = load_report_model(dump, jndi or None)
    except Exception as exc:
        result.verdict = "BLOCKED"
        result.parse_error = str(exc)
        result.reasons.append(f"parse failed: {exc}")
        return result

    result.name = model.name
    for f in model.formulas.values():
        result.auto += f.status == "auto"
        result.review += f.status == "review"
        result.manual += f.status == "manual"
        result.rewrites += bool(f.rewrite_class)
    from pentaho_migration.reports.model import is_todo_element

    result.todos = sum(1 for s in model.sections for el in s.elements
                       if is_todo_element(el))
    effort = build_report_effort(model)
    result.copilot_hours = effort.copilot_hours
    result.manual_hours = effort.manual_hours

    qa = lint_layout(model)
    result.layout_errors = len(qa.errors)
    result.layout_warnings = len(qa.warnings)
    for finding in qa.errors + qa.warnings:
        result.reasons.append(
            f"layout {finding.code} [{finding.band}] {finding.element}: {finding.message}")

    if check_sql and jndi:
        check = validate_sql(jndi, model.sql,
                             [{"name": p.name, "default": p.default}
                              for p in model.parameters])
        if check["ok"]:
            result.sql_status = "valid"
        elif check["checked_sql"]:
            result.sql_status = "invalid"      # a real database error
            result.sql_error = check["error"]
            result.reasons.append(f"SQL fails against {jndi}: {check['error']}")
        else:
            result.sql_status = "unchecked"    # DB/driver unavailable - not the report's fault
            result.sql_error = check["error"]

    if result.manual:
        result.reasons.append(f"{result.manual} manual formula(s) to rebuild")
    if result.rewrites:
        result.reasons.append(
            f"{result.rewrites} idiom rewrite(s) to verify (running totals / aggregates)")
    if result.todos:
        result.reasons.append(f"{result.todos} TODO placeholder(s) (subreport/image/cross-tab)")

    if result.sql_status == "invalid":
        result.verdict = "BLOCKED"
    elif (result.manual or result.todos or result.rewrites
          or result.layout_errors or result.layout_warnings):
        result.verdict = "REVIEW"
    else:
        result.verdict = "READY"
    return result


def triage_corpus(directory: Path, jndi: str = "", check_sql: bool = True,
                  progress=None) -> list[TriageResult]:
    files = sorted(Path(directory).glob("*.xml"))
    results = []
    for i, dump in enumerate(files):
        results.append(triage_one(dump, jndi, check_sql=check_sql))
        if progress:
            progress(i + 1, len(files))
    return results


# ------------------------------------------------------------- LLM brief

TRIAGE_PROMPT = """\
You write the one-paragraph review brief for a SAP Crystal report that was
auto-converted to Pentaho Report Designer. You get the conversion's facts;
tell the reviewing consultant what to check first and in what order. Be
specific to the facts given - never invent issues. Two to four sentences.
Reply with JSON only: {"brief": "<the paragraph>"}
"""

TRIAGE_SCHEMA = {"type": "object", "properties": {"brief": {"type": "string"}},
                 "required": ["brief"]}


def llm_brief(result: TriageResult, settings: LLMSettings | None = None,
              timeout: float = 120.0) -> str:
    """Two-to-four-sentence 'what to check first' for one triage result."""
    settings = settings or load_settings()
    facts = {
        "report": result.name or result.file,
        "verdict": result.verdict,
        "formulas": {"auto": result.auto, "review": result.review,
                     "manual": result.manual, "idiom_rewrites": result.rewrites},
        "todo_placeholders": result.todos,
        "layout_findings": result.reasons[:8],
        "sql_validation": result.sql_status +
                          (f" ({result.sql_error})" if result.sql_error else ""),
        "estimated_hours_with_copilot": result.copilot_hours,
    }
    from pentaho_migration.llm.translate import chat_json

    messages = [{"role": "system", "content": TRIAGE_PROMPT},
                {"role": "user", "content": json.dumps(facts, indent=1)}]
    return chat_json(settings, messages, TRIAGE_SCHEMA, timeout).get("brief", "")


# ------------------------------------------------------- markdown report

def build_triage_report(results: list[TriageResult], jndi: str = "") -> str:
    """The consultant-facing triage document for a whole corpus."""
    ready = [r for r in results if r.verdict == "READY"]
    review = [r for r in results if r.verdict == "REVIEW"]
    blocked = [r for r in results if r.verdict == "BLOCKED"]
    unchecked = sum(1 for r in results if r.sql_status == "unchecked")

    lines = ["# Migration Triage Report", ""]
    lines.append(f"**{len(results)} reports** - "
                 f"READY {len(ready)} | REVIEW {len(review)} | BLOCKED {len(blocked)}")
    if jndi:
        note = f"SQL validated against JNDI `{jndi}`"
        if unchecked == len(results):
            note += " - **database unreachable, SQL checks skipped**"
        elif unchecked:
            note += f" ({unchecked} unchecked)"
        lines.append(note)
    hours = sum(r.copilot_hours for r in results)
    manual = sum(r.manual_hours for r in results)
    lines += ["", f"Portfolio effort: ~{hours:.0f}h with Copilot vs "
                  f"~{manual:.0f}h manual rebuild.", ""]

    lines += ["| Verdict | Report | SQL | Formulas (a/r/m) | TODOs | Layout | Hours |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    order = {"BLOCKED": 0, "REVIEW": 1, "READY": 2}
    for r in sorted(results, key=lambda r: (order[r.verdict], r.file)):
        icon = {"READY": "✅", "REVIEW": "⚠️", "BLOCKED": "⛔"}[r.verdict]
        layout = (f"{r.layout_errors}E/{r.layout_warnings}W"
                  if (r.layout_errors or r.layout_warnings) else "clean")
        lines.append(
            f"| {icon} {r.verdict} | {r.name or r.file} | {r.sql_status} | "
            f"{r.auto}/{r.review}/{r.manual} | {r.todos} | {layout} | "
            f"{r.copilot_hours:g}h |")
    lines.append("")

    for title, bucket in (("Blocked", blocked), ("Needs review", review)):
        if not bucket:
            continue
        lines.append(f"## {title}")
        for r in bucket:
            lines.append(f"\n### {r.name or r.file}  (`{r.file}`)")
            if r.brief:
                lines.append(f"\n> {r.brief}")
            lines.append("")
            for reason in r.reasons:
                lines.append(f"- {reason}")
        lines.append("")
    return "\n".join(lines)
