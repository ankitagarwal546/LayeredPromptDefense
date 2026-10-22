"""Summary tables (pandas) and plots (matplotlib) over a RunResult."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from injection_defense.evaluation import metrics as m
from injection_defense.evaluation.metrics import CaseOutcome, RateResult


def watermark_text(evidence_status: str) -> str | None:
    """Short chart label for runs that are not candidate evidence (None otherwise)."""
    if evidence_status.startswith("SMOKE"):
        return "SMOKE TEST ONLY: not evidence"
    if evidence_status.startswith("PRELIMINARY"):
        return "PRELIMINARY: synthetic data, small n"
    return None


def _fmt(rate: RateResult) -> str:
    return "n/a (0 evaluated)" if rate.percent is None else f"{rate.percent:.1f}% ({rate.numerator}/{rate.denominator})"


def _bounds(outcomes: list[CaseOutcome]) -> str:
    b = m.asr_sensitivity(outcomes)
    if b.lower is None:
        return "n/a"
    return f"{100 * b.lower:.1f}-{100 * b.upper:.1f}% (all {b.n_attacks} attacks)"


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
            "ASR_bounds": _bounds(outcomes),
            "detection_rate": _fmt(m.detection_rate(outcomes)),
            "FPR": _fmt(m.false_positive_rate(outcomes)),
            "benign_blocked": _fmt(m.benign_block_rate(outcomes)),
            "task_completion": _fmt(m.task_completion_rate(outcomes)),
            "mean_ms": None if ops.mean_ms is None else round(ops.mean_ms, 2),
            "median_ms": None if ops.median_ms is None else round(ops.median_ms, 2),
            "p95_ms": ops.p95_ms if ops.p95_ms is None else round(ops.p95_ms, 2),
            "model_calls": None if ops.mean_model_calls is None else round(ops.mean_model_calls, 2),
            "model_failures": _fmt(m.technical_failure_rate(outcomes)),
            "detector_failures": m.detector_failure_count(outcomes),
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


def family_table(outcomes: list[CaseOutcome]) -> pd.DataFrame:
    """ASR per experiment and attack family, with denominators and unresolved counts."""
    rows = []
    for experiment in sorted({o.experiment for o in outcomes}):
        for family in sorted({o.attack_family for o in outcomes if o.is_attack}):
            subset = [o for o in outcomes if o.experiment == experiment and o.attack_family == family]
            asr = m.attack_success_rate(subset)
            rows.append({"experiment": experiment, "attack_family": family, "ASR": _fmt(asr),
                         "successes": asr.numerator, "evaluated": asr.denominator, "unresolved": asr.unknown})
    return pd.DataFrame(rows)


def _finish_plot(fig, path: str | Path, watermark: str | None) -> Path:
    import matplotlib.pyplot as plt

    if watermark:
        fig.text(0.5, 0.5, watermark, ha="center", va="center", rotation=25, alpha=0.2, fontsize=16, color="red")
    fig.tight_layout()
    path = Path(path)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _bars(labels: list[str], series: dict[str, list[float | None]], ylabel: str, title: str, path, watermark):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4.2))
    width = 0.8 / max(len(series), 1)
    for i, (name, values) in enumerate(series.items()):
        xs = [x + i * width for x in range(len(labels))]
        ax.bar(xs, [0 if v is None else v for v in values], width, label=name)
        for x, v in zip(xs, values):
            ax.text(x, 1 if v is None else v + 0.5, "n/a" if v is None else f"{v:.0f}", ha="center", fontsize=7)
    ax.set_xticks([x + width * (len(series) - 1) / 2 for x in range(len(labels))], labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if len(series) > 1:
        ax.legend()
    return _finish_plot(fig, path, watermark)


def plot_fpr(by_experiment: dict[str, list[CaseOutcome]], path, watermark: str | None = None) -> Path:
    names = list(by_experiment)
    pct = lambda r: None if r.percent is None else r.percent  # noqa: E731
    series = {"FPR (flagged)": [pct(m.false_positive_rate(by_experiment[n])) for n in names],
              "benign blocked": [pct(m.benign_block_rate(by_experiment[n])) for n in names]}
    return _bars(names, series, "% of benign cases", "False positives and blocked benign cases", path, watermark)


def plot_generalization(by_experiment: dict[str, list[CaseOutcome]], heldout_families: set[str], path,
                        watermark: str | None = None) -> Path:
    names = list(by_experiment)
    fam, held = [], []
    for n in names:
        outs = by_experiment[n]
        g = m.generalization_gap([o for o in outs if o.attack_family not in heldout_families],
                                 [o for o in outs if o.attack_family in heldout_families])
        fam.append(g.familiar_asr.percent)
        held.append(g.heldout_asr.percent)
    return _bars(names, {"familiar attacks": fam, "held-out attacks": held}, "ASR (%)",
                 "Attack success: familiar vs held-out families", path, watermark)


def plot_latency(by_experiment: dict[str, list[CaseOutcome]], path, watermark: str | None = None) -> Path:
    names = list(by_experiment)
    stats = [m.operational_stats(by_experiment[n]) for n in names]
    return _bars(names, {"mean": [s.mean_ms for s in stats], "median": [s.median_ms for s in stats]},
                 "latency (ms)", "Per-request latency (includes all layers)", path, watermark)


def markdown_report(metadata: dict, by_experiment: dict[str, list[CaseOutcome]], pending: int) -> str:
    heldout = set(metadata.get("heldout_families", []))
    table = summary_table(by_experiment, heldout)
    lines = [
        f"# Run {metadata['run_id']}", "",
        f"**Evidence status:** {metadata['evidence_status']}", "",
        f"- model: `{metadata['model']['name']}` (mock: {metadata['model']['is_mock']}), params {metadata['model']['generation_params']}",
        f"- case set: {metadata.get('case_set', '?')}; cases: {metadata['dataset']['n_cases']}; repetitions: {metadata['repetitions']}",
        f"- dataset sha256: `{metadata['dataset']['sha256']}`; started {metadata['started_at']}; finished {metadata.get('finished_at', 'n/a')}",
        f"- held-out families: {sorted(heldout) or 'none'}",
        f"- outcomes awaiting manual review: **{pending}** (excluded from the ASR denominator; see ASR_bounds)", "",
    ]
    for name, reason in metadata.get("unavailable_experiments", {}).items():
        lines.append(f"- **{name}: NOT RUN.** {reason}")
    lines += ["", "## Summary", "", table.to_markdown(index=False) if hasattr(table, "to_markdown") and _has_tabulate() else "```\n" + table.to_string(index=False) + "\n```", ""]
    return "\n".join(lines)


def _has_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401
    except ImportError:
        return False
    return True
