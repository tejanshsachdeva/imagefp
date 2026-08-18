"""Tests for the public package surface."""

from __future__ import annotations

import imagefp


def test_version_is_exposed():
    assert isinstance(imagefp.__version__, str)
    assert imagefp.__version__.count(".") == 2


def test_public_api_is_importable():
    from imagefp import (  # noqa: F401
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


def test_descriptor_is_lightweight_and_slotted():
    d = imagefp.Descriptor(b"\x00" * 48, b"\xff" * 16, 1.0)
    assert d.aspect == 1.0
    assert not hasattr(d, "__dict__")  # __slots__ enforced
