"""Version 3: the research agent.

    planner -> [ search all queries -> pick pages -> read them -> extract quoted facts ] -> critic
                    ^                                                                        |
                    +------------------ "not enough, try these queries" ----------------------+
    -> writer

Everything the answer may contain comes from a fact, and every fact carries a quote that plain code
checked against the page it came from. Made-up quotes are dropped before the writer ever sees them.
"""
import asyncio
from collections import Counter
from dataclasses import dataclass, field

from . import prompts
from .llm import LLM, LLMJSONError
from .pages import relevant_passages, select_pages, verify_quote
from .schemas import Critique, Extraction, Fact, Page, Plan, Report, SearchResult, Source
from .search import Search, domain
from .text import normalize_ws, remap_citations


@dataclass
class _ReadPage:
    """A page we fetched, plus the facts we kept from it. Gets a source number only if it has facts."""
    result: SearchResult
    page: Page
    facts: list[Fact] = field(default_factory=list)

    @property
    def url(self) -> str:
        return self.result.url


async def run_v3(question: str, llm: LLM, search: Search) -> Report:
    return await Research(question, llm, search).run()


class Research:
    def __init__(self, question: str, llm: LLM, search: Search):
        self.question = question
        self.llm = llm
        self.search = search
        self.settings = llm.settings
        self.trace = llm.trace
        self.subquestions: list[str] = []
        self.read: list[_ReadPage] = []
        self.seen_urls: set[str] = set()
        self.domain_counts: Counter = Counter()
        self.seen_titles: set[str] = set()
        self.tried_queries: list[str] = []
        self.contradictions: list[str] = []
        self.published_after: str | None = None

    # ---------- the loop ----------

    async def run(self) -> Report:
        queries = await self._plan()
        for round_no in range(1, self.settings.v3_max_rounds + 1):
            self.trace.event("step", name="round", round=round_no, queries=len(queries))
            self.trace.count("rounds")
            await self._search_and_read(queries, round_no)
            rounds_left = self.settings.v3_max_rounds - round_no
            stop = "max_rounds" if not rounds_left else self._budget_reached()
            if stop:
                self.trace.event("step", name="stop", reason=stop)
                break
            critique = await self._critic(round_no, rounds_left)
            if critique is not None and critique.enough:
                self.trace.event("step", name="stop", reason="enough")
                break
            # a round can also fail because the plan misread the question, so fall back to the question itself
            queries = (self._new_queries(critique) if critique else []) or self._fallback_queries()
            if not queries:
                self.trace.event("step", name="stop", reason="no_new_queries")
                break
        return await self._write()

    async def _plan(self) -> list[str]:
        """Sub-questions and the first batch of searches."""
        self.trace.event("step", name="plan")
        try:
            plan = await self.llm.json(prompts.v3_plan_messages(self.question), Plan, purpose="v3_plan")
        except LLMJSONError as e:  # never lose the run over a broken plan: search the question itself
            self.trace.event("plan_failed", error=repr(e))
            plan = Plan()
        self.subquestions = [normalize_ws(sq.question).strip() for sq in plan.subquestions
                             if sq.question.strip()][:6]
        queries = [normalize_ws(q).strip() for sq in plan.subquestions for q in sq.queries if q.strip()]
        queries = _dedupe(queries)[:8] or [self.question]
        self.published_after = plan.published_after if _is_date(plan.published_after) else None
        self.trace.event("step", name="plan_done", subquestions=self.subquestions, queries=queries,
                         published_after=self.published_after)
        return queries

    def _budget_reached(self) -> str | None:
        """Why we should stop, or None. Guards against an endless (and expensive) loop."""
        if len(self.read) >= self.settings.v3_max_pages:
            return "page_limit"
        if len(self._all_facts()) >= self.settings.v3_max_facts:
            return "fact_limit"
        if self.trace.elapsed() >= self.settings.v3_time_budget_s:
            return "time_limit"
        return None

    # ---------- search and read ----------

    async def _search_and_read(self, queries: list[str], round_no: int) -> None:
        self.tried_queries += [q for q in queries if q not in self.tried_queries]
        results = await self._search_all(queries)
        room = self.settings.v3_max_pages - len(self.read)
        picked = select_pages(results, seen=self.seen_urls, per_domain=self.settings.v3_per_domain,
                              domain_counts=self.domain_counts, seen_titles=self.seen_titles,
                              limit=min(self.settings.v3_pages_per_round, max(room, 0)))
        self.trace.event("step", name="select", round=round_no, candidates=len(results),
                         picked=[r.url for r in picked])
        if not picked:
            return
        self.trace.event("step", name="read", round=round_no, pages=len(picked))
        fetched = await asyncio.gather(*(self.search.fetch(r.url, max_chars=self.settings.v3_page_chars)
                                        for r in picked), return_exceptions=True)
        pairs = [(r, p) for r, p in zip(picked, fetched) if isinstance(p, Page) and p.text.strip()]
        for r, p in zip(picked, fetched):
            if isinstance(p, BaseException):
                self.trace.event("fetch_error", url=r.url, error=repr(p))
        if not pairs:
            return
        self.trace.event("step", name="extract", round=round_no, pages=len(pairs))
        await asyncio.gather(*(self._extract(r, p) for r, p in pairs))
        self.trace.event("step", name="extract_done", round=round_no,
                         facts=len(self._all_facts()), pages_read=len(self.read))

    async def _search_all(self, queries: list[str]) -> list[SearchResult]:
        """Run every query at once; one failing search must not stop the round."""
        done = await asyncio.gather(*(self.search.search(q, max_results=self.settings.v3_search_results,
                                                        published_after=self.published_after)
                                     for q in queries), return_exceptions=True)
        results: list[SearchResult] = []
        for query, res in zip(queries, done):
            if isinstance(res, BaseException):
                self.trace.event("search_failed", query=query, error=repr(res))
                continue
            results += res
        return results

    async def _extract(self, result: SearchResult, page: Page) -> None:
        """Read one page: keep the relevant parts, ask the fast model for quoted facts, check the quotes."""
        source = Source(id=0, url=result.url, title=page.title or result.title, domain=domain(result.url),
                        published=result.published, snippet=result.snippet)
        entry = _ReadPage(result=result, page=page)
        self.read.append(entry)
        text = relevant_passages(page.text, [self.question] + self.subquestions,
                                 max_chars=self.settings.v3_passage_chars)
        if len(text) < 200:  # paywall, cookie wall or an empty stub
            self.trace.event("page_too_short", url=result.url, chars=len(text))
            return
        try:
            extraction = await self.llm.json(
                prompts.v3_extract_messages(self.question, self.subquestions, source, text,
                                            self.settings.v3_facts_per_page),
                Extraction, model=self.settings.fast_model, purpose="v3_extract")
        except LLMJSONError as e:
            self.trace.event("extract_failed", url=result.url, error=repr(e))
            return
        kept, rejected = [], 0
        for raw in extraction.facts[:self.settings.v3_facts_per_page]:
            statement, quote = normalize_ws(raw.statement).strip(), normalize_ws(raw.quote).strip()
            if not statement or not quote:
                continue
            score = verify_quote(quote, page.text, min_score=self.settings.quote_min_score)
            if not score:
                rejected += 1
                self.trace.count("quotes_rejected")
                self.trace.event("quote_rejected", url=result.url, statement=statement, quote=quote)
                continue
            if any(_same(statement, f.statement) for f in kept):
                continue
            self.trace.count("facts_kept")
            kept.append(Fact(id=0, statement=statement, quote=quote, source_id=0, quote_score=score,
                             subquestion=self._valid_subquestion(raw.subquestion)))
        entry.facts = kept
        self.trace.event("facts", url=result.url, kept=len(kept), rejected=rejected,
                         statements=[f.statement for f in kept])

    def _valid_subquestion(self, n: int | None) -> int | None:
        return n if n is not None and 1 <= n <= len(self.subquestions) else None

    # ---------- critic ----------

    async def _critic(self, round_no: int, rounds_left: int) -> Critique | None:
        """The one loop: is this enough, what is missing, what disagrees, what to search next."""
        facts, sources = self._numbered()
        self.trace.event("step", name="critic", round=round_no, facts=len(facts))
        try:
            critique = await self.llm.json(
                prompts.v3_critic_messages(self.question, self.subquestions, facts, sources,
                                           self.tried_queries, round_no, rounds_left),
                Critique, purpose="v3_critic")
        except LLMJSONError as e:
            self.trace.event("critic_failed", error=repr(e))
            return None
        self._mark_contradictions(critique, facts)
        self.trace.event("step", name="critic_done", enough=critique.enough, missing=critique.missing,
                         contradictions=self.contradictions, note=critique.note, queries=critique.queries)
        return critique

    def _mark_contradictions(self, critique: Critique, facts: list[Fact]) -> None:
        """Flag the facts the critic says disagree; the confidence score lowers those sentences (Phase 3)."""
        by_id = {f.id: f for f in facts}
        for c in critique.contradictions:
            hits = [by_id[i] for i in c.fact_ids if i in by_id]
            if len(hits) < 2:  # a contradiction needs two sides
                continue
            note = normalize_ws(c.note).strip() or "sources disagree"
            for f in hits:
                f.disputed = True
                self._source_fact(f).disputed = True
            if note not in self.contradictions:
                self.contradictions.append(note)
                self.trace.count("contradictions")

    def _source_fact(self, numbered: Fact) -> Fact:
        """The stored fact behind a numbered copy (numbering is rebuilt on every critic call)."""
        for entry in self.read:
            for f in entry.facts:
                if f.statement == numbered.statement and f.quote == numbered.quote:
                    return f
        return numbered

    def _new_queries(self, critique: Critique) -> list[str]:
        queries = [normalize_ws(q).strip() for q in critique.queries if q.strip()]
        fresh = [q for q in _dedupe(queries) if not any(_same(q, old) for old in self.tried_queries)]
        return fresh[:4]

    def _fallback_queries(self) -> list[str]:
        """Last resort when the critic has nothing new: search the question as the user wrote it.

        This saves runs where the planner misread the question (for example by expanding an
        abbreviation into the wrong institute) and every planned query looked for the wrong thing.
        """
        if any(_same(self.question, q) for q in self.tried_queries):
            return []
        return [self.question]

    # ---------- writer ----------

    async def _write(self) -> Report:
        facts, sources = self._numbered()
        self.trace.event("step", name="write", facts=len(facts), sources=len(sources))
        answer = await self.llm.chat(
            prompts.v3_write_messages(self.question, self.subquestions, facts, sources),
            purpose="v3_write", max_tokens=2048)
        # the writer cites fact numbers; the report cites source numbers
        answer = remap_citations(answer, {f.id: f.source_id for f in facts})
        answered = {f.subquestion for f in facts}
        not_found = [sq for i, sq in enumerate(self.subquestions, 1) if i not in answered]
        return Report(question=self.question, mode="v3", answer=answer,
                      sources=list(sources.values()), facts=facts,
                      subquestions=self.subquestions, contradictions=self.contradictions,
                      not_found=not_found,
                      models={"main": self.settings.main_model, "fast": self.settings.fast_model})

    def _numbered(self) -> tuple[list[Fact], dict[int, Source]]:
        """Number the pages that produced facts as sources 1..k and their facts as 1..m.

        Numbering happens here, not while reading, so the report never shows a source with no fact
        and the numbers the writer cites are the numbers the reader sees.
        """
        facts: list[Fact] = []
        sources: dict[int, Source] = {}
        for entry in self.read:
            if not entry.facts:
                continue
            sid = len(sources) + 1
            sources[sid] = Source(id=sid, url=entry.url, title=entry.page.title or entry.result.title,
                                  domain=domain(entry.url), published=entry.result.published,
                                  snippet=entry.result.snippet)
            for f in entry.facts:
                facts.append(f.model_copy(update={"id": len(facts) + 1, "source_id": sid}))
        return facts, sources

    def _all_facts(self) -> list[Fact]:
        return [f for entry in self.read for f in entry.facts]


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if not any(_same(item, kept) for kept in out):
            out.append(item)
    return out


def _same(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def _is_date(value: str | None) -> bool:
    return bool(value) and len(value) == 10 and value[:4].isdigit() and value[4] == "-"
