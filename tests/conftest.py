"""Shared helpers for generating synthetic image bytes used across the test suite."""

from __future__ import annotations

import io
import struct

import pytest
from PIL import Image


def _png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(im: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


@pytest.fixture
def red_square_transparent_png() -> bytes:
    """A red square centered on a transparent 64x64 canvas."""
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for y in range(16, 48):
        for x in range(16, 48):
            im.putpixel((x, y), (220, 30, 30, 255))
    return _png_bytes(im)


@pytest.fixture
def red_square_on_white_jpeg() -> bytes:
    """The same red square, pre-flattened onto white and JPEG-compressed
    (as PowerPoint would re-save it), at a slightly different canvas size."""
    im = Image.new("RGB", (80, 80), (255, 255, 255))
    for y in range(24, 56):
        for x in range(24, 56):
            im.putpixel((x, y), (220, 30, 30))
    return _jpeg_bytes(im, quality=85)


@pytest.fixture
def red_square_transparent_png_padded() -> bytes:
    """Same content as red_square_transparent_png, but on a much larger
    transparent canvas (heavy padding)."""
    im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    for y in range(16, 48):
        for x in range(16, 48):
            im.putpixel((x, y), (220, 30, 30, 255))
    return _png_bytes(im)


@pytest.fixture
def blue_circle_png() -> bytes:
    """A visually distinct image: a blue-ish square in a different position,
    used as a clear non-match."""
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for y in range(0, 32):
        for x in range(0, 32):
            im.putpixel((x, y), (20, 50, 220, 255))
    return _png_bytes(im)


@pytest.fixture
def red_banner_png() -> bytes:
    """Same red fill colour as red_square_transparent_png, but a wide banner
    shape -- should fail the aspect-ratio gate even though colours match."""
    im = Image.new("RGBA", (256, 32), (0, 0, 0, 0))
    for y in range(4, 28):
        for x in range(4, 252):
            im.putpixel((x, y), (220, 30, 30, 255))
    return _png_bytes(im)


@pytest.fixture
def truncated_png() -> bytes:
    """Bytes that look like a PNG but are cut off mid-stream."""
    im = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    full = buf.getvalue()
    return full[: len(full) // 2]


def build_emf(records: list[tuple[int, bytes]]) -> bytes:
    """Assemble a minimal, syntactically valid EMF byte stream from a list of
    (record_type, payload) tuples. Not a real renderable EMF -- just enough
    structure for emf_signature() to parse."""
    out = bytearray()
    for rtype, payload in records:
        size = 8 + len(payload)
        # EMF records are DWORD-aligned; pad payload if needed.
        pad = (-size) % 4
        payload = payload + b"\x00" * pad
        size = 8 + len(payload)
        out += struct.pack("<II", rtype, size)
        out += payload
    return bytes(out)


@pytest.fixture
def emf_header() -> bytes:
    """A minimal EMR_HEADER (type 1) payload, large enough to satisfy the
    88-byte minimum-length check in emf_signature."""
    return b"\x00" * 80  # header body; exact field layout doesn't matter here


@pytest.fixture
def emf_base(emf_header: bytes) -> bytes:
    """A small, valid-looking EMF: header + a comment + one drawing record +
    EOF. A comment record is included in the baseline itself, since real
    EMF+/add-in exports always carry one -- the fixture for "comment-only
    difference" then only changes its *content*, not its presence."""
    return build_emf([
        (1, emf_header),                              # EMR_HEADER
        (70, b"export-timestamp-2025-01-01"),         # EMR_COMMENT (per-instance metadata)
        (54, b"\x01\x02\x03\x04"),                    # arbitrary drawing record
        (14, b"\x00\x00\x00\x00"),                    # EMR_EOF
    ])


@pytest.fixture
def emf_same_drawing_different_header(emf_header: bytes) -> bytes:
    """Same drawing record, but a different header payload (simulating a
    resize that only touches the bounds, not the geometry)."""
    return build_emf([
        (1, b"\xff" * 80),                            # different EMR_HEADER bounds
        (70, b"export-timestamp-2025-01-01"),
        (54, b"\x01\x02\x03\x04"),                    # identical drawing record
        (14, b"\x00\x00\x00\x00"),
    ])


@pytest.fixture
def emf_same_drawing_different_comment(emf_header: bytes) -> bytes:
    """Same drawing record and header, but a different EMR_COMMENT (type 70)
    payload -- e.g. a re-export a week later with a new timestamp/GUID."""
    return build_emf([
        (1, emf_header),
        (70, b"export-timestamp-2026-01-01-DIFFERENT"),  # different comment content
        (54, b"\x01\x02\x03\x04"),                       # identical drawing record
        (14, b"\x00\x00\x00\x00"),
    ])


@pytest.fixture
def wmf_bytes() -> bytes:
    """Bytes shaped like a legacy (non-EMF) WMF file: a placeable-WMF magic
    number rather than the EMF magic, padded past the 88-byte minimum length
    that emf_signature checks before it will even look at the magic."""
    return b"\xd7\xcd\xc6\x9a" + b"\x00" * 100


@pytest.fixture
def emf_real_edit(emf_header: bytes) -> bytes:
    """A genuinely different drawing: the drawing record payload itself changed."""
    return build_emf([
        (1, emf_header),
        (54, b"\xAA\xBB\xCC\xDD"),             # different drawing coordinates
        (14, b"\x00\x00\x00\x00"),
    ])
