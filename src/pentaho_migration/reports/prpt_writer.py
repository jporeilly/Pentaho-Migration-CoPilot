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

from pentaho_migration.reports.model import SUMMARY_CLASS_MAP
from pentaho_migration.reports.prpt_render import _num, render_element


def _needs_page_function(model):
    return any(el.kind == "special" and el.column in ("pagenumber", "pagenofm", "totalpagecount")
               for s in model.sections for el in s.elements)


def _band_content(sections, band_type, tp="", sp="style:"):
    """Merge one or more Crystal sections of an area into a single PRD band.
    Returns (inner_xml, height, bg_color) — the first styled section supplies
    the band background."""
    inner, y_offset, bg = [], 0.0, ""
    for section in sections:
        if section.suppressed:
            continue
        if section.bg_color and not bg:
            bg = section.bg_color
        for el in section.elements:
            if y_offset:
                el = _shifted(el, y_offset)
            inner.append(render_element(el, tp, sp))
        y_offset += section.height
    height = max(y_offset, 20.0)
    return "".join(inner), height, bg


def _shifted(el, dy):
    import copy
    el2 = copy.copy(el)
    el2.y = el.y + dy
    return el2


def _band_style_expressions(sections):
    """Section-level conditional formatting (suppress condition, background)
    as band style-expressions. The parser only converts these when the
    section is alone in its band, so emitting them all here is safe."""
    return "".join(
        f"<style-expression style-key={quoteattr(key)} formula={quoteattr(formula)}/>"
        for section in sections
        for key, formula in section.style_expressions)


def _root_band(sections, element_type):
    content, height, bg = _band_content(sections, element_type)
    style = ""
    if bg:
        style = ("<style:element-style>"
                 f'<style:border-styles background-color={quoteattr(bg)}/>'
                 "</style:element-style>")
    return (f'<root-level-content core:element-type="{element_type}" '
            f'xmlns:report-designer="http://reporting.pentaho.org/namespaces/report-designer/2.0" '
            f'report-designer:visual-height="{_num(height)}">'
            f"{style}{_band_style_expressions(sections)}{content}</root-level-content>")


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
                f"<group-header>{_root_band(headers, 'group-header')}</group-header>"
                f"{body}"
                f"<group-footer>{_root_band(footers, 'group-footer')}</group-footer>"
                f"</group>")
        # innermost: the data body with the detail band. Crystal's PageHeader
        # becomes a REPEATING details-header: Crystal prints page 1 as
        # ReportHeader then PageHeader, but PRD's physical page-header always
        # tops the page — a repeating details-header renders below the
        # masthead on page 1 and repeats on continuation pages, matching what
        # Crystal users expect (this is also how PRD's own samples do column
        # labels).
        details = model.sections_of("Detail")
        ph_content, ph_height, ph_bg = _band_content(model.sections_of("PageHeader"), "details-header")
        ph_style = ("<style:element-style>"
                    '<style:page-band-styles repeat="true"/>'
                    + (f'<style:border-styles background-color={quoteattr(ph_bg)}/>' if ph_bg else "")
                    + "</style:element-style>") if ph_content else ""
        details_header = (
            f'<details-header core:element-type="details-header" '
            f'xmlns:report-designer="http://reporting.pentaho.org/namespaces/report-designer/2.0" '
            f'report-designer:visual-height="{_num(ph_height)}">{ph_style}{ph_content}</details-header>'
            if ph_content else '<details-header core:element-type="details-header"/>')
        return (
            '<data-body core:element-type="group-data-body">'
            f"{details_header}"
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


# ---------------------------------------------------------------- styles.xml

def _page_band_bg(bg):
    return (f'<element-style><border-styles background-color={quoteattr(bg)}/></element-style>'
            if bg else "")


def build_styles_xml(model):
    # Crystal's PageHeader lives in the layout as a repeating details-header
    # (see build_layout_xml); only the PageFooter maps to the physical page
    # band, whose bottom-of-every-page semantics match Crystal's.
    p = model.page
    pf_content, _, pf_bg = _band_content(model.sections_of("PageFooter"), "page-footer", tp="layout:", sp="")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<style xmlns="{NS_STYLE}" xmlns:layout="{NS_LAYOUT}" xmlns:core="{NS_CORE}">'
        f'<page-definition horizontal-span="1" vertical-span="1" pageformat={quoteattr(p.paper)} '
        f'orientation={quoteattr(p.orientation)} margin-top="{_num(p.margin_top)}" '
        f'margin-left="{_num(p.margin_left)}" margin-bottom="{_num(p.margin_bottom)}" '
        f'margin-right="{_num(p.margin_right)}"/>'
        '<layout:watermark core:element-type="watermark"></layout:watermark>'
        '<layout:page-header core:element-type="page-header"></layout:page-header>'
        f'<layout:page-footer core:element-type="page-footer">{_page_band_bg(pf_bg)}{pf_content}</layout:page-footer>'
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
        cls = SUMMARY_CLASS_MAP.get(s.operation)
        if not cls:
            continue
        from .rpt_parser import parse_field_ref
        _, column = parse_field_ref(s.field_ref)
        props = ([] if _is_fieldless(cls)
                 else [f'<property name="field">{escape(column)}</property>'])
        if s.group_field:
            props.append(f'<property name="group">{escape(s.group_field)}</property>')
        parts.append(f"<expression name={quoteattr(s.expression_name)} class=\"{cls}\">"
                     f"<properties>{''.join(props)}</properties></expression>")

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

def build_sql_ds_xml(model):
    return (
        f'<data:sql-datasource xmlns:data="{NS_SQL}">'
        "<data:config/>"
        f"<data:jndi><data:path>{escape(model.jndi)}</data:path></data:jndi>"
        "<data:query-definitions>"
        '<data:query name="default"><data:static-query>'
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


def build_compound_ds_xml():
    return (f'<data:compound-datasource xmlns:data="{NS_COMPOUND}">'
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


def build_meta_xml(model):
    from pentaho_migration import __version__
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
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
    [(dirname, element)]."""
    subs, idx = [], 0
    for section in model.sections:
        for el in section.elements:
            if el.kind == "subreport" and el.subreport is not None:
                dirname = "subreport" if idx == 0 else f"subreport-{idx}"
                el.subreport_href = f"/{dirname}/content.xml"
                subs.append((dirname, el))
                idx += 1
    return subs


def write_prpt(model, out_path):
    images = _collect_images(model)  # assigns resource paths before layout is built
    subreports = _collect_subreports(model)  # assigns hrefs before layout is built
    docs = {
        "content.xml": CONTENT_XML,
        "layout.xml": build_layout_xml(model),
        "styles.xml": build_styles_xml(model),
        "datadefinition.xml": build_datadefinition_xml(model),
        "dataschema.xml": DATASCHEMA_XML,
        "settings.xml": SETTINGS_XML,
        "meta.xml": build_meta_xml(model),
        "datasources/sql-ds.xml": build_sql_ds_xml(model),
        "datasources/compound-ds.xml": build_compound_ds_xml(),
    }
    media = {name: "text/xml" for name in docs}
    for dirname, el in subreports:
        child = el.subreport
        child_docs = {
            f"{dirname}/content.xml": CONTENT_XML,
            f"{dirname}/layout.xml": build_layout_xml(child, root_type="sub-report"),
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
