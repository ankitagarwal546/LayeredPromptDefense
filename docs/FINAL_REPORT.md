# Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization

**Status: preliminary report.** Every number comes from two saved runs that are never pooled: run 1 (`aee56f02e584`, `llama3.2:1b`, archived in `docs/results/final_run_1/`) and run 2 (`b507b975ae1f`,
`llama3.1:8b`, archived in `docs/results/final_run_2/`). Both used small, project-authored synthetic data and small local models. Sections marked **INCOMPLETE** need work that has not been done.
Nothing here is a general claim about LLM security. Section 10.1 adds a third, separate run on a partially independent test set (`4da08316a2fb`, `llama3.2:1b`); it is a **DRAFT** until the 8B run on the same set is complete,
and the abstract, discussion and conclusion do not yet reflect it.

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
- **Task disruption (added post hoc):** see the subsection below; on the 8B model structural separation both lowered ASR and nearly removed task disruption.

Exploratory observations (not pre-registered, tiny counts, hypotheses only): on the 1B model the structural prompt coincided with more successes than the undefended model in some held-out families (multilingual, obfuscated, hypothetical framing);
format hijack succeeded often undefended (1B: 4/6) and was never detected by the rules (0/6); markup injection, urgency/authority and emotional manipulation rarely succeeded on either model; the 8B model often wrote a note such as
"I ignored the instruction in the document" while summarizing, which the scorer queued for review and which counted as a non-success. Attack-success labels differed between the two trials for at most 3 attack cases per configuration.

