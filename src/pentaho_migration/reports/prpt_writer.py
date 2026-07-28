"""Emit a Pentaho Report Designer .prpt bundle from a ReportModel.

A .prpt is a ZIP (ODF-style): a stored (uncompressed) `mimetype` entry
first, a META-INF/manifest.xml, and a set of XML documents:

    content.xml          - global templates (intentionally empty)
    layout.xml           - master report: report bands, groups, elements
    styles.xml           - page definition + page-header/footer/watermark bands
    datadefinition.xml   - parameters, data-source ref, expressions/functions
    dataschema.xml       - designtime schema hints (empty is valid)
    settings.xml         - runtime settings (empty is valid)
    meta.xml             - ODF document metadata
    datasources/*.xml    - data factories (JNDI SQL here)

The XML shapes below were reverse-engineered from the sample reports that
ship with Pentaho Report Designer CE (pentaho/pentaho-reporting on GitHub).
"""

import re
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape, quoteattr

MIMETYPE = "application/vnd.pentaho.reporting.classic"

NS_LAYOUT = "http://reporting.pentaho.org/namespaces/engine/classic/bundle/layout/1.0"
NS_STYLE = "http://reporting.pentaho.org/namespaces/engine/classic/bundle/style/1.0"
NS_CORE = "http://reporting.pentaho.org/namespaces/engine/attributes/core"
NS_DATA = "http://reporting.pentaho.org/namespaces/engine/classic/bundle/data/1.0"
NS_PARAM = "http://reporting.pentaho.org/namespaces/engine/parameter-attributes/core"
NS_SQL = "http://jfreereport.sourceforge.net/namespaces/datasources/sql"
NS_COMPOUND = "http://reporting.pentaho.org/namespaces/datasources/compound/1.0"

PARAM_TYPE_MAP = {
    "StringField": "java.lang.String",
    "NumberField": "java.lang.Double",
    "CurrencyField": "java.lang.Double",
    "IntegerField": "java.lang.Long",
    "DateField": "java.util.Date",
    "DateTimeField": "java.sql.Timestamp",
    "TimeField": "java.sql.Time",
    "BooleanField": "java.lang.Boolean",
}

from pentaho_migration.reports.model import (
    CROSSTAB_AGG_MAP, RUNNING_CLASS_MAP, SUMMARY_CLASS_MAP)
from pentaho_migration.reports.prpt_render import _num, render_element

# Outline indent for nested groups. A NON-BREAKING space, because a PDF
# viewer is free to collapse ordinary leading spaces in an outline title.
NBSP = " "

NS_CROSSTAB = "http://reporting.pentaho.org/namespaces/engine/attributes/crosstab"
NS_WIZARD = "http://reporting.pentaho.org/namespaces/engine/attributes/wizard"


def _needs_page_function(model):
    # standalone special elements, or a text template that interpolates the
    # page number ("Page PageNumber" text objects resolve to $(PageofPages))
    return any(
        (el.kind == "special" and el.column in ("pagenumber", "pagenofm", "totalpagecount"))
        or "$(PageofPages)" in getattr(el, "text_template", "")
        for s in model.sections for el in s.elements)


_SUM_FN = "org.pentaho.reporting.engine.classic.core.function.TotalGroupSumFunction"


def _percent_of_sum_xml(summary, column):
    """Crystal PercentOfSum as PRD functions: this group's sum, the wider
    total it is a share of, and a formula dividing one by the other.

    The engine's own TotalGroupSumQuotientPercentFunction is NOT the
    equivalent - it divides two different FIELDS inside one group, where
    Crystal divides ONE field across two group SCOPES. Wired to it, every
    row printed the same percentage. A formula over two declared sums says
    exactly what Crystal means. Crystal's value is already scaled to
    0-100, so the x100 keeps the numbers identical."""
    part = summary.expression_name + "_part"
    whole = summary.expression_name + "_whole"

    def total(name, group):
        props = [f'<property name="field">{escape(column)}</property>']
        if group:
            props.append(f'<property name="group">{escape(group)}</property>')
        return (f'<expression name={quoteattr(name)} class="{_SUM_FN}">'
                f"<properties>{''.join(props)}</properties></expression>")

    formula = (f"=IF([{whole}] = 0;0;[{part}] / [{whole}] * 100)")
    return (total(part, summary.group_field)
            + total(whole, summary.percent_of)
            + f'<expression name={quoteattr(summary.expression_name)} '
              f"formula={quoteattr(formula)}/>")


def _special_functions_used(model):
    """Report functions the converted formulas reference by name, because
    Crystal wrote a special field bare inside one ("PageNumber = 1"). Found
    by scanning the emitted text rather than threaded through the translator,
    the same way the page function is: a declaration is needed exactly when
    some formula names it, wherever that formula ended up.

    Returns (function name, java class) pairs, declaration order stable."""
    from .formula_translator import SPECIAL_FUNCTIONS

    text = []
    for section in model.sections:
        text.extend(f for _, f in section.style_expressions)
        for el in section.elements:
            text.extend(f for _, f in el.style_expressions)
    for f in model.formulas.values():
        text.append(getattr(f, "translation", "") or "")
    blob = " ".join(text)
    return [(name, cls) for name, cls in SPECIAL_FUNCTIONS.values()
            if f"[{name}]" in blob]


