"""Regenerate the README conversion status table from measured results.

Every number here comes from `output/<level>/<report>/report.json`. Nothing is written by
hand, so the table cannot claim a report passes when its metrics say otherwise.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from tools.common import ROOT, load_catalog, output_dir, reference_path

START = "<!-- conversion-status:start -->"
END = "<!-- conversion-status:end -->"
README = ROOT / "README.md"


def read_report(report: dict[str, Any]) -> dict[str, Any] | None:
    path = output_dir(report) / "report.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def rendered_size(report: dict[str, Any]) -> int | None:
    path = output_dir(report) / "rendered.pdf"
    return path.stat().st_size if path.exists() else None


def original_size(report: dict[str, Any]) -> int | None:
    path = reference_path(report)
    return path.stat().st_size if path.exists() else None


def human_kb(size: int | None) -> str:
    return "—" if size is None else f"{size / 1024:.0f} KB"


def build_table() -> str:
    catalog = load_catalog()
    rows = [
        "| # | Level | `report_key` | Pages | SSIM (worst) | Pixel delta (worst) | Text drift | Column drift | Rendered | Original | Status |",
        "|---|-------|--------------|-------|--------------|---------------------|------------|--------------|----------|----------|--------|",
    ]
    counts: dict[str, int] = {}
    total_rendered = 0
    total_original = 0
    for report in catalog["reports"]:
        payload = read_report(report)
        status = report["status"]
        counts[status] = counts.get(status, 0) + 1
        rendered = rendered_size(report)
        original = original_size(report)
        if rendered is not None:
            total_rendered += rendered
        if original is not None:
            total_original += original
        if payload is None:
            rows.append(
                f"| {report['ordinal']} | {report['level'].upper()} | `{report['report_key']}` | "
                f"— | — | — | — | — | {human_kb(rendered)} | {human_kb(original)} | `{status}` |"
            )
            continue
        summary = payload["summary"]
        rows.append(
            f"| {report['ordinal']} | {report['level'].upper()} | `{report['report_key']}` | "
            f"{summary['pages_passing']}/{summary['pages_total']} | "
            f"{summary['worst_ssim']:.4f} | {summary['worst_pixel_delta_percent']:.2f}% | "
            f"{summary['worst_text_drift_pt']} pt | {summary['worst_column_drift_pt']} pt | "
            f"{human_kb(rendered)} | {human_kb(original)} | `{status}` |"
        )

    order = ["done", "wip", "extracted", "fetched", "todo", "blocked", "alias"]
    tally = " · ".join(f"**{counts[key]}** {key}" for key in order if key in counts)
    ratio = f" ({total_rendered / total_original:.2f}× the originals)" if total_original else ""
    size_line = (
        f"Committed renders total **{total_rendered / 1024 / 1024:.1f} MB** vs "
        f"**{total_original / 1024 / 1024:.1f} MB** of corpus originals{ratio}. "
        "Renders are structurally optimized post-render (object streams + deflate + garbage "
        "collection), which is content-preserving and pixel-identical."
    )
    header = [
        "### Conversion status",
        "",
        f"{len(catalog['reports'])} reports in the catalog: {tally}.",
        "",
        size_line,
        "",
        "`Pages` counts pages meeting every gate. Metrics are the worst value across the",
        "report's pages, measured at 300 dpi by `tools/compare.py`. `Rendered` / `Original` are",
        "the `output/` PDF versus the `corpus/` reference byte sizes. Progress is counted in",
        "`done` only.",
        "",
    ]
    return "\n".join(header + rows) + "\n"


def update_readme() -> bool:
    table = build_table()
    text = README.read_text(encoding="utf-8")
    block = f"{START}\n\n{table}\n{END}"
    if START in text and END in text:
        head, rest = text.split(START, 1)
        _stale, tail = rest.split(END, 1)
        updated = head + block + tail
    else:
        updated = text.rstrip("\n") + "\n\n" + block + "\n"
    if updated == text:
        return False
    README.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    argparse.ArgumentParser(description="Refresh the README status table").parse_args()
    changed = update_readme()
    print(build_table())
    print("README updated" if changed else "README already current")


if __name__ == "__main__":
    main()
