"""Impact analysis: a detailed, per-step examination of what changes when an
Informatica construct becomes its PDI equivalent.

The knowledge base below encodes *semantic* differences — behaviors that can
silently change results (sorting requirements, null handling, caching, state
persistence) — not just naming. Impact levels:

- none:   1:1 semantics, config fully emitted
- low:    equivalent semantics, minor config to verify
- medium: behavioral differences that need review/config before trusting output
- high:   state, orchestration, or semantics PDI handles fundamentally
          differently — must be redesigned or hand-verified
"""

from pydantic import BaseModel, Field

from pdi_migration.generator.ktr import STEP_CONFIG_EMITTERS
from pdi_migration.ir import Confidence, Pipeline

IMPACT_LEVELS = ("none", "low", "medium", "high")


class TypeKnowledge(BaseModel):
    impact: str
    differences: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


KNOWLEDGE: dict[str, TypeKnowledge] = {
    "Source Qualifier": TypeKnowledge(
        impact="medium",
        differences=[
            "Informatica applies source filters, user-defined joins, and 'select distinct' inside the qualifier; PDI Table Input runs exactly the SQL it is given.",
            "SQL overrides are copied verbatim — dialect functions (Oracle NVL, DECODE, ROWNUM, …) may not run on a different sandbox/target database.",
            "Datatype coercion at extract time differs: PDI derives types from JDBC metadata, not the qualifier's declared ports.",
        ],
        actions=[
            "Review the generated SQL against the target database dialect.",
            "Verify number/date precision after the first sandbox run (compare step metadata).",
        ],
    ),
    "Expression": TypeKnowledge(
        impact="medium",
        differences=[
            "Informatica expression language becomes JavaScript: NULL propagation differs — Informatica arithmetic with NULL yields NULL; JavaScript may yield NaN or type-coerce.",
            "Variable ports (evaluation order within the transformation) have no direct JS equivalent — order of var statements matters.",
            "Informatica implicit datatype conversion is stricter than JavaScript coercion.",
            "The Modified Java Script step is interpreted — noticeably slower than native steps on high row counts.",
        ],
        actions=[
            "Review every translated expression flagged 'review' (original kept as a comment).",
            "Add explicit null guards where a port can be NULL.",
            "For simple arithmetic, consider replacing the script step with a native Calculator step for speed.",
        ],
    ),
    "Aggregator": TypeKnowledge(
        impact="high",
        differences=[
            "Informatica's Aggregator caches and does not require sorted input; PDI Group By REQUIRES rows sorted by the group keys or results are silently wrong.",
            "NULL group keys: Informatica treats NULLs as equal in grouping; verify the PDI sort/group handles NULL ordering the same way.",
            "Informatica aggregate expressions can nest conditions (SUM(IIF(...))) — only plain SUM/AVG/COUNT/MIN/MAX are auto-configured.",
        ],
        actions=[
            "Insert a Sort rows step on the group keys immediately upstream of the Group By.",
            "Hand-configure any non-trivial aggregate expression (left as TODO).",
            "Compare aggregate totals against the original on sandbox data before trusting.",
        ],
    ),
    "Lookup Procedure": TypeKnowledge(
        impact="medium",
        differences=[
            "Informatica lookups are cached with configurable persistence; PDI Stream Lookup reads the lookup stream fully into memory per run.",
            "Unconnected lookups (called from expressions) have no PDI equivalent — they must be restructured into the stream.",
            "Lookup SQL overrides and 'multiple match' policies (first/last/any/error) differ; PDI Stream Lookup returns one match.",
            "Very large lookup tables may need Database Lookup (with cache) instead of Stream Lookup for memory reasons.",
        ],
        actions=[
            "Add the lookup source (Table Input) feeding the Stream Lookup's lookup hop.",
            "Check the original's multiple-match policy and replicate it.",
            "Switch to Database Lookup if the lookup set is too large for memory.",
        ],
    ),
    "Filter": TypeKnowledge(
        impact="low",
        differences=[
            "Filter condition needs translation from Informatica expression language to a PDI condition (or JavaScript).",
            "Rows failing an Informatica filter are silently dropped; PDI Filter Rows can route them to a 'false' hop — decide whether to discard or capture.",
        ],
        actions=["Configure the filter condition; route or discard the false branch deliberately."],
    ),
    "Router": TypeKnowledge(
        impact="medium",
        differences=[
            "A Router evaluates groups in order with one default group; PDI Switch/Case matches a single field value — complex group conditions may need a chain of Filter Rows instead.",
            "Rows matching multiple Informatica groups go to ALL of them; Switch/Case sends a row to exactly one target.",
        ],
        actions=[
            "Verify each output group's condition and the multi-match behavior of the original.",
            "Use cascaded Filter Rows if groups overlap or conditions are non-trivial.",
        ],
    ),
    "Joiner": TypeKnowledge(
        impact="medium",
        differences=[
            "PDI Merge Join requires BOTH inputs sorted on the join keys; Informatica's Joiner does not.",
            "Master/Detail in Informatica maps to join order in PDI — getting it backwards flips left/right outer joins.",
        ],
        actions=[
            "Insert Sort rows on both inputs.",
            "Map master/detail to the correct join type (INNER/LEFT OUTER/RIGHT OUTER/FULL OUTER).",
        ],
    ),
    "Sorter": TypeKnowledge(
        impact="low",
        differences=[
            "Case-sensitivity and null-ordering defaults may differ between engines.",
            "Informatica sorter 'distinct' option must become a PDI Unique rows step after the sort.",
        ],
        actions=["Verify sort key config; add Unique rows if the original used distinct."],
    ),
    "Sequence": TypeKnowledge(
        impact="high",
        differences=[
            "Informatica sequence values persist in the repository across runs; PDI's Add sequence counter resets per transformation run unless backed by a database sequence.",
            "Restart/recovery behavior therefore differs — duplicate or reset keys are possible after failure.",
        ],
        actions=[
            "Back the PDI sequence with a database sequence (or stored max-key lookup) for production keys.",
            "Decide the starting value explicitly — it will NOT continue from Informatica's last value automatically.",
        ],
    ),
    "Sequence Generator": TypeKnowledge(
        impact="high",
        differences=["Same considerations as Sequence (repository-persisted vs per-run counter)."],
        actions=["Back with a database sequence; set the start value from the source's current value."],
    ),
    "Update Strategy": TypeKnowledge(
        impact="high",
        differences=[
            "DD_INSERT/DD_UPDATE/DD_DELETE/DD_REJECT flag rows dynamically; PDI has no per-row strategy on a single output — Insert/Update, Update, and Delete are separate steps.",
            "Session-level 'treat source rows as' overrides are lost with the workflow layer.",
        ],
        actions=[
            "Split flagged flows: route by strategy into Insert/Update, Update, or Delete steps (Switch/Case on the flag logic).",
            "Recreate rejected-row handling explicitly.",
        ],
    ),
    "Stored Procedure": TypeKnowledge(
        impact="high",
        differences=[
            "Informatica stored-procedure transformations can run per row, or once pre/post-session — PDI's Call DB Procedure runs per row only; pre/post execution belongs in the job (.kjb) as a SQL entry.",
            "OUT/INOUT parameters and return values need explicit field mapping; the generated step assumes IN parameters.",
        ],
        actions=[
            "Confirm the original's execution mode (per-row vs pre/post-session) and relocate to the job level if needed.",
            "Map parameter directions and result fields by hand; verify the procedure exists in the sandbox database.",
        ],
    ),
    "Normalizer": TypeKnowledge(
        impact="medium",
        differences=[
            "COBOL/occurs-based normalization has richer semantics than PDI Row Normaliser's fieldname/value pivoting.",
            "Generated keys (GK/GCID ports) need explicit replication.",
        ],
        actions=["Map occurs groups to Normaliser rows by hand; recreate GK/GCID keys if used downstream."],
    ),
    "Rank": TypeKnowledge(
        impact="medium",
        differences=[
            "Emulated as Sort rows + row limit; Informatica RANK handles ties by rank index — PDI's top-N after sort may cut ties differently.",
        ],
        actions=["Verify tie behavior matches; consider Analytic Query step for true ranking."],
    ),
    "Union Transformation": TypeKnowledge(
        impact="low",
        differences=["PDI Append streams requires identical row layouts; column alignment is by name/order, not by group mapping."],
        actions=["Verify field order/types match across all inputs (add Select values to align)."],
    ),
    "Source": TypeKnowledge(impact="low", differences=["Connection and table/file location must be configured in PDI."], actions=["Point at the sandbox source."]),
    "Target": TypeKnowledge(
        impact="medium",
        differences=[
            "Session-level target properties (commit interval, constraint-failure handling, bulk loading) lived in the Informatica session, which is not converted.",
            "PDI Table Output commit size and batch settings default to generic values.",
        ],
        actions=["Set commit/batch sizes; decide error handling (error hop vs abort)."],
    ),
    "Target Definition": TypeKnowledge(impact="medium", differences=["See Target."], actions=["Set commit/batch sizes and error handling."]),
}

