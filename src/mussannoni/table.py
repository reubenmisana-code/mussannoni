"""Place a caller's rows onto a report's measured grid.

This is the layer that makes the package usable from an application: you pass rows of values as
a dict, and it produces the geometry document :mod:`mussannoni.document` renders. The grid it
places them on is not invented — the page box, the table origin, the column widths, the header
band, the row height, the fonts and the hairline weight all come from measuring the reference
PDF, so a generated report sits on the same grid as the real one.

**Where generated output differs from a reproduced reference.** The workshop's fixtures place
every glyph cluster at the advance width recorded in the reference PDF, with a sub-point
correction per cluster. Those corrections describe one specific string; reusing them for
different text would smear the new glyphs across the old advances. Generated rows therefore lay
text out normally and are positioned by *measuring* the string with the same face MuPDF would
use. That is accurate to the font's own metrics, which is what the reference was typeset with,
but it is not the same thing as reproducing a measured original glyph for glyph. Reproducing a
reference exactly is what passing a full geometry document to
:func:`mussannoni.render_document` is for.

The header band is copied verbatim from the measurement, so it keeps its per-glyph fidelity
unless you override its text — an overridden header cell is re-laid out like a body cell.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from functools import lru_cache
from typing import Any

import pymupdf

from .errors import InvalidDataError
from .resources import report_dir

ALIGNMENTS = ("left", "center", "right")


@lru_cache(maxsize=64)
def _font(base14: str | None, fontfile: str | None) -> pymupdf.Font:
    if fontfile:
        return pymupdf.Font(fontfile=fontfile)
    return pymupdf.Font(base14 or "helv")


def _style_font(style: Mapping[str, Any], level: str, report_key: str) -> pymupdf.Font:
    """The face used to measure a text class's advance widths.

    A class backed by a font embedded in the reference PDF is measured with that exact file. A
    class that only *names* Arial or Times is measured with the base-14 face MuPDF substitutes,
    which is also the face bundled as the ``Report Sans`` / ``Report Serif`` fallback.
    """
    relative = style.get("fontfile")
    if relative:
        candidate = report_dir(level, report_key) / relative
        if candidate.exists():
            return _font(None, str(candidate))
    return _font(style.get("base14", "helv"), None)


def _text_width(text: str, style: Mapping[str, Any], level: str, report_key: str) -> float:
    if not text:
        return 0.0
    font = _style_font(style, level, report_key)
    return font.text_length(text, fontsize=float(style.get("size_pt", 8.0)))


def _offset(text: str, width_pt: float, cell: Mapping[str, Any], text_width: float) -> float:
    """Where a string starts inside its cell, given the cell's alignment and padding."""
    pad_left = float(cell.get("pad_left", 0.0) or 0.0)
    pad_right = float(cell.get("pad_right", 0.0) or 0.0)
    align = cell.get("align", "left")
    if align == "right":
        return max(0.0, width_pt - pad_right - text_width)
    if align == "center":
        inner = width_pt - pad_left - pad_right
        return pad_left + max(0.0, (inner - text_width) / 2.0)
    return pad_left


