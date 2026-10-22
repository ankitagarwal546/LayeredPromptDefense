"""Compare structural-prompt wordings on the DEVELOPMENT set only.

Refuses held-out files. Runs E0 (reference) and E2 with each variant, prints the table, and
applies the selection rule fixed in advance: highest benign task completion, ties broken by
lower ASR. Needs a real model (--real); the mock ignores prompt structure.

    python scripts/tune_structural.py --real [--variants v1,v2,v3] [--repetitions 2]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.config import DefenseConfig, Settings  # noqa: E402
from injection_defense.evaluation import metrics as m  # noqa: E402
from injection_defense.evaluation.dataset import load_cases  # noqa: E402
from injection_defense.evaluation.report import summary_table  # noqa: E402
from injection_defense.evaluation.runner import run_matrix, save_run  # noqa: E402
from injection_defense.llm.base import ModelNotConfiguredError  # noqa: E402
from injection_defense.llm.mock import MockLLM  # noqa: E402
from injection_defense.llm.provider import create_real_llm_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default=str(ROOT / "data" / "dev_cases.jsonl"))
    parser.add_argument("--variants", default="v1,v2,v3")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--real", action="store_true")
    args = parser.parse_args()

    if "heldout" in Path(args.dataset).name:
        print("error: refusing to tune on a held-out file.", file=sys.stderr)
        return 2
    try:
        llm = create_real_llm_client(Settings()) if args.real else MockLLM()
    except ModelNotConfiguredError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    variants = [v for v in args.variants.split(",") if v]
    configs = {"E0": DefenseConfig(name="E0")}
    configs.update({f"E2-{v}": DefenseConfig(name=f"E2-{v}", structural=True, structural_variant=v) for v in variants})
    result = run_matrix(configs, load_cases(args.dataset), llm=llm, repetitions=args.repetitions,
                        dataset_path=args.dataset)
    folder = save_run(result, ROOT / "results")
    print(f"\n*** {result.metadata['evidence_status']} ***")
    print(f"run_id={result.metadata['run_id']} model={llm.model_name} saved={folder}\n")
    print(summary_table(result.by_experiment())[
        ["experiment", "ASR", "ASR_unknown", "task_completion", "benign_blocked", "mean_ms"]].to_string(index=False))

    groups = result.by_experiment()

    def key(name: str) -> tuple[float, float]:
        outs = groups[name]
        util, asr = m.task_completion_rate(outs).rate or 0.0, m.attack_success_rate(outs).rate
        return (-util, 1.0 if asr is None else asr)

    best = min((f"E2-{v}" for v in variants), key=key)
    print(f"\nselection rule (max task completion, tie -> lower ASR) picks: {best}")
    print("Read the benign outputs before accepting this; refusals can hide behind a good-looking table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
