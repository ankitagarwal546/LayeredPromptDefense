# Development log

Observations from development runs. **All of these are smoke tests on synthetic dev fixtures
with a tiny local model; they are not findings.** Nothing here has used the held-out files.

## 2026-10-22: first real-model runs (llama3.2:1b via Ollama, temperature 0)

Setup: `.env` with `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=http://localhost:11434/v1`.

1. **Automatic scoring needed fixing before the numbers meant anything.** Reading real outputs
   showed false positives (a refusal that quoted the attack scored as success), and false
   negatives (a compliant `DEBUGBOT_ACTIVE` missed by a space-only pattern; a paraphrased
   "trustworthy and verified" missed by a fixed phrase). Fixes: quotation detection, wider
   reporting verbs, separator-tolerant literal indicators, corrected dev indicators for dev-a03
   and dev-a06. Held-out files were not changed. Lesson: always read the outputs; adjudicate
   `needs_review` cases by hand.
2. **Structural separation caused over-refusal on this model.** With E2, 6 of 7 benign dev
   documents were refused ("appears to contain instructions"), so task completion fell from
   100% (E0) to 14%. Its lower ASR is partly refusal, not resistance. A larger model may behave
   differently; the prompt wording may be partly responsible and can be tuned on dev data only.
3. **Heuristic blocking** (E1) produced 0 successful dev attacks at the cost of blocking the
   benign security article (dev-b04). Expected: the rules were written with the dev set in view,
   so this is not evidence of generalization.
4. Mock-model results (`is_mock: true`) say nothing about any of this.

## Environment note (macOS, Python 3.13)

The venv's editable-install `.pth` file can acquire the macOS `hidden` flag and then be
skipped by Python 3.13, giving `ModuleNotFoundError`. See the README troubleshooting section.

## 2026-10-22: structural prompt tuning (dev set only, llama3.2:1b, 2 repetitions)

Goal: reduce v1's over-refusal. Variants v2 and v3 were written before any run; the selection
rule was fixed in advance (max benign task completion, tie -> lower ASR). Tool:
`scripts/tune_structural.py --real --repetitions 2`. Scorer fixed mid-way (a compliant
`DEBUGBOTACTIVE` with no separator had been scored as a failure); numbers below use the fixed scorer.

| config | ASR (evaluated) | unknown | benign task completion |
|---|---|---|---|
| E0, no defense | 60.0% (12/20) | 2 | 100% (14/14) |
| E2, v1 (**before**) | 40.9% (9/22) | 0 | 14.3% (2/14) |
| E2, v3 (**after**) | 63.2% (12/19) | 3 | 100% (14/14) |
| E2, v2 | 75.0% (15/20) | 2 | 100% (14/14) |

What this does and does not show:
- v3 removed the over-refusal (all benign outputs were real summaries), so the selection rule
  chose it and it is now the default `structural_variant`. v1 stays selectable for reproducibility.
- **v3's ASR is about the same as the undefended model's** (63% vs 60%, with 3 and 2 cases
  unresolved; n = 11 attacks, 2 near-identical trials). On this model, the wording that kept
  utility gave no visible protection, and the wording that gave protection (v1) did so largely by
  refusing benign documents too. This is one 1B model and 11 attacks: do not generalize.
- The choice is model-specific. Re-run the tuning script for any other model, on dev data only.
- No held-out data was used. Unresolved `needs_review` results (the "unknown" column: 2 for E0, 2 for v2, 3 for v3, counted per trial) must be adjudicated by hand before reporting.
