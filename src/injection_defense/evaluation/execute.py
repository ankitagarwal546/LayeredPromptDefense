"""Run an experiment matrix with checkpointing: the single entry point used by the CLI and the API."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from injection_defense.config import PRESETS
from injection_defense.defenses.base import Detector
from injection_defense.evaluation.registry import CaseSet
from injection_defense.evaluation.runner import run_matrix
from injection_defense.evaluation.store import RunWriter
from injection_defense.llm.base import LLMClient


def resolve_configs(names: list[str]):
    unknown = [n for n in names if n not in PRESETS]
    if unknown:
        raise ValueError(f"Unknown experiment(s) {unknown}; choose from {sorted(PRESETS)}")
    return {n: PRESETS[n] for n in names}


def execute_run(
    *,
    case_set: CaseSet,
    experiment_names: list[str],
    llm: LLMClient,
    classifier: Detector | None,
    repetitions: int,
    results_dir: Path,
    run_id: str | None = None,
    resume: bool = False,
    progress: Callable[[int], None] | None = None,
) -> Path:
    """Execute and persist a run; returns its folder. With resume=True, completed
    (experiment, trial, case) triples are skipped and the new outcomes are appended."""
    configs = resolve_configs(experiment_names)
    run_id = run_id or uuid.uuid4().hex[:12]
    writer = RunWriter(results_dir, run_id, resume=resume)
    completed: set[tuple[str, int, str]] = set()
    if resume:
        completed = writer.completed_keys()

    done = len(completed)

    def on_outcome(outcome) -> None:
        nonlocal done
        writer.append(outcome)
        done += 1
        if progress:
            progress(done)

    def on_start(metadata: dict) -> None:
        if resume:
            old = writer.read_metadata()
            for key in ("dataset", "configs", "repetitions"):
                if old.get(key) != metadata.get(key) or old["model"]["name"] != metadata["model"]["name"]:
                    raise ValueError(f"cannot resume run {run_id}: {key} or model changed since it started")
            old.setdefault("resumed_at", []).append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
            writer.write_metadata(old)
        else:
            writer.write_metadata(metadata)

    first, *rest = case_set.files
    result = run_matrix(
        configs, case_set.cases, llm=llm, classifier=classifier, repetitions=repetitions,
        dataset_path=first, extra_dataset_paths=[str(p) for p in rest], heldout_families=case_set.heldout_families,
        run_id=run_id, completed=completed, on_outcome=on_outcome, on_start=on_start,
    )
    meta = writer.read_metadata()
    meta["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta["unavailable_experiments"] = result.metadata["unavailable_experiments"]
    meta["case_set"] = case_set.name
    writer.write_metadata(meta)
    return writer.folder
