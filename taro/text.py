"""Text helpers: whitespace cleanup, sentence splitting, [n] citation parsing."""
import re

# gpt-oss emits narrow/regular no-break spaces and other odd spaces
_ODD_SPACES = re.compile(r"[     　]")
# gpt-oss sometimes writes its own source markers, e.g. 【source: 3】 or 【3†L5-L9】
_BRACKET_MARKERS = re.compile(r"【[^】]*】")
# [1] · [1][2] · [1, 2] · [1-3] · [1–3]
_CITATION = re.compile(r"\[(\d+(?:\s*[,;–-]\s*\d+)*)\]")
# A sentence ends at . ! ? … (optionally followed by citations or a closing quote/bracket),
# then whitespace, then something that starts a new sentence.
_SENTENCE_END = re.compile(
    r"(?<=[.!?…])([\"'»”)]?(?:\s*\[\d+(?:\s*[,;–-]\s*\d+)*\])*)\s+(?=[\"'«“(]?[A-ZА-ЯЁ0-9])"
)
_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
# A period after these is not a sentence end: initials ("Michel H. Devoret") and common abbreviations
_ABBREVIATION = re.compile(
    r"(?:^|[\s(])(?:[A-ZА-ЯЁ]|Dr|Mr|Mrs|Ms|Prof|St|Jr|Sr|No|vs|Inc|Ltd|Co|e\.g|i\.e|"
    r"акад|проф|им|г|ул|т\.е|т\.к|др|см)\.$"
)


def normalize_ws(text: str) -> str:
    """Replace odd spaces with plain ones and collapse runs of spaces/tabs."""
    return re.sub(r"[ \t]+", " ", _ODD_SPACES.sub(" ", text))


def clean_answer(text: str) -> str:
    """Tidy LLM answer text: odd spaces, model-specific source markers, stray blank lines."""
    text = normalize_ws(_BRACKET_MARKERS.sub("", text))
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_citations(sentence: str) -> tuple[str, list[int]]:
    """Return the sentence without [n] markers and the cited numbers (in order, no repeats)."""
    nums: list[int] = []
    for group in _CITATION.findall(sentence):
        for part in re.split(r"\s*[,;]\s*", group):
            if m := re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part):
                lo, hi = int(m[1]), int(m[2])
                span = range(lo, hi + 1) if 0 < hi - lo < 20 else (lo, hi)
            else:
                span = (int(part),)
            nums.extend(n for n in span if n not in nums)
    text = _CITATION.sub("", sentence)
    text = re.sub(r"\s+([.,;:!?…])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip(), nums


def split_sentences(text: str) -> list[str]:
    """Split markdown answer text into sentences, keeping each sentence's trailing citations.

    Every line (paragraph or list item) is split on its own; headings and table rules are skipped.
    """
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or set(line) <= set("|-: "):
            continue
        line = _LIST_MARKER.sub("", line)
        # re.split with one capture group returns [sentence, citations, sentence, citations, ...]
        parts = _SENTENCE_END.split(line)
        pending = ""
        for i in range(0, len(parts), 2):
            cites = parts[i + 1] if i + 1 < len(parts) else ""
            pending += parts[i]
            if i + 1 < len(parts) and not cites and _ABBREVIATION.search(pending):
                pending += " "  # the split point was an abbreviation, not a sentence end
                continue
            if (pending + cites).strip():
                out.append((pending + cites).strip())
            pending = ""
    return out
