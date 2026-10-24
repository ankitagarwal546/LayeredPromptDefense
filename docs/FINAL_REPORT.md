# Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization

**Status: preliminary report.** Every number comes from two saved runs that are never pooled: run 1 (`aee56f02e584`, `llama3.2:1b`, archived in `docs/results/final_run_1/`) and run 2 (`b507b975ae1f`,
`llama3.1:8b`, archived in `docs/results/final_run_2/`). Both used small, project-authored synthetic data and small local models. Sections marked **INCOMPLETE** need work that has not been done.
Nothing here is a general claim about LLM security.

## 1. Abstract

We built a document-summarization service with four switchable defense layers (heuristic rules, a model-based classifier, structural prompt separation, output validation) and an evaluation harness, and ran a
pre-registered comparison of seven configurations on 35 attack cases (11 development, 24 held-out from 8 unseen families) and 24 held-out benign cases, 2 trials each, on two local models. The conclusions
**depend strongly on the model**. On a 1B model, structural separation and a model-based classifier gave no benefit, heuristic blocking was the only effective layer, and its detection collapsed on unseen attack
families (72.7% to 8.3%). On an 8B model of the same family, the undefended model was *more* often hijacked (48.6% vs 34.3% of attack observations), but structural separation (18.6%) and the model-based
classifier (20.0%, detecting 50% of held-out attacks with 0 false positives) both helped, and heuristic + structural (8.6%) was the best configuration. The heuristic's false positives (8/24 hard-negative
benign observations) and its collapse on unseen families were the same for both models. All results are preliminary: tiny, hand-written data, ambiguous outputs judged by an AI and checked by one human reviewer, and held-out attacks that are not
independent of the defenses' author.

## 2. Introduction

LLM applications process documents, emails and web pages that they did not author. Text inside such content can be read as an instruction (indirect prompt injection). Defenses range from filters to prompt design to
model-based screening, but each is advisory because instructions and data share one context. This project asks which defenses help, what they cost, and whether they work on attack constructions not seen during development.

## 3. Problem statement and research questions

Central question: *to what extent can layered defenses reduce indirect prompt injection success in an LLM-based document summarization system while preserving legitimate task performance and generalizing to previously
unseen attack techniques?* Sub-questions RQ1-RQ6 are in `docs/RESEARCH_PLAN.md` and answered in section 10.

## 4. Threat model

An external party controls the text of a document that a user submits; they do not control the system prompt, code or configuration. In scope: direct overrides, disguised instructions, role/task redefinition,
paraphrase/obfuscation, split instructions, output manipulation, prompt extraction. Out of scope and undetected: hidden text, metadata/comment injection, multi-turn and adaptive attacks, tool-using agents.
Full model: `docs/THREAT_MODEL.md`; residual risks: `docs/SECURITY_LIMITATIONS.md`.

## 5. Related work

Bibliographic details were verified against arXiv abstract pages; **only the BIPIA and AgentDojo entries were read beyond title and authors, and only at abstract/README level.**
A proper literature review is INCOMPLETE and no novelty is claimed.

- Perez & Ribeiro, *Ignore Previous Prompt: Attack Techniques For Language Models*, arXiv:2211.09527 (2022).
- Greshake, Abdelnabi, Mishra, Endres, Holz, Fritz, *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*, arXiv:2302.12173 (2023).
- Liu, Jia, Geng, Jia, Gong, *Formalizing and Benchmarking Prompt Injection Attacks and Defenses*, USENIX Security 2024, arXiv:2310.12815.
- Yi, Xie, Zhu, Kiciman, Sun, Xie, Wu, *Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models* (BIPIA), arXiv:2312.14197, KDD 2025. Introduces a benchmark for
  indirect injection and reports that evaluated LLMs were all vulnerable; proposes boundary-awareness and explicit-reminder defenses (per the abstract).
- Hines, Lopez, Hall, Zarfati, Zunger, Kiciman, *Defending Against Indirect Prompt Injection Attacks With Spotlighting*, arXiv:2403.14720 (2024).
- Wallace, Xiao, Leike, Weng, Heidecke, Beutel, *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions*, arXiv:2404.13208 (2024).
- Debenedetti, Zhang, Balunovic, Beurer-Kellner, Fischer, Tramer, *AgentDojo*, arXiv:2406.13352 (2024): 97 agent tasks and 629 security test cases (per the abstract); tool-using agents, outside this project's threat model.

