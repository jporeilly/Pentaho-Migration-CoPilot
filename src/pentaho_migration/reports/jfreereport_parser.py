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

from pentaho_migration.reports.jfreereport_functions import (
    CHART_TYPES, COLLECTOR_CLASSES, build_chart_protos, clone_chart,
    port_note, targets, translate,
)
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


def _parse_element(node, width: float, font: Font, offset_x=0.0,
                   offset_y=0.0, resource_loader=None, charts=None):
    """One band child -> an Element, or None for structural/ignored nodes."""
    tag = node.tag
    x = _pt(node.get("x"), width) + offset_x
    y = _pt(node.get("y"), 100.0) + offset_y   # y percents are rare; band-relative
    w = _pt(node.get("width"), width, 100.0)
    h = _pt(node.get("height"), 100.0, 14.0)
    visible = (node.get("visible") or "true").lower() != "false"
    align = (node.get("alignment") or "").lower()
    valign = (node.get("vertical-alignment") or "").lower()
    common = dict(name=node.get("name") or "",
                  x=x, y=y, width=w, height=h, visible=visible,
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
    if tag == "drawable-field":
        proto = (charts or {}).get(node.get("fieldname") or "")
        if proto:
            el = clone_chart(proto)
            el.x, el.y, el.width, el.height = x, y, w, h
            return el
        el = Element(kind="unknown", **common)
        el.notes.append(
            f"drawable field {node.get('fieldname', '?')!r} references an "
            "expression this report does not define as a chart - rebuild "
            "the drawable in PRD")
        return el
    if tag == "imageref":
        src = node.get("src") or ""
        el = Element(kind="image",
                     **{**common, "name": common["name"] or Path(src).name})
        data, mime, note = resolve_image(src, el.width, el.height,
                                         resource_loader)
        el.image_bytes = data
        el.image_mime = mime
        el.notes.append(note)
        return el
    return None


_IMAGE_MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".gif": "image/gif"}


def _asset_roots():
    """Where the old server's web assets live locally: the env override
    first, then the conventional install location. A missing root is simply
    skipped - resolution is best-effort and the note says what happened."""
    import os

    roots = []
    env = os.environ.get("PENTAHO_SERVER_WEBAPPS")
    if env:
        roots.append(Path(env))
    conventional = Path("C:/Pentaho/server/pentaho-server/tomcat/webapps")
    if conventional.is_dir():
        roots.append(conventional)
    return roots


def _resolve_image_asset(src: str):
    """A JFreeReport image src (`${serverBaseURL}/sw-style/...` or an
    http URL) -> (local path, bytes) when the file exists under a known local
    server root; None otherwise. Path components are normalised so a hostile
    src cannot escape the root."""
    rel = re.sub(r"^\$\{[^}]*\}/*", "", src or "")
    rel = re.sub(r"^https?://[^/]+/+", "", rel)
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    if not parts:
        return None
    for root in _asset_roots():
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            try:
                return candidate, candidate.read_bytes()
            except OSError:
                return None
    return None


def _placeholder_png(width, height, label=""):
    """A stamped placeholder raster: grey field, border, diagonal cross,
    the missing file's name when it fits. Visually unmistakable as
    NOT-the-real-image, so layout review proceeds without anyone
    mistaking the stand-in for design."""
    w = max(8, min(int(width or 100), 2000))
    h = max(8, min(int(height or 40), 2000))
    try:
        import io

        from PIL import Image, ImageDraw

        img = Image.new("RGB", (w, h), "#e9e9e9")
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, w - 1, h - 1], outline="#9a9a9a", width=1)
        draw.line([0, 0, w - 1, h - 1], fill="#c4c4c4", width=1)
        draw.line([0, h - 1, w - 1, 0], fill="#c4c4c4", width=1)
        if w >= 90 and h >= 14:
            text = (label or "image")[:24] + " (placeholder)"
            draw.text((4, max(1, h // 2 - 6)), text, fill="#666666")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:                      # pragma: no cover - Pillow
        import struct
        import zlib
        row = b"\x00" + b"\xe9\xe9\xe9" * w
        raw = row * h

        def chunk(tag, data):
            body = tag + data
            return (struct.pack(">I", len(data)) + body
                    + struct.pack(">I", zlib.crc32(body)))
        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2,
                                             0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw))
                + chunk(b"IEND", b""))


