"""Phase 0 model selection benchmark for the LiteLLM models.

For each candidate model it measures:
  - JSON: fact extraction into a Pydantic schema (EN + RU passage), with quotes checked against the source
  - speed: latency and output tokens/s
  - Russian: writes a short cited answer in Russian from numbered facts
  - context: needle-in-a-haystack at growing prompt sizes

Usage:  python scripts/model_bench.py [model ...]
Results are printed and saved to scripts/model_bench_results.json.
"""
import asyncio
import json
import os
import re
import sys
import time

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from rapidfuzz import fuzz

load_dotenv(".env")
sys.stdout.reconfigure(encoding="utf-8")

CANDIDATES = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27B-fp8",
    "qwen/qwen3.6-35b-A3B",
    "google/gemma4:31b",
    "glm-4.7-flash",
]

client = AsyncOpenAI(base_url=os.environ["LITELLM_BASE_URL"], api_key=os.environ["LITELLM_API_KEY"],
                     timeout=120, max_retries=0)
SEM = asyncio.Semaphore(3)  # shared service: keep parallel calls low
MODEL_BUDGET_S = 480  # give up on a model that takes longer than this in total


class Fact(BaseModel):
    statement: str
    quote: str


class Facts(BaseModel):
    facts: list[Fact]


PASSAGE_EN = (
    "The Ivannikov Institute for System Programming of the Russian Academy of Sciences (ISP RAS) is a scientific "
    "research organization specializing in system programming, founded on January 25, 1994, in Moscow, Russia, on the "
    "basis of departments from the Institute for Cybernetics Problems of the RAS. It operates under the Division of "
    "Mathematical Sciences of the RAS and employs over 200 researchers including 12 Doctors of Science and 45 PhD "
    "holders. Academician V.P. Ivannikov led the institute for 21 years from its founding until 2015. Since 2015 the "
    "director has been Academician A.I. Avetisyan."
)
QUESTION_EN = "When was ISP RAS founded, who led it, and how many researchers does it have?"

PASSAGE_RU = (
    "Байкал — озеро тектонического происхождения в южной части Восточной Сибири, самое глубокое озеро на планете. "
    "Максимальная глубина озера составляет 1642 метра. В Байкале содержится около 23 615 кубических километров воды, "
    "что составляет примерно 20 % мировых запасов пресной озёрной воды. В озеро впадает более 300 рек, а вытекает "
    "только одна — Ангара. В 1996 году Байкал был включён в список объектов Всемирного наследия ЮНЕСКО."
)
QUESTION_RU = "Какова глубина Байкала, сколько в нём воды и какие реки с ним связаны?"

EXTRACT_SYSTEM = (
    "You extract facts from a web page to answer a research question. Use ONLY the page text. "
    'Return JSON: {"facts": [{"statement": "<fact in your own words>", "quote": "<exact verbatim substring of the page>"}]}. '
    "The quote must be copied character-for-character from the page. Return 3-6 facts. Output only JSON."
)

WRITER_FACTS = """[1] The Eiffel Tower is 330 metres tall including antennas. (source: toureiffel.paris)
[2] The tower was completed in March 1889 for the Exposition Universelle. (source: britannica.com)
[3] It was designed by the engineering company of Gustave Eiffel; the main engineers were Maurice Koechlin and Émile Nouguier. (source: wikipedia.org)
[4] About 6 million people visit the tower each year. (source: toureiffel.paris)
[5] A 2024 news report says the tower received 6.3 million visitors in 2023. (source: reuters.com)"""
WRITER_SYSTEM = (
    "You write the answer to a research question using ONLY the numbered facts. Answer in Russian. "
    "Every sentence must end with citations like [1] or [2][4]. If facts disagree, say so. Write 4-5 sentences, no preamble."
)
WRITER_Q = "Расскажи кратко об Эйфелевой башне: когда построена, кто спроектировал, высота и посещаемость."

NEEDLE = "The secret launch code for project Tamarind is 7461-KESTREL."
FILLER = (
    "Research agents retrieve documents, extract evidence, and synthesize answers with citations. "
    "Each retrieved page is split into passages that are ranked by relevance before extraction. "
)


def cyr_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in letters) / max(1, len(letters))


async def chat(model: str, messages: list[dict], max_tokens: int = 4096, json_mode: bool = False) -> dict:
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    async with SEM:
        t0 = time.time()
        try:
            r = await client.chat.completions.create(
                model=model, messages=messages, temperature=0.1, max_tokens=max_tokens, **kwargs
            )
        except Exception as e:  # noqa: BLE001 - benchmark records any failure
            return {"error": f"{type(e).__name__}: {str(e)[:200]}", "latency": time.time() - t0}
    dt = time.time() - t0
    msg = r.choices[0].message
    reasoning = getattr(msg, "reasoning_content", None) or ""
    out = r.usage.completion_tokens if r.usage else 0
    return {
        "content": msg.content or "",
        "reasoning_chars": len(reasoning),
        "latency": dt,
        "prompt_tokens": r.usage.prompt_tokens if r.usage else 0,
        "completion_tokens": out,
        "tok_per_s": out / dt if dt else 0,
        "finish": r.choices[0].finish_reason,
    }


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text)


