# CLAUDE.md

Follow `AGENTS.md` (permanent project rules) and `HANDOFF.md` (current state and next steps).

Quick start for a new session:
1. Read `AGENTS.md`, then `HANDOFF.md`, `README.md`, `docs/EXPERIMENT_PROTOCOL.md`.
2. Run `git status` and `git log --oneline -10`; inspect actual files before trusting any status.
3. Run `PYTHONPATH=src .venv/bin/python -m pytest` to verify the baseline.
4. Resume the highest-priority incomplete task in `HANDOFF.md`; update it at every checkpoint.

Claude Code specifics: use dedicated file tools for edits; keep `.env` out of every command output;
tell the user the number of external model calls before running anything that makes them.
