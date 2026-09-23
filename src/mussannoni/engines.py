"""Selectable rendering engines.

The HTML is built once, identically, whichever engine renders it, so any difference in the
result is the engine's own and not an artefact of two code paths.

Three engines ship:

- ``weasyprint`` renders in-process through the ``weasyprint`` library. It is the **packaged
  default**, because it is the only engine that works from a plain ``pip install``.
- ``chromium`` shells the ``agent-browser`` headless-Chromium CLI. It is the workshop's reference
  renderer for CSS fidelity — every committed calibration was measured against it — but
  ``agent-browser`` is a Node binary that is not a Python dependency and cannot be installed from
  PyPI. It is therefore opt-in, and asks for a clear error rather than a traceback when absent.
- ``chromium-cli`` drives a Chromium binary directly through ``--print-to-pdf``, for hosts where
  ``agent-browser``'s daemon cannot run at all. It needs no Node and no daemon, and it works
  around snap confinement's private ``/tmp``.

None of the three are interchangeable at sub-point precision. The baseline corrections baked into
the measured layouts were fitted against the Chromium ``agent-browser`` drives, so rendering them
through WeasyPrint — or through a different Chromium build — carries a small systematic offset. It
is well under a point and invisible in a printed report, but it is the difference between "looks
right" and "passes the fidelity gate", and only ``chromium`` is gated.

Adding an engine is registering one class in :data:`ENGINES`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from .errors import EngineUnavailableError, RenderError, UnknownEngineError

DEFAULT_ENGINE = "weasyprint"
ENGINE_ENV_VAR = "MUSSANNONI_ENGINE"
# Where a confined browser may render. See ChromiumCliEngine.
WORK_DIR_ENV_VAR = "MUSSANNONI_WORK_DIR"
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


class ChromiumCliEngine:
    """Headless Chromium driven straight from its own binary, with no automation CLI.

    ``chromium`` needs ``agent-browser``, which is a client for a daemon it starts itself. Where
    that daemon cannot run — a container without the IPC it wants, which reports
    ``Resource temporarily unavailable`` and then times out — the browser is still perfectly
    usable through its own ``--print-to-pdf``. This engine is that path, and the invocation is
    the one the ShuleYetu backend used before it adopted this package.

    **Why it does not render where it is told.** A snap-packaged Chromium runs under confinement
    and gets a *private* ``/tmp``: it reports success writing a PDF there while the host sees
    nothing, or fails outright with ``No such file or directory`` for a path that plainly
    exists. :func:`mussannoni.document.render_html_to_pdf` renders inside
    ``tempfile.TemporaryDirectory``, i.e. under ``/tmp``, so this engine copies the HTML to a
    working directory outside ``/tmp``, renders there, and copies the PDF back to ``pdf_path``.
    That costs two file copies of a document that is already in memory, and it is the difference
    between this engine working and silently producing nothing. Override the location with
    ``MUSSANNONI_WORK_DIR`` if the default is not writable.

    The HTML links its stylesheets as absolute ``file://`` URIs into the packaged resources, so
    moving the document does not change what it resolves.

    **Fidelity.** This is not the ``chromium`` engine under another name. The committed
    calibrations were measured against the Chromium that ``agent-browser`` drives; a different
    Chromium build seats baselines slightly differently, so a pass here is not a pass there, in
    exactly the way this module's docstring already says of WeasyPrint.
    """

    name = "chromium-cli"
    # Most specific first: the Debian/Ubuntu wrapper, then the plain names, then Chrome.
    binaries = (
        "chromium-browser",
        "chromium",
        "google-chrome-stable",
        "google-chrome",
    )

    def executable(self) -> str | None:
        """The first Chromium-family binary on PATH, or ``None``."""
        for binary in self.binaries:
            location = shutil.which(binary)
            if location is not None:
                return location
        return None

    def available(self) -> bool:
        return self.executable() is not None

    def build_command(self, executable: str, html_path: Path, pdf_path: Path,
                      profile_dir: Path) -> list[str]:
        """The exact invocation, exposed so it can be asserted without running a browser.

        ``--no-sandbox`` because this runs as root in a container, where the sandbox cannot
        initialise; ``--disable-dev-shm-usage`` because a container's ``/dev/shm`` is typically
        64 MB and Chromium will exhaust it on a large document; ``--user-data-dir`` so a render
        never inherits or mutates a real browser profile.
        """
        return [
            executable,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_path}",
            str(html_path),
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
        executable = self.executable()
        if executable is None:
            raise EngineUnavailableError(
                f"The {self.name} engine needs one of {list(self.binaries)} on PATH. Use "
                "engine='weasyprint' for an in-process render."
            )

        root = _confinement_safe_root()
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"{session}-", dir=root) as raw:
            outside = Path(raw)
            staged_html = outside / html_path.name
            staged_html.write_text(html, encoding="utf-8")
            staged_pdf = outside / pdf_path.name
            profile = outside / "profile"

            command = self.build_command(executable, staged_html, staged_pdf, profile)
            completed = subprocess.run(
                command, cwd=outside, check=False, timeout=900,
                capture_output=True,
            )
            if not staged_pdf.exists():
                detail = completed.stderr.decode("utf-8", "replace")[-600:]
                raise RenderError(
                    f"The {self.name} engine produced no PDF (exit {completed.returncode}). "
                    f"Chromium said: {detail}"
                )
            pdf_path.write_bytes(staged_pdf.read_bytes())
        _require_pdf(pdf_path, self.name)


def _confinement_safe_root() -> Path:
    """A working directory a confined browser can actually write to.

    Never under ``/tmp``: see :class:`ChromiumCliEngine`. ``MUSSANNONI_WORK_DIR`` wins, then a
    cache directory under the user's home, which exists for the process that is rendering.
    """
    override = os.environ.get(WORK_DIR_ENV_VAR)
    if override:
        return Path(override)
    return Path.home() / ".cache" / "mussannoni" / "render"


def _require_pdf(pdf_path: Path, engine_name: str) -> None:
    if not pdf_path.exists() or not pdf_path.read_bytes().startswith(PDF_MAGIC):
        raise RenderError(f"The {engine_name} engine did not produce a valid PDF: {pdf_path}")


ENGINES: dict[str, Engine] = {
    engine.name: engine
    for engine in (WeasyPrintEngine(), ChromiumEngine(), ChromiumCliEngine())
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
