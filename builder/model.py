"""Requirement IR (internal representation).

This is our own format, not a Freya schema. It sits between briefs and any
future workflow schema: briefs are parsed into it, and a workflow generator
can be written against it once the official schema is known.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

MODALITIES = ("must", "must_not", "should", "should_not", "may")
NEGATIVE_MODALITIES = ("must_not", "should_not")
COUNTER_KINDS = ("max", "threshold", "count")
TERMINATION_KINDS = ("end", "handoff")


@dataclass(frozen=True)
class SourceRef:
    """Where a requirement came from.

    locator is "L12" or "L12-L14" for text lines, or "#/a/0/b" (a JSON
    pointer as a URI fragment) for JSON values. quote is the source text,
    whitespace-normalized.
    """

    doc: str
    locator: str
    section: tuple[str, ...] = ()
    quote: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"doc": self.doc, "locator": self.locator, "section": list(self.section), "quote": self.quote}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRef:
        return cls(
            doc=data.get("doc", ""),
            locator=data.get("locator", ""),
            section=tuple(data.get("section") or ()),
            quote=data.get("quote", ""),
        )


@dataclass
class Counter:
    """A numeric limit.

    kind "max": an upper bound on something the actor does ("up to three times").
    kind "threshold": a count that triggers something ("after three failed attempts").
    kind "count": a number was found but its role is unclear.
    """

    subject: str
    limit: int
    kind: str = "count"


@dataclass
class Termination:
    """A way the conversation ends for this agent: "end" or "handoff" to someone else."""

    kind: str
    outcome: str
    conditions: list[str] = field(default_factory=list)


@dataclass
class Requirement:
    id: str
    modality: str
    statement: str
    source: SourceRef
    actor: str | None = None
    preconditions: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)
    terminations: list[Termination] = field(default_factory=list)
    origin: str = "manual"
    notes: list[str] = field(default_factory=list)
    # Unknown keys from hand-written or externally produced requirement files
    # are kept here, so they survive a load/dump round trip.
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "modality": self.modality,
            "statement": self.statement,
            "source": self.source.to_dict(),
            "actor": self.actor,
            "preconditions": list(self.preconditions),
            "required_actions": list(self.required_actions),
            "allowed_actions": list(self.allowed_actions),
            "forbidden_actions": list(self.forbidden_actions),
            "counters": [asdict(c) for c in self.counters],
            "terminations": [asdict(t) for t in self.terminations],
            "origin": self.origin,
            "notes": list(self.notes),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Requirement:
        known = {f.name for f in fields(cls)}
        extra = dict(data.get("extra") or {})
        extra.update({k: v for k, v in data.items() if k not in known})
        return cls(
            id=data["id"],
            modality=data["modality"],
            statement=data["statement"],
            source=SourceRef.from_dict(data["source"]),
            actor=data.get("actor"),
            preconditions=list(data.get("preconditions") or []),
            required_actions=list(data.get("required_actions") or []),
            allowed_actions=list(data.get("allowed_actions") or []),
            forbidden_actions=list(data.get("forbidden_actions") or []),
            counters=[
                Counter(subject=c["subject"], limit=c["limit"], kind=c.get("kind", "count"))
                for c in data.get("counters") or []
            ],
            terminations=[
                Termination(kind=t["kind"], outcome=t["outcome"], conditions=list(t.get("conditions") or []))
                for t in data.get("terminations") or []
            ],
            origin=data.get("origin", "manual"),
            notes=list(data.get("notes") or []),
            extra=extra,
        )


def dump_requirements(reqs: list[Requirement]) -> str:
    return json.dumps([r.to_dict() for r in reqs], indent=2, ensure_ascii=False) + "\n"


def load_requirements(text: str) -> list[Requirement]:
    return [Requirement.from_dict(d) for d in json.loads(text)]
