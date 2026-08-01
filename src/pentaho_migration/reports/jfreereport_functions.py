"""Old JFreeReport function/expression classes -> their PRD translation.

ONE table serves both definition dialects (the simple `<report>` parser
and the legacy-EXT `<report-definition>` parser) - the corpus2 sweep
found the same classes blocking reports in both, and a mapping fixed in
two places is a mapping that drifts.

The ground truth is the PRD engine itself: every fully-qualified class
in PORTABLE below is verified present in the local install's engine
jars by tests/test_jfreereport_functions.py (the same evidence standard
as the emitter-vs-shipped-samples harness). The old classes did not
die - they moved wholesale from ``org.jfree.report.*`` to
``org.pentaho.reporting.engine.classic.core.*`` with their subpackages
(``strings``, ``date``, ``modules.misc.beanshell``) preserved, so the
properties carry over verbatim, indexed names (``field[0]``) included.
"""

_CORE = 'org.pentaho.reporting.engine.classic.core.'

# short class name -> PRD fully-qualified class (jar-verified)
PORTABLE = {
    # element visibility / decoration drivers
    'ElementVisibilitySwitchFunction':
        _CORE + 'function.ElementVisibilitySwitchFunction',
    'ShowElementIfDataAvailableExpression':
        _CORE + 'function.ShowElementIfDataAvailableExpression',
    'HideElementIfDataAvailableExpression':
        _CORE + 'function.HideElementIfDataAvailableExpression',
    'ItemHideFunction': _CORE + 'function.ItemHideFunction',
    'ElementColorFunction': _CORE + 'function.ElementColorFunction',
    'CreateHyperLinksFunction': _CORE + 'function.CreateHyperLinksFunction',
    'CreateGroupAnchorsFunction':
        _CORE + 'function.CreateGroupAnchorsFunction',
    # computed values
    'AverageExpression': _CORE + 'function.AverageExpression',
    'TextFormatExpression': _CORE + 'function.TextFormatExpression',
    'DateExpression': _CORE + 'function.date.DateExpression',
    'ToUpperCaseStringExpression':
        _CORE + 'function.strings.ToUpperCaseStringExpression',
    'ToLowerCaseStringExpression':
        _CORE + 'function.strings.ToLowerCaseStringExpression',
    'SubStringExpression': _CORE + 'function.strings.SubStringExpression',
    'MessageFormatExpression':
        _CORE + 'function.strings.MessageFormatExpression',
    # scripted: PRD ships the same BeanShell interpreter (bsh jar in lib)
    'BSHExpression': _CORE + 'modules.misc.beanshell.BSHExpression',
}

# property names that reference layout ELEMENTS by name - the writer
# must emit core:name on those elements or the ported function finds
# nothing to act on
TARGET_PROPS = ('element',)

# aggregate function classes -> (operation, running). The Item* family
# is a RUNNING value (row-by-row); Group*/TotalGroup* are group totals.
AGGREGATES = {
    'GroupCountFunction': ('Count', False),
    'ItemCountFunction': ('Count', True),
    'GroupSumFunction': ('Sum', False),
    'ItemSumFunction': ('Sum', True),
    'TotalGroupSumFunction': ('Sum', False),
    'ItemAvgFunction': ('Average', True),
    'ItemMinFunction': ('Minimum', True),
    'ItemMaxFunction': ('Maximum', True),
}

# classes the writer re-creates itself - elements bound to the function
# name become PRD special fields instead
SPECIALS = {
    'PageOfPagesFunction': 'pagenofm',
}

# per-class flavour for the conversion note, so the reviewer knows WHAT
# behaviour to verify rather than just that a class moved packages
_NOTE_FLAVOUR = {
    'ElementVisibilitySwitchFunction':
        "it toggles element '{element}' per row (banded shading) - "
        'verify the shading',
    'ShowElementIfDataAvailableExpression':
        "it shows element '{element}' only when the query returns rows "
        '- verify the no-data state',
    'HideElementIfDataAvailableExpression':
        "it hides element '{element}' when the query returns rows (the "
        "classic no-data banner) - verify the no-data state",
    'ItemHideFunction':
        "it suppresses repeated values of '{field}' on element "
        "'{element}' - verify the first row of each group still prints",
    'ElementColorFunction':
        "it colours element '{element}' by boolean '{field}' "
        '({colorTrue}/{colorFalse})',
    'CreateHyperLinksFunction':
        "it links element '{element}' to the URL in '{field}' - "
        'hyperlinks show in HTML/PDF output, not on paper',
    'BSHExpression':
        'a BeanShell SCRIPT carried verbatim (PRD ships the same '
        'interpreter, bsh 2.x in lib) - review the script logic',
}


def targets(cls_short, props):
    """Element names this function acts on, for core:name emission."""
    if cls_short not in PORTABLE:
        return []
    return [props[p] for p in TARGET_PROPS if props.get(p)]


def port_note(name, cls_short, props):
    flavour = _NOTE_FLAVOUR.get(cls_short)
    note = ("report function '{}' ({}) ported unchanged - PRD ships the "
            'same class'.format(name, cls_short))
    if flavour:
        class _Blank(dict):
            def __missing__(self, key):
                return '?'
        note += '; ' + flavour.format_map(_Blank(props))
    return note


