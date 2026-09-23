# 06 — Aligning all 46 reports with ExaMetrics data

Design credit: Mussa Nnoni — SARS (sars.ac.tz).

This is the working document for taking the remaining reports from "renders something" to "renders this
exam's own data on the reference's own geometry". It exists because `school_results` (secondary) was
solved and the method that solved it generalises, while three earlier attempts that did **not**
generalise are recorded here so they are not tried again.

Every number below was measured on 2026-09-23, not estimated. Reproduce any of them with the commands
in [Verification](#verification).

---

## 1. What "aligned" means

A report is aligned when all four hold:

1. **Geometry is the reference's.** Not reconstructed — the report renders from its measured document,
   so every band, per-page column grid, rule, vector and the typography come from the measurement.
2. **Every data cell carries this exam's value**, placed by *column identity*.
3. **No cell carries the reference exam's value.** Not the letterhead, not a summary band, not a
   trailing section, not a row the caller under-filled.
4. **Pagination is the reference's**, because each measured page holds the rows the reference put on it.

Item 3 is the one that fails silently, so it is the one to test first.

---

## 2. The mechanism that works

```
catalog/bindings.yaml          column identity per report, aligned to the measured grid
        │
        ▼
layout.json  header.fields     shipped alongside header.labels
        │
        ▼
document.json.gz               the measured document: every page, band, grid and rule
        │                      per-page `data_rows` — which rows are this table's data
        ▼
measured.build_measured_document(document, layout, data)
        │                      places values by column identity; distributes rows across the
        │                      measured pages; carries everything else verbatim
        ▼
render_document()              the same renderer the fidelity workshop uses
```

`render_report(key, {"rows": …, "bands": …, "title": …}, level=…)` uses this path automatically when the
report has column identity. Rows may be mappings keyed by field name — no positional order, no padding
of the grid's unlabelled edge columns.

### Why a caller's row is placed by column identity, never by row shape

Whether a cell exists in a measured row depends on whether the reference happened to print something
there, so two rows of the same table differ. On `secondary/school-results` page 2, two of thirty-seven
candidate rows have a different cell signature. Keyed on shape those two rows are not recognised as
data and are emitted verbatim — which puts a real candidate from the sample exam into another school's
report. This was observed, not theorised.

Column identity is stable. Every cell in a column that carries a field name is overwritten or blanked,
and a measured row the caller has no values for is removed rather than left standing.

### Which pages belong to the table

The table's pages are those on the **repeating grid**, plus page 1 when it is measured on its own
compound grid — the same rule `distil_layout` uses to choose which grid to distil. Anything else is a
further section the report prints whole, and is carried verbatim.

Three content-based tests were tried for this and all three failed. They are recorded in
[§6](#6-rejected-approaches) so they are not retried.

### Unchanged text is never re-placed

A line whose replacement text equals its measured text keeps its measured offset, its letter spacing and
its per-cluster corrections. Re-placing such a line from font metrics moved the letterhead **193 pt** out
of position, because `header_overrides` supplies all six letterhead lines including the two authority
lines that every caller supplies identically.

Corollary for anything new: **do not recompute what has not changed.**

---

## 3. Per-report status

`cols` = measured columns · `cap` = total rows the reference's own pages hold · `p1` = rows on page 1 ·
`tbl`/`sec` = table pages / further-section pages · `ident` = ships column identity · `src` = backend
row source exists

| # | level | report | cols | cap | p1 | tbl | sec | ident | src | class |
|--:|---|---|--:|--:|--:|--:|--:|:-:|:-:|---|
| 1 | secondary | school_results | 9 | 491 | 26 | 13 | 2 | ✅ | ✅ | **A** (done) |
| 2 | secondary | council_subjects_rank | 15 | 23 | 20 | 2 | 0 | ✅ | ✅ | A |
| 3 | secondary | council_schools_rank | 39 | 65 | 65 | 1 | 0 | ✅ | ✅ | A |
| 4 | secondary | council_wards_rank | 19 | 19 | 19 | 1 | 0 | ✅ | ✅ | A |
| 5 | secondary | council_top_schools | 36 | 30 | 10 | 3 | 0 | ✅ | ✅ | A |
| 6 | secondary | council_best_students | 8 | 50 | 10 | 5 | 0 | ✅ | ✅ | A |
| 7 | secondary | council_best_students_subjectwise | 10 | 200 | 10 | 20 | 10 | ✅ | ❌ | **C** |
| 8 | secondary | council_schools_rank_subjectwise | 15 | 664 | 54 | 23 | 1 | ✅ | ❌ | C |
| 9 | secondary | subject_schools_rank | 17 | 388 | 62 | 6 | 0 | ✅ | ✅ | A |
| 10 | secondary | region_schools_rank_overall | 39 | 393 | 59 | 6 | 0 | ✅ | ✅ | A |
| 11 | secondary | region_schools_rank_government | 39 | 304 | 65 | 4 | 0 | ✅ | ✅ | A |
| 12 | secondary | region_schools_rank_private | 41 | 89 | 65 | 2 | 0 | ✅ | ✅ | A |
| 13 | secondary | region_top_schools | 34 | 60 | 10 | 6 | 0 | ✅ | ✅ | A |
| 14 | secondary | region_best_students_overall | 10 | 90 | 10 | 9 | 0 | ✅ | ✅ | A |
| 15 | secondary | region_best_students_subjectwise | 11 | 230 | 10 | 23 | 0 | ✅ | ❌ | C |
| 16 | secondary | region_council_performance | 38 | 26 | 9 | 3 | 2 | ✅ | ✅ | A + **D** |
| 17 | secondary | region_subjects_performance | 15 | 37 | 24 | 2 | 0 | ✅ | ✅ | A |
| 18 | secondary | region_mobility | 13 | 361 | 53 | 6 | 0 | ✅ | ❌ | C |
| 19 | primary | school_results | 23 | 118 | 37 | 5 | 0 | ✅ | ✅ | A |
| 20 | primary | council_kata_rank_alama | 30 | 0 | 0 | 0 | 2 | ❌ | ✅ | **B** |
| 21 | primary | council_kata_rank_grading | 35 | 19 | 19 | 1 | 0 | ✅ | ✅ | A |
| 22 | primary | council_school_rank_binafsi | 35 | 86 | 48 | 2 | 0 | ✅ | ✅ | A |
| 23 | primary | council_school_rank_serikali | 36 | 85 | 46 | 2 | 0 | ✅ | ✅ | A |
| 24 | primary | council_school_rank_in_grade | 38 | 170 | 64 | 3 | 0 | ✅ | ✅ | A |
| 25 | primary | council_school_rank_ufaulu_alama | 30 | 189 | 41 | 4 | 0 | ✅ | ✅ | A |
| 26 | primary | council_best_students | 24 | 40 | 10 | 4 | 0 | ✅ | ✅ | A |
| 27 | primary | council_top_schools_alama | 21 | 20 | 10 | 2 | 0 | ✅ | ✅ | A |
| 28 | primary | council_top_schools_grading | 36 | 30 | 10 | 3 | 0 | ✅ | ✅ | A |
| 29 | primary | council_top_schools_kimasomo_overall | 36 | 0 | 0 | 0 | 3 | ❌ | ❌ | **B + C** |
| 30 | primary | council_top_schools_kimasomo_serikali | 35 | 0 | 0 | 0 | 3 | ❌ | ❌ | B + C |
| 31 | primary | council_subject_summary | 19 | 0 | 0 | 0 | 1 | ❌ | ❌ | B + C |
| 32 | primary | council_ufaulu_wa_masomo | 28 | 0 | 0 | 0 | 1 | ❌ | ❌ | B + C |
| 33 | primary | region_kata_serikali | 36 | 192 | 58 | 4 | 0 | ✅ | ✅ | A |
| 34 | primary | region_kata_binafsi | 36 | 63 | 58 | 2 | 0 | ✅ | ✅ | A |
| 35 | primary | region_kata_jumla | 36 | 192 | 50 | 4 | 0 | ✅ | ✅ | A |
| 36 | primary | region_shule_bora_jumla | 33 | 30 | 10 | 3 | 2 | ✅ | ✅ | A + D |
| 37 | primary | region_shule_bora_masomo_serikali | 32 | 0 | 0 | 0 | 3 | ❌ | ❌ | B + C |
| 38 | primary | region_shule_bora_masomo_jumla | 33 | 0 | 0 | 0 | 3 | ❌ | ❌ | B + C |
| 39 | primary | region_ufaulu_masomo | 20 | 0 | 0 | 0 | 3 | ❌ | ✅ | B |
| 40 | primary | region_ufaulu_masomo_jumla | 28 | 7 | 7 | 1 | 0 | ✅ | ✅ | A |
| 41 | primary | region_wanafunzi_bora | 23 | 60 | 10 | 6 | 0 | ✅ | ✅ | A |
| 42 | primary | region_shule_serikali | 35 | 927 | 50 | 15 | 0 | ✅ | ✅ | A |
| 43 | primary | region_shule_binafsi | 35 | 236 | 52 | 4 | 0 | ✅ | ✅ | A |
| 44 | primary | region_shule_nafasi_jumla | 38 | 1162 | 62 | 16 | 0 | ✅ | ✅ | A |
| 45 | primary | region_halmashauri_masomo | 34 | 60 | 10 | 6 | 0 | ✅ | ✅ | A |
| 46 | primary | region_halmashauri_jumla | 34 | 40 | 10 | 4 | 0 | ✅ | ✅ | A |

**Totals:** 38 ship column identity · 36 have a backend row source · **34 have both** · 13 carry further
section pages · 8 have neither identity nor a usable plan.

---

## 4. Work classes

### Class A — 34 reports: verify, do not rebuild

These have column identity and a row source. The pipeline already handles them. The work is **only**
verification, per [§5](#verification), and fixing whatever it reports. Do not write per-report code.

Expected per report: 0 text differences and 0.0000 pt drift against the fixture, sections verbatim.

### Class B — 8 reports: column identity missing

Without `header.fields` there is no safe way to place a value, so `cap` is 0 and the measured path
refuses the report. Two distinct causes:

| report | cause |
|---|---|
| `council_kata_rank_alama` | registry has 29 columns, measured grid has 30, and 2 unlabelled columns cannot disambiguate which is unmapped |
| `region_ufaulu_masomo` | registry has 28 columns, measured grid has 20 — the binding matches page 1's grid, not the repeating one |
| `council_top_schools_kimasomo_overall` | no registry entry |
| `council_top_schools_kimasomo_serikali` | no registry entry |
| `council_subject_summary` | no registry entry |
| `council_ufaulu_wa_masomo` | no registry entry |
| `region_shule_bora_masomo_serikali` | no registry entry |
| `region_shule_bora_masomo_jumla` | no registry entry |

Procedure: add the entry to `catalog/bindings.yaml`, one field name per measured column, `""` for a
column the reference draws blank. `len(fields)` **must** equal `len(header.labels)`; the build fails
otherwise, deliberately — do not pad to make it pass. Regenerate, then verify.

For the two count mismatches, resolve against the measurement, not the registry: read
`layout.header.labels` and `layout.body.cells` and decide which measured column each registry name
belongs to. `region_ufaulu_masomo` additionally needs its grid question settled — its binding describing
page 1's grid while the layout describes the repeating one is a symptom, not the disease.

### Class C — 6 reports: no backend row source

`resolve.ROW_QUERIES` has no entry, so there are no rows to place regardless of geometry. Four have
identity already (`council_best_students_subjectwise`, `council_schools_rank_subjectwise`,
`region_best_students_subjectwise`, `region_mobility`) and need only the resolver; the other two are
also Class B.

These are ExaMetrics data-coverage gaps, not package defects. What each needs:

- `*_best_students_subjectwise` — per-subject student ranking
- `council_schools_rank_subjectwise` — a school × subject matrix per page
- `region_mobility` — comparison against a previous exam

Add the resolver in `resolve.py` alongside `ROW_QUERIES`, and any new aggregation in `data.py` where the
other aggregations live. Never in `service.py`.

### Class D — 13 reports: further sections carry reference data

These print additional sections after their main table, on their own grids, and those pages are carried
verbatim — which means they still hold the reference exam's figures. Affected: reports 1, 7, 8, 16, 20,
29, 30, 31, 32, 36, 37, 38, 39. Worst is `council_best_students_subjectwise` with 10 section pages
against 20 table pages.

This is the **largest remaining correctness gap** and it is a live leak, not a cosmetic one. Until it is
closed, a generated report must either supply those sections or omit them; it must not print them as
measured. `s1869_results.pdf` omits them for that reason.

Two things are needed, in order:

1. Column identity for each section, so its cells can be addressed. A section is a table in its own
   right and needs its own entry — extend `catalog/bindings.yaml` to carry per-section fields keyed by
   the section's grid, rather than assuming one grid per report.
2. A resolver for each section's data. Most are aggregates `SchoolAnalysis` / `LocationAnalysis` already
   hold: `secondary/school_results`'s two sections are a division summary
   (`REGIST | ABSENT | SAT | INC | CLEAN | DIV I…`) and a subject analysis
   (`CODE | SUBJECT NAME | F | M | T` per grade), both present in `grades_summary` and
   `division_summary`.

Interim rule until then: **omit** a section whose data cannot be supplied. Printing it is publishing
another school's numbers.

---

## 5. Verification

Verify at **document level**, not by rendering. It is instant, and stricter — it compares every cell and
every measured offset rather than a rasterisation.

The decisive test is a round trip: recover the reference's own values from the fixture, feed them back
through the pipeline, and require the result to equal the fixture.

```bash
cd /root/apis/mussannoni
.venv/bin/python - <<'PY'
import json
from mussannoni import measured
from mussannoni.resources import layout_payload

LEVEL, KEY, DIR = "secondary", "school_results", "school-results"
fx  = json.load(open(f"templates/{LEVEL}/{DIR}/fixture.json"))
lay = layout_payload(LEVEL, KEY)
doc = measured.measured_document(LEVEL, KEY)

fields = lay["header"]["fields"]
named  = {i for i, f in enumerate(fields) if f}
text   = lambda c: "".join("".join(r.get("text", "") for r in (l.get("runs") or []))
                           for l in (c.get("lines") or []))
plans  = [p.get("data_rows") or [] for p in doc["pages"]]

rows = [{fields[int(c["column"])]: text(c)
         for c in fx["pages"][pi]["rows"][i]["cells"] if int(c["column"]) in named}
        for pi, plan in enumerate(plans) for i in plan]

built = measured.build_measured_document(doc, lay, {"rows": rows})

diffs = drift = cells = 0
for rp, bp in zip(fx["pages"], built["pages"]):
    assert len(rp["rows"]) == len(bp["rows"]), "row count changed"
    for rr, br in zip(rp["rows"], bp["rows"]):
        for rc, bc in zip(rr["cells"], br["cells"]):
            cells += 1
            diffs += text(rc) != text(bc)
            for rl, bl in zip(rc.get("lines") or [], bc.get("lines") or []):
                drift = max(drift, abs(float(rl.get("left_pt", 0)) - float(bl.get("left_pt", 0))))
print(f"rows {len(rows)} | pages {len(built['pages'])}/{len(fx['pages'])} "
      f"| cells {cells} | text diffs {diffs} | max drift {drift:.4f} pt")
PY
```

Passing means `text diffs 0`, `max drift 0.0000 pt`, and page counts equal. For
`secondary/school_results` this reports `rows 491 | pages 15/15 | cells 4161 | text diffs 0 | max drift
0.0000 pt`.

Then the leak test, which is the one that matters for production: supply a distinct marker in every
field of every row and assert that no filled data row retains anything else. Across the 38 reports with
identity this currently passes 38/38.

Finally, the package gates:

```bash
make check-resources     # committed resources match the distiller
uv run ruff check .
uv run pytest            # see §7 on the engine test
```

### Do not verify by eye on a rendered PDF

Two defects in this work were missed by exactly that. Comparing only page 1 hid a 29.26 pt error on page
14, and checking that expected strings were *present* hid four candidates being silently dropped.
Compare **all** pages, and compare cell by cell.

---

## 6. Rejected approaches

Do not retry these. Each was implemented, measured, and failed.

| approach | how it failed |
|---|---|
| Reconstruct bands into the distilled layout (`front`, `value_columns`, `body_to_front_column`, `header_row_map`) | A second geometry model maintained alongside the measurement. Superseded by rendering the measured document. |
| Ship geometry uncompressed | 269 MB for 46 fixtures, 36 MB with corrections stripped. Gzipped it is **1.90 MB** against 3.85 MB for the distilled layouts — the original "too big to ship" reasoning was simply never tested. |
| Identify data rows by cell signature | Cell presence is content-dependent. Leaked `S0333-0027 ESTER PASCHAL BISEKO` into another school's report. |
| Identify sections by grid equality | Excluded page 1, whose 11 columns are a subdivision of the table's 9. |
| Identify sections by grid subdivision | `school_results` page 14's 24-column grid contains every table edge, so it passed and was overwritten. |
| Identify sections by label-row text | A candidate row with no numeric field looked like a label row, which killed pages 3–13. |
| Derive page capacity by dividing available height | Gives 43 rows where the reference demonstrably fits 39. Capacity is counted from the reference, never computed. |
| Re-place text from font metrics | Moved the letterhead 193 pt. Unchanged text must keep its measurement. |

The common thread: **every time judgement was substituted for measurement, it produced a wrong report.**
When a signal is not in the measurement, add it to the measurement — `catalog/bindings.yaml` — rather
than inferring it at build or render time.

---

## 7. Known constraints

**Engine.** The corpus originals and `output/**/rendered.pdf` are Chromium renders
(`report.json` → `"engine": "chromium (headless, print-to-pdf)"`), and every calibration was fitted
against Chromium. WeasyPrint carries a uniform sub-point vertical offset — measured at +1.0 to +1.6 pt on
`school_results` page 1 — which is invisible in print but is the difference between "looks right" and
"passes the fidelity gate". On this host neither Chromium path runs: `agent-browser`'s daemon fails, and
snap Chromium is blocked by an AppArmor DBus policy. Direct invocation *does* still write a valid PDF,
so `engines.ChromiumCliEngine` is close to working; it needs a work directory outside snap's private
`/tmp`. That engine is uncommitted and out of scope here, and it is the sole `pytest` failure
(`test_packaged_default_engine_is_weasyprint` asserts two engines, not three).

**Rendering cost.** A full 15-page render takes well over a minute under WeasyPrint. Verify at document
level; render only to inspect a final artifact.

**Backend uses the installed package.** `backend-sis/venv` resolves `mussannoni` to the installed 0.1.0,
not the working tree, so production renders the old behaviour until the package is reinstalled and
`celery` restarted. Both are deployment actions and belong to the user.

**Two names per school, and they are not interchangeable.** `data.py::_sname()` strips the trailing
` SS`/` PS` for the table's narrow school-name column. The letterhead needs the full name: take
`ExamSchool.school_name` un-stripped and pass it through the existing
`app/services/necta/school_profile_narrative.py::_expand_school_name()`, which maps `\bSS\b` →
`SECONDARY SCHOOL` and `\bPS\b` → `PRIMARY SCHOOL`. Using the column form in the letterhead produced
`S1869 - IGOGO` where the reference has `S0333 - MWANZA SECONDARY SCHOOL`. `service.py::scope_title_for`
still has this bug, so it affects every school artifact.

---

## 8. Order of work

1. **Class A verification sweep** — 34 reports, document level. Fixes whatever it finds. No new code
   expected; anything it does find is a generalisation bug worth having.
2. **Class D, `secondary/school_results` first** — it has only 2 section pages and both aggregates are
   already in `SchoolAnalysis`. Solving it establishes the per-section identity shape for the other 12.
3. **Class B, the 6 reports with no registry entry** — pure data entry into `catalog/bindings.yaml`,
   verified by the build's own length check.
4. **Class B, the 2 count mismatches** — resolve against the measurement; `region_ufaulu_masomo` needs
   its grid question answered.
5. **Class C** — 4 resolvers in `resolve.py`, aggregations in `data.py`.
6. **Backend reduction** — with identity shipped, delete `bindings.py` (1306 lines), `headers.py` (407),
   `_positional_rows`, `binding_matches_layout`, and both `SAMPLE_LOCATIONS`. Fix `scope_title_for`.

Nothing in steps 1–5 requires a migration, a service restart or a frontend deploy.
