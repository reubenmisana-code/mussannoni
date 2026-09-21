import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = yaml.safe_load((ROOT / "catalog" / "reports.yaml").read_text())
REPORTS = CATALOG["reports"]


def test_330_links_deduplicate_to_46_reports() -> None:
    assert len(REPORTS) == 46
    assert sum(1 for item in REPORTS if item["level"] == "secondary") == 18
    assert sum(1 for item in REPORTS if item["level"] == "primary") == 28


def test_no_key_collisions_and_stable_ordinals() -> None:
    keys = [(item["level"], item["report_key"]) for item in REPORTS]
    assert len(set(keys)) == len(keys)
    assert [item["ordinal"] for item in REPORTS] == list(range(1, 47))


def test_every_entry_carries_its_provenance() -> None:
    for item in REPORTS:
        assert item["object_key"].startswith(("results/pdfs/", "summaries/")), item
        assert item["source_url"].startswith("https://sars.ac.tz/view-results?"), item
        assert item["sample_unit"].strip()
        assert item["status"] in {"todo", "fetched", "extracted", "wip", "done", "blocked", "alias"}


def test_object_keys_are_unique() -> None:
    keys = [item["object_key"] for item in REPORTS]
    assert len(set(keys)) == len(keys)


def test_rank_variants_are_not_collapsed_before_being_diffed() -> None:
    """Government / private / overall may only become aliases after their HTML is compared."""
    variants = [
        item
        for item in REPORTS
        if item["report_key"]
        in {
            "region_schools_rank_overall",
            "region_schools_rank_government",
            "region_schools_rank_private",
        }
    ]
    assert len(variants) == 3
    assert all(item["status"] != "alias" for item in variants)
    assert len({item["object_key"] for item in variants}) == 3


def test_subject_reports_collapse_to_one_sample() -> None:
    subjects = yaml.safe_load((ROOT / "catalog" / "subjects.yaml").read_text())
    equivalents = subjects["secondary"]["equivalent_layout_subjects"]
    assert subjects["secondary"]["canonical_sample"] == "MATHEMATICS"
    assert len(equivalents) == 22
    assert len(set(equivalents)) == 22
    sample = next(item for item in REPORTS if item["report_key"] == "subject_schools_rank")
    assert "Mathematics" in sample["sample_unit"]


def test_manifest_covers_every_fetched_report() -> None:
    manifest = json.loads((ROOT / "corpus" / "MANIFEST.json").read_text())
    for item in REPORTS:
        if item["status"] == "todo":
            continue
        relative = f"corpus/{item['level']}/{item['report_key'].replace('_', '-')}.pdf"
        entry = manifest["files"][relative]
        assert len(entry["sha256"]) == 64
        assert entry["byte_size"] > 0
        assert entry["page_count"] >= 1
        assert entry["object_key"] == item["object_key"]
        assert entry["fetched_at"]
