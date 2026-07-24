"""Corpus gap analysis: aggregate mapper coverage across many real exports.

Answers "where does the rules library fall short?" — which source
transformation types appear in the wild, how often, and whether each is
auto-mapped, review-flagged, or unmapped. This is the evidence behind the
brief's 70-80% clean-mapping claim.
"""

from collections import Counter

from pydantic import BaseModel, Field

from pentaho_migration.ir import Confidence, Pipeline


class TypeCoverage(BaseModel):
    source_type: str
    count: int
    pdi_type: str | None
    confidence: Confidence


class GapReport(BaseModel):
    mappings: int = 0
    steps: int = 0
    auto: int = 0
    review: int = 0
    manual: int = 0
    expressions: int = 0
    types: list[TypeCoverage] = Field(default_factory=list)

    @property
    def auto_rate(self) -> float:
        return self.auto / self.steps if self.steps else 0.0


def build_gap_report(pipelines: list[Pipeline]) -> GapReport:
    """Aggregate mapped pipelines (mapper already applied) into a coverage report."""
    report = GapReport(mappings=len(pipelines))
    type_counts: Counter[str] = Counter()
    type_info: dict[str, tuple[str | None, Confidence]] = {}

    for pipeline in pipelines:
        for step in pipeline.steps:
            report.steps += 1
            type_counts[step.source_type] += 1
            type_info.setdefault(step.source_type, (step.pdi_type, step.confidence))
            if step.confidence == Confidence.AUTO:
                report.auto += 1
            elif step.confidence == Confidence.REVIEW:
                report.review += 1
            else:
                report.manual += 1
            report.expressions += sum(1 for e in step.expressions if e.translated is None)

    # Unmapped (manual) types first, then by frequency — the gap list is the point.
    report.types = sorted(
        (
            TypeCoverage(
                source_type=t,
                count=n,
                pdi_type=type_info[t][0],
                confidence=type_info[t][1],
            )
            for t, n in type_counts.items()
        ),
        key=lambda tc: (tc.pdi_type is not None, -tc.count),
    )
    return report
