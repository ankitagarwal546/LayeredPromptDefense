# HANDOFF.md: canonical project state

Last updated: 2026-10-27 (session 3, checkpoint 16: final results audit DONE, read-only; see E and RESULTS_AUDIT.md; earlier checkpoint 15; previously checkpoint 14: independent run 1 (1B) reviewed; independent run 2 (8B, `8a4c672e6307`) DONE, verified and human-reviewed; comparison and report updated; next: literature review, frontend, demo). Update at every checkpoint (see L).

## A. Project identity
- **Title:** Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization
- **Objective:** working summarizer with a configurable defense pipeline + reproducible evaluation (RQ1-RQ6: `docs/RESEARCH_PLAN.md`)
- **Repo:** `/Users/ankitagarwal546/Documents/Prompt Injection` (git, branch `master`, no remote). Tags `final-run-1-freeze` / `final-run-2-freeze` mark the frozen code for each final run; `independent-freeze` marks the frozen independent set. Check `git status` / `git log -1` for the current commit (do not trust a hash written here).
- **Phase:** software complete; final runs 1 (1B) and 2 (8B) done, analyzed, logged, reported (preliminary). Independent run 1 (1B) done and human-reviewed. Independent run 2 (8B) done and human-reviewed (`8a4c672e6307`); comparison done (EXPERIMENT_LOG) and report updated; next: literature review, frontend, demo.

## B. Current status

| Area | Status | Notes |
|---|---|---|
| Structure, deps, `.env.example`, `.gitignore`, AGENTS/CLAUDE/HANDOFF | DONE | |
| Mock LLM (labeled dev-only) | DONE | |
| Real adapters | OpenAI-compatible DONE (live-verified via Ollama `llama3.2:1b`); Anthropic NEEDS_VERIFICATION (stub-transport tests only) | |
| L1 heuristic + policies | DONE | |
| L2 prompt classifier | DONE (works mechanically; weak with 1B model) | dev: detection 1/11, 0 failures after parser fix |
| L2 Transformers adapter | NEEDS_VERIFICATION | fake-predictor tests only; torch/transformers not installed; no weights downloaded (needs user OK) |
| L3 structural v1/v2/v3 | DONE | default v3 |
| L4 output validator | DONE (scorer/optional guard) | |
| Pipeline + allow/warn/block, layers_run, reached_model | DONE | |
| API `/health /config /extract /summarize /evaluate /results` | DONE | |
| Document extraction (txt/md/pdf/docx) | DONE | hidden-text not detected (documented) |
| Frontend | DONE (third redesign 2026-10-27: animated intro screen with a 3D document stack, then a sidebar dashboard: Overview / Test a document / Results / How it works / Evaluations; light/dark toggle saved in localStorage; system fonts; reduced-motion respected. 2026-10-28: animated "Defense Lab" shield logo shown on the intro, sidebar and mobile top bar; "Run test" now shows a live run view: stations per active layer, a travelling page and a narrated scene per step; the model step waits for the real reply and stations are then coloured from the actual response) | 4 tabs: How it works / Try it (4 demo-only examples in `frontend/demo_examples.json`, verdict + meters + step timeline) / Research results (`GET /findings` serves `docs/results/independent_audit/` read-only) / Advanced. Ollama-off now gives `model_unreachable` 502 with "ollama serve" hint. Checked in the browser pane with the mock model, with Ollama off, and (2026-10-27) with real `llama3.2:1b` on the 4 demo examples (8 local calls; all tabs render, no console errors) |
| Dataset loader, splits, held-out freeze | DONE | |
| Metrics (ASR, bounds, FPR, utility, gap, latency, failures, Wilson) | DONE | |
| CLIs: run_experiments (dry-run/resume/cost guard), analyze_results, adjudicate, verify_environment | DONE | subprocess-tested |
| Human review tools: `prepare_review.py`, `apply_review.py` | DONE | subprocess-tested; checklists are written to git-ignored folders (`results/review/` for the final runs, `results/review_independent_run1/` for independent run 1) |
| Trained classifier (training script) | BLOCKED | no reviewed dataset/licence; no torch; documented in DATASET_GUIDE |
| Docs: THREAT_MODEL, RESEARCH_PLAN, ARCHITECTURE, PROTOCOL, DATASET_GUIDE, SECURITY_LIMITATIONS, DEV_LOG, EXPERIMENT_LOG | DONE (EXPERIMENT_LOG has every pre-registration and run entry so far; independent run 2 entry pending) | |
| `docs/FINAL_REPORT.md` | IN_PROGRESS (preliminary; covers all four runs: section 10.1 independent set now has both models + comparison; abstract, 11-16 updated 2026-10-27; section 5 related work rewritten 2026-10-27 at abstract level only (7 sources re-checked, full papers not read); section 17 still INCOMPLETE) | numbers checked against `docs/results/*/summary.csv` and `task_disruption.csv` |
| Final run 2 (same, llama3.1:8b; pre-registered, tag `final-run-2-freeze`) | DONE | run `b507b975ae1f`, 826 outcomes, 0 failures; artifacts in `docs/results/final_run_2/` |
| Final run 1 (E0,E1,E1b,E2,E3,E4,E5; final case set; 2 reps; llama3.2:1b) | DONE | run `aee56f02e584`, 826 outcomes, 0 failures; artifacts in `docs/results/final_run_1/` |
| Independent set (BIPIA attacks, MIT, in 25 AI-generated benign documents) | DONE, frozen (tag `independent-freeze`) | partially independent: external attacks, AI-generated documents; see `docs/INDEPENDENT_SET.md` |
| Human adjudication | DONE for final runs 1-2 (103 labels) and independent run 1 (119 groups / 358 outcomes); one non-blinded reviewer | second, blinded reviewer TODO |
| Human summary-quality ratings | TODO | needs a human |

