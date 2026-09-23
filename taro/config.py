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

    cache_dir: Path = ROOT / "cache"
    runs_dir: Path = ROOT / "runs"

    # v2 simple RAG
    v2_results: int = 8
    v2_snippet_chars: int = 2000


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
    )
