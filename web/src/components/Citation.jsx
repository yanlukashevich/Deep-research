import { useEffect, useId, useRef, useState } from "react";
import { host } from "../lib/format";

/** A [n] marker. Hover or focus shows what that page actually said; clicking opens the page. */
export function Citation({ n, source, quotes }) {
  const [open, setOpen] = useState(false);
  const [left, setLeft] = useState(false);
  const wrap = useRef(null);
  const id = useId();

  useEffect(() => {
    if (!open || !wrap.current) return;
    // flip the card to the left edge when it would run off the screen
    const box = wrap.current.getBoundingClientRect();
    setLeft(box.left + 340 > window.innerWidth);
  }, [open]);

  if (!source) return <sup className="text-muted dark:text-night-muted">[{n}]</sup>;

  return (
    <span
      ref={wrap}
      className="relative inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <a
        href={source.url}
        target="_blank"
        rel="noreferrer"
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="mx-px align-super font-sans text-[0.68em] font-medium text-accent decoration-none
                   hover:underline dark:text-night-accent"
      >
        [{n}]
      </a>
      {open && (
        <span
          id={id}
          role="tooltip"
          className={`absolute bottom-[calc(100%+8px)] z-30 block w-[min(20rem,calc(100vw-2rem))]
                      border border-rule bg-card p-3 font-sans text-sm shadow-[0_8px_30px_rgba(21,26,35,0.18)]
                      dark:border-night-rule dark:bg-night-card ${left ? "right-0" : "left-0"}`}
        >
          <span className="block text-xs text-muted dark:text-night-muted">{host(source.url)}</span>
          <span className="mt-1 block font-serif leading-snug">{source.title || source.url}</span>
          {quotes.length > 0 ? (
            quotes.slice(0, 2).map((q, i) => (
              <span key={i} className="mt-2 block border-l-2 border-rule pl-2 font-serif italic
                                       leading-snug text-ink/85 dark:border-night-rule dark:text-night-ink/85">
                “{q}”
              </span>
            ))
          ) : (
            <span className="mt-2 block text-xs text-muted dark:text-night-muted">
              No quote was kept from this page — it was read, but nothing passed the quote check.
            </span>
          )}
          <span className="mt-2 block text-xs text-accent dark:text-night-accent">Click to open the page</span>
        </span>
      )}
    </span>
  );
}
