import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { currentStep, graphSummary } from "../lib/graph";
import { host } from "../lib/format";
import { StepDetail } from "./StepDetail";

/**
 * The research drawn as the graph it is: the question at the top, the planner under it, the
 * searches fanning out, the pages each search found hanging under it, and everything gathering
 * back into the critic before the writer.
 *
 * The nodes are laid out by ordinary flexbox rows, and the edges are measured from the DOM after
 * every render, so a row that wraps on a narrow screen still gets its curves drawn correctly.
 */

/** Steps the model itself took. A filled marker is the model; a hollow one is code or the search. */
const MODEL_STEPS = new Set(["plan", "critic", "write", "answer"]);

const same = (a, b) =>
  a.length === b.length && a.every((x, i) => x.d === b[i].d && x.live === b[i].live && x.id === b[i].id);

function Marker({ kind, running, tone }) {
  const filled = MODEL_STEPS.has(kind);
  const colour = tone === "warn"
    ? "bg-weak dark:bg-weak-dark"
    : filled
      ? "bg-accent dark:bg-night-accent"
      : "bg-ink/40 dark:bg-night-ink/40";
  return (
    <span
      aria-hidden="true"
      className={`h-[6px] w-[6px] shrink-0 rounded-full ${colour} ${running ? "breathing" : ""}`}
    />
  );
}

/** One block of the graph. Clicking it opens what that step sent and what came back. */
function Node({ node, selected, onSelect, compact, width }) {
  const wide = node.wide;
  const label = node.kind === "page" ? node.label || host(node.url) : node.label;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-expanded={selected}
      className={`node-in group relative ${width} h-full rounded-xl border px-3 py-2.5 text-left
                  backdrop-blur-sm transition-[transform,box-shadow,border-color] duration-200
                  hover:-translate-y-[2px] hover:shadow-[0_10px_30px_-12px_rgba(20,25,34,0.35)]
                  ${selected
                    ? "border-accent bg-card ring-1 ring-accent/40 dark:border-night-accent dark:bg-night-card dark:ring-night-accent/40"
                    : node.tone === "warn"
                      ? "border-weak/40 bg-card/70 dark:border-weak-dark/40 dark:bg-night-card/70"
                      : "border-rule bg-card/70 dark:border-night-rule dark:bg-night-card/70"}`}
    >
      <span className="flex items-center gap-[6px]">
        <Marker kind={node.kind} running={node.running} tone={node.tone} />
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted dark:text-night-muted">
          {node.kicker}
        </span>
        {node.sub > 0 && (
          <span
            className="ml-auto font-mono text-[10px] text-muted/80 dark:text-night-muted/80"
            title={`written for sub-question ${node.sub}`}
          >
            #{node.sub}
          </span>
        )}
      </span>

      <span
        className={`mt-[6px] font-serif leading-snug ${wide ? "text-[0.975rem]" : "text-[0.8125rem]"} ${
          wide ? "line-clamp-3" : node.kind === "search" ? "line-clamp-4" : "line-clamp-2"
        }`}
      >
        {label || (node.running ? "working" : "")}
      </span>

      {(node.count !== null || node.note) && (
        <span className="mt-[6px] flex flex-wrap items-baseline gap-x-2 font-mono text-[10px] text-muted dark:text-night-muted">
          {node.count !== null && (
            <span className={node.count ? "text-ink dark:text-night-ink" : ""}>
              {node.count} {node.unit}
            </span>
          )}
          {node.note && <span className="truncate">{node.note}</span>}
        </span>
      )}

      {node.llm && !compact && (
        <span className="mt-1 block truncate font-mono text-[10px] text-muted/80 dark:text-night-muted/80">
          {(node.llm.model || "").replace(/^[^/]+\//, "")} · {node.llm.tokens.toLocaleString("en-US")} tok
        </span>
      )}

      {node.detail.length > 0 && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-1.5 right-2 font-mono text-[10px] text-muted/0
                     transition-colors group-hover:text-muted dark:group-hover:text-night-muted"
        >
          {selected ? "close" : "open"}
        </span>
      )}
    </button>
  );
}

