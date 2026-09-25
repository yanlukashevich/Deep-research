/** Trace events as one readable line each. Mirrors taro/progress.py, in the page's own words. */
const short = (text, limit = 70) =>
  !text ? "" : text.length <= limit ? text : `${text.slice(0, limit - 1)}…`;

export function describe(event) {
  // lists are counted, so `subquestions: [...]` reads as how many
  const n = (k) =>
    Array.isArray(event[k]) ? String(event[k].length)
      : event[k] === undefined || event[k] === null ? "?" : String(event[k]);
  if (event.kind === "search") return `searched: ${short(event.query)} — ${n("n_results")} results`;
  if (event.kind === "fetch") return `read ${host(event.url)} (${n("chars")} chars)`;
  if (event.kind === "facts") {
    const rejected = event.rejected || 0;
    return `${n("kept")} facts from ${host(event.url)}` +
      (rejected ? `, ${rejected} quote${rejected > 1 ? "s" : ""} rejected` : "");
  }
  if (event.kind === "llm_call") return null;
  if (event.kind === "start") return "starting";
  if (event.kind === "done") return "finished";
  if (event.kind !== "step") return null;

  switch (event.name) {
    case "plan": return "planning the research";
    case "plan_done":
      return `plan: ${n("subquestions")} sub-questions, ${n("queries")} queries` +
        (event.published_after ? `, only pages after ${event.published_after}` : "");
    case "search": return `searching: ${short(event.query)}`;
    case "round": return `round ${n("round")}: ${n("queries")} searches`;
    case "select": return `picked ${n("picked")} pages out of ${n("candidates")} found`;
    case "read": return `reading ${n("pages")} pages`;
    case "extract": return `extracting facts from ${n("pages")} pages`;
    case "extract_done": return `round ${n("round")}: ${n("facts")} facts from ${n("pages_read")} pages`;
    case "critic": return `critic is checking ${n("facts")} facts`;
    case "critic_done":
      if (event.enough) return "critic: enough material";
      return `critic: ${(event.missing || []).length} sub-questions still open, ` +
        `${(event.queries || []).length} new searches`;
    case "stop": return `stopping: ${event.reason || ""}`;
    case "write": return `writing the answer from ${n("facts")} facts and ${n("sources")} sources`;
    case "answer": return "answer ready, scoring the sentences";
    default: return event.name;
  }
}

export function host(url = "") {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** The site quality the confidence formula used, in words the reader can check. */
export function quality(score) {
  if (score === null || score === undefined) return { label: "site not rated", pips: 0 };
  if (score >= 1) return { label: "official source", pips: 4 };
  if (score >= 0.8) return { label: "encyclopedia", pips: 3 };
  if (score >= 0.65) return { label: "news site", pips: 3 };
  if (score >= 0.5) return { label: "unknown site", pips: 2 };
  return { label: "blog or forum", pips: 1 };
}

export const MODE_NAME = { v1: "v1 · bare model", v2: "v2 · one search", v3: "v3 · research agent" };
export const MODE_BLURB = {
  v1: "Answers from memory. No search, no sources — every sentence scores zero.",
  v2: "One search, top pages, one answer. Usually one site per claim.",
  v3: "Plans sub-questions, reads pages, quotes them, criticises itself, then writes.",
};

export function download(name, text, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function slug(text, max = 40) {
  return (text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "") || "run").slice(0, max);
}
