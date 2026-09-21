"""Derive the 46-report catalog from the two live SARS listing pages.

The listing pages publish 330 links for 46 distinct layouts. This module applies the
deduplication rules recorded in the README and fails loudly when the live pages stop
matching the published link budget, instead of silently producing a short catalog.
"""

from __future__ import annotations

import argparse
import re
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urlparse

import httpx
import yaml
from lxml import html as lxml_html

from tools.common import CATALOG_PATH, ROOT

SOURCES = {
    "secondary": "https://sars.ac.tz/results/exam/form-two-mock-result/2026/mwanza/mwanza-cc-1787231849",
    "primary": "https://sars.ac.tz/results/exam/matokeo-darasa-la-iv-mock-mkoa/2026/mwanza/mwanza-cc-1787231849",
}
BLOCK_MARKERS = ("School List", "District Summaries", "Regional Summaries")
PUBLISHED_LINK_BUDGET = {
    "secondary": {"school": 64, "council": 7, "region": 48, "total": 119},
    "primary": {"school": 170, "council": 13, "region": 28, "total": 211},
}
SUBJECT_SAMPLE = "MATHEMATICS"


class Link(NamedTuple):
    level: str
    block: str
    display_name: str
    object_key: str
    url: str
    position: int


class Spec(NamedTuple):
    ordinal: int
    level: str
    report_key: str
    scope: str
    title: str
    match: str


def normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().upper()


