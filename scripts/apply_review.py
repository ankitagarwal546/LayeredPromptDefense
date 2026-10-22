"""Apply human decisions from review_decisions.csv as manual labels.

    python scripts/apply_review.py results/review/review_decisions.csv [--dry-run]

Each row with human_label yes/no and a reviewer name appends a label (adjudicator "human: <name>") for every outcome
in that group, overriding the earlier AI label (last label wins; the AI labels stay in the file for the record).
Blank rows are skipped. Re-run analyze_results.py afterwards.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.config import Settings  # noqa: E402
from injection_defense.evaluation.store import append_label, load_outcomes, run_folder  # noqa: E402
from prepare_review import group_id  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path")
    parser.add_argument("--results-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    results_dir = Path(args.results_dir) if args.results_dir else Settings().results_dir
    rows = list(csv.DictReader(Path(args.csv_path).open(encoding="utf-8")))

    problems = [f"item {r['item']}: human_label must be yes, no or blank (got {r['human_label']!r})"
                for r in rows if r["human_label"].strip().lower() not in ("", "yes", "no")]
    problems += [f"item {r['item']}: reviewer name is required when a verdict is given"
                 for r in rows if r["human_label"].strip() and not r["reviewer"].strip()]
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2

    applied = skipped = changed = 0
    for r in rows:
        verdict = r["human_label"].strip().lower()
        if not verdict:
            skipped += 1
            continue
        folder = run_folder(results_dir, r["run_id"])
        members = [o for o in load_outcomes(folder)
                   if o.is_attack and o.case_id == r["case_id"] and o.scoring == "needs_review"
                   and group_id(r["run_id"], o.case_id, o.output_text or "") == r["group_id"]]
        if not members:
            print(f"item {r['item']}: no matching outcomes in run {r['run_id']} (group changed?)", file=sys.stderr)
            return 2
        want = verdict == "yes"
        changed += sum(1 for o in members if o.manual_label is not None and o.manual_label != want)
        if not args.dry_run:
            for o in members:
                append_label(folder, o, want, f"human: {r['reviewer'].strip()}", r["note"].strip())
        applied += len(members)
    print(f"{'would apply' if args.dry_run else 'applied'} {applied} outcome label(s) from {len(rows) - skipped} item(s); "
          f"{skipped} blank item(s) skipped; {changed} outcome(s) change the AI label")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
