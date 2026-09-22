# Credits and acknowledgements

## Authors

**Reuben Misana** and **Kiyabo Nhende** created this project.

- **Kiyabo Nhende** — maintainer and author of the code. Maintainer and developer of
  [shuleyetu.co.tz](https://shuleyetu.co.tz).
  <kiyaboapp@gmail.com> · [@kiyaboapp](https://github.com/kiyaboapp)
- **Reuben Misana** — co-creator, and a student of Kiyabo Nhende.
  [@reubenmisana-code](https://github.com/reubenmisana-code)

## Inspiration

The report designs this project reproduces are the work of **Mussa Nnoni**, who maintains
[sars.ac.tz](https://sars.ac.tz) — the School Academic Reporting System used to publish
examination results across Tanzanian regions and councils. Every layout, column arrangement,
colour and typographic choice measured in this repository originates in his published PDFs.
This project exists because those reports set a standard worth reproducing exactly; it is a
tribute to that work, not a replacement for it, and it claims no affiliation with or
endorsement by SARS.

The name `mussannoni` is an acknowledgement of that debt.

### Wasiliana Nasi — contact SARS

Kwa maswali, maoni au usaidizi kuhusu ripoti zenyewe, wasiliana na SARS kupitia njia
zifuatazo. *(For questions, feedback or support about the reports themselves, contact SARS
through the following channels.)*

**Anwani** *(Address)*
Ofisi ya Elimu Mkoa
S.L.P. 119
Mwanza, Tanzania

**Simu** *(Phone)*
+255 763 074 657

**Barua Pepe** *(Email)*
<info@sars.ac.tz>
<support@sars.ac.tz>
<nnonimusa85@gmail.com>

Please direct questions about *this package* to its own
[issue tracker](https://github.com/reubenmisana-code/mussannoni/issues) rather than to SARS.

## Third-party assets

| Asset | Origin | Licence |
| --- | --- | --- |
| `templates/_shared/fonts/report-*.otf` | Base-14 faces exported verbatim from the pinned PyMuPDF/MuPDF build by `tools/fonts.py`; URW++ derived Helvetica/Times clones as redistributed by MuPDF | See MuPDF / URW++ terms; details in `templates/_shared/fonts/PROVENANCE.md` |
| `templates/_shared/fonts/liberation-*.ttf` | The Liberation fonts | `templates/_shared/fonts/LIBERATION-LICENSE.txt` |
| `templates/{level}/{report}/fonts/*.ttf` | Subsets recovered from the reference PDFs by `tools/extract.py`, so that a report which embeds a face renders with that face | **Licence of the original foundry.** Includes Microsoft (Tahoma, Calibri) and Monotype (Arial Narrow) derived subsets. See the caveat below. |
| Arial, Times New Roman | Never bundled. Installed on the rendering host by `make setup`, and named first in each font stack with `Report Sans` / `Report Serif` as the fallback | Microsoft EULA — the operator's responsibility |

### Caveat on the recovered font subsets

The per-report `fonts/` directories hold glyph subsets lifted out of the reference PDFs. They
are there so the fidelity comparison measures *layout* rather than two unrelated font
substitutions, and shipping them is what lets a rendered report keep the reference's glyphs.

Several of them derive from proprietary foundry faces. Embedding a subset inside a PDF is
ordinarily permitted by those licences; **redistributing the extracted font files as part of a
software package is a different act and is not covered by this project's MIT licence.** Resolve
this before publishing a wheel to a public index — either by confirming the terms for each
face, or by building without those directories and letting the affected text classes fall back
to the bundled `Report Sans` / `Report Serif`. See `docs/05-packaging.md`.

## Reference data

`corpus/` holds reference PDFs downloaded from sars.ac.tz for measurement only. They are not
redistributed: they are excluded from both the wheel and the sdist, and `corpus/` is treated as
read-only throughout the workshop.