SPECS: tuple[Spec, ...] = (
    Spec(1, "secondary", "school_results", "school", "SCHOOL RESULTS", "S0333"),
    Spec(
        2,
        "secondary",
        "council_subjects_rank",
        "council",
        "SUBJECTS RANK",
        "MWANZA CC SUBJECTS RANK",
    ),
    Spec(
        3, "secondary", "council_schools_rank", "council", "SCHOOLS RANK", "MWANZA CC SCHOOLS RANK"
    ),
    Spec(4, "secondary", "council_wards_rank", "council", "WARDS RANK", "MWANZA CC WARDS RANK"),
    Spec(
        5,
        "secondary",
        "council_top_schools",
        "council",
        "10 BEST SCHOOLS",
        "MWANZA CC 10 BEST SCHOOLS",
    ),
    Spec(
        6,
        "secondary",
        "council_best_students",
        "council",
        "10 BEST STUDENTS",
        "MWANZA CC 10 BEST STUDENTS",
    ),
    Spec(
        7,
        "secondary",
        "council_best_students_subjectwise",
        "council",
        "10 BEST STUDENTS SUBJECTWISE",
        "MWANZA CC 10 BEST STUDENTS SUBJECTWISE",
    ),
    Spec(
        8,
        "secondary",
        "council_schools_rank_subjectwise",
        "council",
        "SCHOOLS RANK SUBJECTWISE",
        "MWANZA CC SCHOOLS RANK SUBJECTWISE",
    ),
    Spec(
        9,
        "secondary",
        "subject_schools_rank",
        "subject",
        "SCHOOL RANK-MATHEMATICS",
        "MWANZA SCHOOL RANK-MATHEMATICS",
    ),
    Spec(
        10,
        "secondary",
        "region_schools_rank_overall",
        "region",
        "SCHOOLS RANK OVERALL",
        "MWANZA SCHOOLS RANK OVERALL",
    ),
    Spec(
        11,
        "secondary",
        "region_schools_rank_government",
        "region",
        "SCHOOLS RANK FOR GOVERNMENTS",
        "MWANZA SCHOOLS RANK FOR GOVERNMENTS",
    ),
    Spec(
        12,
        "secondary",
        "region_schools_rank_private",
        "region",
        "SCHOOL RANK FOR PRIVATES",
        "MWANZA SCHOOL RANK FOR PRIVATES",
    ),
    Spec(
        13, "secondary", "region_top_schools", "region", "TOP 10 SCHOOLS", "MWANZA TOP 10 SCHOOLS"
    ),
    Spec(
        14,
        "secondary",
        "region_best_students_overall",
        "region",
        "BEST STUDENTS-OVERALL",
        "MWANZA BEST STUDENTS-OVERALL",
    ),
    Spec(
        15,
        "secondary",
        "region_best_students_subjectwise",
        "region",
        "BEST STUDENTS-SUBJECTWISE",
        "MWANZA BEST STUDENTS-SUBJECTWISE",
    ),
    Spec(
        16,
        "secondary",
        "region_council_performance",
        "region",
        "F2 DISTRICT PERFORMANCE",
        "MWANZA F2 DISTRICT PERFORMANCE",
    ),
    Spec(
        17,
        "secondary",
        "region_subjects_performance",
        "region",
        "OVERALL SUBJECTS PERFORMANCE",
        "MWANZA OVERALL SUBJECTS PERFORMANCE",
    ),
    Spec(
        18,
        "secondary",
        "region_mobility",
        "region",
        "F2 MOCK MOBILITY 2026",
        "MWANZA F2 MOCK MOBILITY 2026",
    ),
    Spec(19, "primary", "school_results", "school", "SCHOOL RESULTS", "PS1304014"),
    Spec(
        20,
        "primary",
        "council_kata_rank_alama",
        "council",
        "KATA RANK ALAMA",
        "MWANZA CC KATA RANK ALAMA",
    ),
    Spec(
        21,
        "primary",
        "council_kata_rank_grading",
        "council",
        "KATA RANK GRADING",
        "MWANZA CC KATA RANK GRADING",
    ),
    Spec(
        22,
        "primary",
        "council_school_rank_binafsi",
        "council",
        "SCHOOL RANK BINAFSI",
        "MWANZA CC SCHOOL RANK BINAFSI",
    ),
    Spec(
        23,
        "primary",
        "council_school_rank_serikali",
        "council",
        "SCHOOL RANK SERIKALI",
        "MWANZA CC SCHOOL RANK SERIKALI",
    ),
    Spec(
        24,
        "primary",
        "council_school_rank_in_grade",
        "council",
        "SCHOOL RANK IN GRADE",
        "MWANZA CC SCHOOL RANK IN GRADE",
    ),
    Spec(
        25,
        "primary",
        "council_school_rank_ufaulu_alama",
        "council",
        "SCHOOL RANK UFAULU ALAMA",
        "MWANZA CC SCHOOL RANK UFAULU ALAMA",
    ),
    Spec(
        26,
        "primary",
        "council_best_students",
        "council",
        "10 BEST STUDENTS",
        "MWANZA CC 10 BEST STUDENTS",
    ),
    Spec(
        27,
        "primary",
        "council_top_schools_alama",
        "council",
        "10 BEST SCHOOLS ALAMA",
        "MWANZA CC 10 BEST SCHOOLS ALAMA",
    ),
    Spec(
        28,
        "primary",
        "council_top_schools_grading",
        "council",
        "10 BEST SCHOOLS GRADING",
        "MWANZA CC 10 BEST SCHOOLS GRADING",
    ),
    Spec(
        29,
        "primary",
        "council_top_schools_kimasomo_overall",
        "council",
        "10 BEST SCHOOLS KIMASOMO OVERALL",
        "MWANZA CC 10 BEST SCHOOLS KIMASOMO OVERALL",
    ),
    Spec(
        30,
        "primary",
        "council_top_schools_kimasomo_serikali",
        "council",
        "10 BEST SCHOOLS KIMASOMO SERIKALI",
        "MWANZA CC 10 BEST SCHOOLS KIMASOMO SERIKALI",
    ),
    Spec(
        31,
        "primary",
        "council_subject_summary",
        "council",
        "SUBJECT SUMMARY",
        "MWANZA CC SUBJECT SUMMARY",
    ),
    Spec(
        32,
        "primary",
        "council_ufaulu_wa_masomo",
        "council",
        "UFAULU WA MASOMO",
        "MWANZA CC UFAULU WA MASOMO",
    ),
    Spec(
        33,
        "primary",
        "region_kata_serikali",
        "region",
        "MKOA KATA SHULE ZA SERIKALI STD4 2026",
        "MKOA KATA SHULE ZA SERIKALI STD4 2026",
    ),
    Spec(
        34,
        "primary",
        "region_kata_binafsi",
        "region",
        "MKOA KATA SHULE BINAFSI STD4 2026",
        "MKOA KATA SHULE BINAFSI STD4 2026",
    ),
    Spec(
        35, "primary", "region_kata_jumla", "region", "KATA STD4 JUMLA 2026", "KATA STD4 JUMLA 2026"
    ),
    Spec(
        36,
        "primary",
        "region_shule_bora_jumla",
        "region",
        "MKOA SHULE BORA STD4 JUMLA 2026",
        "MKOA SHULE BORA STD4 JUMLA 2026",
    ),
    Spec(
        37,
        "primary",
        "region_shule_bora_masomo_serikali",
        "region",
        "MKOA SHULE BORA MASOMO SERIKALI STD4 2026",
        "MKOA SHULE BORA MASOMO SERIKALI STD4 2026",
    ),
    Spec(
        38,
        "primary",
        "region_shule_bora_masomo_jumla",
        "region",
        "MKOA SHULE BORA MASOMO STD4 JUMLA 2026",
        "MKOA SHULE BORA MASOMO STD4 JUMLA 2026",
    ),
    Spec(
        39,
        "primary",
        "region_ufaulu_masomo",
        "region",
        "MKOA UFAULU MASOMO STD4 2026",
        "MKOA UFAULU MASOMO STD4 2026",
    ),
    Spec(
        40,
        "primary",
        "region_ufaulu_masomo_jumla",
        "region",
        "MKOA UFAULU MASOMO STD4 JUMLA 2026",
        "MKOA UFAULU MASOMO STD4 JUMLA 2026",
    ),
    Spec(
        41,
        "primary",
        "region_wanafunzi_bora",
        "region",
        "MKOA WANAFUNZI BORA STD4 2026",
        "MKOA WANAFUNZI BORA STD4 2026",
    ),
    Spec(
        42,
        "primary",
        "region_shule_serikali",
        "region",
        "SHULE SERIKALI STD4 2026",
        "SHULE SERIKALI STD4 2026",
    ),
    Spec(
        43,
        "primary",
        "region_shule_binafsi",
        "region",
        "SHULE BINAFSI STD4 2026",
        "SHULE BINAFSI STD4 2026",
    ),
    Spec(
        44,
        "primary",
        "region_shule_nafasi_jumla",
        "region",
        "SHULE NAFASI STD4 JUMLA 2026",
        "SHULE NAFASI STD4 JUMLA 2026",
    ),
    Spec(
        45,
        "primary",
        "region_halmashauri_masomo",
        "region",
        "HALMASHAURI MASOMO STD4 2026",
        "HALMASHAURI MASOMO STD4 2026",
    ),
    Spec(
        46,
        "primary",
        "region_halmashauri_jumla",
        "region",
        "HALMASHAURI STD4 JUMLA 2026",
        "HALMASHAURI STD4 JUMLA 2026",
    ),
)


