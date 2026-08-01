"""Element and style rendering for the .prpt layout — the "how one Crystal
object becomes one PRD element" layer, split from prpt_writer.py so the
formatting/rendering concern has its own home.
"""

from xml.sax.saxutils import escape, quoteattr

NUMERIC_TYPES = {"NumberField", "CurrencyField", "IntegerField", "Int16sField",
                 "Int32sField", "Int64sField", "DecimalField"}
DATE_TYPES = {"DateField", "DateTimeField", "TimeField"}

# An empty cell must print as EMPTY, not as whatever happens to lie under it.
# PRD skips an element whose value is null - background included - so a field
# over one of Crystal's full-width row rules stopped masking it, and every row
# with no purchase-order number grew a long underline the original never had
# (the stray marks in the gaps BETWEEN fields are the same rule showing
# through). Giving the field an empty null-value makes it render, and paint,
# exactly as it does when the data is present.
NULL_BLANK = ' core:null-value=""'


def _num(v):
    return ("%g" % round(float(v), 2))


# ---------------------------------------------------------------- elements

def _style_block(el, sp):
    parts = [f"<{sp}element-style>"]
    common = []
    if el.align:
        common.append(f'alignment="{el.align}"')
    if el.valign:
        common.append(f'vertical-alignment="{el.valign}"')
    if not el.visible:
        common.append('visible="false"')
    if el.can_grow:
        common.append('dynamic-height="true"')
    if common:
        parts.append(f'<{sp}common-styles {" ".join(common)}/>')
    text_attrs = [f'font-face={quoteattr(el.font.name)}', f'font-size="{_num(el.font.size)}"']
    if el.font.bold:
        text_attrs.append('bold="true"')
    if el.font.italic:
        text_attrs.append('italic="true"')
    if el.font.underline:
        text_attrs.append('underline="true"')
    parts.append(f'<{sp}text-styles {" ".join(text_attrs)}/>')
    if el.font.color:
        parts.append(f'<{sp}content-styles color={quoteattr(el.font.color)}/>')
    border = _border_styles(el, sp)
    if border:
        parts.append(border)
    parts.append(f'<{sp}spatial-styles x="{_num(el.x)}" y="{_num(el.y)}" '
                 f'min-width="{_num(el.width)}" min-height="{_num(el.height)}"/>')
    parts.append(f"</{sp}element-style>")
    return "".join(parts)


def _border_styles(el, sp):
    """A border-styles element carrying background fill and/or a border, when
    the element defines them. PRD paints element backgrounds this way.
    Crystal borders are per-side (a column header usually has only a bottom
    rule), so only the authored sides are emitted — a full box would draw
    vertical lines between adjacent cells that Crystal never showed."""
    attrs = []
    # White is Crystal's "no fill", not an opaque white. RptToXml exports
    # <BackgroundColor Name="White"/> on virtually every object whether or
    # not a fill is applied, so painting it made every label an opaque tile -
    # which is what hid the grey Total box behind the "Total:" label and the
    # amount. The section parser already drops white for this reason; element
    # backgrounds now do the same.
    if el.bg_color and el.bg_color.lower() not in ("#ffffff", "#fff"):
        attrs.append(f"background-color={quoteattr(el.bg_color)}")
    if el.border_width and el.border_color:
        sides = el.border_sides or ("top", "bottom", "left", "right")
        if len(sides) == 4:
            attrs.append(f'border-width="{_num(el.border_width)}"')
            attrs.append(f"border-color={quoteattr(el.border_color)}")
            attrs.append('border-style="solid"')
        else:
            for side in sides:
                attrs.append(f'border-{side}-width="{_num(el.border_width)}"')
                attrs.append(f"border-{side}-color={quoteattr(el.border_color)}")
                attrs.append(f'border-{side}-style="solid"')
    return f'<{sp}border-styles {" ".join(attrs)}/>' if attrs else ""


def _line_style(el, sp):
    color = el.border_color or "#000000"
    weight = el.border_width or 0.5
    return (f"<{sp}element-style>"
            f'<{sp}content-styles draw-shape="true" scale="true" '
            f"color={quoteattr(color)} "
            f'stroke-weight="{_num(weight)}" stroke-style="solid"/>'
            f'<{sp}spatial-styles x="{_num(el.x)}" y="{_num(el.y)}" '
            f'min-width="{_num(el.width)}" min-height="1"/>'
            f"</{sp}element-style>")


