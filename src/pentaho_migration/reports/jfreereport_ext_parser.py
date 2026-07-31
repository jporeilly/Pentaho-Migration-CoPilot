"""Parse the JFreeReport legacy-EXT format (`report-definition` root) into
our ReportModel.

The EXT format is the other dialect the old BI platform shipped beside the
simple `<report>` format: everything is spelled as the parser's object graph.
An element is a `<style>` block of basic-key/compound-key values plus a
`<template references="...">` node naming what it shows; report logic lives
under `<functions>` as class-named expressions. Steel Wheels ships four of
them (Inventory List, invoice, Variance Report, Top Ten).

The engine underneath is the same one PRD grew out of, so almost everything
carries: style keys keep their names, `$(field)` message templates and
`report:`-prefixed LibFormula expressions transfer verbatim, chart
expressions map onto PRD's legacy-chart element, and functions PRD still
ships (ElementVisibilitySwitchFunction and the aggregate family) port
unchanged. What genuinely cannot carry - a resource bundle that was not
uploaded, a run-time image URL that does not resolve - gets the honest note.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from pentaho_migration.reports.jfreereport_parser import (
    _IMAGE_MIMES, _PAGE_SIZES, _resolve_image_asset,
)
from pentaho_migration.reports.model import (
    Element, Font, Group, PageSetup, ReportModel, Section, Summary,
)

# Java colour constant -> hex, for style VALUES (formulas keep their names -
# the engine's own colour converter resolves them at run time)
_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000",
    "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00",
    "orange": "#ffa500", "gray": "#808080", "grey": "#808080",
    "lightgray": "#d3d3d3", "darkgray": "#a9a9a9", "pink": "#ffc0cb",
    "cyan": "#00ffff", "magenta": "#ff00ff",
}

# aggregate function classes -> (operation, running); same split as the
# simple format: Item* accumulates row by row, Group*/TotalGroup* totals
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

_CHART_TYPES = {
    "BarChartExpression": "bar",
    "LineChartExpression": "line",
    "AreaChartExpression": "area",
    "PieChartExpression": "pie",
}

# legacy functions PRD still ships under the classic-core package; they port
# with their properties unchanged
_PORTABLE_FUNCTIONS = {
    "ElementVisibilitySwitchFunction":
        "org.pentaho.reporting.engine.classic.core.function."
        "ElementVisibilitySwitchFunction",
}

_EXT_BANDS = [
    ("report-header", "ReportHeader"),
    ("page-header", "PageHeader"),
    ("itemband", "Detail"),
]


def _local(node):
    return node.tag.split("}")[-1]


def _kids(node, name):
    return [ch for ch in node if _local(ch) == name]


def _kid(node, name):
    hits = _kids(node, name)
    return hits[0] if hits else None


def _f(value, default=0.0):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _color(value):
    if not value:
        return ""
    v = value.strip()
    return _COLORS.get(v.lower(), v if v.startswith("#") else "")


def _style_map(node):
    """A <style> block -> {key: text}, compound keys flattened to their
    'value' child (the stroke width is the only compound the corpus uses)."""
    style = _kid(node, "style")
    out = {}
    if style is None:
        return out
    for key in style:
        name = key.get("name") or ""
        if _local(key) == "basic-key":
            out[name] = (key.text or "").strip()
        elif _local(key) == "compound-key":
            val = next((o.text for o in key
                        if o.get("name") == "value" and o.text), None)
            if val is not None:
                out[name] = val.strip()
    return out


def _formula_text(raw):
    """`report: IF(...)` / `=IF(...)` -> a PRD `=...` formula. The old engine
    already spoke LibFormula, so beyond the prefix nothing needs translating."""
    text = (raw or "").strip()
    text = re.sub(r"^report:\s*", "", text)
    return text if text.startswith("=") else "=" + text


def _template_props(node):
    tmpl = _kid(node, "template")
    if tmpl is None:
        return None, {}
    props = {o.get("name"): (o.text or "").strip()
             for o in tmpl if _local(o) == "basic-object"}
    # number/date formats hide inside a compound decimalFormat block; the
    # flat 'format' basic-object carries the same pattern when present
    for comp in tmpl:
        if _local(comp) == "compound-object":
            pat = next((o.text for o in comp.iter()
                        if o.get("name") == "pattern" and o.text), None)
            if pat and "format" not in props:
                props["format"] = pat.strip()
    return tmpl.get("references") or "", props


class _Ctx:
    """Everything the element walk needs from the report-wide passes."""

    def __init__(self):
        self.width = 540.0
        self.bundle = {}            # resource key -> text
        self.bundle_name = ""
        self.bundle_used = {}       # key -> resolved? (for the summary note)
        self.charts = {}            # expression name -> chart Element proto
        self.specials = {}          # function name -> special column
        self.inputs = {}            # xaction input name -> default value
        self.known_names = set()    # summaries/functions declared by name
        self.fn_targets = set()     # element/band names report functions toggle
        self.loader = None          # resource_loader, for nested sub-reports
        self.notes = []


def _dim(value, parent, default):
    """A JFreeReport length: absolute points, or (negative) a percentage of
    the CONTAINING band - `-100.0` fills the parent, whatever its size."""
    v = _f(value, default)
    return parent * (-v) / 100.0 if v < 0 else v


def _base_element(node, st, ox, oy, ctx, pw, ph):
    x = ox + _f(st.get("x"))
    y = oy + _f(st.get("y"))
    w = _dim(st.get("min-width"), pw, 100.0)
    h = _dim(st.get("min-height"), ph, 14.0)
    font = Font(
        name=st.get("font") or "Arial",
        size=_f(st.get("font-size"), 10.0),
        bold=st.get("font-bold") == "true",
        italic=st.get("font-italic") == "true",
        underline=st.get("font-underline") == "true",
        color=_color(st.get("paint")) or None,
    )
    align = (st.get("alignment") or "").lower()
    valign = (st.get("valignment") or "").lower()
    el = Element(
        kind="label", name=node.get("name") or "",
        x=x, y=y, width=w, height=h,
        align=align if align in ("left", "center", "right") else "",
        valign=valign if valign in ("top", "middle", "bottom") else "",
        font=font,
        bg_color=_color(st.get("background-color")),
        visible=st.get("visible") != "false",
        can_grow=st.get("dynamic_height") == "true",
    )
    sides = []
    widths = []
    for side in ("top", "left", "bottom", "right"):
        if (st.get(f"border-{side}-style", "none") != "none"
                and _f(st.get(f"border-{side}-width")) > 0):
            sides.append(side)
            widths.append(_f(st.get(f"border-{side}-width")))
            if not el.border_color:
                el.border_color = _color(st.get(f"border-{side}-color")) \
                    or "#000000"
    if sides:
        el.border_sides = tuple(sides)
        el.border_width = max(widths)
    for expr in _kids(node, "style-expression"):
        if expr.get("active") == "false":
            continue
        key = expr.get("style-key") or ""
        if key:
            el.style_expressions.append((key, _formula_text(expr.get("formula"))))
    return el


def _resource_text(key, ctx):
    """A resource-bundle key -> its text when the bundle was found. Records
    what happened either way so the report-level note can say it once."""
    if key in ctx.bundle:
        ctx.bundle_used[key] = True
        return ctx.bundle[key]
    ctx.bundle_used.setdefault(key, False)
    return None


def _conditional_images(el, formula, ctx):
    """`IF(cond; [A]; [B])` picking between two url inputs -> two stacked
    images with opposite visibility - the layered-visibility layout the
    pipeline already badges and QA understands. Returns None when the
    formula is not that shape or either image fails to embed."""
    text = re.sub(r"^report:\s*|^=\s*", "", (formula or "").strip())
    m = re.match(r"IF\s*\(\s*(?P<cond>.*?);\s*\[(?P<a>[^\]]+)\]\s*;"
                 r"\s*\[(?P<b>[^\]]+)\]\s*;?\s*\)\s*;?\s*$", text, re.S)
    if not m:
        return None
    # every reference inside the condition must stand a chance of resolving:
    # a declared summary/function name, a template placeholder, or a bare
    # column token. "Total Selected" (a name nothing declares) fails the
    # whole translation rather than shipping arrows that never toggle.
    for ref in re.findall(r"\[([^\]]+)\]", m.group("cond")):
        if ref in ctx.known_names or "${" in ref:
            continue
        if re.fullmatch(r"[A-Za-z0-9_.]+", ref):
            continue
        return None
    pair = []
    for ref, cond in ((m.group("a"), f'={m.group("cond").strip()}'),
                      (m.group("b"), f'=NOT({m.group("cond").strip()})')):
        src = ctx.inputs.get(ref, "")
        resolved = _resolve_image_asset(src) if src else None
        if resolved is None:
            return None
        path, data = resolved
        img = Element(kind="image", name=ref, x=el.x, y=el.y,
                      width=el.width, height=el.height,
                      image_bytes=data,
                      )
        img.image_mime = _IMAGE_MIMES.get(Path(src).suffix.lower(), "image/png")
        img.style_expressions.append(("visible", cond))
        pair.append((ref, img))
    ctx.notes.append(
        "conditional image translated to two stacked images with opposite "
        f"visibility ({pair[0][0]!r} / {pair[1][0]!r}), both embedded from "
        "the local server install - verify the right one shows per row")
    return [img for _ref, img in pair]


def _element(node, ox, oy, ctx, pw, ph):
    """One <element> -> a list of Elements (a conditional image becomes two,
    an unknown template becomes none-plus-note)."""
    st = _style_map(node)
    el = _base_element(node, st, ox, oy, ctx, pw, ph)
    etype = node.get("type") or ""

    if etype.startswith("shape"):
        ds = _kid(node, "datasource")
        shape_cls = ""
        if ds is not None:
            comp = _kid(ds, "compound-object")
            shape_cls = (comp.get("class") or "") if comp is not None else ""
        if "Line2D" in shape_cls:
            el.kind = "line"
            el.border_color = _color(st.get("paint")) or "#000000"
            el.border_width = _f(st.get("stroke"), 1.0)
            el.height = min(el.height, 1.0)
            return [el]
        # Rectangle2D (and round variants): filled and/or outlined box
        el.kind = "box"
        if st.get("fill-shape") == "true":
            el.bg_color = _color(st.get("paint"))
        if st.get("draw-shape") == "true":
            el.border_color = _color(st.get("paint")) or "#000000"
            el.border_width = _f(st.get("stroke"), 1.0)
            el.border_sides = ("top", "left", "bottom", "right")
        return [el]

    ref, props = _template_props(node)
    if ref in ("label",):
        el.text = props.get("content", "")
        return [el]
    if ref in ("string-field", "number-field", "date-field"):
        el.kind = "field"
        el.value_type = {"string-field": "StringField",
                         "number-field": "NumberField",
                         "date-field": "DateField"}[ref]
        if props.get("formula"):
            # the template computes its value; the formula is LibFormula
            # already, so it rides along as a named expression
            fname = el.name or f"expr_{abs(hash(props['formula'])) % 99991}"
            el.column = fname
            el.formula = _formula_text(props["formula"])  # marker for caller
            el.notes.append(
                f"computed field carries its own formula - emitted as a "
                f"PRD expression '{fname}' (the old engine already spoke "
                "LibFormula, so the text transferred verbatim)")
        else:
            el.column = props.get("field", "")
        if props.get("format"):
            if ref == "date-field":
                el.format_date = props["format"]
            else:
                el.format_string = props["format"]
        if el.column in ctx.specials:
            el.kind = "special"
            el.column = ctx.specials[el.column]
        return [el]
    if ref == "message-field":
        el.text_template = props.get("format", "")
        return [el]
    if ref in ("resource-label", "resource-message"):
        key = props.get("content") or props.get("formatKey") or ""
        text = _resource_text(key, ctx)
        if text is None:
            el.text = key
        elif "$(" in text:
            el.text_template = text
        else:
            el.text = text
        return [el]
    if ref == "image-url-element":
        src = props.get("content", "")
        el.kind = "image"
        el.name = el.name or Path(src).name
        resolved = _resolve_image_asset(src)
        if resolved is not None:
            path, data = resolved
            el.image_bytes = data
            el.image_mime = _IMAGE_MIMES.get(Path(src).suffix.lower(),
                                             "image/png")
            el.notes.append(
                f"image {Path(src).name!r} embedded from the local server "
                f"install ({path}) - the old xaction loaded it from "
                f"{src!r} at run time")
        else:
            el.notes.append(
                f"image resource {src!r} - a server-side path the bundle "
                "cannot carry and no local copy was found; re-embed the image "
                "in PRD (Insert > image), point the element at a reachable "
                "URL, or set PENTAHO_SERVER_WEBAPPS to the old server's "
                "tomcat/webapps folder so conversion embeds it")
        return [el]
    if ref == "image-url-field":
        formula = props.get("formula", "")
        stacked = _conditional_images(el, formula, ctx) if formula else None
        if stacked is not None:
            return stacked
        what = formula or f"field {props.get('field', '?')!r}"
        ctx.notes.append(
            f"image element takes its URL from data at run time ({what}) - "
            "PRD's content-field does exactly this: add one bound to the "
            "resolved column, or re-embed the images by hand")
        return []
    if ref == "drawable-field":
        proto = ctx.charts.get(props.get("field", ""))
        if proto is not None:
            proto = _clone_chart(proto)
            proto.x, proto.y = el.x, el.y
            proto.width, proto.height = el.width, el.height
            return [proto]
        ctx.notes.append(
            f"drawable field {props.get('field', '?')!r} references an "
            "expression this sequence does not define as a chart - rebuild "
            "the drawable in PRD")
        return []
    if ref:
        ctx.notes.append(
            f"element template {ref!r} has no translation - rebuild that "
            "element in PRD by hand")
    return []


def _clone_chart(proto):
    el = Element(kind="chart")
    for attr in ("chart_type", "chart_title", "chart_category",
                 "chart_series", "chart_value", "chart_title_literal",
                 "chart_category_axis_label", "chart_value_axis_label"):
        setattr(el, attr, getattr(proto, attr))
    el.chart_values = list(proto.chart_values)
    return el


def _band(node, area_kind, ctx, group_index=-1):
    """A band -> one Section; nested <band> children flatten with their
    offsets, a painted nested band leaves a box behind so its fill (and any
    function that toggles it by name) survives the flattening."""
    st = _style_map(node)
    section = Section(area_kind=area_kind, name=node.get("name") or "",
                      group_index=group_index)
    if st.get("visible") == "false":
        section.suppressed = True
    elements = []

    def walk(container, ox, oy, pw, ph, inherit=""):
        for child in container:
            if _local(child) == "band":
                bst = _style_map(child)
                bx, by = ox + _f(bst.get("x")), oy + _f(bst.get("y"))
                bw = _dim(bst.get("min-width"), pw, pw)
                bh = _dim(bst.get("min-height"), ph, ph)
                bname = child.get("name") or ""
                if _color(bst.get("background-color")):
                    box = Element(kind="box", name=bname,
                                  x=bx, y=by, width=bw, height=bh,
                                  bg_color=_color(bst.get("background-color")))
                    elements.append(box)
                # a band a report function toggles by name flattens
                # away, so its children CARRY the name - the engine
                # switches every element bearing it
                walk(child, bx, by, bw, bh,
                     bname if bname in ctx.fn_targets else inherit)
            elif _local(child) == "sub-report":
                elements.append(_sub_report(child, ox, oy, ctx, pw, ph))
            elif _local(child) == "element":
                for el in _element(child, ox, oy, ctx, pw, ph):
                    if inherit:
                        el.name = inherit
                    elements.append(el)

    walk(node, 0.0, 0.0, ctx.width, _f(st.get("min-height"), 100.0) or 100.0)
    section.elements = elements
    section.new_page_after = st.get("pagebreak-after") == "true"
    declared = _f(st.get("min-height"))
    content = max((e.y + e.height for e in elements), default=0.0)
    section.height = max(declared, content, 0.0) or 12.0
    section.bg_color = _color(st.get("background-color"))
    return section


def _sub_report(node, ox, oy, ctx, pw, ph):
    """An EXT sub-report (a whole report-description nested in a band) ->
    kind="subreport" with an attached child model - the same nested-bundle
    machinery Crystal subreports convert through. The child keeps its own
    functions and charts; its data feed is one of the sequence's other
    lookups, which the caller stubs runnable and notes."""
    st = _style_map(node)
    synthetic = ET.Element("report-definition",
                           {"name": node.get("name") or "sub-report"})
    for ch in node:
        synthetic.append(ch)
    child = parse_ext_report(synthetic, resource_loader=ctx.loader,
                             input_defaults=ctx.inputs)
    el = Element(kind="subreport", name=node.get("name") or "sub-report",
                 x=ox + _f(st.get("x")), y=oy + _f(st.get("y")),
                 width=_dim(st.get("min-width"), pw, pw),
                 height=_dim(st.get("min-height"), ph, ph) or 120.0)
    el.subreport = child
    ctx.notes.append(
        f"sub-report {el.name!r} converted as a nested PRD sub-report "
        "(its own bands, functions and charts) - bind its query to the "
        "sequence's matching lookup to restore its data")
    return el


def _load_bundle(rid, resource_loader):
    """`<rid>.properties` via the solution resolver -> {key: text}. Java
    properties are latin-1 key=value lines; that is all the corpus uses."""
    if not rid or resource_loader is None:
        return {}, ""
    for candidate in (f"{rid}.properties", f"{rid}_en.properties"):
        try:
            data = resource_loader(candidate)
        except Exception:
            data = None
        if not data:
            continue
        bundle = {}
        for line in data.decode("latin-1").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "!")) or "=" not in line:
                continue
            key, _, value = line.partition("=")
            bundle[key.strip()] = value.strip()
        if bundle:
            return bundle, candidate
    return {}, ""


def _scan_functions(root, model, ctx):
    """The <functions> block: aggregates -> summaries, charts -> prototypes,
    page-of-pages -> the writer's own function, portable classes -> ported
    verbatim, the rest -> honest notes. Group scoping translates from the
    JFreeReport group NAME to that group's break column (which is also the
    PRD group name the writer emits)."""
    group_columns = {}
    for g in root.iter():
        if _local(g) != "group":
            continue
        fields = [f.text.strip() for ff in _kids(g, "fields")
                  for f in ff if f.text and f.text.strip()]
        if fields:
            group_columns[g.get("name") or ""] = fields[-1]

    fns = [n for n in root.iter() if _local(n) in ("function", "expression")]
    collectors = {}
    charts = []
    for fn in fns:
        cls = (fn.get("class") or "").rsplit(".", 1)[-1]
        name = fn.get("name") or cls
        props = {}
        for pp in fn.iter():
            if _local(pp) == "property":
                props[pp.get("name") or ""] = (pp.text or "").strip()
        if _local(fn) == "property-ref":
            continue
        if cls in ("PieSetCollectorFunction", "CategorySetCollectorFunction"):
            collectors[name] = (cls, props)
            continue
        if cls in _CHART_TYPES:
            charts.append((name, cls, props))
            continue
        if cls == "PageOfPagesFunction":
            ctx.specials[name] = "pagenofm"
            continue
        ctx.known_names.add(name)
        op_running = _FUNCTION_OPS.get(cls)
        if op_running:
            op, running = op_running
            gcol = group_columns.get(props.get("group", ""), "")
            model.summaries.append(Summary(
                name=name, operation=op,
                field_ref="{R." + props.get("field", "") + "}"
                if props.get("field") else "",
                group_field=gcol, expression_name=name, running=running))
            continue
        if cls == "ItemPercentageFunction":
            # a row's share of the report total, already scaled to 100 -
            # the same percent machinery Crystal's PercentOfSum uses
            model.summaries.append(Summary(
                name=name, operation="Sum",
                field_ref="{R." + props.get("field", "") + "}"
                if props.get("field") else "",
                group_field="", expression_name=name,
                percent_of=""))
            model.issues.append(
                f"per-row percentage '{name}' computed as a formula over "
                "two declared sums (the same share machinery Crystal's "
                "PercentOfSum converts through)")
            continue
        if cls in _PORTABLE_FUNCTIONS:
            model.port_functions.append((name, _PORTABLE_FUNCTIONS[cls],
                                         props))
            target = props.get("element", "")
            if target:
                ctx.fn_targets.add(target)
            model.issues.append(
                f"report function '{name}' ({cls}) ported unchanged - PRD "
                "ships the same class"
                + (f"; it toggles element '{target}' per row (banded "
                   "shading) - verify the shading" if target else ""))
            continue
        if cls == "HideElementByNameFunction":
            continue  # handled by the simple parser's machinery when present
        model.issues.append(
            f"report function '{name}' ({cls}) has no direct PRD "
            "equivalent - rebuild it as a PRD function or a computed "
            "SQL column, then point the elements that reference "
            f"$({name}) at it")

    for name, cls, props in charts:
        proto = Element(kind="chart", chart_type=_CHART_TYPES[cls],
                        chart_title=props.get("title", ""))
        # the definition SAYS what the chart shows - no title means
        # none, and the axis labels ride along
        proto.chart_title_literal = True
        proto.chart_category_axis_label = props.get("categoryAxisLabel", "")
        proto.chart_value_axis_label = props.get("valueAxisLabel", "")
        col_cls, col_props = collectors.get(props.get("dataSource", ""),
                                            ("", {}))
        if col_cls == "PieSetCollectorFunction":
            proto.chart_category = col_props.get("seriesColumn", "")
            proto.chart_value = col_props.get("valueColumn", "")
        elif col_cls == "CategorySetCollectorFunction":
            proto.chart_category = col_props.get("categoryColumn", "")
            values = []
            for i in range(8):
                col = col_props.get(f"valueColumn[{i}]")
                if not col:
                    break
                values.append((col, col_props.get(f"seriesName[{i}]", col)))
            proto.chart_values = values
            proto.chart_value = values[0][0] if values else ""
        if proto.chart_value:
            ctx.charts[name] = proto
            model.issues.append(
                f"chart migrated as a PRD legacy chart ('{name}': {cls} -> "
                f"{proto.chart_type})")
        else:
            model.issues.append(
                f"chart expression '{name}' ({cls}) has an empty or "
                "unrecognised data collector - rebuild the chart in PRD")


def parse_ext_report(source, resource_loader=None,
                     input_defaults=None) -> ReportModel:
    """A legacy-EXT report definition -> ReportModel. `resource_loader(name)
    -> bytes` resolves solution-folder siblings (the resource bundle);
    `input_defaults` carries the owning xaction's input values (conditional
    image URLs live there)."""
    if isinstance(source, ET.Element):
        root = source
    else:
        data = (Path(source).read_bytes()
                if not isinstance(source, (bytes, bytearray))
                else bytes(source))
        root = ET.fromstring(data)

    model = ReportModel()
    model.name = root.get("name") or "Converted xaction report"
    model.definition_format = "legacy-ext"
    ctx = _Ctx()
    ctx.inputs = dict(input_defaults or {})
    ctx.loader = resource_loader
    # the definition's own property-refs are values too (Variance keeps its
    # arrow-image URLs there); the xaction's inputs win on a name clash
    for pr in root.iter():
        if (_local(pr) == "property-ref" and pr.get("name")
                and pr.text and pr.text.strip()):
            ctx.inputs.setdefault(pr.get("name"), pr.text.strip())

    # ---- page ------------------------------------------------------------
    page_node = next((n for n in root.iter() if _local(n) == "page"), None)
    fmt = ((page_node.get("pageformat") if page_node is not None else "")
           or "LETTER").upper()
    rotated = fmt.endswith("_ROTATED")
    paper = fmt[:-8] if rotated else fmt
    page_w, _h = _PAGE_SIZES.get(paper, _PAGE_SIZES["LETTER"])
    orientation = (page_node.get("orientation", "portrait")
                   if page_node is not None else "portrait")
    page = PageSetup(
        paper=paper if paper in _PAGE_SIZES else "LETTER",
        orientation="landscape" if (rotated or orientation == "landscape")
        else "portrait",
        margin_top=_f(page_node.get("topmargin"), 18.0)
        if page_node is not None else 18.0,
        margin_left=_f(page_node.get("leftmargin"), 18.0)
        if page_node is not None else 18.0,
        margin_bottom=_f(page_node.get("bottommargin"), 18.0)
        if page_node is not None else 18.0,
        margin_right=_f(page_node.get("rightmargin"), 18.0)
        if page_node is not None else 18.0,
    )
    model.page = page
    ctx.width = ((page_w if not page.orientation == "landscape" else _h)
                 - page.margin_left - page.margin_right)

    # ---- resource bundle -------------------------------------------------
    rid = next((o.text.strip() for o in root.iter()
                if o.get("name") == "resourceIdentifier" and o.text), "")
    ctx.bundle, ctx.bundle_name = _load_bundle(rid, resource_loader)

    desc = next((n for n in root.iter()
                 if _local(n) == "report-description"), None)
    if desc is None:
        model.issues.append(
            "the definition has no report-description block - the layout "
            "must be rebuilt by hand")
        return model

    # ---- functions FIRST (element templates reference them) --------------
    _scan_functions(root, model, ctx)

    # ---- bands -----------------------------------------------------------
    for tag, kind in _EXT_BANDS:
        node = _kid(desc, tag)
        if node is not None:
            model.sections.append(_band(node, kind, ctx))

    ndb = _kid(desc, "no-data-band")
    if ndb is not None and _band(ndb, "Detail", ctx).elements:
        model.issues.append(
            "the no-data band (what the original showed when the query "
            "returned nothing) is omitted - PRD prints an empty details "
            "area instead; add PRD's own no-data band if the empty-state "
            "message matters")

    # groups: a group WITH fields is a real break (its column is the last
    # listed field; earlier entries repeat the parents' keys). A fieldless
    # group is JFreeReport's whole-report wrapper - its header/footer fire
    # once, so they become extra report header/footer sections.
    named_footers = []
    wrapper_footers = []
    groups_node = _kid(desc, "groups")
    for g in (_kids(groups_node, "group") if groups_node is not None else []):
        fields = [f.text.strip() for ff in _kids(g, "fields")
                  for f in ff if f.text and f.text.strip()]
        gh, gf = _kid(g, "group-header"), _kid(g, "group-footer")
        if fields:
            column = fields[-1]
            gi = len(model.groups)
            model.groups.append(Group(condition_field=column, column=column,
                                      name=g.get("name") or f"group-{gi}"))
            if gh is not None:
                model.sections.append(_band(gh, "GroupHeader", ctx,
                                            group_index=gi))
            if gf is not None:
                named_footers.append(_band(gf, "GroupFooter", ctx,
                                           group_index=gi))
        else:
            if gh is not None and len(gh):
                model.sections.append(_band(gh, "ReportHeader", ctx))
            if gf is not None and len(gf):
                wrapper_footers.append(_band(gf, "ReportFooter", ctx))
    model.sections.extend(named_footers)

    # wrapper-group footers fire before the report footer proper
    model.sections.extend(wrapper_footers)
    rf = _kid(desc, "report-footer")
    if rf is not None:
        model.sections.append(_band(rf, "ReportFooter", ctx))
    pf = _kid(desc, "page-footer")
    if pf is not None:
        model.sections.append(_band(pf, "PageFooter", ctx))

    # ---- watermark: the underlay machinery, image embedded when local ----
    wm = _kid(desc, "watermark")
    section = _band(wm, "ReportHeader", ctx) if wm is not None else None
    if section is not None and section.elements:
        section.underlay = True
        model.sections.insert(0, section)
        embedded = any(e.image_bytes for e in section.elements)
        model.issues.append(
            "the watermark band converts as an underlay behind the report "
            "header"
            + (" with its background image embedded from the local server "
               "install" if embedded else
               " - its background image could not be resolved locally, so "
               "re-embed it in PRD or set PENTAHO_SERVER_WEBAPPS")
            + " - verify the placement against the original")

    # ---- computed-field formulas gathered from the walk ------------------
    from pentaho_migration.reports.model import Formula
    for s in model.sections:
        for el in s.elements:
            formula = getattr(el, "formula", "")
            if formula and el.column not in model.formulas:
                model.formulas[el.column] = Formula(
                    name=el.column, text=formula, translation=formula,
                    status="auto", source="rules")

    # a ported function that targets an element by name needs that name in
    # the emitted bundle; everything else keeps its name model-side only
    targets = ctx.fn_targets
    if targets:
        for s in model.sections:
            for el in s.elements:
                if el.name in targets:
                    el.emit_name = True

    # ---- resource-bundle honesty ----------------------------------------
    resolved = sorted(k for k, ok in ctx.bundle_used.items() if ok)
    missing = sorted(k for k, ok in ctx.bundle_used.items() if not ok)
    if resolved:
        model.issues.append(
            "resource-bundle text resolved from the report's resource "
            f"bundle ({ctx.bundle_name}): " + ", ".join(resolved[:6])
            + (", ..." if len(resolved) > 6 else ""))
    if missing:
        model.issues.append(
            "resource-bundle key(s) shown literally ("
            + ", ".join(missing[:6]) + (", ..." if len(missing) > 6 else "")
            + f") - the bundle '{rid}.properties' was not in the uploaded "
            "solution; include it beside the .xaction and re-convert, or "
            "replace the labels by hand")

    model.issues.extend(ctx.notes)

    # field types for every bound column, so the writer types its fields
    for s in model.sections:
        for el in s.elements:
            if el.kind == "field" and el.column:
                model.field_types.setdefault(el.column,
                                             el.value_type or "StringField")
    return model