/** What happened between two rows: how much the funnel threw away, or which round this is. */
function Caption({ text }) {
  return (
    <div className="relative z-10 -mt-3 mb-3 flex">
      <span className="rounded-full bg-paper px-2 py-[2px] font-mono text-[10px] text-muted dark:bg-night dark:text-night-muted">
        {text}
      </span>
    </div>
  );
}

export function RunGraph({ graph, running, done, compact = false }) {
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(!compact);
  const [paths, setPaths] = useState([]);
  const wrap = useRef(null);
  const marks = useRef(new Map());
  const panel = useRef(null);

  // the detail of a block opens under the whole graph, so bring it into view when it is far away
  useEffect(() => {
    if (!selected || !panel.current) return;
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    panel.current.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "nearest" });
  }, [selected]);

  // the answer is the point, so the graph folds itself away the moment the report arrives
  useEffect(() => {
    if (done) setOpen(false);
  }, [done]);

  const measure = useCallback(() => {
    const box = wrap.current;
    if (!box) return;
    const base = box.getBoundingClientRect();
    if (!base.height) return;
    const next = [];
    for (const edge of graph.edges) {
      const a = marks.current.get(edge.from);
      const b = marks.current.get(edge.to);
      if (!a || !b) continue;
      const ra = a.getBoundingClientRect();
      const rb = b.getBoundingClientRect();
      const x1 = ra.left - base.left + ra.width / 2;
      const y1 = ra.bottom - base.top;
      const x2 = rb.left - base.left + rb.width / 2;
      const y2 = rb.top - base.top;
      if (y2 < y1) continue; // a row that wrapped oddly: skip rather than draw a loop upwards
      const bend = Math.max(14, (y2 - y1) * 0.55);
      next.push({
        id: edge.id,
        kind: edge.kind,
        live: !!graph.nodes.find((n) => n.id === edge.to)?.running,
        d: `M${x1.toFixed(1)},${y1.toFixed(1)} C${x1.toFixed(1)},${(y1 + bend).toFixed(1)} ${x2.toFixed(1)},${(y2 - bend).toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`,
      });
    }
    setPaths((prev) => (same(prev, next) ? prev : next));
  }, [graph]);

  useLayoutEffect(measure);

  useEffect(() => {
    const box = wrap.current;
    if (!box || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure]);

  const rows = useMemo(() => {
    const byRow = new Map();
    for (const node of graph.nodes) byRow.set(node.row, [...(byRow.get(node.row) || []), node]);
    return [...byRow.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([row, nodes]) => {
        // eight searches in one row need narrower blocks than two do, or the row wraps into a wall
        const side = nodes.filter((n) => !n.wide).length;
        const width = compact
          ? "w-[6.5rem]"
          : side >= 7
            ? "w-[6.75rem] sm:w-[7rem]"
            : side >= 5
              ? "w-[8rem] sm:w-[9rem]"
              : "w-[10rem] sm:w-[11.5rem]";
        return { row, nodes, width, gap: side >= 5 ? "gap-2" : "gap-2 sm:gap-3" };
      });
  }, [graph, compact]);

  const captions = useMemo(() => {
    const out = new Map();
    for (const round of graph.rounds) {
      if (graph.rounds.length > 1) out.set(round.searchRow, `Round ${round.n}`);
      if (round.select) {
        out.set(round.pageRow, `${round.select.candidates} results → ${round.select.picked} worth opening`);
      }
      if (round.extract.calls) {
        const had = out.get(round.pageRow) || "";
        out.set(round.pageRow, `${had}${had ? " · " : ""}${round.extract.calls} model calls, ${Math.round(round.extract.tokens / 100) / 10}k tokens`);
      }
    }
    return out;
  }, [graph]);

  if (!graph.nodes.length || (graph.nodes.length === 1 && !running)) {
    return running ? <Ticker text="starting the run" /> : null;
  }

  const chosen = graph.nodes.find((n) => n.id === selected) || null;
  const summary = graphSummary(graph);

  return (
    <section className="mt-2">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 font-sans text-sm text-accent hover:underline dark:text-night-accent"
          aria-expanded={open}
        >
          <span
            aria-hidden="true"
            className={`inline-block transition-transform duration-300 ${open ? "rotate-90" : ""}`}
          >
            ›
          </span>
          {running ? "Researching" : open ? "Hide how it got there" : "How it got there"}
        </button>
        {running && !open && <Ticker text={currentStep(graph)} />}
        {!running && summary.length > 0 && (
          <span className="font-mono text-[11px] text-muted dark:text-night-muted">{summary.join("   ")}</span>
        )}
      </header>

      <div className={`fold ${open ? "fold-open" : ""}`}>
        <div>
          <div ref={wrap} className="relative pt-6">
            <svg
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
            >
              {paths.map((p) => (
                <path
                  key={p.id}
                  d={p.d}
                  fill="none"
                  strokeWidth={p.kind === "weak" ? 1 : 1.25}
                  className={`${p.live ? "edge-live" : "edge-draw"} ${
                    p.kind === "loop"
                      ? "stroke-accent/60 dark:stroke-night-accent/60"
                      : p.kind === "weak"
                        ? "stroke-rule/60 dark:stroke-night-rule/60"
                        : "stroke-rule dark:stroke-night-rule"
                  }`}
                />
              ))}
            </svg>

            {rows.map(({ row, nodes, width, gap }) => (
              <div key={row}>
                {captions.has(row) && <Caption text={captions.get(row)} />}
                <div className={`relative z-10 mb-10 flex flex-wrap items-stretch justify-center ${gap}`}>
                  {nodes.map((node) => (
                    <div
                      key={node.id}
                      ref={(el) => {
                        if (el) marks.current.set(node.id, el);
                        else marks.current.delete(node.id);
                      }}
                      className={node.wide ? "flex w-full justify-center" : "flex"}
                    >
                      <Node
                        node={node}
                        compact={compact}
                        width={node.wide ? "w-full max-w-[30rem]" : width}
                        selected={selected === node.id}
                        onSelect={() => setSelected(selected === node.id ? null : node.id)}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {chosen && (
            <div ref={panel} className="unfold rounded-xl border border-rule bg-card/60 p-4 dark:border-night-rule dark:bg-night-card/60">
              <header className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h4 className="font-sans text-sm font-semibold">{chosen.kicker}</h4>
                <p className="min-w-0 flex-1 truncate font-serif text-sm text-muted dark:text-night-muted">
                  {chosen.label}
                </p>
                <span className="font-mono text-[11px] text-muted dark:text-night-muted">
                  {chosen.t.toFixed(1)} s
                </span>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="font-sans text-xs text-accent hover:underline dark:text-night-accent"
                >
                  close
                </button>
              </header>
              {chosen.detail.length ? (
                <StepDetail blocks={chosen.detail} />
              ) : (
                <p className="text-sm text-muted dark:text-night-muted">
                  Nothing was logged for this step beyond what the block already says.
                </p>
              )}
              {chosen.after && (
                <p className="mt-3 font-sans text-xs text-muted dark:text-night-muted">{chosen.after}</p>
              )}
            </div>
          )}

          <p className="mt-2 font-sans text-xs text-muted dark:text-night-muted">
            A filled dot is a step the model took, a hollow one is plain code or the search tool.
            Click any block to see what it sent and what came back.
          </p>
        </div>
      </div>
    </section>
  );
}

/** One line, for when there is no room for the graph: the step the run is on right now. */
export function Ticker({ text }) {
  return (
    <p className="flex items-baseline gap-2 font-mono text-[11px] text-muted dark:text-night-muted">
      <span className="breathing mt-[4px] h-[6px] w-[6px] shrink-0 rounded-full bg-accent dark:bg-night-accent" />
      <span className="truncate">{text}</span>
    </p>
  );
}
