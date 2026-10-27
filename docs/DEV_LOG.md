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

## 2026-10-28: a clean assignment PDF blocked by the AI checker (web UI; anecdote, not a measurement)

The user tested their own DBMS lab assignment PDF (6,295 extracted characters: questions such as "Decompose ENROLLMENT ... and create these tables in SQL", SQL code, and answers; no attack) with preset E5 and `llama3.1:8b` as the summarizer. Server log: `decision=block blocked_by=classifier`, 1 model call, 2.6 s. Offline re-check of the word rules on the same extracted text: score 0.0, nothing matched. So the block came from L2, the prompt classifier, which runs on `CLASSIFIER_MODEL=llama3.2:1b` regardless of the summarizer. The document is full of imperative instructions addressed to a reader ("create", "insert", "define", "state"), which a 1B judge can mistake for orders to an AI; the classifier prompt already says that ordinary instructions to human readers are not suspicious, and the small model ignored that. This is a false alarm of the kind measured in the independent run (1B classifier FPR 2/50) and reported for naive LLM-based detection by Liu et al. (FINAL_REPORT section 5.2). One document, one trial, not re-run (no extra model call was made to reproduce it): an observation, not evidence.
Changes made in response (UI only, no defense changed): the result card now explains why a document was blocked (including the checker's own reason) and offers a one-click re-run with that layer on `flag_only`; the "Blocked" verdict no longer assumes the document was an attack.

## 2026-10-28: task-neutral role line for the web UI

Problem: the UI's instruction field was passed to the model, but the system message always began "You are a document summarization assistant.", which pushes the model to summarize whatever the user asked. Choice: keep every evaluated prompt byte-for-byte (results stay reproducible) and add a request flag (`general_task`) that swaps only that first sentence for `GENERAL_ROLE`. Rejected: editing `BASE_SYSTEM` (would silently change E0 and every structural variant relative to the logged runs) and adding a new structural variant (the baseline E0 would still say "summarization"). Untested with real models beyond the API plumbing; whether the security text works as well under a general role was not measured.