def _band_content(sections, band_type, tp="", sp="style:"):
    """One or more Crystal sections of an area as the inner XML of one PRD
    band. Each section becomes a NESTED sub-band stacked in block layout,
    carrying its own height, background, suppress condition and page-break -
    so a conditionally suppressed section COLLAPSES exactly like Crystal
    (three letter variants take one section's height, not three), instead of
    hiding its elements inside a band that keeps its full height.

    An UNDERLAY section (Crystal "Underlay Following Sections") takes no
    vertical space of its own: its elements are painted BEHIND the sections
    that follow it. Reproduced by copying its elements - shifted into each
    following section's coordinate space - to the FRONT of that section's
    band (PRD paints in document order, first = behind), and dropping the
    underlay band itself. This is what lets a watermark sit behind a letter
    instead of pushing it half a page down.

    Returns (inner_xml, height, bg_color) - bg is the first styled section's,
    kept for the callers that paint a whole-band background (page bands)."""
    import copy as _copy

    visible = [s for s in sections
               if not s.suppressed
               and not (s.suppress_if_blank and not s.elements)]

    # Underlay element placement: each element goes to the following
    # section(s) that can hold it - every section covering >=90% of its span
    # (Crystal's mutually-exclusive letter variants share one geometry, and
    # exactly one of them renders), or failing that the single best-overlap
    # section. Copying into every intersecting section instead duplicates the
    # watermark AND grows small bands to the raster's height, pushing
    # everything below onto the next page.
    behind: dict = {}
    offset_after = 0.0
    for i, section in enumerate(visible):
        if not section.underlay:
            offset_after += section.height
            continue
        # Span offsets in RUNTIME terms, not design terms: consecutive
        # sections that carry visibility CONDITIONS are mutually-exclusive
        # alternatives (Crystal's letter variants) - at runtime exactly one
        # occupies the slot, so they all share ONE start offset and the
        # stack advances once, by the tallest of the run. Computing offsets
        # from the design stack instead put the underlay copy in variant 1
        # only, and the customer whose statement shows variant 2 lost the
        # signature block - found by the release gate.
        gap = 0.0
        spans = []
        run_height = 0.0
        for j in range(i + 1, len(visible)):
            target = visible[j]
            if target.underlay:
                continue
            conditional = any(k == "visible" for k, _ in target.style_expressions)
            spans.append((j, gap, target.height))
            if conditional:
                run_height = max(run_height, target.height)
            else:
                if run_height:
                    gap += run_height        # the alternatives' shared slot
                    run_height = 0.0
                gap += target.height
        for el in section.elements:
            overlaps = []
            for j, start, t_height in spans:
                lo = max(el.y - start, 0.0)
                hi = min(el.y - start + el.height, t_height)
                overlaps.append((max(hi - lo, 0.0), j, start))
            if not overlaps:
                continue
            best = max(cover for cover, _j, _s in overlaps)
            if best <= 0:
                continue
            # every section tied for best coverage gets the copy - Crystal's
            # mutually-exclusive letter variants share one geometry, and the
            # element must ride whichever of them renders
            targets = [(j, start) for cover, j, start in overlaps
                       if cover >= best - 1.0]
            for j, start in targets:
                el2 = _copy.copy(el)
                # Clamped at the band top. Crystal can paint an underlay from
                # ABOVE the section it underlays - an empty spacer section
                # between the two makes the offset negative - but a PRD band
                # has no space above its origin, and a negative y made the
                # engine push the watermark BELOW the letter instead of
                # behind it. Starting it at the top keeps it behind the text,
                # which is the point of an underlay.
                el2.y = max(el.y - start, 0.0)
                behind.setdefault(j, []).append(el2)

    inner, total, bg = [], 0.0, ""
    for i, section in enumerate(visible):
        if section.underlay:
            continue
        if section.bg_color and not bg:
            bg = section.bg_color
        inner.append(_section_band(section, tp, sp,
                                   behind_elements=behind.get(i, [])))
        total += section.height
    height = max(total, 20.0)
    return "".join(inner), height, bg


