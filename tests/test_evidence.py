import hashlib
import json
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]


def test_reference_matches_immutable_manifest() -> None:
    manifest = json.loads((ROOT / "corpus" / "MANIFEST.json").read_text())
    relative = "corpus/secondary/school-results.pdf"
    reference = ROOT / relative
    expected = manifest["files"][relative]
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == expected["sha256"]
    with pymupdf.open(reference) as document:
        assert document.page_count == expected["page_count"] == 15
        assert all(page.rect.width == 792 and page.rect.height == 612 for page in document)


def test_extraction_is_complete() -> None:
    extraction = ROOT / "extract" / "secondary" / "school-results"
    spans = json.loads((extraction / "spans.json").read_text())
    rules = json.loads((extraction / "rules.json").read_text())
    geometry = json.loads((extraction / "geometry.json").read_text())
    assert len(spans["pages"]) == len(rules["pages"]) == len(geometry["pages"]) == 15
    assert sum(len(page["spans"]) for page in spans["pages"]) == 4_083
    assert sum(len(page["rectangles"]) for page in rules["pages"]) == 51_924
    for number in range(1, 16):
        image = extraction / f"page-{number:02d}.png"
        assert image.exists()
