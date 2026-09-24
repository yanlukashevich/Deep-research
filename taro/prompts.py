"""All prompts in one place."""
from datetime import date

from .schemas import Fact, Source


def _today() -> str:
    return date.today().isoformat()


# ---------- v1: bare LLM (baseline, no search) ----------

V1_SYSTEM = """You are a research assistant. Answer the user's question from your own knowledge.
Today's date is {today}.
- Answer in the same language as the question.
- Be concise: 1-3 short paragraphs of plain prose, no tables, no headings.
- If you are not sure, or the question is about events after your training data, say so plainly."""


def v1_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": V1_SYSTEM.format(today=_today())},
        {"role": "user", "content": question},
    ]


# ---------- v2: simple RAG (one search, answer from the snippets) ----------

V2_SYSTEM = """You answer a research question using ONLY the numbered search results given by the user.
Today's date is {today}.
Rules:
- Every sentence that states a fact ends with the numbers of the results that support it, e.g. "... in 1994 [2]." or "... [1][3]."
- Use only information that is present in the results. Do not add facts from your own knowledge, even if you are sure.
- If the results do not answer the question (or answer only part of it), say so explicitly, e.g. "The sources found do not say ...".
- If results disagree, say so and cite each side.
- Answer in the same language as the question.
- Be concise: 1-3 short paragraphs of plain prose (a short bulleted list is fine), no tables, no headings,
  no list of sources at the end, no other citation format than [n]."""


def format_sources(sources: list[Source]) -> str:
    if not sources:
        return "(no results)"
    blocks = []
    for s in sources:
        meta = ", ".join(x for x in (s.domain, f"published {s.published}" if s.published else "") if x)
        blocks.append(f"[{s.id}] {s.title} ({meta})\n{s.snippet}")
    return "\n\n".join(blocks)


def v2_messages(question: str, sources: list[Source]) -> list[dict[str, str]]:
    user = f"Question: {question}\n\nSearch results:\n\n{format_sources(sources)}\n\nQuestion (again): {question}"
    return [
        {"role": "system", "content": V2_SYSTEM.format(today=_today())},
        {"role": "user", "content": user},
    ]


# ---------- v3: research agent ----------
# The JSON shapes live in their own constants: they contain braces and must not go through .format().

V3_PLAN_SYSTEM = """You plan web research for a question. Today's date is {today}.

Split the question into 3-5 sub-questions: the things a reader must know before the question counts as answered.
Cover the fact that is actually asked, the dates or numbers behind it, the context or cause, and anything likely
to be disputed. Do not invent sub-questions about matters the question does not raise.

For each sub-question write 1-2 search queries. A query is a short DESCRIPTION OF THE IDEAL PAGE in natural
language, not a pile of keywords: "official announcement naming the 2025 Nobel Physics laureates and their
discovery" beats "nobel physics 2025".
- Name the subject in every query: each search runs on its own and knows nothing about the question.
- Keep names and abbreviations exactly as the question writes them. NEVER guess what an abbreviation stands for.
  If you are certain of the full name, you may add one query that uses it, but keep the question's own wording too.
- Write the queries in the language of the question, plus English ones if the question is in another language.
  Do not use a third language.

If the question is about recent or still unfolding events, set "published_after" to a YYYY-MM-DD date a few
months back, so old pages are filtered out. Otherwise leave it null."""

V3_PLAN_FORMAT = """Return JSON:
{"subquestions": [{"question": "...", "queries": ["...", "..."]}], "published_after": null}"""


def v3_plan_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": f"{V3_PLAN_SYSTEM.format(today=_today())}\n\n{V3_PLAN_FORMAT}"},
        {"role": "user", "content": f"Question: {question}"},
    ]


V3_EXTRACT_SYSTEM = """You pull facts out of one web page for a research team. Today's date is {today}.

The user gives the research question, the sub-questions, and the text of a single page.
Return the facts from that page which help answer those sub-questions, at most {max_facts} of them.

Each fact has:
- "statement": one self-contained sentence in the language of the research question. Spell out names, places,
  dates and numbers; never write "he", "the company" or "last year".
- "quote": the words from the page that prove the statement, copied CHARACTER BY CHARACTER out of the page text,
  between 5 and 40 words, with no ellipses and no edits of any kind. An automatic check searches for the quote
  in the page and throws the fact away if it is not there, so never reword, translate or stitch it together.
- "subquestion": the number of the sub-question it answers, or null if it fits none of them.

Rules:
- Use the page text only. Add nothing from your own knowledge, even if you are certain of it.
- Ignore menus, adverts, cookie notices, comments and "related articles".
- If the page holds nothing useful, return an empty list. That is a correct answer, not a failure."""

V3_EXTRACT_FORMAT = """Return JSON:
{"facts": [{"statement": "...", "quote": "...", "subquestion": 1}]}"""


