"""Parse a Report Designer 1.x `.report` file into our ReportModel.

The THIRD old definition format: Pentaho Report Designer 1.x (the
pre-PRD "CRM" designer) saved an object tree - `<child type="org.
pentaho.reportdesigner.crm.report.model.X">` nodes with `<property>`
children - rather than a report grammar. Estates pair these designer
sources with the runtime `.xml` the server executed; when the runtime
file was never committed (lanit does this), the designer source is the
only surviving layout, so it is worth reading directly.

Coverage is the corpus's shapes: toplevel bands (page/report/item),
groups, labels, text fields and message fields (whose `formatString`
already speaks PRD's `$()` syntax). Anything else gets an honest note.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from pentaho_migration.reports.model import (
    Element, Font, Group, PageSetup, ReportModel, Section,
)

_MARKER = "org.pentaho.reportdesigner"


def looks_like_designer1(data: bytes) -> bool:
    return _MARKER.encode() in (data or b"")[:4000]


def _props(node):
    return {c.get("name"): (c.text or "").strip()
            for c in node if c.tag == "property"}


def _pair(text, default=(0.0, 0.0)):
    try:
        a, b = (float(v.strip()) for v in (text or "").split(",")[:2])
        return a, b
    except (ValueError, AttributeError):
        return default


def _color(text):
    try:
        r, g, b = (int(v.strip()) for v in text.split(",")[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, AttributeError):
        return ""


def _font(text):
    # "Roman Unicode,12,0" - java.awt.Font style bits: 1 bold, 2 italic
    try:
        name, size, style = text.rsplit(",", 2)
        bits = int(style)
        return Font(name=name.strip(), size=float(size),
                    bold=bool(bits & 1), italic=bool(bits & 2))
    except (ValueError, AttributeError):
        return Font()


def _element(node, kind_suffix, unknown):
    p = _props(node)
    x, y = _pair(p.get("position"))
    w, h = _pair(p.get("minimumSize"), (100.0, 14.0))
    halign = (p.get("horizontalAlignment") or "").lower()
    valign = (p.get("verticalAlignment") or "").lower()
    el = Element(
        kind="label", name=p.get("name", ""),
        x=x, y=y, width=w, height=h,
        align=halign if halign in ("left", "center", "right") else "",
        valign=valign if valign in ("top", "middle", "bottom") else "",
        font=_font(p.get("font", "")),
    )
    color = _color(p.get("foreground", ""))
    if color and color != "#000000":
        el.font.color = color
    if kind_suffix == "LabelReportElement":
        el.text = p.get("text", "")
        return el
    if kind_suffix == "TextFieldReportElement":
        el.kind = "field"
        el.column = p.get("fieldName", "")
        el.value_type = "StringField"
        return el
    if kind_suffix == "MessageFieldReportElement":
        # formatString already uses $(FIELD) - the syntax PRD inherited
        el.text_template = p.get("formatString", "")
        return el
    unknown.add(kind_suffix)
    return None


_SKIP_TYPES = {"DataSetsReportElement", "ReportFunctionsElement"}


def _band(node, area_kind, unknown, group_index=-1):
    p = _props(node)
    section = Section(area_kind=area_kind, name=p.get("name", ""),
                      group_index=group_index)
    for child in node:
        if child.tag != "child":
            continue
        suffix = (child.get("type") or "").rsplit(".", 1)[-1]
        el = _element(child, suffix, unknown)
        if el is not None:
            section.elements.append(el)
    declared = 0.0
    try:
        declared = float(p.get("visualHeight") or 0.0)
    except ValueError:
        pass
    content = max((e.y + e.height for e in section.elements), default=0.0)
    section.height = max(declared, content) or 12.0
    return section


def parse_designer1_report(source) -> ReportModel:
    """A Report Designer 1.x `.report` object tree -> ReportModel."""
    data = (Path(source).read_bytes()
            if not isinstance(source, (bytes, bytearray, ET.Element))
            else source)
    root = data if isinstance(data, ET.Element) else ET.fromstring(data)

    model = ReportModel()
    model.definition_format = "designer1"
    model.page = PageSetup()      # RD1 stores no page block the corpus uses
    top = _props(root)
    if top.get("name") and top["name"] != "Report":
        model.name = top["name"]

    unknown: set = set()
    page_bands = 0
    report_bands = 0
    seen_items = False

    for child in root:
        if child.tag != "child":
            continue
        suffix = (child.get("type") or "").rsplit(".", 1)[-1]
        if suffix in _SKIP_TYPES:
            continue
        if suffix == "BandToplevelPageReportElement":
            kind = "PageHeader" if page_bands == 0 else "PageFooter"
            page_bands += 1
            section = _band(child, kind, unknown)
            if section.elements:
                model.sections.append(section)
        elif suffix == "BandToplevelItemReportElement":
            seen_items = True
            model.sections.append(_band(child, "Detail", unknown))
        elif suffix == "BandToplevelReportElement":
            # file order: the band before the item band is the report
            # header, the first after it the footer; trailing empties
            # (the designer always saved the full set) are dropped
            kind = "ReportFooter" if seen_items and report_bands >= 1 \
                else "ReportHeader"
            report_bands += 1
            section = _band(child, kind, unknown)
            if section.elements:
                model.sections.append(section)
        elif suffix == "ReportGroups":
            for g in child:
                if (g.get("type") or "").rsplit(".", 1)[-1] != "ReportGroup":
                    continue
                gi = len(model.groups)
                gname = _props(g).get("name") or f"group-{gi}"
                model.groups.append(Group(condition_field="", column="",
                                          name=gname))
                bands = [b for b in g if b.tag == "child"]
                for i, b in enumerate(bands):
                    kind = "GroupHeader" if i == 0 else "GroupFooter"
                    section = _band(b, kind, unknown, group_index=gi)
                    if section.elements:
                        model.sections.append(section)
                model.issues.append(
                    f"group {gname!r} carries no break field in the "
                    "designer source - set the group's field in PRD "
                    "(the query's grouping column)")
        elif suffix not in _SKIP_TYPES:
            unknown.add(suffix)

    if unknown:
        model.issues.append(
            "Report Designer 1.x element type(s) with no translation: "
            + ", ".join(sorted(unknown)) + " - rebuild those in PRD")

    for s in model.sections:
        for el in s.elements:
            if el.kind == "field" and el.column:
                model.field_types.setdefault(el.column, "StringField")
    return model
