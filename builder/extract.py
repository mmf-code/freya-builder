"""Heuristic requirement extraction.

Deterministic and dependency-free. It finds normative sentences with a
Lexicon and fills the Requirement IR. It prefers recall plus review notes
over clever parsing. Every requirement keeps the verbatim sentence it came
from, so a human or a later model pass can correct it.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .ingest import Brief, Segment, iter_sentences
from .lexicon import EN, Cue, Lexicon
from .model import NEGATIVE_MODALITIES, Counter, Requirement, SourceRef, Termination

_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_COORDINATOR = re.compile(r"(?:or|and|but|nor)\b", re.I)
_CLAUSE_SPLIT = re.compile(r";\s+")


@dataclass
class Parsed:
    modality: str
    actor: str | None
    action: str
    preconditions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def extract(brief: Brief, lexicon: Lexicon = EN) -> list[Requirement]:
    reqs: list[Requirement] = []
    for seg in brief.segments:
        if seg.kind == "number":
            req = requirement_from_number(seg, lexicon)
            if req:
                reqs.append(req)
            continue
        for sentence in iter_sentences(seg):
            for clause in _clauses(sentence):
                req = requirement_from_sentence(clause, lexicon)
                if req:
                    reqs.append(req)
    return assign_ids(reqs)


def requirement_id(statement: str) -> str:
    """Content-derived id: stable when unrelated text is added or moved."""
    norm = " ".join(statement.lower().split()).rstrip(" .")
    return "R-" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:8]


def assign_ids(reqs: list[Requirement]) -> list[Requirement]:
    seen: dict[str, int] = {}
    for r in reqs:
        base = requirement_id(r.statement)
        seen[base] = seen.get(base, 0) + 1
        r.id = base if seen[base] == 1 else f"{base}-{seen[base]}"
    return reqs


def requirement_from_sentence(seg: Segment, lexicon: Lexicon = EN) -> Requirement | None:
    parsed = parse_sentence(seg.text, lexicon, seg.keys)
    if parsed is None:
        return None
    action, modality = parsed.action, parsed.modality
    return Requirement(
        id="",
        modality=modality,
        statement=seg.text,
        source=seg.ref,
        actor=parsed.actor,
        preconditions=parsed.preconditions,
        required_actions=[action] if action and modality in ("must", "should") else [],
        allowed_actions=[action] if action and modality == "may" else [],
        forbidden_actions=[action] if action and modality in NEGATIVE_MODALITIES else [],
        counters=find_counters(seg.text, parsed, lexicon),
        terminations=find_terminations(parsed, lexicon),
        origin=f"heuristic:{lexicon.name}",
        notes=parsed.notes,
    )


def requirement_from_number(seg: Segment, lexicon: Lexicon = EN) -> Requirement | None:
    """A JSON number whose key names a limit, e.g. {"max_call_attempts": 3}."""
    if not seg.keys:
        return None
    key = normalize_key(seg.keys[-1])
    if not lexicon.counter_keys.search(key):
        return None
    try:
        limit = int(seg.text)
    except ValueError:
        return None
    kind = "max" if lexicon.limit_keys.search(key) else "count"
    subject = " ".join(lexicon.limit_keys.sub(" ", key).split()) or key
    return Requirement(
        id="",
        modality="must",
        statement=f"{'.'.join(seg.keys)} = {seg.text}",
        source=seg.ref,
        counters=[Counter(subject, limit, kind)],
        origin=f"heuristic:{lexicon.name}",
        notes=[f"counter inferred from key '{seg.keys[-1]}'"],
    )


def parse_sentence(text: str, lexicon: Lexicon = EN, keys: tuple[str, ...] = ()) -> Parsed | None:
    """Classify one sentence. Returns None when it carries no normative signal."""
    lex = lexicon
    body = text.strip().rstrip(".!;:").strip()
    if not body:
        return None
    notes: list[str] = []
    preconditions: list[str] = []

    lead, main = _split_leading(body, lex)
    if lead:
        preconditions.append(lead)
    elif lex.connectives.match(body):
        notes.append("leading condition not separated from the main clause")
    main = _strip_words(main, {"then", "please", "kindly"})
    if re.match(r"only\b", main, re.I):
        main = main[4:].lstrip()
        notes.append("restrictive 'only': the action may be forbidden outside its condition")

    limit = _first_connective(main, lex)
    found = _find_cue(main, lex, limit)
    hint = None if found else _key_hint(keys, lex)
    if found is None and hint is None and not _is_imperative(main, lex):
        found = _find_cue(main, lex)
        if found is None:
            return None

    actor: str | None = None
    if found is not None:
        cue, m = found
        modality = cue.modality
        before, rest = main[: m.start()].strip(" ,"), main[m.end() :]
        action, trailing = _split_trailing(rest, lex)
        if cue.passive:
            action = before
        else:
            actor = before.lower() or None
    elif hint is not None:
        modality, key = hint
        notes.append(f"modality from key '{key}'")
        action, trailing = _split_trailing(main, lex)
    else:
        modality = "must"
        notes.append("implicit imperative")
        action, trailing = _split_trailing(main, lex)

    if trailing:
        preconditions.append(trailing)
    action = _clean_action(action, lex)
    if not action:
        notes.append("no action parsed")
    if len(_cue_spans(main[:limit] if limit is not None else main, lex)) > 1:
        notes.append("several normative cues; may be a compound rule")
    return Parsed(modality, actor, action, preconditions, notes)


def find_counters(text: str, parsed: Parsed, lexicon: Lexicon = EN) -> list[Counter]:
    lex = lexicon
    norm = lex.rewrite_counts(text)
    pre = [lex.rewrite_counts(p).lower() for p in parsed.preconditions]
    max_before = re.compile(f"(?:{lex.max_marker.pattern})\\s*$", re.I)
    out: list[Counter] = []
    for m in lex.counter.finditer(norm):
        limit = lex.to_int(m.group("n"))
        if limit is None:
            continue
        subject = " ".join(m.group("subject").lower().split())
        if any(m.group(0).lower() in p for p in pre):
            kind = "threshold"
        elif max_before.search(norm[: m.start()]):
            kind = "max"
        else:
            kind = "count"
        if kind == "max" and subject in ("time", "times"):
            subject = _counted_activity(parsed.action, lex) or subject
        counter = Counter(subject, limit, kind)
        if counter not in out:
            out.append(counter)
    return out


def find_terminations(parsed: Parsed, lexicon: Lexicon = EN) -> list[Termination]:
    if parsed.modality in NEGATIVE_MODALITIES or not parsed.action:
        return []
    for pattern, kind in lexicon.terminations:
        if pattern.search(parsed.action):
            return [Termination(kind, parsed.action, list(parsed.preconditions))]
    return []


def normalize_key(key: str) -> str:
    """'maxCallAttempts' / 'max_call-attempts' -> 'max call attempts'."""
    k = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", k).lower().split())


# --- helpers -----------------------------------------------------------------


def _clauses(sentence: Segment) -> list[Segment]:
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(sentence.text) if p.strip()]
    if len(parts) <= 1:
        return [sentence]
    ref = sentence.ref
    return [Segment("sentence", p, SourceRef(ref.doc, ref.locator, ref.section, p), sentence.keys) for p in parts]


def _split_leading(body: str, lex: Lexicon) -> tuple[str | None, str]:
    """'If X, the agent must Y' -> ('If X', 'the agent must Y').

    Splits at the first comma whose remainder starts a main clause, so commas
    inside the condition ("If X, Y, or Z, transfer ...") are skipped.
    """
    if not lex.connectives.match(body):
        return None, body
    for i, ch in enumerate(body):
        if ch != ",":
            continue
        rest = _strip_words(body[i + 1 :].strip(), {"then"})
        if not rest or _COORDINATOR.match(rest):
            continue
        if _is_imperative(rest, lex) or _early_cue(rest, lex):
            return body[:i].strip(), rest
    m = re.search(r"\bthen\b", body, re.I)
    if m:
        return body[: m.start()].strip(" ,"), body[m.end() :].strip()
    return None, body


def _split_trailing(rest: str, lex: Lexicon) -> tuple[str, str | None]:
    """'verify identity before discussing X' -> ('verify identity', 'before discussing X')."""
    t = rest.strip(" ,")
    words = t.split()
    first = words[0].lower() if words else ""
    for m in lex.connectives.finditer(t):
        if m.start() == 0:
            return "", t
        if first in lex.reporting_verbs and m.group(0).lower() in ("if", "when"):
            continue  # "tell the caller when ..." is an object clause, not a condition
        return t[: m.start()].rstrip(" ,"), t[m.start() :].strip()
    return t, None


def _first_connective(text: str, lex: Lexicon) -> int | None:
    for m in lex.connectives.finditer(text):
        if m.start() > 0:
            return m.start()
    return None


def _find_cue(text: str, lex: Lexicon, limit: int | None = None) -> tuple[Cue, re.Match[str]] | None:
    """Earliest cue wins; on a tie the longest match wins."""
    best = None
    for cue in lex.cues:
        m = cue.pattern.search(text)
        if m is None or (limit is not None and m.start() >= limit):
            continue
        rank = (m.start(), m.start() - m.end())
        if best is None or rank < best[0]:
            best = (rank, cue, m)
    return (best[1], best[2]) if best else None


def _early_cue(text: str, lex: Lexicon) -> bool:
    found = _find_cue(text, lex)
    if found is None:
        return False
    prefix = text[: found[1].start()]
    return "," not in prefix and len(prefix.split()) <= 6


def _cue_spans(text: str, lex: Lexicon) -> list[tuple[int, int]]:
    """Cue matches, with overlapping or adjacent ones merged ("must always" counts once)."""
    spans = sorted((m.start(), m.end()) for cue in lex.cues for m in cue.pattern.finditer(text))
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and (s <= merged[-1][1] or not text[merged[-1][1] : s].strip()):
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    return merged


def _is_imperative(text: str, lex: Lexicon) -> bool:
    t = _strip_words(text.strip(), lex.fillers | {"only"})
    m = _WORD.match(t)
    if not m or m.group(0).lower() not in lex.imperative_verbs:
        return False
    tail = t[m.end() :]
    if tail.lstrip().startswith(","):
        return False  # "block, freeze, or cancel ..." is a list, not a command
    following = [w.lower() for w in _WORD.findall(tail)[:2]]
    if following and (following[0] in lex.auxiliaries or following[0] == "of"):
        return False  # "Use of data is ...", "Block is ..."
    if len(following) == 2 and following[1] in lex.auxiliaries and following[0] not in lex.object_starters:
        return False  # "Transfer requests are handled ..."
    return True


def _key_hint(keys: tuple[str, ...], lex: Lexicon) -> tuple[str, str] | None:
    for key in reversed(keys):
        norm = normalize_key(key)
        for pattern, modality in lex.key_hints:
            if pattern.search(norm):
                return modality, key
    return None


def _counted_activity(action: str, lex: Lexicon) -> str | None:
    """'retry verification up to three times' -> 'retry verification'."""
    m = lex.max_marker.search(action)
    if m is None:
        return None
    return action[: m.start()].strip(" ,").lower() or None


def _clean_action(text: str, lex: Lexicon) -> str:
    t = " ".join(text.split()).strip(" ,;:.")
    t = _strip_words(t, lex.fillers)
    if t and not (len(t) > 1 and t[1].isupper()):
        t = t[0].lower() + t[1:]
    return t


def _strip_words(text: str, words: set[str] | frozenset[str]) -> str:
    while True:
        m = re.match(r"([A-Za-z]+)\s+", text)
        if not m or m.group(1).lower() not in words:
            return text
        text = text[m.end() :]
