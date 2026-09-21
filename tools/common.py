from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog" / "reports.yaml"
MANIFEST_PATH = ROOT / "corpus" / "MANIFEST.json"


def load_catalog() -> dict[str, Any]:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))


def find_report(level: str, report_key: str) -> dict[str, Any]:
    matches = [
        item
        for item in load_catalog()["reports"]
        if item["level"] == level and item["report_key"] == report_key
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one catalog entry for {level}/{report_key}; found {len(matches)}"
        )
    return matches[0]


def artifact_name(report_key: str) -> str:
    return report_key.replace("_", "-")


def reference_path(report: dict[str, Any]) -> Path:
    return ROOT / "corpus" / report["level"] / f"{artifact_name(report['report_key'])}.pdf"


def extraction_dir(report: dict[str, Any]) -> Path:
    return ROOT / "extract" / report["level"] / artifact_name(report["report_key"])


def output_dir(report: dict[str, Any]) -> Path:
    return ROOT / "output" / report["level"] / artifact_name(report["report_key"])


def template_dir(report: dict[str, Any]) -> Path:
    return ROOT / "templates" / report["level"] / artifact_name(report["report_key"])


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def set_status(level: str, report_key: str, status: str) -> None:
    catalog = load_catalog()
    for item in catalog["reports"]:
        if item["level"] == level and item["report_key"] == report_key:
            item["status"] = status
            break
    else:
        raise ValueError(f"Unknown report: {level}/{report_key}")
    CATALOG_PATH.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
