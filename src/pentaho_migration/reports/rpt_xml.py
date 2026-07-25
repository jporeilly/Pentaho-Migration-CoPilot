"""Low-level RptToXml helpers: fork-tolerant attribute access and the
formatting readers (colours, borders, fonts) shared by the parser.

Kept separate from rpt_parser.py so the formatting-extraction concern — the
part most affected by any RptToXml improvement — has one home.
"""

from .model import TWIPS_PER_POINT, Font


# ---------------------------------------------------------------- attributes

def _attr(node, *names, default=""):
    for n in names:
        if n in node.attrib:
            return node.attrib[n]
    return default


def _twips(node, *names, default=0.0):
    raw = _attr(node, *names, default="")
    try:
        return float(raw) / TWIPS_PER_POINT
    except ValueError:
        return default


def _text_of(node, *child_names):
    """Text content from an attribute-or-child-element, fork-tolerantly."""
    for name in child_names:
        if name in node.attrib:
            return node.attrib[name]
        child = node.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return (node.text or "").strip()


def _local(tag):
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------- colours

def _argb_to_hex(node):
    """RptToXml dumps colours as <Color/BackgroundColor/... A R G B> children.
    Return #rrggbb, or "" when fully transparent / absent."""
    if node is None:
        return ""
    try:
        a = int(_attr(node, "A", default="255"))
        r = int(_attr(node, "R", default="0"))
        g = int(_attr(node, "G", default="0"))
        b = int(_attr(node, "B", default="0"))
    except ValueError:
        return ""
    if a == 0:
        return ""  # transparent -> no fill
    return f"#{r:02x}{g:02x}{b:02x}"


def _find_color(obj, tag_name):
    """First colour child with exactly this local tag name in the subtree
    (exact match so 'Color' does not catch 'BackgroundColor'/'BorderColor')."""
    for child in obj.iter():
        if _local(child.tag) == tag_name:
            hexval = _argb_to_hex(child)
            if hexval:
                return hexval
    return ""


# ---------------------------------------------------------------- border

LINE_STYLE_ATTRS = ("TopLineStyle", "BottomLineStyle", "LeftLineStyle", "RightLineStyle")


def _parse_border(obj):
    """(border_color, border_width, sides) from an object's <Border> child.
    Crystal borders are per-side (a column-header label typically has ONLY a
    bottom rule); sides is the tuple of lowercase side names that actually
    carry a line ('top', 'bottom', 'left', 'right') so the writer can emit
    per-edge borders instead of boxing every element."""
    border = None
    for child in obj.iter():
        if child.tag.endswith("Border"):
            border = child
            break
    if border is None:
        return "", 0.0, ()
    sides = tuple(
        a[: -len("LineStyle")].lower()
        for a in LINE_STYLE_ATTRS
        if _attr(border, a, default="NoLine") not in ("NoLine", "", "0")
    )
    if not sides:
        return "", 0.0, ()
    color = _find_color(border, "BorderColor") or "#000000"
    return color, 1.0, sides


# ---------------------------------------------------------------- font

def _parse_font(obj):
    font = Font()
    fnode = obj.find("Font")
    src = fnode if fnode is not None else obj
    name = _attr(src, "FontName", "Name", "FontFamily", default="")
    if name and src is not obj:
        font.name = name
    try:
        font.size = float(_attr(src, "Size", "PointSize", default="10") or 10)
    except ValueError:
        pass
    font.bold = _attr(src, "Bold", default="false").lower() in ("true", "1") or \
        "bold" in _attr(src, "Style", default="").lower()
    font.italic = _attr(src, "Italic", default="false").lower() in ("true", "1")
    font.underline = _attr(src, "Underline", default="false").lower() in ("true", "1")
    color = _attr(obj, "Color", "FontColor", default="") or _attr(src, "Color", default="")
    if color.startswith("#"):
        font.color = color
    else:
        # real RptToXml dumps the font colour as a <Color A R G B> child of the
        # object (a sibling of <Font>), so search the object, not the font node
        nested = _find_color(obj, "Color")
        if nested:
            font.color = nested
    return font


ALIGN_MAP = {
    "leftalign": "left", "rightalign": "right",
    "horizontalcenteralign": "center", "justified": "justify",
    "left": "left", "right": "right", "center": "center",
}
