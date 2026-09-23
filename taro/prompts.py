"""All prompts in one place."""
from datetime import date

from .schemas import Source


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
