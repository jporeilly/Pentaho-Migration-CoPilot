"""Parse RptToXml output into the intermediate ReportModel.

RptToXml (https://github.com/ajryan/RptToXml) dumps a Crystal .rpt via the
SAP Crystal Reports .NET SDK. Its rough shape:

    <Report Name=".." FileName="..">
      <Database>
        <Tables><Table Name=".." Alias=".."><Command>SQL</Command><Fields><Field .../></Fields></Table></Tables>
      </Database>
      <DataDefinition>
        <RecordSelectionFormula>..</RecordSelectionFormula>
        <Groups><Group ConditionField="{T.F}"/></Groups>
        <FormulaFieldDefinitions><FormulaFieldDefinition Name=".." ..>text</..></FormulaFieldDefinitions>
        <ParameterFieldDefinitions><ParameterFieldDefinition Name=".." ValueType=".."/></..>
        <SummaryFields><SummaryFieldDefinition Name=".." Operation="Sum" .../></..>
      </DataDefinition>
      <ReportDefinition>
        <Areas><Area Kind="Detail"><Sections><Section Height=".."><ReportObjects>
          <TextObject Text=".." Left=".." Top=".." Width=".." Height=".."/>
          <FieldObject DataSource="{T.F}" .../>
        </ReportObjects></Section></Sections></Area></Areas>
      </ReportDefinition>
    </Report>

Attribute names vary a little between RptToXml forks, so lookups here are
tolerant (several candidate names per attribute).
"""

import re
import xml.etree.ElementTree as ET

from .model import (
    SUMMARY_CLASS_MAP, WINDOW_AGG_MAP, Element, Formula, Group,
    PageSetup, Parameter, ReportModel, Section, Summary,
)
from .rpt_xml import (
    ALIGN_MAP, _argb_to_hex, _attr, _find_color, _local, _parse_border,
    _parse_font, _text_of, _twips,
)

CHART_STYLE_MAP = {
    "crChartStyleTypeBar": "bar",
    "crChartStyleTypeLine": "line",
    "crChartStyleTypeArea": "area",
    "crChartStyleTypePie": "pie",
    "crChartStyleTypeDoughnut": "pie",
}

FIELD_REF_RE = re.compile(r"^\{([^}]+)\}$")

SPECIAL_FIELDS = {
    "pagenumber", "totalpagecount", "pagenofm", "printdate", "printtime",
    "recordnumber", "groupnumber", "datadate", "datatime", "modificationdate",
    "reporttitle", "filename",
}


def parse_field_ref(ref):
    """Classify a Crystal field reference.

    Returns (kind, name): kind in {db, formula, parameter, summary, special, unknown}.
    For db refs the name is the bare column (portion after the last dot).
    """
    ref = (ref or "").strip()
    m = FIELD_REF_RE.match(ref)
    if m:
        inner = m.group(1)
        if inner.startswith("@"):
            return "formula", inner[1:]
        if inner.startswith("?"):
            return "parameter", inner[1:]
        if inner.startswith("#"):
            return "summary", inner[1:]
        return "db", inner.split(".")[-1]
    if ref.lower() in SPECIAL_FIELDS:
        return "special", ref
    return "unknown", ref


def _condition_formula_pairs(node):
    """Conditional-formatting formulas (RptToXml dumps them in
    *ConditionFormulas elements, sometimes nested under Border/SectionFormat)
    as raw (attribute, crystal_text) pairs. Conversion to PRD style
    expressions happens later, in _resolve_references, where the model's
    field types are known. Safe to scan the whole subtree of an object or a
    SectionFormat: neither contains other report objects."""
    pairs = []
    for child in node.iter():
        if not child.tag.endswith("ConditionFormulas"):
            continue
        for attr, raw in child.attrib.items():
            body = "\n".join(
                line for line in raw.splitlines()
                if line.strip() and not line.strip().startswith("//"))
            if body.strip():
                pairs.append((attr, body.strip()))
    return pairs


def _convert_condition_formulas(target, field_types, context=""):
    """Turn a Section's/Element's raw condition formulas into PRD style
    expressions where the translator can prove them; everything else becomes
    the honest 'not carried' note. Returns the fallback notes."""
    from .formula_translator import (
        NO_PRINT_EFFECT, TranslationError, translate_style_conditions)

    notes = []
    for attr, body in target.condition_formulas:
        snippet = " ".join(body.split())[:100]
        why = NO_PRINT_EFFECT.get(attr.lower())
        if why:
            # not a failure to fix: nothing a paged report can render, so it
            # is recorded and kept out of the manual backlog
            notes.append(
                f"conditional {attr} has no effect in a PRD report{context} "
                f"- {why}: {snippet}")
            continue
        body = _resolve_current_field_value(body, target)
        try:
            pairs = translate_style_conditions(attr, body, field_types)
        except TranslationError as e:
            notes.append(
                f"conditional {attr} formula not carried{context} ({e}): {snippet}")
            continue
        target.style_expressions.extend(pairs)
        keys = "' + '".join(key for key, _ in pairs)
        notes.append(
            f"conditional {attr} converted to a '{keys}' style expression{context} "
            f"- verify against Crystal: {snippet}")
    return notes


_CURRENT_FIELD_VALUE = re.compile(r"\bcurrentfieldvalue\b", re.I)


def _resolve_current_field_value(body, target):
    """In a Crystal HIGHLIGHTING expression, CurrentFieldValue means "the
    value of the element this format is attached to". Substituting the
    element's `column` - the PRD-side name of whatever it displays - covers
    every element kind uniformly, including a summary field, whose Crystal
    source reads 'Sum ({@Line_Debit})' but whose value on the PRD side is the
    generated report function. A section has no value of its own, so its
    formulas are left to fail honestly rather than be guessed at."""
    if not _CURRENT_FIELD_VALUE.search(body):
        return body
    column = (getattr(target, "column", "") or "").strip()
    if not column or not re.fullmatch(r"[^{}]+", column):
        return body
    return _CURRENT_FIELD_VALUE.sub(lambda _m: "{" + column + "}", body)


def _numeric_format_from_parts(node):
    """Crystal frequently stores a CURRENCY format as PARTS - DecimalPlaces,
    CurrencySymbol, CurrencySymbolFormat - with no assembled FormatString.
    Left alone, a $1,139.55 renders as "1139.55". Assemble the format the
    parts describe - but only when a symbol is actually in play: Crystal
    stamps DecimalPlaces="2" on EVERY field (invoice numbers included), so
    synthesizing for plain numbers would print id 2886 as "2,886.00"."""
    symbol = _attr(node, "CurrencySymbol", default="")
    symbol_mode = _attr(node, "CurrencySymbolFormat", default="")
    if not symbol or "NoSymbol" in symbol_mode:
        return ""
    try:
        decimals = int(_attr(node, "DecimalPlaces", default="2"))
    except ValueError:
        decimals = 2
    decimals = max(0, min(decimals, 10))
    return symbol + "#,##0" + ("." + "0" * decimals if decimals else "")


