# HANDOFF

## Status
- **Phase 0 (setup): DONE**
- **Phase 1 (foundation, v1 bare LLM, v2 simple RAG): DONE**
- **Next: Phase 2:** v3 research agent (planner → search & read → critic loop → writer) in `taro/v3_research.py`.
  Commit message: `Phase 2: v3 research agent with critic loop`.
  When done: add `"v3"` to `IMPLEMENTED_MODES` in `taro/runner.py`, call it from `run()`, and switch the CLI default `--mode` to `v3`.

## What exists
| file | what it does |
|---|---|
| `taro/config.py` | `get_settings()`: keys and models from `.env`, plus limits (LLM concurrency 3, timeouts, v2 sizes) |
| `taro/llm.py` | `LLM.chat()`: temperature 0.1, tenacity retries on connection/429/5xx/empty content, one semaphore per event loop. `LLM.json(messages, Schema)`: `response_format=json_object`, validates with Pydantic, sends the error back and retries (2 repairs). Every call is logged to the trace with its tokens |
| `taro/search.py` | `Search` (async context manager, one MCP session): `search(query, **filters)` returns `list[SearchResult]` and `fetch(url)` returns `Page \| None`. `diskcache` in `cache/keenable` (errors aren't cached). Also `normalize_url()`, `domain()`, `clean_title()` and the parsers for Keenable's plain-text output |
| `taro/schemas.py` | `SearchResult`, `Page`, `Source`, `Fact`, `Sentence`, `Report` (already has fields for confidence and not_found for Phase 3) |
| `taro/text.py` | `normalize_ws`, `clean_answer` (strips `【…】`, odd spaces), `parse_citations` (`[1][2]`, `[1, 2]`, `[1-3]`), `split_sentences` (per line, keeps trailing citations, doesn't split on initials/abbreviations) |
| `taro/report.py` | `Trace` (appends each event to `trace.jsonl` immediately, counters in `stats`, optional `listener` for the Phase 4 live UI), `new_run_dir`, `finalize` (parses sentences, drops out-of-range citations), `save_report` (`report.md` + `report.json`) |
| `taro/prompts.py` | v1 and v2 prompts. Both include today's date and answer in the question's language |
| `taro/v1_bare.py` | 1 LLM call, no search |
| `taro/v2_rag.py` | 1 search with the raw question (12 results, snippets ≤2000 chars) → dedupe by URL → top 8 → 1 LLM call with `[n]` rules |
| `taro/runner.py` | `run(question, mode, listener=, use_cache=)` returns `(Report, run_dir)`. Shared by the CLI and the future server |
| `taro/__main__.py` | the CLI |
| `tests/` | 16 unit tests: text/citations, search parsing/URLs, LLM JSON repair and retries (with a fake client, no network) |

## Key decisions
- **v2 uses the search snippets, not fetched pages.** Keenable snippets are already query-relevant passages (up to 2000 chars), so this is the "simplest real RAG": 1 search + 1 LLM call, about 5 s. Reading whole pages is what v3 adds.
- In v2, `[n]` points to sources. In v3 the writer will cite facts, which should be mapped back to source ids in `Sentence.citations` so the report/UI stays the same.
- Run folders are `runs/<YYYYmmdd-HHMMSS>-<mode>/` (the plan says `runs/<time>/`). The mode suffix keeps "compare all 3" runs apart.
- The Keenable `session_id` is set to the run folder name but left out of the cache key.
- The Search cache has no expiry, so repeated runs give the same results. Delete `cache/` to get fresh search results.

## Deviations from plan
- New files not in the plan's layout: `taro/text.py` (sentence and citation parsing, needed by v2 already and by the confidence code later), `taro/runner.py` (shared by the CLI and the server), and `pytest.ini`.
- Some unit tests were written already (the plan puts them in Phase 3). Phase 3 still needs tests for the quote check and the confidence formula.
- The CLI default `--mode` is `v2` until v3 exists.

## Known issues / TODO
- v2 example of the "writer adds its own inference" error, useful for error analysis: `Кто стал директором ИСП РАН после Иванникова…` → v2 says Avetisyan became director "after Ivannikov's death", but the appointment was in 2015 and the death in 2016. v3's quote-backed facts should prevent this.
- Search results can include junk (hh.ru vacancies, tracking redirect links like `link.cfr.org/click/...`). v3's page selection should filter these by domain quality.
- `python -m taro serve` doesn't exist yet (Phase 4).

## Check it works
```
.venv\Scripts\activate
pytest                                                    # 16 tests, ~5 s, no network
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v1   # says it doesn't know
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v2   # Clarke, Devoret, Martinis with [n]
python -m taro "What was the name of the first human to walk on Mars in 2024?" --mode v2   # "sources do not say"
python scripts/smoke_test.py                              # raw connectivity check
```
Each run writes `runs/<time>-<mode>/report.md`, `report.json` and `trace.jsonl`.
