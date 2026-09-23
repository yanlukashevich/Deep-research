"""Keenable MCP: search() and fetch(), cached on disk so repeated runs are free and reproducible."""
import asyncio
import html
import json
import re
import time
from contextlib import AsyncExitStack
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import diskcache
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .config import Settings
from .report import Trace
from .schemas import Page, SearchResult

_TRACKING_PARAMS = re.compile(r"^(utm_\w+|fbclid|gclid|yclid|mc_cid|mc_eid|ref|ref_src|_ga)$", re.I)


def normalize_url(url: str) -> str:
    """Canonical form used to spot duplicate pages: lower-case host without www, no fragment,
    no tracking parameters, no trailing slash."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                             if not _TRACKING_PARAMS.match(k)))
    path = parts.path.rstrip("/") if parts.path not in ("", "/") else ""
    return urlunsplit(((parts.scheme or "https").lower(), host, path, query, ""))


def domain(url: str) -> str:
    """Host without www and port, e.g. 'en.wikipedia.org'."""
    return (urlsplit(url.strip()).hostname or "").lower().removeprefix("www.")


def clean_title(title: str) -> str:
    """Some sites put HTML into <title>: strip tags and entities."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", title))).strip()


def parse_search_results(text: str) -> list[SearchResult]:
    """Parse Keenable's plain-text result blocks (Title:/URL:/Published:/Acquired:/Snippets:)."""
    results = []
    for block in re.split(r"\n+---\n+", text.strip()):
        head, _, snippet = block.partition("Snippets:")
        fields = {}
        for line in head.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip() in ("Title", "URL", "Published", "Acquired"):
                fields[key.strip().lower()] = value.strip()
        if fields.get("url"):
            snippet = re.sub(r"\s*\n\[\.\.\.\]\n\s*", " … ", snippet.strip())
            results.append(SearchResult(url=fields["url"], title=clean_title(fields.get("title", "")),
                                        published=fields.get("published"), acquired=fields.get("acquired"),
                                        snippet=snippet))
    return results


def parse_page(url: str, text: str) -> Page:
    """Split Keenable's 'Title: …\\nURL: …\\n\\n<markdown>' page into title and body."""
    title = ""
    head, sep, body = text.partition("\n\n")
    if sep and head.startswith("Title:"):
        for line in head.splitlines():
            if line.startswith("Title:"):
                title = clean_title(line.removeprefix("Title:"))
        text = body
    return Page(url=url, title=title, text=text.strip())


class SearchError(Exception):
    pass


class Search:
    """Keenable MCP client. Use as `async with Search(settings, trace) as s:`."""

    def __init__(self, settings: Settings, trace: Trace | None = None, *, session_id: str | None = None,
                 use_cache: bool = True):
        self.settings = settings
        self.trace = trace or Trace()
        self.session_id = session_id
        self.cache = diskcache.Cache(str(settings.cache_dir / "keenable")) if use_cache else None
        self._sem = asyncio.Semaphore(settings.search_concurrency)
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "Search":
        # Connect eagerly: the MCP transport runs an anyio task group that must be closed by the task
        # that opened it, so it can't be opened lazily inside a gathered child task.
        self._stack = AsyncExitStack()
        http = httpx2.AsyncClient(headers={"X-API-Key": self.settings.keenable_api_key},
                                  timeout=httpx2.Timeout(30, read=self.settings.search_timeout_s))
        await self._stack.enter_async_context(http)
        streams = await self._stack.enter_async_context(
            streamable_http_client(self.settings.keenable_url, http_client=http))
        self._session = await self._stack.enter_async_context(ClientSession(*streams[:2]))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._stack:
            await self._stack.aclose()
        if self.cache is not None:
            self.cache.close()

    async def _call(self, tool: str, args: dict) -> tuple[str, bool]:
        """Call a Keenable tool. Returns (text, is_error). Successful results are cached."""
        key = json.dumps([tool, args], sort_keys=True, ensure_ascii=False)
        if self.cache is not None and (hit := self.cache.get(key)) is not None:
            self.trace.count("cache_hits")
            return hit, False
        if self._session is None:
            raise SearchError("Search is not connected: use `async with Search(...)`")
        call_args = args | ({"session_id": self.session_id} if self.session_id else {})
        retrying = AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10),
                                 retry=retry_if_exception_type(Exception), reraise=True)
        async for attempt in retrying:
            with attempt:
                async with self._sem:
                    res = await asyncio.wait_for(self._session.call_tool(tool, call_args),
                                                 self.settings.search_timeout_s)
        text = "".join(c.text for c in res.content if hasattr(c, "text"))
        if not res.is_error and self.cache is not None:
            self.cache.set(key, text)
        return text, bool(res.is_error)

    async def search(self, query: str, *, max_results: int = 10, **filters) -> list[SearchResult]:
        """Search the web. `filters` go to Keenable as-is: site, published_after/before (YYYY-MM-DD),
        snippet_max_length, mode ("pro" | "realtime") and so on."""
        args = {"query": query, "max_results": max_results} | {k: v for k, v in filters.items() if v is not None}
        t0 = time.monotonic()
        text, is_error = await self._call("search_web_pages", args)
        self.trace.count("searches")
        if is_error:
            self.trace.event("search_error", args=args, error=text[:500])
            raise SearchError(f"search failed: {text[:300]}")
        results = parse_search_results(text)
        self.trace.event("search", args=args, n_results=len(results), latency=round(time.monotonic() - t0, 2),
                         urls=[r.url for r in results])
        return results

    async def fetch(self, url: str, *, max_chars: int = 50_000) -> Page | None:
        """Fetch a page as markdown. Returns None if Keenable can't get it (the failure is logged)."""
        t0 = time.monotonic()
        try:
            text, is_error = await self._call("fetch_page_content", {"url": url, "max_chars": max_chars})
        except Exception as e:  # network trouble after retries: treat as a bad page
            text, is_error = repr(e), True
        self.trace.count("fetches")
        if is_error or not text.strip():
            self.trace.count("fetch_errors")
            self.trace.event("fetch_error", url=url, error=text[:300])
            return None
        page = parse_page(url, text)
        self.trace.event("fetch", url=url, chars=len(page.text), latency=round(time.monotonic() - t0, 2))
        return page
