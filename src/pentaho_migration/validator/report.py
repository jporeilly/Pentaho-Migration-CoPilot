"""Migration report (Stage 4: VALIDATE, static half).

Summarizes per-step confidence so the report can flag what was
auto-converted, what needs review, and what a human must handle.
The runtime diff harness (run old vs. new on sample data, diff outputs)
is a later milestone — see validator/harness.py.
"""

from pydantic import BaseModel

from pentaho_migration.ir import Confidence, Pipeline


class MigrationReport(BaseModel):
    pipeline: str
    total_steps: int
    auto: int
    review: int
    manual: int
    untranslated_expressions: int

    @property
    def auto_rate(self) -> float:
        return self.auto / self.total_steps if self.total_steps else 0.0


def build_report(pipeline: Pipeline) -> MigrationReport:
    by_confidence = {c: 0 for c in Confidence}
    for step in pipeline.steps:
        by_confidence[step.confidence] += 1
    return MigrationReport(
        pipeline=pipeline.name,
        total_steps=len(pipeline.steps),
        auto=by_confidence[Confidence.AUTO],
        review=by_confidence[Confidence.REVIEW],
        manual=by_confidence[Confidence.MANUAL],
        untranslated_expressions=sum(
            1 for s in pipeline.steps for e in s.expressions if e.translated is None
        ),
    )
