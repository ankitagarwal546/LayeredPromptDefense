# HANDOFF.md: canonical project state

Last updated: 2026-10-24 (session 2, checkpoint 12: independent run 1 (1B) DONE, pre-review; awaiting human review before the 8B run). Update at every checkpoint (see L).

## A. Project identity
- **Title:** Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization
- **Objective:** working summarizer with a configurable defense pipeline + reproducible evaluation (RQ1-RQ6: `docs/RESEARCH_PLAN.md`)
- **Repo:** `/Users/ankitagarwal546/Documents/Prompt Injection` (git, branch `master`, no remote). Tags `final-run-1-freeze` / `final-run-2-freeze` mark the frozen code for each final run. Working tree was clean at the last commit (`cdbe06d`).
- **Phase:** software complete; final runs 1 (1B) and 2 (8B) done, analyzed, logged, reported (preliminary). Next: the author reviews the independent run 1 unresolved outputs; then (user go-ahead) run the 8B model on the frozen set.

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
| Frontend | DONE | verified by hand in a browser (summarize, compare, upload, real local model, evaluation tab, XSS check) |
| Dataset loader, splits, held-out freeze | DONE | |
| Metrics (ASR, bounds, FPR, utility, gap, latency, failures, Wilson) | DONE | |
| CLIs: run_experiments (dry-run/resume/cost guard), analyze_results, adjudicate, verify_environment | DONE | subprocess-tested |
| Human review tools: `prepare_review.py`, `apply_review.py` | DONE | subprocess-tested; checklist generated in `results/review/` (git-ignored) |
| Trained classifier (training script) | BLOCKED | no reviewed dataset/licence; no torch; documented in DATASET_GUIDE |
| Docs: THREAT_MODEL, RESEARCH_PLAN, ARCHITECTURE, PROTOCOL, DATASET_GUIDE, SECURITY_LIMITATIONS, DEV_LOG, EXPERIMENT_LOG | DONE (EXPERIMENT_LOG has pre-registration; run results pending) | |
| `docs/FINAL_REPORT.md` | DONE (preliminary; sections 5 and 17 marked incomplete) | every number from run `aee56f02e584` |
| Final run 2 (same, llama3.1:8b; pre-registered, tag `final-run-2-freeze`) | DONE | run `b507b975ae1f`, 826 outcomes, 0 failures; artifacts in `docs/results/final_run_2/` |
| Final run 1 (E0,E1,E1b,E2,E3,E4,E5; final case set; 2 reps; llama3.2:1b) | DONE | run `aee56f02e584`, 826 outcomes, 0 failures; artifacts in `docs/results/final_run_1/` |
| Independent held-out data (e.g. BIPIA) | TODO / BLOCKED on data access | steps in DATASET_GUIDE |
| Human adjudication, human utility ratings | TODO | needs a human |

## C. Completed and verified
- `pytest` -> **187 passed** (2026-10-23, offline, ~6 s). Includes API, evaluation, CLI subprocess (incl. review tools), frontend-static, extraction, adapter tests.
- Live checks: Ollama real-model summarize via API/UI; `run_experiments.py --dry-run` plan and guards (needs `--yes`, `--final-ack`); mock run + analyze; adjudicate flow.
- Dev real-model smoke runs and structural-prompt tuning: `docs/DEV_LOG.md`.
- Commits: see `git log` (foundation, extraction/store/API, frontend, CLIs, adapter, freeze + label fix).

## D. Remaining tasks (priority order)
| ID | Task | Status | Acceptance |
|---|---|---|---|
| R1 | Human verification of the 103 AI-adjudicated labels | DONE (2026-10-24) | reviewer Ankit; 33 items, agreed 32, changed 1 (run 1 dev-a09 E2 t0 yes->no: run 1 E2 ASR 41.4% -> 40.0%); decisions in `docs/results/human_review_decisions.csv`; see EXPERIMENT_LOG |
| R8 | Task-disruption measure (separate outcome; ASR unchanged) | DONE (2026-10-24) | `evaluation/disruption.py`, `scripts/task_disruption.py`, criteria `data/task_disruption_carriers.json`; rule committed (`1ab56a4`) before computing; agrees with human labels 62/64; results in EXPERIMENT_LOG / FINAL_REPORT and `docs/results/final_run_{1,2}/task_disruption*.csv` |
| R2 | Run the same protocol on a hosted frontier model as a further SEPARATE condition (the 8B condition is done) | TODO / needs user key | new run id and EXPERIMENT_LOG entry; never mixed with the 1B run; held-out set is already spent for tuning purposes, so use a new held-out set for any further tuning |
| R3 | Independent set (BIPIA attacks in AI-generated benign documents; partially independent) | FROZEN; **run 1 (llama3.2:1b, `4da08316a2fb`) DONE pre-review**; human review of 358 unresolved outcomes pending; **8B run NOT started (user must approve)** | see section E |
| R4 | Transformers classifier verification (user must approve torch + weights download) | TODO | one real run; update status |
| R5 | Human summary-quality ratings on a benign subset | TODO | documented rubric + saved ratings |
| R6 | Optional: operator deny-list output validation as E6 (criteria independent of scorer); hidden-text experiments | TODO | new experiment entries |
| R7 | Literature review beyond abstracts (FINAL_REPORT section 5 is INCOMPLETE) | TODO | verified, cited summaries only |