def _parse_object(obj):
    tag = obj.tag
    el = Element(
        kind="unknown",
        name=_attr(obj, "Name", default=""),
        x=_twips(obj, "Left"),
        y=_twips(obj, "Top"),
        width=_twips(obj, "Width", default=100.0) or 100.0,
        height=_twips(obj, "Height", default=14.0) or 14.0,
        font=_parse_font(obj),
    )
    el.align = ALIGN_MAP.get(
        _attr(obj, "HorizontalAlignment", "Alignment", default="").lower(), "")
    el.valign = {"top": "top", "middle": "middle", "bottom": "bottom"}.get(
        _attr(obj, "VerticalAlignment", default="").lower().replace("align", ""), "")
    # formatting carried from the Crystal object (real RptToXml color children)
    el.bg_color = _find_color(obj, "BackgroundColor")
    el.border_color, el.border_width, el.border_sides = _parse_border(obj)
    objfmt = next((c for c in obj if _local(c.tag) == "ObjectFormat"), None)
    if objfmt is not None:
        el.visible = _attr(objfmt, "EnableSuppress", default="false").lower() not in ("true", "1")
        el.can_grow = _attr(objfmt, "EnableCanGrow", default="false").lower() in ("true", "1")
        if not el.align:
            el.align = ALIGN_MAP.get(_attr(objfmt, "HorizontalAlignment", default="").lower(), "")
    # explicit per-field format strings (the forked extractor emits
    # <FieldFormat><NumericFieldFormat FormatString=../><DateFieldFormat ../>;
    # Crystal reports both for every field, so capture both candidates and
    # resolve by the field's value type later)
    el.format_string = _attr(obj, "FormatString", default="")
    for node in obj.iter():
        fmt_tag = _local(node.tag)
        if fmt_tag == "NumericFieldFormat" and not el.format_numeric:
            el.format_numeric = (_attr(node, "FormatString", default="")
                                 or _numeric_format_from_parts(node))
        elif fmt_tag in ("DateFieldFormat", "DateTimeFieldFormat") and not el.format_date:
            el.format_date = _attr(node, "FormatString", default="")

    if tag == "TextObject":
        el.kind = "label"
        el.text = _text_of(obj, "Text")
    elif tag == "FieldHeadingObject":
        # Crystal's automatic column heading for a field. It has no DataSource
        # of its own - the caption is its <Text> child, and FieldObjectName
        # only says which field it sits above. Treating it as a field left an
        # unbound element and a spurious "unresolved reference" on every
        # standard-layout report.
        el.kind = "label"
        el.text = _text_of(obj, "Text") or _attr(obj, "FieldObjectName", default="")
    elif tag in ("FieldObject", "SpecialVarFieldObject",
                 "DatabaseFieldObject", "FormulaFieldObject", "ParameterFieldObject"):
        el.kind = "field"
        el.field_ref = _attr(obj, "DataSource", "DataSourceName", "FieldSource",
                             "FieldName", default="")
    elif tag in ("LineObject", "BoxObject"):
        el.kind = "line" if tag == "LineObject" else "box"
        # Crystal does not draw a zero-thickness line - it is how a designer
        # leaves a guide in place without printing it, NOT a hairline. Drawn
        # anyway, the demo statement's detail band grew a rule under every
        # row, showing through as a stray dot between two columns and a
        # trailing underline past the last one. Verified against the
        # original: the two zero-thickness objects render nowhere, the
        # thickness-20 and -30 ones render exactly where Crystal shows them.
        if _attr(obj, "LineThickness", default="").strip() == "0":
            el.visible = False
    elif tag == "PictureObject":
        el.kind = "image"
        # richer RptToXml forks export the raster as base64 (ImageData child or
        # ImageBase64 attr) — carry it so the logo survives the migration
        raw_b64 = _attr(obj, "ImageBase64", "ImageData", default="")
        if not raw_b64:
            data_node = obj.find("ImageData")
            if data_node is not None and data_node.text:
                raw_b64 = data_node.text.strip()
                if data_node.get("Carved", "").lower() == "true":
                    # injected by report-images: bytes carved from the .rpt
                    # binary and matched by aspect ratio, not read via the SDK
                    el.notes.append(
                        "image carved from the .rpt binary and matched by "
                        "aspect ratio - verify it is the right picture")
        if raw_b64:
            import base64
            try:
                el.image_bytes = base64.b64decode(raw_b64)
                el.image_mime = ("image/png" if el.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
                                 else "image/jpeg")
            except (ValueError, Exception):
                pass
    elif tag == "ChartObject":
        chart_def = next((c for c in obj.iter() if _local(c.tag) == "ChartDefinition"), None)
        style = _attr(chart_def, "StyleType", default="") if chart_def is not None else ""
        mapped = CHART_STYLE_MAP.get(style, "")
        if chart_def is not None and mapped:
            el.kind = "chart"
            el.chart_type = mapped
            el.chart_title = _attr(chart_def, "Title", default="")
            cond = [_attr(f, "FormulaName", default="") or _attr(f, "Name", default="")
                    for parent in chart_def if _local(parent.tag) == "ConditionFields"
                    for f in parent]
            data = [_attr(f, "FormulaName", default="") or _attr(f, "Name", default="")
                    for parent in chart_def if _local(parent.tag) == "DataFields"
                    for f in parent]
            el.chart_category = cond[0] if cond else ""
            el.chart_value = data[0] if data else ""
            el.notes.append(
                "chart migrated as a PRD legacy chart collecting detail rows - "
                "verify aggregation semantics match the Crystal summary")
        else:
            el.kind = "unknown"
            el.text = f"ChartObject ({style or 'no definition in dump'})"
    elif tag == "CrossTabObject":
        # The free SAP .NET SDK does not expose a cross-tab's grid definition
        # (rows/columns/summaries sit behind reserved COM slots), so the dump
        # only carries this block when hand-added (or from a future extractor):
        #   <CrossTabDefinition>
        #     <RowFields><Field FieldName="{T.COL}"/></RowFields>
        #     <ColumnFields><Field FieldName="{T.COL}"/></ColumnFields>
        #     <SummaryFields><Field FieldName="{T.COL}" Operation="Sum"/></SummaryFields>
        #   </CrossTabDefinition>
        ct = next((c for c in obj.iter() if _local(c.tag) == "CrossTabDefinition"), None)

        def _ct_fields(parent_tag):
            if ct is None:
                return []
            return [_attr(f, "FieldName", "FormulaName", default="")
                    for parent in ct if _local(parent.tag) == parent_tag
                    for f in parent if _attr(f, "FieldName", "FormulaName", default="")]

        rows, cols = _ct_fields("RowFields"), _ct_fields("ColumnFields")
        summaries = ([( _attr(f, "FieldName", "FormulaName", default=""),
                        _attr(f, "Operation", default="Sum"))
                      for parent in ct if _local(parent.tag) == "SummaryFields"
                      for f in parent] if ct is not None else [])
        if rows and cols and summaries:
            el.kind = "crosstab"
            el.crosstab_rows = rows
            el.crosstab_columns = cols
            el.crosstab_summaries = summaries
            el.notes.append(
                "cross-tab converted to a nested PRD crosstab sub-report - "
                "verify row/column grouping and aggregation in PRD")
            if ct is not None and ct.get("Recovered") == "rpt-rs":
                el.notes.append(
                    "cross-tab grid recovered from the .rpt binary by rpt-rs "
                    "(the SAP SDK cannot export it) - verify the rows, columns "
                    "and aggregations against the report in the Crystal designer")
        else:
            el.kind = "unknown"
            el.text = f"CrossTabObject ({el.name or 'cross-tab'} - definition not in dump)"
    elif tag == "SubreportObject":
        el.kind = "subreport"
        el.text = _attr(obj, "SubreportName", "Name", default="subreport")
    else:
        el.kind = "unknown"
        el.text = tag
    el.condition_formulas = _condition_formula_pairs(obj)
    return el


def parse_rpttoxml(path):
    tree = ET.parse(path)
    return _parse_report(tree.getroot())


def _parse_report(root):
    """Parse one <Report> element (top-level or nested subreport definition)
    into a ReportModel. Nested <SubReports> are detached first so the scoped
    iter() calls never leak child tables/formulas into the parent, then each
    child <Report> is parsed recursively and attached to its placeholder."""
    subs = root.find("SubReports")
    if subs is not None:
        root.remove(subs)

    model = ReportModel()
    model.name = _attr(root, "Name", default="") or _attr(root, "FileName", default="Converted Report")
    model.name = re.sub(r"\.rpt$", "", model.name.replace("\\", "/").split("/")[-1], flags=re.I)

    _parse_database(root, model)
    _parse_data_definition(root, model)
    _parse_print_options(root, model)
    _parse_areas(root, model)
    _resolve_references(model)

    if (any(s.elements for s in model.sections_of("PageHeader"))
            and any(s.elements for s in model.sections_of("ReportHeader"))):
        model.issues.append(
            "PageHeader converted to PRD's physical page-header band - on "
            "page 1 it prints ABOVE the report header, where Crystal prints "
            "it below; every other page is identical. Swap the page-1 order "
            "in PRD only if the customer notices")

    if subs is not None:
        for rep in subs.findall("Report"):
            child = _parse_report(rep)
            model.subreports[_subreport_key(child.name)] = child
        _attach_subreports(model)
    return model


