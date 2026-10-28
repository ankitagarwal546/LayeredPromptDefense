"""Aggregate filled-in summary-quality ratings by model and configuration (task R5). Changes no run.

    python scripts/summarize_quality.py results/quality_rating

Reads <kit>/ratings.csv and <kit>_key/rating_key.csv (written by prepare_quality_rating.py), validates every filled
row, and writes <kit>_key/quality_summary.md and quality_summary.csv: per model x configuration the number rated,
mean faithfulness and coverage (1-5) and the share judged usable with a Wilson 95% interval. Unrated items are
counted, never treated as good or bad. Outcomes that had no summary (blocked/failed) are listed from kit.json.
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

from injection_defense.evaluation.metrics import RateResult  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kit")
    args = parser.parse_args()
    kit = Path(args.kit)
    key_dir = kit.parent / f"{kit.name}_key"
    ratings = list(csv.DictReader((kit / "ratings.csv").open(encoding="utf-8")))
    key = {r["blind_id"]: r for r in csv.DictReader((key_dir / "rating_key.csv").open(encoding="utf-8"))}

    problems, rated = [], []
    for r in ratings:
        filled = [r[k].strip() for k in ("faithful", "coverage", "usable")]
        if not any(filled):
            continue
        if not all(filled):
            problems.append(f"{r['blind_id']}: fill in faithful, coverage and usable together")
        elif r["faithful"].strip() not in "12345" or r["coverage"].strip() not in "12345" or len(r["faithful"].strip()) != 1 or len(r["coverage"].strip()) != 1:
            problems.append(f"{r['blind_id']}: faithful and coverage must be 1-5")
        elif r["usable"].strip().lower() not in ("yes", "no"):
            problems.append(f"{r['blind_id']}: usable must be yes or no")
        elif not r["rater"].strip():
            problems.append(f"{r['blind_id']}: rater name is required")
        elif r["blind_id"] not in key:
            problems.append(f"{r['blind_id']}: not in the key")
        else:
            rated.append(r)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    if not rated:
        print("no ratings yet: fill in ratings.csv first", file=sys.stderr)
        return 1

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rated:
        k = key[r["blind_id"]]
        groups[(k["model"], k["experiment"])].append(r)
    totals = defaultdict(int)
    for k in key.values():
        totals[(k["model"], k["experiment"])] += 1
    rows = []
    for (model, exp) in sorted(totals):
        rs = groups.get((model, exp), [])
        usable = RateResult(sum(r["usable"].strip().lower() == "yes" for r in rs), len(rs))
        ci = usable.wilson_95  # a property
        rows.append({"model": model, "config": exp, "items": totals[(model, exp)], "rated": len(rs),
                     "faithful_mean": round(sum(int(r["faithful"]) for r in rs) / len(rs), 2) if rs else "",
                     "coverage_mean": round(sum(int(r["coverage"]) for r in rs) / len(rs), 2) if rs else "",
                     "usable": f"{usable.numerator}/{usable.denominator}",
                     "usable_ci95": f"[{100 * ci[0]:.0f}%, {100 * ci[1]:.0f}%]" if ci else ""})
    with (key_dir / "quality_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    kit_meta = json.loads((key_dir / "kit.json").read_text(encoding="utf-8"))
    raters = sorted({r["rater"].strip() for r in rated})
    lines = ["# Summary-quality ratings", "", f"Rater(s): {', '.join(raters)}. {len(rated)} of {len(key)} items rated; "
             f"{len(kit_meta.get('not_rateable', []))} outcome(s) had no summary to rate (listed in kit.json). Blinded to model and configuration.", "",
             "| model | config | items | rated | faithful (mean 1-5) | coverage (mean 1-5) | usable | usable 95% CI |", "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['model']} | {r['config']} | {r['items']} | {r['rated']} | {r['faithful_mean']} | {r['coverage_mean']} | {r['usable']} | {r['usable_ci95']} |" for r in rows]
    (key_dir / "quality_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rated)} rated item(s) by {', '.join(raters)}\n  {key_dir / 'quality_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
