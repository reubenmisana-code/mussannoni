# MussaNnoni Report Conversion — Specification

Design credit: Mussa Nnoni — SARS (sars.ac.tz).

## Goal

Reproduce every SARS report as an HTML + CSS template that renders to a PDF
**visually identical** to the original. The original PDFs are the reference; our
templates are the product. Success is measured by page-for-page comparison, not
by "looks close".

Two sources define the whole corpus — one secondary exam, one primary exam, both
2026 Mwanza / Mwanza CC:

| Level | Exam | URL |
|-------|------|-----|
| SECONDARY | Form Two Mock Result 2026 | `https://sars.ac.tz/results/exam/form-two-mock-result/2026/mwanza/mwanza-cc-1787231849` |
| PRIMARY | Matokeo Darasa la IV Mock Mkoa 2026 | `https://sars.ac.tz/results/exam/matokeo-darasa-la-iv-mock-mkoa/2026/mwanza/mwanza-cc-1787231849` |

Each page exposes three blocks: **School List**, **District Summaries**,
**Regional Summaries**. Every link is a `view-results?file=<key>.pdf&name=<label>`
redirect to a stored PDF — `results/pdfs/…` for schools, `summaries/…` for
summaries.

## The deduplication rule (this is the whole point)

The two pages carry **330 links** but only **46 distinct layouts** — 284
redundant PDFs of identical structure with different numbers in them. A layout is
identified by *what it is*, never by whose data was in the sample.

Link budget as published:

| Block | Secondary | Primary | Total |
|-------|-----------|---------|-------|
| School list | 64 | 170 | 234 |
| District summaries | 7 | 13 | 20 |
| Regional summaries | 48 | 28 | 76 |
| **Links** | **119** | **211** | **330** |
| **Distinct layouts** | **18** | **28** | **46** |

Collapse in this order:

1. **Schools — 234 links → 2 PDFs.** Every school results PDF on a level shares
   one layout. Take **one school per level** and stop. (Secondary: 64 schools.
   Primary: 170 schools.)
2. **Per-subject reports — 36 links across 22 subjects → 1 PDF.**
   `SCHOOL RANK-<SUBJECT>` is published once per subject offered — Mathematics,
   Biology, Kiswahili, Chemistry, EDK, HTM, Fine Art, Agriculture, BKeeping,
   Busines Studies, Bible Knowledge, Computer Science, Chines Language, English
   Language, Food, French Language, Geography, History, Music, Physics, Sport
   Studies, Theatre Arts — 22 distinct subjects, 14 of them listed twice. One
   subject's report *is* the template for all of them; the subject name is data,
   not layout. Take **Mathematics only**.
3. **Republished duplicates — drop the second copy.** Both pages list the same
   report twice under different object keys (the secondary regional block
   repeats most of its list; every primary regional entry appears exactly twice).
   Dedup by display name, keep the first key.
4. **Government / Private / Overall variants — download all three, then verify.**
   `SCHOOLS RANK OVERALL`, `SCHOOLS RANK FOR GOVERNMENTS`, `SCHOOL RANK FOR
   PRIVATES` are probably one layout with a different row filter. Confirm by
   diffing the converted HTML; if identical, keep one template and alias the
   other two to it. Do not assume before diffing.

Net corpus: **18 secondary + 28 primary = 46 PDFs.**

This count is not a coincidence. `app/services/exametrics/mussannoni/registry.py`
already declares 18 `SECONDARY_REPORTS` and 28 `PRIMARY_REPORTS`, and the keys
line up one-for-one with the live page. The registry is correct and complete —
this conversion fills in the templates behind it, it does not redesign it.

## Download manifest

Order matters: one school first, then council, then region. Prove the pipeline on
the hardest layout (school results — the widest grid) before scaling out.

### SECONDARY — 18

**Phase 1 · school (1)**

| # | `report_key` | Sample to take |
|---|--------------|----------------|
| 1 | `school_results` | `S0333 – MWANZA SECONDARY SCHOOL` |

**Phase 2 · council, scope `MWANZA CC` (7)**

| # | `report_key` | Page label |
|---|--------------|------------|
| 2 | `council_subjects_rank` | SUBJECTS RANK |
| 3 | `council_schools_rank` | SCHOOLS RANK |
| 4 | `council_wards_rank` | WARDS RANK |
| 5 | `council_top_schools` | 10 BEST SCHOOLS |
| 6 | `council_best_students` | 10 BEST STUDENTS |
| 7 | `council_best_students_subjectwise` | 10 BEST STUDENTS SUBJECTWISE |
| 8 | `council_schools_rank_subjectwise` | SCHOOLS RANK SUBJECTWISE |

**Phase 3 · subject scope (1) + region scope, `MWANZA` (9)**

