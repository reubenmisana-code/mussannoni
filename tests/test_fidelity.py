import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPORTS = yaml.safe_load((ROOT / "catalog" / "reports.yaml").read_text())["reports"]
THRESHOLDS = {
    "minimum_ssim": 0.98,
    "maximum_differing_pixels_percent": 0.5,
    "maximum_text_drift_pt": 1.0,
    "maximum_column_edge_drift_pt": 0.5,
}


def report_path(report: dict) -> Path:
    return (
        ROOT / "output" / report["level"] / report["report_key"].replace("_", "-") / "report.json"
    )


MEASURED = [item for item in REPORTS if report_path(item).exists()]
IDS = [f"{item['level']}/{item['report_key']}" for item in MEASURED]


def test_every_report_has_a_rendered_pdf_and_metrics() -> None:
    for report in REPORTS:
        directory = report_path(report).parent
        assert (directory / "rendered.pdf").exists(), report["report_key"]
        assert report_path(report).exists(), report["report_key"]


@pytest.mark.parametrize("report", MEASURED, ids=IDS)
def test_thresholds_are_never_relaxed(report: dict) -> None:
    payload = json.loads(report_path(report).read_text())
    assert payload["thresholds"] == THRESHOLDS
    assert payload["metric_dpi"] == 300


@pytest.mark.parametrize("report", MEASURED, ids=IDS)
def test_status_agrees_with_the_measurements(report: dict) -> None:
    """A report may only be `done` when every page meets every gate."""
    payload = json.loads(report_path(report).read_text())
    passing = payload["passes"]
    assert payload["status"] == ("done" if passing else "wip")
    if report["status"] == "done":
        assert passing, f"{report['report_key']} is marked done but its metrics fail"
        assert all(page["passes"] for page in payload["pages"])


@pytest.mark.parametrize("report", MEASURED, ids=IDS)
def test_done_reports_meet_every_gate(report: dict) -> None:
    payload = json.loads(report_path(report).read_text())
    if not payload["passes"]:
        pytest.skip(f"{report['report_key']} is wip")
    assert payload["page_count_equal"]
    for page in payload["pages"]:
        assert page["ssim"] >= THRESHOLDS["minimum_ssim"]
        assert page["differing_pixels_percent"] <= THRESHOLDS["maximum_differing_pixels_percent"]
        assert page["text"]["maximum_drift_pt"] <= THRESHOLDS["maximum_text_drift_pt"]
        assert page["maximum_column_edge_drift_pt"] <= THRESHOLDS["maximum_column_edge_drift_pt"]
        assert page["text"]["text_content_equal"]


@pytest.mark.parametrize("report", MEASURED, ids=IDS)
def test_page_count_and_size_always_match(report: dict) -> None:
    """Pagination and page geometry are structural: they must match even while a report is wip."""
    payload = json.loads(report_path(report).read_text())
    assert payload["page_count_equal"], report["report_key"]
    for page in payload["pages"]:
        assert page["page_size_equal"], (report["report_key"], page["page"])


@pytest.mark.parametrize("report", MEASURED, ids=IDS)
def test_all_reference_text_is_reproduced(report: dict) -> None:
    payload = json.loads(report_path(report).read_text())
    for page in payload["pages"]:
        text = page["text"]
        assert text["text_content_equal"], (
            report["report_key"],
            page["page"],
            text["reference_character_count"],
            text["rendered_character_count"],
        )
