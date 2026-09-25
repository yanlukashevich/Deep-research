import { useEffect, useRef } from "react";
import { describe } from "../lib/format";

/** What the agent is doing, line by line, as it happens. */
export function RunLog({ events, running, compact = false }) {
  const lines = events.map((e) => ({ t: e.t, text: describe(e) })).filter((l) => l.text);
  const box = useRef(null);

  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines.length]);

  if (!lines.length && !running) return null;
  const last = lines[lines.length - 1];

  if (compact) {
    return (
      <p className="font-mono text-xs text-muted dark:text-night-muted">
        {running && <Dot />}
        {last ? last.text : "starting"}
      </p>
    );
  }

  return (
    <div
      ref={box}
      className="max-h-[22rem] overflow-y-auto pr-2 font-mono text-xs leading-relaxed
                 text-muted dark:text-night-muted"
    >
      {lines.map((line, i) => (
        <p key={i} className="log-line flex gap-3 py-[2px]">
          <span className="w-10 shrink-0 text-right tabular-nums opacity-60">{line.t.toFixed(1)}</span>
          <span className={i === lines.length - 1 && running ? "text-ink dark:text-night-ink" : ""}>
            {line.text}
          </span>
        </p>
      ))}
      {running && (
        <p className="flex gap-3 py-[2px]">
          <span className="w-10 shrink-0" />
          <Dot />
        </p>
      )}
    </div>
  );
}

function Dot() {
  return (
    <span className="mr-2 inline-block h-2 w-2 animate-pulse bg-accent align-middle dark:bg-night-accent" />
  );
}
