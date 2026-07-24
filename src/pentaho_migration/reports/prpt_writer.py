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

NUMERIC_TYPES = {"NumberField", "CurrencyField", "IntegerField", "Int16sField",
                 "Int32sField", "Int64sField", "DecimalField"}
DATE_TYPES = {"DateField", "DateTimeField", "TimeField"}


def _num(v):
    return ("%g" % round(float(v), 2))


def _needs_page_function(model):
    return any(el.kind == "special" and el.column in ("pagenumber", "pagenofm", "totalpagecount")
               for s in model.sections for el in s.elements)


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
    the element defines them. PRD paints element backgrounds this way."""
    attrs = []
    if el.bg_color:
        attrs.append(f"background-color={quoteattr(el.bg_color)}")
    if el.border_width and el.border_color:
        attrs.append(f'border-width="{_num(el.border_width)}"')
        attrs.append(f"border-color={quoteattr(el.border_color)}")
        attrs.append('border-style="solid"')
    return f'<{sp}border-styles {" ".join(attrs)}/>' if attrs else ""


def _line_style(el, sp):
    return (f"<{sp}element-style>"
            f'<{sp}content-styles draw-shape="true" scale="true" color="#000000" '
            f'stroke-weight="0.5" stroke-style="solid"/>'
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


def render_element(el, tp="", sp="style:"):
    """Render one Element. tp/sp are tag prefixes for layout.xml vs styles.xml."""
    if el.kind == "label":
        return (f'<{tp}label core:element-type="label">{_style_block(el, sp)}'
                f"<core:value>{escape(el.text)}</core:value></{tp}label>")
    if el.kind == "line":
        return f'<{tp}horizontal-line core:element-type="horizontal-line">{_line_style(el, sp)}</{tp}horizontal-line>'
    if el.kind == "box":
        fill = el.bg_color or el.font.color
        stroke = el.border_color or "black"
        return (f'<{tp}rectangle core:element-type="rectangle" core:arc-width="0.0" core:arc-height="0.0">'
                f"<{sp}element-style>"
                f'<{sp}content-styles draw-shape="{str(bool(el.border_width)).lower()}" '
                f'fill-shape="{str(bool(el.bg_color)).lower()}" scale="true" '
                f'color={quoteattr(stroke)} fill-color={quoteattr(fill)} '
                f'stroke-weight="{_num(el.border_width or 1)}" stroke-style="solid"/>'
                f'<{sp}spatial-styles x="{_num(el.x)}" y="{_num(el.y)}" '
                f'min-width="{_num(el.width)}" min-height="{_num(el.height)}"/>'
                f"</{sp}element-style></{tp}rectangle>")
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
            fmt = _number_format(el.value_type)
            return (f'<{tp}number-field core:element-type="number-field" '
                    f"core:format-string={quoteattr(fmt)} core:field={quoteattr(el.column)}>"
                    f"{_style_block(el, sp)}</{tp}number-field>")
        if el.value_type in DATE_TYPES:
            fmt = _date_format(el.value_type)
            return (f'<{tp}date-field core:element-type="date-field" '
                    f"core:format-string={quoteattr(fmt)} core:field={quoteattr(el.column)}>"
                    f"{_style_block(el, sp)}</{tp}date-field>")
        return (f'<{tp}text-field core:element-type="text-field" core:field={quoteattr(el.column)}>'
                f"{_style_block(el, sp)}</{tp}text-field>")
    if el.kind == "subreport":
        return render_element(_todo_label(el, f"[TODO subreport: {el.text} - convert separately]"), tp, sp)
    if el.kind == "image":
        if el.image_bytes and el.resource_path:
            # a real embedded raster carried from the Crystal report
            key = ("resourcekey:org.pentaho.reporting.libraries.docbundle.bundleloader."
                   f"RepositoryResourceBundleLoader;{el.resource_path};")
            return (f'<{tp}content core:element-type="content">'
                    f"<{sp}element-style>"
                    f'<{sp}content-styles scale="true" keep-aspect-ratio="true"/>'
                    f'<{sp}spatial-styles x="{_num(el.x)}" y="{_num(el.y)}" '
                    f'min-width="{_num(el.width)}" min-height="{_num(el.height)}"/>'
                    f"</{sp}element-style>"
                    f'<core:value resource-type="resource-key">{escape(key)}</core:value>'
                    f"</{tp}content>")
        return render_element(_todo_label(el, "[TODO image: re-embed resource]"), tp, sp)
    return render_element(_todo_label(el, f"[TODO unsupported object: {el.text or el.kind}]"), tp, sp)


def _todo_label(el, text):
    from .model import Element, Font
    return Element(kind="label", x=el.x, y=el.y, width=el.width, height=el.height,
                   text=text, font=Font(size=8, italic=True, color="#cc0000"))


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
            f"{style}{content}</root-level-content>")


# ---------------------------------------------------------------- layout.xml

def build_layout_xml(model):
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
                f'core:group-fields={quoteattr(g.column)} core:name={quoteattr(g.name or ("Group" + str(i + 1)))}>'
                f"<fields><field>{escape(g.column)}</field></fields>"
                f"<group-header>{_root_band(headers, 'group-header')}</group-header>"
                f"{body}"
                f"<group-footer>{_root_band(footers, 'group-footer')}</group-footer>"
                f"</group>")
        # innermost: the data body with the detail band
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
        f'core:element-type="master-report" core:name={quoteattr(model.name)}>'
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
        f'<layout:page-header core:element-type="page-header">{_page_band_bg(ph_bg)}{ph_content}</layout:page-header>'
        f'<layout:page-footer core:element-type="page-footer">{_page_band_bg(pf_bg)}{pf_content}</layout:page-footer>'
        "</style>")


# ------------------------------------------------------- datadefinition.xml

def _parameter_xml(prm):
    """A Crystal parameter -> PRD parameter. Multi-value or pick-list (LOV)
    parameters become list-parameters; simple prompts stay plain textboxes.
    Optional Crystal prompts map to mandatory=false."""
    jtype = PARAM_TYPE_MAP.get(prm.value_type, "java.lang.String")
    mandatory = "false" if prm.optional else "true"
    label = (f'<attribute namespace="{NS_PARAM}" name="label">'
             f'{escape(prm.prompt or prm.name)}</attribute>')
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


def build_datadefinition_xml(model):
    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<data-definition xmlns="{NS_DATA}">']
    parts.append("<parameter-definition>")
    for prm in model.parameters:
        parts.append(_parameter_xml(prm))
    parts.append("</parameter-definition>")
    parts.append('<data-source report-query="default" limit="-1" timout="0" '
                 'ref="datasources/compound-ds.xml"/>')

    for f in model.formulas.values():
        if f.status in ("auto", "review") and f.translation:
            parts.append(f"<expression name={quoteattr(f.name)} formula={quoteattr(f.translation)}/>")

    for s in model.summaries:
        cls = SUMMARY_CLASS_MAP.get(s.operation)
        if not cls:
            continue
        from .rpt_parser import parse_field_ref
        _, column = parse_field_ref(s.field_ref)
        props = [f'<property name="field">{escape(column)}</property>']
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
        "</data:query-definitions>"
        "</data:sql-datasource>")


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

def write_prpt(model, out_path):
    images = _collect_images(model)  # assigns resource paths before layout is built
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
