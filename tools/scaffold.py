from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from tools.common import extraction_dir, find_report, template_dir, write_json

SYSTEM_FONTS = {
    "liberation-sans-regular.ttf": Path(
        "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf"
    ),
    "liberation-sans-bold.ttf": Path("/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf"),
    "liberation-serif-bold.ttf": Path("/usr/share/fonts/liberation-serif/LiberationSerif-Bold.ttf"),
}
LIBERATION_LICENSE = Path("/usr/share/licenses/liberation-fonts-common/LICENSE")
FONT_FAMILIES = {
    "Tahoma-Bold": "Evidence Tahoma",
    "ArialNarrow-Bold": "Evidence Arial Narrow",
    "Arial-BoldMT": "Liberation Sans",
    "ArialMT": "Liberation Sans",
    "TimesNewRomanPS-BoldMT": "Liberation Serif",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_fonts(source_dir: Path, shared_dir: Path) -> None:
    fonts_dir = shared_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for destination_name, source in SYSTEM_FONTS.items():
        if not source.exists():
            raise FileNotFoundError(f"Install Liberation fonts before scaffolding: {source}")
        shutil.copy2(source, fonts_dir / destination_name)
    shutil.copy2(LIBERATION_LICENSE, fonts_dir / "LIBERATION-LICENSE.txt")

    embedded = source_dir / "embedded-fonts"
    for source in embedded.glob("*.ttf"):
        shutil.copy2(source, fonts_dir / source.name)
    (fonts_dir / "EVIDENCE-FONTS.md").write_text(
        "# Embedded evidence fonts\n\n"
        "The subset Tahoma Bold and Arial Narrow Bold files were extracted from the immutable "
        "reference PDF solely for local fidelity verification. Confirm redistribution rights before "
        "promoting either file into a production asset bundle. Liberation fonts are distributed under "
        "the adjacent license.\n",
        encoding="utf-8",
    )


def scaffold(level: str, report_key: str) -> Path:
    report = find_report(level, report_key)
    source_dir = extraction_dir(report)
    destination = template_dir(report)
    shared_dir = destination.parents[1] / "_shared"
    destination.mkdir(parents=True, exist_ok=True)
    copy_fonts(source_dir, shared_dir)

    spans = load_json(source_dir / "spans.json")["pages"]
    rules = load_json(source_dir / "rules.json")["pages"]
    geometry = load_json(source_dir / "geometry.json")["pages"]
    rules_by_page = {item["page"]: item["rectangles"] for item in rules}
    geometry_by_page = {item["page_number"]: item for item in geometry}

    pages = []
    for text_page in spans:
        number = text_page["page"]
        page_geometry = geometry_by_page[number]
        positioned_spans = []
        for span in text_page["spans"]:
            positioned_spans.append(
                {
                    "text": span["text"],
                    "x": span["origin"][0],
                    "y": span["origin"][1],
                    "font_family": FONT_FAMILIES.get(span["font"], "Liberation Sans"),
                    "font_size": span["size_pt"],
                    "text_length": round(span["x1"] - span["x0"], 4),
                    "font_weight": 700 if "Bold" in span["font"] else 400,
                    "fill": span["color_hex"],
                    "opacity": round(span["alpha"] / 255, 4),
                    "source_font": span["font"],
                }
            )
        pages.append(
            {
                "number": number,
                "width": page_geometry["width_pt"],
                "height": page_geometry["height_pt"],
                "rectangles": rules_by_page[number],
                "spans": positioned_spans,
            }
        )

    fixture = {
        "schema_version": 1,
        "report": {
            "level": level,
            "report_key": report_key,
            "sample_unit": report["sample_unit"],
            "render_model": "measured-positioned-display-list",
        },
        "pages": pages,
    }
    write_json(destination / "fixture.json", fixture)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold a measured report template and proof fixture"
    )
    parser.add_argument("level", choices=("secondary", "primary"))
    parser.add_argument("report_key")
    args = parser.parse_args()
    print(scaffold(args.level, args.report_key))


if __name__ == "__main__":
    main()
