"""Local validation of a requirement set.

Checks the IR on its own (ids, modalities, counters, contradictions) and,
when briefs are given, against them (traceability and coverage). It works on
requirements from any origin: the heuristic extractor, a hand-edited file,
or a later model pass. It knows nothing about any workflow schema.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .extract import parse_sentence, requirement_from_number
from .ingest import Brief, iter_sentences
from .lexicon import EN, Lexicon
from .model import COUNTER_KINDS, MODALITIES, TERMINATION_KINDS, Requirement

LEVELS = ("error", "warning", "info")


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    requirement_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate(reqs: list[Requirement], briefs: Iterable[Brief] = (), lexicon: Lexicon = EN) -> list[Finding]:
    findings = check_ids(reqs)
    for r in reqs:
        findings += check_requirement(r)
    findings += check_conflicts(reqs)
    briefs = list(briefs)
    if briefs:
        findings += check_traceability(reqs, briefs)
        for brief in briefs:
            findings += check_coverage(reqs, brief, lexicon)
    return findings


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "error"]


def check_ids(reqs: list[Requirement]) -> list[Finding]:
    out: list[Finding] = []
    seen: set[str] = set()
    for r in reqs:
        if not r.id:
            out.append(Finding("error", "E-ID-EMPTY", f"requirement without id: {r.statement!r}"))
        elif r.id in seen:
            out.append(Finding("error", "E-ID-DUP", f"duplicate id {r.id}", r.id))
        seen.add(r.id)
    return out


def check_requirement(r: Requirement) -> list[Finding]:
    out: list[Finding] = []

    def add(level: str, code: str, message: str) -> None:
        out.append(Finding(level, code, message, r.id))

    if r.modality not in MODALITIES:
        add("error", "E-MODALITY", f"unknown modality {r.modality!r}")
    if not r.statement.strip():
        add("error", "E-STATEMENT", "empty statement")
    s = r.source
    if not (s.doc and s.locator and s.quote.strip()):
        add("error", "E-SOURCE", "source needs doc, locator and quote")
    positive = {norm_action(a) for a in r.required_actions + r.allowed_actions}
    for action in sorted(positive & {norm_action(a) for a in r.forbidden_actions}):
        add("error", "E-ACTION-CONTRADICTION", f"action both permitted and forbidden: {action!r}")
    for c in r.counters:
        if isinstance(c.limit, bool) or not isinstance(c.limit, int) or c.limit < 1:
            add("error", "E-COUNTER", f"counter limit must be a positive integer, got {c.limit!r}")
        if c.kind not in COUNTER_KINDS:
            add("error", "E-COUNTER", f"unknown counter kind {c.kind!r}")
        if not c.subject.strip():
            add("error", "E-COUNTER", "counter without subject")
    for t in r.terminations:
        if t.kind not in TERMINATION_KINDS or not t.outcome.strip():
            add("error", "E-TERMINATION", f"termination needs kind in {TERMINATION_KINDS} and an outcome")
        elif not t.conditions:
            add("warning", "W-UNCONDITIONAL-TERMINATION", f"termination without condition: {t.outcome!r}")
    if not (r.required_actions or r.allowed_actions or r.forbidden_actions or r.counters):
        add("warning", "W-NO-ACTION", "no action and no counter")
    if r.notes:
        add("info", "I-REVIEW", "; ".join(r.notes))
    return out


def check_conflicts(reqs: list[Requirement]) -> list[Finding]:
    """Same action permitted by one requirement and forbidden by another under the same preconditions."""
    positive: dict[str, list[Requirement]] = defaultdict(list)
    negative: dict[str, list[Requirement]] = defaultdict(list)
    for r in reqs:
        for a in r.required_actions + r.allowed_actions:
            positive[norm_action(a)].append(r)
        for a in r.forbidden_actions:
            negative[norm_action(a)].append(r)
    out: list[Finding] = []
    for action in sorted(positive.keys() & negative.keys()):
        for p in positive[action]:
            for n in negative[action]:
                if p.id == n.id:
                    continue
                if _conditions(p) == _conditions(n):
                    msg = f"{p.id} permits and {n.id} forbids {action!r} under the same conditions"
                    out.append(Finding("warning", "W-CONFLICT", msg, p.id))
                else:
                    # Not wrong, but a workflow has to order these two rules.
                    msg = f"{p.id} permits and {n.id} forbids {action!r} under different conditions"
                    out.append(Finding("info", "I-CONDITIONAL-CONFLICT", msg, p.id))
    return out


def check_traceability(reqs: list[Requirement], briefs: list[Brief]) -> list[Finding]:
    by_doc = {b.doc: b for b in briefs}
    out: list[Finding] = []
    for r in reqs:
        brief = by_doc.get(r.source.doc)
        if brief is None:
            out.append(Finding("error", "E-TRACE-DOC", f"source doc {r.source.doc!r} not among the given briefs", r.id))
            continue
        text = brief.text_at(r.source.locator)
        if text is None:
            out.append(Finding("error", "E-TRACE-LOCATOR", f"locator {r.source.locator!r} not found in {brief.doc}", r.id))
        elif _ws(r.source.quote) not in _ws(text):
            out.append(Finding("error", "E-TRACE-QUOTE", f"quote not found at {brief.doc}:{r.source.locator}", r.id))
    return out


def check_coverage(reqs: list[Requirement], brief: Brief, lexicon: Lexicon = EN) -> list[Finding]:
    """Every sentence the lexicon considers normative should back at least one requirement."""
    quotes: dict[str, list[str]] = defaultdict(list)
    for r in reqs:
        if r.source.doc == brief.doc and r.source.quote.strip():
            quotes[r.source.locator].append(_ws(r.source.quote).lower())
    out: list[Finding] = []
    for seg in brief.segments:
        loc = seg.ref.locator
        if seg.kind == "number":
            if requirement_from_number(seg, lexicon) and not quotes.get(loc):
                out.append(Finding("warning", "W-COVERAGE", f"limit-like value at {brief.doc}:{loc} has no requirement"))
            continue
        normative = False
        for sentence in iter_sentences(seg):
            if parse_sentence(sentence.text, lexicon, sentence.keys) is None:
                continue
            normative = True
            q = _ws(sentence.text).lower()
            if not any(c in q or q in c for c in quotes.get(loc, [])):
                out.append(Finding("warning", "W-COVERAGE", f"normative sentence at {brief.doc}:{loc} has no requirement: {sentence.text!r}"))
        # The coverage check shares the extractor's lexicon, so it cannot see a rule the
        # lexicon misses. List items are where rules usually live: surface the unclassified ones.
        if not normative and not quotes.get(loc) and _is_list_entry(seg):
            out.append(Finding("info", "I-UNCLASSIFIED", f"list entry at {brief.doc}:{loc} produced no requirement: {seg.text!r}"))
    return out


def _is_list_entry(seg) -> bool:
    return seg.kind == "list_item" or (seg.kind == "value" and seg.ref.locator.rsplit("/", 1)[-1].isdigit())


_ARTICLES = re.compile(r"\b(?:a|an|the)\b")


def norm_action(action: str) -> str:
    t = re.sub(r"[^\w\s]", " ", action.lower())
    return " ".join(_ARTICLES.sub(" ", t).split())


def _conditions(r: Requirement) -> list[str]:
    return sorted(_ws(p).lower() for p in r.preconditions)


def _ws(text: str) -> str:
    return " ".join(text.split())