def _section_band(section, tp="", sp="style:", behind_elements=None):
    """One Crystal section as a nested PRD band: canvas inside (elements keep
    their absolute positions), block-stacked by the parent. `behind_elements`
    (underlay copies) render first, i.e. behind the section's own content."""
    # The band must be at least as tall as what it holds. Crystal's declared
    # height is authoritative for EMPTY bands (a zero-height detail band is
    # how a chart report prints one page instead of one per row), but a band
    # whose objects reach past it would clip them.
    content_bottom = max((el.y + el.height for el in section.elements
                          if getattr(el, "visible", True)), default=0.0)
    height = max(section.height, content_bottom)
    # Trailing empty space in a band that is followed by a page break cannot
    # be seen - nothing renders in it and the page ends immediately after.
    # Reserving it anyway is what split 21 of the demo's 36 statements: the
    # group footer declared 138.75pt while its content ended at 80.25pt, the
    # page had 125pt left, so a band that would have FIT jumped to the next
    # page and took the statement's total with it.
    #
    # Only when a break follows, only when the slack is genuinely empty (a
    # background fill or a box would show it), and never for an empty band -
    # Crystal's declared height is what makes a zero-height detail band print
    # one page instead of one per row.
    if (section.new_page_after and content_bottom and not section.bg_color
            and height > content_bottom):
        height = content_bottom
    # Crystal's "Keep Together": the band moves whole to the next page rather
    # than splitting across one. PRD spells it `avoid-page-break`. Without it
    # a statement broke halfway down its invoice table where the original
    # broke after the letter - same page count, wrong place.
    keep = ('<{0}common-styles avoid-page-break="true"/>'.format(sp)
            if section.keep_together else "")
    styles = [f'<{sp}band-styles layout="canvas"'
              + (' pagebreak-after="true"' if section.new_page_after else "")
              + "/>", keep,
              f'<{sp}spatial-styles x="0" y="0" '
              f'min-width="100%" min-height="{_num(height)}"/>']
    if section.bg_color:
        styles.append(f'<{sp}border-styles background-color={quoteattr(section.bg_color)}/>')
    exprs = "".join(
        f"<style-expression style-key={quoteattr(key)} formula={quoteattr(formula)}/>"
        for key, formula in section.style_expressions)
    # Crystal's paint order: drawing objects (boxes, lines) sit BEHIND report
    # objects - a grey total box must not cover the "Total:" printed on it.
    # Underlay copies go first of all (they underlay everything).
    decor = [el for el in section.elements if el.kind in ("box", "line")]
    front = [el for el in section.elements if el.kind not in ("box", "line")]
    content = "".join(render_element(el, tp, sp)
                      for el in (behind_elements or []) + decor + front)
    return (f'<{tp}band core:element-type="band">'
            f"<{sp}element-style>{''.join(styles)}</{sp}element-style>"
            f"{exprs}{content}</{tp}band>")


def _root_band(sections, element_type, bookmark_field="", bookmark_depth=0):
    content, height, _bg = _band_content(sections, element_type)
    # The parent stacks its section sub-bands; each sub-band paints its own
    # background and carries its own suppress condition.
    style = ('<style:element-style><style:band-styles layout="block"/>'
             "</style:element-style>")
    # Crystal's viewer navigates a long report by its GROUP TREE - countries,
    # then customers within each. PRD's equivalent is the `bookmark` band
    # style: a group header carrying one becomes an entry in the PDF outline
    # panel, bound to the group's own column so every value labels its entry.
    #
    # The engine's PDF writer attaches every bookmark to the ROOT outline
    # (PdfLogicalPageDrawable.drawBookmark -> new PdfOutline(getRootOutline(),
    # ...)), so a real hierarchy is not reachable from here. Inner groups are
    # INDENTED instead, which reads as the tree it represents in every PDF
    # viewer's outline panel.
    bookmark = ""
    if bookmark_field:
        indent = NBSP * 4 * bookmark_depth
        formula = (f'="{indent}" & [{bookmark_field}]' if indent
                   else f"=[{bookmark_field}]")
        bookmark = ('<style-expression style-key="bookmark" '
                    f"formula={quoteattr(formula)}/>")
    return (f'<root-level-content core:element-type="{element_type}" '
            f'xmlns:report-designer="http://reporting.pentaho.org/namespaces/report-designer/2.0" '
            f'report-designer:visual-height="{_num(height)}">'
            f"{style}{bookmark}{content}</root-level-content>")


# ---------------------------------------------------------------- layout.xml

