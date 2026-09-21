import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_done_reports_meet_every_fidelity_gate() -> None:
    catalog = yaml.safe_load((ROOT / "catalog" / "reports.yaml").read_text())
    for report in catalog["reports"]:
        if report["status"] != "done":
            continue
        identity = report["report_key"].replace("_", "-")
        result_path = ROOT / "output" / report["level"] / identity / "report.json"
        assert result_path.exists(), f"done report has no fidelity evidence: {report}"
        result = json.loads(result_path.read_text())
        assert result["passes"] is True
        assert result["page_count_equal"] is True
        assert all(page["passes"] for page in result["pages"])
