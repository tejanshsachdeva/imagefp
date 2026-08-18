# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
- WMF metafiles remain unsupported (`emf_signature` returns `None`); tracked
  as a known limitation, not a bug.