def build_layout_xml(model, root_type="master-report"):
    def group_block(i):
        if i < len(model.groups):
            g = model.groups[i]
            headers = model.sections_of("GroupHeader", i)
            footers = model.sections_of("GroupFooter", i)
            inner = group_block(i + 1)
            if i + 1 < len(model.groups):
                body = f'<group-body core:element-type="sub-group-body">{inner}</group-body>'
            else:
                body = inner
            return (
                f'<group core:element-type="relational-group" '
                f'core:group-fields={quoteattr(g.column)} core:name={quoteattr(g.column)}>'
                f"<fields><field>{escape(g.column)}</field></fields>"
                f"<group-header>"
                f"{_root_band(headers, 'group-header', bookmark_field=g.column, bookmark_depth=i)}"
                f"</group-header>"
                f"{body}"
                f"<group-footer>{_root_band(footers, 'group-footer')}</group-footer>"
                f"</group>")
        # innermost: the data body with the detail band. Crystal's PageHeader
        # maps to PRD's physical page-header (see build_styles_xml) - a
        # details-header was tried and is the wrong band: it lives inside the
        # innermost group, so a letterhead rendered above each detail block
        # (or, with grouped reports, not visibly at all) instead of topping
        # the page the way the page-FOOTER already tops the bottom.
        details = model.sections_of("Detail")
        return (
            '<data-body core:element-type="group-data-body">'
            '<details-header core:element-type="details-header"/>'
            f"<details>{_root_band(details, 'itemband')}</details>"
            '<no-data><root-level-content core:element-type="no-data-band"/></no-data>'
            '<details-footer core:element-type="details-footer"/>'
            "</data-body>")

    if model.groups:
        group_xml = group_block(0)
    else:
        inner = group_block(len(model.groups))  # data-body directly
        group_xml = (f'<group core:element-type="relational-group" core:group-fields="">'
                     f"<fields></fields>"
                     f"<group-header><root-level-content core:element-type=\"group-header\"/></group-header>"
                     f"{inner}"
                     f"<group-footer><root-level-content core:element-type=\"group-footer\"/></group-footer>"
                     f"</group>")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<layout xmlns="{NS_LAYOUT}" xmlns:style="{NS_STYLE}" xmlns:core="{NS_CORE}" '
        f'core:element-type="{root_type}" core:name={quoteattr(model.name)}>'
        "<style:element-style><style:text-styles font-face=\"Arial\"/></style:element-style>"
        f"<report-header>{_root_band(model.sections_of('ReportHeader'), 'report-header')}</report-header>"
        f"{group_xml}"
        f"<report-footer>{_root_band(model.sections_of('ReportFooter'), 'report-footer')}</report-footer>"
        "</layout>")


# ------------------------------------------------------- crosstab layout.xml
# The exact shapes below were produced by the ENGINE's own bundle writer from
# CrosstabBuilder-built reports (tools/CrosstabRef*.java) and verified to
# parse, render and aggregate - mimic them precisely.

_CT_CELL = ('<style:element-style><style:spatial-styles min-width="80" '
            'min-height="20" max-width="80" max-height="20"/></style:element-style>')
_CT_FULL = ('<style:element-style><style:spatial-styles min-height="100%"/>'
            "</style:element-style>")


def _ct_group_headers(column):
    """title-header / header / summary-header triple every crosstab group carries."""
    return (
        f"<crosstab-title-header>{_CT_FULL}"
        f'<label wizard:allow-metadata-attributes="true" wizard:label-for={quoteattr(column)}>'
        f"{_CT_CELL}<core:value>{escape(column)}</core:value></label></crosstab-title-header>"
        f"<crosstab-header>{_CT_FULL}"
        f"<text-field core:field={quoteattr(column)}>{_CT_CELL}</text-field></crosstab-header>"
        f"<crosstab-summary-header>{_CT_FULL}"
        f'<label wizard:allow-metadata-attributes="true" wizard:label-for={quoteattr(column)}>'
        f"{_CT_CELL}<core:value>Summary</core:value></label></crosstab-summary-header>")


def _ct_cell_body(summaries):
    """details-header labels + the details cell, one number-field per measure."""
    headers = "".join(
        f'<label wizard:allow-metadata-attributes="true" wizard:label-for={quoteattr(c)}>'
        f"{_CT_CELL}<core:value>{escape(f'{op} of {c}')}</core:value></label>"
        for c, op in summaries)
    fields = "".join(
        f'<number-field core:format-string={quoteattr("#,##0" if op == "Count" else "#,##0.00")} '
        f"core:field={quoteattr(c)} "
        f"wizard:aggregation-type={quoteattr(CROSSTAB_AGG_MAP[op])}>{_CT_CELL}</number-field>"
        for c, op in summaries)
    return (
        '<crosstab-cell-body><style:element-style>'
        '<style:common-styles avoid-page-break="false"/></style:element-style>'
        '<details-header><style:element-style><style:band-styles layout="row"/>'
        '<style:common-styles avoid-page-break="true"/>'
        '<style:spatial-styles min-height="100%"/></style:element-style>'
        f"{headers}</details-header>"
        '<crosstab-cell core:name="details-cell"><style:element-style>'
        '<style:band-styles layout="row"/><style:spatial-styles min-height="100%"/>'
        f"</style:element-style>{fields}</crosstab-cell></crosstab-cell-body>")


def _ct_column_chain(columns, summaries):
    inner = _ct_cell_body(summaries)
    for column in reversed(columns):
        inner = (
            f'<crosstab-column-group-body><crosstab-column-group '
            f"core:name={quoteattr(column)} core:field={quoteattr(column)} "
            f'crosstab:print-summary="false">'
            f"<field>{escape(column)}</field>{_ct_group_headers(column)}{inner}"
            "</crosstab-column-group></crosstab-column-group-body>")
    return inner