| # | `report_key` | Page label | Note |
|---|--------------|------------|------|
| 9 | `subject_schools_rank` | SCHOOL RANK-MATHEMATICS | stands for all 22 subjects |
| 10 | `region_schools_rank_overall` | SCHOOLS RANK OVERALL | |
| 11 | `region_schools_rank_government` | SCHOOLS RANK FOR GOVERNMENTS | diff against #10 |
| 12 | `region_schools_rank_private` | SCHOOL RANK FOR PRIVATES | diff against #10 |
| 13 | `region_top_schools` | TOP 10 SCHOOLS | |
| 14 | `region_best_students_overall` | BEST STUDENTS-OVERALL | |
| 15 | `region_best_students_subjectwise` | BEST STUDENTS-SUBJECTWISE | |
| 16 | `region_council_performance` | F2 DISTRICT PERFORMANCE | |
| 17 | `region_subjects_performance` | OVERALL SUBJECTS PERFORMANCE | |
| 18 | `region_mobility` | F2 MOCK MOBILITY 2026 | |

### PRIMARY — 28

Swahili report names below are reproduced verbatim from the SARS site. They are
the originals and stay as-is; no new Swahili is introduced anywhere else.

**Phase 1 · school (1)**

| # | `report_key` | Sample to take |
|---|--------------|----------------|
| 19 | `school_results` | `PS1304014 – BUTIMBA PRIMARY SCHOOL` |

**Phase 2 · council, scope `MWANZA CC` (13)**

| # | `report_key` | Page label |
|---|--------------|------------|
| 20 | `council_kata_rank_alama` | KATA RANK ALAMA |
| 21 | `council_kata_rank_grading` | KATA RANK GRADING |
| 22 | `council_school_rank_binafsi` | SCHOOL RANK BINAFSI |
| 23 | `council_school_rank_serikali` | SCHOOL RANK SERIKALI |
| 24 | `council_school_rank_in_grade` | SCHOOL RANK IN GRADE |
| 25 | `council_school_rank_ufaulu_alama` | SCHOOL RANK UFAULU ALAMA |
| 26 | `council_best_students` | 10 BEST STUDENTS |
| 27 | `council_top_schools_alama` | 10 BEST SCHOOLS ALAMA |
| 28 | `council_top_schools_grading` | 10 BEST SCHOOLS GRADING |
| 29 | `council_top_schools_kimasomo_overall` | 10 BEST SCHOOLS KIMASOMO OVERALL |
| 30 | `council_top_schools_kimasomo_serikali` | 10 BEST SCHOOLS KIMASOMO SERIKALI |
| 31 | `council_subject_summary` | SUBJECT SUMMARY |
| 32 | `council_ufaulu_wa_masomo` | UFAULU WA MASOMO |

**Phase 3 · region, scope `MWANZA` (14)**

Every one of these is listed twice on the page under two object keys. Keep the
first, discard the second.

| # | `report_key` | Page label |
|---|--------------|------------|
| 33 | `region_kata_serikali` | MKOA KATA SHULE ZA SERIKALI STD4 2026 |
| 34 | `region_kata_binafsi` | MKOA KATA SHULE BINAFSI STD4 2026 |
| 35 | `region_kata_jumla` | KATA STD4 JUMLA 2026 |
| 36 | `region_shule_bora_jumla` | MKOA SHULE BORA STD4 JUMLA 2026 |
| 37 | `region_shule_bora_masomo_serikali` | MKOA SHULE BORA MASOMO SERIKALI STD4 2026 |
| 38 | `region_shule_bora_masomo_jumla` | MKOA SHULE BORA MASOMO STD4 JUMLA 2026 |
| 39 | `region_ufaulu_masomo` | MKOA UFAULU MASOMO STD4 2026 |
| 40 | `region_ufaulu_masomo_jumla` | MKOA UFAULU MASOMO STD4 JUMLA 2026 |
| 41 | `region_wanafunzi_bora` | MKOA WANAFUNZI BORA STD4 2026 |
| 42 | `region_shule_serikali` | SHULE SERIKALI STD4 2026 |
| 43 | `region_shule_binafsi` | SHULE BINAFSI STD4 2026 |
| 44 | `region_shule_nafasi_jumla` | SHULE NAFASI STD4 JUMLA 2026 |
| 45 | `region_halmashauri_masomo` | HALMASHAURI MASOMO STD4 2026 |
| 46 | `region_halmashauri_jumla` | HALMASHAURI STD4 JUMLA 2026 |

### Not in the corpus

**Zone scope.** `registry.applicable()` emits zone reports only when an exam
spans two or more regions. Mwanza is a single region, so no zone sample exists
and none can be converted from this corpus. That is a known, recorded gap — it
must not be faked by widening a region template.

## Repository structure

