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


def test_truncated_emf_is_reported_as_corrupt(emf_base):
    truncated = emf_base[:10]
    match, reason = images_match(emf_base, "a.emf", truncated, "b.emf")
    assert match is False
    assert "truncated or corrupt" in reason


def test_mid_record_truncation_is_reported_as_corrupt(emf_base):
    """A cut that lands after a full record header but never reaches
    EMR_EOF -- distinct from the too-short-to-even-parse case above."""
    truncated = emf_base[: len(emf_base) - 4]
    match, reason = images_match(emf_base, "a.emf", truncated, "b.emf")
    assert match is False
    assert "truncated or corrupt" in reason


def test_non_emf_bytes_return_none_signature():
    assert emf_signature(b"not an emf file at all") is None
    assert emf_signature(b"\x00" * 100) is None  # right length, wrong magic


def test_wmf_extension_gets_its_own_explicit_message(wmf_bytes):
    """WMF is a known, documented gap: legacy WMF byte streams should be
    reported with a specific "not supported" message -- distinct from a
    corrupt/truncated EMF -- never silently treated as a match."""
    match, reason = images_match(wmf_bytes, "a.wmf", wmf_bytes, "b.wmf")
    assert match is False
    assert "WMF is not supported" in reason


def test_wmf_extension_wins_even_if_bytes_look_like_emf(emf_base):
    """The extension check runs before signature parsing, so a part merely
    *named* .wmf is never silently compared as if it were EMF, even if its
    bytes happen to satisfy the EMF magic-number check."""
    match, reason = images_match(emf_base, "a.wmf", emf_base, "b.wmf")
    assert match is False
    assert "WMF is not supported" in reason


def test_emfplus_drawing_content_difference_is_detected(
    emf_emfplus_base, emf_emfplus_different_drawing
):
    """Two EMF+ drawings that only share a GDI fallback but differ in their
    actual EMF+ payload must NOT be reported as the same picture."""
    match, reason = images_match(
        emf_emfplus_base, "chart.emf",
        emf_emfplus_different_drawing, "chart2.emf",
    )
    assert match is False
    assert "differs" in reason


def test_emfplus_metadata_only_difference_still_matches(
    emf_emfplus_base, emf_emfplus_different_metadata
):
    """Two EMF+ drawings with identical EMF+ payloads but different
    surrounding metadata comments (timestamps/GUIDs, non-EMF+ identifier)
    should still be recognised as the same drawing."""
    match, reason = images_match(
        emf_emfplus_base, "chart.emf",
        emf_emfplus_different_metadata, "chart_reexported.emf",
    )
    assert match is True
    assert reason == "same metafile drawing"
