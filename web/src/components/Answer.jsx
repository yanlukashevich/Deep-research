import { Citation } from "./Citation";

const CITATION = /\[(\d+(?:\s*[,;–-]\s*\d+)*)\]/g;
const LEVEL_CLASS = { high: "claim claim-high", medium: "claim claim-medium", low: "claim claim-low" };

function numbers(group) {
  const out = [];
  for (const part of group.split(/\s*[,;]\s*/)) {
    const range = part.match(/^(\d+)\s*[–-]\s*(\d+)$/);
    if (range) {
      const [lo, hi] = [Number(range[1]), Number(range[2])];
      if (hi - lo > 0 && hi - lo < 20) for (let i = lo; i <= hi; i++) out.push(i);
      else out.push(lo, hi);
    } else if (part.trim()) out.push(Number(part));
  }
  return out;
}

/** One sentence: its text, its [n] chips, and the underline that says how well it is backed. */
function Claim({ raw, sentence, sources, quotes }) {
  const pieces = [];
  let last = 0;
  for (const match of raw.matchAll(CITATION)) {
    if (match.index > last) pieces.push(raw.slice(last, match.index));
    for (const n of numbers(match[1])) {
      pieces.push(<Citation key={`${match.index}-${n}`} n={n} source={sources[n]} quotes={quotes[n] || []} />);
    }
    last = match.index + match[0].length;
  }
  pieces.push(raw.slice(last));

  if (!sentence) return <span>{pieces}</span>;
  return (
    <span
      className={LEVEL_CLASS[sentence.level] || ""}
      title={`confidence ${sentence.score?.toFixed(2)} — ${sentence.why}`}
    >
      {pieces}
    </span>
  );
}

/** The answer itself: paragraphs, lists and headings as the writer wrote them. */
export function Answer({ report }) {
  const sources = Object.fromEntries((report.sources || []).map((s) => [s.id, s]));
  const quotes = {};
  for (const fact of report.facts || []) (quotes[fact.source_id] ||= []).push(fact.quote);

  const lines = report.lines || [];
  const blocks = [];
  let paragraph = [];
  const flush = (key) => {
    if (paragraph.length) blocks.push(<p key={key} className="mb-4">{paragraph}</p>);
    paragraph = [];
  };

  lines.forEach((line, i) => {
    if (line.kind === "raw") {
      flush(`p${i}`);
      const text = (line.text || "").trim();
      if (text.startsWith("#")) {
        blocks.push(
          <h3 key={i} className="mt-6 mb-2 font-sans text-sm font-semibold tracking-wide">
            {text.replace(/^#+\s*/, "")}
          </h3>
        );
      }
      return;
    }
    const content = line.parts.map((part, j) => (
      <span key={j}>
        <Claim
          raw={part.raw}
          sentence={part.sentence === null ? null : report.sentences[part.sentence]}
          sources={sources}
          quotes={quotes}
        />{" "}
      </span>
    ));
    if (line.prefix) {
      flush(`p${i}`);
      blocks.push(
        <div key={i} className="mb-2 flex gap-2">
          <span className="select-none text-muted dark:text-night-muted">{line.prefix.trim()}</span>
          <span>{content}</span>
        </div>
      );
    } else {
      paragraph.push(<span key={i}>{content}</span>);
    }
  });
  flush("p-last");

  return (
    <div className="font-serif text-[1.0625rem] leading-[1.7] [text-wrap:pretty]">
      {blocks.length ? blocks : <p className="text-muted dark:text-night-muted">The run produced no answer.</p>}
    </div>
  );
}
