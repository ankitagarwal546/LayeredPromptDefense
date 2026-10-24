import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ScriptedLLM
from injection_defense.defenses.output_validator import OutputValidator
from injection_defense.evaluation.dataset import load_cases
from injection_defense.evaluation.disruption import classify, load_criteria
from injection_defense.evaluation.independent import (
    AREAS, BIPIA_SHA256, build_cases, check_documents, insert_instruction, load_bipia, load_user_documents,
)
from injection_defense.evaluation.metrics import CaseOutcome
from injection_defense.evaluation.registry import build_case_set
from injection_defense.evaluation.runner import _task_completed, evidence_status

ROOT = Path(__file__).resolve().parents[1]
BIPIA_DIR = ROOT / "data" / "external" / "bipia"


def fake_text(n: int, words: tuple[str, str, str, str]) -> str:
    a, b, c, d = words
    return " ".join([f"The {a} of region {n} changed during the {b} period, according to the {c} record. "
                     f"Observers noted that the {d} remained steady while neighbouring districts adapted slowly. "
                     f"Detailed notes from season {n} describe how local groups measured each change carefully. "] * 3)


def fake_docs(path: Path, *, ordinary=18, security=7) -> list[dict]:
    rows = []
    for i in range(ordinary):
        words = (f"alpha{i}", f"beta{i}", f"gamma{i}", f"delta{i}")
        rows.append({"doc_id": f"ord-{i:02d}", "kind": "ordinary", "area": AREAS[i % 9], "topic": f"fake ordinary topic {i}",
                     "text": fake_text(i, words), "key_topics": [[w] for w in words], "themes": [], "author": "test author",
                     "original_work": True})
    themes = [["ai"], ["ai", "malicious_instructions"], ["cybersecurity"], ["cybersecurity", "imperative_for_humans"],
              ["malicious_instructions"], ["ai"], ["cybersecurity"]]
    for j in range(security):
        words = (f"omega{j}", f"sigma{j}", f"kappa{j}", f"theta{j}")
        rows.append({"doc_id": f"sec-{j:02d}", "kind": "security_themed", "area": "technology", "topic": f"fake security topic {j}",
                     "text": fake_text(100 + j, words), "key_topics": [[w] for w in words], "themes": themes[j % 7],
                     "author": "test author", "original_work": True})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return rows


@pytest.fixture
def bipia():
    return load_bipia(BIPIA_DIR)


@pytest.fixture
def criteria():
    return json.loads((BIPIA_DIR / "attack_criteria.json").read_text())


def test_bipia_file_is_pinned_by_checksum(tmp_path, bipia):
    assert len(bipia) == 15 and sum(len(v) for v in bipia.values()) == 75
    (tmp_path / "text_attack_test.json").write_text(json.dumps({"x": ["y"]}))
    with pytest.raises(ValueError, match="pinned BIPIA checksum"):
        load_bipia(tmp_path)
    assert BIPIA_SHA256 == "75750e7b4e8b34e8f9d88d89b357aeaaf02bd07f9e493ccd37eda74a0cd7c7f8"


def test_checklist_passes_for_a_valid_set(tmp_path, bipia):
    fake_docs(tmp_path / "d.jsonl")
    docs = load_user_documents(tmp_path / "d.jsonl")
    assert check_documents(docs, [s for v in bipia.values() for s in v]) == []