## E. Current task checkpoint
Independent run 1 finished and verified: run id `4da08316a2fb`, 1,400 outcomes (100 cases x 7 configs x 2 trials), clean tree at tag `independent-freeze` (`a9991f5`), checksums OK, 0 model failures, 8 detector failures (classifier unparseable on ind-a51/ind-a61), 24 blocked. Results, commands, versions and scorer hashes are in `docs/EXPERIMENT_LOG.md`
(section "Independent run 1"); archived artifacts in `docs/results/independent_run_1/`. **Results are PRE-REVIEW:** 358 outcomes (119 distinct outputs) are unresolved; ASR bounds 16-53% overlap across configs; no between-config difference is established yet.
Waiting for the author:
1. Review `results/review_independent_run1/review_checklist.md` (119 items, the AI's PROPOSED label and why each needs a human; local, git-ignored, regenerate with `python scripts/prepare_review.py 4da08316a2fb --include-unlabeled --proposals results/review_independent_run1/proposals.json --out results/review_independent_run1` if lost; proposals are archived as `docs/results/independent_run_1/ai_proposed_judgments.json` (the local `proposals.json` has the same content)).
Fill `human_label` (yes/no) and `reviewer` in `review_decisions.csv`.
2. Then: `python scripts/apply_review.py results/review_independent_run1/review_decisions.csv --dry-run`, apply, `python scripts/analyze_results.py 4da08316a2fb`, `python scripts/task_disruption.py 4da08316a2fb` (add `--review` only if a `task_disrupted` column is filled), refresh `docs/results/independent_run_1/`, update the log with the human-verified numbers.
3. Optional post-hoc: `results/review_independent_run1/reverse_text_posthoc.md` (22 outputs, Reverse Text compliance in non-character forms; registered ASR unchanged; label any statement post-hoc).
4. Only after the author approves: the 8B run: `ollama serve`, then `LLM_MODEL=llama3.1:8b CLASSIFIER_MODEL=llama3.1:8b python scripts/run_experiments.py --case-set independent --final-ack --configs E0,E1,E1b,E2,E3,E4,E5 --repetitions 2 --real --yes` (est. 1,800 calls, ~2-3 h; keep the Mac awake), same preflight, separate run id, never pooled.
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
Local-only data on this machine: `results/` (git-ignored: run folders with model outputs, `results/review/`). Archived copies without model text are in `docs/results/final_run_{1,2}/`.

## H. Commands and outcomes
- `pytest` -> 187 passed. `python scripts/verify_environment.py` -> ok (mock mode + Ollama configured; classifier via Ollama).
- `python scripts/run_experiments.py ... --dry-run` -> plan printed, no calls. Mock `run_experiments` + `analyze_results` -> ok.
- Real dev runs (smoke): see DEV_LOG. Final run 1: `python scripts/run_experiments.py --case-set final --final-ack --configs E0,E1,E1b,E2,E3,E4,E5 --repetitions 2 --real --yes` -> completed (826 outcomes); `analyze_results.py aee56f02e584` -> ok.
- Not run: Anthropic live; Transformers classifier with a real model; any hosted model.

## I. Research and experimental state
Datasets: dev 18, held-out attacks 24, held-out benign 24 (all project-authored synthetic; see DATASET_GUIDE). External benchmark: none integrated (BIPIA investigated: summarization contexts must be built locally from XSum; AgentDojo is agent-focused).
Experiments completed with held-out data: final runs 1 and 2 (run 2 8B: ASR E0 48.6%, E1 28.6%, E2 18.6%, E3 20.0%, E4 8.6%, E5 10.0%; 8B classifier FPR 0/48; see EXPERIMENT_LOG and FINAL_REPORT). Run 1 (1B): ASR E0 34.3%, E1 11.4%, E2 41.4%, E3 34.3%, E4 21.4%, E5 21.4%; heuristic detection 72.7% familiar vs 8.3% held-out). Result locations: `results/<run_id>/` (git-ignored). Limitations: small n, non-independent held-out, 1B model, lexical scoring, keyword utility proxy.

## J. Problems and blockers
- Findings are specific to a 1B local model and project-authored data (held-out authored by the same AI as the rules).
- Labels were verified by one non-blinded human reviewer (the author); an independent second reviewer would be stronger. A hosted model, torch/transformers, and independent data need the user's decision/access.
- Python 3.13 on macOS may skip the hidden editable `.pth` (README troubleshooting).

## K. Immediate next steps
1. Author reviews the 119 unresolved outputs (E item 1) and optionally the Reverse Text post-hoc file. 2. Apply, re-analyze, update the log/report with human-verified numbers. 3. Ask the author for approval, then run the 8B model on the frozen independent set. 4. Add an "independent set" subsection to `docs/FINAL_REPORT.md` after both models are reviewed.

## L. Continuation instructions
Read `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `README.md`, and `docs/EXPERIMENT_PROTOCOL.md`. Inspect `git status` and the actual files. Verify the recorded state (`pytest`) before continuing. Resume the highest-priority incomplete task without redoing verified work or discarding existing changes. Checkpoint checklist: stop starting big tasks; save work; `git status`; quick `pytest`; update this file (status, E, K); commit.
