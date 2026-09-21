"""Font assets and metrics for faithful rendering.

Two font sources, both mechanical:

* Reports that embed their faces (Arial/Times subsets, Tahoma, Arial Narrow, Calibri) reuse
  the exact files recovered by ``tools/extract.py``, so the rendered glyphs are the reference
  glyphs.
* Reports that only *name* Arial or Times New Roman embed nothing. MuPDF rasterises those
  with its built-in base-14 faces, so the same buffers are exported here and used by the
  templates. That keeps the comparison a measurement of layout rather than of two different
  font substitutions. Production must install licensed Arial/Times; see docs/03-fonts.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from tools.common import ROOT

SHARED_FONT_DIR = ROOT / "templates" / "_shared" / "fonts"

BASE14_EXPORTS = {
    "report-sans-regular.otf": ("helv", "Report Sans", 400, "normal"),
    "report-sans-bold.otf": ("hebo", "Report Sans", 700, "normal"),
    "report-sans-italic.otf": ("heit", "Report Sans", 400, "italic"),
    "report-sans-bold-italic.otf": ("hebi", "Report Sans", 700, "italic"),
    "report-serif-regular.otf": ("tiro", "Report Serif", 400, "normal"),
    "report-serif-bold.otf": ("tibo", "Report Serif", 700, "normal"),
    "report-mono-regular.otf": ("cour", "Report Mono", 400, "normal"),
}

# PDF base font name -> (css family, weight, style, base-14 code, licensed system file)
#
# A report that names Arial without embedding it still carries Arial's advance widths in the
# PDF, so the text must be laid out with Arial metrics or long strings drift. The CSS stack
# therefore asks for the licensed face first and falls back to the exported base-14 buffer,
# which is also what MuPDF uses when rasterising the reference.
SYSTEM_FONTS = {
    "arial": Path("/usr/share/fonts/msttcore/arial.ttf"),
    "arial-bold": Path("/usr/share/fonts/msttcore/arialbd.ttf"),
    "arial-italic": Path("/usr/share/fonts/msttcore/ariali.ttf"),
    "arial-bold-italic": Path("/usr/share/fonts/msttcore/arialbi.ttf"),
    "times": Path("/usr/share/fonts/msttcore/times.ttf"),
    "times-bold": Path("/usr/share/fonts/msttcore/timesbd.ttf"),
    "times-italic": Path("/usr/share/fonts/msttcore/timesi.ttf"),
}

BASE14_MAP = {
    "ArialMT": ("Arial, 'Report Sans'", 400, "normal", "helv", "arial"),
    "Arial-BoldMT": ("Arial, 'Report Sans'", 700, "normal", "hebo", "arial-bold"),
    "Arial-ItalicMT": ("Arial, 'Report Sans'", 400, "italic", "heit", "arial-italic"),
    "Arial-BoldItalicMT": ("Arial, 'Report Sans'", 700, "italic", "hebi", "arial-bold-italic"),
    "Helvetica": ("Arial, 'Report Sans'", 400, "normal", "helv", "arial"),
    "Helvetica-Bold": ("Arial, 'Report Sans'", 700, "normal", "hebo", "arial-bold"),
    "TimesNewRomanPSMT": ("'Times New Roman', 'Report Serif'", 400, "normal", "tiro", "times"),
    "TimesNewRomanPS-BoldMT": (
        "'Times New Roman', 'Report Serif'",
        700,
        "normal",
        "tibo",
        "times-bold",
    ),
    "TimesNewRomanPS-ItalicMT": (
        "'Times New Roman', 'Report Serif'",
        400,
        "italic",
        "tiro",
        "times-italic",
    ),
    "CourierNewPSMT": ("'Report Mono'", 400, "normal", "cour", None),
}


@dataclass(frozen=True, slots=True)
class FaceMetrics:
    family: str
    weight: int
    style: str
    ascender: float
    descender: float

    @property
    def baseline_factor(self) -> float:
        """Baseline position inside a ``line-height: 1`` line box, in em."""
        return (1.0 + self.ascender - abs(self.descender)) / 2.0


def sanitise(name: str) -> str:
    stripped = re.sub(r"^[A-Z]{6}\+", "", name)
    return re.sub(r"[^A-Za-z0-9]+", "-", stripped).strip("-")


def export_base14() -> list[Path]:
    """Write the base-14 faces MuPDF uses into the shared asset directory."""
    SHARED_FONT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, (code, _family, _weight, _style) in BASE14_EXPORTS.items():
        try:
            font = pymupdf.Font(code)
        except (RuntimeError, ValueError):
            # Not every base-14 alias exists in every MuPDF build; a missing one is not fatal.
            continue
        path = SHARED_FONT_DIR / filename
        path.write_bytes(font.buffer)
        written.append(path)
    (SHARED_FONT_DIR / "PROVENANCE.md").write_text(
        "# Shared font assets\n\n"
        "`report-*.otf` are the base-14 faces bundled with the pinned PyMuPDF/MuPDF build, "
        "exported verbatim by `tools/fonts.py`. MuPDF rasterises the reference PDFs with these "
        "faces whenever a report names Arial or Times New Roman without embedding it, so the "
        "templates use the same buffers and the fidelity comparison measures layout rather than "
        "two unrelated font substitutions.\n\n"
        "They are URW++ derived Helvetica/Times clones as redistributed by MuPDF. Regenerate with "
        "`make fonts`. Production rendering should install licensed Arial and Times New Roman and "
        "map `Report Sans` / `Report Serif` onto them; the measured effect is recorded in "
        "`docs/03-fonts.md`.\n",
        encoding="utf-8",
    )
    return written


def base14_metrics(
    code: str, family: str, weight: int, style: str, system_key: str | None = None
) -> FaceMetrics:
    """Metrics come from the licensed face when it is installed, else the base-14 buffer."""
    path = SYSTEM_FONTS.get(system_key or "")
    if path is not None and path.exists():
        font = pymupdf.Font(fontfile=str(path))
    else:
        font = pymupdf.Font(code)
    return FaceMetrics(family, weight, style, font.ascender, font.descender)


def licensed_faces_present() -> dict[str, bool]:
    return {name: path.exists() for name, path in SYSTEM_FONTS.items()}


def embedded_metrics(path: Path, family: str, weight: int, style: str) -> FaceMetrics:
    font = pymupdf.Font(fontfile=str(path))
    return FaceMetrics(family, weight, style, font.ascender, font.descender)


def main() -> None:
    written = export_base14()
    for path in written:
        font = pymupdf.Font(fontfile=str(path))
        print(f"{path.relative_to(ROOT)}  {font.name!r} {len(path.read_bytes())}B")


if __name__ == "__main__":
    main()
