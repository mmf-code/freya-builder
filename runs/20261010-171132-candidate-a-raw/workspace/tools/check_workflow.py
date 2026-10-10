"""Static checks of a Freya workflow against its tool API file and a terminal-action contract. Standard library only.

    python3 check_workflow.py WORKFLOW.json --tools OPENAPI.json [--contract CONTRACT.json] [--json]

WORKFLOW.json is a workflow definition or an export from freya.export_workflow ({"workflow": {...}}). For an export
the null check is skipped: the platform fills in null defaults after saving.
CONTRACT.json names the terminal tools, each with quotes from the inputs that make it terminal:

    {"terminal_tools": [{"tool": "<OpenAPI path name>", "evidence": [{"source": "tools/openapi.json", "quote": "..."}]}],
     "every_call_ends_with_terminal": true}

Nothing about a particular brief is built in. Tool names, fields and allowed values come from the OpenAPI file;
which tool is terminal comes from the contract, and every quote in it must appear in its source file.

What a pass proves, for the graph only:
  - no step offers or runs a terminal tool together with another bank tool, so no single model message or entry
    action can send them at the same time (the platform runs the tool calls of one message concurrently);
  - after a step with a terminal tool, no reachable step offers or runs another bank tool, and no end-of-call
    lifecycle tool calls the bank;
  - with every_call_ends_with_terminal, every end_call step is entered only from a terminal step.
It does not prove what the model says or which tool it decides to call in a conversation. Only test calls show that.
Exit status: 0 no errors, 1 errors found, 2 unreadable input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import deque
from pathlib import Path

PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}")


class Finding:
    def __init__(self, level: str, code: str, where: str, message: str):
        self.level, self.code, self.where, self.message = level, code, where, message

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "where": self.where, "message": self.message}

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code:24} {self.where}: {self.message}"


# ---------------------------------------------------------------- tool API

def load_operations(openapi: dict) -> dict[str, dict]:
    """OpenAPI operations by name (the path without its leading slash)."""
    servers = [s.get("url", "").rstrip("/") for s in openapi.get("servers") or [] if isinstance(s, dict)]
    ops = {}
    for path, methods in (openapi.get("paths") or {}).items():
        for method, op in (methods or {}).items():
            if not isinstance(op, dict):
                continue
            schema = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            ops[path.strip("/")] = {"path": path, "method": method.upper(), "servers": servers,
                                    "properties": schema.get("properties") or {}, "required": schema.get("required") or [],
                                    "text": json.dumps(op)}
    return ops


def _default(spec: dict | None):
    return spec.get("default") if isinstance(spec, dict) else None


def tool_operation(tool: dict, ops: dict[str, dict]) -> str | None:
    """The OpenAPI operation an api_call tool calls, matched on the URL path."""
    fn = tool.get("function") or {}
    if fn.get("handler") != "__function__:api_call":
        return None
    url = str(_default((fn.get("parameters") or {}).get("properties", {}).get("url")) or "")
    url = url.split("?")[0].rstrip("/")
    matches = [name for name, op in ops.items() if url.endswith(op["path"].rstrip("/"))]
    return max(matches, key=len) if matches else ""


def check_tool(tool: dict, ops: dict[str, dict], where: str) -> list[Finding]:
    out = []
    fn = tool.get("function") or {}
    if fn.get("handler") != "__function__:api_call":
        return out
    name = fn.get("name", "?")
    props = (fn.get("parameters") or {}).get("properties") or {}
    op_name = tool_operation(tool, ops)
    url = str(_default(props.get("url")) or "")
    if "const" in json.dumps(fn.get("parameters") or {}):
        out.append(Finding("warning", "W-CONST", where, f"tool {name} uses const; the engine bakes only default"))
    if not op_name:
        out.append(Finding("error", "E-TOOL-UNKNOWN", where, f"tool {name} calls {url or '(no url default)'}, which is no path of the tool API"))
        return out
    op = ops[op_name]
    hooked = bool(str(tool.get("pre_process_code") or "").strip())
    field_level = "warning" if hooked else "error"
    note = " (a pre_process_code hook may rewrite the request; checked as declared)" if hooked else ""
    if op["servers"] and not any(url.startswith(s) for s in op["servers"]):
        out.append(Finding("error", "E-TOOL-SERVER", where, f"tool {name} url {url} is not under the tool API server {op['servers'][0]}"))
    method = str(_default(props.get("method")) or "").upper()
    if method != op["method"]:
        out.append(Finding("error", "E-TOOL-METHOD", where, f"tool {name} sends {method or 'no method'}, the tool API wants {op['method']}"))
    body = props.get("body") or {}
    fields = body.get("properties") or {}
    if "default" in body and not fields:
        out.append(Finding("error", "E-TOOL-BODY", where, f"tool {name} declares its body as one default object; declare each field under body.properties"))
    for field, spec in fields.items():
        api = op["properties"].get(field)
        if api is None:
            out.append(Finding(field_level, "E-TOOL-FIELD", where, f"tool {name} sends field {field}, which {op_name} does not have{note}"))
            continue
        allowed = api.get("enum")
        if not allowed:
            continue
        extra = [v for v in spec.get("enum") or [] if v not in allowed]
        if extra:
            out.append(Finding("error", "E-TOOL-ENUM", where, f"tool {name} field {field} allows {extra}, not in the tool API values {allowed}"))
        d = spec.get("default")
        if isinstance(d, str) and not PLACEHOLDER.search(d) and d not in allowed:
            out.append(Finding("error", "E-TOOL-ENUM", where, f"tool {name} field {field} is fixed to {d!r}, not one of {allowed}"))
        if (d is None or (isinstance(d, str) and PLACEHOLDER.fullmatch(d.strip()))) and not spec.get("enum"):
            out.append(Finding("warning", "W-TOOL-ENUM-MISSING", where, f"tool {name} field {field} can be filled by the model without the allowed values {allowed}"))
    for field in op["required"]:
        if field not in fields:
            out.append(Finding(field_level, "E-TOOL-REQUIRED", where, f"tool {name} does not declare required field {field} of {op_name}{note}"))
    return out


# ---------------------------------------------------------------- graph

def _all_nodes(wf: dict) -> dict[str, dict]:
    return {**(wf.get("nodes") or {}), **(wf.get("global_nodes") or {})}


def edges(wf: dict) -> dict[str, set[str]]:
    """Every step a step can move to: transitions, passthrough default, turn cap target, global interrupts."""
    nodes, globals_ = wf.get("nodes") or {}, wf.get("global_nodes") or {}
    out = {k: set() for k in _all_nodes(wf)}
    for key, node in _all_nodes(wf).items():
        for t in node.get("transitions") or []:
            if isinstance(t, dict) and t.get("target_node"):
                out[key].add(t["target_node"])
        for f in ("passthrough_default_transition", "max_turn_transition"):
            if node.get(f):
                out[key].add(node[f])
    for g, gnode in globals_.items():
        excluded = set(gnode.get("excluded_nodes") or [])
        entered_from = {k for k, n in nodes.items() if k not in excluded and n.get("node_type") != "end_call"}
        for k in entered_from:
            out[k].add(g)
        if "__previous__" in out[g]:
            out[g].discard("__previous__")
            out[g] |= entered_from
    return out


def bank_ops(node: dict, ops: dict[str, dict]) -> list[str]:
    tools = (node.get("tools") or []) + (node.get("pre_actions") or [])
    return [o for o in (tool_operation(t, ops) for t in tools if isinstance(t, dict)) if o]


def check_graph(wf: dict, exported: bool = False) -> list[Finding]:
    out = []
    if "agent_config" in wf and not exported:
        out.append(Finding("warning", "W-AGENT-CONFIG", "agent_config", "leave agent_config out; freya.py sets the event model"))
    nodes = _all_nodes(wf)
    if wf.get("initial_node") not in (wf.get("nodes") or {}):
        out.append(Finding("error", "E-REF", "initial_node", f"{wf.get('initial_node')!r} is not a step"))
    for key, node in nodes.items():
        kind = node.get("node_type")
        for t in node.get("transitions") or []:
            target = t.get("target_node") if isinstance(t, dict) else None
            if target not in nodes and not (target == "__previous__" and key in (wf.get("global_nodes") or {})):
                out.append(Finding("error", "E-REF", key, f"transition to unknown step {target!r}"))
        for f in ("passthrough_default_transition", "max_turn_transition"):
            if node.get(f) and node[f] not in nodes and node[f] != "__previous__":
                out.append(Finding("error", "E-REF", key, f"{f} is unknown step {node[f]!r}"))
        if node.get("tools") and kind != "conversation":
            out.append(Finding("error", "E-PLACEMENT", key, f"tools on a {kind} step are removed by the platform"))
        if node.get("pre_actions") and kind == "conversation":
            out.append(Finding("error", "E-PLACEMENT", key, "pre_actions on a conversation step are removed by the platform"))
        if node.get("passthrough"):
            last = (node.get("transitions") or [{}])[-1]
            if ((last or {}).get("condition") or {}).get("operator") != "always":
                out.append(Finding("error", "E-PASSTHROUGH", key, "a passthrough step must end with an always transition, or it can deadlock"))
        if kind == "end_call" and (node.get("transitions") or node.get("tools")):
            out.append(Finding("error", "E-END", key, "an end_call step has no transitions and no tools"))
        if node.get("max_node_turns") and not node.get("max_turn_transition"):
            out.append(Finding("warning", "W-TURN-CAP", key, "max_node_turns without max_turn_transition changes nothing at the cap"))
        for t in node.get("pre_actions") or []:
            code = str(_default(((t.get("function") or {}).get("parameters") or {}).get("properties", {}).get("code")) or "")
            if "{{" in code or "}}" in code:
                out.append(Finding("error", "E-CODE-BRACES", key, "code contains {{ or }}; read values from vars instead"))
    for path in ([] if exported else _null_paths(wf, "$")):
        out.append(Finding("error", "E-NULL", path, "null values fail the platform's validation"))
    graph = edges(wf)
    ends = {k for k, n in nodes.items() if n.get("node_type") == "end_call"}
    for key in nodes:
        if key not in ends and not _reach(graph, key) & ends:
            out.append(Finding("warning", "W-NO-END", key, "no path from this step reaches an end_call step"))
    return out


def _null_paths(value, path):
    if value is None:
        yield path
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _null_paths(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _null_paths(v, f"{path}[{i}]")


def _reach(graph: dict[str, set[str]], start: str) -> set[str]:
    seen, queue = set(), deque(graph.get(start, ()))
    while queue:
        k = queue.popleft()
        if k in seen:
            continue
        seen.add(k)
        queue.extend(graph.get(k, ()))
    return seen


# ---------------------------------------------------------------- terminal actions

def check_contract(contract: dict, ops: dict[str, dict], base: Path) -> list[Finding]:
    out = []
    terminals = contract.get("terminal_tools") or []
    if not terminals:
        out.append(Finding("warning", "W-NO-TERMINAL", "contract", "no terminal tool declared; check the tool API and the brief"))
    for t in terminals:
        name = t.get("tool")
        if name not in ops:
            out.append(Finding("error", "E-CONTRACT-TOOL", "contract", f"terminal tool {name!r} is not an operation of the tool API"))
        if not t.get("evidence"):
            out.append(Finding("error", "E-CONTRACT-EVIDENCE", "contract", f"terminal tool {name!r} has no evidence"))
        for ev in t.get("evidence") or []:
            src = base / str(ev.get("source", ""))
            quote = " ".join(str(ev.get("quote", "")).split())
            text = " ".join(src.read_text(errors="replace").split()) if src.is_file() else ""
            if not quote or quote not in text:
                out.append(Finding("error", "E-CONTRACT-EVIDENCE", "contract", f"quote for {name!r} not found in {ev.get('source')}: {quote[:80]!r}"))
    return out


def check_terminal(wf: dict, ops: dict[str, dict], contract: dict) -> list[Finding]:
    out = []
    terminal = {t.get("tool") for t in contract.get("terminal_tools") or []}
    if not terminal:
        return out
    nodes = _all_nodes(wf)
    graph = edges(wf)
    term_nodes = set()
    for key, node in nodes.items():
        for field in ("tools", "pre_actions"):
            used = [o for o in (tool_operation(t, ops) for t in node.get(field) or [] if isinstance(t, dict)) if o]
            hit = set(used) & terminal
            if hit:
                term_nodes.add(key)
                others = sorted(set(used) - hit)
                if others:
                    out.append(Finding("error", "E-TERMINAL-SHARED", key,
                                       f"{sorted(hit)} is offered together with {others}; tool calls of one message run concurrently, so the terminal call can land first"))
    if not term_nodes:
        out.append(Finding("error", "E-TERMINAL-MISSING", "workflow", f"no step offers or runs the terminal tool {sorted(terminal)}"))
    for t in term_nodes:
        for r in sorted(_reach(graph, t) - {t}):
            later = sorted(set(bank_ops(nodes[r], ops)) - terminal)
            if later:
                out.append(Finding("error", "E-TERMINAL-AFTER", r, f"reachable from terminal step {t!r} and offers or runs {later}; a terminal step may lead only to end_call steps"))
    for tool in wf.get("tools") or []:
        if "end_of_call" in ((tool.get("config") or {}).get("alwaysRunsAt") or []) and tool_operation(tool, ops):
            out.append(Finding("error", "E-TERMINAL-AFTER", "tools", f"end-of-call lifecycle tool {tool['function'].get('name')} calls the bank after the call"))
    if contract.get("every_call_ends_with_terminal"):
        ends = {k for k, n in nodes.items() if n.get("node_type") == "end_call"}
        if wf.get("initial_node") in ends:
            out.append(Finding("error", "E-TERMINAL-BYPASS", wf["initial_node"], "the call can end without the terminal tool"))
        for src, targets in graph.items():
            for e in sorted(targets & ends):
                if src not in term_nodes:
                    out.append(Finding("error", "E-TERMINAL-BYPASS", src, f"enters end_call step {e!r} without passing a terminal step"))
    return out


# ---------------------------------------------------------------- entry points

def check(workflow: dict, openapi: dict, contract: dict | None = None, base: Path = Path(".")) -> list[Finding]:
    exported = "nodes" not in workflow and isinstance(workflow.get("workflow"), dict)
    wf = workflow["workflow"] if exported else workflow
    ops = load_operations(openapi)
    findings = check_graph(wf, exported)
    for key, node in _all_nodes(wf).items():
        for field in ("tools", "pre_actions"):
            for t in node.get(field) or []:
                if isinstance(t, dict):
                    findings += check_tool(t, ops, key)
    for t in wf.get("tools") or []:
        findings += check_tool(t, ops, "tools")
    if contract is not None:
        findings += check_contract(contract, ops, base)
        findings += check_terminal(wf, ops, contract)
    return findings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("workflow", type=Path)
    p.add_argument("--tools", type=Path, required=True)
    p.add_argument("--contract", type=Path)
    p.add_argument("--base", type=Path, default=Path("."), help="directory that contract evidence sources are relative to")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    try:
        wf, api = json.loads(a.workflow.read_text()), json.loads(a.tools.read_text())
        contract = json.loads(a.contract.read_text()) if a.contract else None
    except (OSError, ValueError) as e:
        print(f"cannot read input: {e}", file=sys.stderr)
        return 2
    findings = check(wf, api, contract, a.base)
    errors = [f for f in findings if f.level == "error"]
    if a.json:
        print(json.dumps({"errors": len(errors), "findings": [f.as_dict() for f in findings]}, indent=1))
    else:
        for f in findings:
            print(f)
        print(f"{len(errors)} errors, {len(findings) - len(errors)} warnings"
              + ("" if contract is not None else ". No contract given: terminal-action ordering was not checked."))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
