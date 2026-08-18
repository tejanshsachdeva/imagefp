"""Tests for EMF/WMF metafile comparison."""

from __future__ import annotations

from imagefp import emf_signature, images_match


def test_identical_emf_matches(emf_base):
    match, reason = images_match(emf_base, "chart.emf", emf_base, "chart.emf")
    assert match is True
    assert reason == "same metafile drawing"


def test_header_only_difference_still_matches(emf_base, emf_same_drawing_different_header):
    """A resize that only rewrites the header bounds (not the drawing
    records) should still be recognised as the same chart."""
    match, reason = images_match(
        emf_base, "chart.emf",
        emf_same_drawing_different_header, "chart_resized.emf",
    )
    assert match is True
    assert reason == "same metafile drawing"


def test_comment_only_difference_still_matches(emf_base, emf_same_drawing_different_comment):
    """A re-export that only adds/changes an EMR_COMMENT (per-instance
    metadata, timestamps, etc.) should still be recognised as the same chart."""
    match, reason = images_match(
        emf_base, "chart.emf",
        emf_same_drawing_different_comment, "chart_reexported.emf",
    )
    assert match is True
    assert reason == "same metafile drawing"


def test_real_drawing_edit_does_not_match(emf_base, emf_real_edit):
    match, reason = images_match(
        emf_base, "chart.emf",
        emf_real_edit, "chart_edited.emf",
    )
    assert match is False
    assert "differs" in reason


def test_truncated_emf_is_unreadable(emf_base):
    truncated = emf_base[:10]
    match, reason = images_match(emf_base, "a.emf", truncated, "b.emf")
    assert match is False
    assert "unreadable" in reason


def test_non_emf_bytes_return_none_signature():
    assert emf_signature(b"not an emf file at all") is None
    assert emf_signature(b"\x00" * 100) is None  # right length, wrong magic


def test_wmf_extension_is_reported_unreadable_not_crashed(wmf_bytes):
    """WMF is a known, documented gap: legacy WMF byte streams (wrong magic
    number for the EMF parser) should fail closed as "unreadable", never
    raise or be silently treated as a match."""
    match, reason = images_match(wmf_bytes, "a.wmf", wmf_bytes, "b.wmf")
    assert match is False
    assert "unreadable" in reason
