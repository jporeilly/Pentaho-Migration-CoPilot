"""Rules-library mapper (Stage 2: MAP, deterministic half).

Applies known 1:1 step equivalents from a YAML rules file. Steps with no rule
are marked MANUAL and left for the LLM mapper or human handoff — the mapper
never guesses.
"""

from pathlib import Path

import yaml

from pentaho_migration.ir import Confidence, Pipeline, SourceTool

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
        return pipeline
