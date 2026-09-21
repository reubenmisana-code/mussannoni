"""Readers for extracted evidence.

Extraction writes interned, compact JSON so 267 reference pages stay reviewable in git.
Every consumer rehydrates through this module rather than parsing the files by hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Style:
    font: str
    size_pt: float
    bold: bool
    italic: bool
    colour: tuple[float, float, float]
    alpha: int

    @property
    def css_colour(self) -> str:
        return "color(srgb " + " ".join(f"{channel:.6f}" for channel in self.colour) + ")"

    @property
    def hex_colour(self) -> str:
        return "#" + "".join(
            f"{max(0, min(255, round(channel * 255))):02x}" for channel in self.colour
        )

    @property
    def weight(self) -> int:
        return 700 if self.bold else 400


@dataclass(frozen=True, slots=True)
class Span:
    style: Style
    x0: float
    y0: float
    x1: float
    y1: float
    ox: float
    oy: float
    text: str
    rotation: int = 0
    char_offsets: tuple[float, ...] = ()

    @property
    def width(self) -> float:
        return round(self.x1 - self.x0, 3)

    @property
    def is_rotated(self) -> bool:
        return self.rotation != 0


@dataclass(frozen=True, slots=True)
class Paint:
    kind: str
    fill: tuple[float, float, float] | None
    fill_opacity: float
    stroke: tuple[float, float, float] | None
    stroke_width: float

    @staticmethod
    def _css(colour: tuple[float, float, float] | None) -> str | None:
        if colour is None:
            return None
        return "color(srgb " + " ".join(f"{channel:.6f}" for channel in colour) + ")"

    @property
    def fill_css(self) -> str | None:
        return self._css(self.fill)

    @property
    def stroke_css(self) -> str | None:
        return self._css(self.stroke)

    @property
    def fill_hex(self) -> str | None:
        if self.fill is None:
            return None
        return "#" + "".join(
            f"{max(0, min(255, round(channel * 255))):02x}" for channel in self.fill
        )


@dataclass(frozen=True, slots=True)
class Rect:
    paint: Paint
    x: float
    y: float
    w: float
    h: float

    @property
    def x1(self) -> float:
        return round(self.x + self.w, 3)

    @property
    def y1(self) -> float:
        return round(self.y + self.h, 3)

    @property
    def is_vertical_rule(self) -> bool:
        return self.w <= 1.5 and self.h >= 5

    @property
    def is_horizontal_rule(self) -> bool:
        return self.h <= 1.5 and self.w >= 5

    @property
    def is_cell(self) -> bool:
        return self.w > 1.5 and self.h > 1.5


@dataclass(frozen=True, slots=True)
class VectorPath:
    paint: Paint
    items: tuple[tuple, ...]

    @property
    def is_rectangular(self) -> bool:
        return all(item[0] == "re" for item in self.items)

    def svg_path(self) -> str:
        commands: list[str] = []
        for item in self.items:
            kind = item[0]
            values = item[1:]
            if kind == "re":
                x, y, w, h = values
                commands.append(f"M{x} {y}h{w}v{h}h{-w}Z")
            elif kind == "l":
                x0, y0, x1, y1 = values
                commands.append(f"M{x0} {y0}L{x1} {y1}")
            elif kind == "c":
                x0, y0, x1, y1, x2, y2, x3, y3 = values
                commands.append(f"M{x0} {y0}C{x1} {y1} {x2} {y2} {x3} {y3}")
            elif kind == "qu":
                points = list(values)
                head = f"M{points[0]} {points[1]}"
                rest = "".join(f"L{points[i]} {points[i + 1]}" for i in range(2, len(points), 2))
                commands.append(head + rest + "Z")
        return "".join(commands)


@dataclass(slots=True)
class PageEvidence:
    number: int
    width_pt: float
    height_pt: float
    orientation: str
    spans: list[Span]
    rects: list[Rect]
    paths: list[VectorPath]
    geometry: dict[str, Any]

    @property
    def cells(self) -> list[Rect]:
        return [rect for rect in self.rects if rect.is_cell]

    @property
    def vertical_rules(self) -> list[Rect]:
        return [rect for rect in self.rects if rect.is_vertical_rule]

    @property
    def horizontal_rules(self) -> list[Rect]:
        return [rect for rect in self.rects if rect.is_horizontal_rule]

    @property
    def curved_paths(self) -> list[VectorPath]:
        return [path for path in self.paths if not path.is_rectangular]


def load_evidence(directory: Path) -> list[PageEvidence]:
    spans_doc = json.loads((directory / "spans.json").read_text(encoding="utf-8"))
    rules_doc = json.loads((directory / "rules.json").read_text(encoding="utf-8"))
    geometry_doc = json.loads((directory / "geometry.json").read_text(encoding="utf-8"))

    styles = [
        Style(
            font=item["font"],
            size_pt=item["size_pt"],
            bold=item["bold"],
            italic=item["italic"],
            colour=tuple(item["colour"]),
            alpha=item["alpha"],
        )
        for item in spans_doc["styles"]
    ]
    paints = [
        Paint(
            kind=item["kind"],
            fill=tuple(item["fill"]) if item.get("fill") else None,
            fill_opacity=item.get("fill_opacity", 1.0),
            stroke=tuple(item["stroke"]) if item.get("stroke") else None,
            stroke_width=item.get("stroke_width", 0.0),
        )
        for item in rules_doc["paints"]
    ]
    geometry_by_page = {page["page_number"]: page for page in geometry_doc["pages"]}
    rules_by_page = {page["page"]: page for page in rules_doc["pages"]}

    pages: list[PageEvidence] = []
    for page_doc in spans_doc["pages"]:
        number = page_doc["page"]
        geometry = geometry_by_page[number]
        spans = [
            Span(
                styles[row[0]],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8] if len(row) > 8 else 0,
                tuple(row[9]) if len(row) > 9 else (),
            )
            for row in page_doc["spans"]
        ]
        paths: list[VectorPath] = []
        rects: list[Rect] = []
        for row in rules_by_page[number]["paths"]:
            paint = paints[row[0]]
            items = tuple(tuple(item) for item in row[1:])
            paths.append(VectorPath(paint, items))
            for item in items:
                if item[0] == "re":
                    rects.append(Rect(paint, item[1], item[2], item[3], item[4]))
        pages.append(
            PageEvidence(
                number=number,
                width_pt=geometry["width_pt"],
                height_pt=geometry["height_pt"],
                orientation=geometry["orientation"],
                spans=spans,
                rects=rects,
                paths=paths,
                geometry=geometry,
            )
        )
    return pages
