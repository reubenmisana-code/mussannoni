"""Run the whole conversion loop for one report, or for the entire catalog.

    extract -> scaffold -> render -> tune -> scaffold -> render -> compare

The tuning pass is measured once: it records the residual offset of the first render and the
second render lands on it. Reports are processed in catalog order so the corpus can be
converted unattended and every status in `catalog/reports.yaml` comes from a real measurement.
"""

from __future__ import annotations

import argparse
import traceback
from typing import Any

from tools.common import load_catalog, output_dir
from tools.compare import compare
from tools.extract import extract
from tools.render import engine_names, render
from tools.scaffold import scaffold
from tools.tune import residuals


def convert(
    level: str,
    report_key: str,
    *,
    re_extract: bool = False,
    tune: bool = True,
    engine: str | None = None,
) -> dict[str, Any]:
    if re_extract:
        extract(level, report_key)
    scaffold(level, report_key)
    render(level, report_key, engine=engine)
    if tune:
        residuals(level, report_key)
        scaffold(level, report_key)
        render(level, report_key, engine=engine)
    return compare(level, report_key)


def convert_all(
    *,
    re_extract: bool = False,
    tune: bool = True,
    only: str | None = None,
    first: int = 1,
    last: int = 46,
    engine: str | None = None,
) -> None:
    reports = load_catalog()["reports"]
    if only:
        reports = [item for item in reports if item["level"] == only]
    reports = [item for item in reports if first <= item["ordinal"] <= last]
    failures: list[tuple[str, str, str]] = []
    for report in reports:
        label = f"{report['ordinal']:>2} {report['level']:<9} {report['report_key']:<38}"
        try:
            payload = convert(
                report["level"],
                report["report_key"],
                re_extract=re_extract,
                tune=tune,
                engine=engine,
            )
        except Exception as error:  # noqa: BLE001 - one bad report must not stop the corpus
            failures.append((report["level"], report["report_key"], str(error)))
            print(f"{label} FAILED  {type(error).__name__}: {error}", flush=True)
            traceback.print_exc()
            continue
        summary = payload["summary"]
        print(
            f"{label} {summary['pages_passing']:>2}/{summary['pages_total']:<2} pages  "
            f"ssim {summary['worst_ssim']:.4f}-{summary['best_ssim']:.4f}  "
            f"delta {summary['worst_pixel_delta_percent']:.2f}%  "
            f"text {summary['worst_text_drift_pt']}pt  col {summary['worst_column_drift_pt']}pt  "
            f"{payload['status']}",
            flush=True,
        )
    if failures:
        print(f"\n{len(failures)} report(s) failed:", flush=True)
        for level, key, error in failures:
            print(f"  {level}/{key}: {error}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the conversion loop")
    parser.add_argument("level", nargs="?", choices=("secondary", "primary"))
    parser.add_argument("report_key", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--only", choices=("secondary", "primary"), help="restrict --all to one level"
    )
    parser.add_argument("--re-extract", action="store_true")
    parser.add_argument("--no-tune", action="store_true")
    parser.add_argument("--engine", choices=engine_names(), default=None, help="rendering engine")
    parser.add_argument("--from", dest="first", type=int, default=1, help="first catalog ordinal")
    parser.add_argument("--to", dest="last", type=int, default=46, help="last catalog ordinal")
    args = parser.parse_args()
    if args.all:
        convert_all(
            re_extract=args.re_extract,
            tune=not args.no_tune,
            only=args.only,
            first=args.first,
            last=args.last,
            engine=args.engine,
        )
        return
    if not args.level or not args.report_key:
        parser.error("provide LEVEL and REPORT_KEY, or --all")
    payload = convert(
        args.level,
        args.report_key,
        re_extract=args.re_extract,
        tune=not args.no_tune,
        engine=args.engine,
    )
    print(payload["status"], payload["summary"])
    print(output_dir({"level": args.level, "report_key": args.report_key}) / "report.json")


if __name__ == "__main__":
    main()
