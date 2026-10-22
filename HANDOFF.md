# HANDOFF.md: canonical project state

Last updated: 2026-10-23 (session 1, checkpoint 1). Update this file at every checkpoint (see L).

## A. Project identity
- **Title:** Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization
- **Objective:** working summarizer with a configurable defense pipeline + reproducible evaluation (RQ1-RQ6 in `docs/RESEARCH_PLAN.md`)
- **Repo:** `/Users/ankitagarwal546/Documents/Prompt Injection` (git, branch `master`, no remote)
- **Phase:** Phases 1-2 and most of 4 done; building Phase 3 (frontend/upload/API extras) and Phase 6 tooling.

## B. Current status

| Area | Status | Notes |
|---|---|---|
| Project structure, deps, `.env.example`, `.gitignore` | DONE | clean-copy install verified earlier |
| Mock LLM (labeled dev-only) | DONE | `llm/mock.py` |
| Real adapters (OpenAI-compatible, Anthropic) | DONE for OpenAI-compatible via Ollama (live-verified with `llama3.2:1b`); Anthropic NEEDS_VERIFICATION (stub-transport tests only) | |
| L1 heuristic detector + policies | DONE | rules in `defenses/heuristic_rules.py` |
| L2 prompt classifier | NEEDS_VERIFICATION | unit-tested with fake LLM; never run against a real classifier model |
| L3 structural separation (v1,v2,v3) | DONE | default v3 |
| L4 output validator | DONE (as scorer + optional guard) | lexical; `needs_review` for ambiguous |
| Pipeline, enforcement (block/sanitize/flag_only) | DONE | allow/warn/block decision field: TODO (see D) |
| API `/health`, `/summarize` | DONE | |
| API `/config`, `/extract`, `/evaluate`, `/results` | TODO | |
| Document extraction (txt/md/pdf/docx) | TODO | |
| Frontend | TODO | |
| Dataset loader, splits, held-out freeze | DONE | |
| Metrics (ASR, FPR, utility, gap, latency, Wilson) | DONE | ASR sensitivity bounds: TODO |
| Experiment CLI (resume, dry-run), analyze, adjudicate | TODO | `scripts/run_smoke_eval.py`, `tune_structural.py` exist |
| Trained (Transformers) classifier | TODO / BLOCKED on user permission to download torch + model weights | adapter with injected pipeline planned |
| Real-model experiments | IN_PROGRESS | only dev smoke runs so far (`docs/DEV_LOG.md`); no held-out run yet |

## C. Completed tasks (verified)
- Foundation + pipeline + defenses + eval harness + tests: `pytest` -> **111 passed** (2026-10-22, 0.25 s, no network).
- Live real-model smoke (E0,E1,E1b,E2,E4) on dev with Ollama `llama3.2:1b`: ran; results in `docs/DEV_LOG.md` (smoke only).
- Held-out set (24 attacks/8 families, 24 benign) authored and frozen: `data/heldout.sha256`, `tests/test_heldout.py`.
- Known limitations: see `docs/SECURITY_LIMITATIONS.md` (when created), `README.md`.

## D. Remaining tasks (priority order)
| ID | Task | Priority | Status | Acceptance |
|---|---|---|---|---|
| T1 | allow/warn/block `enforcement_decision` in response + logging module | P1 | TODO | tests; response field present |
| T2 | `documents.py` extraction + `/extract` | P1 | TODO | txt/md/pdf/docx tests incl. malformed/oversize |
| T3 | `/config`, `/evaluate` (job, allowlisted datasets, call-count confirm), `/results` | P1 | TODO | tests; no arbitrary paths |
| T4 | Frontend (`frontend/`) | P1 | TODO | verified in a browser: submit, defenses, compare, export |
| T5 | `scripts/run_experiments.py` (dry-run, resume, cost guard), `analyze_results.py`, `adjudicate.py`, ASR bounds | P1 | TODO | tested on mock; real run resumable |
| T6 | Transformers classifier adapter | P2 | TODO | injected-pipeline unit test; docs of limits |
| T7 | Real run E0-E5 dev+held-out (freeze first) | P1 | TODO | saved run, logged in EXPERIMENT_LOG |
| T8 | Docs: DATASET_GUIDE, SECURITY_LIMITATIONS, EXPERIMENT_LOG, FINAL_REPORT; update others | P1 | TODO | no invented numbers |
| T9 | Independent held-out attacks (e.g. BIPIA after license check) | P2 | TODO/BLOCKED on data access | documented adapter steps |
| T10 | Human adjudication of `needs_review`; human utility ratings | P2 | TODO | needs a human |

