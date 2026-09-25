"""Running the question set: one question in one configuration, then the judge, then save.

Every finished record is written to `eval/results/records/` straight away. The evaluation is a
long sequence of network calls against a shared LLM service, so it has to survive being stopped:
re-running skips everything already on disk unless `--force` is given.
"""
import asyncio
import traceback
from dataclasses import dataclass
from typing import Any

from taro import runner
from taro.config import get_settings
from taro.llm import LLM
from taro.report import answer_lines  # noqa: F401  (kept importable for scripts inspecting a run)
from taro.schemas import Mode, Report
from taro.trace import Trace

from .dataset import load_record, save_record
from .judge import judge_answer, judge_citations, self_confidence
from .schemas import Item, Record, SentenceRec


@dataclass(frozen=True)
class Config:
    """One column of a results table: a mode, optionally with changed settings."""
    label: str
    mode: Mode
    overrides: dict[str, Any] | None = None
    note: str = ""


V1 = Config("v1", "v1", note="bare LLM, no search")
V2 = Config("v2", "v2", note="one search, answer from the snippets")
V3 = Config("v3", "v3", note="research agent, up to 3 rounds")
V3_R1 = Config("v3-r1", "v3", {"v3_max_rounds": 1}, "research agent, one round, no critic")
V3_R2 = Config("v3-r2", "v3", {"v3_max_rounds": 2}, "research agent, two rounds")


SNIPPET_CHARS = 700


def evidence_of(report: Report) -> dict[str, list[str]]:
    """What each source actually gave the writer, keyed by source id.

    In v3 that is the verified quotes. v2 has no facts: the writer saw the search snippet, so the
    snippet is the evidence its citations have to be judged against. Judging v2 against nothing
    would score it 0% by construction and prove only that v2 does not extract quotes.
    """
    quotes: dict[str, list[str]] = {}
    for fact in report.facts:
        quotes.setdefault(str(fact.source_id), []).append(fact.quote)
    for source in report.sources:
        if str(source.id) not in quotes and source.snippet.strip():
            quotes[str(source.id)] = [source.snippet.strip()[:SNIPPET_CHARS]]
    return quotes


def to_record(item: Item, config: Config, report: Report, run_dir: str) -> Record:
    """Flatten a report into a record: enough to score it and to read it, without the run folder."""
    quotes = evidence_of(report)
    return Record(
        qid=item.id, label=config.label, mode=config.mode, question=item.question,
        type=item.type, lang=item.lang,
        answer=report.answer,
        sentences=[SentenceRec(text=s.text, citations=s.citations, score=s.score, level=s.level)
                   for s in report.sentences],
        domains=[s.domain or s.url for s in report.sources],
        quotes=quotes,
        confidence=report.confidence, confidence_why=report.confidence_why,
        not_found=report.not_found, contradictions=report.contradictions,
        stats=report.stats, run_dir=run_dir,
    )


async def judge_record(record: Record, item: Item, llm: LLM) -> Record:
    """Fill in the three judge fields. A failing judge call must not lose the run it graded."""
    try:
        record.judgement = await judge_answer(llm, item, record.answer)
    except Exception as e:
        record.error = (record.error + f" | judge_answer failed: {e!r}").strip(" |")
    try:
        record.citations = await judge_citations(llm, record)
    except Exception as e:
        record.error = (record.error + f" | judge_citations failed: {e!r}").strip(" |")
    try:
        record.self_confidence, record.self_confidence_why = await self_confidence(
            llm, record.question, record.answer)
    except Exception as e:
        record.error = (record.error + f" | self_confidence failed: {e!r}").strip(" |")
    return record


async def run_item(item: Item, config: Config, *, use_cache: bool = True, force: bool = False) -> Record:
    """One question in one configuration: run it, judge it, save it. Returns the stored record."""
    if not force:
        if (existing := load_record(item.id, config.label)) and existing.ok and existing.judgement:
            return existing
    try:
        report, run_dir = await runner.run(item.question, config.mode, use_cache=use_cache,
                                           overrides=config.overrides, label=config.label)
        record = to_record(item, config, report, str(run_dir))
    except Exception as e:
        traceback.print_exc()
        record = Record(qid=item.id, label=config.label, mode=config.mode, question=item.question,
                        type=item.type, lang=item.lang, error=repr(e))
        save_record(record)
        return record

    # the judge runs on its own trace: its tokens are evaluation cost, not the agent's
    record = await judge_record(record, item, LLM(get_settings(), Trace()))
    save_record(record)
    return record


async def run_all(items: list[Item], configs: list[Config], *, concurrency: int = 2,
                  use_cache: bool = True, force: bool = False,
                  on_done=None) -> list[Record]:
    """Run every (question, configuration) pair, `concurrency` at a time.

    The limit is on whole runs, not on calls: the LLM semaphore inside the agent is shared by
    everything in the process, so two research runs at once already keep the service busy.
    """
    jobs = [(item, config) for config in configs for item in items]
    gate = asyncio.Semaphore(concurrency)
    done = 0
    lock = asyncio.Lock()

    async def one(item: Item, config: Config) -> Record:
        nonlocal done
        async with gate:
            record = await run_item(item, config, use_cache=use_cache, force=force)
        async with lock:
            done += 1
            if on_done:
                on_done(done, len(jobs), record)
        return record

    return list(await asyncio.gather(*(one(i, c) for i, c in jobs)))
