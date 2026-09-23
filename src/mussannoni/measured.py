"""Place a caller's data into a report's measured document.

Design credit: Mussa Nnoni — SARS (sars.ac.tz).

Why this exists
---------------
:mod:`mussannoni.table` rebuilds a report as a flat table from a distilled ``layout.json``. That
throws away whatever does not fit the shape of one repeating table: the bands a first page carries
above its rows, the grid a compound page is measured on, the later pages of a report that is
actually several tables in sequence. Each of those had to be reconstructed, and reconstruction
loses to measurement every time.

This module does not reconstruct anything. It loads the report's measured document — the same
geometry the fidelity workshop reproduces — replaces the values, and hands it to
:func:`mussannoni.render_document`. Every band, every per-page column grid, every measured rule
and vector and every page of a multi-section report is carried as measured, because it was never
taken apart.

It is also smaller. The 46 measured documents ship gzipped in about 2 MB; the 46 distilled
layouts are 3.85 MB.

How a value is placed
---------------------
By **column identity**, never by row shape. ``layout.json`` ships ``header.fields``, the field
name of each measured column, so a cell is data if its column carries a name.

Row shape cannot be used for this and trying it leaks the reference's data. Whether a cell exists
in a measured row at all depends on whether the reference happened to print something there, so
two rows of the same table differ: on ``secondary/school-results`` page 2, two of thirty-seven
candidate rows have a different cell signature. Keyed on shape, those two rows are not recognised
as data and are emitted verbatim — which puts a real candidate from the sample exam into another
school's report. Keyed on column identity every data cell is overwritten or blanked, and a
measured row the caller has no value for is removed rather than left standing.

Capacity
--------
Not computed. Each measured page holds the number of rows the reference put on it, so the rows are
distributed across the measured pages in order. A caller with more rows than the reference measured
gets copies of the last full data page; a caller with fewer gets fewer pages.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from functools import lru_cache
from typing import Any

from .errors import InvalidDataError
from .resources import report_dir
from .table import _text_width as _table_text_width

DOCUMENT_NAME = "document.json.gz"


@lru_cache(maxsize=64)
def _load(level: str, report_key: str) -> str:
    path = report_dir(level, report_key) / DOCUMENT_NAME
    if not path.exists():
        raise InvalidDataError(
            f"Report {report_key!r} at level {level!r} has no measured document; the package was "
            "built without one."
        )
    with gzip.open(path, "rb") as handle:
        return handle.read().decode("utf-8")


def measured_document(level: str, report_key: str) -> dict[str, Any]:
    """The report's measured document, ready to have values placed into it."""
    return json.loads(_load(level, report_key))


def has_measured_document(level: str, report_key: str) -> bool:
    return (report_dir(level, report_key) / DOCUMENT_NAME).exists()


def _cell_text(cell: Mapping[str, Any]) -> str:
    return "".join(
        "".join(run.get("text", "") for run in (line.get("runs") or []))
        for line in (cell.get("lines") or [])
    ).strip()


def _as_text(value: Any) -> str:
    """Render a value as the report would print it.

    ``None`` is a blank cell rather than the string "None": these tables have plenty of
    legitimately empty cells and they must not read as data.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _place(cell: dict[str, Any], text: str) -> None:
    """Put a caller's value into a measured cell, or empty the cell.

    The measured line keeps its class, its baseline offset within the row and its rotation — that
    is the report's typography. The letter spacing goes, because it belonged to the old string.
    """
    lines = cell.get("lines") or []
    if not text:
        cell["lines"] = []
        return
    if not lines:
        return
    line = lines[0]
    runs = line.get("runs") or []
    line["letter_spacing_pt"] = 0.0
    line["runs"] = [
        {
            "class": runs[0].get("class", line.get("class", "t0")) if runs else
            line.get("class", "t0"),
            "text": text,
            "chunks": [],
        }
    ]
    cell["lines"] = [line]


def _row_values(row: Any, fields: Sequence[str], position: int) -> dict[int, str]:
    """A caller's row as ``{column index: text}``, from a mapping or a positional sequence."""
    by_name = {name: index for index, name in enumerate(fields) if name}
    values: dict[int, str] = {}
    if isinstance(row, Mapping):
        for key, value in row.items():
            if isinstance(key, str) and key in by_name:
                values[by_name[key]] = _as_text(value)
            elif isinstance(key, int):
                values[key] = _as_text(value)
            elif isinstance(key, str) and key.isdigit():
                values[int(key)] = _as_text(value)
            else:
                raise InvalidDataError(
                    f"data['rows'][{position}] has key {key!r}, which is not one of this report's "
                    f"column fields {sorted(by_name)}"
                )
        return values
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
        named = [index for index, name in enumerate(fields) if name]
        if len(row) > len(named):
            raise InvalidDataError(
                f"data['rows'][{position}] has {len(row)} values but this report has "
                f"{len(named)} data columns"
            )
        for slot, value in zip(named, row):
            values[slot] = _as_text(value)
        return values
    raise InvalidDataError(
        f"data['rows'][{position}] must be a mapping or a list, got {type(row).__name__}"
    )


