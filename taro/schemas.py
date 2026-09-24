"""Data shapes shared by all versions of the agent."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["v1", "v2", "v3"]


class SearchResult(BaseModel):
    """One hit from Keenable `search_web_pages`."""
    url: str
    title: str = ""
    published: str | None = None
    acquired: str | None = None
    snippet: str = ""


class Page(BaseModel):
    """A page from Keenable `fetch_page_content` (markdown)."""
    url: str
    title: str = ""
    text: str


class Source(BaseModel):
    """A web page the answer may cite as [id]."""
    id: int
    url: str
    title: str = ""
    domain: str = ""
    published: str | None = None
    snippet: str = ""  # the text the writer saw (v2)


class Fact(BaseModel):
    """A fact extracted from a source, backed by an exact quote (v3)."""
    id: int
    statement: str
    quote: str
    source_id: int
    subquestion: int | None = None
    quote_score: float | None = None  # how well the quote matched the page text
    disputed: bool = False  # the critic found a source saying the opposite


class Sentence(BaseModel):
    """One sentence of the answer with the sources it cites."""
    text: str  # without the [n] markers
    citations: list[int] = Field(default_factory=list)  # Source.id values
    score: float | None = None  # confidence, filled in Phase 3
    level: Literal["high", "medium", "low"] | None = None
    why: str = ""


class Report(BaseModel):
    question: str
    mode: Mode
    answer: str  # markdown with [n] citations
    sentences: list[Sentence] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    confidence: float | None = None
    confidence_why: str = ""
    not_found: list[str] = Field(default_factory=list)
    subquestions: list[str] = Field(default_factory=list)  # v3 research plan
    contradictions: list[str] = Field(default_factory=list)  # what the critic saw disagreeing
    models: dict[str, str] = Field(default_factory=dict)
    stats: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


# ---------- what the LLM returns in v3 (validated by LLM.json) ----------


class PlannedSubQuestion(BaseModel):
    """One sub-question with the searches that should answer it. Ids come from the list order."""
    question: str
    queries: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    subquestions: list[PlannedSubQuestion] = Field(default_factory=list)
    published_after: str | None = None  # YYYY-MM-DD, set only for questions about recent events


class ExtractedFact(BaseModel):
    statement: str
    quote: str
    subquestion: int | None = None


class Extraction(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)


class Contradiction(BaseModel):
    fact_ids: list[int] = Field(default_factory=list)
    note: str = ""


class Critique(BaseModel):
    """The critic's verdict after a round of reading."""
    enough: bool = False
    missing: list[int] = Field(default_factory=list)  # sub-question ids still without facts
    contradictions: list[Contradiction] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)  # searches to fill the gaps
    note: str = ""
