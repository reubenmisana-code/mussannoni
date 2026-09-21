"""Turn measured grids into a data-driven HTML table template, CSS and proof fixture.

The template is real table markup: ``<colgroup>`` widths, ``<thead>`` for the repeating
header band, ``<tr>`` rows, ``<td>`` cells with colspan/rowspan, and generated classes for
the measured fills, borders and text styles. Sample values live only in ``fixture.json``.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from tools.common import (
    ROOT,
    extraction_dir,
    find_report,
    load_catalog,
    template_dir,
    write_json,
)
from tools.evidence import Style, load_evidence
from tools.fonts import (
    BASE14_MAP,
    FaceMetrics,
    base14_metrics,
    embedded_metrics,
    export_base14,
    sanitise,
)
from tools.grid import Cell, PageGrid, Run, build_grids
from tools.tune import correction_for, load_calibration

SHARED_TEMPLATE = ROOT / "templates" / "_shared"


def css_colour(colour: tuple[float, ...]) -> str:
    return "color(srgb " + " ".join(f"{channel:.6f}" for channel in colour) + ")"


class FontResolver:
    """Map every PDF font name in a report to a CSS family plus real face metrics."""

    def __init__(self, report: dict[str, Any], destination: Path) -> None:
        self.faces: dict[str, FaceMetrics] = {}
        self.embedded_files: dict[str, tuple[Path, int, str]] = {}
        self.destination = destination
        self.report_font_dir = destination / "fonts"
        self.extraction = extraction_dir(report)

    def resolve(self, style: Style) -> FaceMetrics:
        if style.font in self.faces:
            return self.faces[style.font]
        face = self._build(style)
        self.faces[style.font] = face
        return face

    def _build(self, style: Style) -> FaceMetrics:
        embedded = self._find_embedded(style.font)
        if embedded is not None:
            family = f"'Report {sanitise(style.font)}'"
            self.report_font_dir.mkdir(parents=True, exist_ok=True)
            target = self.report_font_dir / embedded.name
            shutil.copy2(embedded, target)
            css_style = "italic" if style.italic else "normal"
            self.embedded_files[family] = (target, style.weight, css_style)
            return embedded_metrics(target, family, style.weight, css_style)

        mapped = BASE14_MAP.get(style.font)
        if mapped is None:
            serif = "Times" in style.font
            mapped = (
                "'Times New Roman', 'Report Serif'" if serif else "Arial, 'Report Sans'",
                style.weight,
                "italic" if style.italic else "normal",
                ("tibo" if style.bold else "tiro") if serif else ("hebo" if style.bold else "helv"),
                ("times-bold" if style.bold else "times")
                if serif
                else ("arial-bold" if style.bold else "arial"),
            )
        family, weight, css_style, code, system_key = mapped
        return base14_metrics(code, family, weight, css_style, system_key)

    def _find_embedded(self, font_name: str) -> Path | None:
        directory = self.extraction / "embedded-fonts"
        if not directory.exists():
            return None
        wanted = sanitise(font_name).lower()
        for candidate in sorted(directory.glob("*")):
            stem = candidate.stem.lower()
            if stem.startswith(wanted) or wanted in stem:
                return candidate
        return None


class ClassTable:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.rules: dict[str, str] = {}
        self.names: dict[str, str] = {}

    def add(self, key: str, declarations: str) -> str:
        if key not in self.names:
            name = f"{self.prefix}{len(self.names)}"
            self.names[key] = name
            self.rules[name] = declarations
        return self.names[key]

    def css(self) -> str:
        return "\n".join(
            f".{name} {{ {declarations} }}" for name, declarations in self.rules.items()
        )


def build_fixture(
    report: dict[str, Any],
    grids: list[PageGrid],
    resolver: FontResolver,
    calibration: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    style_classes = ClassTable("t")
    fill_classes = ClassTable("f")

    def style_class(style: Style) -> str:
        face = resolver.resolve(style)
        key = f"{face.family}|{face.weight}|{face.style}|{style.size_pt}|{style.hex_colour}"
        return style_classes.add(
            key,
            f"font-family: {face.family}; font-size: {style.size_pt}pt; font-weight: {face.weight}; "
            f"font-style: {face.style}; color: {style.css_colour};",
        )

    pages: list[dict[str, Any]] = []
    for grid in grids:
        rows: list[dict[str, Any]] = []
        by_row: dict[int, list[Cell]] = {}
        for cell in grid.cells:
            if cell.row_span:
                by_row.setdefault(cell.row, []).append(cell)

        for row_index, height in enumerate(grid.row_heights):
            cells_payload = []
            for cell in sorted(by_row.get(row_index, []), key=lambda item: item.column):
                lines = build_lines(cell, style_class, resolver, calibration)
                payload: dict[str, Any] = {
                    "column": cell.column,
                    "colspan": cell.column_span,
                    "rowspan": cell.row_span,
                    "classes": [],
                    "lines": lines,
                }
                if cell.fill is not None:
                    payload["classes"].append(
                        fill_classes.add(str(cell.fill), f"background: {css_colour(cell.fill)};")
                    )
                payload["align"] = cell.align
                payload["pad_left"] = cell.pad_left
                payload["pad_right"] = cell.pad_right
                cells_payload.append(payload)
            rows.append({"index": row_index, "height_pt": height, "cells": cells_payload})

        vectors = [
            {
                "d": path.svg_path(),
                "fill": css_colour(path.paint.fill) if path.paint.fill else "none",
                "stroke": css_colour(path.paint.stroke) if path.paint.stroke else "none",
                "stroke_width": path.paint.stroke_width,
            }
            for path in grid.curved_paths
        ]
        rules = build_rule_layer(grid)
        # Text that belongs to no cell - a page with no gridlines at all, or a caption painted
        # outside the table - still has to be rendered, or the page silently loses content.
        loose = build_loose_lines(grid, style_class, resolver, calibration)
        pages.append(
            {
                "number": grid.number,
                "width_pt": grid.width_pt,
                "height_pt": grid.height_pt,
                "orientation": grid.orientation,
                "table_x_pt": grid.column_edges[0] if grid.column_edges else 0.0,
                "table_y_pt": grid.row_edges[0] if grid.row_edges else 0.0,
                "table_width_pt": round(sum(grid.column_widths), 2),
                "table_height_pt": round(sum(grid.row_heights), 2),
                "columns": grid.column_widths,
                "header_rows": grid.header_rows,
                "rows": rows,
                "vectors": vectors,
                "rules": rules,
                "loose_lines": loose,
            }
        )

    fixture = {
        "schema_version": 1,
        "report": {
            "level": report["level"],
            "report_key": report["report_key"],
            "title": report["title"],
            "scope": report["scope"],
            "sample_unit": report["sample_unit"],
        },
        "pages": pages,
    }
    first = pages[0] if pages else {"width_pt": 612, "height_pt": 792}
    css = render_css(style_classes, fill_classes, resolver, first["width_pt"], first["height_pt"])
    return fixture, css


def build_rule_layer(grid: PageGrid) -> list[dict[str, Any]]:
    """Gridlines as exact vector rules, one path per colour.

    They are deliberately not CSS borders. A CSS border width rounds to whole device pixels,
    and these reports draw 0.48pt hairlines - often two of them 0.48pt apart for an
    emphasised rule - which a rounded border cannot express: Chromium collapses
    `1.44pt double` into a single line and half the rule pixels disappear. Vector rules
    reproduce weight, position and colour exactly, while the table still carries the
    structure, the fills and the text.
    """
    by_colour: dict[tuple[float, float, float], list[str]] = {}
    for rule in grid.rules:
        colour = rule.paint.fill or rule.paint.stroke
        if colour is None:
            continue
        by_colour.setdefault(colour, []).append(f"M{rule.x} {rule.y}h{rule.w}v{rule.h}h{-rule.w}Z")
    return [
        {"d": "".join(commands), "fill": css_colour(colour)}
        for colour, commands in sorted(by_colour.items())
    ]


def build_loose_lines(
    grid: PageGrid,
    style_class,
    resolver: FontResolver,
    calibration: dict[str, Any],
) -> list[dict[str, Any]]:
    """Place spans that belong to no cell, measured from the page origin."""
    if not grid.loose_spans:
        return []
    carrier = Cell(
        row=0,
        column=0,
        row_span=1,
        column_span=1,
        x=0.0,
        y=0.0,
        width=grid.width_pt,
        height=grid.height_pt,
    )
    carrier.runs = [
        Run(span.text, span.style, span.x0, span.x1, span.oy) for span in grid.loose_spans
    ]
    carrier.runs.sort(key=lambda run: (round(run.baseline, 1), run.x0))
    return build_lines(carrier, style_class, resolver, calibration)


def build_lines(
    cell: Cell,
    style_class,
    resolver: FontResolver,
    calibration: dict[str, Any],
) -> list[dict[str, Any]]:
    """Group runs into baseline lines and place each line from its measured baseline."""
    if not cell.runs:
        return []
    grouped: dict[float, list] = {}
    for run in cell.runs:
        grouped.setdefault(round(run.baseline, 2), []).append(run)

    lines: list[dict[str, Any]] = []
    for baseline in sorted(grouped):
        runs = sorted(grouped[baseline], key=lambda item: item.x0)
        payload_runs = []
        cursor: float | None = None
        for run in runs:
            entry: dict[str, Any] = {"class": style_class(run.style), "text": run.text}
            if cursor is not None:
                gap = round(run.x0 - cursor, 2)
                if gap > 0.75:
                    entry["spacer_pt"] = gap
            payload_runs.append(entry)
            cursor = run.x1
        leader = runs[0].style
        factor = resolver.resolve(leader).baseline_factor
        dx, dy = correction_for(calibration, leader.size_pt)
        lines.append(
            {
                # The leading run's style sits on the line box so `line-height: 1` resolves
                # against the text's own font size rather than an inherited one.
                "class": style_class(leader),
                "left_pt": round(runs[0].x0 - cell.x - dx, 2),
                "top_pt": round(baseline - leader.size_pt * factor - cell.y - dy, 2),
                "runs": payload_runs,
            }
        )
    return lines


def render_css(
    style_classes: ClassTable,
    fill_classes: ClassTable,
    resolver: FontResolver,
    page_width_pt: float,
    page_height_pt: float,
) -> str:
    face_rules = []
    for family, (path, weight, css_style) in sorted(resolver.embedded_files.items()):
        face_rules.append(
            "@font-face {\n"
            f"  font-family: {family};\n"
            f"  src: url('fonts/{path.name}') format('truetype');\n"
            f"  font-weight: {weight};\n"
            f"  font-style: {css_style};\n"
            "}"
        )
    sections = [
        "/* Generated by tools/scaffold.py from measured evidence. Do not hand-edit. */",
        f"@page {{ size: {page_width_pt}pt {page_height_pt}pt; margin: 0; }}",
        "\n".join(face_rules),
        "/* text styles */",
        style_classes.css(),
        "/* cell fills */",
        fill_classes.css(),
    ]
    return "\n\n".join(section for section in sections if section.strip()) + "\n"


TEMPLATE_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{{ report.title }}</title>
    <link rel="stylesheet" href="{{ assets.shared_css }}">
    <link rel="stylesheet" href="{{ assets.report_css }}">
  </head>
  <body>
    {% for page in pages %}
    <section class="report-page" data-page="{{ page.number }}"
             style="width: {{ page.width_pt }}pt; height: {{ page.height_pt }}pt;">
      {% if page.vectors %}
      <svg class="report-vectors" viewBox="0 0 {{ page.width_pt }} {{ page.height_pt }}" aria-hidden="true">
        {% for vector in page.vectors %}
        <path d="{{ vector.d }}" fill="{{ vector.fill }}" stroke="{{ vector.stroke }}"
              stroke-width="{{ vector.stroke_width }}"/>
        {% endfor %}
      </svg>
      {% endif %}
      {% if page.loose_lines %}
      <div class="page-text">
        {% for line in page.loose_lines %}
        <div class="cell-line {{ line.class }}" style="left: {{ line.left_pt }}pt; top: {{ line.top_pt }}pt;">
          {%- for run in line.runs %}{% if run.spacer_pt is defined %}<span class="spacer" style="width: {{ run.spacer_pt }}pt;"></span>{% endif %}<span class="{{ run.class }}">{{ run.text }}</span>{% endfor %}
        </div>
        {% endfor %}
      </div>
      {% endif %}
      {% if page.columns %}
      <table class="report-grid"
             style="left: {{ page.table_x_pt }}pt; top: {{ page.table_y_pt }}pt;
                    width: {{ page.table_width_pt }}pt; height: {{ page.table_height_pt }}pt;">
        <colgroup>
          {% for width in page.columns %}
          <col style="width: {{ width }}pt;">
          {% endfor %}
        </colgroup>
        {% if page.header_rows %}
        <thead>
          {% for row in page.rows[:page.header_rows] %}
          {{ render_row(row) }}
          {% endfor %}
        </thead>
        {% endif %}
        <tbody>
          {% for row in page.rows[page.header_rows:] %}
          {{ render_row(row) }}
          {% endfor %}
        </tbody>
      </table>
      {% endif %}
      {% if page.rules %}
      <svg class="report-rules" viewBox="0 0 {{ page.width_pt }} {{ page.height_pt }}" aria-hidden="true">
        {% for rule in page.rules %}
        <path d="{{ rule.d }}" fill="{{ rule.fill }}"/>
        {% endfor %}
      </svg>
      {% endif %}
    </section>
    {% endfor %}
  </body>
</html>
"""

