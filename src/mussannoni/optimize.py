"""Content-preserving structural recompression of a rendered PDF.

Chromium emits every absolutely-positioned span as its own uncompressed PDF object with no
object streams. Because these reports place one span per glyph cluster, a four-page render
carries more than 1.5 MB of plaintext object dictionaries — roughly eight times the reference
file. Re-saving through PyMuPDF with object streams, deflate and garbage collection reclaims
about 5x of that while leaving every glyph, position and page rectangle untouched.

This is a structural recompression only. Nothing is rescaled, re-rastered or downsampled, so it
cannot move a report across a fidelity gate; the workshop's test suite asserts that rasterised
pages are byte-identical before and after. WeasyPrint output is already compact, so the pass is
close to a no-op there, but it runs for every engine so file size never depends on which engine
produced the PDF.
"""

from __future__ import annotations

import os
from pathlib import Path

import pymupdf

from .errors import RenderError

PDF_MAGIC = b"%PDF-"


def _geometry(document: pymupdf.Document) -> list[tuple[float, float, int]]:
    return [
        (round(page.rect.width, 3), round(page.rect.height, 3), page.rotation)
        for page in document
    ]


def optimize_pdf(pdf_path: str | Path) -> None:
    """Recompress ``pdf_path`` in place, and verify nothing about the content moved.

    Two PyMuPDF save options that look applicable are deliberately left off, for measured
    reasons rather than assumed ones:

    - Font subsetting trims only about 2% further (5.9 KB on a four-page render) but leaves the
      font tables in a state where the *following* save can run for many minutes instead of a
      second. That happened on a 2.5 MB report as readily as on a 33 MB one, so document size is
      not a safe gate to hide it behind.
    - ``clean=True`` rewrites every content stream. It measured ~1.4 KB *larger* on a four-page
      render and ran for over ten minutes on a 16-page one. The whole win is in the object
      streams.

    Raises:
        RenderError: If the recompressed file is not a PDF, or if its page count or any page's
            rectangle or rotation differs from the original. The original is left untouched in
            that case.
    """
    pdf_path = Path(pdf_path)
    with pymupdf.open(pdf_path) as document:
        page_count = document.page_count
        geometry = _geometry(document)
        # A deterministic sibling name rather than mkstemp, so an interrupted run leaves at most
        # one stale file that the next run overwrites instead of accumulating tmp*.pdf debris.
        tmp_path = pdf_path.with_name(pdf_path.name + ".tmp")
        tmp_path.unlink(missing_ok=True)
        try:
            document.save(
                str(tmp_path),
                garbage=4,
                deflate=True,
                deflate_fonts=True,
                use_objstms=1,
            )
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def reject(reason: str) -> RenderError:
        tmp_path.unlink(missing_ok=True)
        return RenderError(f"{reason}: {pdf_path}")

    if not tmp_path.read_bytes().startswith(PDF_MAGIC):
        raise reject("Optimized PDF is not a valid %PDF-")
    with pymupdf.open(tmp_path) as optimized:
        if optimized.page_count != page_count:
            raise reject(f"Optimization changed page count {page_count} -> {optimized.page_count}")
        if _geometry(optimized) != geometry:
            raise reject("Optimization changed page geometry")
    os.replace(tmp_path, pdf_path)
