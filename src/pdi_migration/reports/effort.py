"""Effort and cost estimation for the reports family: remaining human work on
a converted .prpt vs rebuilding the Crystal report from scratch in PRD.

Same philosophy as validator/effort.py: transparent static heuristics,
every constant surfaced in `assumptions`, hours server-side and money
client-side (hours x consultant rate)."""

from pdi_migration.reports.model import ReportModel
from pdi_migration.validator.effort import EffortEstimate, _round_half

# Remaining work on a converted .prpt (hours)
COPILOT_BASE = 0.75         # datasource wiring, layout eyeball, publish
COPILOT_AUTO_FORMULA = 0.05
COPILOT_REVIEW_FORMULA = 0.25
COPILOT_MANUAL_FORMULA = 1.0
COPILOT_TODO = 1.5          # subreport / image / unsupported placeholder
COPILOT_PARAM = 0.1         # wire ${param} into the query, test prompt
COPILOT_TEST_OVERHEAD = 0.25

# From-scratch rebuild in PRD (hours)
MANUAL_BASE = 3.0           # datasource, page setup, band scaffolding
MANUAL_ELEMENT = 0.05       # place + style one element
MANUAL_FORMULA = 0.75
MANUAL_SUMMARY = 0.5
MANUAL_GROUP = 0.5
MANUAL_PARAM = 0.25
MANUAL_TODO = 2.0
MANUAL_TEST_OVERHEAD = 0.25


def count_todos(model: ReportModel) -> int:
    todos = 0
    for section in model.sections:
        for el in section.elements:
            if el.kind in ("subreport", "image", "unknown"):
                todos += 1
            todos += len(el.notes)
    return todos + len(model.issues)


def build_report_effort(model: ReportModel) -> EffortEstimate:
    statuses = [f.status for f in model.formulas.values()]
    auto = statuses.count("auto")
    review = statuses.count("review")
    manual = statuses.count("manual")
    todos = count_todos(model)
    n_elements = sum(len(s.elements) for s in model.sections)

    copilot = COPILOT_BASE \
        + auto * COPILOT_AUTO_FORMULA \
        + review * COPILOT_REVIEW_FORMULA \
        + manual * COPILOT_MANUAL_FORMULA \
        + todos * COPILOT_TODO \
        + len(model.parameters) * COPILOT_PARAM
    copilot *= 1 + COPILOT_TEST_OVERHEAD

    rebuild = MANUAL_BASE \
        + n_elements * MANUAL_ELEMENT \
        + len(model.formulas) * MANUAL_FORMULA \
        + len(model.summaries) * MANUAL_SUMMARY \
        + len(model.groups) * MANUAL_GROUP \
        + len(model.parameters) * MANUAL_PARAM \
        + todos * MANUAL_TODO
    rebuild *= 1 + MANUAL_TEST_OVERHEAD

    copilot_h = _round_half(copilot)
    manual_h = max(_round_half(rebuild), copilot_h)
    saved = manual_h - copilot_h
    return EffortEstimate(
        copilot_hours=copilot_h,
        manual_hours=manual_h,
        saved_hours=saved,
        saved_pct=round(saved / manual_h * 100) if manual_h else 0,
        assumptions=[
            f"With Copilot: verify auto formula {COPILOT_AUTO_FORMULA}h, review formula "
            f"{COPILOT_REVIEW_FORMULA}h, rebuild manual formula {COPILOT_MANUAL_FORMULA}h, "
            f"TODO placeholder (subreport/image) {COPILOT_TODO}h, parameter {COPILOT_PARAM}h, "
            f"+{COPILOT_TEST_OVERHEAD:.0%} testing.",
            f"Manual rebuild in PRD: base {MANUAL_BASE}h, element {MANUAL_ELEMENT}h, "
            f"formula {MANUAL_FORMULA}h, summary {MANUAL_SUMMARY}h, group {MANUAL_GROUP}h, "
            f"TODO {MANUAL_TODO}h, +{MANUAL_TEST_OVERHEAD:.0%} testing.",
            "Typical blended consultant rate $125-$175/h ($1,000-$1,400 per 8h day); "
            "adjust the rate to your engagement.",
        ],
    )