def _subreport_key(name):
    return re.sub(r"\.rpt$", "", (name or "").strip(), flags=re.I).lower()


def _attach_subreports(model):
    """Wire each SubreportObject placeholder to its parsed child model and
    derive the parent->child links from Crystal's Pm-<field> parameters
    (renamed to PRD-safe identifiers, rewritten through the child's record
    selection and formulas)."""
    for section in model.sections:
        for el in section.elements:
            if el.kind != "subreport":
                continue
            if section.area_kind in ("PageHeader", "PageFooter"):
                # engine boundary (verified): "SubReports cannot be started
                # for page headers" - a converted one would render-fail
                el.notes.append(
                    f"subreport '{el.text}' sits in a Crystal {section.area_kind} - "
                    "PRD forbids sub-reports in page bands; emitted as a TODO "
                    "placeholder (move it to a report or group band instead)")
                continue
            child = model.subreports.get(_subreport_key(el.text))
            if child is None:
                el.notes.append(
                    f"subreport '{el.text}' has no definition in the dump - "
                    "emitted as a TODO placeholder")
                continue
            el.subreport = child
            for prm in child.parameters:
                if not prm.name.startswith("Pm-"):
                    continue
                master_raw = prm.name[3:]
                if master_raw.startswith("#"):
                    el.notes.append(
                        f"subreport link on summary {{?{prm.name}}} not carried "
                        "- link on a plain field or formula instead")
                    continue
                master = (master_raw[1:] if master_raw.startswith("@")
                          else master_raw.split(".")[-1])
                alias = re.sub(r"\W+", "_", prm.name)
                old = prm.name
                prm.name = alias
                token, replacement = "{?" + old + "}", "{?" + alias + "}"
                child.record_selection = child.record_selection.replace(token, replacement)
                for f in child.formulas.values():
                    f.text = f.text.replace(token, replacement)
                el.subreport_links.append((master, alias))
            el.notes.append(
                f"subreport '{child.name}' converted as a nested PRD sub-report"
                + (f" ({len(el.subreport_links)} linked parameter(s))"
                   if el.subreport_links else " (unlinked - shows all rows)")
                + " - verify layout and data")


def _normalize_value_type(raw: str) -> str:
    """Crystal reports a field's type two ways: the bare name on formula
    definitions ("DateField") and the SDK enum on database fields
    ("crFieldValueTypeDateField"). Only the bare form matches the pipeline's
    type sets, so an un-stripped enum silently made every DATABASE field a
    plain string - dates printed ISO instead of their Crystal format and
    currency columns lost their symbol."""
    value = (raw or "").strip()
    for prefix in ("crFieldValueType", "crFieldValue", "crValueType"):
        if value.startswith(prefix):
            return value[len(prefix):] or "StringField"
    return value or "StringField"


def _decode_name(raw: str) -> str:
    """Undo the XML name-escape convention Crystal uses for characters that
    are illegal in an identifier: `_x0020_` is a space, `_x005F_` an
    underscore. Left encoded, the same table arrives under two spellings -
    `variance_xtab` and `variance_x005F_xtab` - and joins between them
    silently fail to resolve."""
    return re.sub(r"_x([0-9A-Fa-f]{4})_",
                  lambda m: chr(int(m.group(1), 16)), raw or "")


def _parse_database(root, model):
    for table in root.iter("Table"):
        # The ALIAS is the report's name for the table, and the only one
        # anything else uses: every Field LongName, every FormulaForm and
        # both ends of every TableLink are written against it. Across the
        # corpus 83 tables have an alias that differs from the name and
        # NOT ONE of them qualifies its fields by the name.
        #
        # Keying by Name broke exactly that: an XML datasource names its
        # table `dataroot/Customer_Query` while its links say
        # `{Customer.Customer_ID}`, so no link matched a table, the join
        # was silently dropped, and the generated SELECT became a
        # cartesian product with a path where a table name should be.
        tname = _decode_name(_attr(table, "Alias", "Name", default="TABLE"))
        # Where the data physically came from. A real table name for a
        # database, an XPath for an XML file - which is why it can only be
        # emitted into SQL when it looks like an identifier.
        source = _decode_name(_attr(table, "Name", "Alias", default=""))
        if source and source != tname:
            model.table_sources[tname] = source
        fields = {}
        for f in table.iter("Field"):
            fname = _attr(f, "Name", "ShortName", default="")
            fname = fname.split(".")[-1].strip("{}")
            if fname:
                fields[fname] = _normalize_value_type(
                    _attr(f, "ValueType", "Type", default="StringField"))
        model.tables[tname] = fields
        for fname, vtype in fields.items():
            model.field_types[fname] = vtype
        cmd = table.find("Command")
        if cmd is not None and (cmd.text or "").strip():
            model.sql = cmd.text.strip()

    # visual table links (Database Expert joins) - feed generated SQL
    for link in root.iter("TableLink"):
        src = link.find("SourceFields/Field")
        dst = link.find("DestinationFields/Field")
        if src is None or dst is None:
            continue
        s = _attr(src, "FormulaName", default="").strip("{}")
        d = _attr(dst, "FormulaName", default="").strip("{}")
        if "." in s and "." in d:
            st, sc = s.rsplit(".", 1)
            dt, dc = d.rsplit(".", 1)
            model.table_links.append(((_decode_name(st), sc),
                                      (_decode_name(dt), dc)))


def _parse_data_definition(root, model):
    dd = root.find("DataDefinition")
    if dd is None:
        return

    rsf = dd.find("RecordSelectionFormula")
    if rsf is not None and (rsf.text or "").strip():
        model.record_selection = rsf.text.strip()

    for g in dd.iter("Group"):
        cond = _attr(g, "ConditionField", "Condition", default="")
        kind, column = parse_field_ref(cond)
        model.groups.append(Group(condition_field=cond, column=column,
                                  name=_attr(g, "Name", default="")))

    # sort fields: group direction + detail (record) ordering
    for sf in dd.iter("SortField"):
        raw = _attr(sf, "Field", default="")
        direction = _attr(sf, "SortDirection", default="AscendingOrder")
        descending = direction.startswith("Descending")
        stype = _attr(sf, "SortType", default="RecordSortField")
        if stype == "GroupSortField":
            matched = next((g for g in model.groups if g.condition_field == raw), None)
            if matched is not None and not direction.startswith(("TopN", "BottomN")):
                matched.descending = descending
            else:
                # Group Sort Expert: groups ordered by a summary value / Top N
                model.issues.append(
                    f"group sort '{raw}' ({direction}) not carried - order the "
                    "groups in the query or rebuild with PRD group sorting")
        else:
            skind, column = parse_field_ref(raw)
            if skind == "db":
                model.record_sorts.append((column, descending))
            else:
                model.issues.append(
                    f"record sort on {raw} ({direction}) not carried - the "
                    "sort key is not a plain database column")

    for f in dd.iter("FormulaFieldDefinition"):
        name = _attr(f, "Name", "FormulaName", default="").strip("{}@")
        text = _text_of(f, "Text", "Formula")
        if name:
            model.formulas[name] = Formula(
                name=name, text=text,
                value_type=_normalize_value_type(
                    _attr(f, "ValueType", default="")) if _attr(
                        f, "ValueType", default="") else "")

    for p in dd.iter("ParameterFieldDefinition"):
        name = _attr(p, "Name", "ParameterFieldName", default="").strip("{}?")
        if not name or name in [x.name for x in model.parameters]:
            continue
        # RptToXml carries the pick-list (LOV) under <ParameterDefaultValues>
        default_values = []
        dv = p.find("ParameterDefaultValues")
        if dv is not None:
            for v in dv:
                text = (v.text or _attr(v, "Value", "Description", default="")).strip()
                if text:
                    default_values.append(text)
        model.parameters.append(Parameter(
            name=name,
            value_type=_normalize_value_type(
                _attr(p, "ValueType", default="StringField")),
            prompt=_attr(p, "PromptText", "Prompt", default=""),
            default=_attr(p, "DefaultValue", default="") or (default_values[0] if default_values else ""),
            multi_value=_attr(p, "EnableAllowMultipleValue", default="false").lower() in ("true", "1"),
            optional=_attr(p, "IsOptionalPrompt", default="false").lower() in ("true", "1"),
            default_values=default_values,
        ))

    _parse_summaries(dd, model)
    _parse_running_totals(dd, model)


