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

REQUIRED_BINARIES = ("pdftoppm", "agent-browser")


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


def main() -> int:
    argparse.ArgumentParser(description="Check the measurement environment").parse_args()
    ok = True

    print("binaries")
    for name, present, detail in binary_report():
        print(f"  [{'ok' if present else 'XX'}] {name:<16} {detail}")
        ok = ok and present

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
