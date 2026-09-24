# Work log

A simple diary of what the agent did in each phase. New entries go at the bottom, and old entries are never rewritten.
(For the *current* state and next steps, see `HANDOFF.md`.)

---

## Phase 0: project setup (2026-09-23)

**What I did, step by step**
1. Read the plan and the assignment. There was no `HANDOFF.md`, so I started from Phase 0.
2. Created `.gitignore` so that `.env` (keys), `task.md` (also has keys), `.venv`, `cache/` and `runs/` never go into git.
3. Created the `.venv` virtual environment and installed the libraries from `requirements.txt`.
4. Put the keys in `.env` and created `.env.example` with no real values.
5. Tested Keenable search: listed its 2 tools, then ran 1 search and 1 page fetch. Both work and are fast (under half a second).
6. Listed the language models on the LiteLLM server (7 models) and wrote a small benchmark (`scripts/model_bench.py`) that checks each model for:
   - correct JSON
   - quotes copied exactly from the text
   - speed
   - quality of Russian
   - how long a text it can read
7. Picked the models based on the results, then ran the final smoke test: 1 LLM call, 1 search, 1 fetch.
8. Wrote `HANDOFF.md`, updated `CLAUDE.md` and made the commit.

**What came out**
- A working project skeleton with all libraries installed and secrets kept safe.
- Main model: **gpt-oss-120b** (fast, reliable). Fast model for reading pages: **gemma4:31b**.
- Two models turned out to be broken on the server: `qwen3.6` doesn't answer, and `glm-4.7-flash` fails on JSON.

**Problems and how I solved them**
- The `mcp` library is a new version (2.x) with different function names than the docs. I found the right names in its source code.
- The Windows console couldn't print Russian letters. Fix: switch output to UTF-8.
- **My mistake:** once a command hung because I left a stray `cat >` in it that waited for keyboard input. I stopped it and reran it correctly.
- **My mistake:** the benchmark looked frozen for about 8 minutes. The broken `qwen3.6` model never answered, and I had piped the output through `tail`, which shows nothing until the very end. Fix: shorter timeouts, a time limit per model, and results printed as soon as each model finishes.

**Commit:** `Phase 0: project setup`

---

## Phase 1: foundation, v1 bare LLM, v2 simple RAG (2026-09-23)

**What I did, step by step**
1. Read `HANDOFF.md` and the plan. Phase 0 was done, so this session was Phase 1.
2. Looked at the raw output of Keenable once more (search results are plain text blocks separated by `---`, a failed page fetch comes back marked as an error), so the parser matches reality.
3. Wrote the foundation:
   - `config.py`: reads the keys and model names.
   - `llm.py`: talks to the language model, retries when the server has trouble, and at most 3 calls at a time. When we ask for JSON, it checks the JSON and, if it's wrong, tells the model the error and asks again.
   - `search.py`: search and page fetch through Keenable, saved on disk so a repeated question costs nothing.
   - `report.py`: a step log (`trace.jsonl`) written as the run goes, plus the final `report.md` and `report.json`.
   - `text.py`: splits the answer into sentences and reads the `[1][2]` citations.
4. Wrote v1 (the model answers alone) and v2 (1 search → 8 best results → answer with `[n]`), plus the `python -m taro "question" --mode v1|v2` command.
5. Wrote 16 small tests that run without internet.
6. Ran real questions in English and Russian, and a trick question ("first human on Mars in 2024").

**What came out**
- v1 honestly says it doesn't know about the 2025 Nobel Prize, which is a good baseline.
- v2 answers correctly (Clarke, Devoret, Martinis) with citations in about 5 seconds, and for the Mars question says the sources don't mention it.
- A repeated question uses the saved search result (cache hit).
- Interesting v2 mistake: asked who led ISP RAS after Ivannikov, it said "after his death", but he died in 2016 and the new director was appointed in 2015. The model filled a gap on its own. This is exactly what v3 must prevent, and it's a good example for the report.

**Problems and how I solved them**
- **My mistake:** the retry logger read the previous error at the wrong moment (the retry library had already cleared it), which crashed the test. Fix: log the error in the library's "before waiting" hook.
- **My mistake:** the sentence splitter cut "Michel H. Devoret" into pieces at the initial "H.", so the first pieces lost their citations. I found it by reading the saved report. Fix: don't split after single-letter initials and common abbreviations (Dr., им., г. …), and added a test for it.
- Some search results have HTML inside the title (`<br/><small>…`). Fix: strip the tags.
- Removing the model's own `【source】` markers left double spaces. Fix: clean spaces after removing the markers.
- One test run took about 5 minutes for no clear reason (it normally takes 5 seconds). A rerun was normal, so it was a one-time slowdown on the machine, not in the code.

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
