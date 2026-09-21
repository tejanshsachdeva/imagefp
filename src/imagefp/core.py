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
from collections import Counter
from pathlib import Path
from typing import cast

try:
    from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError
    from PIL.Image import DecompressionBombError
    from PIL.Image import Image as PILImage

    _RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    Image = ImageChops = ImageOps = None  # type: ignore[assignment]
    PILImage = object  # type: ignore[assignment,misc]
    UnidentifiedImageError = OSError  # type: ignore[assignment,misc]
    DecompressionBombError = Exception  # type: ignore[assignment,misc]
    _RESAMPLE = None
    _PIL_AVAILABLE = False

RASTER_EXTS = {".png", ".jpg", ".jpeg", ".jfif", ".gif", ".bmp", ".dib",
               ".tif", ".tiff", ".webp", ".ico"}
METAFILE_EXTS = {".emf", ".wmf"}

MAX_PIXELS = 50_000_000        # decode-bomb guard
THUMB = 16                     # 16x16 comparison grid
TRIM_TOL = 8                   # alpha below this is blank (trim)
TRIM_TOL_COLOUR = 26           # colour delta from the border that counts as ink
BORDER_FLAT_RATIO = 0.6        # fraction of border pixels that must agree to call it "background"
DEFAULT_SHAPE_DIST = 30.0      # mean abs difference of the ink masks
DEFAULT_THUMB_DIST = 18.0      # mean abs channel difference over co-inked cells
DEFAULT_INK_FLOOR = 200        # cells below this are edge/antialiasing
DEFAULT_ASPECT_TOL = 0.11      # |log(a/b)| aspect ratio tolerance
_COMPOSITE_BG = (255, 255, 255)  # flatten alpha onto white, as PowerPoint does

# Exceptions that mean "these bytes are not a usable image" -- narrow on
# purpose, so a genuine bug elsewhere in describe() surfaces as a real
# traceback instead of silently becoming "undecodable".
_DECODE_ERRORS = (UnidentifiedImageError, OSError, ValueError, DecompressionBombError)


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def kind(name: str) -> str:
    """Classify a file by extension as ``"raster"``, ``"metafile"``, or ``"other"``."""
    ext = _ext(name)
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
            "Install it with: pip install Pillow"
        )


def _open(data: bytes) -> PILImage:
    """Decode to RGB/RGBA, or raise. Palette/greyscale/CMYK/16-bit fold into
    RGB so pixel identity means visual identity; a fully-opaque alpha channel
    is dropped (PowerPoint re-saves such images as RGB). EXIF orientation is
    applied so a phone photo and the same photo with only its orientation
    tag changed still compare equal."""
    _require_pillow()
    # Decompression-bomb guard: Pillow's MAX_IMAGE_PIXELS is process-global,
    # so a long-lived app that also uses Pillow elsewhere shouldn't have its
    # own limit silently overwritten by ours for the rest of the process.
    # Save/restore around just this decode, and only tighten the limit (never
    # loosen it) in case the host app has already set something stricter.
    _prev_max_pixels = Image.MAX_IMAGE_PIXELS
    if _prev_max_pixels is None or _prev_max_pixels > MAX_PIXELS:
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        im: PILImage = Image.open(io.BytesIO(data))
        w, h = im.size
        if w <= 0 or h <= 0:
            raise ValueError(f"{w}x{h} invalid dimensions")
        im = ImageOps.exif_transpose(im) or im
        has_alpha = im.mode in ("RGBA", "LA", "PA") or (
            im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if has_alpha else "RGB")
        im.load()  # force full decode now, so the bomb guard fires here, not later
        if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] == 255:
            im = im.convert("RGB")
        return im
    finally:
        Image.MAX_IMAGE_PIXELS = _prev_max_pixels


def _px(im: PILImage, xy: tuple[int, int]) -> tuple[int, int, int]:
    """getpixel() typed as the RGB triple it always is for an 'RGB' image."""
    return cast("tuple[int, int, int]", im.getpixel(xy))


def _border_colour(rgb: PILImage) -> tuple[int, int, int] | None:
    """Dominant colour along the image border, or None if the border is not
    reasonably flat (e.g. a full-bleed photo with no margin). Sampling the
    whole border rather than a single corner pixel avoids being fooled by
    compression noise or art that happens to touch the corner."""
    w, h = rgb.size
    if w < 2 or h < 2:
        return _px(rgb, (0, 0))
    pixels = (
        [_px(rgb, (x, 0)) for x in range(w)]
        + [_px(rgb, (x, h - 1)) for x in range(w)]
        + [_px(rgb, (0, y)) for y in range(h)]
        + [_px(rgb, (w - 1, y)) for y in range(h)]
    )
    colour, freq = Counter(pixels).most_common(1)[0]
    if freq / len(pixels) < BORDER_FLAT_RATIO:
        return None
    return colour


