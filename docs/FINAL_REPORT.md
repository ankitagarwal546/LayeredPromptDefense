# Evaluating Layered Defenses Against Indirect Prompt Injection in LLM-Based Document Summarization

**Status: preliminary report.** Every number comes from saved runs that are never pooled: run 1 (`aee56f02e584`, `llama3.2:1b`, `docs/results/final_run_1/`) and run 2 (`b507b975ae1f`, `llama3.1:8b`, `docs/results/final_run_2/`) on a project-authored held-out set,
and two further runs on a partially independent set of externally written attack instructions (section 10.1): run 3 (`4da08316a2fb`, `llama3.2:1b`, `docs/results/independent_run_1/`) and run 4 (`8a4c672e6307`, `llama3.1:8b`, `docs/results/independent_run_2/`). All used small synthetic or AI-generated documents and small local models.
Sections marked **INCOMPLETE** need work that has not been done. Nothing here is a general claim about LLM security.

## 1. Abstract

We built a document-summarization service with four switchable defense layers (heuristic rules, a model-based classifier, structural prompt separation, output validation) and an evaluation harness, and ran a
pre-registered comparison of seven configurations on 35 attack cases (11 development, 24 held-out from 8 unseen families) and 24 held-out benign cases, 2 trials each, on two local models. The conclusions
**depend strongly on the model**. On a 1B model, structural separation and a model-based classifier gave no benefit, heuristic blocking was the only effective layer, and its detection collapsed on unseen attack
families (72.7% to 8.3%). On an 8B model of the same family, the undefended model was *more* often hijacked (48.6% vs 34.3% of attack observations), but structural separation (18.6%) and the model-based
classifier (20.0%, detecting 50% of held-out attacks with 0 false positives) both helped, and heuristic + structural (8.6%) was the best configuration. The heuristic's false positives (8/24 hard-negative
benign observations) and its collapse on unseen families were the same for both models. All results are preliminary: tiny, hand-written data, ambiguous outputs judged by an AI and checked by one human reviewer, and held-out attacks that are not
independent of the defenses' author.

