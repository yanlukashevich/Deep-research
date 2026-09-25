"""The demo server: one page, one streaming endpoint.

`GET /api/run` runs the agent and forwards every trace event to the browser as it happens
(Server-Sent Events), so the page shows the research as it goes instead of a spinner. The last
message of each run is the whole report as JSON plus its markdown, ready for the download button.

Keys live here, never in the page: the browser only ever talks to this server.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT
from .report import answer_lines, to_markdown
from .runner import IMPLEMENTED_MODES, run
from .schemas import Mode

log = logging.getLogger("taro.server")

WEB_DIR = ROOT / "web" / "dist"
NO_BUILD_PAGE = """<!doctype html><meta charset="utf-8"><title>TARO</title>
<body style="font:16px/1.6 system-ui;max-width:40em;margin:4em auto;padding:0 1em">
<h1>TARO</h1><p>The page has not been built yet. Run:</p>
<pre>cd web
npm install
npm run build</pre>
<p>Meanwhile the API works: <code>/api/run?question=...&amp;mode=v3</code>.</p>"""

MEDIA_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".js": "text/javascript",
               ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml"}

# fields that must not reach the browser: whole prompts and page texts, megabytes of them
DROP = {"messages", "response", "run_dir", "text"}


def slim(event: dict[str, Any]) -> dict[str, Any]:
    """The part of a trace event the page needs. Prompts and answers of single LLM calls are dropped."""
    out = {k: v for k, v in event.items() if k not in DROP}
    if out.get("kind") == "search":
        args = out.pop("args", {}) or {}
        out["query"] = args.get("query", "")
    if out.get("kind") == "facts":
        out["statements"] = (out.get("statements") or [])[:4]
    return out


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def stream_run(question: str, modes: list[Mode]):
    """Run every mode at once and yield SSE frames as the events arrive.

    The modes share the LLM semaphore, so running them together costs little more than the slowest
    one and the page can fill three columns side by side.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def listener_for(mode: Mode):
        def listen(event: dict[str, Any]) -> None:
            queue.put_nowait(sse("trace", {"mode": mode, **slim(event)}))
        return listen

    async def one(mode: Mode) -> None:
        try:
            report, run_dir = await run(question, mode, listener=listener_for(mode))
            queue.put_nowait(sse("report", {
                "mode": mode,
                "run": run_dir.name,
                "report": json.loads(report.model_dump_json()),
                "markdown": to_markdown(report),
                "lines": answer_lines(report),
            }))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # one broken mode must not kill the others
            log.exception("mode %s failed", mode)
            queue.put_nowait(sse("failed", {"mode": mode, "message": f"{type(e).__name__}: {e}"}))

    async def run_all() -> None:
        try:
            await asyncio.gather(*(one(m) for m in modes))
        finally:
            queue.put_nowait(sse("end", {}))
            queue.put_nowait(None)

    worker = asyncio.create_task(run_all())
    yield sse("hello", {"question": question, "modes": list(modes)})
    try:
        while True:
            frame = await queue.get()
            if frame is None:
                return
            yield frame
    finally:  # the browser closed the tab: stop the research instead of burning the API budget
        worker.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="TARO", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.get("/api/run")
    async def api_run(
        question: str = Query(min_length=2),
        mode: str = Query("v3", pattern="^(v1|v2|v3|all)$"),
    ) -> StreamingResponse:
        modes: list[Mode] = list(IMPLEMENTED_MODES) if mode == "all" else [mode]  # type: ignore[list-item]
        return StreamingResponse(
            stream_run(question.strip(), modes),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
                     "Connection": "keep-alive"},
        )

    @app.get("/api/health")
    async def api_health() -> dict[str, Any]:
        return {"ok": True, "modes": list(IMPLEMENTED_MODES), "web_built": WEB_DIR.exists()}

    if (WEB_DIR / "index.html").exists():
        assets = WEB_DIR / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def page(path: str) -> FileResponse:  # one page, any route
            file = (WEB_DIR / path).resolve()
            # only files of the built page: a path like ../../.env must not be served
            if path and file.is_file() and file.is_relative_to(WEB_DIR.resolve()):
                # Windows has no registry entry for woff2, and a font served as octet-stream
                # is refused by the browser
                return FileResponse(file, media_type=MEDIA_TYPES.get(file.suffix))
            return FileResponse(WEB_DIR / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        async def no_build() -> HTMLResponse:
            return HTMLResponse(NO_BUILD_PAGE)

    return app


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
