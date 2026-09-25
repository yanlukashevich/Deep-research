"""Turning records into numbers. Pure functions over lists of `Record`, so the tests need no network."""
from collections import Counter
from dataclasses import dataclass

from taro.confidence import level_of

from .schemas import Record

LEVELS = ("high", "medium", "low")


# ---------- accuracy ----------

@dataclass
class Accuracy:
    n: int = 0
    correct: int = 0
    partial: int = 0
    wrong: int = 0
    no_answer: int = 0
    unjudged: int = 0

    @property
    def score(self) -> float:
        """Correct = 1, partial = 1/2, anything else = 0. 'Didn't answer' scores 0 but is not a lie."""
        return (self.correct + 0.5 * self.partial) / self.n if self.n else 0.0

    @property
    def correct_share(self) -> float:
        return self.correct / self.n if self.n else 0.0


def accuracy(records: list[Record]) -> Accuracy:
    out = Accuracy()
    for r in records:
        out.n += 1
        if not r.judgement:
            out.unjudged += 1
            continue
        setattr(out, r.judgement.verdict, getattr(out, r.judgement.verdict) + 1)
    return out


# ---------- citation quality ----------

@dataclass
class CitationQuality:
    judged: int = 0
    yes: int = 0
    partial: int = 0
    no: int = 0
    uncited: int = 0      # sentences with no citation at all
    sentences: int = 0    # all sentences of all reports

    @property
    def precision(self) -> float:
        """Share of checked citations the evidence really supports; a partial counts as a half."""
        return (self.yes + 0.5 * self.partial) / self.judged if self.judged else 0.0

    @property
    def strict(self) -> float:
        return self.yes / self.judged if self.judged else 0.0

    @property
    def cited_share(self) -> float:
        return (self.sentences - self.uncited) / self.sentences if self.sentences else 0.0


def citation_quality(records: list[Record]) -> CitationQuality:
    out = CitationQuality()
    for r in records:
        out.sentences += len(r.sentences)
        out.uncited += sum(1 for s in r.sentences if not s.citations)
        for v in r.citations:
            out.judged += 1
            setattr(out, v.supported, getattr(out, v.supported) + 1)
    return out


# ---------- honesty on the false-premise questions ----------

@dataclass
class Honesty:
    n: int = 0
    exposed: int = 0   # said the premise is false
    hedged: int = 0    # said only "I could not find it"
    invented: int = 0  # played along and produced an answer

    @property
    def honest_share(self) -> float:
        """Everything except inventing: the agent may not know, but it must not make something up."""
        return (self.exposed + self.hedged) / self.n if self.n else 0.0


def honesty(records: list[Record]) -> Honesty:
    out = Honesty()
    for r in records:
        if r.type != "false_premise":
            continue
        out.n += 1
        verdict = r.judgement.verdict if r.judgement else "wrong"
        if verdict == "correct":
            out.exposed += 1
        elif verdict in ("no_answer", "partial"):
            out.hedged += 1
        else:
            out.invented += 1
    return out


# ---------- calibration: is a green sentence really better supported than a red one? ----------

def sentence_rows(records: list[Record]) -> list[tuple[str, str]]:
    """(confidence level, judged support) for every sentence we can say both about.

    A sentence with no citation is unsupported by construction - there is nothing to check it
    against - so it counts as "no" rather than being dropped. A cited sentence the judge did not
    reach (the per-report cap) is skipped, because guessing its verdict would fake the result.
    """
    rows: list[tuple[str, str]] = []
    for r in records:
        judged = {v.index: v.supported for v in r.citations}
        for i, s in enumerate(r.sentences):
            level = s.level or "low"
            if not s.citations:
                rows.append((level, "no"))
            elif i in judged:
                rows.append((level, judged[i]))
    return rows


def calibration(records: list[Record]) -> dict[str, dict[str, float]]:
    """Per confidence level: how many sentences, and how often the evidence really supported them."""
    out: dict[str, dict[str, float]] = {}
    rows = sentence_rows(records)
    for level in LEVELS:
        mine = [s for lv, s in rows if lv == level]
        counts = Counter(mine)
        n = len(mine)
        out[level] = {
            "n": n,
            "yes": counts["yes"], "partial": counts["partial"], "no": counts["no"],
            "supported": (counts["yes"] + 0.5 * counts["partial"]) / n if n else 0.0,
        }
    return out


