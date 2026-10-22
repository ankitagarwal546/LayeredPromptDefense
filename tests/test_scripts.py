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
