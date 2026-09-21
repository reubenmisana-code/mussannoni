---
inclusion: always
---

# PDF fidelity workflow

- Treat the original SARS PDFs as immutable visual and data authorities.
- Preserve source PDFs, checksums, extraction data, page rasters, rendered output, visual diffs, and metrics needed to reproduce and audit every rebuild.
- Implement one report at a time in README manifest order, beginning with SECONDARY `school_results`; do not mark a report done until every README fidelity gate passes.
- Measure geometry mechanically with PyMuPDF. Do not estimate dimensions or encode Mwanza sample values in reusable templates.
- Verify Chromium output first and retain comparison artifacts in the repository.
- Commit and push completed work. If blocked, commit and push reproducible partial progress with the blocker documented; never claim fidelity that was not measured.
