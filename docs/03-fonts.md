# Fonts: what is embedded, what is substituted

Measured across all 46 reports by `tools/extract.py`:

| Face | Embedded in the PDF? | What the templates use |
|------|----------------------|------------------------|
| `CIDFont+F1`…`F5` (Arial and Times subsets) | yes | the extracted file itself |
| `BCDEEE+Tahoma-Bold` | yes | the extracted file itself |
| `BCDEEE+ArialNarrow-Bold`, `BCDFEE+ArialNarrow-Bold` | yes | the extracted file itself |
| `BCDFEE+Calibri` | yes | the extracted file itself |
| `ArialMT`, `Arial-BoldMT` | **no** | `Arial`, falling back to `Report Sans` |
| `TimesNewRomanPS-BoldMT` | **no** | `Times New Roman`, falling back to `Report Serif` |

## Embedded faces are reused verbatim

Where a report embeds its face, `tools/scaffold.py` copies the file recovered from the PDF into
the report's `fonts/` directory and declares it with `@font-face`. The rendered glyphs are then
the reference glyphs, and no substitution question arises. Each `@font-face` declares the real
weight and style so the browser never synthesises a bold or an oblique on top of a face that
already is one.

Those files are subsets extracted from the source PDFs for verification. Confirm redistribution
rights before promoting any of them into a production asset bundle.

## Non-embedded Arial and Times

Two thirds of the reports name Arial or Times New Roman and embed nothing. Two consequences:

1. **Layout needs the real metrics.** The PDF still carries Arial's advance widths, so text laid
   out with different advances drifts as a string gets longer. The CSS stack therefore asks for
   the licensed face first. With Arial installed, drift on the secondary school report fell to
   0.76 pt; before that it was several points on long strings.
2. **The reference has no fixed appearance.** What a reader sees depends on the renderer's font
   stack. `tools/compare.py` rasterises both sides with poppler so both resolve to the same
   installed faces.

`Report Sans` and `Report Serif` are the fallback: the base-14 faces bundled with the pinned
MuPDF build (URW++ derived Nimbus Sans and Nimbus Roman), exported verbatim by
`tools/fonts.py` into `templates/_shared/fonts/` with their provenance recorded. They keep the
templates renderable on a machine without licensed fonts, and they are what MuPDF itself uses
when it rasterises these PDFs.

**Production and verification both need licensed Arial and Times New Roman installed.** Without
them the render falls back to Nimbus: the metrics are compatible, so the layout holds, but the
glyph outlines differ from what the reference viewer shows, and the pixel metrics will be worse.
No substitution is silent - the stack is visible in every generated `report.css`.
