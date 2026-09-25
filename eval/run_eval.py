"""Runs the evaluation and writes the result tables.

    python -m eval.run_eval                 # everything that is not already on disk
    python -m eval.run_eval --only e1       # just the main comparison
    python -m eval.run_eval --report        # rebuild the tables from stored records, run nothing
    python -m eval.run_eval --force         # ignore stored records and run everything again

Experiments:
  E1  v1 vs v2 vs v3 on all questions           - does each step earn its cost?
  E2  v3 with 1, 2 and 3 rounds                 - does the critic loop pay off?
  E3  our confidence formula vs asking the model - which number tells right from wrong?
  E4  the quote check                            - how many invented quotes does it catch?

Everything is written to `eval/results/`: `results.md` (the tables), `raw.jsonl` (every record),
`judge_sample.md` (decisions to check by hand) and `failures.md` (every answer that was not correct).
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from taro.confidence import MARKS, level_of

from .dataset import all_records, load_questions, write_raw
from .harness import V1, V2, V3, V3_R1, V3_R2, Config, run_all
from .judge import citation_items
from .metrics import (Accuracy, accuracy, by_confidence_bucket, by_label, by_type, calibration,
                      citation_quality, cost, discrimination, honesty, quote_check)
from .schemas import RESULTS, Item, Record

E2_QUESTIONS = 12  # multi-step and fresh questions only: the ones where another round could help


def pct(x: float) -> str:
    return "—" if x != x else f"{100 * x:.0f}%"


def num(x: float, digits: int = 2) -> str:
    return "—" if x != x else f"{x:.{digits}f}"


def table(header: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(header) + " |"
    rule = "|" + "|".join("---" for _ in header) + "|"
    return "\n".join([line, rule] + ["| " + " | ".join(r) + " |" for r in rows])


# ---------- which runs each experiment needs ----------

def e2_items(items: list[Item]) -> list[Item]:
    """The E2 subset: fresh and multi-step questions, interleaved so both types are represented."""
    fresh = [i for i in items if i.type == "fresh"]
    multihop = [i for i in items if i.type == "multihop"]
    mixed: list[Item] = []
    for a, b in zip(fresh, multihop):
        mixed += [a, b]
    return mixed[:E2_QUESTIONS]


def plan(only: set[str], items: list[Item]) -> list[tuple[list[Item], list[Config]]]:
    """(questions, configurations) pairs to run. E3 and E4 need no runs of their own:
    E3 uses the self-confidence call the harness already makes, E4 the counters in each run's stats."""
    jobs = []
    if "e1" in only:
        jobs.append((items, [V1, V2, V3]))
    if "e2" in only:
        jobs.append((e2_items(items), [V3_R1, V3_R2]))
    return jobs


# ---------- the tables ----------

def main_table(records: list[Record]) -> str:
    rows = []
    for label in ("v1", "v2", "v3"):
        mine = by_label(records).get(label, [])
        if not mine:
            continue
        acc, cit, c = accuracy(mine), citation_quality(mine), cost(mine)
        conf = [r.confidence for r in mine if r.confidence is not None]
        rows.append([
            f"**{label}**", str(acc.n), pct(acc.correct_share), num(acc.score),
            pct(cit.cited_share), pct(cit.precision),
            num(sum(conf) / len(conf) if conf else 0.0),
            num(c.seconds, 0), num(c.llm_calls, 1), f"{c.tokens:,.0f}", num(c.sites, 1),
        ])
    return table(["version", "n", "correct", "score", "sentences cited", "citations supported",
                  "avg confidence", "s/run", "LLM calls", "tokens", "sites/run"], rows)


def per_type_table(records: list[Record]) -> str:
    labels = [l for l in ("v1", "v2", "v3") if l in by_label(records)]
    rows = []
    for qtype, group in sorted(by_type(records).items()):
        row = [qtype, str(len({r.qid for r in group}))]
        for label in labels:
            acc = accuracy([r for r in group if r.label == label])
            row.append(f"{num(acc.score)} ({acc.correct}/{acc.n})")
        rows.append(row)
    return table(["question type", "n", *[f"{l} score" for l in labels]], rows)


def honesty_table(records: list[Record]) -> str:
    rows = []
    for label in ("v1", "v2", "v3"):
        mine = by_label(records).get(label, [])
        h = honesty(mine)
        if not h.n:
            continue
        rows.append([f"**{label}**", str(h.n), str(h.exposed), str(h.hedged), str(h.invented),
                     pct(h.honest_share)])
    return table(["version", "false-premise questions", "said the premise is false",
                  "only 'not found'", "invented an answer", "did not invent"], rows)


