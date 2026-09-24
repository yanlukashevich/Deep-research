"""Choosing which pages to read, trimming them to the relevant parts, and checking quotes are real.

Three jobs, all plain code (no LLM):
- `domain_quality` / `is_junk`: how much a website is worth reading (also used by the confidence score)
- `select_pages`: from many search hits pick a few good, different pages
- `relevant_passages` (BM25) and `verify_quote` (fuzzy search in the page text)
"""
import re
from collections import Counter
from collections.abc import Iterable

from rank_bm25 import BM25Okapi
from rapidfuzz import fuzz

from .schemas import SearchResult
from .search import domain, normalize_url

# ---------- how good is a website ----------

# Official bodies, universities and science publishers: 1.0
OFFICIAL_SUFFIXES = (".gov", ".mil", ".int", ".edu", ".ac.uk", ".gov.uk", ".edu.au", ".ac.jp", ".gov.ru", ".edu.ru")
OFFICIAL = {
    "europa.eu", "un.org", "who.int", "imf.org", "worldbank.org", "oecd.org", "nato.int", "esa.int",
    "nasa.gov", "nobelprize.org", "kremlin.ru", "government.ru", "ras.ru", "ispras.ru", "minobrnauki.gov.ru",
    "nature.com", "science.org", "sciencedirect.com", "springer.com", "wiley.com", "arxiv.org", "doi.org",
    "ncbi.nlm.nih.gov", "ieee.org", "acm.org", "jstor.org", "cell.com", "thelancet.com", "nejm.org",
    "pnas.org", "plos.org", "biorxiv.org", "medrxiv.org", "elibrary.ru", "cyberleninka.ru", "mathnet.ru",
}
ENCYCLOPEDIA = {"wikipedia.org", "wikidata.org", "wikisource.org", "britannica.com", "bigenc.ru",
                "scholarpedia.org", "encyclopedia.com"}
NEWS = {
    "reuters.com", "apnews.com", "afp.com", "bbc.com", "bbc.co.uk", "nytimes.com", "washingtonpost.com",
    "theguardian.com", "ft.com", "wsj.com", "economist.com", "bloomberg.com", "cnbc.com", "cnn.com",
    "nbcnews.com", "abcnews.go.com", "npr.org", "dw.com", "france24.com", "aljazeera.com", "politico.com",
    "axios.com", "time.com", "forbes.com", "businessinsider.com", "theverge.com", "wired.com", "arstechnica.com",
    "techcrunch.com", "newscientist.com", "scientificamerican.com", "phys.org",
    "tass.ru", "ria.ru", "interfax.ru", "kommersant.ru", "vedomosti.ru", "rbc.ru", "iz.ru", "lenta.ru",
    "gazeta.ru", "meduza.io", "rg.ru", "cnews.ru", "3dnews.ru", "naked-science.ru", "nplus1.ru",
}
# Blogs, forums and other user-generated pages: 0.4
UGC = {
    "medium.com", "substack.com", "blogspot.com", "wordpress.com", "livejournal.com", "telegra.ph", "t.me",
    "reddit.com", "quora.com", "stackoverflow.com", "stackexchange.com", "superuser.com", "habr.com",
    "dzen.ru", "zen.yandex.ru", "pikabu.ru", "vc.ru", "youtube.com", "facebook.com", "twitter.com", "x.com",
    "vk.com", "instagram.com", "tiktok.com", "tumblr.com", "answers.com", "fandom.com", "pinterest.com",
}
# Not worth a fetch at all: job boards, shops, aggregators, link trackers
JUNK = {
    "hh.ru", "rabota.ru", "superjob.ru", "zarplata.ru", "indeed.com", "glassdoor.com", "linkedin.com",
    "aliexpress.com", "amazon.com", "ebay.com", "ozon.ru", "wildberries.ru", "avito.ru",
    "coursera.org", "udemy.com", "scribd.com", "slideshare.net", "issuu.com", "academia.edu",
}
_JUNK_PATH = re.compile(r"/(click|redirect|track|goto|out)/|[?&](utm_|redirect=)", re.I)


def _in(d: str, names: set[str]) -> bool:
    """True if `d` is one of `names` or a subdomain of one (ru.wikipedia.org -> wikipedia.org)."""
    return any(d == n or d.endswith("." + n) for n in names)


def domain_quality(url_or_domain: str) -> float:
    """0.4-1.0: official/scientific 1.0, encyclopedia 0.8, news 0.7, unknown site 0.5, blog/forum 0.4."""
    d = domain(url_or_domain) if "/" in url_or_domain or ":" in url_or_domain else url_or_domain.lower()
    d = d.removeprefix("www.")
    if _in(d, OFFICIAL) or d.endswith(OFFICIAL_SUFFIXES):
        return 1.0
    if _in(d, ENCYCLOPEDIA):
        return 0.8
    if _in(d, NEWS):
        return 0.7
    if _in(d, UGC):
        return 0.4
    return 0.5


