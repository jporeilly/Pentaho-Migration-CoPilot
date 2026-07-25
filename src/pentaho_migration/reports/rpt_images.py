"""Carve embedded pictures out of Crystal .rpt binaries and inject them into
RptToXml dumps as <ImageData> (base64 PNG) — so logos survive the migration.

Why carving: the free SAP .NET SDK cannot READ picture bytes. The RAS model
exposes `ISCRPictureObject.PictureData`, but it returns null in the embedded
(in-proc) RAS the free runtime uses — verified across the corpus with typed
access. Render-based harvesting (HTML export) needs the report's database,
which corpus/customer .rpt files rarely reach. What always works: the .rpt
file itself contains the raster bytes. This module signature-scans the OLE2
binary for PNG / JPEG / DIB blobs, proves each candidate by decoding it with
Pillow, converts to PNG, and matches blobs to the dump's PictureObjects by
aspect ratio (layout boxes may be stretched, so matching is greedy best-score,
and every injected image carries a verify note downstream).

Honesty rules: only decode-proven images are used; a PictureObject with no
plausible match keeps its TODO; report preview thumbnails (page-shaped DIBs
Crystal saves) simply never win a match.
"""

import base64
import io
import struct
from dataclasses import dataclass
from math import log
from xml.etree import ElementTree as ET

# layout boxes can be stretched vs the original raster; beyond this
# |ln(aspect ratio quotient)| a candidate is considered implausible
MAX_ASPECT_DISTANCE = 0.6
MIN_DIMENSION = 8  # px — anything smaller is scan noise


@dataclass
class CarvedImage:
    png: bytes
    width: int
    height: int
    bpp: int      # source bit depth (DIB) or 32 for PNG/JPEG originals
    kind: str     # png | jpeg | dib

    @property
    def aspect(self):
        return self.width / self.height if self.height else 0.0


def _try_decode(blob):
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
        return img
    except Exception:
        return None


def _to_png(img):
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def carve_rpt_images(path):
    """Signature-scan an .rpt (any binary, really) for embedded images.
    Returns decode-proven CarvedImages, deduplicated per (width, height)
    keeping the deepest bit-depth rendition (Crystal stores several)."""
    data = path.read_bytes()
    found: dict = {}

    def _keep(img, bpp, kind):
        if img.width < MIN_DIMENSION or img.height < MIN_DIMENSION:
            return
        key = (img.width, img.height)
        if key not in found or bpp > found[key].bpp:
            found[key] = CarvedImage(_to_png(img), img.width, img.height, bpp, kind)

    i = 0
    while (i := data.find(b"\x89PNG\r\n\x1a\n", i)) != -1:
        end = data.find(b"IEND", i)
        if end != -1 and (img := _try_decode(data[i:end + 8])) is not None:
            _keep(img, 32, "png")
        i += 8

    i = 0
    while (i := data.find(b"\xff\xd8\xff", i)) != -1:
        end = data.find(b"\xff\xd9", i + 3)
        if end != -1 and (img := _try_decode(data[i:end + 2])) is not None:
            _keep(img, 32, "jpeg")
        i += 3

    # DIB: BITMAPINFOHEADER (biSize=40), uncompressed - Crystal stores static
    # pictures this way. Prepend a BITMAPFILEHEADER so Pillow can read it.
    i = 0
    while (i := data.find(b"\x28\x00\x00\x00", i)) != -1:
        try:
            w, h = struct.unpack_from("<ii", data, i + 4)
            planes, bpp = struct.unpack_from("<HH", data, i + 12)
            compression = struct.unpack_from("<I", data, i + 16)[0]
        except struct.error:
            i += 4
            continue
        if (planes == 1 and compression == 0 and bpp in (1, 4, 8, 16, 24, 32)
                and 0 < w <= 5000 and 0 < abs(h) <= 5000):
            row = ((w * bpp + 31) // 32) * 4
            palette = (2 ** bpp) * 4 if bpp <= 8 else 0
            size = 40 + palette + row * abs(h)
            if i + size <= len(data):
                header = b"BM" + struct.pack("<IHHI", 14 + size, 0, 0, 14 + 40 + palette)
                if (img := _try_decode(header + data[i:i + size])) is not None:
                    _keep(img, bpp, "dib")
        i += 4
    return list(found.values())


def _aspect_distance(box_aspect, image):
    if box_aspect <= 0 or image.aspect <= 0:
        return float("inf")
    return abs(log(box_aspect / image.aspect))


def match_images(picture_boxes, images):
    """picture_boxes: [(key, width, height)] layout boxes (any unit — only the
    ratio is used). Returns {key: CarvedImage}. Greedy best-score per box;
    several boxes may share one image (a logo reused per band is normal).
    A single box with a single candidate matches unconditionally (the box may
    crop the raster, breaking the ratio)."""
    if not images:
        return {}
    if len(picture_boxes) == 1 and len(images) == 1:
        return {picture_boxes[0][0]: images[0]}
    matched = {}
    for key, w, h in picture_boxes:
        aspect = (w / h) if h else 0.0
        best = min(images, key=lambda img: _aspect_distance(aspect, img))
        if _aspect_distance(aspect, best) <= MAX_ASPECT_DISTANCE:
            matched[key] = best
    return matched


def enrich_dump(dump_path, rpt_path, out_path=None):
    """Inject carved images into an RptToXml dump's PictureObjects (in place
    unless out_path is given). Elements that already carry <ImageData> are
    left alone. Returns the number of images injected."""
    images = carve_rpt_images(rpt_path)
    tree = ET.parse(dump_path)
    pictures = [
        el for el in tree.getroot().iter("PictureObject")
        if el.find("ImageData") is None
    ]
    boxes = []
    for idx, el in enumerate(pictures):
        try:
            w = float(el.get("Width", "0"))
            h = float(el.get("Height", "0"))
        except ValueError:
            w = h = 0.0
        boxes.append((idx, w, h))
    assignments = match_images(boxes, images)
    for idx, image in assignments.items():
        data_el = ET.SubElement(pictures[idx], "ImageData")
        data_el.set("Carved", "true")  # parser adds a verify note downstream
        data_el.text = base64.b64encode(image.png).decode("ascii")
    if assignments:
        tree.write(out_path or dump_path, encoding="utf-8", xml_declaration=True)
    return len(assignments)
