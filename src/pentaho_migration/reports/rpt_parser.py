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
    SUMMARY_CLASS_MAP, Element, Formula, Group,
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
    from .formula_translator import TranslationError, translate_style_condition

    notes = []
    for attr, body in target.condition_formulas:
        snippet = " ".join(body.split())[:100]
        try:
            key, formula = translate_style_condition(attr, body, field_types)
        except TranslationError as e:
            notes.append(
                f"conditional {attr} formula not carried{context} ({e}): {snippet}")
            continue
        target.style_expressions.append((key, formula))
        notes.append(
            f"conditional {attr} converted to a '{key}' style expression{context} "
            f"- verify against Crystal: {snippet}")
    return notes


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
    el.border_color, el.border_width = _parse_border(obj)
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
            el.format_numeric = _attr(node, "FormatString", default="")
        elif fmt_tag in ("DateFieldFormat", "DateTimeFieldFormat") and not el.format_date:
            el.format_date = _attr(node, "FormatString", default="")

    if tag == "TextObject":
        el.kind = "label"
        el.text = _text_of(obj, "Text")
    elif tag in ("FieldObject", "FieldHeadingObject", "SpecialVarFieldObject",
                 "DatabaseFieldObject", "FormulaFieldObject", "ParameterFieldObject"):
        el.kind = "field"
        el.field_ref = _attr(obj, "DataSource", "DataSourceName", "FieldSource",
                             "FieldName", default="")
    elif tag == "LineObject":
        el.kind = "line"
    elif tag == "BoxObject":
        el.kind = "box"
    elif tag == "PictureObject":
        el.kind = "image"
        # richer RptToXml forks export the raster as base64 (ImageData child or
        # ImageBase64 attr) — carry it so the logo survives the migration
        raw_b64 = _attr(obj, "ImageBase64", "ImageData", default="")
        if not raw_b64:
            data_node = obj.find("ImageData")
            if data_node is not None and data_node.text:
                raw_b64 = data_node.text.strip()
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


def _parse_database(root, model):
    for table in root.iter("Table"):
        tname = _attr(table, "Name", "Alias", default="TABLE")
        fields = {}
        for f in table.iter("Field"):
            fname = _attr(f, "Name", "ShortName", default="")
            fname = fname.split(".")[-1].strip("{}")
            if fname:
                fields[fname] = _attr(f, "ValueType", "Type", default="StringField")
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
            model.table_links.append(((st, sc), (dt, dc)))


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
                value_type=_attr(f, "ValueType", default=""))

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
            value_type=_attr(p, "ValueType", default="StringField"),
            prompt=_attr(p, "PromptText", "Prompt", default=""),
            default=_attr(p, "DefaultValue", default="") or (default_values[0] if default_values else ""),
            multi_value=_attr(p, "EnableAllowMultipleValue", default="false").lower() in ("true", "1"),
            optional=_attr(p, "IsOptionalPrompt", default="false").lower() in ("true", "1"),
            default_values=default_values,
        ))

    for s in dd.iter("SummaryFieldDefinition"):
        op = _attr(s, "Operation", "SummaryOperation", default="Sum")
        fref = _attr(s, "SummarizedField", "Field", "DataSource", default="")
        gref = _attr(s, "Group", "GroupConditionField", default="")
        _, column = parse_field_ref(fref)
        _, gcolumn = parse_field_ref(gref) if gref else ("", "")
        name = _attr(s, "Name", default="") or f"{op} of {column}"
        expr_name = re.sub(r"\W+", "_", f"{op}_{column}" + (f"_{gcolumn}" if gcolumn else ""))
        model.summaries.append(Summary(
            name=name.strip("{}#"), operation=op, field_ref=fref,
            group_field=gcolumn, expression_name=expr_name))
        if op not in SUMMARY_CLASS_MAP:
            model.issues.append(
                f"summary '{name.strip('{}#')}' uses operation {op!r}, which has "
                "no PRD report-function mapping - rebuild by hand (custom "
                "function or a pre-computed SQL column)")


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
        for sec in area.iter("Section"):
            # suppression: real RptToXml puts it on a <SectionFormat> child
            # (EnableSuppress); tolerate a Suppress attribute on Section too
            fmt = sec.find("SectionFormat")
            suppressed = _attr(sec, "Suppress", default="false").lower() in ("true", "1")
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
            section = Section(
                area_kind=kind,
                name=_attr(sec, "Name", default=""),
                height=_twips(sec, "Height", default=20.0) or 20.0,
                group_index=group_index,
                suppressed=suppressed,
                bg_color=band_bg if band_bg not in ("#ffffff",) else "",
            )
            if fmt is not None:
                section.condition_formulas = _condition_formula_pairs(fmt)
            objects = sec.find("ReportObjects")
            if objects is not None:
                for obj in objects:
                    section.elements.append(_parse_object(obj))
            model.sections.append(section)

    # Crystal group footers are listed innermost-first in some SDK versions;
    # normalize so index i always matches group i.
    n_groups = len(model.groups)
    if n_groups and group_counters["GroupFooter"] == n_groups:
        footers = [s for s in model.sections if s.area_kind == "GroupFooter"]
        if len(footers) == n_groups:
            pass  # index order already matches area order; nothing to do


