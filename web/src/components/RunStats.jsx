import { useEffect, useRef, useState } from "react";
import { Sources } from "./Sources";
import { compact, estimateCost, host, money, RATES, shortModel, thousands } from "../lib/format";

/**
 * Everything about a run that is not the answer: the confidence, and then the cost of getting
 * there — model calls, tokens, searches, pages, facts, money. One tile opens at a time, so the
 * page stays a page of prose with a strip of numbers under it, not a dashboard.
 */

const reduced = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A number that rolls to its new value, so a figure rising during the run is visible as movement. */
function useCountUp(value, ms = 600) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (reduced()) {
      from.current = value;
      setShown(value);
      return;
    }
    const start = performance.now();
    const a = from.current;
    if (a === value) return;
    let raf = 0;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / ms);
      const eased = 1 - (1 - p) ** 3;
      const at = a + (value - a) * eased;
      from.current = at;
      setShown(at);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return shown;
}

function Tile({ id, value, unit, label, hint, open, onToggle }) {
  const rolled = useCountUp(typeof value === "number" ? value : 0);
  const shown = typeof value === "number" ? hint(rolled) : value;
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={`group min-w-[6.5rem] flex-1 rounded-xl border px-3 py-2.5 text-left transition-colors
                  ${open
                    ? "border-accent bg-card dark:border-night-accent dark:bg-night-card"
                    : "border-rule bg-card/50 hover:border-ink/25 dark:border-night-rule dark:bg-night-card/50 dark:hover:border-night-ink/25"}`}
    >
      <span className="flex items-baseline gap-1">
        <span className="font-serif text-[1.375rem] leading-none tabular-nums">{shown}</span>
        {unit && <span className="font-mono text-[11px] text-muted dark:text-night-muted">{unit}</span>}
      </span>
      <span className="mt-[6px] block font-mono text-[10px] uppercase tracking-[0.1em] text-muted dark:text-night-muted">
        {label}
      </span>
    </button>
  );
}

function Panel({ open, children }) {
  return (
    <div className={`fold ${open ? "fold-open" : ""}`}>
      <div>
        <div className="mt-3 rounded-xl border border-rule bg-card/60 p-4 dark:border-night-rule dark:bg-night-card/60">
          {children}
        </div>
      </div>
    </div>
  );
}

function Note({ children }) {
  return <p className="max-w-[46rem] text-sm leading-relaxed text-muted dark:text-night-muted">{children}</p>;
}