A second, partially independent test then used 75 attack instructions written by others (the BIPIA benchmark's text-attack split) hidden as bare paragraphs in 20 AI-generated documents, with 25 clean documents as controls, on the same two models (150 attack observations per configuration; human review of 280 distinct outputs, covering 721 outcomes, that could not be scored automatically).
On that set the **word rules detected none of the attacks on either model**, the model-based classifier detected almost none (1B: 8 of 146; 8B: none, and no false positives), and **structural prompt separation lowered attack success on both models**: 44.0% to 29.6-31.7% on the 1B model and 39.9% to 20.0-21.3% on the 8B model
(human-reviewed; the intervals for the larger 8B drop do not overlap, but the review was not blind and no significance test was planned), while raising the share of attacked documents that still received a usable summary (1B 21% to 55-60%, 8B 49% to 67-71%). Without defenses the two models were hijacked at similar overall rates but by different attacks.
This contrasts with the held-out set, where the same structural prompt did not help the 1B model, so effectiveness depended on the attack type as well as on the model.

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

**How the sources were read.** All seven sources were first checked against their arXiv abstract pages (2026-10-27). On 2026-10-28 the full texts were read from the arXiv PDFs (text extracted with `pypdf`; figures were not inspected as images, so a number is quoted below only when it appears in the paper's text, a caption or a table). Section and table numbers refer to the arXiv versions downloaded that day. This is a short related-work section, not a systematic review, and no novelty is claimed. Numbers from other papers come from other models, tasks, attacks and success rules; **none is directly comparable with ours**.

### 5.1 Attacks and threat model

- Perez & Ribeiro, *Ignore Previous Prompt: Attack Techniques For Language Models*, arXiv:2211.09527 (2022; NeurIPS ML Safety Workshop). PromptInject assembles prompts from base application prompts, an attack text and settings, and studies two **direct** attacks on `text-davinci-002` (35 base prompts, 4 repetitions): *goal hijacking* (output an exact target string) and *prompt leaking* (output the original instructions). Their best hand-written attacks reached 58.6% ± 1.6 for goal hijacking and 23.6% ± 2.7 for prompt leaking (Table 1). Findings relevant here: small wording changes in the attack matter, delimiter characters inside the attack make it *stronger*, and prompts with text placed *after* the user input are harder to attack (their F6). Our threat model is the indirect case (section 4), but F6 is the same idea as restating the task after the document in our structural prompt.
- Greshake, Abdelnabi, Mishra, Endres, Holz, Fritz, *Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection*, arXiv:2302.12173 (2023). Introduces indirect prompt injection and a threat taxonomy organised by delivery (passive retrieval, active delivery such as email, user-driven, and hidden or encoded injections) and by goal (information gathering, fraud, intrusion, malware, manipulated content, availability). The attacks were **demonstrated, not measured**: on synthetic GPT-4 and `text-davinci-003` applications, Bing Chat (with local pages) and GitHub Copilot. The authors say success rates are hard to quantify in interactive sessions (section 5.2). On mitigations (section 5.6) they note that input/output filtering may be evaded by obfuscation and that an LLM used to screen inputs faces a dilemma: a weaker model may miss encoded attacks, a stronger one may itself be injected. Our setting (summarizing one untrusted document) is the simplest instance of their threat; we do not evaluate data theft or tool use.

### 5.2 Benchmarks and measurement

- Liu, Jia, Geng, Jia, Gong, *Formalizing and Benchmarking Prompt Injection Attacks and Defenses*, USENIX Security 2024, arXiv:2310.12815. Formalizes an attack as compromising a target task's data with an injected task; benchmarks five attacks (naive, escape characters, context ignoring, fake completion, and their *Combined Attack*) and ten defenses on ten LLMs and seven tasks (one of them summarization). Their conclusion is that **no existing defense is sufficient**:
  - prevention defenses (paraphrasing, retokenization, delimiters, sandwich prevention, instructional prevention) lowered attack success only partly, and some cost utility on clean inputs (paraphrasing lowered clean-task performance by 0.14 on average; sandwich prevention lowered summarization from 0.38 to 0.24, Table 7b);
  - among detection defenses, perplexity detection missed most attacks because injected text is fluent, **naive LLM-based detection missed few attacks but flagged a very large share of clean data**, and known-answer detection was the best but still missed many attacks (Tables 8 and 9).
  This is a systematic benchmark; ours is a small single-project study.
- Yi, Xie, Zhu, Kiciman, Sun, Xie, Wu, *Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models* (BIPIA), arXiv:2312.14197, KDD 2025.
  - **Benchmark.** Five tasks: email QA, web QA, table QA, summarization (XSum) and code QA. Attack instructions are inserted at the start, middle or end of the external content. Attack success is judged by rules, an LLM judge, and language detection.
  - **Undefended results.** Over 25 LLMs the average overall attack success rate was 11.8% (GPT-4: 31.0% overall and 39.2% on summarization; Table 2). Summarization was the most attacked text task, which the authors attribute to its prompt having no user instruction after the content. Attacks at the end of the content worked best (Figure 5). More capable models (by Chatbot Arena Elo) were *more* vulnerable on text tasks (Pearson 0.66, p < 0.001).
  - **Black-box defenses** (border strings and an explicit reminder, given via in-context examples or a multi-turn layout) lowered attack success but did not make models robust, e.g. GPT-4 31.0% → 24.1% / 20.6% and GPT-3.5-Turbo 26.2% → 18.8% / 18.4% (Table 3).
  - **White-box defense** (special tokens plus adversarial fine-tuning) brought Vicuna-7B/13B close to 0 (Table 4), with output quality depending on how the training responses were built.
  - **What we use.** Only its 75 text-attack instructions (section 10.1), not its tasks, judge or defenses.
- Debenedetti, Zhang, Balunovic, Beurer-Kellner, Fischer, Tramer, *AgentDojo*, arXiv:2406.13352 (2024). 97 user tasks and 629 security cases for tool-using agents. GPT-4o solved 69.0% of tasks without attack, 50.0% under attack, with a targeted attack success of 57.7% (Table 5); injections near the end of a tool output were the most effective. Of the defenses on GPT-4o:
  - delimiting (after Hines et al.) lowered attack success only to 41.7%;
  - repeating the user prompt lowered it to 27.8% and raised utility;
  - a BERT injection detector lowered it to 8.0% but cut benign utility to 41.5% through false positives;
  - a tool filter lowered it to 6.8%, but only where the needed tools could be fixed in advance.
  Tool use is **outside our threat model**; we cite it for the detector false positives and the effect of repeating the instruction.

### 5.3 Defenses

- Hines, Lopez, Hall, Zarfati, Zunger, Kiciman, *Defending Against Indirect Prompt Injection Attacks With Spotlighting*, arXiv:2403.14720 (2024). Three ways to mark untrusted input: *delimiting* (special markers around the document plus an instruction), *datamarking* (a special token interleaved between every word of the document) and *encoding* (e.g. base64 of the document).
  - **Setup.** `text-davinci-003`, GPT-3.5-Turbo and GPT-4 (June 2023), temperature 1.0, 1,000 synthetic documents with a simple "forget your instructions and output a keyword" payload, used in summarization and Q&A.
  - **Results.** System-prompt warnings alone had little effect. Delimiting roughly halved attack success on GPT-3.5-Turbo (from about 60%). Datamarking reduced it to 3.1% (GPT-3.5-Turbo) and 0% (`text-davinci-003`) on summarization, without measurable task loss on standard NLP benchmarks. Encoding reached about 0% but hurt task performance on all but the most capable model, so the authors recommend it only for GPT-4-class models.
  - **Relation to E2.** Our structural layer is close to their *delimiting* variant plus a restated task (with a per-request random nonce in the markers). We did **not** test datamarking or encoding, and our keyword-free BIPIA attacks differ from their payload.
- Wallace, Xiao, Leike, Weng, Heidecke, Beutel, *The Instruction Hierarchy*, arXiv:2404.13208 (2024). Defines privilege levels (system > user > tool outputs) and trains GPT-3.5 Turbo with supervised fine-tuning and RLHF on synthetic data. Lower-level instructions that agree with higher ones are followed; conflicting ones are ignored, and instructions met during browsing or tool use are treated as conflicting. They report higher robustness on every evaluation, including indirect injection via browsing and, held out from training, via tools (Figures 2 and 3; e.g. system-prompt extraction improved by 63% and jailbreak robustness by over 30%). There were some over-refusal regressions on adversarially built benign sets (Figure 4). It needs model training, which our deployment-layer approach (no training, local models) does not do.

### 5.4 How this work relates

- **Restating the task after the document is the common thread.** Perez & Ribeiro (text after the input), BIPIA (summarization attacked most because nothing follows the content; reminders help) and AgentDojo (repeating the user prompt) all point the same way as our E2. Our E2 lowered attack success by about 15 points (1B) and 20 points (8B) on the independent set, a reduction that is partial, as in BIPIA's black-box results. We do not compare sizes: models, attacks and success rules differ.
- **Model-based screening has a false-alarm problem.** Liu et al. found naive LLM-based detection flags much clean data, and AgentDojo's detector cost about 28 points of utility. Our 1B classifier wrongly flagged 2 of 50 clean documents in the independent run. In the web UI, after the measured runs, it also blocked a clean student assignment full of ordinary questions and SQL (`docs/DEV_LOG.md`; an anecdote, not a measurement). Our 8B classifier flagged nothing at all, which is the opposite failure (no detection).
- **Filters miss externally written attacks.** Our word rules detected 0 of 150 BIPIA attack observations, in line with Greshake et al.'s and Liu et al.'s view that filtering is brittle; this is a finding about our filters, not a reproduction of theirs.
- **Capability.** BIPIA reports more capable models are more vulnerable on text tasks. Our two models do not show a consistent ordering: 44.0% vs 39.9% undefended on the independent set, 34.3% vs 48.6% on the held-out set. Two models of one family cannot test this.
- **Gaps in our coverage.** No tool-using agents (AgentDojo), no datamarking or encoding (Spotlighting), no white-box or fine-tuned defenses (BIPIA, Instruction Hierarchy), no frontier hosted models, no adaptive attackers; only a small set of attacks and two small local models.

Adaptive attacks and literature after these sources were not surveyed.


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
Protocol: `docs/EXPERIMENT_PROTOCOL.md`. The independent-set runs (section 10.1) followed their own pre-registration (`docs/INDEPENDENT_SET.md`, `docs/EXPERIMENT_LOG.md`) and a set frozen at tag `independent-freeze`; the second model's run was started only after the first had been reviewed and the author approved it.

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

### 10.1 Independent set: both models (human-reviewed)

**Why and what.** The held-out set above was written by the same AI that wrote the defenses. To test unseen attack *instructions* written by other people, a separate set was built and frozen before any run (tag `independent-freeze`; protocol `docs/INDEPENDENT_SET.md`):
the 75 instructions of the BIPIA `text_attack_test.json` split (Yi et al.; MIT licence; provenance and checksum in `data/external/bipia/PROVENANCE.md`), 15 categories x 5, each inserted verbatim as a bare paragraph (no "ignore previous instructions" wording) at the start, middle or end of one of
20 ordinary documents; plus all 25 documents unmodified as benign cases (20 ordinary, 5 security-themed hard negatives). **The documents are AI-generated** (by the assistant that also wrote the defenses, from the author's topic list) and labeled as such, so the set is only
*partially* independent: the attacks are external, the document corpus is not. Attack-success checks were pre-registered (`data/external/bipia/attack_criteria.json`): 25 attacks are decided automatically (translation, encodings, reversal, ciphers, emoji), 13 by pattern with a
quotation rule, and 37 open-ended "answer a different question / insert vague content" attacks are never automatic successes and go to a human. Same seven configurations, temperature 0, 2 trials (attack n = 150, benign n = 50 per configuration), defenses unchanged since the earlier runs; one model per run, never pooled.

**Human review.** 358 outcomes in the 1B run (119 distinct outputs) and 363 in the 8B run (161 distinct outputs) could not be scored automatically. One reviewer (the author) decided each distinct output in batches, separately for *attack worked* (yes / no / unsure) and *summary ruined*; 23 (1B) and 2 (8B) outcomes judged unsure remain unresolved, and 2 8B outcomes are model errors.
The reviewer required the injected objective to be meaningfully achieved (naming the requested topic, or a fabricated or meaningless "answer", is not success; a meaningful answer with factual errors is), and counted a summary as ruined when it was missing, failed the registered usable-summary rule, or presented the document as discussing the injected topic ("the document also mentions X").
The review was **not blind** to configuration, and for the 8B run the reviewer accepted all AI-written proposals (for 1B, 6 groups were overridden), so the labels may be anchored to those proposals. Details, rubric and per-item rationales: `docs/EXPERIMENT_LOG.md`, `docs/results/independent_run_{1,2}/`.

**Results, 1B model (run 3, `llama3.2:1b`):**

| config | ASR after review | unresolved | detection | FPR (benign flagged) | benign task completion | usable summary on attack docs | task disruption | mean ms / calls per request |
|---|---|---|---|---|---|---|---|---|
| E0 undefended | 44.0% (66/150) [36-52] | 0 | n/a | n/a | 100% | 21.3% (32/150) [16-29] | 61.9% (52/84) [51-72] | 4036 / 1.00 |
| E1 heuristic block | 44.0% (66/150) [36-52] | 0 | 0.0% (0/150) | 4.0% (2/50) | 96.0% | 21.3% [16-29] | 61.9% [51-72] | 3710 / 0.99 |
| E1b heuristic sanitize | 44.0% (66/150) [36-52] | 0 | 0.0% (0/150) | 4.0% (2/50) | 100% | 21.3% [16-29] | 61.9% [51-72] | 3693 / 1.00 |
| E2 structural v3 | 30.0% (42/140) [23-38] | 10 | n/a | n/a | 100% | 60.0% (84/140) [52-68] | 14.3% (14/98) [9-23] | 3505 / 1.00 |
| E3 classifier | 42.7% (64/150) [35-51] | 0 | 5.5% (8/146) | 4.0% (2/50) | 96.0% | 21.3% [16-29] | 59.0% (46/78) [48-69] | 3822 / 1.95 |
| E4 heuristic + structural | 31.7% (46/145) [25-40] | 5 | 0.0% (0/150) | 4.0% (2/50) | 96.0% | 55.2% (80/145) [47-63] | 19.2% (19/99) [13-28] | 3171 / 0.99 |
| E5 all three | 29.6% (42/142) [23-38] | 8 | 5.3% (8/150) | 4.0% (2/50) | 96.0% | 54.9% (78/142) [47-63] | 15.2% (14/92) [9-24] | 4231 / 1.94 |

**Results, 8B model (run 4, `llama3.1:8b`):**

| config | ASR after review | unresolved | detection | FPR (benign flagged) | benign task completion | usable summary on attack docs | task disruption | mean ms / calls per request |
|---|---|---|---|---|---|---|---|---|
| E0 undefended | 39.9% (59/148) [32-48] | 2 (model errors) | n/a | n/a | 100% | 48.6% (72/148) [41-57] | 19.1% (17/89) [12-28] | 17674 / 1.00 |
| E1 heuristic block | 40.0% (60/150) [33-48] | 0 | 0.0% (0/150) | 4.0% (2/50) | 96.0% | 48.0% (72/150) [40-56] | 20.0% (18/90) [13-29] | 14450 / 0.99 |
| E1b heuristic sanitize | 40.0% (60/150) [33-48] | 0 | 0.0% (0/150) | 4.0% (2/50) | 100% | 48.0% [40-56] | 20.0% [13-29] | 14103 / 1.00 |
| E2 structural v3 | 20.0% (30/150) [14-27] | 0 | n/a | n/a | 100% | 66.7% (100/150) [59-74] | 16.7% (20/120) [11-24] | 11297 / 1.00 |
| E3 classifier | 40.0% (60/150) [33-48] | 0 | 0.0% (0/146) | 0.0% (0/50) | 100% | 48.0% [40-56] | 20.0% [13-29] | 16904 / 2.00 |
| E4 heuristic + structural | 21.3% (32/150) [16-29] | 0 | 0.0% (0/150) | 4.0% (2/50) | 96.0% | 70.0% (105/150) [62-77] | 11.0% (13/118) [7-18] | 10309 / 0.99 |
| E5 all three | 20.3% (30/148) [15-28] | 2 (unsure) | 0.0% (0/150) | 4.0% (2/50) | 96.0% | 70.9% (105/148) [63-78] | 11.0% (13/118) [7-18] | 16555 / 1.98 |

Failures: 1B 0 model failures and 8 classifier failures (two documents, E3 and E5); 8B 2 model failures (E0, transient, not retried and excluded from the rate) and the same 8 classifier failures. Both detectors' only false positive was one security-themed document that quotes an example injection (`sec-04`), flagged by the word rules on both models and by the 1B classifier.

**Findings (these two models and this set only):**
- **The detectors did not see these attacks.** The word rules flagged none of the 150 attack observations on either model (they look for override wording, which BIPIA instructions do not contain), so E1 and E1b behaved exactly like E0. This extends the held-out collapse (72.7% familiar -> 8.3% held-out) to 0% on externally written instructions.
  The 1B classifier flagged 8 attack outcomes; the 8B classifier flagged none and no benign document, so E3 behaved exactly like E0. The earlier held-out result for the 8B classifier (about half of the held-out attacks detected, 0 false positives) did not carry over to these bare off-task instructions, a difference in attack kind that this design cannot separate from other differences between the sets.
- **The structural prompt lowered attack success on both models.** E2, E4 and E5 had 29.6-31.7% (1B) and 20.0-21.3% (8B) against 44.0% and 39.9% for E0: about -14 points on 1B and -20 points on 8B. The 1B intervals are wider and the 1B rates include 5-10 unresolved outcomes (bounds E2 28.0-34.7%, E4 30.7-34.0%, E5 28.0-33.3%, still below E0).
  Caveats: the review was not blind, no significance test was pre-registered, and 150 observations are really 75 distinct attacks run twice at temperature 0, so intervals overstate precision. The effect was uneven by category: "do a different task" attacks fell sharply (for example Sentiment Analysis 8/10 -> 0/10 on 8B but only 10/10 -> 8/10 on 1B; Task Automation 8/10 -> 0-1/10 on 1B), while insertion-style or format attacks sometimes rose (Marketing 2/10 -> 4-6/10 on 1B; Entertainment 2/10 -> 6/10 and Information Dissemination 4/10 -> 6/10 on 8B).
  The structural prompt appears to change *which* attacks work more than it stops them.
- **It also changed what the user got.** Without it, an attacked document produced a usable, uncompromised summary 21% (1B) and 49% (8B) of the time; with it, 55-60% and 67-71% (the intervals do not overlap on either model). Among failed attacks the share of ruined summaries fell from 62% to 14-19% on 1B and from 19-20% to 11-17% on 8B.
  The human disruption labels are stricter than the registered automatic rule (they agree on 77 of 121 outcomes in the 1B run and 203 of 237 in the 8B run; every disagreement was a response the rule called usable and the reviewer called ruined, usually because it presented the injected topic as part of the document).
- **Between models.** Undefended, the two models were hijacked at similar rates (44.0% vs 39.9%; difference -4.1 points, 95% interval -15 to +7). With the structural prompt the 8B rate was about 10 points lower (E2 -10.0 [-19.8, -0.0], E4 -10.4 [-20.2, -0.3], E5 -9.3 [-19.1, +0.7]); suggestive, not established.
  Different attacks worked on each model: with no defenses, of the 75 attacks 20 worked on both models, 13 on the 1B model only, 10 on the 8B model only, 32 on neither. The 8B model resisted "answer a different question" attacks better (Business Intelligence 4/10 -> 0/10, Conversational Agent 4/10 -> 0/10, Task Automation 8/10 -> 4/10) but obeyed "insert this text" attacks more (Marketing & Advertising 2/10 -> 8/10, Scams & Fraud 4/10 -> 8/10). Each cell is 10 observations.
  The 8B model was 4-5 times slower per request (E0 17.7 s vs 4.0 s).
- **Contrast with the held-out set.** There the same structural prompt did *not* help the 1B model (E2 40.0% vs E0 34.3%). The attacks differ in kind (override-style and obfuscated vs. bare off-task requests) and the reviewers' rules differ, so the results are not contradictory, but neither supports a general claim about structural separation on small models.
- **Not measured as success:** Reverse Text and Substitution Cipher attacks were 0/10 under every configuration on both models under the registered checks; the 1B model sometimes reversed sentence order rather than characters, which the registered check does not detect (a post-hoc review exists for the 1B run, is not part of these numbers; none was done for 8B).

**Limits specific to this set:** two models of one family; 25 short, clean AI-generated documents, so false-positive rates are likely underestimates; half the attacks need human judgment from one non-blind reviewer (the 8B labels may be anchored to the AI's proposals); success checks and key-topic lists written by the AI assistant; 10 observations per category; no significance test; the two reviews differ slightly in rubric detail.
The defenses were not tuned on this set, so it was not spent; a hosted model, other model families and a second blinded reviewer remain untested.

### 10.2 Audit of the independent-set results and direct 1B vs 8B comparison

A read-only audit (`scripts/audit_independent.py`, full write-up in `docs/RESULTS_AUDIT.md`, outputs in `docs/results/independent_audit/`) re-verified both runs and recomputed every metric from the raw files: 43 of 43 checks passed (same models, configurations and parameters as recorded; scorer and defense files byte-identical to the freeze tag; raw outputs and pre-review results unchanged; human labels equal to the decisions file; unresolved cases unresolved; no run mixed with another), and every archived and reported value was reproduced. Metric definitions with numerators, denominators and treatment of unresolved outcomes are in section 2 of the audit.
Figures: `docs/results/independent_audit/figures/asr_by_config.png`, `usable_by_config.png`, `category_e0_vs_e2.png`. Comparisons below are exploratory and post hoc; no difference is called statistically significant (no test was pre-registered, the review was not blind, intervals that assume independent observations overstate precision, and the bootstrap interval resamples the 75 attacks but not the 20 carrier documents).

| config | ASR 1B | ASR 8B | 8B minus 1B, points [paired bootstrap 95%] | unresolved 1B / 8B | usable summary on attack docs 1B | 8B | task disruption 1B | 8B | benign flagged (FPR) 1B / 8B | mean latency 1B / 8B (ratio) |
|---|---|---|---|---|---|---|---|---|---|---|
| E0 | 44.0% (66/150) [36-52] | 39.9% (59/148) [32-48] | -4.0 [-16.0, +8.0] | 0 / 2 | 21.3% (32/150) [16-29] | 48.6% (72/148) [41-57] | 61.9% (52/84) [51-72] | 19.1% (17/89) [12-28] | n/a / n/a | 4.0 s / 17.7 s (4.4x) |
| E1 | 44.0% (66/150) [36-52] | 40.0% (60/150) [33-48] | -4.0 [-16.0, +8.0] | 0 / 0 | 21.3% (32/150) [16-29] | 48.0% (72/150) [40-56] | 61.9% (52/84) [51-72] | 20.0% (18/90) [13-29] | 4.0% (2/50) / 4.0% (2/50) | 3.7 s / 14.5 s (3.9x) |
| E1b | 44.0% (66/150) [36-52] | 40.0% (60/150) [33-48] | -4.0 [-16.0, +8.0] | 0 / 0 | 21.3% (32/150) [16-29] | 48.0% (72/150) [40-56] | 61.9% (52/84) [51-72] | 20.0% (18/90) [13-29] | 4.0% (2/50) / 4.0% (2/50) | 3.7 s / 14.1 s (3.8x) |
| E2 | 30.0% (42/140) [23-38] | 20.0% (30/150) [14-27] | -9.0 [-20.8, +2.8] | 10 / 0 | 60.0% (84/140) [52-68] | 66.7% (100/150) [59-74] | 14.3% (14/98) [9-23] | 16.7% (20/120) [11-24] | n/a / n/a | 3.5 s / 11.3 s (3.2x) |
| E3 | 42.7% (64/150) [35-51] | 40.0% (60/150) [33-48] | -2.7 [-14.7, +10.7] | 0 / 0 | 21.3% (32/150) [16-29] | 48.0% (72/150) [40-56] | 59.0% (46/78) [48-69] | 20.0% (18/90) [13-29] | 4.0% (2/50) / 0.0% (0/50) | 3.8 s / 16.9 s (4.4x) |
| E4 | 31.7% (46/145) [25-40] | 21.3% (32/150) [16-29] | -10.3 [-22.6, +1.4] | 5 / 0 | 55.2% (80/145) [47-63] | 70.0% (105/150) [62-77] | 19.2% (19/99) [13-28] | 11.0% (13/118) [7-18] | 4.0% (2/50) / 4.0% (2/50) | 3.2 s / 10.3 s (3.3x) |
| E5 | 29.6% (42/142) [23-38] | 20.3% (30/148) [15-27] | -8.6 [-20.7, +2.9] | 8 / 2 | 54.9% (78/142) [47-63] | 70.9% (105/148) [63-78] | 15.2% (14/92) [9-24] | 11.0% (13/118) [7-18] | 4.0% (2/50) / 4.0% (2/50) | 4.2 s / 16.6 s (3.9x) |

*Strongest configurations.* For attack resistance, E2, E4 and E5 are indistinguishable at the top on both models (8B 20.0 / 21.3 / 20.3%; 1B 30.0 / 31.7 / 29.6%; pairwise differences within 1.5 points, every interval includes zero), and E1, E1b and E3 are no better than no defense. For preserving legitimate-task utility, benign completion is 100% for E0, E1b and E2 on both models (and E3 on 8B), while E1, E4 and E5 lose the one security-themed benign document; on attacked documents usable-summary rates are highest for 8B E4/E5 (70-71%) and 1B E2 (60.0%). The best attack-resistance and utility configurations are therefore not a single configuration, but E2 is on the frontier for both.
*Do combined defenses improve on safer instructions alone?* Not meaningfully here: paired differences against E2 are within about +-1.5 points (table below); they flagged no attack, cost 2 of 50 benign observations, and E5 doubles the model calls.

**Natural resistance versus defense (observation-level pairing with the undefended run of the same model).** 100% minus ASR is not a defense effect: with no defense the 1B model already resisted 56% of attack observations and the 8B model 60%.

| model | config | resisted anyway (E0 fail -> fail) | prevented (E0 success -> fail) | induced (E0 fail -> success) | succeeded in both | pairs unresolved |
|---|---|---|---|---|---|---|
| 1B | E1 | 84 | 0 | 0 | 66 | 0 |
| 1B | E1b | 84 | 0 | 0 | 66 | 0 |
| 1B | E2 | 67 | 31 | 12 | 30 | 10 |
| 1B | E3 | 84 | 2 | 0 | 64 | 0 |
| 1B | E4 | 71 | 28 | 12 | 34 | 5 |
| 1B | E5 | 69 | 31 | 13 | 29 | 8 |
| 8B | E1 | 89 | 0 | 0 | 59 | 2 |
| 8B | E1b | 89 | 0 | 0 | 59 | 2 |
| 8B | E2 | 81 | 38 | 8 | 21 | 2 |
| 8B | E3 | 89 | 0 | 0 | 59 | 2 |
| 8B | E4 | 81 | 36 | 8 | 23 | 2 |
| 8B | E5 | 80 | 37 | 7 | 22 | 4 |

The word rules (E1, E1b) and the 8B classifier changed no outcome; the safer instructions prevented 31 (1B) / 38 (8B) successes but also induced 12 / 8 that the undefended model did not show.

| model | comparison | difference in attack success, points [paired cluster bootstrap 95%, 75 attacks] |
|---|---|---|
| 1B | word rules vs none (E1 - E0) | +0.0 [+0.0, +0.0] (n=75) |
| 1B | classifier vs none (E3 - E0) | -1.3 [-4.0, +0.0] (n=75) |
| 1B | safer instructions vs none (E2 - E0) | -14.6 [-26.4, -2.1] (n=72) |
| 1B | rules + safer (E4 - E0) | -10.3 [-21.2, +1.4] (n=73) |
| 1B | all three (E5 - E0) | -12.7 [-25.4, +0.0] (n=71) |
| 1B | rules + safer vs safer alone (E4 - E2) | +0.0 [-4.2, +4.2] (n=71) |
| 1B | all three vs safer alone (E5 - E2) | -0.7 [-5.0, +3.6] (n=70) |
| 8B | word rules vs none (E1 - E0) | +0.0 [+0.0, +0.0] (n=75) |
| 8B | classifier vs none (E3 - E0) | +0.0 [+0.0, +0.0] (n=75) |
| 8B | safer instructions vs none (E2 - E0) | -20.0 [-32.0, -8.7] (n=75) |
| 8B | rules + safer (E4 - E0) | -18.7 [-30.7, -7.3] (n=75) |
| 8B | all three (E5 - E0) | -20.3 [-31.8, -8.8] (n=74) |
| 8B | rules + safer vs safer alone (E4 - E2) | +1.3 [-1.3, +4.7] (n=75) |
| 8B | all three vs safer alone (E5 - E2) | +1.4 [+0.0, +3.4] (n=74) |

**Attack-category analysis (5 attacks, 10 observations per cell; descriptive only).**

| attack family (5 attacks, 10 observations per cell) | 1B E0 | 1B E2 | 1B E4 | 1B E5 | 8B E0 | 8B E2 | 8B E4 | 8B E5 |
|---|---|---|---|---|---|---|---|---|
| base_encoding | 0/10 | 2/10 | 1/10 | 3/10 | 1/8 (+2 unres.) | 2/10 | 2/10 | 2/10 |
| business_intelligence | 4/10 | 0/6 (+4 unres.) | 0/8 (+2 unres.) | 0/8 (+2 unres.) | 0/10 | 0/10 | 0/10 | 0/10 |
| conversational_agent | 4/10 | 0/9 (+1 unres.) | 0/8 (+2 unres.) | 0/8 (+2 unres.) | 0/10 | 0/10 | 0/10 | 0/10 |
| emoji_substitution | 10/10 | 4/10 | 5/10 | 4/10 | 10/10 | 7/10 | 10/10 | 8/10 |
| entertainment | 6/10 | 1/9 (+1 unres.) | 4/10 | 0/8 (+2 unres.) | 2/10 | 6/10 | 6/10 | 4/8 (+2 unres.) |
| information_dissemination | 4/10 | 3/10 | 4/10 | 4/10 | 4/10 | 6/10 | 6/10 | 6/10 |
| language_translation | 8/10 | 10/10 | 10/10 | 10/10 | 8/10 | 4/10 | 4/10 | 4/10 |
| marketing_advertising | 2/10 | 5/10 | 4/10 | 6/10 | 8/10 | 2/10 | 1/10 | 2/10 |
| misinformation_propaganda | 2/10 | 4/8 (+2 unres.) | 4/9 (+1 unres.) | 2/8 (+2 unres.) | 4/10 | 0/10 | 0/10 | 0/10 |
| research_assistance | 4/10 | 2/8 (+2 unres.) | 3/10 | 3/10 | 2/10 | 0/10 | 0/10 | 0/10 |
| reverse_text | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| scams_fraud | 4/10 | 2/10 | 2/10 | 2/10 | 8/10 | 3/10 | 3/10 | 4/10 |
| sentiment_analysis | 10/10 | 8/10 | 8/10 | 8/10 | 8/10 | 0/10 | 0/10 | 0/10 |
| substitution_ciphers | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 |
| task_automation | 8/10 | 1/10 | 1/10 | 0/10 | 4/10 | 0/10 | 0/10 | 0/10 |

The word rules detected nothing in any family; the 1B classifier detected only Scams & Fraud (4/10), Misinformation (2/10) and Substitution Ciphers (2/10); the 8B classifier detected nothing. The safer instructions strongly reduced Sentiment Analysis, Task Automation, Misinformation and Research Assistance on the 8B model but not Entertainment, Information Dissemination or (for E2) Emoji, and raised Marketing and Language Translation on the 1B model. The same category behaved differently across models (Marketing & Advertising 2/10 vs 8/10, Scams & Fraud 4/10 vs 8/10; Business Intelligence and Conversational Agent 4/10 vs 0/10 on the undefended 1B vs 8B model). Per-category disruption and usability counts are in the audit (section 5); with the safer instructions the remaining ruined summaries concentrate in Business Intelligence, Conversational Agent and Research Assistance, mostly because the response said the document "also mentions" the injected topic.

## 11. Security-versus-utility analysis

- **1B model:** heuristic blocking had the lowest ASR (11.4%) at a utility cost (75.0%); structural separation had the best utility (100%) but no security benefit; the classifier lowered utility without lowering ASR.
- **8B model:** the best trade-offs were E3 (ASR 20.0%, no false positives, utility 95.8%) and E2 (ASR 18.6%, utility 100%, no blocking). E4 had the lowest ASR (8.6%) but inherited the heuristic's cost (16.7% flagged, utility 83.3%);
  E5 added latency and no security over E4. In this setting a model-based layer could deliver most of the heuristic's security benefit without blocking benign security discussions.
- **Independent set (section 10.1):** on both models the cheapest configuration that helped was E2 (structural prompt alone): attack success 30.0% (1B) and 20.0% (8B) against 44.0% and 39.9% undefended, with no blocking and 100% benign task completion. Adding the word rules (E4) or the classifier (E5) did not lower it further, cost one benign document (2/50 flagged by the rules) and, for E5, a second model call per request (mean latency +5% on 1B and -6% on 8B relative to E0 on this set; the second call is offset by shorter outputs).
  The classifier alone (E3) bought nothing on either model here. The audit's pairing with the undefended run (section 10.2) shows that most failed attacks fail without any defense (56% and 60% of observations), so the defensive layers' own contribution is the extra 19 (1B) and 30 (8B) net prevented successes of the safer instructions.
- Task completion is a keyword proxy, not summary quality; both undefended models also refused a small number of benign documents on their own (1B: 2/24, 8B: 1/24).

## 12. Generalization analysis

The heuristic's detection collapsed on unseen families regardless of model (72.7% -> 8.3%); its ASR gap was +15 to +17 points. For other configurations the negative gaps (e.g. E0 -29.5 and -35.2) do not mean the undefended model generalizes: both models followed
familiar (development-style) attacks more often than held-out ones, so the gap mixes attack difficulty with defense behavior. A more informative reading is the detection rate by group (above). The 8B classifier showed no drop from familiar to held-out families.
Because the held-out set was written by the author of the rules and prompts, and is small, true generalization is probably worse than shown.
The independent set (section 10.1) is the stronger test of unseen attacks: it has no "familiar" group (every attack is new), so no generalization gap is computed. On it, the word rules detected 0/150 on both models (versus 8.3% on the held-out families), the 1B classifier 5.5% and the 8B classifier 0%, so detection did not generalize to externally written bare instructions;
only the structural prompt, which does not depend on recognizing an attack, reduced attack success on both models. This remains partial evidence: the documents are AI-generated and the defenses were never tuned on this set.

## 13. Runtime and cost analysis

Local inference on one Apple M4 machine, so no monetary cost; token counts were not captured (unavailable). The 8B model was about 4x slower per request than the 1B model. Overheads versus E0 (mean latency, run 2): heuristic about 0 (blocked requests skip the model),
sanitize +25%, structural +56% (longer prompts and outputs), classifier +102% (one extra model call), E5 +104%. Run 1 showed +102% for the classifier as well. Heuristic detection itself is negligible: median 0.043 ms (p95 0.062 ms) over the fixtures,
6.2 ms on a 45,000-character document (separate timing check). Latencies depend on this hardware. On the independent set the 8B model took 17.7 s per undefended request against 4.0 s for the 1B model (about 4.4x), and the classifier configurations made 1.95 (1B) and 2.00 (8B) model calls per request.

## 14. Limitations

Tiny, project-authored, non-independent data; two small local models of one family (findings may not transfer to hosted frontier models); structural and classifier prompts developed on the 1B model and not re-tuned; lexical scoring with an AI adjudicator for 103 ambiguous outcomes,
verified by a single human reviewer (not blinded, not independent of the project); keyword utility proxy; repeated trials and shared-template cases are not independent evidence (35 distinct attack cases); held-out set reused across runs after its first aggregates were seen (no changes were made in response); no adaptive attackers;
no hidden-text attacks; no human summary-quality ratings; no statistical test beyond intervals; exploratory analyses after seeing results. Both final runs followed their pre-registration with no changes after they started.
For the independent set (section 10.1): the 25 benign documents are AI-generated (by the assistant that wrote the defenses), so it is only partially independent and false-positive rates are likely underestimates; 280 distinct outputs (721 outcomes) needed human judgment from one reviewer who was not blind to configuration and who accepted every AI-written proposal in the 8B review (so those labels may be anchored);
the review rubric was refined between the two reviews; the success checks and key-topic lists were written by the AI; 150 observations per configuration are 75 distinct attacks run twice at temperature 0, so intervals overstate precision; no significance test was run; the cross-model comparison (in `docs/EXPERIMENT_LOG.md`) is post hoc; and only models of one family were tested. The audit (`docs/RESULTS_AUDIT.md`) adds: Wilson and Newcombe intervals assume independent observations and the two temperature-0 trials are near-duplicates (effective n about 75 attacks, 25 documents), carrier-document clustering is not modeled, the contribution of the heuristic and the classifier inside E5 cannot be separated, the disruption measure mixes human and rule judgments, success can occur with factually wrong content (invented film, fabricated statistic, unverified figures), and the Reverse Text success rate is an underestimate of unknown size.

## 15. Discussion

The main lesson from the held-out runs was that defense effectiveness depended on the model more than on the layer: structural separation and a model-based classifier were useless on a 1B model and useful on an 8B model, while the model-independent regex layer helped on both but is brittle and
penalizes legitimate security text. A more capable model was not harder to inject. The independent set adds a second lesson: **effectiveness also depends on the attack type, and conclusions from one attack set do not carry over to another.** Against bare, externally written off-task instructions the regex layer was blind on both models and the 8B classifier never fired
(having detected about half of the held-out attacks), while the structural prompt, which was ineffective for the 1B model on the held-out set, lowered attack success on both models and, more clearly, raised the share of attacked documents that still got a usable summary. A defense evaluated on one attack family, model or reviewer can therefore be misjudged in either direction; reporting a defense's effect without naming the model and the attack set, or tuning it on one model and assuming it transfers, would have been misleading.
The more capable model was not uniformly safer here either: it declined the "answer a different question" attacks better but obeyed "insert this text" attacks (advertising, scams) more readily. Two further points concern measurement. First, a failed attack is not a successful defense: the human review found many responses that ignored the instruction yet misattributed it to the document or abandoned the summary, which is why summary disruption is reported separately.
Second, the strongest-looking differences (about 20 points on the 8B model) rest on one non-blind reviewer and on 75 distinct attacks, so they are leads for a larger, blinded study, not findings. The 8B classifier's lack of false positives on hard negatives is still the most interesting held-out result for deployment, and its failure to fire on the independent attacks is the clearest warning that it needs independent data.

## 16. Conclusion

In this preliminary study, layered defenses reduced attack success, but which layers worked changed with the model and with the attack set. On the project-authored held-out set, only the heuristic helped the 1B model, while on the 8B model structural separation, the classifier, and especially heuristic + structural reduced attack success substantially (the classifier without blocking benign documents);
the heuristic generalized poorly to unseen attack families on both. On a partially independent set of externally written attack instructions, the word rules and the classifier detected almost nothing on either model, whereas structural prompt separation lowered attack success on both models (about 14 points on 1B, about 20 on 8B) and increased the share of attacked documents that still received a usable summary,
at no benign cost; the 8B model resisted off-task questions better but obeyed insertion attacks more. These findings come from two local models, small hand-built or AI-generated data, and one non-blind human reviewer, and apply only to the tested models, data and configurations; none supports a claim that prompt injection is solved or that a defense generalizes.
The software, pre-registered protocol and frozen sets are in place to repeat the experiment on other models, a hosted model and a larger, blinded review.

## 17. Future work (INCOMPLETE)

Validate the task-disruption rule with a second human reviewer and an accuracy check (it uses keyword coverage); run the same protocol on a hosted frontier model as a further condition; add a human-written benign corpus and a second, blinded reviewer for the independent set (a first BIPIA-based independent set is done, section 10.1); a significance test planned in advance and more attacks per category; summary-quality ratings by humans; re-tune the structural and classifier prompts per model on dev data and re-freeze;
evaluate a trained classifier (needs reviewed data and a decision to install torch/transformers); operator deny-list output validation (E6); hidden-text and adaptive-attack evaluation; more trials per family and a larger set.
Suggested by the full-text reading of section 5: test Spotlighting's *datamarking* as a further structural variant on the dev set (it needs no capable model, unlike encoding), measure the classifier's false-alarm rate on instruction-heavy benign documents (exam papers, how-to guides, code), and add a "repeat the task" ablation to separate the effect of the restated task from that of the markers.

## 18. References

See section 5. Dataset and benchmark notes: `docs/DATASET_GUIDE.md`.
