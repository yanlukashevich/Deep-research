"""The LLM judge.

Three separate questions, each its own call, because mixing them makes the model lazy:

1. `judge_answer`  - is the answer right, compared to the gold answer written by hand?
2. `judge_citations` - does the evidence a sentence cites really say what the sentence says?
3. `self_confidence` - "how sure are you?", asked of the model itself. This is the baseline that
   experiment E3 compares our confidence formula against, so it must see the answer and nothing else:
   no sources, no quotes, no score.

The judge is the main model. It grades an answer written by the same model, which is a known weakness
of LLM judges; the gold answer and the key points are there to give it something outside the answer to
compare against, and `judge_sample.md` exists so a human can check a slice of its decisions by hand.
"""
from pydantic import BaseModel, Field

from taro.llm import LLM
from taro.text import parse_citations

from .schemas import CitationVerdict, Item, Judgement, Record

MAX_SENTENCES = 14        # per report, so one citation call stays small
MAX_QUOTES_PER_SOURCE = 3
QUOTE_CHARS = 400


# ---------- 1. is the answer right? ----------

ANSWER_SYSTEM = """You grade the answers of a question-answering system. You see the question, a reference \
answer written by a human, and the system's answer. Decide how the system's answer compares to the reference.

Verdicts:
- "correct": everything the reference requires is there, and nothing in the answer contradicts the reference.
- "partial": part of what the reference requires is there, the rest is missing or wrong.
- "wrong": the answer contradicts the reference, or answers a question that has no answer.
- "no_answer": the system says it could not find out or does not know, and states nothing false.

Rules:
- Grade facts, not style. Extra correct detail is fine; the answer may be longer than the reference.
- Accept equivalent wording, rounding and transliteration ("26" = "twenty-six", "Hammarskjold" = "Hammarskjöld").
- The answer may be in any language, and citation markers like [1][2] are not mistakes.
- Set "refused" to true when the answer explicitly says it could not find the information, or says that what \
the question assumes did not happen.
- "covered" lists the key points from the reference that the answer really contains, copied exactly as given.

Return only JSON: {"verdict": "...", "refused": true|false, "covered": ["..."], "reason": "one sentence"}"""

FALSE_PREMISE_NOTE = """This question is built on something that never happened. The reference says so.
- "correct" only if the answer states that the premise is false (no such person, no such prize, no such event).
- "no_answer" if the answer only says it found nothing, without saying the premise is false.
- "wrong" if the answer plays along and gives a name, a date or an explanation as if the premise were true."""

OPEN_NOTE = """This is an open question with no single right answer. Grade by the key points:
- "correct" if the answer covers most of the key points (more than half) and contradicts none of them.
- "partial" if it covers a few.
- "wrong" if it covers almost none, or states something plainly false about the topic."""


class _Answer(BaseModel):
    verdict: str = "wrong"
    refused: bool = False
    covered: list[str] = Field(default_factory=list)
    reason: str = ""


VERDICTS = {"correct", "partial", "wrong", "no_answer"}


