"""The geometry document: the low-level contract between data and a rendered page.

A *geometry document* describes finished pages, not business facts. Every glyph run carries an
absolute offset inside its cell, and every page carries its own size, column widths and row
heights. This is the shape the workshop's ``fixture.json`` files hold, and rendering one
reproduces a reference report exactly.

Callers who have rows of values rather than placed glyphs want :mod:`mussannoni.table`, which
builds one of these from a report's measured layout. This module is the layer underneath, and it
is public because full control is occasionally the only way to reproduce an unusual report.

The shape, in full::

    {
      "report": {"title": str},              # only .title is read
      "pages": [{
        "number": int,
        "width_pt": float, "height_pt": float, "orientation": "portrait" | "landscape",
        "table_x_pt": float, "table_y_pt": float,
        "table_width_pt": float, "table_height_pt": float,
        "columns": [float, ...],             # column widths, in points
        "header_rows": int,                  # leading rows of `rows` that go in <thead>
        "rows": [{
          "index": int, "height_pt": float,
          "cells": [{
            "column": int, "colspan": int, "rowspan": int,
            "classes": [str, ...],           # CSS classes from the report's report.css
            "align": "left" | "center" | "right",
            "pad_left": float, "pad_right": float,
            "lines": [{
              "class": str,                  # a .tN text class
              "left_pt": float, "top_pt": float,
              "letter_spacing_pt": float, "rotation": 0 | 90 | 180 | 270,
              "runs": [{
                "class": str, "text": str,
                "chunks": [{"text": str, "margin_pt": float}, ...],   # may be empty
              }, ...],
            }, ...],
          }, ...],
        }, ...],
        "vectors": [{"d", "fill", "stroke", "stroke_width"}, ...],    # page decorations
        "rules": [{"d": str, "fill": str}, ...],                      # gridlines
        "loose_lines": [...],                # lines placed from the page origin, not a cell
      }, ...]
    }

``chunks`` exist because the reference reports place each glyph cluster at the advance width
recorded in the PDF. When they are present they replace the run's own text, and each carries a
sub-point ``margin_pt`` correction. They are measurements *of a specific string*: substituting
different text while keeping the chunks would smear the new glyphs across the old advances. So
generated documents leave ``chunks`` empty and let the text lay out normally.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from . import resources
from .engines import get_engine
from .errors import InvalidDocumentError
from .optimize import optimize_pdf

REQUIRED_PAGE_KEYS = (
    "number",
    "width_pt",
    "height_pt",
    "orientation",
    "table_x_pt",
    "table_y_pt",
    "table_width_pt",
    "table_height_pt",
    "columns",
    "header_rows",
    "rows",
    "vectors",
    "rules",
    "loose_lines",
)


def _environment() -> Environment:
    """A Jinja environment over the packaged template.

    ``StrictUndefined`` is deliberate: a missing key must fail loudly rather than render an empty
    cell, because an empty cell in a results table is indistinguishable from a legitimate blank.
    """
    return Environment(
        loader=FileSystemLoader(resources.resource_root()),
        autoescape=select_autoescape(("html", "xml")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def validate_document(document: Mapping[str, Any]) -> None:
    """Check a geometry document against what the template reads, with a useful message.

    Jinja's own ``StrictUndefined`` error says only which name was missing, not where. Since the
    interesting failures are nested several levels down inside a list of pages, this locates them.

    Raises:
        InvalidDocumentError: On the first problem found.
    """
    if not isinstance(document, Mapping):
        raise InvalidDocumentError(f"document must be a mapping, got {type(document).__name__}")

    report = document.get("report")
    if not isinstance(report, Mapping) or "title" not in report:
        raise InvalidDocumentError("document['report'] must be a mapping containing 'title'")

    pages = document.get("pages")
    if not isinstance(pages, list) or not pages:
        raise InvalidDocumentError("document['pages'] must be a non-empty list")

    for position, page in enumerate(pages):
        where = f"document['pages'][{position}]"
        if not isinstance(page, Mapping):
            raise InvalidDocumentError(f"{where} must be a mapping")
        missing = [key for key in REQUIRED_PAGE_KEYS if key not in page]
        if missing:
            raise InvalidDocumentError(f"{where} is missing {missing}")

        columns = page["columns"]
        if not isinstance(columns, list) or not columns:
            raise InvalidDocumentError(f"{where}['columns'] must be a non-empty list of widths")

        for row_position, row in enumerate(page["rows"]):
            _validate_row(row, f"{where}['rows'][{row_position}]", len(columns))


def _validate_row(row: Any, where: str, column_count: int) -> None:
    if not isinstance(row, Mapping):
        raise InvalidDocumentError(f"{where} must be a mapping")
    for key in ("index", "height_pt", "cells"):
        if key not in row:
            raise InvalidDocumentError(f"{where} is missing {key!r}")

    for cell_position, cell in enumerate(row["cells"]):
        cell_where = f"{where}['cells'][{cell_position}]"
        if not isinstance(cell, Mapping):
            raise InvalidDocumentError(f"{cell_where} must be a mapping")
        for key in (
            "column",
            "colspan",
            "rowspan",
            "classes",
            "align",
            "pad_left",
            "pad_right",
            "lines",
        ):
            if key not in cell:
                raise InvalidDocumentError(f"{cell_where} is missing {key!r}")
        column = cell["column"]
        if not isinstance(column, int) or not 0 <= column < column_count:
            raise InvalidDocumentError(
                f"{cell_where}['column'] is {column!r}, outside the {column_count} columns "
                "declared for this page"
            )
        for line_position, line in enumerate(cell["lines"]):
            _validate_line(line, f"{cell_where}['lines'][{line_position}]")


def _validate_line(line: Any, where: str) -> None:
    if not isinstance(line, Mapping):
        raise InvalidDocumentError(f"{where} must be a mapping")
    for key in ("class", "left_pt", "top_pt", "letter_spacing_pt", "rotation", "runs"):
        if key not in line:
            raise InvalidDocumentError(f"{where} is missing {key!r}")
    for run_position, run in enumerate(line["runs"]):
        run_where = f"{where}['runs'][{run_position}]"
        if not isinstance(run, Mapping):
            raise InvalidDocumentError(f"{run_where} must be a mapping")
        for key in ("class", "text", "chunks"):
            if key not in run:
                raise InvalidDocumentError(f"{run_where} is missing {key!r}")


def build_html(
    document: Mapping[str, Any],
    level: str,
    report_key: str,
    *,
    validate: bool = True,
) -> str:
    """Render a geometry document to a standalone HTML string.

    The stylesheets are linked as absolute ``file://`` URIs into the packaged resources rather
    than inlined, because each one resolves its own relative font references against its own
    directory.

    Args:
        document: A geometry document. Not modified.
        level: ``"primary"`` or ``"secondary"`` — selects which ``report.css`` to link.
        report_key: The report whose measured CSS and fonts this document was built for.
        validate: Check the document shape first. Turn off only when rendering a document this
            package just produced.

    Raises:
        InvalidDocumentError: If the document does not match the template's contract.
    """
    if validate:
        validate_document(document)

    shared_css, report_css, _ = resources.asset_uris(level, report_key)
    payload = deepcopy(dict(document))
    payload["assets"] = {"shared_css": shared_css, "report_css": report_css}

    template = _environment().get_template("template.html")
    return template.render(**payload)


def render_html_to_pdf(
    html: str,
    level: str,
    report_key: str,
    *,
    engine: str | None = None,
    optimize: bool = True,
) -> bytes:
    """Render an HTML string to PDF bytes through the selected engine.

    Engines write files rather than returning bytes — Chromium because it is a separate process,
    and the recompression pass because it re-saves through PyMuPDF — so the work happens in a
    temporary directory that is cleaned up on the way out.
    """
    implementation = get_engine(engine)
    _, _, base_url = resources.asset_uris(level, report_key)

    with tempfile.TemporaryDirectory(prefix="mussannoni-render-") as raw:
        work_dir = Path(raw)
        html_path = work_dir / "rendered.html"
        html_path.write_text(html, encoding="utf-8")
        pdf_path = work_dir / "rendered.pdf"

        implementation.render(
            html=html,
            html_path=html_path,
            pdf_path=pdf_path,
            base_url=base_url,
            work_dir=work_dir,
            session=f"mussannoni-{level}-{resources.artifact_name(report_key)}",
        )
        if optimize:
            optimize_pdf(pdf_path)
        return pdf_path.read_bytes()


def render_document(
    document: Mapping[str, Any],
    level: str,
    report_key: str,
    *,
    engine: str | None = None,
    optimize: bool = True,
    validate: bool = True,
) -> bytes:
    """Render a geometry document straight to PDF bytes.

    Args:
        document: A geometry document, as described in this module's docstring.
        level: ``"primary"`` or ``"secondary"``.
        report_key: The report whose measured CSS and fonts to render against.
        engine: ``"weasyprint"`` (default) or ``"chromium"``. ``None`` consults the
            ``MUSSANNONI_ENGINE`` environment variable, then the default.
        optimize: Structurally recompress the result. Content-preserving; leave it on.
        validate: Check the document shape before rendering.

    Returns:
        The PDF as bytes.
    """
    html = build_html(document, level, report_key, validate=validate)
    return render_html_to_pdf(html, level, report_key, engine=engine, optimize=optimize)
