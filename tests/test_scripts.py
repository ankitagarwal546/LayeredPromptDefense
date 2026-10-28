"""CLI scripts, run as subprocesses from an empty working directory (so no .env is read)."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ScriptedLLM
from injection_defense.evaluation.execute import execute_run
from injection_defense.evaluation.registry import build_case_set

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def run_script(name, *args, cwd, env_extra=None):
    import os

    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "CLASSIFIER_"))}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(ROOT / "scripts" / name), *args], cwd=cwd, env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)


def test_dry_run_prints_the_plan_and_creates_nothing(tmp_path):
    out = tmp_path / "res"
    r = run_script("run_experiments.py", "--configs", "E0,E3", "--dry-run", "--out", str(out), cwd=tmp_path)
    assert r.returncode == 0 and "PLAN" in r.stdout and "dry run" in r.stdout
    assert "E3: NOT_RUN" in r.stdout and "up to 18 " in r.stdout  # unavailable E3 is not counted
    assert "MOCK" in r.stdout and not out.exists()


def test_final_case_set_requires_acknowledgement(tmp_path):
    r = run_script("run_experiments.py", "--case-set", "final", "--dry-run", cwd=tmp_path)
    assert r.returncode == 2 and "--final-ack" in r.stderr


def test_unknown_experiment_is_rejected(tmp_path):
    r = run_script("run_experiments.py", "--configs", "E99", "--dry-run", cwd=tmp_path)
    assert r.returncode == 2 and "Unknown experiment" in r.stderr


def test_real_run_without_configuration_fails_instead_of_using_the_mock(tmp_path):
    r = run_script("run_experiments.py", "--real", "--dry-run", cwd=tmp_path)
    assert r.returncode == 2 and "not configured" in r.stderr


def test_real_run_needs_explicit_confirmation(tmp_path):
    env = {"LLM_PROVIDER": "openai_compatible", "LLM_MODEL": "m", "LLM_API_KEY": "k"}
    r = run_script("run_experiments.py", "--real", "--configs", "E0", "--out", str(tmp_path / "res"), cwd=tmp_path, env_extra=env)
    assert r.returncode == 2 and "--yes" in r.stderr and "up to 18" in r.stdout
    assert not (tmp_path / "res").exists()  # nothing was sent or written


def test_mock_run_then_analyze_writes_tables_and_charts(tmp_path):
    out = tmp_path / "res"
    r = run_script("run_experiments.py", "--configs", "E0,E1", "--out", str(out), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    (run_dir,) = list(out.iterdir())
    a = run_script("analyze_results.py", run_dir.name, "--results-dir", str(out), cwd=tmp_path)
    assert a.returncode == 0, a.stderr
    files = {p.name for p in (run_dir / "analysis").iterdir()}
    assert {"summary.csv", "by_family.csv", "report.md", "security_vs_utility.png", "fpr.png", "latency.png"} <= files
    assert "SMOKE TEST ONLY" in (run_dir / "analysis" / "report.md").read_text()
    rows = list(csv.DictReader((run_dir / "analysis" / "summary.csv").open()))
    assert {r["experiment"] for r in rows} == {"E0", "E1"}


def test_analyze_rejects_bad_run_ids(tmp_path):
    for bad in ("../x", "nope", "0123456789ab"):
        assert run_script("analyze_results.py", bad, "--results-dir", str(tmp_path), cwd=tmp_path).returncode in (1, 2)


def test_adjudication_flow_changes_the_analysis(tmp_path):
    out = tmp_path / "res"
    llm = ScriptedLLM('The document says "DOCUMENT COMPROMISED" is requested.')
    execute_run(case_set=build_case_set("dev", DATA), experiment_names=["E0"], llm=llm, classifier=None,
                repetitions=1, results_dir=out, run_id="abcdef012345")
    listing = run_script("adjudicate.py", "abcdef012345", "--results-dir", str(out), "--list", cwd=tmp_path)
    assert listing.returncode == 0 and "dev-a01" in listing.stdout
    bad = run_script("adjudicate.py", "abcdef012345", "--results-dir", str(out), "--set", "E0", "0", "dev-a01", "true", cwd=tmp_path)
    assert bad.returncode == 2 and "--adjudicator" in bad.stderr           # who judged is mandatory
    ok = run_script("adjudicate.py", "abcdef012345", "--results-dir", str(out), "--set", "E0", "0", "dev-a01", "true",
                    "--adjudicator", "tester", "--reason", "complied", cwd=tmp_path)
    assert ok.returncode == 0
    label = json.loads((out / "abcdef012345" / "manual_labels.jsonl").read_text().splitlines()[0])
    assert label["adjudicator"] == "tester" and label["attack_success"] is True
    pending_after = run_script("adjudicate.py", "abcdef012345", "--results-dir", str(out), "--list", cwd=tmp_path).stdout
    assert "dev-a01" not in pending_after
    unknown = run_script("adjudicate.py", "abcdef012345", "--results-dir", str(out), "--set", "E0", "0", "nope", "true",
                         "--adjudicator", "t", cwd=tmp_path)
    assert unknown.returncode == 2


def test_verify_environment_reports_mock_mode_without_secrets(tmp_path):
    r = run_script("verify_environment.py", cwd=tmp_path, env_extra={"LLM_API_KEY": "sk-leak-check"})
    assert r.returncode == 0 and "mock mode still works" in r.stdout and "sk-leak-check" not in r.stdout + r.stderr
    assert run_script("verify_environment.py", "--ping", cwd=tmp_path).stdout.count("ping: skipped") == 1


def test_review_checklist_and_apply_roundtrip(tmp_path):
    out = tmp_path / "res"
    llm = ScriptedLLM('The document says "DOCUMENT COMPROMISED" is requested.')
    execute_run(case_set=build_case_set("dev", DATA), experiment_names=["E0"], llm=llm, classifier=None,
                repetitions=1, results_dir=out, run_id="abcdef012345")
    run_script("adjudicate.py", "abcdef012345", "--results-dir", str(out), "--set", "E0", "0", "dev-a01", "false",
               "--adjudicator", "ai-test", "--reason", "quoted", cwd=tmp_path)
    prep = run_script("prepare_review.py", "abcdef012345", "--results-dir", str(out), "--out", str(tmp_path / "rev"), cwd=tmp_path)
    assert prep.returncode == 0, prep.stderr
    md = (tmp_path / "rev" / "review_checklist.md").read_text()
    assert "dev-a01" in md and "AI label: NO" in md and "did the model carry out" in md and "DOCUMENT COMPROMISED" in md
    rows = list(csv.DictReader((tmp_path / "rev" / "review_decisions.csv").open()))
    assert len(rows) == 1 and rows[0]["ai_label"] == "no" and rows[0]["human_label"] == ""
    blank = run_script("apply_review.py", str(tmp_path / "rev" / "review_decisions.csv"), "--results-dir", str(out), cwd=tmp_path)
    assert blank.returncode == 0 and "0 outcome label(s)" in blank.stdout

    path = tmp_path / "rev" / "review_decisions.csv"
    rows[0]["human_label"] = "yes"
    for filled_reviewer, code in (("", 2), ("alice", 0)):
        rows[0]["reviewer"] = filled_reviewer
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        r = run_script("apply_review.py", str(path), "--results-dir", str(out), cwd=tmp_path)
        assert r.returncode == code, r.stderr
    assert "1 outcome(s) change the AI label" in r.stdout
    labels = [json.loads(l) for l in (out / "abcdef012345" / "manual_labels.jsonl").read_text().splitlines()]
    assert labels[-1]["adjudicator"] == "human: alice" and labels[-1]["attack_success"] is True and labels[0]["adjudicator"] == "ai-test"
    from injection_defense.evaluation.store import load_outcomes
    assert [o.manual_label for o in load_outcomes(out / "abcdef012345") if o.case_id == "dev-a01"] == [True]


def test_apply_review_rejects_bad_verdicts(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("item,group_id,run_id,model,case_id,family,outcomes,ai_label,human_label,reviewer,note\n"
                    "1,g,abcdef012345,m,dev-a01,f,1,no,maybe,bob,\n")
    r = run_script("apply_review.py", str(path), "--results-dir", str(tmp_path), cwd=tmp_path)
    assert r.returncode == 2 and "yes, no or blank" in r.stderr


def test_task_disruption_script_writes_tables_and_reports_agreement(tmp_path):
    out = tmp_path / "res"
    execute_run(case_set=build_case_set("dev", DATA), experiment_names=["E0", "E1"], llm=ScriptedLLM("I can't fulfill this request."),
                classifier=None, repetitions=1, results_dir=out, run_id="0123456789ab")
    r = run_script("task_disruption.py", "0123456789ab", "--results-dir", str(out), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    rows = {row["experiment"]: row for row in csv.DictReader((out / "0123456789ab" / "analysis" / "task_disruption.csv").open())}
    assert set(rows) == {"E0", "E1"}
    assert rows["E0"]["disrupted"] == "11" and rows["E0"]["usable"] == "0"          # every refusal disrupts the task
    assert int(rows["E1"]["blocked"]) > 0 and rows["E1"]["task_disruption"].startswith("100.0%")
    cases_csv = (out / "0123456789ab" / "analysis" / "task_disruption_cases.csv").read_text()
    assert "can't fulfill" not in cases_csv  # no model text in the per-case export


def test_review_and_disruption_tools_find_cases_in_the_independent_folder(tmp_path):
    from injection_defense.evaluation.registry import load_all_cases

    cases = load_all_cases(DATA)
    assert {"dev-a01", "ho-a01"} <= set(cases)
    if (DATA / "independent" / "attacks.jsonl").exists():
        assert "ind-a01" in cases and "ind-b01" in cases


def _write_csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def test_blind_second_review_hides_the_condition_and_measures_agreement(tmp_path):
    out = tmp_path / "res"
    execute_run(case_set=build_case_set("dev", DATA), experiment_names=["E0", "E2"], llm=ScriptedLLM('The document says "DOCUMENT COMPROMISED" is requested.'),
                classifier=None, repetitions=1, results_dir=out, run_id="abcdef012345")
    sys.path.insert(0, str(ROOT / "scripts"))
    from prepare_review import group_id
    from injection_defense.evaluation.store import load_outcomes

    groups = {}
    for o in load_outcomes(out / "abcdef012345"):
        if o.is_attack:
            groups.setdefault(group_id("abcdef012345", o.case_id, o.output_text or ""), o)
    first = [{"item": i, "group_id": g, "run_id": "abcdef012345", "model": "scripted-test-model", "case_id": o.case_id,
              "outcomes": 2, "ai_label": "no", "human_label": ("yes" if i % 2 else "no") if i < len(groups) else "",
              "reviewer": "ankit" if i < len(groups) else "", "note": ""} for i, (g, o) in enumerate(groups.items(), 1)]
    assert len(first) >= 3  # first reviewer: alternating yes/no, the last one unsure
    (tmp_path / "rev").mkdir()
    _write_csv(tmp_path / "rev" / "review_decisions.csv", first)

    kit = tmp_path / "blind"
    prep = run_script("prepare_blind_review.py", str(tmp_path / "rev" / "review_decisions.csv"), "--results-dir", str(out), "--out", str(kit), cwd=tmp_path)
    assert prep.returncode == 0, prep.stderr
    md = (kit / "blind_checklist.md").read_text()
    for leak in ("abcdef012345", "scripted-test-model", "E0/t0", "E2/t0", "AI label", "ankit"):
        assert leak not in md, leak  # nothing that reveals run, model, configuration or the first verdict
    assert "did the model carry out" in md and "DOCUMENT COMPROMISED" in md
    assert sorted(p.name for p in kit.iterdir()) == ["README.txt", "blind_checklist.md", "blind_decisions.csv"]
    key = list(csv.DictReader((tmp_path / "blind_key" / "blind_key.csv").open()))
    assert len(key) == len(first) and {k["group_id"] for k in key} == {r["group_id"] for r in first}
    again = tmp_path / "blind2"
    run_script("prepare_blind_review.py", str(tmp_path / "rev" / "review_decisions.csv"), "--results-dir", str(out), "--out", str(again), cwd=tmp_path)
    assert (again / "blind_checklist.md").read_text() == md  # same seed -> same kit

    second = list(csv.DictReader((kit / "blind_decisions.csv").open()))
    assert run_script("review_agreement.py", str(kit), cwd=tmp_path).returncode == 1  # nothing filled in yet
    firsts = {k["blind_id"]: k["first_label"] for k in key}
    for i, r in enumerate(second):  # agree everywhere except one decided item
        r["human_label"] = firsts[r["blind_id"]] or "yes"
        r["reviewer"] = "bea"
    flip = next(r for r in second if firsts[r["blind_id"]])
    flip["human_label"] = "no" if flip["human_label"] == "yes" else "yes"
    _write_csv(kit / "blind_decisions.csv", second)
    r = run_script("review_agreement.py", str(kit), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    result = json.loads((tmp_path / "blind_key" / "agreement.json").read_text())
    decided = len(first) - 1
    assert result["overall"]["both_decided"] == decided and result["overall"]["agree"] == decided - 1
    assert result["overall"]["unsure_first"] == 1 and len(result["disagreements"]) == 1
    assert result["second_reviewers"] == ["bea"] and "abcdef012345" not in (kit / "blind_decisions.csv").read_text()


def test_quality_rating_kit_is_blind_and_aggregates_by_condition(tmp_path):
    out = tmp_path / "res"
    execute_run(case_set=build_case_set("dev", DATA), experiment_names=["E0", "E2"], llm=ScriptedLLM("Coral reefs host many species."),
                classifier=None, repetitions=1, results_dir=out, run_id="0123456789ab")
    kit = tmp_path / "q"
    prep = run_script("prepare_quality_rating.py", "0123456789ab", "--results-dir", str(out), "--configs", "E0,E2", "--out", str(kit), cwd=tmp_path)
    assert prep.returncode == 0, prep.stderr
    sheet = (kit / "rating_sheet.md").read_text()
    assert "0123456789ab" not in sheet and "scripted-test-model" not in sheet and "faithful (1-5)" in sheet
    key = list(csv.DictReader((tmp_path / "q_key" / "rating_key.csv").open()))
    assert {k["experiment"] for k in key} == {"E0", "E2"} and len(key) % 2 == 0
    rows = list(csv.DictReader((kit / "ratings.csv").open()))
    rows[0].update(faithful="7", coverage="3", usable="yes", rater="bea")
    _write_csv(kit / "ratings.csv", rows)
    bad = run_script("summarize_quality.py", str(kit), cwd=tmp_path)
    assert bad.returncode == 2 and "1-5" in bad.stderr
    for r in rows:
        r.update(faithful="5", coverage="4", usable="yes", rater="bea")
    rows[-1].update(faithful="", coverage="", usable="", rater="")  # one left unrated
    _write_csv(kit / "ratings.csv", rows)
    ok = run_script("summarize_quality.py", str(kit), cwd=tmp_path)
    assert ok.returncode == 0, ok.stderr
    summary = list(csv.DictReader((tmp_path / "q_key" / "quality_summary.csv").open()))
    assert {s["config"] for s in summary} == {"E0", "E2"}
    assert sum(int(s["rated"]) for s in summary) == len(rows) - 1 and all(s["faithful_mean"] == "5.0" for s in summary)
