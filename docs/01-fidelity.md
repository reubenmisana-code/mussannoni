# Fidelity gates and how they are measured

A report is `done` only when every page meets every gate:

| Check | Threshold | Where it is measured |
|-------|-----------|----------------------|
| Page count | equal to the reference | `compare.page_count_equal` |
| Page size and orientation | equal | `page_size_equal` |
| Structural similarity (SSIM) | ≥ 0.98 | `ssim` |
| Differing pixels at 300 dpi | ≤ 0.5% | `differing_pixels_percent` |
| Text baseline / left-edge drift | ≤ 1.0 pt for every span | `text.maximum_drift_pt` |
| Table column x-edges | ≤ 0.5 pt | `maximum_column_edge_drift_pt` |
| Text content | every span present, none surplus | `text.text_content_equal` |
| Rule weights and colours | identical | vector rules carry the measured geometry |

Thresholds are never relaxed. A report that misses one is `wip`, and `tools/status.py` reports
it as such.

## How the comparison is made fair

Both PDFs are rasterised by the same rasteriser, poppler, at 300 dpi.

This matters more than it looks. Most of these reports *name* Arial and Times New Roman without
embedding them, so the glyphs a reader sees depend entirely on the renderer's font stack.
MuPDF ignores system fonts and substitutes its own base-14 faces; poppler resolves them
through fontconfig. Rasterising the reference with one substitution and the render with another
measures the font fallback, not the template - early runs lost about 9% of pixels to exactly
that. Verification therefore requires the licensed Arial and Times New Roman faces to be
installed; see `docs/03-fonts.md`.

## Span matching

Drift is measured by matching each reference span to the nearest rendered span carrying the
same text. Pairing spans by extraction order reports enormous drift the moment the order
differs, which says nothing about fidelity: an early run reported 222 pt of "drift" for a page
whose text was in the right place. `missing_spans` and `surplus_spans` are reported separately
so a real content difference cannot hide inside a drift number.

## Current limitation

Text-dense pages do not reach the 0.5% differing-pixel gate. With placement calibrated to
about 0.07 pt, roughly 23% of dark pixels still fail to overlap, because a sub-pixel offset
changes the antialiasing of every glyph edge at 300 dpi. Two independently produced PDFs will
differ there even when both are laid out correctly. The measured values per report are in the
README table; the gate has not been moved to accommodate them.
