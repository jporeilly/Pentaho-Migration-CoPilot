"""Element and style rendering for the .prpt layout — the "how one Crystal
object becomes one PRD element" layer, split from prpt_writer.py so the
formatting/rendering concern has its own home.
"""

from xml.sax.saxutils import escape, quoteattr

NUMERIC_TYPES = {"NumberField", "CurrencyField", "IntegerField", "Int16sField",
                 "Int32sField", "Int64sField", "DecimalField"}
DATE_TYPES = {"DateField", "DateTimeField", "TimeField"}


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
            fmt = el.format_string or _number_format(el.value_type)
            return (f'<{tp}number-field core:element-type="number-field" '
                    f"core:format-string={quoteattr(fmt)} core:field={quoteattr(el.column)}>"
                    f"{_style_block(el, sp)}</{tp}number-field>")
        if el.value_type in DATE_TYPES:
            fmt = el.format_string or _date_format(el.value_type)
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


