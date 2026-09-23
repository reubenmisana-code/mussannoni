"""The public entry points: data in, PDF out."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import measured, resources
from .document import render_document
from .registry import Report, find, list_reports
from .table import build_document


def report_roles(report_key: str, *, level: str | None = None) -> list[dict[str, Any]]:
    """What each static cell of each page IS, so a caller knows what to supply.

    Returns one entry per measured page::

        [{"rows":  {"0.0.2": "region", "0.0.3": "exam", "2.4": "figure", ...},
          "loose": {"2": "region", "3": "exam"}},
         ...]

    ``rows`` addresses are ``"row.column"`` or ``"row.column.line"``; ``loose`` addresses are line
    indices. Roles are ``authority`` (fixed institutional text, reproduced unchanged), ``region``,
    ``exam``, ``scope`` (the unit the artifact covers), ``heading`` (a static heading) and ``figure``
    (a computed value from the measured exam).

    Two things follow from this, and they are the whole point of it:

    * A caller replaces per-exam text by looking up the role rather than pattern-matching the
      reference's own string. Write to the same address through ``data["bands"]``
      (``"row.column"`` or ``"page.row.column"``) or ``data["loose"]`` (``"index"`` or
      ``"page.index"``).
    * Any ``figure`` the caller does not supply is rendered **empty**. A report may be structurally
      complete and numerically empty, but it never publishes the measured exam's figures.

    Roles are decided when the package is built, against the reference, so nothing is inferred at
    render time.
    """
    report = find(report_key, level)
    document = measured.measured_document(report.level, report.report_key)
    return [
        {"rows": page.get("roles") or {}, "loose": page.get("loose_roles") or {}}
        for page in document["pages"]
    ]


def report_layout(report_key: str, *, level: str | None = None) -> dict[str, Any]:
    """The measured layout of a report: its page box, column grid, header band and row shape.

    Useful for discovering what a report expects before sending it data — in particular
    ``layout["header"]["labels"]``, which names the columns, and ``layout["rows_per_page"]``.
    """
    report = find(report_key, level)
    return resources.layout_payload(report.level, report.report_key)


def render_report(
    report_key: str,
    data: Mapping[str, Any],
    *,
    level: str | None = None,
    engine: str | None = None,
    optimize: bool = True,
) -> bytes:
    """Render a report from tabular data and return the PDF as bytes.

    Args:
        report_key: Which report to render, e.g. ``"council_best_students"``. Call
            :func:`list_reports` for the full set.
        data: The report's data::

                {
                  "title": str,                  # optional; defaults to the measured title
                  "columns": [str, ...],         # optional; override the measured column labels
                  "header": {"0.3": str, ...},   # optional; override any header cell, "row.col"
                  #           a list value sets one measured line each
                  "rows": [[value, ...], ...],   # required; or [{"LABEL": value, ...}, ...]
                  "loose": {2: str, ...},        # optional; replace a loose letterhead line
                }

            Rows may be lists (positional, by column) or mappings keyed by column label or
            index. ``None`` renders as an empty cell. Rows are paginated automatically, and the
            measured header band repeats on every page.
        level: ``"primary"`` or ``"secondary"``. Required only for the few report keys that exist
            at both levels.
        engine: ``"weasyprint"`` (the default, in-process) or ``"chromium"`` (needs the
            ``agent-browser`` CLI). ``None`` consults ``MUSSANNONI_ENGINE``, then the default.
        optimize: Structurally recompress the PDF. Content-preserving; leave it on.

    Returns:
        The PDF as bytes.

    Raises:
        UnknownReportError: If ``report_key`` is not in the registry, or is ambiguous without a
            level.
        InvalidDataError: If the data does not fit the report's column grid, or the report has no
            uniform body row to place rows on.
        UnknownEngineError: If ``engine`` is not a registered engine name.
        EngineUnavailableError: If the chosen engine cannot run here.
        RenderError: If the engine ran but produced no usable PDF.

    Example:
        >>> pdf = render_report("council_best_students", {
        ...     "rows": [[1, "NYAMAGANA", "MWANZA SEC", "GOVERNMENT"]],
        ... })
        >>> pdf.startswith(b"%PDF-")
        True
    """
    report = find(report_key, level)
    layout = resources.layout_payload(report.level, report.report_key)

    # Prefer the report's measured document. It carries every band, every per-page column grid and
    # every page of a multi-section report exactly as measured, so nothing has to be reconstructed
    # — and each page holds the number of rows the reference put on it, so no capacity is computed.
    # The distilled table path remains for reports that have no column identity yet, since safe
    # substitution depends on knowing which columns are data.
    if measured.has_measured_document(report.level, report.report_key) and any(
        layout["header"].get("fields") or []
    ):
        allowed = {"rows", "title", "bands"}
        if set(data) <= allowed:
            document = measured.build_measured_document(
                measured.measured_document(report.level, report.report_key), layout, data
            )
            return render_document(
                document,
                report.level,
                report.report_key,
                engine=engine,
                optimize=optimize,
                validate=False,
            )

    document = build_document(layout, data)
    return render_document(
        document,
        report.level,
        report.report_key,
        engine=engine,
        optimize=optimize,
        # build_document produced this document, so it is known-good by construction.
        validate=False,
    )


def render_report_to_file(
    report_key: str,
    data: Mapping[str, Any],
    path: str | Path,
    *,
    level: str | None = None,
    engine: str | None = None,
    optimize: bool = True,
) -> Path:
    """Render a report from tabular data and write it to ``path``.

    Parent directories are created. See :func:`render_report` for the arguments.

    Returns:
        The path written.
    """
    pdf = render_report(
        report_key, data, level=level, engine=engine, optimize=optimize
    )
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pdf)
    return destination


def write_pdf(pdf: bytes, path: str | Path) -> Path:
    """Write PDF bytes to ``path``, creating parent directories. Returns the path."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pdf)
    return destination


__all__ = [
    "Report",
    "find",
    "list_reports",
    "render_report",
    "render_report_to_file",
    "report_layout",
    "report_roles",
    "write_pdf",
]