def _date_format(value_type):
    return "yyyy-MM-dd HH:mm" if value_type == "DateTimeField" else "MMM d, yyyy"


def _number_format(value_type):
    if value_type == "CurrencyField":
        return "$ #,##0.00;($ #,##0.00)"
    if value_type in ("IntegerField", "Int16sField", "Int32sField", "Int64sField"):
        return "#,##0"
    return "#,##0.00"


def _java_number_format(fmt):
    """Crystal treats '%' (and per-mille) in a format as LITERAL text; Java's
    DecimalFormat, which PRD uses, treats them as multiply-by-100/1000
    operators. So a PercentOfSum that already yields 36.16 with a "% #,##0.0"
    format printed 3,616. Quote the literal so the value is not scaled again -
    "36.16" stays "36.16". Formats that already use quoting are left as-is."""
    if not fmt or "'" in fmt:
        return fmt
    return fmt.replace("%", "'%'").replace("‰", "'‰'")


def _style_expr_block(el):
    """Converted conditional formatting: PRD style expressions on the element
    (paint / background-color / visible), evaluated per row by the engine."""
    return "".join(
        f"<style-expression style-key={quoteattr(key)} formula={quoteattr(formula)}/>"
        for key, formula in el.style_expressions)


def _name_attr(el):
    """`core:name` for elements a report function targets by name (PRD's own
    files carry the attribute the same way); unnamed elements stay clean."""
    if getattr(el, "emit_name", False) and el.name:
        return f" core:name={quoteattr(el.name)}"
    return ""