def calibration_table(records: list[Record]) -> str:
    rows = []
    for level, r in calibration(records).items():
        if not r["n"]:
            continue
        rows.append([f"{MARKS[level]} {level}", f"{r['n']:.0f}", f"{r['yes']:.0f}",
                     f"{r['partial']:.0f}", f"{r['no']:.0f}", pct(r["supported"])])
    return table(["sentence mark", "sentences", "supported", "partly", "not supported",
                  "support score"], rows)


def bucket_table(records: list[Record], pick) -> str:
    rows = []
    for level, acc in by_confidence_bucket(records, pick).items():
        if not acc.n:
            continue
        rows.append([f"{MARKS[level]} {level}", str(acc.n), pct(acc.correct_share), num(acc.score)])
    return table(["report confidence", "answers", "correct", "score"], rows)


def rounds_table(records: list[Record], items: list[Item]) -> str:
    wanted = {i.id for i in e2_items(items)}
    rows = []
    for label in ("v3-r1", "v3-r2", "v3"):
        mine = [r for r in by_label(records).get(label, []) if r.qid in wanted]
        if not mine:
            continue
        acc, cit, c = accuracy(mine), citation_quality(mine), cost(mine)
        conf = [r.confidence for r in mine if r.confidence is not None]
        rounds = sum(r.stats.get("rounds", 0) for r in mine) / len(mine)
        rows.append([f"**{label}**", str(acc.n), pct(acc.correct_share), num(acc.score),
                     pct(cit.precision), num(sum(conf) / len(conf) if conf else 0.0),
                     num(rounds, 1), num(c.sources, 1), num(c.seconds, 0), f"{c.tokens:,.0f}"])
    return table(["rounds allowed", "n", "correct", "score", "citations supported", "avg confidence",
                  "rounds used", "sources/run", "s/run", "tokens"], rows)


def e3_table(records: list[Record]) -> str:
    ours = discrimination(records, "our formula", lambda r: r.confidence)
    theirs = discrimination(records, "the model's own", lambda r: r.self_confidence)
    rows = [[d.name, str(d.n), num(d.mean_correct), num(d.mean_wrong), num(d.gap), num(d.auc)]
            for d in (ours, theirs)]
    return table(["confidence number", "answers", "mean when correct", "mean when wrong",
                  "gap", "AUC"], rows)


def e4_table(records: list[Record]) -> str:
    rows = []
    for label in ("v3-r1", "v3-r2", "v3"):
        mine = by_label(records).get(label, [])
        q = quote_check(mine)
        if not q.runs:
            continue
        rows.append([f"**{label}**", str(q.runs), f"{q.kept}", f"{q.rejected}", pct(q.reject_share),
                     f"{q.runs_with_rejects}/{q.runs}"])
    return table(["configuration", "runs", "quotes kept", "quotes rejected", "rejected share",
                  "runs with a rejection"], rows)


def rejected_examples(records: list[Record], limit: int = 5) -> list[str]:
    """Real quotes the check threw out, read back from the traces of the runs that produced them."""
    out: list[str] = []
    for r in records:
        if not r.run_dir or int(r.stats.get("quotes_rejected", 0)) == 0:
            continue
        trace = Path(r.run_dir) / "trace.jsonl"
        if not trace.exists():
            continue
        for line in trace.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("kind") != "quote_rejected":
                continue
            quote = " ".join(str(event.get("quote", "")).split())[:200]
            out.append(f"- `{r.qid}` {event.get('url', '')}\n  - claimed quote: \"{quote}\"\n"
                       f"  - statement it was backing: {event.get('statement', '')}")
            if len(out) >= limit:
                return out
    return out


# ---------- the documents ----------

