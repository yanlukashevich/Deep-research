# TARO: plan for the whole project

*The original plan, written before Phase 0 and kept here unchanged as the record of how the
project was designed and built. Every phase below was implemented. Where the finished system
departs from the plan — the search cache was dropped, both model roles ended up on the same
model — the current state and the reasons are in [`HANDOFF.md`](HANDOFF.md), and the story of
each phase is in [`WORKLOG.md`](WORKLOG.md).*

## Context

**What we must build:** a "deep research" agent. It takes a question, searches the web, collects facts, and writes an answer.
Each sentence cites a source, and the answer shows how confident it is.
**Most important rule:** the answer must come from the pages it found, **not** from what the model already knows.
The reviewers (ISP RAS) care about the process, a working prototype, experiments with results, and ideas for the future.

**Decisions already made**
- Claude writes all the code. You review it.
- After each phase: **a git commit** plus a short, simple explanation from me of what was built.
- README and report are in **Russian**. Code and comments are in English.
- The demo is a **CLI plus a custom web app**: a FastAPI backend and a React/Tailwind page in a Perplexity style. Node.js 24 is already installed.
- Plain **Python 3.12 + asyncio**, with no heavy framework and no over-engineering.
- Search uses **Keenable MCP**. It works; I tested it. It has 2 tools:
  - `search_web_pages`: search with filters for dates, site, number of results, and `pro`/`realtime` mode
  - `fetch_page_content`: returns a page as markdown
- LLMs come from **LiteLLM** (`https://litellm.ispras.ru/`). It is OpenAI-compatible, so we use the normal `openai` library.

---

## The 3 versions

| Version | What it does | Why |
|---|---|---|
| **v1 Bare LLM** | The model answers alone, with no internet | Baseline that shows the search really matters |
| **v2 Simple RAG** | 1 search → top results → answer with citations `[1][2]` | The simplest real agent |
| **v3 Research agent** | Plan → search and read pages → **one loop**: "enough? if not, search more" → answer + confidence | The final system |

Choose the version with `python -m taro "question" --mode v1|v2|v3`.

### How v3 works (simple)

```
 Question
    │
    ▼
 Planner ─────► 3–5 sub-questions + search queries (question's language + English)
    │
    ▼
 Search & read ◄──────────────┐   search all queries at once → remove duplicate pages
    │                         │   → choose good pages → read them → pull out facts WITH EXACT QUOTES
    ▼                         │   (the code checks each quote really is on the page; fake quotes are dropped)
 Critic ── "not enough" ──────┘   "Does every sub-question have facts? Do sources disagree?"
    │ enough (or max 3 rounds)    → new queries for the gaps
    ▼
 Writer ──────► answer ONLY from the collected facts; every sentence ends with [1][2]
    │
    ▼
 Confidence ──► score for each sentence + overall, with a short "why"   (plain code, no LLM)
    │
    ▼
 Report: answer · confidence · sources · "what we couldn't find"
```

**Confidence (simple and explainable).** For each sentence we look at the facts it cites:
- **sites**: how many *different* websites say it (1 / 2 / 3+)
- **quality**: what kind of websites they are (official or scientific 1.0 · encyclopedia 0.8 · news 0.7 · company 0.6 · blog or forum 0.4)
- **contradiction**: did the critic find a source saying the opposite?
- Starting formula: `score = 0.5·min(sites,3)/3 + 0.5·quality − 0.3·contradiction`
- Buckets: 🟢 high ≥ 0.75 · 🟡 medium ≥ 0.5 · 🔴 low. A sentence with no citation is always 🔴.
- **Overall confidence** = average sentence score × the share of sub-questions we found facts for.

---

## Project layout

```
Dzimas_task/
├── taro/
│   ├── config.py        # keys from .env, model names, limits
│   ├── llm.py           # talks to LiteLLM + checks JSON answers + retries
│   ├── search.py        # Keenable MCP: search() and fetch(), cached on disk
│   ├── schemas.py       # data shapes: Source, Fact, Report …
│   ├── prompts.py       # all prompts in one place
│   ├── v1_bare.py       # version 1
│   ├── v2_rag.py        # version 2
│   ├── v3_research.py   # version 3: planner → search & read → critic loop → writer
│   ├── confidence.py    # confidence formula
│   ├── report.py        # Markdown/JSON report + log of all steps (trace.jsonl)
│   ├── server.py        # FastAPI: streams live steps + the final report to the web page
│   └── __main__.py      # CLI:  python -m taro "question"   /   python -m taro serve
├── web/                 # React + Tailwind page (built once; FastAPI serves it)
├── eval/                # test questions, metrics, experiment runner, results
├── tests/               # small unit tests
├── examples/            # saved example reports for the reviewers
├── README.md, REPORT.md # in Russian
└── requirements.txt, .env.example, .gitignore
```