# RptToXml writes an object's .NET TYPE name when it cannot resolve the object
# itself - "CrystalDecisions.CrystalReports.Engine.DatabaseFieldDefinition"
# where a field name belongs.
_DOTNET_TYPE = re.compile(r"^CrystalDecisions(\.\w+)+$")


_GROUP_NAME = re.compile(r"^\s*GroupName\s*\(\s*\{?([^{}(),]+)\}?", re.I)


def _group_name_field(field_ref, model):
    """The column behind a Crystal GroupName special field, if that is what
    this reference is. "GroupName ({Customer.Country})" prints the current
    Country value, which in PRD is simply that column in the group header.
    Returns "" when the reference is not a GroupName, or names a column the
    report does not actually group by (in which case it stays a TODO rather
    than being silently bound to something else)."""
    match = _GROUP_NAME.match((field_ref or "").strip("{}#"))
    if not match:
        return ""
    # parse_field_ref needs the braces to recognise a database field
    _, column = parse_field_ref("{" + match.group(1).strip() + "}")
    for group in model.groups:
        if group.column.lower() == column.lower():
            return group.column
    return ""


def _summary_label(name):
    """The operation as the report itself names it: "PercentOfSum" out of
    "PercentOfSum ({Customer.Last_Years_Sales}, {Customer.City})"."""
    match = re.match(r"\s*([A-Za-z][A-Za-z0-9]*)\s*\(", name or "")
    return match.group(1) if match else ""


def _recover_summary_refs(name, fref, gref):
    """Recover the summarized field and its group when RptToXml stringified the
    .NET objects instead. Every summary in such a report otherwise reads as the
    same field grouped the same way, which collapses six distinct report
    functions into one name - and layout elements then all reference whichever
    survived. The summary's name still spells out the real arguments."""
    if not (_DOTNET_TYPE.match(fref or "") or _DOTNET_TYPE.match(gref or "")):
        return fref, gref
    args = re.findall(r"\{([^{}]+)\}", name or "")
    if not args:
        return fref, gref
    # keep the braces: parse_field_ref only recognizes a db column as
    # "{Table.Field}" - a bare "ORDERS.ORDER_AMOUNT" classifies as unknown and
    # the emitted function then sums a field the query does not have ($0.00
    # totals, found by the release gate)
    if _DOTNET_TYPE.match(fref or ""):
        fref = "{" + args[0] + "}"
    if _DOTNET_TYPE.match(gref or "") and len(args) > 1:
        gref = "{" + args[1] + "}"  # PercentOfSum(field, group, outer) - own group first
    return fref, gref


def _parse_summaries(dd, model):
    for s in dd.iter("SummaryFieldDefinition"):
        op = _attr(s, "Operation", "SummaryOperation", default="Sum")
        fref = _attr(s, "SummarizedField", "Field", "DataSource", default="")
        gref = _attr(s, "Group", "GroupConditionField", default="")
        name = _attr(s, "Name", default="")
        fref, gref = _recover_summary_refs(name, fref, gref)
        _, column = parse_field_ref(fref)
        _, gcolumn = parse_field_ref(gref) if gref else ("", "")
        name = name or f"{op} of {column}"
        # Crystal reports the storage operation ("Sum") for the whole family,
        # so PercentOfSum and Sum over the same field/group would generate one
        # name and silently overwrite each other. The summary's own name spells
        # out which one it is.
        label = _summary_label(name) or op
        expr_name = re.sub(r"\W+", "_", f"{label}_{column}" + (f"_{gcolumn}" if gcolumn else ""))
        percent_of = None
        if label.lower() == "percentofsum":
            # PercentOfSum(field, ownGroup [, outerGroup]) - the share of the
            # outer group's sum, or of the report's grand total when the
            # third argument is absent. Emitted as a real PRD quotient
            # function; left as a plain Sum it printed the raw total in a
            # percent column ("% 603"), which reads as data, not as a gap.
            args = re.findall(r"\{([^{}]+)\}", name or "")
            percent_of = (parse_field_ref("{" + args[2] + "}")[1]
                          if len(args) > 2 else "")
        model.summaries.append(Summary(
            name=name.strip("{}#"), operation=op, field_ref=fref,
            group_field=gcolumn, expression_name=expr_name,
            percent_of=percent_of))
        if percent_of is not None:
            model.issues.append(
                f"summary '{name.strip('{}#')}' converted to a PRD "
                "percent-of-total function (this group's sum over "
                + (f"the {percent_of} total" if percent_of
                   else "the report total")
                + ") - Crystal stores the operation as 'Sum', so verify the "
                "scope reads as a share and not a running total")
        elif label.lower().startswith(("percentof", "percentage")):
            model.issues.append(
                f"summary '{name.strip('{}#')}' is a percent-of-total, but "
                f"Crystal stores its operation as {op!r} - PRD would total the "
                "field instead of expressing it as a share. Add the percentage "
                "calculation by hand (or compute it in SQL)")
        if op not in SUMMARY_CLASS_MAP and op not in WINDOW_AGG_MAP:
            model.issues.append(
                f"summary '{name.strip('{}#')}' uses operation {op!r}, which has "
                "no PRD report-function mapping - rebuild by hand (custom "
                "function or a pre-computed SQL column)")


def _parse_running_totals(dd, model):
    """RunningTotalFieldDefinitions -> the same Summary machinery the {#name}
    references already resolve through: Sum/Count/... running totals become
    group-scoped Item* report functions (an Item*Function read mid-detail IS
    the running value - the same live-verified mapping as the
    WhilePrintingRecords variable rewrite). The fork emits engine AND RAS
    variants; entries are deduped by name, preferring the one that names the
    reset group (the engine loses it)."""
    defs: dict = {}
    for rt in dd.iter("RunningTotalFieldDefinition"):
        name = _attr(rt, "Name", default="")
        if not name:
            continue
        if name not in defs or (_attr(rt, "ResetCondition", default="")
                                and not _attr(defs[name], "ResetCondition", default="")):
            defs[name] = rt
    for name, rt in defs.items():
        op = _attr(rt, "Operation", default="Sum")
        fref = _attr(rt, "SummarizedField", default="")
        eval_type = _attr(rt, "EvaluationConditionType", default="NoCondition")
        reset_type = _attr(rt, "ResetConditionType", default="NoCondition")
        reset_ref = _attr(rt, "ResetCondition", default="")
        if not fref:
            continue
        if op not in SUMMARY_CLASS_MAP or eval_type != "NoCondition":
            model.issues.append(
                f"running total '{name}' uses "
                + (f"operation {op!r}" if op not in SUMMARY_CLASS_MAP
                   else f"an evaluate condition ({eval_type})")
                + " - no mechanical PRD equivalent, rebuild by hand")
            continue
        group_col = ""
        if reset_type in ("OnChangeOfGroup", "OnChangeOfField"):
            if reset_ref:
                _, group_col = parse_field_ref(reset_ref)
            elif model.groups:
                # engine-emitted defs lose the reset group: assume the
                # innermost report group (the overwhelmingly common design)
                group_col = model.groups[-1].column or ""
                model.issues.append(
                    f"running total '{name}' resets on a group the dump does "
                    f"not name - assumed the innermost group ({group_col}); "
                    "verify in PRD (re-extract with the current fork to carry it)")
        elif reset_type != "NoCondition":
            model.issues.append(
                f"running total '{name}' has reset condition {reset_type!r} - "
                "no mechanical PRD equivalent, rebuild by hand")
            continue
        expr_name = re.sub(r"\W+", "_", f"RT_{name}")
        model.summaries.append(Summary(
            name=name, operation=op, field_ref=fref,
            group_field=group_col, expression_name=expr_name,
            running=True))


