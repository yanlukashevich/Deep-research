"""CLI:  python -m taro "question" [--mode v1|v2|v3] [--no-cache]"""
import argparse
import asyncio
import sys

from rich.console import Console
from rich.markdown import Markdown

from .runner import IMPLEMENTED_MODES, run


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1250
    parser = argparse.ArgumentParser(prog="python -m taro", description="TARO deep-research agent")
    parser.add_argument("question")
    parser.add_argument("--mode", choices=["v1", "v2", "v3"], default="v2",
                        help="v1 bare LLM, v2 simple RAG, v3 research agent")
    parser.add_argument("--no-cache", action="store_true", help="do not use the on-disk search/fetch cache")
    args = parser.parse_args(argv)

    console = Console()
    if args.mode not in IMPLEMENTED_MODES:
        console.print(f"[red]Mode {args.mode} is not implemented yet. Available: {', '.join(IMPLEMENTED_MODES)}")
        return 2

    def show_step(event: dict) -> None:
        if event["kind"] == "step":
            details = " ".join(f"{k}={v}" for k, v in event.items() if k not in ("t", "kind", "name"))
            console.print(f"[dim]{event['t']:6.1f}s  {event['name']}  {details}")

    report, run_dir = asyncio.run(run(args.question, args.mode, listener=show_step, use_cache=not args.no_cache))

    console.rule(f"[bold]{args.mode}")
    console.print(Markdown(report.answer))
    if report.sources:
        console.print()
        for s in report.sources:
            console.print(f"[dim][{s.id}] {s.title} · {s.domain} · {s.url}")
    s = report.stats
    console.print(f"\n[dim]{s.get('seconds', 0):.0f} s · {s.get('llm_calls', 0):.0f} LLM calls · "
                  f"{s.get('searches', 0):.0f} searches · saved to {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
