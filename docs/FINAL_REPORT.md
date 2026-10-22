# Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization

**Status: preliminary report.** Every number below comes from one saved run (`aee56f02e584`, archived in `docs/results/final_run_1/`), using one tiny local
model (`llama3.2:1b`) and small, project-authored synthetic data. Sections marked **INCOMPLETE** need work that has not been done. Nothing here is a general
claim about LLM security.

## 1. Abstract

We built a document-summarization service with four switchable defense layers (heuristic rules, a model-based classifier, structural prompt separation, output
validation) and an evaluation harness, and ran a pre-registered comparison of seven configurations against 35 attack cases (11 development, 24 held-out from 8
unseen families) and 24 held-out benign cases, 2 trials each, on a local 1B-parameter model. Undefended, the model followed the embedded instruction in 34.3% of
attack observations (24/70, 95% CI 24-46%). Heuristic blocking cut this to 11.4% (8/70) but its detection rate fell from 72.7% on familiar attacks to 8.3% on held-out families, and it
flagged 33% of hard-negative benign documents (8/24 observations). Structural separation removed the model's over-refusal of benign inputs (utility 100%) but
did not reduce attack success (41.4%, 29/70). The prompt-based classifier, using the same 1B model, was ineffective (6/70 attacks detected, 34.3% ASR). Combining
heuristic and structural defenses (21.4%) was not better than the heuristic alone. These results show how brittle simple defenses can be across attack families, on this
model and data; they do not show how defenses behave on stronger models or realistic attacks.

## 2. Introduction

LLM applications process documents, emails and web pages that they did not author. Text inside such content can be read as an instruction (indirect prompt
injection). Defenses range from filters to prompt design to model-based screening, but each is advisory because instructions and data share one context. This project
asks which defenses help, what they cost, and whether they work on attack constructions not seen during development.

## 3. Problem statement and research questions

Central question: *to what extent can layered defenses reduce indirect prompt injection success in an LLM-based document summarization system while preserving
legitimate task performance and generalizing to previously unseen attack techniques?* Sub-questions RQ1-RQ6 are in `docs/RESEARCH_PLAN.md` and answered in section 10.

## 4. Threat model

An external party controls the text of a document that a user submits; they do not control the system prompt, code or configuration. In scope: direct overrides,
disguised instructions, role/task redefinition, paraphrase/obfuscation, split instructions, output manipulation, prompt extraction. Out of scope and undetected: hidden
text, metadata/comment injection, multi-turn and adaptive attacks, tool-using agents. Full model: `docs/THREAT_MODEL.md`; residual risks: `docs/SECURITY_LIMITATIONS.md`.

## 5. Related work

Bibliographic details below were verified against arXiv abstract pages; **only the BIPIA and AgentDojo entries were read beyond title and authors, and only at abstract/README level.**
A proper literature review is INCOMPLETE and no novelty is claimed.

- Perez & Ribeiro, *Ignore Previous Prompt: Attack Techniques For Language Models*, arXiv:2211.09527 (2022).
- Greshake, Abdelnabi, Mishra, Endres, Holz, Fritz, *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*, arXiv:2302.12173 (2023).
- Liu, Jia, Geng, Jia, Gong, *Formalizing and Benchmarking Prompt Injection Attacks and Defenses*, USENIX Security 2024, arXiv:2310.12815.
- Yi, Xie, Zhu, Kiciman, Sun, Xie, Wu, *Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models* (BIPIA), arXiv:2312.14197, KDD 2025. Introduces a benchmark for indirect injection
  and reports that evaluated LLMs were all vulnerable; proposes boundary-awareness and explicit-reminder defenses (per the abstract).
- Hines, Lopez, Hall, Zarfati, Zunger, Kiciman, *Defending Against Indirect Prompt Injection Attacks With Spotlighting*, arXiv:2403.14720 (2024).
- Wallace, Xiao, Leike, Weng, Heidecke, Beutel, *The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructions*, arXiv:2404.13208 (2024).
- Debenedetti, Zhang, Balunovic, Beurer-Kellner, Fischer, Tramer, *AgentDojo*, arXiv:2406.13352 (2024): 97 agent tasks and 629 security test cases (per the abstract); tool-using agents, outside this project's threat model.

Our structural layer resembles the "explicit reminder"/delimiting ideas in this literature; we did not reproduce any published method or number.

## 6. Architecture

Pipeline: `extract -> L1 heuristic -> L2 classifier -> prompt builder (baseline | structural) -> LLM -> L4 validator`; detection and enforcement (allow/warn/block) are
separate; the evaluation scores outputs afterwards with criteria the pipeline never sees. FastAPI service, static web UI, CLIs. See `docs/ARCHITECTURE.md`.

