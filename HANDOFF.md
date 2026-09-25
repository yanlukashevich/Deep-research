# HANDOFF

## Status
- **Phase 0 (setup): DONE**
- **Phase 1 (foundation, v1 bare LLM, v2 simple RAG): DONE**
- **Phase 2 (v3 research agent with critic loop): DONE**
- **Phase 3 (confidence scoring, report format, tests): DONE**
- **Phase 4 (CLI and web UI): DONE**
- **Phase 5 (evaluation and experiments): DONE** - 28 questions, 108 runs, E1-E4 all measured.
- **Extra pass (the page): DONE (2026-09-25)** - chat-style asking, one rotating example, and the run
  drawn as a layered graph whose every step opens up. Not in the plan; asked for after Phase 6.
- **Second pass (the page again): DONE (2026-09-25)** - an empty landing page with the box in the
  middle that flies to the top right when the question is sent, the run drawn as a real two-dimensional
  graph (searches fan out, pages hang off the search that found them, everything converges on the
  critic), and one answer with the numbers under it as fold-out statistics instead of several
  sections. Not in the plan; asked for after the first extra pass.
- **Phase 6 (README, report, examples): DONE** - `README.md` and `REPORT.md` in Russian,
  `examples/` with 5 saved reports, fresh-clone check passed (it found two real bugs, both fixed
  below).
- **Next: nothing is planned.** The plan is finished. What is left is the TODO list at the bottom,
  ordered by what the evaluation showed actually matters; the two things worth doing first are the
  premise check in the planner and an answer verifier. Nothing has been pushed to GitHub - the user
  asks for that explicitly.

