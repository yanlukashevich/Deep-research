"""Runs one question in a given mode and saves the output to runs/<time>-<mode>/. Used by the CLI and the server."""
from pathlib import Path

from .config import get_settings
from .llm import LLM
from .report import finalize, save_report
from .schemas import Mode, Report
from .search import Search
from .trace import Listener, Trace, new_run_dir
from .v1_bare import run_v1
from .v2_rag import run_v2
from .v3_research import run_v3

IMPLEMENTED_MODES: tuple[Mode, ...] = ("v1", "v2", "v3")


async def run(question: str, mode: Mode, *, listener: Listener | None = None,
              use_cache: bool = True) -> tuple[Report, Path]:
    if mode not in IMPLEMENTED_MODES:
        raise NotImplementedError(f"mode {mode} is not implemented yet")
    settings = get_settings()
    run_dir = new_run_dir(settings.runs_dir, mode)
    trace = Trace(run_dir / "trace.jsonl", listener)
    trace.event("start", question=question, mode=mode, run_dir=str(run_dir))
    llm = LLM(settings, trace)
    try:
        if mode == "v1":
            report = await run_v1(question, llm)
        else:
            async with Search(settings, trace, session_id=run_dir.name, use_cache=use_cache) as search:
                report = await (run_v2(question, llm, search) if mode == "v2"
                                else run_v3(question, llm, search))
    except Exception as e:
        trace.event("error", error=repr(e))
        raise
    report = finalize(report, trace)
    save_report(report, run_dir)
    trace.event("done", stats=report.stats)
    return report, run_dir
