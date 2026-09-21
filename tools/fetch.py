from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import pymupdf as fitz

from tools.common import MANIFEST_PATH, find_report, reference_path, set_status, write_json

BASE_URL = "https://sars.ac.tz"


def fetch(level: str, report_key: str, *, force: bool = False) -> Path:
    report = find_report(level, report_key)
    destination = reference_path(report)
    if destination.exists() and not force:
        raise FileExistsError(
            f"Reference already exists; refusing to replace immutable input: {destination}"
        )

    object_key = report["object_key"]
    url = f"{BASE_URL}/serve-pdf?file={quote(object_key, safe='')}"
    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        response = client.get(url)
        response.raise_for_status()
    content = response.content
    if response.headers.get("content-type", "").split(";", 1)[0] != "application/pdf":
        raise ValueError(f"Expected application/pdf, got {response.headers.get('content-type')!r}")
    if not content.startswith(b"%PDF-"):
        raise ValueError("Downloaded content does not have a PDF signature")

    with fitz.open(stream=content, filetype="pdf") as document:
        page_count = document.page_count
        pages = [
            {
                "number": page.number + 1,
                "width_pt": page.rect.width,
                "height_pt": page.rect.height,
                "rotation": page.rotation,
            }
            for page in document
        ]

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".pdf.tmp")
    temporary.write_bytes(content)
    temporary.replace(destination)

    manifest = {"schema_version": 1, "files": {}}
    if MANIFEST_PATH.exists():
        import json

        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    relative = destination.relative_to(MANIFEST_PATH.parent.parent).as_posix()
    manifest.setdefault("files", {})[relative] = {
        "level": level,
        "report_key": report_key,
        "sample_unit": report["sample_unit"],
        "source_page": report["source_url"],
        "object_key": object_key,
        "resolved_url": url,
        "sha256": hashlib.sha256(content).hexdigest(),
        "byte_size": len(content),
        "page_count": page_count,
        "pages": pages,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    write_json(MANIFEST_PATH, manifest)
    set_status(level, report_key, "fetched")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch an immutable SARS reference PDF")
    parser.add_argument("level", choices=("secondary", "primary"))
    parser.add_argument("report_key")
    parser.add_argument(
        "--force", action="store_true", help="replace an existing reference explicitly"
    )
    args = parser.parse_args()
    print(fetch(args.level, args.report_key, force=args.force))


if __name__ == "__main__":
    main()
