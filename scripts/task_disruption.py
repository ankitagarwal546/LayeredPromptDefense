"""Task-disruption measure for saved runs (separate from attack success; exploratory, defined post hoc).

    python scripts/task_disruption.py <run_id> [<run_id> ...] [--review docs/results/human_review_decisions.csv]

For each run writes results/<run_id>/analysis/task_disruption.csv (per configuration) and
task_disruption_cases.csv (per outcome, no model text), and prints how often the automatic rule agrees with
human task_disrupted labels where those exist. Human labels then override the rule.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.config import Settings  # noqa: E402
from injection_defense.evaluation.dataset import load_cases  # noqa: E402
from injection_defense.evaluation.disruption import (  # noqa: E402
    CATEGORIES, classify, load_criteria, load_overrides, summarize,
)
from injection_defense.evaluation.store import load_outcomes, run_folder  # noqa: E402


def fmt(rate) -> str:
    if rate.percent is None:
        return "n/a (0)"
    low, high = rate.wilson_95
    return f"{rate.percent:.1f}% ({rate.numerator}/{rate.denominator}) [{100 * low:.0f}-{100 * high:.0f}]"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_ids", nargs="+")
    parser.add_argument("--review", default=None, help="review CSV with a task_disrupted column")
    parser.add_argument("--results-dir", default=None)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    settings = Settings()
    results_dir = Path(args.results_dir) if args.results_dir else settings.results_dir
    data_dir = Path(args.data_dir) if args.data_dir else settings.data_dir
    criteria = load_criteria(data_dir / "task_disruption_carriers.json")
    cases = {c.case_id: c for f in sorted(data_dir.glob("*.jsonl")) for c in load_cases(f)}
    overrides = load_overrides(args.review) if args.review else {}

    for run_id in args.run_ids:
        folder = run_folder(results_dir, run_id)
        model = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))["model"]["name"]
        attacks = [o for o in load_outcomes(folder) if o.is_attack]
        automatic = [classify(o, cases[o.case_id], criteria) for o in attacks]
        final = [classify(o, cases[o.case_id], criteria, overrides) for o in attacks]

        checked = [(a, f) for a, f in zip(automatic, final) if f.source == "human"]
        agree = sum(1 for a, f in checked if a.category == f.category)
        print(f"\n=== run {run_id} ({model}); exploratory, post-hoc measure")
        if checked:
            print(f"rule vs human task_disrupted labels: agree on {agree}/{len(checked)} outcomes")
            for a, f in checked:
                if a.category != f.category:
                    print(f"  disagree: {f.outcome.experiment}/t{f.outcome.trial} {f.outcome.case_id}: rule={a.category} ({a.reason}), human={f.category}")

        by_exp: dict[str, list] = defaultdict(list)
        for c in final:
            by_exp[c.outcome.experiment].append(c)
        rows = []
        for exp, cs in by_exp.items():
            s = summarize(cs)
            rows.append({"experiment": exp, **{k: s.counts.get(k, 0) for k in CATEGORIES},
                         "task_disruption": fmt(s.task_disruption), "usable_on_attack": fmt(s.usable_on_attack),
                         "decided_by_human": sum(1 for c in cs if c.source == "human")})
        out = folder / "analysis"
        out.mkdir(exist_ok=True)
        with (out / "task_disruption.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with (out / "task_disruption_cases.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["experiment", "trial", "case_id", "attack_family", "category", "source", "reason"])
            for c in final:
                o = c.outcome
                writer.writerow([o.experiment, o.trial, o.case_id, o.attack_family, c.category, c.source, c.reason])
        print(f"{'exp':5}" + "".join(f"{k:>17}" for k in CATEGORIES) + "   task disruption | usable summary on attack docs")
        for r in rows:
            print(f"{r['experiment']:5}" + "".join(f"{r[k]:>17}" for k in CATEGORIES) + f"   {r['task_disruption']} | {r['usable_on_attack']}")
        print(f"wrote {out / 'task_disruption.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
