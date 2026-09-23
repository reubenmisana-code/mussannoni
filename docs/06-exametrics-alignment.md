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

Item 4 has one deliberate exception, for trailing sections. A **section must not be forced onto a new
page** — it follows immediately after the table before it. The reference puts `school_results`'s summary
on page 14 only because 491 candidates filled 13 pages first; a school with 44 candidates ends its
candidate table partway down page 2, and the section belongs there. Section placement is flow-relative
to where the data ended; the section's own grid, band and typography stay exactly as measured.
Relatedly, the blue background belongs to the whole report **wherever there is data** — a generated
report with fewer rows than the reference carries it across its own data extent, and not over empty
rows.

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
| 7 | secondary | council_best_students_subjectwise | 10 | 200 | 10 | 20 | 0† | ✅ | ❌ | **C** |
| 8 | secondary | council_schools_rank_subjectwise | 15 | 664 | 54 | 23 | 0† | ✅ | ❌ | C |
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

**Totals:** 38 ship column identity · 36 have a backend row source · **34 have both** · 11 carry real
further-section pages · 8 have neither identity nor a usable plan.

† **Re-measured 2026-09-23: these two carry no section pages at all.** Their trailing pages are
**blank in the reference PDF itself** — `council_best_students_subjectwise` pages 21–30 and
`council_schools_rank_subjectwise` page 24 extract 0 characters, and the fixture correctly records 0
rows for each. The build drops them, which is why the round trip reports 20/30 and 23/24 pages. This
is correct behaviour on a correct measurement, not a defect. An earlier revision of this table counted
them as section pages and named report 7 the worst Class D case; that was wrong on both counts.

---

## 4. Work classes

### Class A — 34 reports: verify, do not rebuild