def v3_extract_messages(question: str, subquestions: list[str], source: Source, text: str,
                        max_facts: int) -> list[dict[str, str]]:
    meta = ", ".join(x for x in (source.domain, f"published {source.published}" if source.published else "") if x)
    user = (f"Research question: {question}\n\n"
            f"Sub-questions:\n{format_subquestions(subquestions)}\n\n"
            f"Page: {source.title or source.url} ({meta})\nURL: {source.url}\n\n"
            f"--- page text ---\n{text}\n--- end of page text ---")
    return [
        {"role": "system", "content": f"{V3_EXTRACT_SYSTEM.format(today=_today(), max_facts=max_facts)}\n\n"
                                      f"{V3_EXTRACT_FORMAT}"},
        {"role": "user", "content": user},
    ]


V3_CRITIC_SYSTEM = """You decide whether a research team can already answer its question. Today's date is {today}.

You get the question, the numbered sub-questions, the facts collected so far (each with the website it came
from) and the searches already tried. Judge only what is written in the facts.

- "enough": true when the question itself can be answered from these facts without guessing, and every
  sub-question that really matters has at least one fact from a credible site. Be strict about the main
  question, forgiving about side details.
- "missing": numbers of the sub-questions that still have no usable fact.
- "contradictions": groups of fact numbers that cannot all be true at once - a different date, name, number or
  order of events for the same thing - each with a one-line note. The same fact in different words is NOT a
  contradiction, and neither are two facts about two different things.
- "queries": when "enough" is false, 2-4 new searches that would close the gaps, again written as descriptions
  of the ideal page, and different from the searches already tried. If nothing new is worth trying, return an
  empty list and set "enough" to true.
- "note": one sentence about what is still weak."""

V3_CRITIC_FORMAT = """Return JSON:
{"enough": false, "missing": [2], "contradictions": [{"fact_ids": [3, 7], "note": "..."}],
 "queries": ["..."], "note": "..."}"""


def v3_critic_messages(question: str, subquestions: list[str], facts: list[Fact], sources: dict[int, Source],
                       tried: list[str], round_no: int, rounds_left: int) -> list[dict[str, str]]:
    user = (f"Question: {question}\n\n"
            f"Sub-questions:\n{format_subquestions(subquestions)}\n\n"
            f"Facts collected ({len(facts)}):\n{format_facts(facts, sources, with_quotes=False)}\n\n"
            f"Searches already tried:\n" + "\n".join(f"- {q}" for q in tried) +
            f"\n\nThis was round {round_no}; {rounds_left} more round(s) of searching are possible.")
    return [
        {"role": "system", "content": f"{V3_CRITIC_SYSTEM.format(today=_today())}\n\n{V3_CRITIC_FORMAT}"},
        {"role": "user", "content": user},
    ]


V3_WRITE_SYSTEM = """You write the final answer of a research report. Today's date is {today}.

You get the question, the sub-questions the team worked on, and a numbered list of FACTS, each backed by an
exact quote from a web page. Write the answer from those facts and nothing else.

- Every sentence that states a fact ends with the numbers of the facts that support it:
  "... was founded in 1994 [2]." or "... three researchers shared the prize [1][3]."
- Add no information that is not in the facts, even if you are sure of it. No fact, no sentence.
- Where the facts do not answer part of the question, say so plainly: "The sources found do not say ...".
- Where facts disagree, give both versions with their numbers and say that the sources disagree.
- Answer in the language of the question: 1-4 short paragraphs of plain prose (a short bulleted list is fine).
- No headings, no tables, no list of sources at the end, and no citation format other than [n]."""


def v3_write_messages(question: str, subquestions: list[str], facts: list[Fact],
                      sources: dict[int, Source]) -> list[dict[str, str]]:
    user = (f"Question: {question}\n\n"
            f"Sub-questions:\n{format_subquestions(subquestions)}\n\n"
            f"Facts:\n{format_facts(facts, sources)}\n\n"
            f"Question (again): {question}")
    return [
        {"role": "system", "content": V3_WRITE_SYSTEM.format(today=_today())},
        {"role": "user", "content": user},
    ]


def format_subquestions(subquestions: list[str]) -> str:
    return "\n".join(f"{i}. {q}" for i, q in enumerate(subquestions, 1)) or "(none)"


def format_facts(facts: list[Fact], sources: dict[int, Source], *, with_quotes: bool = True) -> str:
    """The numbered fact list the critic and the writer see. Numbers are what the writer cites."""
    blocks = []
    for f in facts:
        s = sources.get(f.source_id)
        meta = ", ".join(x for x in ((s.domain if s else ""), (s.published if s and s.published else "")) if x)
        lines = [f"[{f.id}] {f.statement}"]
        if with_quotes:
            lines.append(f'    quote: "{f.quote}"')
        lines.append(f"    source: {meta or (s.url if s else '?')}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks) or "(no facts were found)"
