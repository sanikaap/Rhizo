import re

NOTE = "_Some details were removed because the graph did not support them._"

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_ID_PREFIX = re.compile(r"^[a-z]+:")
_LIST_ITEM = re.compile(r"^\s*([-*]|\d+\.)\s")


def find_mentions(text: str, names: list[str]) -> list[tuple[int, str]]:
    lowered = text.lower()
    hits = []
    for name in names:
        lower = name.lower()
        for alias in {lower, f"{lower.removesuffix('service')} service"}:
            m = re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", lowered)
            if m:
                hits.append((m.start(), name))
    return sorted(hits)


def names_from_ids(ids: list[str]) -> set[str]:
    return {_ID_PREFIX.sub("", i) for i in ids}


def ungrounded(text: str, known: list[str], allowed: set[str]) -> list[str]:
    return sorted({name for _, name in find_mentions(text, known)} - allowed)


def strip(text: str, names: list[str]) -> str:
    kept_lines = []
    for line in text.splitlines():
        if _LIST_ITEM.match(line):
            if not find_mentions(line, names):
                kept_lines.append(line)
            continue
        sentences = [s for s in _SENTENCE_END.split(line) if not find_mentions(s, names)]
        if sentences or not line.strip():
            kept_lines.append(" ".join(sentences))
    body = "\n".join(kept_lines).strip()
    return f"{body}\n\n{NOTE}" if body else NOTE
