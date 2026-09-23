from taro.search import clean_title, domain, normalize_url, parse_page, parse_search_results

RAW = (
    "Title: Nobel Prize in Physics 2025\nURL: https://www.nobelprize.org/prizes/physics/2025/press-release/\n"
    "Acquired: 2026-08-21\nSnippets:\nFirst part of the snippet.\n[...]\nSecond part.\n\n---\n\n"
    "Title: APS congratulates winners | APS\nURL: https://aps.org/news/nobel-2025\nPublished: 2025-10-07\n"
    "Acquired: 2026-05-23\nSnippets:\nAnnouncement text"
)


def test_parse_search_results():
    results = parse_search_results(RAW)
    assert [r.url for r in results] == ["https://www.nobelprize.org/prizes/physics/2025/press-release/",
                                        "https://aps.org/news/nobel-2025"]
    assert results[0].title == "Nobel Prize in Physics 2025"
    assert results[0].published is None and results[0].acquired == "2026-08-21"
    assert results[0].snippet == "First part of the snippet. … Second part."
    assert results[1].published == "2025-10-07"


def test_parse_search_results_empty():
    assert parse_search_results("") == []


def test_parse_page():
    page = parse_page("https://x.org/a", "Title: Hello\nURL: https://x.org/a\n\n# Hello\n\nBody text.")
    assert page.title == "Hello"
    assert page.text == "# Hello\n\nBody text."


def test_normalize_url_dedupes_variants():
    a = normalize_url("https://www.Example.com/path/?utm_source=x&b=2&a=1#section")
    b = normalize_url("https://example.com/path?a=1&b=2")
    assert a == b == "https://example.com/path?a=1&b=2"
    assert normalize_url("https://example.com/") == normalize_url("https://example.com")


def test_domain():
    assert domain("https://www.En.Wikipedia.org:443/wiki/X") == "en.wikipedia.org"


def test_clean_title():
    title = 'Quantum Trio<br/><small class="x">By Reuters</small> | GOLDSEA &amp; co'
    assert clean_title(title) == "Quantum Trio By Reuters | GOLDSEA & co"
