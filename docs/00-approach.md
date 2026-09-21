# Conversion approach

Reports are converted sequentially in the README manifest order. Each vertical slice fetches an immutable PDF, records its hash, extracts machine-measured text/vector/font evidence and 300-dpi rasters, renders through Chromium, and retains metrics and visual diffs.

The first slice uses a measured positioned display list to prove that the extraction, rendering, and comparison pipeline can preserve the reference geometry. It is deliberately marked provisional until the external `backend-sis` canonical semantic binding contract is available. Sample values live only in `fixture.json`; the template contains loops and slots only.
