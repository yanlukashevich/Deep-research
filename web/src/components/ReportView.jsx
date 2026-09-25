import { useState } from "react";
import { Answer } from "./Answer";
import { Sources } from "./Sources";
import { RunLog } from "./RunLog";
import { MODE_BLURB, MODE_NAME, download, slug } from "../lib/format";

const BAR = { high: "bg-solid dark:bg-solid-dark", medium: "bg-thin dark:bg-thin-dark", low: "bg-weak dark:bg-weak-dark" };

function levelOf(score) {
  return score >= 0.75 ? "high" : score >= 0.5 ? "medium" : "low";
}

/** The overall score, as a bar the reader can compare between modes, with its reasoning. */
function Confidence({ report }) {
  const [why, setWhy] = useState(false);
  const score = report.confidence ?? 0;
  const level = levelOf(score);
  return (
    <div className="mt-8 border-t border-rule pt-4 dark:border-night-rule">
      <div className="flex items-baseline gap-3">
        <span className="font-serif text-3xl tabular-nums">{score.toFixed(2)}</span>
        <span className="text-sm text-muted dark:text-night-muted">
          confidence, {level === "high" ? "well backed" : level === "medium" ? "thinly backed" : "weakly backed"}
        </span>
        <button
          onClick={() => setWhy(!why)}
          className="ml-auto text-xs text-accent hover:underline dark:text-night-accent"
          aria-expanded={why}
        >
          {why ? "hide the maths" : "why this number"}
        </button>
      </div>
      <div className="mt-2 h-[6px] w-full bg-rule dark:bg-night-rule">
        <div className={`h-full ${BAR[level]}`} style={{ width: `${Math.max(score, 0.01) * 100}%` }} />
      </div>
      {why && (
        <p className="mt-3 text-sm leading-relaxed text-muted dark:text-night-muted">
          {report.confidence_why}
          <br />
          Per sentence: half the score comes from how many different sites back it (three is full marks),
          half from how good those sites are, minus 0.3 when the sources disagree. A sentence with no
          citation scores zero.
        </p>
      )}
    </div>
  );
}

/** What v3 decided to find out before answering. Nothing to show for v1 and v2. */
function Plan({ questions }) {
  const [open, setOpen] = useState(false);
  if (!questions?.length) return null;
  return (
    <div className="mt-4">
      <button
        onClick={() => setOpen(!open)}
        className="font-mono text-xs text-muted hover:text-accent dark:text-night-muted dark:hover:text-night-accent"
        aria-expanded={open}
      >
        {open ? "hide" : "show"} the {questions.length} questions it set out to answer
      </button>
      {open && (
        <ol className="mt-2 space-y-1 border-l border-rule pl-4 font-serif text-sm leading-snug
                       text-muted dark:border-night-rule dark:text-night-muted">
          {questions.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ol>
      )}
    </div>
  );
}

function List({ title, items }) {
  if (!items?.length) return null;
  return (
    <section className="mt-8">
      <h2 className="font-sans text-sm font-semibold">{title}</h2>
      <ul className="mt-2 space-y-1 font-serif leading-snug">
        {items.map((x, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-muted dark:text-night-muted">—</span>
            <span>{x}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Stats({ report, runName }) {
  const s = report.stats || {};
  const bits = [
    `${Math.round(s.seconds || 0)} s`,
    `${s.llm_calls || 0} LLM calls`,
    `${s.searches || 0} searches`,
    `${s.fetches || 0} pages fetched`,
    s.quotes_rejected ? `${s.quotes_rejected} quotes rejected` : null,
  ].filter(Boolean);
  return (
    <p className="mt-8 border-t border-rule pt-3 font-mono text-xs text-muted dark:border-night-rule dark:text-night-muted">
      {bits.join("   ")}
      {runName ? `   saved to runs/${runName}` : ""}
    </p>
  );
}

/** One mode's result: the answer, what it missed, the sources, and the files to take away. */
export function ReportView({ mode, run, question, compare }) {
  const { report, markdown, error, done, events, run: runName } = run;
  const name = slug(question);

  return (
    <article className={compare ? "min-w-0" : ""}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-rule pb-2 dark:border-night-rule">
        <h2 className="font-sans text-sm font-semibold">{MODE_NAME[mode]}</h2>
        <p className="text-xs text-muted dark:text-night-muted">{MODE_BLURB[mode]}</p>
      </header>

      {!done && (
        <div className="mt-3">
          <RunLog events={events} running={!done} compact={compare} />
        </div>
      )}

      {error && (
        <p className="mt-4 border-l-2 border-weak pl-3 text-sm dark:border-weak-dark">
          This run stopped: {error} — check the server terminal for the full traceback.
        </p>
      )}

      {report && (
        <>
          <Plan questions={report.subquestions} />
          <div className="mt-5">
            <Answer report={report} />
          </div>
          <Confidence report={report} />
          <List title="Where the sources disagree" items={report.contradictions} />
          <List title="What we couldn't find" items={report.not_found} />
          {compare ? <CompactSources report={report} /> : <Sources report={report} />}
          <div className="mt-6 flex flex-wrap gap-2">
            <button
              onClick={() => download(`${name}-${mode}.md`, markdown)}
              className="border border-rule px-3 py-1 text-xs hover:border-accent hover:text-accent
                         dark:border-night-rule dark:hover:border-night-accent dark:hover:text-night-accent"
            >
              Download report.md
            </button>
            <button
              onClick={() => download(`${name}-${mode}.json`, JSON.stringify(report, null, 2), "application/json")}
              className="border border-rule px-3 py-1 text-xs hover:border-accent hover:text-accent
                         dark:border-night-rule dark:hover:border-night-accent dark:hover:text-night-accent"
            >
              Download report.json
            </button>
          </div>
          <Stats report={report} runName={runName} />
        </>
      )}
    </article>
  );
}

/** In the three-way comparison the source list folds away, so the answers stay side by side. */
function CompactSources({ report }) {
  const [open, setOpen] = useState(false);
  if (!report.sources?.length) {
    return (
      <p className="mt-6 text-sm text-muted dark:text-night-muted">
        No sources: this answer comes from the model's memory alone.
      </p>
    );
  }
  return (
    <div className="mt-6">
      <button
        onClick={() => setOpen(!open)}
        className="text-xs text-accent hover:underline dark:text-night-accent"
        aria-expanded={open}
      >
        {open ? "hide sources" : `${report.sources.length} sources`}
      </button>
      {open && <Sources report={report} />}
    </div>
  );
}