## E. Current task checkpoint
Starting T1-T5 in order. Nothing partially edited. Safest next action: run `pytest`, then T1.

## F. Architecture and decisions (why)
- **Provider:** OpenAI-compatible HTTP adapter first (works with Ollama/local and hosted); no vendor SDKs, no LangChain; custom pipeline for control.
- **Main model in use:** Ollama `llama3.2:1b` (already installed locally, free). Very weak model: results are model-specific and PRELIMINARY.
- **Detection vs policy:** detectors only report; pipeline applies policy (`block`, `sanitize`, `flag_only`=warn).
- **Oracle-leakage rule:** pipeline never gets ground-truth criteria; the runner scores outputs afterwards. L4 is a scorer in experiments, so E5 excludes L4.
- **Structural prompt:** versions v1 (original, byte-stable), v2, v3 (default). v3 chosen on dev by a pre-set rule (max benign completion, tie -> lower ASR): it removed v1's over-refusal but showed no ASR benefit on this model.
- **Scoring:** regex indicators; literal indicators tolerate separators; quoted/reported matches -> `needs_review`; unknowns excluded from ASR denominator and reported.
- **Splits:** dev = `dev_cases.jsonl`; held-out = `heldout_*.jsonl` (families/templates disjoint, checksum-frozen). Held-out was authored by an LLM that also wrote the rules: not independent.
- **Evidence labels:** `SMOKE TEST ONLY` (mock or dev fixtures), `PRELIMINARY` (real model on project-authored synthetic data).
- **Deviations from the master prompt:** `llm/provider.py` (not `providers.py`); `evaluation/report.py` (not `reporting.py`); no `utils/`.

## G. Environment
macOS, Python 3.13.9 (Anaconda) in `.venv`. Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`; `cp .env.example .env`.
Local model: Ollama (`/opt/homebrew/bin/ollama`), model `llama3.2:1b` (1.3 GB) present; server must be running (`ollama serve`).
`.env` (git-ignored) currently set to Ollama via `openai_compatible`; no real API keys exist.
**Quirk:** editable-install `.pth` gets macOS `hidden` flag -> use `PYTHONPATH=src`, `uvicorn --app-dir src`.

## H. Commands and outcomes
- `pytest` -> 111 passed (2026-10-22).
- `python scripts/run_smoke_eval.py` (mock) -> works; E3/E5 reported UNAVAILABLE.
- `python scripts/run_smoke_eval.py --real --experiments E0,E1,E1b,E2,E4` (Ollama) -> ran; see DEV_LOG.
- `python scripts/tune_structural.py --real --repetitions 2` -> ran; see DEV_LOG.
- Not run: held-out evaluation; classifier with a real model; Anthropic adapter live.

## I. Research and experimental state
Datasets: `data/dev_cases.jsonl` (18 synthetic), `data/heldout_attacks.jsonl` (24), `data/heldout_benign.jsonl` (24), all project-authored synthetic. No external benchmark integrated (BIPIA investigated; AgentDojo is agent-focused; see RESEARCH_PLAN). Experiments completed: dev smoke only. Pending: E0-E5 held-out. Result locations: `results/<run_id>/` (git-ignored). Limitations: small n, non-independent held-out, 1B model, lexical scoring.

## J. Problems and blockers
- No hosted-model API key (not required; Ollama used).
- Trained classifier needs `torch`/`transformers` + weights download: ask the user first.
- `needs_review` outputs need a human label.

## K. Immediate next steps
1. T1 enforcement decision + logging. 2. T2 extraction. 3. T3 API. 4. T4 frontend + browser check. 5. T5 CLIs. 6. freeze + T7 real run. 7. T8 docs.

## L. Continuation instructions
Read `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, `README.md`, and `docs/EXPERIMENT_PROTOCOL.md`. Inspect `git status` and the actual files. Verify the recorded state (`pytest`) before continuing. Resume the highest-priority incomplete task without redoing verified work or discarding existing changes. Checkpoint checklist: stop starting big tasks; save work; `git status`; quick `pytest`; update this file (status, checkpoint E, next steps); commit.