def _chart_column(ref, model):
    """A chart condition/data field ('{T.F}' or 'Sum ({T.F}, ...)') -> the bare
    query column name."""
    if not ref:
        return ""
    m = re.search(r"\{(\w+)\.(\w+)\}", ref)
    if m:
        return m.group(2)
    return ref.strip("{}@?#").split(".")[-1]


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


def _resolve_references(model):
    """Resolve element field refs to PRD column/expression names."""
    summary_by_name = {s.name: s for s in model.summaries}
    for section in model.sections:
        for el in section.elements:
            if el.kind == "chart":
                el.chart_category = _chart_column(el.chart_category, model)
                el.chart_value = _chart_column(el.chart_value, model)
                continue
            if el.kind != "field":
                continue
            kind, name = parse_field_ref(el.field_ref)
            if kind == "db":
                el.column = name
                el.value_type = model.field_types.get(name, "StringField")
            elif kind in ("formula", "parameter"):
                el.column = name
                if kind == "formula" and not el.value_type:
                    formula = model.formulas.get(name)
                    if formula is not None:
                        el.value_type = formula.value_type
            elif kind == "summary":
                summ = summary_by_name.get(name)
                if summ is not None and summ.operation not in SUMMARY_CLASS_MAP:
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
                if summ is not None and summ.operation not in SUMMARY_CLASS_MAP:
                    el.kind = "unknown"
                    el.text = f"summary '{summ.name}' ({summ.operation}) - no PRD function"
                    el.notes.append(
                        f"summary operation {summ.operation!r} unsupported - "
                        "element emitted as TODO placeholder")
                elif summ:
                    el.column = summ.expression_name
                    el.value_type = "NumberField"
                else:
                    el.notes.append(f"Unresolved field reference: {el.field_ref!r}")
            _resolve_format(el)

    # conditional formatting -> PRD style expressions (needs field types,
    # so it runs here rather than at parse time)
    band_counts: dict = {}
    for section in model.sections:
        band_counts[(section.area_kind, section.group_index)] = \
            band_counts.get((section.area_kind, section.group_index), 0) + 1
    for section in model.sections:
        for el in section.elements:
            if el.condition_formulas:
                el.notes.extend(_convert_condition_formulas(el, model.field_types))
        if not section.condition_formulas:
            continue
        context = f" (section {section.name or section.area_kind})"
        if band_counts[(section.area_kind, section.group_index)] == 1:
            model.issues.extend(_convert_condition_formulas(
                section, model.field_types, context))
        else:
            # several Crystal sections merge into one PRD band - a per-section
            # condition cannot be applied to the merged band
            for attr, body in section.condition_formulas:
                snippet = " ".join(body.split())[:100]
                model.issues.append(
                    f"conditional {attr} formula not carried{context} "
                    f"(sections merge into one PRD band): {snippet}")


def generate_sql(model):
    """Build a SELECT statement from the columns the layout actually uses."""
    used = []
    for section in model.sections:
        for el in section.elements:
            if el.kind == "field" and el.column and el.column in model.field_types:
                qualified = None
                for tname, fields in model.tables.items():
                    if el.column in fields:
                        qualified = f"{tname}.{el.column}"
                        break
                item = qualified or el.column
                if item not in used:
                    used.append(item)
    for g in model.groups:
        for tname, fields in model.tables.items():
            if g.column in fields:
                q = f"{tname}.{g.column}"
                if q not in used:
                    used.insert(0, q)
    if not used:
        used = ["*"]

    # FROM clause: honor the Database Expert's visual links as JOIN ... ON
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
                    joins.append(f"JOIN {dt} ON {st}.{sc} = {dt}.{dc}")
                    placed.append(dt)
                elif dt in placed and st not in placed and st in table_names:
                    joins.append(f"JOIN {st} ON {dt}.{dc} = {st}.{sc}")
                    placed.append(st)
                else:
                    continue
                remaining_links.remove(link)
                progress = True
        leftovers = [t for t in table_names if t not in placed]
        from_clause = placed[0] + ("\n" + "\n".join(joins) if joins else "")
        if leftovers:
            from_clause = ", ".join([from_clause] + leftovers)
    else:
        from_clause = ", ".join(table_names)
    sql = "SELECT\n  " + ",\n  ".join(used) + f"\nFROM {from_clause}"

    # PRD relational groups need pre-sorted data: order by the group columns
    # (honoring group direction), then the report's record sorts
    def _qualify(column):
        for tname, fields in model.tables.items():
            if column in fields:
                return f"{tname}.{column}"
        return column

    order = [f"{_qualify(g.column)}{' DESC' if g.descending else ''}"
             for g in model.groups if g.column]
    order += [f"{_qualify(col)}{' DESC' if desc else ''}"
              for col, desc in model.record_sorts
              if _qualify(col) not in [o.split(" ")[0] for o in order]]
    if order:
        sql += "\nORDER BY " + ", ".join(order)
    return sql