async def test_extract(model: str, passage: str, question: str) -> dict:
    res = await chat(
        model,
        [{"role": "system", "content": EXTRACT_SYSTEM},
         {"role": "user", "content": f"Question: {question}\n\nPage:\n{passage}"}],
        json_mode=True,
    )
    if "error" in res:
        return res
    try:
        facts = Facts.model_validate(parse_json(res["content"])).facts
        exact = sum(f.quote in passage for f in facts)
        fuzzy = sum(fuzz.partial_ratio(f.quote, passage) >= 90 for f in facts)
        res.update(valid=True, n_facts=len(facts), exact_quotes=exact, fuzzy_quotes=fuzzy)
    except (json.JSONDecodeError, ValidationError) as e:
        res.update(valid=False, parse_error=str(e)[:200])
    res.pop("content")
    return res


async def test_writer(model: str) -> dict:
    res = await chat(
        model,
        [{"role": "system", "content": WRITER_SYSTEM},
         {"role": "user", "content": f"Question: {WRITER_Q}\n\nFacts:\n{WRITER_FACTS}"}],
    )
    if "error" in res:
        return res
    text = res["content"]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if len(s) > 3]
    cited = sum(bool(re.search(r"\[\d+\]", s)) for s in sentences)
    res.update(
        text=text,
        cyrillic_share=round(cyr_share(text), 2),
        cjk_leak=bool(re.search(r"[一-鿿]", text)),
        sentences=len(sentences),
        cited_sentences=cited,
    )
    return res


async def test_context(model: str) -> dict:
    """Needle in a haystack; stop at the first size that fails."""
    passed = 0
    detail = {}
    for k_tokens in (16, 48, 100):
        n = k_tokens * 1000 * 4 // len(FILLER)  # ~4 chars per token
        hay = [FILLER] * n
        hay.insert(n // 2, NEEDLE + " ")
        res = await chat(
            model,
            [{"role": "user", "content": "".join(hay) + "\n\nWhat is the secret launch code for project Tamarind? Reply with the code only."}],
            max_tokens=2048,
        )
        ok = "error" not in res and "7461-KESTREL" in res.get("content", "")
        detail[f"{k_tokens}k"] = {"ok": ok, "latency": round(res["latency"], 1), "prompt_tokens": res.get("prompt_tokens"),
                                  "error": res.get("error")}
        if not ok:
            break
        passed = k_tokens
    return {"max_passed_k": passed, "detail": detail}


async def bench(model: str) -> dict:
    print(f"… {model}", flush=True)
    ex = await asyncio.gather(*[test_extract(model, PASSAGE_EN, QUESTION_EN) for _ in range(2)],
                              *[test_extract(model, PASSAGE_RU, QUESTION_RU) for _ in range(2)])
    writer = await test_writer(model)
    ctx = await test_context(model)
    return {"model": model, "extract": ex, "writer": writer, "context": ctx}


def summarize(r: dict) -> str:
    ex = r["extract"]
    ok = [e for e in ex if e.get("valid")]
    q_total = sum(e["n_facts"] for e in ok)
    q_exact = sum(e["exact_quotes"] for e in ok)
    q_fuzzy = sum(e["fuzzy_quotes"] for e in ok)
    lat = sum(e["latency"] for e in ex) / len(ex)
    tps = sum(e.get("tok_per_s", 0) for e in ok) / max(1, len(ok))
    w = r["writer"]
    return (
        f"{r['model']:24} json {len(ok)}/{len(ex)} | quotes exact {q_exact}/{q_total} fuzzy {q_fuzzy}/{q_total} | "
        f"extract {lat:5.1f}s {tps:5.0f} tok/s | RU cyr={w.get('cyrillic_share')} cited={w.get('cited_sentences')}/{w.get('sentences')} "
        f"cjk={w.get('cjk_leak')} {w.get('latency', 0):.1f}s | ctx ≥{r['context']['max_passed_k']}k"
    )


async def bench_safe(model: str) -> dict | None:
    try:
        r = await asyncio.wait_for(bench(model), MODEL_BUDGET_S)
    except asyncio.TimeoutError:
        print(f"✗ {model}: gave up after {MODEL_BUDGET_S}s", flush=True)
        return None
    print(summarize(r), flush=True)  # report each model as soon as it is done
    return r


async def main() -> None:
    models = sys.argv[1:] or CANDIDATES
    results = [r for r in await asyncio.gather(*[bench_safe(m) for m in models]) if r]
    print("\n=== SUMMARY ===")
    for r in results:
        print(summarize(r))
    print("\n=== RUSSIAN WRITER OUTPUT ===")
    for r in results:
        print(f"\n--- {r['model']} ---\n{r['writer'].get('text') or r['writer'].get('error')}")
    with open("scripts/model_bench_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
