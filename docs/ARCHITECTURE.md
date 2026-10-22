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
   the mock.
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
