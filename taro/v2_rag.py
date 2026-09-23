"""Version 2: simple RAG. One search with the question, top results' snippets, an answer with [n] citations."""
from . import prompts
from .llm import LLM
from .schemas import Report, Source
from .search import Search, domain, normalize_url


async def run_v2(question: str, llm: LLM, search: Search) -> Report:
    settings, trace = llm.settings, llm.trace

    trace.event("step", name="search", query=question)
    # ask for a few extra results: duplicates and empty snippets are dropped below
    results = await search.search(question, max_results=settings.v2_results + 4,
                                  snippet_max_length=settings.v2_snippet_chars)
    sources: list[Source] = []
    seen: set[str] = set()
    for r in results:
        key = normalize_url(r.url)
        if key in seen or not r.snippet.strip():
            continue
        seen.add(key)
        sources.append(Source(id=len(sources) + 1, url=r.url, title=r.title, domain=domain(r.url),
                              published=r.published, snippet=r.snippet))
        if len(sources) == settings.v2_results:
            break

    trace.event("step", name="answer", n_sources=len(sources))
    answer = await llm.chat(prompts.v2_messages(question, sources), purpose="v2_answer")
    return Report(question=question, mode="v2", answer=answer, sources=sources,
                  models={"main": settings.main_model})