These have column identity and a row source. The pipeline already handles them. The work is **only**
verification, per [§5](#verification), and fixing whatever it reports. Do not write per-report code.

Expected per report: 0 text differences and 0.0000 pt drift against the fixture, sections verbatim.

### Class B — 8 reports: column identity missing

Without `header.fields` there is no safe way to place a value, so `cap` is 0 and the measured path
refuses the report. **Re-measured 2026-09-23 against every page of all 8**, the cause is neither one
shared gap nor registry data entry. It is three distinct causes:

| group | reports | cause |
|---|---|---|
| **1 — repeated blocks per page** | `council_top_schools_kimasomo_overall` (36 cols) · `council_top_schools_kimasomo_serikali` (35) · `region_shule_bora_masomo_serikali` (32) · `region_shule_bora_masomo_jumla` (33) | They **do** have a repeating table. Each page carries **several 10-row blocks**, each repeating its own full-width label row, and the distiller's single-label-row model cannot express that — so it marked nothing as data. Measured label-row positions `[3,17]` / `[2,8,22]` / `[2,6,20]` with 20 data rows per page, totalling **60 = 6 subjects × 10 schools**, blocks spanning page boundaries. |
| **2 — layout took the wrong grid** | `region_ufaulu_masomo` | `header.labels` holds 20 entries and **all are empty**, because the layout latched onto pages 2–3's 20-column compound grid. The real table is page 1's 28-column subject list, label row `NA │ SOMO │ WAV │ WAS │ JML │ …`, numbered subject rows beneath. The binding is right; the layout is wrong. |
| **3 — genuinely no repeating table** | `council_subject_summary` (1 page, 19 cols) · `council_ufaulu_wa_masomo` (1 page, 28) · `council_kata_rank_alama` (2 pages) | Fixed-shape compound summary sheets whose content is aggregates split by sex (`WAV`/`WAS`/`JML`) nested in several mini-tables per page — not a variable-length row list. `council_kata_rank_alama`'s page 2 does carry a real 29-column label row, but the sample has only the `JUMLA` totals row beneath it, so `cap` 0 is **correct** for it. Its `header.labels` is a **data row** (`'01','HISABATI','0','0.0',…,'DARAJA C (VIZURI)'`) — the actual cause of the 29-vs-30 mismatch. |

So the work is one distiller change for group 1 (four reports, no hand-typed bindings), one grid choice
for group 2, and group 3 handed to the roles/bands contract rather than given an invented table.

Where a binding *is* added the rule stands: one field name per measured column, `""` for a column the
reference draws blank. `len(fields)` **must** equal `len(header.labels)`; the build fails otherwise,
deliberately — do not pad to make it pass. Regenerate, then verify.

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

### Class D — 3 reports: further sections carry reference data

Re-measured 2026-09-23 by classifying every page of all 46 measured documents as *table* (has
`data_rows`), *section* (no `data_rows` but has rows) or *blank* (no rows at all). The result is
smaller and sharper than the earlier estimate of 13:

| shape | count | reports |
|---|--:|---|
| table pages **and** trailing section pages | **3** | `secondary/school_results` (14,15) · `secondary/region_council_performance` (4,5) · `primary/region_shule_bora_jumla` (4,5) |
| every page is a section, no table page at all | 8 | exactly the Class B set — see below |
| trailing **blank** pages only | 2 | reports 7 and 8; nothing to do |

**The 8 "all sections" reports are the same 8 that lack column identity.** That is not a coincidence
and it reframes Class B: those reports have `cap` 0 because no page of their measured document is a
table page, so there is nothing for a field list to address yet. Fixing them is a question of deciding
what their repeating grid *is*, not of typing names into a registry. `council_kata_rank_alama` (2
pages), `council_top_schools_kimasomo_overall` (3), `council_top_schools_kimasomo_serikali` (3),
`council_subject_summary` (1), `council_ufaulu_wa_masomo` (1), `region_shule_bora_masomo_serikali` (3),
`region_shule_bora_masomo_jumla` (3), `region_ufaulu_masomo` (3).

For the 3 mixed-shape reports the leak is confirmed, not inferred. Filling every data row of
`secondary/school_results` with a marker leaves page 14 carrying 320 non-empty cells and **zero**
markers, among them `MWANZA`, `MWANZA CC`, `TOTAL PASSED CANDIDATES 434`, `EXAMINATION CENTRE GPA
4.1593` and `RANKING COUNCILWISE 58 / 64`. `region_council_performance` pages 4–5 carry the full
`MWANZA REGION` letterhead plus two district tables; `region_shule_bora_jumla` pages 4–5 the same in
Swahili.

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

### Corpus-wide sweep result, 2026-09-23

Both tests were run over all 46 reports. Outcome: **36 pass** with `text diffs 0` and `max drift
0.0000 pt`, **2 "fail" on page count alone** (reports 7 and 8, entirely from the reference's own blank
trailing pages — see the † note in §3), and **8 skip** for no column identity (the Class B set). No
report showed a single text difference, any drift, or any leak in a named column. Largest verified:
`primary/region_shule_nafasi_jumla` at 1162 rows over 16 pages and 45,178 cells.

So the measured path generalises across the whole corpus, and the remaining work is entirely the three
named gaps — section data (Class D, 3 reports), column identity (Class B, 8), row sources (Class C, 6)
— not per-report placement bugs.

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

**Dependency discovered 2026-09-23 — the backend reduction cannot come last by itself.**
`api.py::render_report` falls back to the distilled `build_document` in two cases: a report with no
column identity, and **any caller passing data keys outside `{rows, title, bands}`** — which is every
caller using the documented `header` and `loose` overrides. So deleting the distilled path requires
*both* column identity for all 46 *and* a bands contract that covers those overrides. It is the last
step of the thread, not the first.

1. **Class A verification sweep** — done, `tools/verify_alignment.py`. 36 pass with 0 diffs and 0.0000 pt
   drift, 2 blank-page artifacts, 8 skipped. Re-run it after every change below.
2. **Class B group 1 + 2** — one distiller change for the four repeated-block reports, one grid choice
   for `region_ufaulu_masomo`. This is what unblocks deleting the approximation.
3. **Roles and the bands contract** — covers Class B group 3 and the `header`/`loose` override callers.
4. **Class D, `secondary/school_results` first** — 2 section pages, both aggregates already in
   `SchoolAnalysis`. Solving it establishes the per-section identity shape for the other two. Note the
   section must **flow** after the data rather than start a new page, per §1.
5. **Class C** — 4 resolvers in `resolve.py`, aggregations in `data.py`.
6. **Delete the approximation, then the backend reduction** — `_transplanted_header`, `_remap_row`,
   `_rows_per_page`, `_synthesise_rules` and the `front`/`first_page_rows`/`rows_per_page` keys; then
   `bindings.py` (1306 lines), `headers.py` (407), `_positional_rows`, `binding_matches_layout` and both
   `SAMPLE_LOCATIONS`. Fix `scope_title_for`.

Nothing in steps 1–5 requires a migration, a service restart or a frontend deploy.
