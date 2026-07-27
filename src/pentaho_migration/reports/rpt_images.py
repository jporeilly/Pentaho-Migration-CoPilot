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

Read the STREAMS, not the file. An .rpt is an OLE compound file: a stream's
bytes are chained through 512-byte sectors that are not necessarily contiguous
on disk. Scanning raw file bytes therefore splices foreign sector data into any
image bigger than one sector — which decodes without complaint and renders as a
rolled or torn picture. So the scan runs per stream (embedded pictures live in
their own `Embedding N/CONTENTS`), and only falls back to the raw bytes when the
file is not a readable compound file.

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


def _carved_from_raw_bytes(path):
    """The pre-stream carve: scan the file as one flat blob. Kept as the
    fallback for anything that is not a compound file — and used by the tests
    to prove the sector splicing this module now avoids."""
    found: dict = {}
    _carve_blob(path.read_bytes(), found)
    return list(found.values())


def _streams(path):
    """The .rpt's compound-file streams, longest first (pictures are big).
    Falls back to the whole file when it is not a readable compound file, so
    loose dumps and test fixtures still work."""
    try:
        import olefile
    except ImportError:
        return [path.read_bytes()]
    try:
        if not olefile.isOleFile(str(path)):
            return [path.read_bytes()]
        with olefile.OleFileIO(str(path)) as ole:
            blobs = []
            for entry in ole.listdir():
                try:
                    blobs.append(ole.openstream(entry).read())
                except OSError:
                    continue
    except Exception:
        return [path.read_bytes()]
    blobs.sort(key=len, reverse=True)
    return blobs or [path.read_bytes()]


def carve_rpt_images(path):
    """Signature-scan an .rpt for embedded images. Returns decode-proven
    CarvedImages, deduplicated per (width, height) keeping the deepest
    bit-depth rendition (Crystal stores several)."""
    found: dict = {}
    for data in _streams(path):
        _carve_blob(data, found)
    return list(found.values())


def _carve_blob(data, found):

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


def _aspect_distance(box_aspect, image):
    if box_aspect <= 0 or image.aspect <= 0:
        return float("inf")
    return abs(log(box_aspect / image.aspect))


# Crystal places a picture at its natural size unless someone resizes it, and
# rasters are authored at 96 DPI, so box_points == pixels * 72/96. When a box
# lands within this many points of an image's natural size it is that image —
# a far stronger signal than the aspect ratio, which cannot tell a 2.14 logo
# from a 2.33 box.
PT_PER_PX = 72.0 / 96.0
NATURAL_SIZE_TOLERANCE_PT = 3.0


def _natural_size_distance(box_w_pt, box_h_pt, image):
    """Width is the axis to trust. A Crystal picture box routinely CROPS its
    raster vertically — a tall watermark shown as a band — but a box placed at
    natural size keeps the raster's full width. So match on width, and reject
    when the box is taller than the raster, which means it was stretched rather
    than placed."""
    natural_w = image.width * PT_PER_PX
    natural_h = image.height * PT_PER_PX
    if box_h_pt > natural_h + NATURAL_SIZE_TOLERANCE_PT:
        return float("inf")
    return abs(box_w_pt - natural_w)


def match_images(picture_boxes, images, boxes_in_points=False):
    """picture_boxes: [(key, width, height)] layout boxes. Returns
    {key: CarvedImage}.

    With `boxes_in_points` the natural-size test runs first: any box sitting
    within a few points of an image's own dimensions is that image, full stop.
    Whatever is left falls back to aspect ratio.

    Either way, confident pairs claim each other first, so a distinct image is
    never spent twice while another image is still unused — three logos in a
    report come out as three logos, not the best-matching one repeated. Only
    once the images run out may the remainder reuse one, which is the honest
    reading of a report that repeats a logo per band. A single box with a
    single candidate matches unconditionally (the box may crop the raster,
    breaking the ratio)."""
    if not images:
        return {}
    if len(picture_boxes) == 1 and len(images) == 1:
        return {picture_boxes[0][0]: images[0]}

    claimed_boxes, claimed_images, matched = set(), set(), {}
    if boxes_in_points:
        exact = sorted(
            (_natural_size_distance(w, h, img), bi, ii)
            for bi, (_key, w, h) in enumerate(picture_boxes)
            for ii, img in enumerate(images))
        for distance, bi, ii in exact:
            if distance > NATURAL_SIZE_TOLERANCE_PT:
                break
            if bi in claimed_boxes or ii in claimed_images:
                continue
            matched[picture_boxes[bi][0]] = images[ii]
            claimed_boxes.add(bi)
            claimed_images.add(ii)

    scored = sorted(
        (_aspect_distance((w / h) if h else 0.0, img), bi, ii)
        for bi, (_key, w, h) in enumerate(picture_boxes)
        for ii, img in enumerate(images)
        if bi not in claimed_boxes and ii not in claimed_images)
    taken_boxes, taken_images = set(claimed_boxes), set(claimed_images)
    for distance, bi, ii in scored:
        if distance > MAX_ASPECT_DISTANCE:
            break
        if bi in taken_boxes or ii in taken_images:
            continue
        matched[picture_boxes[bi][0]] = images[ii]
        taken_boxes.add(bi)
        taken_images.add(ii)

    # images exhausted but boxes left over — now reuse is the right answer
    for distance, bi, ii in scored:
        if distance > MAX_ASPECT_DISTANCE:
            break
        if bi not in taken_boxes:
            matched[picture_boxes[bi][0]] = images[ii]
            taken_boxes.add(bi)
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
    # RptToXml writes geometry in twips; points let the natural-size test work
    boxes = []
    for idx, el in enumerate(pictures):
        try:
            w = float(el.get("Width", "0")) / 20.0
            h = float(el.get("Height", "0")) / 20.0
        except ValueError:
            w = h = 0.0
        boxes.append((idx, w, h))
    assignments = match_images(boxes, images, boxes_in_points=True)
    for idx, image in assignments.items():
        data_el = ET.SubElement(pictures[idx], "ImageData")
        data_el.set("Carved", "true")  # parser adds a verify note downstream
        data_el.text = base64.b64encode(image.png).decode("ascii")
    if assignments:
        tree.write(out_path or dump_path, encoding="utf-8", xml_declaration=True)
    return len(assignments)
