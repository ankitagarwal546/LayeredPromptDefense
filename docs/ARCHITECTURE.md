# Architecture

## Components

```
                         +------------------+
 HTTP client ---------->|  api.py (FastAPI) |  GET /health, POST /summarize
                         +---------+--------+
                                   | SummarizeRequest (schemas.py)
                                   v
                         +------------------+      config.py: Settings (env), DefenseConfig, PRESETS
                         | pipeline.py      |
                         | DefensePipeline  |
                         +--+----+----+--+--+
   document text            |    |    |  |
        |                   |    |    |  +--> L4 defenses/output_validator.py  (after generation)
        v                   |    |    |
  L1 defenses/heuristic.py -+    |    +-----> defenses/structural.py  (L3 / baseline prompt builder)
     (rules in heuristic_rules.py)|                      |
  L2 defenses/classifier.py -----+                      v PromptBundle(system, user)
     (PromptClassifier | UnavailableClassifier)     llm/base.py  LLMClient
                                                       |-- llm/mock.py      (DEV ONLY)
                                                       `-- llm/provider.py  (OpenAI-compatible, Anthropic)

 evaluation/  dataset.py (JSONL) -> runner.py (E0..E5 x cases) -> metrics.py -> report.py
              splits.py (hold out whole attack families/templates)
