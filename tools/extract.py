"""Machine-read the reference PDFs: text spans, vector rules, geometry, fonts, rasters.

Nothing here is hand-typed. Every number comes from PyMuPDF. Stored rasters are review
evidence only - fidelity metrics are always recomputed from the PDFs at 300 dpi.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

import pymupdf as fitz
from PIL import Image

from tools.common import (
    extraction_dir,
    find_report,
    load_catalog,
    reference_path,
    set_status,
    write_json,
)

METRIC_DPI = 300
REVIEW_RASTER_DPI = 150
RASTER_COLOURS = 256


class Interner:
    """Collapse repeated span styles and paint styles into a shared table."""

    def __init__(self) -> None:
        self.keys: dict[str, int] = {}
        self.values: list[dict[str, Any]] = []

    def intern(self, value: dict[str, Any]) -> int:
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if key not in self.keys:
            self.keys[key] = len(self.values)
            self.values.append(value)
        return self.keys[key]


def write_compact_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def colour_components(value: tuple[float, ...] | int | None) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, int):
        return [round(((value >> shift) & 0xFF) / 255, 4) for shift in (16, 8, 0)]
    if len(value) < 3:
        return None
    return [round(channel, 4) for channel in value[:3]]


def encode_item(item: tuple) -> list[Any]:
    """Encode one path primitive compactly: rectangles, lines, beziers and quads."""
    kind = item[0]
    if kind == "re":
        rectangle = item[1]
        return [
            "re",
            round(rectangle.x0, 2),
            round(rectangle.y0, 2),
            round(rectangle.width, 2),
            round(rectangle.height, 2),
        ]
    points: list[float] = []
    for value in item[1:]:
        if isinstance(value, fitz.Point):
            points += [round(value.x, 2), round(value.y, 2)]
        elif isinstance(value, fitz.Quad):
            for corner in (value.ul, value.ur, value.lr, value.ll):
                points += [round(corner.x, 2), round(corner.y, 2)]
    return [kind, *points]


def extract_paths(
    page: fitz.Page, paints: Interner
) -> tuple[list[list[Any]], list[dict[str, Any]]]:
    """Return (encoded paths, axis-aligned rectangles).

    Encoded paths preserve every painted primitive in paint order as
    ``[paint_index, item, item, ...]``. The rectangle view is what the table grid is built from.
    """
    encoded: list[list[Any]] = []
    rectangles: list[dict[str, Any]] = []
    for drawing in page.get_drawings(extended=True):
        if drawing.get("type") not in {"f", "s", "fs"}:
            continue
        paint = {
            "kind": drawing["type"],
            "fill": colour_components(drawing.get("fill")),
            "fill_opacity": round(drawing.get("fill_opacity") or 1.0, 3),
            "stroke": colour_components(drawing.get("color")),
            "stroke_width": round(drawing.get("width") or 0.0, 3),
        }
        paint_index = paints.intern(paint)
        items = [encode_item(item) for item in drawing.get("items", [])]
        encoded.append([paint_index, *items])
        for item in items:
            if item[0] == "re":
                rectangles.append({"x": item[1], "y": item[2], "w": item[3], "h": item[4]})
    return encoded, rectangles


def simple_font_widths(document: fitz.Document, xref: int) -> dict[str, int]:
    """Advance widths a non-embedded font declares, keyed by character code.

    A report that names Arial without embedding it still tells the renderer how wide every
    character is, and those numbers are not the installed face's: this corpus advances 'E' by
    672/1000 em where Arial itself uses 667. The reference is authoritative, so the widths have
    to be captured to be reproduced.
    """
    kind, first_char = document.xref_get_key(xref, "FirstChar")
    if kind != "int":
        return {}
    kind, value = document.xref_get_key(xref, "Widths")
    if kind == "xref":
        value = document.xref_object(int(value.split()[0]), compressed=True)
    if not isinstance(value, str) or "[" not in value:
        return {}
    numbers = value[value.index("[") + 1 : value.rindex("]")].split()
    widths: dict[str, int] = {}
    for offset, number in enumerate(numbers):
        try:
            width = round(float(number))
        except ValueError:
            continue
        if width:
            widths[str(int(first_char) + offset)] = width
    return widths


def rotation_of(line: dict[str, Any]) -> int:
    """Writing direction in degrees, from the line's direction vector.

    Vertical column headings are common in these reports - 38 of the 46 carry them - and a
    rotated span reports an origin that is not its left edge, so the rotation has to travel
    with the span or the text is rebuilt lying on its side.
    """
    cosine, sine = (round(value, 3) for value in line.get("dir", (1.0, 0.0)))
    if (cosine, sine) == (1.0, 0.0):
        return 0
    if (cosine, sine) in {(0.0, -1.0), (-0.0, -1.0)}:
        return 90
    if (cosine, sine) in {(-1.0, 0.0), (-1.0, -0.0)}:
        return 180
    if (cosine, sine) in {(0.0, 1.0), (-0.0, 1.0)}:
        return 270
    raise ValueError(f"Unsupported writing direction {(cosine, sine)}")


def character_offsets(span: dict[str, Any], rotation: int) -> list[float]:
    """Each character's advance from the start of its span, as the reference positions it.

    The declared font widths are not the whole story: these producers also emit explicit
    per-glyph adjustments, so the text on the page is spaced slightly differently from what the
    widths alone would give. Capturing the actual offsets is the only way to put every glyph
    back exactly where it was.
    """
    characters = span.get("chars") or []
    if len(characters) < 2:
        return []
    axis = 1 if rotation in (90, 270) else 0
    origin = float(characters[0]["origin"][axis])
    offsets = [round(float(char["origin"][axis]) - origin, 3) for char in characters]
    return offsets if any(offsets) else []


def extract_spans(page: fitz.Page, styles: Interner) -> list[list[Any]]:
    """Encode spans as ``[style_index, x0, y0, x1, y1, ox, oy, text, rotation, char_offsets]``.

    The two trailing fields are omitted when they carry nothing: rotation for horizontal text,
    and the character offsets for single-character spans.
    """
    spans: list[list[Any]] = []
    for block in page.get_text("rawdict", sort=True).get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            rotation = rotation_of(line)
            for span in line.get("spans", []):
                span["text"] = "".join(char["c"] for char in span.get("chars", []))
                bbox = span["bbox"]
                origin = span.get("origin") or (bbox[0], bbox[3])
                style_index = styles.intern(
                    {
                        "font": span["font"],
                        "size_pt": round(span["size"], 2),
                        "bold": bool(span["flags"] & 2**4) or "Bold" in span["font"],
                        "italic": bool(span["flags"] & 2**1),
                        "colour": colour_components(span["color"]),
                        "alpha": span.get("alpha", 255),
                    }
                )
                row: list[Any] = [
                    style_index,
                    round(bbox[0], 2),
                    round(bbox[1], 2),
                    round(bbox[2], 2),
                    round(bbox[3], 2),
                    round(float(origin[0]), 2),
                    round(float(origin[1]), 2),
                    span["text"],
                ]
                offsets = character_offsets(span, rotation)
                if rotation or offsets:
                    row.append(rotation)
                if offsets:
                    row.append(offsets)
                spans.append(row)
    return spans


def horizontal_bands(rectangles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Thin wide rectangles are horizontal rules; thin tall ones are column separators."""
    rules = [item for item in rectangles if item["h"] <= 1.5 and item["w"] >= 5]
    return [
        {"y": item["y"], "x0": item["x"], "x1": round(item["x"] + item["w"], 2)} for item in rules
    ]


