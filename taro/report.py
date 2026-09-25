"""The final report: sentences with their confidence marks, rendered to report.md and report.json."""
from pathlib import Path
from urllib.parse import urlsplit

from .confidence import MARKS, level_of, score_report
from .pages import domain_quality
from .schemas import Report, Sentence, Source
from .text import clean_answer, is_prose_line, parse_citations, split_line, split_sentences
from .trace import Listener, Trace, new_run_dir

__all__ = ["Listener", "Trace", "new_run_dir", "build_sentences", "finalize", "marked_answer",
           "answer_lines", "to_markdown", "save_report"]


def build_sentences(answer: str, n_sources: int) -> list[Sentence]:
    """Split the answer into sentences; keep only citations that point to a real source."""
    sentences = []
    for raw in split_sentences(answer):
        text, cites = parse_citations(raw)
        if text:
            sentences.append(Sentence(text=text, citations=[c for c in cites if 1 <= c <= n_sources]))
    return sentences


def finalize(report: Report, trace: Trace) -> Report:
    """Clean the answer, parse sentences, score them and copy run stats into the report."""
    report.answer = clean_answer(report.answer)
    report.sentences = build_sentences(report.answer, len(report.sources))
    for source in report.sources:  # the same number the score uses, so a reader can check it
        source.quality = domain_quality(source.domain or source.url)
    score_report(report)
    report.stats = {k: round(v, 2) for k, v in trace.stats.items()} | {"seconds": round(trace.elapsed(), 1)}
    return report


def marked_answer(report: Report) -> str:
    """The answer with a 🟢🟡🔴 mark after each sentence, the rest of the markdown untouched.

    Walks the answer exactly the way `build_sentences` did, so mark i belongs to sentence i even
    when a line holds several sentences or a piece was only a stray citation.
    """
    marks = iter(MARKS.get(s.level or "low", "") for s in report.sentences)
    out: list[str] = []
    for line in report.answer.splitlines():
        if not is_prose_line(line):
            out.append(line)
            continue
        prefix, sentences = split_line(line)
        pieces = []
        for raw in sentences:
            text, _ = parse_citations(raw)
            pieces.append(f"{raw} {next(marks, '')}".strip() if text else raw)
        out.append(prefix + " ".join(pieces))
    return "\n".join(out)


def answer_lines(report: Report) -> list[dict]:
    """The answer as structured lines for the web UI.

    The same walk as `marked_answer`, but instead of a 🟢🟡🔴 mark each sentence carries its index
    in `report.sentences`, so the page can underline it and show its "why". The `[n]` markers stay
    in the text: the page turns them into the chips that show the quote.
    """
    lines: list[dict] = []
    index = 0
    for line in report.answer.splitlines():
        if not is_prose_line(line):
            lines.append({"kind": "raw", "text": line})
            continue
        prefix, sentences = split_line(line)
        parts = []
        for raw in sentences:
            text, _ = parse_citations(raw)
            parts.append({"raw": raw, "sentence": index if text else None})
            index += 1 if text else 0
        lines.append({"kind": "prose", "prefix": prefix, "parts": parts})
    return lines


def to_markdown(report: Report) -> str:
    lines = [
        f"# {report.question}",
        "",
        f"*Mode: {report.mode} · models: {', '.join(f'{k}={v}' for k, v in report.models.items())}"
        f" · {report.created_at:%Y-%m-%d %H:%M}*",
        "",
        "## Answer",
        "",
        marked_answer(report) if report.answer else "_(empty answer)_",
        "",
        "*Per sentence: 🟢 well supported · 🟡 thin support · 🔴 weak or not cited at all.*",
        "",
    ]
    if report.confidence is not None:
        mark = MARKS.get(level_of(report.confidence), "")
        lines += ["## Confidence", "",
                  f"**{report.confidence:.2f}** {mark} — {report.confidence_why}", ""]
    if report.contradictions:
        lines += ["## Where the sources disagree", ""] + [f"- {x}" for x in report.contradictions] + [""]
    if report.not_found:
        lines += ["## What we couldn't find", ""] + [f"- {x}" for x in report.not_found] + [""]
    if report.sources:
        lines += ["## Sources", ""]
        cited = {c for sent in report.sentences for c in sent.citations}
        for s in report.sources:
            lines.append(_source_line(s) + ("" if s.id in cited else " _(read, but the answer does not cite it)_"))
            # the quotes this source supplied, so a reader can open the page and check them
            lines += [f"   > {q}" for q in _quotes(report, s.id)]
        lines += [""]
    s = report.stats
    lines += [
        "## Run stats",
        "",
        f"{s.get('seconds', 0):.0f} s · LLM calls: {s.get('llm_calls', 0):.0f}"
        f" ({s.get('prompt_tokens', 0):.0f} prompt + {s.get('completion_tokens', 0):.0f} completion tokens)"
        f" · searches: {s.get('searches', 0):.0f} · fetches: {s.get('fetches', 0):.0f}",
        "",
    ]
    return "\n".join(lines)

QUOTE_CHARS = 300


def _quotes(report: Report, source_id: int, limit: int = 3) -> list[str]:
    """Up to `limit` different quotes this source supplied, each on one line so the > block holds."""
    out: list[str] = []
    for f in report.facts:
        if f.source_id != source_id:
            continue
        quote = " ".join(f.quote.split())
        if len(quote) > QUOTE_CHARS:
            quote = quote[:QUOTE_CHARS].rsplit(" ", 1)[0] + " ..."
        if quote and quote not in out:
            out.append(quote)
        if len(out) == limit:
            break
    return out


def _source_line(s: Source) -> str:
    meta = ", ".join(x for x in (s.domain or urlsplit(s.url).netloc, s.published) if x)
    return f"{s.id}. [{s.title or s.url}]({s.url}) ({meta})"


def save_report(report: Report, run_dir: Path) -> None:
    (run_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(to_markdown(report), encoding="utf-8")
