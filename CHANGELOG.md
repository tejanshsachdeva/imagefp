# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.6.0] - 2026-09-21

### Added
- EMF+ drawing payloads inside `EMR_COMMENT` records are included in
  `emf_signature` (metadata-only comments are still excluded).
- Border-based ink-mask estimation for RGB rasters; full-bleed images treat
  all pixels as content when the border is not a flat background.
- EXIF orientation is applied before raster comparison.
- Tests for EMF+ drawing vs metadata differences, mid-record truncation, and
  explicit WMF handling.

### Changed
- Incomplete or corrupt EMF files no longer produce a signature; they are
  reported as truncated/corrupt instead of same/different.
- WMF parts get an explicit “not supported yet” message (extension check
  runs before EMF parsing).
- Raster decode errors are narrowed to expected failure types; Pillow
  decompression-bomb limit is tightened only for the duration of each decode.
- `__version__` is read from package metadata (`pyproject.toml` when installed).

### Fixed
- Two EMF+ charts that shared a GDI fallback but differed in EMF+ content
  could previously hash as identical.

## [0.5.0] - 2026-08-18

### Added
- Initial packaged release: `pyproject.toml`, `src/` layout, `py.typed` marker.
- Type hints across the public API.
- Test suite covering raster comparison (identical, flattened-alpha,
  cropped/padded, aspect mismatch, undecodable), EMF signature comparison
  (identical, header-only diff, comment-only diff, real edit, truncated,
  non-EMF), and the `images_match` dispatch logic.
- `README.md` with usage, algorithm summary, and documented limitations.

### Notes
- Core comparison logic (rasters via 16x16 thumbnail + ink mask + aspect
  guard; metafiles via drawing-record SHA-256 signature) is unchanged from
  the original internal script.
- WMF metafiles remain unsupported; tracked as a known limitation, not a bug.
