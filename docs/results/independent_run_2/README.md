# Independent run 2: archived artifacts (post-review)

Run id `8a4c672e6307` (2026-10-24 20:55 to 2026-10-25 02:34 UTC; model `llama3.1:8b`, classifier = same model; code commit `fd66e17`, clean tree; case set `independent`, 100 cases x 7 configs x 2 trials = 1,400 outcomes).
Evidence status: PRELIMINARY. **Human review completed 2026-10-27 (reviewer: the author): 161 distinct outputs covering 363 attack outcomes; 2 outcomes judged unsure remain unresolved.** The top-level files are the post-review results.

Post-review (top level): `summary.csv`, `by_family.csv`, `task_disruption.csv`, `task_disruption_cases.csv`, `outcomes_no_text.csv` (no model text, with `manual_label`), `figures/`;
`human_review_decisions.csv` (per output group: `human_attack` YES/NO/UNSURE, `human_label`, `task_disrupted`, rationale in `note`, `output_quality_note` for factual or security concerns kept separate from the attack decision); `manual_labels.jsonl` (labels as applied); `review_impact.md` (before/after table).
Pre-review (`pre_review/`): the same files as first logged, before any human label, kept unchanged for comparison.
`metadata.json`. Raw outputs stay in the git-ignored `results/8a4c672e6307/outcomes.jsonl` (sha256 in `outcomes_pre_review.sha256`, verified unchanged after the review). See `docs/EXPERIMENT_LOG.md`.
