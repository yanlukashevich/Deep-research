from collections import Counter

from taro.pages import domain_quality, is_junk, relevant_passages, select_pages, verify_quote
from taro.schemas import SearchResult


def test_domain_quality_buckets():
    assert domain_quality("https://www.nobelprize.org/prizes/physics/2025/") == 1.0
    assert domain_quality("https://arxiv.org/abs/2501.00001") == 1.0
    assert domain_quality("https://www.mit.edu/about") == 1.0
    assert domain_quality("https://ru.wikipedia.org/wiki/ИСП_РАН") == 0.8
    assert domain_quality("https://tass.ru/nauka/123") == 0.7
    assert domain_quality("https://some-company.io/news") == 0.5
    assert domain_quality("https://habr.com/ru/post/1") == 0.4
    assert domain_quality("reddit.com") == 0.4


def test_is_junk_skips_vacancies_and_trackers():
    assert is_junk("https://hh.ru/vacancy/12345")
    assert is_junk("https://link.cfr.org/click/abc/def")
    assert is_junk("https://example.com/go/out/?redirect=https://x.ru")
    assert not is_junk("https://www.nobelprize.org/prizes/physics/2025/")


def _r(url: str) -> SearchResult:
    return SearchResult(url=url, title=url, snippet="text")


def test_select_pages_prefers_good_sites_and_caps_one_domain():
    results = [
        _r("https://habr.com/a"), _r("https://habr.com/b"), _r("https://habr.com/c"),
        _r("https://ru.wikipedia.org/wiki/X"),
        _r("https://www.nobelprize.org/prizes/physics/2025/"),
        _r("https://hh.ru/vacancy/1"),  # junk, never read
    ]
    picked = select_pages(results, seen=set(), limit=4, per_domain=2)
    assert [p.url for p in picked] == [
        "https://www.nobelprize.org/prizes/physics/2025/",
        "https://ru.wikipedia.org/wiki/X",
        "https://habr.com/a",
        "https://habr.com/b",
    ]


def test_select_pages_skips_duplicates_across_rounds():
    seen: set[str] = set()
    counts: Counter = Counter()
    first = select_pages([_r("https://tass.ru/a"), _r("https://tass.ru/b")], seen=seen, limit=2,
                         per_domain=2, domain_counts=counts)
    assert len(first) == 2
    # the same pages (one with tracking parameters and a trailing slash) and one new page from the same site
    again = select_pages([_r("https://tass.ru/a/?utm_source=x"), _r("https://www.tass.ru/b"),
                          _r("https://tass.ru/c")], seen=seen, limit=2, per_domain=2, domain_counts=counts)
    assert again == []  # duplicates are gone and the per-domain cap is already used up


def test_relevant_passages_keeps_the_lead_and_the_matching_part():
    # paragraphs long enough to stay separate blocks (blocks are built up to roughly 700 characters)
    lead = "The institute was founded in 1994 in Moscow. " * 20
    noise = "Cookie notice and newsletter signup text about unrelated products. " * 20
    hit = "Arutyun Avetisyan was appointed director of the institute in 2015. " * 20
    text = "\n\n".join([lead, noise, hit])
    kept = relevant_passages(text, ["Who became director of the institute?"], max_chars=2400)
    assert "founded in 1994" in kept  # the start of the page is always kept
    assert "appointed director" in kept
    assert "Cookie notice" not in kept
    assert len(kept) < len(text)


PAGE = ("Title: Prize page\n\nThe Royal Swedish Academy of Sciences has decided to award the 2025 Nobel Prize "
        "in Physics to John Clarke, Michel H. Devoret and John M. Martinis.\n\n"
        "The discovery concerned macroscopic quantum mechanical tunnelling in an electric circuit.")


def test_verify_quote_accepts_a_real_quote_even_with_odd_spacing():
    quote = "award the 2025 Nobel  Prize in Physics to John Clarke, Michel H. Devoret"
    assert verify_quote(quote, PAGE) >= 85


def test_verify_quote_accepts_typographic_punctuation():
    assert verify_quote("macroscopic quantum mechanical tunnelling in an electric circuit", PAGE) == 100
    assert verify_quote("«macroscopic quantum mechanical tunnelling in an electric circuit»", PAGE) >= 85


def test_verify_quote_rejects_an_invented_quote():
    assert verify_quote("The prize was awarded to Peter Higgs for the Higgs boson", PAGE) == 0
    assert verify_quote("in 2025", PAGE) == 0  # too short to prove anything
    assert verify_quote("", PAGE) == 0


def test_select_pages_drops_the_same_article_on_another_host():
    title = "About feasibility of SpaceX human exploration Mars mission scenario"
    results = [SearchResult(url="https://www.nature.com/articles/s41598-024-54012-0", title=title),
               SearchResult(url="https://doi.org/10.1038/s41598-024-54012-0", title=title),
               SearchResult(url="https://en.wikipedia.org/wiki/Human_mission_to_Mars",
                            title="Human mission to Mars - Wikipedia")]
    picked = select_pages(results, seen=set(), limit=3, per_domain=2)
    assert [p.url for p in picked] == ["https://www.nature.com/articles/s41598-024-54012-0",
                                       "https://en.wikipedia.org/wiki/Human_mission_to_Mars"]
