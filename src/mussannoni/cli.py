"""The ``mussannoni`` command line interface.

Three subcommands, enough to explore the package and to render from a shell script:

    mussannoni reports                       # list what can be rendered
    mussannoni layout council_best_students  # inspect a report's grid
    mussannoni render council_best_students --data rows.json --out report.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .api import render_report, report_layout
from .engines import DEFAULT_ENGINE, ENGINE_ENV_VAR, available_engines, engine_names
from .errors import MussaNnoniError
from .registry import LEVELS, list_reports


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("report_key", help="the report to act on, e.g. council_best_students")
    parser.add_argument(
        "--level",
        choices=LEVELS,
        default=None,
        help="only needed when a report key exists at both levels",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mussannoni",
        description="Render Tanzanian school examination result reports to PDF.",
    )
    parser.add_argument("--version", action="version", version=f"mussannoni {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reports = subparsers.add_parser("reports", help="list the available reports")
    reports.add_argument("--level", choices=LEVELS, default=None)
    reports.add_argument("--json", action="store_true", help="emit JSON instead of a table")

    layout = subparsers.add_parser("layout", help="inspect a report's measured grid")
    _add_common(layout)
    layout.add_argument(
        "--full", action="store_true", help="emit the whole layout, not just a summary"
    )

    render = subparsers.add_parser("render", help="render a report from a JSON data file")
    _add_common(render)
    render.add_argument(
        "--data",
        required=True,
        help="path to a JSON file holding the report data, or - to read stdin",
    )
    render.add_argument("--out", required=True, help="path to write the PDF to")
    render.add_argument(
        "--engine",
        choices=engine_names(),
        default=None,
        help=f"rendering engine (default: ${ENGINE_ENV_VAR}, else {DEFAULT_ENGINE})",
    )
    render.add_argument(
        "--no-optimize",
        dest="optimize",
        action="store_false",
        help="skip the structural PDF recompression pass",
    )

    subparsers.add_parser("doctor", help="report which rendering engines are usable here")
    return parser


def _cmd_reports(args: argparse.Namespace) -> int:
    reports = list_reports(args.level)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "ordinal": report.ordinal,
                        "level": report.level,
                        "report_key": report.report_key,
                        "title": report.title,
                        "scope": report.scope,
                    }
                    for report in reports
                ],
                indent=2,
            )
        )
        return 0
    width = max(len(report.report_key) for report in reports)
    for report in reports:
        print(
            f"{report.ordinal:>3}  {report.level:<9}  {report.report_key:<{width}}  {report.title}"
        )
    print(f"\n{len(reports)} reports")
    return 0


def _cmd_layout(args: argparse.Namespace) -> int:
    layout = report_layout(args.report_key, level=args.level)
    if args.full:
        print(json.dumps(layout, indent=2, ensure_ascii=False))
        return 0

    page = layout["page"]
    table = layout["table"]
    body = layout.get("body")
    print(f"{layout['report_key']}  ({layout['level']}, scope: {layout['scope']})")
    print(f"  title        {layout['title']}")
    print(f"  page         {page['width_pt']} x {page['height_pt']} pt, {page['orientation']}")
    print(f"  table        origin ({table['x_pt']}, {table['y_pt']}) pt, width {table['width_pt']} pt")
    print(f"  columns      {len(table['columns'])}")
    print(f"  header rows  {layout['header']['row_count']} ({layout['header']['height_pt']} pt)")
    if body:
        print(f"  body row     {body['row_height_pt']} pt")
        print(f"  rows/page    {layout['rows_per_page']}")
    else:
        print("  body row     none - this report has no uniform repeating row")
    print("  labels:")
    for index, label in enumerate(layout["header"]["labels"]):
        print(f"    {index:>3}  {label}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.data == "-" else Path(args.data).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"mussannoni: {args.data} is not valid JSON: {error}", file=sys.stderr)
        return 2

    pdf = render_report(
        args.report_key,
        data,
        level=args.level,
        engine=args.engine,
        optimize=args.optimize,
    )
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pdf)
    print(f"{destination} ({len(pdf):,} bytes)")
    return 0


def _cmd_doctor(_: argparse.Namespace) -> int:
    engines = available_engines()
    for name, ok in engines.items():
        marker = "ok" if ok else "--"
        default = "  (default)" if name == DEFAULT_ENGINE else ""
        print(f"  [{marker}] {name}{default}")
    if not any(engines.values()):
        print("\nNo rendering engine is usable here.", file=sys.stderr)
        return 1
    print(f"\n{sum(engines.values())} of {len(engines)} engines usable")
    return 0


COMMANDS = {
    "reports": _cmd_reports,
    "layout": _cmd_layout,
    "render": _cmd_render,
    "doctor": _cmd_doctor,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except MussaNnoniError as error:
        # These are the caller's problems, not crashes: report them without a traceback.
        print(f"mussannoni: {error}", file=sys.stderr)
        return 1
    except FileNotFoundError as error:
        print(f"mussannoni: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
