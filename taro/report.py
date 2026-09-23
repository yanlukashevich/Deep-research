"""Run output: the step log (trace.jsonl) and the final report (report.md, report.json)."""
import json
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .schemas import Report, Sentence, Source
from .text import clean_answer, parse_citations, split_sentences

Listener = Callable[[dict[str, Any]], None]


class Trace:
    """Records every step of a run.

    Each event is appended to trace.jsonl right away (so a crashed run still leaves a log) and passed
    to an optional listener (the web UI streams these live). `stats` counts calls, tokens and cache hits.
    """

    def __init__(self, path: Path | None = None, listener: Listener | None = None):
        self.path = path
        self.listener = listener
        self.stats: Counter[str] = Counter()
        self.t0 = time.monotonic()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def event(self, kind: str, **data: Any) -> None:
        record = {"t": round(time.monotonic() - self.t0, 3), "kind": kind, **data}
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        if self.listener:
            self.listener(record)

    def count(self, key: str, n: float = 1) -> None:
        self.stats[key] += n

    def elapsed(self) -> float:
        return time.monotonic() - self.t0


def new_run_dir(runs_dir: Path, mode: str) -> Path:
    """runs/<YYYYmmdd-HHMMSS>-<mode>/, with a numeric suffix if that already exists."""
    base = runs_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{mode}"
    path, i = base, 1
    while path.exists():
        i += 1
        path = base.with_name(f"{base.name}-{i}")
    path.mkdir(parents=True)
    return path


def build_sentences(answer: str, n_sources: int) -> list[Sentence]:
    """Split the answer into sentences; keep only citations that point to a real source."""
    sentences = []
    for raw in split_sentences(answer):
        text, cites = parse_citations(raw)
        if text:
            sentences.append(Sentence(text=text, citations=[c for c in cites if 1 <= c <= n_sources]))
    return sentences


def finalize(report: Report, trace: Trace) -> Report:
    """Clean the answer, parse sentences and copy run stats into the report."""
    report.answer = clean_answer(report.answer)
    report.sentences = build_sentences(report.answer, len(report.sources))
    report.stats = {k: round(v, 2) for k, v in trace.stats.items()} | {"seconds": round(trace.elapsed(), 1)}
    return report


def to_markdown(report: Report) -> str:
    lines = [
        f"# {report.question}",
        "",
        f"*Mode: {report.mode} · models: {', '.join(f'{k}={v}' for k, v in report.models.items())}"
        f" · {report.created_at:%Y-%m-%d %H:%M}*",
        "",
        "## Answer",
        "",
        report.answer or "_(empty answer)_",
        "",
    ]
    if report.confidence is not None:
        lines += ["## Confidence", "", f"**{report.confidence:.2f}**: {report.confidence_why}", ""]
    if report.not_found:
        lines += ["## What we couldn't find", ""] + [f"- {x}" for x in report.not_found] + [""]
    if report.sources:
        lines += ["## Sources", ""] + [_source_line(s) for s in report.sources] + [""]
    s = report.stats
    lines += [
        "## Run stats",
        "",
        f"{s.get('seconds', 0):.0f} s · LLM calls: {s.get('llm_calls', 0):.0f}"
        f" ({s.get('prompt_tokens', 0):.0f} prompt + {s.get('completion_tokens', 0):.0f} completion tokens)"
        f" · searches: {s.get('searches', 0):.0f} · fetches: {s.get('fetches', 0):.0f}"
        f" · cache hits: {s.get('cache_hits', 0):.0f}",
        "",
    ]
    return "\n".join(lines)


def _source_line(s: Source) -> str:
    meta = ", ".join(x for x in (s.domain or urlsplit(s.url).netloc, s.published) if x)
    return f"{s.id}. [{s.title or s.url}]({s.url}) ({meta})"


def save_report(report: Report, run_dir: Path) -> None:
    (run_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(to_markdown(report), encoding="utf-8")