One report converts to one directory. Everything needed to prove that report is
correct lives in that directory, so a report can be reviewed, re-cut, or deleted
on its own.

```
mussannoni/
├── README.md                       what this is, how to run it, conversion status table
├── Makefile                        fetch / convert / render / verify / report
├── pyproject.toml                  pinned deps: httpx, pymupdf, lxml, jinja2, pillow, pytest
├── .gitignore                      work/, *.local.*  — never the corpus or the outputs
│
├── catalog/
│   ├── reports.yaml                the 46 entries: key, level, scope, title, source URL,
│   │                               object key, sample unit, status, aliases
│   ├── subjects.yaml               subjects per level — the dedup evidence for rule 2
│   └── dedup.md                    which links collapsed into which entry, and why
│
├── corpus/                         REFERENCE — read-only, never edited, committed
│   ├── secondary/
│   │   ├── school-results.pdf
│   │   ├── council-subjects-rank.pdf
│   │   ├── region-schools-rank-overall.pdf
│   │   └── …                       18 files, named by report_key
│   ├── primary/
│   │   └── …                       28 files
│   └── MANIFEST.json               sha256 + byte size + page count + fetch timestamp
│
├── extract/                        what the PDF actually contains — machine-read, not typed
│   ├── secondary/school-results/
│   │   ├── spans.json              every text span: text, x, y, font, size, weight, colour
│   │   ├── rules.json              every line and filled rect: x0,y0,x1,y1, width, colour
│   │   ├── geometry.json           page size, margins, column x-edges, row pitch, header bands
│   │   ├── fonts.json              embedded fonts → local face + fallback
│   │   └── page-01.png             300 dpi raster, the visual baseline
│   └── …                           one directory per report
│
├── templates/                      THE PRODUCT
│   ├── _shared/
│   │   ├── reset.css               page box, @page size/margin, zero-default table
│   │   ├── tokens.css              measured values only — font stack, sizes, rules, pitch
│   │   ├── grid.css               column-width primitives keyed to measured x-edges
│   │   ├── header.html             exam title / scope line / logo block
│   │   ├── footer.html             page x of y, generated-on, closing block
│   │   └── fonts/                  woff faces + LICENSE for each
│   ├── secondary/
│   │   ├── school-results/
│   │   │   ├── template.html       Jinja2 — structure and slots, no literal sample data
│   │   │   ├── report.css          only what this report adds over _shared
│   │   │   ├── bindings.yaml       column → canonical field, formats, alignment, widths
│   │   │   └── fixture.json        data scraped from the reference, for rendering a diffable proof
│   │   └── …
│   └── primary/ …
│
├── output/                         generated — committed so a diff is reviewable
│   ├── secondary/school-results/
│   │   ├── rendered.pdf            template + fixture, through the real engine
│   │   ├── rendered-page-01.png    300 dpi, same raster settings as the reference
│   │   ├── diff-page-01.png        red = our pixels, blue = reference pixels
│   │   └── report.json             per-page ssim, pixel delta %, text-position max drift
│   └── …
│
├── tools/
│   ├── fetch.py                    resolve view-results → object key → PDF, honour catalog dedup
│   ├── extract.py                  PyMuPDF → spans/rules/geometry/fonts/raster
│   ├── measure.py                  spans → column edges, row pitch, font sizes, margins
│   ├── scaffold.py                 measurements → first-cut template.html + report.css
│   ├── render.py                   template + fixture → PDF (same engine as production)
│   ├── compare.py                  reference vs rendered → ssim, delta, drift, diff image
│   └── status.py                   regenerate the README status table from output/*/report.json
│
├── docs/
│   ├── 00-approach.md              the convert-one-at-a-time loop, and why
│   ├── 01-fidelity.md              acceptance thresholds and how they are measured
│   ├── 02-geometry.md              how column edges and row pitch are derived from spans
│   ├── 03-fonts.md                 embedded-font identification and substitution decisions
│   └── 04-integration.md           promoting a finished template into backend-sis
│
└── tests/
    ├── test_catalog.py             330 links dedup to 46 entries; no key collisions
    ├── test_templates.py           every template parses; every binding field is canonical;
    │                               no literal sample value from the reference survives
    └── test_fidelity.py            every report marked done still meets threshold
```

### Why this shape

- **`corpus/` is read-only input, never source.** It is committed so conversions
  are reproducible, and it is never edited. Editing a reference to make a
  template pass is the one failure that invalidates the whole exercise.
- **`extract/` is machine-read, never hand-typed.** Column positions and font
  sizes come out of PyMuPDF. Eyeballing a PDF and typing `width: 72px` is how
  drift gets in.
- **`output/` is committed.** A pixel diff is only useful if a reviewer can see
  it in the pull request without running anything.
