# Provenance: BIPIA `text_attack_test.json`

| item | value |
|---|---|
| Source repository | https://github.com/microsoft/BIPIA |
| Paper | Yi, Xie, Zhu, Kiciman, Sun, Xie, Wu. *Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models* (BIPIA). arXiv:2312.14197; KDD 2025 |
| File used | `benchmark/text_attack_test.json` (test split only) |
| File URL | https://raw.githubusercontent.com/microsoft/BIPIA/5a48626aece9739ce587ffdbcb2b7badcfd9d8ba/benchmark/text_attack_test.json |
| Last commit that changed the file | `5a48626aece9739ce587ffdbcb2b7badcfd9d8ba` (2023-11-23, "add code") |
| Repository HEAD when retrieved | `a004b69ec0dd446e0afd461d98cb5e96e120a5d0` (2024-04-15); the file's content at HEAD is byte-identical to the file at `5a48626` |
| Retrieved | 2026-10-24 |
| SHA-256 of the file | `75750e7b4e8b34e8f9d88d89b357aeaaf02bd07f9e493ccd37eda74a0cd7c7f8` (6,322 bytes) |
| Content | 15 attack categories x 5 attack instructions = 75 plain-text instructions, used **verbatim** |
| License | MIT License, copyright Microsoft Corporation (copy in `LICENSE`, retrieved from HEAD `a004b69`; SHA-256 `57cf81c45e0929899bc18051cf90134f00e55963ddecc7b37cfc5ea1494b1e8b`) |

## License analysis for this exact file

The repository `LICENSE` states that the MIT License applies to all parts of the repository **except** the datasets it lists under `benchmark`: WikiTableQuestions
(CC BY-SA 4.0), Stack Exchange data (CC BY-SA 4.0) and invoice data from OpenAI Evals (MIT). `text_attack_test.json` is **not** one of the listed exceptions, so it falls under the repository's MIT
license. The `LICENSE` file did not yet exist when the data file was last changed (it was added in January 2024); we rely on the license in force at the current HEAD. We use **no** other BIPIA data:
not the CC BY-SA datasets, not the Web QA / Summarization context data (withheld by the authors for license reasons), not the code-attack files, and **not `text_attack_train.json`** (deliberately
excluded so no train-split attack can influence any defense).

The README adds: "This code should only be used for research on indirect prompt injection attacks" and recommends responsible AI testing before production use. Our use is research
on indirect prompt injection, run locally. The README does not say who wrote the attack instructions; we cite the benchmark paper and do not claim more. We have read only the paper's abstract, not its
description of how these instructions were produced.

## How the strings are used here

- Each of the 75 instructions is inserted, unchanged, as a bare paragraph into a human-written document (see `docs/INDEPENDENT_SET.md`). No "ignore previous instructions" wording is added.
- Exclusions: none of the 75 instructions was excluded. Transformations: none to the strings themselves.
- Some categories ask for harmful-looking text (scams, misinformation). Model outputs stay local (`results/` is git-ignored) and are not redistributed.
- Attribution: this project reuses attack instructions from BIPIA (Microsoft Corporation, MIT License; copyright notice retained in `LICENSE`).