def _as_text(value: Any) -> str:
    """Render a cell value as the report would print it.

    ``None`` is a blank cell, not the string "None" — a results table has plenty of legitimately
    empty cells and they must not read as data. Floats that are whole numbers print without a
    trailing ``.0``, because these reports show ranks and counts as integers.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _normalise_rows(data: Mapping[str, Any], labels: Sequence[str], count: int) -> list[list[str]]:
    """Accept rows as sequences (positional) or mappings (keyed by column label or index)."""
    raw = data.get("rows")
    if raw is None:
        raise InvalidDataError("data['rows'] is required")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise InvalidDataError("data['rows'] must be a list of rows")

    lookup: dict[str, int] = {}
    for index, label in enumerate(labels):
        if label and label not in lookup:
            lookup[label] = index

    rows: list[list[str]] = []
    for position, row in enumerate(raw):
        cells = [""] * count
        if isinstance(row, Mapping):
            for key, value in row.items():
                index = lookup.get(key) if isinstance(key, str) else None
                if index is None and isinstance(key, int):
                    index = key
                if index is None and isinstance(key, str) and key.isdigit():
                    index = int(key)
                if index is None:
                    raise InvalidDataError(
                        f"data['rows'][{position}] has key {key!r}, which is neither a column "
                        f"index nor one of the measured column labels {list(lookup)}"
                    )
                if not 0 <= index < count:
                    raise InvalidDataError(
                        f"data['rows'][{position}] key {key!r} maps to column {index}, outside "
                        f"the {count} columns of this report"
                    )
                cells[index] = _as_text(value)
        elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
            if len(row) > count:
                raise InvalidDataError(
                    f"data['rows'][{position}] has {len(row)} values but this report has "
                    f"{count} columns"
                )
            for index, value in enumerate(row):
                cells[index] = _as_text(value)
        else:
            raise InvalidDataError(
                f"data['rows'][{position}] must be a list or a mapping, got "
                f"{type(row).__name__}"
            )
        rows.append(cells)
    return rows


def _body_cell(
    text: str,
    prototype: Mapping[str, Any],
    width_pt: float,
    styles: Mapping[str, Any],
    level: str,
    report_key: str,
) -> dict[str, Any]:
    line_class = prototype.get("line_class", "t0")
    style = styles.get(line_class, {"size_pt": 8.0, "base14": "helv"})
    cell: dict[str, Any] = {
        "column": int(prototype["column"]),
        "colspan": 1,
        "rowspan": 1,
        "classes": list(prototype.get("classes") or []),
        "align": prototype.get("align", "left"),
        "pad_left": float(prototype.get("pad_left", 0.0) or 0.0),
        "pad_right": float(prototype.get("pad_right", 0.0) or 0.0),
        "lines": [],
    }
    if not text:
        # No line at all rather than an empty one: an empty absolutely-positioned div is a real
        # element in the PDF and the reports are already span-heavy.
        return cell

    width = _text_width(text, style, level, report_key)
    cell["lines"] = [
        {
            "class": line_class,
            "left_pt": round(_offset(text, width_pt, cell, width), 3),
            "top_pt": float(prototype.get("top_pt", 0.0) or 0.0),
            "letter_spacing_pt": 0.0,
            "rotation": int(prototype.get("rotation", 0) or 0),
            "runs": [{"class": prototype.get("run_class", line_class), "text": text, "chunks": []}],
        }
    ]
    return cell


def _synthesise_rules(
    layout: Mapping[str, Any], body_row_heights: Sequence[float]
) -> list[dict[str, Any]]:
    """Draw the gridlines for the number of body rows this page actually has.

    The measured ``rules`` path holds absolute coordinates for the reference's own row count, so
    the body's lines cannot be reused once the data changes. They are redrawn the way the
    reference draws them: filled hairline rectangles at the measured weight, one per column
    boundary and one per row boundary.

    The header band is a different matter. Its cells are merged into subject groups, so drawing
    every column boundary across it would strike lines through the merged headings. The measured
    header segments are therefore emitted verbatim and only the body band is generated.
    """
    rule = layout.get("rule")
    if not rule:
        return []

    hairline = float(rule.get("width_pt", 0.48))
    table = layout["table"]
    x0 = float(table["x_pt"])
    columns = [float(width) for width in table["columns"]]
    total_width = round(sum(columns), 2)
    body_top = float(table["y_pt"]) + float(layout["header"].get("height_pt", 0.0))
    body_height = sum(body_row_heights)

    segments: list[str] = [rule.get("header_d", "")]

    if body_height > 0:
        x = x0
        for edge in [0.0, *columns]:
            x += edge
            segments.append(
                f"M{round(x, 2)} {round(body_top, 2)}h{hairline}"
                f"v{round(body_height, 2)}h-{hairline}Z"
            )
        y = body_top
        for edge in [0.0, *body_row_heights]:
            y += edge
            segments.append(
                f"M{round(x0, 2)} {round(y, 2)}h{total_width}v{hairline}h-{total_width}Z"
            )

    path = "".join(segments)
    if not path:
        return []
    return [{"d": path, "fill": rule.get("fill", "color(srgb 0 0 0)")}]


def _apply_header_overrides(
    header_rows: list[dict[str, Any]],
    overrides: Mapping[str, Any],
    layout: Mapping[str, Any],
    styles: Mapping[str, Any],
    level: str,
    report_key: str,
) -> None:
    """Replace the text of individual header cells, addressed as ``"row.column"``."""
    columns = [float(width) for width in layout["table"]["columns"]]
    for address, value in overrides.items():
        try:
            row_text, column_text = str(address).split(".", 1)
            row_index, column_index = int(row_text), int(column_text)
        except ValueError as error:
            raise InvalidDataError(
                f"data['header'] key {address!r} must be 'row.column', e.g. '0.3'"
            ) from error
        if not 0 <= row_index < len(header_rows):
            raise InvalidDataError(
                f"data['header'] key {address!r} names row {row_index}, but this report's header "
                f"has {len(header_rows)} rows"
            )
        row = header_rows[row_index]
        for cell in row["cells"]:
            if int(cell["column"]) != column_index:
                continue
            _rewrite_cell_text(
                cell, _as_text(value), columns, styles, level, report_key
            )
            break
        else:
            raise InvalidDataError(
                f"data['header'] key {address!r} names column {column_index}, which has no cell "
                f"in header row {row_index}"
            )


def _rewrite_cell_text(
    cell: dict[str, Any],
    text: str,
    columns: Sequence[float],
    styles: Mapping[str, Any],
    level: str,
    report_key: str,
) -> None:
    """Put new text into a measured cell, dropping the old string's glyph corrections."""
    lines = cell.get("lines") or []
    if not lines:
        return
    if not text:
        cell["lines"] = []
        return

    line = lines[0]
    line_class = line.get("class", "t0")
    style = styles.get(line_class, {"size_pt": 8.0, "base14": "helv"})
    span = sum(
        float(columns[index])
        for index in range(
            int(cell["column"]), min(int(cell["column"]) + int(cell.get("colspan", 1)), len(columns))
        )
    )
    width = _text_width(text, style, level, report_key)
    line["left_pt"] = round(_offset(text, span, cell, width), 3)
    # The measured letter spacing and per-cluster margins belong to the old string.
    line["letter_spacing_pt"] = 0.0
    line["runs"] = [{"class": line_class, "text": text, "chunks": []}]
    cell["lines"] = [line]


