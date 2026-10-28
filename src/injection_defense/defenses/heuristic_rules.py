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


# --- Rules v2 (added 2026-10-29; NOT used by any logged run) -------------------------------------------------
# Designed AFTER seeing the held-out and independent-set results (the BIPIA attacks, the hard-negative false alarms),
# so any measurement of v2 on those sets is in-sample, not a generalization test (see docs/EXPERIMENT_LOG.md).
# v2 = every v1 rule plus low-weight patterns for polite / indirect payloads. Each is weak on its own (< 1.0) and
# only flags in combination; bare off-task questions ("What are the benefits of X?") remain undetectable by wording.
V2_EXTRA_RULES: tuple[Rule, ...] = (
    _rule(
        "polite_aside",
        r"\b(by\s+the\s+way|oh,?\s+and|p\.\s?s\.?|while\s+you'?re\s+at\s+it|also|additionally)\b[^.\n]{0,40}"
        r"\b(could|can|would|will)\s+you\b|\bplease\s+(also|additionally)\b",
        "Polite side request that may switch the task",
        weight=0.4,
    ),
    _rule(
        "append_to_output",
        r"\b(append|add|include|insert|attach)\b[^.\n]{0,40}\b(to|in|at\s+the\s+end\s+of|after)\s+(your|the)\s+"
        r"(summary|answer|response|reply|output)\b"
        r"|\b(end|finish|conclude|close)\s+(your|the)\s+(summary|answer|response|reply)\s+(with|by)\b",
        "Asks to add text to the model's answer",
        weight=0.6,
    ),
    _rule(
        "unrelated_question",
        r"\b(answer|respond\s+to|address|handle)\b[^.\n]{0,25}\b(unrelated|separate|different|other|additional|following)\s+"
        r"(question|task|request|query)\b",
        "Asks the model to take on a different question or task",
        weight=0.6,
    ),
    _rule(
        "language_switch",
        r"\b(translate|respond|reply|answer|write|summari[sz]e)\b[^.\n]{0,30}\b(in|into)\s+"
        r"(french|spanish|german|italian|portuguese|chinese|japanese|korean|russian|arabic|hindi|dutch|turkish)\b",
        "Asks for the answer in another language",
        weight=0.5,
    ),
    _rule(
        "markdown_exfiltration",
        r"!\[[^\]\n]*\]\(\s*https?://|\[[^\]\n]+\]\(\s*https?://[^)\s]*\?[^)\s]*=",
        "Markdown image or tracking link (can leak data when rendered)",
        weight=0.5,
    ),
    _rule(
        "imperative_shift",
        r"\b(from\s+now\s+on|now|next|before\s+you\s+(summari[sz]e|answer|respond))\b,?\s+"
        r"(write|tell|list|translate|give|explain|describe|answer|compose|generate|create|recommend)\b",
        "Abrupt imperative that starts a new task",
        weight=0.4,
    ),
)
V2_RULES: tuple[Rule, ...] = DEFAULT_RULES + V2_EXTRA_RULES

# Dampening (v2): a match inside quotation marks, or right after teaching/reporting framing, is far more often a
# security text discussing an attack (the hard negatives) than an attack. Its weight is multiplied by DAMPEN_FACTOR.
# LIMITATION: an attacker can exploit this by framing an instruction as an example; that trade-off is deliberate.
DAMPEN_FACTOR = 0.3
TEACHING_FRAME = re.compile(
    r"(for\s+example|for\s+instance|e\.g\.|such\s+as|like\s+the\s+(phrase|line|sentence)|the\s+(phrase|line|sentence)"
    r"|an?\s+example\s+(of|is)|known\s+as|attackers?\s+(often\s+|may\s+|might\s+|can\s+)?(write|use|insert|hide|plant|add)"
    r"|(hidden|injected|malicious|embedded)\s+(line|text|instruction|sentence)s?\s+(such\s+as|like|saying|reading)"
    r"|a\s+(line|sentence|message)\s+(such\s+as|like|saying|reading))[^.\n]{0,40}$",
    _F,
)
# Straight single quotes are left out: they are mostly apostrophes ("don't").
QUOTE_PAIRS = (('"', '"'), ("\u201c", "\u201d"), ("\u2018", "\u2019"), ("\u00ab", "\u00bb"))


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
