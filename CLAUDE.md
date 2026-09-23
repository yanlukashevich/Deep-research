# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TARO is a deep-research agent. It takes a question, searches the web through Keenable MCP, extracts facts with exact quotes, and writes an answer where every sentence is cited and scored for confidence. The answer must come from the pages it retrieved, not from what the model already knows.

- **The full plan is the source of truth:** `C:\Users\yanlu\.claude\plans\ok-zrob-plan-zrobienia-federated-dewdrop.md`. It covers the phases, the layout, the v1/v2/v3 design, the confidence formula and the verification criteria. Read it before starting.
- `task.md` is the original assignment. It contains **API keys**: never commit it and never copy its keys anywhere except `.env`.

## Working in phases (start here)

1. **Read `HANDOFF.md` first.** It says which phases are done and what comes next. If the file is missing, nothing has been built yet: start with Phase 0.
2. Do **only one phase** per session, following the plan.
3. When the phase is done:
   - Update `HANDOFF.md`. Keep it short and replace outdated content instead of appending a log. It should cover:
     - the current phase status (done / next)
     - what was built and the key decisions (for example, the chosen models and why)
     - any deviations from the plan
     - known issues or TODOs
     - exact commands to check that things work
   - Add an entry at the bottom of `WORKLOG.md`: a simple diary in plain language, with no jargon. Never rewrite old entries. Each entry covers:
     - what you did, step by step
     - what came out
     - problems and how you solved them, including your own mistakes
     - the commit message

     `HANDOFF.md` holds the current state, while `WORKLOG.md` is the history.
   - Commit using the message given in the plan (for example, `Phase 1: foundation, v1 bare LLM, v2 simple RAG`), with `HANDOFF.md` and `WORKLOG.md` included.
   - Give the user a short, simple explanation of what was built.
4. If you change a command or a key architectural fact, update this file too.

## Conventions

- Python 3.12 + asyncio, with no agent frameworks. LLM calls use the `openai` client against LiteLLM (`https://litellm.ispras.ru/`), and search uses the official `mcp` SDK.
- Models: the main one is `openai/gpt-oss-120b` (context 60k tokens) and the fast one is `google/gemma4:31b`. Both are set in `.env`. Why they were chosen is in `HANDOFF.md`.
- The `mcp` SDK is **2.x**: use `streamable_http_client(url, http_client=httpx2.AsyncClient(headers=...))` and snake_case result fields. `scripts/smoke_test.py` has working code.
- The Windows console is cp1250, so any script that prints Cyrillic must call `sys.stdout.reconfigure(encoding="utf-8")`.
- Code and comments are in English. `README.md` and `REPORT.md` are in **Russian**.
- Keys go only in `.env`. `.gitignore` must cover `.env`, `.venv`, `cache/`, `runs/` and `task.md`.
- LLM service is shared: keep parallel calls to 3–4, retry on errors, and cache searches and fetches on disk.
- Push to GitHub only when the user asks.

## Commands

These are planned commands. Confirm them in `HANDOFF.md` once they exist.

- Setup: `python -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt`, copy `.env.example` to `.env` and fill in the keys.
- `python scripts/smoke_test.py`: runs 1 LLM call, 1 Keenable search and 1 fetch (exists, Phase 0).
- `python scripts/model_bench.py [model ...]`: the model selection benchmark (exists, Phase 0).
- `python -m taro "question" --mode v1|v2|v3 [--no-cache]`: run the agent (v1 and v2 exist since Phase 1, v3 comes in Phase 2). Output goes to `runs/<YYYYmmdd-HHMMSS>-<mode>/` (`report.md`, `report.json`, `trace.jsonl`). `taro/runner.py:run()` is the shared entry point for the CLI and the server.
- `python -m taro serve`: start the web UI at http://localhost:8000. The built page in `web/` is committed, so Node is only needed to change the UI.
- `pytest` runs all tests (they need no network; `pytest.ini` sets `asyncio_mode = auto`). `pytest tests/test_x.py::test_name` runs a single test.
- `python -m eval.run_eval`: run the evaluation and experiments.
