"""Compare a rendered report against its immutable reference.

Both PDFs are rasterised at 300 dpi here, so the metrics never depend on the compressed
review rasters stored under ``extract/``. The rendered PDF is the deliverable; page images
are only written for pages that fail, as diff evidence.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf as fitz
from PIL import Image
from scipy.ndimage import maximum_filter, minimum_filter
from skimage.metrics import structural_similarity

from tools.common import (
    ROOT,
    find_report,
    load_catalog,
    output_dir,
    reference_path,
    set_status,
    write_json,
)

DPI = 300
MAX_DIFF_IMAGES = 2
THRESHOLDS = {
    "minimum_ssim": 0.98,
    "maximum_differing_pixels_percent": 0.5,
    "maximum_text_drift_pt": 1.0,
    "maximum_column_edge_drift_pt": 0.5,
}


BASELINE_TOLERANCE_PT = 0.6


def page_spans(page: fitz.Page) -> list[dict[str, Any]]:
    """Spans anchored on their first visible glyph and their baseline.

    The gate is defined on the baseline and the left edge, so the anchor must be the first
    glyph that actually marks the page. Neither the text origin nor the span bounding box will
    do: both sit a space-width to the left when a span begins with a space, and the reference
    and the render do not group spaces into spans the same way - which showed up as 5 pt of
    phantom drift on text that was in exactly the right place.
    """
    spans = []
    for block in page.get_text("rawdict", sort=True).get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                visible = [char for char in span.get("chars", []) if char["c"].strip()]
                if not visible:
                    continue
                spans.append(
                    {
                        "text": "".join(char["c"] for char in span["chars"]).strip(),
                        "origin": (visible[0]["bbox"][0], span["origin"][1]),
                    }
                )
    return spans


def page_glyph_census(page: fitz.Page) -> Counter[str]:
    """Count every non-space character painted on the page.

    Two things make a literal text comparison useless here. A PDF extractor splits a visually
    continuous string wherever the producer emitted a new show-text operator, and the two
    producers split differently ("MKOA" + "KATA" against "MKOA KATA"). The extractor also
    returns spans in producer order, so two files with identical output enumerate a row's cells
    in a different sequence. A census answers the question that matters - is any text missing or
    extra - and per-span drift separately proves every piece is in the right place, so text
    could not be scrambled without the drift showing it.
    """
    census: Counter[str] = Counter()
    for span in page_spans(page):
        census.update("".join(span["text"].split()))
    return census


def vertical_edges(page: fitz.Page) -> list[float]:
    edges: set[float] = set()
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] == "re":
                rectangle = item[1]
                if rectangle.width <= 1.5 and rectangle.height >= 5:
                    edges.add(round((rectangle.x0 + rectangle.x1) / 2, 2))
            elif item[0] == "l":
                start, end = item[1], item[2]
                if abs(start.x - end.x) <= 0.3 and abs(start.y - end.y) >= 5:
                    edges.add(round((start.x + end.x) / 2, 2))
    return sorted(edges)


def maximum_nearest_drift(reference: list[float], candidate: list[float]) -> float | None:
    if not reference:
        return 0.0
    if not candidate:
        return None
    return round(max(min(abs(value - other) for other in candidate) for value in reference), 3)


def text_metrics(reference: fitz.Page, candidate: fitz.Page) -> dict[str, Any]:
    """Match spans by content, then measure how far each one moved.

    Pairing by index would report enormous drift whenever extraction order differs, which
    says nothing about fidelity. Each reference span is matched to the nearest unused
    rendered span carrying the same text.
    """
    expected = page_spans(reference)
    actual = page_spans(candidate)
    drifts, unmatched, surplus = match_spans(expected, actual)
    expected_census = page_glyph_census(reference)
    actual_census = page_glyph_census(candidate)
    missing_glyphs = expected_census - actual_census
    surplus_glyphs = actual_census - expected_census
    return {
        "reference_span_count": len(expected),
        "rendered_span_count": len(actual),
        "unmatched_reference_spans": unmatched,
        "unmatched_rendered_spans": surplus,
        "text_content_equal": not missing_glyphs and not surplus_glyphs,
        "missing_characters": sum(missing_glyphs.values()),
        "surplus_characters": sum(surplus_glyphs.values()),
        "reference_character_count": sum(expected_census.values()),
        "rendered_character_count": sum(actual_census.values()),
        "maximum_drift_pt": round(max(drifts), 3) if drifts else None,
        "median_drift_pt": round(sorted(drifts)[len(drifts) // 2], 3) if drifts else None,
    }


def match_spans(
    expected: list[dict[str, Any]], actual: list[dict[str, Any]]
) -> tuple[list[float], int, int]:
    """Pair spans of identical text in reading order.

    Repeated short strings ("F", "1", "IV") appear dozens of times on a page. Matching each
    reference span to its nearest rendered twin mis-pairs them and invents drift of hundreds
    of points. Sorting both sides in reading order and pairing positionally is correct whenever
    the layout matches, and any count difference is reported instead of hidden.
    """
    grouped_expected: dict[str, list[dict[str, Any]]] = {}
    grouped_actual: dict[str, list[dict[str, Any]]] = {}
    for span in expected:
        grouped_expected.setdefault(span["text"], []).append(span)
    for span in actual:
        grouped_actual.setdefault(span["text"], []).append(span)

    drifts: list[float] = []
    missing = 0
    surplus = 0
    for text, references in grouped_expected.items():
        candidates = grouped_actual.pop(text, [])
        drifts += assign_nearest(references, candidates)
        missing += max(0, len(references) - len(candidates))
        surplus += max(0, len(candidates) - len(references))
    surplus += sum(len(remaining) for remaining in grouped_actual.values())
    return drifts, missing, surplus


def assign_nearest(
    references: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> list[float]:
    """Pair equal-text spans by closest distance first.

    Sorting both sides in reading order looks sufficient but is not: two instances whose y
    differ by a fraction of a point can sort differently on each side, pairing spans that sit
    hundreds of points apart and reporting that as drift.
    """
    pairs = sorted(
        (
            (
                max(
                    abs(float(reference["origin"][0]) - float(candidate["origin"][0])),
                    abs(float(reference["origin"][1]) - float(candidate["origin"][1])),
                ),
                index,
                other,
            )
            for index, reference in enumerate(references)
            for other, candidate in enumerate(candidates)
        ),
        key=lambda item: item[0],
    )
    used_references: set[int] = set()
    used_candidates: set[int] = set()
    drifts: list[float] = []
    for distance, index, other in pairs:
        if index in used_references or other in used_candidates:
            continue
        used_references.add(index)
        used_candidates.add(other)
        drifts.append(distance)
    return drifts


def require_rasteriser() -> None:
    if shutil.which("pdftoppm") is None:
        raise RuntimeError(
            "pdftoppm (poppler) is not installed, so the reference and the render cannot be "
            "rasterised by the same engine. Run `make setup` first."
        )


def raster_pages(pdf: Path, work: Path, prefix: str) -> list[Path]:
    """Rasterise a whole PDF at 300 dpi with poppler.

    Both sides go through the same rasteriser and the same system font stack. That matters
    because these reports mostly do not embed Arial or Times: rasterising the reference with
    one substitution and the render with another would measure the font fallback rather than
    the template.
    """
    work.mkdir(parents=True, exist_ok=True)
    for stale in work.glob(f"{prefix}-*.png"):
        stale.unlink()
    subprocess.run(
        [
            "pdftoppm",
            "-r",
            str(DPI),
            "-png",
            "-aa",
            "yes",
            "-aaVector",
            "yes",
            str(pdf),
            str(work / prefix),
        ],
        check=True,
        capture_output=True,
        timeout=1800,
    )
    return sorted(work.glob(f"{prefix}-*.png"))


def load_raster(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


def pixel_diagnostics(reference: np.ndarray, rendered: np.ndarray) -> dict[str, Any]:
    """Describe *how* the pixels differ, without softening the gate.

    The gate counts any pixel that is not identical, which is the right bar but a blunt
    instrument: it cannot distinguish a glyph in the wrong place from a glyph whose edge is
    antialiased a shade differently. These numbers separate the two, so the remaining gap can
    be characterised honestly instead of argued about.
    """
    left = reference.astype(np.int16).mean(axis=2)
    right = rendered.astype(np.int16).mean(axis=2)
    difference = np.abs(left - right)

    neighbourhood_low = minimum_filter(left, size=3)
    neighbourhood_high = maximum_filter(left, size=3)
    within_jitter = (right >= neighbourhood_low - 8) & (right <= neighbourhood_high + 8)

    reference_ink = float((255 - left).sum())
    rendered_ink = float((255 - right).sum())
    return {
        "differing_pixels_percent_tolerance_8": round(float((difference > 8).mean() * 100), 4),
        "differing_pixels_percent_tolerance_32": round(float((difference > 32).mean() * 100), 4),
        "explained_by_one_pixel_jitter_percent": round(float(within_jitter.mean() * 100), 4),
        "beyond_one_pixel_jitter_percent": round(float((~within_jitter).mean() * 100), 4),
        "ink_ratio": round(rendered_ink / reference_ink, 5) if reference_ink else None,
        "mean_absolute_difference": round(float(difference.mean()), 4),
    }


def save_diff(reference: np.ndarray, candidate: np.ndarray, path: Path) -> None:
    mask = np.any(reference != candidate, axis=2)
    luminosity = (reference.mean(axis=2) * 0.35 + 160).clip(0, 255).astype(np.uint8)
    image = np.stack([luminosity] * 3, axis=2)
    reference_darker = reference.mean(axis=2) < candidate.mean(axis=2)
    image[mask & reference_darker] = (0, 90, 255)
    image[mask & ~reference_darker] = (255, 30, 0)
    Image.fromarray(image).convert("P", palette=Image.ADAPTIVE, colors=64).save(path, optimize=True)


ENGINE_LABELS = {
    "chromium": "chromium (headless, print-to-pdf)",
    "weasyprint": "weasyprint (in-process)",
}


def render_engine(destination: Path) -> str:
    """The engine that produced rendered.pdf, from the render-meta.json sidecar.

    Falls back to the historical chromium label when no sidecar is present (e.g. a render
    committed before the pluggable-engine work), so existing reports keep their value.
    """
    meta_path = destination / "render-meta.json"
    if meta_path.exists():
        name = json.loads(meta_path.read_text(encoding="utf-8")).get("engine")
        if name:
            return ENGINE_LABELS.get(name, name)
    return ENGINE_LABELS["chromium"]


def compare(level: str, report_key: str, *, keep_diffs: bool = True) -> dict[str, Any]:
    report = find_report(level, report_key)
    reference_pdf = reference_path(report)
    destination = output_dir(report)
    rendered_pdf = destination / "rendered.pdf"
    if not rendered_pdf.exists():
        raise FileNotFoundError(f"Render the report first: {rendered_pdf}")
    engine = render_engine(destination)
    require_rasteriser()
    destination.mkdir(parents=True, exist_ok=True)
    for stale in destination.glob("diff-page-*.png"):
        stale.unlink()

    work = ROOT / "work" / level / report_key.replace("_", "-")
    reference_rasters = raster_pages(reference_pdf, work, "reference")
    rendered_rasters = raster_pages(rendered_pdf, work, "rendered")

    page_reports: list[dict[str, Any]] = []
    with fitz.open(reference_pdf) as reference, fitz.open(rendered_pdf) as candidate:
        page_count_equal = reference.page_count == candidate.page_count
        for index in range(max(reference.page_count, candidate.page_count)):
            if index >= reference.page_count or index >= candidate.page_count:
                page_reports.append({"page": index + 1, "missing": True, "passes": False})
                continue
            source_page = reference[index]
            rendered_page = candidate[index]
            source_pixels = load_raster(reference_rasters[index])
            rendered_pixels = load_raster(rendered_rasters[index])
            dimensions_equal = source_pixels.shape == rendered_pixels.shape
            page_size_equal = (
                abs(source_page.rect.width - rendered_page.rect.width) < 0.01
                and abs(source_page.rect.height - rendered_page.rect.height) < 0.01
                and source_page.rotation == rendered_page.rotation
            )
            diagnostics: dict[str, Any] = {}
            if dimensions_equal:
                pixel_delta = float(np.any(source_pixels != rendered_pixels, axis=2).mean() * 100)
                ssim = float(
                    structural_similarity(
                        source_pixels, rendered_pixels, channel_axis=2, data_range=255
                    )
                )
                diagnostics = pixel_diagnostics(source_pixels, rendered_pixels)
            else:
                pixel_delta, ssim = 100.0, 0.0

            text = text_metrics(source_page, rendered_page)
            column_drift = maximum_nearest_drift(
                vertical_edges(source_page), vertical_edges(rendered_page)
            )
            passes = bool(
                dimensions_equal
                and page_size_equal
                and ssim >= THRESHOLDS["minimum_ssim"]
                and pixel_delta <= THRESHOLDS["maximum_differing_pixels_percent"]
                and text["text_content_equal"]
                # Several reports end with genuinely blank pages. A page with no text has no
                # drift to measure, and requiring a number here failed pages that reproduce
                # the reference exactly.
                and (
                    text["maximum_drift_pt"] is None
                    or text["maximum_drift_pt"] <= THRESHOLDS["maximum_text_drift_pt"]
                )
                and column_drift is not None
                and column_drift <= THRESHOLDS["maximum_column_edge_drift_pt"]
            )
            # Diffs are review evidence, capped so a 30-page report does not commit 30 images.
            diffs_written = sum(1 for _ in destination.glob("diff-page-*.png"))
            if dimensions_equal and keep_diffs and not passes and diffs_written < MAX_DIFF_IMAGES:
                save_diff(
                    source_pixels, rendered_pixels, destination / f"diff-page-{index + 1:02d}.png"
                )
            page_reports.append(
                {
                    "page": index + 1,
                    "page_size_pt": [
                        round(rendered_page.rect.width, 2),
                        round(rendered_page.rect.height, 2),
                    ],
                    "page_size_equal": page_size_equal,
                    "ssim": round(ssim, 6),
                    "differing_pixels_percent": round(pixel_delta, 4),
                    "text": text,
                    "maximum_column_edge_drift_pt": column_drift,
                    "passes": passes,
                    "diagnostics": diagnostics,
                }
            )

    passed = page_count_equal and all(page["passes"] for page in page_reports)
    payload = {
        "schema_version": 2,
        "report_key": report_key,
        "level": level,
        "engine": engine,
        "metric_dpi": DPI,
        "thresholds": THRESHOLDS,
        "reference_page_count": len(page_reports),
        "page_count_equal": page_count_equal,
        "passes": passed,
        "status": "done" if passed else "wip",
        "summary": summarise(page_reports),
        "pages": page_reports,
    }
    write_json(destination / "report.json", payload)
    set_status(level, report_key, payload["status"])
    return payload


def summarise(pages: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [page for page in pages if "ssim" in page]
    if not scored:
        return {}
    drifts = [
        page["text"]["maximum_drift_pt"]
        for page in scored
        if page["text"]["maximum_drift_pt"] is not None
    ]
    columns = [
        page["maximum_column_edge_drift_pt"]
        for page in scored
        if page["maximum_column_edge_drift_pt"] is not None
    ]
    jitter = [
        page["diagnostics"]["explained_by_one_pixel_jitter_percent"]
        for page in scored
        if page.get("diagnostics")
    ]
    return {
        "pages_passing": sum(1 for page in scored if page["passes"]),
        "pages_total": len(pages),
        "blank_pages": sum(1 for page in scored if page["text"]["reference_character_count"] == 0),
        "worst_explained_by_one_pixel_jitter_percent": min(jitter) if jitter else None,
        "worst_ssim": min(page["ssim"] for page in scored),
        "best_ssim": max(page["ssim"] for page in scored),
        "worst_pixel_delta_percent": max(page["differing_pixels_percent"] for page in scored),
        "text_content_equal": all(page["text"]["text_content_equal"] for page in scored),
        "worst_text_drift_pt": max(drifts) if drifts else None,
        "worst_column_drift_pt": max(columns) if columns else None,
    }


def compare_all(*, first: int = 1, last: int = 46) -> None:
    for report in load_catalog()["reports"]:
        if not first <= report["ordinal"] <= last:
            continue
        destination = output_dir(report)
        if not (destination / "rendered.pdf").exists():
            print(
                f"{report['ordinal']:>2} {report['level']:<9} {report['report_key']:<38} no render"
            )
            continue
        payload = compare(report["level"], report["report_key"])
        summary = payload["summary"]
        print(
            f"{report['ordinal']:>2} {report['level']:<9} {report['report_key']:<38} "
            f"{summary['pages_passing']}/{summary['pages_total']} pages  "
            f"ssim {summary['worst_ssim']:.4f}  delta {summary['worst_pixel_delta_percent']:.3f}%  "
            f"drift {summary['worst_text_drift_pt']}  {payload['status']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure rendered output against the reference PDF"
    )
    parser.add_argument("level", nargs="?", choices=("secondary", "primary"))
    parser.add_argument("report_key", nargs="?")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--from", dest="first", type=int, default=1)
    parser.add_argument("--to", dest="last", type=int, default=46)
    args = parser.parse_args()
    if args.all:
        compare_all(first=args.first, last=args.last)
        return
    if not args.level or not args.report_key:
        parser.error("provide LEVEL and REPORT_KEY, or --all")
    payload = compare(args.level, args.report_key)
    print(
        f"{payload['status']}: {output_dir(find_report(args.level, args.report_key)) / 'report.json'}"
    )
    print(payload["summary"])


if __name__ == "__main__":
    main()
