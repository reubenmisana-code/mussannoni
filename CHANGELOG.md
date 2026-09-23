# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-09-23

### Fixed

- **A substituted text class now names its licensed face first.** 0.1.1 replaced the extracted
  proprietary subsets with metric-compatible open faces, but left those classes declaring only their
  own `@font-face` family — `font-family: 'Report CIDFont-F1'` — so they resolved to the bundled
  Liberation face and could never reach a real Arial, even on a host that had it installed. The
  classes that never embedded a font already did the right thing (`font-family: Arial, 'Report Sans'`),
  so the two halves of the corpus disagreed. All 426 substituted declarations now name the licensed
  face ahead of the fallback: Arial, `Arial Narrow`, Calibri or Tahoma as appropriate. A host with the
  licensed fonts renders with the reference's own outlines again; one without falls back to the open
  metric twin, as before.
- The licensed name is chosen per report from the file each `@font-face` was cut from, not from the
  family name: `Report CIDFont-F4` is Arial in eleven declarations and `Arial Narrow` in two, so a
  table keyed on the family alone would have mislabelled it.



## [0.1.1] - 2026-09-23

Everything in this release exists to stop a generated report carrying the exam it was measured from.

### Added

- **Each report renders from its own measured document.** `document.json.gz` ships per report — the
  fixture with per-cluster corrections emptied on data rows and kept everywhere else — so every band,
  every per-page column grid, every measured rule and vector and every page of a multi-section report
  is carried as measured rather than rebuilt from a flat approximation. Each measured page holds the
  rows the reference put on it, so page capacity is never computed. 46 documents come to **2.14 MB**
  gzipped against 3.85 MB for the distilled layouts they supplement — the measured geometry is
  *cheaper* than the approximation, which the original "too big to ship" reasoning never tested.
- **Values are placed by column identity, never by row shape.** `layout.header.fields` names each
  measured column, and rows may be mappings keyed by field name. Keying on a row's cell signature
  instead was implemented and measured as unsafe: whether a cell exists depends on whether the
  reference happened to print something there, so two rows of one table differ, and two of
  `secondary/school-results` page 2's thirty-seven candidate rows were emitted verbatim — putting a
  real candidate from the reference exam into another school's report.
- **`report_roles(key, level=…)`** returns, per measured page, what each static cell *is*:
  `authority`, `region`, `exam`, `scope`, `heading`, `figure` or `sample`. Decided when the package is
  built, against the reference, so no consumer has to pattern-match the reference's own strings. A
  caller looks up the role and writes to that address.
- **`data["bands"]`** addresses any static cell — `"row.column"` (page 1), `"page.row.column"`, or
  `"page.row.column.line"` for one line of a multi-line cell, which leaves the cell's other lines
  exactly as measured. **`data["loose"]`** does the same for the absolutely-positioned lines six
  reports draw beside the table instead of inside a header band; those letterheads were previously
  unreachable.
- Column identity for five more reports (43 of 46 now ship it): the four that print several ten-row
  blocks per page, and `region_ufaulu_masomo`.

### Fixed

- **Every `figure` and `sample` cell the caller does not supply now renders empty.** This is the
  release's point. Previously a generated report kept the measured exam's totals, averages, ranks and
  competency bands wherever they sat outside a data column. Measured on
  `secondary/school-results` page 14 with every data row filled: **320 non-empty cells before, 66
  after**, and the only remaining cell containing a digit is the column heading `DIV 0`. Across the
  corpus **6,996** figures blank and none survive. Blanking is removal, not replacement, so nothing
  is re-placed from font metrics.
- **Twelve reports were publishing the reference's schools.** A page carrying several blocks of rows
  had only its last block treated as data; the earlier ones were carried verbatim.
  `council_top_schools_grading` printed `MWANZA CC` in its council column on all three pages, thirty
  rows. Fixed for all twelve, declared in `catalog/bindings.yaml` rather than detected — every
  content-based detection attempt misclassified some page.
- `region_ufaulu_masomo` distilled the wrong grid. It is one page of 28-column subject rows followed
  by two pages of 20-column summaries, so the majority-of-pages rule chose the summaries' grid and
  `header.labels` came out as twenty empty strings. Counting rows instead does not separate them
  either — the summary pages carry thirteen full-width rows against page 1's seven.
- Reports whose trailing pages are **blank in the reference** are no longer mistaken for section
  pages: `council-best-students-subjectwise` pages 21–30 and `council-schools-rank-subjectwise` page
  24 extract zero characters.

### Changed

