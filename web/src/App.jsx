import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { QuestionForm } from "./components/QuestionForm";
import { ReportView } from "./components/ReportView";
import { MODE_NAME } from "./lib/format";
import { useRun } from "./lib/useRun";

const EXAMPLES = [
  "Кто выиграл последний чемпионат мира по футболу?",
  "Кто получил Нобелевскую премию по физике в 2025 году и за что?",
  "Какая сейчас ключевая ставка Банка России?",
  "В каком городе пройдут зимние Олимпийские игры 2026 года?",
  "Чем LiteLLM отличается от vLLM и когда что выбирать?",
  "Кто стал директором ИСП РАН после Иванникова и в каком году?",
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

/** The composer is one element that lives in two places; this is how it travels between them.
 *
 * The rect is taken in the click handler, before React moves the box, and the difference is played
 * back as a transform: the box appears to fly from the middle of the page to the top right corner
 * instead of vanishing from one place and appearing in another. */
function useFlight(ref, from, asked) {
  useLayoutEffect(() => {
    const el = ref.current;
    const start = from.current;
    from.current = null;
    if (!el || !start || !asked) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const end = el.getBoundingClientRect();
    const dx = start.left - end.left;
    const dy = start.top - end.top;
    if (Math.abs(dx) < 2 && Math.abs(dy) < 2 && Math.abs(start.width - end.width) < 2) return;
    el.animate(
      [
        { transform: `translate(${dx}px, ${dy}px)`, width: `${start.width}px` },
        { transform: "translate(0, 0)", width: `${end.width}px` },
      ],
      { duration: 680, easing: "cubic-bezier(0.22, 1, 0.36, 1)" }
    );
  }, [asked, ref, from]);
}

/** One question and everything that came of it. */
function Turn({ turn, latest }) {
  const modes = Object.keys(turn.runs);
  const compare = modes.length > 1;
  const box = useRef(null);

  // a new question scrolls itself into view, the way a message does
  useEffect(() => {
    if (!latest || !box.current) return;
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.current.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  }, [latest]);

  return (
    <section
      ref={box}
      className="scroll-mt-28 border-t border-rule pb-20 pt-10 first:border-0 first:pt-2 dark:border-night-rule"
    >
      <header className="reveal">
        <h2 className="max-w-[46rem] font-serif text-[1.5rem] leading-snug [text-wrap:pretty] sm:text-[1.75rem]">
          {turn.question}
        </h2>
        <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-muted dark:text-night-muted">
          {turn.mode === "all" ? "all three, side by side" : `${MODE_NAME[turn.mode]} · ${turn.mode}`}
        </p>
      </header>

      {compare ? (
        <div className="mt-8 grid gap-x-8 gap-y-14 lg:grid-cols-3">
          {modes.map((m) => (
            <ReportView key={m} mode={m} run={turn.runs[m]} question={turn.question} compare />
          ))}
        </div>
      ) : (
        <div className="mt-6">
          <ReportView mode={modes[0]} run={turn.runs[modes[0]]} question={turn.question} />
        </div>
      )}
    </section>
  );
}

export default function App() {
  const { turns, running, start, stop } = useRun();
  const [dark, setDark] = useTheme();
  const asked = turns.length > 0;
  const composer = useRef(null);
  const from = useRef(null);
  useFlight(composer, from, asked);

  const ask = (question, mode) => {
    from.current = asked ? null : composer.current?.getBoundingClientRect() || null;
    start(question, mode);
  };

  return (
    <div className="min-h-screen">
      {/* the bar is always there; the right half of it is where the composer lands */}
      <header
        className={`fixed inset-x-0 top-0 z-30 flex items-center gap-4 px-4 py-4 transition-colors duration-500
                    sm:px-8 ${asked ? "bg-paper/85 backdrop-blur-md dark:bg-night/85" : ""}`}
      >
        <h1 className="font-serif text-lg tracking-tight">TARO</h1>
        <p className="hidden font-serif text-sm text-muted sm:block dark:text-night-muted">
          An answer is only as good as the page it came from.
        </p>
        <button
          onClick={() => setDark(!dark)}
          className="rounded-full border border-rule px-2 py-[3px] font-sans text-[11px] text-muted
                     transition-colors hover:border-accent hover:text-accent dark:border-night-rule
                     dark:text-night-muted dark:hover:border-night-accent dark:hover:text-night-accent"
        >
          {dark ? "light" : "dark"}
        </button>
      </header>

      <div
        ref={composer}
        className={`fixed z-40 ${
          asked
            ? "left-3 right-3 top-[4.25rem] sm:left-auto sm:right-6 sm:top-3 sm:w-[24rem] lg:w-[27rem]"
            : "inset-x-5 top-[42vh] mx-auto max-w-[42rem] sm:inset-x-8"
        }`}
      >
        <QuestionForm examples={EXAMPLES} running={running} onRun={ask} onStop={stop} hero={!asked} />
      </div>

      {asked ? (
        <main className="mx-auto max-w-[66rem] px-4 pb-24 pt-[9.5rem] sm:px-8 sm:pt-24">
          {turns.map((turn, i) => (
            <Turn key={turn.id} turn={turn} latest={i === turns.length - 1} />
          ))}
        </main>
      ) : (
        <main className="pointer-events-none fixed inset-x-0 top-0 flex h-[42vh] items-end justify-center px-5">
          <div className="reveal max-w-[38rem] pb-10 text-center">
            <p className="font-serif text-[1.75rem] leading-tight [text-wrap:balance] sm:text-[2.125rem]">
              What should be looked up?
            </p>
            <p className="mx-auto mt-4 max-w-[32rem] text-sm leading-relaxed text-muted dark:text-night-muted">
              TARO reads the web while you wait and answers only from the pages it opened. Every
              sentence carries the sites behind it and a mark for how well they hold it up.
            </p>
          </div>
        </main>
      )}
    </div>
  );
}
