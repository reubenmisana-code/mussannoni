"""Measure the residual offset of a render and record it as a correction.

Placing text from font metrics assumes the engine computes its baseline the same way. Instead
of trusting that, this compares a real render against the reference, takes the median residual
per font size, and writes it next to the template. The scaffold then applies it, so the second
render lands on the reference. This is the measured form of "iterate until the gates pass" -
nothing here is hand-tuned.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

import pymupdf

from tools.common import find_report, output_dir, reference_path, template_dir, write_json
from tools.extract import rotation_of

MAX_RESIDUAL_PT = 6.0


def spans_of(page: pymupdf.Page) -> list[dict[str, Any]]:
    out = []
    for block in page.get_text("rawdict", sort=True).get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            rotation = rotation_of(line)
            for span in line.get("spans", []):
                visible = [char for char in span.get("chars", []) if char["c"].strip()]
                if not visible:
                    continue
                out.append(
                    {
                        "text": "".join(char["c"] for char in span["chars"]).strip(),
                        # First visible glyph, not the text origin: see compare.page_spans.
                        "x": float(visible[0]["bbox"][0]),
                        "y": float(span["origin"][1]),
                        "size": round(span["size"], 2),
                        "font": span["font"],
                        "rotation": rotation,
                    }
                )
    return out


def residuals(level: str, report_key: str) -> dict[str, Any]:
    report = find_report(level, report_key)
    rendered_pdf = output_dir(report) / "rendered.pdf"
    if not rendered_pdf.exists():
        raise FileNotFoundError(f"Render before tuning: {rendered_pdf}")

    by_size: dict[float, list[tuple[float, float]]] = {}
    by_face: dict[str, list[tuple[float, float]]] = {}
    with pymupdf.open(reference_path(report)) as reference, pymupdf.open(rendered_pdf) as rendered:
        for index in range(min(reference.page_count, rendered.page_count)):
            grouped_expected: dict[str, list[dict[str, Any]]] = {}
            grouped_actual: dict[str, list[dict[str, Any]]] = {}
            for span in spans_of(reference[index]):
                grouped_expected.setdefault(span["text"], []).append(span)
            for span in spans_of(rendered[index]):
                grouped_actual.setdefault(span["text"], []).append(span)

            for text, references in grouped_expected.items():
                candidates = grouped_actual.get(text, [])
                # Reading order, so repeated short strings pair with their own twin.
                references = sorted(
                    references, key=lambda span: (round(span["y"], 1), round(span["x"], 1))
                )
                candidates = sorted(
                    candidates, key=lambda span: (round(span["y"], 1), round(span["x"], 1))
                )
                for reference_span, candidate_span in zip(references, candidates, strict=False):
                    dx = candidate_span["x"] - reference_span["x"]
                    dy = candidate_span["y"] - reference_span["y"]
                    if max(abs(dx), abs(dy)) > MAX_RESIDUAL_PT:
                        continue
                    if not reference_span["rotation"]:
                        by_size.setdefault(reference_span["size"], []).append((dx, dy))
                    by_face.setdefault(
                        face_key(
                            reference_span["font"],
                            reference_span["size"],
                            reference_span["rotation"],
                        ),
                        [],
                    ).append((dx, dy))

    # Corrections accumulate: the residual measured now is on top of whatever correction the
    # current render already applied, so it is added rather than replacing it.
    previous = load_calibration(template_dir(report))
    previous_sizes = previous.get("by_size", {})
    per_size = {}
    for size, pairs in sorted(by_size.items()):
        if len(pairs) < 5:
            continue
        old = previous_sizes.get(f"{size}", {})
        per_size[f"{size}"] = {
            "dx": round(float(old.get("dx", 0.0)) + statistics.median(dx for dx, _ in pairs), 4),
            "dy": round(float(old.get("dy", 0.0)) + statistics.median(dy for _, dy in pairs), 4),
            "samples": len(pairs),
        }

    # Every face that appears at least once gets its own correction; a single sample is still a
    # real measurement of that face and is better than borrowing another face's offset.
    previous_faces = previous.get("by_face", {})
    per_face = {}
    for key, pairs in sorted(by_face.items()):
        old = previous_faces.get(key, {})
        per_face[key] = {
            "dx": round(float(old.get("dx", 0.0)) + statistics.median(dx for dx, _ in pairs), 4),
            "dy": round(float(old.get("dy", 0.0)) + statistics.median(dy for _, dy in pairs), 4),
            "samples": len(pairs),
        }

    everything = [pair for pairs in by_size.values() for pair in pairs]
    old_global = previous.get("global", {})
    payload = {
        "schema_version": 1,
        "report_key": report_key,
        "level": level,
        "note": "cumulative correction in points; the scaffold subtracts it from placed text",
        "iterations": int(previous.get("iterations", 0)) + 1,
        "global": {
            "dx": round(
                float(old_global.get("dx", 0.0))
                + (statistics.median(dx for dx, _ in everything) if everything else 0.0),
                3,
            ),
            "dy": round(
                float(old_global.get("dy", 0.0))
                + (statistics.median(dy for _, dy in everything) if everything else 0.0),
                3,
            ),
            "samples": len(everything),
        },
        "residual": {
            "dx": round(statistics.median(dx for dx, _ in everything), 4) if everything else 0.0,
            "dy": round(statistics.median(dy for _, dy in everything), 4) if everything else 0.0,
            "worst_dx": round(max((abs(dx) for dx, _ in everything), default=0.0), 4),
            "worst_dy": round(max((abs(dy) for _, dy in everything), default=0.0), 4),
        },
        "by_face": per_face,
        "by_size": per_size,
    }
    write_json(template_dir(report) / "calibration.json", payload)
    return payload


def load_calibration(directory: Path) -> dict[str, Any]:
    path = directory / "calibration.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def face_key(font: str, size_pt: float, rotation: int = 0) -> str:
    return f"{font}|{size_pt}|{rotation}"


def correction_for(
    calibration: dict[str, Any], font: str, size_pt: float, rotation: int = 0
) -> tuple[float, float]:
    """Corrections are keyed by face, size *and* rotation.

    Keying by size alone applies one face's baseline offset to another: Times New Roman Bold at
    8.16 pt inherited Arial's correction and stayed 0.46 pt low. Rotation matters for the same
    reason - a rotated run's residual lies along the other page axis, so mixing it with
    horizontal text of the same face would corrupt both corrections.
    """
    if not calibration:
        return 0.0, 0.0
    entry = calibration.get("by_face", {}).get(face_key(font, size_pt, rotation))
    if entry is None and not rotation:
        entry = calibration.get("by_size", {}).get(f"{size_pt}") or calibration.get("global")
    if not entry:
        return 0.0, 0.0
    return float(entry.get("dx", 0.0)), float(entry.get("dy", 0.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Record the residual offset of a render")
    parser.add_argument("level", choices=("secondary", "primary"))
    parser.add_argument("report_key")
    args = parser.parse_args()
    payload = residuals(args.level, args.report_key)
    print(f"iteration {payload['iterations']}  residual {json.dumps(payload['residual'])}")
    for key, entry in payload["by_face"].items():
        print(f"  {key:<34} dx {entry['dx']:+.4f}  dy {entry['dy']:+.4f}  n={entry['samples']}")


if __name__ == "__main__":
    main()
