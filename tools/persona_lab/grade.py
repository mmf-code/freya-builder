"""Grade a Builder's first export against a blind scenario. Offline: no Freya, no bank.

Three separate results, never merged into one score:
- contract: `builder.workflow_check.check` against the scenario's (mutated) OpenAPI, plus stale field names and
  enum values of the public contract that the export still sends, plus bank tools that no tool binds.
- evidence: each probe of the scenario key is FOUND / ABSENT (kind found) or STALE / CLEAR (kind stale), from the
  export's text. Text evidence is necessary, not sufficient: FOUND does not prove the agent applies the rule.
- leak: public practice-customer values in the export (names, case ids, case amounts) that the input briefs do not
  contain. A blind build saw no practice customers, so a hit suggests public data carried by the Builder; a short
  amount can also match by chance, so read the hit before concluding.
"""
from __future__ import annotations

import json
from pathlib import Path

from builder import workflow_check as wc

from .common import load_cases

BANK_TOOLS = ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call")


def _strings(x, out: list[str]) -> list[str]:
    if isinstance(x, str):
        out.append(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            out.append(str(k))
            _strings(v, out)
    elif isinstance(x, list):
        for v in x:
            _strings(v, out)
    return out


def workflow_text(wf: dict) -> str:
    return "\n".join(_strings(wf, [])).lower()


def _api_tools(wf: dict, ops: dict) -> list[tuple[str, str, dict]]:
    """(where, operation, tool) for every api_call tool of the workflow."""
    out = []
    for name, node in {**(wf.get("nodes") or {}), **(wf.get("global_nodes") or {})}.items():
        for t in [*(node.get("tools") or []), *(node.get("pre_actions") or [])]:
            if not isinstance(t, dict):
                continue
            op = wc.tool_operation(t, ops)
            if op is not None:
                out.append((name, op, t))
    return out


def leak_terms() -> list[str]:
    terms = set()
    for c in load_cases().values():
        v = c["variables"]
        terms |= {c["id"].lower(), f"{v['first_name']} {v['last_name']}".lower()}
        for p in c["expected"]["promises"]:
            terms.add(f"{p['amount']:.2f}")
    return sorted(terms)


def grade(export: dict, key: dict, openapi: dict, brief_text: str = "") -> dict:
    wf = export.get("workflow", export)
    ops = wc.load_operations(openapi)
    findings = [f.as_dict() for f in wc.check(export, openapi)]     # the wrapper keeps export mode
    tools = _api_tools(wf, ops)
    stale_fields, stale_enum = [], []
    for where, op, t in tools:
        body = (((t.get("function") or {}).get("parameters") or {}).get("properties") or {}).get("body") or {}
        fields = body.get("properties") or {}
        gone = key.get("stale_api", {}).get(op, {})
        stale_fields += [f"{where}/{op}.{f}" for f in gone.get("fields", []) if f in fields]
        for f, removed in gone.get("enum", {}).items():
            spec = fields.get(f) or {}
            vals = list(spec.get("enum") or []) + [spec.get("default")]
            stale_enum += [f"{where}/{op}.{f}={v}" for v in removed if v in vals]
    bound = {op for _, op, _ in tools}
    unbound = [t for t in key.get("required_tools", BANK_TOOLS) if t in ops and t not in bound]
    errors = [f for f in findings if f["level"] == "error"]
    contract = {"pass": not errors and not stale_fields and not stale_enum and not unbound,
                "errors": errors, "warnings": [f for f in findings if f["level"] != "error"],
                "stale_fields": stale_fields, "stale_enum": stale_enum, "unbound_tools": unbound}
    text = workflow_text(wf)
    evidence = []
    for p in key.get("probes", []):
        hit = [s for s in p["any"] if s.lower() in text]
        status = ("FOUND" if hit else "ABSENT") if p["kind"] == "found" else ("STALE" if hit else "CLEAR")
        evidence.append({"id": p["id"], "status": status, "strong": p["strong"], "hits": hit, "why": p["why"]})
    brief_text = brief_text.lower()
    leak = [t for t in leak_terms() if t in text and t not in brief_text]
    return {"scenario": key.get("scenario"), "form": key.get("form"), "contract": contract, "evidence": evidence,
            "strong_stale": [e["id"] for e in evidence if e["status"] == "STALE" and e["strong"]], "leak": leak,
            "note": key.get("scoring")}


def grade_paths(export_path: Path, scenario_dir: Path) -> dict:
    briefs = "\n".join(p.read_text() for p in sorted((scenario_dir / "inputs").glob("*.md")))
    return grade(json.loads(export_path.read_text()), json.loads((scenario_dir / "key.json").read_text()),
                 json.loads((scenario_dir / "inputs" / "openapi.json").read_text()), briefs)


def render(r: dict) -> str:
    c = r["contract"]
    lines = [f"{r['scenario']} [{r['form']}]  contract {'PASS' if c['pass'] else 'FAIL'}  ({r['note']})"]
    for e in c["errors"]:
        lines.append(f"  ERROR {e['code']} {e['where']}: {e['message'][:160]}")
    for s in c["stale_fields"]:
        lines.append(f"  STALE-FIELD {s}")
    for s in c["stale_enum"]:
        lines.append(f"  STALE-ENUM {s}")
    for s in c["unbound_tools"]:
        lines.append(f"  UNBOUND {s}")
    for e in r["evidence"]:
        lines.append(f"  {e['status']:6} {'strong' if e['strong'] else 'weak  '} {e['id']}: {e['why']}{' ' + str(e['hits']) if e['hits'] else ''}")
    lines.append(f"  leak: {r['leak'] or 'none'}")
    return "\n".join(lines)


def fresh_exports() -> list[tuple[Path, Path]]:
    """(export, scenario dir) for every blind build on disk: kitrun runs labelled pl-<scenario dir>, whose exports
    are runs/<stamp>-pl-<scenario>/<slot>.workflow.json, plus files dropped into results/blind/<scenario>/."""
    from .common import GEN, RESULTS, ROOT
    found = []
    for scn in sorted((GEN / "blind").glob("g*-*")):
        if not scn.is_dir():
            continue
        for run in sorted((ROOT / "runs").glob(f"*-pl-{scn.name}")):
            found += [(p, scn) for p in sorted(run.glob("*.workflow.json"))]
        found += [(p, scn) for p in sorted((RESULTS / "blind" / scn.name).glob("*.json"))]
    return found
