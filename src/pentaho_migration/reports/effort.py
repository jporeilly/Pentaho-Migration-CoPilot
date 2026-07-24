"""Effort and cost estimation for the reports family: remaining human work on
a converted .prpt vs rebuilding the Crystal report from scratch in PRD.

Same philosophy as validator/effort.py: transparent static heuristics,
every constant surfaced in `assumptions`, hours server-side and money
client-side (hours x consultant rate)."""

from pentaho_migration.reports.model import ReportModel
from pentaho_migration.validator.effort import SCALE, EffortEstimate, _round_half, _vol

# Remaining work on a converted .prpt (hours per first-instance; volume
# discounted sub-linearly — see validator/effort.py SCALE). Calibrated so a
# moderate report (7 fields, 1 group, a few formulas) lands well under an
# hour: the converter did the layout, the human verifies and wires the JNDI.
COPILOT_BASE = 0.1          # verify JNDI, eyeball layout, publish
COPILOT_AUTO_FORMULA = 0.01
COPILOT_REVIEW_FORMULA = 0.04
COPILOT_MANUAL_FORMULA = 0.15
COPILOT_TODO = 0.1          # subreport / image / conditional-format placeholder
COPILOT_PARAM = 0.02        # prompts fold into the query automatically now
COPILOT_TEST_OVERHEAD = 0.10

# From-scratch rebuild in PRD (hours per first-instance; SCALE-discounted).
# Calibrated so the same moderate report is ~2-3h by hand: build the
# datasource, lay out the bands, place and style fields, write the formulas,
# add groups/summaries, and test.
MANUAL_BASE = 0.4           # datasource, page setup, band scaffolding
MANUAL_ELEMENT = 0.02       # place + style one element
MANUAL_FORMULA = 0.12
MANUAL_SUMMARY = 0.1
MANUAL_GROUP = 0.15
MANUAL_PARAM = 0.08
MANUAL_TODO = 0.25
MANUAL_TEST_OVERHEAD = 0.10


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
        + _vol(auto) * COPILOT_AUTO_FORMULA \
        + _vol(review) * COPILOT_REVIEW_FORMULA \
        + _vol(manual) * COPILOT_MANUAL_FORMULA \
        + _vol(todos) * COPILOT_TODO \
        + _vol(len(model.parameters)) * COPILOT_PARAM
    copilot *= 1 + COPILOT_TEST_OVERHEAD

    rebuild = MANUAL_BASE \
        + _vol(n_elements) * MANUAL_ELEMENT \
        + _vol(len(model.formulas)) * MANUAL_FORMULA \
        + _vol(len(model.summaries)) * MANUAL_SUMMARY \
        + _vol(len(model.groups)) * MANUAL_GROUP \
        + _vol(len(model.parameters)) * MANUAL_PARAM \
        + _vol(todos) * MANUAL_TODO
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
            f"Volume scales sub-linearly (n^{SCALE}): repeated formulas/elements "
            "within one report reuse patterns - first instances carry the full rate.",
            "Typical blended consultant rate $125-$175/h ($1,000-$1,400 per 8h day); "
            "adjust the rate to your engagement.",
        ],
    )
