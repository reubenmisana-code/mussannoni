"""Report whether this machine can produce trustworthy fidelity measurements.

The metrics depend on two things outside Python: the poppler rasteriser, and the licensed
Arial and Times New Roman faces most reports name without embedding. If either is missing the
pipeline still runs, but the numbers mean something different, so it is worth saying so plainly
rather than letting a silent fallback move the results.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess

from tools.fonts import SYSTEM_FONTS

# pdftoppm is the comparison rasteriser and is required regardless of rendering engine.
REQUIRED_BINARIES = ("pdftoppm",)


def font_report() -> list[tuple[str, bool, str]]:
    rows = []
    for name, path in sorted(SYSTEM_FONTS.items()):
        present = path.exists()
        detail = str(path) if present else "missing - renders will fall back to Report Sans/Serif"
        rows.append((name, present, detail))
    return rows


def binary_report() -> list[tuple[str, bool, str]]:
    rows = []
    for binary in REQUIRED_BINARIES:
        location = shutil.which(binary)
        if location and binary == "pdftoppm":
            version = subprocess.run(
                [binary, "-v"], capture_output=True, text=True, check=False
            ).stderr.splitlines()
            detail = version[0] if version else location
        else:
            detail = location or "missing"
        rows.append((binary, location is not None, detail))
    return rows


def engine_report() -> list[tuple[str, bool, str]]:
    """Report each rendering engine's availability without requiring both.

    A machine only needs whichever engine it renders with. ``chromium`` needs the
    ``agent-browser`` CLI on PATH; ``weasyprint`` needs its library importable.
    """
    rows: list[tuple[str, bool, str]] = []

    chromium = shutil.which("agent-browser")
    rows.append(
        (
            "chromium",
            chromium is not None,
            chromium or "agent-browser missing - install to use the chromium engine",
        )
    )

    try:
        import weasyprint

        weasy = (True, f"weasyprint {getattr(weasyprint, '__version__', '')}".strip())
    except Exception as error:  # noqa: BLE001 - any import failure means it is unavailable
        weasy = (False, f"import failed ({type(error).__name__}) - install to use weasyprint")
    rows.append(("weasyprint", weasy[0], weasy[1]))
    return rows


def main() -> int:
    argparse.ArgumentParser(description="Check the measurement environment").parse_args()
    ok = True

    print("binaries")
    for name, present, detail in binary_report():
        print(f"  [{'ok' if present else 'XX'}] {name:<16} {detail}")
        ok = ok and present

    # Engines are reported for information only: at least one must be usable, but a machine that
    # has just one engine is still fully functional, so a single missing engine is not a failure.
    print("rendering engines")
    engines = engine_report()
    for name, present, detail in engines:
        print(f"  [{'ok' if present else '--'}] {name:<16} {detail}")
    ok = ok and any(present for _, present, _ in engines)

    print("licensed faces")
    for name, present, detail in font_report():
        print(f"  [{'ok' if present else 'XX'}] {name:<16} {detail}")
        ok = ok and present

    if ok:
        print("\nenvironment ready: measurements are comparable to the committed results")
        return 0
    print("\nenvironment incomplete - run `make setup`.")
    print("Without the licensed faces the layout still holds, because the fallback faces are")
    print("metric-compatible, but glyph outlines differ and the pixel metrics will be worse.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
