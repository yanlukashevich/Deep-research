"""Phase 0 smoke test: list LiteLLM models, 1 LLM call, 1 Keenable search, 1 page fetch.

Usage:  python scripts/smoke_test.py
"""
import asyncio
import os
import sys
import time

import httpx2
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openai import OpenAI

load_dotenv(".env")
sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1250/cp1251


def llm_smoke() -> None:
    client = OpenAI(base_url=os.environ["LITELLM_BASE_URL"], api_key=os.environ["LITELLM_API_KEY"])
    models = sorted(m.id for m in client.models.list().data)
    print(f"{len(models)} LiteLLM models: {', '.join(models)}")

    model = os.environ.get("TARO_MAIN_MODEL") or models[0]
    t0 = time.time()
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Ответь одним предложением: что такое RAG?"}],
        temperature=0.1,
        max_tokens=1024,
    )
    print(f"\nLLM {model} ({time.time() - t0:.1f}s): {r.choices[0].message.content}")


async def keenable_smoke() -> None:
    headers = {"X-API-Key": os.environ["KEENABLE_API_KEY"]}
    http = httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(30, read=120))
    async with http, streamable_http_client(os.environ["KEENABLE_URL"], http_client=http) as streams:
        async with ClientSession(*streams[:2]) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"\nKeenable tools: {', '.join(t.name for t in tools.tools)}")

            t0 = time.time()
            res = await session.call_tool("search_web_pages", {"query": "ISP RAS Ivannikov Institute for System Programming"})
            text = "".join(c.text for c in res.content if hasattr(c, "text"))
            print(f"\nsearch ({time.time() - t0:.1f}s, {text.count('URL:')} results):\n{text[:600]}")

            t0 = time.time()
            res = await session.call_tool("fetch_page_content", {"url": "https://www.ispras.ru/en/", "max_chars": 5000})
            text = "".join(c.text for c in res.content if hasattr(c, "text"))
            print(f"\nfetch ({time.time() - t0:.1f}s, {len(text)} chars):\n{text[:600]}")


if __name__ == "__main__":
    llm_smoke()
    asyncio.run(keenable_smoke())