def column_edges(rectangles: list[dict[str, Any]]) -> list[float]:
    separators = [item for item in rectangles if item["w"] <= 1.5 and item["h"] >= 5]
    return sorted({round(item["x"] + item["w"] / 2, 2) for item in separators})


def infer_geometry(
    page: fitz.Page,
    spans: list[list[Any]],
    rectangles: list[dict[str, Any]],
    styles: list[dict[str, Any]],
) -> dict[str, Any]:
    x0 = min((span[1] for span in spans), default=0.0)
    y0 = min((span[2] for span in spans), default=0.0)
    x1 = max((span[3] for span in spans), default=page.rect.width)
    y1 = max((span[4] for span in spans), default=page.rect.height)
    baselines = sorted({span[6] for span in spans})
    pitches = [round(b - a, 2) for a, b in pairwise(baselines) if 2 <= b - a <= 30]
    left_edges = Counter(round(span[1] * 2) / 2 for span in spans)
    sizes = Counter(styles[span[0]]["size_pt"] for span in spans)
    return {
        "page_number": page.number + 1,
        "width_pt": round(page.rect.width, 2),
        "height_pt": round(page.rect.height, 2),
        "orientation": "landscape" if page.rect.width > page.rect.height else "portrait",
        "rotation": page.rotation,
        "media_box": [round(value, 2) for value in tuple(page.mediabox)],
        "content_bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
        "margins_pt": {
            "left": round(x0, 2),
            "top": round(y0, 2),
            "right": round(page.rect.width - x1, 2),
            "bottom": round(page.rect.height - y1, 2),
        },
        "span_count": len(spans),
        "rectangle_count": len(rectangles),
        "baseline_count": len(baselines),
        "row_pitch_candidates": [
            {"pitch_pt": pitch, "occurrences": count}
            for pitch, count in Counter(pitches).most_common(8)
        ],
        "font_size_histogram": [
            {"size_pt": size, "occurrences": count} for size, count in sizes.most_common()
        ],
        "measured_column_edges": column_edges(rectangles),
        "candidate_left_edges": [
            {"x_pt": edge, "occurrences": count} for edge, count in left_edges.most_common(40)
        ],
        "horizontal_rule_count": len(horizontal_bands(rectangles)),
    }


def save_raster(page: fitz.Page, path: Path) -> None:
    """Write a palette-compressed review raster.

    Fidelity metrics never read these files; ``tools/compare.py`` rasterises both PDFs at
    300 dpi at comparison time. These exist so a reviewer can see the reference in a diff.
    """
    pixmap = page.get_pixmap(dpi=REVIEW_RASTER_DPI, alpha=False, colorspace=fitz.csRGB)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    image.convert("P", palette=Image.ADAPTIVE, colors=RASTER_COLOURS).save(path, optimize=True)


