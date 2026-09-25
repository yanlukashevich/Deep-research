"""E4 in detail: what kind of quote does the check actually throw out?

`results.md` counts the rejections. This asks the more useful question: was the rejected quote
invented, or was it real text the model re-typed badly? The two are different problems - one is a
model that makes things up, the other is a model that cannot copy - and only the first is what the
check was built for.

For every `quote_rejected` event in the run folders, the page is fetched again (from the disk cache,
so this costs nothing) and the quote is scored against it with the agent's own `verify_quote`:

    >= 85  the check should have accepted it (a bug in the threshold or in the page we re-fetched)
    70-85  real text of the page, re-typed with edits: joined fragments, inserted "...", changed dashes
    50-70  a loose paraphrase, or a line assembled out of a table
    < 50   not on the page at all: the model made it up

    python -m eval.quote_audit            # writes eval/results/quote_audit.md
"""
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from taro.config import get_settings
from taro.pages import MIN_QUOTE_CHARS, verify_quote
from taro.search import Search
from taro.trace import Trace

from .schemas import RESULTS

RUNS = get_settings().runs_dir
BANDS = [(85.0, "the check should have accepted it"),
         (70.0, "real text of the page, re-typed with edits"),
         (50.0, "a loose paraphrase or a line built out of a table"),
         (0.0, "not on the page at all: invented")]


def rejected_quotes(runs: Path = RUNS) -> list[tuple[str, str, str, str]]:
    """(run, url, quote, statement) for every quote the check threw out, read back from the traces."""
    out = []
    for run in sorted(runs.glob("*-v3*")):
        trace = run / "trace.jsonl"
        if not trace.exists():
            continue
        for line in trace.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("kind") == "quote_rejected":
                out.append((run.name, event.get("url", ""), event.get("quote", ""),
                            event.get("statement", "")))
    return out


def band(score: float) -> str:
    return next(name for floor, name in BANDS if score >= floor)


async def audit() -> str:
    items = rejected_quotes()
    if not items:
        return "# Rejected quotes\n\nNo run folders with rejected quotes were found.\n"
    settings = get_settings()
    counts: Counter[str] = Counter()
    examples: dict[str, list[tuple[float, str, str, str]]] = {}
    pages: dict[str, str] = {}
    async with Search(settings, Trace(), session_id="quote_audit") as search:
        for _, url, _, _ in items:
            if url in pages:
                continue
            try:
                page = await search.fetch(url, max_chars=settings.v3_page_chars)
                pages[url] = page.text if page else ""
            except Exception:
                pages[url] = ""
        for _, url, quote, statement in items:
            text = pages.get(url, "")
            if not text:
                name, score = "the page could not be read again", -1.0
            elif len(" ".join(quote.split())) < MIN_QUOTE_CHARS:
                name, score = f"too short to be evidence (under {MIN_QUOTE_CHARS} characters)", 100.0
            else:
                score = verify_quote(quote, text, min_score=0.0)
                name = band(score)
            counts[name] += 1
            examples.setdefault(name, []).append((round(score, 1), url, quote, statement))

    total = sum(counts.values())
    lines = ["# What the quote check threw out", "",
             f"{total} rejected quotes from {len({i[0] for i in items})} runs, each scored again against "
             "the page it claimed to come from. Written by `python -m eval.quote_audit`.", "",
             "| what it was | quotes | share |", "|---|---|---|"]
    for name, n in counts.most_common():
        lines.append(f"| {name} | {n} | {100 * n / total:.0f}% |")
    lines += [""]
    for name, _ in counts.most_common():
        lines += [f"## {name}", ""]
        for score, url, quote, statement in examples[name][:4]:
            lines += [f"- score {score} · {url}",
                      f'  - what the model claimed to be quoting: "{" ".join(quote.split())[:300]}"',
                      f"  - the fact it was backing: {statement}", ""]
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    text = asyncio.run(audit())
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "quote_audit.md").write_text(text, encoding="utf-8")
    print(text.split("## ")[0])
    print(f"-> {RESULTS / 'quote_audit.md'}")


if __name__ == "__main__":
    main()
