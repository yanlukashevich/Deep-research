# Checking the judge by hand

Every number in `results/results.md` comes from an LLM judge, so the numbers are worth only as much
as the judge is. These 21 decisions — the whole of `results/judge_sample.md`, three of each verdict
the judge can give — were re-read one by one against the answer and, for the citation verdicts,
against exactly the quotes the judge was shown. This is a first pass by the person who built the
harness, not an independent annotation; it is enough to say whether the tables mean anything, not
enough to publish an agreement coefficient.

**Result: 18 of 21 agree (86%). All three disagreements are the judge being stricter than a reader
would be, so the accuracy numbers in `results.md` are a floor, not a ceiling.**

## Answer verdicts (12)

| # | run | judge | checked | note |
|---|---|---|---|---|
| 1 | `v1` / `fp01` | correct | ✅ agree | says no confirmed Mars landing — that is the point of the question |
| 2 | `v2` / `fr08` | correct | ✅ agree | PSG and Budapest both there; the extra claim about the opponent is outside the gold |
| 3 | `v3` / `mh06` | correct | ✅ agree | 26 years old, Annalen der Physik |
| 4 | `v1` / `fr02` | no_answer | ✅ agree | "I'm not aware of the results of the 2026 Winter Olympics" |
| 5 | `v1` / `fr06` | no_answer | ✅ agree | same, for the Turing Award |
| 6 | `v2` / `fp04` | no_answer | ✅ agree | lists the Abel Prize but never says a Nobel in mathematics does not exist |
| 7 | `v1` / `fp04` | partial | ✅ agree | right that there is no such Nobel, then invents Abel and Fields laureates |
| 8 | `v2` / `mh03` | partial | ✅ agree | Colombia yes, capital missing |
| 9 | `v3` / `mh08` | partial | ❌ **disagree** | the answer gives 27 years and Klushino; the judge marked it down only for omitting "Smolensk region". A reader would call this correct |
| 10 | `v1` / `fp02` | wrong | ✅ agree | invents a whole 2019 reorganisation that closed the institute |
| 11 | `v1` / `fr04` | wrong | ❌ **disagree** | the answer is "I don't have information about the winner". That is `no_answer`. The judge even set `refused: true` and still called it wrong |
| 12 | `v2` / `mh01` | wrong | ❌ **disagree** | names Nixon correctly and then says the sources do not give his age. Nothing false is stated: `partial` fits, `wrong` does not |

The pattern in 11 and 12: when an answer is right about part of the question and honestly says the
rest is missing, the judge sometimes reaches for `wrong` instead of `partial` or `no_answer`.
It never went the other way — it never called an invented answer correct.

## Citation verdicts (9)

| # | run | judge | checked | note |
|---|---|---|---|---|
| 13 | `v2` / `mh04` s1 | no | ✅ agree | the sentence names Satya Nadella; the cited snippet is an ownership table that never mentions a CEO |
| 14 | `v2` / `op04` s2 | no | ✅ agree | the sentence claims only RAGAS is used; the cited page is about R packages |
| 15 | `v3` / `op04` s14 | no | ✅ agree | the sentence compares GPT-4o with open models; no quote contains a comparison |
| 16 | `v2` / `fp03` s1 | partial | ✅ agree | the quote confirms the 1937 nomination but not "never received the award" |
| 17 | `v3` / `fp05` s3 | partial | ✅ agree | generous: the quotes support "no moons", not the Hill sphere or the radiation |
| 18 | `v3` / `op02` s8 | partial | ✅ agree | binlog, group replication and InnoDB Cluster appear in no quote |
| 19 | `v2` / `fp02` s1 | yes | ✅ agree | the quotes show the institute celebrating its 25th anniversary in 2019 and working after it |
| 20 | `v3` / `fr07` s2 | yes | ✅ agree | series 4-2, sixth game 3-2, 21 May 2026 — all in one quote |
| 21 | `v3-r1` / `fr04` s2 | yes | ✅ agree | four of the twelve quotes name "Bangaranga" |

On the citation side the judge was right every time, including on the three "no" verdicts, which are
the ones that cost the agent points. It refused to be talked into a sentence by its own knowledge:
in 13 it knows perfectly well that Nadella was Microsoft's CEO, and it still said the evidence does
not show it.

## What this means for the numbers

- **Accuracy (E1, E2) is understated**, by roughly one question in ten for v2 and v3. The direction
  is consistent: strictness, not generosity.
- **Citation quality (E1) can be read as it stands.** Nine out of nine agreed, and the judge held to
  "judge the evidence, not the world" even when that made it contradict itself.
- **The calibration table (E3) rests on the citation verdicts**, so it inherits their reliability.
- One thing this check cannot see: the judge grades answers written by the same model family that
  wrote them. A second judge from a different family would be the real test, and is not something
  this evaluation has.

## How to redo this

`python -m eval.run_eval --report` rebuilds `results/judge_sample.md` from the stored records. It shows
each decision with the exact evidence the judge was given — an earlier version of the page trimmed the
quote list, which made one verdict look like a hallucination when the judge had in fact been shown the
proof. If you change what the judge sees, change the sample page with it.