def _ink_mask(im: PILImage) -> PILImage:
    """Full-size 'L' mode mask (255 = content, 0 = background) for the given
    image. Alpha is used directly when present; otherwise content is
    estimated as distance from the dominant border colour. When there is no
    flat border to treat as background (e.g. a full-bleed photo), the whole
    image is treated as content rather than diffing against a meaningless
    guess."""
    if im.mode == "RGBA":
        return im.getchannel("A").point(lambda v: 255 if v > TRIM_TOL else 0)
    rgb = im.convert("RGB")
    bg = _border_colour(rgb)
    if bg is None:
        return Image.new("L", rgb.size, 255)
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
    return diff.point(lambda v: 255 if v > TRIM_TOL_COLOUR else 0)


class Descriptor:
    """A 16x16 colour thumbnail, a 16x16 ink mask, and the artwork aspect."""

    __slots__ = ("aspect", "ink", "thumb")

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
    the estimated border colour) is what survives flattening: a
    transparent-background logo and the same logo composited onto white share
    an ink mask, so colour can be compared only where both actually have ink.
    """
    im = _open(data)
    ink_uncropped = _ink_mask(im)
    box = ink_uncropped.getbbox() or (0, 0, im.size[0], im.size[1])

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

# EMR_HEADER(1) carries size-dependent bounds and is excluded so a resize
# that only touches the header bounds still matches. EMR_COMMENT(70) is
# where both harmless per-export metadata (timestamps, GUIDs -- excluded)
# AND real EMF+ drawing commands (included) live; see _emf_comment_payload.
_EMF_HEADER_TYPE = 1
_EMF_COMMENT_TYPE = 70
_EMF_EOF_TYPE = 14
_EMFPLUS_COMMENT_ID = 0x2B464D45  # ASCII "+FME" little-endian; marks EMF+ payloads


def _emf_comment_payload(payload: bytes) -> bytes:
    """What to hash from an EMR_COMMENT record's payload.

    EMR_COMMENT records carry a 4-byte DataSize, then a 4-byte
    CommentIdentifier, then the actual comment content. When the identifier
    marks this as EMR_COMMENT_EMFPLUS, that content is real EMF+ drawing
    records (PowerPoint/Excel's GDI+ fallback for a chart) and MUST be
    hashed, or two visually different EMF+ drawings that share a GDI
    fallback would hash identically. Any other identifier (public GDI
    comments, private per-export metadata, timestamps, GUIDs) is excluded,
    same as before, since re-exporting the same drawing legitimately changes
    that content without changing the picture.
    """
    if len(payload) < 8:
        return b""  # too short to carry an identifier; nothing safe to hash
    comment_id = struct.unpack_from("<I", payload, 4)[0]
    if comment_id == _EMFPLUS_COMMENT_ID:
        return payload
    return b""


def emf_signature(data: bytes, max_records: int = 200_000) -> str | None:
    """Drawing-record signature of an EMF, or None if it is not a parseable,
    complete EMF (WMF, truncated, or corrupt files all return None -- a
    partial parse is never turned into a signature, since a truncated file
    being reported as "same" or "different" would both be a lie about data
    that was never actually read)."""
    if len(data) < 88 or data[:4] != b"\x01\x00\x00\x00":
        return None
    h = hashlib.sha256()
    off, n, end = 0, 0, len(data)
    reached_eof = False
    while off + 8 <= end and n < max_records:
        rtype, rsize = struct.unpack_from("<II", data, off)
        if rsize < 8 or off + rsize > end:
            return None  # malformed or truncated mid-record -- unreadable, not a signature
        h.update(struct.pack("<I", rtype))
        payload = data[off + 8:off + rsize]
        if rtype == _EMF_HEADER_TYPE:
            pass  # size-dependent bounds excluded
        elif rtype == _EMF_COMMENT_TYPE:
            h.update(_emf_comment_payload(payload))
        else:
            h.update(payload)
        off += rsize
        n += 1
        if rtype == _EMF_EOF_TYPE:
            reached_eof = True
            break
    if not reached_eof:
        return None  # ran out of records/hit the cap without EMR_EOF -- incomplete
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
        ext_a, ext_b = _ext(name_a or ""), _ext(name_b or "")
        if ext_a == ".wmf" or ext_b == ".wmf":
            return False, "WMF is not supported yet (only EMF metafiles are compared)"
        sa, sb = emf_signature(data_a), emf_signature(data_b)
        if sa is None or sb is None:
            return False, "metafile truncated or corrupt (not a complete, parseable EMF)"
        if sa == sb:
            return True, "same metafile drawing"
        return False, "metafile drawing differs (resize or edit)"
    if ka == "metafile" or kb == "metafile":
        return False, "different media kind (raster vs metafile)"

    try:
        a, b = describe(data_a), describe(data_b)
    except _DECODE_ERRORS as exc:
        return False, f"undecodable ({type(exc).__name__})"

    match = bool(same_image(a, b, thumb, aspect, shape))
    detail = (f"shape {shape_distance(a, b):.0f}/{shape:.0f}, "
              f"colour {colour_distance(a, b):.0f}/{thumb:.0f}, "
              f"aspect {abs(math.log(a.aspect / b.aspect)):.3f}/{aspect:.2f}")
    return match, ("same picture -- " if match else "different picture -- ") + detail