def build_document(layout: Mapping[str, Any], data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a geometry document by placing ``data`` onto a report's measured ``layout``.

    Args:
        layout: A report's distilled layout, from :func:`mussannoni.resources.layout_payload`.
        data: The report data::

                {
                  "title": str,                  # optional; defaults to the measured title
                  "columns": [str, ...],         # optional; override the measured column labels
                  "header": {"0.3": str, ...},   # optional; override any header cell, "row.col"
                  "rows": [[value, ...], ...],   # required; or [{"LABEL": value, ...}, ...]
                }

    Returns:
        A geometry document ready for :func:`mussannoni.render_document`.

    Raises:
        InvalidDataError: If the report has no repeating body row, or the data does not fit the
            report's column grid.
    """
    if not isinstance(data, Mapping):
        raise InvalidDataError(f"data must be a mapping, got {type(data).__name__}")

    body = layout.get("body")
    if not body:
        raise InvalidDataError(
            f"Report {layout['report_key']!r} has no uniform repeating body row, so its rows "
            "cannot be generated from tabular data. Build a geometry document and call "
            "render_document() instead."
        )

    level = layout["level"]
    report_key = layout["report_key"]
    styles = layout.get("text_styles", {})
    columns = [float(width) for width in layout["table"]["columns"]]
    labels = list(layout["header"].get("labels") or [])
    labels += [""] * (len(columns) - len(labels))

    unknown = set(data) - {"title", "columns", "header", "rows"}
    if unknown:
        raise InvalidDataError(
            f"Unknown key(s) in data: {sorted(unknown)}. "
            "Expected any of: title, columns, header, rows."
        )

    rows = _normalise_rows(data, labels, len(columns))

    header_rows = deepcopy(layout["header"]["rows"])
    if data.get("columns") is not None:
        supplied = list(data["columns"])
        if len(supplied) > len(columns):
            raise InvalidDataError(
                f"data['columns'] has {len(supplied)} labels but this report has "
                f"{len(columns)} columns"
            )
        label_row = _label_row_index(header_rows, len(columns))
        if label_row is None:
            raise InvalidDataError(
                f"Report {report_key!r} has no header row carrying column labels, so "
                "data['columns'] cannot be applied."
            )
        for index, label in enumerate(supplied):
            for cell in header_rows[label_row]["cells"]:
                if int(cell["column"]) == index:
                    _rewrite_cell_text(
                        cell, _as_text(label), columns, styles, level, report_key
                    )
                    break
    if data.get("header"):
        _apply_header_overrides(
            header_rows, data["header"], layout, styles, level, report_key
        )

    prototypes = {int(cell["column"]): cell for cell in body["cells"]}
    fallback = _fallback_prototype(body["cells"])
    per_page = int(layout.get("rows_per_page") or 0) or len(rows) or 1
    chunks = [rows[start : start + per_page] for start in range(0, len(rows), per_page)] or [[]]

    row_height = float(body["row_height_pt"])
    header_height = float(layout["header"].get("height_pt", 0.0))
    page_template = layout["page"]
    decorations = layout.get("decorations") or {}

    pages: list[dict[str, Any]] = []
    for number, chunk in enumerate(chunks, start=1):
        page_rows = deepcopy(header_rows)
        for offset, values in enumerate(chunk):
            cells = []
            for column, width in enumerate(columns):
                # A handful of columns are merged away in every measured body row, so the
                # measurement never saw a plain cell there and has no prototype for them. Borrow
                # the report's most common cell shape rather than emitting an empty cell: the
                # caller passed a value for that column and silently dropping it would be the
                # worst of the available behaviours.
                prototype = prototypes.get(column, fallback) | {"column": column}
                cells.append(
                    _body_cell(values[column], prototype, width, styles, level, report_key)
                )
            page_rows.append(
                {
                    "index": len(header_rows) + offset,
                    "height_pt": row_height,
                    "cells": cells,
                }
            )

        body_heights = [row_height] * len(chunk)
        pages.append(
            {
                "number": number,
                "width_pt": float(page_template["width_pt"]),
                "height_pt": float(page_template["height_pt"]),
                "orientation": page_template["orientation"],
                "table_x_pt": float(layout["table"]["x_pt"]),
                "table_y_pt": float(layout["table"]["y_pt"]),
                "table_width_pt": float(layout["table"]["width_pt"]),
                "table_height_pt": round(header_height + row_height * len(chunk), 3),
                "columns": columns,
                "header_rows": int(layout["header"]["row_count"]),
                "rows": page_rows,
                "vectors": deepcopy(decorations.get("vectors") or []),
                "rules": _synthesise_rules(layout, body_heights),
                "loose_lines": deepcopy(decorations.get("loose_lines") or []),
            }
        )

    return {
        "report": {"title": _as_text(data.get("title") or layout.get("title", ""))},
        "pages": pages,
    }


def _fallback_prototype(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The cell shape to use for a column the measurement has no prototype for.

    The most common shape across the report's other columns, so borrowed cells inherit that
    report's own text class, baseline offset and padding rather than a generic default.
    """
    counts: Counter[str] = Counter()
    for cell in cells:
        shape = {key: value for key, value in cell.items() if key != "column"}
        counts[json.dumps(shape, sort_keys=True)] += 1
    if not counts:
        return {
            "classes": [],
            "align": "left",
            "pad_left": 0.0,
            "pad_right": 0.0,
            "line_class": "t0",
            "top_pt": 0.0,
            "rotation": 0,
            "run_class": "t0",
        }
    return json.loads(counts.most_common(1)[0][0])


def _label_row_index(header_rows: Sequence[Mapping[str, Any]], column_count: int) -> int | None:
    """Which header row carries the per-column labels: the one naming the most columns."""
    best: int | None = None
    best_filled = 0
    for index, row in enumerate(header_rows):
        filled = sum(
            1
            for cell in row["cells"]
            if int(cell.get("colspan", 1)) == 1
            and int(cell["column"]) < column_count
            and any(
                run.get("text", "").strip()
                for line in cell.get("lines") or []
                for run in line.get("runs") or []
            )
        )
        if filled > best_filled:
            best, best_filled = index, filled
    return best
