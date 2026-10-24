"""Run experiments with a plan, cost guard, checkpointing and resume.

    python scripts/run_experiments.py --case-set dev --configs E0,E1 --dry-run
    python scripts/run_experiments.py --case-set dev --configs E0,E1,E2,E4 --real --yes
    python scripts/run_experiments.py --case-set final --final-ack --real --yes   # spends the held-out set
    python scripts/run_experiments.py --resume <run_id> --case-set dev --configs E0,E1 --real --yes

Results go to results/<run_id>/ (never overwritten). --dry-run validates everything and makes no
model calls. A real-model run prints its estimated call count and needs --yes (or an interactive
confirmation) before anything is sent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.config import PRESETS, Settings  # noqa: E402
from injection_defense.defenses.classifier import UnavailableClassifier, create_classifier  # noqa: E402
from injection_defense.evaluation.execute import execute_run, resolve_configs  # noqa: E402
from injection_defense.evaluation.registry import CASE_SETS, build_case_set, estimate_model_calls  # noqa: E402
from injection_defense.evaluation.report import summary_table  # noqa: E402
from injection_defense.evaluation.runner import evidence_status, experiment_unavailable_reason  # noqa: E402
from injection_defense.evaluation.store import load_outcomes  # noqa: E402
from injection_defense.llm.base import ModelNotConfiguredError  # noqa: E402
from injection_defense.llm.mock import MockLLM  # noqa: E402
from injection_defense.llm.provider import create_real_llm_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case-set", choices=CASE_SETS, default="dev")
    parser.add_argument("--configs", "--config", dest="configs", default="E0,E1,E2,E4",
                        help=f"comma-separated presets from {sorted(PRESETS)}")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--real", action="store_true", help="use the configured real model (external calls)")
    parser.add_argument("--yes", action="store_true", help="confirm external model calls non-interactively")
    parser.add_argument("--final-ack", action="store_true", help="acknowledge that --case-set final spends the held-out set")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit; no model calls")
    parser.add_argument("--resume", metavar="RUN_ID", help="continue an interrupted run")
    parser.add_argument("--out", default=None, help="results directory (default: results/)")
    args = parser.parse_args()

    settings = Settings()
    results_dir = Path(args.out) if args.out else settings.results_dir
    names = [n for n in args.configs.split(",") if n]
    try:
        configs = resolve_configs(names)
        case_set = build_case_set(args.case_set, settings.data_dir)
        llm = create_real_llm_client(settings) if args.real else MockLLM()
    except (ValueError, ModelNotConfiguredError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.case_set in ("final", "independent") and not args.final_ack:
        print(f"error: --case-set {args.case_set} uses frozen test files; pass --final-ack to proceed.", file=sys.stderr)
        return 2

    classifier = create_classifier(settings) if any(c.classifier for c in configs.values()) else None
    runnable = [n for n, c in configs.items() if not experiment_unavailable_reason(c, classifier)]
    estimate = estimate_model_calls({n: configs[n] for n in runnable}, len(case_set.cases), args.repetitions)

    print("PLAN")
    print(f"  case set        : {case_set.name} ({len(case_set.cases)} cases; held-out families: {sorted(case_set.heldout_families) or 'none'})")
    print(f"  experiments     : {', '.join(names)}")
    for n in names:
        if n not in runnable:
            print(f"    {n}: NOT_RUN ({experiment_unavailable_reason(configs[n], classifier)})")
    print(f"  model           : {llm.provider}/{llm.model_name} ({'MOCK' if llm.is_mock else 'REAL'})")
    if classifier is not None:
        clf_model = getattr(getattr(classifier, "llm", None), "model_name", None)
        print(f"  classifier      : {'unavailable' if isinstance(classifier, UnavailableClassifier) else clf_model}")
    print(f"  repetitions     : {args.repetitions}")
    print(f"  model calls     : up to {estimate:,} ({'EXTERNAL' if not llm.is_mock else 'none: mock'})")
    print(f"  evidence label  : {evidence_status(llm.is_mock, {c.provenance for c in case_set.cases})}")
    if args.dry_run:
        print("\n(dry run: nothing executed)")
        return 0

    if not llm.is_mock and not args.yes:
        if not sys.stdin.isatty():
            print("error: real-model run needs --yes (or an interactive terminal).", file=sys.stderr)
            return 2
        if input(f"\nSend up to {estimate:,} calls to the real model? [y/N] ").strip().lower() != "y":
            print("cancelled")
            return 1

    total = len(case_set.cases) * args.repetitions * len(runnable)
    step = max(1, total // 20)

    def progress(done: int) -> None:
        if done % step == 0 or done == total:
            print(f"  {done}/{total}", flush=True)

    try:
        folder = execute_run(case_set=case_set, experiment_names=names, llm=llm, classifier=classifier,
                             repetitions=args.repetitions, results_dir=results_dir, run_id=args.resume,
                             resume=bool(args.resume), progress=progress)
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(f"\ninterrupted; resume with --resume {args.resume or '<run_id from the results folder>'}", file=sys.stderr)
        return 130

    outcomes = load_outcomes(folder)
    grouped: dict[str, list] = {}
    for o in outcomes:
        grouped.setdefault(o.experiment, []).append(o)
    print(f"\nrun folder: {folder}")
    print(summary_table(grouped, case_set.heldout_families).to_string(index=False))
    print("\nNext: python scripts/analyze_results.py", folder.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
