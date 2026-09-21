# Fidelity gates

A report is `done` only when every page has the same dimensions, orientation, row/page breaks, and rule styling as the reference, with SSIM at least 0.98, differing pixels at 300 dpi no more than 0.5%, text baseline and left-edge drift no more than 1 point, and column-edge drift no more than 0.5 point.

`tools/compare.py` writes all measurements to the report output directory. A failed gate keeps catalog status at `wip`; thresholds are not relaxed.
