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
    TWIPS_PER_POINT, Element, Font, Formula, Group, PageSetup,
    Parameter, ReportModel, Section, Summary,
)

FIELD_REF_RE = re.compile(r"^\{([^}]+)\}$")

SPECIAL_FIELDS = {
    "pagenumber", "totalpagecount", "pagenofm", "printdate", "printtime",
    "recordnumber", "groupnumber", "datadate", "datatime", "modificationdate",
    "reporttitle", "filename",
}


def _attr(node, *names, default=""):
    for n in names:
        if n in node.attrib:
            return node.attrib[n]
    return default


def _twips(node, *names, default=0.0):
    raw = _attr(node, *names, default="")
    try:
        return float(raw) / TWIPS_PER_POINT
    except ValueError:
        return default


def _text_of(node, *child_names):
    """Text content from an attribute-or-child-element, fork-tolerantly."""
    for name in child_names:
        if name in node.attrib:
            return node.attrib[name]
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return (node.text or "").strip()


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


def _parse_font(obj):
    font = Font()
    fnode = obj.find("Font")
    src = fnode if fnode is not None else obj
    name = _attr(src, "FontName", "Name", "FontFamily", default="")
    if name and src is not obj:
        font.name = name
    try:
        font.size = float(_attr(src, "Size", "PointSize", default="10") or 10)
    except ValueError:
        pass
    font.bold = _attr(src, "Bold", default="false").lower() in ("true", "1") or \
        "bold" in _attr(src, "Style", default="").lower()
    font.italic = _attr(src, "Italic", default="false").lower() in ("true", "1")
    font.underline = _attr(src, "Underline", default="false").lower() in ("true", "1")
    color = _attr(obj, "Color", "FontColor", default="") or _attr(src, "Color", default="")
    if color.startswith("#"):
        font.color = color
    return font


ALIGN_MAP = {
    "leftalign": "left", "rightalign": "right",
    "horizontalcenteralign": "center", "justified": "justify",
    "left": "left", "right": "right", "center": "center",
}


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
    elif tag == "SubreportObject":
        el.kind = "subreport"
        el.text = _attr(obj, "SubreportName", "Name", default="subreport")
    else:
        el.kind = "unknown"
        el.text = tag
    return el


def parse_rpttoxml(path):
    tree = ET.parse(path)
    root = tree.getroot()
    model = ReportModel()
    model.name = _attr(root, "Name", default="") or _attr(root, "FileName", default="Converted Report")
    model.name = re.sub(r"\.rpt$", "", model.name.replace("\\", "/").split("/")[-1], flags=re.I)

    _parse_database(root, model)
    _parse_data_definition(root, model)
    _parse_print_options(root, model)
    _parse_areas(root, model)
    _resolve_references(model)
    return model


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

    for f in dd.iter("FormulaFieldDefinition"):
        name = _attr(f, "Name", "FormulaName", default="").strip("{}@")
        text = _text_of(f, "Text", "Formula")
        if name:
            model.formulas[name] = Formula(name=name, text=text)

    for p in dd.iter("ParameterFieldDefinition"):
        name = _attr(p, "Name", "ParameterFieldName", default="").strip("{}?")
        if not name or name in [x.name for x in model.parameters]:
            continue
        model.parameters.append(Parameter(
            name=name,
            value_type=_attr(p, "ValueType", default="StringField"),
            prompt=_attr(p, "PromptText", "Prompt", default=""),
            default=_attr(p, "DefaultValue", default=""),
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
        for attr, names in (
            ("margin_top", ("PageMarginTop", "MarginTop")),
            ("margin_left", ("PageMarginLeft", "MarginLeft")),
            ("margin_bottom", ("PageMarginBottom", "MarginBottom")),
            ("margin_right", ("PageMarginRight", "MarginRight")),
        ):
            v = _twips(po, *names, default=-1.0)
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
            section = Section(
                area_kind=kind,
                name=_attr(sec, "Name", default=""),
                height=_twips(sec, "Height", default=20.0) or 20.0,
                group_index=group_index,
                suppressed=_attr(sec, "Suppress", default="false").lower() in ("true", "1"),
            )
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


def _resolve_references(model):
    """Resolve element field refs to PRD column/expression names."""
    summary_by_name = {s.name: s for s in model.summaries}
    for section in model.sections:
        for el in section.elements:
            if el.kind != "field":
                continue
            kind, name = parse_field_ref(el.field_ref)
            if kind == "db":
                el.column = name
                el.value_type = model.field_types.get(name, "StringField")
            elif kind in ("formula", "parameter"):
                el.column = name
            elif kind == "summary":
                summ = summary_by_name.get(name)
                el.column = summ.expression_name if summ else name
                el.value_type = "NumberField"
            elif kind == "special":
                el.kind = "special"
                el.column = name.lower()
            else:
                # maybe it is a summary referenced by display name
                summ = summary_by_name.get(el.field_ref.strip("{}#"))
                if summ:
                    el.column = summ.expression_name
                    el.value_type = "NumberField"
                else:
                    el.notes.append(f"Unresolved field reference: {el.field_ref!r}")


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
    tables = ", ".join(model.tables) if model.tables else "TABLE"
    return "SELECT\n  " + ",\n  ".join(used) + f"\nFROM {tables}"
