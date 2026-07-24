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
    SUMMARY_CLASS_MAP, TWIPS_PER_POINT, Element, Font, Formula, Group,
    PageSetup, Parameter, ReportModel, Section, Summary,
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


def _argb_to_hex(node):
    """RptToXml dumps colors as <Color/BackgroundColor/... A R G B> children.
    Return #rrggbb, or "" when fully transparent / absent."""
    if node is None:
        return ""
    try:
        a = int(_attr(node, "A", default="255"))
        r = int(_attr(node, "R", default="0"))
        g = int(_attr(node, "G", default="0"))
        b = int(_attr(node, "B", default="0"))
    except ValueError:
        return ""
    if a == 0:
        return ""  # transparent -> no fill
    return f"#{r:02x}{g:02x}{b:02x}"


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _find_color(obj, tag_name, max_depth=None):
    """First color child with exactly this local tag name in the subtree
    (exact match so 'Color' does not catch 'BackgroundColor'/'BorderColor')."""
    for child in obj.iter():
        if _local(child.tag) == tag_name:
            hexval = _argb_to_hex(child)
            if hexval:
                return hexval
    return ""


LINE_STYLE_ATTRS = ("TopLineStyle", "BottomLineStyle", "LeftLineStyle", "RightLineStyle")


def _parse_border(obj):
    """(border_color, border_width) from an object's <Border> child. A border
    exists when any side has a line style other than NoLine."""
    border = None
    for child in obj.iter():
        if child.tag.endswith("Border"):
            border = child
            break
    if border is None:
        return "", 0.0
    has_line = any(_attr(border, a, default="NoLine") not in ("NoLine", "", "0")
                   for a in LINE_STYLE_ATTRS)
    if not has_line:
        return "", 0.0
    color = _find_color(border, "BorderColor") or "#000000"
    return color, 1.0


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
    else:
        # real RptToXml dumps the font colour as a <Color A R G B> child of the
        # object (a sibling of <Font>), so search the object, not the font node
        nested = _find_color(obj, "Color")
        if nested:
            font.color = nested
    return font


ALIGN_MAP = {
    "leftalign": "left", "rightalign": "right",
    "horizontalcenteralign": "center", "justified": "justify",
    "left": "left", "right": "right", "center": "center",
}


def _conditional_formula_notes(node, context=""):
    """Conditional-formatting formulas (RptToXml dumps them in
    *ConditionFormulas elements, sometimes nested under Border/SectionFormat).
    Not convertible mechanically — but dropping them silently hides real
    behavior, so surface each as a note. Safe to scan the whole subtree of an
    object or a SectionFormat: neither contains other report objects."""
    notes = []
    for child in node.iter():
        if not child.tag.endswith("ConditionFormulas"):
            continue
        for attr, raw in child.attrib.items():
            body = "\n".join(
                line for line in raw.splitlines()
                if line.strip() and not line.strip().startswith("//"))
            if body.strip():
                snippet = " ".join(body.split())[:100]
                notes.append(
                    f"conditional {attr} formula not carried{context}: {snippet}")
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
    elif tag == "SubreportObject":
        el.kind = "subreport"
        el.text = _attr(obj, "SubreportName", "Name", default="subreport")
    else:
        el.kind = "unknown"
        el.text = tag
    el.notes.extend(_conditional_formula_notes(obj))
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
                model.issues.extend(_conditional_formula_notes(
                    fmt, context=f" (section {section.name or kind})"))
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
