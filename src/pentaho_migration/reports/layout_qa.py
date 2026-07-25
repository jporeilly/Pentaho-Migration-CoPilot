"""Layout QA agent: catch visual defects before anyone opens PRD.

Two layers, deterministic first:

1. lint_layout(model)  - geometry lint on the parsed report model: elements
   that overflow the printable page width (the classic masthead-wider-than-
   A4 defect), elements taller than their band, colliding fields, fonts too
   large for their box, charts missing their data columns, and TODO
   placeholders that will print as boxes.
2. render_qa(model, prpt) - proof from the real engine: render the bundle's
   design-time PDF, then verify the page count and that every band label
   actually made it onto the page (pypdf text extraction). Optional - needs
   a local PRD install; the lint alone needs nothing.

Findings feed the batch triage agent, the report-qa CLI, and the conversion
report. Severities: error (broken output), warning (probably wrong), info
(known manual work).
"""

from dataclasses import dataclass, field

# printable paper sizes in points (width, height), portrait orientation
PAPER_SIZES = {
    "LETTER": (612.0, 792.0),
    "LEGAL": (612.0, 1008.0),
    "A4": (595.0, 842.0),
}


@dataclass
class Finding:
    severity: str          # error | warning | info
    code: str              # page-overflow | band-overflow | overlap | ...
    band: str = ""
    element: str = ""
    message: str = ""


@dataclass
class LayoutQA:
    findings: list = field(default_factory=list)

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.severity == "warning"]


def usable_page_width(page) -> float:
    w, h = PAPER_SIZES.get(page.paper, PAPER_SIZES["LETTER"])
    if page.orientation == "landscape":
        w, h = h, w
    return w - page.margin_left - page.margin_right


def _band(section) -> str:
    if section.group_index >= 0:
        return f"{section.area_kind} G{section.group_index + 1}"
    return section.area_kind


def _label(el) -> str:
    return el.name or el.text or el.column or el.field_ref or el.kind


_CONTENT_KINDS = {"label", "field", "chart", "image", "special"}


_DEOVERLAP_GAP = 2.0  # points of clearance between nudged elements


def _movable_text(section):
    """Text elements safe to nudge apart: always-visible labels/fields.
    Anything with a visibility condition is exempt - Crystal designs stack
    mutually-exclusive fields in the same spot and show one at runtime."""
    return [el for el in section.elements
            if el.kind in ("label", "field", "special")
            and el.visible
            and not any(key == "visible" for key, _ in el.style_expressions)
            and not el.condition_formulas]


def _deoverlap_text(section):
    """Nudge overlapping always-visible text apart: the later element (by
    reading order) moves right or down, whichever displacement is smaller.
    Sweeps until stable; anything a sweep cap leaves stays lint-flagged."""
    moved = set()
    content = sorted(_movable_text(section), key=lambda e: (e.y, e.x))
    for _ in range(4):
        collided = False
        for i, a in enumerate(content):
            for b in content[i + 1:]:
                ox = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
                oy = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
                if ox <= 0 or oy <= 0:
                    continue
                smaller = min(a.width * a.height, b.width * b.height)
                if smaller <= 0 or (ox * oy) / smaller <= 0.4:
                    continue
                dx = a.x + a.width - b.x + _DEOVERLAP_GAP
                dy = a.y + a.height - b.y + _DEOVERLAP_GAP
                # keep visual structure: same-row neighbours spread RIGHT
                # (a row of columns stays a row), same-column stacks go DOWN
                same_row = oy >= 0.6 * min(a.height, b.height)
                stacked = abs(a.x - b.x) < 4.0
                if same_row and not stacked:
                    b.x = round(b.x + dx, 1)   # a row of columns stays a row
                elif stacked:
                    b.y = round(b.y + dy, 1)   # a stack becomes clean rows
                elif dx <= dy:
                    b.x = round(b.x + dx, 1)   # otherwise: minimal displacement
                else:
                    b.y = round(b.y + dy, 1)
                moved.add(id(b))
                collided = True
        if not collided:
            break
        content.sort(key=lambda e: (e.y, e.x))
    return len(moved)


