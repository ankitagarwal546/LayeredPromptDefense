# Research Plan

Status: **plan and hypotheses only. No findings yet.**

## Working title

Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization

## Motivation

LLM applications ingest untrusted documents, emails and web pages. Instructions and data share
one natural-language context, so text inside a document can be treated as a command. For a
summarizer the harm is a corrupted or attacker-controlled output (and potentially leaked
configuration), not tool misuse; this makes it a tractable, well-scoped setting.

## Problem statement

Given a summarizer that must treat document text as data, how much do individual and combined
defenses reduce the success of embedded instructions, what do they cost in legitimate
performance and latency, and do they hold up on attack families not used during development?

## Central research question

To what extent can layered defenses reduce indirect prompt injection success in an LLM-based
document summarization system while preserving legitimate task performance and generalizing to
previously unseen attack techniques?

## Sub-questions

- **RQ1** Baseline vulnerability of the undefended model (E0).
- **RQ2** Effectiveness of individual defenses (E1, E2, E3).
- **RQ3** Whether combinations beat individuals (E4, E5).
- **RQ4** False positives on legitimate content, including hard negatives that discuss or quote attacks.
- **RQ5** Generalization to held-out attack families.
- **RQ6** Latency and extra model calls.

## Working hypotheses (untested)

- H1: The undefended model follows a non-trivial fraction of embedded instructions; rate varies by model and family.
- H2: Heuristics have low ASR on familiar families but a large positive generalization gap (obfuscated/multilingual/distributed evade rules) and non-zero FPR on security-themed benign text.
- H3: Structural separation lowers ASR for some models/families but not to zero.
- H4: A model classifier generalizes better than rules but adds a model call and is itself injectable.
- H5: Combinations reduce ASR further than any single layer, at a cost in FPR/latency; the gain may be smaller than the sum of parts because failures correlate.

Hypotheses may be falsified; report either outcome.

## Existing work to investigate

Verified bibliographic details (checked against arXiv abstract pages):

- Perez, F., Ribeiro, I. *Ignore Previous Prompt: Attack Techniques For Language Models.* arXiv:2211.09527 (2022). https://arxiv.org/abs/2211.09527
- Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., Fritz, M. *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection.* arXiv:2302.12173 (2023). https://arxiv.org/abs/2302.12173
- Liu, Y., Jia, Y., Geng, R., Jia, J., Gong, N. Z. *Formalizing and Benchmarking Prompt Injection Attacks and Defenses.* USENIX Security 2024; arXiv:2310.12815. https://arxiv.org/abs/2310.12815
- Yi, J., Xie, Y., Zhu, B., Kiciman, E., Sun, G., Xie, X., Wu, F. *Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models* (BIPIA). arXiv:2312.14197; KDD 2025. https://arxiv.org/abs/2312.14197
- Hines, K., Lopez, G., Hall, M., Zarfati, F., Zunger, Y., Kiciman, E. *Defending Against Indirect Prompt Injection Attacks With Spotlighting.* arXiv:2403.14720 (2024). https://arxiv.org/abs/2403.14720
- Wallace, E., Xiao, K., Leike, R., Weng, L., Heidecke, J., Beutel, A. *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions.* arXiv:2404.13208 (2024). https://arxiv.org/abs/2404.13208
- Debenedetti, E., Zhang, J., Balunović, M., Beurer-Kellner, L., Fischer, M., Tramèr, F. *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.* arXiv:2406.13352 (2024). https://arxiv.org/abs/2406.13352

To read in full before citing claims from them (only abstracts were checked): what each
reports about delimiter-style defenses, detection-based defenses, and generalization. Add
further related work (e.g. trained detectors, adaptive-attack studies) only after verifying it.

### Candidate evaluation resources

- **BIPIA** (github.com/microsoft/BIPIA): benchmark of instructions embedded in external
  content across five tasks (web QA, email QA, table QA, summarization, code QA). Closest match
  to this threat model. Per its README, some task data (web QA, summarization) cannot be
  redistributed and must be rebuilt locally under the sources' terms; code license is in its
  LICENSE file. Action: read the README and licenses, then decide what to reuse.
- **AgentDojo** (github.com/ethz-spylab/agentdojo, MIT): tasks for *tool-using agents*
  (email, banking, travel...) with injection test cases. Our system has no tools, so it is
  mostly outside scope; useful for attack ideas and as related work, not as a drop-in benchmark.

