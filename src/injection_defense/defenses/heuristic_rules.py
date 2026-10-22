"""Inspectable rule set for the heuristic detector (Layer 1).

Each rule is a regex plus a weight. The detector sums the weights of distinct matching rules
and flags the text when the sum reaches its threshold (default 1.0), so a weak signal
(weight < 1) needs corroboration. These patterns catch known phrasings only: paraphrases,
other languages, encodings, and split instructions will evade them. Keyword matching is a
baseline, not comprehensive protection.

Rules can be replaced from a JSON file: [{"rule_id", "pattern", "description", "weight"}].
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_F = re.IGNORECASE | re.MULTILINE


@dataclass(frozen=True)
class Rule:
    rule_id: str
    pattern: re.Pattern[str]
    description: str
    weight: float = 1.0


def _rule(rule_id: str, pattern: str, description: str, weight: float = 1.0) -> Rule:
    return Rule(rule_id, re.compile(pattern, _F), description, weight)


DEFAULT_RULES: tuple[Rule, ...] = (
    _rule(
        "override_previous",
        r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}"
        r"\b(previous|prior|above|earlier|preceding|all|any|your|the\s+user'?s?)\b[^.\n]{0,40}"
        r"\b(instructions?|prompts?|rules?|directions?|requests?|tasks?|guidelines)\b",
        "Tells the model to ignore or override earlier instructions",
    ),
    _rule(
        "new_instructions",
        r"\b(new|updated|revised)\s+(instructions?|task|directive)s?\s*[:\-]",
        "Introduces replacement instructions",
    ),
    _rule(
        "role_reassignment",
        r"\byou\s+are\s+now\s+((a|an|the|my|acting|going\s+to\s+be|in\s+\w+\s+mode)\b|(?-i:[A-Z]\w+))"
        r"|\bpretend\s+(to\s+be|you\s+are)\b|\byou\s+are\s+no\s+longer\b",
        "Tries to reassign the model's role",
    ),
    _rule(
        "instead_output",
        r"\binstead\b[,:]?\s*(you\s+)?(must|should|will|shall)?\s*"
        r"(output|print|say|respond|reply|write)\b",
        "Redirects the model to produce different output instead",
    ),
    _rule(
        "do_not_summarize",
        r"\bdo\s+not\s+(summari[sz]e|follow\s+the\s+user)\b|\binstead\s+of\s+summari[sz]ing\b"
        r"|\bstop\s+summari[sz]ing\b",
        "Tells the model to abandon the summarization task",
    ),
    _rule(
        "reveal_prompt",
        r"\b(reveal|show|print|repeat|output|leak|display)\b[^.\n]{0,40}"
        r"\b(system\s+prompt|hidden\s+instructions?|your\s+instructions|initial\s+prompt"
        r"|developer\s+message)\b",
        "Asks for the system prompt or hidden instructions",
    ),
    _rule(
        "fake_authority",
        r"\b(system|developer|admin(istrator)?)\s*(message|override|note|instruction|prompt)\s*[:\]]"
        r"|^\s*\[?(system|assistant)\]?\s*:",
        "Impersonates the system, developer, or administrator",
    ),
    _rule(
        "addresses_the_model",
        r"\b(attention|note\s+to|message\s+to|instructions?\s+for)\s+(the\s+)?"
        r"(ai|assistant|llm|language\s+model|model|summari[sz]er)\b"
        r"|\bai\s+(summari[sz]ers?|assistants?)\s*[:,]",
        "Speaks directly to the AI reader inside the document",
    ),
    _rule(
        "claim_trustworthy",
        r"\b(state|claim|say|declare|report|conclude|write)\b[^.\n]{0,40}\b(this\s+)?"
        r"(document|paper|source|text)\b[^.\n]{0,30}\b(is|as)\b[^.\n]{0,20}"
        r"\b(trustworthy|verified|authoritative|reliable|accurate|safe)\b",
        "Tries to make the model vouch for the document",
    ),
    _rule(
        "output_exact_text",
        r"\b(respond|reply|answer|output|say|print|write)\b\s+(only\s+|exactly\s+|just\s+)?"
        r"(with\s+)?(the\s+(phrase|words|text)\s+)?[\"“'][^\"”'\n]{3,}[\"”']",
        "Dictates exact output text (weak signal on its own)",
        weight=0.5,
    ),
)


def load_rules(path: str | Path) -> tuple[Rule, ...]:
    """Load rules from JSON, validating that each pattern compiles."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = []
    for record in records:
        try:
            rules.append(
                _rule(record["rule_id"], record["pattern"], record["description"], record.get("weight", 1.0))
            )
        except (KeyError, re.error) as exc:
            raise ValueError(f"Invalid heuristic rule {record!r}: {exc}") from exc
    return tuple(rules)
