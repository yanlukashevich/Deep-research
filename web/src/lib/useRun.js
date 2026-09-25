import { useCallback, useRef, useState } from "react";

const MODES = ["v1", "v2", "v3"];

const emptyRun = () => ({ events: [], report: null, markdown: "", error: null, done: false });

/** Runs questions on the server and keeps the thread of everything asked so far.
 *
 * A question becomes a turn the moment it is sent, and a turn never changes again: its events, its
 * report and its error stay as they came in. One EventSource at a time, belonging to the newest
 * turn — asking again stops the run before it, and closing the stream stops the research on the
 * server too.
 */
export function useRun() {
  const [turns, setTurns] = useState([]); // [{id, question, mode, runs: {mode: run}}]
  const [running, setRunning] = useState(false);
  const sourceRef = useRef(null);
  const lastId = useRef(0);

  const stop = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
    setRunning(false);
  }, []);

  const start = useCallback(
    (question, mode) => {
      stop();
      const id = (lastId.current += 1);
      const modes = mode === "all" ? MODES : [mode];
      setTurns((prev) => [
        ...prev,
        { id, question, mode, runs: Object.fromEntries(modes.map((m) => [m, emptyRun()])) },
      ]);
      setRunning(true);

      /** Change one mode's run inside this turn, leaving every other turn alone. */
      const patch = (m, change) =>
        setTurns((prev) =>
          prev.map((turn) =>
            turn.id !== id
              ? turn
              : {
                  ...turn,
                  runs: {
                    ...turn.runs,
                    [m]: { ...(turn.runs[m] || emptyRun()), ...(typeof change === "function" ? change(turn.runs[m] || emptyRun()) : change) },
                  },
                }
          )
        );

      const source = new EventSource(`api/run?question=${encodeURIComponent(question)}&mode=${mode}`);
      sourceRef.current = source;

      source.addEventListener("trace", (e) => {
        const event = JSON.parse(e.data);
        patch(event.mode, (run) => ({ events: [...run.events, event] }));
      });
      source.addEventListener("report", (e) => {
        const data = JSON.parse(e.data);
        // `lines` (the answer split into sentences) travels beside the report, not inside it
        patch(data.mode, {
          report: { ...data.report, lines: data.lines || [] },
          markdown: data.markdown,
          run: data.run,
          done: true,
        });
      });
      source.addEventListener("failed", (e) => {
        const data = JSON.parse(e.data);
        patch(data.mode, { error: data.message, done: true });
      });
      source.addEventListener("end", () => stop());
      source.onerror = () => {
        // the server closed the stream, or it was never reachable
        for (const m of modes) {
          patch(m, (run) =>
            run.done ? {} : { done: true, error: run.error || "Lost the connection to the server." }
          );
        }
        stop();
      };
    },
    [stop]
  );

  return { turns, running, start, stop, modes: MODES };
}
