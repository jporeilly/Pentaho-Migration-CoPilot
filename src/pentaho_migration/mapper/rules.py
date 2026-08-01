"""Rules-library mapper (Stage 2: MAP, deterministic half).

Applies known 1:1 step equivalents from a YAML rules file. Steps with no rule
are marked MANUAL and left for the LLM mapper or human handoff — the mapper
never guesses.
"""

from pathlib import Path

import yaml

from pentaho_migration.ir import Confidence, FieldDef, Hop, Pipeline, SourceTool, Step

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"
DEFAULT_RULES = RULES_DIR / "powercenter_to_pdi.yaml"

RULES_BY_TOOL = {
    SourceTool.POWERCENTER: RULES_DIR / "powercenter_to_pdi.yaml",
    SourceTool.TALEND: RULES_DIR / "talend_to_pdi.yaml",
}


def _no_rule_note(source_type: str, source_tool: SourceTool | None = None) -> str:
    """The honest handoff message for a step with no rule AND no known
    suggestion. Even here we point at the PDI approach for arbitrary logic, so
    it is a suggestion, not a bare error."""
    if source_tool == SourceTool.POWERCENTER:
        return (f"'{source_type}' has no 1:1 PDI rule and no known category — "
                "most likely a custom or rare transformation. Inspect it in the "
                "PowerCenter Designer and rebuild its behaviour with PDI steps; "
                "a 'User Defined Java Class' step covers arbitrary per-row logic.")
    # Talend / default. Custom and joblet components can never be enumerated in
    # a rules library (every estate has its own), so name that category
    # explicitly instead of implying the library is simply incomplete — the
    # rebuild advice differs completely.
    conventional = (len(source_type) > 1
                    and source_type[0] in "tc"
                    and source_type[1].isupper())
    if not conventional or source_type.lower().startswith("joblet"):
        return (f"'{source_type}' does not follow the Talend component naming "
                "convention — it is most likely a CUSTOM component or a joblet "
                "built in-house. No rules library can cover these: open it in "
                "Studio to see what it does, then rebuild that behaviour with "
                "PDI steps (a joblet usually becomes a mapping/sub-transformation).")
    return f"No mapping rule for '{source_type}' — manual conversion required."


class RulesMapper:
    def __init__(self, rules_path: str | Path = DEFAULT_RULES):
        with open(rules_path, encoding="utf-8") as f:
            loaded: dict = yaml.safe_load(f)
        # keys starting with "_" are governance metadata, not mapping rules
        self.meta: dict = loaded.get("_meta", {})
        # _suggestions: TYPE -> the closest PDI approach for a type with no 1:1
        # rule, so an unmapped step gets a suggested solution, not a bare error.
        self.suggestions: dict[str, str] = loaded.get("_suggestions", {})
        self.rules: dict[str, dict] = {
            k: v for k, v in loaded.items() if not k.startswith("_")
        }

    @classmethod
    def for_tool(cls, source_tool: SourceTool) -> "RulesMapper":
        """The rules library for a given source tool (defaults to PowerCenter)."""
        return cls(RULES_BY_TOOL.get(source_tool, DEFAULT_RULES))

    @classmethod
    def for_pipeline(cls, pipeline: Pipeline) -> "RulesMapper":
        return cls.for_tool(pipeline.source_tool)

    def apply(self, pipeline: Pipeline) -> Pipeline:
        for step in pipeline.steps:
            rule = self.rules.get(step.source_type)
            if rule is None:
                step.confidence = Confidence.MANUAL
                # No 1:1 rule: suggest the closest PDI approach if we know the
                # transformation category, else fall back to the honest custom-
                # component handoff (which still names the PDI approach).
                suggestion = self.suggestions.get(step.source_type)
                if suggestion:
                    step.notes.append(
                        f"'{step.source_type}' has no 1:1 PDI step - suggested "
                        f"approach: {suggestion}")
                else:
                    step.notes.append(
                        _no_rule_note(step.source_type, pipeline.source_tool))
                continue
            step.pdi_type = rule["pdi_type"]
            step.confidence = Confidence(rule.get("confidence", "review"))
            if note := rule.get("notes"):
                step.notes.append(note)
            # Untranslated expressions force at least REVIEW even on an AUTO rule.
            if step.expressions and step.confidence == Confidence.AUTO:
                step.confidence = Confidence.REVIEW
        insert_required_sorters(pipeline)
        return pipeline


def insert_required_sorters(pipeline: Pipeline) -> int:
    """Insert a Sort rows step upstream of every Group By / Merge Join /
    Unique rows leg that lacks one - suggest AND apply, not just log.

    PDI's sorted-input steps run green on unsorted data and produce
    silently wrong results; the source engines sorted internally, so a
    1:1 mapping quietly drops that guarantee. The inserted step carries
    the keys the target actually needs (group keys / per-leg join keys),
    is marked confidence=review with a note saying why it exists, and is
    tagged in properties so the source diagram can hide it (it has no
    source-tool counterpart). Legs whose keys are NOT knowable from the
    export are left alone - the review agent keeps the honest finding
    rather than a sort that sorts nothing. Idempotent: a leg that
    already has a sorter (including one from a previous pass) is
    skipped. Returns how many steps were inserted."""
    from pentaho_migration.generator.ktr import (
        INSERTED_MARK, SORT_REQUIRED_TYPES, leg_has_sorter, sort_keys_for)

    inserted = 0
    names = {s.name for s in pipeline.steps}
    for target in [s for s in pipeline.steps
                   if s.pdi_type in SORT_REQUIRED_TYPES]:
        legs = [h for h in pipeline.hops if h.to_step == target.name]
        for leg_idx, hop in enumerate(legs):
            if leg_has_sorter(pipeline, hop.from_step):
                continue
            keys = sort_keys_for(target, leg_idx, pipeline)
            if not keys:
                continue
            base = (f"Sort rows ({target.name}"
                    + (f" #{leg_idx + 1}" if len(legs) > 1 else "") + ")")
            name, n = base, 2
            while name in names:
                name, n = f"{base} {n}", n + 1
            names.add(name)
            label = SORT_REQUIRED_TYPES[target.pdi_type]
            sorter = Step(
                name=name, source_type="Sort rows", pdi_type="SortRows",
                confidence=Confidence.REVIEW,
                fields=[FieldDef(name=k) for k in keys],
                properties={INSERTED_MARK: "sorted-input"},
                notes=[
                    f"INSERTED by the converter: PDI's {label} step "
                    f"requires rows sorted by {', '.join(keys)} - the "
                    "source engine sorted internally, PDI does not, and "
                    "unsorted input produces silently wrong results. "
                    "Verify the keys and direction (ascending assumed)."])
            # the existing hop keeps its LIST POSITION and becomes
            # sorter->target (Merge Join reads its two input steps from
            # hop order - appending instead would swap the join legs);
            # a new hop feeds the sorter from the original upstream
            pipeline.hops.append(Hop(from_step=hop.from_step, to_step=name))
            hop.from_step = name
            pipeline.steps.insert(pipeline.steps.index(target), sorter)
            inserted += 1
    return inserted
