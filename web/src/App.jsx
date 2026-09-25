import { useEffect, useState } from "react";
import { QuestionForm } from "./components/QuestionForm";
import { ReportView } from "./components/ReportView";
import { RunLog } from "./components/RunLog";
import { useRun } from "./lib/useRun";

const EXAMPLES = [
  "Who won the Nobel Prize in Physics in 2025 and for what?",
  "Кто стал директором ИСП РАН после Иванникова и в каком году?",
  "What was the name of the first human to walk on Mars in 2024?",
  "Чем LiteLLM отличается от vLLM и когда что выбирать?",
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("taro-theme", dark ? "dark" : "light");
    } catch {}
  }, [dark]);
  return [dark, setDark];
}

/** The legend is the point of the page: an underline says how well a sentence is backed. */
function Legend() {
  const items = [
    ["claim-high", "three good sites agree"],
    ["claim-medium", "one site, or a weak one"],
    ["claim-low", "barely backed, or not cited at all"],
  ];
  return (
    <ul className="flex flex-wrap gap-x-7 gap-y-2 font-serif text-sm text-muted dark:text-night-muted">
      {items.map(([cls, text]) => (
        <li key={cls}>
          <span className={`claim ${cls} text-ink dark:text-night-ink`}>{text}</span>
        </li>
      ))}
    </ul>
  );
}

export default function App() {
  const { runs, running, asked, start, stop } = useRun();
  const [dark, setDark] = useTheme();
  const modes = Object.keys(runs);
  const compare = modes.length > 1;

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-[76rem] px-4 pb-24 sm:px-8">
        <header className="flex items-baseline gap-4 border-b border-rule py-5 dark:border-night-rule">
          <h1 className="font-serif text-2xl tracking-tight">TARO</h1>
          <p className="font-serif text-sm text-muted dark:text-night-muted">
            An answer is only as good as the page it came from.
          </p>
          <button
            onClick={() => setDark(!dark)}
            className="ml-auto border border-rule px-2 py-1 font-mono text-xs hover:text-accent
                       dark:border-night-rule dark:hover:text-night-accent"
          >
            {dark ? "light" : "dark"}
          </button>
        </header>

        <section className="grid gap-10 py-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <div className="max-w-[46rem]">
            <QuestionForm examples={EXAMPLES} running={running} onRun={start} onStop={stop} />
          </div>
          <aside className="lg:pt-1">
            <Legend />
          </aside>
        </section>

        {asked && (
          <section className="border-t border-rule pt-8 dark:border-night-rule">
            <p className="mb-8 max-w-[46rem] font-serif text-lg leading-snug">{asked}</p>

            {compare ? (
              <>
                {running && (
                  <div className="mb-8 grid gap-4 sm:grid-cols-3">
                    {modes.map((m) => (
                      <div key={m}>
                        <p className="mb-1 font-mono text-[11px] uppercase tracking-wider opacity-60">{m}</p>
                        <RunLog events={runs[m].events} running={!runs[m].done} compact />
                      </div>
                    ))}
                  </div>
                )}
                <div className="grid gap-x-8 gap-y-12 lg:grid-cols-3">
                  {modes.map((m) => (
                    <ReportView key={m} mode={m} run={runs[m]} question={asked} compare />
                  ))}
                </div>
              </>
            ) : (
              <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
                <div className="max-w-[46rem]">
                  <ReportView mode={modes[0]} run={runs[modes[0]]} question={asked} />
                </div>
                <aside className="order-first lg:order-none lg:sticky lg:top-6 lg:self-start">
                  <h2 className="mb-2 font-sans text-xs font-semibold tracking-wide">Run log</h2>
                  <RunLog events={runs[modes[0]].events} running={!runs[modes[0]].done} />
                </aside>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
