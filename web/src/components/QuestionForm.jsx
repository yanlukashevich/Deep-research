import { useState } from "react";

const MODES = [
  { id: "v3", label: "v3" },
  { id: "v2", label: "v2" },
  { id: "v1", label: "v1" },
  { id: "all", label: "all three" },
];

export function QuestionForm({ examples, running, onRun, onStop }) {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState("v3");

  const submit = (e) => {
    e.preventDefault();
    const text = question.trim();
    if (text.length > 1 && !running) onRun(text, mode);
  };

  return (
    <form onSubmit={submit}>
      <label htmlFor="question" className="sr-only">Your question</label>
      <textarea
        id="question"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) submit(e);
        }}
        rows={2}
        placeholder="Ask anything that can be checked against a web page"
        className="w-full resize-none border-b-2 border-ink bg-transparent pb-2 font-serif text-xl
                   leading-snug outline-none placeholder:text-muted/70 focus:border-accent
                   dark:border-night-ink dark:placeholder:text-night-muted/70 dark:focus:border-night-accent"
      />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="flex border border-rule dark:border-night-rule" role="group" aria-label="Mode">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={mode === m.id}
              onClick={() => setMode(m.id)}
              className={`px-3 py-[6px] font-mono text-xs transition-colors ${
                mode === m.id
                  ? "bg-ink text-paper dark:bg-night-ink dark:text-night"
                  : "hover:text-accent dark:hover:text-night-accent"
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
            className="border border-rule px-4 py-[6px] text-sm hover:border-weak hover:text-weak
                       dark:border-night-rule dark:hover:border-weak-dark dark:hover:text-weak-dark"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            className="bg-accent px-5 py-[7px] text-sm text-white hover:opacity-90
                       dark:bg-night-accent dark:text-night"
          >
            Research
          </button>
        )}
        <span className="text-xs text-muted dark:text-night-muted">
          v3 takes about a minute. The steps show up as they happen.
        </span>
      </div>

      <div className="mt-5 flex flex-wrap gap-x-4 gap-y-2">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => setQuestion(example)}
            className="text-left font-serif text-sm text-muted underline decoration-rule
                       underline-offset-4 hover:text-accent hover:decoration-accent
                       dark:text-night-muted dark:decoration-night-rule dark:hover:text-night-accent"
          >
            {example}
          </button>
        ))}
      </div>
    </form>
  );
}