## 7. Defense implementations

- **L1 heuristic:** weighted regex rules (`defenses/heuristic_rules.py`), threshold 1.0; policies block / sanitize (redact matched spans) / flag only.
- **L2 classifier:** prompt-based JSON verdict from an LLM (here the same 1B model); failures counted, never treated as benign. A Transformers adapter exists but is unverified.
- **L3 structural:** system rule that the document is third-party content, per-request random-nonce delimiters, restated task; wording versions v1 (original) and v3 (used here).
- **L4 output validation:** lexical check against explicit criteria; used only as the scorer in these experiments (otherwise it would see the answer key).

## 8. Experimental methodology

Pre-registered before the run in `docs/EXPERIMENT_LOG.md`; code frozen at tag `final-run-1-freeze` (commit `adbf5d4`). Same cases for every configuration; temperature 0, 2 trials;
ASR on evaluated cases with unresolved outcomes reported separately (none remained after adjudication); Wilson 95% intervals; blocked attacks count as not successful and are
reported through detection rate. Protocol: `docs/EXPERIMENT_PROTOCOL.md`.

## 9. Datasets and evaluation design

Development: 18 hand-written fixtures (used for tuning). Held-out: 24 attacks in 8 families/24 templates absent from development, plus 24 benign cases (12 ordinary, 12 hard negatives),
checksum-frozen. **All data were written by the same AI assistant that wrote the rules and prompts**, so attack style is shared even though families are disjoint; results are likely optimistic
about generalization. Attack success is scored by predefined indicators; 53 ambiguous outcomes were labeled by an AI adjudicator (not a human) using a written rubric. Utility is a keyword
proxy (benign summary completed, not blocked, required keyword present), not summary quality. Details: `docs/DATASET_GUIDE.md`.

## 10. Results

Pooled over 2 trials. Attack n = 70 (35 cases), benign n = 48 (24 cases). Full table with intervals, latency percentiles and per-family counts: `docs/results/final_run_1/`.

| config | ASR [95% CI] | held-out ASR | detection familiar / held-out | FPR (flagged) | task completion | mean ms | calls |
|---|---|---|---|---|---|---|---|
| E0 undefended | 34.3% (24/70) [24-46] | 25.0% (12/48) | n/a | n/a | 91.7% (44/48) | 938 | 1.00 |
| E1 heuristic block | 11.4% (8/70) [6-21] | 16.7% (8/48) | 72.7% / 8.3% | 16.7% (8/48) | 75.0% (36/48) | 943 | 0.76 |
| E1b heuristic sanitize | 17.1% (12/70) [10-28] | 20.8% (10/48) | same detector | 16.7% (8/48) | 87.5% (42/48) | 1168 | 1.00 |
| E2 structural v3 | 41.4% (29/70) [31-53] | 29.2% (14/48) | n/a | n/a | 100% (48/48) | 1259 | 1.00 |
| E3 classifier (1B) | 34.3% (24/70) [24-46] | 25.0% (12/48) | 8.6% overall | 20.8% (10/48) | 75.0% (36/48) | 1893 | 1.86 |
| E4 heuristic + structural | 21.4% (15/70) [13-32] | 22.9% (11/48) | 72.7% / 8.3% | 16.7% (8/48) | 83.3% (40/48) | 1065 | 0.76 |
| E5 all three | 21.4% (15/70) [13-32] | 22.9% (11/48) | 81.8% / 16.7% | 29.2% (14/48) | 70.8% (34/48) | 1725 | 1.42 |

Figures: `docs/results/final_run_1/figures/` (security vs. utility, generalization, FPR, latency); all carry a PRELIMINARY watermark.

**Answers to the research questions (for this model, data and configuration only):**

- **RQ1 baseline:** the undefended 1B model followed the embedded instruction in 34.3% of attack observations; 54.5% on development attacks and 25.0% on held-out families. (The model also refused 2 benign documents unprompted.)
- **RQ2 individual defenses:** heuristic blocking reduced ASR to 11.4%; sanitizing to 17.1%; structural separation did not reduce it (41.4% vs 34.3%, overlapping intervals); the 1B classifier did not reduce it (34.3%).
- **RQ3 combinations:** E4 (21.4%) was higher than E1 alone (11.4%; the 95% intervals overlap, so this is suggestive only) and E5 added nothing over E4 while adding false positives. No evidence that combining helped on this model.
- **RQ4 false positives:** zero on 24 ordinary benign observations for every detector; on 24 hard-negative observations (documents that quote or discuss attacks) the heuristic flagged 8, the classifier 10, E5 14.
- **RQ5 generalization:** heuristic detection fell from 72.7% (16/22) to 8.3% (4/48) on held-out families; heuristic ASR was 0.0% (0/22) on development attacks and 16.7% (8/48) on held-out ones. Held-out gain over baseline was small (25.0% -> 16.7%, intervals overlap).
- **RQ6 cost:** see section 13.

