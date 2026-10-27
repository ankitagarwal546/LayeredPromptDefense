# Security controls and limitations

This is a research prototype for local use. It is not hardened for public exposure, and none of its defenses is a
guarantee against prompt injection.

## Controls implemented

| area | control | where |
|---|---|---|
| input | request/field size limits (document 50,000 chars, instruction 1,000), non-blank validation | `schemas.py` |
| upload | extension allowlist (.txt .md .pdf .docx), 5 MB cap, magic-byte check, UTF-8 requirement, PDF page cap, DOCX zip-bomb guard, filename never used as a path (only its extension is echoed in errors) | `documents.py` |
| parsing | files are parsed, never executed; no macros/scripts/active content run; parser errors return generic messages | `documents.py` |
| secrets | env-only config, `SecretStr`, `.env` git-ignored, keys never in responses/logs/`/config`; provider errors carry status codes only | `config.py`, `llm/provider.py` |
| privacy | document text and summaries are not logged or stored by the API; logs hold ids, config, timings; UI states whether text goes to a local or remote model | `pipeline.py`, `frontend/` |
| real vs mock | `real` never falls back to the mock; mock output is labeled everywhere | `api.py`, `llm/mock.py` |
| files/paths | `/results` accepts only 12-hex run ids; `/evaluate` accepts only named case sets; no client-supplied paths | `evaluation/store.py`, `evaluation/registry.py` |
| cost | real-model evaluations need explicit confirmation with a call estimate; API job cap 3,000 calls; one job at a time; CLI dry-run and `--yes` | `api.py`, `scripts/run_experiments.py` |
| errors | no stack traces or internals in responses; model failures are 502, config problems 503 | `api.py` |
| XSS | the frontend renders all document/model text with `textContent` only (tested) | `frontend/app.js` |
| untrusted config | the document cannot change defenses: configuration comes only from the request/server, never from document text | `pipeline.py` |

## Defense limitations (by layer)

- **L1 heuristic:** regexes catch known phrasings only. Paraphrase, other languages, encodings (e.g. base64), homoglyphs, and instructions split
  across a document evade it, and benign text that quotes or discusses attacks is flagged. Offsets are on the raw text only.
- **L2 classifier:** the classifying model reads the same untrusted text and can itself be injected or simply be wrong; self-reported confidence is
  uncalibrated; it costs another model call. With the 1B local model it detected almost nothing on the independent set and wrongly flagged 2 of 50 clean
  documents; with the 8B model it flagged nothing (see `docs/EXPERIMENT_LOG.md`). In the web UI it also blocked a clean assignment PDF full of ordinary
  questions and SQL (`docs/DEV_LOG.md`, 2026-10-28; one anecdote): documents with many instructions addressed to a reader are at risk of false alarms.
  The UI explains such blocks and offers a re-run with the layer on warn only. The Transformers adapter is untested against a real model.
- **L3 structural:** delimiters and instructions are advisory. The model sees one token stream. Wording changes behavior in model-specific ways: on the
  1B model the original wording caused refusals of benign documents and the revised wording gave no measurable protection (`docs/DEV_LOG.md`).
  The web UI's general-task role line (`general_task=true`) was never evaluated: its protection on non-summary tasks is unknown.
- **L4 output validation:** needs predefined criteria (canaries, deny-lists) and is lexical. In experiments it is the scorer, not a defense, to avoid oracle leakage.
- **Policies:** blocking trades availability for security; sanitizing can leave an attack partly intact; the fail-open default means a failed detector lets input through
  (visible as a `warn` decision and counted in `detector_failures`).

## Not covered / out of scope

Hidden text (white-on-white, tiny fonts, hidden DOCX runs, annotations), metadata and comment injection, image/OCR content, multi-turn and delayed attacks, tool-using
agents, adaptive attackers who know the rules or delimiter scheme, denial of service beyond the size limits, authentication/authorization, TLS, rate limiting, multi-user
isolation. Text extraction can include invisible text and omit visible-only-as-image text; this project does not detect hidden-text attacks. Do not expose the API publicly
without adding authentication and rate limits; the default server binds to localhost only when started with the documented commands.

## Experimental validity limits

Small, project-authored datasets; one weak local model; lexical scoring; held-out data not independent of the rules' author; LLM adjudication of ambiguous outputs
(unless a human re-labels them); utility measured by a keyword proxy, not summary quality. See `docs/EXPERIMENT_PROTOCOL.md` and `docs/FINAL_REPORT.md`.
