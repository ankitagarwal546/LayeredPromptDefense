"""Smoke evaluation: run E0-E5 over the development fixtures and print a summary table.

Default is the mock model, which makes this a check that the plumbing works. The numbers it
prints are NOT evidence about LLM security. Use --real only with explicit configuration
(see .env.example); that run calls a paid API.

    python scripts/run_smoke_eval.py [--real] [--dataset PATH] [--heldout-families a,b]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.config import PRESETS, Settings  # noqa: E402
from injection_defense.defenses.classifier import create_classifier
from injection_defense.evaluation.dataset import load_cases
from injection_defense.evaluation.report import plot_security_vs_utility, summary_table
from injection_defense.evaluation.runner import run_matrix, save_run
from injection_defense.evaluation.splits import split_by_family
from injection_defense.llm.base import ModelNotConfiguredError
from injection_defense.llm.mock import MockLLM
from injection_defense.llm.provider import create_real_llm_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default=str(ROOT / "data" / "dev_cases.jsonl"))
    parser.add_argument("--real", action="store_true", help="use the configured real LLM (paid API calls)")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--experiments", default=",".join(PRESETS), help="comma-separated preset ids, e.g. E0")
    parser.add_argument("--heldout-dataset", nargs="+", default=[],
                        help="held-out JSONL file(s); their attack families become the held-out group, "
                             "and only their benign cases are used (dev benign data was used for tuning)")
    parser.add_argument("--heldout-families", default="obfuscated,distributed",
                        help="only used without --heldout-dataset (mechanics demo on dev data)")
    parser.add_argument("--out", default=str(ROOT / "results"))
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    try:
        llm = create_real_llm_client(settings) if args.real else MockLLM()
    except ModelNotConfiguredError as exc:
        print(f"error: {exc}. Configure .env (see .env.example) or run without --real.", file=sys.stderr)
        return 2

    cases = load_cases(args.dataset)
    if args.heldout_dataset:
        held = [c for path in args.heldout_dataset for c in load_cases(path)]
        heldout = {c.attack_family for c in held if c.is_attack}
        if overlap := heldout & {c.attack_family for c in cases if c.is_attack}:
            print(f"error: held-out families also appear in the dev set: {sorted(overlap)}", file=sys.stderr)
            return 2
        cases = [c for c in cases if c.is_attack] + held
        heldout_note = "held-out families from --heldout-dataset (dev benign cases excluded)"
    else:
        heldout = {f for f in args.heldout_families.split(",") if f}
        split_by_family(cases, heldout)  # validates the family names against the data
        heldout_note = "held-out families (mechanics demo only)"
    chosen = [e for e in args.experiments.split(",") if e]
    if unknown := [e for e in chosen if e not in PRESETS]:
        print(f"error: unknown experiment(s) {unknown}; choose from {sorted(PRESETS)}", file=sys.stderr)
        return 2
    result = run_matrix(
        {name: PRESETS[name] for name in chosen}, cases, llm=llm, classifier=create_classifier(settings),
        repetitions=args.repetitions, dataset_path=args.dataset,
        extra_dataset_paths=args.heldout_dataset,
    )
    folder = save_run(result, args.out)

    banner = result.metadata["evidence_status"]
    print(f"\n*** {banner} ***")
    print(f"run_id={result.metadata['run_id']} model={llm.model_name} cases={len(cases)} "
          f"{heldout_note}={sorted(heldout)}\n")
    table = summary_table(result.by_experiment(), heldout)
    print(table.to_string(index=False))
    for name, reason in result.unavailable.items():
        print(f"\n{name}: UNAVAILABLE, no results produced ({reason})")
    if args.plot:
        png = plot_security_vs_utility(
            result.by_experiment(), folder / "security_vs_utility.png",
            watermark=banner if banner.startswith("SMOKE") else None,
        )
        print(f"\nplot: {png}")
    print(f"\nsaved: {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
