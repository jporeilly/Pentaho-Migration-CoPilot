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

from pentaho_migration.ir import Hop, Pipeline, Step

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

# PDI step types whose semantics REQUIRE sorted input, and the sorters
# that satisfy them. ONE definition: the mapper's sorter insertion and
# the review agent's lint both read these - the hazard cannot drift
# between the tool that fixes it and the tool that checks it.
SORT_REQUIRED_TYPES = {"GroupBy": "Group By", "MergeJoin": "Merge Join",
                       "Unique": "Unique rows"}
SORTER_TYPES = {"SortRows"}
# step.properties marker for steps the CONVERTER synthesized (they have
# no source-tool counterpart; the source diagram hides them)
INSERTED_MARK = "inserted"


def group_key_fields(step) -> list[str]:
    """The group-by key columns of a GroupBy step, from either dialect:
    Talend's GROUPBYS table, or Informatica's port metadata (GROUPBY
    expression type; plain pass-through ports count as keys the same way
    the Aggregator treats them)."""
    rows = _table_rows(step, "GROUPBYS")
    if rows:
        return [r.get("INPUT_COLUMN", "") for r in rows if r.get("INPUT_COLUMN")]
    expression_fields = {e.field for e in step.expressions}
    return [f.name for f in step.fields
            if f.attrs.get("EXPRESSIONTYPE") == "GROUPBY"
            or (f.name not in expression_fields
                and not f.attrs.get("EXPRESSIONTYPE"))]


def sort_keys_for(step, leg: int, pipeline) -> list[str]:
    """The columns a Sort rows step upstream of `step` must sort by, for
    incoming leg `leg` (hop order). Empty when the keys are not knowable
    from the export - the caller then leaves the hazard flagged instead
    of inserting a sort that sorts nothing."""
    if step.pdi_type == "GroupBy":
        return group_key_fields(step)
    if step.pdi_type == "MergeJoin":
        pairs = CONDITION_RE.findall(step.properties.get("Join Condition", ""))
        if not pairs:
            return []
        return [left for left, _r in pairs] if leg == 0 \
            else [right for _l, right in pairs]
    if step.pdi_type == "Unique":
        rows = _table_rows(step, "UNIQUE_KEY") or _table_rows(step, "KEYS")
        keys = [r.get("COLNAME") or r.get("KEY_COLUMN", "") for r in rows]
        return [k for k in keys if k]
    return []


def leg_has_sorter(pipeline, start: str) -> bool:
    """Walk upward from `start` (inclusive) looking for a Sort rows step.
    Another sort-requiring step resets the guarantee - its output order
    is its own concern, not a promise to what follows."""
    seen: set = set()
    frontier = [start]
    while frontier:
        name = frontier.pop()
        if name in seen:
            continue
        seen.add(name)
        step = pipeline.step(name)
        if step is None:
            continue
        if step.pdi_type in SORTER_TYPES:
            return True
        if step.pdi_type in SORT_REQUIRED_TYPES:
            continue
        frontier.extend(h.from_step for h in pipeline.hops
                        if h.to_step == name)
    return False

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
        SubElement(step_el, "distribute").text = "Y"
        SubElement(step_el, "copies").text = "1"

        if emitter := STEP_CONFIG_EMITTERS.get(pdi_type):
            emitter(step, step_el, pipeline)  # may append step.notes

        description = [f"[confidence: {step.confidence.value}]", *step.notes]
        for expr in step.expressions:
            if expr.translated is None:
                description.append(f"TODO expression [{expr.field}]: {expr.raw}")
            else:
                description.append(f"translated [{expr.field}] — verify: {expr.raw}")
        desc_el = Element("description")
        desc_el.text = "\n".join(description)
        step_el.insert(1, desc_el)  # right after <name> for readability

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


def _table_rows(step: Step, key: str) -> list[dict]:
    """Talend TABLE params are stored as JSON rows by the parser."""
    import json

    raw = step.properties.get(key, "")
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except ValueError:
            pass
    return []


# PDI datatype names for text-file field configs (IR datatype -> PDI type).
PDI_FIELD_TYPES = {
    "string": "String",
    "integer": "Integer",
    "small integer": "Integer",
    "bigint": "Integer",
    "double": "Number",
    "decimal": "BigNumber",
    "date/time": "Date",
}


def _emit_sort_rows(step: Step, el: Element, pipeline: Pipeline) -> None:
    SubElement(el, "directory").text = "%%java.io.tmpdir%%"
    SubElement(el, "prefix").text = "out"
    SubElement(el, "sort_size").text = "1000000"
    fields = SubElement(el, "fields")
    criteria = _table_rows(step, "CRITERIA")  # Talend tSortRow sort table
    if criteria:
        for row in criteria:
            field = SubElement(fields, "field")
            SubElement(field, "name").text = row.get("COLNAME", "")
            SubElement(field, "ascending").text = (
                "N" if row.get("ORDER", "asc").lower().startswith("desc") else "Y")
            SubElement(field, "case_sensitive").text = "N"
        return
    for f in step.fields:
        field = SubElement(fields, "field")
        SubElement(field, "name").text = f.name
        SubElement(field, "ascending").text = "Y"
        SubElement(field, "case_sensitive").text = "N"