_BACKDROP_RATIO = 1.5  # an image this much larger than overlapped content is a backdrop


def _is_backdrop_pair(img, other):
    """True when `img` acts as a backdrop for `other`: substantially larger
    and overlapping it (fade/watermark images behind text)."""
    if img.kind != "image":
        return False
    ox = min(img.x + img.width, other.x + other.width) - max(img.x, other.x)
    oy = min(img.y + img.height, other.y + other.height) - max(img.y, other.y)
    if ox <= 0 or oy <= 0:
        return False
    return img.width * img.height >= _BACKDROP_RATIO * max(other.width * other.height, 1.0)


def _promote_backdrops(section):
    """Move backdrop images to the FRONT of the band: PRD paints elements in
    document order, so first = behind - the fade renders under the text it
    overlaps, exactly the original design intent."""
    backdrops = []
    for el in section.elements:
        if el.kind != "image":
            continue
        if any(_is_backdrop_pair(el, other) for other in section.elements
               if other is not el and other.kind in ("label", "field", "special", "image")):
            backdrops.append(el)
    promoted = 0
    for el in backdrops:
        idx = section.elements.index(el)
        if any(o.kind != "image" for o in section.elements[:idx]):
            section.elements.remove(el)
            section.elements.insert(0, el)
            promoted += 1
    return promoted


def autofit_layout(model) -> int:
    """Deterministic layout repair for the mechanically-safe finding classes:

    - text overlaps: always-visible labels/fields that would print on top of
      each other are nudged apart (right or down, minimal displacement) -
      elements with a visibility condition are exempt (stacked alternates),
      and image/chart overlaps stay flagged (usually intentional watermarks);
    - page-overflow: a band whose content extends past the printable width
      has ALL its elements' x/width scaled proportionally to fit (runs after
      the de-overlap so nudges that pushed content wide are squeezed back);
    - font-clip: a text box shorter than its font grows to font size + 2pt,
      and the band grows with the content if needed.

    Each repair lands in model.issues for review. Returns repairs made."""
    width = usable_page_width(model.page)
    repaired = 0
    for section in model.sections:
        if section.suppressed:
            continue
        promoted = _promote_backdrops(section)
        if promoted:
            repaired += 1
            model.issues.append(
                f"layout auto-fit: {_band(section)} - {promoted} backdrop "
                "image(s) moved behind the content they overlap (paint order) "
                "- the fade/watermark renders under the text, as designed")
        nudged = _deoverlap_text(section)
        if nudged:
            repaired += 1
            model.issues.append(
                f"layout auto-fit: {_band(section)} - {nudged} overlapping text "
                "element(s) nudged apart (right/down, reading order kept) - "
                "verify against the original layout")
        extent = max((el.x + el.width for el in section.elements), default=0.0)
        if extent > width:
            factor = width / extent
            for el in section.elements:
                el.x = round(el.x * factor, 1)
                el.width = round(el.width * factor, 1)
            repaired += 1
            model.issues.append(
                f"layout auto-fit: {_band(section)} content ended at {extent:.0f}pt "
                f"but the printable width is {width:.0f}pt ({model.page.paper} "
                f"{model.page.orientation}) - every element in the band was scaled "
                f"by {factor:.2f} to fit; verify label wrapping (fonts unchanged)")
        grown = 0
        for el in section.elements:
            if (el.kind in ("label", "field") and el.font.size > 0
                    and el.height > 0 and el.font.size + 2 > el.height):
                el.height = round(el.font.size + 2, 1)
                grown += 1
        if grown:
            repaired += 1
            model.issues.append(
                f"layout auto-fit: {_band(section)} - {grown} text box(es) grown "
                "to fit their font (descenders would have clipped); verify "
                "nothing now touches the element below")
        if nudged or grown:
            bottom = max((el.y + el.height for el in section.elements), default=0.0)
            if bottom > section.height:
                section.height = round(bottom, 1)
    return repaired


