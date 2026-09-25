# HANDOFF

## Status
- **Phase 0 (setup): DONE**
- **Phase 1 (foundation, v1 bare LLM, v2 simple RAG): DONE**
- **Phase 2 (v3 research agent with critic loop): DONE**
- **Phase 3 (confidence scoring, report format, tests): DONE**
- **Phase 4 (CLI and web UI): DONE**
- **Next: Phase 5:** evaluation and experiments — `eval/questions.jsonl` (~30 questions), an LLM judge,
  the E1–E4 experiments and the error analysis. Commit message: `Phase 5: evaluation and experiment results`.
  What Phase 5 needs from what exists: `runner.run(question, mode)` returns `(Report, run_dir)` and writes
  `report.json`, so the harness only has to loop over questions and modes and read the JSON back.
  `Report.confidence`, `sentences[*].score` and `stats` are all the calibration and cost numbers need;
  `stats["quotes_rejected"]` is E4 and is already counted.

## What exists
| file | what it does |
|---|---|
| `taro/config.py` | `get_settings()`: keys and models from `.env`, plus limits (LLM concurrency 3, timeouts, v2 sizes, the v3 budgets) |
| `taro/llm.py` | `LLM.chat()`: temperature 0.1, tenacity retries on connection/429/5xx/empty content, one semaphore per event loop. `LLM.json(messages, Schema)`: `response_format=json_object`, validates with Pydantic, sends the error back and retries (2 repairs). Every call is logged to the trace with its tokens |
| `taro/search.py` | `Search` (async context manager, one MCP session): `search(query, **filters)` returns `list[SearchResult]` and `fetch(url)` returns `Page \| None`. `diskcache` in `cache/keenable` (errors aren't cached). Also `normalize_url()`, `domain()`, `clean_title()` and the parsers for Keenable's plain-text output |
| `taro/schemas.py` | `SearchResult`, `Page`, `Source`, `Fact`, `Sentence`, `Report`, plus the shapes the v3 LLM calls return: `Plan`, `Extraction`, `Critique` |
| `taro/text.py` | `normalize_ws`, `clean_answer`, `parse_citations` (`[1][2]`, `[1, 2]`, `[1-3]`), `split_sentences`, `remap_citations` (fact numbers → source numbers) |
| `taro/pages.py` | v3's plain-code helpers: `domain_quality()` (official 1.0 · encyclopedia 0.8 · news 0.7 · unknown 0.5 · blog/forum 0.4), `is_junk()` (job boards, shops, tracking links), `select_pages()` (dedupe by URL and by title, max 2 per site, better sites first), `relevant_passages()` (BM25 trim), `verify_quote()` (rapidfuzz) |
| `taro/trace.py` | `Trace` (appends each event to `trace.jsonl` immediately, counters in `stats`, optional `listener` for the Phase 4 live UI) and `new_run_dir`. Split out of `report.py` in Phase 3: `search`/`llm` write to the trace, while `report.py` now imports the confidence score, which imports `pages` → `search` |
| `taro/confidence.py` | the formula below: `score_sentence` fills `score`/`level`/`why`, `score_report` fills `Report.confidence`/`confidence_why`, `MARKS` holds 🟢🟡🔴 |
| `taro/report.py` | `finalize` (parses sentences, drops out-of-range citations, then scores them), `marked_answer` (the answer with a mark after each sentence), `to_markdown`, `save_report` (`report.md` + `report.json`). Re-exports `Trace`/`new_run_dir` |
| `taro/prompts.py` | all prompts: v1, v2, and v3's planner / extractor / critic / writer. Each includes today's date and answers in the question's language |
| `taro/v1_bare.py` | 1 LLM call, no search |
| `taro/v2_rag.py` | 1 search with the raw question (12 results, snippets ≤2000 chars) → dedupe by URL → top 8 → 1 LLM call with `[n]` rules |
| `taro/v3_research.py` | `Research`: planner → (search all queries → pick pages → read → extract quoted facts) → critic → loop → writer |
| `taro/runner.py` | `run(question, mode, listener=, use_cache=)` returns `(Report, run_dir)`. Shared by the CLI and the future server |
| `taro/server.py` | FastAPI. `GET /api/run?question=&mode=v1\|v2\|v3\|all&cache=` streams the run as Server-Sent Events: `hello`, one `trace` per step, one `report` per mode, `end`. `slim()` drops prompts, model replies and local paths before anything leaves the machine. `mode=all` runs the three in parallel and labels every event. Also `/api/health` and the built page from `web/dist` |
| `taro/progress.py` | `describe(event)`: one trace event as one readable line ("picked 6 pages out of 31 found"). Used by the CLI; `web/src/lib/format.js` is the same thing for the page |
| `taro/__main__.py` | the CLI (default `--mode v3`) and `python -m taro serve [--host --port]` |
| `web/` | the page: `src/` (React sources), `dist/` (**committed build**, served by the server), `public/fonts` (latin+cyrillic woff2, so it works offline). `npm install && npm run build` after changing `src/` |
| `tests/` | 59 unit tests, no network: text/citations, search parsing/URLs, LLM JSON repair, page choice/quality/BM25/quote check, v3's extraction step against a scripted fake model, the confidence formula, the report rendering (marks, sections, quotes), and the server (what streams, what is stripped, compare mode, one broken mode, the static route) |

## How v3 works now
1. **Planner** (main model, JSON): 3–6 sub-questions, 1–2 queries each (max 8), written as "a description of the
   ideal page". It may set `published_after` for questions about recent events.
2. **Round** (up to `v3_max_rounds = 3`): all queries searched in parallel → `select_pages` (≤6 per round,
   ≤2 per site, junk domains dropped, same article on another host dropped) → pages fetched in parallel →
   each page trimmed to 6k chars by BM25 → the **fast model** extracts `{statement, quote, subquestion}`.
3. **Quote check** (plain code): `verify_quote` fuzzy-searches each quote in the full page text and drops the
   fact if the score is under 85. Rejections are counted in `stats["quotes_rejected"]` and logged.
4. **Critic** (main model, JSON): enough / missing sub-questions / contradictions / new queries. Contradicting
   facts get `disputed = True`, and the notes go to `Report.contradictions`.
5. **Writer** (main model): sees the numbered facts with their quotes and cites fact numbers; `remap_citations`
   then turns those into source numbers, so `[3][7]` from one page becomes `[2]`.
6. Stops on "enough", after 3 rounds, or when a budget is spent (14 pages, 60 facts, 420 s) — the reason is in
   the trace as `step: stop`.

## How the confidence score works

Per sentence, from the sources it cites: `score = 0.5*min(sites,3)/3 + 0.5*quality - 0.3*contradiction`.

- `sites` counts **different websites** (`Source.domain`), so two pages of nobelprize.org are one site.
- `quality` is the average `pages.domain_quality` of the cited sites (official 1.0 · encyclopedia 0.8 ·
  news 0.7 · unknown 0.5 · blog/forum 0.4).
- `contradiction` is 1 when a cited source carries a fact the critic marked `disputed`.
- Buckets: 🟢 ≥ 0.75 · 🟡 ≥ 0.5 · 🔴 below. **No citation always means 0.00 and 🔴.**
- `Report.confidence` = the average sentence score × the share of sub-questions that got a fact.
  With no sub-questions (v1, v2) or when no fact carries a sub-question number, the share is 1.0.
- `Report.confidence_why` is one line a reader can check: how many sentences cite something, how many
  different sites, the average, the sub-question share and whether sources disagree.

Useful numbers: one official page alone → 0.67 🟡 · two official pages → 0.83 🟢 · one news site → 0.52 🟡 ·
one blog → 0.37 🔴 · three news sites → 0.85 🟢. v1 always scores 0.00, which is the point of keeping it.


## How the demo works
1. `python -m taro serve` starts FastAPI on 127.0.0.1:8000 and serves the committed build in `web/dist`.
2. The page opens `GET /api/run?question=…&mode=…`. The server starts the run with a listener that puts every
   trace event on a queue, and yields them as SSE frames: `hello`, then `trace` per step, then one `report`
   per mode (`{report, markdown, lines, run}`), then `end`. Closing the tab cancels the run.
3. The page keeps one state object per mode (`web/src/lib/useRun.js`) and renders: the run log
   (`RunLog` + `format.js` describe), the answer (`Answer` walks `lines`, colours each piece from
   `sentences[i].level`, turns `[n]` into `Citation` chips that show `facts[*].quote` on hover), the
   confidence bar with its "why", the contradictions and not-found lists, and the source cards
   (`Source.quality` → pips and a label).
4. `mode=all` does the same with three runs at once; every event carries `mode`, so three columns fill in
   parallel.

## Key decisions
- **Numbering happens at the end** (`Research._numbered`). Only pages that produced at least one verified fact
  become sources, so the report never lists a source nothing came from, and the numbers the writer cites are the
  numbers the reader sees.
- **The writer cites facts, the report cites sources.** The writer needs the quote-level detail; the reader wants
  one number per page.
- **The fast model reads pages, the main model plans, criticises and writes.** Extraction is the only step that
  runs once per page, so it must be cheap; gemma4:31b copies quotes well enough for the check to pass.
- **A quote is dropped rather than repaired.** Cheap insurance against invented facts, and it costs only a fact.
- **When a round finds nothing and the critic has no new ideas, v3 searches the question itself**
  (`_fallback_queries`), which rescues runs where the planner misread the question.
- The search cache has no expiry, so repeated runs give the same results. Delete `cache/` for fresh ones.
- **One site twice is not a confirmation**, so the score counts domains, not citations. This is what makes
  v3's "two hosts, one article" dedupe worth having: without it a copied claim would look confirmed.
- **An uncited sentence scores 0 even when it is true.** The score measures evidence, not correctness, and
  the whole project exists to keep those two apart.
- **The marks live in the markdown, not in `Report.answer`.** `report.answer` stays clean text with `[n]`;
  `marked_answer()` adds 🟢🟡🔴 for `report.md` and the CLI, and the web UI colours sentences from
  `sentences[*].level` itself.
- **The page never re-derives anything.** `report.answer` is split into sentences by Python only
  (`report.answer_lines()`, the same walk as `marked_answer`), and the server sends the result as `lines`
  next to the report, so the browser just paints piece *i* with sentence *i*'s level. Writing a second
  sentence splitter in JavaScript would put the colours one sentence out of step the first time the two
  disagreed. `Source.quality` is sent for the same reason: the page shows the number the formula used.
- **The trace is the UI.** The server does not invent progress messages; it forwards the events the agent
  already writes to `trace.jsonl`, minus the fields a browser must not see. Anything the page should display
  has to be added to the trace, not to the server.
- **`slim()` is a whitelist in spirit**: prompts (`messages`), model replies (`response`), local paths
  (`run_dir`) and page text are dropped; the token and timing counters stay. A test fails if a prompt ever
  reaches the page.
- **Compare mode runs the three versions in parallel, not one after another.** They share the same LLM
  semaphore, so it costs about as long as v3 alone, and the demo shows v1 finishing in two seconds with no
  sources while v3 is still on round two.

## Deviations from plan
- New files not in the plan's layout: `taro/text.py`, `taro/pages.py` (site quality, page choice, BM25 trim,
  quote check — `confidence.py` imports `domain_quality` from it), `taro/runner.py`, `taro/trace.py`, `pytest.ini`.
