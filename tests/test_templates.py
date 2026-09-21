import json
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
REPORTS = yaml.safe_load((ROOT / "catalog" / "reports.yaml").read_text())["reports"]
BUILT = [
    item
    for item in REPORTS
    if (
        ROOT / "templates" / item["level"] / item["report_key"].replace("_", "-") / "template.html"
    ).exists()
]
IDS = [f"{item['level']}/{item['report_key']}" for item in BUILT]


def template_dir(report: dict) -> Path:
    return ROOT / "templates" / report["level"] / report["report_key"].replace("_", "-")


def test_every_catalog_entry_has_a_template() -> None:
    assert len(BUILT) == len(REPORTS)


@pytest.mark.parametrize("report", BUILT, ids=IDS)
def test_template_parses_and_is_data_driven(report: dict) -> None:
    source = (template_dir(report) / "template.html").read_text()
    Environment(undefined=StrictUndefined).parse(source)
    assert "{% for page in pages %}" in source
    assert "<table" in source and "<colgroup>" in source and "<td" in source


@pytest.mark.parametrize("report", BUILT, ids=IDS)
def test_no_sample_value_is_baked_into_the_template(report: dict) -> None:
    """Sample data belongs in fixture.json. A literal here would print the reference's own
    figures as if they were live results."""
    source = (template_dir(report) / "template.html").read_text()
    fixture = json.loads((template_dir(report) / "fixture.json").read_text())
    sample_texts = {
        run["text"].strip()
        for page in fixture["pages"]
        for row in page["rows"]
        for cell in row["cells"]
        for line in cell["lines"]
        for run in line["runs"]
        if len(run["text"].strip()) >= 4
    }
    leaked = sorted(text for text in sample_texts if text in source)
    assert not leaked, f"sample values leaked into the template: {leaked[:5]}"
    unit = report["sample_unit"].split("-", 1)[0].strip()
    assert unit not in source


@pytest.mark.parametrize("report", BUILT, ids=IDS)
def test_fixture_geometry_is_complete(report: dict) -> None:
    fixture = json.loads((template_dir(report) / "fixture.json").read_text())
    assert fixture["pages"]
    for page in fixture["pages"]:
        assert page["width_pt"] > 0 and page["height_pt"] > 0
        # A page carries a measured grid, or loose text, or nothing at all: several reports
        # end with genuinely blank pages, and reproducing a blank page means emitting nothing.
        if not page["columns"] and not page["loose_lines"]:
            assert not page["rows"] and not page["rules"], page["number"]
        assert page["table_width_pt"] == pytest.approx(sum(page["columns"]), abs=0.05)
        for row in page["rows"]:
            assert row["height_pt"] > 0
            for cell in row["cells"]:
                assert cell["colspan"] >= 1 and cell["rowspan"] >= 1
                for line in cell["lines"]:
                    assert "left_pt" in line and "top_pt" in line


@pytest.mark.parametrize("report", BUILT, ids=IDS)
def test_bindings_declare_measured_columns(report: dict) -> None:
    bindings = yaml.safe_load((template_dir(report) / "bindings.yaml").read_text())
    assert bindings["report_key"] == report["report_key"]
    assert bindings["columns"], report["report_key"]
    for column in bindings["columns"]:
        assert column["width_pt"] > 0
    # `field` is deliberately unset until the backend registry is available; it must never be
    # invented, but the column geometry and the reference labels must be present.
    assert all("field" in column for column in bindings["columns"])


@pytest.mark.parametrize("report", BUILT, ids=IDS)
def test_report_css_declares_measured_page_box(report: dict) -> None:
    css = (template_dir(report) / "report.css").read_text()
    assert "@page" in css and "margin: 0" in css
    fixture = json.loads((template_dir(report) / "fixture.json").read_text())
    first = fixture["pages"][0]
    assert f"size: {first['width_pt']}pt {first['height_pt']}pt" in css



@pytest.mark.parametrize("report", BUILT, ids=IDS)
def test_rotated_headings_are_carried_through(report: dict) -> None:
    """38 of the 46 reports set their column headings sideways.

    A rotated span reports an origin that is not its left edge, so if the rotation is lost the
    heading is rebuilt lying flat and lands several points out of place.
    """
    extraction = ROOT / "extract" / report["level"] / report["report_key"].replace("_", "-")
    spans = json.loads((extraction / "spans.json").read_text())
    rotated_in_evidence = sum(
        1 for page in spans["pages"] for row in page["spans"] if len(row) > 8 and row[8]
    )
    fixture = json.loads((template_dir(report) / "fixture.json").read_text())
    rotated_in_fixture = sum(
        1
        for page in fixture["pages"]
        for row in page["rows"]
        for cell in row["cells"]
        for line in cell["lines"]
        if line["rotation"]
    ) + sum(1 for page in fixture["pages"] for line in page["loose_lines"] if line["rotation"])

    assert rotated_in_fixture == rotated_in_evidence, report["report_key"]
    if rotated_in_evidence:
        css = (ROOT / "templates" / "_shared" / "reset.css").read_text()
        assert ".rot90" in css and "rotate(-90deg)" in css
        source = (template_dir(report) / "template.html").read_text()
        assert "rot{{ line.rotation }}" in source


@pytest.mark.parametrize("report", BUILT, ids=IDS)
def test_calibration_is_a_recorded_measurement(report: dict) -> None:
    """Placement corrections must come from a measured render, not a hand-tuned constant."""
    path = template_dir(report) / "calibration.json"
    assert path.exists(), report["report_key"]
    calibration = json.loads(path.read_text())
    assert calibration["iterations"] >= 1
    assert calibration["by_face"], report["report_key"]
    for key, entry in calibration["by_face"].items():
        assert len(key.split("|")) == 3, key
        assert entry["samples"] >= 1
        # A correction is a sub-point nudge. Anything larger means a structural problem is
        # being papered over instead of fixed.
        assert abs(entry["dx"]) < 3.0 and abs(entry["dy"]) < 3.0, (report["report_key"], key, entry)