- **Templates carry no sample values.** `fixture.json` holds the reference's
  numbers for proof-rendering; `template.html` holds only slots. This mirrors the
  rule already enforced in `mussannoni/service.py`: a report with no binding is
  skipped, never rendered, because rendering it would print the reference's own
  figures as if they were live results.
- **Naming is by identity, not by sample.** `council-subjects-rank`, never
  `mwanza-cc-subjects-rank`. Mwanza was the source of the sample; it is not part
  of any report's identity.

## The conversion loop

One report at a time, fully finished before the next starts. A half-converted
report is worth nothing, and forty half-converted reports are worth less.

```
1  fetch      tools/fetch.py <key>       → corpus/<level>/<key>.pdf + MANIFEST entry
2  extract    tools/extract.py <key>     → extract/<level>/<key>/{spans,rules,geometry,fonts}.json
                                          + page-NN.png at 300 dpi
3  measure    tools/measure.py <key>     → column x-edges, row pitch, font sizes, margins,
                                          header/footer bands. Read from spans — never guessed.
4  scaffold   tools/scaffold.py <key>    → first-cut template.html + report.css from step 3
5  bind       edit bindings.yaml         → each column mapped to a canonical field,
                                          with format, alignment, width
6  fixture    edit/generate fixture.json → the reference's own rows, for proof-rendering only
7  render     tools/render.py <key>      → output/.../rendered.pdf via the production engine
8  compare    tools/compare.py <key>     → ssim, pixel delta, text drift, diff-page-NN.png
9  iterate    adjust report.css only     → repeat 7–8 until thresholds pass
10 record     tools/status.py            → flip catalog status to done, refresh README table
```

Step 9 adjusts **CSS**, not the reference and not the thresholds.

### Order

`school_results` converts first on each level. It is the widest grid, the most
page-break-sensitive, and the only report that repeats per school — so it
exercises pagination, column compression, and header repetition all at once.
Whatever `_shared/` primitives it needs, every later report reuses. Council
reports follow (narrower, single-table, footer totals), then region reports
(mostly council variants of the same shapes).

## Fidelity criteria

A report is `done` only when, on **every** page:

| Check | Threshold |
|-------|-----------|
| Page count | exactly equal to the reference |
| Page size and orientation | exactly equal |
| Structural similarity (SSIM) | ≥ 0.98 |
| Differing pixels at 300 dpi | ≤ 0.5% |
| Text baseline / left-edge drift | ≤ 1.0 pt for every span |
| Table column x-edges | ≤ 0.5 pt from reference |
| Row count per page and break positions | identical |
| Rule weights and colours | identical |

Anything short of that is `wip`, whatever it looks like at a glance.

Font substitution is the one permitted deviation, and only when the embedded
face cannot be licensed or extracted. It must be recorded in `docs/03-fonts.md`
with the measured drift it introduces — never silently swapped.

## Rendering engine

Render with the same engine production uses, or the comparison proves nothing.
`mussannoni/pdf.py` supports two:

- **`chromium`** — `chromium-browser --headless --print-to-pdf`. The reference
  renderer for CSS fidelity and the house default.
- **`weasyprint`** — in-process, much smaller files, but its CSS support differs.

Convert and verify against **chromium** first. If a template also needs to hold
up under weasyprint, that is a second, separately recorded verification — a pass
on one engine is not a pass on the other.

Note the snap-confinement trap already documented in `pdf.py`:
`/usr/bin/chromium-browser` is the snap build and gets a private `/tmp`, so
writing a PDF there reports success while the host sees nothing. All Chromium
work must happen in a working directory under the project tree.

## Integration back into backend-sis

This repo is a **conversion workshop**, not a runtime dependency. Nothing in
`backend-sis` imports it. A finished template is promoted by copying:

- `templates/<level>/<key>/template.html` → the path
  `registry.ReportDef.template` already resolves to
  (`<level>/<key-with-dashes>.html`)
- `templates/_shared/*.css` and `_shared/fonts/*` → the assets bundle served
  alongside generated reports
- `bindings.yaml` → the column binding the resolver consumes

`fixture.json`, `corpus/`, `extract/`, and `output/` never ship. They are
evidence, not product.

## Status tracking

`catalog/reports.yaml` carries one status per report and `tools/status.py`
renders it into the README:

| status | meaning |
|--------|---------|
| `todo` | not fetched |
| `fetched` | reference in corpus, not yet extracted |
| `extracted` | measurements available, no template |
| `wip` | template renders, thresholds not met |
| `done` | all fidelity checks pass, recorded in `output/<key>/report.json` |
| `blocked` | cannot proceed — no sample exists (zone scope), or font unobtainable |
| `alias` | identical layout to another key; points at it, carries no template |

Progress is counted in `done`, never in "templates written".