Libraries: `openai`, `mcp` (official MCP SDK), `pydantic`, `python-dotenv`, `tenacity` (retries), `rapidfuzz` (quote check),
`rank-bm25` (finding relevant parts of a page), `diskcache`, `rich`, `fastapi` + `uvicorn` (web server), `pytest`.
Web page: React + TypeScript + Tailwind, built with Vite.

---

## Phases (commit after each one)

### Phase 0: Setup
- Create `git init`, a venv, and `requirements.txt`.
- `.gitignore` covers `.env`, `.venv`, `cache/`, `runs/`, **and `task.md`**, because it contains the API keys.
- Keys go only in `.env`. `.env.example` has no real values.
- Smoke test: 1 Keenable search, 1 page fetch, 1 LLM call.
  Note: my session's safety check blocked a LiteLLM call earlier, so you may need to approve it once.
- **Choose the model:** list the LiteLLM models and quickly test the best 2–3 for:
  - valid JSON
  - speed
  - Russian quality
  - context size

  Pick one main model, plus a faster one for reading pages if it helps.
- **Commit:** `Phase 0: project setup`

### Phase 1: Foundation + v1 + v2
- `llm.py` does 3 things:
  - calls the model with low temperature
  - asks for JSON, checks it with Pydantic, and if it's broken sends the error back and asks again
  - limits parallel calls to 3–4 (it's a shared internal service) and retries on errors
- `search.py`: a small wrapper around the MCP SDK. Everything is cached on disk, so repeated runs are free and results are reproducible.
- `report.py`: saves `report.md`, `report.json` and `trace.jsonl` (every step) to `runs/<time>/`.
- **v1:** a single LLM call.
- **v2:** 1 search with the question → top ~8 results → answer where every fact has `[n]`.
- **Commit:** `Phase 1: foundation, v1 bare LLM, v2 simple RAG`

### Phase 2: v3 research agent
- **Planner:** 3–5 sub-questions, 1–2 search queries each.
  - Queries are written as "a description of the ideal page", which Keenable recommends.
  - It adds date filters when the question is about recent events.
- **Search & read:**
  1. run all searches in parallel
  2. remove duplicate URLs
  3. choose pages, max 2 per website, preferring better sites
  4. fetch each page
  5. keep only the relevant parts (BM25)
  6. the LLM extracts facts as `{statement, exact quote}`
- **Quote check:** fuzzy-search each quote in the real page text and drop it if it isn't there. This is a cheap guard against made-up facts.
- **Critic (the one loop):** checks which sub-questions still have no facts, notes contradictions, and writes new queries. It stops when there is enough, or after 3 rounds, or when a page or time limit is reached.
- **Writer:** gets a numbered list of facts and writes the answer. The rules:
  - every factual sentence ends with `[n]`
  - it answers in the question's language
  - it may say "not found in the sources"
  - it must mention when sources disagree
- **Commit:** `Phase 2: v3 research agent with critic loop`

### Phase 3: Confidence + final report + tests
- `confidence.py`: the formula above. Sentences are marked 🟢🟡🔴, and the overall score comes with a short "why".
- The final report contains:
  - the answer with `[n]` and colors
  - overall confidence and why
  - a **"What we couldn't find"** section
  - a sources list (title, site, date, quotes used)
- Unit tests cover the citation parser, quote check, confidence formula and URL cleanup.
- **Commit:** `Phase 3: confidence scoring, report format, tests`

### Phase 4: Demo (CLI + web app)
- **CLI:** live progress in the terminal (planning → searching → reading N pages → round 2 …).
- **Backend (`taro/server.py`, FastAPI):**
  - The agent already reports each step it takes, and the server sends those steps to the page **live** (Server-Sent Events). The user never stares at a blank screen for 2 minutes.
  - The last message is the full report as JSON.
  - API keys stay on the server; the page never sees them.
- **Web page (`web/`, React + Tailwind):**
  - a question box, a **v1 / v2 / v3** switch, and a **"compare all 3"** mode with answers side by side (shows the bare LLM inventing things while v3 cites sources)
  - a **live steps timeline**: plan → searching → reading 9/14 pages → critic round 2
  - an **answer** with sentences underlined by confidence color. **Hovering a citation `[1]` shows the exact quote** and the site; clicking opens the page.
  - an overall confidence badge with a "why" dropdown, plus a "What we couldn't find" section
  - **source cards** with icon, site, title, date and quality stars
  - a few example questions to click during the demo, a download button (md/json), and a light/dark theme
- **One command to run:** `python -m taro serve` → open `http://localhost:8000`.
  The built page is committed, so reviewers only need Python. Node is needed only to change the UI.
- **Commit:** `Phase 4: CLI and web UI (FastAPI + React)`

### Phase 5: Evaluation and experiments
- **Test set** (`eval/questions.jsonl`), about 30 questions:
  - ~10 multi-step questions from **FRAMES**
  - ~8 **"fresh" questions about 2026 events**, which the model can't know without search (I find and double-check the correct answers)
  - ~5 open "compare / explain" questions
  - ~4 **impossible or false-premise questions**: does the agent say "not found" instead of inventing an answer?
  - several of the above in Russian
- **Metrics:**
  - **accuracy:** an LLM judge compares the answer to the correct one (correct / wrong / didn't answer)
  - **citation quality:** % of citations that really support their sentence
  - **honesty** on the impossible questions
  - **calibration:** is 🟢 really correct more often than 🔴?
  - **cost:** LLM calls, searches, seconds

  I hand-check about 20 of the judge's decisions to confirm it's reliable.
- **Experiments:**

  | # | Question | 
  |---|---|
  | E1 | v1 vs v2 vs v3: how much does each step help? (main table) |
  | E2 | v3 with 1 vs 2 vs 3 loop rounds: does the loop pay off? |
  | E3 | Our confidence formula vs just asking the LLM "how sure are you?" |
  | E4 | How many fake quotes does the quote check catch? (counted from the logs, no extra cost) |
- **Error analysis:** sort the failures into types (bad search, bad page, missed fact, writer went beyond the facts, wrong confidence), with 1–2 real examples each.
- **Commit:** `Phase 5: evaluation and experiment results`

### Phase 6: README, report, examples
- **README.md (RU):**
  - what it is
  - installation and running
  - an architecture diagram (mermaid)
  - examples
- **REPORT.md (RU):**
  - how we understood the task
  - design and why it's built this way
  - a short list of the key papers the ideas come from (ReAct, STORM, ALCE, CRAG)
  - experiments and results
  - errors
  - limitations
  - future development: a verifier step, STORM-style perspectives, clarifying questions, a reranker, RL-trained search agents
- `examples/`: 4–5 saved reports in RU and EN.
- Final check: fresh clone → install → run.
- Pushing to GitHub happens only if you ask.
- **Commit:** `Phase 6: README, report, examples`

---

## Things to watch out for

1. **Keys:** `task.md` and `.env` never go into git.
2. **Open-source models break JSON.** We validate every answer and retry with the error message.
3. **Context is limited.** Never paste whole pages; keep only the relevant parts and extract facts.
4. **The model "sneaks in" its own knowledge.** Strict prompts, the quote check, and permission to say "not found" guard against this.
5. **Bad pages** (paywalls, cookie walls, empty pages): skip them and log them.
6. **Endless loop or cost:** max 3 rounds, plus limits on pages and time.
7. **Shared LLM service:** few parallel calls, cache everything, wait and retry when rate-limited.

## Verification
- `pytest` passes.
- `python -m taro "<question>" --mode v3` produces a report where:
  - there are ≥3 sources
  - every factual sentence has a citation
  - each sentence has a confidence color
  - `trace.jsonl` is saved
- v1 and v2 also run from the CLI.
- `python -m taro serve`: I open the page in the browser myself and take screenshots. I check:
  - the live steps
  - the colored sentences
  - hover quotes on `[n]`
  - the source cards
  - "compare all 3" mode
  - the page at a narrow (phone) width
- `python -m eval.run_eval` produces the results table. Sanity checks:
  - v3 clearly beats v1 on the "fresh 2026" questions
  - citation quality is high (target ≥ 85%)
- Manual check: read 3 reports, open the cited pages, and confirm the quotes are really there.
