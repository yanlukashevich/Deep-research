/** The run as a graph.
 *
 * `buildGraph(events, question)` folds the live trace into nodes laid out in rows — the question,
 * the planner, one node per search, one node per page it opened, the critic that gathers them all
 * back together, the writer — and the edges between them. A page is joined to the search that
 * actually returned its url, so the fan-out and the fan-in are the real ones, not a drawing.
 *
 * Pure: no React, no DOM, no imports. Rebuilt from scratch on every event, which keeps it honest
 * about out-of-order arrivals (a rejected quote is traced before the page it came from is finished).
 */

const num = (x) => (typeof x === "number" ? x : 0);
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** A python repr is not something to show a reader: unwrap it and keep the message. */
const reason = (text = "") => {
  const wrapped = /^[A-Za-z_][\w.]*\((['"])([\s\S]*),?\)$/.exec(String(text).trim());
  return (wrapped ? wrapped[2] : String(text)).replace(/^search failed: /, "").trim();
};

/** Two urls are the same page when host and path match; the scheme and a trailing slash are noise. */
export function normUrl(url = "") {
  try {
    const u = new URL(url);
    return (u.hostname.replace(/^www\./, "") + u.pathname.replace(/\/$/, "")).toLowerCase();
  } catch {
    return String(url).replace(/\/$/, "").toLowerCase();
  }
}

const PURPOSE_LABEL = {
  v3_plan: "planning",
  v3_extract: "reading pages",
  v3_critic: "criticising",
  v3_write: "writing",
  v1_answer: "answering",
  v2_answer: "answering",
};

const STOP_REASON = {
  enough: "the critic is satisfied, no more searching",
  max_rounds: "the last allowed round is done",
  page_limit: "the page budget is used up",
  fact_limit: "enough facts collected",
  time_limit: "the time budget is used up",
  no_new_queries: "nothing new left to search for",
};

function emptyStats() {
  return {
    llm_calls: 0, prompt_tokens: 0, completion_tokens: 0, llm_seconds: 0,
    searches: 0, results: 0, fetches: 0, fetch_errors: 0, chars: 0,
    facts_kept: 0, quotes_rejected: 0, rounds: 0, seconds: 0,
    by_purpose: {}, models: [],
  };
}

function makeNode(base) {
  return {
    id: "", kind: "", row: 0, t: 0,
    kicker: "", label: "", note: "", sub: 0,
    count: null, unit: "",
    running: true, tone: "normal", wide: false,
    detail: [], llm: null, after: "",
    ...base,
  };
}

/**
 * @param {Array} events   the slimmed trace, in arrival order
 * @param {string} question what was asked, for the root node
 * @returns {{nodes: Array, edges: Array, rounds: Array, stats: object, mode: string, error: string, done: boolean}}
 */
export function buildGraph(events = [], question = "") {
  const nodes = [];
  const edges = [];
  const stats = emptyStats();
  const rounds = [];
  const strayRejects = new Map(); // url -> quotes traced before their page finished extracting

  let row = 0;
  let mode = "";
  let subquestions = [];
  let queryOwner = {}; // query text -> sub-question number, from the plan
  let plan = null;
  let current = null;  // the round being filled
  let prevCritic = null;
  let error = "";

  const add = (node) => {
    nodes.push(node);
    return node;
  };
  const link = (from, to, kind = "flow") => {
    if (!from || !to || from.id === to.id) return;
    const id = `${from.id}~${to.id}`;
    if (!edges.some((e) => e.id === id)) edges.push({ id, from: from.id, to: to.id, kind });
  };

  const root = add(makeNode({
    id: "question", kind: "question", row, kicker: "Question",
    label: question, running: false, wide: true,
  }));

  const startRound = (n, expected) => {
    const round = {
      n, expected: num(expected), searchRow: ++row, pageRow: ++row, criticRow: null,
      searches: [], pages: [], critic: null, select: null, expectedPages: 0,
      extract: { calls: 0, tokens: 0 },
    };
    rounds.push(round);
    current = round;
    return round;
  };
  const round = () => current || startRound(1, 0);

  const searchNode = (e, query) => {
    const r = round();
    const parent = prevCritic || plan || root;
    const node = add(makeNode({
      id: `s${r.n}-${r.searches.length}`, kind: "search", row: r.searchRow, t: num(e.t),
      kicker: "Search", label: query, sub: queryOwner[query] || 0,
      urlKeys: new Set(),
      query: { query, filters: e.filters || null, n: 0, seconds: num(e.latency), results: [] },
    }));
    r.searches.push(node);
    link(parent, node, prevCritic ? "loop" : "flow");
    return node;
  };

  const pageNode = (url, e) => {
    const r = round();
    const found = r.pages.find((p) => p.url === url);
    if (found) return found;
    const node = add(makeNode({
      id: `p${r.n}-${r.pages.length}`, kind: "page", row: r.pageRow, t: num(e.t),
      kicker: "Page", label: url, url,
      page: { url, title: "", chars: 0, seconds: 0 }, extract: null,
    }));
    r.pages.push(node);
    const key = normUrl(url);
    const parents = r.searches.filter((s) => s.urlKeys.has(key));
    // a page whose search cannot be named (its result list was cut short) hangs off the first few
    if (parents.length) parents.forEach((s) => link(s, node));
    else r.searches.slice(0, 3).forEach((s) => link(s, node, "weak"));
    return node;
  };

  for (const e of events) {
    if (e.kind === "start") {
      mode = e.mode || mode;
      if (e.question) root.label = e.question;
      continue;
    }

    if (e.kind === "llm_call") {
      const tokens = num(e.prompt_tokens) + num(e.completion_tokens);
      stats.llm_calls += 1;
      stats.prompt_tokens += num(e.prompt_tokens);
      stats.completion_tokens += num(e.completion_tokens);
      stats.llm_seconds += num(e.latency);
      if (e.model && !stats.models.includes(e.model)) stats.models.push(e.model);
      const key = PURPOSE_LABEL[e.purpose] || e.purpose || "other";
      const bucket = (stats.by_purpose[key] ||= { calls: 0, tokens: 0, seconds: 0, model: e.model || "" });
      bucket.calls += 1;
      bucket.tokens += tokens;
      bucket.seconds += num(e.latency);
      bucket.model = e.model || bucket.model;

      // only the steps that run alone can be pinned to a node; reading pages happens six at a time
      const target = e.purpose === "v3_plan" ? plan
        : e.purpose === "v3_critic" ? current?.critic
        : ["v3_write", "v1_answer", "v2_answer"].includes(e.purpose) ? nodes[nodes.length - 1]
        : null;
      if (e.purpose === "v3_extract" && current) {
        current.extract.calls += 1;
        current.extract.tokens += tokens;
      }
      if (target) {
        const llm = target.llm || { calls: 0, tokens: 0, seconds: 0, model: e.model };
        llm.calls += 1;
        llm.tokens += tokens;
        llm.seconds += num(e.latency);
        llm.model = e.model || llm.model;
        target.llm = llm;
      }
      continue;
    }

    if (e.kind === "search" || e.kind === "search_failed" || e.kind === "search_error") {
      const query = e.query || e.args?.query || "";
      const r = round();
      const node = r.searches.find((s) => s.query.query === query) || searchNode(e, query);
      if (e.kind === "search") {
        stats.searches += 1;
        stats.results += num(e.n_results);
        node.query.n = num(e.n_results);
        node.query.seconds = num(e.latency);
        node.query.results = e.results?.length ? e.results : (e.urls || []).map((url) => ({ url }));
        for (const url of e.urls || node.query.results.map((x) => x.url)) node.urlKeys.add(normUrl(url));
      } else {
        node.query.error = reason(e.error) || "the search failed";
        node.tone = "warn";
      }
      fillSearch(node);
      continue;
    }

    if (e.kind === "fetch" || e.kind === "fetch_error") {
      const node = pageNode(e.url, e);
      if (e.kind === "fetch") {
        stats.fetches += 1;
        stats.chars += num(e.chars);
        node.page = { url: e.url, title: e.title || "", chars: num(e.chars), seconds: num(e.latency) };
      } else {
        stats.fetch_errors += 1;
        node.page = { url: e.url, error: `the page would not load — ${reason(e.error) || "no reason given"}` };
        node.tone = "warn";
        node.running = false;
      }
      fillPage(node);
      continue;
    }

    if (e.kind === "page_too_short") {
      const node = current?.pages.find((p) => p.url === e.url);
      if (node) {
        node.page.note = "too little text to read — a paywall, a cookie wall or a stub";
        node.running = false;
        fillPage(node);
      }
      continue;
    }

    if (e.kind === "quote_rejected") {
      stats.quotes_rejected += 1;
      const node = current?.pages.find((p) => p.url === e.url);
      const reject = { statement: e.statement || "", quote: e.quote || "" };
      if (node?.extract) node.extract.rejects.push(reject);
      else strayRejects.set(e.url, [...(strayRejects.get(e.url) || []), reject]);
      continue;
    }

    if (e.kind === "facts" || e.kind === "extract_failed") {
      const node = pageNode(e.url, e);
      stats.facts_kept += num(e.kept);
      node.extract = {
        url: e.url, kept: num(e.kept), rejected: num(e.rejected),
        statements: e.statements || [], quotes: e.quotes || [],
        rejects: strayRejects.get(e.url) || [],
        error: e.kind === "extract_failed" ? `the model's answer could not be read — ${reason(e.error)}` : null,
      };
      strayRejects.delete(e.url);
      node.running = false;
      if (e.kind === "extract_failed") node.tone = "warn";
      fillPage(node);
      continue;
    }

    if (e.kind === "error") error = reason(e.error);
    if (e.kind !== "step") continue;

    switch (e.name) {
      case "plan":
        plan = add(makeNode({
          id: "plan", kind: "plan", row: ++row, t: num(e.t), kicker: "Planner", wide: true,
          label: "splitting the question into sub-questions",
        }));
        link(root, plan);
        break;

      case "plan_done": {
        subquestions = e.subquestions || [];
        const queries = e.queries || [];
        queryOwner = {};
        (e.query_subquestions || []).forEach((n, i) => {
          if (queries[i]) queryOwner[queries[i]] = num(n);
        });
        if (!plan) {
          plan = add(makeNode({ id: "plan", kind: "plan", row: ++row, t: num(e.t), kicker: "Planner", wide: true }));
          link(root, plan);
        }
        plan.running = false;
        plan.label = `${plural(subquestions.length, "sub-question")} to answer`;
        plan.count = queries.length;
        plan.unit = queries.length === 1 ? "query" : "queries";
        plan.subquestions = subquestions;
        plan.detail = [
          subquestions.length && { kind: "list", label: "What it set out to answer", items: subquestions, ordered: true },
          queries.length && { kind: "lines", label: "The searches it wrote", items: queries },
          e.published_after && { kind: "note", text: `Only pages published after ${e.published_after}.` },
        ].filter(Boolean);
        break;
      }

      case "round":
        stats.rounds += 1;
        startRound(num(e.round) || rounds.length + 1, num(e.queries));
        break;

      case "search": // v2 searches once, with the question as the user wrote it
        round();
        break;

      case "select": {
        const r = round();
        r.select = { candidates: num(e.candidates), picked: (e.picked || []).length };
        for (const node of r.searches) node.running = false;
        break;
      }

      case "read": {
        const r = round();
        r.expectedPages = num(e.pages);
        for (const node of r.searches) node.running = false;
        break;
      }

      case "extract_done":
        for (const node of round().pages) {
          node.running = false;
          fillPage(node);
        }
        break;

      case "critic": {
        const r = round();
        r.criticRow = ++row;
        const node = add(makeNode({
          id: `c${r.n}`, kind: "critic", row: r.criticRow, t: num(e.t), kicker: "Critic", wide: true,
          label: `weighing ${plural(num(e.facts), "fact")} against the plan`,
        }));
        r.critic = node;
        for (const page of r.pages) link(page, node);
        if (prevCritic) link(prevCritic, node, "carry");
        break;
      }

      case "critic_done": {
        const node = round().critic;
        if (!node) break;
        const missing = (e.missing || []).map((id) => subquestions[id - 1] || `sub-question ${id}`);
        const queries = e.queries || [];
        const disagree = e.contradictions || [];
        node.running = false;
        node.enough = !!e.enough;
        node.label = e.enough ? "enough material to answer" : `${plural(missing.length, "sub-question")} still open`;
        node.note = e.enough ? "" : plural(queries.length, "new search", "new searches");
        node.detail = [
          e.note && { kind: "quote", label: "What the critic said", text: e.note },
          missing.length && { kind: "list", label: "Still open", items: missing },
          disagree.length && { kind: "list", label: "Sources disagree about", items: disagree, tone: "warn" },
          queries.length && { kind: "lines", label: "Searches it asked for next", items: queries },
        ].filter(Boolean);
        if (disagree.length) node.tone = "warn";
        prevCritic = node;
        break;
      }

      case "stop": {
        const last = nodes[nodes.length - 1];
        if (last) last.after = STOP_REASON[e.reason] || `stopping: ${e.reason}`;
        break;
      }

      case "write": {
        const r = rounds[rounds.length - 1];
        const node = add(makeNode({
          id: "write", kind: "write", row: ++row, t: num(e.t), kicker: "Writer", wide: true,
          label: `writing from ${plural(num(e.facts), "fact")} and ${plural(num(e.sources), "source")}`,
          detail: [{
            kind: "note",
            text: "The writer only sees the facts and their quotes, never the pages. It cites fact numbers; the report renumbers them as sources.",
          }],
        }));
        if (r?.critic) link(r.critic, node);
        else if (r?.pages.length) r.pages.forEach((p) => link(p, node));
        else link(root, node);
        break;
      }

      case "answer": {
        const r = rounds[rounds.length - 1];
        const node = add(makeNode({
          id: "answer", kind: "answer", row: ++row, t: num(e.t), kicker: "Answer", wide: true,
          label: e.n_sources
            ? `answering from ${plural(num(e.n_sources), "search result")}`
            : "answering from the model's own memory",
        }));
        if (r?.searches.length) r.searches.forEach((s) => link(s, node));
        else link(root, node);
        if (!e.n_sources) {
          node.tone = "warn";
          node.detail = [{
            kind: "note",
            text: "No page was opened, so no sentence can be backed. Every sentence scores zero.",
          }];
        }
        break;
      }

      default:
        break;
    }
  }

  const finished = events.some((e) => e.kind === "done" || e.kind === "error");
  if (finished) {
    for (const node of nodes) {
      node.running = false;
      if (node.kind === "search") fillSearch(node);
      if (node.kind === "page") fillPage(node);
    }
  }
  if (error) {
    const last = nodes[nodes.length - 1];
    if (last) {
      last.tone = "warn";
      last.detail = [...last.detail, { kind: "note", text: `The run stopped here: ${error}` }];
    }
  }
  stats.seconds = events.length ? num(events[events.length - 1].t) : 0;

  return { nodes, edges, rounds, stats, mode, error, done: finished };
}

function fillSearch(node) {
  const q = node.query;
  node.count = q.error ? null : q.n;
  node.unit = q.n === 1 ? "result" : "results";
  node.note = q.error ? q.error : q.seconds ? `${q.seconds.toFixed(2)} s` : "";
  if (q.n || q.error) node.running = false;
  node.detail = [{ kind: "queries", items: [q] }];
}

function fillPage(node) {
  const p = node.page;
  node.label = p.title || ""; // the block falls back to the host, which reads better than a long url
  node.count = node.extract ? node.extract.kept : null;
  node.unit = node.extract?.kept === 1 ? "fact" : "facts";
  node.note = p.error
    ? "would not load"
    : p.chars
      ? p.chars < 1500 ? `${p.chars} characters` : `${Math.round(p.chars / 1000)}k characters`
      : "";
  if (p.note) node.tone = "warn";
  node.detail = [
    { kind: "pages", items: [p] },
    node.extract && {
      kind: "note",
      text: "Every fact carries a quote. Plain code looks that quote up in the page text and drops the fact if it is not there.",
    },
    node.extract && { kind: "facts", items: [node.extract] },
  ].filter(Boolean);
}

/** One line for the folded graph: what the run actually did. */
export function graphSummary({ stats, rounds }) {
  const bits = [];
  if (stats.searches) bits.push(plural(stats.searches, "search", "searches"));
  if (stats.fetches) bits.push(`${plural(stats.fetches, "page")} read`);
  if (stats.facts_kept) bits.push(plural(stats.facts_kept, "quoted fact"));
  const critics = rounds.filter((r) => r.critic).length;
  if (critics) bits.push(`${plural(critics, "round")} of criticism`);
  if (!bits.length && stats.llm_calls) bits.push(plural(stats.llm_calls, "model call"));
  return bits;
}

/** The one line that says what is happening right now, for a run shown beside two others. */
export function currentStep({ nodes }) {
  const running = [...nodes].reverse().find((n) => n.running);
  const node = running || nodes[nodes.length - 1];
  if (!node || node.kind === "question") return "starting the run";
  return `${node.kicker.toLowerCase()}: ${node.label || "working"}`;
}