def render_element(el, tp="", sp="style:"):
    """Render one Element. tp/sp are tag prefixes for layout.xml vs styles.xml."""
    if el.kind == "label":
        if el.text_template:
            # Crystal text object with fields embedded in its prose. PRD's
            # message element interpolates $(column) at render time, which is
            # the same thing Crystal does with {Table.Column}.
            return (f'<{tp}message core:element-type="message"{_name_attr(el)}{NULL_BLANK}>{_style_block(el, sp)}'
                    f"{_style_expr_block(el)}"
                    f"<core:value>{escape(el.text_template)}</core:value></{tp}message>")
        return (f'<{tp}label core:element-type="label"{_name_attr(el)}>{_style_block(el, sp)}'
                f"{_style_expr_block(el)}"
                f"<core:value>{escape(el.text)}</core:value></{tp}label>")
    if el.kind == "line":
        return f'<{tp}horizontal-line core:element-type="horizontal-line">{_line_style(el, sp)}</{tp}horizontal-line>'
    if el.kind == "box":
        fill = el.bg_color or el.font.color
        stroke = el.border_color or "black"
        return (f'<{tp}rectangle core:element-type="rectangle"{_name_attr(el)} core:arc-width="0.0" core:arc-height="0.0">'
                f"<{sp}element-style>"
                f'<{sp}content-styles draw-shape="{str(bool(el.border_width)).lower()}" '
                f'fill-shape="{str(bool(el.bg_color)).lower()}" scale="true" '
                f'color={quoteattr(stroke)} fill-color={quoteattr(fill)} '
                f'stroke-weight="{_num(el.border_width or 1)}" stroke-style="solid"/>'
                f'<{sp}spatial-styles x="{_num(el.x)}" y="{_num(el.y)}" '
                f'min-width="{_num(el.width)}" min-height="{_num(el.height)}"/>'
                f"</{sp}element-style>{_style_expr_block(el)}</{tp}rectangle>")
    if el.kind == "special":
        if el.column in ("pagenumber", "pagenofm", "totalpagecount"):
            return (f'<{tp}message core:element-type="message">{_style_block(el, sp)}'
                    f"<core:value>Page $(PageofPages)</core:value></{tp}message>")
        if el.column in ("printdate", "datadate", "modificationdate"):
            return (f'<{tp}message core:element-type="message">{_style_block(el, sp)}'
                    f"<core:value>$(report.date, date, MMM d, yyyy)</core:value></{tp}message>")
        return render_element(_todo_label(el, f"[TODO special field: {el.column}]"), tp, sp)
    if el.kind == "field":
        if not el.column:
            return render_element(_todo_label(el, f"[TODO unresolved: {el.field_ref}]"), tp, sp)
        if el.value_type in NUMERIC_TYPES:
            fmt = _java_number_format(el.format_string or _number_format(el.value_type))
            return (f'<{tp}number-field core:element-type="number-field" '
                    f"core:format-string={quoteattr(fmt)} core:field={quoteattr(el.column)}"
                    f"{NULL_BLANK}>"
                    f"{_style_block(el, sp)}{_style_expr_block(el)}</{tp}number-field>")
        if el.value_type in DATE_TYPES:
            fmt = el.format_string or _date_format(el.value_type)
            return (f'<{tp}date-field core:element-type="date-field" '
                    f"core:format-string={quoteattr(fmt)} core:field={quoteattr(el.column)}"
                    f"{NULL_BLANK}>"
                    f"{_style_block(el, sp)}{_style_expr_block(el)}</{tp}date-field>")
        return (f'<{tp}text-field core:element-type="text-field" '
                f"core:field={quoteattr(el.column)}{NULL_BLANK}>"
                f"{_style_block(el, sp)}{_style_expr_block(el)}</{tp}text-field>")
    if el.kind == "chart":
        return _render_chart(el, tp, sp)
    if el.kind in ("subreport", "crosstab"):
        if el.subreport_href:
            # a converted nested sub-report (or a cross-tab hosted in one):
            # banded, linked to the parent via input-parameter mappings
            # (master column/parameter -> child parameter)
            links = "".join(
                f"<input-parameter master-fieldname={quoteattr(m)} "
                f"detail-fieldname={quoteattr(d)}/>"
                for m, d in el.subreport_links)
            return (f'<{tp}sub-report href="{el.subreport_href}">'
                    f"<{sp}element-style>"
                    f'<{sp}spatial-styles x="{_num(el.x)}" y="{_num(el.y)}" '
                    f'min-width="{_num(el.width)}" min-height="{_num(el.height)}"/>'
                    f"</{sp}element-style>{links}</{tp}sub-report>")
        if el.kind == "crosstab":
            return render_element(
                _todo_label(el, f"[TODO cross-tab: {el.name or 'CrossTab'}]"), tp, sp)
        return render_element(_todo_label(el, f"[TODO subreport: {el.text} - convert separately]"), tp, sp)
    if el.kind == "image":
        if el.image_bytes and el.resource_path:
            # a real embedded raster carried from the Crystal report
            key = ("resourcekey:org.pentaho.reporting.libraries.docbundle.bundleloader."
                   f"RepositoryResourceBundleLoader;{el.resource_path};")
            return (f'<{tp}content core:element-type="content">'
                    f"<{sp}element-style>"
                    # Crystal scales a picture to FILL its box; preserving the
                    # aspect letterboxed the statement's watermark to 315pt
                    # inside a 475pt box, so it read as clipped. The logos are
                    # unaffected - their boxes already match their natural
                    # aspect (2.61 vs 2.61) - and where a box does differ,
                    # stretching is what Crystal shows.
                    f'<{sp}content-styles scale="true" keep-aspect-ratio="false"/>'
                    f'<{sp}spatial-styles x="{_num(el.x)}" y="{_num(el.y)}" '
                    f'min-width="{_num(el.width)}" min-height="{_num(el.height)}"/>'
                    f"</{sp}element-style>"
                    f"{_style_expr_block(el)}"
                    f'<core:value resource-type="resource-key">{escape(key)}</core:value>'
                    f"</{tp}content>")
        return render_element(_todo_label(el, "[TODO image: re-embed resource]"), tp, sp)
    return render_element(_todo_label(el, f"[TODO unsupported object: {el.text or el.kind}]"), tp, sp)


