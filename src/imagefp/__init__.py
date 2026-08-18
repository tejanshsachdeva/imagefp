"""imagefp — decide whether two images are the same picture.

Typical usage::

    from imagefp import images_match

    match, reason = images_match(bytes_a, "logo.png", bytes_b, "logo_export.jpg")
    if match:
        print("duplicate:", reason)
"""

from .core import (
    DEFAULT_ASPECT_TOL,
    DEFAULT_INK_FLOOR,
    DEFAULT_SHAPE_DIST,
    DEFAULT_THUMB_DIST,
    MAX_PIXELS,
    METAFILE_EXTS,
    RASTER_EXTS,
    THUMB,
    Descriptor,
    colour_distance,
    describe,
    emf_signature,
    images_match,
    kind,
    same_image,
    shape_distance,
    thumb_distance,
)

__version__ = "0.5.0"

__all__ = [
    "__version__",
    "images_match",
    "kind",
    "describe",
    "Descriptor",
    "same_image",
    "thumb_distance",
    "shape_distance",
    "colour_distance",
    "emf_signature",
    "RASTER_EXTS",
    "METAFILE_EXTS",
    "MAX_PIXELS",
    "THUMB",
    "DEFAULT_SHAPE_DIST",
    "DEFAULT_THUMB_DIST",
    "DEFAULT_INK_FLOOR",
    "DEFAULT_ASPECT_TOL",
]
