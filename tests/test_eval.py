"""The evaluation: the question set, the judge's prompt building, and the metrics.

No network. The judge is exercised against a scripted fake model, the same trick `test_v3.py` uses.
"""
import json

import pytest

from eval import metrics
from eval.dataset import load_questions
from eval.judge import citation_items, judge_answer, judge_citations, self_confidence
from eval.run_eval import e2_items, main_table, results_md
from eval.schemas import CitationVerdict, Item, Judgement, Record, SentenceRec


# ---------- the question set ----------

def test_questions_load_and_cover_every_type():
    items = load_questions()
    assert len(items) >= 25
    types = {i.type for i in items}
    assert types == {"multihop", "fresh", "open", "false_premise"}
    assert sum(1 for i in items if i.lang == "ru") >= 5
    assert all(i.gold.strip() for i in items)
    assert all(i.expect == "refuse" for i in items if i.type == "false_premise")


def test_fresh_questions_carry_the_page_the_gold_was_checked_against():
    for item in load_questions(types=["fresh"]):
        assert item.sources, f"{item.id} has no verification source"
        assert item.sources[0].startswith("http")


def test_question_ids_are_unique():
    ids = [i.id for i in load_questions()]
    assert len(ids) == len(set(ids))


def test_e2_subset_mixes_fresh_and_multihop():
    picked = e2_items(load_questions())
    types = {i.type for i in picked}
    assert types == {"fresh", "multihop"}
    assert len(picked) == 12


# ---------- records to work with ----------

def make_record(label="v3", qid="q1", verdict="correct", levels=("high", "low"),
                supported=("yes",), stats=None, self_conf=None, conf=0.8) -> Record:
    sentences = [SentenceRec(text=f"sentence {i}", citations=[1] if lv != "low" else [],
                             score=0.8 if lv == "high" else 0.0, level=lv)
                 for i, lv in enumerate(levels)]
    citations = [CitationVerdict(index=i, supported=s)
                 for i, s in enumerate(supported) if sentences[i].citations]
    return Record(qid=qid, label=label, mode="v3", question="q?", type="multihop", lang="en",
                  answer="sentence 0 [1] sentence 1", sentences=sentences,
                  domains=["a.com", "b.com"], quotes={"1": ["a quote"]},
                  confidence=conf, judgement=Judgement(verdict=verdict), citations=citations,
                  self_confidence=self_conf, stats=stats or {"seconds": 10, "llm_calls": 5})


# ---------- accuracy ----------

def test_accuracy_counts_partials_as_half():
    records = [make_record(verdict=v, qid=str(i)) for i, v in
               enumerate(["correct", "correct", "partial", "wrong", "no_answer"])]
    acc = metrics.accuracy(records)
    assert (acc.correct, acc.partial, acc.wrong, acc.no_answer) == (2, 1, 1, 1)
    assert acc.score == pytest.approx(2.5 / 5)
    assert acc.correct_share == pytest.approx(0.4)


def test_accuracy_of_nothing_is_zero_not_a_crash():
    acc = metrics.accuracy([])
    assert acc.score == 0.0 and acc.n == 0


def test_unjudged_records_count_against_the_score():
    record = make_record()
    record.judgement = None
    acc = metrics.accuracy([record])
    assert acc.unjudged == 1 and acc.score == 0.0


# ---------- citation quality ----------

def test_citation_quality_scores_partial_as_half():
    r = make_record(levels=("high", "high", "high"), supported=("yes", "partial", "no"))
    q = metrics.citation_quality([r])
    assert (q.yes, q.partial, q.no, q.judged) == (1, 1, 1, 3)
    assert q.precision == pytest.approx(1.5 / 3)
    assert q.strict == pytest.approx(1 / 3)


def test_cited_share_counts_sentences_without_citations():
    r = make_record(levels=("high", "low", "low"), supported=("yes",))
    q = metrics.citation_quality([r])
    assert q.sentences == 3 and q.uncited == 2
    assert q.cited_share == pytest.approx(1 / 3)


# ---------- honesty ----------

def test_honesty_separates_hedging_from_inventing():
    def fp(verdict):
        r = make_record(verdict=verdict)
        r.type = "false_premise"
        return r
    h = metrics.honesty([fp("correct"), fp("no_answer"), fp("wrong"), make_record()])
    assert (h.n, h.exposed, h.hedged, h.invented) == (3, 1, 1, 1)
    assert h.honest_share == pytest.approx(2 / 3)


# ---------- calibration ----------

def test_uncited_sentences_count_as_unsupported():
    rows = metrics.sentence_rows([make_record(levels=("high", "low"), supported=("yes",))])
    assert rows == [("high", "yes"), ("low", "no")]


