"""Offline comparison of L1 rule versions on every dataset (no model calls).

    python scripts/compare_heuristic_versions.py

Prints, per case set, how many attack documents each rule version flags (detection) and how many benign documents
it flags (false alarms). IN-SAMPLE: rules v2 were written after these sets' results were seen, so the v2 numbers are
not evidence of generalization; they only show what v2 changes on known data.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.config import Settings  # noqa: E402
from injection_defense.defenses.heuristic import HeuristicDetector  # noqa: E402
from injection_defense.evaluation.registry import CASE_SETS, build_case_set  # noqa: E402


def main() -> int:
    data_dir = Settings().data_dir
    detectors = {v: HeuristicDetector.for_version(v) for v in ("v1", "v2")}
    print("IN-SAMPLE (v2 was designed after these results were seen)\n")
    print(f"{'case set':<14}{'version':<9}{'attacks flagged':>18}{'benign flagged':>17}")
    for name in CASE_SETS:
        try:
            cases = build_case_set(name, data_dir).cases
        except (FileNotFoundError, ValueError):
            continue
        attacks = [c for c in cases if c.is_attack]
        benign = [c for c in cases if not c.is_attack]
        for version, det in detectors.items():
            hit = sum(det.detect(c.document_text).flagged for c in attacks)
            fp = sum(det.detect(c.document_text).flagged for c in benign)
            print(f"{name:<14}{version:<9}{f'{hit}/{len(attacks)}':>18}{f'{fp}/{len(benign)}':>17}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
