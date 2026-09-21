# Font evidence and substitutions

The source uses Arial, Arial Bold, Times New Roman Bold, an embedded subset of Tahoma Bold, and an embedded subset of Arial Narrow Bold.

For local proof rendering, the two embedded subsets are loaded directly from extraction evidence. Arial and Times New Roman are not embedded in the source PDF, so Liberation Sans and Liberation Serif 2.1.5 are used as metrically compatible open substitutes. The Liberation license is committed beside the font files. Exact measured drift is recorded by `tools/compare.py` and this report cannot be marked `done` if drift exceeds the README gate.

The embedded evidence fonts must not be promoted to a production asset bundle until redistribution rights are confirmed.