def results_md(records: list[Record], items: list[Item]) -> str:
    e1 = [r for r in records if r.label in ("v1", "v2", "v3")]
    v3 = by_label(records).get("v3", [])
    both = [r for r in e1 if r.confidence is not None and r.self_confidence is not None]
    errors = [r for r in records if r.error]
    parts = [
        "# Evaluation results",
        "",
        f"{len({r.qid for r in records})} questions · {len(records)} runs · "
        f"{len({r.label for r in records})} configurations. "
        f"Generated by `python -m eval.run_eval`. Raw records: `raw.jsonl`.",
        "",
        "The judge is the main model (`openai/gpt-oss-120b`) and is asked three separate questions per run: "
        "is the answer right (against a gold answer written by hand), does each cited sentence really "
        "follow from the quotes it cites, and - with the sources hidden - how sure is the model itself. "
        "`judge_sample.md` holds decisions to check by hand and `../judge_check.md` what came of "
        "checking them; `../error_analysis.md` sorts every failure below into causes.",
        "",
        "## E1 — v1 vs v2 vs v3",
        "",
        "`score` counts a correct answer as 1 and a partly correct one as 1/2. `citations supported` is the "
        "share of cited sentences whose own quotes really back them, judged against the evidence only.",
        "",
        main_table(e1),
        "",
        "### By question type",
        "",
        per_type_table(e1),
        "",
        "### Honesty on the false-premise questions",
        "",
        honesty_table(e1),
        "",
        "## E2 — how many rounds does v3 need?",
        "",
        f"The same {E2_QUESTIONS} questions (multi-step and fresh) with the round budget set to 1, 2 and 3. "
        "One round means no critic at all: plan, search, read, write.",
        "",
        rounds_table(records, items),
        "",
        "## E3 — our confidence formula vs asking the model",
        "",
        "Both numbers are about the same v1/v2/v3 answers. `AUC` is the chance that a correct answer gets a "
        "higher number than a wrong one: 0.5 is a coin flip, 1.0 is perfect.",
        "",
        e3_table(both),
        "",
        "### Can a reader trust the colour?",
        "",
        "Our formula, per bucket:",
        "",
        bucket_table(both, lambda r: r.confidence),
        "",
        "The model's own number, per bucket:",
        "",
        bucket_table(both, lambda r: r.self_confidence),
        "",
        "### Per-sentence calibration (v3)",
        "",
        "Every sentence of every v3 answer, grouped by the mark the formula gave it. A sentence with no "
        "citation counts as unsupported, because nothing backs it.",
        "",
        calibration_table(v3),
        "",
        "## E4 — the quote check",
        "",
        "Plain code fuzzy-searches every quote the fast model returns in the page it claims to come from "
        "(`rapidfuzz`, threshold 85). A quote that is not there means the fact goes in the bin.",
        "",
        e4_table(records),
        "",
        "`python -m eval.quote_audit` scores every rejected quote against its page again and sorts the "
        "rejections by what they actually were - see `quote_audit.md`.",
        "",
    ]
    examples = rejected_examples([r for r in records if r.mode == "v3"])
    if examples:
        parts += ["### Quotes that were thrown out", "", *examples, ""]
    if errors:
        parts += ["## Runs that failed", "",
                  *[f"- `{r.label}` / `{r.qid}`: {r.error}" for r in errors], ""]
    return "\n".join(parts)


def _key_points(record: Record) -> list[str]:
    for item in load_questions():
        if item.id == record.qid:
            return item.key_points
    return []


