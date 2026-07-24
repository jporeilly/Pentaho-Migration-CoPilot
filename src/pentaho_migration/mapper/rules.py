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


class RulesMapper:
    def __init__(self, rules_path: str | Path = DEFAULT_RULES):
        with open(rules_path, encoding="utf-8") as f:
            loaded: dict = yaml.safe_load(f)
        # keys starting with "_" are governance metadata, not mapping rules
        self.meta: dict = loaded.get("_meta", {})
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
                step.notes.append(
                    f"No mapping rule for '{step.source_type}' — manual conversion required."
                )
                continue
            step.pdi_type = rule["pdi_type"]
            step.confidence = Confidence(rule.get("confidence", "review"))
            if note := rule.get("notes"):
                step.notes.append(note)
            # Untranslated expressions force at least REVIEW even on an AUTO rule.
            if step.expressions and step.confidence == Confidence.AUTO:
                step.confidence = Confidence.REVIEW
        return pipeline
