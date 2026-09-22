# Shared font assets

`report-*.otf` are the base-14 faces bundled with the pinned PyMuPDF/MuPDF build, exported verbatim by `tools/fonts.py`. MuPDF rasterises the reference PDFs with these faces whenever a report names Arial or Times New Roman without embedding it, so the templates use the same buffers and the fidelity comparison measures layout rather than two unrelated font substitutions.

They are URW++ derived Helvetica/Times clones as redistributed by MuPDF. Regenerate with `make fonts`. Production rendering should install licensed Arial and Times New Roman and map `Report Sans` / `Report Serif` onto them; the measured effect is recorded in `docs/03-fonts.md`.