function Table({ head, rows }) {
  if (!rows.length) return null;
  return (
    <table className="mt-3 w-full max-w-[46rem] border-collapse font-mono text-xs">
      <thead>
        <tr className="border-b border-rule text-left text-muted dark:border-night-rule dark:text-night-muted">
          {head.map((h, i) => (
            <th key={i} className={`py-1 font-normal ${i ? "text-right" : ""}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} className="border-b border-rule/50 last:border-0 dark:border-night-rule/50">
            {row.map((cell, j) => (
              <td key={j} className={`py-[5px] ${j ? "text-right tabular-nums" : "pr-3"}`}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The score as a bar the reader can read as a percentage, with the sentence mix under it. */
export function Confidence({ report }) {
  const [open, setOpen] = useState(false);
  const onToggle = () => setOpen(!open);
  const score = report.confidence ?? 0;
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const percent = useCountUp(grown ? score * 100 : 0, 900);

  const level = score >= 0.75 ? "high" : score >= 0.5 ? "medium" : "low";
  const words = { high: "well backed", medium: "thinly backed", low: "weakly backed" }[level];
  const counts = { high: 0, medium: 0, low: 0 };
  for (const s of report.sentences || []) counts[s.level || "low"] += 1;
  const total = (report.sentences || []).length || 1;
  const bar = { high: "bg-solid dark:bg-solid-dark", medium: "bg-thin dark:bg-thin-dark", low: "bg-weak dark:bg-weak-dark" };

  return (
    <section className="mt-9 border-t border-rule pt-5 dark:border-night-rule">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-serif text-[2rem] leading-none tabular-nums">{Math.round(percent)}%</span>
        <span className="text-sm text-muted dark:text-night-muted">confidence · {words}</span>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="ml-auto font-sans text-xs text-accent hover:underline dark:text-night-accent"
        >
          {open ? "hide the maths" : "why this number"}
        </button>
      </div>

      <div className="mt-3 h-[8px] w-full overflow-hidden rounded-full bg-rule dark:bg-night-rule">
        <div
          className={`h-full rounded-full ${bar[level]} transition-[width] duration-[900ms] ease-out`}
          style={{ width: `${(grown ? score : 0) * 100}%` }}
        />
      </div>

      {(report.sentences || []).length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="flex h-[4px] w-full max-w-[22rem] overflow-hidden rounded-full" aria-hidden="true">
            {["high", "medium", "low"].map((k) =>
              counts[k] ? (
                <span key={k} className={`${bar[k]} h-full`} style={{ width: `${(counts[k] / total) * 100}%` }} />
              ) : null
            )}
          </span>
          <span className="font-mono text-[11px] text-muted dark:text-night-muted">
            {counts.high} well backed · {counts.medium} thin · {counts.low} weak, of {total} sentences
          </span>
        </div>
      )}

      <Panel open={open}>
        <Note>{report.confidence_why}</Note>
        <p className="mt-3 max-w-[46rem] text-sm leading-relaxed text-muted dark:text-night-muted">
          Per sentence: half the score comes from how many different sites back it (three is full marks),
          half from how good those sites are, minus 0.3 when the sources disagree. A sentence with no
          citation scores zero. The number above is the average over every sentence.
        </p>
        <p className="mt-3 max-w-[46rem] font-serif text-[0.9375rem] leading-[1.9]">
          The marks under the answer: <span className="claim claim-high">three good sites agree</span>,{" "}
          <span className="claim claim-medium">one site, or a weak one</span>,{" "}
          <span className="claim claim-low">barely backed, or not cited at all</span>.
        </p>
        <ol className="mt-4 max-w-[46rem] space-y-2">
          {(report.sentences || []).map((s, i) => (
            <li key={i} className="flex gap-3">
              <span className="mt-[6px] h-[4px] w-10 shrink-0 rounded-full bg-rule dark:bg-night-rule">
                <span className={`block h-full rounded-full ${bar[s.level || "low"]}`} style={{ width: `${(s.score || 0) * 100}%` }} />
              </span>
              <span className="min-w-0">
                <span className="font-serif text-sm leading-snug">{s.text}</span>
                <span className="mt-[2px] block font-mono text-[11px] text-muted dark:text-night-muted">
                  {(s.score ?? 0).toFixed(2)} — {s.why}
                </span>
              </span>
            </li>
          ))}
        </ol>
      </Panel>
    </section>
  );
}

export function RunStats({ graph, report, live }) {
  const [open, setOpen] = useState(null);
  const toggle = (id) => setOpen(open === id ? null : id);

  const stats = { ...graph.stats, ...(report?.stats || {}) };
  const tokens = (stats.prompt_tokens || 0) + (stats.completion_tokens || 0);
  const cost = estimateCost(stats);
  const purposes = Object.entries(graph.stats.by_purpose || {});
  const searches = graph.rounds.flatMap((r) => r.searches);
  const pages = graph.rounds.flatMap((r) => r.pages);
  const cited = new Set((report?.sources || []).map((s) => s.url));

  const tiles = [
    { id: "time", value: stats.seconds || 0, unit: "s", label: "start to answer", hint: (n) => n.toFixed(1) },
    { id: "calls", value: stats.llm_calls || 0, label: "model calls", hint: (n) => Math.round(n) },
    { id: "tokens", value: tokens, label: "tokens of context", hint: compact },
    { id: "searches", value: stats.searches || 0, label: "web searches", hint: (n) => Math.round(n) },
    { id: "pages", value: stats.fetches || 0, label: "pages fetched", hint: (n) => Math.round(n) },
    { id: "facts", value: stats.facts_kept || 0, label: "quoted facts", hint: (n) => Math.round(n) },
    { id: "sources", value: (report?.sources || []).length, label: "sources cited", hint: (n) => Math.round(n) },
    { id: "cost", value: money(cost), label: "est. cost", hint: (n) => n },
  ];

  return (
    <section className="mt-8">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted dark:text-night-muted">
        What the run cost {live && <span className="breathing">· still running</span>}
      </h3>
      <div className="mt-3 flex flex-wrap gap-2">
        {tiles.map((tile) => (
          <Tile key={tile.id} {...tile} open={open === tile.id} onToggle={() => toggle(tile.id)} />
        ))}
      </div>

      <Panel open={open === "time"}>
        <Note>
          {(stats.seconds || 0).toFixed(1)} seconds from the question to the finished answer, of which
          the models were busy {(graph.stats.llm_seconds || 0).toFixed(1)} seconds — more than the run
          took, because the searches and the page readings happen several at a time.
        </Note>
        <Table
          head={["step", "calls", "seconds"]}
          rows={purposes.map(([name, p]) => [name, p.calls, p.seconds.toFixed(1)])}
        />
      </Panel>

      <Panel open={open === "calls"}>
        <Note>
          Every call to a model, by what it was for. Planning, criticising and writing use the main
          model; reading a page uses the fast one, once per page.
        </Note>
        <Table
          head={["step", "model", "calls", "tokens"]}
          rows={purposes.map(([name, p]) => [name, shortModel(p.model), p.calls, thousands(p.tokens)])}
        />
      </Panel>

      <Panel open={open === "tokens"}>
        <Note>
          {thousands(stats.prompt_tokens || 0)} tokens went into the models and{" "}
          {thousands(stats.completion_tokens || 0)} came back. The context never holds a whole page:
          each page is trimmed to the passages that match the question before the model sees it.
        </Note>
        <Table
          head={["step", "tokens", "share"]}
          rows={purposes.map(([name, p]) => [
            name,
            thousands(p.tokens),
            `${Math.round((p.tokens / (tokens || 1)) * 100)}%`,
          ])}
        />
      </Panel>

      <Panel open={open === "searches"}>
        <Note>
          Every query the agent wrote, in the order it sent them. Nothing is cached: each one is a
          live call, so an answer is never older than the run.
        </Note>
        <ul className="mt-3 max-w-[46rem] space-y-2">
          {searches.map((s) => (
            <li key={s.id} className="flex flex-wrap items-baseline justify-between gap-x-4 border-b border-rule/50 pb-2 last:border-0 dark:border-night-rule/50">
              <span className="min-w-0 flex-1 font-mono text-xs">{s.query.query}</span>
              <span className="font-mono text-[11px] text-muted dark:text-night-muted">
                {s.query.error ? s.query.error : `${s.query.n} results · ${s.query.seconds.toFixed(2)} s`}
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel open={open === "pages"}>
        <Note>
          {stats.fetches || 0} pages were opened and{" "}
          {compact(graph.stats.chars || 0)} characters of text came back.
          {stats.quotes_rejected
            ? ` ${stats.quotes_rejected} quotes were thrown out because the words were not on the page.`
            : " Every quote the model produced was found on its page."}
        </Note>
        <ul className="mt-3 max-w-[46rem] space-y-2">
          {pages.map((p) => (
            <li key={p.id} className="border-b border-rule/50 pb-2 last:border-0 dark:border-night-rule/50">
              <a href={p.url} target="_blank" rel="noreferrer" className="font-serif text-sm leading-snug hover:text-accent dark:hover:text-night-accent">
                {p.page.title || p.url}
              </a>
              <p className="font-mono text-[11px] text-muted dark:text-night-muted">
                {host(p.url)}
                {p.page.chars ? ` · ${thousands(p.page.chars)} characters` : ""}
                {p.extract ? ` · ${p.extract.kept} facts kept` : ""}
                {cited.has(p.url) ? " · cited" : ""}
              </p>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel open={open === "facts"}>
        <Note>
          A fact is one statement plus the exact sentence from the page that says it. Plain code
          looks that quote up in the page text with a fuzzy match and drops the fact when it is not
          there, so the writer never sees an invented quote
          {stats.quotes_rejected ? `: ${stats.quotes_rejected} were dropped this way.` : "."}
        </Note>
        <Table
          head={["", "count"]}
          rows={[
            ["facts kept", stats.facts_kept || 0],
            ["quotes thrown out", stats.quotes_rejected || 0],
            ["rounds of search and criticism", stats.rounds || 0],
            ["contradictions the critic marked", (report?.contradictions || []).length],
          ]}
        />
      </Panel>

      <Panel open={open === "sources"}>
        {report?.sources?.length ? (
          <Sources report={report} inline />
        ) : (
          <Note>No sources: this answer comes from the model's memory alone.</Note>
        )}
      </Panel>

      <Panel open={open === "cost"}>
        <Note>
          An estimate, not a bill. This demo talks to a shared LiteLLM gateway that is not billed per
          token, so the figure is what the same traffic would cost on a commercial host of the same
          open-weight models: ${RATES.prompt.toFixed(2)} per million tokens in and $
          {RATES.completion.toFixed(2)} per million out. Searches and page fetches are not counted.
        </Note>
        <Table
          head={["", "tokens", "estimate"]}
          rows={[
            ["into the models", thousands(stats.prompt_tokens || 0), money(((stats.prompt_tokens || 0) * RATES.prompt) / 1e6)],
            ["back from them", thousands(stats.completion_tokens || 0), money(((stats.completion_tokens || 0) * RATES.completion) / 1e6)],
            ["together", thousands(tokens), money(cost)],
          ]}
        />
      </Panel>
    </section>
  );
}
