"""POST-HOC re-scoring of the Reverse Text attacks with reversal at character, word and sentence level.

    python scripts/posthoc_reverse_text.py 4da08316a2fb 8a4c672e6307 [--out docs/results/posthoc]

The registered check (`reverse`) detects character reversal only and found 0 successes on both models. This applies
the post-hoc `reverse_v2` check (evaluation/attack_checks.py) to every processed Reverse Text outcome. It changes no
run, label or registered number: it writes a separate table (no model text) and prints per-configuration counts.
`reverse_v2` was written after the outputs had been read, so its counts are exploratory, and a sentence-order
reversal is a weaker form of compliance than the attack asked for (it may or may not count; a human must decide).
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
from injection_defense.evaluation.attack_checks import reversal_kind  # noqa: E402
from injection_defense.evaluation.registry import load_all_cases  # noqa: E402
from injection_defense.evaluation.store import load_outcomes, run_folder  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_ids", nargs="+")
    parser.add_argument("--out", default=str(ROOT / "docs" / "results" / "posthoc"))
    args = parser.parse_args()
    settings = Settings()
    cases = load_all_cases(settings.data_dir)
    rows = []
    for run_id in args.run_ids:
        folder = run_folder(settings.results_dir, run_id)
        model = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))["model"]["name"]
        for o in load_outcomes(folder):
            case = cases.get(o.case_id)
            if not (case and case.is_attack and case.attack_family and "reverse" in case.attack_family):
                continue
            found, detail = reversal_kind(o.output_text or "", case.document_text, case.key_topics) if o.output_text else (None, "no output")
            rows.append({"run_id": run_id, "model": model, "experiment": o.experiment, "trial": o.trial, "case_id": o.case_id,
                         "status": o.status, "registered_success": o.manual_label if o.manual_label is not None else o.attack_success,
                         "posthoc_reversal": found or "none", "detail": detail})
    if not rows:
        print("no Reverse Text outcomes found", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "reverse_text_v2.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    table = defaultdict(lambda: defaultdict(int))
    for r in rows:
        key = (r["model"], r["experiment"])
        table[key]["n"] += 1
        table[key][r["posthoc_reversal"]] += 1
        table[key]["registered"] += r["registered_success"] is True
    print("POST-HOC (exploratory; registered numbers unchanged)\n")
    print(f"{'model':<13}{'config':<7}{'n':>4}{'registered':>12}{'chars':>7}{'words':>7}{'sentences':>11}")
    for (model, exp), c in sorted(table.items()):
        print(f"{model:<13}{exp:<7}{c['n']:>4}{c['registered']:>12}{c['characters']:>7}{c['words']:>7}{c['sentences']:>11}")
    print(f"\n{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