async def judge_answer(llm: LLM, item: Item, answer: str) -> Judgement:
    """Compare one answer to the gold answer. An empty answer is 'wrong' without spending a call."""
    if not answer.strip():
        return Judgement(verdict="wrong", reason="empty answer")
    note = {"false_premise": FALSE_PREMISE_NOTE, "open": OPEN_NOTE}.get(item.type, "")
    points = "\n".join(f"- {p}" for p in item.key_points) or "- (none listed)"
    parts = [f"QUESTION:\n{item.question}",
             f"REFERENCE ANSWER:\n{item.gold}",
             f"KEY POINTS:\n{points}"]
    if note:
        parts.append(note)
    parts.append(f"SYSTEM ANSWER:\n{answer.strip()}")
    user = "\n\n".join(parts)
    raw = await llm.json([{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": user}],
                         _Answer, purpose="judge_answer", max_tokens=1024)
    verdict = raw.verdict if raw.verdict in VERDICTS else "wrong"
    covered = [p for p in raw.covered if p in item.key_points]
    return Judgement(verdict=verdict, refused=bool(raw.refused), covered=covered, reason=raw.reason.strip())


# ---------- 2. does the evidence support the sentence? ----------

CITATION_SYSTEM = """You check citations. Each item is one sentence from an answer plus the evidence it \
cites: quotes taken from the web pages the sentence points to.

For every item say whether the evidence supports the sentence:
- "yes": the evidence states what the sentence claims (wording may differ).
- "partial": the evidence supports part of the claim; the rest is not in the evidence.
- "no": the evidence does not support the claim, or is about something else.

Judge ONLY against the evidence shown. Whether the sentence is true in the real world does not matter here: \
a true sentence with unrelated evidence is "no". Ignore citation markers like [1][2] inside the sentence.

Return only JSON: {"verdicts": [{"i": 1, "supported": "yes|partial|no", "reason": "a few words"}, ...]} \
with one entry per item, keeping the item numbers."""


class _CitationVerdict(BaseModel):
    i: int
    supported: str = "no"
    reason: str = ""


class _Citations(BaseModel):
    verdicts: list[_CitationVerdict] = Field(default_factory=list)


SUPPORTED = {"yes", "partial", "no"}


def citation_items(record: Record) -> list[tuple[int, str, list[str]]]:
    """(sentence index, sentence text, evidence) for every sentence that cites a source.

    The evidence is what the agent itself had: in v3 the verified quotes of the cited sources, in v2 the
    search snippet the writer saw. A sentence whose sources supplied neither is still checked, with an
    empty evidence list, and the judge will call it unsupported - which is the honest verdict.
    """
    items = []
    for i, sentence in enumerate(record.sentences):
        if not sentence.citations:
            continue
        evidence: list[str] = []
        for cite in sentence.citations:
            for quote in record.quotes.get(str(cite), [])[:MAX_QUOTES_PER_SOURCE]:
                quote = " ".join(quote.split())[:QUOTE_CHARS]
                if quote and quote not in evidence:
                    evidence.append(quote)
        text, _ = parse_citations(sentence.text)
        items.append((i, text or sentence.text, evidence))
    return items[:MAX_SENTENCES]


async def judge_citations(llm: LLM, record: Record) -> list[CitationVerdict]:
    """One call for the whole report: every cited sentence with the quotes of its sources."""
    items = citation_items(record)
    if not items:
        return []
    blocks = []
    for n, (_, text, evidence) in enumerate(items, 1):
        quotes = "\n".join(f'  - "{q}"' for q in evidence) or "  - (the cited sources supplied no quote)"
        blocks.append(f"ITEM {n}\nSENTENCE: {text}\nEVIDENCE:\n{quotes}")
    user = f"QUESTION: {record.question}\n\n" + "\n\n".join(blocks)
    raw = await llm.json([{"role": "system", "content": CITATION_SYSTEM}, {"role": "user", "content": user}],
                         _Citations, purpose="judge_citations", max_tokens=2048)
    by_number = {v.i: v for v in raw.verdicts}
    out = []
    for n, (index, _, _) in enumerate(items, 1):
        v = by_number.get(n)
        supported = v.supported if v and v.supported in SUPPORTED else "no"
        reason = v.reason.strip() if v else "the judge returned no verdict for this sentence"
        out.append(CitationVerdict(index=index, supported=supported, reason=reason))
    return out


# ---------- 3. "how sure are you?" (the E3 baseline) ----------

SELF_SYSTEM = """You are shown a question and an answer. Say how confident you are that the answer is \
factually correct, as a number between 0 and 1: 0 means certainly wrong, 1 means certainly correct.
Judge from your own knowledge. You cannot look anything up. If the answer is about events you cannot \
know about, or about something you are unsure of, say so with a low number.
Return only JSON: {"confidence": 0.0, "why": "one short sentence"}"""


class _SelfConfidence(BaseModel):
    confidence: float = 0.0
    why: str = ""


async def self_confidence(llm: LLM, question: str, answer: str) -> tuple[float, str]:
    """What the model says about its own answer, with no sources and no score in front of it."""
    if not answer.strip():
        return 0.0, "empty answer"
    text, _ = parse_citations(" ".join(answer.split()))
    raw = await llm.json(
        [{"role": "system", "content": SELF_SYSTEM},
         {"role": "user", "content": f"QUESTION:\n{question}\n\nANSWER:\n{text}"}],
        _SelfConfidence, purpose="judge_self_confidence", max_tokens=512)
    return round(min(max(raw.confidence, 0.0), 1.0), 2), raw.why.strip()
