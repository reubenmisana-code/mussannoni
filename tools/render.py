from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from tools.common import ROOT, find_report, output_dir, template_dir


def render(level: str, report_key: str) -> Path:
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

    pdf_path = destination / "rendered.pdf"
    session = f"render-{level}-{report_key.replace('_', '-')}"
    commands = [
        ["agent-browser", "--session", session, "open", html_path.as_uri()],
        ["agent-browser", "--session", session, "wait", "1000"],
        ["agent-browser", "--session", session, "pdf", str(pdf_path)],
        ["agent-browser", "--session", session, "close"],
    ]
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
    return pdf_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a report through headless Chromium")
    parser.add_argument("level", choices=("secondary", "primary"))
    parser.add_argument("report_key")
    args = parser.parse_args()
    print(render(args.level, args.report_key))


if __name__ == "__main__":
    main()