def _parse_print_options(root, model):
    po = root.find("PrintOptions")
    page = PageSetup()
    if po is not None:
        orient = _attr(po, "PaperOrientation", "Orientation", default="Portrait").lower()
        page.orientation = "landscape" if "landscape" in orient else "portrait"
        size = _attr(po, "PaperSize", default="").lower()
        if "a4" in size:
            page.paper = "A4"
        elif "legal" in size:
            page.paper = "LEGAL"
        # margins: real RptToXml emits a <PageMargins> child; older/simulated
        # dumps carry attributes on PrintOptions itself
        margins = po.find("PageMargins")
        source = margins if margins is not None else po
        for attr, names in (
            ("margin_top", ("topMargin", "PageMarginTop", "MarginTop")),
            ("margin_left", ("leftMargin", "PageMarginLeft", "MarginLeft")),
            ("margin_bottom", ("bottomMargin", "PageMarginBottom", "MarginBottom")),
            ("margin_right", ("rightMargin", "PageMarginRight", "MarginRight")),
        ):
            v = _twips(source, *names, default=-1.0)
            if v >= 0:
                setattr(page, attr, v)
    model.page = page


def _parse_areas(root, model):
    rd = root.find("ReportDefinition")
    if rd is None:
        return
    group_counters = {"GroupHeader": 0, "GroupFooter": 0}
    for area in rd.iter("Area"):
        kind = _attr(area, "Kind", default="Detail")
        group_index = -1
        if kind in group_counters:
            group_index = group_counters[kind]
            group_counters[kind] += 1
        # Crystal suppresses at the AREA level too - the Statement demo hides
        # its whole country-group header there, and a drill-down report's
        # detail areas are hidden until drilled (which a static PRD report
        # never is, so hide-for-drill-down means suppressed here).
        area_fmt = area.find("AreaFormat")
        area_hidden = drill_hidden = False
        if area_fmt is not None:
            area_hidden = _attr(area_fmt, "EnableSuppress",
                                default="false").lower() in ("true", "1")
            drill_hidden = _attr(area_fmt, "EnableHideForDrillDown",
                                 default="false").lower() in ("true", "1")
        if drill_hidden:
            model.issues.append(
                f"{kind} area is hidden-for-drill-down in Crystal - PRD has "
                "no drill-down, so it stays hidden; delete it in PRD if the "
                "top-level view is all you need")
        for sec in area.iter("Section"):
            # suppression: real RptToXml puts it on a <SectionFormat> child
            # (EnableSuppress); tolerate a Suppress attribute on Section too
            fmt = sec.find("SectionFormat")
            suppressed = (area_hidden or drill_hidden
                          or _attr(sec, "Suppress", default="false").lower() in ("true", "1"))
            if fmt is not None:
                suppressed = suppressed or \
                    _attr(fmt, "EnableSuppress", default="false").lower() in ("true", "1")
            # band background: SectionFormat's direct <BackgroundColor> child
            # (skip the fully-transparent white default the corpus emits)
            band_bg = ""
            if fmt is not None:
                for child in fmt:
                    if _local(child.tag) == "BackgroundColor":
                        band_bg = _argb_to_hex(child)
                        break
            new_page_after = fmt is not None and _attr(
                fmt, "EnableNewPageAfter", default="false").lower() in ("true", "1")
            underlay = fmt is not None and _attr(
                fmt, "EnableUnderlaySection", default="false").lower() in ("true", "1")
            suppress_blank = fmt is not None and _attr(
                fmt, "EnableSuppressIfBlank", default="false").lower() in ("true", "1")
            keep_together = fmt is not None and _attr(
                fmt, "EnableKeepTogether", default="false").lower() in ("true", "1")
            section = Section(
                area_kind=kind,
                name=_attr(sec, "Name", default=""),
                # A declared Height of 0 is REAL and must survive: a chart
                # report collapses its detail band to nothing, and forcing a
                # 20pt floor turned 5000 invisible rows into 187 blank pages
                # where Crystal prints one. Only a MISSING height defaults.
                height=_twips(sec, "Height", default=20.0),
                group_index=group_index,
                suppressed=suppressed,
                bg_color=band_bg if band_bg not in ("#ffffff",) else "",
                new_page_after=new_page_after,
                underlay=underlay,
                suppress_if_blank=suppress_blank,
                keep_together=keep_together,
            )
            if fmt is not None:
                section.condition_formulas = _condition_formula_pairs(fmt)
            objects = sec.find("ReportObjects")
            if objects is not None:
                for obj in objects:
                    element = _parse_object(obj)
                    # A zero-thickness rule is not drawn by Crystal at all, so
                    # it must not reach the bundle. Marking it invisible was
                    # not enough - the engine drew it anyway, which is how the
                    # detail band kept its stray dot and trailing underline.
                    if element.kind in ("line", "box") and not element.visible:
                        continue
                    section.elements.append(element)
            model.sections.append(section)

    # Crystal nests bands, so the physical area order is GH1..GHn, Detail,
    # GFn..GF1 - group FOOTERS arrive innermost-first. Assigning them in
    # encounter order handed the innermost footer to the OUTERMOST group: the
    # Statement demo's per-customer "Total + Remit-to + new page" footer
    # rendered once per COUNTRY instead of once per customer. Reverse the
    # footer indices when the full set is present; with fewer footer areas
    # than groups the mapping is ambiguous, so encounter order stands.
    n_groups = len(model.groups)
    if n_groups > 1 and group_counters["GroupFooter"] == n_groups:
        for section in model.sections:
            if section.area_kind == "GroupFooter":
                section.group_index = n_groups - 1 - section.group_index


def _chart_column(ref, model):
    """A chart condition/data field ('{T.F}' or 'Sum ({T.F}, ...)') -> the bare
    query column name."""
    if not ref:
        return ""
    m = re.search(r"\{(\w+)\.(\w+)\}", ref)
    if m:
        return m.group(2)
    return ref.strip("{}@?#").split(".")[-1]


def _resolve_crosstab(el, model):
    """Resolve a cross-tab's dimension/measure refs to bare query columns.
    Anything unresolvable (or an unsupported summary operation) downgrades the
    element to an honest TODO - the writer never guesses a pivot."""
    from pentaho_migration.reports.model import CROSSTAB_AGG_MAP

    def _bare(ref):
        """A cross-tab binding -> the column the PRD crosstab groups on.
        Accepts database fields, formulas (which become PRD expressions), and
        Crystal's duplicate-usage suffix (a field grouped twice is stored as
        `Table.Field1`)."""
        kind, name = parse_field_ref(ref)
        if kind == "formula":
            return name if name in model.formulas else ""
        column = _chart_column(ref, model)
        if column in model.field_types:
            return column
        # rpt-rs reports the raw stored name, which uses the XML name-escape
        # convention for characters illegal in an identifier (`_x0020_` = space);
        # RptToXml normalises those to underscores. Decode, then normalise.
        decoded = re.sub(r"_x([0-9A-Fa-f]{4})_",
                         lambda m: chr(int(m.group(1), 16)), column)
        for candidate in (decoded, re.sub(r"\W", "_", decoded)):
            if candidate in model.field_types:
                return candidate
        stripped = re.sub(r"\d+$", "", column)
        if stripped and stripped != column and stripped in model.field_types:
            el.notes.append(
                f"cross-tab binding {ref!r} resolved to column {stripped!r} "
                "(Crystal suffixes a field grouped more than once) - verify "
                "the grouping level in PRD")
            return stripped
        return ""

    rows = [_bare(r) for r in el.crosstab_rows]
    cols = [_bare(c) for c in el.crosstab_columns]
    sums = [(_bare(f), op) for f, op in el.crosstab_summaries]
    problems = [ref for ref, ok in
                list(zip(el.crosstab_rows, rows)) + list(zip(el.crosstab_columns, cols))
                + [(f, c) for (f, _), (c, _) in zip(el.crosstab_summaries, sums)]
                if not ok]
    bad_ops = sorted({op for _, op in sums if op not in CROSSTAB_AGG_MAP})
    if problems or bad_ops:
        el.kind = "unknown"
        el.text = f"CrossTabObject ({el.name or 'cross-tab'})"
        if problems:
            el.notes.append(
                "cross-tab fields not found in the report's query: "
                + ", ".join(repr(p) for p in problems))
        if bad_ops:
            el.notes.append(
                "cross-tab summary operation(s) with no PRD crosstab aggregation: "
                + ", ".join(bad_ops)
                + f" (supported: {', '.join(CROSSTAB_AGG_MAP)})")
        return
    def _dedupe(levels, axis):
        """Crystal can group the SAME field at several granularities (a date by
        year then by month, via per-group options). PRD dimensions are plain
        columns, so repeated levels would produce a degenerate grid: keep one
        and say what was dropped."""
        seen, kept = set(), []
        for column in levels:
            if column in seen:
                el.notes.append(
                    f"cross-tab groups {column!r} more than once on the {axis} "
                    "axis (Crystal per-group date/interval options) - kept a "
                    "single level; add a derived column per granularity in the "
                    "query to reproduce the original nesting")
                continue
            seen.add(column)
            kept.append(column)
        return kept

    el.crosstab_rows = _dedupe(rows, "row")
    el.crosstab_columns = _dedupe(cols, "column")
    el.crosstab_summaries = sums


