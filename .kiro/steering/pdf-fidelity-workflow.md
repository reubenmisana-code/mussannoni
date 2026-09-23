---
inclusion: always
---

# PDF fidelity workflow

- **Before writing any code in this repository, read [`docs/06-exametrics-alignment.md`](../../docs/06-exametrics-alignment.md).** It is the working document for aligning all 46 reports with ExaMetrics data: the per-report status table, the verification procedure, and a rejected-approaches table of eight dead ends that were each implemented and measured as wrong. Update its status table when you change anything.
- Do not infer from row content what the measurement can state. Place values by column identity (`layout.header.fields`), never by cell shape; decide a report's pages by grid, never by inspecting text. Both content-based approaches leaked the reference exam's data into another school's report.
- Never re-place text whose value has not changed — it keeps its measured offset, letter spacing and per-cluster corrections. Recomputing unchanged text from font metrics moved a letterhead 193 pt.
- Verify at document level across **all** pages, cell by cell, not by eye on a rendered page 1. Comparing page 1 alone hid a 29.26 pt error on page 14, and checking that expected strings were present hid four candidates being silently dropped.
- Treat the original SARS PDFs as immutable visual and data authorities.
- Preserve source PDFs, checksums, extraction data, page rasters, rendered output, visual diffs, and metrics needed to reproduce and audit every rebuild.
- Implement one report at a time in README manifest order, beginning with SECONDARY `school_results`; do not mark a report done until every README fidelity gate passes.
- Measure geometry mechanically with PyMuPDF. Do not estimate dimensions or encode Mwanza sample values in reusable templates.
- Verify Chromium output first and retain comparison artifacts in the repository.
- Commit and push completed work. If blocked, commit and push reproducible partial progress with the blocker documented; never claim fidelity that was not measured.
