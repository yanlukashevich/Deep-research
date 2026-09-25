import { useCallback, useRef, useState } from "react";

const MODES = ["v1", "v2", "v3"];

const emptyRun = () => ({ events: [], report: null, markdown: "", error: null, done: false });

/** Runs a question on the server and keeps the live state of every mode it runs.
 *
 * One EventSource per run. `trace` events append to that mode's log, `report` finishes it,
 * `failed` records why it stopped. Closing the stream also stops the research on the server.
 */
export function useRun() {
  const [runs, setRuns] = useState({});       // mode -> {events, report, markdown, error, done}
  const [running, setRunning] = useState(false);
  const [asked, setAsked] = useState("");
  const sourceRef = useRef(null);

  const stop = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
    setRunning(false);
  }, []);

  const start = useCallback(
    (question, mode, useCache = true) => {
      stop();
      const modes = mode === "all" ? MODES : [mode];
      setRuns(Object.fromEntries(modes.map((m) => [m, emptyRun()])));
      setAsked(question);
      setRunning(true);

      const url = `api/run?question=${encodeURIComponent(question)}&mode=${mode}&cache=${useCache}`;
      const source = new EventSource(url);
      sourceRef.current = source;

      const patch = (m, change) =>
        setRuns((prev) => ({ ...prev, [m]: { ...(prev[m] || emptyRun()), ...change } }));

      source.addEventListener("trace", (e) => {
        const event = JSON.parse(e.data);
        setRuns((prev) => {
          const run = prev[event.mode] || emptyRun();
          return { ...prev, [event.mode]: { ...run, events: [...run.events, event] } };
        });
      });
      source.addEventListener("report", (e) => {
        const data = JSON.parse(e.data);
        patch(data.mode, { report: data.report, markdown: data.markdown, run: data.run, done: true });
      });
      source.addEventListener("failed", (e) => {
        const data = JSON.parse(e.data);
        patch(data.mode, { error: data.message, done: true });
      });
      source.addEventListener("end", () => stop());
      source.onerror = () => {
        // the server closed the stream, or it was never reachable
        setRuns((prev) => {
          const next = { ...prev };
          for (const m of modes) {
            if (!next[m]?.done) next[m] = { ...next[m], done: true, error: next[m]?.error || "Lost the connection to the server." };
          }
          return next;
        });
        stop();
      };
    },
    [stop]
  );

  return { runs, running, asked, start, stop, modes: MODES };
}
