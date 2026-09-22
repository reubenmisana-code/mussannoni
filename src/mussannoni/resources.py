"""Access to the data files shipped inside the installed package.

The workshop half of this repository is anchored to the repository root: ``tools/common.py``
derives every path from ``ROOT = Path(__file__).resolve().parents[1]``. That is correct for a
checkout and wrong for an install, where it would resolve into ``site-packages``. So the runtime
never looks at the repository layout. It reads only what was copied into
``mussannoni/resources/`` at build time, through :mod:`importlib.resources`.

What is shipped, and what is not:

- ``template.html`` — one copy. The 46 per-report templates in ``templates/`` are byte-identical,
  so shipping 46 of them would be 46 copies of the same file.
- ``_shared/reset.css`` and ``_shared/fonts/`` — the page box, table primitives and base-14 faces.
- ``<level>/<report>/report.css``, ``fonts/`` and ``layout.json`` — the measured CSS, the faces
  that report embeds, and the distilled layout the table API places data onto.
- ``reports.json`` — the report registry, distilled from ``catalog/reports.yaml``.

Deliberately **not** shipped: ``templates/**/fixture.json`` (257 MB of measured geometry, which
is sample data, not code), ``corpus/`` (reference PDFs we do not own), ``extract/`` (76 MB of
evidence) and ``output/``. Regenerate everything under ``resources/`` with
``python -m tools.package_resources``.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import weakref
from functools import cache, lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

RESOURCE_PACKAGE = "mussannoni"
RESOURCE_DIR = "resources"

_TEMPORARY_COPIES: list[Any] = []


@lru_cache(maxsize=1)
def resource_root() -> Path:
    """The packaged resource directory as a real filesystem path.

    WeasyPrint resolves ``url()`` references in the stylesheets against a ``base_url``, and
    fonts are referenced relatively, so the resources have to exist as real files rather than as
    abstract ``Traversable`` objects. A wheel installed normally is already unpacked on disk and
    is used in place. Only a zipimported install needs materialising, and then it is extracted
    once into a temporary directory that lives as long as the process.
    """
    traversable = files(RESOURCE_PACKAGE) / RESOURCE_DIR
    direct = getattr(traversable, "__fspath__", None)
    if direct is not None:
        path = Path(traversable.__fspath__())  # type: ignore[attr-defined]
        if path.is_dir():
            return path

    # Zipimported (or otherwise non-filesystem) install: extract once.
    target = Path(tempfile.mkdtemp(prefix="mussannoni-resources-"))
    _TEMPORARY_COPIES.append(
        weakref.finalize(resource_root, shutil.rmtree, target, ignore_errors=True)
    )
    _extract(traversable, target)
    return target


def _extract(traversable: Any, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in traversable.iterdir():
        destination = target / child.name
        if child.is_dir():
            _extract(child, destination)
        else:
            destination.write_bytes(child.read_bytes())


def artifact_name(report_key: str) -> str:
    """The on-disk directory name for a report key: ``council_best_students`` -> ``council-best-students``."""
    return report_key.replace("_", "-")


def template_path() -> Path:
    """The single Jinja template shared by every report."""
    return resource_root() / "template.html"


def shared_dir() -> Path:
    """The ``_shared`` directory holding ``reset.css`` and the base-14 faces."""
    return resource_root() / "_shared"


def report_dir(level: str, report_key: str) -> Path:
    """The packaged directory for one report: its CSS, embedded faces and layout."""
    return resource_root() / level / artifact_name(report_key)


def registry_payload() -> dict[str, Any]:
    """The raw contents of the packaged report registry."""
    return _read_json(resource_root() / "reports.json")


def layout_payload(level: str, report_key: str) -> dict[str, Any]:
    """The distilled layout for one report."""
    return _read_json(report_dir(level, report_key) / "layout.json")


@cache
def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def asset_uris(level: str, report_key: str) -> tuple[str, str, str]:
    """The ``(shared_css, report_css, base_url)`` triple the template and engines need.

    The two stylesheets are handed to the template as absolute ``file://`` URIs because they sit
    in different directories and each resolves its own relative ``url("fonts/...")`` references
    against itself: ``reset.css`` against ``_shared/``, ``report.css`` against the report
    directory. ``base_url`` points at the report directory, which is what an engine needs to
    resolve anything else relative.
    """
    shared_css = shared_dir() / "reset.css"
    directory = report_dir(level, report_key)
    report_css = directory / "report.css"
    for path in (shared_css, report_css):
        if not path.exists():
            raise FileNotFoundError(
                f"Packaged resource missing: {path}. "
                "Regenerate with `python -m tools.package_resources`."
            )
    return shared_css.as_uri(), report_css.as_uri(), f"{directory.as_uri()}/"