def test_a_cited_sentence_the_judge_never_saw_is_skipped():
    r = make_record(levels=("high", "high"), supported=("yes",))
    r.citations = [CitationVerdict(index=0, supported="yes")]  # sentence 1 was past the cap
    assert metrics.sentence_rows([r]) == [("high", "yes")]


def test_calibration_groups_by_mark():
    r = make_record(levels=("high", "high", "low"), supported=("yes", "no"))
    table = metrics.calibration([r])
    assert table["high"]["n"] == 2 and table["high"]["supported"] == pytest.approx(0.5)
    assert table["low"]["n"] == 1 and table["low"]["supported"] == 0.0
    assert table["medium"]["n"] == 0


# ---------- E3 ----------

def test_auc_is_one_when_correct_answers_always_score_higher():
    assert metrics.auc([(0.9, True), (0.8, True), (0.3, False)]) == 1.0


def test_auc_is_half_on_ties_and_nan_without_both_classes():
    assert metrics.auc([(0.5, True), (0.5, False)]) == 0.5
    assert metrics.auc([(0.9, True)]) != metrics.auc([(0.9, True)])  # nan != nan


def test_discrimination_compares_the_two_numbers():
    records = [make_record(qid="1", verdict="correct", conf=0.9, self_conf=0.5),
               make_record(qid="2", verdict="wrong", conf=0.2, self_conf=0.9)]
    ours = metrics.discrimination(records, "ours", lambda r: r.confidence)
    theirs = metrics.discrimination(records, "theirs", lambda r: r.self_confidence)
    assert ours.gap == pytest.approx(0.7) and ours.auc == 1.0
    assert theirs.gap == pytest.approx(-0.4) and theirs.auc == 0.0


def test_buckets_follow_the_confidence_thresholds():
    records = [make_record(qid="1", conf=0.9), make_record(qid="2", conf=0.6),
               make_record(qid="3", conf=0.1)]
    buckets = metrics.by_confidence_bucket(records, lambda r: r.confidence)
    assert [buckets[l].n for l in ("high", "medium", "low")] == [1, 1, 1]


# ---------- cost and E4 ----------

def test_cost_averages_over_runs():
    c = metrics.cost([make_record(qid="1", stats={"seconds": 10, "llm_calls": 4}),
                      make_record(qid="2", stats={"seconds": 20, "llm_calls": 6})])
    assert c.seconds == 15.0 and c.llm_calls == 5.0 and c.sites == 2.0


def test_quote_check_counts_rejections():
    q = metrics.quote_check([make_record(qid="1", stats={"facts_kept": 9, "quotes_rejected": 1}),
                             make_record(qid="2", stats={"facts_kept": 10})])
    assert (q.kept, q.rejected, q.runs_with_rejects) == (19, 1, 1)
    assert q.reject_share == pytest.approx(0.05)


# ---------- the judge ----------