# Talend aggregate FUNCTION values -> PDI Group By aggregate type codes.
TALEND_AGGREGATES = {
    "sum": "SUM", "count": "COUNT_ALL", "avg": "AVERAGE", "average": "AVERAGE",
    "min": "MIN", "max": "MAX", "first": "FIRST", "last": "LAST",
    "count_distinct": "COUNT_DISTINCT", "list": "CONCAT_COMMA",
    "std_dev": "STD_DEV",
}


def _emit_group_by(step: Step, el: Element, pipeline: Pipeline) -> None:
    groupbys = _table_rows(step, "GROUPBYS")     # Talend tAggregateRow tables
    operations = _table_rows(step, "OPERATIONS")
    if groupbys or operations:
        SubElement(el, "all_rows").text = "N"
        group = SubElement(el, "group")
        for row in groupbys:
            field = SubElement(group, "field")
            SubElement(field, "name").text = row.get("INPUT_COLUMN", "")
        fields = SubElement(el, "fields")
        for row in operations:
            func = row.get("FUNCTION", "").lower()
            pdi_type = TALEND_AGGREGATES.get(func)
            field = SubElement(fields, "field")
            SubElement(field, "aggregate").text = row.get("OUTPUT_COLUMN", "")
            SubElement(field, "subject").text = row.get("INPUT_COLUMN", "")
            SubElement(field, "type").text = pdi_type or "COUNT_ALL"
            if pdi_type is None:
                step.notes.append(
                    f"aggregate function {func!r} has no direct Group By type - "
                    f"emitted COUNT_ALL for '{row.get('OUTPUT_COLUMN', '')}', fix in Spoon")
        return
    SubElement(el, "all_rows").text = "N"
    group = SubElement(el, "group")
    for key in group_key_fields(step):
        field = SubElement(group, "field")
        SubElement(field, "name").text = key

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


def _infer_update_keys(step: Step, pipeline: Pipeline):
    """(target_step, key_field_names) for an Insert/Update step: follow the
    flow to the target it writes into and take that target's PRIMARY KEY
    fields (Informatica's update-strategy flags never name the keys, but the
    target definition does)."""
    seen, queue = set(), [h.to_step for h in pipeline.hops if h.from_step == step.name]
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        nxt = pipeline.step(name)
        if nxt is not None and nxt.source_type == "Target":
            keys = [f.name for f in nxt.fields
                    if "PRIMARY" in f.attrs.get("KEYTYPE", "")]
            return nxt, keys
        queue += [h.to_step for h in pipeline.hops if h.from_step == name]
    return None, []


def _emit_insert_update(step: Step, el: Element, pipeline: Pipeline) -> None:
    outgoing = [h.to_step for h in pipeline.hops if h.from_step == step.name]
    target, keys = _infer_update_keys(step, pipeline)
    SubElement(el, "connection")
    SubElement(el, "commit").text = "100"
    SubElement(el, "update_bypassed").text = "N"
    lookup = SubElement(el, "lookup")
    SubElement(lookup, "schema")
    SubElement(lookup, "table").text = (
        target.name if target is not None else (outgoing[0] if outgoing else step.name))
    # match keys inferred from the target's PRIMARY KEY fields; = comparison
    for key in keys:
        k = SubElement(lookup, "key")
        SubElement(k, "name").text = key
        SubElement(k, "field").text = key
        SubElement(k, "condition").text = "="
        SubElement(k, "name2")
    if not keys:
        # no primary key on the target -> can't infer; the step description
        # carries the TODO (added in the mapper notes)
        step.notes.append("Insert/Update keys could not be inferred (target has "
                           "no PRIMARY KEY) - set the match keys by hand in PDI")
    # update columns: the target's non-key fields, or the step's own fields
    update_fields = ([f.name for f in target.fields if f.name not in keys]
                     if target is not None and target.fields
                     else [f.name for f in step.fields])
    for name in update_fields:
        value = SubElement(lookup, "value")
        SubElement(value, "name").text = name
        SubElement(value, "rename").text = name
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


def _talend_literal(step: Step, *keys: str, default: str = "") -> str:
    for key in keys:
        value = step.properties.get(key, "")
        if value:
            return _clean_java_string(value)
    return default


