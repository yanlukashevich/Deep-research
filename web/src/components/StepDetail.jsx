/** The inside of one step of the run: what it sent, what came back, what it decided.
 *
 * Mono is used only for text that went to or came from a machine — the query as the search tool
 * received it, a host, a count. Serif is for text a person wrote or a page said.
 */
import { host } from "../lib/format";

const thousands = (n) => n.toLocaleString("en-US");
const path = (url) => {
  try {
    const u = new URL(url);
    return u.pathname === "/" ? "" : u.pathname;
  } catch {
    return "";
  }
};

function Snippet({ text }) {
  if (!text) return null;
  return (
    <p className="mt-1 line-clamp-2 font-serif text-sm leading-snug text-muted dark:text-night-muted">{text}</p>
  );
}

function Quote({ text, tone }) {
  return (
    <p
      className={`mt-1 border-l-2 pl-3 font-serif text-sm italic leading-snug ${
        tone === "warn"
          ? "border-weak text-muted line-through decoration-weak/60 dark:border-weak-dark dark:text-night-muted"
          : "border-rule text-ink/85 dark:border-night-rule dark:text-night-ink/85"
      }`}
    >
      “{text}”
    </p>
  );
}

function Label({ children }) {
  return <h4 className="mb-2 font-sans text-xs font-semibold">{children}</h4>;
}

function Block({ block }) {
  if (block.kind === "note") {
    return <p className="max-w-[44rem] text-sm leading-relaxed text-muted dark:text-night-muted">{block.text}</p>;
  }

  if (block.kind === "quote") {
    return (
      <div>
        <Label>{block.label}</Label>
        <p className="max-w-[44rem] border-l-2 border-accent pl-3 font-serif leading-snug dark:border-night-accent">
          {block.text}
        </p>
      </div>
    );
  }

  if (block.kind === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    return (
      <div>
        <Label>{block.label}</Label>
        <Tag className="max-w-[44rem] space-y-1 font-serif leading-snug">
          {block.items.map((item, i) => (
            <li key={i} className="flex gap-3">
              <span
                className={`shrink-0 font-mono text-xs leading-6 ${
                  block.tone === "warn" ? "text-weak dark:text-weak-dark" : "text-muted dark:text-night-muted"
                }`}
              >
                {block.ordered ? i + 1 : "—"}
              </span>
              <span>{item}</span>
            </li>
          ))}
        </Tag>
      </div>
    );
  }

  if (block.kind === "lines") {
    return (
      <div>
        <Label>{block.label}</Label>
        <ul className="space-y-[3px]">
          {block.items.map((item, i) => (
            <li key={i} className="border-l border-rule pl-3 font-mono text-xs leading-5 dark:border-night-rule">
              {item}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (block.kind === "links") {
    return (
      <div>
        <Label>{block.label}</Label>
        <ul className="space-y-1">
          {block.items.map((item, i) => (
            <li key={i} className="font-mono text-xs leading-5">
              <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-accent dark:hover:text-night-accent">
                {host(item.url)}
                <span className="text-muted dark:text-night-muted">{path(item.url)}</span>
              </a>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (block.kind === "queries") {
    return (
      <ul className="space-y-5">
        {block.items.map((q, i) => (
          <li key={i}>
            <p className="font-mono text-xs leading-5">
              {q.query}
              {q.filters?.published_after && (
                <span className="text-muted dark:text-night-muted"> published_after={q.filters.published_after}</span>
              )}
            </p>
            <p className="mt-[2px] font-mono text-[11px] text-muted dark:text-night-muted">
              {q.error ? q.error : `${q.n} results in ${q.seconds.toFixed(2)} s`}
            </p>
            <ol className="mt-2 space-y-2 border-l border-rule pl-3 dark:border-night-rule">
              {q.results.map((r, j) => (
                <li key={j}>
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-serif leading-snug hover:text-accent dark:hover:text-night-accent"
                  >
                    {r.title || r.url}
                  </a>
                  <p className="font-mono text-[11px] text-muted dark:text-night-muted">
                    {host(r.url)}
                    {r.published ? ` ${r.published}` : ""}
                  </p>
                  <Snippet text={r.snippet} />
                </li>
              ))}
            </ol>
          </li>
        ))}
      </ul>
    );
  }

  if (block.kind === "pages") {
    return (
      <ul className="space-y-3">
        {block.items.map((p, i) => (
          <li key={i}>
            <a
              href={p.url}
              target="_blank"
              rel="noreferrer"
              className="font-serif leading-snug hover:text-accent dark:hover:text-night-accent"
            >
              {p.title || host(p.url)}
            </a>
            <p className="font-mono text-[11px] text-muted dark:text-night-muted">
              {p.title ? `${host(p.url)}  ` : ""}
              {p.chars ? `${thousands(p.chars)} characters in ${p.seconds.toFixed(2)} s` : ""}
            </p>
            {(p.error || p.note) && (
              <p className="font-sans text-xs text-weak dark:text-weak-dark">{p.error || p.note}</p>
            )}
          </li>
        ))}
      </ul>
    );
  }

  if (block.kind === "facts") {
    return (
      <ul className="space-y-6">
        {block.items.map((page, i) => (
          <li key={i}>
            <p className="font-mono text-[11px] text-muted dark:text-night-muted">
              {host(page.url)}
              {`  ${page.kept} kept`}
              {page.rejected ? `  ${page.rejected} thrown out` : ""}
            </p>
            {page.error && <p className="mt-1 font-sans text-xs text-weak dark:text-weak-dark">{page.error}</p>}
            <ul className="mt-2 space-y-3">
              {page.statements.map((statement, j) => (
                <li key={j}>
                  <p className="max-w-[44rem] font-serif leading-snug">{statement}</p>
                  {page.quotes[j] && <Quote text={page.quotes[j]} />}
                </li>
              ))}
              {!page.kept && !page.rejects.length && !page.error && (
                <li className="text-sm text-muted dark:text-night-muted">
                  Nothing on this page answered a sub-question.
                </li>
              )}
              {page.rejects.map((reject, j) => (
                <li key={`r${j}`}>
                  <p className="max-w-[44rem] font-serif leading-snug text-muted dark:text-night-muted">
                    {reject.statement}
                  </p>
                  <Quote text={reject.quote} tone="warn" />
                  <p className="mt-1 font-sans text-xs text-weak dark:text-weak-dark">
                    dropped: this quote is not in the page text
                  </p>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    );
  }
  return null;
}

export function StepDetail({ blocks }) {
  return (
    <div className="rail-detail mt-4 space-y-5 border-l border-rule pl-4 dark:border-night-rule">
      {blocks.map((block, i) => (
        <Block key={i} block={block} />
      ))}
    </div>
  );
}
