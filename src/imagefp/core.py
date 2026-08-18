"""imagefp.core — decide whether two images are the same picture.

A pair evaluator: hand it two image byte streams (and their part names, so it
can tell a raster from a metafile) and it answers match / no-match. Rasters are
compared by a trimmed 16x16 thumbnail with a separate ink mask (so a logo
flattened onto white still matches its transparent original) and an aspect
guard; metafiles by their drawing-record signature. It biases to "different"
whenever it cannot decode, so it never claims two pictures are the same when
they might not be.
"""

from __future__ import annotations

import hashlib
import io
import math
import struct
from pathlib import Path

try:
    from PIL import Image, ImageChops
    from PIL.Image import Image as PILImage

    _RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    Image = ImageChops = None  # type: ignore[assignment]
    PILImage = object  # type: ignore[assignment,misc]
    _RESAMPLE = None
    _PIL_AVAILABLE = False

RASTER_EXTS = {".png", ".jpg", ".jpeg", ".jfif", ".gif", ".bmp", ".dib",
               ".tif", ".tiff", ".webp", ".ico"}
METAFILE_EXTS = {".emf", ".wmf"}

MAX_PIXELS = 50_000_000        # decode-bomb guard
THUMB = 16                     # 16x16 comparison grid
TRIM_TOL = 8                   # alpha below this is blank (trim)
TRIM_TOL_COLOUR = 26           # colour delta from the border that counts as ink
DEFAULT_SHAPE_DIST = 30.0      # mean abs difference of the ink masks
DEFAULT_THUMB_DIST = 18.0      # mean abs channel difference over co-inked cells
DEFAULT_INK_FLOOR = 200        # cells below this are edge/antialiasing
DEFAULT_ASPECT_TOL = 0.11      # |log(a/b)| aspect ratio tolerance
_COMPOSITE_BG = (255, 255, 255)  # flatten alpha onto white, as PowerPoint does


def kind(name: str) -> str:
    """Classify a file by extension as ``"raster"``, ``"metafile"``, or ``"other"``."""
    ext = Path(name).suffix.lower()
    if ext in RASTER_EXTS:
        return "raster"
    if ext in METAFILE_EXTS:
        return "metafile"
    return "other"


# --------------------------------------------------------------------------
# raster descriptor + comparison
# --------------------------------------------------------------------------

def _require_pillow() -> None:
    if not _PIL_AVAILABLE:
        raise RuntimeError(
            "Pillow is required for raster image comparison. "
            "Install it with: pip install imagefp[raster]  (or: pip install Pillow)"
        )


def _open(data: bytes) -> PILImage:
    """Decode to RGB/RGBA, or raise. Palette/greyscale/CMYK/16-bit fold into
    RGB so pixel identity means visual identity; a fully-opaque alpha channel
    is dropped (PowerPoint re-saves such images as RGB)."""
    _require_pillow()
    im: "PILImage" = Image.open(io.BytesIO(data))
    w, h = im.size
    if w <= 0 or h <= 0 or w * h > MAX_PIXELS:
        raise ValueError(f"{w}x{h} outside decode limits")
    has_alpha = im.mode in ("RGBA", "LA", "PA") or (
        im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if has_alpha else "RGB")
    im.load()
    if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] == 255:
        im = im.convert("RGB")
    return im


def _content_box(im: PILImage) -> tuple[int, int, int, int]:
    """Bounding box of non-blank content, so padding does not defeat the match
    and aspect ratio is measured on the artwork rather than the canvas."""
    if im.mode == "RGBA":
        bbox = im.getchannel("A").point(
            lambda v: 255 if v > TRIM_TOL else 0).getbbox()
        if bbox:
            return bbox
    rgb = im.convert("RGB")
    diff = ImageChops.difference(
        rgb, Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))).convert("L")
    return diff.point(lambda v: 255 if v > TRIM_TOL_COLOUR else 0).getbbox() \
        or (0, 0, im.size[0], im.size[1])


class Descriptor:
    """A 16x16 colour thumbnail, a 16x16 ink mask, and the artwork aspect."""

    __slots__ = ("thumb", "ink", "aspect")

    def __init__(self, thumb: bytes, ink: bytes, aspect: float) -> None:
        self.thumb = thumb
        self.ink = ink
        self.aspect = aspect

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return (f"Descriptor(aspect={self.aspect:.3f}, "
                f"thumb_len={len(self.thumb)}, ink_len={len(self.ink)})")


def describe(data: bytes) -> Descriptor:
    """Descriptor for one image, or raise if the bytes are not a raster.

    The ink mask (where the image has content, from alpha or from distance to
    the border colour) is what survives flattening: a transparent-background
    logo and the same logo composited onto white share an ink mask, so colour
    can be compared only where both actually have ink.
    """
    im = _open(data)
    box = _content_box(im)
    if im.mode == "RGBA":
        ink_uncropped = im.getchannel("A")
    else:
        rgb = im.convert("RGB")
        ink_uncropped = ImageChops.difference(
            rgb, Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
        ).convert("L").point(lambda v: 255 if v > TRIM_TOL_COLOUR else 0)

    cropped = im.crop(box)
    ink_full = ink_uncropped.crop(box)
    cw, ch = max(1, cropped.size[0]), max(1, cropped.size[1])

    if cropped.mode == "RGBA":
        bg = Image.new("RGB", cropped.size, _COMPOSITE_BG)
        bg.paste(cropped, mask=cropped.getchannel("A"))
        cropped = bg
    else:
        cropped = cropped.convert("RGB")

    thumb = cropped.resize((THUMB, THUMB), _RESAMPLE).tobytes()
    ink = ink_full.resize((THUMB, THUMB), _RESAMPLE).tobytes()
    return Descriptor(thumb, ink, cw / ch)


