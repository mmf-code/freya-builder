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

An optional "ladder" in the plan turns one conversation step of the body into counted, ordered attempts per item:

    "ladder": {"template": "<body step>", "done": "<body step or close:<id>>",
               "items": {"count": "<variable>", "max": <n>, "evidence": [...]},
               "attempts": {"allowed": "<variable with {i}>", "max": <m>, "evidence": [...]},
               "refusal": "<extracted variable with {i} and {a}>"}

The template is written for item {i}, attempt {a}; every "{i}" and "{a}" in it is replaced. It declares the refusal
variable in its extraction_schema (value "yes" on a flat refusal of the current offer), and leaves for the next item
through the target "item:next". Other steps enter the ladder through "item:first". The lowering writes one step per
item and attempt and, before the template's own routes: a refusal goes to the next attempt while the item's allowed
count is above the attempt number, else to the next item. A passthrough router per item skips items beyond the count.
The counts are variables a step before the ladder sets once; the ladder itself runs no code and only moves forward,
so a refused attempt cannot be offered again and no item gets more attempts than allowed.
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
NEXT_ITEM, FIRST_ITEM = "item:next", "item:first"
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


def _var(name: str, op: str, operand) -> dict:
    return {"variable": name, "operator": op, "operand": operand}


def _when(*checks: dict) -> dict:
    return {"logic": "or", "conditions": [checks[0] if len(checks) == 1 else {"logic": "and", "conditions": list(checks)}]}


def check_ladder(ladder: dict, body: dict, base: Path) -> list[str]:
    problems = []
    nodes = body.get("nodes") or {}
    template = nodes.get(ladder.get("template"))
    if not template or template.get("node_type") != "conversation" or template.get("passthrough"):
        return [f"ladder template {ladder.get('template')!r} is not a waiting conversation step of the body"]
    done = str(ladder.get("done") or "")
    if done not in nodes and not done.startswith(SYMBOL):
        problems.append(f"ladder done {done!r} is neither a body step nor a close:<id> target")
    for part, key in (("items", "count"), ("attempts", "allowed")):
        spec = ladder.get(part) or {}
        if not isinstance(spec.get("max"), int) or not 1 <= spec["max"] <= 9:
            problems.append(f"ladder {part}.max must be a whole number from 1 to 9")
        if not str(spec.get(key) or "").strip():
            problems.append(f"ladder {part}.{key} names no variable")
        quotes = _quotes(spec.get("evidence") or [], base)
        if not quotes or not all(quotes):
            problems.append(f"ladder {part}: every evidence quote must appear in its source")
    if "{i}" not in str((ladder.get("attempts") or {}).get("allowed", "")):
        problems.append("ladder attempts.allowed must contain {i}: one allowed count per item")
    refusal = str(ladder.get("refusal") or "")
    if "{i}" not in refusal or "{a}" not in refusal:
        problems.append("ladder refusal must contain {i} and {a}: one variable per item and attempt")
    if refusal not in [e.get("name") for e in template.get("extraction_schema") or []]:
        problems.append(f"the ladder template does not extract its refusal variable {refusal!r}")
    key = ladder["template"]
    written = {f"{key}_item_{i}" for i in range(1, 10)} | {f"{key}_{i}_{a}" for i in range(1, 10) for a in range(1, 10)}
    if written & set(nodes):
        problems.append(f"body steps {sorted(written & set(nodes))} use names the ladder writes")
    return problems


def expand_ladder(wf: dict, ladder: dict) -> None:
    """Replace the template step by its item and attempt steps, in place."""
    nodes = wf["nodes"]
    key, done = ladder["template"], ladder["done"]
    template = nodes.pop(key)
    items, attempts = ladder["items"]["max"], ladder["attempts"]["max"]
    count, allowed, refusal = ladder["items"]["count"], ladder["attempts"]["allowed"], ladder["refusal"]

    def step(i, a):
        return f"{key}_{i}_{a}"

    def router(i):
        return f"{key}_item_{i}"

    def after(i):
        return router(i + 1) if i < items else done

    for i in range(1, items + 1):
        nodes[router(i)] = {
            "name": router(i), "node_type": "conversation", "passthrough": True, "passthrough_default_transition": step(i, 1),
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "task_message": "Do not call a tool in this turn.",
            "transitions": [{"target_node": done, "description": f"fewer than {i} items", "condition": _when(_var(count, "less_than", i))},
                            {"target_node": step(i, 1), "description": "always", "condition": {"operator": "always"}}]}
        for a in range(1, attempts + 1):
            text = json.dumps(template).replace("{i}", str(i)).replace("{a}", str(a))
            clone = json.loads(text.replace(json.dumps(NEXT_ITEM), json.dumps(after(i))))
            said_no = _var(refusal.replace("{i}", str(i)).replace("{a}", str(a)), "equals", "yes")
            first = []
            if a < attempts:
                first.append({"target_node": step(i, a + 1), "description": f"refused attempt {a}, another attempt is allowed",
                              "condition": _when(said_no, _var(allowed.replace("{i}", str(i)), "greater_than", a))})
            first.append({"target_node": after(i), "description": f"refused attempt {a}, attempts used up",
                          "condition": _when(said_no)})
            for t in clone.get("transitions") or []:
                if t.get("target_node") == key:
                    t["target_node"] = step(i, a)
            if clone.get("max_turn_transition") == key:
                clone["max_turn_transition"] = step(i, a)
            clone["transitions"] = first + (clone.get("transitions") or [])
            clone["name"] = step(i, a)
            nodes[step(i, a)] = clone
    text = json.dumps(wf)
    if json.dumps(FIRST_ITEM) in text:
        wf.update(json.loads(text.replace(json.dumps(FIRST_ITEM), json.dumps(router(1)))))


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
    ladder = plan.get("ladder")
    if ladder:
        found = check_ladder(ladder, body, base)
        if found:
            raise LoweringError(problems + found)
        expand_ladder(wf, ladder)
    if NEXT_ITEM in json.dumps(wf) or FIRST_ITEM in json.dumps(wf):
        problems.append(f"{NEXT_ITEM} and {FIRST_ITEM} need a ladder in the plan, entered from outside its template")
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
