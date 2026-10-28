"""Compare a second, blinded reviewer with the first one (inter-rater agreement). Changes no run.

    python scripts/review_agreement.py results/blind_review

Reads <kit>/blind_decisions.csv (the second reviewer) and <kit>_key/blind_key.csv (the first reviewer's labels and
the mapping back to runs, written by prepare_blind_review.py). Agreement and Cohen's kappa are computed on items
both reviewers decided (yes/no), per item (one item = one unique output, which may cover several outcomes) and per
run. Writes <kit>_key/agreement.md and agreement.json, including every disagreement with its run and group id.
Disagreements are not applied anywhere: resolve them by discussion, record the outcome in docs/EXPERIMENT_LOG.md,
and only then decide (and log) whether any label changes.
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

from injection_defense.evaluation.review_kit import cohen_kappa  # noqa: E402

LABELS = ("yes", "no", "")


def stats(pairs: list[tuple[str, str]]) -> dict:
    both = [(a, b) for a, b in pairs if a and b]
    agree = sum(a == b for a, b in both)
    kappa = cohen_kappa(both)
    return {"items": len(pairs), "both_decided": len(both), "agree": agree,
            "agreement": round(agree / len(both), 4) if both else None, "kappa": round(kappa, 4) if kappa is not None else None,
            "first_yes_second_no": sum(1 for a, b in both if (a, b) == ("yes", "no")),
            "first_no_second_yes": sum(1 for a, b in both if (a, b) == ("no", "yes")),
            "unsure_first": sum(1 for a, _ in pairs if not a), "unsure_second": sum(1 for _, b in pairs if not b)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kit")
    args = parser.parse_args()
    kit = Path(args.kit)
    key_dir = kit.parent / f"{kit.name}_key"
    second = {r["blind_id"]: r for r in csv.DictReader((kit / "blind_decisions.csv").open(encoding="utf-8"))}
    key = {r["blind_id"]: r for r in csv.DictReader((key_dir / "blind_key.csv").open(encoding="utf-8"))}

    problems = [f"{bid}: human_label must be yes, no or blank (got {r['human_label']!r})"
                for bid, r in second.items() if r["human_label"].strip().lower() not in LABELS]
    problems += [f"{bid}: reviewer name is required when a verdict is given"
                 for bid, r in second.items() if r["human_label"].strip() and not r["reviewer"].strip()]
    problems += [f"{bid}: not in the key" for bid in second if bid not in key]
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    reviewers = sorted({r["reviewer"].strip() for r in second.values() if r["reviewer"].strip()})
    if not reviewers:
        print("no decisions yet: fill in blind_decisions.csv first", file=sys.stderr)
        return 1
    first_reviewers = sorted({k["first_reviewer"] for k in key.values() if k["first_reviewer"]})
    if set(reviewers) & set(first_reviewers):
        print(f"warning: the same name appears as first and second reviewer ({', '.join(set(reviewers) & set(first_reviewers))})", file=sys.stderr)

    pairs_by_run: dict[str, list[tuple[str, str]]] = defaultdict(list)
    disagreements = []
    for bid, k in key.items():
        a, b = k["first_label"], second[bid]["human_label"].strip().lower()
        pairs_by_run[f"{k['run_id']} ({k['model']})"].append((a, b))
        if a and b and a != b:
            disagreements.append({"blind_id": bid, "run_id": k["run_id"], "group_id": k["group_id"], "case_id": k["case_id"],
                                  "first": a, "second": b, "second_note": second[bid]["note"]})
    overall = stats([p for ps in pairs_by_run.values() for p in ps])
    result = {"second_reviewers": reviewers, "first_reviewers": first_reviewers, "overall": overall,
              "by_run": {run: stats(ps) for run, ps in sorted(pairs_by_run.items())}, "disagreements": disagreements}
    (key_dir / "agreement.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    def row(name, s):
        pct = f"{100 * s['agreement']:.1f}%" if s["agreement"] is not None else "n/a"
        kap = f"{s['kappa']:.2f}" if s["kappa"] is not None else "n/a"
        return (f"| {name} | {s['items']} | {s['both_decided']} | {s['agree']} ({pct}) | {kap} | "
                f"{s['first_yes_second_no']} / {s['first_no_second_yes']} | {s['unsure_first']} / {s['unsure_second']} |")
    lines = ["# Inter-rater agreement (blinded second review)", "",
             f"First reviewer(s): {', '.join(first_reviewers) or 'unknown'}; second reviewer(s): {', '.join(reviewers)}. "
             "Unit: one unique model output (it may cover several outcomes). Agreement and kappa use items both decided.", "",
             "| set | items | both decided | agree | Cohen's kappa | yes->no / no->yes | unsure (1st / 2nd) |",
             "|---|---|---|---|---|---|---|", row("all", overall)]
    lines += [row(run, s) for run, s in result["by_run"].items()]
    lines += ["", f"## Disagreements ({len(disagreements)})", "",
              "Not applied to any run. Resolve by discussion and log the outcome in docs/EXPERIMENT_LOG.md.", ""]
    lines += [f"- {d['blind_id']}: run `{d['run_id']}` group `{d['group_id']}`: first **{d['first']}**, second **{d['second']}**"
              + (f" ({d['second_note']})" if d["second_note"] else "") for d in disagreements]
    (key_dir / "agreement.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pct = f"{100 * overall['agreement']:.1f}%" if overall["agreement"] is not None else "n/a"
    print(f"{overall['both_decided']} items decided by both: agreement {pct}, kappa {overall['kappa']}; "
          f"{len(disagreements)} disagreement(s)\n  {key_dir / 'agreement.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
