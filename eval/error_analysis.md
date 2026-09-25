# What goes wrong, and why

Sorted by cause, from the 28 questions of `questions.jsonl` run in every configuration. Each type has
real examples with the run folder they came from; `results/failures.md` lists every answer that was
not correct, and `results/judge_sample.md` the judge's own words.

The headline: **v3 answered 25 of 28 questions correctly and invented nothing on any of them.** The
three misses are not three random mistakes — they are three different mechanisms, and none of them
is a retrieval problem.

---

## 1. The plan inherits the question's premise

**2 of the 3 v3 misses (`fp01`, `fp02`) — the single biggest cause of a wrong v3 answer.**

Asked *"What was the name of the first human to walk on Mars in 2024?"*, the planner writes
sub-questions that take the premise for granted:

> Which space mission in 2024 landed the first humans on Mars?
> Who was the first human to step onto the Martian surface during that 2024 mission?
> On what exact date in 2024 did the first human walk on Mars?

Every search then looks for a landing that never happened, nothing is found, no page yields a fact,
and the writer — correctly, by its own rules — reports the absence:

> The sources found do not say which space mission in 2024 landed the first humans on Mars. The
> sources found do not say who was the first human to step onto the Martian surface…

The answer is honest. It is also useless, and the judge marks it `no_answer` rather than `correct`,
because it never says the thing the reader needs: **nobody has walked on Mars.** The same happens in
Russian with *"Почему ИСП РАН был закрыт в 2019 году?"* — five sub-questions about the paperwork of a
closure that never took place.

