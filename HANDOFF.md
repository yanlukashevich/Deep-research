# HANDOFF

## Status
- **Phase 0 (setup): DONE**
- **Phase 1 (foundation, v1 bare LLM, v2 simple RAG): DONE**
- **Phase 2 (v3 research agent with critic loop): DONE**
- **Next: Phase 3:** confidence scoring (`taro/confidence.py`), the final report format, tests.
  Commit message: `Phase 3: confidence scoring, report format, tests`.
  What Phase 3 needs from what exists: `Fact.disputed` is already set by the critic, `Source.domain` plus
  `pages.domain_quality()` give the site quality, and `Report.sentences[*].citations` hold the source ids of
  each sentence. So the formula is `0.5·min(sites,3)/3 + 0.5·quality − 0.3·contradiction`, where `sites` counts
  distinct domains among the cited sources, `quality` averages their `domain_quality`, and `contradiction` is 1
  when any disputed fact belongs to a cited source. Fill `Sentence.score/level/why`, `Report.confidence` and
  `Report.confidence_why`, and show the 🟢🟡🔴 marks in `report.py:to_markdown`.

## What exists
| file | what it does |
|---|---|
| `taro/config.py` | `get_settings()`: keys and models from `.env`, plus limits (LLM concurrency 3, timeouts, v2 sizes, the v3 budgets) |
| `taro/llm.py` | `LLM.chat()`: temperature 0.1, tenacity retries on connection/429/5xx/empty content, one semaphore per event loop. `LLM.json(messages, Schema)`: `response_format=json_object`, validates with Pydantic, sends the error back and retries (2 repairs). Every call is logged to the trace with its tokens |
| `taro/search.py` | `Search` (async context manager, one MCP session): `search(query, **filters)` returns `list[SearchResult]` and `fetch(url)` returns `Page \| None`. `diskcache` in `cache/keenable` (errors aren't cached). Also `normalize_url()`, `domain()`, `clean_title()` and the parsers for Keenable's plain-text output |
| `taro/schemas.py` | `SearchResult`, `Page`, `Source`, `Fact`, `Sentence`, `Report`, plus the shapes the v3 LLM calls return: `Plan`, `Extraction`, `Critique` |
| `taro/text.py` | `normalize_ws`, `clean_answer`, `parse_citations` (`[1][2]`, `[1, 2]`, `[1-3]`), `split_sentences`, `remap_citations` (fact numbers → source numbers) |
| `taro/pages.py` | v3's plain-code helpers: `domain_quality()` (official 1.0 · encyclopedia 0.8 · news 0.7 · unknown 0.5 · blog/forum 0.4), `is_junk()` (job boards, shops, tracking links), `select_pages()` (dedupe by URL and by title, max 2 per site, better sites first), `relevant_passages()` (BM25 trim), `verify_quote()` (rapidfuzz) |
| `taro/report.py` | `Trace` (appends each event to `trace.jsonl` immediately, counters in `stats`, optional `listener` for the Phase 4 live UI), `new_run_dir`, `finalize` (parses sentences, drops out-of-range citations), `save_report` (`report.md` + `report.json`) |
| `taro/prompts.py` | all prompts: v1, v2, and v3's planner / extractor / critic / writer. Each includes today's date and answers in the question's language |
| `taro/v1_bare.py` | 1 LLM call, no search |
| `taro/v2_rag.py` | 1 search with the raw question (12 results, snippets ≤2000 chars) → dedupe by URL → top 8 → 1 LLM call with `[n]` rules |
| `taro/v3_research.py` | `Research`: planner → (search all queries → pick pages → read → extract quoted facts) → critic → loop → writer |
| `taro/runner.py` | `run(question, mode, listener=, use_cache=)` returns `(Report, run_dir)`. Shared by the CLI and the future server |
| `taro/__main__.py` | the CLI (default `--mode v3`) |
| `tests/` | 29 unit tests, no network: text/citations, search parsing/URLs, LLM JSON repair, page choice/quality/BM25/quote check, and v3's extraction step against a scripted fake model |

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

## Deviations from plan
- New files not in the plan's layout: `taro/text.py`, `taro/pages.py` (site quality, page choice, BM25 trim,
  quote check — `confidence.py` will import `domain_quality` from it), `taro/runner.py`, `pytest.ini`.
- Tests were written in Phases 1–2 although the plan puts them in Phase 3. Phase 3 still adds the confidence tests.
- `report.md` already prints the quotes under each source and a "Where the sources disagree" section (the plan
  puts the source list with quotes in Phase 3), because otherwise v3's own output was not checkable by hand.
- Run folders are `runs/<YYYYmmdd-HHMMSS>-<mode>/`, not `runs/<time>/`, so "compare all 3" runs stay apart.

## Known issues / TODO
- **The planner can misread an abbreviation.** The first v3 run on `ИСП РАН` expanded it to "Институт солнечной
  физики" and wasted a whole round on the wrong institute. The prompt now forbids guessing an expansion, and
  `_fallback_queries` is the safety net, but a wrong guess still costs a round.
- Sources that supplied facts the writer did not use still appear in the source list (for example the Economics
  Nobel page in the physics run). Harmless, but a reader may wonder why source 4 is never cited.
- Fact statements from the fast model sometimes spell numbers out in words ("две тысячи пятнадцатом"). The writer
  fixes this in the answer, but the raw facts in `report.json` look odd.
- `v3_time_budget_s = 420` is only checked between rounds, so a single slow round can overrun it.
- `python -m taro serve` doesn't exist yet (Phase 4).

## Check it works
```
.venv\Scripts\activate
pytest                                                    # 29 tests, ~5 s, no network
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v3   # ~60 s, 5 sources, 13 facts
python -m taro "Кто стал директором ИСП РАН после Иванникова и в каком году?" --mode v3
        # 2 rounds; says Avetisyan, August 2015 — and does NOT repeat v2's "after his death" invention
python -m taro "What was the name of the first human to walk on Mars in 2024?" --mode v3   # says it didn't happen
python -m taro "<question>" --mode v1|v2                  # the baselines still work
python scripts/smoke_test.py                              # raw connectivity check
```
Each run writes `runs/<time>-<mode>/report.md`, `report.json` and `trace.jsonl`. In the terminal the run prints
its steps live (`plan → round → select → read → extract → critic → write`).
