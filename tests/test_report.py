"""Rendering the report: confidence marks in the answer and the sections of report.md."""
from taro.report import finalize, marked_answer, to_markdown
from taro.schemas import Fact, Report, Source
from taro.trace import Trace


def _report(answer: str, *, sources: int = 2, **kw) -> Report:
    domains = ["nobelprize.org", "bbc.com", "habr.com"][:sources]
    report = Report(question="q", mode="v3", answer=answer,
                    sources=[Source(id=i, url=f"https://{d}/p", title=d, domain=d)
                             for i, d in enumerate(domains, 1)], **kw)
    return finalize(report, Trace())


def test_every_sentence_gets_one_mark_in_its_place():
    report = _report("Первое [1][2]. Второе [3].\n\n- Третье [1]\n- Четвёртое")
    marked = marked_answer(report)
    assert marked.count("🟢") + marked.count("🟡") + marked.count("🔴") == len(report.sentences) == 4
    assert marked.startswith("Первое [1][2]. 🟢")  # the mark goes after the sentence it judges
    assert marked.splitlines()[2].startswith("- Третье")  # the list stays a list


def test_marks_match_the_sentence_levels():
    report = _report("Two good sources [1][2]. One weak source [3].", sources=3)
    lines = marked_answer(report).splitlines()[0]
    assert [s.level for s in report.sentences] == ["high", "low"]
    assert lines.index("🟢") < lines.index("🔴")


def test_headings_and_rules_pass_through_untouched():
    report = _report("# Heading\n\nA sentence [1].")
    marked = marked_answer(report)
    assert marked.splitlines()[0] == "# Heading"
    assert marked.splitlines()[2].endswith("🟡")


def test_answer_in_json_keeps_no_marks():
    report = _report("A sentence [1].")
    assert "🟡" not in report.answer  # the marks are only for the markdown view; the UI uses levels


def test_markdown_has_the_phase3_sections():
    report = _report("Answer [1].", not_found=["how much it cost"],
                     contradictions=["the dates differ"],
                     facts=[Fact(id=1, statement="s", quote="the exact quote", source_id=1)])
    md = to_markdown(report)
    assert "## Confidence" in md and report.confidence_why in md
    assert "## What we couldn't find" in md and "how much it cost" in md
    assert "## Where the sources disagree" in md
    assert "> the exact quote" in md  # the quote a reader can check on the page
    assert "nobelprize.org" in md


def test_sources_nobody_cites_are_flagged():
    report = _report("Only the first source is used [1].")
    md = to_markdown(report)
    uncited = [line for line in md.splitlines() if line.startswith("2. ")]
    assert uncited and "does not cite it" in uncited[0]


def test_source_quotes_are_one_line_and_not_repeated():
    long_quote = "word " * 100
    report = _report("Answer [1].", facts=[
        Fact(id=1, statement="a", quote="first line" + chr(10) + chr(10) + "second line", source_id=1),
        Fact(id=2, statement="b", quote="first line" + chr(10) + "second line", source_id=1),
        Fact(id=3, statement="c", quote=long_quote, source_id=1),
    ])
    quotes = [l for l in to_markdown(report).splitlines() if l.startswith("   > ")]
    assert quotes == ["   > first line second line", "   > " + " ".join(long_quote.split())[:300].rsplit(" ", 1)[0] + " ..."]
