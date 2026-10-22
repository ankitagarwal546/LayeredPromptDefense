"""Turn a saved run into tables and charts under results/<run_id>/analysis/.

    python scripts/analyze_results.py <run_id>

Applies manual labels (scripts/adjudicate.py) when present. Charts of mock or development-fixture
runs carry a watermark. Nothing is recomputed from the model: it only reads saved outcomes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.config import Settings  # noqa: E402
from injection_defense.evaluation import report  # noqa: E402
from injection_defense.evaluation.store import load_outcomes, pending_review, run_folder  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_id")
    parser.add_argument("--results-dir", default=None)
    args = parser.parse_args()
    results_dir = Path(args.results_dir) if args.results_dir else Settings().results_dir
    try:
        folder = run_folder(results_dir, args.run_id)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not (folder / "metadata.json").exists():
        print(f"error: no such run: {args.run_id}", file=sys.stderr)
        return 2

    import json

    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    outcomes = load_outcomes(folder)
    if not outcomes:
        print("error: the run has no outcomes", file=sys.stderr)
        return 2
    grouped: dict[str, list] = {}
    for o in outcomes:
        grouped.setdefault(o.experiment, []).append(o)
    heldout = set(metadata.get("heldout_families", []))
    out = folder / "analysis"
    out.mkdir(exist_ok=True)
    mark = metadata["evidence_status"] if metadata["evidence_status"].startswith(("SMOKE", "PRELIMINARY")) else None
    pending = len(pending_review(outcomes))

    report.summary_table(grouped, heldout).to_csv(out / "summary.csv", index=False)
    report.family_table(outcomes).to_csv(out / "by_family.csv", index=False)
    report.plot_security_vs_utility(grouped, out / "security_vs_utility.png", watermark=mark)
    report.plot_fpr(grouped, out / "fpr.png", watermark=mark)
    report.plot_latency(grouped, out / "latency.png", watermark=mark)
    if heldout:
        report.plot_generalization(grouped, heldout, out / "generalization.png", watermark=mark)
    (out / "report.md").write_text(report.markdown_report(metadata, grouped, pending), encoding="utf-8")

    print(f"evidence status: {metadata['evidence_status']}")
    print(f"wrote {out}")
    for path in sorted(out.iterdir()):
        print(f"  {path.name}")
    if pending:
        print(f"\n{pending} outcome(s) still need manual review: python scripts/adjudicate.py {args.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