def _spread(rows: list, key, per_class: int) -> list:
    """A sample that covers every verdict, not just the common one.

    Taking every Nth decision would fill the page with "correct": the decisions worth checking by
    hand are the rare ones, so take up to `per_class` of each verdict and shuffle them back together.
    """
    buckets: dict[str, list] = {}
    for row in rows:
        buckets.setdefault(key(row), []).append(row)
    out = []
    for name in sorted(buckets):
        group = buckets[name]
        step = max(1, len(group) // per_class)
        out += group[::step][:per_class]
    return out


def judge_sample_md(records: list[Record], per_class: int = 3) -> str:
    """Decisions laid out for a human to check, spread over every verdict the judge can give."""
    parts = ["# Judge decisions to check by hand", "",
             "Up to three decisions of each kind, with everything the judge saw. Reading these is how we "
             "find out whether the numbers in `results.md` mean anything; `judge_check.md` holds what a "
             "human made of them.", "",
             "## Answer verdicts", ""]
    judged = [r for r in records if r.judgement]
    for r in _spread(judged, lambda r: r.judgement.verdict, per_class):
        answer = " ".join(r.answer.split())
        parts += [f"### `{r.label}` / `{r.qid}` ({r.type}) — **{r.judgement.verdict}**"
                  f"{' (refused)' if r.judgement.refused else ''}",
                  "", f"- question: {r.question}",
                  f"- gold key points: {', '.join(_key_points(r)) or '(none)'}",
                  f"- answer: {answer[:600]}{'…' if len(answer) > 600 else ''}",
                  f"- judge's reason: {r.judgement.reason}",
                  f"- key points it found: {', '.join(r.judgement.covered) or '(none)'}", ""]
    parts += ["## Citation verdicts", ""]
    pairs = [(r, v) for r in records for v in r.citations]
    for r, v in _spread(pairs, lambda rv: rv[1].supported, per_class):
        sentence = r.sentences[v.index] if v.index < len(r.sentences) else None
        # exactly the evidence the judge was given, or a hand-check would check the wrong thing
        evidence = next((e for i, _, e in citation_items(r) if i == v.index), [])
        parts += [f"### `{r.label}` / `{r.qid}` sentence {v.index} — **{v.supported}**",
                  "", f"- sentence: {sentence.text if sentence else '(missing)'}",
                  f"- mark the formula gave it: {MARKS.get(sentence.level or 'low', '')} "
                  f"{sentence.score if sentence else ''}",
                  *[f'- quote: "{" ".join(q.split())[:300]}"' for q in evidence],
                  f"- judge's reason: {v.reason}", ""]
    return "\n".join(parts)


def failures_md(records: list[Record]) -> str:
    """Every answer that was not judged correct, with its run folder - the input to the error analysis."""
    parts = ["# Every answer that was not correct", "",
             "Sorted by version. `run` is the folder with `report.md` and `trace.jsonl` for that run.", ""]
    for label, group in sorted(by_label(records).items()):
        bad = [r for r in group if not r.judgement or r.judgement.verdict != "correct"]
        parts += [f"## {label} — {len(bad)} of {len(group)}", ""]
        for r in bad:
            answer = " ".join(r.answer.split())
            verdict = r.judgement.verdict if r.judgement else f"not judged ({r.error})"
            parts += [f"### `{r.qid}` ({r.type}) — {verdict}",
                      "", f"- question: {r.question}",
                      f"- answer: {answer[:500]}{'…' if len(answer) > 500 else ''}",
                      f"- judge: {r.judgement.reason if r.judgement else '—'}",
                      f"- confidence: {r.confidence} ({r.confidence_why})",
                      f"- not found: {', '.join(r.not_found) or '—'}",
                      f"- run: `{r.run_dir}`", ""]
    return "\n".join(parts)


def write_results(items: list[Item]) -> None:
    records = all_records()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "results.md").write_text(results_md(records, items), encoding="utf-8")
    (RESULTS / "judge_sample.md").write_text(judge_sample_md(records), encoding="utf-8")
    (RESULTS / "failures.md").write_text(failures_md(records), encoding="utf-8")
    write_raw(records, RESULTS / "raw.jsonl")
    print(f"\n{len(records)} records -> {RESULTS}")
    print(results_md(records, items).split("## E2")[0])


# ---------- CLI ----------

def progress(done: int, total: int, record: Record) -> None:
    verdict = record.judgement.verdict if record.judgement else (record.error or "?")[:40]
    conf = "—" if record.confidence is None else f"{record.confidence:.2f}"
    print(f"[{done:>3}/{total}] {record.label:<6} {record.qid:<5} {verdict:<12} conf {conf}", flush=True)


async def main_async(args) -> None:
    items = load_questions(types=args.types, limit=args.limit)
    only = set(args.only.split(",")) if args.only else {"e1", "e2"}
    if not args.report:
        for questions, configs in plan(only, items):
            names = "/".join(c.label for c in configs)
            print(f"\n=== {len(questions)} questions x {names} ===", flush=True)
            await run_all(questions, configs, concurrency=args.concurrency,
                          force=args.force, on_done=progress)
    write_results(load_questions())


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # the Windows console is cp1250
    p = argparse.ArgumentParser(description="Run the TARO evaluation and write the result tables.")
    p.add_argument("--only", help="comma-separated experiments to run: e1,e2 (e3 and e4 need no runs)")
    p.add_argument("--types", help="comma-separated question types to include")
    p.add_argument("--limit", type=int, help="use only the first N questions")
    p.add_argument("--concurrency", type=int, default=2, help="runs at a time (default 2)")
    p.add_argument("--force", action="store_true", help="re-run questions that already have a record")
    p.add_argument("--report", action="store_true", help="only rebuild the tables from stored records")
    args = p.parse_args()
    args.types = args.types.split(",") if args.types else None
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
