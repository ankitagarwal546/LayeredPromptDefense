"""Run persistence: incremental writes, resume, manual labels, and safe listing.

A run lives in <results_dir>/<run_id>/ with metadata.json, outcomes.jsonl (one line per case,
appended as it completes) and optional manual_labels.jsonl. Runs are never overwritten.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from injection_defense.evaluation.metrics import CaseOutcome

RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
_FIELDS = {f.name for f in dataclasses.fields(CaseOutcome)}


def valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id))


def run_folder(results_dir: Path, run_id: str) -> Path:
    if not valid_run_id(run_id):
        raise ValueError("invalid run id")
    return results_dir / run_id


class RunWriter:
    """Create (or reopen) a run folder and append outcomes as they complete."""

    def __init__(self, results_dir: Path, run_id: str, *, resume: bool = False):
        self.folder = run_folder(results_dir, run_id)
        exists = self.folder.exists()
        if exists and not resume:
            raise FileExistsError(f"run {run_id} already exists; pass resume=True to continue it")
        if resume and not exists:
            raise FileNotFoundError(f"cannot resume: run {run_id} not found")
        self.folder.mkdir(parents=True, exist_ok=True)
        self._outcomes = self.folder / "outcomes.jsonl"

    def write_metadata(self, metadata: dict) -> None:
        (self.folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def read_metadata(self) -> dict:
        return json.loads((self.folder / "metadata.json").read_text(encoding="utf-8"))

    def append(self, outcome: CaseOutcome) -> None:
        with self._outcomes.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dataclasses.asdict(outcome)) + "\n")

    def completed_keys(self) -> set[tuple[str, int, str]]:
        return {(o.experiment, o.trial, o.case_id) for o in load_outcomes(self.folder, apply_labels=False)}


def load_outcomes(folder: Path, *, apply_labels: bool = True) -> list[CaseOutcome]:
    path = folder / "outcomes.jsonl"
    if not path.exists():
        return []
    outcomes = [
        CaseOutcome(**{k: v for k, v in json.loads(line).items() if k in _FIELDS})
        for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if apply_labels:
        labels = load_labels(folder)
        for o in outcomes:
            o.manual_label = labels.get((o.experiment, o.trial, o.case_id), o.manual_label)
    return outcomes


def load_labels(folder: Path) -> dict[tuple[str, int, str], bool]:
    path = folder / "manual_labels.jsonl"
    labels: dict[tuple[str, int, str], bool] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                labels[(r["experiment"], r["trial"], r["case_id"])] = r["attack_success"]  # last wins
    return labels


def append_label(folder: Path, outcome: CaseOutcome, attack_success: bool, adjudicator: str, reason: str = "") -> None:
    record = {"experiment": outcome.experiment, "trial": outcome.trial, "case_id": outcome.case_id,
              "attack_success": attack_success, "adjudicator": adjudicator, "reason": reason}
    with (folder / "manual_labels.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def pending_review(outcomes: list[CaseOutcome]) -> list[CaseOutcome]:
    return [o for o in outcomes if o.is_attack and o.scoring == "needs_review" and o.manual_label is None]


def list_runs(results_dir: Path) -> list[dict]:
    """Run summaries, newest first. Only reads folders whose names are valid run ids."""
    runs = []
    if results_dir.exists():
        for folder in results_dir.iterdir():
            if folder.is_dir() and valid_run_id(folder.name) and (folder / "metadata.json").exists():
                meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
                runs.append({
                    "run_id": folder.name,
                    "started_at": meta.get("started_at"),
                    "model": meta.get("model", {}).get("name"),
                    "model_is_mock": meta.get("model", {}).get("is_mock"),
                    "evidence_status": meta.get("evidence_status"),
                    "experiments": sorted(meta.get("configs", {})),
                    "unavailable": meta.get("unavailable_experiments", {}),
                })
    return sorted(runs, key=lambda r: r["started_at"] or "", reverse=True)