# Rows are emitted without any stray whitespace: a whitespace text node inside a <td>
# creates a real line box and silently makes every row taller than its measured height.
ROW_MACRO = (
    "{% macro render_row(row) %}"
    '<tr style="height: {{ row.height_pt }}pt;">'
    "{% for cell in row.cells %}"
    "<td class=\"{{ cell.classes | join(' ') }}\""
    '{% if cell.colspan > 1 %} colspan="{{ cell.colspan }}"{% endif %}'
    '{% if cell.rowspan > 1 %} rowspan="{{ cell.rowspan }}"{% endif %}'
    ' style="text-align: {{ cell.align }};'
    "{% if cell.pad_left %} padding-left: {{ cell.pad_left }}pt;{% endif %}"
    '{% if cell.pad_right %} padding-right: {{ cell.pad_right }}pt;{% endif %}">'
    "{% for line in cell.lines %}"
    '<div class="cell-line {{ line.class }}" style="left: {{ line.left_pt }}pt; top: {{ line.top_pt }}pt;">'
    "{% for run in line.runs %}"
    '{% if run.spacer_pt is defined %}<span class="spacer" style="width: {{ run.spacer_pt }}pt;"></span>{% endif %}'
    '<span class="{{ run.class }}">{{ run.text }}</span>'
    "{% endfor %}"
    "</div>"
    "{% endfor %}"
    "</td>"
    "{% endfor %}"
    "</tr>"
    "{% endmacro %}\n"
)


