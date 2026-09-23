"""
Corpus-wide document-level verification for the measured render path.

Two tests per report, both from docs/06-exametrics-alignment.md section 5:

1. Round trip — recover the reference's own values from the fixture, feed them back
   through build_measured_document, and require the result to equal the fixture.
   Passing means 0 text differences and 0.0000 pt drift with page counts equal.

2. Leak test — supply a distinct marker in every field of every row and require that
   no filled data row retains anything else. This is the test that matters for
   production: a retained value is the reference exam's figure published as this
   exam's own.

Document level only. Nothing is rendered, no service is touched, nothing is written.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import mussannoni
from mussannoni import measured
from mussannoni.resources import layout_payload

ROOT = Path(__file__).resolve().parent


def text_of(cell: dict) -> str:
    return "".join(
        "".join(run.get("text", "") for run in (line.get("runs") or []))
        for line in (cell.get("lines") or [])
    )


def fixture_path(level: str, key: str) -> Path:
    return Path("templates") / level / key.replace("_", "-") / "fixture.json"


def round_trip(level: str, key: str) -> dict:
    """Rebuild the reference from its own values and diff against the fixture."""
    path = fixture_path(level, key)
    if not path.exists():
        return {"skip": "no fixture"}

    fixture = json.loads(path.read_text())
    layout = layout_payload(level, key)
    document = measured.measured_document(level, key)

    fields = layout["header"].get("fields") or []
    named = {index for index, field in enumerate(fields) if field}
    if not named:
        return {"skip": "no column identity"}

    plans = [page.get("data_rows") or [] for page in document["pages"]]
    rows = []
    for page_index, plan in enumerate(plans):
        if page_index >= len(fixture["pages"]):
            continue
        for row_index in plan:
            cells = fixture["pages"][page_index]["rows"][row_index]["cells"]
            rows.append({
                fields[int(cell["column"])]: text_of(cell)
                for cell in cells
                if int(cell["column"]) in named
            })

    built = measured.build_measured_document(document, layout, {"rows": rows})

    diffs = cells = 0
    drift = 0.0
    pages_equal = len(built["pages"]) == len(fixture["pages"])
    row_counts_equal = True
    blanked = survived = 0
    for page_index, (ref_page, new_page) in enumerate(zip(fixture["pages"], built["pages"])):
        if len(ref_page["rows"]) != len(new_page["rows"]):
            row_counts_equal = False
            continue
        # Cells the build marked `figure` or `sample` are deliberately emptied when the caller
        # supplies no value, so they are excluded from the fidelity comparison and asserted
        # separately: one that still holds text is the reference exam's own number or name,
        # published.
        # Addressed per LINE, because a cell may hold a column heading and a figure — the
        # `WASTANI WA SHULE` cells carry a two-line heading plus a measured average, and only the
        # average is blanked. Checking whole-cell text would report those as survivors.
        figures: dict[tuple[int, int], set[int] | None] = {}
        for address, role in (document["pages"][page_index].get("roles") or {}).items():
            # `sample` is reference identity outside the letterhead — a council or school name the
            # reference printed where no field addresses it. Blanked like a figure, so excluded from
            # the fidelity comparison for the same reason.
            if role not in ("figure", "sample"):
                continue
            parts = address.split(".")
            key = (int(parts[0]), int(parts[1]))
            if len(parts) == 2:
                figures[key] = None
            elif figures.get(key, set()) is not None:
                figures.setdefault(key, set()).add(int(parts[2]))
        for row_index, (ref_row, new_row) in enumerate(zip(ref_page["rows"], new_page["rows"])):
            for ref_cell, new_cell in zip(ref_row["cells"], new_row["cells"]):
                key = (row_index, int(new_cell["column"]))
                if key in figures:
                    wanted = figures[key]
                    built_lines = {
                        "".join(run.get("text", "") for run in (line.get("runs") or [])).strip()
                        for line in (new_cell.get("lines") or [])
                    }
                    ref_lines = [
                        "".join(run.get("text", "") for run in (line.get("runs") or [])).strip()
                        for line in (ref_cell.get("lines") or [])
                    ]
                    targets = (
                        ref_lines
                        if wanted is None
                        else [ref_lines[i] for i in sorted(wanted) if i < len(ref_lines)]
                    )
                    for value in targets:
                        if value and value in built_lines:
                            survived += 1
                        else:
                            blanked += 1
                    continue
                cells += 1
                if text_of(ref_cell) != text_of(new_cell):
                    diffs += 1
                for ref_line, new_line in zip(ref_cell.get("lines") or [],
                                              new_cell.get("lines") or []):
                    drift = max(drift, abs(float(ref_line.get("left_pt", 0))
                                           - float(new_line.get("left_pt", 0))))
    return {
        "rows": len(rows),
        "pages": f"{len(built['pages'])}/{len(fixture['pages'])}",
        "cells": cells,
        "diffs": diffs,
        "drift": drift,
        "pages_equal": pages_equal,
        "row_counts_equal": row_counts_equal,
        "blanked": blanked,
        "survived": survived,
        "ok": (pages_equal and row_counts_equal and diffs == 0 and drift < 1e-9
               and survived == 0),
    }


def leak_test(level: str, key: str) -> dict:
    """
    Fill every field of every row with a marker and look for anything else.

    A data cell in a named column that does not carry the marker and is not empty is
    holding a measured value the caller did not supply — the reference exam's own.
    """
    layout = layout_payload(level, key)
    document = measured.measured_document(level, key)
    fields = layout["header"].get("fields") or []
    named = {index for index, field in enumerate(fields) if field}
    if not named:
        return {"skip": "no column identity"}

    plans = [page.get("data_rows") or [] for page in document["pages"]]
    total = sum(len(plan) for plan in plans)
    if not total:
        return {"skip": "no data rows"}

    marker = "ZQX"
    rows = [{field: marker for field in fields if field} for _ in range(total)]
    built = measured.build_measured_document(document, layout, {"rows": rows})

    leaks = []
    checked = 0
    for page_index, page in enumerate(built["pages"]):
        plan = plans[page_index] if page_index < len(plans) else []
        for row_index in plan:
            if row_index >= len(page["rows"]):
                continue
            for cell in page["rows"][row_index]["cells"]:
                if int(cell.get("column", -1)) not in named:
                    continue
                checked += 1
                value = text_of(cell).strip()
                if value and marker not in value:
                    leaks.append((page["number"], row_index, value))
    return {"checked": checked, "leaks": len(leaks),
            "sample": leaks[:3], "ok": not leaks}


def main() -> int:
    reports = mussannoni.list_reports()
    print(f"{len(reports)} reports in the registry\n")

    header = (f"{'level':<9} {'report':<38} {'rows':>5} {'pages':>8} {'cells':>6} "
              f"{'diffs':>5} {'drift':>8}  {'leak':>5} {'blank':>6} {'kept':>5}  result")
    print(header)
    print("-" * len(header))

    passed = skipped = failed = 0
    failures = []
    for report in reports:
        level, key = report.level, report.report_key
        try:
            trip = round_trip(level, key)
            if "skip" in trip:
                print(f"{level:<9} {key:<38} {'':>5} {'':>8} {'':>6} {'':>5} {'':>8}"
                      f"  {'':>5}  SKIP ({trip['skip']})")
                skipped += 1
                continue
            leak = leak_test(level, key)
            leak_cell = "n/a" if "skip" in leak else str(leak["leaks"])
            ok = trip["ok"] and (leak.get("ok", True))
            print(f"{level:<9} {key:<38} {trip['rows']:>5} {trip['pages']:>8} "
                  f"{trip['cells']:>6} {trip['diffs']:>5} {trip['drift']:>8.4f}"
                  f"  {leak_cell:>5} {trip['blanked']:>6} {trip['survived']:>5}"
                  f"  {'PASS' if ok else 'FAIL'}")
            if ok:
                passed += 1
            else:
                failed += 1
                failures.append((level, key, trip, leak))
        except Exception as exc:  # noqa: BLE001 - one bad report must not stop the corpus
            print(f"{level:<9} {key:<38} {'':>5} {'':>8} {'':>6} {'':>5} {'':>8}"
                  f"  {'':>5}  ERROR {type(exc).__name__}: {exc}")
            failed += 1
            failures.append((level, key, {"error": traceback.format_exc()}, {}))

    print(f"\npassed {passed} · failed {failed} · skipped {skipped}")

    if failures:
        print("\n--- failures ---")
        for level, key, trip, leak in failures:
            print(f"\n{level}/{key}")
            if "error" in trip:
                print(trip["error"].strip().splitlines()[-1])
                continue
            print(f"  pages_equal={trip['pages_equal']} "
                  f"row_counts_equal={trip['row_counts_equal']} "
                  f"diffs={trip['diffs']} drift={trip['drift']:.4f} "
                  f"figures_blanked={trip.get('blanked')} figures_survived={trip.get('survived')}")
            if leak.get("leaks"):
                for page, row, value in leak["sample"]:
                    print(f"  LEAK page {page} row {row}: {value[:70]!r}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