- `render_report` takes the measured path whenever the data keys are a subset of
  `{rows, title, bands, loose}`. The older `header` key still selects the distilled path.



### Added

- **The project is now an installable package.** `pyproject.toml` previously had no
  `[build-system]` at all, so nothing could be built or installed. It now builds a wheel and an
  sdist with `hatchling`, from a `src/mussannoni/` layout.
- **A data-in / PDF-out public API.** `render_report(report_key, data)` takes rows of values as a
  dict and returns PDF bytes, placing them on the report's measured grid — page box, column
  widths, header band, row height, fonts and hairline weight all taken from the reference
  measurement. `render_report_to_file()` writes to a path. `render_document()` remains available
  for reproducing a reference glyph for glyph.
- `list_reports()` and `report_layout()` for discovering the 46 reports and what each expects.
- **Overrides for every measured line that is per-exam data, not layout.** Each report was
  measured from one exam, so its letterhead names that exam's region and the unit it covered. An
  application rendering a different exam has to be able to replace those lines, or it publishes
  the reference exam's region on its own results:
  - a `data["header"]` value may now be a *list of strings*, setting one measured line each. A
    letterhead is a single cell holding several lines, and a scalar would have collapsed them onto
    one baseline; a list keeps each line at its own measured position and re-centres it for its new
    string. Passing fewer strings than there are lines blanks the remainder.
  - `data["loose"]` overrides the absolutely-positioned letterhead lines that several reports draw
    beside the table rather than inside the header band. Those are outside the header's
    `"row.column"` address space and were previously unreachable, so nothing could replace them.
    Addressed by line index; a line centred on the page is re-centred for its new string, and an
    empty value removes it.
- A `mussannoni` console script: `reports`, `layout`, `render` and `doctor` subcommands.
- A distilled `layout.json` per report as package data, reducing a 257 MB corpus of measured
  geometry fixtures to a few KB each — the parts that generalise to new data.
- `tools/package_resources.py` (`make package-resources`) syncs the workshop's measured artifacts
  into the package, with a `--check` mode wired into `make check` and the test suite so the
  committed resources cannot silently go stale.
- A single sample pair in the sdist — `corpus/secondary/school-results.pdf` and the render made
  from it, with its `report.json` metrics — so the fidelity claim is demonstrable from the
  distribution alone. Kept out of the wheel, which is what applications install.
- `LICENSE` (MIT), `CREDITS.md` and `docs/05-packaging.md`.
- 57 tests covering the public API, the registry, resource resolution, engine selection, layout
  flowing and the CLI.

### Changed

- `tools/render.py` now imports its engines from `mussannoni.engines` and its recompression pass
  from `mussannoni.optimize` rather than carrying its own copies. The workshop keeps `chromium` as
  its default engine and keeps rendering from `templates/`; only the shared implementations moved.
- Runtime dependencies narrowed to `jinja2`, `pymupdf` and `weasyprint`. The measurement
  machinery's dependencies (`httpx`, `lxml`, `pillow`, `pyyaml`, `scikit-image`) moved to a
  `workshop` extra.
- The packaged default engine is `weasyprint`; `chromium` needs the `agent-browser` Node binary,
  which `pip` cannot install, and now raises a clear error instead of a traceback when missing.

- The sdist no longer ships `templates/`. `src/mussannoni/resources/` already carries every
  shipped byte of it, so including both duplicated ~24 MB of identical font files — and it could
  not regenerate those resources from an sdist anyway, since that needs the excluded fixtures.
  The sdist drops from 13.3 MB to 9.3 MB even after adding the sample pair.

### Fixed

- **Five of the 46 committed renders had never been recompressed.** The
  earlier optimization pass covered 41 files; `secondary/school-results`,
  `subject-schools-rank`, `region-schools-rank-private`, `region-top-schools` and
  `region-subjects-performance` still had no object streams. Recompressing them took the corpus
  from a 3.4× to a **5.1×** reduction (181,693,210 bytes to roughly 35.6 MB), each verified
  page-count-, geometry- and pixel-identical.
- `README.md` and `docs/01-fidelity.md` claimed the recompression pass used font subsetting and
  `clean=True`. It deliberately uses neither, for measured reasons now recorded alongside the
  claim.
- Columns that are merged away in every measured body row had no cell prototype, so data the
  caller supplied for them was silently dropped. They now borrow the report's modal cell shape.
  Affected `school_results` (both levels), `council_kata_rank_alama`, `council_subject_summary`,
  `region_best_students_subjectwise` and `region_council_performance`.
