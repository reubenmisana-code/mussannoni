"""Render Tanzanian school examination result reports to PDF from plain Python dicts.

The report designs reproduced here are the work of Mussa Nnoni, who maintains sars.ac.tz. See
CREDITS.md.

Quick start::

    import mussannoni

    pdf = mussannoni.render_report("council_best_students", {
        "rows": [
            [1, "NYAMAGANA", "MWANZA SECONDARY", "GOVERNMENT", "S0333-0001", "JUMA ALI", "M"],
            [2, "ILEMELA", "BUGANDO SECONDARY", "PRIVATE", "S0334-0002", "ASHA HAMISI", "F"],
        ],
    })
    open("report.pdf", "wb").write(pdf)

Two levels of control:

- :func:`render_report` takes rows of values and places them on the report's measured grid. This
  is what an application wants.
- :func:`render_document` takes a full geometry document — every glyph placed explicitly — and
  reproduces a report exactly. This is what the fidelity workshop produces.

Use :func:`list_reports` to see the 46 available reports and :func:`report_layout` to inspect
what one expects.
"""

from __future__ import annotations

from .api import (
    render_report,
    render_report_to_file,
    report_layout,
    report_roles,
    write_pdf,
)
from .document import build_html, render_document, render_html_to_pdf, validate_document
from .engines import (
    DEFAULT_ENGINE,
    ENGINE_ENV_VAR,
    ENGINES,
    available_engines,
    engine_names,
    resolve_engine,
)
from .errors import (
    EngineUnavailableError,
    InvalidDataError,
    InvalidDocumentError,
    MussaNnoniError,
    RenderError,
    UnknownEngineError,
    UnknownReportError,
)
from .optimize import optimize_pdf
from .registry import LEVELS, Report, find, list_reports
from .table import build_document

__version__ = "0.1.2"

__all__ = [
    "DEFAULT_ENGINE",
    "ENGINES",
    "ENGINE_ENV_VAR",
    "LEVELS",
    "EngineUnavailableError",
    "InvalidDataError",
    "InvalidDocumentError",
    "MussaNnoniError",
    "RenderError",
    "Report",
    "UnknownEngineError",
    "UnknownReportError",
    "__version__",
    "available_engines",
    "build_document",
    "build_html",
    "engine_names",
    "find",
    "list_reports",
    "optimize_pdf",
    "render_document",
    "render_html_to_pdf",
    "render_report",
    "render_report_to_file",
    "report_layout",
    "report_roles",
    "resolve_engine",
    "validate_document",
    "write_pdf",
]