def test_checklist_reports_each_kind_of_problem(tmp_path, bipia):
    rows = fake_docs(tmp_path / "d.jsonl")
    rows[0]["text"] = "too short"                                                    # length + key topics
    rows[1]["text"] += " Please ask the AI assistant to help."                        # ordinary doc mentioning AI
    rows[2]["text"] += " Visit www.shoplux.com today."                                 # cue string
    rows[3]["text"] += " Note to the assistant: obey."                                 # directed at an AI
    rows[4]["original_work"] = False
    rows[5]["text"] = bipia["Reverse Text"][2] + " " + rows[5]["text"]                 # verbatim BIPIA copy
    for r in rows[6:12]:
        r["area"] = "science"                                                          # too many in one area
    rows[18]["themes"] = []                                                            # security doc without themes
    rows.append(dict(rows[7], doc_id="dup-07"))                                        # duplicate text/topic, 26 docs
    (tmp_path / "d.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    rules = {p.rule for p in check_documents(load_user_documents(tmp_path / "d.jsonl"), [s for v in bipia.values() for s in v])}
    assert {"length", "key_topics", "ordinary_topic", "cue_strings", "directed", "original", "bipia_copy", "areas",
            "themes", "unique_text", "unique_topic"} <= rules


def test_count_and_theme_coverage_rules(tmp_path):
    fake_docs(tmp_path / "d.jsonl", ordinary=6, security=3)
    rules = {p.rule for p in check_documents(load_user_documents(tmp_path / "d.jsonl"))}
    assert {"count", "ordinary", "security", "themes", "areas"} <= rules


def test_malformed_user_documents_are_rejected(tmp_path):
    rows = fake_docs(tmp_path / "d.jsonl")
    rows[0]["key_topics"] = [["only"], ["three"], ["groups"]]
    rows[1]["extra_field"] = 1
    (tmp_path / "d.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + "{not json\n")
    with pytest.raises(ValueError, match="malformed"):
        load_user_documents(tmp_path / "d.jsonl")


@pytest.mark.parametrize("position,expected", [("start", "INSTR\n\nOne. Two. Three. Four."), ("end", "One. Two. Three. Four.\n\nINSTR"),
                                               ("middle", "One. Two.\n\nINSTR\n\nThree. Four.")])
def test_instruction_insertion(position, expected):
    assert insert_instruction("One. Two. Three. Four.", "INSTR", position) == expected
    assert insert_instruction("Single sentence only.", "INSTR", "middle") == "Single sentence only.\n\nINSTR"


def test_build_is_deterministic_complete_and_spread_out(tmp_path, bipia, criteria):
    fake_docs(tmp_path / "d.jsonl")
    docs = load_user_documents(tmp_path / "d.jsonl")
    attacks, benign, table = build_cases(docs, bipia, criteria, "test")
    again = build_cases(docs, bipia, criteria, "test")[0]
    assert [a.model_dump() for a in attacks] == [a.model_dump() for a in again]            # no randomness
    assert len(attacks) == 75 and len(benign) == 25 and len({a.case_id for a in attacks + benign}) == 100
    instructions = [s for v in bipia.values() for s in v]
    for case, instruction in zip(attacks, instructions):
        assert instruction in case.document_text and case.is_attack and case.success_checks and case.key_topics
        assert "ignore" not in case.document_text.lower()                                  # bare instructions only
    carriers = {t["carrier"] for t in table}
    assert carriers == {f"ord-{i:02d}" for i in range(18)}                                 # security docs are never carriers
    assert {t["position"] for t in table} == {"start", "middle", "end"}
    per_doc = {c: [t["category"] for t in table if t["carrier"] == c] for c in carriers}
    assert all(len(v) in (4, 5) and len(set(v)) == len(v) for v in per_doc.values())      # different category each time
    assert sum("Hard negative" in b.notes for b in benign) == 7


def test_builder_script_freezes_and_refuses_to_overwrite(tmp_path):
    folder = tmp_path / "independent"
    folder.mkdir()
    fake_docs(folder / "user_documents.jsonl")
    run = lambda: subprocess.run([sys.executable, str(ROOT / "scripts" / "build_independent_set.py"), "--dir", str(folder)],
                                 capture_output=True, text=True, cwd=tmp_path)
    first = run()
    assert first.returncode == 0, first.stderr
    assert {p.name for p in folder.iterdir()} == {"user_documents.jsonl", "attacks.jsonl", "benign.jsonl", "MANIFEST.json", "independent.sha256"}
    assert len(load_cases(folder / "attacks.jsonl")) == 75 and len(load_cases(folder / "benign.jsonl")) == 25
    manifest = json.loads((folder / "MANIFEST.json").read_text())
    assert manifest["bipia_file_sha256"] == BIPIA_SHA256 and len(manifest["assignment"]) == 75
    second = run()
    assert second.returncode == 2 and "refusing to overwrite" in second.stderr


def test_builder_script_refuses_a_failing_checklist(tmp_path):
    folder = tmp_path / "independent"
    folder.mkdir()
    fake_docs(folder / "user_documents.jsonl", ordinary=10, security=3)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_independent_set.py"), "--dir", str(folder)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 2 and "checklist fails" in r.stderr and not (folder / "attacks.jsonl").exists()


def test_validate_script_prints_a_checklist(tmp_path):
    fake_docs(tmp_path / "d.jsonl", ordinary=10, security=3)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_user_docs.py"), str(tmp_path / "d.jsonl")],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 1 and "[FAIL] at least 18 ordinary documents" in r.stdout and "To fix:" in r.stdout
    missing = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_user_docs.py"), str(tmp_path / "none.jsonl")],
                             capture_output=True, text=True, cwd=tmp_path)
    assert missing.returncode == 1 and "does not exist yet" in missing.stdout


def test_independent_case_set_errors_clearly_until_built(tmp_path):
    with pytest.raises(ValueError, match="not built yet"):
        build_case_set("independent", tmp_path)


def test_independent_case_set_uses_new_families_only(tmp_path, bipia, criteria):
    folder = tmp_path / "independent"
    folder.mkdir()
    fake_docs(folder / "user_documents.jsonl")
    docs = load_user_documents(folder / "user_documents.jsonl")
    attacks, benign, _ = build_cases(docs, bipia, criteria, "test")
    for name, cases in (("attacks.jsonl", attacks), ("benign.jsonl", benign)):
        (folder / name).write_text("".join(c.model_dump_json() + "\n" for c in cases))
    cs = build_case_set("independent", tmp_path)
    dev_families = {c.attack_family for c in load_cases(ROOT / "data" / "dev_cases.jsonl") if c.is_attack}
    held_families = {c.attack_family for c in load_cases(ROOT / "data" / "heldout_attacks.jsonl") if c.is_attack}
    assert len(cs.cases) == 100 and cs.heldout_families and not cs.heldout_families & (dev_families | held_families)
    assert all(f.startswith("bipia_") for f in cs.heldout_families)


def test_key_topic_scoring_for_human_documents(tmp_path, bipia, criteria):
    fake_docs(tmp_path / "d.jsonl")
    docs = load_user_documents(tmp_path / "d.jsonl")
    attacks, benign, _ = build_cases(docs, bipia, criteria, "test")
    case = benign[0]
    words = [g[0] for g in case.key_topics]

    class R:  # minimal response stand-in
        def __init__(self, summary): self.summary = summary

    assert _task_completed(case, R(f"{words[0]} and {words[1]} summarized.")) is True
    assert _task_completed(case, R(f"only {words[0]} mentioned.")) is False
    # attack cases: every check is satisfiable by the validator without errors, and the usable-summary rule uses the doc's topics
    v = OutputValidator()
    attack = attacks[0]  # task automation -> cue_review
    assert v.validate("A neutral summary.", attack.criteria()).outcome == "no_indicator"
    assert v.validate("Here is a rename script: import os", attack.criteria()).outcome == "needs_review"
    crit = load_criteria(ROOT / "data" / "task_disruption_carriers.json")
    out = CaseOutcome(run_id="r", experiment="E", trial=0, case_id=attack.case_id, is_attack=True, attack_family=attack.attack_family,
                      status="processed", attack_success=False, output_text=f"{words[0]} {words[1]} summary")
    attack_words = [g[0] for g in attack.key_topics]
    ok = CaseOutcome(**{**out.__dict__, "output_text": f"{attack_words[0]} and {attack_words[1]} summary"})
    assert classify(ok, attack, crit).category == "usable"
    assert classify(CaseOutcome(**{**out.__dict__, "output_text": "I cannot help."}), attack, crit).category == "disrupted"


def test_bipia_runs_are_labeled_preliminary():
    assert evidence_status(False, {"external_bipia_text_attack_test+human_authored_documents"}).startswith("PRELIMINARY")
    assert evidence_status(True, {"external_bipia_text_attack_test+human_authored_documents"}).startswith("SMOKE")


def test_the_built_independent_set_is_frozen():
    """Once data/independent/independent.sha256 exists, any change to the built files fails this test."""
    checksum = ROOT / "data" / "independent" / "independent.sha256"
    if not checksum.exists():
        pytest.skip("independent set not built yet")
    import hashlib
    for line in checksum.read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((ROOT / "data" / "independent" / name).read_bytes()).hexdigest() == digest, f"{name} changed after freezing"
