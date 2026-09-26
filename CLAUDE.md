# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TARO is a deep-research agent. It takes a question, searches the web through Keenable MCP, extracts facts with exact quotes, and writes an answer where every sentence is cited and scored for confidence. The answer must come from the pages it retrieved, not from what the model already knows.

- **The full plan is the source of truth:** `PLAN.md` in this repo (a verbatim copy of the original plan, `C:\Users\yanlu\.claude\plans\ok-zrob-plan-zrobienia-federated-dewdrop.md`). It covers the phases, the layout, the v1/v2/v3 design, the confidence formula and the verification criteria. Read it before starting.
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
   - Add an entry at the bottom of `WORKLOG.md`: a simple diary in plain language, with no jargon. Never rewrite old entries. Write it in detail, so that someone who has not seen the code can follow what happened. Each entry covers:
     - what you did, step by step, and why each step was needed
     - what came out
     - **interesting moments**: things that were surprising or that you had to decide about the AI side of the work, and what you decided in the end. For example how the model behaved, where it made things up or ignored the instructions, what the prompt had to say to make it behave, which model turned out better and why, how the search results or the confidence scores looked. Plain technical hiccups (typos, wrong imports, library versions, failing tests) do **not** belong here.
     - examples what to check by hand that things work
     - the commit message

     `HANDOFF.md` holds the current state, while `WORKLOG.md` is the history.
   - Commit using the message given in the plan (for example, `Phase 1: foundation, v1 bare LLM, v2 simple RAG`), with `HANDOFF.md` and `WORKLOG.md` included.
4. If you change a command or a key architectural fact, update this file too.

## Conventions

- Python 3.12 + asyncio, with no agent frameworks. LLM calls use the `openai` client against LiteLLM (`https://litellm.ispras.ru/`), and search uses the official `mcp` SDK.
- Models: `openai/gpt-oss-120b` (context 60k tokens) in **both** roles since 2026-09-25 — the gateway serves `google/gemma4:31b` at ~28 tok/s against gpt-oss's ~95, so page reading moved too. Both are set in `.env` (`TARO_MAIN_MODEL`, `TARO_FAST_MODEL`); nothing in the code names a model. The measurement is in `HANDOFF.md`.
- The `mcp` SDK is **2.x**: use `streamable_http_client(url, http_client=httpx2.AsyncClient(headers=...))` and snake_case result fields. `scripts/smoke_test.py` has working code.
- The Windows console is cp1250, so any script that prints Cyrillic must call `sys.stdout.reconfigure(encoding="utf-8")`.
- Code and comments are in English. `README.md` and `REPORT.md` are in **Russian**.
- Keys go only in `.env`. `.gitignore` must cover `.env`, `.venv`, `runs/` and `task.md`.
- LLM service is shared: keep parallel calls to 3–4 and retry on errors. Searches and fetches are **not**
  cached: every run goes to the network, so an answer is never older than the run.
- Push to GitHub only when the user asks.

## Commands

These are planned commands. Confirm them in `HANDOFF.md` once they exist.

- Setup: `python -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt`, copy `.env.example` to `.env` and fill in the keys.
- `python scripts/smoke_test.py`: runs 1 LLM call, 1 Keenable search and 1 fetch (exists, Phase 0).
- `python scripts/model_bench.py [model ...]`: the model selection benchmark (exists, Phase 0).
- `python -m taro "question" --mode v1|v2|v3`: run the agent (all three exist; `v3` is the default). Output goes to `runs/<YYYYmmdd-HHMMSS>-<mode>/` (`report.md`, `report.json`, `trace.jsonl`); `TARO_RUNS_DIR` moves that folder elsewhere, e.g. `/home/runs` on Azure App Service. `taro/runner.py:run()` is the shared entry point for the CLI and the server.
- `python -m taro serve [--host --port]`: start the web UI at http://localhost:8000 (FastAPI + SSE).
  The built page in `web/dist` is committed, so Node is only needed to change the UI: `cd web && npm install && npm run build`
  (`npm run dev` proxies `/api` to a running server on port 8000).
- Deployed on Azure App Service: **https://taro-research.azurewebsites.net** (resource group
  `rg-taro`, plan `asp-taro` B1 Linux, app `taro-research`). Redeploy with `az webapp deploy -g rg-taro
  -n taro-research --src-path deploy.zip --type zip`; the zip holds only `taro/`, `web/dist/` and
  `requirements.txt`, never `.env`. Keys live as App Service settings. The startup command runs **one**
  uvicorn process (never gunicorn workers: the LLM semaphore is per event loop, and SSE must stay on
  one instance). Full details and the zip recipe are in `HANDOFF.md`. Other apps in that subscription
  are unrelated — do not touch them.
- `pytest` runs all tests (they need no network; `pytest.ini` sets `asyncio_mode = auto`). `pytest tests/test_x.py::test_name` runs a single test.
- `python -m eval.run_eval`: run the evaluation and experiments (exists, Phase 5). Resumable: it skips
  every question already stored in `eval/results/records/`, and that folder is re-seeded from the
  committed `eval/results/raw.jsonl` when it is missing, so `--report` works on a fresh clone. `--only e1|e2`, `--types`, `--limit`,
  `--concurrency` (default 2), `--force`, `--report` (rebuild the tables without running anything).
  Writes `eval/results/`: `results.md`, `raw.jsonl`, `judge_sample.md`, `failures.md`.
- `python -m eval.quote_audit`: scores every rejected quote against its page again (E4 in detail),
  writes `eval/results/quote_audit.md`.
