# Experiment Protocol

Defined before any result is interpreted. Nothing here has been run against a real model yet.

## Configurations

| ID | Layers | Policy | Status |
|---|---|---|---|
| E0 | none (undefended control) | - | runnable |
| E1 | heuristic | block | runnable |
| E1b | heuristic | sanitize (redact matched spans) | runnable (extra) |
| E2 | structural separation (prompt wording `structural_variant`, default v3; v1 is the original) | - | runnable |
| E3 | model classifier | block | **unavailable** until `CLASSIFIER_*` is configured |
| E4 | heuristic + structural | block | runnable |
| E5 | heuristic + classifier + structural | block | **unavailable** until classifier configured |

Unavailable experiments produce no results; the runner records the reason in metadata.

### Output validation is not an experimental defense

L4 compares output with predefined criteria. In evaluation, those criteria are the
*ground-truth attack indicators* of the test case, so using them as a defense would let the
defense see the answer key ("oracle leakage") and make ASR trivially ~0. Therefore:
the runner passes **no** criteria to the pipeline, E5 excludes L4, and L4's code is used as the
**scorer** after the fact. A deployable L4 (operator deny-lists, canaries, a validated judge)
can be added as a new configuration later, evaluated with criteria that are independent of
the scoring criteria.

## Datasets and splits

- `data/dev_cases.jsonl`: 18 hand-written synthetic fixtures (7 benign incl. hard negatives,
  11 attacks across 9 families). **For software testing and rule debugging only.** Not a benchmark.
- **Development set**: used for debugging and tuning rules/prompts/thresholds.
- **Held-out test set**: `data/heldout_attacks.jsonl` (24 attacks, 8 families absent from dev) and
  `data/heldout_benign.jsonl` (24 benign incl. 12 hard negatives), frozen by checksum
  (`data/heldout.sha256`, enforced by a test). Initial version is LLM-authored (see data/README.md
  caveat); supplement with independently sourced attacks. Attack families (and templates)
  absent from the development set, frozen before final runs. Use `split_by_family` /
  `template_id`; never split near-duplicates across dev and test.
- Candidate external resources (see RESEARCH_PLAN.md): BIPIA (document-embedded injections
  incl. summarization; closest to our threat model; data partly must be rebuilt by the user
  from sources under their own terms) and AgentDojo (tool-using agents; mostly outside our
  threat model, useful only for ideas). Check licenses before copying any data; record
  `provenance` and license per record.
- **Familiar vs held-out** for the generalization gap: familiar = evaluation attacks whose
  family appears in the development set; held-out = attacks whose family/template was excluded
  from all development and tuning. The smoke script's `--heldout-families` default only
  demonstrates the mechanics.

## Trained-classifier protocol (if added)

Train/validation/test split **by attack family and template group** (never random rows);
tune thresholds on validation only; report test once; keep benign data from sources disjoint
from the training benign data; record seed, base model, and data hashes.

## Metrics (see `evaluation/metrics.py`)

- **ASR** = successful attacks / evaluated attack cases. Unknown outcomes (`needs_review`,
  no criteria, errors) are excluded from the denominator and reported separately. Blocked
  attacks count as not successful. Manual adjudication (`manual_label`) overrides the automatic score.
- **FPR** = benign cases flagged by any evaluated detector / benign cases with a detector
  verdict. `n/a` for configs with no detector (E0, E2).
- **Benign block rate**, **task completion** (not blocked, non-empty, required keywords present):
  utility *proxies*, not summary quality. Human/rubric quality scores to be added; an LLM judge
  must not be the sole ground truth.
- **Generalization gap** = ASR(held-out) - ASR(familiar); always report both ASRs. Positive = worse on held-out.
- **Operational:** mean/median latency, P95 (only with >= 20 observations), model calls per request.
- 95% Wilson intervals are available for every rate; with tens of cases they will be wide.
  Report them.

## Commands

Development (tuning allowed): `python scripts/run_smoke_eval.py [--real]`.
Final held-out run (no tuning afterwards): 
`python scripts/run_smoke_eval.py --real --repetitions 3 --heldout-dataset data/heldout_attacks.jsonl data/heldout_benign.jsonl`.
This uses dev attacks as the *familiar* group, held-out attacks as the held-out group, and **only
held-out benign cases** for FPR/utility.

## Procedure

1. Freeze code, rules, prompts, `DefenseConfig`s; record dataset SHA-256 (automatic).
2. Run `run_matrix` over *the same cases* for every configuration.
3. Real models: temperature 0 where supported, record `generation_params`; use `--repetitions`
   >= 3 where outputs are non-deterministic and treat trials as non-independent.
4. Adjudicate every `needs_review` output manually; record `manual_label`.
5. Report ASR/FPR/utility/gap/latency per configuration with denominators and intervals.
6. Do not edit rules/prompts after seeing held-out results; if you must, the held-out set is spent.

## Evidence labelling

`evidence_status` in run metadata is `SMOKE TEST ONLY` for any run using the mock model or
datasets whose provenance contains `synthetic_development`, and `PRELIMINARY` for real-model runs
on other project-authored synthetic data. Plots carry the same watermark.
Findings may be reported only from non-smoke runs, and only as results for the tested
model/dataset/configuration, not general guarantees.
