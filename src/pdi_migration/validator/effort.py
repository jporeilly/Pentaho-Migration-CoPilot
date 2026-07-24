"""Effort and cost estimation: remaining human work with Copilot vs a
from-scratch manual rebuild.

STATIC heuristics, deliberately transparent and conservative — every number
that goes into an estimate is listed in `assumptions` so a presales engineer
can defend (or adjust) it in front of a customer. Hours are the server-side
product; money is hours x rate, where the rate is chosen client-side
(typical blended ETL/BI consultant rates run $125-$175/h, i.e. $1,000-$1,400
per 8-hour day — the UI defaults to $150/h).
"""

from pydantic import BaseModel

from pdi_migration.ir import Pipeline
from pdi_migration.validator.report import MigrationReport

DEFAULT_RATE = 150.0  # USD per hour; UI/CLI override

# Remaining-work heuristics with Copilot output (hours)
COPILOT_BASE = 0.5          # connections, import, publish
COPILOT_AUTO_STEP = 0.1     # eyeball an auto-converted step
COPILOT_REVIEW_STEP = 0.75  # verify an assumption/AI-translated step
COPILOT_MANUAL_STEP = 3.0   # hand-convert an unmapped step
COPILOT_UNTRANSLATED = 0.25 # translate + wire one expression by hand
COPILOT_REVIEW_EXPR = 0.1   # verify one AI-translated expression
COPILOT_TEST_OVERHEAD = 0.25

# From-scratch rebuild heuristics (hours)
MANUAL_BASE = 1.0
MANUAL_STEP = 1.5           # analyze + rebuild one transformation step
MANUAL_EXPR = 0.33          # re-derive one expression
MANUAL_TEST_OVERHEAD = 0.30


def _round_half(x: float) -> float:
    return max(round(x * 2) / 2, 0.5)


class EffortEstimate(BaseModel):
    """Hours only — cost = hours x consultant rate, applied by the caller."""

    copilot_hours: float
    manual_hours: float
    saved_hours: float
    saved_pct: int
    assumptions: list[str]


def build_effort(pipeline: Pipeline, report: MigrationReport) -> EffortEstimate:
    total_exprs = sum(len(s.expressions) for s in pipeline.steps)
    reviewed_exprs = total_exprs - report.untranslated_expressions

    copilot = COPILOT_BASE \
        + report.auto * COPILOT_AUTO_STEP \
        + report.review * COPILOT_REVIEW_STEP \
        + report.manual * COPILOT_MANUAL_STEP \
        + report.untranslated_expressions * COPILOT_UNTRANSLATED \
        + reviewed_exprs * COPILOT_REVIEW_EXPR
    copilot *= 1 + COPILOT_TEST_OVERHEAD

    manual = MANUAL_BASE \
        + report.total_steps * MANUAL_STEP \
        + total_exprs * MANUAL_EXPR
    manual *= 1 + MANUAL_TEST_OVERHEAD

    copilot_h = _round_half(copilot)
    manual_h = max(_round_half(manual), copilot_h)
    saved = manual_h - copilot_h
    return EffortEstimate(
        copilot_hours=copilot_h,
        manual_hours=manual_h,
        saved_hours=saved,
        saved_pct=round(saved / manual_h * 100) if manual_h else 0,
        assumptions=[
            f"With Copilot: verify auto step {COPILOT_AUTO_STEP}h, review step "
            f"{COPILOT_REVIEW_STEP}h, hand-convert manual step {COPILOT_MANUAL_STEP}h, "
            f"hand-translate expression {COPILOT_UNTRANSLATED}h, verify AI-translated "
            f"expression {COPILOT_REVIEW_EXPR}h, +{COPILOT_TEST_OVERHEAD:.0%} testing.",
            f"Manual rebuild: {MANUAL_STEP}h per step, {MANUAL_EXPR}h per expression, "
            f"+{MANUAL_TEST_OVERHEAD:.0%} testing.",
            "Typical blended consultant rate $125-$175/h ($1,000-$1,400 per 8h day); "
            "adjust the rate to your engagement.",
        ],
    )