def _ct_row_chain(rows, columns, summaries):
    inner = _ct_column_chain(columns, summaries)
    for column in reversed(rows):
        inner = (
            f'<crosstab-row-group-body><crosstab-row-group '
            f"core:name={quoteattr(column)} core:field={quoteattr(column)} "
            f'crosstab:print-summary="false">'
            f"<field>{escape(column)}</field>{_ct_group_headers(column)}{inner}"
            "</crosstab-row-group></crosstab-row-group-body>")
    return inner


def build_crosstab_layout_xml(child, el, root_type="sub-report"):
    """layout.xml for a bundle whose ROOT GROUP is the crosstab - PRD pivots
    are a group structure, not a band element, so each Crystal cross-tab
    becomes a nested sub-report carrying this layout."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<layout xmlns="{NS_LAYOUT}" xmlns:style="{NS_STYLE}" xmlns:core="{NS_CORE}" '
        f'xmlns:crosstab="{NS_CROSSTAB}" xmlns:wizard="{NS_WIZARD}" '
        f'core:element-type="{root_type}" core:name={quoteattr(child.name)}>'
        '<style:element-style><style:text-styles font-face="Arial"/></style:element-style>'
        '<report-header><root-level-content core:element-type="report-header"/></report-header>'
        "<crosstab>"
        '<group-header><root-level-content core:element-type="group-header"/></group-header>'
        '<no-data><root-level-content core:element-type="no-data-band"/></no-data>'
        f"{_ct_row_chain(el.crosstab_rows, el.crosstab_columns, el.crosstab_summaries)}"
        '<group-footer><root-level-content core:element-type="group-footer"/></group-footer>'
        "</crosstab>"
        '<report-footer><root-level-content core:element-type="report-footer"/></report-footer>'
        "</layout>")


def _crosstab_child_model(model, el):
    """Synthetic child ReportModel for one cross-tab element: the parent's
    datasource and SQL, no bands/groups of its own (the crosstab group IS the
    report body). Parent parameters stay so ${P} in the SQL resolves - they
    are imported through the sub-report's parameter mappings, not re-prompted.

    The crosstab runtime REQUIRES rows sorted by row dims then column dims
    ('Unsorted column dimension data' InvalidReportStateException otherwise),
    so the child SQL gets its own ORDER BY over the dimensions."""
    import copy

    child = copy.deepcopy(model)
    child.name = el.name or "CrossTab"
    child.sections = []
    child.groups = []
    child.subreports = {}
    child.record_sorts = []
    child.summaries = []

    def _order_expr(column):
        if model.sql_generated:
            return next((f"{t}.{column}" for t, fs in model.tables.items()
                         if column in fs), column)
        return f'"{column}"'  # Command SQL exposes the quoted SELECT aliases

    dims = el.crosstab_rows + el.crosstab_columns
    base = re.sub(r"\s+ORDER\s+BY\b.*$", "", child.sql, flags=re.I | re.S)
    child.sql = base + "\nORDER BY " + ", ".join(_order_expr(c) for c in dims)
    return child


# ---------------------------------------------------------------- styles.xml

def _page_band_bg(bg):
    return (f'<element-style><border-styles background-color={quoteattr(bg)}/></element-style>'
            if bg else "")


def build_styles_xml(model):
    # Both Crystal page bands map to PRD's physical page bands. One known
    # difference, called out as a conversion note: Crystal prints page 1 as
    # ReportHeader then PageHeader, while PRD's page-header tops every page
    # including the first. Losing the letterhead on every page (what any other
    # mapping costs) is strictly worse than that page-1 band-order swap.
    p = model.page
    ph_content, _, ph_bg = _band_content(model.sections_of("PageHeader"), "page-header", tp="layout:", sp="")
    pf_content, _, pf_bg = _band_content(model.sections_of("PageFooter"), "page-footer", tp="layout:", sp="")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<style xmlns="{NS_STYLE}" xmlns:layout="{NS_LAYOUT}" xmlns:core="{NS_CORE}">'
        f'<page-definition horizontal-span="1" vertical-span="1" pageformat={quoteattr(p.paper)} '
        f'orientation={quoteattr(p.orientation)} margin-top="{_num(p.margin_top)}" '
        f'margin-left="{_num(p.margin_left)}" margin-bottom="{_num(p.margin_bottom)}" '
        f'margin-right="{_num(p.margin_right)}"/>'
        '<layout:watermark core:element-type="watermark"></layout:watermark>'
        f'<layout:page-header core:element-type="page-header">'
        f'<element-style><band-styles layout="block"/></element-style>'
        f'{_page_band_bg(ph_bg)}{ph_content}</layout:page-header>'
        f'<layout:page-footer core:element-type="page-footer">'
        f'<element-style><band-styles layout="block"/></element-style>'
        f'{_page_band_bg(pf_bg)}{pf_content}</layout:page-footer>'
        "</style>")


# ------------------------------------------------------- datadefinition.xml

def _parameter_xml(prm, lov_query=None):
    """A Crystal parameter -> PRD parameter. Multi-value or pick-list (LOV)
    parameters become list-parameters; a prompt whose record selection folded
    against a known column becomes a QUERY-BACKED dropdown (SELECT DISTINCT
    from the live database); simple prompts stay plain textboxes.
    Optional Crystal prompts map to mandatory=false."""
    jtype = PARAM_TYPE_MAP.get(prm.value_type, "java.lang.String")
    mandatory = "false" if prm.optional else "true"
    label = (f'<attribute namespace="{NS_PARAM}" name="label">'
             f'{escape(prm.prompt or prm.name)}</attribute>')
    if lov_query and not prm.default_values:
        default = f" default-value={quoteattr(prm.default)}" if prm.default else ""
        jtype_list = f"[L{jtype};" if prm.multi_value else jtype
        render = "checkbox" if prm.multi_value else "dropdown"
        return (
            f'<list-parameter name={quoteattr(prm.name)} '
            f'allow-multi-selection="{str(prm.multi_value).lower()}" '
            f'strict-values="false" mandatory="{mandatory}" '
            f'type={quoteattr(jtype_list)} query={quoteattr(lov_query)} '
            f'key-column="LOV" value-column="LOV"{default}>'
            f'{label}'
            f'<attribute namespace="{NS_PARAM}" name="parameter-render-type">{render}</attribute>'
            "</list-parameter>")
    if prm.multi_value or prm.default_values:
        # a static pick-list built from the Crystal default-value list
        items = "".join(
            f'<value type="{jtype}" value={quoteattr(v)} null="false"/>'
            for v in prm.default_values)
        render = "checkbox" if prm.multi_value else "dropdown"
        default = f" default-value={quoteattr(prm.default)}" if prm.default else ""
        jtype_list = f"[L{jtype};" if prm.multi_value else jtype
        return (
            f'<list-parameter name={quoteattr(prm.name)} '
            f'allow-multi-selection="{str(prm.multi_value).lower()}" '
            f'strict-values="false" mandatory="{mandatory}" '
            f'type={quoteattr(jtype_list)}{default}>'
            f'{label}'
            f'<attribute namespace="{NS_PARAM}" name="parameter-render-type">{render}</attribute>'
            + (f'<value-list>{items}</value-list>' if items else "")
            + "</list-parameter>")
    default = f" default-value={quoteattr(prm.default)}" if prm.default else ""
    return (
        f'<plain-parameter name={quoteattr(prm.name)} mandatory="{mandatory}" '
        f'type="{jtype}"{default}>'
        f'{label}'
        f'<attribute namespace="{NS_PARAM}" name="parameter-render-type">textbox</attribute>'
        f"</plain-parameter>")


def _is_fieldless(cls):
    """Row-count functions have no 'field' bean property (they count rows) -
    the engine rejects the property outright. CountDistinct DOES take one."""
    return cls.endswith(("ItemCountFunction", "TotalGroupCountFunction",
                         "TotalItemCountFunction", "GroupCountFunction"))


def build_datadefinition_xml(model, parameter_mappings=None):
    """parameter_mappings: [(master_column, child_param)] for a subreport's
    imported parameters - those arrive from the parent row, so they are
    declared as mappings, not prompts."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<data-definition xmlns="{NS_DATA}">']
    imported = set()
    if parameter_mappings:
        parts.append("<parameter-mapping>")
        for master, alias in parameter_mappings:
            imported.add(alias)
            parts.append(f'<input-parameter name={quoteattr(master)} '
                         f'alias={quoteattr(alias)}/>')
        parts.append("</parameter-mapping>")
    parts.append("<parameter-definition>")
    for prm in model.parameters:
        if prm.name in imported:
            continue  # supplied by the parent row, never prompted
        lov = f"lov_{prm.name}" if prm.name in model.param_sql_columns else None
        parts.append(_parameter_xml(prm, lov_query=lov))
    parts.append("</parameter-definition>")
    parts.append('<data-source report-query="default" limit="-1" timout="0" '
                 'ref="datasources/compound-ds.xml"/>')

    for f in model.formulas.values():
        if f.rewrite_class:
            # blocked Crystal idiom rewritten as a native PRD report function
            # (e.g. running-total variable -> ItemSumFunction); review-flagged
            props = []
            if f.rewrite_field and not _is_fieldless(f.rewrite_class):
                props.append(f'<property name="field">{escape(f.rewrite_field)}</property>')
            if f.rewrite_group:
                props.append(f'<property name="group">{escape(f.rewrite_group)}</property>')
            body = f"<properties>{''.join(props)}</properties>" if props else ""
            parts.append(f"<expression name={quoteattr(f.name)} "
                         f"class=\"{f.rewrite_class}\">{body}</expression>")
        elif f.status in ("auto", "review") and f.translation:
            parts.append(f"<expression name={quoteattr(f.name)} formula={quoteattr(f.translation)}/>")

    for s in model.summaries:
        cls = (RUNNING_CLASS_MAP if s.running else SUMMARY_CLASS_MAP).get(s.operation)
        if not cls:
            continue
        from .rpt_parser import parse_field_ref
        _, column = parse_field_ref(s.field_ref)
        if s.percent_of is not None:
            parts.append(_percent_of_sum_xml(s, column))
            continue
        props = ([] if _is_fieldless(cls)
                 else [f'<property name="field">{escape(column)}</property>'])
        if s.group_field:
            props.append(f'<property name="group">{escape(s.group_field)}</property>')
        parts.append(f"<expression name={quoteattr(s.expression_name)} class=\"{cls}\">"
                     f"<properties>{''.join(props)}</properties></expression>")

    for name, cls in _special_functions_used(model):
        parts.append(f'<expression name="{name}" class="{cls}">'
                     "<properties/></expression>")

    if _needs_page_function(model):
        parts.append(
            '<expression name="PageofPages" '
            'class="org.pentaho.reporting.engine.classic.core.function.PageOfPagesFunction">'
            "<properties><property name=\"format\">{0} / {1}</property>"
            '<property name="pageIncrement">1</property>'
            '<property name="startPage">1</property></properties></expression>')

    parts.append("</data-definition>")
    return "".join(parts)


