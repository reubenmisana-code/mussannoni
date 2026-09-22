"""Render a report to PDF from its measured fixture, through a selectable engine.

This is the *workshop* renderer. It reads the measured ``fixture.json`` out of
``templates/<level>/<report>/`` and writes ``output/<level>/<report>/rendered.pdf``, which
``tools/compare.py`` then rasterises against the reference. It exists to reproduce a reference
PDF as exactly as possible.

The engine implementations and the post-render recompression are **not** duplicated here: they
live in the installable package (:mod:`mussannoni.engines`, :mod:`mussannoni.optimize`) and are
imported. Only two things differ from the packaged renderer, and both are deliberate:

- **The default engine is ``chromium``, not ``weasyprint``.** Every committed calibration and
  fidelity metric was measured against headless Chromium, so the workshop must keep rendering
  through it or the numbers stop being comparable. The package defaults to WeasyPrint because it
  is the only engine that works from a plain ``pip install``.
- **Assets come from ``templates/``, not from the packaged resources.** The workshop renders the
  working copy that ``tools/scaffold.py`` has just written, which is the whole point of the
  tune-and-re-render loop.

Adding an engine is registering one class in :data:`mussannoni.engines.ENGINES`; it becomes
available here and in the package at once.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from mussannoni.engines import ENGINES, Engine, engine_names
from mussannoni.optimize import optimize_pdf
from tools.common import ROOT, find_report, output_dir, template_dir, write_json

# The workshop's reference renderer. Distinct from mussannoni.engines.DEFAULT_ENGINE on purpose;
# see the module docstring.
DEFAULT_ENGINE = "chromium"
ENGINE_ENV_VAR = "MUSSANNONI_ENGINE"

# Re-exported so the workshop's own call sites and tests keep a single import site.
ChromiumEngine = type(ENGINES["chromium"])
WeasyPrintEngine = type(ENGINES["weasyprint"])

__all__ = [
    "DEFAULT_ENGINE",
    "ENGINES",
    "ENGINE_ENV_VAR",
    "ChromiumEngine",
    "Engine",
    "WeasyPrintEngine",
    "build_html",
    "engine_names",
    "optimize_pdf",
    "render",
    "resolve_engine",
]


def resolve_engine(engine: str | None) -> str:
    """Selection precedence: explicit argument > ``MUSSANNONI_ENGINE`` > the workshop default."""
    name = engine or os.environ.get(ENGINE_ENV_VAR) or DEFAULT_ENGINE
    if name not in ENGINES:
        raise ValueError(f"Unknown rendering engine {name!r}; choose from {engine_names()}")
    return name


def build_html(level: str, report_key: str) -> tuple[str, Path, Path, str]:
    """Render the working template + fixture to HTML on disk, identically for every engine.

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


def render(
    level: str, report_key: str, *, engine: str | None = None, optimize: bool = True
) -> Path:
    """Build the HTML once and render it to PDF through the selected engine.

    Unless ``optimize`` is False, the engine's output is structurally recompressed in place by
    :func:`mussannoni.optimize.optimize_pdf` (object streams + deflate + garbage collection),
    which is content-preserving and pixel-identical.
    """
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

    if optimize:
        optimize_pdf(pdf_path)

    # Record the engine that produced this render so compare() reports it truthfully. Kept as a
    # sidecar next to the PDF; the optimize flag is recorded too for provenance.
    write_json(destination / "render-meta.json", {"engine": engine_name, "optimized": optimize})
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
    parser.add_argument(
        "--no-optimize",
        dest="optimize",
        action="store_false",
        help="skip the structural PDF recompression pass (inspect raw engine output)",
    )
    args = parser.parse_args()
    path = render(args.level, args.report_key, engine=args.engine, optimize=args.optimize)
    print(f"{resolve_engine(args.engine)}: {path}")


if __name__ == "__main__":
    main()
