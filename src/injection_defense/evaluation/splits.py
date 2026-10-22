"""Family-level partitioning for generalization testing.

Attacks from a held-out family (or template) never appear in the "familiar" group, so rules,
prompts, and thresholds tuned on familiar attacks are not scored on near-duplicates of them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from injection_defense.evaluation.dataset import EvalCase


@dataclass(frozen=True)
class CaseSplit:
    familiar_attacks: list[EvalCase]
    heldout_attacks: list[EvalCase]
    benign: list[EvalCase]


def split_by_family(
    cases: Iterable[EvalCase],
    heldout_families: Iterable[str],
    heldout_templates: Iterable[str] = (),
) -> CaseSplit:
    cases = list(cases)
    families, templates = set(heldout_families), set(heldout_templates)
    present_families = {c.attack_family for c in cases if c.is_attack}
    present_templates = {c.template_id for c in cases if c.is_attack}
    if missing := families - present_families:
        raise ValueError(f"held-out families not present in the data: {sorted(missing)}")
    if missing := templates - present_templates:
        raise ValueError(f"held-out templates not present in the data: {sorted(missing)}")

    familiar, heldout, benign = [], [], []
    for case in cases:
        if not case.is_attack:
            benign.append(case)
        elif case.attack_family in families or case.template_id in templates:
            heldout.append(case)
        else:
            familiar.append(case)
    return CaseSplit(familiar, heldout, benign)
