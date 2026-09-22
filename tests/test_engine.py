"""Tests for the pluggable rendering-engine abstraction in tools/render.py."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from tools import render as render_module
from tools.render import (
    DEFAULT_ENGINE,
    ENGINES,
    ChromiumEngine,
    build_html,
    engine_names,
    render,
    resolve_engine,
)

ROOT = Path(__file__).resolve().parents[1]


def test_registry_exposes_both_engines() -> None:
    assert "chromium" in ENGINES
    assert "weasyprint" in ENGINES
    assert set(engine_names()) == set(ENGINES)


def test_default_engine_is_chromium() -> None:
    assert DEFAULT_ENGINE == "chromium"


def test_engine_names_match_registered_names() -> None:
    for name, engine in ENGINES.items():
        assert engine.name == name


def test_selection_defaults_to_house_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUSSANNONI_ENGINE", raising=False)
    assert resolve_engine(None) == "chromium"


def test_selection_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUSSANNONI_ENGINE", "weasyprint")
    assert resolve_engine(None) == "weasyprint"


def test_explicit_argument_overrides_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MUSSANNONI_ENGINE", "weasyprint")
    assert resolve_engine("chromium") == "chromium"


def test_unknown_engine_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MUSSANNONI_ENGINE", raising=False)
    with pytest.raises(ValueError):
        resolve_engine("ghostscript")


def test_chromium_engine_builds_expected_command_list(tmp_path: Path) -> None:
    engine = ChromiumEngine()
    html_path = tmp_path / "rendered.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    pdf_path = tmp_path / "rendered.pdf"
    commands = engine.build_commands("render-primary-council-best-students", html_path, pdf_path)
    assert commands == [
        [
            "agent-browser",
            "--session",
            "render-primary-council-best-students",
            "open",
            html_path.as_uri(),
        ],
        ["agent-browser", "--session", "render-primary-council-best-students", "wait", "1000"],
        ["agent-browser", "--session", "render-primary-council-best-students", "pdf", str(pdf_path)],
        ["agent-browser", "--session", "render-primary-council-best-students", "close"],
    ]


def test_build_html_is_engine_independent() -> None:
    html, work_dir, destination, base_url = build_html("primary", "council_best_students")
    assert "<html" in html.lower()
    assert base_url.startswith("file://")
    assert base_url.endswith("/")
    assert (work_dir / "rendered.html").read_text(encoding="utf-8") == html
    assert destination.name == "council-best-students"


def test_weasyprint_engine_renders_valid_multipage_pdf(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("weasyprint")
    # Render into a temp destination so the committed output/ is not touched.
    real_output_dir = render_module.output_dir

    def fake_output_dir(report: dict) -> Path:
        target = tmp_path / report["level"] / report["report_key"].replace("_", "-")
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(render_module, "output_dir", fake_output_dir)
    try:
        pdf_path = render("primary", "council_best_students", engine="weasyprint")
    finally:
        render_module.output_dir = real_output_dir

    data = pdf_path.read_bytes()
    assert data.startswith(b"%PDF-")
    with pymupdf.open(pdf_path) as doc:
        assert doc.page_count == 4
        rect = doc[0].rect
        assert round(rect.width) == 792
        assert round(rect.height) == 612

    meta = pdf_path.parent / "render-meta.json"
    assert meta.exists()
    assert '"weasyprint"' in meta.read_text(encoding="utf-8")