## Expected contribution (modest, to be earned)

Not a new defense. A reproducible, family-held-out comparison of simple layered defenses on a
summarization task, reporting security, false positives, utility, generalization gap and cost
together, with explicit denominators and intervals, plus open tooling. Novelty is not claimed.

## Methodology and metrics

See EXPERIMENT_PROTOCOL.md (configurations, splits, metric definitions, evidence labelling).

## Limitations

Small, partly synthetic datasets; few models; non-adaptive attackers; lexical output scoring
(manual adjudication needed); text-only input; no hidden-text attacks; defenses depend on the
tested model's behavior; results are not guarantees.

## One-week roadmap

| Day | Goal |
|---|---|
| 1 | Foundation: repo, pipeline, mock, heuristic, structural, metrics, tests (**done**) |
| 2 | Choose a real model + key; run E0 on dev fixtures; fix scoring problems; read BIPIA, check license/availability |
| 3 | Build dev + held-out attack sets (templates grouped by family; hard-negative benign set); freeze held-out |
| 4 | Configure the prompt classifier (E3/E5); tune rules/prompts on dev only |
| 5 | Final runs E0-E5 on held-out; repetitions; manual adjudication of `needs_review` |
| 6 | Analysis: tables, plots, intervals, gap, latency; failure-case analysis |
| 7 | Write-up; limitations; polish README; optional PDF/DOCX text extraction |


## Status update (2026-10-23)

Roadmap progress (actuals, not plans): foundation, pipeline, API, UI, evaluation harness, CLIs and tests are done. Real-model work so far used one local
1B model (`llama3.2:1b`). Dev-set observations are in `docs/DEV_LOG.md`; the pre-registered final run and its results are in `docs/EXPERIMENT_LOG.md`;
write-up in `docs/FINAL_REPORT.md`. Hypotheses H1-H5 above remain hypotheses until a run supports or contradicts them, and conclusions apply only to the tested
model, data and configuration. Not yet done: a stronger model, independently sourced held-out attacks, human adjudication, a trained classifier.


### Hypotheses vs. first findings (final run 1, `llama3.2:1b`, preliminary; 2026-10-23)

Hypotheses are as written above; findings apply only to this model, this data and these configurations (`docs/FINAL_REPORT.md`).

| hypothesis | outcome on this run |
|---|---|
| H1 undefended model follows a non-trivial fraction of embedded instructions | **Supported:** 34.3% (24/70), CI 24-46% |
| H2 heuristics: low ASR on familiar, large gap on held-out, false positives on security text | **Supported:** familiar 0/22 vs held-out 8/48; detection 72.7% -> 8.3%; hard-negative FPR 8/24, ordinary 0/24 |
| H3 structural separation lowers ASR for some models/families but not to zero | **Not supported here:** E2 41.4% vs E0 34.3% (overlapping CIs); utility rose to 100% |
| H4 a model classifier generalizes better than rules | **Not supported with a 1B classifier** (6/70 detected); says nothing about stronger classifiers |
| H5 combinations reduce ASR beyond any single layer, at an FPR/latency cost | **Not supported here:** E4 21.4% > E1 11.4%; E5 = E4 with higher FPR and latency |

### Hypotheses vs. findings after run 2 (`llama3.1:8b`, preliminary; 2026-10-23)

Run 2 reused all code, data and configs; only the model changed. Findings are per model and are not pooled.

| hypothesis | 1B (run 1) | 8B (run 2) |
|---|---|---|
| H1 undefended model follows a non-trivial fraction | Supported: 34.3% | Supported: 48.6% (higher than 1B; intervals overlap) |
| H2 heuristics: low familiar ASR, large held-out gap, security-text false positives | Supported | Supported (same detector; detection 72.7% -> 8.3%; hard-negative FPR 8/24) |
| H3 structural separation lowers ASR but not to zero | Not supported (41.4% vs 34.3%) | **Supported**: 18.6% vs 48.6%, not zero |
| H4 model classifier generalizes better than rules | Not supported (6/70 detected) | **Supported**: held-out detection 50.0% vs 8.3%; 0/48 false positives |
| H5 combinations beat any single layer at an FPR/latency cost | Not supported | **Partly supported**: E4 8.6% < E1 28.6%, E2 18.6% (E4 vs E2 overlap); E5 not better than E4 |