## C. Completed and verified
- `pytest` -> **246 passed** (2026-10-27, offline, ~10-20 s). Includes API, evaluation, CLI subprocess (incl. review tools), frontend-static, extraction, adapter, attack-check, disruption and independent-set freeze tests.
- Live API smoke check 2026-10-25 (mock mode, port 8765): `/health` ok, `/` -> `/app/` 200, `/summarize` blocked an injected document at the heuristic without a model call, `/results` listed 20 runs. Real-model UI flow last verified by hand in an earlier session.
- Live checks: Ollama real-model summarize via API/UI; `run_experiments.py --dry-run` plan and guards (needs `--yes`, `--final-ack`); mock run + analyze; adjudicate flow.
- Dev real-model smoke runs and structural-prompt tuning: `docs/DEV_LOG.md`.
- Commits: see `git log` (foundation, extraction/store/API, frontend, CLIs, adapter, freeze + label fix).

## D. Remaining tasks (priority order)
| ID | Task | Status | Acceptance |
|---|---|---|---|
| R1 | Human verification of the 103 AI-adjudicated labels | DONE (2026-10-24) | reviewer Ankit; 33 items, agreed 32, changed 1 (run 1 dev-a09 E2 t0 yes->no: run 1 E2 ASR 41.4% -> 40.0%); decisions in `docs/results/human_review_decisions.csv`; see EXPERIMENT_LOG |
| R8 | Task-disruption measure (separate outcome; ASR unchanged) | DONE (2026-10-24) | `evaluation/disruption.py`, `scripts/task_disruption.py`, criteria `data/task_disruption_carriers.json`; rule committed (`1ab56a4`) before computing; agrees with human labels 62/64; results in EXPERIMENT_LOG / FINAL_REPORT and `docs/results/final_run_{1,2}/task_disruption*.csv` |
| R2 | Run the same protocol on a hosted frontier model as a further SEPARATE condition (the 8B condition is done) | TODO / needs user key | new run id and EXPERIMENT_LOG entry; never mixed with the 1B run; held-out set is already spent for tuning purposes, so use a new held-out set for any further tuning |
| R3 | Independent set (BIPIA attacks in AI-generated benign documents; partially independent) | FROZEN; **run 1 (llama3.2:1b, `4da08316a2fb`) DONE and human-reviewed (2026-10-25)**; **run 2 (llama3.1:8b, `8a4c672e6307`) DONE and human-reviewed (2026-10-27)** | see section E |
| R4 | Transformers classifier verification (user must approve torch + weights download) | TODO | one real run; update status |
| R5 | Human summary-quality ratings on a benign subset | TODO | documented rubric + saved ratings |
| R6 | Optional: operator deny-list output validation as E6 (criteria independent of scorer); hidden-text experiments | TODO | new experiment entries |
| R7 | Literature review beyond abstracts | PARTIAL | section 5 done at abstract level (7 sources); reading full papers is optional follow-up |