def _text_of(cell: Mapping[str, Any]) -> str:
    return _cell_text(cell)


def _rewrite(cell: dict[str, Any], value: Any, span_pt: float,
             styles: Mapping[str, Any], level: str, report_key: str) -> None:
    """Put new text into a measured cell of a static band.

    ``value`` may be one string, or one string per measured line — a letterhead is a single cell
    holding the authority lines, the region, the exam title and the scope.

    A line whose text is unchanged is left **completely** untouched: its measured offset, its
    letter spacing and its per-cluster corrections all stay. That matters because every caller
    supplies the same authority lines, and re-placing them from font metrics moves them — measured
    at 193pt out of position on ``school-results``. Nothing that has not changed is recomputed.
    """
    lines = cell.get("lines") or []
    if not lines:
        return
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        texts = [_as_text(value)]
    else:
        texts = [_as_text(item) for item in value]
        if len(texts) > len(lines):
            raise InvalidDataError(
                f"An override for {report_key!r} supplied {len(texts)} lines but the measured cell "
                f"has {len(lines)}"
            )

    if not any(texts):
        cell["lines"] = []
        return

    kept: list[dict[str, Any]] = []
    for index, line in enumerate(lines[: len(texts)]):
        text = texts[index]
        if not text:
            continue
        old = "".join(run.get("text", "") for run in (line.get("runs") or []))
        if text == old:
            kept.append(line)
            continue
        line_class = line.get("class", "t0")
        style = styles.get(line_class, {"size_pt": 8.0, "base14": "helv"})
        width = _measure(text, style, level, report_key)
        old_width = _measure(old, style, level, report_key)
        old_left = float(line.get("left_pt", 0.0) or 0.0)
        if old_width > 0 and abs((old_left + old_width / 2.0) - span_pt / 2.0) <= 6.0:
            # The reference centres this line across the cell; keep it centred for its new text.
            line["left_pt"] = round(max(0.0, (span_pt - width) / 2.0), 3)
        elif cell.get("align") == "right":
            line["left_pt"] = round(max(0.0, span_pt - float(cell.get("pad_right", 0.0) or 0.0)
                                        - width), 3)
        elif cell.get("align") == "center":
            line["left_pt"] = round(max(0.0, (span_pt - width) / 2.0), 3)
        line["letter_spacing_pt"] = 0.0
        line["runs"] = [{"class": line_class, "text": text, "chunks": []}]
        kept.append(line)
    cell["lines"] = kept


def _measure(text: str, style: Mapping[str, Any], level: str, report_key: str) -> float:
    if not text:
        return 0.0
    return _table_text_width(text, style, level, report_key)


