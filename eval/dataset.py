"""Loading the question set and the records of finished runs."""
import json
from collections.abc import Iterable

from .schemas import QUESTIONS, RECORDS, RESULTS, Item, Record


def load_questions(path=QUESTIONS, types: Iterable[str] | None = None, limit: int | None = None) -> list[Item]:
    items = [Item.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if types:
        wanted = set(types)
        items = [i for i in items if i.type in wanted]
    return items[:limit] if limit else items


def seed_records() -> None:
    """Unpack the committed `raw.jsonl` into `records/` the first time it is needed.

    `records/` is the resume file and is not committed (one file per run, 108 of them), while
    `raw.jsonl` is the same content in one committed file. Without this a fresh clone has no
    records at all, so `--report` would rebuild the tables out of nothing and overwrite the
    committed results with empty ones.
    """
    raw = RESULTS / "raw.jsonl"
    if not raw.exists() or any(RECORDS.glob("*.json")):
        return
    for line in raw.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            save_record(Record.model_validate_json(line))
        except Exception:  # a record this version can no longer read: it will simply be re-run
            continue


def load_record(qid: str, label: str) -> Record | None:
    seed_records()
    path = RECORDS / f"{label}-{qid}.json"
    if not path.exists():
        return None
    try:
        return Record.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # a half-written file from an interrupted run: redo it
        return None


def save_record(record: Record) -> None:
    RECORDS.mkdir(parents=True, exist_ok=True)
    record.path().write_text(record.model_dump_json(indent=2), encoding="utf-8")


def all_records() -> list[Record]:
    """Every stored record, sorted so tables come out in a stable order."""
    seed_records()
    out = []
    for path in sorted(RECORDS.glob("*.json")):
        try:
            out.append(Record.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(out, key=lambda r: (r.label, r.qid))


def write_raw(records: list[Record], path) -> None:
    """One JSON object per record: the whole evaluation in a file a reviewer can read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n")
