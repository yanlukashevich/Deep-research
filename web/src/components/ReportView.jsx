import { useMemo, useState } from "react";
import { Answer } from "./Answer";
import { RunGraph, Ticker } from "./RunGraph";
import { RunStats, Confidence } from "./RunStats";
import { buildGraph, currentStep } from "../lib/graph";
import { MODE_BLURB, MODE_NAME, download, slug } from "../lib/format";

/** Something the run wants to say beside the answer: where sources disagreed, what it never found. */
function Aside({ title, items, tone }) {
  const [open, setOpen] = useState(false);
  if (!items?.length) return null;
  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={`inline-flex items-center gap-2 rounded-full border px-3 py-[5px] font-sans text-xs
                    transition-colors ${
                      tone === "warn"
                        ? "border-weak/40 text-weak hover:bg-weak/5 dark:border-weak-dark/40 dark:text-weak-dark"
                        : "border-rule text-muted hover:border-ink/25 dark:border-night-rule dark:text-night-muted"
                    }`}
      >
        <span className={`h-[5px] w-[5px] rounded-full ${tone === "warn" ? "bg-weak dark:bg-weak-dark" : "bg-muted dark:bg-night-muted"}`} />
        {title} · {items.length}
      </button>
      <div className={`fold ${open ? "fold-open" : ""}`}>
        <div>
          <ul className="mt-2 max-w-[44rem] space-y-1 font-serif leading-snug">
            {items.map((x, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-muted dark:text-night-muted">—</span>
                <span>{x}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

/**
 * One run, from the outside in: the graph of how it worked while it works, then the answer, and
 * under the answer everything else — the confidence, the numbers, the sources — folded away until
 * the reader wants it. The text is the point; the rest is evidence about the text.
 */
export function ReportView({ mode, run, question, compare = false }) {
  const { report, markdown, error, done, events, run: runName } = run;
  const graph = useMemo(() => buildGraph(events, question), [events, question]);
  const name = slug(question);

  return (
    <article className={compare ? "min-w-0" : ""}>
      {compare && (
        <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-rule pb-2 dark:border-night-rule">
          <h3 className="font-sans text-sm font-semibold">{MODE_NAME[mode]}</h3>
          <span className="font-mono text-[11px] text-muted dark:text-night-muted">{mode}</span>
        </header>
      )}

      {compare && !done && (
        <div className="mt-3">
          <Ticker text={currentStep(graph)} />
        </div>
      )}

      {!compare && <RunGraph graph={graph} running={!done} done={done} />}

      <div className={compare ? "" : "max-w-[52rem]"}>
      {error && (
        <p className="mt-6 rounded-xl border border-weak/40 bg-weak/5 p-4 text-sm dark:border-weak-dark/40">
          This run stopped: {error} — the server terminal has the full traceback.
        </p>
      )}

      {!report && !error && !compare && (
        <p className="mt-10 font-serif text-lg text-muted dark:text-night-muted">
          <span className="breathing">Reading the web, writing nothing yet.</span>
        </p>
      )}

      {report && (
        <>
          <div className={compare ? "mt-5" : "mt-10"}>
            {compare && (
              <p className="mb-3 text-xs text-muted dark:text-night-muted">{MODE_BLURB[mode]}</p>
            )}
            <div className="reveal">
              <Answer report={report} large={!compare} />
            </div>
            <Aside title="Where the sources disagree" items={report.contradictions} tone="warn" />
            <Aside title="What it could not find" items={report.not_found} />
          </div>

          <Confidence report={report} />
          <RunStats graph={graph} report={report} live={!done} />

          {compare && (
            <div className="mt-6">
              <RunGraph graph={graph} running={!done} done={done} compact />
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              onClick={() => download(`${name}-${mode}.md`, markdown)}
              className="rounded-full border border-rule px-3 py-[5px] font-sans text-xs text-muted
                         transition-colors hover:border-accent hover:text-accent
                         dark:border-night-rule dark:text-night-muted dark:hover:border-night-accent dark:hover:text-night-accent"
            >
              report.md
            </button>
            <button
              onClick={() => download(`${name}-${mode}.json`, JSON.stringify(report, null, 2), "application/json")}
              className="rounded-full border border-rule px-3 py-[5px] font-sans text-xs text-muted
                         transition-colors hover:border-accent hover:text-accent
                         dark:border-night-rule dark:text-night-muted dark:hover:border-night-accent dark:hover:text-night-accent"
            >
              report.json
            </button>
            {runName && (
              <span className="font-mono text-[11px] text-muted dark:text-night-muted">runs/{runName}</span>
            )}
          </div>
        </>
      )}
      </div>
    </article>
  );
}
