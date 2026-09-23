"""LiteLLM client: low-temperature calls, JSON answers checked with Pydantic, retries, a parallel-call limit."""
import asyncio
import json
import re
import time
from typing import TypeVar

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .config import Settings
from .report import Trace

T = TypeVar("T", bound=BaseModel)


class EmptyResponse(Exception):
    """The model returned no content (gpt-oss can spend all max_tokens on reasoning)."""


class LLMJSONError(Exception):
    """The model kept returning JSON that does not match the schema."""


TRANSIENT = (
    openai.APIConnectionError,  # includes APITimeoutError
    openai.RateLimitError,
    openai.InternalServerError,
    EmptyResponse,
)

# One limit per event loop (i.e. for all runs in the process): the LiteLLM proxy is shared with other users.
_semaphore: tuple[asyncio.AbstractEventLoop, asyncio.Semaphore] | None = None


def _get_semaphore(limit: int) -> asyncio.Semaphore:
    global _semaphore
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore[0] is not loop:
        _semaphore = (loop, asyncio.Semaphore(limit))
    return _semaphore[1]


def extract_json(text: str) -> str:
    """Strip ```json fences and any chatter around the outermost JSON object."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text


class LLM:
    def __init__(self, settings: Settings, trace: Trace | None = None):
        self.settings = settings
        self.trace = trace or Trace()
        self.client = AsyncOpenAI(
            base_url=settings.litellm_base_url,
            api_key=settings.litellm_api_key,
            timeout=settings.llm_timeout_s,
            max_retries=0,  # retries are ours (tenacity), so they respect the semaphore
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        purpose: str = "chat",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """One chat completion with retries on transient errors. Returns the message text."""
        model = model or self.settings.main_model
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.settings.llm_attempts),
            wait=wait_exponential_jitter(initial=2, max=30),
            retry=retry_if_exception_type(TRANSIENT),
            before_sleep=lambda rs: self.trace.event("llm_retry", purpose=purpose, model=model,
                                                     attempt=rs.attempt_number, error=repr(rs.outcome.exception())),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                async with _get_semaphore(self.settings.llm_concurrency):
                    t0 = time.monotonic()
                    r = await self.client.chat.completions.create(
                        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, **kwargs
                    )
                    latency = time.monotonic() - t0
                content = (r.choices[0].message.content or "").strip() if r.choices else ""
                usage = r.usage
                self.trace.count("llm_calls")
                self.trace.count("prompt_tokens", usage.prompt_tokens if usage else 0)
                self.trace.count("completion_tokens", usage.completion_tokens if usage else 0)
                self.trace.event(
                    "llm_call", purpose=purpose, model=model, latency=round(latency, 2),
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=usage.completion_tokens if usage else None,
                    messages=messages, response=content,
                )
                if not content:
                    raise EmptyResponse(f"{model} returned empty content (finish_reason="
                                        f"{r.choices[0].finish_reason if r.choices else None})")
                return content
        raise AssertionError("unreachable")

    async def json(
        self,
        messages: list[dict[str, str]],
        schema: type[T],
        *,
        model: str | None = None,
        purpose: str = "json",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        repairs: int = 2,
    ) -> T:
        """Ask for JSON and validate it with `schema`. On invalid JSON, send the error back and ask again."""
        messages = list(messages)
        for i in range(repairs + 1):
            content = await self.chat(messages, model=model, purpose=purpose, temperature=temperature,
                                      max_tokens=max_tokens, json_mode=True)
            try:
                return schema.model_validate_json(extract_json(content))
            except ValidationError as e:
                error = _short_error(e)
                self.trace.event("llm_json_invalid", purpose=purpose, attempt=i + 1, error=error)
                self.trace.count("json_repairs")
                messages += [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"Your JSON is invalid: {error}\n"
                                                f"Return the corrected JSON only, matching this schema:\n"
                                                f"{json.dumps(schema.model_json_schema())}"},
                ]
        raise LLMJSONError(f"{purpose}: no valid JSON after {repairs + 1} attempts: {error}")


def _short_error(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or '<root>'}: {err['msg']}" for err in e.errors()[:5])
