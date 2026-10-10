"""Schema-agnostic structural diff for JSON documents.

Built to compare workflow JSON versions before the official schema is known.
It needs no schema. Lists whose items are all objects are matched by an
identity key when one is usable (default candidates: id, key, name), so
inserting one node does not show up as every later node changing. Other
lists are aligned with difflib.

Paths render JSONPath-style: $.nodes[id="greet"].prompt, $.edges[2].
"""
from __future__ import annotations

import json
import re
from collections import Counter as Tally
from dataclasses import dataclass
from difflib import SequenceMatcher
from fnmatch import fnmatchcase
from typing import Any, Iterable

DEFAULT_ID_KEYS = ("id", "key", "name")
CHANGE_KINDS = ("added", "removed", "changed", "type_changed", "reordered")
# shape_diff kinds: old/new hold lists of JSON type names, not values.
SHAPE_KINDS = ("path_added", "path_removed", "types_changed")
STRUCTURAL_KINDS = frozenset({"added", "removed", "type_changed", "reordered", *SHAPE_KINDS})


@dataclass(frozen=True)
class Change:
    kind: str
    path: str
    old: Any = None
    new: Any = None

    @property
    def structural(self) -> bool:
        return self.kind in STRUCTURAL_KINDS

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "path": self.path, "old": self.old, "new": self.new}


def json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def diff(old: Any, new: Any, *, id_keys: Iterable[str] = DEFAULT_ID_KEYS, ignore: Iterable[str] = ()) -> list[Change]:
    """All differences between two JSON values.

    old/new on a Change hold the removed/added subtree, the changed scalars,
    or (for "reordered") the identity values in old and new order.
    ignore takes fnmatch globs over rendered paths, e.g. "$.meta*" or "*.updatedAt".
    """
    out: list[Change] = []
    _Differ(tuple(id_keys), tuple(ignore), out).walk(old, new, "$")
    return out


def summarize(changes: list[Change]) -> dict[str, int]:
    tally = Tally(c.kind for c in changes)
    return {kind: tally[kind] for kind in CHANGE_KINDS + SHAPE_KINDS if tally[kind]}


def shape(doc: Any) -> dict[str, list[str]]:
    """Every path pattern in the document with the JSON types seen there. List indices become [*]."""
    return _shape(doc)[0]


def shape_diff(old: Any, new: Any) -> list[Change]:
    """Differences in paths and types only, ignoring values. Child paths of an added/removed path are folded in."""
    (sa, pa), (sb, pb) = _shape(old), _shape(new)
    out: list[Change] = []
    for path in sorted(sa.keys() | sb.keys()):
        if path not in sb:
            if pa.get(path) not in sa.keys() - sb.keys():
                out.append(Change("path_removed", path, sa[path], None))
        elif path not in sa:
            if pb.get(path) not in sb.keys() - sa.keys():
                out.append(Change("path_added", path, None, sb[path]))
        elif sa[path] != sb[path]:
            out.append(Change("types_changed", path, sa[path], sb[path]))
    return out


def format_report(changes: list[Change], *, title: str | None = None, width: int = 60) -> str:
    structural = sum(c.structural for c in changes)
    counts = ", ".join(f"{k}={v}" for k, v in summarize(changes).items())
    head = f"{len(changes)} changes ({structural} structural, {len(changes) - structural} value)"
    lines = [title] if title else []
    lines.append(head + (f": {counts}" if counts else ""))
    for c in changes:
        if c.kind == "added":
            lines.append(f"  + {c.path} = {_short(c.new, width)}")
        elif c.kind == "removed":
            lines.append(f"  - {c.path} (was {_short(c.old, width)})")
        elif c.kind == "changed":
            lines.append(f"  ~ {c.path}: {_short(c.old, width)} -> {_short(c.new, width)}")
        elif c.kind == "type_changed":
            lines.append(f"  ! {c.path}: {json_type(c.old)} {_short(c.old, width)} -> {json_type(c.new)} {_short(c.new, width)}")
        elif c.kind == "reordered":
            lines.append(f"  ^ {c.path}: order {_short(c.old, width)} -> {_short(c.new, width)}")
        elif c.kind == "path_added":
            lines.append(f"  + {c.path}: {'|'.join(c.new)}")
        elif c.kind == "path_removed":
            lines.append(f"  - {c.path}: {'|'.join(c.old)}")
        else:
            lines.append(f"  ! {c.path}: {'|'.join(c.old)} -> {'|'.join(c.new)}")
    return "\n".join(lines)