# ------------------------------------------------------------- datasources

def build_sql_ds_xml(model, query_name="default"):
    return (
        f'<data:sql-datasource xmlns:data="{NS_SQL}">'
        "<data:config/>"
        f"<data:jndi><data:path>{escape(model.jndi)}</data:path></data:jndi>"
        "<data:query-definitions>"
        f'<data:query name="{escape(query_name)}"><data:static-query>'
        f"{escape(model.sql)}"
        "</data:static-query></data:query>"
        + "".join(
            f'<data:query name="lov_{escape(name)}"><data:static-query>'
            f'{escape(_lov_sql(model, column))}'
            "</data:static-query></data:query>"
            for name, column in model.param_sql_columns.items())
        + "</data:query-definitions>"
        "</data:sql-datasource>")


def _lov_sql(model, column):
    """Pick-list query for a folded prompt: SELECT DISTINCT the filtered
    column over the report's own FROM clause (before WHERE/ORDER BY), so the
    dropdown offers exactly the values the report can filter on."""
    m = re.search(r"\bFROM\b(.*?)(?:\bWHERE\b|\bORDER\s+BY\b|\bGROUP\s+BY\b|$)",
                  model.sql, flags=re.IGNORECASE | re.DOTALL)
    from_clause = m.group(1).strip() if m else "TABLE"
    return (f'SELECT DISTINCT {column} AS "LOV"\nFROM {from_clause}\n'
            f"ORDER BY 1")


