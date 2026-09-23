# Shared font assets

Every face here is redistributable, and that is the point: the package ships no font derived from
a proprietary one.

| File | Family | Licence | Stands in for |
|---|---|---|---|
| `liberation-sans-regular.ttf`, `-bold`, `-italic`, `-bold-italic` | Liberation Sans | SIL OFL 1.1 | Arial |
| `liberation-serif-regular.ttf`, `-bold` | Liberation Serif | SIL OFL 1.1 | Times New Roman |
| `liberation-mono-regular.ttf` | Liberation Mono | SIL OFL 1.1 | Courier New |
| `liberation-sans-narrow-bold.ttf` | Liberation Sans Narrow | GPL v2 + font exception (`LIBERATION-NARROW-LICENSE.txt`) | Arial Narrow |
| `carlito-regular.ttf`, `carlito-bold.ttf` | Carlito | SIL OFL 1.1 (`CARLITO-LICENSE.txt`) | Calibri |

Each is **metric-compatible** with the face it stands in for, which is what lets a generated report
keep the reference's measured placement. Verified per character over each replaced subset's own
cmap on 2026-09-23: twelve of the thirteen substitutions are exact at 0.0000 pt. The Arial subsets
differ only on `U+0640` and `U+2070`–`U+2079`, none of which occurs anywhere in the 46 reports (the
corpus uses 73 distinct characters, highest `U+2019`). Tahoma is the one inexact case — it has no
metric-compatible open clone, 36 of its 39 characters differ by up to 0.7852 pt against Liberation
Sans Bold, and it backs one text class in one report.

Production rendering should still install the licensed Arial, Times New Roman, Arial Narrow and
Calibri: every text class names the real face first and one of these second, so a host that has them
uses them and only falls back here when it does not.

## What is deliberately absent

The reference PDFs embed subsets of Tahoma, Arial, Arial Narrow and Calibri, and `tools/extract.py`
lifts them out for local fidelity work. Embedding a subset in a PDF is ordinarily permitted by those
licences; redistributing the extracted files inside a software package is a different act and is not
covered by this project's MIT licence. They stay in the workshop and are never packaged —
`tools/package_resources.py::_FONT_SUBSTITUTES` is where the mapping lives, and the build fails
rather than shipping a face it has no substitute for.

Also absent are the URW-derived base-14 faces previously exported from MuPDF as `report-*.otf`.
Those carry MuPDF's own copyleft terms, which do not sit inside an MIT distribution, so the
`Report Sans` / `Report Serif` / `Report Mono` families are backed by Liberation instead.