def resolve_image(src, width, height, resource_loader=None):
    """An image reference -> (bytes, mime, note), three tiers deep:

    1. a local copy under the old server's webapps (env override or the
       conventional install) - the true original;
    2. a SAME-NAMED file in the solution folder, via the caller's
       resource loader - estates often ship the image beside the
       xaction even though the definition points at a server URL;
    3. a stamped same-size placeholder - the URL is dead, but layout
       review must not be hostage to a logo. The note says the one
       estate-wide fix: drop the real file into the solution folder
       (the tier-2 fallback then resolves every report at once).
    """
    basename = Path((src or "").split("?")[0]).name
    mime = _IMAGE_MIMES.get(Path(basename).suffix.lower(), "image/png")
    resolved = _resolve_image_asset(src)
    if resolved is not None:
        path, data = resolved
        return data, mime, (
            f"image {basename!r} embedded from the local server "
            f"install ({path}) - the old xaction loaded it from "
            f"{src!r} at run time")
    if resource_loader is not None and basename:
        try:
            data = resource_loader(basename)
        except Exception:
            data = None
        if data:
            return data, mime, (
                f"image {basename!r} embedded from the solution folder - "
                f"the definition pointed at {src!r}, and a same-named "
                "file shipped beside the xaction")
    return _placeholder_png(width, height, basename), "image/png", (
        f"image URL {src!r} is unreachable - a same-size placeholder is "
        "stamped so layout review proceeds; drop the real file "
        f"({basename or 'the image'}) into the solution folder and "
        "re-convert - the basename fallback then fixes every report "
        "that points at it")


def _parse_band(node, area_kind: str, width: float, base_font: Font,
                group_index: int = -1, vis_map: dict | None = None,
                fn_targets: set | None = None,
                resource_loader=None, charts: dict | None = None) -> Section:
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

    fn_targets = fn_targets or set()

    def walk(container, ox, oy, vis, inherit=""):
        for child in container:
            if child.tag == "band":
                bname = child.get("name") or ""
                walk(child, ox + _pt(child.get("x"), width),
                     oy + _pt(child.get("y"), 100.0),
                     _visibility(bname) or vis,
                     bname if bname in fn_targets else inherit)
                continue
            el = _parse_element(child, width, font, ox, oy,
                                resource_loader=resource_loader,
                                charts=charts)
            if el is not None:
                own = _visibility(child.get("name"))
                if own or vis:
                    el.style_expressions.append(own or vis)
                if inherit:
                    el.name = inherit
                elements.append(el)

    walk(node, 0.0, 0.0, None)
    section.elements = elements
    declared = _pt(node.get("height"), 100.0, 0.0)
    content = max((e.y + e.height for e in elements), default=0.0)
    section.height = max(declared, content, 0.0) or 12.0
    return section


