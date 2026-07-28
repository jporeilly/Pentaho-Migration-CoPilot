"""Recreate Crystal's group tree as PDF bookmarks (the outline panel).

The Crystal viewer's left-hand tree - countries, customers - is how people
navigate a long report. The converted report's PDF gets the same tree:
group values come from the EMBEDDED saved rows (in row order, so the outline
matches the rendered order), and each entry points at the first page whose
text carries that value. Pure post-processing - the render is untouched.

Needs pypdf (outline writing) and pypdfium2 (page text); both ship with the
[api] extra. Any failure returns the original bytes - a missing outline is
not worth failing a preview over.
"""

import io

MAX_OUTLINE_ENTRIES = 300   # a navigation aid, not a phone book


def _page_texts(pdf_bytes: bytes) -> list:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        return [page.get_textpage().get_text_bounded() for page in doc]
    finally:
        doc.close()


def add_group_outline(pdf_bytes: bytes, model) -> bytes:
    """Return the PDF with a nested group-tree outline, or the input bytes
    unchanged when there is nothing to build it from."""
    saved = getattr(model, "saved_rows", None)
    groups = [g.column for g in getattr(model, "groups", [])]
    if saved is None or not groups or not saved.rows:
        return pdf_bytes
    columns = [c[0] for c in saved.columns]
    indices = []
    for column in groups:
        if column not in columns:
            return pdf_bytes
        indices.append(columns.index(column))

    try:
        from pypdf import PdfReader, PdfWriter

        texts = _page_texts(pdf_bytes)
    except Exception:
        return pdf_bytes

    # group values in ROW order (the rendered order), nested outer -> inner
    seen = set()
    entries = []          # (level, value, search_text)
    for row in saved.rows:
        path = tuple(str(row[i]) for i in indices)
        for level in range(len(path)):
            key = path[:level + 1]
            if key in seen:
                continue
            seen.add(key)
            entries.append((level, path[level]))
            if len(entries) >= MAX_OUTLINE_ENTRIES:
                break
        if len(entries) >= MAX_OUTLINE_ENTRIES:
            break

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        writer.append(reader)
        parents = {}                 # level -> last outline node at that level
        cursor = 0                   # pages only move forward
        for level, value in entries:
            page_index = next(
                (i for i in range(cursor, len(texts)) if value in texts[i]),
                None)
            if page_index is None:   # not found ahead - look anywhere
                page_index = next(
                    (i for i, t in enumerate(texts) if value in t), None)
            if page_index is None:
                continue
            if level == 0:
                cursor = page_index
            node = writer.add_outline_item(
                str(value)[:80], page_index,
                parent=parents.get(level - 1))
            parents[level] = node
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return pdf_bytes