- Tests were written in Phases 1–2 although the plan puts them in Phase 3. Phase 3 added the confidence and
  report-rendering tests on top.
- `report.md` already prints the quotes under each source and a "Where the sources disagree" section (the plan
  puts the source list with quotes in Phase 3), because otherwise v3's own output was not checkable by hand.
- Run folders are `runs/<YYYYmmdd-HHMMSS>-<mode>/`, not `runs/<time>/`, so "compare all 3" runs stay apart.
- Phase 4 added `taro/progress.py` (not in the plan's layout) so the CLI and the page describe the same event
  in the same words, and `report.answer_lines()` + `Source.quality` so the page needs no logic of its own.
- Fonts are vendored in `web/public/fonts` (latin + cyrillic woff2, ~300 kB) instead of loaded from a CDN:
  the demo has to render Russian answers and must not depend on the network for its own chrome.

## Known issues / TODO
- **The planner can misread an abbreviation.** The first v3 run on `ИСП РАН` expanded it to "Институт солнечной
  физики" and wasted a whole round on the wrong institute. The prompt now forbids guessing an expansion, and
  `_fallback_queries` is the safety net, but a wrong guess still costs a round.
- Sources that supplied facts the writer did not use still appear in the source list. They are now tagged
  "_(read, but the answer does not cite it)_" instead of being dropped, because dropping one would renumber
  the rest and break the `[n]` markers the writer already wrote. In v2 that tag covers most of the list.
- **The contradiction penalty is per source, not per sentence.** A sentence loses 0.3 when any cited source
  carries a disputed fact, even when the sentence is about something else entirely. Fixing it properly means
  keeping the writer's fact numbers per sentence (`remap_citations` throws them away today) and checking
  whether *that* sentence rests on a disputed fact.
- A sentence with no citation always scores 0, so a harmless lead-in ("Ниже — краткий обзор.") pulls the
  average down as hard as an unsupported claim. The writer prompt discourages such sentences; it does not
  forbid them.
- Fact statements from the fast model sometimes spell numbers out in words ("две тысячи пятнадцатом"). The writer
  fixes this in the answer, but the raw facts in `report.json` look odd.
- `v3_time_budget_s = 420` is only checked between rounds, so a single slow round can overrun it.
- **The page has not been looked at by a human yet.** No browser was available in the Phase 4 session, so it
  was verified headless (the real page mounted in a simulated browser, fed a recorded event stream: the
  answer, underlines, citation links, score, sources and theme toggle all appear). The visual pass and the
  phone-width check are still open.
- The web UI has no automated test in `pytest` — the checks above were a one-off script. If the page keeps
  growing, it needs a JS test runner.
- A report saved by an older version can have `sentences` that no longer match its own `answer` (the initials
  fix changed the splitting). The page renders such a piece as plain text instead of crashing, but the
  colours will be off. Re-run rather than trust an old `report.json`.
- The server has no limit on how many runs can be started at once: every open tab is a live research run.
  Fine for a demo on one machine, not for anything public.
- Stopping a run in the browser closes the stream, which cancels the server task — but a search or LLM call
  already in flight still finishes.

## Check it works
```
.venv\Scripts\activate
pytest                                                    # 50 tests, ~5 s, no network
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v3   # ~60 s, 5 sources, 13 facts
python -m taro "Кто стал директором ИСП РАН после Иванникова и в каком году?" --mode v3
        # 2 rounds; says Avetisyan, August 2015 — and does NOT repeat v2's "after his death" invention
python -m taro "What was the name of the first human to walk on Mars in 2024?" --mode v3   # says it didn't happen
python -m taro "<question>" --mode v1                     # always 0.00 🔴: nothing was verified
python -m taro "<question>" --mode v2                     # usually 🟡: one site per claim
python scripts/smoke_test.py                              # raw connectivity check
python -m taro serve                                      # http://localhost:8000
cd web && npm install && npm run build                    # only when changing the UI
```
Each run writes `runs/<time>-<mode>/report.md`, `report.json` and `trace.jsonl`. In the terminal the run prints
its steps live (`plan → round → select → read → extract → critic → write`), then the answer with a 🟢🟡🔴 mark
after every sentence and the overall confidence with its "why".

In `report.md` check by hand: every sentence carries a mark; a 🔴 sentence really is weakly sourced (open its
`[n]` in the source list and look at the site); the "Confidence" line adds up; the quotes under each source are
one line each and can be found on the page.

On the page check by hand: the steps appear one by one while the run is going (not all at the end); hovering a
`[1]` shows a quote that really is on the page it links to; "why this number" adds up against the sentences on
screen; "all three" shows v1 finishing first with no sources at all; the downloaded markdown is the same report
the CLI writes; the dark theme; and nothing overflows sideways at phone width.
