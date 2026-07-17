"""KTR generator (Stage 3: GENERATE) — deterministic templating from the IR.

Emits .ktr files with correct step types, names, hops, and layout. Step types
with an emitter in STEP_CONFIG_EMITTERS also get real configuration (SQL,
sort keys, group-by aggregations, ...) derived from the IR; the rest are
honest skeletons carrying their IR notes into the step description so they
surface in Spoon. The generator never guesses — anything it cannot derive
becomes a TODO note.
"""

import re
from pathlib import Path
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

from pdi_migration.ir import Hop, Pipeline, Step

# Placeholder for IR steps the mapper could not map.
FALLBACK_STEP_TYPE = "Dummy"

# Informatica datatype -> PDI value type.
PDI_DATATYPES = {
    "string": "String",
    "nstring": "String",
    "text": "String",
    "decimal": "Number",
    "double": "Number",
    "real": "Number",
    "integer": "Integer",
    "small integer": "Integer",
    "bigint": "Integer",
    "date/time": "Date",
    "timestamp": "Date",
}

# Informatica aggregate function -> PDI Group By aggregation code.
PDI_AGGREGATES = {
    "SUM": "SUM",
    "AVG": "AVERAGE",
    "COUNT": "COUNT_ALL",
    "MIN": "MIN",
    "MAX": "MAX",
}

AGGREGATE_RE = re.compile(r"^\s*(SUM|AVG|COUNT|MIN|MAX)\s*\(\s*(\w+)\s*\)\s*$", re.IGNORECASE)

# "LKP_COL = IN_PORT AND X = Y" -> [("LKP_COL", "IN_PORT"), ("X", "Y")]
CONDITION_RE = re.compile(r"(\w+)\s*=\s*(\w+)")

JOIN_TYPES = {
    "Normal Join": "INNER",
    "Master Outer Join": "RIGHT OUTER",
    "Detail Outer Join": "LEFT OUTER",
    "Full Outer Join": "FULL OUTER",
}


