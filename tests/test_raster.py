"""Tests for raster (PNG/JPEG/etc.) comparison."""

from __future__ import annotations

from imagefp import images_match, kind


def test_kind_classifies_extensions():
    assert kind("logo.png") == "raster"
    assert kind("photo.JPG") == "raster"
    assert kind("chart.emf") == "metafile"
    assert kind("chart.WMF") == "metafile"
    assert kind("readme.txt") == "other"
    assert kind("") == "other"


def test_identical_bytes_match(red_square_transparent_png):
    match, reason = images_match(
        red_square_transparent_png, "a.png",
        red_square_transparent_png, "b.png",
    )
    assert match is True
    assert "same picture" in reason


def test_transparent_matches_flattened_on_white(
    red_square_transparent_png, red_square_on_white_jpeg
):
    """The core promise of the library: a transparent-background logo and its
    PowerPoint-flattened JPEG export should still be recognised as the same
    picture, despite different canvas size, format, and background."""
    match, reason = images_match(
        red_square_transparent_png, "logo.png",
        red_square_on_white_jpeg, "logo_export.jpg",
    )
    assert match is True
    assert "same picture" in reason


def test_padding_does_not_defeat_match(
    red_square_transparent_png, red_square_transparent_png_padded
):
    """Same artwork, very different canvas padding -> should still match
    because comparison is done on the cropped content box."""
    match, reason = images_match(
        red_square_transparent_png, "a.png",
        red_square_transparent_png_padded, "b.png",
    )
    assert match is True


def test_visually_different_images_do_not_match(
    red_square_transparent_png, blue_circle_png
):
    match, reason = images_match(
        red_square_transparent_png, "a.png",
        blue_circle_png, "b.png",
    )
    assert match is False
    assert "different picture" in reason


def test_aspect_ratio_guard_rejects_banner_vs_square(
    red_square_transparent_png, red_banner_png
):
    """Same fill colour, very different proportions -> aspect gate should
    reject before the (looser) colour check would otherwise pass it."""
    match, reason = images_match(
        red_square_transparent_png, "square.png",
        red_banner_png, "banner.png",
    )
    assert match is False
    assert "different picture" in reason


def test_undecodable_bytes_report_different(red_square_transparent_png, truncated_png):
    match, reason = images_match(
        red_square_transparent_png, "a.png",
        truncated_png, "b.png",
    )
    assert match is False
    assert "undecodable" in reason or "different picture" in reason


def test_missing_bytes_report_different(red_square_transparent_png):
    match, reason = images_match(None, "a.png", red_square_transparent_png, "b.png")
    assert match is False
    assert "unavailable" in reason

    match, reason = images_match(red_square_transparent_png, "a.png", None, "b.png")
    assert match is False
    assert "unavailable" in reason


def test_raster_vs_metafile_reports_different_media_kind(red_square_transparent_png):
    match, reason = images_match(
        red_square_transparent_png, "a.png",
        b"whatever-bytes", "b.emf",
    )
    assert match is False
    assert "media kind" in reason


def test_custom_thresholds_are_respected(red_square_transparent_png, blue_circle_png):
    """With an absurdly loose colour/shape tolerance, even very different
    images should be reported as matching -- confirms thresholds are wired
    through, not hardcoded."""
    match, _ = images_match(
        red_square_transparent_png, "a.png",
        blue_circle_png, "b.png",
        shape=255.0, thumb=255.0, aspect=10.0,
    )
    assert match is True