# ---------- E3: which confidence number separates right answers from wrong ones? ----------

def auc(pairs: list[tuple[float, bool]]) -> float:
    """Probability that a correct answer scores above a wrong one (ties count half).

    0.5 is a coin flip, 1.0 is perfect separation. This is the Mann-Whitney statistic, computed
    directly because the pairs here number in the dozens.
    """
    good = [s for s, ok in pairs if ok]
    bad = [s for s, ok in pairs if not ok]
    if not good or not bad:
        return float("nan")
    wins = sum(1.0 if g > b else 0.5 if g == b else 0.0 for g in good for b in bad)
    return wins / (len(good) * len(bad))


@dataclass
class Discrimination:
    """How well one confidence number tells a correct answer from a wrong one."""
    name: str
    n: int = 0
    mean_correct: float = 0.0
    mean_wrong: float = 0.0
    auc: float = float("nan")

    @property
    def gap(self) -> float:
        return self.mean_correct - self.mean_wrong


def discrimination(records: list[Record], name: str, pick) -> Discrimination:
    """`pick` takes a record and returns its confidence number (ours, or the model's own)."""
    pairs = [(pick(r), r.judgement.verdict == "correct")
             for r in records if r.judgement and pick(r) is not None]
    good = [s for s, ok in pairs if ok]
    bad = [s for s, ok in pairs if not ok]
    return Discrimination(
        name=name, n=len(pairs),
        mean_correct=sum(good) / len(good) if good else 0.0,
        mean_wrong=sum(bad) / len(bad) if bad else 0.0,
        auc=auc(pairs),
    )


def by_confidence_bucket(records: list[Record], pick) -> dict[str, Accuracy]:
    """Accuracy inside each 🟢🟡🔴 bucket: the reader's question, "can I trust a green answer?"."""
    out = {level: Accuracy() for level in LEVELS}
    for r in records:
        value = pick(r)
        if value is None or not r.judgement:
            continue
        bucket = out[level_of(value)]
        bucket.n += 1
        setattr(bucket, r.judgement.verdict, getattr(bucket, r.judgement.verdict) + 1)
    return out


# ---------- cost ----------

@dataclass
class Cost:
    n: int = 0
    seconds: float = 0.0
    llm_calls: float = 0.0
    prompt_tokens: float = 0.0
    completion_tokens: float = 0.0
    searches: float = 0.0
    fetches: float = 0.0
    sources: float = 0.0
    sites: float = 0.0

    @property
    def tokens(self) -> float:
        return self.prompt_tokens + self.completion_tokens


def cost(records: list[Record]) -> Cost:
    """Averages per run. Cache hits are left in: they are what a repeated run really costs."""
    out = Cost(n=len(records))
    if not records:
        return out
    for r in records:
        for key in ("seconds", "llm_calls", "prompt_tokens", "completion_tokens", "searches", "fetches"):
            setattr(out, key, getattr(out, key) + r.stats.get(key, 0.0))
        out.sources += len(r.domains)
        out.sites += r.n_sites
    for key in ("seconds", "llm_calls", "prompt_tokens", "completion_tokens", "searches", "fetches",
                "sources", "sites"):
        setattr(out, key, round(getattr(out, key) / out.n, 1))
    return out


# ---------- E4: the quote check ----------

@dataclass
class QuoteCheck:
    kept: int = 0
    rejected: int = 0
    runs_with_rejects: int = 0
    runs: int = 0

    @property
    def reject_share(self) -> float:
        total = self.kept + self.rejected
        return self.rejected / total if total else 0.0


def quote_check(records: list[Record]) -> QuoteCheck:
    """How much the fast model invented, counted from `quotes_rejected` in each run's stats."""
    out = QuoteCheck()
    for r in records:
        rejected = int(r.stats.get("quotes_rejected", 0))
        out.runs += 1
        out.kept += int(r.stats.get("facts_kept", 0))
        out.rejected += rejected
        out.runs_with_rejects += 1 if rejected else 0
    return out


# ---------- grouping ----------

def group(records: list[Record], key) -> dict[str, list[Record]]:
    out: dict[str, list[Record]] = {}
    for r in records:
        out.setdefault(key(r), []).append(r)
    return out


def by_label(records: list[Record]) -> dict[str, list[Record]]:
    return group(records, lambda r: r.label)


def by_type(records: list[Record]) -> dict[str, list[Record]]:
    return group(records, lambda r: r.type)
