"""Look at the two renders, not just read them.

The rest of the gate compares EXTRACTED TEXT - page counts, numbers, lines,
group spans. That misses everything the eye notices first: a background panel
that vanished, a rule drawn where the original has none, a total box that
lost its fill. All of those leave the text identical, so the gate reported
SHIP through a whole afternoon of real visual defects.

This adds the missing dimension. Two problems have to be solved for it to be
worth anything:

**Pages do not correspond.** The demo statement renders 74 pages from Crystal
and 58 from Pentaho, so page N against page N would flag everything. Pages
are PAIRED BY CONTENT first - each converted page is matched to the original
page whose normalized text overlaps it most - and only confident pairs are
compared.

**Two engines never rasterize identically.** Font hinting, kerning and
antialiasing differ on every glyph, so a pixel-exact comparison is noise.
Each page is reduced to a coarse grid of ink-density cells; a cell has to
change substantially before it counts. That is deliberately blind to text
shifting a fraction of a millimetre and loud about a panel disappearing.
"""

# Rasterization is cheap at this size and the grid is what does the work.
RENDER_SCALE = 0.5            # ~36 dpi: enough for regions, not for glyphs
GRID_COLS, GRID_ROWS = 16, 22  # ~A4 proportions
# Set from the two cases that have to be separated, not by taste. A pale
# background panel - the beige letter block the statement lost - is about
# 0.06 of ink density once greyscaled; a shape shifting a couple of points
# between engines moves an edge cell by about 0.026. Anything between the two
# divides them; 0.04 sits in the middle.
CELL_TOLERANCE = 0.04          # ink-density change before a cell counts
PAGE_TOLERANCE = 0.06          # fraction of cells differing before a page does
# EVERY pairable page. A sample cannot see the page it did not look at, and
# the defects this exists to catch - an orphaned total, a panel missing from
# one statement - live on specific pages. Rasterizing at RENDER_SCALE is
# cheap: a 58-page report is well under a second of the gate's two minutes.
# The cap is a runaway guard for a report of thousands of pages, not a
# sampling strategy, and whatever it drops is reported.
MAX_PAGES_COMPARED = 2000
MIN_TEXT_OVERLAP = 0.4         # below this two pages are not the same page


def _grid(image):
    """A page as GRID_ROWS x GRID_COLS ink densities in 0..1.

    Ink density, not colour: a region that loses a pale background panel and
    a region that loses black text both register, and neither depends on the
    two engines agreeing about a shade."""
    gray = image.convert("L").resize((GRID_COLS, GRID_ROWS))
    # get_flattened_data() on Pillow 11+, getdata() before it
    pixels = (gray.get_flattened_data() if hasattr(gray, "get_flattened_data")
              else gray.getdata())
    return [1.0 - (p / 255.0) for p in pixels]


def _page_grids(pdf_bytes, indices):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        return {i: _grid(doc[i].render(scale=RENDER_SCALE).to_pil())
                for i in indices if 0 <= i < len(doc)}
    finally:
        doc.close()


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def pair_pages(orig_lines: list, conv_lines: list) -> list:
    """(original index, converted index) for pages that are the same page.

    Matching is by normalized-text overlap and is monotonic: a converted page
    is only matched forward of the previous match, so a repeated page
    furniture line cannot pair page 50 with page 2."""
    pairs = []
    start = 0
    for ci, conv in enumerate(conv_lines):
        best, best_score = -1, 0.0
        for oi in range(start, len(orig_lines)):
            score = _overlap(conv, orig_lines[oi])
            if score > best_score:
                best, best_score = oi, score
            if score == 1.0:
                break
        if best >= 0 and best_score >= MIN_TEXT_OVERLAP:
            pairs.append((best, ci))
            start = best
    return pairs


def _sample(pairs, cap=MAX_PAGES_COMPARED):
    if len(pairs) <= cap:
        return pairs
    step = len(pairs) / cap
    return [pairs[int(i * step)] for i in range(cap)]


def compare_visually(original_pdf: bytes, converted_pdf: bytes,
                     orig_lines: list, conv_lines: list) -> dict:
    """{'compared': n, 'available': n, 'pages': [(orig, conv, fraction,
    where)]} - the pages whose appearance differs, worst first.

    Returns an empty 'pages' list when the two renders look the same, and
    when the comparison could not run at all (no Pillow, no pairable pages):
    a gate that cannot see is not evidence of a defect, and 'available' says
    which case it was."""
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        return {"compared": 0, "available": 0, "pages": []}

    pairs = pair_pages(orig_lines, conv_lines)
    sampled = _sample(pairs)
    if not sampled:
        return {"compared": 0, "available": 0, "pages": []}

    try:
        og = _page_grids(original_pdf, [o for o, _ in sampled])
        cg = _page_grids(converted_pdf, [c for _, c in sampled])
    except Exception:
        return {"compared": 0, "available": 0, "pages": []}

    differing = []
    for oi, ci in sampled:
        a, b = og.get(oi), cg.get(ci)
        if a is None or b is None:
            continue
        changed = [n for n, (x, y) in enumerate(zip(a, b))
                   if abs(x - y) > CELL_TOLERANCE]
        fraction = len(changed) / (GRID_COLS * GRID_ROWS)
        if fraction > PAGE_TOLERANCE:
            differing.append((oi, ci, fraction, _describe(changed, a, b)))
    differing.sort(key=lambda d: -d[2])
    return {"compared": len(sampled), "available": len(pairs),
            "pages": differing}


def _describe(changed, a, b) -> str:
    """Where on the page, and which way - said the way someone looking at
    the two pages side by side would say it."""
    if not changed:
        return ""
    rows = [n // GRID_COLS for n in changed]
    band = sum(rows) / len(rows) / GRID_ROWS
    where = ("top" if band < 0.33 else
             "middle" if band < 0.66 else "bottom")
    lost = sum(1 for n in changed if a[n] > b[n])
    if lost > len(changed) * 0.75:
        what = "the conversion is missing something the original prints"
    elif lost < len(changed) * 0.25:
        what = "the conversion prints something the original does not"
    else:
        what = "content differs"
    return f"{where} of the page - {what}"
