"""Layer 1: rule-based detection. Reports matches; policy (block/sanitize) lives in the pipeline."""

from __future__ import annotations

from injection_defense.defenses.base import Detector
from injection_defense.defenses.heuristic_rules import DEFAULT_RULES, Rule
from injection_defense.schemas import DetectionResult, RuleMatch

REDACTION = "[REDACTED: suspected embedded instruction]"


class HeuristicDetector(Detector):
    layer = "heuristic"

    def __init__(self, rules: tuple[Rule, ...] = DEFAULT_RULES, threshold: float = 1.0):
        self.rules = rules
        self.threshold = threshold

    def detect(self, text: str) -> DetectionResult:
        matches = []
        for rule in self.rules:
            spans = [m.span() for m in rule.pattern.finditer(text)]
            if spans:
                matches.append(
                    RuleMatch(rule_id=rule.rule_id, description=rule.description, weight=rule.weight, spans=spans)
                )
        score = sum(m.weight for m in matches)
        flagged = score >= self.threshold
        if flagged:
            ids = ", ".join(m.rule_id for m in matches)
            explanation = f"Score {score:g} >= threshold {self.threshold:g}; matched rules: {ids}"
        elif matches:
            ids = ", ".join(m.rule_id for m in matches)
            explanation = f"Score {score:g} < threshold {self.threshold:g}; weak matches only: {ids}"
        else:
            explanation = "No heuristic rule matched (this does not mean the text is safe)"
        return DetectionResult(
            layer=self.layer,
            status="evaluated",
            flagged=flagged,
            score=score,
            matched_rules=matches,
            explanation=explanation,
        )


def redact_matches(text: str, result: DetectionResult) -> str:
    """Replace every matched span with a placeholder (used by the "sanitize" policy)."""
    spans = sorted(span for match in result.matched_rules for span in match.spans)
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    pieces, cursor = [], 0
    for start, end in merged:
        pieces.append(text[cursor:start])
        pieces.append(REDACTION)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)
