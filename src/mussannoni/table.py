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


def _normalise_rows(
    data: Mapping[str, Any],
    labels: Sequence[str],
    count: int,
    fields: Sequence[str] | None = None,
) -> list[list[str]]:
    """Accept rows as sequences (positional) or mappings (keyed by field name, label, or index).

    The field names are the ones the packaged layout ships, so an application addresses columns by
    identity and never has to retype a 38-column order or pad the grid's unlabelled edge slots.
    """
    raw = data.get("rows")
    if raw is None:
        raise InvalidDataError("data['rows'] is required")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise InvalidDataError("data['rows'] must be a list of rows")

    lookup: dict[str, int] = {}
    # Field names take precedence over measured labels: they are unique by construction, whereas
    # a reference grid repeats labels like F / M / T across every division block.
    for index, label in enumerate(labels):
        if label and label not in lookup:
            lookup[label] = index
    for index, name in enumerate(fields or []):
        if name:
            lookup[name] = index

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
        "colspan": int(prototype.get("colspan", 1) or 1),
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
    layout: Mapping[str, Any],
    body_row_heights: Sequence[float],
    *,
    columns: Sequence[float] | None = None,
    table: Mapping[str, Any] | None = None,
    header_height: float | None = None,
    rule: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Draw the gridlines for the number of body rows this page actually has.

    The measured ``rules`` path holds absolute coordinates for the reference's own row count, so
    the body's lines cannot be reused once the data changes. They are redrawn the way the
    reference draws them: filled hairline rectangles at the measured weight, one per column
    boundary and one per row boundary.

    The header band is a different matter. Its cells are merged into subject groups, so drawing
    every column boundary across it would strike lines through the merged headings. The measured
    header segments are therefore emitted verbatim and only the body band is generated.

    A compound first page has its own grid, origin, band height and measured rule segments, so
    those are passed in rather than read from the repeating layout.
    """
    rule = rule if rule is not None else layout.get("rule")
    if not rule:
        return []

    table = table if table is not None else layout["table"]
    if columns is None:
        columns = [float(width) for width in layout["table"]["columns"]]
    else:
        columns = [float(width) for width in columns]
    if header_height is None:
        header_height = float(layout["header"].get("height_pt", 0.0))

    hairline = float(rule.get("width_pt", 0.48))
    x0 = float(table["x_pt"])
    total_width = round(sum(columns), 2)
    body_top = float(table["y_pt"]) + float(header_height)
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
    *,
    columns: Sequence[float] | None = None,
    row_map: Sequence[int] | None = None,
    column_map: Sequence[int] | None = None,
) -> None:
    """Replace the text of individual header cells, addressed as ``"row.column"``.

    ``row_map`` and ``column_map`` translate an address written against the repeating band onto a
    compound first page's own band and grid, so a caller writes one set of overrides and both
    pages honour it.
    """
    if columns is None:
        columns = [float(width) for width in layout["table"]["columns"]]
    else:
        columns = [float(width) for width in columns]
    for address, value in overrides.items():
        try:
            row_text, column_text = str(address).split(".", 1)
            row_index, column_index = int(row_text), int(column_text)
        except ValueError as error:
            raise InvalidDataError(
                f"data['header'] key {address!r} must be 'row.column', e.g. '0.3'"
            ) from error
        if row_map is not None:
            if not 0 <= row_index < len(row_map):
                raise InvalidDataError(
                    f"data['header'] key {address!r} names row {row_index}, but this report's "
                    f"header has {len(row_map)} rows"
                )
            row_index = int(row_map[row_index])
        if column_map is not None:
            if not 0 <= column_index < len(column_map):
                raise InvalidDataError(
                    f"data['header'] key {address!r} names column {column_index}, outside this "
                    f"report's {len(column_map)} columns"
                )
            column_index = int(column_map[column_index])
        if not 0 <= row_index < len(header_rows):
            raise InvalidDataError(
                f"data['header'] key {address!r} names row {row_index}, but this report's header "
                f"has {len(header_rows)} rows"
            )
        row = header_rows[row_index]
        for cell in row["cells"]:
            if int(cell["column"]) != column_index:
                continue
            # A list value addresses the cell's measured lines one by one; a scalar
            # replaces the cell with a single line.
            replacement = (
                value
                if isinstance(value, Sequence) and not isinstance(value, (str, bytes))
                else _as_text(value)
            )
            _rewrite_cell_text(
                cell, replacement, columns, styles, level, report_key
            )
            break
        else:
            raise InvalidDataError(
                f"data['header'] key {address!r} names column {column_index}, which has no cell "
                f"in header row {row_index}"
            )


def _rewrite_cell_text(
    cell: dict[str, Any],
    text: str | Sequence[str],
    columns: Sequence[float],
    styles: Mapping[str, Any],
    level: str,
    report_key: str,
) -> None:
    """Put new text into a measured cell, dropping the old string's glyph corrections.

    ``text`` may be a single string or one string per measured line. A letterhead is one cell
    holding several lines — the authority lines, the region, the exam title — and replacing it
    with a single string would collapse them onto one baseline. Supplying a sequence keeps each
    line at its own measured ``top_pt`` and text class, and re-centres each one for its new
    string. Passing fewer strings than there are lines blanks the remainder, so a report can drop
    a letterhead line it does not need.
    """
    lines = cell.get("lines") or []
    if not lines:
        return

    if isinstance(text, (str, bytes)) or not isinstance(text, Sequence):
        texts = [_as_text(text)]
    else:
        texts = [_as_text(value) for value in text]
        if len(texts) > len(lines):
            raise InvalidDataError(
                f"A header override for report {report_key!r} supplied {len(texts)} lines but "
                f"the measured cell has {len(lines)}"
            )

    if not any(texts):
        cell["lines"] = []
        return

    span = sum(
        float(columns[index])
        for index in range(
            int(cell["column"]), min(int(cell["column"]) + int(cell.get("colspan", 1)), len(columns))
        )
    )

    rewritten: list[dict[str, Any]] = []
    for index, line in enumerate(lines[: len(texts)]):
        value = texts[index]
        if not value:
            continue
        line_class = line.get("class", "t0")
        style = styles.get(line_class, {"size_pt": 8.0, "base14": "helv"})
        old_text = "".join(run.get("text", "") for run in (line.get("runs") or []))
        if value == old_text:
            # Unchanged text keeps its measurement untouched — its offset, its letter spacing and
            # its per-cluster corrections. Re-placing it from font metrics would move it: the
            # authority lines of a letterhead are supplied identically by every caller, and
            # recomputing them put them 193pt from where the reference draws them. Nothing that
            # has not changed is ever recomputed.
            rewritten.append(line)
            continue
        width = _text_width(value, style, level, report_key)
        # A letterhead is one cell holding several lines, each centred across the cell by its own
        # measured offset while the cell itself is left-aligned. Re-placing such a line by the
        # cell's alignment would move it to the left margin, so centring is detected from the
        # line's own measurement and preserved.
        old_width = _text_width(old_text, style, level, report_key)
        old_left = float(line.get("left_pt", 0.0) or 0.0)
        centred = old_width > 0 and abs((old_left + old_width / 2.0) - span / 2.0) <= 6.0
        if centred:
            line["left_pt"] = round(max(0.0, (span - width) / 2.0), 3)
        else:
            line["left_pt"] = round(_offset(value, span, cell, width), 3)
        # The measured letter spacing and per-cluster margins belong to the old string.
        line["letter_spacing_pt"] = 0.0
        line["runs"] = [{"class": line_class, "text": value, "chunks": []}]
        rewritten.append(line)
    cell["lines"] = rewritten


def _apply_loose_overrides(
    loose_lines: list[dict[str, Any]],
    overrides: Mapping[str, Any],
    layout: Mapping[str, Any],
    styles: Mapping[str, Any],
    level: str,
    report_key: str,
) -> list[dict[str, Any]]:
    """Replace the text of individual loose lines, addressed by their index.

    Several reports draw the letterhead as absolutely-positioned lines beside the table rather
    than as cells inside its header band. Those lines carry the reference exam's own region and
    scope, so an application rendering a different exam has to be able to replace them — and
    ``header`` cannot reach them, because they are not in the header band.

    A line that was centred on the page is re-centred for its new string; one that was not keeps
    its measured left edge. Setting a line to an empty string removes it.
    """
    page_width = float(layout["page"]["width_pt"])
    removed: set[int] = set()

    for address, value in overrides.items():
        try:
            index = int(str(address))
        except ValueError as error:
            raise InvalidDataError(
                f"data['loose'] key {address!r} must be a line index, e.g. 2"
            ) from error
        if not 0 <= index < len(loose_lines):
            raise InvalidDataError(
                f"data['loose'] key {address!r} names line {index}, but report {report_key!r} "
                f"has {len(loose_lines)} loose lines"
            )

        line = loose_lines[index]
        text = _as_text(value)
        if not text:
            removed.add(index)
            continue

        line_class = line.get("class", "t0")
        style = styles.get(line_class, {"size_pt": 8.0, "base14": "helv"})
        old_text = "".join(run.get("text", "") for run in (line.get("runs") or []))
        old_width = _text_width(old_text, style, level, report_key)
        new_width = _text_width(text, style, level, report_key)
        old_left = float(line.get("left_pt", 0.0) or 0.0)
        # Within a point of centred counts as centred: the measurement records the
        # reference's own rounding, not an exact midpoint.
        was_centred = abs((old_left + old_width / 2.0) - page_width / 2.0) <= 2.0
        if was_centred:
            line["left_pt"] = round(max(0.0, (page_width - new_width) / 2.0), 3)
        # The measured letter spacing and per-cluster margins belong to the old string.
        line["letter_spacing_pt"] = 0.0
        line["runs"] = [{"class": line_class, "text": text, "chunks": []}]

    return [line for index, line in enumerate(loose_lines) if index not in removed]


def build_document(layout: Mapping[str, Any], data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a geometry document by placing ``data`` onto a report's measured ``layout``.

    Args:
        layout: A report's distilled layout, from :func:`mussannoni.resources.layout_payload`.
        data: The report data::

                {
                  "title": str,                  # optional; defaults to the measured title
                  "columns": [str, ...],         # optional; override the measured column labels
                  "header": {"0.3": str, ...},   # optional; override any header cell, "row.col"
                  #           a list value sets one measured line each
                  "rows": [[value, ...], ...],   # required; or [{"LABEL": value, ...}, ...]
                  "loose": {2: str, ...},        # optional; replace a loose letterhead line
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

    unknown = set(data) - {"title", "columns", "header", "front_header", "rows", "loose"}
    if unknown:
        raise InvalidDataError(
            f"Unknown key(s) in data: {sorted(unknown)}. "
            "Expected any of: title, columns, header, front_header, rows, loose."
        )

    rows = _normalise_rows(data, labels, len(columns), layout["header"].get("fields"))

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

    # A compound first page carries measured bands above its data rows — a division summary, a
    # grade matrix — on its own finer grid. It is kept as measured rather than flattened onto the
    # repeating grid, which is why it also has its own capacity.
    front = layout.get("front")
    front_usable = bool(front and front.get("body") and front.get("value_columns"))
    first_page_rows = int(layout.get("first_page_rows") or 0) or per_page

    chunks: list[list[list[str]]] = []
    start = 0
    capacity = first_page_rows
    while start < len(rows):
        chunks.append(rows[start : start + capacity])
        start += capacity
        capacity = per_page
    if not chunks:
        chunks = [[]]

    row_height = float(body["row_height_pt"])
    header_height = float(layout["header"].get("height_pt", 0.0))
    page_template = layout["page"]
    decorations = layout.get("decorations") or {}

    loose_lines = deepcopy(decorations.get("loose_lines") or [])
    if data.get("loose"):
        loose_lines = _apply_loose_overrides(
            loose_lines, data["loose"], layout, styles, level, report_key
        )

    front_rows: list[dict[str, Any]] = []
    front_loose: list[dict[str, Any]] = []
    if front_usable:
        front_columns = [float(width) for width in front["columns"]]
        front_rows = deepcopy(front["rows"])
        column_map = front.get("body_to_front_column")
        if data.get("columns") is not None:
            label_row = int(front["row_count"]) - 1
            for index, label in enumerate(list(data["columns"])):
                target = int(column_map[index]) if column_map else index
                for cell in front_rows[label_row]["cells"]:
                    if int(cell["column"]) == target:
                        _rewrite_cell_text(
                            cell, _as_text(label), front_columns, styles, level, report_key
                        )
                        break
        if data.get("header"):
            _apply_header_overrides(
                front_rows,
                data["header"],
                layout,
                styles,
                level,
                report_key,
                columns=front_columns,
                row_map=front.get("header_row_map"),
                column_map=column_map,
            )
        if data.get("front_header"):
            # Addresses the front band's OWN rows and columns, which is how a caller fills a band
            # the repeating grid cannot describe — the division summary on `school-results`, the
            # grade matrix on its primary counterpart. Without this those bands would keep the
            # reference exam's figures.
            _apply_header_overrides(
                front_rows,
                data["front_header"],
                layout,
                styles,
                level,
                report_key,
                columns=front_columns,
            )
        front_loose = deepcopy(front.get("loose_lines") or [])
        if data.get("loose"):
            front_loose = _apply_loose_overrides(
                front_loose, data["loose"], layout, styles, level, report_key
            )

    pages: list[dict[str, Any]] = []
    for number, chunk in enumerate(chunks, start=1):
        on_front = front_usable and number == 1
        if on_front:
            page_columns = [float(width) for width in front["columns"]]
            band_rows = deepcopy(front_rows)
            band_height = float(front["height_pt"])
            page_table = front["table"]
            page_row_height = float(front["body"]["row_height_pt"])
            value_columns = [int(index) for index in front["value_columns"]]
            front_cells = front["body"]["cells"]
        else:
            page_columns = columns
            band_rows = deepcopy(header_rows)
            band_height = header_height
            page_table = layout["table"]
            page_row_height = row_height

        page_rows = band_rows
        for offset, values in enumerate(chunk):
            cells = []
            if on_front:
                for prototype, source in zip(front_cells, value_columns):
                    column = int(prototype["column"])
                    colspan = int(prototype.get("colspan", 1) or 1)
                    width = sum(
                        page_columns[index]
                        for index in range(column, min(column + colspan, len(page_columns)))
                    )
                    cells.append(
                        _body_cell(values[source], prototype, width, styles, level, report_key)
                    )
            else:
                for column, width in enumerate(page_columns):
                    # A handful of columns are merged away in every measured body row, so the
                    # measurement never saw a plain cell there and has no prototype for them.
                    # Borrow the report's most common cell shape rather than emitting an empty
                    # cell: the caller passed a value for that column and silently dropping it
                    # would be the worst of the available behaviours.
                    prototype = prototypes.get(column, fallback) | {"column": column}
                    cells.append(
                        _body_cell(values[column], prototype, width, styles, level, report_key)
                    )
            page_rows.append(
                {
                    "index": len(band_rows) + offset,
                    "height_pt": page_row_height,
                    "cells": cells,
                }
            )

        body_heights = [page_row_height] * len(chunk)
        pages.append(
            {
                "number": number,
                "width_pt": float(page_template["width_pt"]),
                "height_pt": float(page_template["height_pt"]),
                "orientation": page_template["orientation"],
                "table_x_pt": float(page_table["x_pt"]),
                "table_y_pt": float(page_table["y_pt"]),
                "table_width_pt": float(page_table["width_pt"]),
                "table_height_pt": round(band_height + page_row_height * len(chunk), 3),
                "columns": page_columns,
                "header_rows": int(
                    front["row_count"] if on_front else layout["header"]["row_count"]
                ),
                "rows": page_rows,
                "vectors": deepcopy(
                    (front.get("vectors") or []) if on_front
                    else (decorations.get("vectors") or [])
                ),
                "rules": _synthesise_rules(
                    layout,
                    body_heights,
                    columns=page_columns,
                    table=page_table,
                    header_height=band_height,
                    rule=front.get("rule") if on_front else layout.get("rule"),
                ),
                "loose_lines": deepcopy(front_loose if on_front else loose_lines),
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
