"""Deterministic lowering of a declared closing plan into a Freya workflow. Standard library only.

    python3 -m builder.lower BODY.json PLAN.json --tools OPENAPI.json [--base DIR] [-o WORKFLOW.json] [--contract OUT.json]

The builder's model declares how calls can end; this code writes the steps that end them. BODY.json is a workflow
whose conversation steps leave for an ending through a symbolic target "close:<id>" (in target_node,
passthrough_default_transition or max_turn_transition). PLAN.json names the terminal tool and each ending:

    {"terminal": {"tool": "<OpenAPI path name>", "evidence": [{"source": "...", "quote": "..."}]},
     "fields": {"<request field>": "{{<call variable>}}"},
     "closings": {"<id>": {"set": {"<request field>": "<value>"}, "say": "<optional fixed farewell>",
                           "evidence": [{"source": "...", "quote": "..."}]}}}

For each referenced id the lowering writes one passthrough step that runs the terminal tool with the declared values
and then enters the one end_call step. So by construction: the terminal tool runs alone, in an engine step, after
which only end_call follows; every ending passes it; no ending needs code. Nothing about a brief is built in: the
tool, its URL, method and fields come from the OpenAPI file, the values from the plan. A value the OpenAPI file does
not enumerate must appear in that closing's quoted evidence, and every quote must appear in its source file.
Exit status: 0 lowered, 1 plan or body rejected, 2 unreadable input.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

try:
    from .workflow_check import _all_nodes, check_contract, load_operations, tool_operation
except ImportError:  # run as tools/lower.py in a kit workspace, next to its copy tools/check_workflow.py
    from check_workflow import _all_nodes, check_contract, load_operations, tool_operation

SYMBOL = "close:"
END_STEP = "hang_up"
TERMINAL_CONFIG = {"timeoutMs": 12000, "maxRetries": 2}  # as in the best measured workflow (runs/20261010-161811-candidate-ab)


class LoweringError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def step_name(closing_id: str) -> str:
    return "close_" + "".join(c if c.isalnum() else "_" for c in closing_id).strip("_")


def _quotes(evidence: list[dict], base: Path) -> list[str]:
    out = []
    for ev in evidence or []:
        src = base / str(ev.get("source", ""))
        text = " ".join(src.read_text(errors="replace").split()) if src.is_file() else ""
        quote = " ".join(str(ev.get("quote", "")).split())
        out.append(quote if quote and quote in text else "")
    return out


def check_plan(plan: dict, ops: dict[str, dict], base: Path) -> list[str]:
    problems = []
    term = (plan.get("terminal") or {}).get("tool")
    contract = {"terminal_tools": [{"tool": term, "evidence": (plan.get("terminal") or {}).get("evidence") or []}]}
    problems += [f"{f.code}: {f.message}" for f in check_contract(contract, ops, base) if f.level == "error"]
    if term not in ops:
        return problems
    props, required = ops[term]["properties"], ops[term]["required"]
    for field in plan.get("fields") or {}:
        if field not in props:
            problems.append(f"field {field!r} is not a request field of {term}")
    closings = plan.get("closings") or {}
    if not closings:
        problems.append("no closings declared")
    names: dict[str, str] = {}
    for cid in closings:
        if step_name(cid) in names:
            problems.append(f"closings {names[step_name(cid)]!r} and {cid!r} would get the same step name {step_name(cid)!r}; rename one")
        names.setdefault(step_name(cid), cid)
    for cid, closing in closings.items():
        values = closing.get("set") or {}
        quotes = _quotes(closing.get("evidence") or [], base)
        if not quotes or not all(quotes):
            problems.append(f"closing {cid!r}: every evidence quote must appear in its source")
        for field, value in values.items():
            spec = props.get(field)
            if spec is None:
                problems.append(f"closing {cid!r}: {field!r} is not a request field of {term}")
            elif spec.get("enum") and value not in spec["enum"]:
                problems.append(f"closing {cid!r}: {field}={value!r} is not one of {spec['enum']}")
            elif not spec.get("enum") and not any(str(value) in q for q in quotes):
                problems.append(f"closing {cid!r}: {field}={value!r} is not enumerated by the tool API and not in its evidence")
        missing = [f for f in required if f not in values and f not in (plan.get("fields") or {})]
        if missing:
            problems.append(f"closing {cid!r}: required fields {missing} of {term} are neither set nor mapped")
    return problems


def terminal_tool(term: str, op: dict, fields: dict, values: dict) -> dict:
    body = {}
    for name in op["properties"]:
        if name in values:
            body[name] = {"type": "string", "default": values[name]}
            if op["properties"][name].get("enum"):
                body[name]["enum"] = [values[name]]
        elif name in fields:
            body[name] = {"type": "string", "default": fields[name]}
    url = (op["servers"][0] if op["servers"] else "") + op["path"]
    return {"type": "function", "config": dict(TERMINAL_CONFIG), "function": {
        "name": term, "handler": "__function__:api_call", "description": "Record how the call ended.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string", "default": url}, "method": {"type": "string", "default": op["method"]},
            "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
            "body": {"type": "object", "properties": body, "required": []}}}}}


def _targets(node: dict):
    """Every place a step names another step, as (container, key)."""
    for t in node.get("transitions") or []:
        if isinstance(t, dict) and "target_node" in t:
            yield t, "target_node"
    for f in ("passthrough_default_transition", "max_turn_transition"):
        if f in node:
            yield node, f


def lower(body: dict, plan: dict, openapi: dict, base: Path = Path(".")) -> tuple[dict, dict]:
    """(workflow, contract) for BODY with PLAN's endings written in. Raises LoweringError."""
    ops = load_operations(openapi)
    problems = check_plan(plan, ops, base)
    term = (plan.get("terminal") or {}).get("tool")
    wf = copy.deepcopy(body)
    nodes = wf.get("nodes") or {}
    for key, node in _all_nodes(wf).items():
        if node.get("node_type") == "end_call":
            problems.append(f"step {key!r} is an end_call step; endings are declared in the plan, not written")
        for field in ("tools", "pre_actions"):
            if any(isinstance(t, dict) and tool_operation(t, ops) == term for t in node.get(field) or []):
                problems.append(f"step {key!r} offers or runs the terminal tool {term}; route to a declared closing instead")
    closings = plan.get("closings") or {}
    used = []
    for key, node in _all_nodes(wf).items():
        for holder, field in _targets(node):
            target = str(holder.get(field) or "")
            if target.startswith(SYMBOL):
                cid = target[len(SYMBOL):]
                if cid not in closings:
                    problems.append(f"step {key!r} routes to undeclared closing {cid!r}")
                    continue
                holder[field] = step_name(cid)
                used.append(cid)
    taken = {step_name(c) for c in closings} | {END_STEP}
    clash = sorted(taken & set(_all_nodes(body)))
    if clash:
        problems.append(f"body steps {clash} use names the lowering writes")
    if not used:
        problems.append("no step routes to a closing")
    if problems:
        raise LoweringError(problems)
    op = ops[term]
    for cid in sorted(set(used)):
        nodes[step_name(cid)] = {
            "name": step_name(cid), "node_type": "api_request", "passthrough": True,
            "passthrough_default_transition": END_STEP, "disable_inactivity_monitor": True,
            "on_enter": {"type": "tts", "text": closings[cid]["say"]} if closings[cid].get("say") else {"type": "silent"},
            "pre_actions": [terminal_tool(term, op, plan.get("fields") or {}, closings[cid].get("set") or {})],
            "response_mapping": [], "transitions": [{"target_node": END_STEP, "description": "always", "condition": {"operator": "always"}}]}
    nodes[END_STEP] = {"name": END_STEP, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                       "transitions": [], "terminal": {"type": "function", "function": {
                           "name": "call_closed", "handler": "__function__:end_call",
                           "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}
    contract = {"terminal_tools": [{"tool": term, "evidence": plan["terminal"]["evidence"]}], "every_call_ends_with_terminal": True}
    return wf, contract


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("body", type=Path)
    p.add_argument("plan", type=Path)
    p.add_argument("--tools", type=Path, required=True)
    p.add_argument("--base", type=Path, default=Path("."), help="directory that evidence sources are relative to")
    p.add_argument("-o", "--out", type=Path)
    p.add_argument("--contract", type=Path, help="also write the terminal contract for workflow_check")
    a = p.parse_args(argv)
    try:
        body, plan, api = (json.loads(x.read_text()) for x in (a.body, a.plan, a.tools))
    except (OSError, ValueError) as e:
        print(f"cannot read input: {e}", file=sys.stderr)
        return 2
    try:
        wf, contract = lower(body, plan, api, a.base)
    except LoweringError as e:
        for problem in e.problems:
            print("REJECTED", problem)
        return 1
    text = json.dumps(wf, indent=1, ensure_ascii=False) + "\n"
    if a.out:
        a.out.write_text(text)
    else:
        sys.stdout.write(text)
    if a.contract:
        a.contract.write_text(json.dumps(contract, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