def translate(cls_short, name, props):
    """One old function -> its PRD decision:

    ``('aggregate', (operation, running))`` - map to a Summary
    ``('special', column)``  - elements bound to it become special fields
    ``('port', fqcn)``       - emit verbatim under the PRD class name
    ``(None, None)``         - no mapping; the caller keeps its honest note
    """
    if cls_short in AGGREGATES:
        return 'aggregate', AGGREGATES[cls_short]
    if cls_short in SPECIALS:
        return 'special', SPECIALS[cls_short]
    if cls_short in PORTABLE:
        return 'port', PORTABLE[cls_short]
    return None, None


# ---------------------------------------------------------------- charts
# Chart expressions and their data collectors appear in BOTH dialects
# with the same class names and property shapes; the scan lives here so
# the mapping cannot drift between parsers. Every expression class below
# ships in PRD's legacy-charts jar and is registered for parsing;
# TimeSeriesChartExpression alone did not survive - but its DATA shape
# did (TimeSeriesCollector), and the corpus's own time-series reports
# author XYLineChartExpression over it, which is exactly the mapping.
CHART_TYPES = {
    'BarChartExpression': 'bar',
    'LineChartExpression': 'line',
    'AreaChartExpression': 'area',
    'PieChartExpression': 'pie',
    'MultiPieChartExpression': 'multi-pie',
    'XYLineChartExpression': 'xy-line',
    'ScatterPlotChartExpression': 'scatter',
    'BubbleChartExpression': 'bubble',
    'TimeSeriesChartExpression': 'xy-line',
}

XY_COLLECTORS = ('XYSeriesCollectorFunction', 'XYZSeriesCollectorFunction',
                 'TimeSeriesCollectorFunction')
COLLECTOR_CLASSES = ('PieSetCollectorFunction',
                     'CategorySetCollectorFunction') + XY_COLLECTORS

# authored expression props the RENDER depends on (a bubble scale of 0 -
# the class default - draws nothing; stacked turns a bar into a stack)
CHART_RIDE_ALONG = ('maxBubbleSize', 'stacked', 'stackedBarRenderPercentages')


def build_chart_protos(charts, collectors, issues):
    """Chart expressions + their collectors -> prototype chart Elements.

    ``charts`` is [(name, cls_short, props)], ``collectors`` is
    {name: (cls_short, props)}; conversion notes append to ``issues``.
    Returns {expression name: prototype Element} for drawable-field
    binding; a proto is cloned per placement (clone_chart)."""
    from pentaho_migration.reports.model import Element

    out = {}
    for name, cls, props in charts:
        proto = Element(kind="chart", chart_type=CHART_TYPES[cls],
                        chart_title=props.get("title", ""))
        # the definition SAYS what the chart shows - no title means
        # none, and the axis labels ride along
        proto.chart_title_literal = True
        proto.chart_category_axis_label = props.get("categoryAxisLabel", "")
        proto.chart_value_axis_label = props.get("valueAxisLabel", "")
        for extra in CHART_RIDE_ALONG:
            if props.get(extra):
                proto.chart_extra[extra] = props[extra]
        col_cls, col_props = collectors.get(props.get("dataSource", ""),
                                            ("", {}))
        if col_cls in XY_COLLECTORS:
            # boolean seriesColumn=true: seriesName[i] holds a COLUMN
            # whose row values name the series (the corpus's only shape)
            by_column = col_props.get("seriesColumn", "") == "true"
            entries = []
            for i in range(64):
                series = col_props.get(f"seriesName[{i}]")
                if col_cls == "TimeSeriesCollectorFunction":
                    x = col_props.get(f"timeValueColumn[{i}]")
                    y = col_props.get(f"valueColumn[{i}]")
                else:
                    x = col_props.get(f"xValueColumn[{i}]")
                    y = col_props.get(f"yValueColumn[{i}]")
                if not (x and y):
                    break
                entry = {"x": x, "y": y}
                if by_column and series:
                    entry["series_col"] = series
                else:
                    entry["series"] = series or f"series {i}"
                z = col_props.get(f"zValueColumn[{i}]")
                if z:
                    entry["z"] = z
                if col_cls == "TimeSeriesCollectorFunction":
                    entry["time"] = True
                    if col_props.get("domainPeriodType"):
                        entry["period"] = col_props["domainPeriodType"]
                entries.append(entry)
            proto.chart_xy = entries
            proto.chart_value = entries[0]["y"] if entries else ""
            # the XY family names its axis labels domainTitle/rangeTitle
            proto.chart_category_axis_label = props.get(
                "domainTitle", proto.chart_category_axis_label)
            proto.chart_value_axis_label = props.get(
                "rangeTitle", proto.chart_value_axis_label)
        elif col_cls == "PieSetCollectorFunction":
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
            out[name] = proto
            issues.append(
                f"chart migrated as a PRD legacy chart ('{name}': {cls} -> "
                f"{proto.chart_type})")
        else:
            issues.append(
                f"chart expression '{name}' ({cls}) has an empty or "
                "unrecognised data collector - rebuild the chart in PRD")
    return out


def clone_chart(proto):
    """A fresh Element from a chart prototype, for one placement."""
    from pentaho_migration.reports.model import Element

    el = Element(kind="chart")
    for attr in ("chart_type", "chart_title", "chart_category",
                 "chart_series", "chart_value", "chart_title_literal",
                 "chart_category_axis_label", "chart_value_axis_label"):
        setattr(el, attr, getattr(proto, attr))
    el.chart_values = list(proto.chart_values)
    el.chart_xy = [dict(e) for e in proto.chart_xy]
    el.chart_extra = dict(proto.chart_extra)
    return el
