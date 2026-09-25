/** Small helpers the page shares: hosts, site quality in words, the mode names, downloads. */
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

export const MODE_NAME = { v1: "Bare model", v2: "One search", v3: "Research agent" };
export const MODE_BLURB = {
  v1: "Answers from memory. No search, no sources — every sentence scores zero.",
  v2: "One search, top pages, one answer. Usually one site per claim.",
  v3: "Plans sub-questions, reads pages, quotes them, criticises itself, then writes.",
};

/** What you can pick in the composer, named by what it does rather than by its version. */
export const MODE_PICK = [
  { id: "v3", label: "Research" },
  { id: "v2", label: "One search" },
  { id: "v1", label: "No search" },
  { id: "all", label: "All three" },
];

export const MODE_HINT = {
  v3: "Plans, searches, reads and criticises itself. About a minute.",
  v2: "One search, then an answer from the snippets. A few seconds.",
  v1: "No search at all: the model answers from memory. Nothing can be backed.",
  all: "Runs all three at once, side by side, on the same question.",
};

/** What a run would cost on a public host of the same open-weight models.
 *
 * The LiteLLM gateway this demo talks to is not billed per token, so no real price exists. These
 * are the published rates of commercial hosts of gpt-oss-120b, in dollars per million tokens, and
 * the page always shows the number as an estimate with the rate next to it. */
export const RATES = { prompt: 0.15, completion: 0.6 };

export function estimateCost(stats = {}) {
  return ((stats.prompt_tokens || 0) * RATES.prompt + (stats.completion_tokens || 0) * RATES.completion) / 1e6;
}

/** Money small enough to need four decimals reads better as cents. */
export function money(usd) {
  if (!usd) return "$0";
  return usd < 0.01 ? `${(usd * 100).toFixed(2)}¢` : `$${usd.toFixed(3)}`;
}

/** 11957 -> "12.0k". Counts stay exact below a thousand. */
export function compact(n = 0) {
  if (n < 1000) return String(Math.round(n));
  if (n < 10000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

export const thousands = (n = 0) => Math.round(n).toLocaleString("en-US");

export const shortModel = (name = "") => name.replace(/^[^/]+\//, "");

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
