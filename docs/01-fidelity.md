# Fidelity gates and how they are measured

A report is `done` only when every page meets every gate:

| Check | Threshold | Field in `report.json` |
|-------|-----------|------------------------|
| Page count | equal to the reference | `page_count_equal` |
| Page size and orientation | equal | `pages[].page_size_equal` |
| Structural similarity (SSIM) | ≥ 0.98 | `pages[].ssim` |
| Differing pixels at 300 dpi | ≤ 0.5% | `pages[].differing_pixels_percent` |
| Text baseline / left-edge drift | ≤ 1.0 pt for every span | `pages[].text.maximum_drift_pt` |
| Table column x-edges | ≤ 0.5 pt | `pages[].maximum_column_edge_drift_pt` |
| Text content | every glyph present, none extra | `pages[].text.text_content_equal` |

Thresholds are never relaxed. A report that misses one is `wip`, and the README table says so.

## Where the corpus stands

| Gate | Reports meeting it |
|------|--------------------|
| Page count, size and orientation | 46 / 46 |
| All reference text reproduced | 46 / 46 |
| Text drift ≤ 1 pt | 45 / 46 |
| Column drift ≤ 0.5 pt | 40 / 46 |
| SSIM ≥ 0.98 on every page | 1 / 46 |
| Differing pixels ≤ 0.5% | 0 / 46 |

11 of 262 pages pass every gate outright. The structural gates are met; the two raster gates
are not, and the reason is specific.

## What the residual difference is

With placement calibrated, a median of **99.77% of every page's pixels are within a
one-pixel neighbourhood** of the reference, ink coverage matches to about 1%, and the best
alignment of the two rasters is a zero-pixel shift - so the glyphs are the right shape, the
right weight, and in the right place.

What remains is sub-pixel: two independently produced PDFs quantise glyph origins slightly
differently, and at 300 dpi a fraction of a pixel changes the antialiasing along every glyph
edge. Because the gate counts any pixel that is not identical, a page of dense 6.6 pt text
fails it while looking indistinguishable. Each page therefore also records diagnostics -
`explained_by_one_pixel_jitter_percent`, `ink_ratio`, `mean_absolute_difference` and
tolerance-based deltas - so the gap can be judged rather than guessed at. Those are
diagnostics only; nothing in the pass/fail decision uses them.

## How the comparison is made fair

Both PDFs are rasterised by the same rasteriser, poppler, at 300 dpi.

This matters more than it looks. Most reports *name* Arial and Times New Roman without
embedding them, so the glyphs a reader sees depend entirely on the renderer's font stack.
MuPDF ignores system fonts and substitutes its own base-14 faces; poppler resolves them
through fontconfig. Rasterising the reference with one substitution and the render with another
measures the font fallback, not the template - early runs lost about 9% of pixels to exactly
that. Run `make setup` before measuring, and `make doctor` to confirm.

## Two measurement traps worth knowing

**Span matching.** Drift is measured by pairing spans of identical text by closest distance.
Pairing by extraction order reported 222 pt of "drift" for a page whose text was correct, and
pairing repeated short strings ("F", "1", "IV") by reading order mispaired them across the
page.

**The anchor.** Drift is measured from each span's first *visible* glyph. Neither the text
origin nor the span bounding box works: both sit a space-width left when a span begins with a
space, and the two producers do not group spaces into spans the same way. That alone accounted
for 5 pt of phantom drift on three reports.

**Content.** Text presence is checked with a per-page glyph census rather than by comparing
span strings, because a PDF extractor splits a visually continuous string wherever the producer
emitted a new show-text operator, and the two producers split differently.