def _apply_band_overrides(page: dict[str, Any], overrides: Mapping[str, Any],
                          styles: Mapping[str, Any], level: str, report_key: str) -> None:
    """Replace text in a measured page's static bands, addressed ``"row.column"``.

    The addresses are the measured document's own row and column indices, so there is one scheme
    for the letterhead, a division summary, a grade matrix or a section heading — no separate
    header and front-matter vocabularies, because the document was never taken apart.
    """
    columns = [float(width) for width in page["columns"]]
    for address, value in overrides.items():
        try:
            row_text, column_text = str(address).split(".", 1)
            row_index, column_index = int(row_text), int(column_text)
        except ValueError as error:
            raise InvalidDataError(
                f"Override key {address!r} must be 'row.column', e.g. '0.3'"
            ) from error
        if not 0 <= row_index < len(page["rows"]):
            raise InvalidDataError(
                f"Override {address!r} names row {row_index}, but this page has "
                f"{len(page['rows'])} rows"
            )
        for cell in page["rows"][row_index]["cells"]:
            if int(cell["column"]) != column_index:
                continue
            start = int(cell["column"])
            stop = min(start + int(cell.get("colspan", 1) or 1), len(columns))
            _rewrite(cell, value, sum(columns[start:stop]), styles, level, report_key)
            break
        else:
            raise InvalidDataError(
                f"Override {address!r} names column {column_index}, which has no cell in row "
                f"{row_index}"
            )


def _page_plan(page: Mapping[str, Any]) -> list[int]:
    """Which of a measured page's rows carry data.

    Recorded by the build step against the reference, not decided here. A renderer that had to work
    this out for itself would have to tell a repeated label band from a row of values, and the only
    signals available at runtime — cell shape, numeric-looking text — are content-dependent and get
    it wrong.
    """
    recorded = page.get("data_rows")
    if recorded is None:
        raise InvalidDataError(
            "This measured document was built without a data-row plan; rebuild the packaged "
            "resources."
        )
    return [int(index) for index in recorded]


def build_measured_document(
    document: Mapping[str, Any],
    layout: Mapping[str, Any],
    data: Mapping[str, Any],
) -> dict[str, Any]:
    """Place ``data`` into a report's measured ``document``.

    Args:
        document: The report's measured document, from :func:`measured_document`.
        layout: The report's layout, for ``header.fields`` — the column identity.
        data: ``{"rows": [...], "title": str}``. Rows may be mappings keyed by field name or
            positional sequences over the report's data columns.

    Returns:
        A geometry document for :func:`mussannoni.render_document`.
    """
    if not isinstance(data, Mapping):
        raise InvalidDataError(f"data must be a mapping, got {type(data).__name__}")
    unknown = set(data) - {"rows", "title", "bands", "loose"}
    if unknown:
        raise InvalidDataError(
            f"Unknown key(s) in data: {sorted(unknown)}. Expected any of: rows, title, bands, "
            "loose."
        )

    fields = list(layout["header"].get("fields") or [])
    if not any(fields):
        raise InvalidDataError(
            f"Report {layout['report_key']!r} has no column identity in the packaged layout, so "
            "values cannot be placed safely. Add it to catalog/bindings.yaml."
        )
    data_columns = {index for index, name in enumerate(fields) if name}

    raw = data.get("rows")
    if raw is None:
        raise InvalidDataError("data['rows'] is required")
    rows = [_row_values(row, fields, position) for position, row in enumerate(raw)]

    built = deepcopy(dict(document))

    bands = data.get("bands") or {}
    per_page = _bands_by_page(bands, len(built["pages"]))
    loose = data.get("loose") or {}
    loose_per_page = _loose_by_page(loose, len(built["pages"]))
    styles = layout.get("text_styles") or {}
    for page, overrides, loose_overrides in zip(built["pages"], per_page, loose_per_page):
        if overrides:
            _apply_band_overrides(
                page, overrides, styles, layout["level"], layout["report_key"]
            )
        if loose_overrides:
            _apply_loose(
                page, loose_overrides, styles, layout["level"], layout["report_key"]
            )
        _blank_unsupplied_loose_figures(page, set(loose_overrides))
        # Every figure the caller did not supply is emptied. Without this a generated report carries
        # the measured exam's own totals, averages, ranks and competency bands wherever the reference
        # printed them — inside the header band and in any further section.
        _blank_unsupplied_figures(page, set(overrides))

    pages: list[dict[str, Any]] = []
    cursor = 0
    template_page: dict[str, Any] | None = None
    template_plan: list[int] = []

    for page in built["pages"]:
        plan = _page_plan(page)
        if not plan:
            # No data rows of this table: a heading page, or a further section the report prints
            # whole on its own grid. Carried verbatim, and never dropped for running out of rows.
            pages.append(page)
            continue
        if template_page is None or len(plan) > len(template_plan):
            template_page, template_plan = deepcopy(page), list(plan)
        consumed = _fill(page, plan, rows, cursor, data_columns)
        cursor += consumed
        if consumed:
            pages.append(page)

    # More rows than the reference measured: repeat its fullest data page, which is the only
    # capacity the reference ever demonstrated.
    while cursor < len(rows) and template_page is not None and template_plan:
        extra = deepcopy(template_page)
        consumed = _fill(extra, template_plan, rows, cursor, data_columns)
        if consumed == 0:
            break
        cursor += consumed
        pages.append(extra)

    built["pages"] = [page for page in pages if page["rows"]]
    for number, page in enumerate(built["pages"], start=1):
        page["number"] = number
        page.pop("data_rows", None)

    if cursor < len(rows):
        raise InvalidDataError(
            f"Report {layout['report_key']!r} could place only {cursor} of {len(rows)} rows."
        )

    report = dict(built.get("report") or {})
    if data.get("title"):
        report["title"] = _as_text(data["title"])
    built["report"] = report
    return built