def thumb_distance(a: bytes, b: bytes) -> float:
    """Mean absolute byte difference between two equal-length colour thumbnails."""
    if len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


def shape_distance(a: Descriptor, b: Descriptor) -> float:
    """Mean absolute difference between two descriptors' ink masks."""
    if len(a.ink) != len(b.ink):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a.ink, b.ink)) / float(len(a.ink))


def colour_distance(a: Descriptor, b: Descriptor,
                     ink_floor: int = DEFAULT_INK_FLOOR, min_cells: int = 6) -> float:
    """Colour distance over cells where both images carry ink; falls back to
    the whole tile when the overlap is too small to be meaningful."""
    cells = [i for i in range(THUMB * THUMB)
             if a.ink[i] > ink_floor and b.ink[i] > ink_floor]
    if len(cells) < min_cells:
        return thumb_distance(a.thumb, b.thumb)
    total = 0
    for i in cells:
        j = i * 3
        total += (abs(a.thumb[j] - b.thumb[j])
                  + abs(a.thumb[j + 1] - b.thumb[j + 1])
                  + abs(a.thumb[j + 2] - b.thumb[j + 2]))
    return total / float(len(cells) * 3)


def same_image(a: Descriptor, b: Descriptor,
                thumb_dist: float = DEFAULT_THUMB_DIST,
                aspect_tol: float = DEFAULT_ASPECT_TOL,
                shape_tol: float = DEFAULT_SHAPE_DIST) -> bool:
    """Aspect guard (square thumbnails destroy aspect, so a banner and an icon
    of the same art would otherwise collide), then shape, then colour judged
    only where both have ink."""
    if abs(math.log(a.aspect / b.aspect)) > aspect_tol:
        return False
    if shape_distance(a, b) > shape_tol:
        return False
    return colour_distance(a, b) <= thumb_dist


# --------------------------------------------------------------------------
# metafile signature
# --------------------------------------------------------------------------

# EMR_HEADER(1) carries size-dependent bounds; EMR_COMMENT(70) is where EMF+
# and add-in per-instance blobs live. Both are excluded so the same chart at a
# different size or re-saved still matches. A resize that rewrites drawing
# coordinates is NOT survived -- that needs a raster replay, out of scope here.
_EMF_SKIP_PAYLOAD = {1, 70}


def emf_signature(data: bytes, max_records: int = 200_000) -> str | None:
    """Drawing-record signature of an EMF, or None if it is not a parseable
    EMF (WMF and truncated files return None)."""
    if len(data) < 88 or data[:4] != b"\x01\x00\x00\x00":
        return None
    h = hashlib.sha256()
    off, n, end = 0, 0, len(data)
    while off + 8 <= end and n < max_records:
        rtype, rsize = struct.unpack_from("<II", data, off)
        if rsize < 8 or off + rsize > end:
            break
        h.update(struct.pack("<I", rtype))
        if rtype not in _EMF_SKIP_PAYLOAD:
            h.update(data[off + 8:off + rsize])
        off += rsize
        n += 1
        if rtype == 14:                       # EMR_EOF
            break
    return h.hexdigest()[:24]


# --------------------------------------------------------------------------
# the one entry point: does this pair depict the same picture?
# --------------------------------------------------------------------------

def images_match(data_a: bytes | None, name_a: str | None,
                  data_b: bytes | None, name_b: str | None,
                  shape: float = DEFAULT_SHAPE_DIST,
                  thumb: float = DEFAULT_THUMB_DIST,
                  aspect: float = DEFAULT_ASPECT_TOL) -> tuple[bool, str]:
    """Decide whether two image parts depict the same picture.

    Raster vs raster is a perceptual match; metafile vs metafile compares
    drawing signatures; anything undecodable or mismatched in kind is reported
    as different, never silently the same.

    :param data_a: Raw bytes of the first image, or ``None`` if unavailable.
    :param name_a: File/part name for the first image (used only for its extension).
    :param data_b: Raw bytes of the second image, or ``None`` if unavailable.
    :param name_b: File/part name for the second image (used only for its extension).
    :param shape: Max mean ink-mask difference to still count as a match.
    :param thumb: Max mean masked colour difference to still count as a match.
    :param aspect: Max ``|log(aspect_a / aspect_b)|`` to still count as a match.
    :return: ``(match, reason)`` — ``reason`` is a human-readable explanation.
    """
    if data_a is None or data_b is None:
        return False, "image bytes unavailable (linked/external or missing)"
    ka, kb = kind(name_a or ""), kind(name_b or "")

    if ka == "metafile" and kb == "metafile":
        sa, sb = emf_signature(data_a), emf_signature(data_b)
        if sa is None or sb is None:
            return False, "metafile unreadable (WMF or truncated)"
        if sa == sb:
            return True, "same metafile drawing"
        return False, "metafile drawing differs (resize or edit)"
    if ka == "metafile" or kb == "metafile":
        return False, "different media kind (raster vs metafile)"

    try:
        a, b = describe(data_a), describe(data_b)
    except Exception as exc:                            # noqa: BLE001
        return False, f"undecodable ({type(exc).__name__})"

    match = bool(same_image(a, b, thumb, aspect, shape))
    detail = (f"shape {shape_distance(a, b):.0f}/{shape:.0f}, "
              f"colour {colour_distance(a, b):.0f}/{thumb:.0f}, "
              f"aspect {abs(math.log(a.aspect / b.aspect)):.3f}/{aspect:.2f}")
    return match, ("same picture -- " if match else "different picture -- ") + detail
