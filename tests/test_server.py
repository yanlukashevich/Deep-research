"""The demo server: what reaches the browser, and what must never leave the machine."""
import json

import pytest
from fastapi.testclient import TestClient

from taro import server
from taro.progress import describe
from taro.report import answer_lines, finalize
from taro.schemas import Report, Source
from taro.trace import Trace


def _events(text: str) -> list[dict]:
    """Parse an SSE body into [{event, data}, ...]."""
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append({"event": lines["event"], "data": json.loads(lines.get("data", "{}"))})
    return out


def _fake_run(*, answer: str = "A fact [1].", fail: bool = False):
    """Stand in for runner.run: no network, no LLM, but the same listener/return contract."""
    async def run(question, mode, *, listener=None):
        if listener:
            listener({"t": 0.0, "kind": "start", "question": question, "mode": mode,
                      "run_dir": "C:/secret/path"})
            listener({"t": 0.4, "kind": "llm_call", "purpose": "write", "model": "m",
                      "prompt_tokens": 12, "messages": [{"role": "system", "content": "SECRET PROMPT"}],
                      "response": "raw model output"})
        if fail:
            raise RuntimeError("keenable is down")
        report = Report(question=question, mode=mode, answer=answer,
                        sources=[Source(id=1, url="https://nobelprize.org/p", domain="nobelprize.org")])
        return finalize(report, Trace()), type("D", (), {"name": "20260101-000000-" + mode})()
    return run


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "run", _fake_run())
    return TestClient(server.create_app())


def test_a_run_streams_its_steps_and_ends_with_the_report(client):
    response = client.get("/api/run", params={"question": "who?", "mode": "v3"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)

    assert [e["event"] for e in events] == ["hello", "trace", "trace", "report", "end"]
    report = events[-2]["data"]
    assert report["mode"] == "v3"
    assert report["report"]["answer"] == "A fact [1]."
    assert report["markdown"].startswith("# who?")
    assert report["lines"]  # the page needs them to colour the sentences


def test_prompts_and_local_paths_never_reach_the_page(client):
    body = client.get("/api/run", params={"question": "who?", "mode": "v3"}).text
    assert "SECRET PROMPT" not in body and "raw model output" not in body
    assert "C:/secret/path" not in body
    llm = [e["data"] for e in _events(body) if e["data"].get("kind") == "llm_call"][0]
    assert llm["prompt_tokens"] == 12  # the counters stay: the page shows what the run cost


def test_compare_mode_runs_all_three_and_labels_every_event(client):
    events = _events(client.get("/api/run", params={"question": "who?", "mode": "all"}).text)
    reports = [e["data"] for e in events if e["event"] == "report"]
    assert sorted(r["mode"] for r in reports) == ["v1", "v2", "v3"]
    assert all("mode" in e["data"] for e in events if e["event"] == "trace")


def test_one_broken_mode_does_not_stop_the_others(monkeypatch):
    def pick(question, mode, **kw):
        return _fake_run(fail=mode == "v2")(question, mode, **kw)
    monkeypatch.setattr(server, "run", pick)
    events = _events(TestClient(server.create_app())
                     .get("/api/run", params={"question": "who?", "mode": "all"}).text)
    failed = [e["data"] for e in events if e["event"] == "failed"]
    assert [f["mode"] for f in failed] == ["v2"]
    assert "keenable is down" in failed[0]["message"]
    assert len([e for e in events if e["event"] == "report"]) == 2


def test_a_bad_mode_is_refused(client):
    assert client.get("/api/run", params={"question": "who?", "mode": "v9"}).status_code == 422


def test_search_events_arrive_flat_and_carry_what_the_tool_returned():
    event = server.slim({"kind": "search", "n_results": 8,
                         "args": {"query": "nobel 2025", "max_results": 8, "published_after": "2025-01-01",
                                  "session_id": "20260101-000000-v3"},
                         "results": [{"url": f"https://s{i}.org", "title": f"t{i}", "published": None,
                                      "snippet": "s"} for i in range(9)]})
    assert event["query"] == "nobel 2025" and "args" not in event
    # the graph node shows what the query was filtered by, but not the run's own session id
    assert event["filters"] == {"published_after": "2025-01-01"}
    assert len(event["results"]) == server.MAX_RESULTS
    assert event["results"][0] == {"url": "https://s0.org", "title": "t0", "published": None, "snippet": "s"}
    # the urls all survive, so the graph can join a page to the search that found it
    assert event["urls"] == [f"https://s{i}.org" for i in range(9)]


def test_facts_and_quotes_are_trimmed_before_the_page_sees_them():
    facts = server.slim({"kind": "facts", "url": "u", "kept": 9, "statements": list("abcdefgh"),
                         "quotes": ["x" * 400] * 8})
    assert facts["statements"] == list("abcdef")  # the page shows a few, not all of them
    assert len(facts["quotes"]) == server.MAX_FACTS and len(facts["quotes"][0]) == server.MAX_QUOTE
    rejected = server.slim({"kind": "quote_rejected", "url": "u", "statement": "s", "quote": "y" * 400})
    assert len(rejected["quote"]) == server.MAX_QUOTE


def test_the_cli_log_line_of_every_step_reads_as_a_sentence():
    assert describe({"kind": "step", "name": "round", "round": 2, "queries": 4}) == "round 2: 4 searches"
    assert describe({"kind": "step", "name": "critic_done", "enough": True}) == "critic: enough material"
    assert "2 quotes rejected" in describe({"kind": "facts", "url": "u", "kept": 3, "rejected": 2})
    assert describe({"kind": "llm_call", "purpose": "write"}) is None  # not interesting to a reader


def test_answer_lines_hand_the_page_one_entry_per_sentence():
    report = Report(question="q", mode="v3", answer="# Head\n\nFirst [1]. Second.\n\n- Third [1]",
                    sources=[Source(id=1, url="https://nobelprize.org/p", domain="nobelprize.org")])
    report = finalize(report, Trace())
    lines = answer_lines(report)
    slots = [p["sentence"] for line in lines if line["kind"] == "prose" for p in line["parts"]]
    assert slots == [0, 1, 2] and len(report.sentences) == 3
    assert lines[0] == {"kind": "raw", "text": "# Head"}
    assert lines[-1]["prefix"] == "- "  # the list marker stays out of the sentence


def test_the_page_route_serves_the_built_page_and_nothing_above_it(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<html>built</html>", encoding="utf-8")
    (tmp_path.parent / "secret.env").write_text("KEENABLE_API_KEY=real-key", encoding="utf-8")
    monkeypatch.setattr(server, "WEB_DIR", tmp_path)
    client = TestClient(server.create_app())
    assert client.get("/").text == "<html>built</html>"
    assert "real-key" not in client.get("/../secret.env").text  # unknown paths fall back to the page