def lint_layout(model) -> LayoutQA:
    """Deterministic geometry lint over every non-suppressed band."""
    qa = LayoutQA()
    page_width = usable_page_width(model.page)

    for section in model.sections:
        if section.suppressed:
            continue
        band = _band(section)
        visible = [el for el in section.elements if el.visible]

        for el in visible:
            if el.x < 0 or el.y < 0:
                qa.findings.append(Finding(
                    "error", "off-page", band, _label(el),
                    f"element starts at ({el.x}, {el.y}) - negative positions "
                    "land outside the printable area"))
            if el.x + el.width > page_width + 0.5:
                qa.findings.append(Finding(
                    "error", "page-overflow", band, _label(el),
                    f"element ends at {el.x + el.width:.0f}pt but the printable "
                    f"width is {page_width:.0f}pt ({model.page.paper} "
                    f"{model.page.orientation}) - it will clip or push a blank page"))
            if (el.y + el.height > section.height + 0.5
                    and not el.can_grow and el.kind in _CONTENT_KINDS):
                qa.findings.append(Finding(
                    "warning", "band-overflow", band, _label(el),
                    f"element bottom ({el.y + el.height:.0f}pt) exceeds the "
                    f"{section.height:.0f}pt band - PRD will clip it"))
            if (el.kind in ("label", "field") and el.font.size > 0
                    and el.height > 0 and el.font.size + 2 > el.height):
                qa.findings.append(Finding(
                    "warning", "font-clip", band, _label(el),
                    f"{el.font.size:.0f}pt text in a {el.height:.0f}pt box - "
                    "descenders will clip"))
            if el.kind == "chart" and not (el.chart_category and el.chart_value):
                qa.findings.append(Finding(
                    "error", "chart-columns", band, _label(el),
                    "chart is missing its category/value columns - it will "
                    "render empty"))
            if el.kind in ("subreport", "unknown"):
                qa.findings.append(Finding(
                    "info", "todo-placeholder", band, _label(el),
                    f"{el.kind} prints as a TODO placeholder - rebuild by hand"))

        # pairwise collision check between content elements
        content = [el for el in visible if el.kind in _CONTENT_KINDS]
        for i, a in enumerate(content):
            for b in content[i + 1:]:
                ox = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
                oy = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
                if ox <= 0 or oy <= 0:
                    continue
                # a backdrop image painting BEHIND the content it overlaps
                # (earlier in the band = under, in PRD paint order) is the
                # intentional fade/watermark pattern, not a defect
                if _is_backdrop_pair(a, b) or _is_backdrop_pair(b, a):
                    continue
                smaller = min(a.width * a.height, b.width * b.height)
                if smaller > 0 and (ox * oy) / smaller > 0.4:
                    qa.findings.append(Finding(
                        "warning", "overlap", band, _label(a),
                        f"overlaps '{_label(b)}' by more than 40% - "
                        "one of them will print on top of the other"))
    return qa


def render_qa(model, prpt_path) -> LayoutQA:
    """Engine ground truth: render the design-time PDF and verify every band
    label made it onto the page. Raises RuntimeError when no PRD install or
    pypdf is available - callers treat that as 'render check skipped'."""
    from pentaho_migration.reports.prpt_validator import render_prpt_pdf, validator_available

    if not validator_available():
        raise RuntimeError("render QA needs a local PRD install + Java")
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("render QA needs pypdf - `pip install pypdf`")

    qa = LayoutQA()
    pdf = render_prpt_pdf(prpt_path)
    reader = PdfReader(BytesIO(pdf))
    if not reader.pages:
        qa.findings.append(Finding(
            "error", "render-empty", message="engine produced a PDF with no pages"))
        return qa
    text = "".join(page.extract_text() or "" for page in reader.pages)
    flat = " ".join(text.split()).lower()

    for section in model.sections:
        if section.suppressed:
            continue
        for el in section.elements:
            if el.kind != "label" or not el.visible:
                continue
            expected = " ".join(el.text.split()).lower()
            if len(expected) >= 3 and expected not in flat:
                qa.findings.append(Finding(
                    "warning", "label-missing", _band(section), _label(el),
                    f"label text {el.text!r} did not appear in the rendered PDF"))
    return qa