def _bind_window_summary(el, summ, model):
    """Bind an element referencing a StdDev/Variance-family summary to a
    windowed SQL column (PRD has no report function for these). The column is
    added to model.window_columns; apply_window_columns() folds it into the
    SQL at load time."""
    _, column = parse_field_ref(summ.field_ref)
    alias = f"WF_{summ.expression_name}"
    entry = (alias, WINDOW_AGG_MAP[summ.operation], column, summ.group_field)
    if entry not in model.window_columns:
        model.window_columns.append(entry)
    summ.expression_name = alias
    el.column = alias
    el.value_type = "NumberField"
    el.notes.append(
        f"summary '{summ.name}' ({summ.operation}) has no PRD report function - "
        f"computed as a windowed SQL column ({WINDOW_AGG_MAP[summ.operation]} OVER "
        + (f"PARTITION BY {summ.group_field}" if summ.group_field else "()")
        + ") - verify dialect (SQL Server uses STDEV/VAR)")


def apply_window_columns(model):
    """Fold the collected window aggregates into the report SQL: wrap it in a
    subquery and select FUNC(col) OVER (PARTITION BY group) AS alias next to
    every original column. The outer query re-applies the group/record sort
    (PRD needs group-ordered rows and a window computation may reorder them).
    Runs once at load time, after model.sql is final."""
    if not model.window_columns:
        return

    def ref(column):
        # Command SQL exposes quoted SELECT aliases; generated SQL exposes
        # the bare column names of the qualified SELECT list
        return column if model.sql_generated else f'"{column}"'

    inner = re.sub(r"\s+ORDER\s+BY\b.*$", "", model.sql, flags=re.I | re.S)
    extras = ", ".join(
        f"{func}(q.{ref(col)}) OVER ("
        + (f"PARTITION BY q.{ref(grp)}" if grp else "")
        + f') AS "{alias}"'
        for alias, func, col, grp in model.window_columns)
    order_cols = [(g.column, g.descending) for g in model.groups]
    order_cols += [(c, d) for c, d in model.record_sorts
                   if c not in {g.column for g in model.groups}]
    order = (", ".join(f"q.{ref(c)}" + (" DESC" if d else "") for c, d in order_cols)
             if order_cols else "")
    model.sql = (f"SELECT q.*, {extras}\nFROM (\n{inner}\n) q"
                 + (f"\nORDER BY {order}" if order else ""))


def _resolve_format(el):
    """Pick the explicit format candidate matching the field's value type."""
    if el.format_string:
        return
    vt = el.value_type
    if vt in ("NumberField", "CurrencyField", "IntegerField", "DecimalField",
              "Int16sField", "Int32sField", "Int64sField"):
        el.format_string = el.format_numeric
    elif vt in ("DateField", "DateTimeField", "TimeField"):
        el.format_string = el.format_date


_EMBEDDED = re.compile(r"\{[^{}]+\}")

# "Sum ({@Late Invoices}, {CUSTOMER.COUNTRY})" - Crystal spells a summary out
# in full wherever it is referenced, including inside a text object's prose.
_SUMMARY_CALL = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*\s*\(\s*\{[^{}]+\}\s*(?:,\s*\{[^{}]+\}\s*)*\)")


# RptToXml flattens a special field embedded in a text object to its BARE name
# - "Page " + {PageNumber} arrives as the text "Page PageNumber" - so the
# braced-marker scan never sees it. These are the runtime values PRD can also
# interpolate. Whole-word, case-exact: prose legitimately containing the word
# "PageNumber" is imaginable but a report printing it literally is not.
_BARE_SPECIALS = {
    "PageNumber": "$(PageofPages)",
    "PageNofM": "$(PageofPages)",
    "TotalPageCount": "$(PageofPages)",
    "PrintDate": "$(report.date, date, MMM d, yyyy)",
    "DataDate": "$(report.date, date, MMM d, yyyy)",
    "ModificationDate": "$(report.date, date, MMM d, yyyy)",
}
_BARE_SPECIAL_RE = re.compile(r"\b(" + "|".join(_BARE_SPECIALS) + r")\b")


def _resolve_embedded_text(el, model, summary_by_name):
    """Crystal text objects can carry field references INSIDE their prose:
    "The total amount due is {@statement amount} and is payable...". Emitted as
    a plain label, that prints the braces at the customer. PRD has the right
    element for this - a message field with $(column) placeholders - so build
    the template here and let the renderer choose the element type.

    A marker that cannot be resolved is left exactly as it was, and the element
    keeps a note: printing '{@thing}' is bad, but silently dropping the phrase
    the letter is built around is worse."""
    text = el.text or ""
    bare = _BARE_SPECIAL_RE.search(text)
    if "{" not in text and not bare:
        return
    if "{" not in text:
        # only bare specials - substitute and note which page/date semantics
        # were assumed (PageNumber alone becomes the "n / m" form)
        el.text_template = _BARE_SPECIAL_RE.sub(
            lambda m: _BARE_SPECIALS[m.group(1)], text)
        if any(m.group(1) in ("PageNumber", "TotalPageCount")
               for m in _BARE_SPECIAL_RE.finditer(text)):
            el.notes.append(
                'special field in text rendered as "page n / m" '
                "($(PageofPages)) - adjust the format in PRD if the report "
                "showed only the bare number")
        return
    unresolved = []

    def fmt_suffix(column):
        """Currency-formatted columns keep their symbol inside prose too:
        "The total amount due is $(X, number, $#,##0.00)"."""
        fmt = model.field_formats.get(column, "")
        return f", number, {fmt}" if fmt else ""

    def substitute(match):
        raw = match.group(0)
        # A summary is spelled by its display name: "Sum ({@x}, {Cust.Name})".
        # Those markers are consumed by the outer expression, not on their own.
        kind, name = parse_field_ref(raw)
        if kind == "db":
            return f"$({name}{fmt_suffix(name)})"
        if kind == "formula":
            # The same reference a standalone formula field uses: the writer
            # emits a PRD expression named after the formula. prd_target() is
            # a description for humans, not something $() can resolve. A
            # formula rewritten as an aggregate over a currency column keeps
            # that column's currency format.
            if name in model.formulas:
                return f"$({name})"
        if kind == "parameter":
            return f"$({name})"
        if kind == "summary":
            summary = summary_by_name.get(name)
            if summary is not None:
                return f"$({summary.expression_name})"
        unresolved.append(raw)
        return raw

    # A summary is spelled out in full - "Sum ({@Late Invoices}, {CUST.NAME})" -
    # so it must be handled BEFORE its inner markers are, or the phrase no
    # longer matches anything. Crystal also allows an INLINE summary here that
    # has no definition anywhere; that one cannot be bound to a PRD function,
    # and half-resolving it to "Sum ($(a), $(b))" would print a number that is
    # not the total. Those are frozen as written and flagged instead.
    frozen = {}

    def summary_call(match):
        phrase = match.group(0)
        summary = summary_by_name.get(phrase) or summary_by_name.get(" ".join(phrase.split()))
        if summary is None:
            # an INLINE aggregate with no definition anywhere - the same
            # synthesis the condition formulas use gives it a report function
            summary = _synthesize_summary(phrase, model)
        if summary is not None:
            return f"$({summary.expression_name})"
        token = f"\x00{len(frozen)}\x00"
        frozen[token] = phrase
        unresolved.append(phrase)
        return token

    template = _SUMMARY_CALL.sub(summary_call, text)
    template = _EMBEDDED.sub(substitute, template)
    template = _BARE_SPECIAL_RE.sub(lambda m: _BARE_SPECIALS[m.group(1)], template)
    for token, phrase in frozen.items():
        template = template.replace(token, phrase)
    if unresolved:
        # Note it even when nothing else in the text resolved - especially
        # then, because the element stays a plain label and prints the Crystal
        # source at the customer. That has to show up in the backlog.
        el.notes.append(
            "text object embeds reference(s) with no PRD equivalent - "
            f"{', '.join(sorted(set(unresolved))[:3])} - left as written so the "
            "gap is visible; add the aggregate or binding by hand in PRD")
    if template != text:
        el.text_template = template


