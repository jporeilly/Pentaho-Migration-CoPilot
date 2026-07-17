"""Deterministic parser for Informatica PowerCenter XML exports (Stage 1: PARSE).

PowerCenter exports are structured XML (POWERMART > REPOSITORY > FOLDER >
MAPPING), so no AI is involved here — real parsing only, per the design
principle that accuracy in this stage is non-negotiable.
"""

from pathlib import Path
from xml.etree import ElementTree

from pdi_migration.ir import Confidence, Expression, FieldDef, Hop, Pipeline, SourceTool, Step


class PowerCenterParseError(Exception):
    pass


class PowerCenterParser:
    def parse_file(self, path: str | Path) -> list[Pipeline]:
        tree = ElementTree.parse(path)
        root = tree.getroot()
        if root.tag != "POWERMART":
            raise PowerCenterParseError(
                f"{path}: expected a PowerCenter export (root POWERMART), got <{root.tag}>"
            )
        return [
            self._parse_mapping(mapping)
            for mapping in root.iter("MAPPING")
        ]

    def _parse_mapping(self, mapping: ElementTree.Element) -> Pipeline:
        pipeline = Pipeline(
            name=mapping.get("NAME", "unnamed_mapping"),
            source_tool=SourceTool.POWERCENTER,
            metadata={"isvalid": mapping.get("ISVALID", "")},
        )

        for xform in mapping.iter("TRANSFORMATION"):
            pipeline.steps.append(self._parse_transformation(xform))

        # Source/target instances appear as INSTANCE elements, not TRANSFORMATION.
        for instance in mapping.iter("INSTANCE"):
            if instance.get("TYPE") in ("SOURCE", "TARGET") and not pipeline.step(
                instance.get("NAME", "")
            ):
                pipeline.steps.append(
                    Step(
                        name=instance.get("NAME", "unnamed"),
                        source_type=instance.get("TYPE", "").title(),
                    )
                )

        seen: set[tuple[str, str]] = set()
        for conn in mapping.iter("CONNECTOR"):
            edge = (conn.get("FROMINSTANCE", ""), conn.get("TOINSTANCE", ""))
            if all(edge) and edge not in seen:
                seen.add(edge)
                pipeline.hops.append(Hop(from_step=edge[0], to_step=edge[1]))

        return pipeline

    def _parse_transformation(self, xform: ElementTree.Element) -> Step:
        step = Step(
            name=xform.get("NAME", "unnamed"),
            source_type=xform.get("TYPE", "Unknown"),
        )
        for field in xform.iter("TRANSFORMFIELD"):
            name = field.get("NAME", "")
            attrs = {
                key: value
                for key in ("PORTTYPE", "EXPRESSIONTYPE")
                if (value := field.get(key))
            }
            step.fields.append(
                FieldDef(
                    name=name,
                    datatype=field.get("DATATYPE", "string"),
                    precision=_to_int(field.get("PRECISION")),
                    scale=_to_int(field.get("SCALE")),
                    attrs=attrs,
                )
            )
            raw_expr = field.get("EXPRESSION")
            # Passthrough ports repeat the field name as their expression; only
            # real derivations need translation.
            if raw_expr and raw_expr != name:
                step.expressions.append(
                    Expression(field=name, raw=raw_expr, confidence=Confidence.MANUAL)
                )
        for attr in xform.iter("TABLEATTRIBUTE"):
            step.properties[attr.get("NAME", "")] = attr.get("VALUE", "")
        return step


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None
