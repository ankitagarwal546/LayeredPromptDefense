"""Named case sets and call-count estimates, shared by the API and the CLIs.

Only datasets listed here can be selected; clients never supply file paths.
  dev    development fixtures (tuning allowed)
  final  dev attacks (familiar group) + held-out attacks + held-out benign cases. Use once, after
         freezing the code. Dev benign cases are excluded because they informed tuning.
  independent  BIPIA attack instructions inside human-written documents plus those documents as benign cases
         (data/independent/, built by scripts/build_independent_set.py). All attack families are new, so there is
         no "familiar" group. Use once, after freezing; never tune on it (docs/INDEPENDENT_SET.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from injection_defense.config import DefenseConfig
from injection_defense.evaluation.dataset import EvalCase, load_cases

DEV_FILE = "dev_cases.jsonl"
HELDOUT_FILES = ("heldout_attacks.jsonl", "heldout_benign.jsonl")
INDEPENDENT_FILES = ("independent/attacks.jsonl", "independent/benign.jsonl")
CASE_SETS = ("dev", "final", "independent")


@dataclass(frozen=True)
class CaseSet:
    name: str
    cases: list[EvalCase]
    heldout_families: set[str]
    files: list[Path]  # every file that contributed cases (for checksums)


def build_case_set(name: str, data_dir: Path) -> CaseSet:
    if name not in CASE_SETS:
        raise ValueError(f"Unknown case set {name!r}; choose from {list(CASE_SETS)}")
    if name == "independent":
        paths = [data_dir / f for f in INDEPENDENT_FILES]
        if missing := [p.name for p in paths if not p.exists()]:
            raise ValueError(f"the independent set is not built yet (missing {missing}); see docs/INDEPENDENT_DOCS_GUIDE.md")
        cases = [c for path in paths for c in load_cases(path)]
        return CaseSet("independent", cases, {c.attack_family for c in cases if c.is_attack}, paths)
    dev_path = data_dir / DEV_FILE
    dev = load_cases(dev_path)
    if name == "dev":
        return CaseSet("dev", dev, set(), [dev_path])
    paths = [data_dir / f for f in HELDOUT_FILES]
    held = [c for path in paths for c in load_cases(path)]
    families = {c.attack_family for c in held if c.is_attack}
    if overlap := families & {c.attack_family for c in dev if c.is_attack}:
        raise ValueError(f"held-out families also appear in the dev set: {sorted(overlap)}")
    return CaseSet("final", [c for c in dev if c.is_attack] + held, families, [dev_path, *paths])


def load_all_cases(data_dir: Path) -> dict[str, EvalCase]:
    """Every known case by id (dev, held-out and, when built, the independent set), for tools that look cases up."""
    files = [data_dir / DEV_FILE, *(data_dir / f for f in HELDOUT_FILES), *(data_dir / f for f in INDEPENDENT_FILES)]
    return {c.case_id: c for path in files if path.exists() for c in load_cases(path)}


def estimate_model_calls(configs: dict[str, DefenseConfig], n_cases: int, repetitions: int) -> int:
    """Upper bound: one generation per case plus one classifier call where that layer is on.
    Blocked cases skip generation, so the real count can be lower."""
    per_case = sum(1 + (1 if cfg.classifier else 0) for cfg in configs.values())
    return per_case * n_cases * repetitions
