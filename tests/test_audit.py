"""Statistics helpers of scripts/audit_independent.py (pure functions; the audit itself needs the local results/)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("audit_independent", ROOT / "scripts" / "audit_independent.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_wilson_interval_matches_known_values_and_handles_empty():
    low, high = audit.wilson(5, 10)
    assert round(low, 3) == 0.237 and round(high, 3) == 0.763
    assert audit.wilson(0, 0) is None
    assert audit.wilson(0, 20)[0] == 0.0


def test_newcombe_difference_is_signed_and_brackets_the_estimate():
    diff, low, high = audit.newcombe(20, 100, 40, 100)
    assert round(diff, 2) == -0.20 and low < diff < high and high < 0.0


def test_paired_bootstrap_is_deterministic_and_skips_unresolved_attacks():
    a = {"x": 1.0, "y": 0.0, "z": None, "w": 1.0}
    b = {"x": 0.0, "y": 0.0, "z": 1.0, "w": 0.0}
    r1 = audit.paired_bootstrap(a, b, resamples=500)
    r2 = audit.paired_bootstrap(a, b, resamples=500)
    assert r1 == r2 and r1["n"] == 3  # z is dropped: it is unresolved in one run
    assert abs(r1["diff"] - 2 / 3) < 1e-9 and r1["lo"] <= r1["diff"] <= r1["hi"]
    assert audit.paired_bootstrap({}, {}, resamples=10) == {"n": 0}


def test_transitions_separate_natural_resistance_from_prevention():
    e0 = {("a", 0): True, ("b", 0): False, ("c", 0): True, ("d", 0): False, ("e", 0): None}
    e2 = {("a", 0): False, ("b", 0): False, ("c", 0): True, ("d", 0): True, ("e", 0): False}
    t = audit.transitions(e0, e2)
    assert (t["success->fail"], t["fail->fail"], t["success->success"], t["fail->success"], t["unresolved"]) == (1, 1, 1, 1, 1)


def test_pct_reports_numerator_denominator_and_interval():
    assert audit.pct(66, 150).startswith("44.0% (66/150) [")
    assert audit.pct(0, 0) == "n/a (0)"