def build_compound_ds_xml(with_inline=False):
    # The inline table (recovered saved data) answers the report query; the
    # SQL factory rides along under "source-sql" so switching to live data in
    # PRD is picking a query, not rebuilding a datasource.
    inline = '<data:data-factory href="inline-ds.xml"/>' if with_inline else ""
    return (f'<data:compound-datasource xmlns:data="{NS_COMPOUND}">'
            f'{inline}'
            '<data:data-factory href="sql-ds.xml"/>'
            "</data:compound-datasource>")


# ------------------------------------------------------------ boilerplate

CONTENT_XML = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<content xmlns="http://reporting.pentaho.org/namespaces/engine/classic/bundle/content/1.0"/>')

SETTINGS_XML = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<settings xmlns="http://reporting.pentaho.org/namespaces/engine/classic/bundle/settings/1.0">'
                "<configuration></configuration><runtime></runtime></settings>")

DATASCHEMA_XML = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<data-schema xmlns="http://reporting.pentaho.org/namespaces/engine/classic/dataschema/1.0"></data-schema>')


def build_meta_xml(model, spec_version=None):
    """spec_version (major, minor, patch) declares the prpt-spec the bundle
    targets. Without it the engine runs the report in pre-4.0 legacy layout
    mode - fine for banded reports (and what every existing conversion is
    verified against), but crosstabs use table layouts which legacy mode
    refuses ('IncompatibleFeatureException'), so bundles containing a
    crosstab declare 5.0.0."""
    from pentaho_migration import __version__
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    ns = "http://reporting.pentaho.org/namespaces/engine/classic/metadata/1.0"
    spec = ""
    if spec_version:
        major, minor, patch = spec_version
        spec = "".join(
            f'<autoGenNs:prpt-spec.version.{part} xmlns:autoGenNs="{ns}">{value}'
            f"</autoGenNs:prpt-spec.version.{part}>"
            for part, value in (("major", major), ("minor", minor), ("patch", patch)))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<office:meta>"
        f"<meta:creation-date>{now}</meta:creation-date>"
        f"<meta:generator>Migration Copilot {__version__}</meta:generator>"
        f"<dc:title>{escape(model.name)}</dc:title>"
        "<dc:description>Converted from SAP Crystal Reports</dc:description>"
        f"<dc:date>{now}</dc:date>"
        f"{spec}"
        "</office:meta></office:document-meta>")


