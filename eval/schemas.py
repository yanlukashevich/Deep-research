"""What the evaluation stores: one question, one run of it, and the judge's verdicts.

A `Record` is written to disk as soon as its run finishes, so an interrupted evaluation resumes
instead of paying for the same runs twice.
"""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from taro.schemas import Mode

QType = Literal["multihop", "fresh", "open", "false_premise"]
Verdict = Literal["correct", "partial", "wrong", "no_answer"]
Supported = Literal["yes", "partial", "no"]

ROOT = Path(__file__).resolve().parent
QUESTIONS = ROOT / "questions.jsonl"
RESULTS = ROOT / "results"
RECORDS = RESULTS / "records"


class Item(BaseModel):
    """One test question with the answer a well-informed person would give."""
    id: str
    type: QType
    lang: str
    question: str
    gold: str
    key_points: list[str] = Field(default_factory=list)
    expect: Literal["answer", "refuse"] = "answer"
    sources: list[str] = Field(default_factory=list)  # where the gold answer was checked by hand


class Judgement(BaseModel):
    """The judge on the whole answer."""
    verdict: Verdict
    refused: bool = False  # the answer says it could not find out, or that the premise is false
    covered: list[str] = Field(default_factory=list)  # key points the answer got
    reason: str = ""


class CitationVerdict(BaseModel):
    """The judge on one sentence against the quotes of the sources it cites."""
    index: int  # into Record.sentences
    supported: Supported
    reason: str = ""


class SentenceRec(BaseModel):
    """A sentence of the answer, as the report scored it."""
    text: str
    citations: list[int] = Field(default_factory=list)
    score: float | None = None
    level: str | None = None


class Record(BaseModel):
    """One question run in one configuration, plus everything the judge said about it."""
    qid: str
    label: str  # "v1", "v2", "v3", "v3-r1", "v3-r2": the configuration, not just the mode
    mode: Mode
    question: str
    type: QType
    lang: str

    answer: str = ""
    sentences: list[SentenceRec] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)  # one entry per source, in source order
    quotes: dict[str, list[str]] = Field(default_factory=dict)  # source id (as str) -> its quotes
    confidence: float | None = None
    confidence_why: str = ""
    not_found: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    stats: dict[str, float] = Field(default_factory=dict)
    run_dir: str = ""
    error: str = ""

    judgement: Judgement | None = None
    citations: list[CitationVerdict] = Field(default_factory=list)
    self_confidence: float | None = None  # E3: the model's own "how sure are you?"
    self_confidence_why: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def n_sites(self) -> int:
        return len(set(self.domains))

    def path(self) -> Path:
        return RECORDS / f"{self.label}-{self.qid}.json"