UNMAPPED_KNOWLEDGE = TypeKnowledge(
    impact="high",
    differences=["No PDI equivalent is configured — this logic does not exist in the converted output."],
    actions=["Convert by hand (see the step's notes) or redesign the flow around a PDI-native approach."],
)


class StepImpact(BaseModel):
    step: str
    source_type: str
    pdi_type: str | None
    confidence: Confidence
    impact: str
    converts: list[str] = Field(default_factory=list)   # what transfers automatically
    differences: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class ImpactSummary(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0
    none: int = 0
    top_risks: list[str] = Field(default_factory=list)


class ImpactAnalysis(BaseModel):
    pipeline: str
    entries: list[StepImpact]
    summary: ImpactSummary


def _converts(step) -> list[str]:
    converts = [f"step type mapped: {step.source_type} → {step.pdi_type}" if step.pdi_type
                else "step type NOT mapped"]
    if step.fields:
        converts.append(f"{len(step.fields)} field definitions carried over")
    if step.pdi_type in STEP_CONFIG_EMITTERS:
        converts.append("step configuration emitted (not just a placeholder)")
    translated = sum(1 for e in step.expressions if e.translated is not None)
    if step.expressions:
        converts.append(f"expressions: {translated}/{len(step.expressions)} translated")
    return converts


def build_impact_analysis(pipeline: Pipeline) -> ImpactAnalysis:
    entries = []
    for step in pipeline.steps:
        knowledge = (
            KNOWLEDGE.get(step.source_type, UNMAPPED_KNOWLEDGE)
            if step.pdi_type is None and step.source_type not in KNOWLEDGE
            else KNOWLEDGE.get(step.source_type)
            or (UNMAPPED_KNOWLEDGE if step.pdi_type is None else TypeKnowledge(impact="low"))
        )
        entries.append(StepImpact(
            step=step.name,
            source_type=step.source_type,
            pdi_type=step.pdi_type,
            confidence=step.confidence,
            impact=knowledge.impact,
            converts=_converts(step),
            differences=knowledge.differences,
            actions=knowledge.actions + [
                f"note: {n}" for n in step.notes if "manual conversion required" in n
            ],
        ))

    summary = ImpactSummary()
    for entry in entries:
        setattr(summary, entry.impact, getattr(summary, entry.impact) + 1)

    risks = []
    types = {s.source_type for s in pipeline.steps}
    if types & {"Aggregator", "Joiner"}:
        risks.append("Sorted-input requirement: Group By / Merge Join produce silently wrong results on unsorted data — add Sort rows steps.")
    if types & {"Sequence", "Sequence Generator"}:
        risks.append("Sequence state: PDI counters reset per run — production keys need database-backed sequences.")
    if types & {"Update Strategy"}:
        risks.append("Per-row update strategies must be split into separate Insert/Update/Update/Delete flows.")
    if any(s.expressions for s in pipeline.steps):
        risks.append("Null-handling differs between Informatica expressions and JavaScript — review translated expressions with NULL-able inputs.")
    if any(s.pdi_type is None for s in pipeline.steps):
        risks.append("Unmapped step types present — converted output is incomplete until they are hand-converted.")
    summary.top_risks = risks

    # highest impact first, then by name for stability
    order = {level: i for i, level in enumerate(reversed(IMPACT_LEVELS))}
    entries.sort(key=lambda e: (order[e.impact], e.step))
    return ImpactAnalysis(pipeline=pipeline.name, entries=entries, summary=summary)
