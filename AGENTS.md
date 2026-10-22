# AGENTS.md: persistent instructions for any AI agent working here

**Current project state lives in `HANDOFF.md`** (canonical). This file holds rules that do not
change from session to session. Do not duplicate status here.

## Objective

Research project: *Evaluating layered defenses against indirect prompt injection in LLM-based
document summarization.* A FastAPI app with a configurable defense pipeline plus an evaluation
harness. Central question and RQ1-RQ6: `docs/RESEARCH_PLAN.md`. Threat model: `docs/THREAT_MODEL.md`.
The contribution is careful measurement (security vs. utility vs. generalization), not a new
defense. Never claim prompt injection is solved or that results are general guarantees.

## Read before major changes

`HANDOFF.md` -> `README.md` -> `docs/EXPERIMENT_PROTOCOL.md` -> `docs/ARCHITECTURE.md`.
Then inspect `git status`, `git log`, and the real files. Do not trust any status claim (including
the handoff) without checking it.

## Architecture in one screen

`src/injection_defense/`: `config.py` (Settings, DefenseConfig, PRESETS) · `schemas.py` ·
`pipeline.py` (orchestration; detection -> policy -> prompt -> LLM -> output validation) ·
`api.py` (FastAPI) · `documents.py` (file text extraction) · `llm/` (interface, mock, real
providers) · `defenses/` (heuristic + rules, classifier, structural prompt variants, output
validator) · `evaluation/` (dataset, splits, metrics, runner, reporting). `frontend/` is static
HTML/JS served by the API. `scripts/` are CLIs. `data/` holds JSONL cases.

Key separations (keep them): detection vs. policy; runtime output validation vs. evaluation
scoring (the pipeline never receives ground-truth criteria); main model vs. classifier model;
mock vs. real model.

## Conventions

Python 3.10+, type hints, small focused functions, Pydantic schemas at boundaries, no new
dependency without a clear purpose, match surrounding style and comment density. No LangChain.
Config via environment (`.env.example` documents every variable). One implementation per
responsibility; no placeholder modules.

## Testing

`pytest` must pass with no network and no credentials (`tests/conftest.py` blocks network and
scrubs env). Use deterministic fakes (`ScriptedLLM`, `MockLLM`). Add tests with every feature.
Never weaken an assertion to get green; fix the cause. Run the suite before marking anything DONE.

## Research integrity (non-negotiable)

1. Never fabricate or round up results; every reported number must trace to a saved run.
2. Mock-model output is plumbing only. `evidence_status` labels runs `SMOKE TEST ONLY` /
   `PRELIMINARY`; never mix categories.
3. No silent fallback to the mock when a real model is requested. Unavailable defenses/experiments
   are reported `UNAVAILABLE`/`NOT_RUN`, never zero-filled.
4. Tune only on `data/dev_cases.jsonl`. Held-out files (`data/heldout_*.jsonl`) are frozen by
   checksum (`data/heldout.sha256`, enforced by a test). Do not read per-case held-out results to
   change rules, prompts, thresholds, or scoring; if that happens, record that the set is spent.
5. Do not change scoring criteria after seeing results to improve numbers. If a scorer bug is
   found, fix it, say so in `docs/EXPERIMENT_LOG.md`, and re-run.
6. Report denominators, unknown/`needs_review` counts, and failures separately. Missing is never favorable.
7. Keep hypotheses separate from findings. Do not invent citations; verify sources.
8. Real model calls only when explicitly requested/configured; state the call count first.

## Security

No secrets in code, logs, API responses, docs, or git. `.env` is git-ignored. Do not log document
or summary text. The untrusted document must never change defense configuration. Uploaded files
are parsed, never executed. No arbitrary file paths from clients.

## Keeping records

- Update `HANDOFF.md` after each milestone, test session, experiment, dataset change, and before
  any long task or when context may run low (checklist in HANDOFF.md section L).
- Record design decisions (what and why) in `HANDOFF.md` section F; methodology in the research docs.
- Record every executed experiment in `docs/EXPERIMENT_LOG.md`; dev-time observations in `docs/DEV_LOG.md`.
- Mark `DONE` only after verification (command + actual outcome). Otherwise `NEEDS_VERIFICATION`.
- Commit locally at milestones with meaningful messages; never commit secrets, results, or
  data whose license forbids it. Never discard uncommitted work.

## macOS quirk

The venv's editable-install `.pth` may get the `hidden` flag and be skipped by Python 3.13. Use
`PYTHONPATH=src` for ad-hoc commands and `uvicorn ... --app-dir src`. Details in README.
