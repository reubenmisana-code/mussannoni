"""Selectable rendering engines.

The HTML is built once, identically, whichever engine renders it, so any difference in the
result is the engine's own and not an artefact of two code paths.

Two engines ship:

- ``weasyprint`` renders in-process through the ``weasyprint`` library. It is the **packaged
  default**, because it is the only engine that works from a plain ``pip install``.
- ``chromium`` shells the ``agent-browser`` headless-Chromium CLI. It is the workshop's reference
  renderer for CSS fidelity — every committed calibration was measured against it — but
  ``agent-browser`` is a Node binary that is not a Python dependency and cannot be installed from
  PyPI. It is therefore opt-in, and asks for a clear error rather than a traceback when absent.

The two are not interchangeable at sub-point precision. The baseline corrections baked into the
measured layouts were fitted against Chromium's baseline seating, so rendering them through
WeasyPrint carries a small systematic offset. It is well under a point and invisible in a printed
report, but it is the difference between "looks right" and "passes the fidelity gate", and only
Chromium is gated.

Adding an engine is registering one class in :data:`ENGINES`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable

from .errors import EngineUnavailableError, RenderError, UnknownEngineError

DEFAULT_ENGINE = "weasyprint"
ENGINE_ENV_VAR = "MUSSANNONI_ENGINE"
PDF_MAGIC = b"%PDF-"


@runtime_checkable
class Engine(Protocol):
    """Turns built HTML into a PDF on disk.

    Implementations receive the HTML both as a string and as a file already written under a
    working directory, plus the ``base_url`` needed to resolve relative ``url()`` asset
    references. They must leave a valid PDF at ``pdf_path`` and raise on failure.
    """

    name: str

    def available(self) -> bool:
        """Whether this engine can actually run here."""
        ...

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


class WeasyPrintEngine:
    """In-process rendering through the ``weasyprint`` library."""

    name = "weasyprint"

    def available(self) -> bool:
        try:
            import weasyprint  # noqa: F401
        except Exception:  # noqa: BLE001 - a probe must never raise; see below
            # Importing weasyprint reaches into the system Pango/cairo/GLib stack through
            # ctypes, so a broken or partial install surfaces as OSError, ImportError or
            # whatever the loader felt like raising. Any failure means "not usable here",
            # which is exactly what this probe reports.
            return False
        return True

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
        try:
            from weasyprint import HTML
        except ImportError as error:  # pragma: no cover - weasyprint is a hard dependency
            raise EngineUnavailableError(
                "The weasyprint engine needs the 'weasyprint' package, which also needs the "
                "system Pango/cairo libraries. See https://doc.courtbouillon.org/weasyprint/"
            ) from error

        HTML(string=html, base_url=base_url).write_pdf(str(pdf_path))
        _require_pdf(pdf_path, self.name)


class ChromiumEngine:
    """Headless Chromium through the ``agent-browser`` CLI. The workshop's reference renderer."""

    name = "chromium"
    binary = "agent-browser"

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def build_commands(self, session: str, html_path: Path, pdf_path: Path) -> list[list[str]]:
        """The exact CLI invocations, exposed so they can be asserted without a browser."""
        return [
            [self.binary, "--session", session, "open", html_path.as_uri()],
            [self.binary, "--session", session, "wait", "1000"],
            [self.binary, "--session", session, "pdf", str(pdf_path)],
            [self.binary, "--session", session, "close"],
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
        if not self.available():
            raise EngineUnavailableError(
                f"The chromium engine needs the {self.binary!r} CLI on PATH, which is a Node "
                "binary and not installable from PyPI. Use engine='weasyprint' for an "
                "in-process render, or install agent-browser to reproduce the workshop's "
                "reference output."
            )
        try:
            for command in self.build_commands(session, html_path, pdf_path):
                subprocess.run(command, cwd=work_dir, check=True, timeout=180)
        finally:
            # Always tear the session down, even if a step raised, or the next render inherits it.
            subprocess.run(
                [self.binary, "--session", session, "close"],
                cwd=work_dir,
                check=False,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        _require_pdf(pdf_path, self.name)


def _require_pdf(pdf_path: Path, engine_name: str) -> None:
    if not pdf_path.exists() or not pdf_path.read_bytes().startswith(PDF_MAGIC):
        raise RenderError(f"The {engine_name} engine did not produce a valid PDF: {pdf_path}")


ENGINES: dict[str, Engine] = {
    engine.name: engine for engine in (WeasyPrintEngine(), ChromiumEngine())
}


def engine_names() -> list[str]:
    """The registered engine names, for CLI choices and diagnostics."""
    return list(ENGINES)


def resolve_engine(engine: str | None) -> str:
    """Resolve an engine name: explicit argument, then ``MUSSANNONI_ENGINE``, then the default.

    Raises:
        UnknownEngineError: If the resolved name is not registered.
    """
    name = engine or os.environ.get(ENGINE_ENV_VAR) or DEFAULT_ENGINE
    if name not in ENGINES:
        raise UnknownEngineError(
            f"Unknown rendering engine {name!r}; choose from {engine_names()}"
        )
    return name


def get_engine(engine: str | None = None) -> Engine:
    """The engine implementation for a name, resolved by :func:`resolve_engine`."""
    return ENGINES[resolve_engine(engine)]


def available_engines() -> dict[str, bool]:
    """Every registered engine mapped to whether it can run on this machine."""
    return {name: implementation.available() for name, implementation in ENGINES.items()}