def write_template(destination: Path) -> None:
    (destination / "template.html").write_text(ROW_MACRO + TEMPLATE_HTML, encoding="utf-8")


def write_bindings(destination: Path, report: dict[str, Any], grids: list[PageGrid]) -> None:
    header = next((grid for grid in grids if grid.header_rows), None)
    columns = []
    if header is not None:
        labels: dict[int, str] = {}
        for cell in header.cells:
            if cell.row_span and cell.row < header.header_rows and cell.text.strip():
                labels[cell.column] = " ".join(cell.text.split())
        for index, width in enumerate(header.column_widths):
            columns.append(
                {
                    "index": index,
                    "width_pt": width,
                    "reference_label": labels.get(index),
                    "field": None,
                }
            )
    payload = {
        "schema_version": 1,
        "report_key": report["report_key"],
        "level": report["level"],
        "status": "provisional",
        "reason": (
            "Column labels and widths are measured from the reference. The canonical field names "
            "come from the backend registry, which is not present in this repository, so `field` "
            "is left unset rather than invented."
        ),
        "columns": columns,
    }
    (destination / "bindings.yaml").write_text(
        "\n".join(
            [
                "# Generated by tools/scaffold.py. `field` must be completed from the backend",
                "# registry before a template is promoted.",
                _yaml_dump(payload),
            ]
        ),
        encoding="utf-8",
    )


