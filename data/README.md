# Data

`dev_cases.jsonl` — 18 hand-written **synthetic development fixtures** (provenance
`synthetic_development_example`). They exist to test the software and to debug/tune rules on a
development set. They are **not a benchmark** and support no claims about security performance.

One JSON object per line. Fields (strictly validated in `evaluation/dataset.py`; unknown fields are rejected):

| field | notes |
|---|---|
| `case_id` | unique |
| `document_text` | text passed to the summarizer |
| `is_attack` | bool |
| `attack_family` | required for attacks, forbidden for benign |
| `template_id` | near-duplicate group; hold out whole templates |
| `attack_goal`, `expected_behavior`, `notes` | documentation |
| `success_indicators` / `forbidden_output_patterns` | regexes; output matching them = attack objective achieved (see output validator for the quotation caveat) |
| `expected_summary_keywords` | benign only; used for the task-completion proxy |
| `provenance` | required; for public datasets also record source and license |

To add data, append lines; no code change needed. Do not add public datasets without checking
their license and redistribution terms (BIPIA, for instance, asks users to rebuild some task
data themselves).

## Held-out files (frozen)

| file | contents |
|---|---|
| `heldout_attacks.jsonl` | 24 attacks, 8 families **absent from `dev_cases.jsonl`**: fake_conversation_turn, markup_injection, hypothetical_framing, urgency_authority, format_hijack, emotional_manipulation, completion_priming, separator_breakout (3 templates each, one case per template) |
| `heldout_benign.jsonl` | 24 benign documents: 12 ordinary, 12 hard negatives that quote or discuss attacks or contain imperative text |
| `heldout.sha256` | checksums; `tests/test_heldout.py` fails if either file changes |

Rules, prompts and thresholds must be tuned on `dev_cases.jsonl` only. Do not read per-case
held-out results to adjust anything; if you do, the set is spent and you need a new one.

**Caveat on independence:** these files were authored by an LLM assistant that had also written
the heuristic rules and prompts. Attack families are disjoint from dev, but the author's habits
are shared, so results are likely optimistic about generalization. Prefer adding attacks written
or collected independently (e.g. from BIPIA after a license check) before drawing conclusions.
Provenance is `synthetic_heldout_llm_authored`; runs on it are labeled `PRELIMINARY`.
