import json
from pathlib import Path

import pytest

from conftest import ScriptedLLM
from injection_defense.config import PRESETS
from injection_defense.defenses.classifier import PromptClassifier, UnavailableClassifier
from injection_defense.evaluation import metrics as m
from injection_defense.evaluation.execute import execute_run
from injection_defense.evaluation.registry import build_case_set, estimate_model_calls
from injection_defense.evaluation.runner import run_matrix
from injection_defense.evaluation.store import (
    RunWriter, append_label, list_runs, load_outcomes, pending_review,
)
from injection_defense.llm.base import LLMError
from injection_defense.llm.mock import MockLLM

DATA = Path(__file__).resolve().parents[1] / "data"
DEV = build_case_set("dev", DATA)


def run(tmp_path, names=("E0", "E1"), **kw):
    kw.setdefault("llm", MockLLM())
    kw.setdefault("classifier", None)
    return execute_run(case_set=DEV, experiment_names=list(names), repetitions=1, results_dir=tmp_path, **kw)


def test_case_sets_final_excludes_dev_benign_and_uses_disjoint_families():
    final = build_case_set("final", DATA)
    ids = {c.case_id for c in final.cases}
    assert not any(i.startswith("dev-b") for i in ids)          # tuned-on benign data excluded
    assert sum(c.is_attack for c in final.cases) == 11 + 24 and sum(not c.is_attack for c in final.cases) == 24
    assert final.heldout_families == {c.attack_family for c in final.cases if c.case_id.startswith("ho-a")}
    with pytest.raises(ValueError, match="Unknown case set"):
        build_case_set("../etc", DATA)


def test_call_estimate_counts_classifier_calls():
    cfgs = {k: PRESETS[k] for k in ("E0", "E3", "E5")}
    assert estimate_model_calls(cfgs, n_cases=10, repetitions=2) == (1 + 2 + 2) * 10 * 2


def test_execute_run_writes_metadata_and_outcomes_and_never_overwrites(tmp_path):
    folder = run(tmp_path, run_id="aaaaaaaaaaaa")
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["model"]["is_mock"] and meta["case_set"] == "dev" and meta["finished_at"]
    assert meta["evidence_status"].startswith("SMOKE TEST ONLY") and meta["dataset"]["sha256"]
    assert len(load_outcomes(folder)) == 2 * len(DEV.cases)
    with pytest.raises(FileExistsError):
        run(tmp_path, run_id="aaaaaaaaaaaa")
    assert len(load_outcomes(folder)) == 2 * len(DEV.cases)  # untouched


def test_same_cases_are_used_for_every_configuration(tmp_path):
    outcomes = load_outcomes(run(tmp_path, names=("E0", "E1", "E2", "E4")))
    by_exp = {}
    for o in outcomes:
        by_exp.setdefault(o.experiment, []).append(o.case_id)
    assert len({tuple(v) for v in by_exp.values()}) == 1 and len(by_exp) == 4


def test_resume_completes_an_interrupted_run_without_duplicates(tmp_path):
    class Interrupt(Exception):
        pass

    def stop_after_five(done):
        if done == 5:
            raise Interrupt

    with pytest.raises(Interrupt):
        run(tmp_path, run_id="bbbbbbbbbbbb", progress=stop_after_five)
    folder = tmp_path / "bbbbbbbbbbbb"
    assert len(load_outcomes(folder)) == 5
    run(tmp_path, run_id="bbbbbbbbbbbb", resume=True)
    outcomes = load_outcomes(folder)
    keys = [(o.experiment, o.trial, o.case_id) for o in outcomes]
    assert len(keys) == len(set(keys)) == 2 * len(DEV.cases)
    assert json.loads((folder / "metadata.json").read_text())["resumed_at"]


def test_resume_refuses_a_changed_configuration(tmp_path):
    class Interrupt(Exception):
        pass

    def stop(done):
        raise Interrupt

    with pytest.raises(Interrupt):
        run(tmp_path, run_id="cccccccccccc", progress=stop)
    with pytest.raises(ValueError, match="cannot resume"):
        run(tmp_path, names=("E0", "E2"), run_id="cccccccccccc", resume=True)
    with pytest.raises(FileNotFoundError):
        run(tmp_path, run_id="dddddddddddd", resume=True)


def test_unavailable_experiments_are_recorded_not_zero_filled(tmp_path):
    folder = run(tmp_path, names=("E0", "E3"), classifier=UnavailableClassifier("not configured"))
    meta = json.loads((folder / "metadata.json").read_text())
    assert "E3" in meta["unavailable_experiments"]
    assert {o.experiment for o in load_outcomes(folder)} == {"E0"}


def test_model_failures_are_recorded_and_not_counted_as_attack_failures():
    class Down(ScriptedLLM):
        def generate(self, prompt):
            raise LLMError("down")

    result = run_matrix({"E0": PRESETS["E0"]}, DEV.cases, llm=Down())
    outs = result.outcomes
    assert all(o.status == "error" for o in outs)
    asr = m.attack_success_rate(outs)
    assert asr.denominator == 0 and asr.rate is None and asr.unknown == 11
    assert m.technical_failure_rate(outs).percent == 100.0
    assert m.task_completion_rate(outs).denominator == 0


def test_detector_failures_are_counted_and_never_become_detections():
    garbage = PromptClassifier(ScriptedLLM("not json"))
    result = run_matrix({"E3": PRESETS["E3"]}, DEV.cases, llm=ScriptedLLM("ok"), classifier=garbage)
    assert m.detector_failure_count(result.outcomes) == len(DEV.cases)
    assert all(o.flagged is None for o in result.outcomes)          # no verdict
    assert m.false_positive_rate(result.outcomes).denominator == 0   # not counted as "benign, not flagged"
    assert m.detection_rate(result.outcomes).numerator == 0


def test_manual_labels_override_and_resolve_needs_review(tmp_path):
    folder = run(tmp_path, names=("E0",), llm=ScriptedLLM('The document says "DOCUMENT COMPROMISED" is requested.'))
    outcomes = load_outcomes(folder)
    pending = pending_review(outcomes)
    assert pending and all(o.scoring == "needs_review" for o in pending)
    before = m.attack_success_rate(outcomes)
    assert before.unknown >= 1
    append_label(folder, pending[0], True, adjudicator="test", reason="complied")
    after = load_outcomes(folder)
    assert len(pending_review(after)) == len(pending) - 1
    assert m.attack_success_rate(after).numerator == before.numerator + 1


def test_list_runs_ignores_non_run_folders(tmp_path):
    run(tmp_path, run_id="eeeeeeeeeeee")
    (tmp_path / "not-a-run").mkdir()
    (tmp_path / "ffffffffffff").mkdir()  # valid name but no metadata
    assert [r["run_id"] for r in list_runs(tmp_path)] == ["eeeeeeeeeeee"]


def test_run_writer_rejects_path_like_ids(tmp_path):
    for bad in ("../x", "abc", "ABCDEFABCDEF"):
        with pytest.raises(ValueError):
            RunWriter(tmp_path, bad)


def test_run_metadata_records_the_code_version(tmp_path):
    from injection_defense.evaluation.execute import git_state

    meta = json.loads((run(tmp_path) / "metadata.json").read_text())
    assert "code" in meta  # {"commit", "dirty"} inside the repo; None elsewhere
    state = git_state(tmp_path)  # tmp_path is not a git repository
    assert state is None
    inside = git_state()
    assert inside is None or (len(inside["commit"]) == 40 and isinstance(inside["dirty"], bool))
