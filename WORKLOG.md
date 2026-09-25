# Work log

A simple diary of what the agent did in each phase. New entries go at the bottom, and old entries are never rewritten.
(For the *current* state and next steps, see `HANDOFF.md`.)

---

## Phase 0: project setup (2026-09-23)

**What I did, step by step**
1. Read the plan and the assignment. There was no `HANDOFF.md`, so nothing had been built yet and this session was
   Phase 0: getting everything ready so the next phases can write the agent itself.
2. **Protected the keys first.** The assignment file `task.md` contains two real keys (for the search service and the
   language-model service). Before anything else I created `.gitignore`, which lists files git must never save:
   `.env` (where the keys now live), `task.md` itself, the Python environment, the cache and the run results. It had
   to come first because a key that has been committed stays in the git history even after the file is deleted.
   The keys went into `.env`, and `.env.example` is a copy with the values left empty, so anyone cloning the project
   knows what to fill in.
3. **Created an isolated Python environment** (`.venv`) and installed the libraries the plan names: the client for
   the language models, the client for the search service, a data checker, retries, fuzzy text matching (for the
   quote check), disk caching, the web server and the test runner. They are listed in `requirements.txt`, so the
   reviewers get exactly the same set.
4. **Tested the search service (Keenable) by hand.** I asked it what tools it offers and read their full
   descriptions, then ran one search and one page download. This was needed because the whole agent depends on
   what these two tools really return, not on what the documentation promises. Search answered in about 0.3
   seconds, a page download in 0.2 seconds, and a search in Russian with a date filter also worked.
5. **Asked the language-model server which models it has.** There are 7. The server refuses to say anything about
   them (their size, how much text they can read), so the only way to choose was to try them.
6. **Wrote a small benchmark** (`scripts/model_bench.py`) that gives every model the same tasks the agent will give
   it later:
   - **reading a page:** get a short text (one in English, one in Russian) and return facts as JSON, each with an
     exact quote. The script checks that the JSON is valid and that each quote really appears in the text.
     Each model ran this twice per language.
   - **writing an answer:** get five numbered facts and write a short answer in Russian, where every sentence ends
     with `[n]`. Two of the facts deliberately disagree (about 6 million visitors a year vs 6.3 million in 2023),
     to see whether the model says so.
   - **reading a long text:** one sentence hidden in the middle of a very long text (about 10, 30 and 65 thousand
     tokens), and the question asks for it. This shows how much text a model can really take in.
   - **speed** of every call.
7. **Chose the models** from the results (see below), wrote them into `.env`, and ran the final check the plan asks
   for: one model call, one search, one page download, all in one script (`scripts/smoke_test.py`).
8. Wrote `HANDOFF.md` (the current state for the next session), added the new facts and commands to `CLAUDE.md`,
   and made the commit.

