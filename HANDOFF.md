# HANDOFF.md: canonical project state

Last updated: 2026-10-23 (session 1, checkpoint 3: final run 1 IN PROGRESS). Update at every checkpoint (see L).

## A. Project identity
- **Title:** Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization
- **Objective:** working summarizer with a configurable defense pipeline + reproducible evaluation (RQ1-RQ6: `docs/RESEARCH_PLAN.md`)
- **Repo:** `/Users/ankitagarwal546/Documents/Prompt Injection` (git, branch `master`, no remote). Tag `final-run-1-freeze` marks the frozen code for final run 1.
- **Phase:** software complete (Phases 1-4); Phase 6 final run 1 started; analysis/report (Phases 7-8) pending the run.

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
| Trained classifier (training script) | BLOCKED | no reviewed dataset/licence; no torch; documented in DATASET_GUIDE |
| Docs: THREAT_MODEL, RESEARCH_PLAN, ARCHITECTURE, PROTOCOL, DATASET_GUIDE, SECURITY_LIMITATIONS, DEV_LOG, EXPERIMENT_LOG | DONE (EXPERIMENT_LOG has pre-registration; run results pending) | |
| `docs/FINAL_REPORT.md` | TODO (needs final run results) | |
| Final run 1 (E0,E1,E1b,E2,E3,E4,E5; final case set; 2 reps; llama3.2:1b) | IN_PROGRESS | see E |
| Independent held-out data (e.g. BIPIA) | TODO / BLOCKED on data access | steps in DATASET_GUIDE |
| Human adjudication, human utility ratings | TODO | needs a human |

## C. Completed and verified
- `pytest` -> **185 passed** (2026-10-23, offline, ~6 s). Includes API, evaluation, CLI subprocess, frontend-static, extraction, adapter tests.
- Live checks: Ollama real-model summarize via API/UI; `run_experiments.py --dry-run` plan and guards (needs `--yes`, `--final-ack`); mock run + analyze; adjudicate flow.
- Dev real-model smoke runs and structural-prompt tuning: `docs/DEV_LOG.md`.
- Commits: see `git log` (foundation, extraction/store/API, frontend, CLIs, adapter, freeze + label fix).

## D. Remaining tasks (priority order)
| ID | Task | Status | Acceptance |
|---|---|---|---|
| R1 | Finish final run 1 (see E), then `analyze_results.py`, adjudicate `needs_review` (rubric in protocol), re-analyze | IN_PROGRESS | run folder complete; labels recorded with adjudicator named; EXPERIMENT_LOG entry with actual numbers |
| R2 | Write `docs/FINAL_REPORT.md` from the saved run only; update RESEARCH_PLAN (hypotheses vs findings), README status | TODO | every number traceable to the run id |
| R3 | Run with a stronger model (hosted key or larger Ollama model) as a separate experimental condition | TODO / needs user | new run id; never mixed with the 1B run |
| R4 | Independent held-out attacks (BIPIA adapter) | TODO | `DATASET_GUIDE` steps; new frozen set |
| R5 | Transformers classifier real verification (user must approve torch + weights download) | TODO | one real model run; update status |
| R6 | Human adjudication + summary-quality rubric ratings on a subset | TODO | human-labeled records |
| R7 | Optional: operator-deny-list output validation as E6 | TODO | criteria independent of scorer |

## E. Current task checkpoint (R1)
- Final run started with: `python scripts/run_experiments.py --case-set final --final-ack --configs E0,E1,E1b,E2,E3,E4,E5 --repetitions 2 --real --yes`
  (background; log `/private/tmp/claude-501/final_run_1.log`; run folder `results/aee56f02e584/`; 826 outcomes expected = 59 cases x 2 reps x 7 configs).
- **Do not read per-case held-out results to change anything** (pre-registered in `docs/EXPERIMENT_LOG.md`).
- If the run was interrupted: `python scripts/run_experiments.py --resume aee56f02e584 --case-set final --final-ack --configs E0,E1,E1b,E2,E3,E4,E5 --repetitions 2 --real --yes`
  (needs Ollama running: `ollama serve`; resume refuses if model/config/dataset changed). Verify with `wc -l results/aee56f02e584/outcomes.jsonl` (expect 826).
- Safest next action: wait for completion, then `analyze_results.py aee56f02e584`.

## F. Architecture and decisions (why)
- OpenAI-compatible HTTP adapter first (Ollama/local + hosted); no vendor SDKs, no LangChain.
- Main model: Ollama `llama3.2:1b` (free, already installed). Very weak: all findings are model-specific and PRELIMINARY. Classifier model for E3/E5: same model.
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
macOS, Python 3.13.9 (Anaconda) in `.venv`. Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`; `cp .env.example .env`; `python scripts/verify_environment.py`.
`.env` (git-ignored) currently: `LLM_PROVIDER=openai_compatible`, model `llama3.2:1b`, base `http://localhost:11434/v1`, dummy key `ollama`; `CLASSIFIER_PROVIDER=openai_compatible` with the same model. No real API keys exist.
Ollama: `/opt/homebrew/bin/ollama`, server must be running. **Quirk:** the editable `.pth` gets the macOS `hidden` flag -> use `PYTHONPATH=src`, `uvicorn --app-dir src`; scripts/tests self-heal.
The built-in preview launcher did not work for the server; run uvicorn directly (README) and open it in the browser pane.

## H. Commands and outcomes
- `pytest` -> 185 passed. `python scripts/verify_environment.py` -> ok (mock mode + Ollama configured; classifier via Ollama).
- `python scripts/run_experiments.py ... --dry-run` -> plan printed, no calls. Mock `run_experiments` + `analyze_results` -> ok.
- Real dev runs (smoke): see DEV_LOG. Final run 1: IN_PROGRESS (E).
- Not run: Anthropic live; Transformers classifier with a real model; any hosted model.

## I. Research and experimental state
Datasets: dev 18, held-out attacks 24, held-out benign 24 (all project-authored synthetic; see DATASET_GUIDE). External benchmark: none integrated (BIPIA investigated: summarization contexts must be built locally from XSum; AgentDojo is agent-focused).
Experiments completed with held-out data: none yet (final run 1 in progress). Result locations: `results/<run_id>/` (git-ignored). Limitations: small n, non-independent held-out, 1B model, lexical scoring, keyword utility proxy.

## J. Problems and blockers
- Run speed ~35 outcomes/min with the local model (~1 hour for 826).
- `needs_review` outputs need adjudication (AI-assisted labels must be marked as such and human-verified).
- A hosted/stronger model and torch/transformers need the user's decision.

## K. Immediate next steps
1. Wait for run `aee56f02e584`; confirm 826 outcomes and `finished_at` in metadata. 2. `python scripts/analyze_results.py aee56f02e584`. 3. Adjudicate `needs_review` (`adjudicate.py`, rubric in protocol). 4. Re-analyze; log in EXPERIMENT_LOG (actual numbers only). 5. Write FINAL_REPORT. 6. Update this file, commit.

## L. Continuation instructions
Read `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `README.md`, and `docs/EXPERIMENT_PROTOCOL.md`. Inspect `git status` and the actual files. Verify the recorded state (`pytest`) before continuing. Resume the highest-priority incomplete task without redoing verified work or discarding existing changes. Checkpoint checklist: stop starting big tasks; save work; `git status`; quick `pytest`; update this file (status, E, K); commit.
