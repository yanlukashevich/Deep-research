"""Settings: keys from .env, model names and limits."""
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    litellm_base_url: str
    litellm_api_key: str
    keenable_url: str
    keenable_api_key: str
    main_model: str  # planner, critic, writer
    fast_model: str  # page reading / fact extraction

    # LiteLLM is a shared service: keep parallel calls low
    llm_concurrency: int = 3
    llm_timeout_s: float = 180
    llm_attempts: int = 4
    search_concurrency: int = 6
    search_timeout_s: float = 60

    # Where each run writes report.md / report.json / trace.jsonl. TARO_RUNS_DIR moves it off the
    # code folder, which is read-only on hosts that deploy the app as a package (Azure App Service).
    runs_dir: Path = ROOT / "runs"

    # v2 simple RAG
    v2_results: int = 8
    v2_snippet_chars: int = 2000

    # v3 research agent
    v3_max_rounds: int = 3            # planner round + up to 2 critic rounds
    v3_search_results: int = 8        # results per query
    v3_pages_per_round: int = 6
    v3_max_pages: int = 14            # pages read per run
    v3_per_domain: int = 2            # pages from one website
    v3_page_chars: int = 40_000       # how much of a page Keenable returns
    v3_passage_chars: int = 6_000     # how much of it the extractor sees (after BM25)
    v3_facts_per_page: int = 8
    v3_max_facts: int = 60
    v3_time_budget_s: float = 420     # stop starting new rounds after this
    quote_min_score: float = 85.0     # rapidfuzz partial_ratio needed to accept a quote


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set: copy .env.example to .env and fill in the keys")
    return value


@cache
def get_settings() -> Settings:
    return Settings(
        litellm_base_url=_required("LITELLM_BASE_URL"),
        litellm_api_key=_required("LITELLM_API_KEY"),
        keenable_url=_required("KEENABLE_URL"),
        keenable_api_key=_required("KEENABLE_API_KEY"),
        main_model=os.environ.get("TARO_MAIN_MODEL") or "openai/gpt-oss-120b",
        fast_model=os.environ.get("TARO_FAST_MODEL") or "google/gemma4:31b",
        runs_dir=Path(os.environ.get("TARO_RUNS_DIR", "").strip() or ROOT / "runs"),
    )
