"""The step log of a run: every step is written to trace.jsonl as it happens.

Kept apart from `report.py` because search and llm record steps while report.py, which builds the
final document, imports them back through the confidence score.
"""
import json
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

Listener = Callable[[dict[str, Any]], None]


class Trace:
    """Records every step of a run.

    Each event is appended to trace.jsonl right away (so a crashed run still leaves a log) and passed
    to an optional listener (the web UI streams these live). `stats` counts calls, tokens and cache hits.
    """

    def __init__(self, path: Path | None = None, listener: Listener | None = None):
        self.path = path
        self.listener = listener
        self.stats: Counter[str] = Counter()
        self.t0 = time.monotonic()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def event(self, kind: str, **data: Any) -> None:
        record = {"t": round(time.monotonic() - self.t0, 3), "kind": kind, **data}
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        if self.listener:
            self.listener(record)

    def count(self, key: str, n: float = 1) -> None:
        self.stats[key] += n

    def elapsed(self) -> float:
        return time.monotonic() - self.t0


def new_run_dir(runs_dir: Path, mode: str) -> Path:
    """runs/<YYYYmmdd-HHMMSS>-<mode>/, with a numeric suffix if that already exists."""
    base = runs_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{mode}"
    path, i = base, 1
    while path.exists():
        i += 1
        path = base.with_name(f"{base.name}-{i}")
    path.mkdir(parents=True)
    return path
