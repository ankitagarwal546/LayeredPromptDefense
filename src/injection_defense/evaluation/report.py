"""Summary tables (pandas) and plots (matplotlib) over a RunResult."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from injection_defense.evaluation import metrics as m
from injection_defense.evaluation.metrics import CaseOutcome, RateResult


def _fmt(rate: RateResult) -> str:
    return "n/a (0 evaluated)" if rate.percent is None else f"{rate.percent:.1f}% ({rate.numerator}/{rate.denominator})"


def summary_table(
    by_experiment: dict[str, list[CaseOutcome]], heldout_families: set[str] | None = None
) -> pd.DataFrame:
    heldout_families = heldout_families or set()
    rows = []
    for name, outcomes in by_experiment.items():
        familiar = [o for o in outcomes if o.is_attack and o.attack_family not in heldout_families]
        heldout = [o for o in outcomes if o.is_attack and o.attack_family in heldout_families]
        asr, ops = m.attack_success_rate(outcomes), m.operational_stats(outcomes)
        row = {
            "experiment": name,
            "ASR": _fmt(asr),
            "ASR_unknown": asr.unknown,
            "detection_rate": _fmt(m.detection_rate(outcomes)),
            "FPR": _fmt(m.false_positive_rate(outcomes)),
            "benign_blocked": _fmt(m.benign_block_rate(outcomes)),
            "task_completion": _fmt(m.task_completion_rate(outcomes)),
            "mean_ms": None if ops.mean_ms is None else round(ops.mean_ms, 2),
            "median_ms": None if ops.median_ms is None else round(ops.median_ms, 2),
            "p95_ms": ops.p95_ms if ops.p95_ms is None else round(ops.p95_ms, 2),
            "model_calls": None if ops.mean_model_calls is None else round(ops.mean_model_calls, 2),
        }
        if heldout_families:
            gap = m.generalization_gap(familiar, heldout)
            row.update(
                ASR_familiar=_fmt(gap.familiar_asr),
                ASR_heldout=_fmt(gap.heldout_asr),
                gen_gap="n/a" if gap.gap is None else f"{100 * gap.gap:+.1f} pts",
            )
        rows.append(row)
    return pd.DataFrame(rows)


def plot_security_vs_utility(
    by_experiment: dict[str, list[CaseOutcome]], path: str | Path, *, watermark: str | None = None
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4.5))
    for name, outcomes in by_experiment.items():
        asr, util = m.attack_success_rate(outcomes).rate, m.task_completion_rate(outcomes).rate
        if asr is None or util is None:
            continue
        ax.scatter(util * 100, asr * 100)
        ax.annotate(name, (util * 100, asr * 100), textcoords="offset points", xytext=(5, 5))
    ax.set_xlabel("Benign task completion (%)")
    ax.set_ylabel("Attack success rate (%)")
    ax.set_title("Security vs. utility")
    if watermark:
        fig.text(0.5, 0.5, watermark, ha="center", va="center", rotation=25, alpha=0.25, fontsize=14, color="red")
    fig.tight_layout()
    path = Path(path)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
