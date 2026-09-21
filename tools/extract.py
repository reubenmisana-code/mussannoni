from __future__ import annotations

import argparse
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any

import pymupdf as fitz

from tools.common import extraction_dir, find_report, reference_path, set_status, write_json

DPI = 300


def serialise(value: Any) -> Any:
    if isinstance(value, (fitz.Point, fitz.Rect, fitz.IRect, fitz.Quad, fitz.Matrix)):
        return list(value)
    if isinstance(value, bytes):
        return {"byte_length": len(value)}
    if isinstance(value, dict):
        return {str(key): serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialise(item) for item in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


def colour_hex(value: int) -> str:
    return f"#{value & 0xFFFFFF:06x}"


def pdf_colour_hex(value: tuple[float, ...] | None) -> str | None:
    if value is None or len(value) < 3:
        return None
    channels = [max(0, min(255, round(channel * 255))) for channel in value[:3]]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def pdf_colour_css(value: tuple[float, ...] | None) -> str | None:
    if value is None or len(value) < 3:
        return None
    return "color(srgb " + " ".join(f"{channel:.6f}" for channel in value[:3]) + ")"


def extract_rectangles(page: fitz.Page) -> list[dict[str, Any]]:
    rectangles: list[dict[str, Any]] = []
    for drawing in page.get_drawings(extended=True):
        if drawing.get("type") not in {"f", "s", "fs"}:
            continue
        for item in drawing.get("items", []):
            if item[0] != "re":
                raise ValueError(
                    f"Unsupported vector primitive on page {page.number + 1}: {item[0]}"
                )
            rectangle = item[1]
            rectangles.append(
                {
                    "x": round(rectangle.x0, 4),
                    "y": round(rectangle.y0, 4),
                    "width": round(rectangle.width, 4),
                    "height": round(rectangle.height, 4),
                    "fill": pdf_colour_hex(drawing.get("fill")),
                    "fill_css": pdf_colour_css(drawing.get("fill")),
                    "fill_opacity": round(drawing.get("fill_opacity") or 0.0, 4),
                    "stroke": pdf_colour_hex(drawing.get("color")),
                    "stroke_css": pdf_colour_css(drawing.get("color")),
                    "stroke_opacity": round(drawing.get("stroke_opacity") or 0.0, 4),
                    "stroke_width": round(drawing.get("width") or 0.0, 4),
                    "sequence": drawing.get("seqno"),
                }
            )
    return rectangles


def extract_spans(page: fitz.Page) -> list[dict[str, Any]]:
    text = page.get_text("dict", sort=True)
    spans: list[dict[str, Any]] = []
    for block_index, block in enumerate(text.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for line_index, line in enumerate(block.get("lines", [])):
            for span_index, span in enumerate(line.get("spans", [])):
                bbox = span["bbox"]
                spans.append(
                    {
                        "block": block_index,
                        "line": line_index,
                        "span": span_index,
                        "text": span["text"],
                        "x0": round(bbox[0], 4),
                        "y0": round(bbox[1], 4),
                        "x1": round(bbox[2], 4),
                        "y1": round(bbox[3], 4),
                        "origin": serialise(span.get("origin")),
                        "font": span["font"],
                        "size_pt": round(span["size"], 4),
                        "flags": span["flags"],
                        "char_flags": span.get("char_flags"),
                        "color": span["color"],
                        "color_hex": colour_hex(span["color"]),
                        "alpha": span.get("alpha", 255),
                        "ascender": round(span.get("ascender", 0.0), 4),
                        "descender": round(span.get("descender", 0.0), 4),
                    }
                )
    return spans


def infer_geometry(page: fitz.Page, spans: list[dict[str, Any]]) -> dict[str, Any]:
    x0 = min((span["x0"] for span in spans), default=0.0)
    y0 = min((span["y0"] for span in spans), default=0.0)
    x1 = max((span["x1"] for span in spans), default=page.rect.width)
    y1 = max((span["y1"] for span in spans), default=page.rect.height)
    baselines = sorted(
        {
            round(float(span["origin"][1]), 2)
            for span in spans
            if span.get("origin") and len(span["origin"]) > 1
        }
    )
    pitches = [round(b - a, 2) for a, b in pairwise(baselines) if 2 <= b - a <= 30]
    common_pitches = [
        {"pitch_pt": pitch, "occurrences": count}
        for pitch, count in Counter(pitches).most_common(12)
    ]
    x_edges = Counter(round(span["x0"] * 2) / 2 for span in spans)
    return {
        "page_number": page.number + 1,
        "width_pt": round(page.rect.width, 4),
        "height_pt": round(page.rect.height, 4),
        "orientation": "landscape" if page.rect.width > page.rect.height else "portrait",
        "rotation": page.rotation,
        "media_box": serialise(page.mediabox),
        "crop_box": serialise(page.cropbox),
        "content_bbox": [x0, y0, x1, y1],
        "margins_pt": {
            "left": round(x0, 4),
            "top": round(y0, 4),
            "right": round(page.rect.width - x1, 4),
            "bottom": round(page.rect.height - y1, 4),
        },
        "baseline_count": len(baselines),
        "common_row_pitches": common_pitches,
        "candidate_left_edges": [
            {"x_pt": edge, "occurrences": count} for edge, count in x_edges.most_common(30)
        ],
    }


def extract(level: str, report_key: str) -> Path:
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

    with fitz.open(source) as document:
        for page in document:
            spans = extract_spans(page)
            all_spans.append({"page": page.number + 1, "spans": spans})
            rectangles = extract_rectangles(page)
            all_rules.append({"page": page.number + 1, "rectangles": rectangles})
            all_geometry.append(infer_geometry(page, spans))
            for font in page.get_fonts(full=True):
                key = tuple(font)
                fonts[key] = {
                    "xref": font[0],
                    "extension": font[1],
                    "type": font[2],
                    "base_font": font[3],
                    "resource_name": font[4],
                    "encoding": font[5],
                    "referencer": font[6] if len(font) > 6 else None,
                    "pages": sorted(set(fonts.get(key, {}).get("pages", [])) | {page.number + 1}),
                }
            pixmap = page.get_pixmap(dpi=DPI, alpha=False, colorspace=fitz.csRGB)
            pixmap.save(destination / f"page-{page.number + 1:02d}.png")

        embedded_dir = destination / "embedded-fonts"
        for font in fonts.values():
            if not font["xref"]:
                continue
            try:
                base_name, extension, _font_type, content = document.extract_font(font["xref"])
            except (RuntimeError, ValueError):
                continue
            if not content:
                continue
            embedded_dir.mkdir(exist_ok=True)
            safe_name = "".join(
                char if char.isalnum() or char in "-_" else "-" for char in base_name
            )
            font_path = embedded_dir / f"{safe_name}-{font['xref']}.{extension or 'bin'}"
            font_path.write_bytes(content)
            font["extracted_file"] = font_path.relative_to(destination).as_posix()
            font["extracted_byte_size"] = len(content)

    write_json(destination / "spans.json", {"schema_version": 1, "pages": all_spans})
    write_json(destination / "rules.json", {"schema_version": 1, "pages": all_rules})
    write_json(
        destination / "geometry.json",
        {"schema_version": 1, "measurement_source": "PyMuPDF", "dpi": DPI, "pages": all_geometry},
    )
    write_json(
        destination / "fonts.json",
        {
            "schema_version": 1,
            "fonts": sorted(fonts.values(), key=lambda item: (item["xref"], item["base_font"])),
        },
    )
    set_status(level, report_key, "extracted")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract measured PDF structure and 300-dpi baselines"
    )
    parser.add_argument("level", choices=("secondary", "primary"))
    parser.add_argument("report_key")
    args = parser.parse_args()
    print(extract(args.level, args.report_key))


if __name__ == "__main__":
    main()
