import { useEffect, useRef, useState } from "react";
import { MODE_PICK, MODE_HINT } from "../lib/format";

const ROTATE_MS = 9000;

/** One example at a time, changing on its own until the reader starts typing or takes hold of it. */
function Suggestion({ examples, paused, onPick }) {
  const [i, setI] = useState(() => Math.floor(Math.random() * examples.length));
  const [held, setHeld] = useState(false);

  useEffect(() => {
    if (paused || held || examples.length < 2) return;
    const timer = setInterval(() => setI((n) => (n + 1) % examples.length), ROTATE_MS);
    return () => clearInterval(timer);
  }, [paused, held, examples.length]);

  return (
    <p
      className="mt-4 flex items-baseline justify-center gap-2 text-sm text-muted dark:text-night-muted"
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
    >
      <span className="shrink-0">Try</span>
      <button
        key={i}
        type="button"
        onClick={() => onPick(examples[i])}
        onFocus={() => setHeld(true)}
        onBlur={() => setHeld(false)}
        className="suggestion truncate text-left font-serif text-ink/80 underline decoration-rule
                   underline-offset-4 transition-colors hover:text-accent hover:decoration-accent
                   dark:text-night-ink/80 dark:decoration-night-rule dark:hover:text-night-accent"
      >
        {examples[i]}
      </button>
    </p>
  );
}

function Send({ disabled }) {
  return (
    <button
      type="submit"
      disabled={disabled}
      aria-label="Ask"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-white
                 transition-[opacity,transform] enabled:hover:scale-[1.06] disabled:opacity-30
                 dark:bg-night-accent dark:text-night"
    >
      <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <path d="M8 13V3M8 3 3.5 7.5M8 3l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

/**
 * The box you ask from. It is the same box in both places on the page — in the middle of an empty
 * page before anything is asked, and pinned to the top right once the research is running — so it
 * can travel between the two instead of being replaced.
 */
export function QuestionForm({ examples, running, onRun, onStop, hero }) {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("v3");
  const [focused, setFocused] = useState(false);
  const field = useRef(null);

  const grow = (el) => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, hero ? 200 : 140)}px`;
  };

  // the box shrinks when it is pinned, so the text has to be re-laid-out for the new width
  useEffect(() => {
    grow(field.current);
  }, [hero]);

  const send = () => {
    const text = question.trim();
    if (text.length < 2 || running) return;
    setQuestion("");
    requestAnimationFrame(() => grow(field.current));
    onRun(text, mode);
  };

  const pick = (example) => {
    setQuestion(example);
    field.current?.focus();
    requestAnimationFrame(() => grow(field.current));
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
    >
      <div
        className={`rounded-2xl border bg-card/85 backdrop-blur-xl transition-[box-shadow,border-color] duration-300
                    dark:bg-night-card/85 ${
                      focused
                        ? "border-accent/60 shadow-[0_18px_50px_-24px_rgba(20,25,34,0.55)] dark:border-night-accent/60"
                        : "border-rule shadow-[0_10px_34px_-22px_rgba(20,25,34,0.5)] dark:border-night-rule"
                    }`}
      >
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          ref={field}
          value={question}
          onChange={(e) => {
            setQuestion(e.target.value);
            grow(e.target);
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={1}
          placeholder={hero ? "Ask anything that can be checked against a web page" : "Ask something else"}
          className={`block w-full resize-none overflow-y-auto bg-transparent font-serif leading-snug
                      outline-none placeholder:text-muted/70 dark:placeholder:text-night-muted/70 ${
                        hero ? "px-5 pt-4 text-xl" : "px-4 pt-3 text-[0.9375rem]"
                      }`}
        />

        <div className={`flex flex-wrap items-center gap-2 ${hero ? "px-4 pb-3" : "px-3 pb-2.5"}`}>
          <div
            className="flex rounded-full border border-rule p-[2px] dark:border-night-rule"
            role="group"
            aria-label="How to answer"
          >
            {MODE_PICK.map((m) => (
              <button
                key={m.id}
                type="button"
                aria-pressed={mode === m.id}
                title={MODE_HINT[m.id]}
                onClick={() => setMode(m.id)}
                className={`rounded-full px-2 py-[3px] font-sans transition-colors sm:px-[10px] ${
                  hero ? "text-[11px] sm:text-xs" : "text-[10px]"
                } ${
                  mode === m.id
                    ? "bg-ink text-paper dark:bg-night-ink dark:text-night"
                    : "text-muted hover:text-accent dark:text-night-muted dark:hover:text-night-accent"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {running ? (
            <button
              type="button"
              onClick={onStop}
              className="ml-auto rounded-full border border-rule px-3 py-[4px] font-sans text-xs text-muted
                         transition-colors hover:border-weak hover:text-weak dark:border-night-rule
                         dark:text-night-muted dark:hover:border-weak-dark dark:hover:text-weak-dark"
            >
              Stop
            </button>
          ) : (
            <div className="ml-auto">
              <Send disabled={question.trim().length < 2} />
            </div>
          )}
        </div>
      </div>

      {hero && (
        <>
          <p className="mt-3 text-center text-xs text-muted dark:text-night-muted">{MODE_HINT[mode]}</p>
          <Suggestion examples={examples} paused={!!question || focused || running} onPick={pick} />
        </>
      )}
    </form>
  );
}