# Op({field-or-formula} [, {group}]) inside a condition formula. Crystal
# evaluates the aggregate inline; PRD needs it to exist as a report function.
_AGG_IN_CONDITION = re.compile(
    r"\b(Sum|Count|Average|Maximum|Minimum|DistinctCount)\s*"
    r"\(\s*(\{[^{}]+\})\s*(?:,\s*(\{[^{}]+\}))?\s*\)", re.I)
_AGG_OPS = {"sum": "Sum", "count": "Count", "average": "Average",
            "maximum": "Maximum", "minimum": "Minimum",
            "distinctcount": "DistinctCount"}


def _synthesize_summary(phrase, model):
    """A Summary for one aggregate call spelled inline ("Sum ({@x}, {g})"),
    reusing an equivalent one when the report already defines it. Returns None
    when the call is not a supported aggregate over a resolvable field."""
    match = _AGG_IN_CONDITION.fullmatch(" ".join(phrase.split()))
    if not match:
        return None
    op = _AGG_OPS[match.group(1).lower()]
    fref, gref = match.group(2), match.group(3) or ""
    kind, column = parse_field_ref(fref)
    if kind == "formula":
        if column not in model.formulas:
            return None
    elif kind != "db":
        return None
    _, gcolumn = parse_field_ref(gref) if gref else ("", "")
    expr = re.sub(r"\W+", "_", f"{op}_{column}" + (f"_{gcolumn}" if gcolumn else ""))
    summary = next((s for s in model.summaries if s.expression_name == expr), None)
    if summary is None:
        summary = Summary(name=" ".join(phrase.split()), operation=op,
                          field_ref=fref, group_field=gcolumn,
                          expression_name=expr)
        model.summaries.append(summary)
    return summary


def _bind_condition_aggregates(pairs, model):
    """Rewrite aggregate calls inside condition formulas as references to a
    report function, synthesizing the summary when the report does not already
    define it. "Sum ({@Late Invoices}, {CUST.NAME}) <> 0" cannot translate
    inline — OpenFormula has no windowed Sum — but the writer emits every
    model.summaries entry as a PRD function, so the aggregate becomes a
    defined name the condition can simply reference. The synthesized function
    accumulates over exactly the rows the Crystal aggregate saw."""
    summary_by_name = {" ".join(s.name.split()): s for s in model.summaries}

    def bind(match):
        summary = (summary_by_name.get(" ".join(match.group(0).split()))
                   or _synthesize_summary(match.group(0), model))
        if summary is None:
            return match.group(0)
        return "{" + summary.expression_name + "}"

    return [(attr, _AGG_IN_CONDITION.sub(bind, body)) for attr, body in pairs]


def _resolve_references(model):
    """Resolve element field refs to PRD column/expression names."""
    summary_by_name = {s.name: s for s in model.summaries}

    # Currency formats first: a text template mentioning {ORDERS.ORDER_AMOUNT}
    # may resolve BEFORE the field element that carries the format, so the
    # map has to exist up front.
    for section in model.sections:
        for el in section.elements:
            if el.kind == "field" and el.format_numeric:
                kind, name = parse_field_ref(el.field_ref)
                if kind == "db" and name not in model.field_formats:
                    model.field_formats[name] = el.format_numeric
    for section in model.sections:
        for el in section.elements:
            if el.kind == "label":
                _resolve_embedded_text(el, model, summary_by_name)
                continue
            if el.kind == "chart":
                el.chart_category = _chart_column(el.chart_category, model)
                el.chart_value = _chart_column(el.chart_value, model)
                continue
            if el.kind == "crosstab":
                _resolve_crosstab(el, model)
                continue
            if el.kind != "field":
                continue
            kind, name = parse_field_ref(el.field_ref)
            if kind == "db":
                el.column = name
                el.value_type = model.field_types.get(name, "StringField")
                if not el.format_numeric:
                    el.format_numeric = model.field_formats.get(name, "")

            elif kind in ("formula", "parameter"):
                el.column = name
                if kind == "formula" and not el.value_type:
                    formula = model.formulas.get(name)
                    if formula is not None:
                        el.value_type = formula.value_type
            elif kind == "summary":
                summ = summary_by_name.get(name)
                if summ is not None and summ.operation in WINDOW_AGG_MAP:
                    _bind_window_summary(el, summ, model)
                elif summ is not None and summ.operation not in SUMMARY_CLASS_MAP:
                    # the writer will not emit a function for this operation —
                    # a number-field referencing it would break the bundle
                    el.kind = "unknown"
                    el.text = f"summary '{summ.name}' ({summ.operation}) - no PRD function"
                    el.notes.append(
                        f"summary operation {summ.operation!r} unsupported - "
                        "element emitted as TODO placeholder")
                else:
                    el.column = summ.expression_name if summ else name
                    el.value_type = "NumberField"
            elif kind == "special":
                el.kind = "special"
                el.column = name.lower()
            else:
                # maybe it is a summary referenced by display name
                summ = summary_by_name.get(el.field_ref.strip("{}#"))
                if summ is not None and summ.operation in WINDOW_AGG_MAP:
                    _bind_window_summary(el, summ, model)
                elif summ is not None and summ.operation not in SUMMARY_CLASS_MAP:
                    el.kind = "unknown"
                    el.text = f"summary '{summ.name}' ({summ.operation}) - no PRD function"
                    el.notes.append(
                        f"summary operation {summ.operation!r} unsupported - "
                        "element emitted as TODO placeholder")
                elif summ:
                    el.column = summ.expression_name
                    el.value_type = "NumberField"
                elif (group_column := _group_name_field(el.field_ref, model)):
                    # Crystal's GroupName special field prints the value the
                    # report is currently grouped by. In PRD that is just the
                    # group's own field in the group header - no TODO needed.
                    el.column = group_column
                    el.value_type = "StringField"
                elif not el.field_ref.strip("{}#"):
                    el.notes.append(
                        "field reference is empty in the dump - the element "
                        "prints nothing; delete it or bind it in PRD")
                else:
                    el.notes.append(f"Unresolved field reference: {el.field_ref!r}")
            _resolve_format(el)

    # cross-tabs without a definition get a global issue naming the exact
    # block to hand-add (the free SAP SDK cannot export it - see coverage doc)
    for section in model.sections:
        for el in section.elements:
            if el.kind == "unknown" and "definition not in dump" in (el.text or ""):
                model.issues.append(
                    f"{el.text}: the free SAP SDK does not export cross-tab "
                    "definitions. Read the grid off the Crystal designer and add "
                    "<CrossTabDefinition><RowFields><Field FieldName=\"{T.COL}\"/>"
                    "</RowFields><ColumnFields>...</ColumnFields><SummaryFields>"
                    "<Field FieldName=\"{T.COL}\" Operation=\"Sum\"/></SummaryFields>"
                    "</CrossTabDefinition> inside the CrossTabObject in the dump, "
                    "then re-convert for a live PRD crosstab.")

    # conditional formatting -> PRD style expressions (needs field types,
    # so it runs here rather than at parse time)
    band_counts: dict = {}
    for section in model.sections:
        band_counts[(section.area_kind, section.group_index)] = \
            band_counts.get((section.area_kind, section.group_index), 0) + 1
    for section in model.sections:
        for el in section.elements:
            if el.condition_formulas:
                el.condition_formulas = _bind_condition_aggregates(
                    el.condition_formulas, model)
                el.notes.extend(_convert_condition_formulas(el, model.field_types))
        if not section.condition_formulas:
            continue
        section.condition_formulas = _bind_condition_aggregates(
            section.condition_formulas, model)
        context = f" (section {section.name or section.area_kind})"
        # Every Crystal section becomes its own collapsing sub-band in the
        # writer, so a translated suppress condition simply rides the section
        # - whether the area has one section or nine.
        model.issues.extend(_convert_condition_formulas(
            section, model.field_types, context))

    # Crystal's "Suppress Blank Section": the section (and its height)
    # disappears when its fields print nothing. For a section whose data-bound
    # content is db columns, that is a provable visibility expression.
    for section in model.sections:
        if not section.suppress_if_blank or not section.elements:
            continue
        columns = []
        provable = True
        for el in section.elements:
            refs = ([el.field_ref] if el.kind == "field" else
                    re.findall(r"\{[^{}]+\}", el.text or "") if el.kind == "label"
                    else [])
            for ref in refs:
                kind, name = parse_field_ref(ref)
                if kind == "db":
                    columns.append(name)
                else:
                    provable = False
            if el.kind not in ("field", "label"):
                provable = False
        if provable and columns:
            checks = ";".join(f"NOT(ISBLANK([{c}]))" for c in dict.fromkeys(columns))
            formula = f"=OR({checks})" if ";" in checks else f"={checks}"
            section.style_expressions.append(("visible", formula))


