from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf as fitz
from PIL import Image
from skimage.metrics import structural_similarity

from tools.common import (
    extraction_dir,
    find_report,
    output_dir,
    reference_path,
    set_status,
    write_json,
)

DPI = 300
THRESHOLDS = {
    "minimum_ssim": 0.98,
    "maximum_differing_pixels_percent": 0.5,
    "maximum_text_drift_pt": 1.0,
    "maximum_column_edge_drift_pt": 0.5,
}


def page_spans(page: fitz.Page) -> list[dict[str, Any]]:
    spans = []
    for block in page.get_text("dict", sort=True).get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                spans.append({"text": span["text"], "origin": span["origin"]})
    return spans


def vertical_edges(page: fitz.Page) -> list[float]:
    edges: set[float] = set()
    for drawing in page.get_drawings(extended=True):
        for item in drawing.get("items", []):
            if item[0] != "re":
                continue
            rectangle = item[1]
            if rectangle.width <= 1.5 and rectangle.height >= 5:
                edges.add(round((rectangle.x0 + rectangle.x1) / 2, 4))
    return sorted(edges)


def source_vertical_edges(rectangles: list[dict[str, Any]]) -> list[float]:
    return sorted(
        {
            round(rectangle["x"] + rectangle["width"] / 2, 4)
            for rectangle in rectangles
            if rectangle["width"] <= 1.5 and rectangle["height"] >= 5
        }
    )


def maximum_nearest_drift(reference: list[float], candidate: list[float]) -> float | None:
    if not reference or not candidate:
        return None
    return max(min(abs(value - other) for other in candidate) for value in reference)


def text_metrics(reference: fitz.Page, candidate: fitz.Page) -> dict[str, Any]:
    expected = page_spans(reference)
    actual = page_spans(candidate)
    pairs = list(zip(expected, actual, strict=False))
    text_mismatches = sum(left["text"] != right["text"] for left, right in pairs)
    text_mismatches += abs(len(expected) - len(actual))
    drifts = [
        max(
            abs(float(left["origin"][0]) - float(right["origin"][0])),
            abs(float(left["origin"][1]) - float(right["origin"][1])),
        )
        for left, right in pairs
        if left["text"] == right["text"]
    ]
    return {
        "reference_span_count": len(expected),
        "rendered_span_count": len(actual),
        "text_mismatches": text_mismatches,
        "maximum_drift_pt": round(max(drifts), 4) if drifts else None,
    }


def raster(page: fitz.Page) -> np.ndarray:
    pixmap = page.get_pixmap(dpi=DPI, alpha=False, colorspace=fitz.csRGB)
    return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)


def save_diff(reference: np.ndarray, candidate: np.ndarray, path: Path) -> None:
    mask = np.any(reference != candidate, axis=2)
    luminosity = reference.mean(axis=2).astype(np.uint8)
    difference = np.stack([luminosity, luminosity, luminosity], axis=2)
    reference_darker = reference.mean(axis=2) < candidate.mean(axis=2)
    difference[mask & reference_darker] = (0, 80, 255)
    difference[mask & ~reference_darker] = (255, 40, 0)
    Image.fromarray(difference).save(path, optimize=True)


def compare(level: str, report_key: str) -> Path:
    report = find_report(level, report_key)
    reference_pdf = reference_path(report)
    destination = output_dir(report)
    rendered_pdf = destination / "rendered.pdf"
    if not rendered_pdf.exists():
        raise FileNotFoundError(f"Render the report first: {rendered_pdf}")
    rules = json.loads((extraction_dir(report) / "rules.json").read_text(encoding="utf-8"))
    rules_by_page = {page["page"]: page["rectangles"] for page in rules["pages"]}

    page_reports = []
    with fitz.open(reference_pdf) as reference, fitz.open(rendered_pdf) as candidate:
        page_count_equal = reference.page_count == candidate.page_count
        for index in range(max(reference.page_count, candidate.page_count)):
            if index >= reference.page_count or index >= candidate.page_count:
                page_reports.append({"page": index + 1, "missing": True, "passes": False})
                continue
            source_page = reference[index]
            rendered_page = candidate[index]
            source_pixels = raster(source_page)
            rendered_pixels = raster(rendered_page)
            dimensions_equal = source_pixels.shape == rendered_pixels.shape
            page_size_equal = (
                abs(source_page.rect.width - rendered_page.rect.width) < 0.001
                and abs(source_page.rect.height - rendered_page.rect.height) < 0.001
                and source_page.rotation == rendered_page.rotation
            )
            if dimensions_equal:
                difference_mask = np.any(source_pixels != rendered_pixels, axis=2)
                pixel_delta = float(difference_mask.mean() * 100)
                ssim = float(
                    structural_similarity(
                        source_pixels,
                        rendered_pixels,
                        channel_axis=2,
                        data_range=255,
                    )
                )
                save_diff(
                    source_pixels, rendered_pixels, destination / f"diff-page-{index + 1:02d}.png"
                )
                Image.fromarray(rendered_pixels).save(
                    destination / f"rendered-page-{index + 1:02d}.png", optimize=True
                )
            else:
                pixel_delta = 100.0
                ssim = 0.0
            text = text_metrics(source_page, rendered_page)
            column_drift = maximum_nearest_drift(
                source_vertical_edges(rules_by_page[index + 1]), vertical_edges(rendered_page)
            )
            passes = all(
                (
                    dimensions_equal,
                    page_size_equal,
                    ssim >= THRESHOLDS["minimum_ssim"],
                    pixel_delta <= THRESHOLDS["maximum_differing_pixels_percent"],
                    text["text_mismatches"] == 0,
                    text["maximum_drift_pt"] is not None,
                    text["maximum_drift_pt"] <= THRESHOLDS["maximum_text_drift_pt"],
                    column_drift is not None,
                    column_drift <= THRESHOLDS["maximum_column_edge_drift_pt"],
                )
            )
            page_reports.append(
                {
                    "page": index + 1,
                    "page_size_pt": [rendered_page.rect.width, rendered_page.rect.height],
                    "page_size_equal": page_size_equal,
                    "raster_dimensions_equal": dimensions_equal,
                    "ssim": round(ssim, 6),
                    "differing_pixels_percent": round(pixel_delta, 6),
                    "text": text,
                    "maximum_column_edge_drift_pt": round(column_drift, 4)
                    if column_drift is not None
                    else None,
                    "passes": passes,
                }
            )

    passed = page_count_equal and all(page["passes"] for page in page_reports)
    payload = {
        "schema_version": 1,
        "engine": "chromium via agent-browser",
        "dpi": DPI,
        "thresholds": THRESHOLDS,
        "reference_page_count": len(rules_by_page),
        "rendered_page_count": len(page_reports),
        "page_count_equal": page_count_equal,
        "passes": passed,
        "status": "done" if passed else "wip",
        "pages": page_reports,
    }
    report_path = destination / "report.json"
    write_json(report_path, payload)
    set_status(level, report_key, payload["status"])
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Chromium output to its immutable PDF reference"
    )
    parser.add_argument("level", choices=("secondary", "primary"))
    parser.add_argument("report_key")
    args = parser.parse_args()
    print(compare(args.level, args.report_key))


if __name__ == "__main__":
    main()
