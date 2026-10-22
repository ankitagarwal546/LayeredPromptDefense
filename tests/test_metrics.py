import math

import pytest

from injection_defense.evaluation.metrics import (
    CaseOutcome, RateResult, attack_success_rate, benign_block_rate, false_positive_rate,
    generalization_gap, operational_stats, task_completion_rate,
)


def outcome(is_attack, *, success=None, flagged=None, status="processed", completed=None,
            latency=10.0, calls=1, family="f", manual=None):
    return CaseOutcome(
        run_id="r", experiment="E", trial=0, case_id="c", is_attack=is_attack,
        attack_family=family if is_attack else None, status=status, flagged=flagged,
        attack_success=success, task_completed=completed, latency_ms=latency,
        model_calls=calls, manual_label=manual,
    )


def test_asr_counts_only_evaluated_attacks():
    outs = [outcome(True, success=True), outcome(True, success=False), outcome(True, success=False),
            outcome(True, success=None), outcome(False)]
    asr = attack_success_rate(outs)
    assert (asr.numerator, asr.denominator, asr.unknown) == (1, 3, 1)
    assert asr.rate == pytest.approx(1 / 3)


def test_asr_zero_denominator_is_none_not_zero():
    asr = attack_success_rate([outcome(False), outcome(True, success=None)])
    assert asr.denominator == 0 and asr.rate is None and asr.percent is None and asr.unknown == 1
    assert asr.wilson_95 is None


def test_manual_label_overrides_automatic_score():
    outs = [outcome(True, success=None, manual=True), outcome(True, success=False, manual=True)]
    assert attack_success_rate(outs).numerator == 2


def test_fpr_known_example():
    outs = [outcome(False, flagged=True), outcome(False, flagged=False), outcome(False, flagged=False),
            outcome(False, flagged=False), outcome(True, flagged=True)]
    fpr = false_positive_rate(outs)
    assert (fpr.numerator, fpr.denominator) == (1, 4) and fpr.percent == 25.0


def test_fpr_excludes_cases_without_a_detection_verdict():
    outs = [outcome(False, flagged=None), outcome(False, flagged=True)]
    fpr = false_positive_rate(outs)
    assert (fpr.numerator, fpr.denominator, fpr.unknown) == (1, 1, 1)


def test_fpr_with_no_benign_cases():
    assert false_positive_rate([outcome(True, flagged=True)]).rate is None


def test_benign_block_rate_and_task_completion():
    outs = [outcome(False, status="blocked", completed=False), outcome(False, completed=True),
            outcome(False, completed=True), outcome(False, status="error")]
    assert benign_block_rate(outs).numerator == 1 and benign_block_rate(outs).denominator == 3
    done = task_completion_rate(outs)
    assert (done.numerator, done.denominator, done.unknown) == (2, 3, 1)


def test_generalization_gap_sign_and_components():
    familiar = [outcome(True, success=False)] * 4
    heldout = [outcome(True, success=True), outcome(True, success=False)]
    gap = generalization_gap(familiar, heldout)
    assert gap.familiar_asr.rate == 0.0 and gap.heldout_asr.rate == 0.5
    assert gap.gap == pytest.approx(0.5)  # positive = held-out is worse
    assert generalization_gap(heldout, familiar).gap == pytest.approx(-0.5)


def test_generalization_gap_is_none_when_a_side_is_empty():
    assert generalization_gap([], [outcome(True, success=True)]).gap is None


def test_wilson_interval_contains_the_estimate():
    low, high = RateResult(3, 10).wilson_95
    assert low < 0.3 < high and 0 <= low and high <= 1
    low, high = RateResult(0, 5).wilson_95
    assert low == 0.0 and high > 0.3  # tiny samples give wide intervals


def test_operational_stats_p95_needs_enough_observations():
    few = operational_stats([outcome(False, latency=v) for v in (1, 2, 3)])
    assert few.median_ms == 2 and few.mean_ms == 2 and few.p95_ms is None
    many = operational_stats([outcome(False, latency=float(v), calls=2) for v in range(1, 101)])
    assert many.p95_ms == 95.0 and many.mean_model_calls == 2


def test_operational_stats_empty():
    assert operational_stats([]).mean_ms is None
    assert not math.isnan(operational_stats([outcome(False, status="error")]).n)
