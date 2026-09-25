import { host, quality } from "../lib/format";

function Pips({ n }) {
  return (
    <span className="inline-flex gap-[3px]" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <span
          key={i}
          className={`h-[3px] w-3 ${i < n ? "bg-ink dark:bg-night-ink" : "bg-rule dark:bg-night-rule"}`}
        />
      ))}
    </span>
  );
}

/** The pages the answer stands on, numbered the way the [n] markers are. */
export function Sources({ report }) {
  const sources = report.sources || [];
  if (!sources.length) return null;
  const cited = new Set((report.sentences || []).flatMap((s) => s.citations));
  const quotesOf = (id) => (report.facts || []).filter((f) => f.source_id === id).map((f) => f.quote);

  return (
    <section className="mt-10">
      <h2 className="font-sans text-sm font-semibold">Sources</h2>
      <ol className="mt-3 divide-y divide-rule border-y border-rule dark:divide-night-rule dark:border-night-rule">
        {sources.map((s) => {
          const q = quality(s.quality);
          const quotes = quotesOf(s.id);
          return (
            <li key={s.id} className="flex gap-3 py-3">
              <span className="mt-[2px] flex h-6 w-6 shrink-0 items-center justify-center border
                               border-rule font-mono text-xs dark:border-night-rule">
                {s.id}
              </span>
              <div className="min-w-0 flex-1">
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-serif text-[1.0625rem] leading-snug hover:text-accent
                             hover:underline dark:hover:text-night-accent"
                >
                  {s.title || s.url}
                </a>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs
                                text-muted dark:text-night-muted">
                  <span className="font-mono">{host(s.url)}</span>
                  {s.published && <span>{s.published}</span>}
                  <span className="inline-flex items-center gap-2">
                    <Pips n={q.pips} />
                    {q.label}
                  </span>
                  {!cited.has(s.id) && <span>read, but the answer does not cite it</span>}
                </div>
                {quotes.slice(0, 2).map((quote, i) => (
                  <p
                    key={i}
                    className="mt-2 border-l-2 border-rule pl-3 font-serif text-sm italic leading-snug
                               text-ink/80 dark:border-night-rule dark:text-night-ink/80"
                  >
                    “{quote.length > 320 ? `${quote.slice(0, 320)}…` : quote}”
                  </p>
                ))}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
