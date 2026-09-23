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

---

## Phase 1: foundation, v1 bare LLM, v2 simple RAG (2026-09-23)

**What I did, step by step**
1. Read `HANDOFF.md` and the plan. Phase 0 was done, so this session was Phase 1.
2. Looked at the raw output of Keenable once more (search results are plain text blocks separated by `---`, a failed page fetch comes back marked as an error), so the parser matches reality.
3. Wrote the foundation:
   - `config.py`: reads the keys and model names.
   - `llm.py`: talks to the language model, retries when the server has trouble, and at most 3 calls at a time. When we ask for JSON, it checks the JSON and, if it's wrong, tells the model the error and asks again.
   - `search.py`: search and page fetch through Keenable, saved on disk so a repeated question costs nothing.
   - `report.py`: a step log (`trace.jsonl`) written as the run goes, plus the final `report.md` and `report.json`.
   - `text.py`: splits the answer into sentences and reads the `[1][2]` citations.
4. Wrote v1 (the model answers alone) and v2 (1 search → 8 best results → answer with `[n]`), plus the `python -m taro "question" --mode v1|v2` command.
5. Wrote 16 small tests that run without internet.
6. Ran real questions in English and Russian, and a trick question ("first human on Mars in 2024").

**What came out**
- v1 honestly says it doesn't know about the 2025 Nobel Prize, which is a good baseline.
- v2 answers correctly (Clarke, Devoret, Martinis) with citations in about 5 seconds, and for the Mars question says the sources don't mention it.
- A repeated question uses the saved search result (cache hit).
- Interesting v2 mistake: asked who led ISP RAS after Ivannikov, it said "after his death", but he died in 2016 and the new director was appointed in 2015. The model filled a gap on its own. This is exactly what v3 must prevent, and it's a good example for the report.

**Problems and how I solved them**
- **My mistake:** the retry logger read the previous error at the wrong moment (the retry library had already cleared it), which crashed the test. Fix: log the error in the library's "before waiting" hook.
- **My mistake:** the sentence splitter cut "Michel H. Devoret" into pieces at the initial "H.", so the first pieces lost their citations. I found it by reading the saved report. Fix: don't split after single-letter initials and common abbreviations (Dr., им., г. …), and added a test for it.
- Some search results have HTML inside the title (`<br/><small>…`). Fix: strip the tags.
- Removing the model's own `【source】` markers left double spaces. Fix: clean spaces after removing the markers.
- One test run took about 5 minutes for no clear reason (it normally takes 5 seconds). A rerun was normal, so it was a one-time slowdown on the machine, not in the code.

**Commit:** `Phase 1: foundation, v1 bare LLM, v2 simple RAG`