def build_manifest_xml(entries):
    """entries: {path: media-type}."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">',
             f'  <manifest:file-entry manifest:full-path="/" manifest:media-type="{MIMETYPE}"/>']
    for name in sorted(entries):
        lines.append(f'  <manifest:file-entry manifest:full-path="{escape(name)}" '
                     f'manifest:media-type="{entries[name]}"/>')
    lines.append("</manifest:manifest>")
    return "\n".join(lines)


def _collect_images(model):
    """Assign a bundle resource path to every embedded image and return
    {path: bytes}. Mutates el.resource_path so the layout can reference it."""
    resources, idx = {}, 0
    for section in model.sections:
        for el in section.elements:
            if el.kind == "image" and el.image_bytes:
                idx += 1
                ext = "png" if "png" in (el.image_mime or "") else "jpg"
                path = f"resources/image{idx}.{ext}"
                el.resource_path = path
                resources[path] = el.image_bytes
    return resources


# ------------------------------------------------------------------ bundle

SUBREPORT_MIMETYPE = "application/vnd.pentaho.reporting.classic.subreport"


def _collect_subreports(model):
    """Assign each converted subreport its bundle directory (mutates
    el.subreport_href so the layout can reference it) and return
    [(dirname, element, child_model)]. Cross-tab elements ride the same
    machinery: a synthetic child (parent datasource, crosstab root group) is
    generated per pivot, and every parent parameter is mapped through so
    ${P} in the shared SQL resolves without re-prompting."""
    subs, idx = [], 0
    for section in model.sections:
        for el in section.elements:
            if el.kind == "subreport" and el.subreport is not None:
                child = el.subreport
            elif el.kind == "crosstab":
                child = _crosstab_child_model(model, el)
                el.subreport_links = [(p.name, p.name) for p in model.parameters]
            else:
                continue
            dirname = "subreport" if idx == 0 else f"subreport-{idx}"
            el.subreport_href = f"/{dirname}/content.xml"
            subs.append((dirname, el, child))
            idx += 1
    return subs


def write_prpt(model, out_path, saved_rows=None):
    """saved_rows: a rpt_saved.SavedRows recovered from the .rpt binary. When
    given, the bundle's report query is an INLINE TABLE of those rows - the
    .prpt opens in PRD showing real data with no database - and the report
    SQL ships beside it as the "source-sql" query for going live."""
    images = _collect_images(model)  # assigns resource paths before layout is built
    subreports = _collect_subreports(model)  # assigns hrefs before layout is built
    has_crosstab = any(el.kind == "crosstab" for _, el, _ in subreports)
    docs = {
        "content.xml": CONTENT_XML,
        "layout.xml": build_layout_xml(model),
        "styles.xml": build_styles_xml(model),
        "datadefinition.xml": build_datadefinition_xml(model),
        "dataschema.xml": DATASCHEMA_XML,
        "settings.xml": SETTINGS_XML,
        "meta.xml": build_meta_xml(
            model, spec_version=(5, 0, 0) if has_crosstab else None),
        "datasources/sql-ds.xml": build_sql_ds_xml(
            model, query_name="source-sql" if saved_rows else "default"),
        "datasources/compound-ds.xml": build_compound_ds_xml(
            with_inline=saved_rows is not None),
    }
    if saved_rows is not None:
        from pentaho_migration.reports.rpt_saved import build_inline_ds_xml
        docs["datasources/inline-ds.xml"] = build_inline_ds_xml(saved_rows)
    media = {name: "text/xml" for name in docs}
    for dirname, el, child in subreports:
        layout = (build_crosstab_layout_xml(child, el) if el.kind == "crosstab"
                  else build_layout_xml(child, root_type="sub-report"))
        child_docs = {
            f"{dirname}/content.xml": CONTENT_XML,
            f"{dirname}/layout.xml": layout,
            f"{dirname}/styles.xml": build_styles_xml(child),
            f"{dirname}/datadefinition.xml": build_datadefinition_xml(
                child, parameter_mappings=el.subreport_links),
            f"{dirname}/datasources/sql-ds.xml": build_sql_ds_xml(child),
            f"{dirname}/datasources/compound-ds.xml": build_compound_ds_xml(),
        }
        docs.update(child_docs)
        media.update({name: "text/xml" for name in child_docs})
        media[f"/{dirname}/"] = SUBREPORT_MIMETYPE  # marks the nested bundle
    for path, data in images.items():
        media[path] = "image/png" if path.endswith(".png") else "image/jpeg"
    manifest = build_manifest_xml(media)

    with zipfile.ZipFile(out_path, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        zf.writestr(info, MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/manifest.xml", manifest, compress_type=zipfile.ZIP_DEFLATED)
        for name, doc in docs.items():
            zf.writestr(name, doc, compress_type=zipfile.ZIP_DEFLATED)
        for path, data in images.items():
            zf.writestr(path, data, compress_type=zipfile.ZIP_DEFLATED)
    return out_path
