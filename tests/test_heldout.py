"""Guards for the held-out files: disjoint from the dev set, and frozen by checksum."""

import hashlib
from pathlib import Path

from injection_defense.evaluation.dataset import load_cases

DATA = Path(__file__).resolve().parents[1] / "data"
HELDOUT_FILES = ("heldout_attacks.jsonl", "heldout_benign.jsonl")


def _all():
    dev = load_cases(DATA / "dev_cases.jsonl")
    held = [c for name in HELDOUT_FILES for c in load_cases(DATA / name)]
    return dev, held


def test_heldout_families_and_templates_are_disjoint_from_dev():
    dev, held = _all()
    dev_attacks, held_attacks = [c for c in dev if c.is_attack], [c for c in held if c.is_attack]
    assert {c.attack_family for c in dev_attacks}.isdisjoint({c.attack_family for c in held_attacks})
    assert {c.template_id for c in dev_attacks}.isdisjoint({c.template_id for c in held_attacks})


def test_case_ids_and_documents_do_not_overlap_dev():
    dev, held = _all()
    assert {c.case_id for c in dev}.isdisjoint({c.case_id for c in held})
    assert {c.document_text for c in dev}.isdisjoint({c.document_text for c in held})


def test_heldout_files_contain_the_expected_kinds_of_cases():
    held_attacks = load_cases(DATA / "heldout_attacks.jsonl")
    held_benign = load_cases(DATA / "heldout_benign.jsonl")
    assert all(c.is_attack and c.success_indicators for c in held_attacks)
    assert all(not c.is_attack and c.expected_summary_keywords for c in held_benign)
    assert len({c.template_id for c in held_attacks}) == len(held_attacks)  # one case per template
    assert sum("Hard negative" in c.notes for c in held_benign) >= 10


def test_heldout_files_are_frozen():
    """Fails if a held-out file changes. If the change is deliberate (e.g. fixing a typo
    before any final run), regenerate data/heldout.sha256 and say so in your write-up:
    editing held-out data after seeing results invalidates the generalization test."""
    expected = dict(line.split("  ")[::-1] for line in (DATA / "heldout.sha256").read_text().splitlines())
    for name in HELDOUT_FILES:
        actual = hashlib.sha256((DATA / name).read_bytes()).hexdigest()
        assert actual == expected[name], f"{name} changed since it was frozen"