def extract(level: str, report_key: str, *, rasters: bool = True) -> Path:
    report = find_report(level, report_key)
    source = reference_path(report)
    if not source.exists():
        raise FileNotFoundError(f"Fetch the reference first: {source}")
    destination = extraction_dir(report)
    destination.mkdir(parents=True, exist_ok=True)

    all_spans: list[dict[str, Any]] = []
    all_rules: list[dict[str, Any]] = []
    all_geometry: list[dict[str, Any]] = []
    fonts: dict[tuple[Any, ...], dict[str, Any]] = {}
    styles = Interner()
    paints = Interner()

    with fitz.open(source) as document:
        for page in document:
            spans = extract_spans(page, styles)
            paths, rectangles = extract_paths(page, paints)
            all_spans.append({"page": page.number + 1, "spans": spans})
            all_rules.append({"page": page.number + 1, "paths": paths})
            all_geometry.append(infer_geometry(page, spans, rectangles, styles.values))
            for font in page.get_fonts(full=True):
                key = tuple(font)
                pages = sorted(set(fonts.get(key, {}).get("pages", [])) | {page.number + 1})
                record = {
                    "xref": font[0],
                    "extension": font[1],
                    "type": font[2],
                    "base_font": font[3],
                    "resource_name": font[4],
                    "encoding": font[5],
                    "embedded": font[1] != "n/a",
                    "pages": pages,
                }
                if not record["embedded"]:
                    record["widths"] = simple_font_widths(document, font[0])
                fonts[key] = record
            if rasters:
                save_raster(page, destination / f"page-{page.number + 1:02d}.png")

        embedded_dir = destination / "embedded-fonts"
        for font in fonts.values():
            if not font["xref"] or not font["embedded"]:
                continue
            try:
                base_name, extension, _type, content = document.extract_font(font["xref"])
            except (RuntimeError, ValueError):
                continue
            if not content:
                continue
            embedded_dir.mkdir(exist_ok=True)
            safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in base_name)
            font_path = embedded_dir / f"{safe}-{font['xref']}.{extension or 'bin'}"
            font_path.write_bytes(content)
            font["extracted_file"] = font_path.relative_to(destination).as_posix()
            font["extracted_byte_size"] = len(content)

    write_compact_json(
        destination / "spans.json",
        {
            "schema_version": 3,
            "row_format": ["style_index", "x0", "y0", "x1", "y1", "origin_x", "origin_y", "text"],
            "styles": styles.values,
            "pages": all_spans,
        },
    )
    write_compact_json(
        destination / "rules.json",
        {
            "schema_version": 3,
            "row_format": ["paint_index", "item..."],
            "item_format": {
                "re": ["re", "x", "y", "w", "h"],
                "l": ["l", "x0", "y0", "x1", "y1"],
                "c": ["c", "x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"],
                "qu": ["qu", "8 corner coordinates"],
            },
            "paints": paints.values,
            "pages": all_rules,
        },
    )
    write_json(
        destination / "geometry.json",
        {
            "schema_version": 3,
            "measurement_source": "PyMuPDF",
            "metric_dpi": METRIC_DPI,
            "review_raster_dpi": REVIEW_RASTER_DPI,
            "raster_note": (
                "page-NN.png are palette-compressed review rasters. Fidelity metrics are always "
                "recomputed from the reference and rendered PDFs at 300 dpi by tools/compare.py."
            ),
            "pages": all_geometry,
        },
    )
    write_json(
        destination / "fonts.json",
        {
            "schema_version": 3,
            "fonts": sorted(fonts.values(), key=lambda item: (item["xref"], item["base_font"])),
        },
    )
    set_status(level, report_key, "extracted")
    return destination


def extract_all(*, rasters: bool = True) -> None:
    for report in load_catalog()["reports"]:
        destination = extract(report["level"], report["report_key"], rasters=rasters)
        geometry = json.loads((destination / "geometry.json").read_text(encoding="utf-8"))
        spans = sum(page["span_count"] for page in geometry["pages"])
        rectangles = sum(page["rectangle_count"] for page in geometry["pages"])
        print(
            f"{report['ordinal']:>2} {report['level']:<9} {report['report_key']:<38} "
            f"{len(geometry['pages']):>3}p {spans:>6} spans {rectangles:>7} rects"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract measured structure and 300-dpi baselines")
    parser.add_argument("level", nargs="?", choices=("secondary", "primary"))
    parser.add_argument("report_key", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--no-rasters", action="store_true")
    args = parser.parse_args()
    if args.all:
        extract_all(rasters=not args.no_rasters)
        return
    if not args.level or not args.report_key:
        parser.error("provide LEVEL and REPORT_KEY, or --all")
    print(extract(args.level, args.report_key, rasters=not args.no_rasters))


if __name__ == "__main__":
    main()