The irony is that **v2 does better here** (4 of 5 false-premise questions against v3's 3). v2 shows
the raw search results to the writer, and those results are full of pages saying no human has been to
Mars; v3 filters the same pages through sub-questions that can only ask about the closure documents.
The extraction step throws away exactly the sentence that would have exposed the premise, because that
sentence answers no sub-question.

**Fix:** the planner should be allowed one sub-question of the form *"is the premise of this question
true at all?"*, and the writer should get the top search snippets as context even when no fact was
extracted. Neither is in the code today.

---

## 2. One search cannot answer a question with two hops

**v2 only: 3 of 10 multi-step questions (`mh01`, `mh03`, `mh07`).**

v2 searches the question once and answers from the snippets. When the question joins two facts, the
search finds the first and never looks for the second:

- `mh03` — *"In which country was the author of One Hundred Years of Solitude born, and what is that
  country's capital?"* → "he was born in Colombia [2]. The sources do not give the capital of that
  country." A second search for "capital of Colombia" would have cost one call.
- `mh07` — *"Which river flows through the capital of the 2018 World Cup winner?"* → v2 gets as far as
  "Paris, the capital of France" and then says the sources do not mention the river.
- `mh01` — names Nixon, then says his age cannot be determined.

This is v3's whole reason for existing, and the experiment shows it working: v3 is 9.5/10 on the same
questions where v2 is 7.5/10. It is worth noting *how* v2 fails — it stops and says so, rather than
guessing. The honesty rules in the v2 prompt hold up even when the answer is embarrassing.

---

## 3. The page is a content farm and nothing notices

**v3 `op02`, v2 `op04`, and quietly under many open questions.**

For *"Compare PostgreSQL and MySQL for a read-heavy analytics workload"*, v3 read six pages:

    computingforgeeks.com · leaper.dev · sivaro.in · tech-insider.org · markaicode.com · oneuptime.com

Not one is a database vendor, a benchmark project or a conference paper. The answer they produced is
plausible and was judged correct — this is one of the 25 successes, not one of the misses — and it rests on quotes like

> At 10M rows: PostgreSQL delivered 12,400 q/s, MySQL hit 10,800 q/s, and SQLite managed 8,900 q/s.

Numbers from a page with no methodology, no hardware and no date. The quote check passes them — the
text really is on the page — and `domain_quality` scores all six at 0.5 ("unknown"), so the report
reads 0.46 🔴, which is at least not a lie. Across all v3 runs, **99 of 174 sources are "unknown"
domains**; only 34 are official ones.

This is the limit of a quality score built from a domain list: it can tell nobelprize.org from a blog,
but it cannot tell a real unknown site from an SEO farm that exists to rank for this query. The quote
check guarantees that the model did not invent the number. It cannot guarantee that the page did not.

**Fix:** ask the critic to judge sources, not just coverage — "would you cite this page in a report?" —
and prefer pages that several independent sites agree with. Today the critic is only asked what is
missing.

---

## 4. The writer walks a step past its quotes

**The main cause of citation failures: 74% of v3's cited sentences are supported, not the 85% the plan
aimed for.**

Three distinct habits, in order of how often they appear:

**(a) Derived facts carry the citations of their inputs.** From `mh01`:

> Richard Nixon was born on January 9, 1913 [1][2][3]. Therefore, on July 20, 1969 he was 56 years
> old [1].

The arithmetic is right and the reader needs it, but no page says "he was 56 that day". The sentence
is marked 🟢 0.83 because it cites three good sites — and the judge calls it unsupported, correctly.
Every question of the form "how old / how long between" produces one of these.

**(b) The writer adds detail the quotes do not have.** From `fp05`:

> Mercury's lack of moons is explained by its small mass and extreme proximity to the Sun, which
> produce strong solar tidal forces, high solar radiation, a very small Hill sphere…

The quotes say Mercury has no moons. The Hill sphere is the model's own knowledge, wearing the
citation of a fact that only says "zero moons".

**(c) Claims about the literature from one page.** v2's `op04` says "current publications mention only
RAGAS as a benchmark tool" on the strength of a single page about R packages. One source cannot support
a claim about what all sources say.

**Fix:** (a) deserves a rule of its own — let the writer mark a sentence as *derived from* facts rather
than *stated by* them, and score it on the facts it was derived from. (b) is a prompt problem the
current writer prompt already fights and sometimes loses.

---

## 5. The confidence number disagrees with the evidence

Both directions happen, and they have different causes.

**Too high.** The `mh01` arithmetic sentence above: 🟢 0.83, unsupported. The formula looks at *which
sources the sentence cites* — three, good ones — and never at *whether those sources say it*. This is
the structural gap between the score and the citation judge, and it is why the two are measured
separately. The per-sentence table shows the size of it: 🟢 sentences are supported 85% of the time,
so roughly one green sentence in seven is greener than it deserves.

**Too low.** `fr04`, first sentence: *"The artist announced as the winner of Eurovision 2026 was
DARA"*, backed by eurovision.com and the EBU press release — and scored 🔴 0.49, because the writer
cited one site and `min(sites,3)/3` gives a single site only a third of the site term. The organiser's
own announcement is treated as thin evidence. The formula cannot express "one source, but it is *the*
source".

**The "not found" tax.** 25 of v3's 156 sentences carry no citation, and **12 of those are sentences
saying the sources did not answer a sub-question**. Each scores 0.00 🔴 and drags the report average
down. An agent is punished for admitting a gap exactly as hard as for an unsupported claim — the
opposite of what the project is for. `fp01` and `fp02` score 0.00 overall for answers made entirely of
honest admissions.

**Fix:** three separate changes — score derived sentences from their inputs, give an official primary
source more weight than "one site", and exclude "we could not find X" sentences from the average while
counting them in the coverage term instead.

---

## 6. Things that were not a problem

Worth recording, because they were the risks the design was built around:

- **Invented quotes: none.** All 129 rejected quotes were scored against their page again
  (`results/quote_audit.md`): 64% were real page text re-typed with edits, 34% were paraphrases or
  lines assembled out of a table, 2 were too short to count. **Nothing scored below 50.** The fast
  model does not invent quotes; it fails to copy them. The check is doing quote discipline, not
  hallucination catching — a less dramatic job than expected, and still worth its cost, because a
  paraphrase presented as a quotation is exactly what a reader would check and find missing.
- **Invented answers on the impossible questions: none in v2 or v3.** Only v1, with no sources to
  keep it honest, closed a Russian research institute that is still open and invented two Abel Prize
  laureates.
- **Infrastructure.** One run of 108 died on a TLS error inside the MCP session and was re-run by the
  harness. Nothing else failed.
