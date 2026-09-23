# HANDOFF

## Status
- **Phase 0 (setup): DONE**
- **Next: Phase 1:** foundation (`config.py`, `llm.py`, `search.py`, `schemas.py`, `report.py`), v1 bare LLM, v2 simple RAG.
  Commit message: `Phase 1: foundation, v1 bare LLM, v2 simple RAG`.

## What exists
- `.venv` (Python 3.12.10), `requirements.txt`, `.gitignore` (covers `.env`, `task.md`, `.venv`, `cache/`, `runs/`), `.env.example`.
- `.env` holds the real keys and the chosen models. It is git-ignored.
- `scripts/smoke_test.py`: lists models, then makes 1 LLM call, 1 Keenable search and 1 fetch.
- `scripts/model_bench.py` + `scripts/model_bench_results.json`: the model selection benchmark, kept as evidence for REPORT.md.

## Model choice (benchmark run on 2026-09-23)
| model | JSON valid | verbatim quotes | extract latency | RU writer | context |
|---|---|---|---|---|---|
| **openai/gpt-oss-120b** | 4/4 | 13/13 | 4.4 s, 114 tok/s | good, flags disagreement | **60,144 tokens** (hard limit from vLLM) |
| **google/gemma4:31b** | 4/4 | 16/16 | 4.3 s, 40 tok/s (no reasoning, 0.5 s on short prompts) | good | ≥63k tested |
| qwen/qwen3.8-27B-fp8 | 4/4 | 16/16 | 17.8 s (long reasoning) | good | ≥65k tested |
| glm-4.7-flash | 0/4: the proxy returns HTTP 500 on `response_format=json_object` | – | ~30 s | – | fails at 48k |
| qwen/qwen3.6-35b-A3B | no response: times out twice | – | – | – | – |

- **Main (planner, critic, writer): `openai/gpt-oss-120b`**. Fastest and largest, reliable JSON, and it explicitly mentions when sources disagree.
- **Fast (page reading / fact extraction): `google/gemma4:31b`**. No reasoning overhead, exact quotes, and a bigger context.
- Fallback: `qwen/qwen3.8-27B-fp8` (same quality, about 4× slower). `ollama/*` and `llama2` were not tested (old or small).

## Facts learned (important for Phase 1+)
- **MCP SDK is 2.x** (`mcp==2.2.0`), and its API differs from most docs:
  - `from mcp.client.streamable_http import streamable_http_client` (not `streamablehttp_client`)
  - headers go through `http_client=httpx2.AsyncClient(headers={"X-API-Key": ...})` (the SDK uses `httpx2`, not `httpx`)
  - result fields are snake_case: `tool.input_schema`, `result.structured_content`
  - see `scripts/smoke_test.py` for working code.
- **Keenable** (fast: search about 0.3 s, fetch about 0.2 s):
  - `search_web_pages(query, max_results≤50 (default 10), site, published_after/before, acquired_after/before, query_time, snippet_max_length, mode="pro"|"realtime", session_id)`.
    It returns **plain text** blocks (`Title:/URL:/Published:/Acquired:/Snippets:`) with no structured content, so we must parse them.
  - `fetch_page_content(url, max_chars (default 50000), live, prompt, session_id)` takes **one url** per call and returns markdown with a `Title:/URL:` header.
- **LiteLLM**: the key can only call LLM routes (`/model/info` returns 403). `response_format={"type":"json_object"}` works for gpt-oss, gemma and qwen3.8.
- **gpt-oss quirks:**
  - its text contains ` ` (narrow no-break space), so the quote check must normalize whitespace
  - it sometimes writes `【source: …】` markers, which the writer's output parser must strip
  - it reasons, so give it `max_tokens` ≥ 2048 or `content` may come back empty.
- **Windows console is cp1250**, so Cyrillic output crashes `print`. Call `sys.stdout.reconfigure(encoding="utf-8")` in the CLI or run with `python -X utf8`.

## Deviations from plan
- Added `scripts/` (the smoke test and the benchmark). This folder is not in the plan's layout.
- Added `httpx`/`pytest-asyncio` to requirements (useful for Phase 1 tests).

## Known issues / TODO
- `qwen3.6-35b-A3B` and `glm-4.7-flash` are currently unusable on the proxy. Recheck later if needed.

## Check it works
```
.venv\Scripts\activate
python scripts/smoke_test.py            # 1 LLM call + 1 search + 1 fetch
python scripts/model_bench.py openai/gpt-oss-120b google/gemma4:31b   # optional: rerun the benchmark (~3 min)
```
