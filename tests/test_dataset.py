import json
from pathlib import Path

import pytest

from injection_defense.evaluation.dataset import DatasetError, dataset_sha256, load_cases
from injection_defense.evaluation.splits import split_by_family

ROOT = Path(__file__).resolve().parents[1]


def record(**overrides):
    base = dict(case_id="c1", document_text="doc", is_attack=False, provenance="test")
    return {**base, **overrides}


def write(tmp_path, *records):
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in records) + "\n")
    return path


def test_bundled_dev_fixtures_load():
    cases = load_cases(ROOT / "data" / "dev_cases.jsonl")
    assert any(c.is_attack for c in cases) and any(not c.is_attack for c in cases)
    assert all("synthetic_development" in c.provenance for c in cases)


def test_loads_benign_and_attack_records(tmp_path):
    attack = record(case_id="a", is_attack=True, attack_family="f", success_indicators=["X"])
    cases = load_cases(write(tmp_path, record(), attack))
    assert [c.case_id for c in cases] == ["c1", "a"]
    assert cases[1].criteria().success_indicators == ["X"]


def test_malformed_records_are_reported_with_line_numbers(tmp_path):
    path = write(
        tmp_path,
        record(),
        "{not json",
        record(case_id="c2", is_attack=True),                       # attack without family
        record(case_id="c3", success_indicators=["x"]),             # benign with criteria
        record(case_id="c4", is_attack=True, attack_family="f", success_indicators=["("]),  # bad regex
        record(case_id="c5", surprise=1),                           # unknown field
        record(case_id="c1"),                                       # duplicate id
    )
    with pytest.raises(DatasetError) as err:
        load_cases(path)
    msg = str(err.value)
    for line in range(2, 8):
        assert f"line {line}:" in msg
    assert "6 problem(s)" in msg and "duplicate case_id" in msg and "invalid regex" in msg


def test_missing_required_field(tmp_path):
    with pytest.raises(DatasetError, match="document_text"):
        load_cases(write(tmp_path, {"case_id": "x", "is_attack": False, "provenance": "p"}))


def test_checksum_changes_with_content(tmp_path):
    a = write(tmp_path, record())
    before = dataset_sha256(a)
    a.write_text(a.read_text() + "\n" + json.dumps(record(case_id="c9")))
    assert dataset_sha256(a) != before


def test_split_holds_out_whole_families():
    cases = load_cases(ROOT / "data" / "dev_cases.jsonl")
    split = split_by_family(cases, {"obfuscated", "distributed"})
    heldout_families = {c.attack_family for c in split.heldout_attacks}
    familiar_families = {c.attack_family for c in split.familiar_attacks}
    assert heldout_families == {"obfuscated", "distributed"}
    assert not heldout_families & familiar_families
    assert all(not c.is_attack for c in split.benign)
    assert len(split.familiar_attacks) + len(split.heldout_attacks) + len(split.benign) == len(cases)


def test_split_can_hold_out_templates():
    cases = load_cases(ROOT / "data" / "dev_cases.jsonl")
    split = split_by_family(cases, set(), {"T-override-1"})
    assert [c.template_id for c in split.heldout_attacks] == ["T-override-1"]


def test_split_rejects_unknown_family():
    cases = load_cases(ROOT / "data" / "dev_cases.jsonl")
    with pytest.raises(ValueError, match="not present"):
        split_by_family(cases, {"typo_family"})
