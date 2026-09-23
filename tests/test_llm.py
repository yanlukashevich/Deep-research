from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from taro.config import Settings
from taro.llm import LLM, LLMJSONError, extract_json


class Answer(BaseModel):
    value: int


def make_llm(replies: list[str]) -> tuple[LLM, list]:
    settings = Settings(litellm_base_url="http://localhost", litellm_api_key="x", keenable_url="http://localhost",
                        keenable_api_key="x", main_model="main", fast_model="fast", llm_attempts=2)
    llm = LLM(settings)
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=replies[len(calls) - 1])
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return llm, calls


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('Sure! {"a": {"b": 2}} Hope it helps.') == '{"a": {"b": 2}}'


async def test_json_repairs_invalid_answer():
    llm, calls = make_llm(['{"value": "not a number"}', '{"value": 42}'])
    result = await llm.json([{"role": "user", "content": "give me 42"}], Answer)
    assert result.value == 42
    assert len(calls) == 2
    assert "invalid" in calls[1]["messages"][-1]["content"]  # the error was sent back to the model
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert llm.trace.stats["llm_calls"] == 2 and llm.trace.stats["json_repairs"] == 1


async def test_json_gives_up():
    llm, _ = make_llm(["{}", "{}"])
    with pytest.raises(LLMJSONError):
        await llm.json([{"role": "user", "content": "x"}], Answer, repairs=1)


async def test_empty_content_is_retried():
    llm, calls = make_llm(["", "hello"])
    assert await llm.chat([{"role": "user", "content": "hi"}]) == "hello"
    assert len(calls) == 2
