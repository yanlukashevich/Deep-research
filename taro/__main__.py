"""CLI:  python -m taro "question" [--mode v1|v2|v3]
         python -m taro serve [--host H] [--port P]
"""
import argparse
import asyncio
import sys

from rich.console import Console
from rich.markdown import Markdown

from .confidence import MARKS, level_of
from .progress import describe
from .report import marked_answer
from .runner import IMPLEMENTED_MODES, run


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1250
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "serve":
        return serve_command(argv[1:])

    parser = argparse.ArgumentParser(prog="python -m taro", description="TARO deep-research agent")
    parser.add_argument("question", help='the question, or "serve" to start the web UI')
    parser.add_argument("--mode", choices=["v1", "v2", "v3"], default="v3",
                        help="v1 bare LLM, v2 simple RAG, v3 research agent")
    args = parser.parse_args(argv)

    console = Console()
    if args.mode not in IMPLEMENTED_MODES:
        console.print(f"[red]Mode {args.mode} is not implemented yet. Available: {', '.join(IMPLEMENTED_MODES)}")
        return 2

    def show_step(event: dict) -> None:
        line = describe(event)
        if line:
            console.print(f"[dim]{event['t']:6.1f}s  {line}")

    console.print(f"[bold]{args.question}[/bold] [dim]({args.mode})")
    report, run_dir = asyncio.run(run(args.question, args.mode, listener=show_step))

    console.rule(f"[bold]{args.mode}")
    console.print(Markdown(marked_answer(report)))
    if report.confidence is not None:
        console.print(f"\nconfidence [bold]{report.confidence:.2f}[/bold] "
                      f"{MARKS[level_of(report.confidence)]} [dim]{report.confidence_why}")
    if report.sources:
        console.print()
        for s in report.sources:
            console.print(f"[dim][{s.id}] {s.title} · {s.domain} · {s.url}")
    s = report.stats
    console.print(f"\n[dim]{s.get('seconds', 0):.0f} s · {s.get('llm_calls', 0):.0f} LLM calls · "
                  f"{s.get('searches', 0):.0f} searches · saved to {run_dir}")
    return 0


def serve_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m taro serve", description="TARO web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    from .server import WEB_DIR, serve
    console = Console()
    console.print(f"[bold]TARO[/bold] on http://{args.host}:{args.port}  [dim](Ctrl+C to stop)")
    if not (WEB_DIR / "index.html").exists():
        console.print("[yellow]The web page is not built: run `npm install && npm run build` in web/")
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
