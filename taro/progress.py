"""Trace events turned into one readable line each, for the live CLI output."""
from typing import Any


def _short(text: str, limit: int = 70) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _n(event: dict[str, Any], key: str) -> str:
    """A number for the line: lists are counted, so `subquestions=[...]` prints as how many."""
    value = event.get(key)
    if isinstance(value, (list, tuple, dict)):
        return str(len(value))
    return "?" if value is None else str(value)


def describe(event: dict[str, Any]) -> str | None:
    """A short line for the terminal, or None for events the user does not need to see."""
    kind = event.get("kind")
    if kind == "search":
        query = event.get("query") or (event.get("args") or {}).get("query", "")
        return f"searched: {_short(query)} -> {_n(event, 'n_results')} results"
    if kind == "fetch":
        return f"read {_short(event.get('url', ''), 80)} ({_n(event, 'chars')} chars)"
    if kind == "facts":
        rejected = event.get("rejected") or 0
        tail = f", {rejected} quote{'s' if rejected > 1 else ''} rejected" if rejected else ""
        return f"  {_n(event, 'kept')} facts from {_short(event.get('url', ''), 80)}{tail}"
    if kind != "step":
        return None

    name = event.get("name")
    if name == "plan":
        return "planning the research"
    if name == "plan_done":
        after = event.get("published_after")
        return (f"plan: {_n(event, 'subquestions')} sub-questions, {_n(event, 'queries')} queries"
                + (f", only pages after {after}" if after else ""))
    if name == "search":  # v2 searches once, with the question itself
        return f"searching: {_short(event.get('query', ''))}"
    if name == "round":
        return f"round {_n(event, 'round')}: {_n(event, 'queries')} searches"
    if name == "select":
        return f"picked {_n(event, 'picked')} pages out of {_n(event, 'candidates')} found"
    if name == "read":
        return f"reading {_n(event, 'pages')} pages"
    if name == "extract":
        return f"extracting facts from {_n(event, 'pages')} pages"
    if name == "extract_done":
        return f"round {_n(event, 'round')}: {_n(event, 'facts')} facts from {_n(event, 'pages_read')} pages"
    if name == "critic":
        return f"critic is checking {_n(event, 'facts')} facts"
    if name == "critic_done":
        if event.get("enough"):
            return "critic: enough material"
        missing = event.get("missing") or []
        queries = event.get("queries") or []
        return (f"critic: {len(missing)} sub-question{'s' if len(missing) != 1 else ''} still open,"
                f" {len(queries)} new searches")
    if name == "stop":
        return f"stopping: {event.get('reason', '')}"
    if name == "write":
        return f"writing the answer from {_n(event, 'facts')} facts and {_n(event, 'sources')} sources"
    if name == "answer":
        return "answer ready, scoring the sentences"
    return name
