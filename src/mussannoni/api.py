"""The public entry points: data in, PDF out."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import resources
from .document import render_document
from .registry import Report, find, list_reports
from .table import build_document


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
                  "rows": [[value, ...], ...],   # required; or [{"LABEL": value, ...}, ...]
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
    "write_pdf",
]