def _emit_csv_input(step: Step, el: Element, pipeline: Pipeline) -> None:
    """tFileInputDelimited -> CSV file input, config carried from the .item:
    filename, separator, enclosure, header, and the typed schema."""
    SubElement(el, "filename").text = _talend_literal(step, "FILENAME", "FILENAMETEXT")
    SubElement(el, "separator").text = _talend_literal(step, "FIELDSEPARATOR", default=";")
    SubElement(el, "enclosure").text = _talend_literal(step, "TEXT_ENCLOSURE", default='"')
    header = step.properties.get("HEADER", "0").strip('"')
    SubElement(el, "header").text = "Y" if header not in ("", "0") else "N"
    SubElement(el, "buffer_size").text = "50000"
    SubElement(el, "lazy_conversion").text = "N"
    SubElement(el, "add_filename_result").text = "N"
    SubElement(el, "parallel").text = "N"
    SubElement(el, "encoding").text = _talend_literal(step, "ENCODING", default="UTF-8")
    fields = SubElement(el, "fields")
    for f in step.fields:
        field = SubElement(fields, "field")
        SubElement(field, "name").text = f.name
        SubElement(field, "type").text = PDI_FIELD_TYPES.get(f.datatype, "String")
        SubElement(field, "length").text = "-1"
        SubElement(field, "precision").text = "-1"
        SubElement(field, "trim_type").text = "none"


def _emit_text_file_output(step: Step, el: Element, pipeline: Pipeline) -> None:
    """tFileOutputDelimited -> Text file output with the .item config."""
    SubElement(el, "separator").text = _talend_literal(step, "FIELDSEPARATOR", default=";")
    SubElement(el, "enclosure").text = _talend_literal(step, "TEXT_ENCLOSURE", default='"')
    SubElement(el, "enclosure_forced").text = "N"
    SubElement(el, "header").text = (
        "Y" if step.properties.get("INCLUDEHEADER", "false") == "true" else "N")
    SubElement(el, "footer").text = "N"
    SubElement(el, "format").text = "DOS"
    SubElement(el, "encoding").text = _talend_literal(step, "ENCODING", default="UTF-8")
    SubElement(el, "append").text = (
        "Y" if step.properties.get("APPEND", "false") == "true" else "N")
    filename = SubElement(el, "file")
    name = _talend_literal(step, "FILENAME")
    stem, dot, ext = name.rpartition(".")
    SubElement(filename, "name").text = stem if dot else name
    SubElement(filename, "extention").text = ext if dot else "txt"
    SubElement(filename, "add_date").text = "N"
    SubElement(filename, "add_time").text = "N"
    fields = SubElement(el, "fields")
    for f in step.fields:
        field = SubElement(fields, "field")
        SubElement(field, "name").text = f.name
        SubElement(field, "type").text = PDI_FIELD_TYPES.get(f.datatype, "String")
        SubElement(field, "format").text = ""
        SubElement(field, "length").text = "-1"
        SubElement(field, "precision").text = "-1"


# Talend filter operators -> PDI Filter rows functions.
FILTER_OPERATORS = {
    "==": "=", "!=": "<>", ">": ">", "<": "<", ">=": ">=", "<=": "<=",
}


def _emit_filter_rows(step: Step, el: Element, pipeline: Pipeline) -> None:
    """tFilterRow simple conditions -> Filter rows condition tree. Advanced
    (Java) mode stays a TODO in the step description; the true/false targets
    are wired in Spoon (Talend FILTER/REJECT hops carry no PDI equivalent
    metadata here)."""
    conditions = _table_rows(step, "CONDITIONS")
    if step.properties.get("USE_ADVANCED") == "true" or not conditions:
        step.notes.append(
            "tFilterRow uses advanced (Java) mode or has no simple conditions - "
            "recreate the condition in Filter rows"
            if step.properties.get("USE_ADVANCED") == "true"
            else "tFilterRow carried no simple conditions - configure Filter rows in Spoon")
        return
    logical = "OR" if step.properties.get("LOGICAL_OP", "&&") == "||" else "AND"

    def _condition_el(parent, row, operator=None):
        cond = SubElement(parent, "condition")
        SubElement(cond, "negation").text = "N"
        if operator:
            SubElement(cond, "operator").text = operator
        SubElement(cond, "leftvalue").text = row.get("INPUT_COLUMN", "")
        rvalue = row.get("RVALUE", "").strip()
        if rvalue in ("null", "None", ""):
            SubElement(cond, "function").text = (
                "IS NULL" if row.get("OPERATOR") == "==" else "IS NOT NULL")
            SubElement(cond, "rightvalue")
            return
        SubElement(cond, "function").text = FILTER_OPERATORS.get(
            row.get("OPERATOR", "=="), "=")
        value = SubElement(cond, "value")
        SubElement(value, "name").text = "constant"
        SubElement(value, "type").text = "String"
        SubElement(value, "text").text = rvalue.strip('"')
        SubElement(value, "isnull").text = "N"

    compare = SubElement(el, "compare")
    if len(conditions) == 1:
        _condition_el(compare, conditions[0])
    else:
        outer = SubElement(compare, "condition")
        SubElement(outer, "negation").text = "N"
        for i, row in enumerate(conditions):
            _condition_el(outer, row, operator=None if i == 0 else logical)
    step.notes.append(
        "Filter rows condition carried from tFilterRow - wire the true/false "
        "target steps (Talend FILTER/REJECT flows) in Spoon")


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
    "CsvInput": _emit_csv_input,
    "TextFileOutput": _emit_text_file_output,
    "FilterRows": _emit_filter_rows,
}
