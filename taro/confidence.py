"""How much to trust each sentence of the answer, and the answer as a whole.

Per sentence, from the sources it cites:

    score = 0.5 * min(sites, 3) / 3  +  0.5 * quality  -  0.3 * contradiction

- **sites**: how many *different* websites back the sentence. Two pages of one site are one site:
  a claim repeated by one newsroom is not confirmed, it is copied.
- **quality**: the average `domain_quality` of those sites (official 1.0 ... blog/forum 0.4).
- **contradiction**: 1 when the critic marked a fact from one of those sources as disputed.

A sentence with no citation scores 0: in this agent an uncited sentence has no evidence behind it,
so it is always red, whatever it says.

Overall confidence = the average sentence score * the share of sub-questions we found facts for.
Answering every sentence well is worth little if half the question was never researched.
"""
from .pages import domain_quality
from .schemas import Report, Sentence, Source

HIGH = 0.75
MEDIUM = 0.5

SITES_FOR_FULL_MARK = 3
W_SITES = 0.5
W_QUALITY = 0.5
P_CONTRADICTION = 0.3

MARKS = {"high": "🟢", "medium": "🟡", "low": "🔴"}


def level_of(score: float) -> str:
    """🟢 high >= 0.75 · 🟡 medium >= 0.5 · 🔴 low."""
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


def score_sentence(sentence: Sentence, sources: dict[int, Source], disputed: set[int]) -> Sentence:
    """Fill `score`, `level` and `why` from the sentence's citations. Returns the same sentence."""
    cited = [sources[c] for c in sentence.citations if c in sources]
    if not cited:
        sentence.score, sentence.level = 0.0, "low"
        sentence.why = "no source cited"
        return sentence

    sites = sorted({s.domain or s.url for s in cited})
    quality = sum(domain_quality(s.domain or s.url) for s in cited) / len(cited)
    contradiction = 1.0 if any(s.id in disputed for s in cited) else 0.0

    raw = (W_SITES * min(len(sites), SITES_FOR_FULL_MARK) / SITES_FOR_FULL_MARK
           + W_QUALITY * quality
           - P_CONTRADICTION * contradiction)
    sentence.score = round(min(max(raw, 0.0), 1.0), 2)
    sentence.level = level_of(sentence.score)

    why = f"{len(sites)} site{'s' if len(sites) > 1 else ''} ({', '.join(sites[:3])}), quality {quality:.2f}"
    sentence.why = why + (", sources disagree" if contradiction else "")
    return sentence


def coverage(report: Report) -> tuple[float, int]:
    """Share of sub-questions at least one fact answers, and how many that is.

    When the report has no sub-questions (v1, v2) or no fact carries a sub-question number, there is
    nothing to measure, so coverage is 1.0 and the sentence scores alone decide.
    """
    total = len(report.subquestions)
    answered = {f.subquestion for f in report.facts if f.subquestion}
    if not total or not answered:
        return 1.0, total
    hit = len([i for i in range(1, total + 1) if i in answered])
    return hit / total, total


def score_report(report: Report) -> Report:
    """Score every sentence, then the report. Called from `report.finalize`, so every mode gets it."""
    sources = {s.id: s for s in report.sources}
    disputed = {f.source_id for f in report.facts if f.disputed}
    for sentence in report.sentences:
        score_sentence(sentence, sources, disputed)

    scores = [s.score or 0.0 for s in report.sentences]
    average = sum(scores) / len(scores) if scores else 0.0
    share, total = coverage(report)
    report.confidence = round(average * share, 2)
    report.confidence_why = _why(report, average, share, total)
    return report


def _why(report: Report, average: float, share: float, total: int) -> str:
    """One line a reader can check: what the number is made of."""
    if not report.sources:
        return ("no sources: nothing was searched, so the answer is only what the model already knew"
                if report.mode == "v1" else
                "no sources: the search found nothing usable, so no sentence is backed by a page")
    cited = sum(1 for s in report.sentences if s.citations)
    used = {c for s in report.sentences for c in s.citations}
    sites = len({s.domain or s.url for s in report.sources if s.id in used})
    parts = [f"{cited} of {len(report.sentences)} sentences cite a source",
             f"{sites} different site{'s' if sites != 1 else ''} cited",
             f"average sentence score {average:.2f}"]
    if share < 1.0:
        parts.append(f"only {round(share * total)} of {total} sub-questions answered (x{share:.2f})")
    if any(f.disputed for f in report.facts):
        parts.append("some sources disagree")
    return "; ".join(parts)
