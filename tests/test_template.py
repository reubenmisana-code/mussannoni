from pathlib import Path

from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "secondary" / "school-results" / "template.html"


def test_template_is_data_driven_and_parses() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    Environment(undefined=StrictUndefined).parse(source)
    forbidden_samples = (
        "S0333",
        "MWANZA SECONDARY SCHOOL",
        "ADELINA MARTINE CHARLES",
        "S0333-0001",
    )
    assert not any(sample in source for sample in forbidden_samples)
    assert "{% for page in pages %}" in source
    assert "{{ span.text }}" in source
