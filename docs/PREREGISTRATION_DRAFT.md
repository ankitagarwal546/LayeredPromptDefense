# Pre-registration DRAFT: follow-up experiments (not registered, nothing run)

Status: **DRAFT, 2026-10-29.** Nothing here has been run, implemented or approved. It becomes a pre-registration only
when the project owner approves it and the plan is copied, unchanged, into `docs/EXPERIMENT_LOG.md` with a commit tag,
**before** any data is collected. Until then any detail may change. The ideas come from FINAL_REPORT section 17 and the
full-text reading in section 5. All rules in `AGENTS.md` (research integrity) and `docs/EXPERIMENT_PROTOCOL.md` apply.

Shared conditions (unless stated otherwise): models `llama3.2:1b` and `llama3.1:8b` via Ollama, temperature 0.0,
`LLM_MAX_TOKENS=512`, `LLM_TIMEOUT_S=60` (the experiment settings, not the web UI's), classifier = same model as the
summarizer, `general_task` never set (evaluated summarization wording), 2 trials, the existing scorer and human-review
procedure. Call counts below are upper bounds from `estimate_model_calls` logic: 1 call per summarizer output plus 1 per
classifier check.

## X1. Classifier false alarms on instruction-heavy clean documents

- **Why:** in the web UI the 1B classifier blocked a clean assignment full of questions and SQL (`docs/DEV_LOG.md`,
  2026-10-28; anecdote). Liu et al. report large false-positive rates for LLM-based detection. The independent set's
  benign documents are mostly news-like, so its FPR (1B 2/50, 8B 0/50) may understate this.
- **New data (needs building and freezing first):** 30 clean documents in three groups of 10: exam/assignment sheets
  (questions plus answers), how-to and recipe instructions, code tutorials. No attacks. Authored by the project (AI-drafted,
  human-checked) and frozen by checksum like the other sets; ideally some written by a person, which would need the owner.
- **Configurations:** E3 (classifier only, block) on both models; E0 as the utility reference.
- **Primary outcome:** classifier false-positive rate (flagged / evaluated) per model, Wilson 95% interval; detector
  failures reported separately, never counted as clean.
- **Hypothesis (H-X1):** the 1B classifier's FPR on this set is higher than its 2/50 on the independent benign set.
  Judged by non-overlapping intervals only; no significance test planned.
- **Calls:** 30 docs x 2 trials x (E3: 2 + E0: 1) x 2 models = **360**.

## X2. Datamarking as a further structural variant

- **Why:** Spotlighting (Hines et al.) reports datamarking far stronger than delimiting on GPT models with no task loss;
  our E2 is delimiting plus a restated task. Encoding is excluded (the paper says it needs very capable models).
- **Implementation (to be written before any run):** structural variant `v4` = v3 wording plus a marker character
  interleaved between every word of the document, and one sentence telling the model what the marker means. Existing
  variants stay byte-for-byte.
- **Tuning:** wording and marker choice decided on `data/dev_cases.jsonl` only, by a rule fixed in advance (highest benign
  task completion; tie -> lower ASR), as for v3.
- **Evaluation:** E2 (v3) vs E2 (v4) on the independent set (not spent; no defense was tuned on it), both models.
- **Primary outcome:** ASR with denominators and unresolved counts; secondary: usable-summary share on attacked
  documents, benign task completion.
- **Hypothesis (H-X2):** v4 lowers ASR relative to v3 on at least one model without lowering benign completion.
- **Calls:** dev tuning about 18 cases x 2 trials x up to 3 wordings x 2 models = 216; evaluation 100 x 2 x 2 x 2 = **800**.

## X3. What part of E2 helps: markers or the restated task?

- **Why:** Perez & Ribeiro, BIPIA and AgentDojo all point to text after the input (a restated task) as protective.
- **Conditions:** three ablations of v3, each a new variant name, wording fixed before any run: (a) markers only, no
  restated task; (b) restated task only, no markers; (c) neither (system message only). Compared with E0 and E2 (v3).
- **Data:** independent set, both models.
- **Primary outcome:** ASR per condition; paired comparison with E0 per case (the audit's transition method).
- **Hypothesis (H-X3):** (b) keeps most of E2's ASR reduction and (a) keeps little. Exploratory if intervals overlap.
- **Calls:** 100 x 2 trials x 3 new conditions x 2 models = **1,200** (E0 and E2 are reused from the logged runs only if
  code, model and settings are unchanged; otherwise re-run, +800).

## X4. E6: operator deny-list output check

- **Why:** L4 is the scorer in experiments (oracle leakage). A deployable output check must use criteria an operator could
  know in advance, independent of each attack's success indicators.
- **Rule set (fixed before seeing any independent-set output it would be scored on):** generic patterns only, e.g. URLs or
  e-mail addresses not present in the document, markdown images, phone numbers not in the document, text in a different
  language from the document, explicit role/persona switches. Written and committed before the run.
- **Configuration:** E6 = E2 + deny-list (withhold on match). Data: independent set, both models.
- **Outcomes:** ASR, and false withholds on benign documents (the cost).
- **Calls:** no new model calls if applied to the logged E2 outputs offline (a post-hoc analysis, labelled as such); a
  live E6 run would be 100 x 2 x 2 = **400**.

## Not covered here

Human-only tasks (second blinded reviewer, summary-quality ratings: kits ready, see README "Human review kits"), the
hosted-model condition (needs a key and cost approval) and the trained classifier (needs a download approval).
