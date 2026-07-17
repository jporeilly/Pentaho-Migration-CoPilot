"""KTR generator (Stage 3: GENERATE) — deterministic templating from the IR.

Emits a .ktr skeleton: correct step types, names, hops, and layout, with each
step's IR notes carried into the step description so they surface in Spoon.
Per-step-type configuration (Group By aggregations, join keys, ...) is the
next milestone; unconfigured steps are honest placeholders, never guesses.
"""

from pathlib import Path
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

from pdi_migration.ir import Pipeline

# Placeholder for IR steps the mapper could not map.
FALLBACK_STEP_TYPE = "Dummy"


class KtrGenerator:
    def generate(self, pipeline: Pipeline) -> str:
        root = Element("transformation")
        info = SubElement(root, "info")
        SubElement(info, "name").text = pipeline.name
        SubElement(info, "description").text = (
            f"Converted from {pipeline.source_tool.value} by Migration Copilot. "
            "Review all steps marked review/manual before use."
        )
        SubElement(root, "notepads")

        order = SubElement(root, "order")
        for hop in pipeline.hops:
            hop_el = SubElement(order, "hop")
            SubElement(hop_el, "from").text = hop.from_step
            SubElement(hop_el, "to").text = hop.to_step
            SubElement(hop_el, "enabled").text = "Y"

        for i, step in enumerate(pipeline.steps):
            step_el = SubElement(root, "step")
            SubElement(step_el, "name").text = step.name
            SubElement(step_el, "type").text = step.pdi_type or FALLBACK_STEP_TYPE
            description = [f"[confidence: {step.confidence.value}]", *step.notes]
            for expr in step.expressions:
                description.append(f"TODO expression [{expr.field}]: {expr.raw}")
            SubElement(step_el, "description").text = "\n".join(description)
            SubElement(step_el, "distribute").text = "Y"
            SubElement(step_el, "copies").text = "1"
            gui = SubElement(step_el, "GUI")
            SubElement(gui, "xloc").text = str(100 + i * 200)
            SubElement(gui, "yloc").text = "100"
            SubElement(gui, "draw").text = "Y"

        ElementTree.indent(root)
        return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)

    def write(self, pipeline: Pipeline, out_dir: str | Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{pipeline.name}.ktr"
        out_path.write_text(self.generate(pipeline), encoding="utf-8")
        return out_path
