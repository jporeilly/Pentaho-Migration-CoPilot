"""Migration confidence score: a 0-100 prediction that a converted mapping
will run correctly after standard setup (connections, tables, data).

STATIC analysis — computed from what the converter knows (mapping coverage,
expression translation, config completeness, semantic impact). The runtime
diff harness (run old vs. new, compare outputs) will later provide *measured*
confidence; until then this is an informed prediction, and is labeled as such.
"""

from pydantic import BaseModel, Field

from pdi_migration.generator.ktr import STEP_CONFIG_EMITTERS
from pdi_migration.ir import Confidence, Pipeline
from pdi_migration.validator.impact import ImpactAnalysis

# Steps that are pure passthrough in PDI and need no emitted config.
NO_CONFIG_NEEDED = {"Dummy", "Append", "SortRows"}

IMPACT_VALUE = {"none": 1.0, "low": 0.85, "medium": 0.55, "high": 0.25}
CONFIDENCE_VALUE = {Confidence.AUTO: 1.0, Confidence.REVIEW: 0.6, Confidence.MANUAL: 0.0}

GRADES = ((85, "A"), (70, "B"), (55, "C"), (40, "D"), (0, "E"))

VERDICTS = {
    "A": "High confidence — expect this to run after connection setup, with light review.",
    "B": "Good — a handful of review items stand between this and a clean sandbox run.",
    "C": "Moderate — plan real review time; several constructs need verification or config.",
    "D": "Low — significant manual conversion remains before a sandbox run is meaningful.",
    "E": "Very low — treat the output as a starting skeleton, not a conversion.",
}


class ScoreFactor(BaseModel):
    name: str
    score: int          # 0-100 for this factor
    weight: float
    detail: str


class MigrationScore(BaseModel):
    score: int          # weighted 0-100
    grade: str          # A-E
    verdict: str
    factors: list[ScoreFactor] = Field(default_factory=list)
    is_static: bool = True  # becomes False when the diff harness measures it


def build_score(pipeline: Pipeline, impact: ImpactAnalysis) -> MigrationScore:
    factors = []

    steps = pipeline.steps or []
    mapping_score = (
        sum(CONFIDENCE_VALUE[s.confidence] for s in steps) / len(steps) if steps else 0.0
    )
    factors.append(ScoreFactor(
        name="Step mapping",
        score=round(mapping_score * 100),
        weight=0.35,
        detail=f"{sum(1 for s in steps if s.confidence == Confidence.AUTO)}/{len(steps)} steps auto-mapped",
    ))

    expressions = [e for s in steps for e in s.expressions]
    if expressions:
        def expr_value(e):
            if e.translated is None:
                return 0.2
            return 1.0 if e.confidence == Confidence.AUTO else 0.7
        expr_score = sum(expr_value(e) for e in expressions) / len(expressions)
        translated = sum(1 for e in expressions if e.translated is not None)
        detail = f"{translated}/{len(expressions)} expressions translated"
    else:
        expr_score, detail = 1.0, "no expressions to translate"
    factors.append(ScoreFactor(
        name="Expression translation", score=round(expr_score * 100), weight=0.25, detail=detail,
    ))

    configured = sum(
        1 for s in steps
        if s.pdi_type in STEP_CONFIG_EMITTERS or s.pdi_type in NO_CONFIG_NEEDED
    )
    config_score = configured / len(steps) if steps else 0.0
    factors.append(ScoreFactor(
        name="Config completeness",
        score=round(config_score * 100),
        weight=0.15,
        detail=f"{configured}/{len(steps)} steps emit real configuration",
    ))

    impact_score = (
        sum(IMPACT_VALUE[e.impact] for e in impact.entries) / len(impact.entries)
        if impact.entries else 1.0
    )
    factors.append(ScoreFactor(
        name="Semantic impact",
        score=round(impact_score * 100),
        weight=0.25,
        detail=f"{impact.summary.high} high / {impact.summary.medium} medium impact steps",
    ))

    total = round(sum(f.score * f.weight for f in factors))
    grade = next(g for threshold, g in GRADES if total >= threshold)
    return MigrationScore(score=total, grade=grade, verdict=VERDICTS[grade], factors=factors)
