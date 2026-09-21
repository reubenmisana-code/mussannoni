from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
import pymupdf as fitz

from tools.common import (
    MANIFEST_PATH,
    find_report,
    load_catalog,
    reference_path,
    set_status,
    write_json,
)

BASE_URL = "https://sars.ac.tz"


def read_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"schema_version": 1, "files": {}}


def fetch(level: str, report_key: str, *, force: bool = False, skip_existing: bool = False) -> Path:
    report = find_report(level, report_key)
    destination = reference_path(report)
    if destination.exists() and not force:
        if skip_existing:
            return destination
        raise FileExistsError(
            f"Reference already exists; refusing to replace immutable input: {destination}"
        )

    object_key = report["object_key"]
    url = f"{BASE_URL}/serve-pdf?file={quote(object_key, safe='')}"
    with httpx.Client(follow_redirects=True, timeout=180.0) as client:
        response = client.get(url)
        response.raise_for_status()
    content = response.content
    content_type = response.headers.get("content-type", "").split(";", 1)[0]
    if content_type != "application/pdf":
        raise ValueError(f"Expected application/pdf for {object_key}, got {content_type!r}")
    if not content.startswith(b"%PDF-"):
        raise ValueError(f"Downloaded content for {object_key} has no PDF signature")

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

    manifest = read_manifest()
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


def fetch_all(*, force: bool = False) -> list[Path]:
    paths = []
    for report in load_catalog()["reports"]:
        path = fetch(
            report["level"],
            report["report_key"],
            force=force,
            skip_existing=not force,
        )
        manifest = read_manifest()
        entry = manifest["files"][path.relative_to(MANIFEST_PATH.parent.parent).as_posix()]
        print(
            f"{report['ordinal']:>2} {report['level']:<9} {report['report_key']:<38} "
            f"{entry['page_count']:>3}p {entry['byte_size']:>9}B {path.name}"
        )
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch immutable SARS reference PDFs")
    parser.add_argument("level", nargs="?", choices=("secondary", "primary"))
    parser.add_argument("report_key", nargs="?")
    parser.add_argument("--all", action="store_true", help="fetch every catalog entry")
    parser.add_argument(
        "--force", action="store_true", help="replace an existing reference explicitly"
    )
    args = parser.parse_args()
    if args.all:
        paths = fetch_all(force=args.force)
        print(f"{len(paths)} references in corpus")
        return
    if not args.level or not args.report_key:
        parser.error("provide LEVEL and REPORT_KEY, or --all")
    print(fetch(args.level, args.report_key, force=args.force))


if __name__ == "__main__":
    main()
