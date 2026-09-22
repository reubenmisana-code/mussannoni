"""Render a report to PDF through a selectable rendering engine.

The HTML is built once, identically, regardless of engine, so both engines render the same
input and any difference in the result is the engine's own. Two engines ship today:

- ``chromium`` — shells the ``agent-browser`` headless-Chromium CLI. The reference renderer
  for CSS fidelity and the house default.
- ``weasyprint`` — renders in-process via the ``weasyprint`` library. Much smaller files, but
  its CSS support differs, so its fidelity is a separate, separately recorded verification.

Adding an engine is registering one class in ``ENGINES``. Selection precedence is:
explicit ``--engine`` / ``engine=`` argument, then the ``MUSSANNONI_ENGINE`` environment
variable, then the default (``chromium``).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from tools.common import ROOT, find_report, output_dir, template_dir, write_json

DEFAULT_ENGINE = "chromium"
ENGINE_ENV_VAR = "MUSSANNONI_ENGINE"


class Engine(Protocol):
    """A rendering engine turns built HTML into a PDF on disk.

    Implementations receive the already-built HTML (as both a string and a file already written
    under the project tree) plus the ``base_url`` needed to resolve relative ``url()`` asset
    references. They must leave a valid PDF at ``pdf_path`` and raise on failure.
    """

    name: str

    def render(
        self,
        *,
        html: str,
        html_path: Path,
        pdf_path: Path,
        base_url: str,
        work_dir: Path,
        session: str,
    ) -> None: ...


class ChromiumEngine:
    """Headless Chromium via the ``agent-browser`` CLI. Preserves the original behaviour."""

    name = "chromium"

    def build_commands(self, session: str, html_path: Path, pdf_path: Path) -> list[list[str]]:
        return [
            ["agent-browser", "--session", session, "open", html_path.as_uri()],
            ["agent-browser", "--session", session, "wait", "1000"],
            ["agent-browser", "--session", session, "pdf", str(pdf_path)],
            ["agent-browser", "--session", session, "close"],
        ]

    def render(
        self,
        *,
        html: str,
        html_path: Path,
        pdf_path: Path,
        base_url: str,
        work_dir: Path,
        session: str,
    ) -> None:
        commands = self.build_commands(session, html_path, pdf_path)
        try:
            for command in commands:
                subprocess.run(command, cwd=ROOT, check=True, timeout=180)
        finally:
            subprocess.run(
                ["agent-browser", "--session", session, "close"],
                cwd=ROOT,
                check=False,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if not pdf_path.exists() or not pdf_path.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError(f"Chromium did not produce a valid PDF: {pdf_path}")


class WeasyPrintEngine:
    """In-process rendering via the ``weasyprint`` library."""

    name = "weasyprint"

    def render(
        self,
        *,
        html: str,
        html_path: Path,
        pdf_path: Path,
        base_url: str,
        work_dir: Path,
        session: str,
    ) -> None:
        from weasyprint import HTML

        HTML(string=html, base_url=base_url).write_pdf(str(pdf_path))
        if not pdf_path.exists() or not pdf_path.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError(f"WeasyPrint did not produce a valid PDF: {pdf_path}")


ENGINES: dict[str, Engine] = {
    engine.name: engine
    for engine in (ChromiumEngine(), WeasyPrintEngine())
}


def engine_names() -> list[str]:
    """The registered engine names, for CLI choices and diagnostics."""
    return list(ENGINES)


def resolve_engine(engine: str | None) -> str:
    """Selection precedence: explicit argument > MUSSANNONI_ENGINE env var > default."""
    name = engine or os.environ.get(ENGINE_ENV_VAR) or DEFAULT_ENGINE
    if name not in ENGINES:
        raise ValueError(f"Unknown rendering engine {name!r}; choose from {engine_names()}")
    return name


def build_html(level: str, report_key: str) -> tuple[str, Path, Path, str]:
    """Render the template + fixture to HTML on disk, identically for every engine.

    Returns the HTML string, the work directory, the destination directory, and the base URL
    (the template source directory) that engines use to resolve relative asset references.
    """
    report = find_report(level, report_key)
    source_dir = template_dir(report)
    destination = output_dir(report)
    work_dir = ROOT / "work" / level / report_key.replace("_", "-")
    destination.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    fixture = json.loads((source_dir / "fixture.json").read_text(encoding="utf-8"))
    environment = Environment(
        loader=FileSystemLoader(source_dir),
        autoescape=select_autoescape(("html", "xml")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("template.html")
    fixture["assets"] = {
        "shared_css": (ROOT / "templates" / "_shared" / "reset.css").as_uri(),
        "report_css": (source_dir / "report.css").as_uri(),
    }
    html = template.render(**fixture)
    html_path = work_dir / "rendered.html"
    html_path.write_text(html, encoding="utf-8")

    base_url = f"{source_dir.as_uri()}/"
    return html, work_dir, destination, base_url


def render(level: str, report_key: str, *, engine: str | None = None) -> Path:
    """Build the HTML once and render it to PDF through the selected engine."""
    engine_name = resolve_engine(engine)
    implementation = ENGINES[engine_name]
    html, work_dir, destination, base_url = build_html(level, report_key)
    html_path = work_dir / "rendered.html"
    pdf_path = destination / "rendered.pdf"
    session = f"render-{level}-{report_key.replace('_', '-')}"

    implementation.render(
        html=html,
        html_path=html_path,
        pdf_path=pdf_path,
        base_url=base_url,
        work_dir=work_dir,
        session=session,
    )

    # Record the engine that produced this render so compare() reports it truthfully. Kept as a
    # sidecar next to the PDF; a later post-render optimisation pass can extend this file too.
    write_json(destination / "render-meta.json", {"engine": engine_name})
    return pdf_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a report to PDF")
    parser.add_argument("level", choices=("secondary", "primary"))
    parser.add_argument("report_key")
    parser.add_argument(
        "--engine",
        choices=engine_names(),
        default=None,
        help=f"rendering engine (default: {ENGINE_ENV_VAR} env var, else {DEFAULT_ENGINE})",
    )
    args = parser.parse_args()
    path = render(args.level, args.report_key, engine=args.engine)
    print(f"{resolve_engine(args.engine)}: {path}")


if __name__ == "__main__":
    main()
