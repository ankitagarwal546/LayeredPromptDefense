"""Helpers for blinded human review kits (a second attack-label reviewer, summary-quality ratings).

Blinding here means the reviewer sees an opaque item id, the document and the model output, but never the
run, model, configuration, trial, AI label or another reviewer's decision; those go to a separate key file.
Item order is shuffled with a recorded seed so the kit can be rebuilt exactly.
"""

from __future__ import annotations

import random
from collections.abc import Sequence


def blind_ids(n: int, prefix: str) -> list[str]:
    width = max(3, len(str(n)))
    return [f"{prefix}{i:0{width}d}" for i in range(1, n + 1)]


def shuffled(items: Sequence, seed: int) -> list:
    out = list(items)
    random.Random(seed).shuffle(out)
    return out


def cohen_kappa(pairs: Sequence[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters over the same items (labels are any hashable values).

    None when there are no pairs or chance agreement is 1 (every label identical), where kappa is undefined.
    """
    n = len(pairs)
    if not n:
        return None
    observed = sum(a == b for a, b in pairs) / n
    labels = {label for pair in pairs for label in pair}
    expected = sum((sum(a == lab for a, _ in pairs) / n) * (sum(b == lab for _, b in pairs) / n) for lab in labels)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)
