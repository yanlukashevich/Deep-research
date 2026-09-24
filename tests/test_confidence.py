"""The confidence formula: 0.5*min(sites,3)/3 + 0.5*quality - 0.3*contradiction."""
import pytest

from taro.confidence import coverage, level_of, score_report, score_sentence
from taro.schemas import Fact, Report, Sentence, Source


def _sources(*domains: str) -> dict[int, Source]:
    return {i: Source(id=i, url=f"https://{d}/page{i}", domain=d) for i, d in enumerate(domains, 1)}


def _scored(citations: list[int], *domains: str, disputed: set[int] | None = None) -> Sentence:
    sentence = Sentence(text="something happened", citations=citations)
    return score_sentence(sentence, _sources(*domains), disputed or set())


def test_two_official_sites_are_high():
    s = _scored([1, 2], "nobelprize.org", "nasa.gov")
    assert s.score == pytest.approx(0.5 * 2 / 3 + 0.5 * 1.0, abs=0.005)
    assert s.level == "high"


def test_one_news_site_is_medium():
    s = _scored([1], "reuters.com")
    assert s.score == pytest.approx(0.5 / 3 + 0.5 * 0.7, abs=0.005)
    assert s.level == "medium"


def test_one_blog_is_low():
    assert _scored([1], "habr.com").level == "low"


def test_no_citation_is_always_low():
    s = _scored([])
    assert (s.score, s.level, s.why) == (0.0, "low", "no source cited")


def test_two_pages_of_one_site_count_as_one_site():
    one = _scored([1], "reuters.com")
    two = _scored([1, 2], "reuters.com", "reuters.com")
    assert two.score == one.score  # the same newsroom twice is not a second confirmation
    assert "1 site" in two.why


def test_three_sites_reach_the_cap():
    three = _scored([1, 2, 3], "bbc.com", "reuters.com", "tass.ru")
    four = _scored([1, 2, 3, 4], "bbc.com", "reuters.com", "tass.ru", "cnn.com")
    assert three.score == four.score == pytest.approx(0.5 + 0.5 * 0.7, abs=0.005)


def test_contradiction_costs_three_tenths():
    quiet = _scored([1, 2], "nobelprize.org", "nasa.gov")
    disputed = _scored([1, 2], "nobelprize.org", "nasa.gov", disputed={2})
    assert disputed.score == pytest.approx(quiet.score - 0.3, abs=0.005)
    assert "sources disagree" in disputed.why


def test_levels():
    assert level_of(0.75) == "high"
    assert level_of(0.74) == "medium"
    assert level_of(0.5) == "medium"
    assert level_of(0.49) == "low"


# ---------- the whole report ----------


def _report(**kw) -> Report:
    base = dict(question="q", mode="v3", answer="a", sources=list(_sources("nobelprize.org", "bbc.com").values()))
    return Report(**(base | kw))


def test_report_confidence_is_average_score_times_coverage():
    report = _report(
        sentences=[Sentence(text="one", citations=[1, 2]), Sentence(text="two", citations=[1])],
        facts=[Fact(id=1, statement="s", quote="q", source_id=1, subquestion=1)],
        subquestions=["a", "b"],
    )
    score_report(report)
    average = sum(s.score for s in report.sentences) / 2
    assert report.confidence == pytest.approx(round(average * 0.5, 2), abs=0.005)  # 1 of 2 sub-questions
    assert "1 of 2 sub-questions" in report.confidence_why


def test_coverage_is_one_when_facts_carry_no_subquestion():
    report = _report(facts=[Fact(id=1, statement="s", quote="q", source_id=1)], subquestions=["a", "b"])
    assert coverage(report) == (1.0, 2)  # nothing to measure, so the sentence scores alone decide


def test_v1_without_sources_gets_zero():
    report = Report(question="q", mode="v1", answer="a",
                    sentences=[Sentence(text="the model just knows", citations=[])])
    score_report(report)
    assert report.confidence == 0.0
    assert report.sentences[0].level == "low"
    assert "nothing was searched" in report.confidence_why


def test_disputed_fact_lowers_only_sentences_citing_that_source():
    report = _report(
        sentences=[Sentence(text="one", citations=[1]), Sentence(text="two", citations=[2])],
        facts=[Fact(id=1, statement="s", quote="q", source_id=2, disputed=True)],
    )
    score_report(report)
    assert report.sentences[0].score > report.sentences[1].score
    assert "some sources disagree" in report.confidence_why


def test_v3_that_found_nothing_says_so():
    report = Report(question="q", mode="v3", answer="The sources do not say.",
                    sentences=[Sentence(text="The sources do not say.", citations=[])])
    score_report(report)
    assert report.confidence == 0.0  # a correct "not found" is still an answer with no evidence behind it
    assert "found nothing usable" in report.confidence_why