```

## Data flow for `POST /summarize`

1. Pydantic validates the request (size limits, non-blank).
2. The API picks the model: `mock` or `real` (explicit, or `DEFAULT_MODEL_MODE`). `real`
   without configuration raises `ModelNotConfiguredError` -> HTTP 503. It never falls back to
   the mock. With `model_name`, a real request may use one of `LLM_EXTRA_MODELS` (same provider
   and base URL); any other name is rejected with 422 `unknown_model`. The classifier always uses
   `CLASSIFIER_MODEL`.
   `/summarize` builds the real client with `UI_MAX_TOKENS` / `UI_TIMEOUT_S` (web UI only);
   `/evaluate` and the CLIs keep `LLM_MAX_TOKENS` / `LLM_TIMEOUT_S`. The classifier is unaffected.
2b. `general_task=true` (sent by the web UI) gives the pipeline `role=GENERAL_ROLE`: the prompt
   builders swap only the leading `BASE_SYSTEM` sentence, so the model does the user's task
   instead of being told it is a summarizer. Default `false`; the evaluation runner never sets it,
   so experiments use the evaluated prompts byte-for-byte.
3. Pipeline, in order, for each enabled layer:
   - **L1 heuristic** -> `DetectionResult`; the *pipeline* applies the policy (`block`,
     `sanitize` = redact matched spans, `flag_only`).
   - **L2 classifier** -> `DetectionResult` (`evaluated` / `unavailable` / `error`); policy
     `block` or `flag_only`. Unavailable/error is *fail-open* by default
     (`fail_closed_on_detector_error` flips it).
   - If blocked: return `status="blocked"` with no model call.
   - **Prompt build:** `structural` on -> `build_structural_prompt`, else `build_baseline_prompt`.
   - **Generate** via `LLMClient.generate(PromptBundle)`. System and user content stay separate
     (system message vs. user message).
   - **L4 output validation** if enabled and criteria were supplied; policy `withhold` or `flag_only`.
4. Response: summary, defense config, per-layer detections (with `policy_action`), validation,
   model info (`is_mock`), model-call count, latency and per-stage timings, warnings.

## Defense pipeline and the detection/policy split

Detectors only *report* (`Detector.detect(text) -> DetectionResult`). What happens next is
pipeline policy configured in `DefenseConfig`. This lets an experiment compare e.g. block vs.
sanitize with the same detector (E1 vs E1b).

## Model-provider interface

`LLMClient.generate(PromptBundle) -> LLMResponse`. Implementations: `MockLLM` (deterministic,
labeled `is_mock`), `OpenAICompatibleClient` (chat-completions; works with OpenAI and many
local servers via `LLM_BASE_URL`), `AnthropicClient` (Messages API). Provider errors become
`LLMError` with a sanitized message (status code only; no keys or bodies). The real adapters
are unit-tested against a stubbed HTTP transport only; they have not been run against a live
endpoint in this repository.

## Configuration

- `Settings` (pydantic-settings): env vars / `.env`; keys are `SecretStr`.
- `DefenseConfig`: per-request layer switches and policies; `PRESETS` E0..E5 (+E1b).
- The classifier has its own provider settings (`CLASSIFIER_*`), falling back to `LLM_*`.

## Evaluation harness

`load_cases` (JSONL -> `EvalCase`, strict validation, per-line errors) -> `run_matrix`
(same cases for every config; metadata: run id, model, generation params, dataset SHA-256,
configs, evidence status) -> `CaseOutcome` records -> `metrics` (ASR, FPR, utility, gap,
latency; all with explicit denominators) -> `report` (pandas table, matplotlib plot).
Outcomes are saved to `results/<run_id>/` (git-ignored).

**Scoring is separate from defense.** The runner never gives the pipeline the case's success
criteria; it scores outputs afterwards with `OutputValidator`. Otherwise L4 would be an oracle
(see EXPERIMENT_PROTOCOL.md).

## API design

Two endpoints; stateless; synchronous handler (FastAPI runs it in a threadpool). Error
bodies are `{"error": code, "message"?}`: 422 validation, 502 provider failure, 503 real model
not configured, 500 generic (no trace).

## Logging and data handling

One INFO line per request: request id, status, blocked_by, config name, model, mock flag,
model calls, latency. Never document text, summaries, prompts, or keys. Documents are not
stored. The experiment runner stores model outputs in `results/` (git-ignored) because manual
adjudication needs them; disable with `store_outputs=False`.

## Extension points

| To add | Do |
|---|---|
| A new detector (e.g. trained HF classifier) | Subclass `Detector`, return `DetectionResult`; register in `pipeline._detection_layers` |
| A new real provider | Subclass `_HTTPClient` in `llm/provider.py` |
| New heuristic rules | Edit `heuristic_rules.py` or load a JSON file with `load_rules` |
| New dataset | Add JSONL lines (see `evaluation/dataset.py` schema) |
| New output evaluator (e.g. LLM judge) | Add alongside `OutputValidator`; keep it out of the generation path |
| PDF/DOCX input | Extract text upstream of `SummarizeRequest`; document hidden-text handling first |


## Update (2026-10-23): application layer, extraction, run store

New components since the first version:

| component | file | purpose |
|---|---|---|
| document extraction | `documents.py` | .txt/.md/.pdf/.docx -> plain text with limits and caveats; never executes content |
| enforcement decision | `pipeline.py`, `schemas.py` | `allow` / `warn` / `block`, plus `layers_run` and `reached_model` |
| logging | `logging_config.py` | idempotent setup; metadata-only lines |
| dataset registry | `evaluation/registry.py` | named case sets (`dev`, `final`) and call estimates; clients never pass paths |
| run store | `evaluation/store.py` | incremental `outcomes.jsonl`, resume, manual labels, safe run listing |
| executor | `evaluation/execute.py` | the one place that runs and persists a matrix (CLI and API both call it) |
| frontend | `frontend/` | static page served at `/app/` (text via `textContent` only): landing page with the overview (`GET /findings`), then a dashboard (Test a document with the live run view and "why it was blocked", Results, How it works, Evaluations) |
| scripts | `scripts/` | `run_experiments.py`, `analyze_results.py`, `adjudicate.py`, `verify_environment.py`, `run_smoke_eval.py`, `tune_structural.py` |

Flow of untrusted content (the thing to keep in mind when changing code):

```
upload bytes --> documents.extract_text (size/type checks, parse only) --> document_text  [UNTRUSTED]
document_text --> L1 heuristic (reads) --> L2 classifier (reads; its own LLM call, also exposed to the text)
              --> prompt builder: system message = trusted app text; user message = task + delimited document
              --> LLM --> summary [UNTRUSTED output] --> (L4 validator) --> API / UI (rendered as text only)
Trusted: server settings, request.defenses (set by the operator/user), system prompts, scoring criteria.
The document never influences configuration, scoring criteria or which defenses run.
```

Evaluation data flow: `registry.build_case_set` -> `execute_run` -> `run_matrix` (pipeline gets NO criteria) -> `score_case`
(validator with the case's criteria, after the fact) -> `RunWriter.append` (one line per case, flushed) -> `analyze_results.py`
(applies `manual_labels.jsonl`). The API's `/evaluate` runs `execute_run` in a background thread, one job at a time; job state is in memory,
run data persists on disk.

API additions: `GET /config` (non-sensitive options), `POST /extract`, `POST /evaluate` + `GET /evaluate/{job_id}`, `GET /results`,
`GET /results/{run_id}`, `GET /results/{run_id}/table.csv`, `GET /results/{run_id}/outcomes.csv` (no model output text).
Error contract: 422 validation/extraction, 409 confirmation required or job already running, 502 provider failure, 503 real model not configured, 404 unknown run/job.

Optional classifier backend: `TransformersClassifier` (local Hugging Face model via an injected predictor; chunked inference; no LLM calls).