**What came out**
- A project skeleton that installs with one command and keeps the keys out of git.
- The benchmark results (all saved in `scripts/model_bench_results.json`):

  | model | valid JSON | quotes found in the text | time per page | Russian answer | longest text read |
  |---|---|---|---|---|---|
  | gpt-oss-120b | 4 of 4 | 13 of 13 | 4.4 s | good, points out the disagreement | 31k tokens (the server's limit is 60k) |
  | gemma4:31b | 4 of 4 | 16 of 16 | 4.3 s | good, does not point it out | 65k tokens |
  | qwen3.8-27B | 4 of 4 | 16 of 16 | 17.8 s | good, points out the disagreement | 65k tokens |
  | glm-4.7-flash | 0 of 4: the server returns an error whenever JSON is requested | – | ~30 s | – | 10k tokens |
  | qwen3.6-35B | never answered (tried twice, 60 s each) | – | – | – | – |

- **The choice:** `gpt-oss-120b` is the main model (it plans, criticises and writes the answer), and `gemma4:31b` is
  the fast model that reads pages and pulls out facts. `qwen3.8-27B` is the fallback: its answers are just as good,
  but it takes four times longer.

**Interesting moments**
- **Only two models noticed the planted disagreement.** Given "about 6 million visitors a year" and "6.3 million in
  2023", gpt-oss wrote that the second number "differs a little from the usual 6 million", and qwen also said the
  figures disagree. gemma simply put both numbers in one sentence as if nothing were wrong. The plan requires the
  writer to mention when sources disagree, and this was the deciding point for who writes the final answer: gpt-oss.
- **"Thinking" models against a model that doesn't think.** gpt-oss and qwen write hidden reasoning before they
  answer: 1,000–2,200 characters for every page they read. gemma writes none and goes straight to the answer. On a
  plain "Say OK", glm wrote 512 characters of reasoning. This decided the split of work. Reading pages is the step
  that repeats for every page, so it went to gemma, which is quick and cheap. The steps that happen once per
  question and need judgement (the plan, the critic, the answer) went to gpt-oss. A practical consequence for the
  code: a thinking model spends part of its answer budget on thinking, so if the budget is small, the visible
  answer comes back empty. Calls to gpt-oss must allow plenty of room.
- **gpt-oss looked like it couldn't read long texts, but it was a one-off.** In the first run it missed the hidden
  sentence already at about 10 thousand tokens, while gemma and qwen found it in 65 thousand. My first suspicion
  was a refusal, because the hidden sentence was about a "secret launch code". I reran the same test and gpt-oss
  answered correctly, then it passed at 31 thousand with a harmless sentence. Only at 65 thousand did the server
  reply that the model's limit is 60,144 tokens. Two lessons. First, the same question to the same model can give a
  different result, so one run is not a verdict, and the agent must check every answer and ask again when it is
  bad (this became part of `llm.py` in Phase 1). Second, 60k is enough only if we never paste whole pages, which
  the plan already forbids. Now it is a hard limit rather than good manners.
- **gpt-oss has its own typography.** It puts a special narrow space between numbers and words ("version 7461",
  where the space is not an ordinary space). It also added citation marks of its own that nobody asked for:
  `【source: user‑provided statement】`. Both matter later. A quote with a different kind of space will not match the
  page letter for letter, so the quote check has to treat all spaces as equal. The invented marks have to be
  removed from the answer, or they would look like citations.
- **Copying quotes was easy for every model, and that proves less than it seems.** All three working models copied
  100% of their quotes exactly. But the test texts were short, clean paragraphs of five sentences. Real pages come
  with menus, links and broken formatting, where copying exactly is much harder. So the quote check in the agent
  stays necessary, and this result does not replace it.
- **The top search result was written by an AI.** When I searched for ISP RAS, Keenable's first result was a page
  from Grokipedia, an encyclopedia generated by the Grok model ("Fact-checked by Grok"). That means a "source" on
  the web can itself be another model's text. Its facts were right here, but a claim confirmed only by an
  AI-written page is weaker than it looks. This is worth keeping in mind when the agent rates how good a website
  is. It is also a good point for the report.

**What to check by hand**
```
.venv\Scripts\activate
python scripts/smoke_test.py
```
You should see the list of 7 models, then a one-sentence answer in Russian to "what is RAG?", then 10 search
results for ISP RAS (on 2026-09-23 the first one came from grokipedia.com; the smoke test searches live, so this
can change), and then the start of the ispras.ru home page.
```
python scripts/model_bench.py openai/gpt-oss-120b google/gemma4:31b      # about 3 minutes
```
You should see one summary line per model, similar to the table above (the times will vary a little). At the end
the script prints each model's Russian answer about the Eiffel Tower. Read them and check whether each one says
that the 6 and 6.3 million visitor numbers disagree.

The keys must not be in git: `git check-ignore -v .env task.md` should name both files, and
`git log -p --all | grep -c "keen_rk"` should print `0`.

**Commit:** `Phase 0: project setup`. `WORKLOG.md` itself was added right after, in
`Add WORKLOG.md: plain-language diary of each phase`.

---

## Phase 1: foundation, v1 bare LLM, v2 simple RAG (2026-09-23)

*(Rewritten on 2026-09-25 to follow the new entry format in `CLAUDE.md`; the facts are the same.)*

**What I did, step by step**
1. Read `HANDOFF.md` and the plan. Phase 0 was done, so this session was Phase 1: the plumbing every later version
   stands on, plus the two simple versions that the final agent will be measured against.
2. Looked once more at what Keenable really sends back before writing any code for it. Search results arrive as
   plain text blocks (title, address, dates, excerpt) separated by `---`, not as structured data, and a page that
   cannot be fetched comes back marked as an error instead of failing loudly. Both facts decide how the reading
   code has to work, and guessing them from the documentation would have meant a parser that breaks on the
   first real answer.
3. Wrote the connection to the language model (`llm.py`). It keeps the temperature low, so the same question
   gives nearly the same answer, which matters for experiments. It never has more than 3 requests running at
   once, because the service is shared with other people, and it waits and tries again when the server is busy.
   When we ask for JSON, it checks the answer against the expected shape and, if it doesn't match, tells the
   model exactly what was wrong and asks again. Open models break JSON now and then, and later phases depend
   on it completely.
4. Wrote the search connection (`search.py`), which saves every search and every page on disk. Asking the same
   question twice then costs nothing, and more importantly the experiments become repeatable: without the saved
   copy, the web changes between two runs and you can't tell whether the agent improved or the internet did.
5. Wrote the report part (`report.py`). Every step of a run (each search, each model call with its full prompt
   and answer) is written to `trace.jsonl` the moment it happens, so even a run that crashes leaves a record of
   what it did. At the end the answer is saved as a readable `report.md` and a machine-readable `report.json`.
6. Wrote the two simple versions:
   - **v1**: the model answers alone, with no internet. It exists only as a baseline: it shows what the model
     "knows" by itself, so every later gain can be credited to the search.
   - **v2**: one search with the question exactly as asked, the 8 best results, and one model call that must
     answer only from those results and put `[n]` after every fact. This is the simplest thing that deserves to
     be called a research agent.
   - both run with `python -m taro "question" --mode v1|v2`.
7. Wrote the code that reads the finished answer back: it splits the answer into sentences and records which
   sources each sentence cites. The confidence score in Phase 3 is built sentence by sentence, so this had to be
   exact from the start.
8. Wrote 16 small tests that need no internet, then ran real questions: a fresh one in English (the 2025 Nobel
   Prize in Physics), an older one in Russian (who led ISP RAS after Ivannikov), and a trick question with a
   false premise ("the first human to walk on Mars in 2024"). Then I read every saved report by hand.

**What came out**
- **v1 on the Nobel question:** "I don't have information on the 2025 Nobel Prize in Physics." Honest, and
  exactly the gap the project is about.
- **v2 on the Nobel question:** correct (Clarke, Devoret, Martinis, with the official wording of the prize), every
  sentence cited, in about 5 seconds, using one search and one model call (about 2,700 tokens of input).
- **v2 on the Mars question:** it rejects the premise: "the sources do not give the name of any person who walked
  on Mars in 2024".
- **v2 on the Russian question:** the right person and the right date (Avetisyan, August 2015), plus one invented
  detail. More on that below.
- Asking the same question again reads the search from disk (the report shows 1 cache hit).

**Interesting moments**
- **Citations do not make an answer faithful.** v2 wrote that Avetisyan became director "after the death of
  Viktor Ivannikov" and cited a Wikipedia page for it. The appointment was in August 2015, and Ivannikov died in
  November 2016. Every word of the sentence looks sourced, but the "after his death" link between two facts
  was the model's own. Among the 8 results was a news story headlined "The first director of ISP RAS has died",
  and the model most likely joined that headline to the appointment. The prompt forbids adding anything not in
  the results, and the model broke that rule without noticing, because it didn't feel like adding a fact, just
  connecting two. Decided: this is exactly why v3 must work from separate facts that each carry an exact quote,
  and why the writer must not see loose excerpts. Kept the example for the report's error analysis.
- **The bare model refuses rather than invents, even when it could know.** v1 declined the Nobel question
  (reasonable, since it's after its training) but also the ISP RAS question, where the answer is from 2015 and
  almost certainly in its training data. The prompt gives today's date and says "if you are not sure, say so",
  and gpt-oss took that very cautiously. Decided: keep the prompt, because a baseline that is honest makes the
  comparison fair rather than easy. But the evaluation must count "didn't answer" separately from "wrong", or
  v1 will look like a liar when it is really just silent.
- **One page counted as two sources.** The first sentence of the Nobel answer cites [1][6]. Source [6] had an
  unfamiliar address (`link.cfr.org/click/...`), and decoding it showed a newsletter's redirect link to the very
  same nobelprize.org press release as [1]. The model can't see that, so it honestly cited "two" sources. For
  v2 this is harmless. For v3, where confidence rises with the number of *different* sites confirming a
  sentence, it would inflate the score. Decided: v3's page selection must drop redirect links and treat one
  article as one source even under different addresses (done in Phase 2).
- **The model cites generously.** For the sentence with the official prize wording, v2 put five sources:
  [1][3][4][6][7]. Every one of them really contains that wording, so this is correct, not padding. But it shows
  that "how many sources are cited" says little on its own, since the model cites everything that agrees. The
  quality of each site has to count too, which is what the Phase 3 formula does.
- **Search is good at the top and noisy below.** For the Russian question the top results were right (Wikipedia,
  the institute's own history page, a news story), but the 8 also included a job advert on hh.ru and a Tomsk
  university page. Titles sometimes carry raw HTML (`<br/><small>By Reuters…`). Decided: v2 stays deliberately
  naive and takes the top 8 as they come, so the benchmark shows what a simple approach gets. Filtering junk
  sites and ranking by site quality is v3's job.
- **Snippets instead of pages for v2.** Keenable returns an excerpt of up to 2,000 characters already chosen to
  match the query, so v2 reads those and doesn't open any page. That keeps v2 at one search and one model call.
  The price is the Ivannikov mistake above: excerpts are fragments, and the model fills the space between them.
  Reading whole pages and checking quotes against them is what v3 adds, so the difference between v2 and v3 in
  the experiments measures exactly that step.
- **Names with initials looked like sentence ends.** Reading back the Nobel answer, "Michel H. Devoret" was cut
  at "H.", and the first two pieces lost their citations: a well-sourced sentence would have scored as two
  unsourced ones. Nothing in the answer looked wrong, and only reading the saved report showed it. Fixed, with a
  test for initials and common abbreviations in English and Russian. (In Phase 3 it turned out chained Russian
  initials like "В.П." still slipped through.)
- **gpt-oss has habits of its own.** Phase 0 had already shown that it sometimes adds its own source markers
  (`【source: 3】`) and uses unusual space characters. The v2 prompt says "no citation format other than [n]",
  and the report cleans up whatever gets through anyway. None of it appeared in this phase's runs, but the
  guard costs nothing.

**What to check by hand**
```
pytest                                                    # all tests pass, no internet needed
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v1   # says it doesn't know
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v2   # Clarke, Devoret, Martinis, with [n]
python -m taro "What was the name of the first human to walk on Mars in 2024?" --mode v2   # "the sources do not say"
python -m taro "Кто стал директором ИСП РАН после Иванникова и в каком году?" --mode v2
```
- Open `runs/<time>-v2/report.md`. Every factual sentence should end with `[n]`. Pick one, open that source's
  address, and the fact should be on the page.
- In the ISP RAS answer, look for the "after his death" wording. Since the model call isn't cached it may not come
  back word for word, but the search results are the same ones, headline about the death included.
- Run the same v2 question twice. The "Run stats" line of the second report should show 1 cache hit.
- `trace.jsonl` in the same folder shows the search that was made, the addresses it returned, and the full
  prompt and answer of the model call.

**Commit:** `Phase 1: foundation, v1 bare LLM, v2 simple RAG`

---

## Phase 2: v3 research agent with critic loop (2026-09-24)

**What I did, step by step**
1. Read `HANDOFF.md` and the plan. Phases 0 and 1 were done, so this session was Phase 2: the real agent, the one
   that plans, reads pages and checks itself.
2. Put limits into the settings first: at most 3 rounds, 14 pages, 60 facts, 7 minutes. This had to come before the
   loop, because a loop that searches "until it is satisfied" can run all day, and the language-model service is
   shared with other people.
3. Wrote `pages.py` — everything the agent can decide without asking a model:
   - **a trust score for websites** (an official or scientific site 1.0, an encyclopedia 0.8, news 0.7, an unknown
     site 0.5, a blog or forum 0.4). Needed so a government announcement and a forum post do not count the same
     when choosing what to read; the same numbers will be reused for the confidence score in the next phase.
   - **a list of sites never worth opening** (job boards, shops, and "click here" redirect links). Earlier runs
     kept dragging in job vacancies, so this removes them before anything is fetched.
   - **choosing which pages to read**: never the same page twice, at most two pages from one website, better sites
     first. Without the per-site cap, one news site can fill the whole round and the answer rests on a single source.
   - **cutting a page down** to the parts that match the question. A full page does not fit into the model's
     context, and pasting whole pages is how an agent runs out of room and money.
   - **checking a quote**: search for it inside the real page text, allowing for differences in spaces and
     quotation marks but not for different words. This is the guard against invented facts.
4. Wrote the four prompts — the planner, the page reader, the critic and the writer — each with the rule that it
   may only use what it was given.
5. Wrote `v3_research.py`, which runs them in order: plan → search every query at once → choose pages → read them
   → pull out facts with quotes → throw away every fact whose quote is not really on the page → ask the critic
   "is this enough?" → if not, search again with the critic's new queries → write the answer.
6. Made the numbers in the answer work for a reader: the writer cites *facts* (it needs the quotes), but the
   report lists *pages*, so the numbers are translated at the end and two facts from one page become one number.
7. Turned v3 on in the command line as the default, and made `report.md` print the quotes under each source plus a
   section for places where the sources disagree — otherwise there is no way to check the agent by hand.
8. Wrote 13 more tests (29 in total, still no internet needed) and ran real questions in English and Russian.

**What came out**
- The Nobel question: 66 seconds, 6 pages read, 13 facts kept, 5 sources, and the answer carries the prize's exact
  wording — because it came out of a quote instead of the model's memory.
- **The question v2 got wrong is now right.** Asked who led ISP RAS after Ivannikov, v3 answers Avetisyan, August
  2015. The invented "after his death" from v2 is gone.
- The trick question about a human walking on Mars in 2024: v3 says it did not happen and cites the pages that
  say so.
- Every sentence of all three answers ends with a citation, and behind each one there is a quote I could find on
  the page myself.

**Interesting moments**
- **The planner invented the meaning of an abbreviation.** I had written the rule "name every entity in full in
  every query", and for "ИСП РАН" the model obligingly expanded it — to the Institute of *Solar Physics* instead
  of *System Programming*. The whole first round searched for the wrong institute, found nothing, and the agent
  gave up. Decided: the prompt now forbids guessing what an abbreviation stands for and tells the planner to keep
  the question's own wording. The lesson is uncomfortable and worth keeping: an instruction that sounds helpful
  ("be explicit") invited the model to fill a gap with a guess — the exact failure this project exists to prevent.
- That same run showed the loop was too quick to quit: with no facts at all it stopped instead of trying
  differently. Decided: if a round brings nothing and the critic has no new ideas, search the question exactly as
  the user wrote it. A dumb search of the user's own words is a good last resort, because it cannot misread them.
- **The critic earned its place.** In the ISP RAS run it accepted the successor but noticed that nothing said
  *when* Ivannikov left, wrote two new searches, and the second round found it. That one example is the whole
  difference between v2 and v3.
- **The planner drifted into Swedish.** For the Nobel question it reasoned Nobel → Sweden and wrote several
  Swedish queries. Not wrong, just wasted searches. The prompt now pins the languages: the question's language
  plus English, nothing else.
- **The small model is a good copyist and a poor writer.** gemma4:31b reproduced quotes faithfully — not one
  rejected quote in the Nobel run — but phrases its statements strangely, spelling years out in words ("две
  тысячи пятнадцатом"). Since the main model writes the final answer, this never reaches the reader, so the
  division of labour stands: the cheap model copies, the main model phrases.
- **Two hosts, one article, and a false sense of agreement.** The Mars run cited the same paper twice, once from
  nature.com and once through doi.org. Addresses differ, so the duplicate check missed it — and it would have made
  the answer look better supported than it is, since "two different sites" is what confidence will be built on.
  Decided: compare page titles as well, and skip an article already taken from another host.
- Decided that only a page which produced at least one verified fact gets a number in the report. A source list
  full of pages nothing came from looks thorough and says nothing.
- The quote check has not rejected much in real runs yet, which is either good news about gemma or too small a
  sample. To be sure the guard itself works, one test scripts a fake model that invents a quote and checks the
  fact is dropped and counted.

**What to check by hand**
```
pytest                                                    # 29 tests, ~5 s, no internet
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v3
python -m taro "Кто стал директором ИСП РАН после Иванникова и в каком году?" --mode v3
python -m taro "What was the name of the first human to walk on Mars in 2024?" --mode v3
```
Then open `runs/<time>-v3/report.md`, take a quote from the source list, open that page and search for it.
`trace.jsonl` in the same folder holds every step, every search and every rejected quote.

**Commit:** `Phase 2: v3 research agent with critic loop`

---

## Phase 3: confidence scoring, report format, tests (2026-09-24)

**What I did, step by step**
1. Read `HANDOFF.md`: phases 0-2 were done, so this session was Phase 3 — putting a number on how much each
   sentence of the answer can be trusted.
2. Wrote `taro/confidence.py`. For every sentence it looks only at the sources that sentence cites and asks
   three questions: how many *different* websites back it, how good those websites are, and whether the critic
   caught those sources contradicting each other. The formula from the plan turns that into one number between
   0 and 1, and the number into a colour: green from 0.75, yellow from 0.5, red below that. A sentence with no
   citation at all is always red and scores zero.
3. Gave the whole report a score too: the average of its sentences, multiplied by the share of the sub-questions
   the agent actually found facts for. A report can be beautifully sourced on half the question and should not
   look complete because of it. Next to the number there is a plain line saying what it is made of, so a reader
   never has to trust the number itself.
4. Made the report show it. `report.md` now prints the answer with a 🟢🟡🔴 after every sentence, a legend, and
   a "Confidence" section. The terminal prints the same thing at the end of a run. The saved JSON keeps the
   answer clean and stores the colour per sentence separately, so the web page in the next phase can paint the
   text itself instead of parsing emoji out of it.
5. Tidied the source list at the bottom of the report: quotes are now squeezed onto one line (a quote with a
   line break inside it used to break the layout and spill raw page markup into the report), repeated quotes
   are shown once, very long ones are cut at 300 characters, and a source that no sentence cites is marked as
   such instead of sitting there unexplained.
6. Wrote 21 new tests: the formula on known combinations, the colour boundaries, one site cited twice, the
   contradiction penalty, the no-citation rule, the sub-question multiplier, the v1 case, and the rendering —
   that every sentence gets exactly one mark in the right place and the sections are all there.
7. Ran all three versions on the three test questions and read the reports by hand.

**What came out**
- Nobel question, v3: **0.72 🟡**. The two sentences that matter — who won and the official wording of the
  prize — are green, backed by nobelprize.org and Nature. Two throwaway sentences the writer added at the end,
  sourced from a substack essay and an odd news site, came out red. That is exactly the split I wanted to see:
  the colour separates the core of the answer from its edges without anyone reading the sources.
- ИСП РАН question, v3: **0.72 🟡**, three sentences, the key one (who became director) green.
- v1 on the Nobel question: **0.00 🔴**. It has no sources by construction, so it cannot score anything else.
  This is the cleanest possible demonstration of why the project exists.
- The Mars question (a made-up premise): v3 answers "the sources do not say", every sentence red, **0.00**.

**Interesting moments**
- **The score punished the agent for being careful.** On the Nobel run the very first sentence — who won the
  prize — came out yellow, not green, because both sources it cites are nobelprize.org: the press release and
  the scientific background PDF. Two pages, one site. My first instinct was that the score was wrong. It is
  not: one organisation stating something twice is one claim, not two, and the agent had genuinely not found a
  second independent confirmation for that exact sentence. I left it alone. The lesson is that the score is
  measuring evidence, not truth, and those really are different things.
- **A punctuation bug was quietly costing confidence.** The Russian run marked "Академик В.П." as its own red
  sentence: the sentence splitter saw the dot after "П" and started a new sentence, leaving a two-word fragment
  with no citation. That fragment alone dropped the report from 0.72 to 0.54. The splitter already knew that a
  single initial ("Michel H. Devoret") is not a sentence end, but not that initials come in chains ("В.П."). A
  one-character fix to the rule, and the run scored what it deserved. Worth recording because the failure was
  invisible until a number depended on it — the answer had always read fine.
- **Deciding what an uncited sentence is worth.** Zero is harsh: a lead-in like "Below is a short overview."
  is not a lie, it just carries no facts. I tried excluding such sentences from the average and stopped: any
  rule for "this sentence isn't really a claim" is a rule the model can slip an unsupported claim through.
  Scoring every sentence and letting the writer's own instructions ("no fact, no sentence") keep the answer
  clean is the safer side to err on. Noted in the handoff as a known cost.
- **The contradiction penalty is blunter than it looks.** When the critic finds two sources disagreeing, every
  sentence citing either of them loses 0.3 — even a sentence about a completely different point from the same
  page. To do better, the report would have to remember which *fact* each sentence rests on, and that
  information is deliberately thrown away when the writer's fact numbers are translated into source numbers.
  Left as it is, written down as the first thing to fix if the scores ever look unfair in practice.
- **The zero-source message had to be split in two.** "No sources" means two opposite things: v1 never looked,
  while v3 looked hard and found nothing usable. Both score 0.00, but telling a reader the same sentence in
  both cases would be misleading, so the explanation now depends on which one it was.
- A practical note for the next phase: `report.json` now carries everything a web page needs to colour the
  answer — a level and a one-line reason per sentence — so the page will not need to recompute anything.

**What to check by hand**
```
pytest                                                    # 50 tests, ~4 s, no internet
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v3
python -m taro "Who won the Nobel Prize in Physics in 2025 and for what?" --mode v1   # must be 0.00 red
```
Open `runs/<time>-v3/report.md`. Every sentence should end with a colour. Pick a red one, look up its `[n]` in
the source list, and the site should visibly be a weak one (a blog, a forum, an unknown domain) or the sentence
should have no `[n]` at all. Pick a green one and its sources should be two or three different serious sites.
The "Confidence" line states how many sentences cite something and how many different sites were used — both
are countable by hand from the same report.

**Commit:** `Phase 3: confidence scoring, report format, tests`

---

## Phase 4 — the demo: a web page that shows the research happening

**What I did, step by step**

1. **Read where Phase 3 had left things.** The agent already told its story to itself: every step it takes
   (planning, searching, reading a page, extracting facts, criticising, writing) is written into a log file as
   it happens, and the runner accepts a "listener" — a function that gets handed each step the moment it
   occurs. Phase 3 left that hook unused. Phase 4 is essentially the work of plugging a browser into it.
2. **Wrote the server** (`taro/server.py`, ~130 lines). It has one real endpoint: you ask it a question, it
   starts a run, and it keeps the connection open, pushing each step down the wire as the agent takes it
   (Server-Sent Events — a plain HTTP connection the browser holds open and reads line by line). The last
   thing it sends is the finished report as JSON, plus the same report rendered as markdown so the download
   button has something to hand over. If you ask for "all three", it starts v1, v2 and v3 at the same time and
   labels every message with which one it came from.
3. **Decided what must not leave the machine.** The internal log contains whole prompts, whole model replies
   and local file paths. None of that belongs in a browser: it is megabytes of text and it exposes the
   machine's directory layout. The server strips those fields and keeps the counters (how many tokens, how
   long), which are exactly what a reader wants to see. There is a test that fails if a prompt ever reaches
   the page again.
4. **Made the steps readable.** The raw log says `name=select picked=6 candidates=31`. The page and the
   terminal now say "picked 6 pages out of 31 found". That translation lives in two small files
   (`taro/progress.py` for the terminal, `web/src/lib/format.js` for the page) that say the same thing in the
   two languages.
5. **Added `python -m taro serve`** and rewrote the terminal output so a run narrates itself in plain
   sentences instead of printing raw fields.
6. **Built the page** (React, in `web/`): a question box, a v1/v2/v3/"all three" switch, four example
   questions, a live log of the steps, the answer, the confidence score with a "why this number" button,
   the sources with their quotes, and download buttons. The built page is committed, so a reviewer with only
   Python installed can run the demo; Node is needed only to change the UI.
7. **Checked it end to end**: a full v3 run through the server (72 steps streamed, then the report), and a
   "all three" run that produced 0.00 for v1, 0.78 for v2 and 0.84 for v3 on the same question — the demo's
   whole argument in one screen.

**What came out**

`python -m taro serve` → http://localhost:8000. The page fills as the research happens. The answer's sentences
are underlined by how well they are backed, hovering a `[1]` shows the exact sentence that page really
contains, and the sources are listed with their quotes. 59 tests pass (9 new ones for the server).

**Interesting moments**

- **The page must not re-do the agent's thinking.** My first plan was to let the browser split the answer into
  sentences and match them to the confidence scores. That means writing the sentence splitter a second time,
  in another language — and the Russian answers had already proved how fiddly that splitter is ("Академик
  В.П." is not a sentence). If the two versions ever disagreed by one sentence, every colour on the page would
  shift onto the wrong sentence and quietly lie to the reader. So the server now walks the answer itself and
  hands the page a ready-made list: this piece of text is sentence 3, colour it with sentence 3's score. The
  page does no interpretation at all. Same argument for the site quality: the number the page shows is the
  number the formula used, sent along with each source, not a lookalike computed in the browser.
- **Watching all three versions race is more convincing than any table.** Running v1, v2 and v3 in parallel
  was meant to save time. What it actually produced is the strongest demo in the project: v1 finishes in two
  seconds with a confident-looking paragraph and zero sources, v2 comes back half a minute later with one
  site per claim, and v3 keeps going — round two, a critic, more pages — and lands on 0.84. The difference in
  how long they take is itself part of the argument.
- **An old report revealed a repaired bug.** While testing the page against a report saved earlier in the day,
  the first sentence came out coloured red and unquoted. The cause was not the page: that file had been
  written before Phase 3's initials fix, so its stored sentence list no longer matched its own answer text.
  The page had faithfully rendered stale data. It made me add the one defensive line the UI does keep: if a
  sentence number has nothing behind it, render the text plainly rather than crash. An agent that writes
  files across versions will eventually be handed one.
- **v1 refusing to answer is a result, not a failure.** Asked about the 2025 Nobel Prize, the bare model says
  "I don't have information about that". On the page this sits next to v3's fully cited answer, and it makes
  the point better than a wrong answer would have: the model is not being stupid, it simply has no way to
  know. The page therefore says under v1, in plain words, that this answer comes from memory alone.
- **What the confidence number should look like to a stranger.** A bare "0.84" invites the reader to trust a
  number they cannot check. The page puts the sentence-level explanation one click away ("6 of 6 sentences
  cite a source; 3 different sites; average 0.62") and spells out the formula in a sentence underneath, so the
  reader can recompute it from what they see on screen. The underlines are styled solid, dashed and dotted,
  not just coloured, so the page still reads correctly to someone who cannot distinguish the colours.
- **No browser in this session.** The extension that would let me open the page and look at it was not
  connected, so I verified the interface by running it headless: mounting the real page in a simulated
  browser, typing a question, feeding it a recorded stream of steps, and asserting that the answer, the
  underlines, the citation links, the score, the sources and the theme toggle all appear. Ten checks, all
  green. That is not the same as a human looking at it, and the handoff says so: the visual pass and the
  phone-width check are still to be done by eye.

**What to check by hand**
```
pytest                                     # 59 tests, ~5 s, no internet
python -m taro serve                       # then open http://localhost:8000
```
On the page: click an example question, watch the steps appear one by one (they should not all arrive at the
end); when the answer lands, hover a `[1]` and confirm the quote shown really is on the page it links to;
click "why this number" and check the count of sentences and sites against what you see; switch to "all three"
and watch v1 finish first with no sources at all; download the markdown and confirm it is the same report the
CLI writes; switch to the dark theme; narrow the window to phone width and check nothing overflows sideways.

**Commit:** `Phase 4: CLI and web UI (FastAPI + React)`

---

## Phase 5 — measuring it: does any of this actually help? (2026-09-25)

Up to now the project rested on a story: a bare model makes things up, searching once helps, and a research
agent that reads pages and checks quotes helps more. This phase was about finding out whether that story is
true, with numbers anyone can recompute.

**Step 1: write the exam.** I wrote 28 questions and, for each, the answer a well-informed person would give.
Four kinds, because they fail in different ways:

- 10 **multi-step** questions, where you have to look up one thing to be able to look up the next. "Who was
  the US president when the first human landed on the Moon, and how old was he that day?" — you need the
  landing date, then the president, then his birthday, then the subtraction.
- 8 **fresh 2026** questions, about things that happened this year: who won the World Cup, who topped the
  Winter Olympics medal table, who got the Turing Award. No model can know these; it has to go and look.
- 5 **open** questions with no single right answer ("compare PostgreSQL and MySQL"), graded on whether the
  answer covers the points that matter.
- 5 **questions built on something that never happened**: the first human to walk on Mars in 2024, the Nobel
  Prize in mathematics, why a Russian institute that is still open was closed. These are the honesty test.

Nine of the 28 are in Russian.

The fresh questions needed care. I do not know what happened in 2026 either, so writing the answer key out of
my head would have been inventing the exam as well as sitting it. Instead I ran the project's own search on
each topic first, read the results, and only wrote down answers that several independent pages agreed on —
the Wikipedia article and the official site, for instance. Each of those eight questions carries the page the
answer was checked against, written into the file, so anyone can redo the check.

**Step 2: a grader.** An answer is not a string match: "26 years old" and "twenty-six" are the same answer,
and an answer can be right about half a question. So a model grades the answers, against the answer key, with
three separate jobs:

1. Is this answer right, compared to the key?
2. For every sentence that cites a source: do the quotes from that source actually say what the sentence
   says? (Here the grader is told, in so many words, that whether the sentence is *true* is none of its
   business — a true sentence with unrelated evidence is a failure.)
3. Separately, with all the sources hidden: model, how sure are you that this answer is right?

That third one is not grading, it is the competitor. The whole project claims that a confidence number built
from evidence beats a model's own feeling about itself, and this is how you test it.

**Step 3: run everything.** 28 questions in three versions, plus 12 of them again with the research agent's
thinking budget cut to one and two rounds: 108 runs in all, about an hour of wall time. The runner saves each
finished run to its own file, so stopping it costs nothing — restarting picks up where it left off. That
turned out to matter: one run died on a certificate error halfway through, and re-running the command redid
exactly that one.

**What came out**

|  | right | citations that hold up | seconds |
|---|---|---|---|
| bare model | 57% | never cites anything | 2 |
| one search | 79% | 61% | 5 |
| the research agent | **89%** | **74%** | 57 |

The clean split is on the 2026 questions: **the bare model gets 0 out of 8, and both searching versions get
8 out of 8.** That is the entire argument for retrieval in one line.

On the confidence number, our formula versus the model's own opinion of itself: our number separates right
from wrong 79 times out of 100, the model's own 59 — barely better than a coin flip. More telling is where
the two put their answers. Every single report our formula marked green or yellow was right, 34 for 34. The
model's own confidence put 54 of the 84 answers in the green, wrong ones included. It is not that the model
lies about its confidence; it is that it is cheerful about everything.

Cutting the agent's rounds down showed the loop earns its keep: one round gets 83% of the same questions
right, three rounds 100%, for 1.6 times the cost. Most runs never use the third round — the critic says
"enough" after the first — so the budget is insurance, not a treadmill.

**Interesting moments**

- **Nobody invented a quote. That was not what I expected to find.** The quote check throws out any quotation
  that cannot be found on the page it claims to come from, and across all the runs it threw out 129 of them —
  about one in eight. I had assumed these were fabrications, which is what the check was built for. So I
  fetched every one of those pages again and scored each rejected quote against it properly. Not one scored
  below 50 out of 100. Two thirds were the page's own words, re-typed with an ellipsis dropped in or two
  fragments joined; the rest were paraphrases, or a "quote" assembled out of a table. The small reading model
  does not make things up. It cannot copy. That is a much less alarming problem — and the check is still
  worth its cost, because a paraphrase in quotation marks is exactly the thing a reader would go and check
  and fail to find.
- **The agent's plan can swallow a lie in the question.** Asked who first walked on Mars in 2024, the planner
  writes sub-questions like "Which 2024 mission landed the first humans on Mars?" and "On what exact date did
  he step onto the surface?" Every search then hunts for an event that never happened, nothing is found, and
  the answer is five polite sentences of "the sources do not say". Honest, and useless. The much simpler
  version — one search, hand the raw results to the writer — does *better* here, because those raw results
  are full of pages saying no human has been to Mars, and it just reads them. The research agent's own
  discipline is what loses it: a sentence that answers none of the sub-questions is discarded before the
  writer ever sees it. Structure is not free.
- **"Therefore he was 56" is the most common bad citation in the whole project.** The answer says Nixon was
  born in 1913 with three good citations, says the landing was in July 1969 with three more, and then says
  "therefore he was 56 years old" — carrying the same citations. The grader marks it unsupported, and it is
  right: no page says that. But the confidence formula gives that sentence a green mark, because it only
  looks at *which* sources are cited, never at whether they say it. Every "how old / how long between"
  question produces one. It is the single biggest reason the citation number is 74% and not the 85% I was
  aiming at, and it is one mechanism rather than general sloppiness — which is the useful kind of failure,
  because you can fix a mechanism.
- **Six sources, all content farms, and the answer was graded correct.** For the PostgreSQL versus MySQL
  question the agent read six pages, none of them a database vendor or a benchmark project — sites that exist
  to rank for that search. The answer it wrote is plausible and cites a very precise number: "at 10M rows,
  PostgreSQL delivered 12,400 queries per second". No methodology, no hardware, no date. The quote check
  passes it, because the sentence really is on the page. The site-quality score calls all six "unknown", so
  the report comes out red, which is the system being right by accident. Checking that a model copied its
  source honestly is not the same as checking that the source is worth copying, and nothing in the project
  currently does the second.
- **The grader was harsher than I was, never softer.** I re-read 21 of its decisions by hand, three of each
  kind it can give. I agreed with 18. All three disagreements were the same shape: an answer that got part of
  the question right and honestly said the rest was missing, marked "wrong" instead of "partly right". It
  never once waved through an invented answer. So the accuracy numbers are a floor. On the citation side it
  agreed with me nine times out of nine, including a case where it knows perfectly well who Microsoft's chief
  executive was and still said the cited page does not show it.
- **I nearly caught the grader hallucinating, and the bug was mine.** One verdict said a sentence about the
  Eurovision winning song was supported, and the evidence printed underneath it never mentioned the song. I
  was about to write it up as a grader failure when I checked what the grader had actually been sent: twelve
  quotes, four of which named the song. The page that prints decisions for hand-checking was trimming the
  quote list for readability, so the hand-check was checking something the grader never saw. Now that page
  prints the grader's exact input. A review tool that quietly shows you less than the machine saw will
  manufacture bugs all day.
- **Being honest costs the same as being wrong.** A quarter of the research agent's uncited sentences are
  sentences admitting a gap — "the sources found do not say when the institute was closed". Each scores zero
  and drags the report's average down exactly as hard as an unsupported claim would. For the two impossible
  questions the final score is 0.00 for answers made entirely of honest admissions. The whole project exists
  to reward that kind of sentence, and the formula punishes it. Written up as the first thing to fix.

**What to check by hand**
```
pytest                                      # 93 tests, ~5 s, no internet
python -m eval.run_eval --report            # rebuilds the tables from saved runs, no internet, ~1 s
python -m eval.run_eval --limit 2 --only e1 --concurrency 1    # 6 real runs, about two minutes
```
Then read `eval/results/results.md` top to bottom: the bare model should be at zero on the fresh questions
and the research agent at eight of eight; the per-sentence table should go down, not up, from green to red.
Open `eval/results/judge_sample.md`, pick any citation verdict, and read the quotes under it — they are
exactly what the grader was shown, so if the verdict looks wrong, it is wrong. `eval/judge_check.md` is my
own pass over 21 of them and says where I disagreed. `eval/error_analysis.md` sorts every failure in the
whole run into five causes with real examples, and `eval/results/failures.md` lists every answer that was not
correct, each with the folder holding its full report and step log.

**Commit:** `Phase 5: evaluation and experiment results`
