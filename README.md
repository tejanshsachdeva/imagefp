# imagefp

Decide whether two images are **the same picture** — even when they were
re-encoded, alpha-flattened onto a background, cropped/padded differently,
or resized — without ever falsely claiming a match it isn't sure of.

Built for pipelines that re-save or re-export documents (PowerPoint, Word,
Excel, PDF) where the same source image commonly reappears in a different
container format, with different compression, or with its transparency
flattened away. Generic perceptual-hash libraries don't handle the
alpha-flattening or EMF-metadata-churn cases; this one does.

## Install

```bash
pip install imagefp
```

Raster comparison (`.png`, `.jpg`, `.gif`, `.bmp`, `.tiff`, `.webp`, ...)
requires [Pillow](https://pypi.org/project/Pillow/), which is installed
automatically as a dependency. EMF/WMF metafile comparison has no extra
dependency.

## Quick start

```python
from imagefp import images_match

with open("logo.png", "rb") as f:
    data_a = f.read()
with open("logo_export.jpg", "rb") as f:
    data_b = f.read()

match, reason = images_match(data_a, "logo.png", data_b, "logo_export.jpg")
print(match, reason)
# True "same picture -- shape 0/30, colour 3/18, aspect 0.000/0.11"
```

`images_match` is the one function most callers need. It takes the raw bytes
and the original file/part name (so it knows whether it's looking at a
raster or a vector metafile) for each image, and returns:

```python
(match: bool, reason: str)
```

`reason` is always populated, win or lose, so you can log *why* two images
were or weren't considered the same.

## How it decides "same picture"

1. **Classify** each file as raster (`.png`, `.jpg`, `.webp`, ...) or
   metafile (`.emf`, `.wmf`) by extension.
2. **Rasters** are compared with a perceptual fingerprint:
   - Crop to actual content (ignore blank padding/margins).
   - Composite any transparency onto white, the same way PowerPoint does
     when it re-saves an image — so a transparent logo and its flattened
     export land in the same colour space.
   - Downsample to a 16×16 grid (colour thumbnail + a separate "ink mask"
     of where there's real content vs. background).
   - Compare in three gates, cheapest first: aspect ratio, then ink-mask
     shape, then colour — measured **only** over cells where both images
     actually have ink, so background/padding differences can't skew it.
3. **Metafiles** (EMF) are compared by hashing their drawing records,
   deliberately skipping the header (which changes on resize) and comment
   records (where per-export metadata/timestamps live) — so the same chart
   re-exported a week later still matches, while an actual edit does not.
4. **Anything uncertain returns "different."** Undecodable bytes, a
   raster-vs-metafile mismatch, missing bytes, or an unparsable metafile —
   all of these are reported as *not a match*, never as an uncertain match.

## What it does *not* do

- It cannot detect a match after a resize that rewrites an EMF's actual
  drawing coordinates (as opposed to just its header bounds) — that would
  require rendering the metafile to pixels, which is out of scope.
- `.wmf` files are legacy 16-bit metafiles with a different record format
  and are currently always reported as unreadable (`emf_signature` returns
  `None` for them). If you need WMF support, open an issue.
- This is a "is this the same picture" tool, not a general reverse-image
  search or similarity ranker — it returns a boolean, not a similarity
  score for ranking many candidates (though the `reason` string exposes the
  underlying distances if you want to build that yourself).

## API reference

| Function | Purpose |
|---|---|
| `images_match(data_a, name_a, data_b, name_b, *, shape=30.0, thumb=18.0, aspect=0.11)` | The main entry point. Returns `(match, reason)`. |
| `kind(name)` | `"raster"`, `"metafile"`, or `"other"`, by file extension. |
| `describe(data)` | Build a `Descriptor` (thumbnail + ink mask + aspect) for one raster image. |
| `same_image(a, b, ...)` | Run the three-gate comparison on two `Descriptor`s directly. |
| `emf_signature(data)` | SHA-256-derived signature of an EMF's drawing records, or `None`. |
| `thumb_distance`, `shape_distance`, `colour_distance` | The individual distance metrics, if you want to tune thresholds yourself. |

All public names are also importable directly from the `imagefp` package,
e.g. `from imagefp import Descriptor, kind, emf_signature`.

### Tuning thresholds

The three gates each take a threshold, exposed as keyword arguments on
`images_match`:

```python
images_match(data_a, name_a, data_b, name_b,
             shape=30.0,   # max ink-mask distance
             thumb=18.0,   # max masked colour distance
             aspect=0.11)  # max |log(aspect ratio difference)|
```

Lower values are stricter (fewer false positives, more false negatives);
higher values are looser. The defaults were tuned for documents re-exported
by PowerPoint/Office tooling — you may want to widen `thumb` slightly for
very lossy JPEG re-compression, or tighten `aspect` if your corpus has many
same-content images at deliberately different aspect ratios (e.g. a banner
vs. a thumbnail of unrelated art that happens to share a palette).

## Development

```bash
git clone https://github.com/tejanshsachdeva/imagefp.git
cd imagefp
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).