Our structural layer resembles the "explicit reminder"/delimiting ideas in this literature; we did not reproduce any published method or number.

## 6. Architecture

Pipeline: `extract -> L1 heuristic -> L2 classifier -> prompt builder (baseline | structural) -> LLM -> L4 validator`; detection and enforcement (allow/warn/block) are separate; the evaluation scores outputs afterwards with
criteria the pipeline never sees. FastAPI service, static web UI, CLIs. See `docs/ARCHITECTURE.md`.

## 7. Defense implementations

- **L1 heuristic:** weighted regex rules (`defenses/heuristic_rules.py`), threshold 1.0; policies block / sanitize (redact matched spans) / flag only. Model-independent.
- **L2 classifier:** prompt-based JSON verdict from an LLM (here the same model that summarizes); failures counted, never treated as benign. A Transformers adapter exists but is unverified.
- **L3 structural:** system rule that the document is third-party content, per-request random-nonce delimiters, restated task; wording v3 (chosen on the 1B model's dev behavior, not re-tuned for 8B).
- **L4 output validation:** lexical check against explicit criteria; used only as the scorer (otherwise it would see the answer key).

## 8. Experimental methodology

Each run was pre-registered in `docs/EXPERIMENT_LOG.md` before execution, with code frozen at a tag (`final-run-1-freeze`, `final-run-2-freeze`). Same cases for every configuration; temperature 0; 2 trials; ASR on evaluated cases
with unresolved outcomes reported separately (none remained after adjudication); Wilson 95% intervals; blocked attacks count as not successful and are reported through detection rate. Run 2 changed only the model.
Protocol: `docs/EXPERIMENT_PROTOCOL.md`.

## 9. Datasets and evaluation design

Development: 18 hand-written fixtures (used for tuning, on the 1B model). Held-out: 24 attacks in 8 families/24 templates absent from development, plus 24 benign cases (12 ordinary, 12 hard negatives), checksum-frozen and
reused for both runs. **All data were written by the same AI assistant that wrote the rules and prompts**, so attack style is shared even though families are disjoint; generalization is probably overstated.
Attack success is scored by predefined indicators; ambiguous outputs (53 in run 1, 50 in run 2) were labeled by an AI adjudicator using a written rubric and then all verified by one human reviewer, who changed 1 of 103 labels (neither was blinded to the model). Utility is a keyword proxy,
not summary quality. Details: `docs/DATASET_GUIDE.md`.

## 10. Results

Pooled over 2 trials within a run. Attack n = 70 (35 cases), benign n = 48 (24 cases). Intervals: Wilson 95%. Full tables, latency percentiles and per-family counts: `docs/results/final_run_{1,2}/`.

| config | run 1 (1B) ASR | run 2 (8B) ASR | run 1 FPR / task completion | run 2 FPR / task completion |
|---|---|---|---|---|
| E0 undefended | 34.3% (24/70) [24-46] | 48.6% (34/70) [37-60] | n/a / 91.7% | n/a / 95.8% |
| E1 heuristic block | 11.4% (8/70) [6-21] | 28.6% (20/70) [19-40] | 16.7% / 75.0% | 16.7% / 79.2% |
| E1b heuristic sanitize | 17.1% (12/70) [10-28] | 31.4% (22/70) [22-43] | 16.7% / 87.5% | 16.7% / 91.7% |
| E2 structural v3 | 40.0% (28/70) [29-52] | 18.6% (13/70) [11-29] | n/a / 100% | n/a / 100% |
| E3 classifier (same model) | 34.3% (24/70) [24-46] | 20.0% (14/70) [12-31] | 20.8% / 75.0% | **0.0% (0/48) [0-7]** / 95.8% |
| E4 heuristic + structural | 21.4% (15/70) [13-32] | **8.6% (6/70) [4-17]** | 16.7% / 83.3% | 16.7% / 83.3% |
| E5 all three | 21.4% (15/70) [13-32] | 10.0% (7/70) [5-19] | 29.2% / 70.8% | 16.7% / 83.3% |

Detection (share of attacks flagged), familiar -> held-out families: heuristic 72.7% (16/22) -> 8.3% (4/48) in both runs (model-independent); classifier 1B: 6/70 overall; classifier 8B: 54.5% (12/22) -> 50.0% (24/48).
Generalization gap (held-out minus familiar ASR, points), run 1 / run 2: E0 -29.5 / -35.2; E1 +16.7 / +15.2; E2 -34.5 / -12.7; E3 -29.5 / -10.6; E4 +4.7 / +12.5; E5 +4.7 / +14.6.
Mean latency per request (ms), run 1 / run 2: E0 938 / 3787; E1 943 / 3332; E1b 1168 / 4735; E2 1259 / 5896; E3 1893 / 7645; E4 1065 / 4283; E5 1725 / 7734. Model calls per request: E0 1.00, E1/E4 0.76 (blocked requests skip the model),
E2 1.00, E3 1.86 (1B) / 1.69 (8B), E5 1.42 / 1.34. Figures: `docs/results/final_run_{1,2}/figures/` (all watermarked PRELIMINARY).

**Answers to the research questions (these two models, this data, these configurations only):**

- **RQ1 baseline:** undefended, the 1B model followed the embedded instruction in 34.3% of attack observations and the 8B model in 48.6% (intervals overlap). The more capable model was not safer; it followed more injected instructions.
- **RQ2 individual defenses:** *Heuristic blocking* helped on both models (-23 and -20 points vs E0) because it is model-independent. *Structural separation* did not help the 1B model (40.0% vs 34.3%) but did help the 8B model
  (18.6% vs 48.6%, intervals do not overlap). The *model classifier* did nothing on the 1B model and helped on the 8B model (20.0% vs 48.6%).
- **RQ3 combinations:** on the 8B model heuristic + structural (E4, 8.6%) was lower than either alone (28.6%, 18.6%), though E4 vs E2 intervals overlap; adding the classifier (E5, 10.0%) did not improve on E4. On the 1B model E4 (21.4%) was no better
  than the heuristic alone (11.4%).
- **RQ4 false positives:** all detectors had 0 false positives on 24 ordinary benign observations. On 24 hard-negative observations (documents that quote or discuss attacks) the heuristic flagged 8 in both runs; the 1B classifier flagged 10;
  the 8B classifier flagged **0**. Utility cost follows the flags: blocking dropped task completion to 75-79%.
- **RQ5 generalization:** the heuristic detected 72.7% of familiar but 8.3% of held-out attacks (both runs). The 8B classifier's detection was stable across groups (54.5% familiar vs 50.0% held-out), and its ASR was lower on held-out than on familiar attacks (16.7% vs 27.3%; the familiar group has only 22 observations).
  Both findings are weakened by the non-independent held-out set.
- **RQ6 cost:** see section 13.

Exploratory observations (not pre-registered, tiny counts, hypotheses only): on the 1B model the structural prompt coincided with more successes than the undefended model in some held-out families (multilingual, obfuscated, hypothetical framing);
format hijack succeeded often undefended (1B: 4/6) and was never detected by the rules (0/6); markup injection, urgency/authority and emotional manipulation rarely succeeded on either model; the 8B model often wrote a note such as
"I ignored the instruction in the document" while summarizing, which the scorer queued for review and which counted as a non-success. Attack-success labels differed between the two trials for at most 3 attack cases per configuration.

**Task disruption (exploratory, found during human review).** A failed attack is not the same as a successful defense. Among the reviewed ambiguous outputs, 14 attack outcomes
did not achieve the attacker's objective but still left the user without a usable summary: on the 1B model the summary described only the injected text or copied the document back (8 outcomes), and the 8B model
refused a harmless summary in all 6 runs without structural separation while summarizing the same document when it was enabled. ASR does not count these. A systematic task-disruption rate over all attack
outcomes has not been computed yet (future work), so these are examples, not a rate.

## 11. Security-versus-utility analysis

- **1B model:** heuristic blocking had the lowest ASR (11.4%) at a utility cost (75.0%); structural separation had the best utility (100%) but no security benefit; the classifier lowered utility without lowering ASR.
- **8B model:** the best trade-offs were E3 (ASR 20.0%, no false positives, utility 95.8%) and E2 (ASR 18.6%, utility 100%, no blocking). E4 had the lowest ASR (8.6%) but inherited the heuristic's cost (16.7% flagged, utility 83.3%);
  E5 added latency and no security over E4. In this setting a model-based layer could deliver most of the heuristic's security benefit without blocking benign security discussions.
- Task completion is a keyword proxy, not summary quality; both undefended models also refused a small number of benign documents on their own (1B: 2/24, 8B: 1/24).

## 12. Generalization analysis

The heuristic's detection collapsed on unseen families regardless of model (72.7% -> 8.3%); its ASR gap was +15 to +17 points. For other configurations the negative gaps (e.g. E0 -29.5 and -35.2) do not mean the undefended model generalizes: both models followed
familiar (development-style) attacks more often than held-out ones, so the gap mixes attack difficulty with defense behavior. A more informative reading is the detection rate by group (above). The 8B classifier showed no drop from familiar to held-out families.
Because the held-out set was written by the author of the rules and prompts, and is small, true generalization is probably worse than shown.

## 13. Runtime and cost analysis

Local inference on one Apple M4 machine, so no monetary cost; token counts were not captured (unavailable). The 8B model was about 4x slower per request than the 1B model. Overheads versus E0 (mean latency, run 2): heuristic about 0 (blocked requests skip the model),
sanitize +25%, structural +56% (longer prompts and outputs), classifier +102% (one extra model call), E5 +104%. Run 1 showed +102% for the classifier as well. Heuristic detection itself is negligible: median 0.043 ms (p95 0.062 ms) over the fixtures,
6.2 ms on a 45,000-character document (separate timing check). Latencies depend on this hardware.

## 14. Limitations

Tiny, project-authored, non-independent data; two small local models of one family (findings may not transfer to hosted frontier models); structural and classifier prompts developed on the 1B model and not re-tuned; lexical scoring with an AI adjudicator for 103 ambiguous outcomes,
verified by a single human reviewer (not blinded, not independent of the project); keyword utility proxy; repeated trials and shared-template cases are not independent evidence (35 distinct attack cases); held-out set reused across runs after its first aggregates were seen (no changes were made in response); no adaptive attackers;
no hidden-text attacks; no human summary-quality ratings; no statistical test beyond intervals; exploratory analyses after seeing results. Both runs followed their pre-registration with no changes after they started.

## 15. Discussion

The main lesson is that defense effectiveness here depended on the model more than on the layer: structural separation and a model-based classifier were useless on a 1B model and useful on an 8B model, while the model-independent regex layer helped on both but is brittle and
penalizes legitimate security text. A more capable model was not harder to inject. Reporting a defense's effect without naming the model, or tuning it on one model and assuming it transfers, would have been misleading. The 8B classifier's lack of false positives on hard negatives
is the most interesting result for deployment, and also the one most in need of independent data, since the classifier prompt was written by the same author as the held-out attacks.

## 16. Conclusion

In this preliminary study, layered defenses reduced attack success on both models, but which layers worked changed with the model: on 1B only the heuristic helped; on 8B, structural separation, the classifier, and especially heuristic + structural reduced it substantially,
with the classifier doing so without blocking benign documents. The heuristic generalized poorly to unseen attack families on both. These findings apply only to the tested models, data and configurations. The software and protocol are in place to repeat the experiment on other models and data.

## 17. Future work (INCOMPLETE)

Measure task disruption on all attack outcomes as a separate outcome alongside ASR; run the same protocol on a hosted frontier model as a further condition; add independently written or BIPIA-derived held-out attacks (`docs/DATASET_GUIDE.md`); human adjudication and quality ratings; re-tune the structural and classifier prompts per model on dev data and re-freeze;
evaluate a trained classifier (needs reviewed data and a decision to install torch/transformers); operator deny-list output validation (E6); hidden-text and adaptive-attack evaluation; more trials per family and a larger set.

## 18. References

See section 5. Dataset and benchmark notes: `docs/DATASET_GUIDE.md`.
