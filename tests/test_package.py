"""Tests for the installable package: the public API, the registry and the packaged resources.

These exercise ``src/mussannoni`` the way an application would — through the public surface, never
through the repository layout — so they would still pass against an installed wheel. The workshop's
own renderer is covered by ``test_engine.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

import mussannoni
from mussannoni import cli, document, engines, registry, resources, table
from mussannoni.errors import (
    InvalidDataError,
    InvalidDocumentError,
    UnknownEngineError,
    UnknownReportError,
)

# A report that exists at one level only, so tests need not disambiguate.
SAMPLE = "council_best_students"
SAMPLE_LEVEL = "primary"
# A key that deliberately exists at both levels.
AMBIGUOUS = "school_results"


@pytest.fixture(scope="module")
def sample_layout() -> dict:
    return mussannoni.report_layout(SAMPLE, level=SAMPLE_LEVEL)


def _rows(layout: dict, count: int) -> list[list[str]]:
    width = len(layout["table"]["columns"])
    return [[f"R{index}C{column}" for column in range(width)] for index in range(count)]


# --------------------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------------------


def test_registry_holds_every_report() -> None:
    reports = mussannoni.list_reports()
    assert len(reports) == 46
    assert len(mussannoni.list_reports("primary")) == 28
    assert len(mussannoni.list_reports("secondary")) == 18


def test_reports_are_listed_in_processing_order() -> None:
    ordinals = [report.ordinal for report in mussannoni.list_reports()]
    assert ordinals == sorted(ordinals)


def test_find_accepts_snake_and_kebab_case() -> None:
    assert mussannoni.find(SAMPLE, SAMPLE_LEVEL).report_key == SAMPLE
    assert mussannoni.find(SAMPLE.replace("_", "-"), SAMPLE_LEVEL).report_key == SAMPLE


def test_find_rejects_an_unknown_report() -> None:
    with pytest.raises(UnknownReportError, match="Unknown report"):
        mussannoni.find("no_such_report")


def test_find_requires_a_level_when_the_key_is_ambiguous() -> None:
    # school_results exists at both levels; resolving it silently would render the wrong report.
    with pytest.raises(UnknownReportError, match="exists at levels"):
        mussannoni.find(AMBIGUOUS)
    assert mussannoni.find(AMBIGUOUS, "primary").level == "primary"
    assert mussannoni.find(AMBIGUOUS, "secondary").level == "secondary"


def test_find_rejects_an_unknown_level() -> None:
    with pytest.raises(UnknownReportError, match="Unknown level"):
        mussannoni.find(SAMPLE, "tertiary")


def test_report_identity_is_the_resource_directory_name() -> None:
    report = mussannoni.find(SAMPLE, SAMPLE_LEVEL)
    assert report.identity == "council-best-students"
    assert resources.report_dir(report.level, report.report_key).is_dir()


# --------------------------------------------------------------------------------------
# packaged resources
# --------------------------------------------------------------------------------------


def test_every_report_ships_the_resources_it_needs() -> None:
    for report in mussannoni.list_reports():
        directory = resources.report_dir(report.level, report.report_key)
        assert (directory / "report.css").is_file(), report.report_key
        assert (directory / "layout.json").is_file(), report.report_key


def test_shared_resources_are_present() -> None:
    assert resources.template_path().is_file()
    assert (resources.shared_dir() / "reset.css").is_file()
    # The base-14 fallbacks the stylesheets name must actually be there, or text silently
    # reflows to whatever the host happens to have.
    for name in ("report-sans-regular.otf", "report-sans-bold.otf", "report-serif-regular.otf"):
        assert (resources.shared_dir() / "fonts" / name).is_file(), name


def test_fixtures_are_not_shipped() -> None:
    # The 46 fixtures are 257 MB of sample geometry. Shipping them would be the single biggest
    # packaging mistake available, so assert they stayed behind.
    assert not list(resources.resource_root().rglob("fixture.json"))


def test_asset_uris_point_at_real_files() -> None:
    shared_css, report_css, base_url = resources.asset_uris(SAMPLE_LEVEL, SAMPLE)
    for uri in (shared_css, report_css):
        assert uri.startswith("file://")
        assert Path(uri.removeprefix("file://")).is_file()
    assert base_url.endswith("/")


def test_packaged_resources_are_current() -> None:
    # Guards the one failure mode of a generated directory: someone edits templates/ and the
    # package keeps shipping the old copy.
    pytest.importorskip("yaml")
    from tools import package_resources

    differences = package_resources.build(check=True)
    assert not differences, (
        f"{len(differences)} packaged resources are out of date; "
        f"run `make package-resources`. First few: {differences[:5]}"
    )


# --------------------------------------------------------------------------------------
# layouts
# --------------------------------------------------------------------------------------


def test_every_layout_is_complete_enough_to_render() -> None:
    for report in mussannoni.list_reports():
        layout = mussannoni.report_layout(report.report_key, level=report.level)
        where = f"{report.level}/{report.report_key}"
        assert layout["page"]["width_pt"] > 0, where
        assert layout["page"]["height_pt"] > 0, where
        assert layout["table"]["columns"], where
        assert layout["header"]["row_count"] >= 0, where
        assert layout["text_styles"], where
        assert layout["body"], where
        assert layout["body"]["row_height_pt"] > 0, where
        assert layout["rows_per_page"] >= 1, where


def test_layout_text_styles_can_all_be_measured() -> None:
    # Every .tN class must resolve to a face, or generated text cannot be positioned.
    for report in mussannoni.list_reports():
        layout = mussannoni.report_layout(report.report_key, level=report.level)
        for name, style in layout["text_styles"].items():
            width = table._text_width("MWANZA", style, report.level, report.report_key)
            assert width > 0, f"{report.report_key}.{name} measured as zero-width"


# --------------------------------------------------------------------------------------
# engines
# --------------------------------------------------------------------------------------


def test_packaged_default_engine_is_weasyprint() -> None:
    # The chromium engine needs a Node binary that pip cannot install, so it cannot be the
    # default for an installed package.
    assert engines.DEFAULT_ENGINE == "weasyprint"
    assert set(engines.engine_names()) == {"weasyprint", "chromium"}


def test_engine_selection_prefers_argument_then_environment_then_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(engines.ENGINE_ENV_VAR, raising=False)
    assert engines.resolve_engine(None) == engines.DEFAULT_ENGINE

    monkeypatch.setenv(engines.ENGINE_ENV_VAR, "chromium")
    assert engines.resolve_engine(None) == "chromium"
    assert engines.resolve_engine("weasyprint") == "weasyprint"


def test_unknown_engine_is_rejected() -> None:
    with pytest.raises(UnknownEngineError, match="Unknown rendering engine"):
        engines.resolve_engine("ghostscript")


def test_chromium_command_line_is_built_without_running_a_browser(tmp_path: Path) -> None:
    engine = engines.ENGINES["chromium"]
    commands = engine.build_commands("s1", tmp_path / "in.html", tmp_path / "out.pdf")
    assert [command[3] for command in commands] == ["open", "wait", "pdf", "close"]
    assert all(command[:3] == ["agent-browser", "--session", "s1"] for command in commands)


def test_weasyprint_is_available_here() -> None:
    assert engines.available_engines()["weasyprint"] is True


# --------------------------------------------------------------------------------------
# geometry documents
# --------------------------------------------------------------------------------------


def test_validate_document_names_the_offending_path() -> None:
    with pytest.raises(InvalidDocumentError, match=r"document\['report'\]"):
        document.validate_document({"pages": []})
    with pytest.raises(InvalidDocumentError, match=r"document\['pages'\]"):
        document.validate_document({"report": {"title": "x"}, "pages": []})


def test_validate_document_reports_missing_page_keys() -> None:
    with pytest.raises(InvalidDocumentError, match=r"pages'\]\[0\] is missing"):
        document.validate_document({"report": {"title": "x"}, "pages": [{"number": 1}]})


def test_validate_document_rejects_a_cell_outside_the_column_grid(sample_layout: dict) -> None:
    built = mussannoni.build_document(sample_layout, {"rows": _rows(sample_layout, 1)})
    built["pages"][0]["rows"][-1]["cells"][0]["column"] = 999
    with pytest.raises(InvalidDocumentError, match="outside the"):
        document.validate_document(built)


def test_a_generated_document_passes_validation(sample_layout: dict) -> None:
    built = mussannoni.build_document(sample_layout, {"rows": _rows(sample_layout, 4)})
    document.validate_document(built)  # must not raise


# --------------------------------------------------------------------------------------
# the table layer
# --------------------------------------------------------------------------------------


def test_rows_are_placed_on_the_measured_grid(sample_layout: dict) -> None:
    built = mussannoni.build_document(sample_layout, {"rows": _rows(sample_layout, 3)})
    page = built["pages"][0]
    assert page["width_pt"] == sample_layout["page"]["width_pt"]
    assert page["columns"] == sample_layout["table"]["columns"]
    assert page["header_rows"] == sample_layout["header"]["row_count"]
    assert len(page["rows"]) == sample_layout["header"]["row_count"] + 3


def test_rows_are_paginated_and_the_header_repeats(sample_layout: dict) -> None:
    per_page = sample_layout["rows_per_page"]
    built = mussannoni.build_document(sample_layout, {"rows": _rows(sample_layout, per_page + 2)})
    assert len(built["pages"]) == 2
    assert [page["number"] for page in built["pages"]] == [1, 2]
    header_count = sample_layout["header"]["row_count"]
    for page in built["pages"]:
        assert page["header_rows"] == header_count
    assert len(built["pages"][0]["rows"]) == header_count + per_page
    assert len(built["pages"][1]["rows"]) == header_count + 2


def test_rows_may_be_mappings_keyed_by_column_label(sample_layout: dict) -> None:
    labels = sample_layout["header"]["labels"]
    label = next(item for item in labels if item)
    built = mussannoni.build_document(sample_layout, {"rows": [{label: "MWANZA"}]})
    body = built["pages"][0]["rows"][-1]
    texts = [
        run["text"]
        for cell in body["cells"]
        for line in cell["lines"]
        for run in line["runs"]
    ]
    assert texts == ["MWANZA"]


def test_rows_may_be_mappings_keyed_by_column_index(sample_layout: dict) -> None:
    built = mussannoni.build_document(sample_layout, {"rows": [{1: "MAGU"}]})
    body = built["pages"][0]["rows"][-1]
    placed = [
        (cell["column"], run["text"])
        for cell in body["cells"]
        for line in cell["lines"]
        for run in line["runs"]
    ]
    assert placed == [(1, "MAGU")]


def test_none_renders_as_an_empty_cell_not_the_string_none(sample_layout: dict) -> None:
    built = mussannoni.build_document(sample_layout, {"rows": [[None, "X"]]})
    body = built["pages"][0]["rows"][-1]
    assert body["cells"][0]["lines"] == []
    texts = [run["text"] for line in body["cells"][1]["lines"] for run in line["runs"]]
    assert texts == ["X"]


def test_whole_floats_lose_their_trailing_zero(sample_layout: dict) -> None:
    built = mussannoni.build_document(sample_layout, {"rows": [[3.0, 2.5]]})
    body = built["pages"][0]["rows"][-1]
    rendered = [
        run["text"] for cell in body["cells"] for line in cell["lines"] for run in line["runs"]
    ]
    assert rendered == ["3", "2.5"]


def test_generated_cells_carry_no_measured_glyph_corrections(sample_layout: dict) -> None:
    # chunks/letter_spacing describe one specific measured string. Reusing them for different
    # text would smear the new glyphs across the old advances.
    built = mussannoni.build_document(sample_layout, {"rows": _rows(sample_layout, 2)})
    header_count = sample_layout["header"]["row_count"]
    for row in built["pages"][0]["rows"][header_count:]:
        for cell in row["cells"]:
            for line in cell["lines"]:
                assert line["letter_spacing_pt"] == 0.0
                for run in line["runs"]:
                    assert run["chunks"] == []


def test_right_aligned_text_is_positioned_by_its_measured_width(sample_layout: dict) -> None:
    columns = sample_layout["table"]["columns"]
    right = next(
        (cell for cell in sample_layout["body"]["cells"] if cell["align"] == "right"), None
    )
    if right is None:
        pytest.skip("this report has no right-aligned body column")
    column = int(right["column"])
    short = mussannoni.build_document(sample_layout, {"rows": [{column: "1"}]})
    long = mussannoni.build_document(sample_layout, {"rows": [{column: "1000000"}]})

    def left_of(built: dict) -> float:
        cell = next(
            item for item in built["pages"][0]["rows"][-1]["cells"] if item["column"] == column
        )
        return cell["lines"][0]["left_pt"]

    # Wider text must start further left so that both end at the same right edge.
    assert left_of(long) < left_of(short)
    assert left_of(short) <= columns[column]


def test_column_labels_can_be_overridden(sample_layout: dict) -> None:
    built = mussannoni.build_document(
        sample_layout, {"columns": ["NAMBA", "MKOA"], "rows": [["1", "MWANZA"]]}
    )
    header_text = " ".join(
        run["text"]
        for row in built["pages"][0]["rows"][: sample_layout["header"]["row_count"]]
        for cell in row["cells"]
        for line in cell["lines"]
        for run in line["runs"]
    )
    assert "NAMBA" in header_text
    assert "MKOA" in header_text


def test_header_cells_can_be_overridden_by_address(sample_layout: dict) -> None:
    built = mussannoni.build_document(
        sample_layout, {"header": {"0.0": "HALMASHAURI YA MWANZA"}, "rows": [["1"]]}
    )
    first = built["pages"][0]["rows"][0]
    texts = [
        run["text"] for cell in first["cells"] for line in cell["lines"] for run in line["runs"]
    ]
    assert "HALMASHAURI YA MWANZA" in texts


def test_a_bad_header_address_is_rejected(sample_layout: dict) -> None:
    with pytest.raises(InvalidDataError, match="must be 'row.column'"):
        mussannoni.build_document(sample_layout, {"header": {"top": "x"}, "rows": [["1"]]})
    with pytest.raises(InvalidDataError, match="names row"):
        mussannoni.build_document(sample_layout, {"header": {"99.0": "x"}, "rows": [["1"]]})


def test_missing_rows_is_an_error(sample_layout: dict) -> None:
    with pytest.raises(InvalidDataError, match=r"data\['rows'\] is required"):
        mussannoni.build_document(sample_layout, {})


def test_too_many_values_in_a_row_is_an_error(sample_layout: dict) -> None:
    width = len(sample_layout["table"]["columns"])
    with pytest.raises(InvalidDataError, match="columns"):
        mussannoni.build_document(sample_layout, {"rows": [["x"] * (width + 1)]})


def test_an_unrecognised_row_key_is_an_error(sample_layout: dict) -> None:
    with pytest.raises(InvalidDataError, match="neither a column index nor"):
        mussannoni.build_document(sample_layout, {"rows": [{"NOT A COLUMN": "x"}]})


def test_an_unrecognised_top_level_key_is_an_error(sample_layout: dict) -> None:
    # Catches a typo like "row" or "titel" instead of silently rendering an empty report.
    with pytest.raises(InvalidDataError, match="Unknown key"):
        mussannoni.build_document(sample_layout, {"rows": [["x"]], "titel": "oops"})


def test_every_column_receives_its_value(sample_layout: dict) -> None:
    # A few reports have columns that are merged away in every measured row and so have no
    # prototype. They must borrow one rather than drop the caller's data.
    width = len(sample_layout["table"]["columns"])
    built = mussannoni.build_document(sample_layout, {"rows": [[f"C{i}" for i in range(width)]]})
    placed = {
        cell["column"]
        for cell in built["pages"][0]["rows"][-1]["cells"]
        if cell["lines"]
    }
    assert placed == set(range(width))


# --------------------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------------------


def test_render_report_returns_a_valid_pdf(sample_layout: dict) -> None:
    pdf = mussannoni.render_report(
        SAMPLE, {"rows": _rows(sample_layout, 3)}, level=SAMPLE_LEVEL
    )
    assert pdf.startswith(b"%PDF-")
    with pymupdf.open(stream=pdf, filetype="pdf") as opened:
        assert opened.page_count == 1
        assert round(opened[0].rect.width) == round(sample_layout["page"]["width_pt"])
        assert round(opened[0].rect.height) == round(sample_layout["page"]["height_pt"])


def test_rendered_pdf_contains_the_supplied_values(sample_layout: dict) -> None:
    pdf = mussannoni.render_report(
        SAMPLE, {"rows": [["1", "NYAMAGANA", "MWANZA SECONDARY"]]}, level=SAMPLE_LEVEL
    )
    with pymupdf.open(stream=pdf, filetype="pdf") as opened:
        text = opened[0].get_text()
    assert "NYAMAGANA" in text
    assert "MWANZA SECONDARY" in text


def test_render_paginates_into_multiple_pdf_pages(sample_layout: dict) -> None:
    rows = _rows(sample_layout, sample_layout["rows_per_page"] + 1)
    pdf = mussannoni.render_report(SAMPLE, {"rows": rows}, level=SAMPLE_LEVEL)
    with pymupdf.open(stream=pdf, filetype="pdf") as opened:
        assert opened.page_count == 2


def test_render_report_to_file_creates_parent_directories(
    tmp_path: Path, sample_layout: dict
) -> None:
    destination = tmp_path / "nested" / "deeper" / "report.pdf"
    written = mussannoni.render_report_to_file(
        SAMPLE, {"rows": _rows(sample_layout, 1)}, destination, level=SAMPLE_LEVEL
    )
    assert written == destination
    assert destination.read_bytes().startswith(b"%PDF-")


def test_render_rejects_an_ambiguous_report_key(sample_layout: dict) -> None:
    with pytest.raises(UnknownReportError, match="exists at levels"):
        mussannoni.render_report(AMBIGUOUS, {"rows": [["1"]]})


def test_optimization_preserves_content_exactly(sample_layout: dict) -> None:
    """The recompression pass must never change what is on the page.

    Size is deliberately not asserted to shrink here. WeasyPrint already writes compressed object
    streams, so on its output the pass is a near no-op and can even come out a few hundred bytes
    larger on a small document. The ~5x win is against Chromium's uncompressed objects, and
    ``test_engine.py`` asserts it there. What must hold for *every* engine is that nothing moved.
    """
    rows = _rows(sample_layout, sample_layout["rows_per_page"])
    optimized = mussannoni.render_report(
        SAMPLE, {"rows": rows}, level=SAMPLE_LEVEL, optimize=True
    )
    raw = mussannoni.render_report(SAMPLE, {"rows": rows}, level=SAMPLE_LEVEL, optimize=False)

    with pymupdf.open(stream=optimized, filetype="pdf") as a, pymupdf.open(
        stream=raw, filetype="pdf"
    ) as b:
        assert a.page_count == b.page_count
        for left, right in zip(a, b, strict=True):
            assert left.rect == right.rect
            assert left.rotation == right.rotation
            # Rasterised pixels, page for page: the strongest available statement that the
            # recompression is structural only.
            assert left.get_pixmap(dpi=72).tobytes("ppm") == right.get_pixmap(dpi=72).tobytes(
                "ppm"
            )


def test_optimize_pdf_validates_and_preserves_page_count(tmp_path: Path) -> None:
    from weasyprint import HTML

    path = tmp_path / "sample.pdf"
    HTML(string="<html><body><p>hello</p><p>world</p></body></html>").write_pdf(str(path))
    with pymupdf.open(path) as opened:
        before = opened.page_count

    mussannoni.optimize_pdf(path)

    assert path.read_bytes().startswith(b"%PDF-")
    with pymupdf.open(path) as opened:
        assert opened.page_count == before


# --------------------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------------------


def test_cli_lists_reports(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["reports"]) == 0
    assert "46 reports" in capsys.readouterr().out


def test_cli_lists_reports_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["reports", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 46
    assert {"ordinal", "level", "report_key", "title", "scope"} <= set(payload[0])


def test_cli_summarises_a_layout(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["layout", SAMPLE, "--level", SAMPLE_LEVEL]) == 0
    out = capsys.readouterr().out
    assert SAMPLE in out
    assert "rows/page" in out


def test_cli_renders_from_a_json_file(
    tmp_path: Path, sample_layout: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"rows": _rows(sample_layout, 2)}), encoding="utf-8")
    out = tmp_path / "out.pdf"
    assert (
        cli.main(
            [
                "render",
                SAMPLE,
                "--level",
                SAMPLE_LEVEL,
                "--data",
                str(data),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert out.read_bytes().startswith(b"%PDF-")


def test_cli_reports_a_bad_report_key_without_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["layout", "no_such_report"]) == 1
    assert "mussannoni:" in capsys.readouterr().err


def test_cli_rejects_malformed_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "bad.json"
    data.write_text("{not json", encoding="utf-8")
    assert (
        cli.main(
            ["render", SAMPLE, "--level", SAMPLE_LEVEL, "--data", str(data), "--out", "x.pdf"]
        )
        == 2
    )
    assert "not valid JSON" in capsys.readouterr().err


def test_cli_doctor_reports_engine_availability(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["doctor"]) == 0
    assert "weasyprint" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# public surface
# --------------------------------------------------------------------------------------


def test_every_exported_name_exists() -> None:
    # Catches a name left in __all__ after a rename, which would break `from mussannoni import *`
    # and any documentation generated from the export list.
    assert mussannoni.__all__
    for name in mussannoni.__all__:
        assert hasattr(mussannoni, name), name


def test_the_documented_entry_points_are_exported() -> None:
    for name in ("render_report", "render_report_to_file", "render_document", "report_layout"):
        assert name in mussannoni.__all__
        assert callable(getattr(mussannoni, name))


def test_version_matches_the_distribution_metadata() -> None:
    from importlib.metadata import version

    assert mussannoni.__version__ == version("mussannoni")


def test_registry_module_level_constants() -> None:
    assert registry.LEVELS == ("primary", "secondary")