CHART_EXPRESSIONS = {
    "bar": "org.pentaho.plugin.jfreereport.reportcharts.BarChartExpression",
    "line": "org.pentaho.plugin.jfreereport.reportcharts.LineChartExpression",
    "area": "org.pentaho.plugin.jfreereport.reportcharts.AreaChartExpression",
    "pie": "org.pentaho.plugin.jfreereport.reportcharts.PieChartExpression",
    "xy-line": "org.pentaho.plugin.jfreereport.reportcharts.XYLineChartExpression",
    "scatter": "org.pentaho.plugin.jfreereport.reportcharts.ScatterPlotChartExpression",
    "bubble": "org.pentaho.plugin.jfreereport.reportcharts.BubbleChartExpression",
    "multi-pie": "org.pentaho.plugin.jfreereport.reportcharts.MultiPieChartExpression",
    # PRD's nearest thing to a Crystal gauge: a single value against a scale
    # with warning/critical sub-ranges. Fed by the single-value collector,
    # not the category/pie one.
    "thermometer": "org.pentaho.plugin.jfreereport.reportcharts.ThermometerChartExpression",
}
NS_LEGACY_CHARTS = "http://reporting.pentaho.org/namespaces/engine/classic/legacy/charting/1.0"


def _render_chart(el, tp, sp):
    """A Crystal chart -> PRD legacy chart: a dataset collector over the query
    columns plus the matching JFreeChart expression. Bar/line/area use the
    category collector; pie uses the pie collector."""
    expr_class = CHART_EXPRESSIONS.get(el.chart_type)
    if not expr_class or not el.chart_value:
        return render_element(_todo_label(el, f"[TODO chart: {el.chart_type or 'unsupported'}]"), tp, sp)
    xy = getattr(el, "chart_xy", None) or []
    if el.chart_type in ("xy-line", "scatter", "bubble") and xy:
        # the XY family: per-series x/y(/z) column pairs. The collector
        # classes dropped their -Function suffix moving into PRD's
        # legacy-charts module; the indexed property names survived.
        base = "org.pentaho.plugin.jfreereport.reportcharts.collectors."
        if any("z" in e for e in xy):
            collector = base + "XYZSeriesCollector"
        elif any(e.get("time") for e in xy):
            collector = base + "TimeSeriesCollector"
        else:
            collector = base + "XYSeriesCollector"
        parts = []
        for i, e in enumerate(xy):
            if e.get("series_col"):
                # series named by a data column - the new collectors index
                # this directly (the old boolean-seriesColumn semantics)
                parts.append(f'<property name="seriesColumn[{i}]">'
                             f'{escape(e["series_col"])}</property>')
            else:
                parts.append(f'<property name="seriesName[{i}]">'
                             f'{escape(e["series"])}</property>')
            if e.get("time"):
                parts.append(f'<property name="timeValueColumn[{i}]">'
                             f'{escape(e["x"])}</property>')
                parts.append(f'<property name="valueColumn[{i}]">'
                             f'{escape(e["y"])}</property>')
            else:
                # capital X/Y/Z: JavaBeans keeps the property name as-is
                # when its first two letters are capitals (setXValueColumn
                # introspects as "XValueColumn"), and the parser resolves
                # properties through introspection
                parts.append(f'<property name="XValueColumn[{i}]">'
                             f'{escape(e["x"])}</property>')
                parts.append(f'<property name="YValueColumn[{i}]">'
                             f'{escape(e["y"])}</property>')
                if e.get("z"):
                    parts.append(f'<property name="ZValueColumn[{i}]">'
                                 f'{escape(e["z"])}</property>')
        period = next((e["period"] for e in xy if e.get("period")), "")
        if period in ("Millisecond", "Second", "Minute", "Hour", "Day",
                      "Week", "Month", "Quarter", "Year"):
            # timePeriod is Class-valued; the engine's ClassValueConverter
            # resolves the org.jfree.data.time period class by name
            parts.append('<property name="timePeriod">'
                         f"org.jfree.data.time.{period}</property>")
        dataset_props = "".join(parts)
    elif el.chart_type == "thermometer":
        # a single value against a scale - no category or series axis, just
        # the one measure the gauge was reading
        collector = "org.pentaho.plugin.jfreereport.reportcharts.collectors.ValueDataSetCollector"
        dataset_props = f'<property name="valueColumn">{escape(el.chart_value)}</property>'
    elif el.chart_type == "pie":
        collector = "org.pentaho.plugin.jfreereport.reportcharts.collectors.PieDataSetCollector"
        dataset_props = (f'<property name="seriesColumn">{escape(el.chart_category)}</property>'
                         f'<property name="valueColumn">{escape(el.chart_value)}</property>')
    else:
        collector = "org.pentaho.plugin.jfreereport.reportcharts.collectors.CategorySetDataCollector"
        values = getattr(el, "chart_values", None) or []
        if len(values) > 1:
            # one chart, several measures: the collector takes indexed
            # valueColumn[i]/seriesName[i] pairs (PRD's own property reader
            # handles the [i] convention)
            dataset_props = (
                f'<property name="categoryColumn">{escape(el.chart_category)}</property>'
                + "".join(
                    f'<property name="valueColumn[{i}]">{escape(col)}</property>'
                    f'<property name="seriesName[{i}]">{escape(label or col)}</property>'
                    for i, (col, label) in enumerate(values)))
        else:
            dataset_props = (f'<property name="categoryColumn">{escape(el.chart_category)}</property>'
                             + (f'<property name="seriesColumn">{escape(el.chart_series)}</property>'
                                if el.chart_series else '<property name="seriesName">'
                                + escape(el.chart_value) + "</property>")
                             + f'<property name="valueColumn">{escape(el.chart_value)}</property>')
    if el.chart_type == "thermometer":
        title = el.chart_title or el.chart_value      # no category axis
        # a KPI meter, not a temperature: drop the default "C" unit label and
        # the legend a single value does not need
        chart_props = (f'<property name="titleText">{escape(title)}</property>'
                       '<property name="thermometerUnits" '
                       'class="org.pentaho.plugin.jfreereport.reportcharts.'
                       'ThermometerUnit">None</property>'
                       '<property name="showLegend" class="java.lang.Boolean">false</property>')
    else:
        title = (el.chart_title if getattr(el, "chart_title_literal", False)
                 else el.chart_title or f"{el.chart_value} by {el.chart_category}")
        chart_props = ((f'<property name="titleText">{escape(title)}</property>'
                        if title else "")
                       + '<property name="showLegend" class="java.lang.Boolean">true</property>')
        for prop, value in sorted(getattr(el, "chart_extra", {}).items()):
            chart_props += (f"<property name={quoteattr(prop)}>"
                            f"{escape(value)}</property>")
        xy_family = el.chart_type in ("xy-line", "scatter", "bubble")
        for prop, value in (
                ("domainTitle" if xy_family else "categoryAxisLabel",
                 getattr(el, "chart_category_axis_label", "")),
                ("rangeTitle" if xy_family else "valueAxisLabel",
                 getattr(el, "chart_value_axis_label", ""))):
            if value and el.chart_type not in ("pie", "multi-pie"):
                chart_props += f"<property name={quoteattr(prop)}>{escape(value)}</property>"
    return (
        f'<legacy-charts:legacy-chart core:element-type="legacy-chart" '
        f'xmlns:legacy-charts="{NS_LEGACY_CHARTS}">'
        f"<{sp}element-style>"
        f'<{sp}spatial-styles x="{_num(el.x)}" y="{_num(el.y)}" '
        f'min-width="{_num(el.width)}" min-height="{_num(el.height)}"/>'
        f"</{sp}element-style>"
        f'<expression attribute-namespace="{NS_LEGACY_CHARTS}" '
        f'attribute-name="primary-dataset-expression" class="{collector}">'
        f"<properties>{dataset_props}</properties></expression>"
        f'<attribute-expression namespace="http://reporting.pentaho.org/namespaces/engine/attributes/core" '
        f'name="value" class="{expr_class}">'
        f"<properties>"
        f"{chart_props}"
        f'<property name="backgroundColor">#ffffff</property>'
        f'<property name="showBorder" class="java.lang.Boolean">false</property>'
        f"</properties></attribute-expression>"
        f"</legacy-charts:legacy-chart>")


def _todo_label(el, text):
    from .model import Element, Font
    return Element(kind="label", x=el.x, y=el.y, width=el.width, height=el.height,
                   text=text, font=Font(size=8, italic=True, color="#cc0000"))