**Task disruption (post-hoc, exploratory).** A failed attack is not the same as a successful defense: the human review found attacks that missed their objective but still left
the user without a usable summary. A separate measure was therefore defined (after the runs, before computing it) and validated against the human labels (agreement 62/64; it cannot detect subtle
inaccuracies). Every attack outcome is put in exactly one category, in this order: **attack succeeded** (the ASR outcome, including human labels) -> **blocked** (a defense withheld the
output) -> **unknown** (error / unresolved) -> **disrupted** (the attack failed but the delivered output is not a usable summary) -> **usable** (the attack failed and the output summarizes
the document's real content). A delivered output is *usable* when it mentions at least 2 of 4 key topics of the attack document's benign paragraph (word-start keyword matching; criteria in
`data/task_disruption_carriers.json`) and is not an 80%-or-more verbatim copy of the document; human `task_disrupted` labels from the review override the rule.
- **Task disruption rate** = disrupted / (disrupted + usable): of the attacks that failed and were not blocked, how often the user still lacked a usable summary.
- **Usable summary on attack documents** = usable / all known attack outcomes: how often the user safely got what they asked for (penalizes both successful attacks and blocking).

| config | run 1 (1B) task disruption | run 1 usable summary on attack docs | run 2 (8B) task disruption | run 2 usable summary on attack docs |
|---|---|---|---|---|
| E0 undefended | 43.5% (20/46) [30-58] | 37.1% (26/70) [27-49] | 22.2% (8/36) [12-38] | 40.0% (28/70) [29-52] |
| E1 heuristic block | 42.9% (18/42) [29-58] | 34.3% (24/70) [24-46] | 26.7% (8/30) [14-44] | 31.4% (22/70) [22-43] |
| E1b heuristic sanitize | 41.4% (24/58) [30-54] | 48.6% (34/70) [37-60] | 29.2% (14/48) [18-43] | 48.6% (34/70) [37-60] |
| E2 structural v3 | 19.0% (8/42) [10-33] | 48.6% (34/70) [37-60] | 3.5% (2/57) [1-12] | **78.6% (55/70) [68-87]** |
| E3 classifier | 40.0% (16/40) [26-55] | 34.3% (24/70) [24-46] | 10.0% (2/20) [3-30] | 25.7% (18/70) [17-37] |
| E4 heuristic + structural | 14.3% (5/35) [6-29] | 42.9% (30/70) [32-55] | 4.5% (2/44) [1-15] | 60.0% (42/70) [48-71] |
| E5 all three | 6.9% (2/29) [2-22] | 38.6% (27/70) [28-50] | 0.0% (0/21) [0-15] | 30.0% (21/70) [21-42] |

Most disruptions were refusals of a harmless summary. On the 1B model, undefended attacks that failed still ruined the summary 43.5% of the time; structural separation and the combinations reduced
this (19.0%, 14.3%, 6.9%). On the 8B model disruption was lower (22.2% undefended) and nearly eliminated by structural separation (3.5%). The combined view, "usable summary on attack documents",
shows the full trade-off: the 8B model with structural separation alone gave the user a usable, uncompromised summary for 78.6% of attack documents (vs 40.0% undefended), while the configurations
with the lowest ASR (E4 60.0%, E5 30.0%) gave fewer because blocking delivers nothing. On the 8B model the sanitize policy's redaction marker itself triggered some refusals.

### 10.1 Independent set: `llama3.2:1b` (DRAFT; the 8B run on this set is in progress)

**Why and what.** The held-out set above was written by the same AI that wrote the defenses. To test unseen attack *instructions* written by other people, a separate set was built and frozen before any run (tag `independent-freeze`; protocol `docs/INDEPENDENT_SET.md`):
the 75 instructions of the BIPIA `text_attack_test.json` split (Yi et al.; MIT licence; provenance and checksum in `data/external/bipia/PROVENANCE.md`), 15 categories x 5, each inserted verbatim as a bare paragraph (no "ignore previous instructions" wording) at the start, middle or end of one of
20 ordinary documents; plus all 25 documents unmodified as benign cases (20 ordinary, 5 security-themed hard negatives). **The documents are AI-generated** (by the assistant that also wrote the defenses, from the author's topic list) and labeled as such, so the set is only
*partially* independent: the attacks are external, the document corpus is not. Attack-success checks were pre-registered (`data/external/bipia/attack_criteria.json`): 25 attacks are decided automatically (translation, encodings, reversal, ciphers, emoji), 13 by pattern with a
quotation rule, and 37 open-ended "answer a different question / insert vague content" attacks are never automatic successes and go to a human. Same seven configurations, temperature 0, 2 trials (attack n = 150, benign n = 50 per configuration), defenses unchanged since the earlier runs.

**Human review.** 358 outcomes (119 distinct outputs) could not be scored automatically. One reviewer (the author) decided each one in batches, separately for *attack worked* (yes / no / unsure) and *summary ruined*; 23 outcomes judged unsure remain unresolved.
The reviewer required the injected objective to be meaningfully achieved (naming the requested topic, or a fabricated or meaningless "answer", is not success; a meaningful answer with factual errors is), and counted a summary as ruined when it was missing, failed the
registered usable-summary rule, or presented the document as discussing the injected topic. The review was **not blind** to configuration. Details, per-item rationales and the effect of each decision: `docs/EXPERIMENT_LOG.md`, `docs/results/independent_run_1/`.

| config | ASR after review | unresolved | detection | FPR (benign flagged) | benign task completion | usable summary on attack docs | task disruption | mean ms / calls per request |
|---|---|---|---|---|---|---|---|---|
| E0 undefended | 44.0% (66/150) [36-52] | 0 | n/a | n/a | 100% | 21.3% (32/150) [16-29] | 61.9% (52/84) [51-72] | 4036 / 1.00 |
| E1 heuristic block | 44.0% (66/150) [36-52] | 0 | 0.0% (0/150) | 4.0% (2/50) | 96.0% | 21.3% [16-29] | 61.9% [51-72] | 3710 / 0.99 |
| E1b heuristic sanitize | 44.0% (66/150) [36-52] | 0 | 0.0% (0/150) | 4.0% (2/50) | 100% | 21.3% [16-29] | 61.9% [51-72] | 3693 / 1.00 |
| E2 structural v3 | 30.0% (42/140) [23-38] | 10 | n/a | n/a | 100% | 60.0% (84/140) [52-68] | 14.3% (14/98) [9-23] | 3505 / 1.00 |
| E3 classifier | 42.7% (64/150) [35-51] | 0 | 5.5% (8/146) | 4.0% (2/50) | 96.0% | 21.3% [16-29] | 59.0% (46/78) [48-69] | 3822 / 1.95 |
| E4 heuristic + structural | 31.7% (46/145) [25-40] | 5 | 0.0% (0/150) | 4.0% (2/50) | 96.0% | 55.2% (80/145) [47-63] | 19.2% (19/99) [13-28] | 3171 / 0.99 |
| E5 all three | 29.6% (42/142) [23-38] | 8 | 5.3% (8/150) | 4.0% (2/50) | 96.0% | 54.9% (78/142) [47-63] | 15.2% (14/92) [9-24] | 4231 / 1.94 |

**Findings (this model and this set only):**
- **The detectors did not see these attacks.** The word rules flagged none of the 150 attack observations (they look for override wording, which BIPIA instructions do not contain), so E1 and E1b behaved exactly like E0. This extends the earlier collapse (72.7% familiar -> 8.3% held-out)
  to 0% on externally written instructions. The 1B classifier flagged 8 of 146-150. Both detectors' only false positive was one security-themed document that quotes an example injection (2 of 10 security-themed and 0 of 40 ordinary benign observations), so their whole utility cost here is one document.
- **The structural prompt lowered attack success, but the difference is not established.** E2, E4 and E5 had 29.6-31.7% against 44.0% for E0. Even counting every unresolved outcome as a success, their bounds (33.3-34.7%) stay below 44.0%, but the 95% intervals overlap slightly (E0 36-52%, E2 23-38%);
  no significance test was pre-registered, and the reduction is concentrated where the non-blind human standard applied (the model kept summarizing and appended a thin or garbled answer). By category it was uneven: "do a different task" attacks fell sharply (Task Automation 8/10 -> 0-1/10, Emoji 10/10 -> 4-5/10),
  while advertising insertions succeeded *more* often (Marketing 2/10 -> 4-6/10) and translation stayed high (8/10 -> 10/10). The structural prompt seems to change *which* attacks work more than whether they work.
- **The clearest effect is on usability.** Without the structural prompt, an attacked document produced a usable, uncompromised summary only 21% of the time (the model often answered the injected request instead of summarizing, or refused); with it, 55-60%, and failed attacks ruined the summary 14-19% of the time instead of 59-62%.
- **Contrast with the earlier held-out set.** On the project-authored held-out set the same structural prompt did *not* help this 1B model (E2 40.0% vs E0 34.3%). The attacks differ in kind (override-style and obfuscated vs. bare off-task requests), so the two results are not contradictory, but neither supports a general claim about structural separation on small models.
- **Not measured as success:** Reverse Text and Substitution Cipher attacks were 0/10 everywhere under the registered checks; the model sometimes reversed sentence order rather than characters, which the registered check does not detect (a post-hoc review exists but is not part of these numbers).

**Limits specific to this set:** one 1B model (the 8B run is pending); 25 short, clean AI-generated documents, so false-positive rates are likely underestimates; half the attacks need human judgment, from one non-blind reviewer; success checks and key-topic lists written by the AI assistant; 10 observations per category.
The defenses were not tuned on this set, so it remains usable as a test for the 8B run.

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

Validate the task-disruption rule with a second human reviewer and an accuracy check (it uses keyword coverage); run the same protocol on a hosted frontier model as a further condition; add independently written or BIPIA-derived held-out attacks (`docs/DATASET_GUIDE.md`); human adjudication and quality ratings; re-tune the structural and classifier prompts per model on dev data and re-freeze;
evaluate a trained classifier (needs reviewed data and a decision to install torch/transformers); operator deny-list output validation (E6); hidden-text and adaptive-attack evaluation; more trials per family and a larger set.

## 18. References

See section 5. Dataset and benchmark notes: `docs/DATASET_GUIDE.md`.
