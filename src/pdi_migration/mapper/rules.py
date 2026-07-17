"""Rules-library mapper (Stage 2: MAP, deterministic half).

Applies known 1:1 step equivalents from a YAML rules file. Steps with no rule
are marked MANUAL and left for the LLM mapper or human handoff — the mapper
never guesses.
"""

from pathlib import Path

import yaml

from pdi_migration.ir import Confidence, Pipeline

DEFAULT_RULES = Path(__file__).resolve().parents[3] / "rules" / "powercenter_to_pdi.yaml"


class RulesMapper:
    def __init__(self, rules_path: str | Path = DEFAULT_RULES):
        with open(rules_path, encoding="utf-8") as f:
            self.rules: dict[str, dict] = yaml.safe_load(f)

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
