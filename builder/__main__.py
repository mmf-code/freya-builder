"""Command line: python -m builder <command> ...

  extract   BRIEF... [-o FILE]                 requirements JSON from briefs
  validate  BRIEF... [-r FILE] [--json]        findings; exit 1 on errors
  diff      OLD NEW [--id-key K] [--ignore G] [--structural-only] [--shape] [--json]
                                               exit 1 when there are differences
  shape     FILE                               path -> JSON types
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .extract import assign_ids, extract
from .ingest import load_brief
from .jsondiff import DEFAULT_ID_KEYS, diff, format_report, shape, shape_diff, summarize
from .model import dump_requirements, load_requirements
from .validate import errors, validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m builder")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("extract", help="extract requirements from briefs (.md, .txt, .json)")
    p.add_argument("briefs", nargs="+")
    p.add_argument("-o", "--out", help="write JSON here instead of stdout")

    p = sub.add_parser("validate", help="validate requirements against briefs")
    p.add_argument("briefs", nargs="+")
    p.add_argument("-r", "--requirements", help="requirements JSON; default: extract from the briefs")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("diff", help="structural diff of two JSON files")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--id-key", action="append", dest="id_keys", help=f"list identity key, repeatable (default: {', '.join(DEFAULT_ID_KEYS)})")
    p.add_argument("--ignore", action="append", default=[], help="fnmatch glob over paths, repeatable, e.g. '*.updatedAt'")
    p.add_argument("--structural-only", action="store_true", help="hide scalar value changes")
    p.add_argument("--shape", action="store_true", help="compare paths and types only")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("shape", help="print every path pattern of a JSON file with its types")
    p.add_argument("file")

    args = parser.parse_args(argv)
    return {"extract": _extract, "validate": _validate, "diff": _diff, "shape": _shape}[args.command](args)


def _extract(args: argparse.Namespace) -> int:
    reqs = assign_ids([r for path in args.briefs for r in extract(load_brief(path))])
    text = dump_requirements(reqs)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{len(reqs)} requirements -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def _validate(args: argparse.Namespace) -> int:
    briefs = [load_brief(path) for path in args.briefs]
    if args.requirements:
        reqs = load_requirements(Path(args.requirements).read_text(encoding="utf-8"))
    else:
        reqs = assign_ids([r for b in briefs for r in extract(b)])
    findings = validate(reqs, briefs)
    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2, ensure_ascii=False))
    else:
        for f in findings:
            print(f"{f.level:7} {f.code:28} {f.requirement_id or '-':12} {f.message}")
        levels = {lvl: sum(f.level == lvl for f in findings) for lvl in ("error", "warning", "info")}
        print(f"{len(reqs)} requirements; " + ", ".join(f"{n} {lvl}" for lvl, n in levels.items()))
    return 1 if errors(findings) else 0


def _diff(args: argparse.Namespace) -> int:
    old, new = _load_json(args.old), _load_json(args.new)
    if args.shape:
        changes = shape_diff(old, new)
    else:
        changes = diff(old, new, id_keys=args.id_keys or DEFAULT_ID_KEYS, ignore=args.ignore)
    if args.structural_only:
        changes = [c for c in changes if c.structural]
    if args.json:
        print(json.dumps({"summary": summarize(changes), "changes": [c.to_dict() for c in changes]}, indent=2, ensure_ascii=False))
    else:
        print(format_report(changes, title=f"{args.old} -> {args.new}"))
    return 1 if changes else 0


def _shape(args: argparse.Namespace) -> int:
    for path, types in shape(_load_json(args.file)).items():
        print(f"{path}\t{'|'.join(types)}")
    return 0


def _load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.exit(main())