# --- internals -----------------------------------------------------------------

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _key_path(path: str, key: str) -> str:
    return f"{path}.{key}" if _IDENT.match(key) else f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def _id_path(path: str, id_key: str, value: Any) -> str:
    return f"{path}[{id_key}={json.dumps(value, ensure_ascii=False)}]"


class _Differ:
    def __init__(self, id_keys: tuple[str, ...], ignore: tuple[str, ...], out: list[Change]) -> None:
        self.id_keys, self.ignore, self.out = id_keys, ignore, out

    def emit(self, change: Change) -> None:
        if not self.ignored(change.path):
            self.out.append(change)

    def ignored(self, path: str) -> bool:
        return any(fnmatchcase(path, p) for p in self.ignore)

    def walk(self, a: Any, b: Any, path: str) -> None:
        if self.ignored(path):
            return
        ta, tb = json_type(a), json_type(b)
        if ta != tb:
            self.emit(Change("type_changed", path, a, b))
        elif ta == "object":
            for k in a:
                p = _key_path(path, k)
                if k in b:
                    self.walk(a[k], b[k], p)
                else:
                    self.emit(Change("removed", p, a[k], None))
            for k in b:
                if k not in a:
                    self.emit(Change("added", _key_path(path, k), None, b[k]))
        elif ta == "array":
            key = self.identity_key(a, b)
            if key:
                self.keyed_list(a, b, path, key)
            else:
                self.aligned_list(a, b, path)
        elif a != b:
            self.emit(Change("changed", path, a, b))

    def identity_key(self, a: list[Any], b: list[Any]) -> str | None:
        items = a + b
        if not items or not all(isinstance(x, dict) for x in items):
            return None
        for k in self.id_keys:
            usable = all(k in x and isinstance(x[k], (str, int)) and not isinstance(x[k], bool) for x in items)
            if usable and len({x[k] for x in a}) == len(a) and len({x[k] for x in b}) == len(b):
                return k
        return None

    def keyed_list(self, a: list[dict], b: list[dict], path: str, key: str) -> None:
        old = {x[key]: x for x in a}
        new = {x[key]: x for x in b}
        for x in a:
            if x[key] not in new:
                self.emit(Change("removed", _id_path(path, key, x[key]), x, None))
        for x in b:
            p = _id_path(path, key, x[key])
            if x[key] in old:
                self.walk(old[x[key]], x, p)
            else:
                self.emit(Change("added", p, None, x))
        order_a = [x[key] for x in a if x[key] in new]
        order_b = [x[key] for x in b if x[key] in old]
        if order_a != order_b:
            self.emit(Change("reordered", path, order_a, order_b))

    def aligned_list(self, a: list[Any], b: list[Any], path: str) -> None:
        """Changed items are reported at their new index, removed items at their old index."""
        canon = lambda x: json.dumps(x, sort_keys=True)  # noqa: E731
        matcher = SequenceMatcher(None, [canon(x) for x in a], [canon(x) for x in b], autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            paired = min(i2 - i1, j2 - j1) if tag == "replace" else 0
            for k in range(paired):
                self.walk(a[i1 + k], b[j1 + k], f"{path}[{j1 + k}]")
            for i in range(i1 + paired, i2):
                self.emit(Change("removed", f"{path}[{i}]", a[i], None))
            for j in range(j1 + paired, j2):
                self.emit(Change("added", f"{path}[{j}]", None, b[j]))


def _shape(doc: Any) -> tuple[dict[str, list[str]], dict[str, str]]:
    types: dict[str, set[str]] = {}
    parents: dict[str, str] = {}

    def walk(value: Any, path: str, parent: str | None) -> None:
        types.setdefault(path, set()).add(json_type(value))
        if parent is not None:
            parents[path] = parent
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, _key_path(path, k), path)
        elif isinstance(value, list):
            for v in value:
                walk(v, f"{path}[*]", path)

    walk(doc, "$", None)
    return {p: sorted(t) for p, t in sorted(types.items())}, parents


def _short(value: Any, width: int) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= width else text[: width - 3] + "..."