def fetch_links(level: str, url: str) -> list[Link]:
    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        response = client.get(url)
        response.raise_for_status()
    raw = response.text
    markers = {marker: raw.find(marker) for marker in BLOCK_MARKERS}
    missing = [marker for marker, index in markers.items() if index < 0]
    if missing:
        raise ValueError(f"{level}: listing page is missing blocks {missing}")

    document = lxml_html.fromstring(raw)
    links: list[Link] = []
    for anchor in document.xpath('//a[contains(@href, "view-results")]'):
        href = anchor.get("href")
        query = parse_qs(urlparse(href).query)
        object_key = query.get("file", [""])[0]
        display_name = query.get("name", [""])[0] or (anchor.text_content() or "")
        position = raw.find(href.replace("&", "&amp;"))
        if position < 0:
            position = raw.find(href)
        block = (
            "school"
            if position < markers["District Summaries"]
            else ("council" if position < markers["Regional Summaries"] else "region")
        )
        links.append(Link(level, block, display_name, object_key, href, position))

    budget = PUBLISHED_LINK_BUDGET[level]
    counted = {
        block: sum(1 for link in links if link.block == block)
        for block in ("school", "council", "region")
    }
    if len(links) != budget["total"] or any(counted[block] != budget[block] for block in counted):
        raise ValueError(
            f"{level}: published link budget changed. expected {budget}, found {counted | {'total': len(links)}}"
        )
    return links


def deduplicate(links: list[Link]) -> tuple[list[Link], list[Link]]:
    """Keep the first link for each display name; return (kept, dropped)."""
    seen: dict[str, Link] = {}
    kept: list[Link] = []
    dropped: list[Link] = []
    for link in sorted(links, key=lambda item: item.position):
        name = normalise(link.display_name)
        if name in seen:
            dropped.append(link)
            continue
        seen[name] = link
        kept.append(link)
    return kept, dropped


def resolve(spec: Spec, links: list[Link]) -> Link:
    if spec.scope == "school":
        candidates = [
            link
            for link in links
            if link.block == "school"
            and normalise(link.display_name).split("-", 1)[0].strip() == spec.match
        ]
    else:
        candidates = [
            link
            for link in links
            if link.block in {"council", "region"} and normalise(link.display_name) == spec.match
        ]
    if len(candidates) != 1:
        raise ValueError(
            f"{spec.level}/{spec.report_key}: expected exactly one link for {spec.match!r}, found {len(candidates)}"
        )
    return candidates[0]