## What exists
| file | what it does |
|---|---|
| `taro/config.py` | `get_settings()`: keys and models from `.env`, plus limits (LLM concurrency 3, timeouts, v2 sizes, the v3 budgets) |
| `taro/llm.py` | `LLM.chat()`: temperature 0.1, tenacity retries on connection/429/5xx/empty content, one semaphore per event loop. `LLM.json(messages, Schema)`: `response_format=json_object`, validates with Pydantic, sends the error back and retries (2 repairs). Every call is logged to the trace with its tokens |
| `taro/search.py` | `Search` (async context manager, one MCP session): `search(query, **filters)` returns `list[SearchResult]` and `fetch(url)` returns `Page \| None`. Nothing is cached: every search and fetch is a live call. Also `normalize_url()`, `domain()`, `clean_title()` and the parsers for Keenable's plain-text output |
| `taro/schemas.py` | `SearchResult`, `Page`, `Source`, `Fact`, `Sentence`, `Report`, plus the shapes the v3 LLM calls return: `Plan`, `Extraction`, `Critique` |
| `taro/text.py` | `normalize_ws`, `clean_answer`, `parse_citations` (`[1][2]`, `[1, 2]`, `[1-3]`), `split_sentences`, `remap_citations` (fact numbers → source numbers) |
| `taro/pages.py` | v3's plain-code helpers: `domain_quality()` (official 1.0 · encyclopedia 0.8 · news 0.7 · unknown 0.5 · blog/forum 0.4), `is_junk()`, `select_pages()`, `relevant_passages()` (BM25 trim), `verify_quote()` (rapidfuzz, min 15 chars) |
| `taro/trace.py` | `Trace` (appends each event to `trace.jsonl` immediately, counters in `stats`, optional `listener` for the live UI) and `new_run_dir` |
| `taro/confidence.py` | the formula below: `score_sentence`, `score_report`, `MARKS` (🟢🟡🔴) |
| `taro/report.py` | `finalize`, `marked_answer`, `answer_lines`, `to_markdown`, `save_report` |
| `taro/prompts.py` | all prompts: v1, v2, and v3's planner / extractor / critic / writer |
| `taro/v1_bare.py` | 1 LLM call, no search |
| `taro/v2_rag.py` | 1 search with the raw question → dedupe by URL → top 8 → 1 LLM call with `[n]` rules |
| `taro/v3_research.py` | `Research`: planner → (search → pick pages → read → extract quoted facts) → critic → loop → writer. Counts `rounds` in the trace (Phase 5, for E2) |
| `taro/runner.py` | `run(question, mode, listener=, overrides=, label=)` returns `(Report, run_dir)`. `overrides` replaces Settings fields for one run (E2 varies `v3_max_rounds`), `label` names the run folder. Shared by the CLI, the server and the evaluation |
| `taro/server.py` | FastAPI + SSE. `GET /api/run?question=&mode=v1\|v2\|v3\|all`; `slim()` drops prompts, model replies and local paths |
| `taro/progress.py` | `describe(event)`: one trace event as one readable line, for the CLI (the page draws the graph instead) |
| `taro/__main__.py` | the CLI (default `--mode v3`) and `python -m taro serve` |
| `web/` | the page: `src/` (React), `dist/` (**committed build**), `public/fonts` (offline woff2) |
| `web/src/lib/graph.js` | folds the trace into `{nodes, edges, rounds, stats}`: a node per step (question, planner, one per search, one per page, critic, writer), the edges between them, and the detail blocks a reader opens. Pure, imports nothing - `node` can run it over a saved `trace.jsonl` |
| `web/src/components/RunGraph.jsx` | draws that graph: rows of blocks laid out by flexbox, edges measured from the DOM after every render (so a row that wraps still gets its curves) and drawn as SVG curves, the block that is open showing its detail under the graph, the whole thing folding away when the answer lands |
| `web/src/components/RunStats.jsx` | what the run cost, as tiles that roll to their value and open one at a time: time, model calls, tokens, searches, pages, facts, sources, estimated price. Also `Confidence`: the score as a percentage bar, the sentence mix, and every sentence with its own score |
| `web/src/components/StepDetail.jsx` | the inside of one step: the query as the tool received it and what came back, the pages with their sizes, every statement with its quote, the rejected quotes, the critic's own words |
| `eval/questions.jsonl` | the 28 test questions: 10 multi-step, 8 fresh 2026, 5 open, 5 false premise; 9 in Russian. Each has a gold answer and key points; the fresh ones carry the page the gold was checked against |
| `eval/schemas.py` | `Item` (a question), `Record` (one question in one configuration + the judge's verdicts), `Judgement`, `CitationVerdict` |
| `eval/dataset.py` | load the questions, load/save records, write `raw.jsonl` |
| `eval/judge.py` | the LLM judge, three separate calls: `judge_answer` (against the gold), `judge_citations` (one call per report: every cited sentence against the quotes of its sources), `self_confidence` (the E3 baseline: "how sure are you?", with no sources in the prompt) |
| `eval/harness.py` | `Config` (a labelled mode + settings overrides), `run_item` (run → judge → save, skips what is already on disk), `run_all` (N runs at a time), `evidence_of` (quotes in v3, search snippets in v2) |
| `eval/metrics.py` | pure functions: accuracy, citation quality, honesty, calibration, `auc`, `discrimination`, cost, `quote_check` |
| `eval/run_eval.py` | the CLI and every table. Writes `results.md`, `judge_sample.md`, `failures.md`, `raw.jsonl` |
| `eval/quote_audit.py` | E4 in detail: re-scores every rejected quote against its page and sorts the rejections by what they were → `results/quote_audit.md` |
| `eval/judge_check.md`, `eval/error_analysis.md` | written by hand: the check of 21 judge decisions, and the failures sorted into five causes |
| `README.md` | **RU**: what it is, install, run, mermaid diagram of v3, the headline numbers, limitations |
| `REPORT.md` | **RU**: how the task was read, the five design decisions, the papers the ideas come from (ReAct, Self-RAG/CRAG, STORM, ALCE, FreshQA, FRAMES), E1-E4 with commentary, the five causes of failure, limitations, ten next steps |
| `examples/` | 5 saved reports (`report.md` + `report.json`) with an RU index: fr01 in v3 and v1 (the same question with and without search), fr07 (RU, fresh), mh02 (RU, multi-step, shows a derived sentence), fp05 (false premise). Plus one `trace.jsonl` |
| `tests/` | 97 unit tests, no network. `tests/test_eval.py` (34) covers the question set, the metrics, the judge against a scripted fake model, and the tables |

## How v3 works now
1. **Planner** (main model, JSON): 3–6 sub-questions, 1–2 queries each (max 8). May set `published_after`.
2. **Round** (up to `v3_max_rounds = 3`): all queries searched in parallel → `select_pages` (≤6 per round,
   ≤2 per site, junk dropped) → fetched in parallel → trimmed to 6k chars by BM25 → the **fast model**
   extracts `{statement, quote, subquestion}`.
3. **Quote check** (plain code): `verify_quote` fuzzy-searches each quote in the full page text and drops
   the fact below 85. Counted in `stats["quotes_rejected"]`.
4. **Critic** (main model, JSON): enough / missing sub-questions / contradictions / new queries.
5. **Writer** (main model): cites fact numbers; `remap_citations` turns them into source numbers.
6. Stops on "enough", after 3 rounds, or on a budget (14 pages, 60 facts, 420 s).

## How the confidence score works

Per sentence, from the sources it cites: `score = 0.5*min(sites,3)/3 + 0.5*quality - 0.3*contradiction`.

- `sites` counts **different websites**; `quality` is the average `pages.domain_quality`;
  `contradiction` is 1 when a cited source carries a fact the critic marked `disputed`.
- Buckets: 🟢 ≥ 0.75 · 🟡 ≥ 0.5 · 🔴 below. **No citation always means 0.00 and 🔴.**
- `Report.confidence` = the average sentence score × the share of sub-questions that got a fact.

## What the evaluation found (Phase 5)

28 questions × {v1, v2, v3} plus 12 questions × {1, 2 rounds} = 108 runs. Full tables in
`eval/results/results.md`; every claim below is reproducible from `eval/results/raw.jsonl`.

| | correct | citations supported | avg confidence | s/run | tokens/run |
|---|---|---|---|---|---|
| v1 (bare LLM) | 57% | — (never cites) | 0.00 | 2 | 409 |
| v2 (one search) | 79% | 61% | 0.47 | 5 | 3,186 |
| v3 (research agent) | **89%** | **74%** | 0.53 | 57 | 25,858 |

- **On the 8 fresh 2026 questions: v1 scores 0/8, v2 and v3 both 8/8.** This is the whole argument for
  retrieval, and it is as clean a split as the test set can give.
- **Nothing was invented by v2 or v3 on the false-premise questions** (v1 closed a Russian institute
  that is still open and made up two Abel Prize laureates).
- **E2, the critic loop pays off**: on the same 12 questions, 1 round gives 83% correct, 3 rounds 100%.
  It costs 1.6× the tokens and 1.6× the time. Most runs use 1.4 rounds — the critic usually says
  "enough" after the first.
- **E3, our formula beats the model's own confidence**: AUC 0.79 vs 0.59. Every 🟢 and 🟡 report was
  correct (34 of 34); 🔴 reports were correct 58% of the time. The model's own number puts 54 of 84
  answers in 🟢, wrong ones included — it barely separates anything.
- **Per sentence the formula is monotone**: 🟢 sentences are really supported 85% of the time, 🟡 64%,
  🔴 35%.
- **E4, nobody invented a quote.** All 129 rejected quotes were re-scored against their page
  (`eval/results/quote_audit.md`): 64% were real page text re-typed with edits, 34% paraphrase or a
  line assembled out of a table, 2 too short. **Nothing scored below 50.** The check enforces quote
  discipline rather than catching fabrication.

## Key decisions
- **Numbering happens at the end** (`Research._numbered`). Only pages that produced a verified fact
  become sources.
- **The writer cites facts, the report cites sources.**
- **The fast model reads pages, the main model plans, criticises and writes.**
- **A quote is dropped rather than repaired.**
- **When a round finds nothing and the critic has no new ideas, v3 searches the question itself.**
- **One site twice is not a confirmation**, so the score counts domains, not citations.
- **An uncited sentence scores 0 even when it is true.** The score measures evidence, not correctness.
- **The marks live in the markdown, not in `Report.answer`.**
- **The page never re-derives anything** — `lines` and `Source.quality` are sent by the server.
- **The trace is the UI.** The server forwards the agent's own events, minus what a browser must not see.
- **The graph is rebuilt from the trace on every render**, never accumulated in state. Events arrive out of
  order (a rejected quote is traced before the page it came from is finished), so folding the whole list
  each time is the only version that stays correct.
- **A question, once sent, belongs to the thread.** It leaves the composer, becomes the turn's heading and
  cannot be edited; asking again opens a new turn and stops the run before it.
- **Each round counts its own facts.** `extract_done` traces the run's cumulative total, so the graph adds up
  the round's own pages instead - otherwise round 2 claimed every fact of round 1 as well.
- **One failing search is traced twice** (by the search client as `search_error`, by the agent as
  `search_failed`). The graph merges them on the query text, or a round shows queries that never existed.
- **The graph folds itself away when the answer arrives.** The answer is the deliverable; the work behind
  it stays one click away, and everything that is not the text (confidence, cost, sources) is a fold-out
  under it.
- **The edges are measured, not computed.** Flexbox lays the blocks out and a layout effect reads their
  rects, so the curves stay right when a row wraps on a narrow screen. Rows also pick their block width
  from how many blocks stand in them, or eight searches wrap into a wall.
- **The composer is one element in two places.** It is `position: fixed` in both the middle of the empty
  page and the top right corner; the rect is taken in the click handler and replayed as a transform, so
  the box flies instead of disappearing and reappearing.
- **`slim()` is a whitelist in spirit.** A test fails if a prompt ever reaches the page.
- **The evaluation is resumable and stores one file per run.** It is a long chain of calls against a
  shared service, so it has to survive being stopped; `--force` is the only way to pay twice.
- **`records/` is seeded from the committed `raw.jsonl`** (`eval/dataset.py:seed_records`). The
  resume folder is gitignored, so without this a fresh clone would rebuild the tables out of nothing
  and overwrite the committed results with empty ones. Found by the Phase 6 fresh-clone check.
- **No module may call `get_settings()` at import time.** A reviewer runs `pytest` before filling in
  the keys. `tests/test_eval.py::test_every_module_imports_without_api_keys` imports every module of
  `taro/` and `eval/` in a subprocess with the keys blanked.
- **The judge is asked three separate questions, never one.** Rolling "is it right", "is it cited" and
  "how sure are you" into one call made the model answer the easy part and copy it into the rest.
- **The self-confidence call never sees a source** (a test enforces it), or E3 would compare our
  formula against a model that had read the evidence — a different experiment.
- **v2's citations are judged against the search snippet**, not against nothing. v2 extracts no quotes;
  judging it against an empty evidence list would have scored it 0% by construction.

## Deviations from plan
- New files not in the plan's layout: `taro/text.py`, `taro/pages.py`, `taro/runner.py`, `taro/trace.py`,
  `taro/progress.py`, `pytest.ini`; in `eval/`: `schemas.py`, `dataset.py`, `harness.py`, `metrics.py`,
  `quote_audit.py`, `judge_check.md`, `error_analysis.md`.
- Tests were written from Phase 1 on, although the plan puts them in Phase 3.
- Run folders are `runs/<YYYYmmdd-HHMMSS>-<label>/`, so the E2 configurations stay apart. `TARO_RUNS_DIR`
  moves that folder off the code directory, which a packaged deploy (Azure App Service) mounts read-only.
- Fonts are vendored in `web/public/fonts` instead of loaded from a CDN.
- **The FRAMES questions are written in the style of FRAMES, not taken from the dataset.** The dataset
  is not shipped here and downloading it was not worth a network dependency; the 10 multi-step
  questions were written by hand with gold answers that are stable facts.
- **The plan's target of ≥85% citation quality was not met: v3 reaches 74%.** Cause 4 in
  `eval/error_analysis.md` explains why, and it is one mechanism, not general sloppiness.
- `examples/` holds 5 reports rather than the plan's "4–5", and one of them is a v1 run — the point
  of that pair is the same question with and without search.

## Known issues / TODO
Ordered by what the evaluation showed actually matters.

- **A false premise survives the planner.** Both v3 misses on impossible questions (`fp01`, `fp02`)
  come from sub-questions that take the premise for granted ("Which 2024 mission landed the first
  humans on Mars?"), so every search looks for something that never happened and the answer is five
  honest sentences of "the sources do not say". v2, which shows raw snippets to the writer, does
  *better* here. Fix: let the planner ask "is the premise true?" and give the writer the top snippets
  even when no fact was extracted.
- **Derived sentences look better cited than they are.** "Therefore he was 56 years old [1]" carries
  the citations of the birth date and the landing date, and no page states it. This is the main reason
  🟢 sentences are supported only 85% of the time. Fix: let the writer mark a sentence as derived and
  score it from the facts it was derived from.
- **`domain_quality` cannot see a content farm.** 99 of 174 v3 sources are "unknown" (0.5). For
  `op02` all six sources were SEO pages with invented-looking benchmark numbers; the quote check passed
  them because the text really was on the page. Fix: ask the critic to judge sources, not just coverage.
- **Saying "not found" costs as much as being wrong.** 12 of v3's 25 uncited sentences are sentences
  admitting a gap; each scores 0.00 🔴 and pulls the average down. Fix: keep them out of the average
  and count them in the coverage term instead.
- **One official source counts as "one site".** `fr04`'s first sentence, backed by eurovision.com and
  the EBU, scored 🔴 0.49. The formula cannot say "one source, but it is *the* source".
- **The contradiction penalty is per source, not per sentence.** A sentence loses 0.3 when any cited
  source carries a disputed fact, even about something else.
- **The judge is the same model family as the writer.** `eval/judge_check.md` checks 21 of its
  decisions by hand (18 agree, and all 3 disagreements are the judge being stricter than a reader),
  but a judge from another family is the real test and does not exist here.
- Sources that supplied facts the writer did not use still appear in the source list, tagged
  "_(read, but the answer does not cite it)_", because dropping one would renumber the rest.
- Fact statements from the fast model sometimes spell numbers out in words ("две тысячи пятнадцатом").
- `v3_time_budget_s = 420` is only checked between rounds, so one slow round can overrun it.
- **Two of eight searches in a round can be refused by Keenable** with "Too many requests - your
  organization has a 10 RPS limit", because v3 fires a whole round's queries at once and
  `search_concurrency` is not low enough for a round of 8. It costs real coverage (the round then reads
  fewer pages), and the run graph now shows it plainly: "8 searches, 48 results, 2 did not come back".
  Fix: lower `search_concurrency`, or space a round's searches out.
- **The page has still not been looked at by a human.** It was verified headless again in this pass (see
  below), but nobody has seen it on a screen, and the phone-width check is open.
- The web UI has no automated test in `pytest`. What was used instead, and is worth repeating after any
  change to the graph: `node` over `web/src/lib/graph.js` with a saved `trace.jsonl` (it imports nothing),
  and a throwaway `esbuild` + `jsdom` script that renders the whole page, types a question, replays a
  recorded SSE stream and reads back what the page shows. Neither is committed.
- A report saved by an older version can have `sentences` that no longer match its own `answer`.
- The server has no limit on how many runs can be started at once.
- Stopping a run in the browser cancels the server task, but a call already in flight still finishes.
- One run of the 108 died on a TLS error inside the MCP session; the harness re-ran it. If the
  evaluation shows `error` rows, re-running the same command picks exactly those up.

## Check it works
```
.venv\Scripts\activate
pytest                                                    # 97 tests, ~10 s, no network
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v3
python -m taro "Кто стал директором ИСП РАН после Иванникова и в каком году?" --mode v3
python -m taro "What was the name of the first human to walk on Mars in 2024?" --mode v3
        # honest but weak: it says the sources do not say, not that nobody has been to Mars
python -m taro "<question>" --mode v1                     # always 0.00 🔴: nothing was verified
python -m taro serve                                      # http://localhost:8000
        # ask one question, watch the graph grow, then open blocks: the planner's sub-questions, each
        # query with what it came back with, the quotes kept and thrown out, the critic's own words.
        # Then the tiles under the answer: model calls, tokens, searches, pages, sources, est. price
python -m eval.run_eval --report                          # rebuild the tables, no network, ~1 s
python -m eval.run_eval --limit 2 --only e1 --concurrency 1   # 6 real runs, ~2 min
python -m eval.quote_audit                                # needs the runs/ folders to still be there
```
`python -m eval.run_eval` on its own re-runs nothing that is already in `eval/results/records/`, so it
is safe to repeat; `--force` is the only way to pay for all 108 runs again, about 45 minutes. Deleting
the folder is *not* enough any more: it is re-seeded from the committed `raw.jsonl`.

Fresh-clone check (done in Phase 6, worth repeating before handing the repo over):
```
git clone <repo> fresh && cd fresh
python -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env                 # leave the keys empty for now
.venv\Scripts\python -m pytest        # 95 pass without any key
.venv\Scripts\python -m eval.run_eval --report    # results.md and raw.jsonl come out unchanged
.venv\Scripts\python -m taro serve --port 8123    # the committed page is served
# then fill in the two keys and run one question
```

In `eval/results/results.md` check by hand: the E1 row for v1 has 0% on the fresh questions and v3 8/8;
the per-sentence calibration is monotone (🟢 > 🟡 > 🔴). In `judge_sample.md` open any citation verdict
and confirm the quotes shown are the ones the judge was given — that page prints exactly the judge's
input on purpose.