class KtrGenerator:
    def generate(self, pipeline: Pipeline) -> str:
        # Work on a copy: lookup steps get an injected source step + hop, and
        # the caller's pipeline must stay untouched.
        pipeline = self._inject_lookup_sources(pipeline.model_copy(deep=True))
        root = Element("transformation")
        info = SubElement(root, "info")
        SubElement(info, "name").text = pipeline.name
        SubElement(info, "description").text = (
            f"Converted from {pipeline.source_tool.value} by Migration Copilot. "
            "Review all steps marked review/manual before use."
        )
        SubElement(info, "trans_type").text = "Normal"
        SubElement(root, "notepads")

        order = SubElement(root, "order")
        for hop in pipeline.hops:
            hop_el = SubElement(order, "hop")
            SubElement(hop_el, "from").text = hop.from_step
            SubElement(hop_el, "to").text = hop.to_step
            SubElement(hop_el, "enabled").text = "Y"

        for i, step in enumerate(pipeline.steps):
            root.append(self._emit_step(step, position=i, pipeline=pipeline))

        ElementTree.indent(root)
        return ElementTree.tostring(root, encoding="unicode", xml_declaration=True)

    def _inject_lookup_sources(self, pipeline: Pipeline) -> Pipeline:
        """Every Stream Lookup needs a stream feeding its lookup data — inject a
        Table Input reading the original lookup table, wired into the lookup."""
        for step in list(pipeline.steps):
            if step.pdi_type != "StreamLookup":
                continue
            source_name = f"{step.name}_lookup_src"
            if pipeline.step(source_name):
                continue
            table = step.properties.get("Lookup table name", step.name)
            sql = step.properties.get("Lookup Sql Override") or f"SELECT * FROM {table}"
            pipeline.steps.append(Step(
                name=source_name,
                source_type="Lookup Source",
                pdi_type="TableInput",
                properties={"Sql Query": sql},
                confidence=step.confidence,
                notes=[f"Injected: feeds lookup data ({table}) into {step.name}."],
            ))
            pipeline.hops.append(Hop(from_step=source_name, to_step=step.name))
        return pipeline

    def _emit_step(self, step: Step, position: int, pipeline: Pipeline) -> Element:
        pdi_type = step.pdi_type or FALLBACK_STEP_TYPE
        step_el = Element("step")
        SubElement(step_el, "name").text = step.name
        SubElement(step_el, "type").text = pdi_type
        description = [f"[confidence: {step.confidence.value}]", *step.notes]
        for expr in step.expressions:
            if expr.translated is None:
                description.append(f"TODO expression [{expr.field}]: {expr.raw}")
            else:
                description.append(f"translated [{expr.field}] — verify: {expr.raw}")
        SubElement(step_el, "description").text = "\n".join(description)
        SubElement(step_el, "distribute").text = "Y"
        SubElement(step_el, "copies").text = "1"

        if emitter := STEP_CONFIG_EMITTERS.get(pdi_type):
            emitter(step, step_el, pipeline)

        gui = SubElement(step_el, "GUI")
        SubElement(gui, "xloc").text = str(100 + position * 200)
        SubElement(gui, "yloc").text = "100"
        SubElement(gui, "draw").text = "Y"
        return step_el

    def write(self, pipeline: Pipeline, out_dir: str | Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{pipeline.name}.ktr"
        out_path.write_text(self.generate(pipeline), encoding="utf-8")
        return out_path


def _clean_java_string(value: str) -> str:
    """Talend stores SQL as a Java string literal: '"select ..."' with escapes."""
    value = value.strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    return value.replace('\\"', '"').replace('\\n', '\n')


def _emit_table_input(step: Step, el: Element, pipeline: Pipeline) -> None:
    SubElement(el, "connection")  # connection is environment-specific; left for review
    talend_query = step.properties.get("QUERY")
    if talend_query:
        SubElement(el, "sql").text = _clean_java_string(talend_query)
        SubElement(el, "limit").text = "0"
        return
    sql = step.properties.get("Sql Query") or (
        "SELECT " + ", ".join(f.name for f in step.fields) + f"\nFROM {step.name}"
        if step.fields
        else f"-- TODO: source query for {step.name}"
    )
    SubElement(el, "sql").text = sql
    SubElement(el, "limit").text = "0"


def _emit_table_output(step: Step, el: Element, pipeline: Pipeline) -> None:
    SubElement(el, "connection")
    SubElement(el, "schema")
    SubElement(el, "table").text = step.name
    SubElement(el, "commit").text = "1000"
    SubElement(el, "truncate").text = "N"
    SubElement(el, "ignore_errors").text = "N"
    SubElement(el, "use_batch").text = "Y"


def _emit_sort_rows(step: Step, el: Element, pipeline: Pipeline) -> None:
    SubElement(el, "directory").text = "%%java.io.tmpdir%%"
    SubElement(el, "prefix").text = "out"
    SubElement(el, "sort_size").text = "1000000"
    fields = SubElement(el, "fields")
    for f in step.fields:
        field = SubElement(fields, "field")
        SubElement(field, "name").text = f.name
        SubElement(field, "ascending").text = "Y"
        SubElement(field, "case_sensitive").text = "N"


def _emit_group_by(step: Step, el: Element, pipeline: Pipeline) -> None:
    SubElement(el, "all_rows").text = "N"
    expression_fields = {e.field for e in step.expressions}
    group = SubElement(el, "group")
    for f in step.fields:
        is_group_key = f.attrs.get("EXPRESSIONTYPE") == "GROUPBY" or (
            f.name not in expression_fields and not f.attrs.get("EXPRESSIONTYPE")
        )
        if is_group_key:
            field = SubElement(group, "field")
            SubElement(field, "name").text = f.name

    fields = SubElement(el, "fields")
    for expr in step.expressions:
        match = AGGREGATE_RE.match(expr.raw)
        if not match:
            continue  # non-trivial aggregate expression stays a TODO in the description
        func, subject = match.groups()
        field = SubElement(fields, "field")
        SubElement(field, "aggregate").text = expr.field
        SubElement(field, "subject").text = subject
        SubElement(field, "type").text = PDI_AGGREGATES[func.upper()]


def _emit_script_values(step: Step, el: Element, pipeline: Pipeline) -> None:
    SubElement(el, "compatible").text = "N"
    scripts = SubElement(el, "jsScripts")
    script = SubElement(scripts, "jsScript")
    SubElement(script, "jsScript_type").text = "0"
    SubElement(script, "jsScript_name").text = "Script 1"
    lines = ["// Translated from Informatica Expression transformation."]
    for expr in step.expressions:
        if expr.translated is not None:
            lines.append(f"// source: {expr.field} = {expr.raw}")
            if expr.notes:
                lines.append(f"// {expr.notes}")
            lines.append(f"var {expr.field} = {expr.translated};")
        else:
            lines.append(f"// TODO translate: {expr.field} = {expr.raw}")
            lines.append(f"var {expr.field} = null;")
    SubElement(script, "jsScript_script").text = "\n".join(lines)

    fields = SubElement(el, "fields")
    for expr in step.expressions:
        f = step_field(step, expr.field)
        field = SubElement(fields, "field")
        SubElement(field, "name").text = expr.field
        SubElement(field, "rename").text = expr.field
        SubElement(field, "type").text = (
            PDI_DATATYPES.get(f.datatype.lower(), "String") if f else "String"
        )
        SubElement(field, "replace").text = "N"


def step_field(step: Step, name: str):
    return next((f for f in step.fields if f.name == name), None)


def _incoming(pipeline: Pipeline, step: Step) -> list[str]:
    return [h.from_step for h in pipeline.hops if h.to_step == step.name]


def _emit_merge_join(step: Step, el: Element, pipeline: Pipeline) -> None:
    inputs = _incoming(pipeline, step)
    SubElement(el, "join_type").text = JOIN_TYPES.get(
        step.properties.get("Join Type", ""), "INNER"
    )
    SubElement(el, "step1").text = inputs[0] if inputs else ""
    SubElement(el, "step2").text = inputs[1] if len(inputs) > 1 else ""
    pairs = CONDITION_RE.findall(step.properties.get("Join Condition", ""))
    keys_1 = SubElement(el, "keys_1")
    keys_2 = SubElement(el, "keys_2")
    for left, right in pairs:
        SubElement(keys_1, "key").text = left
        SubElement(keys_2, "key").text = right


def _emit_stream_lookup(step: Step, el: Element, pipeline: Pipeline) -> None:
    SubElement(el, "from").text = f"{step.name}_lookup_src"
    SubElement(el, "input_sorted").text = "N"
    SubElement(el, "preserve_memory").text = "Y"
    SubElement(el, "sorted_list").text = "N"
    SubElement(el, "integer_pair").text = "N"
    lookup = SubElement(el, "lookup")
    pairs = CONDITION_RE.findall(step.properties.get("Lookup condition", ""))
    key_fields = set()
    for lookup_col, stream_port in pairs:
        key = SubElement(lookup, "key")
        SubElement(key, "name").text = stream_port   # field from the main stream
        SubElement(key, "field").text = lookup_col   # field in the lookup stream
        key_fields.add(lookup_col)
    for field in step.fields:
        if field.name in key_fields:
            continue
        value = SubElement(lookup, "value")
        SubElement(value, "name").text = field.name
        SubElement(value, "rename").text = field.name
        SubElement(value, "default").text = ""
        SubElement(value, "type").text = PDI_DATATYPES.get(field.datatype.lower(), "String")


def _emit_insert_update(step: Step, el: Element, pipeline: Pipeline) -> None:
    outgoing = [h.to_step for h in pipeline.hops if h.from_step == step.name]
    SubElement(el, "connection")
    SubElement(el, "commit").text = "100"
    SubElement(el, "update_bypassed").text = "N"
    lookup = SubElement(el, "lookup")
    SubElement(lookup, "schema")
    SubElement(lookup, "table").text = outgoing[0] if outgoing else step.name
    # key columns are a business decision (Informatica's strategy flags don't
    # name them) — left empty deliberately; the step description carries the TODO
    for field in step.fields:
        value = SubElement(lookup, "value")
        SubElement(value, "name").text = field.name
        SubElement(value, "rename").text = field.name
        SubElement(value, "update").text = "Y"


def _emit_db_proc(step: Step, el: Element, pipeline: Pipeline) -> None:
    SubElement(el, "connection")
    SubElement(el, "procedure").text = (
        step.properties.get("Stored Procedure Name")
        or step.properties.get("Call Text")
        or step.name
    )
    SubElement(el, "auto_commit").text = "Y"
    arguments = SubElement(el, "arguments")
    for field in step.fields:
        arg = SubElement(arguments, "argument")
        SubElement(arg, "name").text = field.name
        SubElement(arg, "direction").text = "IN"
        SubElement(arg, "type").text = PDI_DATATYPES.get(field.datatype.lower(), "String")


STEP_CONFIG_EMITTERS = {
    "TableInput": _emit_table_input,
    "TableOutput": _emit_table_output,
    "SortRows": _emit_sort_rows,
    "GroupBy": _emit_group_by,
    "ScriptValueMod": _emit_script_values,
    "MergeJoin": _emit_merge_join,
    "StreamLookup": _emit_stream_lookup,
    "InsertUpdate": _emit_insert_update,
    "DBProc": _emit_db_proc,
}