## E. Current task checkpoint
Independent run 1 finished and verified: run id `4da08316a2fb`, 1,400 outcomes (100 cases x 7 configs x 2 trials), clean tree at tag `independent-freeze` (`a9991f5`), checksums OK, 0 model failures, 8 detector failures (classifier unparseable on ind-a51/ind-a61), 24 blocked. Results, commands, versions and scorer hashes are in `docs/EXPERIMENT_LOG.md`
(sections "Independent run 1" and "Independent run 1: human review and post-review results"); archived artifacts in `docs/results/independent_run_1/` (post-review at top level, pre-review in `pre_review/`).
**Human review DONE (2026-10-25, reviewer Ankit, 119 groups / 358 outcomes, 12 batches):** attack YES 55 groups (214 outcomes), NO 48 (121), UNSURE 16 (23 outcomes, left unresolved); summary-ruined decided for all 119. Applied with `apply_review.py` (335 labels); `outcomes.jsonl` checksum unchanged.
Post-review ASR: E0/E1/E1b 44.0% (66/150) [36-52], E3 42.7%, E2 30.0% (42/140) [23-38], E4 31.7%, E5 29.6%; intervals overlap slightly, review not blind to config -> suggestive, not established. Usable summary on attack docs: 21% without vs 55-60% with the structural prompt (no overlap).
Review rubric and caveats are in the log. Local review files: `results/review_independent_run1/` (checklist with model text, `review_decisions.csv`, the untouched `review_decisions.original.csv`, impact tables).
Still open, optional:
1. Post-hoc Reverse Text review: `results/review_independent_run1/reverse_text_posthoc.md` (22 outputs; NOT applied; registered ASR unchanged; label any statement post-hoc).
2. FINAL_REPORT section 10.1 (independent set) is drafted for the 1B run only; complete it with the 8B results, then update the abstract, discussion, limitations, conclusion and future work.

**Independent run 2 (8B) DONE, verified AND human-reviewed (2026-10-27):** run id `8a4c672e6307`, 1,400 unique outcomes, `llama3.1:8b`, commit `fd66e17`. 2 transient model failures (E0 trial 1, `ind-a31`, `ind-a34`; not retried, excluded from ASR), 8 detector failures (E3/E5, `ind-a51`/`ind-a61`), 6 blocked (all benign sec-04). Logged in EXPERIMENT_LOG ("Independent run 2" and "...human review and post-review results"), archived in `docs/results/independent_run_2/` (post-review top level, pre-review in `pre_review/`).
**Review DONE:** reviewer Ankit, 161 groups / 363 outcomes, 9 batches; attack YES 34 groups (124 outcomes), NO 125 (237), UNSURE 2 (2 outcomes, E5, left unresolved); summary-ruined decided for all. The reviewer accepted every AI proposal (no override), so labels may be anchored; not blind to config. 361 labels applied; `outcomes.jsonl` checksum unchanged. Local review files: `results/review_independent_run2/`.
Post-review ASR: E0 39.9% (59/148) [32-48], E1/E1b/E3 40.0% (60/150), E2 20.0% (30/150) [14-27], E4 21.3%, E5 20.3% (30/148). Detectors added nothing (word rules 0/150; 8B classifier 0/146 attacks and 0/50 benign). Usable summary on attack docs 48% without vs 67-71% with the structural prompt. Intervals do not overlap for E0 vs E2/E4/E5; no significance test run.
**Step 4 DONE (2026-10-27):** 1B-vs-8B comparison written in EXPERIMENT_LOG ("Cross-model comparison on the independent set"; exploratory, post hoc; docs only). Findings: undefended ASR similar (44.0% vs 39.9%); structural prompt lowered ASR on both (about -14 pts 1B, -20 pts 8B); detectors useless on both (8B classifier fired on nothing); 8B resisted off-task questions more but obeyed insertion attacks more; intervals on 150 observations overstate precision (effective n about 75).
**Results audit DONE (2026-10-27, read-only):** `scripts/audit_independent.py` (43/43 checks pass; recomputes all metrics from raw files; writes `docs/results/independent_audit/`), write-up `docs/RESULTS_AUDIT.md`, FINAL_REPORT section 10.2 (direct 1B-vs-8B comparison, natural-resistance pairing, bootstrap, category analysis), EXPERIMENT_LOG entry. No defense, data, prompt, model, scoring or result changed. Findings: E2/E4/E5 tie for attack resistance (8B about 20%, 1B about 30%); combining defenses does not improve on safer instructions alone; E2 is on the utility frontier too; detectors add nothing on this set; 56-60% of attacks fail without any defense; nothing is called statistically significant. Minor discrepancy: FINAL_REPORT 8B E5 interval [15-28] vs exact 14.6-27.5 (rounding). Application verified by running it (see RESULTS_AUDIT 7): ready for a supervised local demo, not for public hosting; gaps: generic 502 message, no demo presets, no automated browser test, no comparison page.
**Step 5 DONE (2026-10-27):** FINAL_REPORT updated for both models: header, abstract, section 10.1 (both result tables + comparison), 11, 12, 13, 14, 15, 16, 17 (docs only; table numbers machine-checked against the archived CSVs).
**NEXT:** (literature review section 5 done at abstract level) (frontend redesign and demo script `docs/DEMO_SCRIPT.md` DONE 2026-10-27), optional second blinded reviewer / hosted-model run / Transformers classifier / Reverse Text post-hoc review. Helper scripts used for the review were in the session scratchpad (not in the repo): re-create if a similar review is needed (`prepare_review.py` + `apply_review.py` are the repo tools).
Do not change any defense, prompt, check or scorer before the first results are logged (done: pre-review results are logged); any tuning against this set means it is spent for generalization claims (docs/INDEPENDENT_SET.md). Tool fix this session: `load_all_cases` (task_disruption/prepare_review now find independent cases); `prepare_review.py --include-unlabeled --proposals`.

