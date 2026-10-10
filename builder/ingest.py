"""Schema-independent brief ingestion.

Turns a brief (Markdown, plain text, or arbitrary JSON) into a flat list of
segments. Each segment keeps a locator back into the original file:
"L12" or "L12-L14" for text lines, "#/a/0/b" (RFC 6901 JSON pointer as a URI
fragment) for JSON values. Nothing here interprets keys or knows about any
workflow schema.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .model import SourceRef

# Segment kinds whose text is prose and may carry requirements.
PROSE_KINDS = frozenset({"paragraph", "list_item", "table_row", "value"})


@dataclass(frozen=True)
class Segment:
    # heading | paragraph | list_item | table_row | code | value | number | scalar | sentence
    kind: str
    text: str
    ref: SourceRef
    keys: tuple[str, ...] = ()  # JSON only: object keys from the root to this value


@dataclass
class Brief:
    doc: str
    format: str  # markdown | text | json
    raw: str
    segments: list[Segment]

    def sentences(self) -> Iterator[Segment]:
        for seg in self.segments:
            yield from iter_sentences(seg)

    def text_at(self, locator: str) -> str | None:
        texts = [s.text for s in self.segments if s.ref.locator == locator]
        return " ".join(texts) if texts else None


def load_brief(path: str | Path) -> Brief:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix == ".json":
        return ingest_json(json.loads(raw), doc=p.name, raw=raw)
    fmt = "markdown" if suffix in (".md", ".markdown") else "text"
    return ingest_text(raw, doc=p.name, fmt=fmt)


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+(.*)$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_QUOTE = re.compile(r"^\s*>\s?")


def ingest_text(text: str, doc: str, fmt: str = "markdown") -> Brief:
    """Split Markdown or plain text into headings, paragraphs, list items, table rows and code."""
    segments: list[Segment] = []
    headings: list[tuple[int, str]] = []
    buf: list[str] = []
    kind = ""
    start = end = 0

    def section() -> tuple[str, ...]:
        return tuple(title for _, title in headings)

    def flush() -> None:
        nonlocal buf, kind
        if buf:
            body = ("\n" if kind == "code" else " ").join(buf).strip()
            if body:
                loc = f"L{start}" if start == end else f"L{start}-L{end}"
                segments.append(Segment(kind, body, SourceRef(doc, loc, section(), body)))
        buf, kind = [], ""

    def begin(new_kind: str, n: int) -> None:
        nonlocal kind, start, end
        flush()
        kind, start, end = new_kind, n, n

    for n, line in enumerate(text.splitlines(), start=1):
        if kind == "code":
            if _FENCE.match(line):
                flush()
            else:
                buf.append(line)
                end = n
            continue
        if _FENCE.match(line):
            begin("code", n + 1)
            continue
        line = _QUOTE.sub("", line)
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        m = _HEADING.match(line)
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            headings = [h for h in headings if h[0] < level] + [(level, title)]
            segments.append(Segment("heading", title, SourceRef(doc, f"L{n}", section(), title)))
            continue
        m = _LIST_ITEM.match(line)
        if m:
            begin("list_item", n)
            buf.append(m.group(1).strip())
            continue
        if _TABLE_ROW.match(line):
            flush()
            if set(stripped) <= set("|-: "):
                continue  # header separator row
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            row = " | ".join(c for c in cells if c)
            if row:
                segments.append(Segment("table_row", row, SourceRef(doc, f"L{n}", section(), row)))
            continue
        if kind == "list_item" and line[:1].isspace():
            buf.append(stripped)
            end = n
            continue
        if kind != "paragraph":
            begin("paragraph", n)
        buf.append(stripped)
        end = n
    flush()
    return Brief(doc=doc, format=fmt, raw=text, segments=segments)


def ingest_json(data: Any, doc: str, raw: str = "") -> Brief:
    """Flatten any JSON value into one segment per leaf. Keys are kept, not interpreted."""
    segments: list[Segment] = []

    def walk(node: Any, path: tuple[str | int, ...]) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + (str(k),))
            return
        if isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + (i,))
            return
        keys = tuple(p for p in path if isinstance(p, str))
        if isinstance(node, str):
            kind, text = "value", " ".join(node.split())
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            kind, text = "number", json.dumps(node)
        else:
            kind, text = "scalar", json.dumps(node)
        if text:
            segments.append(Segment(kind, text, SourceRef(doc, json_pointer(path), keys, text), keys))

    walk(data, ())
    return Brief(doc=doc, format="json", raw=raw or json.dumps(data, ensure_ascii=False, indent=2), segments=segments)


def json_pointer(path: tuple[str | int, ...]) -> str:
    return "#" + "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in path)


def iter_sentences(seg: Segment) -> Iterator[Segment]:
    if seg.kind not in PROSE_KINDS:
        return
    for sentence in split_sentences(seg.text):
        ref = SourceRef(seg.ref.doc, seg.ref.locator, seg.ref.section, sentence)
        yield Segment("sentence", sentence, ref, seg.keys)


_ABBREVIATIONS = frozenset({"e.g.", "i.e.", "etc.", "vs.", "mr.", "mrs.", "ms.", "dr.", "no.", "approx.", "incl.", "st."})
_BOUNDARY = re.compile(r"[.!?][\"”’')\]]*\s+")


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        nxt = text[m.end() : m.end() + 1]
        if not (nxt.isupper() or nxt.isdigit() or nxt in "\"“‘'(["):
            continue
        words = text[start : m.start() + 1].split()
        if words and words[-1].lower() in _ABBREVIATIONS:
            continue
        out.append(text[start : m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out