def build() -> dict[str, Any]:
    all_links: dict[str, list[Link]] = {}
    deduplicated: dict[str, list[Link]] = {}
    dropped: dict[str, list[Link]] = {}
    for level, url in SOURCES.items():
        links = fetch_links(level, url)
        all_links[level] = links
        deduplicated[level], dropped[level] = deduplicate(links)

    existing = {}
    if CATALOG_PATH.exists():
        previous = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
        existing = {
            (item["level"], item["report_key"]): item for item in previous.get("reports", [])
        }

    reports = []
    for spec in SPECS:
        link = resolve(spec, deduplicated[spec.level])
        prior = existing.get((spec.level, spec.report_key), {})
        entry = {
            "ordinal": spec.ordinal,
            "level": spec.level,
            "report_key": spec.report_key,
            "identity": spec.report_key.replace("_", "-"),
            "scope": spec.scope,
            "title": spec.title,
            "sample_unit": re.sub(r"\s+", " ", link.display_name).strip(),
            "object_key": link.object_key,
            "source_url": link.url,
            "status": prior.get("status", "todo"),
            "aliases": prior.get("aliases", []),
        }
        reports.append(entry)

    keys = [(item["level"], item["report_key"]) for item in reports]
    if len(set(keys)) != len(keys):
        raise ValueError("catalog contains duplicate level/report_key pairs")
    if len(reports) != 46:
        raise ValueError(f"expected 46 reports, built {len(reports)}")

    catalog = {"version": 1, "sources": SOURCES, "reports": reports}
    CATALOG_PATH.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=200), encoding="utf-8"
    )
    write_dedup_evidence(all_links, deduplicated, dropped, reports)
    return catalog


def write_dedup_evidence(
    all_links: dict[str, list[Link]],
    deduplicated: dict[str, list[Link]],
    dropped: dict[str, list[Link]],
    reports: list[dict[str, Any]],
) -> None:
    lines = [
        "# Corpus deduplication evidence",
        "",
        "Generated by `tools/catalog.py` from the two live listing pages. The pages publish 330 links",
        "for 46 distinct layouts; every collapse below is mechanical, not a judgement about sample data.",
        "",
        "## Published link budget",
        "",
        "| Level | School list | District summaries | Regional summaries | Links |",
        "|-------|-------------|--------------------|--------------------|-------|",
    ]
    for level, links in all_links.items():
        counted = {
            block: sum(1 for link in links if link.block == block)
            for block in ("school", "council", "region")
        }
        lines.append(
            f"| {level.upper()} | {counted['school']} | {counted['council']} | {counted['region']} | {len(links)} |"
        )
    total = sum(len(links) for links in all_links.values())
    lines += [
        f"| **Total** | | | | **{total}** |",
        "",
        "## Rule 1 - school reports collapse to one sample per level",
        "",
    ]
    for level, links in all_links.items():
        schools = [link for link in links if link.block == "school"]
        sample = next(
            item for item in reports if item["level"] == level and item["scope"] == "school"
        )
        lines.append(
            f"- {level.upper()}: {len(schools)} school links collapse to `{sample['sample_unit']}`."
        )

    subject_reports = [
        link
        for link in deduplicated["secondary"]
        if "RANK-" in normalise(link.display_name) or "RANK HTM" in normalise(link.display_name)
    ]
    kept_subject = next(item for item in reports if item["report_key"] == "subject_schools_rank")
    lines += [
        "",
        "## Rule 2 - per-subject reports collapse to one subject",
        "",
        f"- {len(subject_reports)} distinct subject layouts are published; subject is data, not layout.",
        f"- Retained `{kept_subject['sample_unit']}` as `subject_schools_rank`; see `catalog/subjects.yaml`.",
        "",
        "## Rule 3 - republished duplicates drop the second object key",
        "",
    ]
    for level, items in dropped.items():
        lines.append(
            f"- {level.upper()}: {len(items)} links repeat an earlier display name and were dropped."
        )
        for link in items:
            label = re.sub(r"\s+", " ", link.display_name).strip()
            lines.append(f"  - `{label}` -> `{link.object_key}`")

    lines += [
        "",
        "## Rule 4 - government / private / overall variants stay separate",
        "",
        "`region_schools_rank_overall`, `region_schools_rank_government` and `region_schools_rank_private`",
        "are fetched and converted independently. They may only become aliases after their converted",
        "HTML is diffed and proven structurally identical.",
        "",
        "## Not in the corpus",
        "",
        "Zone scope reports are emitted only for exams spanning two or more regions. This single-region",
        "Mwanza corpus provides no valid zone sample, so no zone report can be converted from it.",
        "",
    ]
    (ROOT / "catalog" / "dedup.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild the 46-report catalog from the live listing pages"
    )
    parser.parse_args()
    catalog = build()
    print(f"catalog: {len(catalog['reports'])} reports -> {CATALOG_PATH}")


if __name__ == "__main__":
    main()
