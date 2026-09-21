"""Reconstruct a real table grid from measured page evidence.

These reports are spreadsheet prints. Each page paints a few large background regions and
then draws every gridline as a thin filled rectangle, so the table can be recovered
mechanically:

* vertical gridlines give the column boundaries,
* horizontal gridlines give the row boundaries,
* background regions give cell fills,
* absence of a gridline between two adjacent slots means the source cells were merged.

The result is an HTML table with measured column widths, row heights, colspans, rowspans,
fills, borders and per-cell text runs - structure, not traced glyph coordinates.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from tools.evidence import PageEvidence, Rect, Span, Style, VectorPath

EDGE_TOLERANCE = 1.6
CONTAIN_SLACK = 0.5
MIN_BORDER_PT = 0.24


def cluster(values: list[float], tolerance: float = EDGE_TOLERANCE) -> list[float]:
    """Collapse near-identical edges. Gridlines are drawn as pairs, so pairs merge here."""
    if not values:
        return []
    ordered = sorted(values)
    groups: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - groups[-1][0] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [round(sum(group) / len(group), 2) for group in groups]


def nearest_index(value: float, edges: list[float], tolerance: float) -> int | None:
    best_index = None
    best_delta = tolerance
    for index, edge in enumerate(edges):
        delta = abs(edge - value)
        if delta <= best_delta:
            best_delta = delta
            best_index = index
    return best_index


@dataclass(slots=True)
class Run:
    text: str
    style: Style
    x0: float
    x1: float
    baseline: float
    origin_x: float = 0.0
    rotation: int = 0
    y_extent: float = 0.0
    char_offsets: tuple[float, ...] = ()


@dataclass(slots=True)
class Cell:
    row: int
    column: int
    row_span: int
    column_span: int
    x: float
    y: float
    width: float
    height: float
    fill: tuple[float, float, float] | None = None
    runs: list[Run] = field(default_factory=list)
    borders: dict[str, dict[str, Any]] = field(default_factory=dict)
    align: str = "left"
    pad_left: float = 0.0
    pad_right: float = 0.0
    baseline_offset: float = 0.0

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


@dataclass(slots=True)
class PageGrid:
    number: int
    width_pt: float
    height_pt: float
    orientation: str
    column_edges: list[float]
    row_edges: list[float]
    cells: list[Cell]
    header_rows: int
    loose_spans: list[Span]
    curved_paths: list[VectorPath]
    rules: list[Rect] = field(default_factory=list)

    @property
    def column_widths(self) -> list[float]:
        return [
            round(b - a, 2) for a, b in zip(self.column_edges, self.column_edges[1:], strict=False)
        ]

    @property
    def row_heights(self) -> list[float]:
        return [round(b - a, 2) for a, b in zip(self.row_edges, self.row_edges[1:], strict=False)]


class RuleIndex:
    """Gridlines bucketed by the boundary they sit on, for fast merge decisions."""

    def __init__(self, rules: list[Rect], edges: list[float], *, vertical: bool) -> None:
        self.buckets: dict[int, list[tuple[float, float, Rect]]] = defaultdict(list)
        for rule in rules:
            centre = (rule.x + rule.w / 2) if vertical else (rule.y + rule.h / 2)
            index = nearest_index(centre, edges, EDGE_TOLERANCE)
            if index is None:
                continue
            extent = (rule.y, rule.y + rule.h) if vertical else (rule.x, rule.x + rule.w)
            self.buckets[index].append((extent[0], extent[1], rule))

    def covering(self, edge_index: int, start: float, end: float) -> Rect | None:
        overlapping = self.overlapping(edge_index, start, end)
        return overlapping[0] if overlapping else None

    def overlapping(self, edge_index: int, start: float, end: float) -> list[Rect]:
        return [
            rule
            for low, high, rule in self.buckets.get(edge_index, ())
            if low < end - CONTAIN_SLACK and high > start + CONTAIN_SLACK
        ]


def fill_at(regions: list[Rect], x: float, y: float) -> tuple[float, float, float] | None:
    """Last painted background region containing the point wins."""
    found = None
    for rect in regions:
        if (
            rect.x - CONTAIN_SLACK <= x <= rect.x1 + CONTAIN_SLACK
            and rect.y - CONTAIN_SLACK <= y <= rect.y1 + CONTAIN_SLACK
        ):
            found = rect.paint.fill
    return found


def border_style(rules: list[Rect], *, vertical: bool) -> dict[str, Any] | None:
    """Describe the border on one cell edge.

    These exports draw a plain gridline as one hairline and an emphasised one as two parallel
    hairlines with an equal gap. The second case is a CSS `double` border, whose three equal
    thirds reproduce the reference band exactly; treating it as a single line loses half the
    rule pixels and puts the edge in the wrong place.
    """
    if not rules:
        return None
    if vertical:
        near = min(rule.x for rule in rules)
        far = max(rule.x1 for rule in rules)
        thin = min(rule.w for rule in rules)
        starts = {round(rule.x, 2) for rule in rules}
    else:
        near = min(rule.y for rule in rules)
        far = max(rule.y1 for rule in rules)
        thin = min(rule.h for rule in rules)
        starts = {round(rule.y, 2) for rule in rules}

    total = round(far - near, 2)
    doubled = len(starts) >= 2 and total >= thin * 2.5
    width = total if doubled else thin
    colour = rules[0].paint.fill or rules[0].paint.stroke or (0.0, 0.0, 0.0)
    return {
        "width_pt": round(max(width, MIN_BORDER_PT), 2),
        "style": "double" if doubled else "solid",
        "colour": [round(channel, 4) for channel in colour],
    }


def build_page_grid(page: PageEvidence) -> PageGrid:
    regions = [rect for rect in page.rects if rect.is_cell]
    verticals = page.vertical_rules
    horizontals = page.horizontal_rules

    column_edges = cluster(
        [rect.x for rect in regions]
        + [rect.x1 for rect in regions]
        + [rule.x + rule.w / 2 for rule in verticals]
    )
    row_edges = cluster(
        [rect.y for rect in regions]
        + [rect.y1 for rect in regions]
        + [rule.y + rule.h / 2 for rule in horizontals]
    )
    if len(column_edges) < 2 or len(row_edges) < 2:
        return PageGrid(
            number=page.number,
            width_pt=page.width_pt,
            height_pt=page.height_pt,
            orientation=page.orientation,
            column_edges=column_edges,
            row_edges=row_edges,
            cells=[],
            header_rows=0,
            loose_spans=list(page.spans),
            curved_paths=page.curved_paths,
            rules=verticals + horizontals,
        )

    vertical_index = RuleIndex(verticals, column_edges, vertical=True)
    horizontal_index = RuleIndex(horizontals, row_edges, vertical=False)

    columns = len(column_edges) - 1
    rows = len(row_edges) - 1
    cells: list[Cell] = []
    grid_fill: list[list[tuple[float, float, float] | None]] = []
    for row in range(rows):
        centre_y = (row_edges[row] + row_edges[row + 1]) / 2
        grid_fill.append(
            [
                fill_at(regions, (column_edges[c] + column_edges[c + 1]) / 2, centre_y)
                for c in range(columns)
            ]
        )

    # Horizontal merge: adjacent slots join unless a gridline or a fill change separates them.
    for row in range(rows):
        top, bottom = row_edges[row], row_edges[row + 1]
        column = 0
        while column < columns:
            span = 1
            while column + span < columns:
                edge = column + span
                separated = vertical_index.covering(edge, top, bottom) is not None
                fill_changes = grid_fill[row][column] != grid_fill[row][edge]
                if separated or fill_changes:
                    break
                span += 1
            cells.append(
                Cell(
                    row=row,
                    column=column,
                    row_span=1,
                    column_span=span,
                    x=column_edges[column],
                    y=top,
                    width=round(column_edges[column + span] - column_edges[column], 2),
                    height=round(bottom - top, 2),
                    fill=grid_fill[row][column],
                )
            )
            column += span

    loose = attach_text(cells, page.spans)
    # The header band is decided before merging: a rowspan may not cross the thead/tbody
    # boundary in HTML, so vertical merges have to stop there or every body row shifts.
    header_rows = detect_header_rows(cells)
    merge_vertically(cells, horizontal_index, row_edges, header_rows)
    if not tiles_exactly(cells, rows, columns):
        # A rowspan that does not tile leaves a hole, and HTML fills holes by sliding the rest
        # of the row sideways - text then inherits a cell that moved. Vertical merging is only
        # a structural nicety, so it is dropped for this page rather than risk the geometry.
        for cell in cells:
            if cell.row_span == 0:
                cell.row_span = 1
            elif cell.row_span > 1:
                cell.row_span = 1
                cell.height = round(row_edges[cell.row + 1] - cell.y, 2)
    attach_borders(cells, vertical_index, horizontal_index, column_edges, row_edges)
    measure_alignment(cells)
    rules = verticals + horizontals

    return PageGrid(
        number=page.number,
        width_pt=page.width_pt,
        height_pt=page.height_pt,
        orientation=page.orientation,
        column_edges=column_edges,
        row_edges=row_edges,
        cells=[cell for cell in cells if cell.row_span > 0],
        header_rows=header_rows,
        loose_spans=loose,
        curved_paths=page.curved_paths,
        rules=rules,
    )


def tiles_exactly(cells: list[Cell], rows: int, columns: int) -> bool:
    """Every grid slot must be covered by exactly one emitted cell.

    HTML places a row's cells left to right into whatever columns are still free, so a hole or
    an overlap does not fail loudly - it silently shifts the rest of the row, and any text
    positioned relative to those cells moves with it.
    """
    covered = [[0] * columns for _ in range(rows)]
    for cell in cells:
        if cell.row_span == 0:
            continue
        for row in range(cell.row, min(cell.row + cell.row_span, rows)):
            for column in range(cell.column, min(cell.column + cell.column_span, columns)):
                covered[row][column] += 1
    return all(count == 1 for row in covered for count in row)


def merge_vertically(
    cells: list[Cell],
    horizontal_index: RuleIndex,
    row_edges: list[float],
    header_rows: int = 0,
) -> None:
    """Collapse stacked empty slots that share a fill and have no gridline between them.

    Merges never cross ``header_rows``: HTML row groups clip rowspans at the thead/tbody
    boundary, which would silently shift every body row one column to the left.
    """
    by_position = {(cell.row, cell.column): cell for cell in cells}
    for cell in sorted(cells, key=lambda item: (item.row, item.column)):
        if cell.row_span == 0 or cell.has_text:
            continue
        while True:
            next_row = cell.row + cell.row_span
            if header_rows and cell.row < header_rows <= next_row:
                break
            below = by_position.get((next_row, cell.column))
            if below is None or below.row_span == 0:
                break
            if below.column_span != cell.column_span or below.fill != cell.fill or below.has_text:
                break
            boundary = cell.row + cell.row_span
            if horizontal_index.covering(boundary, cell.x, cell.x + cell.width) is not None:
                break
            cell.row_span += below.row_span
            cell.height = round(row_edges[cell.row + cell.row_span] - cell.y, 2)
            below.row_span = 0


def attach_borders(
    cells: list[Cell],
    vertical_index: RuleIndex,
    horizontal_index: RuleIndex,
    column_edges: list[float],
    row_edges: list[float],
) -> None:
    for cell in cells:
        if cell.row_span == 0:
            continue
        top, bottom = cell.y, cell.y + cell.height
        left = cell.x, cell.x + cell.width
        sides = {
            "left": (vertical_index.overlapping(cell.column, top, bottom), True),
            "right": (
                vertical_index.overlapping(cell.column + cell.column_span, top, bottom),
                True,
            ),
            "top": (horizontal_index.overlapping(cell.row, *left), False),
            "bottom": (horizontal_index.overlapping(cell.row + cell.row_span, *left), False),
        }
        for side, (rules, vertical) in sides.items():
            style = border_style(rules, vertical=vertical)
            if style:
                cell.borders[side] = style


def attach_text(cells: list[Cell], spans: list[Span]) -> list[Span]:
    index: dict[tuple[int, int], Cell] = {}
    for cell in cells:
        index[(cell.row, cell.column)] = cell
    ordered = sorted(cells, key=lambda cell: (cell.y, cell.x))
    loose: list[Span] = []
    for span in spans:
        centre_x = (span.x0 + span.x1) / 2
        baseline = span.oy
        best: Cell | None = None
        best_area = None
        for cell in ordered:
            if not (cell.x - CONTAIN_SLACK <= centre_x <= cell.x + cell.width + CONTAIN_SLACK):
                continue
            if not (cell.y - CONTAIN_SLACK <= baseline <= cell.y + cell.height + CONTAIN_SLACK):
                continue
            area = cell.width * cell.height
            if best_area is None or area < best_area:
                best, best_area = cell, area
        if best is None:
            loose.append(span)
            continue
        best.runs.append(
            Run(
                span.text,
                span.style,
                span.x0,
                span.x1,
                span.oy,
                span.ox,
                span.rotation,
                span.y0 if span.rotation else 0.0,
                span.char_offsets,
            )
        )
    for cell in cells:
        cell.runs.sort(key=lambda run: (round(run.baseline, 1), run.x0))
    return loose


def measure_alignment(cells: list[Cell]) -> None:
    """Alignment and padding come from where the text actually sits inside the cell."""
    for cell in cells:
        # A rotated run's horizontal extent is its line height, not its text length, so
        # horizontal alignment is meaningless for it.
        if not cell.runs or any(run.rotation for run in cell.runs):
            continue
        left_gap = round(min(run.x0 for run in cell.runs) - cell.x, 2)
        right_gap = round(cell.x + cell.width - max(run.x1 for run in cell.runs), 2)
        cell.baseline_offset = round(min(run.baseline for run in cell.runs) - cell.y, 2)
        if abs(left_gap - right_gap) <= 0.75:
            cell.align = "center"
        elif left_gap <= right_gap:
            cell.align = "left"
            cell.pad_left = max(left_gap, 0.0)
        else:
            cell.align = "right"
            cell.pad_right = max(right_gap, 0.0)


def detect_header_rows(cells: list[Cell]) -> int:
    counts: dict[int, int] = defaultdict(int)
    for cell in cells:
        if cell.row_span and cell.has_text:
            counts[cell.row] += 1
    if not counts:
        return 0
    busiest = max(counts.values())
    for row in sorted(counts):
        if counts[row] >= max(3, busiest * 0.6):
            return row + 1
    return min(counts) + 1


def build_grids(pages: list[PageEvidence]) -> list[PageGrid]:
    return [build_page_grid(page) for page in pages]