def _bands_by_page(bands: Mapping[str, Any], page_count: int) -> list[dict[str, Any]]:
    """Split ``bands`` into one override map per page.

    An address may be ``"row.column"``, which means page 1 — the original spelling, unchanged — or
    ``"page.row.column"`` with a 1-based page number, which is how a further section is reached.
    ``school_results`` measures its division summary on page 14, so without page addressing those
    cells could be blanked but never filled.
    """
    out: list[dict[str, Any]] = [{} for _ in range(page_count)]
    for address, value in bands.items():
        parts = str(address).split(".")
        if not all(part.strip().lstrip("-").isdigit() for part in parts):
            raise InvalidDataError(
                f"Band address {address!r} must be 'row.column' or 'page.row.column'"
            )
        if len(parts) == 2:
            page_index, rest = 0, parts
        elif len(parts) == 3:
            page_index, rest = int(parts[0]) - 1, parts[1:]
        else:
            raise InvalidDataError(
                f"Band address {address!r} must be 'row.column' or 'page.row.column'"
            )
        if not 0 <= page_index < page_count:
            raise InvalidDataError(
                f"Band address {address!r} names page {page_index + 1}, but the document has "
                f"{page_count} pages"
            )
        out[page_index][".".join(rest)] = value
    return out


def _loose_by_page(loose: Mapping[str, Any], page_count: int) -> list[dict[str, Any]]:
    """Split loose overrides per page. ``"index"`` means page 1; ``"page.index"`` names a page."""
    out: list[dict[str, Any]] = [{} for _ in range(page_count)]
    for address, value in loose.items():
        parts = str(address).split(".")
        if not all(part.strip().isdigit() for part in parts) or len(parts) > 2:
            raise InvalidDataError(
                f"Loose address {address!r} must be 'index' or 'page.index'"
            )
        page_index = 0 if len(parts) == 1 else int(parts[0]) - 1
        if not 0 <= page_index < page_count:
            raise InvalidDataError(
                f"Loose address {address!r} names page {page_index + 1}, but the document has "
                f"{page_count} pages"
            )
        out[page_index][parts[-1]] = value
    return out


