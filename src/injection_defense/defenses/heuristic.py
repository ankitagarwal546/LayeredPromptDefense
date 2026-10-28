"""Layer 1: rule-based detection. Reports matches; policy (block/sanitize) lives in the pipeline."""

from __future__ import annotations

from injection_defense.defenses.base import Detector
from injection_defense.defenses.heuristic_rules import (
    DAMPEN_FACTOR, DEFAULT_RULES, QUOTE_PAIRS, TEACHING_FRAME, V2_RULES, Rule,
)
from injection_defense.schemas import DetectionResult, RuleMatch

REDACTION = "[REDACTED: suspected embedded instruction]"  # v1 sanitize marker (logged runs)
NEUTRAL_REDACTION = "..."  # neutral marker: the v1 marker made llama3.1:8b refuse some benign summaries


class HeuristicDetector(Detector):
    layer = "heuristic"

    def __init__(self, rules: tuple[Rule, ...] = DEFAULT_RULES, threshold: float = 1.0, *, dampen: bool = False):
        self.rules = rules
        self.threshold = threshold
        self.dampen = dampen

    @classmethod
    def for_version(cls, version: str) -> "HeuristicDetector":
        """v1: the logged rules. v2: v1 + weak indirect-attack rules + quotation/teaching-context dampening."""
        return cls(V2_RULES, dampen=True) if version == "v2" else cls()

    def detect(self, text: str) -> DetectionResult:
        matches = []
        for rule in self.rules:
            spans = [m.span() for m in rule.pattern.finditer(text)]
            if spans:
                weight = rule.weight
                description = rule.description
                if self.dampen and all(_in_quotes(text, s) or _after_teaching_frame(text, s) for s in spans):
                    weight = round(rule.weight * DAMPEN_FACTOR, 3)
                    description += " (dampened: quoted or presented as an example)"
                matches.append(RuleMatch(rule_id=rule.rule_id, description=description, weight=weight, spans=spans))
        score = sum(m.weight for m in matches)
        if self.dampen:
            score = round(score, 3)
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


def _line_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    return text.rfind("\n", 0, start) + 1, (text.find("\n", end) if text.find("\n", end) != -1 else len(text))


def _in_quotes(text: str, span: tuple[int, int]) -> bool:
    """The match lies inside a quotation on the same line (an opening mark before it, a closing mark after it)."""
    start, end = span
    line_start, line_end = _line_bounds(text, start, end)
    before, after = text[line_start:start], text[end:line_end]
    for open_q, close_q in QUOTE_PAIRS:
        if open_q == close_q:
            if before.count(open_q) % 2 == 1 and close_q in after:
                return True
        elif before.rfind(open_q) > before.rfind(close_q) and close_q in after:
            return True
    return False


def _after_teaching_frame(text: str, span: tuple[int, int]) -> bool:
    start = span[0]
    line_start = text.rfind("\n", 0, start) + 1
    return bool(TEACHING_FRAME.search(text[max(line_start, start - 120):start]))


def redact_matches(text: str, result: DetectionResult, marker: str = REDACTION) -> str:
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
        pieces.append(marker)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)
