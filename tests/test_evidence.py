import hashlib
import json
from pathlib import Path

import pymupdf
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPORTS = yaml.safe_load((ROOT / "catalog" / "reports.yaml").read_text())["reports"]
MANIFEST = json.loads((ROOT / "corpus" / "MANIFEST.json").read_text())
FETCHED = [item for item in REPORTS if item["status"] != "todo"]


def identity(report: dict) -> str:
    return report["report_key"].replace("_", "-")


def extraction_dir(report: dict) -> Path:
    return ROOT / "extract" / report["level"] / identity(report)


@pytest.mark.parametrize(
    "report", FETCHED, ids=lambda item: f"{item['level']}/{item['report_key']}"
)
def test_reference_is_unmodified(report: dict) -> None:
    """The corpus is the reference. If a checksum moves, an input was edited."""
    relative = f"corpus/{report['level']}/{identity(report)}.pdf"
    path = ROOT / relative
    expected = MANIFEST["files"][relative]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]
    with pymupdf.open(path) as document:
        assert document.page_count == expected["page_count"]


@pytest.mark.parametrize(
    "report", FETCHED, ids=lambda item: f"{item['level']}/{item['report_key']}"
)
def test_extraction_is_machine_measured_and_complete(report: dict) -> None:
    directory = extraction_dir(report)
    geometry = json.loads((directory / "geometry.json").read_text())
    spans = json.loads((directory / "spans.json").read_text())
    rules = json.loads((directory / "rules.json").read_text())

    assert geometry["measurement_source"] == "PyMuPDF"
    assert geometry["metric_dpi"] == 300
    relative = f"corpus/{report['level']}/{identity(report)}.pdf"
    pages = MANIFEST["files"][relative]["page_count"]
    assert len(geometry["pages"]) == pages
    assert len(spans["pages"]) == pages
    assert len(rules["pages"]) == pages

    # Interned styles keep the files small; every span must reference a real style.
    assert spans["styles"]
    for page in spans["pages"]:
        for row in page["spans"]:
            assert 0 <= row[0] < len(spans["styles"])
    for page in rules["pages"]:
        for row in page["paths"]:
            assert 0 <= row[0] < len(rules["paints"])


@pytest.mark.parametrize(
    "report", FETCHED, ids=lambda item: f"{item['level']}/{item['report_key']}"
)
def test_geometry_matches_the_reference_pages(report: dict) -> None:
    geometry = json.loads((extraction_dir(report) / "geometry.json").read_text())
    relative = f"corpus/{report['level']}/{identity(report)}.pdf"
    for measured, expected in zip(
        geometry["pages"], MANIFEST["files"][relative]["pages"], strict=True
    ):
        assert measured["width_pt"] == pytest.approx(expected["width_pt"], abs=0.01)
        assert measured["height_pt"] == pytest.approx(expected["height_pt"], abs=0.01)


def test_review_rasters_exist_for_the_first_page() -> None:
    for report in FETCHED:
        assert (extraction_dir(report) / "page-01.png").exists(), report["report_key"]
