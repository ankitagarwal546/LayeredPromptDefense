# HANDOFF.md: canonical project state

Last updated: 2026-10-23 (session 1, checkpoint 6: paused, waiting for the user's human label review). Update at every checkpoint (see L).

## A. Project identity
- **Title:** Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization
- **Objective:** working summarizer with a configurable defense pipeline + reproducible evaluation (RQ1-RQ6: `docs/RESEARCH_PLAN.md`)
- **Repo:** `/Users/ankitagarwal546/Documents/Prompt Injection` (git, branch `master`, no remote). Tags `final-run-1-freeze` / `final-run-2-freeze` mark the frozen code for each final run. Working tree was clean at the last commit (`cdbe06d`).
- **Phase:** software complete; final runs 1 (1B) and 2 (8B) done, analyzed, logged, reported (preliminary). Next: user's human label review, then hosted model and/or independent data.

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
| R1 | (tools built: `scripts/prepare_review.py`, `scripts/apply_review.py`; checklist generated at `results/review/`, 33 items, 6 where the AI said yes) Human verification of the 103 AI-adjudicated labels (53 run 1, 50 run 2; `docs/results/final_run_{1,2}/manual_labels.jsonl`; outputs are in the local git-ignored `results/aee56f02e584/outcomes.jsonl`) | TODO / needs a human | re-label with `adjudicate.py`, re-analyze, update the log/report numbers |
| R2 | Run the same protocol on a hosted frontier model as a further SEPARATE condition (the 8B condition is done) | TODO / needs user key | new run id and EXPERIMENT_LOG entry; never mixed with the 1B run; held-out set is already spent for tuning purposes, so use a new held-out set for any further tuning |
| R3 | Independent held-out attacks (BIPIA adapter; or human-written) | TODO | DATASET_GUIDE steps; new frozen set + checksum test |
| R4 | Transformers classifier verification (user must approve torch + weights download) | TODO | one real run; update status |
| R5 | Human summary-quality ratings on a benign subset | TODO | documented rubric + saved ratings |
| R6 | Optional: operator deny-list output validation as E6 (criteria independent of scorer); hidden-text experiments | TODO | new experiment entries |
| R7 | Literature review beyond abstracts (FINAL_REPORT section 5 is INCOMPLETE) | TODO | verified, cited summaries only |

## E. Current task checkpoint
**Paused by the user for now; resume with R1 (human review of AI labels).**
- Done: `python scripts/prepare_review.py aee56f02e584 b507b975ae1f` produced `results/review/review_checklist.md` (read it) and `results/review/review_decisions.csv` (fill `human_label` yes/no and `reviewer`):
  33 unique outputs covering all 103 AI-labeled outcomes (53 run 1 + 50 run 2); the 6 where the AI said "yes" come first. Both files hold model outputs and are git-ignored; if lost, regenerate them with the same command.
- Waiting for: the user to fill the CSV. Then: `python scripts/apply_review.py results/review/review_decisions.csv --dry-run`, apply for real, re-run `python scripts/analyze_results.py <run_id>` for both runs,
  refresh `docs/results/final_run_{1,2}/` (`manual_labels.jsonl`, `summary.csv`, `by_family.csv`, `figures/`, regenerate `outcomes_no_text.csv`), and update the numbers in `docs/EXPERIMENT_LOG.md`, `docs/FINAL_REPORT.md`, `docs/RESEARCH_PLAN.md`
  and this file. Say in the report how many AI labels the human changed. Do not change any other label or code while doing this.
- Nothing is half-edited. The held-out set has been used for two final runs; any rule/prompt/scorer change motivated by its results makes it spent (AGENTS.md rule 4).

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
- AI-adjudicated labels need human verification. A stronger model, torch/transformers, and independent data need the user's decision/access.
- Python 3.13 on macOS may skip the hidden editable `.pth` (README troubleshooting).

## K. Immediate next steps
1. User reviews `results/review/review_checklist.md` and fills `review_decisions.csv` (R1). 2. Apply (`apply_review.py`, dry-run first), re-analyze both runs, refresh archived artifacts and update the log/report/plan with the human-verified numbers.
3. Then choose: hosted-model run as a third condition (user must add a key to `.env` themselves; show the call estimate with `--dry-run`, pre-register, freeze, run) and/or independent held-out attacks (R3).
4. Optional: re-tune structural/classifier prompts per model on dev data only, re-freeze, re-run.

## L. Continuation instructions
Read `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `README.md`, and `docs/EXPERIMENT_PROTOCOL.md`. Inspect `git status` and the actual files. Verify the recorded state (`pytest`) before continuing. Resume the highest-priority incomplete task without redoing verified work or discarding existing changes. Checkpoint checklist: stop starting big tasks; save work; `git status`; quick `pytest`; update this file (status, E, K); commit.