def _apply_loose(page: dict[str, Any], overrides: Mapping[str, Any],
                 styles: Mapping[str, Any], level: str, report_key: str) -> None:
    """Replace absolutely-positioned lines, addressed by index.

    Six reports draw their whole letterhead beside the table rather than inside a header band, so
    without this they have no way to replace the reference exam's region and title. A line centred on
    the page is re-centred for its new string; an empty value removes it. A line whose text is
    unchanged is left untouched, the same rule the band overrides follow.
    """
    lines = page.get("loose_lines") or []
    for address, value in overrides.items():
        index = int(str(address))
        if not 0 <= index < len(lines):
            raise InvalidDataError(
                f"Loose override {address!r} names line {index}, but this page has {len(lines)}"
            )
        line = lines[index]
        text = _as_text(value)
        old_text = "".join(run.get("text", "") for run in (line.get("runs") or []))
        if text == old_text:
            continue
        if not text:
            line["runs"] = []
            continue
        style = styles.get(line.get("class", "t0"), {"size_pt": 8.0, "base14": "helv"})
        width = _measure(text, style, level, report_key)
        was = _measure(old_text, style, level, report_key) if old_text else width
        # Keep the line's measured anchor: a centred line stays centred on its own midpoint.
        line["left_pt"] = float(line.get("left_pt", 0.0)) + (was - width) / 2.0
        line["runs"] = [{"text": text, "class": line.get("class", "t0")}]
    page["loose_lines"] = [
        line for line in lines if any(run.get("text") for run in (line.get("runs") or []))
    ]


def _blank_unsupplied_loose_figures(page: dict[str, Any], supplied: set[str]) -> int:
    """Empty every loose line the build marked ``figure`` and the caller did not supply."""
    roles = page.get("loose_roles") or {}
    lines = page.get("loose_lines") or []
    blanked = 0
    for address, role in roles.items():
        if role != "figure" or address in supplied:
            continue
        index = int(address)
        if 0 <= index < len(lines):
            lines[index]["runs"] = []
            blanked += 1
    if blanked:
        page["loose_lines"] = [
            line for line in lines if any(run.get("text") for run in (line.get("runs") or []))
        ]
    return blanked


def _blank_unsupplied_figures(page: dict[str, Any], supplied: set[str]) -> int:
    """Empty every ``figure`` cell the caller did not supply a value for.

    This is the safety property the measured path turns on. A report may be structurally complete and
    numerically empty, but it must never publish the measured exam's figures. The roles shipped with
    the document say which cells are computed values rather than labels, so this needs no test on the
    text — a cell is a figure because the build said so, against the reference.

    Removal, never replacement: the line is dropped rather than re-laid-out, so nothing is placed from
    font metrics and no unchanged text loses its measured offset.

    Returns the number of lines blanked, so a caller can assert the leak is closed.
    """
    roles = page.get("roles") or {}
    targets: dict[tuple[int, int], set[int] | None] = {}
    for address, role in roles.items():
        if role != "figure" or address in supplied:
            continue
        parts = address.split(".")
        if len(parts) < 2:
            continue
        row_index, column = int(parts[0]), int(parts[1])
        key = (row_index, column)
        if len(parts) == 2:
            targets[key] = None
        elif targets.get(key, set()) is not None:
            targets.setdefault(key, set()).add(int(parts[2]))  # type: ignore[union-attr]

    blanked = 0
    for (row_index, column), lines in targets.items():
        if not 0 <= row_index < len(page["rows"]):
            continue
        for cell in page["rows"][row_index]["cells"]:
            if int(cell["column"]) != column:
                continue
            measured = cell.get("lines") or []
            if lines is None:
                blanked += len(measured)
                cell["lines"] = []
            else:
                cell["lines"] = [
                    line for index, line in enumerate(measured) if index not in lines
                ]
                blanked += len(measured) - len(cell["lines"])
            break
    return blanked


def _fill(
    page: dict[str, Any],
    plan: Sequence[int],
    rows: Sequence[Mapping[int, str]],
    cursor: int,
    data_columns: set[int],
) -> int:
    """Fill a measured page's data rows, dropping any the caller has no values for."""
    positions = set(plan)
    kept: list[dict[str, Any]] = []
    used = 0
    for index, row in enumerate(page["rows"]):
        if index not in positions:
            kept.append(row)
            continue
        if cursor + used >= len(rows):
            # No value for this measured row. It is removed rather than left, so the reference's
            # own figures cannot survive in it.
            continue
        values = rows[cursor + used]
        used += 1
        for cell in row["cells"]:
            column = int(cell["column"])
            if column in data_columns:
                _place(cell, values.get(column, ""))
        kept.append(row)
    page["rows"] = kept
    return used
