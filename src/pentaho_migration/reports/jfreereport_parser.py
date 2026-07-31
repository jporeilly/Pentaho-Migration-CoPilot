"""Parse an OLD JFreeReport XML report definition (the `.report` / paired
`.xml` beside a BI-platform xaction) into our ReportModel.

The simple JFreeReport format (`<report>` root, report-085.dtd era) is the
DIRECT ANCESTOR of PRD's own format - bands (reportheader, pageheader, groups,
items ...), positioned elements (label, string-field, number-field,
message-field, line, rectangle, imageref) and message templates whose
`$(FIELD, number, fmt)` syntax PRD inherited unchanged. So the translation is
mostly coordinate resolution (percent widths against the printable page) and
band bookkeeping; the honest-flag machinery covers what does not carry
(external image URLs, unknown function classes, the legacy-ext format).
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from pentaho_migration.reports.model import (
    Element, Font, Group, PageSetup, ReportModel, Section, Summary,
)

# page sizes in points (portrait) for the formats the corpus uses
_PAGE_SIZES = {
    "LETTER": (612.0, 792.0),
    "LEGAL": (612.0, 1008.0),
    "A4": (595.0, 842.0),
    "A5": (420.0, 595.0),
}

# JFreeReport function class (short name) -> (operation, running). The Item*
# family is a RUNNING value (row-by-row, JFreeReport resets it per group);
# Group*/TotalGroup* are group totals. The writer emits PRD Item*Function for
# running and TotalGroup*Function for totals - collapsing both to totals put
# the report's ending net income on the Gross Margin line.
_FUNCTION_OPS = {
    "GroupCountFunction": ("Count", False),
    "ItemCountFunction": ("Count", True),
    "GroupSumFunction": ("Sum", False),
    "ItemSumFunction": ("Sum", True),
    "TotalGroupSumFunction": ("Sum", False),
    "ItemAvgFunction": ("Average", True),
    "ItemMinFunction": ("Minimum", True),
    "ItemMaxFunction": ("Maximum", True),
}

_BAND_KINDS = [
    ("reportheader", "ReportHeader"),
    ("pageheader", "PageHeader"),
    ("items", "Detail"),
    ("pagefooter", "PageFooter"),
    ("reportfooter", "ReportFooter"),
]

_VALUE_TYPES = {
    "string-field": "StringField",
    "number-field": "NumberField",
    "date-field": "DateField",
}


def _pt(value, base: float, default: float = 0.0) -> float:
    """A JFreeReport length: absolute points, or a percentage of `base`
    (the printable width for x/width, the band extent for y)."""
    if value is None or str(value).strip() == "":
        return default
    s = str(value).strip()
    try:
        if s.endswith("%"):
            return base * float(s[:-1]) / 100.0
        return float(s)
    except ValueError:
        return default


def _font(el, inherited: Font) -> Font:
    style = (el.get("fontstyle") or "").lower()
    return Font(
        name=el.get("fontname") or inherited.name,
        size=_pt(el.get("fontsize"), 0, inherited.size),
        bold="bold" in style if style else inherited.bold,
        italic="italic" in style or el.get("fsitalic") == "true"
        if (style or el.get("fsitalic")) else inherited.italic,
        color=el.get("color") or inherited.color,
    )


def _parse_element(node, width: float, font: Font, offset_x=0.0, offset_y=0.0):
    """One band child -> an Element, or None for structural/ignored nodes."""
    tag = node.tag
    x = _pt(node.get("x"), width) + offset_x
    y = _pt(node.get("y"), 100.0) + offset_y   # y percents are rare; band-relative
    w = _pt(node.get("width"), width, 100.0)
    h = _pt(node.get("height"), 100.0, 14.0)
    visible = (node.get("visible") or "true").lower() != "false"
    align = (node.get("alignment") or "").lower()
    valign = (node.get("vertical-alignment") or "").lower()
    common = dict(x=x, y=y, width=w, height=h, visible=visible,
                  align=align if align in ("left", "center", "right") else "",
                  valign="middle" if valign == "middle" else
                         ("top" if valign == "top" else
                          ("bottom" if valign == "bottom" else "")),
                  font=_font(node, font))

    if tag == "label":
        return Element(kind="label", text=(node.text or "").strip(), **common)
    if tag in _VALUE_TYPES:
        el = Element(kind="field", column=node.get("fieldname") or "",
                     value_type=_VALUE_TYPES[tag], **common)
        if node.get("format"):
            el.format_string = node.get("format")
        if node.get("nullstring") is not None:
            el.notes.append(f"nullstring {node.get('nullstring')!r} - PRD "
                            "prints blank for null by default")
        return el
    if tag == "message-field":
        # PRD inherited JFreeReport's $(field[, type, format]) template syntax
        # unchanged, so the text carries over verbatim.
        return Element(kind="label", text_template=(node.text or "").strip(),
                       **common)
    if tag == "line":
        x1 = _pt(node.get("x1"), width)
        x2 = _pt(node.get("x2"), width, width)
        y1 = _pt(node.get("y1"), 100.0)
        y2 = _pt(node.get("y2"), 100.0, y1)
        el = Element(kind="line", x=min(x1, x2) + offset_x,
                     y=min(y1, y2) + offset_y,
                     width=abs(x2 - x1) or width, height=abs(y2 - y1),
                     visible=visible, font=_font(node, font))
        el.border_color = node.get("color") or "#000000"
        el.border_width = _pt(node.get("weight"), 0, 1.0)
        return el
    if tag == "rectangle":
        el = Element(kind="box", **common)
        if (node.get("fill") or "").lower() == "true":
            el.bg_color = node.get("color") or ""
        if (node.get("draw") or "").lower() == "true":
            el.border_color = node.get("color") or "#000000"
            el.border_width = _pt(node.get("weight"), 0, 1.0)
        return el
    if tag == "imageref":
        el = Element(kind="image", **common)
        src = node.get("src") or ""
        el.notes.append(
            f"image resource {src!r} - a server-side path the bundle cannot "
            "carry; re-embed the image in PRD (Insert > image) or point the "
            "element at a reachable URL")
        return el
    return None


def _parse_band(node, area_kind: str, width: float, base_font: Font,
                group_index: int = -1, vis_map: dict | None = None) -> Section:
    """A band element and its children -> one Section. A nested <band> child
    offsets its children by its own x/y (JFreeReport's grouping container).

    `vis_map` carries the HideElementByNameFunction wiring: {element name ->
    field}. A named band (or element) the function targets shows only on rows
    where that field equals the name - the classic layered-categories layout
    (Income Statement stacks one band per Category at the same position).
    PRD's per-row element visibility expresses it exactly, so every element
    inside such a band gets a visibility style expression instead of the
    whole layer stack printing at once."""
    vis_map = vis_map or {}
    font = _font(node, base_font)
    section = Section(area_kind=area_kind, name=node.get("name") or "",
                      group_index=group_index)
    elements = []

    def _visibility(name):
        field = vis_map.get(name or "")
        if field is None:
            return None
        return ("visible", f'=([{field}] = "{name}")')

    def walk(container, ox, oy, vis):
        for child in container:
            if child.tag == "band":
                walk(child, ox + _pt(child.get("x"), width),
                     oy + _pt(child.get("y"), 100.0),
                     _visibility(child.get("name")) or vis)
                continue
            el = _parse_element(child, width, font, ox, oy)
            if el is not None:
                own = _visibility(child.get("name"))
                if own or vis:
                    el.style_expressions.append(own or vis)
                elements.append(el)

    walk(node, 0.0, 0.0, None)
    section.elements = elements
    declared = _pt(node.get("height"), 100.0, 0.0)
    content = max((e.y + e.height for e in elements), default=0.0)
    section.height = max(declared, content, 0.0) or 12.0
    return section


def parse_jfreereport(source) -> ReportModel:
    """A simple-format JFreeReport definition -> ReportModel. `source` is a
    path or bytes. The legacy-ext format (`report-definition` root) is not
    translated - it returns a model whose issues say so, honestly."""
    data = Path(source).read_bytes() if not isinstance(source, (bytes, bytearray)) else bytes(source)
    root = ET.fromstring(data)

    model = ReportModel()
    if root.tag != "report":
        model.name = "Legacy report definition"
        model.issues.append(
            f"report definition root <{root.tag.split('}')[-1]}> is the "
            "legacy-EXT JFreeReport format, not the simple format - open the "
            "original in an old Report Designer and re-save, or rebuild the "
            "layout in PRD; the xaction's query and parameters convert either way")
        return model

    model.name = root.get("name") or "Converted xaction report"
    fmt = (root.get("pageformat") or "LETTER").upper()
    page_w, _page_h = _PAGE_SIZES.get(fmt, _PAGE_SIZES["LETTER"])
    page = PageSetup(paper=fmt if fmt in _PAGE_SIZES else "LETTER",
                     orientation="landscape"
                     if (root.get("orientation") or "").lower() == "landscape"
                     else "portrait",
                     margin_top=_pt(root.get("topmargin"), 0, 18.0),
                     margin_left=_pt(root.get("leftmargin"), 0, 18.0),
                     margin_bottom=_pt(root.get("bottommargin"), 0, 18.0),
                     margin_right=_pt(root.get("rightmargin"), 0, 18.0))
    model.page = page
    width = page_w - page.margin_left - page.margin_right

    # Function/expression scan FIRST: the visibility wiring must be known
    # before the bands parse. JFreeReport declares computed values under BOTH
    # <function> and <expression> - same classes, same shape.
    fn_nodes = [n for n in list(root.iter("function"))
                + list(root.iter("expression"))]
    vis_map = {}
    for fn in fn_nodes:
        cls = (fn.get("class") or "").rsplit(".", 1)[-1]
        if cls == "HideElementByNameFunction":
            props = {p.get("name"): (p.text or "").strip()
                     for p in fn.iter("property")}
            if props.get("element") and props.get("field"):
                vis_map[props["element"]] = props["field"]
    if vis_map:
        model.issues.append(
            "layered-visibility layout translated: HideElementByNameFunction "
            "shows one named band per row - each affected element now carries "
            "a PRD visibility expression ("
            + ", ".join(f"'{e}' when {f} matches" for e, f in
                        sorted(vis_map.items())[:4])
            + (", ..." if len(vis_map) > 4 else "")
            + ") - verify each layer prints on its own rows")

    base_font = Font()
    for band_tag, kind in _BAND_KINDS:
        node = root.find(band_tag)
        if node is not None:
            model.sections.append(
                _parse_band(node, kind, width, base_font, vis_map=vis_map))

    wm = root.find("watermark")
    if wm is not None and len(wm):
        model.issues.append(
            "the report carries a watermark band (usually a server-hosted "
            "background image) - PRD has a watermark band too, but the image "
            "must be re-embedded from a reachable file, not the old server path")

    # groups, outermost first; the group column is the LAST listed field
    # (earlier fields are the parent groups' keys, repeated JFreeReport-style)
    for gi, g in enumerate(root.iter("group")):
        fields = [f.text.strip() for f in g.iter("field") if f.text]
        column = fields[-1] if fields else ""
        model.groups.append(Group(condition_field=column, column=column,
                                  name=g.get("name") or f"group-{gi}"))
        gh = g.find("groupheader")
        if gh is not None:
            model.sections.append(_parse_band(gh, "GroupHeader", width,
                                              base_font, group_index=gi,
                                              vis_map=vis_map))
        gf = g.find("groupfooter")
        if gf is not None:
            model.sections.append(_parse_band(gf, "GroupFooter", width,
                                              base_font, group_index=gi,
                                              vis_map=vis_map))

    # functions/expressions -> PRD group functions where the class maps;
    # visibility handled above; honesty otherwise
    for fn in fn_nodes:
        cls = (fn.get("class") or "").rsplit(".", 1)[-1]
        if cls == "HideElementByNameFunction":
            continue
        name = fn.get("name") or cls
        props = {p.get("name"): (p.text or "").strip()
                 for p in fn.iter("property")}
        op_running = _FUNCTION_OPS.get(cls)
        if op_running:
            op, running = op_running
            model.summaries.append(Summary(
                name=name, operation=op,
                field_ref="{R." + props.get("field", "") + "}"
                if props.get("field") else "",
                group_field=props.get("group", ""),
                expression_name=name, running=running))
        else:
            model.issues.append(
                f"report function '{name}' ({cls}) has no direct PRD "
                "equivalent - rebuild it as a PRD function or a computed "
                "SQL column, then point the elements that reference "
                f"$({name}) at it")

    # field types for every bound column, so the writer types its fields
    for s in model.sections:
        for el in s.elements:
            if el.kind == "field" and el.column:
                model.field_types.setdefault(el.column, el.value_type
                                             or "StringField")
    return model
