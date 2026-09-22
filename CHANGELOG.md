# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
