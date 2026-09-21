# Approach

## What the reports actually are

Every source PDF is a spreadsheet print. A page paints a few large background regions, then
draws every gridline as a thin filled rectangle, then paints text at fixed positions. There
are no strokes, no curves except one decorative oval, and no images.

That shape is what makes a mechanical conversion possible. `tools/grid.py` recovers the table
instead of guessing it:

* vertical gridlines give the column boundaries,
* horizontal gridlines give the row boundaries,
* background regions give each cell's fill,
* a missing gridline between two adjacent slots means the source cells were merged, which
  becomes a `colspan` or `rowspan`,
* text is assigned to the cell that contains its baseline.

The output is real table markup - `<colgroup>` widths in points, `<thead>` for the repeating
header band, `<tr>` rows, `<td>` cells with spans and generated fill classes - and a
`fixture.json` holding only the sample values.

## Running it

```
make setup      # poppler + the licensed Arial/Times faces (idempotent; needed for metrics)
make doctor     # confirms this machine can produce comparable measurements
make catalog    # rebuild the 46 entries from the live pages
make fetch      # 46 reference PDFs
make extract    # evidence for all 267 pages
make convert    # scaffold, render, tune, render, compare - the whole corpus
make status     # regenerate the README table from the measurements
make check      # lint + tests
```

`make setup` is not optional for verification: without the licensed faces the render falls back
to the exported base-14 faces, the layout still holds because they are metric-compatible, but
the glyph outlines differ from the reference's and the raster metrics get worse.

## The loop

```
1  catalog    tools/catalog.py            parse both listing pages, apply the dedup rules -> 46 entries
2  fetch      tools/fetch.py --all        immutable PDFs + MANIFEST (sha256, size, pages, timestamp)
3  extract    tools/extract.py --all      spans, paths, geometry, fonts, review rasters
4  scaffold   tools/scaffold.py <key>     grid -> template.html + report.css + fixture.json + bindings.yaml
5  render     tools/render.py <key>       Chromium headless print-to-pdf
6  tune       tools/tune.py <key>         measure the render's residual offset, record it
7  render     tools/render.py <key>       second render lands on the measured reference
8  compare    tools/compare.py <key>      300 dpi metrics + diff images for failing pages
9  record     tools/status.py             regenerate the README table from report.json
```

`tools/convert.py <level> <key>` runs 4-8; `--all` runs the whole corpus.

## Why there is a tuning pass

Placing text from font metrics assumes the browser derives its baseline from the same ascent
and descent values PyMuPDF reports. It does not, quite. Rather than hand-tune a magic number,
step 6 renders once, measures the median residual against the reference, and writes it to
`calibration.json`. The second render applies it. The correction is a measurement, and it is
committed next to the template so a reviewer can see it.

Corrections are keyed by face, size *and* rotation. Keying by size alone applied one face's
baseline offset to another - Times New Roman Bold at 8.16 pt inherited Arial's correction and
stayed 0.46 pt low - and a rotated run's residual lies along the other page axis, so mixing it
with horizontal text of the same face corrupted both.

## Vertical headings

38 of the 46 reports set their column headings sideways. A rotated span reports an origin that
is not its left edge, so the rotation travels with the span through extraction and the text is
placed by rotating about the line box's top-left corner. Before this was handled, those
headings were rebuilt lying flat and sat nearly 7 pt out of place.

## Deviations from the original plan, and why

* **Text is placed at a measured offset inside its own cell** rather than flowed with padding
  and `text-align`. The gates are sub-point; browser text flow cannot hit them. The grid, the
  fills, the spans and the row/column structure are still real table markup, and the measured
  alignment of every cell is kept in `bindings.yaml` for downstream reflow.
* **Gridlines are emitted as exact vector rules, not CSS borders.** CSS border widths round to
  whole device pixels. These reports draw 0.48 pt hairlines, often two of them 0.48 pt apart
  for an emphasised rule, and Chromium collapses `1.44pt double` into a single line - half the
  rule pixels vanish and the edge lands in the wrong place. Vector rules reproduce weight,
  position and colour exactly.
* **Stored page rasters are 150 dpi**, palette compressed, and exist only so a reviewer can
  see a page in a diff. Every metric is recomputed from the PDFs at 300 dpi at comparison
  time, so no measurement depends on them. 267 reference pages at 300 dpi would add roughly
  80 MB of images to the repository for no measurement value.
* **The rendered PDF is the deliverable.** Per-page images of a passing render are not
  committed; diff images are written only for pages that fail, capped at two per report, which
  is what a reviewer needs to see the problem.
* **Runs carry per-character corrections where the reference asks for them.** The declared font
  widths match the licensed faces exactly, but these producers also emit explicit per-glyph
  adjustments, so text on the page is spaced slightly differently from what the widths alone
  give. Each run records the correction needed before each chunk, and consecutive characters
  that need none stay in one chunk, so the markup only grows where the reference demands it.
