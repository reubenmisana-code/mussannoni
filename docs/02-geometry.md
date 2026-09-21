# How the grid is derived

Nothing in this pipeline is eyeballed. `tools/extract.py` records every text span and every
painted path with PyMuPDF; `tools/grid.py` turns that into a table.

## Edges

Candidate column edges are the x positions of every background region plus the centre of every
vertical gridline. Row edges are the same in y. Both are clustered with a 1.6 pt tolerance.

The tolerance is not arbitrary: an emphasised gridline is drawn as two 0.48 pt hairlines
separated by a 0.48 pt gap, so its two rectangles sit 0.96 pt apart and must collapse to one
boundary. Measured on the secondary school report, the pair centres are 0.96 pt apart and the
resulting row pitch is a consistent 12.72 pt.

## Cells, spans and merges

For each row, adjacent column slots are joined into one cell unless a vertical gridline covers
that boundary or the background fill changes across it. The run length becomes `colspan`.
Stacked empty slots that share a fill with no gridline between them collapse into `rowspan`.

Vertical merges stop at the header band. HTML row groups clip a `rowspan` at the
`thead`/`tbody` boundary, so a merge that crosses it silently shifts every body row one column
to the left - which is exactly what happened before the boundary was respected.

## Text

A span belongs to the smallest cell whose box contains its baseline origin. Per cell the
measured left gap, right gap and baseline offset are recorded, which yields the cell's
alignment (`left`, `right` or `centre`) for `bindings.yaml`, and the exact offset used to place
the text.

Runs sharing a baseline form one line. Where two runs on a line are separated by more than
0.75 pt of space, an explicit spacer of the measured width is emitted, so a gap inside a merged
cell survives.

## Header detection

The header band is the rows up to and including the first row carrying at least 60% of the
busiest row's text cells, with a floor of three cells. That band becomes `<thead>` and repeats
per page in the same way the reference repeats it.