def _yaml_dump(payload: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120)


def scaffold(level: str, report_key: str) -> Path:
    report = find_report(level, report_key)
    destination = template_dir(report)
    destination.mkdir(parents=True, exist_ok=True)
    export_base14()

    pages = load_evidence(extraction_dir(report))
    grids = build_grids(pages)
    resolver = FontResolver(report, destination)
    calibration = load_calibration(destination)
    fixture, css = build_fixture(report, grids, resolver, calibration)
    write_json(destination / "fixture.json", fixture)
    (destination / "report.css").write_text(css, encoding="utf-8")
    write_template(destination)
    write_bindings(destination, report, grids)
    return destination


def scaffold_all() -> None:
    for report in load_catalog()["reports"]:
        destination = scaffold(report["level"], report["report_key"])
        print(
            f"{report['ordinal']:>2} {report['level']:<9} {report['report_key']:<38} -> {destination.relative_to(ROOT)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold measured HTML table templates")
    parser.add_argument("level", nargs="?", choices=("secondary", "primary"))
    parser.add_argument("report_key", nargs="?")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.all:
        scaffold_all()
        return
    if not args.level or not args.report_key:
        parser.error("provide LEVEL and REPORT_KEY, or --all")
    print(scaffold(args.level, args.report_key))


if __name__ == "__main__":
    main()
