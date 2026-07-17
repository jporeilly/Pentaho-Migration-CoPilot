"""AI solution suggestions for individual steps (on-demand, never automatic).

Given one step's real context — source component, its configuration, fields,
expressions, and the impact knowledge base's known differences — the configured
LLM proposes a concrete PDI implementation plan. Output is advisory markdown
for a human engineer; nothing is applied to the generated artifacts.
"""

import httpx

from pdi_migration.ir import Pipeline, Step
from pdi_migration.llm.settings import LLMSettings, load_settings
from pdi_migration.llm.translate import TranslationError

SYSTEM_PROMPT = """\
You are a senior Pentaho Data Integration (PDI/Kettle) migration engineer. Given one
component from a legacy ETL job and its known behavioral differences, propose a
concrete, actionable PDI solution.

Structure your answer as markdown:
## Recommended approach
(1-3 sentences: which PDI step(s) and why)
## Configuration
(bullet list of the specific settings to apply, using the real field/property names given)
## Code
(only if needed: SQL or PDI JavaScript, in a fenced block)
## Watch out for
(the 1-3 most likely ways this conversion silently breaks)

Rules: be specific to the given configuration, not generic. If information is missing,
say exactly what to check in the original job. Stay under 300 words. Never invent
field names that were not provided."""


class SolutionSuggester:
    def __init__(self, settings: LLMSettings | None = None, timeout: float = 180.0):
        self.settings = settings or load_settings()
        self.timeout = timeout

    def suggest(self, pipeline: Pipeline, step_name: str, impact_entry: dict | None) -> str:
        self._check_provider()
        step = pipeline.step(step_name)
        if step is None:
            raise ValueError(f"step '{step_name}' not found in pipeline")
        return self._chat(self._context(pipeline, step, impact_entry))

    def _context(self, pipeline: Pipeline, step: Step, impact_entry: dict | None) -> str:
        neighbors_in = [h.from_step for h in pipeline.hops if h.to_step == step.name]
        neighbors_out = [h.to_step for h in pipeline.hops if h.from_step == step.name]
        lines = [
            f"Source tool: {pipeline.source_tool.value}",
            f"Step: {step.name}",
            f"Source component/type: {step.source_type}",
            f"Mapped PDI step: {step.pdi_type or 'NONE - unmapped, needs a from-scratch design'}",
            f"Confidence: {step.confidence.value}",
            f"Upstream steps: {', '.join(neighbors_in) or 'none'}",
            f"Downstream steps: {', '.join(neighbors_out) or 'none'}",
        ]
        if step.fields:
            lines.append("Fields: " + ", ".join(
                f"{f.name} ({f.datatype})" for f in step.fields[:25]
            ))
        interesting = {
            k: v for k, v in step.properties.items()
            if v and k not in ("UNIQUE_NAME",) and len(v) < 500
        }
        if interesting:
            lines.append("Configuration properties:")
            lines.extend(f"  {k} = {v}" for k, v in list(interesting.items())[:15])
        if step.expressions:
            lines.append("Expressions:")
            for e in step.expressions[:10]:
                lines.append(f"  {e.field} = {e.raw}" + (
                    f"  (translated: {e.translated})" if e.translated else ""
                ))
        if step.notes:
            lines.append("Mapper notes: " + "; ".join(step.notes))
        if impact_entry:
            if impact_entry.get("differences"):
                lines.append("Known behavioral differences: " + " | ".join(impact_entry["differences"]))
            if impact_entry.get("actions"):
                lines.append("Required actions already identified: " + " | ".join(impact_entry["actions"]))
        return "\n".join(lines)

    def _check_provider(self) -> None:
        if self.settings.provider == "none":
            raise TranslationError("LLM suggestions are disabled — choose a provider in Settings.")
        if self.settings.provider == "anthropic":
            raise TranslationError("The Anthropic provider is not implemented yet — use Ollama.")
        if not self.settings.model:
            raise TranslationError("No Ollama model configured — open Settings and apply the recommendation.")

    def _chat(self, context: str) -> str:
        response = httpx.post(
            f"{self.settings.base_url}/api/chat",
            json={
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Propose the PDI solution for this step:\n\n{context}"},
                ],
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