class FakeLLM:
    """Replies with whatever the script says next, and remembers the prompts it was given."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    async def json(self, messages, schema, **kwargs):
        self.prompts.append(messages)
        return schema.model_validate(self.replies.pop(0))


ITEM = Item(id="t1", type="multihop", lang="en", question="Who?", gold="Ada Lovelace",
            key_points=["Ada Lovelace", "1843"])


async def test_judge_answer_keeps_only_real_key_points():
    llm = FakeLLM([{"verdict": "correct", "refused": False,
                    "covered": ["Ada Lovelace", "something it made up"], "reason": "ok"}])
    j = await judge_answer(llm, ITEM, "Ada Lovelace [1].")
    assert j.verdict == "correct" and j.covered == ["Ada Lovelace"]


async def test_judge_answer_rejects_a_verdict_it_does_not_know():
    llm = FakeLLM([{"verdict": "mostly right", "covered": [], "reason": ""}])
    assert (await judge_answer(llm, ITEM, "something")).verdict == "wrong"


async def test_an_empty_answer_is_wrong_without_calling_the_model():
    llm = FakeLLM([])
    assert (await judge_answer(llm, ITEM, "   ")).verdict == "wrong"


async def test_false_premise_questions_get_their_own_rubric():
    item = ITEM.model_copy(update={"type": "false_premise"})
    llm = FakeLLM([{"verdict": "correct", "refused": True, "covered": [], "reason": ""}])
    await judge_answer(llm, item, "That never happened.")
    assert "premise" in llm.prompts[0][1]["content"].lower()


def test_citation_items_gather_the_quotes_of_the_cited_sources():
    record = make_record()
    record.sentences = [SentenceRec(text="A claim [1][2].", citations=[1, 2], level="high"),
                        SentenceRec(text="No citation here.", citations=[], level="low")]
    record.quotes = {"1": ["first quote"], "2": ["second quote"]}
    items = citation_items(record)
    assert len(items) == 1
    index, text, evidence = items[0]
    assert index == 0 and "[1]" not in text
    assert evidence == ["first quote", "second quote"]


async def test_judge_citations_maps_verdicts_back_to_sentence_numbers():
    record = make_record(levels=("low", "high"), supported=())
    record.sentences = [SentenceRec(text="uncited.", citations=[], level="low"),
                        SentenceRec(text="cited [1].", citations=[1], level="high")]
    llm = FakeLLM([{"verdicts": [{"i": 1, "supported": "partial", "reason": "half of it"}]}])
    out = await judge_citations(llm, record)
    assert out == [CitationVerdict(index=1, supported="partial", reason="half of it")]


async def test_a_sentence_the_judge_forgot_counts_as_unsupported():
    record = make_record(levels=("high",), supported=())
    llm = FakeLLM([{"verdicts": []}])
    out = await judge_citations(llm, record)
    assert out[0].supported == "no"


async def test_self_confidence_sees_the_answer_without_the_citations():
    llm = FakeLLM([{"confidence": 1.4, "why": "sure"}])
    value, why = await self_confidence(llm, "Who?", "Ada Lovelace [1][2].")
    assert value == 1.0  # clamped
    user = llm.prompts[0][1]["content"]
    assert "[1]" not in user and "Ada Lovelace" in user


async def test_self_confidence_never_sees_a_source():
    llm = FakeLLM([{"confidence": 0.5, "why": ""}])
    await self_confidence(llm, "Who?", "Ada Lovelace [1].")
    text = json.dumps(llm.prompts[0], ensure_ascii=False)
    assert "http" not in text and "quote" not in text.lower()


# ---------- the tables ----------

def test_main_table_has_a_row_per_version():
    records = [make_record(label=l, qid=f"q{i}") for i, l in enumerate(["v1", "v2", "v3"])]
    out = main_table(records)
    assert out.count("\n") == 4  # header, rule, three rows
    assert "**v3**" in out


def test_results_md_survives_a_failed_run():
    broken = Record(qid="q9", label="v3", mode="v3", question="?", type="open", lang="en",
                    error="boom")
    out = results_md([make_record(), broken], load_questions())
    assert "Runs that failed" in out and "boom" in out


# ---------- what the citation judge is shown ----------

def test_v2_citations_are_judged_against_the_snippet_the_writer_saw():
    """v2 extracts no quotes, so its evidence is the search snippet. Judging it against nothing
    would score v2 at 0% by construction."""
    from taro.schemas import Report, Source

    from eval.harness import evidence_of
    report = Report(question="q", mode="v2", answer="a [1].",
                    sources=[Source(id=1, url="https://a.com/x", domain="a.com", snippet="the snippet")])
    assert evidence_of(report) == {"1": ["the snippet"]}


def test_a_source_with_facts_is_judged_against_its_quotes_not_its_snippet():
    from taro.schemas import Fact, Report, Source

    from eval.harness import evidence_of
    report = Report(question="q", mode="v3", answer="a [1].",
                    sources=[Source(id=1, url="https://a.com/x", domain="a.com", snippet="the snippet")],
                    facts=[Fact(id=1, statement="s", quote="the quote", source_id=1)])
    assert evidence_of(report) == {"1": ["the quote"]}


# ---------- the quote audit (E4 in detail) ----------

def test_quote_audit_bands_sort_a_score_into_the_right_story():
    from eval.quote_audit import band
    assert band(95.0) == "the check should have accepted it"
    assert band(78.0) == "real text of the page, re-typed with edits"
    assert band(60.0) == "a loose paraphrase or a line built out of a table"
    assert band(10.0) == "not on the page at all: invented"


def test_quote_audit_reads_rejections_out_of_a_trace(tmp_path):
    from eval.quote_audit import rejected_quotes
    run = tmp_path / "20260101-000000-v3"
    run.mkdir()
    (run / "trace.jsonl").write_text(
        '{"kind": "llm_call", "purpose": "v3_extract"}\n'
        '{"kind": "quote_rejected", "url": "https://a.com", "quote": "q", "statement": "s"}\n'
        'not json\n', encoding="utf-8")
    (tmp_path / "20260101-000000-v1").mkdir()  # a mode without quotes at all
    assert rejected_quotes(tmp_path) == [(run.name, "https://a.com", "q", "s")]
