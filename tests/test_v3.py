"""v3 without the network: the fake model answers from a script, so the checks around it can be tested."""
import json
from types import SimpleNamespace

from taro.config import Settings
from taro.llm import LLM
from taro.schemas import Page, SearchResult
from taro.v3_research import Research, _ReadPage

PAGE_TEXT = (
    "The Institute of System Programming was founded in January 1994 in Moscow, and Viktor Ivannikov "
    "was its first director. " * 3 + "\n\n"
    "Arutyun Avetisyan has been the director of the institute since August 2015. " * 3
)


def make_research(replies: list[str]) -> tuple[Research, list]:
    settings = Settings(litellm_base_url="http://localhost", litellm_api_key="x", keenable_url="http://localhost",
                        keenable_api_key="x", main_model="main", fast_model="fast")
    llm = LLM(settings)
    calls: list[dict] = []

    async def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=replies[len(calls) - 1])
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    research = Research("Who became director of ISP RAS after Ivannikov?", llm, search=None)  # type: ignore[arg-type]
    research.subquestions = ["Who is the new director?", "In which year?"]
    return research, calls


RESULT = SearchResult(url="https://www.ispras.ru/about/", title="About the institute", published="2025-01-01")
PAGE = Page(url=RESULT.url, title="About the institute", text=PAGE_TEXT)


async def test_extract_keeps_real_quotes_and_drops_invented_ones():
    extraction = {"facts": [
        {"statement": "Arutyun Avetisyan has been director since August 2015.",
         "quote": "Arutyun Avetisyan has been the director of the institute since August 2015.",
         "subquestion": 1},
        {"statement": "Avetisyan was appointed after Ivannikov died in 2016.",
         "quote": "Avetisyan took over after the death of Ivannikov in 2016.",  # not on the page
         "subquestion": 1},
        {"statement": "The institute was founded in January 1994.",
         "quote": "founded in January 1994 in Moscow", "subquestion": 7},  # sub-question does not exist
    ]}
    research, _ = make_research([json.dumps(extraction)])
    await research._extract(RESULT, PAGE)

    facts = research._all_facts()
    assert [f.statement for f in facts] == ["Arutyun Avetisyan has been director since August 2015.",
                                            "The institute was founded in January 1994."]
    assert facts[0].subquestion == 1
    assert facts[1].subquestion is None  # 7 is out of range, so no sub-question is claimed
    assert all(f.quote_score >= 85 for f in facts)
    assert research.llm.trace.stats["quotes_rejected"] == 1


async def test_numbering_only_counts_pages_that_gave_facts():
    research, _ = make_research([json.dumps({"facts": [
        {"statement": "Avetisyan is the director since August 2015.",
         "quote": "Arutyun Avetisyan has been the director of the institute since August 2015.",
         "subquestion": 1}]})])
    # an empty page read before the useful one must not take source number 1
    empty = SearchResult(url="https://example.com/empty", title="Empty")
    research.read.append(_ReadPage(result=empty, page=Page(url=empty.url, text="nothing here")))
    await research._extract(RESULT, PAGE)

    facts, sources = research._numbered()
    assert [s.url for s in sources.values()] == [RESULT.url]
    assert [(f.id, f.source_id) for f in facts] == [(1, 1)]
