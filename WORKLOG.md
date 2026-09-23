# Work log

A simple diary of what the agent did in each phase. New entries go at the bottom, and old entries are never rewritten.
(For the *current* state and next steps, see `HANDOFF.md`.)

---

## Phase 0: project setup (2026-09-23)

**What I did, step by step**
1. Read the plan and the assignment. There was no `HANDOFF.md`, so I started from Phase 0.
2. Created `.gitignore` so that `.env` (keys), `task.md` (also has keys), `.venv`, `cache/` and `runs/` never go into git.
3. Created the `.venv` virtual environment and installed the libraries from `requirements.txt`.
4. Put the keys in `.env` and created `.env.example` with no real values.
5. Tested Keenable search: listed its 2 tools, then ran 1 search and 1 page fetch. Both work and are fast (under half a second).
6. Listed the language models on the LiteLLM server (7 models) and wrote a small benchmark (`scripts/model_bench.py`) that checks each model for:
   - correct JSON
   - quotes copied exactly from the text
   - speed
   - quality of Russian
   - how long a text it can read
7. Picked the models based on the results, then ran the final smoke test: 1 LLM call, 1 search, 1 fetch.
8. Wrote `HANDOFF.md`, updated `CLAUDE.md` and made the commit.

**What came out**
- A working project skeleton with all libraries installed and secrets kept safe.
- Main model: **gpt-oss-120b** (fast, reliable). Fast model for reading pages: **gemma4:31b**.
- Two models turned out to be broken on the server: `qwen3.6` doesn't answer, and `glm-4.7-flash` fails on JSON.

**Problems and how I solved them**
- The `mcp` library is a new version (2.x) with different function names than the docs. I found the right names in its source code.
- The Windows console couldn't print Russian letters. Fix: switch output to UTF-8.
- **My mistake:** once a command hung because I left a stray `cat >` in it that waited for keyboard input. I stopped it and reran it correctly.
- **My mistake:** the benchmark looked frozen for about 8 minutes. The broken `qwen3.6` model never answered, and I had piped the output through `tail`, which shows nothing until the very end. Fix: shorter timeouts, a time limit per model, and results printed as soon as each model finishes.

**Commit:** `Phase 0: project setup`