def is_junk(url: str) -> bool:
    """Pages we never read: job boards, shops, and tracking/redirect links."""
    d = domain(url)
    return _in(d, JUNK) or d.startswith("link.") or bool(_JUNK_PATH.search(url))


# ---------- choosing pages to read ----------

MIN_TITLE_FOR_DEDUPE = 25


def title_key(title: str) -> str:
    """Comparable form of a title, used to spot the same article on two hosts (nature.com and doi.org)."""
    key = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title.lower())).strip()
    return key if len(key) >= MIN_TITLE_FOR_DEDUPE else ""


def select_pages(results: Iterable[SearchResult], *, seen: set[str], limit: int, per_domain: int,
                 domain_counts: Counter | None = None, seen_titles: set[str] | None = None) -> list[SearchResult]:
    """Pick up to `limit` pages: no duplicates, at most `per_domain` per website, better sites first.

    `seen` holds normalized URLs already taken (it is updated), `domain_counts` the pages already taken
    per website and `seen_titles` the articles already taken under any host, so the caps hold across rounds.
    """
    counts = domain_counts if domain_counts is not None else Counter()
    titles = seen_titles if seen_titles is not None else set()
    # one entry per URL: the result, its best (smallest) search rank, and how many queries returned it
    best: dict[str, tuple[SearchResult, int, int]] = {}
    for rank, r in enumerate(results):
        if is_junk(r.url):
            continue
        key = normalize_url(r.url)
        if key in seen:
            continue
        if key in best:
            prev, best_rank, hits = best[key]
            best[key] = (prev, min(best_rank, rank), hits + 1)
        else:
            best[key] = (r, rank, 1)

    def score(item: tuple[SearchResult, int, int]) -> float:
        r, rank, hits = item
        # trusted site first, then pages several queries agreed on, then the search engine's own order
        return domain_quality(r.url) + 0.2 * min(hits - 1, 2) - 0.01 * rank

    picked: list[SearchResult] = []
    for r, _, _ in sorted(best.values(), key=score, reverse=True):
        d = domain(r.url)
        if counts[d] >= per_domain:
            continue
        if (key := title_key(r.title)) and key in titles:
            continue  # the same article we already have from another host
        counts[d] += 1
        if key:
            titles.add(key)
        seen.add(normalize_url(r.url))
        picked.append(r)
        if len(picked) >= limit:
            break
    return picked


# ---------- trimming a page to the parts that matter ----------

_TOKEN = re.compile(r"\w+", re.UNICODE)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _blocks(text: str, target: int = 700) -> list[str]:
    """Split page markdown into blocks of roughly `target` characters, dropping obvious navigation."""
    text = _IMAGE.sub(" ", text)
    out: list[str] = []
    buf = ""
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"[ \t]+", " ", para.strip())
        if not para or set(para) <= set("|-=*_ "):
            continue
        plain = _LINK.sub(r"\1", para)  # keep the link text, drop the URL
        if len(plain) < 40 and not re.search(r"\d", plain):
            continue  # a short line with no numbers is a menu item or a stray label
        buf = f"{buf}\n\n{plain}" if buf else plain
        if len(buf) >= target:
            out.append(buf)
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def relevant_passages(text: str, queries: list[str], *, max_chars: int) -> str:
    """Keep the parts of a page that match the question best (BM25), in the page's own order.

    The start of the page is always kept: it carries the lead paragraph and usually the date.
    """
    blocks = _blocks(text)
    if not blocks:
        return text[:max_chars]
    if sum(map(len, blocks)) <= max_chars:
        return "\n\n".join(blocks)
    query = _tokens(" ".join(queries))
    scores = BM25Okapi([_tokens(b) for b in blocks]).get_scores(query) if query else [0.0] * len(blocks)
    order = sorted(range(len(blocks)), key=lambda i: (i > 0, -scores[i]))  # block 0 first, then by score
    keep: set[int] = set()
    used = 0
    for i in order:
        if keep and used + len(blocks[i]) > max_chars:
            continue
        keep.add(i)
        used += len(blocks[i])
        if used >= max_chars:
            break
    return "\n\n".join(blocks[i] for i in sorted(keep))


# ---------- is the quote really on the page ----------

_QUOTE_CHARS = str.maketrans({"“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
                              "’": "'", "‘": "'", "–": "-", "—": "-",
                              " ": " ", " ": " ", " ": " "})
MIN_QUOTE_CHARS = 15


def _flat(text: str) -> str:
    """Lower-case, one-space, plain-punctuation form used for comparing a quote with page text."""
    return re.sub(r"\s+", " ", text.translate(_QUOTE_CHARS).lower()).strip()


def verify_quote(quote: str, page_text: str, *, min_score: float = 85.0) -> float:
    """How well the quote is found in the page (0-100). Below `min_score` returns 0: treat it as made up.

    Fuzzy on purpose: markdown cleanup, ellipses and stray spaces must not sink a real quote,
    while an invented sentence will not match.
    """
    q, page = _flat(quote), _flat(page_text)
    if len(q) < MIN_QUOTE_CHARS or not page:
        return 0.0
    return float(fuzz.partial_ratio(q, page, score_cutoff=min_score))