def parse_jfreereport(source, resource_loader=None,
                      input_defaults=None) -> ReportModel:
    """A JFreeReport definition -> ReportModel. `source` is a path or bytes.
    Both dialects translate: the simple `<report>` format here, the legacy-EXT
    `<report-definition>` format via its own parser. `resource_loader` and
    `input_defaults` feed the EXT side (resource bundles and conditional
    image URLs live outside the definition)."""
    data = Path(source).read_bytes() if not isinstance(source, (bytes, bytearray)) else bytes(source)
    root = ET.fromstring(data)

    model = ReportModel()
    if root.tag != "report":
        if root.tag.split("}")[-1] == "report-definition":
            from pentaho_migration.reports.jfreereport_ext_parser import (
                parse_ext_report,
            )
            try:
                return parse_ext_report(root, resource_loader=resource_loader,
                                        input_defaults=input_defaults)
            except Exception as exc:   # honesty beats a crash mid-conversion
                model.name = "Legacy report definition"
                model.issues.append(
                    "legacy-EXT report definition failed to translate "
                    f"({exc}) - open the original in an old Report Designer "
                    "and re-save, or rebuild the layout in PRD; the "
                    "xaction's query and parameters convert either way")
                return model
        model.name = "Legacy report definition"
        model.issues.append(
            f"report definition root <{root.tag.split('}')[-1]}> is not a "
            "JFreeReport format this pipeline knows - rebuild the layout in "
            "PRD; the xaction's query and parameters convert either way")
        return model

    model.name = root.get("name") or "Converted xaction report"
    model.definition_format = "simple"
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
    fn_targets = set()
    collectors = {}
    chart_exprs = []
    for fn in fn_nodes:
        cls = (fn.get("class") or "").rsplit(".", 1)[-1]
        name = fn.get("name") or cls
        props = {p.get("name"): (p.text or "").strip()
                 for p in fn.iter("property")}
        if cls in COLLECTOR_CLASSES:
            collectors[name] = (cls, props)
        elif cls in CHART_TYPES:
            chart_exprs.append((name, cls, props))
        elif cls == "HideElementByNameFunction":
            if props.get("element") and props.get("field"):
                vis_map[props["element"]] = props["field"]
        else:
            fn_targets.update(targets(cls, props))
    charts = build_chart_protos(chart_exprs, collectors, model.issues)
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
                _parse_band(node, kind, width, base_font, vis_map=vis_map,
                            fn_targets=fn_targets,
                            resource_loader=resource_loader, charts=charts))

    # The watermark band becomes an UNDERLAY section placed first - the same
    # machinery that carries Crystal letterhead watermarks paints its content
    # behind the following band. Its image embeds when a local copy resolves.
    wm = root.find("watermark")
    if wm is not None and len(wm):
        section = _parse_band(wm, "ReportHeader", width, base_font,
                              vis_map=vis_map, fn_targets=fn_targets,
                              resource_loader=resource_loader,
                              charts=charts)
        section.underlay = True
        model.sections.insert(0, section)
        stamped = any("placeholder is stamped" in n
                      for e in section.elements for n in e.notes)
        model.issues.append(
            "the watermark band converts as an underlay behind the report "
            "header"
            + (" - a PLACEHOLDER stands in for its background image (the "
               "URL is unreachable); drop the real file into the solution "
               "folder and re-convert" if stamped else
               " with its background image embedded")
            + " - verify the placement against the original")

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
                                              vis_map=vis_map,
                                              fn_targets=fn_targets,
                                              resource_loader=resource_loader,
                                              charts=charts))
        gf = g.find("groupfooter")
        if gf is not None:
            model.sections.append(_parse_band(gf, "GroupFooter", width,
                                              base_font, group_index=gi,
                                              vis_map=vis_map,
                                              fn_targets=fn_targets,
                                              resource_loader=resource_loader,
                                              charts=charts))

    # functions/expressions -> the shared translation table: aggregates
    # become summaries, PageOfPages becomes the writer's own page
    # function, classes PRD still ships port verbatim; honesty otherwise
    specials = {}
    for fn in fn_nodes:
        cls = (fn.get("class") or "").rsplit(".", 1)[-1]
        if cls == "HideElementByNameFunction":
            continue
        if cls in COLLECTOR_CLASSES or cls in CHART_TYPES:
            continue  # translated by the shared chart machinery above
        name = fn.get("name") or cls
        props = {p.get("name"): (p.text or "").strip()
                 for p in fn.iter("property")}
        decision, payload = translate(cls, name, props)
        if decision == "aggregate":
            op, running = payload
            model.summaries.append(Summary(
                name=name, operation=op,
                field_ref="{R." + props.get("field", "") + "}"
                if props.get("field") else "",
                group_field=props.get("group", ""),
                expression_name=name, running=running))
        elif decision == "special":
            specials[name] = payload
        elif decision == "port":
            model.port_functions.append((name, payload, props))
            model.issues.append(port_note(name, cls, props))
        else:
            model.issues.append(
                f"report function '{name}' ({cls}) has no direct PRD "
                "equivalent - rebuild it as a PRD function or a computed "
                "SQL column, then point the elements that reference "
                f"$({name}) at it")

    # field types for every bound column, so the writer types its fields;
    # elements bound to a special function become PRD special fields, and
    # elements a ported function targets keep their name in the bundle
    for sec in model.sections:
        for el in sec.elements:
            if el.kind == "field" and el.column in specials:
                el.kind = "special"
                el.column = specials[el.column]
                continue
            if el.kind == "field" and el.column:
                model.field_types.setdefault(el.column, el.value_type
                                             or "StringField")
            if el.name and el.name in fn_targets:
                el.emit_name = True

    found = {el.name for sec in model.sections for el in sec.elements
             if el.name}
    for missing in sorted(fn_targets - found):
        model.issues.append(
            f"a report function targets element '{missing}', which the "
            "original itself no longer defines (often commented out in "
            "the source) - the function is inert in PRD exactly as it "
            "was on the platform; delete it or restore the element")
    return model
