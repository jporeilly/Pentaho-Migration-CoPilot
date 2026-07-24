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

from pentaho_migration.ir import Pipeline
from pentaho_migration.validator.report import MigrationReport

DEFAULT_RATE = 150.0  # USD per hour; UI/CLI override

# Repeated work inside one artifact is cheaper than the first instance —
# the 40th expression is usually a variant of an earlier one, steps repeat
# patterns, layouts are copy-adjusted. Volume therefore scales sub-linearly:
# effective(n) = n ** SCALE. At 0.8, 10 items cost ~6.3x one item (not 10x)
# and 100 items ~40x — matching how consultants actually quote (a 100-step
# monster is ~2 weeks, not 4 months).
SCALE = 0.8


def _vol(n: int) -> float:
    return float(n) ** SCALE if n > 0 else 0.0


# Remaining-work heuristics with Copilot output (hours per first-instance;
# volume discounted by SCALE)
COPILOT_BASE = 0.5          # connections, import, publish
COPILOT_AUTO_STEP = 0.05    # eyeball an auto-converted step
COPILOT_REVIEW_STEP = 0.4   # verify an assumption/AI-translated step
COPILOT_MANUAL_STEP = 2.0   # hand-convert an unmapped step
COPILOT_UNTRANSLATED = 0.15 # translate + wire one expression by hand
COPILOT_REVIEW_EXPR = 0.05  # verify one AI-translated expression
COPILOT_TEST_OVERHEAD = 0.20

# From-scratch rebuild heuristics (hours per first-instance; SCALE-discounted)
MANUAL_BASE = 1.0
MANUAL_STEP = 1.2           # analyze + rebuild one transformation step
MANUAL_EXPR = 0.2           # re-derive one expression
MANUAL_TEST_OVERHEAD = 0.25


def _round_half(x: float) -> float:
    return max(round(x * 2) / 2, 0.5)


class EffortEstimate(BaseModel):
    """Hours only — cost = hours x consultant rate, applied by the caller."""

    copilot_hours: float
    manual_hours: float
    saved_hours: float
    saved_pct: int
    assumptions: list[str]


def effort_from_counts(
    steps: int,
    auto: int,
    review: int,
    manual: int,
    untranslated_exprs: int,
    total_exprs: int | None = None,
) -> EffortEstimate:
    """Estimate from the counts alone — usable both for a live pipeline and
    for records in the project store. When the true expression total is
    unknown (stored records only keep the untranslated count), it is
    approximated by the untranslated count, which errs conservative on both
    scenarios."""
    approximated = total_exprs is None
    if total_exprs is None:
        total_exprs = untranslated_exprs
    reviewed_exprs = total_exprs - untranslated_exprs

    copilot = COPILOT_BASE \
        + _vol(auto) * COPILOT_AUTO_STEP \
        + _vol(review) * COPILOT_REVIEW_STEP \
        + _vol(manual) * COPILOT_MANUAL_STEP \
        + _vol(untranslated_exprs) * COPILOT_UNTRANSLATED \
        + _vol(reviewed_exprs) * COPILOT_REVIEW_EXPR
    copilot *= 1 + COPILOT_TEST_OVERHEAD

    rebuild = MANUAL_BASE \
        + _vol(steps) * MANUAL_STEP \
        + _vol(total_exprs) * MANUAL_EXPR
    rebuild *= 1 + MANUAL_TEST_OVERHEAD

    copilot_h = _round_half(copilot)
    manual_h = max(_round_half(rebuild), copilot_h)
    saved = manual_h - copilot_h
    assumptions = _assumptions()
    if approximated:
        assumptions.append(
            "Expression total approximated by the untranslated count "
            "(stored records) — conservative on both scenarios.")
    return EffortEstimate(
        copilot_hours=copilot_h,
        manual_hours=manual_h,
        saved_hours=saved,
        saved_pct=round(saved / manual_h * 100) if manual_h else 0,
        assumptions=assumptions,
    )


def build_effort(pipeline: Pipeline, report: MigrationReport) -> EffortEstimate:
    return effort_from_counts(
        steps=report.total_steps,
        auto=report.auto,
        review=report.review,
        manual=report.manual,
        untranslated_exprs=report.untranslated_expressions,
        total_exprs=sum(len(s.expressions) for s in pipeline.steps),
    )


def _assumptions() -> list[str]:
    return [
            f"With Copilot: verify auto step {COPILOT_AUTO_STEP}h, review step "
            f"{COPILOT_REVIEW_STEP}h, hand-convert manual step {COPILOT_MANUAL_STEP}h, "
            f"hand-translate expression {COPILOT_UNTRANSLATED}h, verify AI-translated "
            f"expression {COPILOT_REVIEW_EXPR}h, +{COPILOT_TEST_OVERHEAD:.0%} testing.",
            f"Manual rebuild: {MANUAL_STEP}h per step, {MANUAL_EXPR}h per expression, "
            f"+{MANUAL_TEST_OVERHEAD:.0%} testing.",
            f"Volume scales sub-linearly (n^{SCALE}): repeated items within one "
            "artifact reuse patterns, so 10 similar items cost ~6x one item, "
            "not 10x - first instances carry the full rate.",
            "Typical blended consultant rate $125-$175/h ($1,000-$1,400 per 8h day); "
            "adjust the rate to your engagement.",
        ]
