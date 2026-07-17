"""Deterministic parser for Talend job design files (.item) — Stage 1: PARSE.

A Talend job is one XML file: <talendfile:ProcessType> containing <node>
elements (componentName + elementParameter children + <metadata><column>
schemas) and <connection> row links. tMap logic lives in a nested
<nodeData xsi:type="mapper:MapperData"> block whose output entries carry
Java expressions.

One .item file = one job = one Pipeline (unlike PowerCenter's multi-mapping
exports).
"""

from pathlib import Path
from xml.etree import ElementTree

from pdi_migration.ir import (
    Confidence,
    Expression,
    FieldDef,
    Hop,
    Pipeline,
    SourceInfo,
    SourceTool,
    Step,
)

# Talend column types -> normalized IR datatypes.
TALEND_DATATYPES = {
    "id_String": "string",
    "id_Character": "string",
    "id_Integer": "integer",
    "id_Short": "small integer",
    "id_Long": "bigint",
    "id_BigDecimal": "decimal",
    "id_Float": "double",
    "id_Double": "double",
    "id_Date": "date/time",
    "id_Boolean": "string",
    "id_Byte": "integer",
    "id_Object": "string",
}

# Row-flow connector styles; everything else (RUN_IF, OK, ERROR, LOOKUP...)
# is orchestration or lookup wiring, handled separately.
FLOW_CONNECTORS = {"FLOW", "MAIN", "FILTER", "REJECT", "UNIQUE", "DUPLICATE"}


from pdi_migration.parser.errors import ParseError


class TalendParseError(ParseError):
    pass


def _local(tag: str) -> str:
    """Strip the XML namespace: '{platform:/...}ProcessType' -> 'ProcessType'."""
    return tag.rsplit("}", 1)[-1]


class TalendParser:
    def parse_file(self, path: str | Path) -> list[Pipeline]:
        root = self._root(path)
        pipeline = Pipeline(
            name=self._job_name(path),
            source_tool=SourceTool.TALEND,
        )
        names: dict[ElementTree.Element, str] = {}
        for node in root.iter():
            if _local(node.tag) != "node":
                continue
            step = self._parse_node(node)
            names[node] = step.name
            pipeline.steps.append(step)

        for conn in root.iter():
            if _local(conn.tag) != "connection":
                continue
            connector = conn.get("connectorName", "")
            source = conn.get("source", "")
            target = conn.get("target", "")
            if source and target and (
                connector in FLOW_CONNECTORS or connector.startswith("LOOKUP")
            ):
                pipeline.hops.append(Hop(from_step=source, to_step=target))
        return [pipeline]

    def analyze_export(self, path: str | Path) -> SourceInfo:
        root = self._root(path)
        nodes = [n for n in root.iter() if _local(n.tag) == "node"]
        components = {n.get("componentName", "") for n in nodes}
        # tRunJob calls another job — the closest thing to a workflow reference
        run_jobs = sum(1 for n in nodes if n.get("componentName") == "tRunJob")
        return SourceInfo(
            tool="Talend",
            product_version=root.get("version") or None,
            repository_name=self._job_name(path),
            mappings=1,
            workflows=run_jobs,   # surfaced as orchestration to review
            mapplets=sum(1 for c in components if c in ("tJoblet",)),
        )

    def _root(self, path: str | Path) -> ElementTree.Element:
        root = ElementTree.parse(path).getroot()
        if _local(root.tag) != "ProcessType":
            raise TalendParseError(
                f"{path}: expected a Talend job (.item with talendfile:ProcessType root), "
                f"got <{_local(root.tag)}>"
            )
        return root

    def _job_name(self, path: str | Path) -> str:
        # process/<JobName>_<major>.<minor>.item -> JobName
        stem = Path(path).stem
        parts = stem.rsplit("_", 1)
        if len(parts) == 2 and parts[1].replace(".", "").isdigit():
            return parts[0]
        return stem

    def _parse_node(self, node: ElementTree.Element) -> Step:
        component = node.get("componentName", "Unknown")
        params: dict[str, str] = {}
        for param in node.iter():
            if _local(param.tag) == "elementParameter" and param.get("name"):
                params[param.get("name")] = param.get("value", "")
        name = params.get("UNIQUE_NAME", component)

        step = Step(name=name, source_type=component, properties=params)
        for metadata in node.iter():
            if _local(metadata.tag) != "metadata":
                continue
            for column in metadata.iter():
                if _local(column.tag) != "column":
                    continue
                step.fields.append(FieldDef(
                    name=column.get("name", ""),
                    datatype=TALEND_DATATYPES.get(column.get("type", ""), "string"),
                    precision=_to_int(column.get("length")),
                    scale=_to_int(column.get("precision")),
                    nullable=column.get("nullable", "true") == "true",
                ))
            break  # first metadata table is the main flow schema

        self._parse_mapper_expressions(node, step)
        return step

    def _parse_mapper_expressions(self, node: ElementTree.Element, step: Step) -> None:
        """tMap output expressions live in nodeData (mapper:MapperData):
        outputTables/mapperTableEntries with name + expression attributes."""
        for node_data in node.iter():
            if _local(node_data.tag) != "nodeData":
                continue
            for table in node_data.iter():
                if _local(table.tag) not in ("outputTables", "varTables"):
                    continue
                for entry in table.iter():
                    if _local(entry.tag) != "mapperTableEntries":
                        continue
                    expression = (entry.get("expression") or "").strip()
                    field = entry.get("name", "")
                    if not expression or not field:
                        continue
                    # bare column passthrough like "row1.CUSTOMER_ID" isn't a derivation
                    if _is_passthrough(expression, field):
                        continue
                    step.expressions.append(Expression(
                        field=field,
                        raw=expression,
                        language="java",
                        confidence=Confidence.MANUAL,
                    ))


def _is_passthrough(expression: str, field: str) -> bool:
    parts = expression.split(".")
    return (
        len(parts) == 2
        and parts[1] == field
        and parts[0].replace("_", "").isalnum()
    )


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None