Exploratory observations (not pre-registered, tiny counts, hypotheses only): in several held-out families the structural prompt coincided with more successes than the undefended model (multilingual 0/2 -> 2/2,
obfuscated 0/4 -> 2/4, hypothetical framing 0/6 -> 2/6); markup injection, urgency/authority and emotional manipulation rarely succeeded on this model; format hijack succeeded in 4/6 undefended and
was almost never detected by the rules (0/6). The attack-success label differed between the two trials for 3 (E2), 1 (E4) and 3 (E5) attack cases, and for none under the other configurations, despite temperature 0.

## 11. Security-versus-utility analysis

Heuristic blocking gave the lowest ASR (11.4%) but cost utility (75.0%): every false positive is a blocked benign document, and the hard negatives are exactly the security-themed documents a real
deployment may see. Sanitizing kept utility at 87.5% for a modest ASR increase (17.1%). Structural separation had the best utility (100%, because it removed the model's own refusals) with no security benefit
on this model. The classifier lowered utility (75.0%) without lowering ASR. No configuration was both clearly more secure and clearly as useful as the baseline; see the security-vs-utility figure.
The task-completion metric is a proxy and does not assess summary quality.

## 12. Generalization analysis

By the project's definition (gap = ASR held-out - ASR familiar) the gap was +16.7 points for E1, +11.7 for E1b, +4.7 for E4/E5 and negative for E0/E2/E3 (-29.5, -39.0, -29.5). Negative gaps do not mean
the undefended model generalizes: they reflect that this model followed *familiar* (development-style) attacks more often than held-out ones, so the gap mixes attack difficulty with defense behavior. The more informative
reading is the heuristic's detection rate, which collapsed on unseen families (72.7% -> 8.3%). Because the held-out set is not independent of the rules' author, true generalization is probably worse than shown.

## 13. Runtime and cost analysis

Local inference (Apple GPU via Ollama), so no monetary cost; token counts were not captured (unavailable). Mean latency per request: 938 ms (E0), 943 (E1; blocked requests skip the model, 0.76 calls/request), 1168 (E1b), 1259 (E2), 1893 (E3, one extra model call:
+102%), 1065 (E4), 1725 (E5). Heuristic detection itself is negligible: in a separate timing check (not part of the run) `detect()` took a median 0.043 ms (p95 0.062 ms) on the 1,320 calls over these fixtures (documents up to 452 characters) and 6.2 ms on a 45,000-character document. Latencies depend on this hardware and a 1B model.

## 14. Limitations

Tiny, project-authored, non-independent data; one weak local model (findings may not transfer to larger models); lexical scoring with an AI (not human) adjudicator for 53 outcomes; keyword utility proxy;
repeated trials and shared-template cases are not independent evidence (35 distinct attack cases); classifier tested only with the same 1B model; no adaptive attackers; no hidden-text attacks; no human summary-quality
ratings; no statistical test beyond intervals; exploratory analyses after seeing results. The pre-registration was followed with no changes after the run started.

## 15. Discussion

On this setup the cheapest defense (regex rules) delivered the largest measured reduction but is the least likely to survive new attack phrasings, as its collapse on held-out families suggests, and it penalizes legitimate
security discussions. Prompt-level separation is highly model-dependent: the same wording that changed refusal behavior produced no measurable protection here. Model-based screening cannot be judged from a 1B model.
Stronger conclusions need a stronger model, independently sourced attacks, human adjudication and larger samples.

## 16. Conclusion

In this preliminary study, layered defenses gave inconsistent and mostly modest protection against held-out attack families on a 1B model, with a clear security-utility trade-off for rule-based blocking and no demonstrated
benefit from structural separation or the 1B classifier. The software and protocol are in place to repeat the experiment on other models and data.

## 17. Future work (INCOMPLETE)

Run the same protocol on a stronger model as a separate condition; add independently written or BIPIA-derived held-out attacks (`docs/DATASET_GUIDE.md`); human adjudication and quality ratings; evaluate a trained classifier
(needs reviewed data and a decision to install torch/transformers); operator deny-list output validation (E6); hidden-text and adaptive-attack evaluation; repeat with more trials per family.

## 18. References

See section 5. Dataset and benchmark notes: `docs/DATASET_GUIDE.md`.