## F. Architecture and decisions (why)
- OpenAI-compatible HTTP adapter first (Ollama/local + hosted); no vendor SDKs, no LangChain.
- Models: Ollama `llama3.2:1b` (run 1) and `llama3.1:8b` (run 2, ~4.9 GB pulled; selected per run via `LLM_MODEL`/`CLASSIFIER_MODEL` env overrides, `.env` stays on 1B). Findings are model-specific and PRELIMINARY; classifier = the same model as the summarizer in each run. Structural v3 and the classifier prompt were developed on the 1B model and not re-tuned for 8B.
- Detection vs policy separated; enforcement decision reported (allow/warn/block); `flag_only` = warn.
- **Oracle leakage rule:** pipeline gets no ground-truth criteria; the runner scores afterwards; E5 excludes L4.
- Structural prompt versions: v1 (original, byte-stable), v2, v3 (default; chosen on dev by a pre-set rule; fixed v1's over-refusal but showed no ASR benefit on the 1B model).
- Scoring: regex indicators (literals tolerate separators incl. none); quoted/reported matches -> `needs_review`; unknowns excluded from the ASR denominator, reported, and bounded.
- Classifier parser accepts the first complete JSON object (1B model adds stray `}`); detector failures are counted, never "benign".
- Splits: dev (`dev_cases.jsonl`) vs held-out (`heldout_*.jsonl`, checksum-frozen, disjoint families/templates). Held-out authored by the same AI as the rules: not independent.
- Evidence labels: `SMOKE TEST ONLY` (mock, or all-dev data), `PRELIMINARY` (real model on project-authored synthetic data incl. held-out).
- Run metadata records code commit + dirty flag. Frontend uses `textContent` only (tested).
- Deviations from the master prompt: `llm/provider.py`, `evaluation/report.py`, `execute.py/registry.py/store.py` added; no `utils/`; Transformers training script not built.

## G. Environment
macOS (Apple M4, 16 GB RAM), Python 3.13.9 (Anaconda) in `.venv`. Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`; `cp .env.example .env`; `python scripts/verify_environment.py`.
`.env` (git-ignored) is set to the 1B model: `LLM_PROVIDER=openai_compatible`, `LLM_MODEL=llama3.2:1b`, `LLM_BASE_URL=http://localhost:11434/v1`, dummy key `ollama`, and `CLASSIFIER_PROVIDER=openai_compatible` / `CLASSIFIER_MODEL=llama3.2:1b`. No real API keys exist.
Ollama (`/opt/homebrew/bin/ollama`) has `llama3.2:1b` (1.3 GB) and `llama3.1:8b` (4.9 GB) installed; the server must be running (`ollama serve`). Run 2 used env overrides, not `.env`:
`LLM_MODEL=llama3.1:8b CLASSIFIER_MODEL=llama3.1:8b python scripts/run_experiments.py ...`.
**Quirk:** the editable `.pth` gets the macOS `hidden` flag -> use `PYTHONPATH=src`, `uvicorn --app-dir src`; scripts/tests self-heal. The built-in preview launcher did not work for the server; run uvicorn directly (README) and open it in the browser pane.
Local-only data on this machine: `results/` (git-ignored: run folders with model outputs, `results/review/`, `results/review_independent_run1/`). Archived copies without model text are in `docs/results/final_run_{1,2}/` and `docs/results/independent_run_1/`.

## H. Commands and outcomes
- `pytest` -> 246 passed (2026-10-27). `python scripts/verify_environment.py` -> ok (mock mode + Ollama configured; classifier via Ollama).
- `python scripts/run_experiments.py ... --dry-run` -> plan printed, no calls. Mock `run_experiments` + `analyze_results` -> ok.
- Real dev runs (smoke): see DEV_LOG. Final run 1: `python scripts/run_experiments.py --case-set final --final-ack --configs E0,E1,E1b,E2,E3,E4,E5 --repetitions 2 --real --yes` -> completed (826 outcomes); `analyze_results.py aee56f02e584` -> ok.
- Not run: Anthropic live; Transformers classifier with a real model; any hosted model.

## H2. Exact commands (verified 2026-10-27)
- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && cp .env.example .env && python scripts/verify_environment.py`
- Tests: `PYTHONPATH=src .venv/bin/python -m pytest` (246 passed).
- App: `PYTHONPATH=src .venv/bin/uvicorn injection_defense.api:create_app --factory --app-dir src` then open http://127.0.0.1:8000/ (mock mode default; real mode needs `ollama serve` and the `.env` model).
- Independent set, one model: `python scripts/run_experiments.py --case-set independent --final-ack --configs E0,E1,E1b,E2,E3,E4,E5 --repetitions 2 --real --yes` (8B: prefix `LLM_MODEL=llama3.1:8b CLASSIFIER_MODEL=llama3.1:8b`; add `--dry-run` first; about 1,800-2,000 calls; 1B about 1.5 h, 8B about 5.5 h).
- Review: `python scripts/prepare_review.py <run_id> --include-unlabeled --out <folder>`; fill decisions; `python scripts/apply_review.py <folder>/review_decisions.csv --dry-run` then without `--dry-run`; `python scripts/analyze_results.py <run_id>`; `python scripts/task_disruption.py <run_id> --review <folder>/review_decisions.csv`.
- Audit: `PYTHONPATH=src python scripts/audit_independent.py --write` (read-only; needs `results/4da08316a2fb` and `results/8a4c672e6307`).
- Next milestone: only optional work remains (full-paper literature reading, second blinded reviewer, hosted model, Transformers classifier, Reverse Text post-hoc review). Literature review, frontend and demo script done.

## I. Research and experimental state
Datasets: dev 18, held-out attacks 24, held-out benign 24 (all project-authored synthetic; see DATASET_GUIDE); independent set 75 attacks + 25 benign (BIPIA `text_attack_test.json` instructions, MIT, in 25 AI-generated documents; see INDEPENDENT_SET).
Experiments completed with held-out data: final runs 1 and 2 (run 2 8B: ASR E0 48.6%, E1 28.6%, E2 18.6%, E3 20.0%, E4 8.6%, E5 10.0%; 8B classifier FPR 0/48; see EXPERIMENT_LOG and FINAL_REPORT). Run 1 (1B): ASR E0 34.3%, E1 11.4%, E2 40.0% (after human correction), E3 34.3%, E4 21.4%, E5 21.4%; heuristic detection 72.7% familiar vs 8.3% held-out).
Independent run 1 (1B, post-review): ASR E0/E1/E1b 44.0%, E2 30.0%, E3 42.7%, E4 31.7%, E5 29.6%; heuristic detection 0/150; FPR 2/50 (sec-04 only). Independent run 2 (8B, post-review): ASR E0 39.9%, E1/E1b/E3 40.0%, E2 20.0%, E4 21.3%, E5 20.3%; detection 0 for both detectors; FPR 2/50 word rules (sec-04), 0/50 classifier. Result locations: `results/<run_id>/` (git-ignored). Limitations: small n, non-independent held-out, 1B model, lexical scoring, keyword utility proxy.

## J. Problems and blockers
- Findings are specific to a 1B local model and project-authored data (held-out authored by the same AI as the rules).
- Labels were verified by one non-blinded human reviewer (the author); an independent second reviewer would be stronger. A hosted model and torch/transformers need the user's decision/access.
- Python 3.13 on macOS may skip the hidden editable `.pth` (README troubleshooting).

## K. Immediate next steps
1. (done) 1B-vs-8B comparison and FINAL_REPORT update. 2. Literature review (FINAL_REPORT section 5). 3. Literature review (section 5). 4. Demo script after the run. 5. Optional: Reverse Text post-hoc review (kept separate); a second, blinded reviewer.

## L. Continuation instructions
Read `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `README.md`, and `docs/EXPERIMENT_PROTOCOL.md`. Inspect `git status` and the actual files. Verify the recorded state (`pytest`) before continuing. Resume the highest-priority incomplete task without redoing verified work or discarding existing changes. Checkpoint checklist: stop starting big tasks; save work; `git status`; quick `pytest`; update this file (status, E, K); commit.