_PLAIN_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")


def quote_ident(name: str) -> str:
    """One SQL identifier, quoted only when it has to be.

    Crystal happily names a column "Last Name" or a table
    "dataroot/Customer_Query" (an XML-backed report). Emitted bare, the SELECT
    is not parseable SQL at all and the report cannot render - three corpus
    reports failed on exactly this. ANSI double quotes are the portable form
    and are what the Pentaho engine's own HSQLDB expects; a plain identifier
    is left alone so the common case reads the way a consultant would write
    it by hand. An embedded quote is doubled, per the standard."""
    name = str(name)
    if _PLAIN_IDENT.fullmatch(name):
        return name
    return '"' + name.replace('"', '""') + '"'


def qualify_ident(table: str, column: str = "") -> str:
    """A dotted reference with each part quoted independently - a quoted
    "a.b" would name ONE column called "a.b", not column b of table a."""
    parts = [quote_ident(p) for p in str(table).split(".") if p]
    if column:
        parts.append(quote_ident(column))
    return ".".join(parts)


def generate_sql(model):
    """Build a SELECT statement from the columns the layout actually uses."""
    used = []

    def _add(column):
        if not column or column not in model.field_types:
            return
        qualified = next((qualify_ident(t, column)
                          for t, fs in model.tables.items()
                          if column in fs), quote_ident(column))
        if qualified not in used:
            used.append(qualified)

    for section in model.sections:
        for el in section.elements:
            if el.kind == "field" and el.column and el.column in model.field_types:
                qualified = None
                for tname, fields in model.tables.items():
                    if el.column in fields:
                        qualified = qualify_ident(tname, el.column)
                        break
                item = qualified or quote_ident(el.column)
                if item not in used:
                    used.append(item)
            elif el.kind == "chart":
                # chart / crosstab columns are not field elements but must be
                # in the SELECT for the collector or pivot to see them
                for c in (el.chart_category, el.chart_series, el.chart_value):
                    _add(c)
            elif el.kind == "crosstab":
                for c in el.crosstab_rows + el.crosstab_columns:
                    _add(c)
                for c, _op in el.crosstab_summaries:
                    _add(c)
    for g in model.groups:
        for tname, fields in model.tables.items():
            if g.column in fields:
                q = qualify_ident(tname, g.column)
                if q not in used:
                    used.insert(0, q)
    if not used:
        used = ["*"]

    # FROM clause: honor the Database Expert's visual links as JOIN ... ON.
    # Tables are named by their alias throughout, because that is what every
    # column reference above is qualified with. Where the report also
    # records a different physical source, it is declared once here as
    # `SOURCE alias` so the query still reads against the real table.
    def _from_item(alias):
        source = model.table_sources.get(alias, "")
        # An XML datasource's "table" is an XPath (`dataroot/Customer_Query`),
        # not something a database can select from. Only a plain identifier
        # is worth emitting; anything else leaves the alias standing alone
        # for the consultant to point at a real table.
        if source and re.fullmatch(r"[A-Za-z_][\w$]*", source):
            return f"{qualify_ident(source)} {qualify_ident(alias)}"
        return qualify_ident(alias)

    table_names = list(model.tables) or ["TABLE"]
    if model.table_links and len(table_names) > 1:
        placed = [table_names[0]]
        joins, remaining_links = [], list(model.table_links)
        progress = True
        while progress:
            progress = False
            for link in list(remaining_links):
                (st, sc), (dt, dc) = link
                if st in placed and dt not in placed and dt in table_names:
                    joins.append(f"JOIN {_from_item(dt)} ON "
                                 f"{qualify_ident(st, sc)} = "
                                 f"{qualify_ident(dt, dc)}")
                    placed.append(dt)
                elif dt in placed and st not in placed and st in table_names:
                    joins.append(f"JOIN {_from_item(st)} ON "
                                 f"{qualify_ident(dt, dc)} = "
                                 f"{qualify_ident(st, sc)}")
                    placed.append(st)
                else:
                    continue
                remaining_links.remove(link)
                progress = True
        leftovers = [_from_item(t) for t in table_names if t not in placed]
        from_clause = (_from_item(placed[0])
                       + ("\n" + "\n".join(joins) if joins else ""))
        if leftovers:
            from_clause = ", ".join([from_clause] + leftovers)
    else:
        from_clause = ", ".join(_from_item(t) for t in table_names)
    sql = "SELECT\n  " + ",\n  ".join(used) + f"\nFROM {from_clause}"

    # PRD relational groups need pre-sorted data: order by the group columns
    # (honoring group direction), then the report's record sorts
    def _qualify(column):
        for tname, fields in model.tables.items():
            if column in fields:
                return qualify_ident(tname, column)
        return quote_ident(column)

    order = [f"{_qualify(g.column)}{' DESC' if g.descending else ''}"
             for g in model.groups if g.column]
    order += [f"{_qualify(col)}{' DESC' if desc else ''}"
              for col, desc in model.record_sorts
              if _qualify(col) not in [o.split(" ")[0] for o in order]]
    if order:
        sql += "\nORDER BY " + ", ".join(order)
    return sql


def apply_template_formats(model):
    """Second pass over message templates, run AFTER formula translation:
    a $(ref) whose formula was rewritten as an aggregate over a currency
    column - or that names a summary over one - picks up that column's
    currency format ("$(statement amount, number, $#,##0.00)"). At resolve
    time the rewrite target is not known yet, so this cannot happen earlier."""
    fmt_of = {}
    for name, formula in model.formulas.items():
        fmt = model.field_formats.get(formula.rewrite_field or "")
        if not fmt:
            # a formula computing over a currency column inherits its format:
            # {@Late Invoices} = IF(... ; [ORDER_AMOUNT] ; 0) is money
            for ref in re.findall(r"\{(\w+)\.(\w+)\}", formula.text or ""):
                fmt = model.field_formats.get(ref[1], "")
                if fmt:
                    break
        if fmt:
            fmt_of[name] = fmt
    for summary in model.summaries:
        kind, column = parse_field_ref(summary.field_ref)
        if kind == "formula":
            # a sum over {@Late Invoices} is as much money as the formula is -
            # reuse the format the formula itself resolved to above
            fmt = fmt_of.get(column, "")
        else:
            fmt = model.field_formats.get(column, "")
        if fmt:
            fmt_of.setdefault(summary.expression_name, fmt)

    def upgrade(match):
        name = match.group(1)
        fmt = fmt_of.get(name)
        return f"$({name}, number, {fmt})" if fmt else match.group(0)

    pattern = re.compile(r"\$\(([^),$]+)\)")
    for section in model.sections:
        for el in section.elements:
            if getattr(el, "text_template", ""):
                el.text_template = pattern.sub(upgrade, el.text_template)
