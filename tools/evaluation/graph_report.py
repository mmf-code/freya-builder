"""Read-only review of exported workflows, to compare final candidates beyond closing_check. Not a repo checker.

    python3 -I graph_report.py OPENAPI.json EXPORT.workflow.json [EXPORT ...]

Per export: every bank tool and the steps that run it (model tool or engine call) with where each result goes;
conversation steps that wait silently or whose model prompt asks for tool calls only or no speech; turn caps and
where they lead; code steps; fixed lines that say "recorded", "text message" or goodbye, and the step they sit on.
It shows structure only. It does not prove what the model says in a call."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from builder import workflow_check as wc  # noqa: E402

ops = wc.load_operations(json.load(open(sys.argv[1])))
QUIET = re.compile(r"tool calls? only|only call|say nothing|do not speak|don't speak|no speech|stay silent|without speaking|do not say anything", re.I)
WORDS = re.compile(r"recorded|text message|goodbye", re.I)


def oe(n):
    o = n.get("on_enter") or {"type": "llm"}
    return o.get("type") + (": " + o["text"][:70] if o.get("text") else "")


def cond(t):
    c = t.get("condition") or {}
    if c.get("operator") == "always":
        return "always"
    if c.get("operator") == "matches_intent":
        return "intent: " + str(c.get("description") or t.get("description") or "")[:60]
    return "vars: " + json.dumps(c.get("conditions") or c)[:90]


for path in sys.argv[2:]:
    w = json.load(open(path))
    w = w.get("workflow", w)
    nodes = wc._all_nodes(w)
    kinds = {}
    for n in nodes.values():
        kinds[n.get("node_type")] = kinds.get(n.get("node_type"), 0) + 1
    print(f"== {path}: {len(nodes)} steps {kinds}, initial {w.get('initial_node')}")
    by_tool = {}
    for k, n in nodes.items():
        for t in n.get("tools") or []:
            if isinstance(t, dict) and wc.tool_operation(t, ops):
                by_tool.setdefault(wc.tool_operation(t, ops), []).append((k, "model"))
        for t in n.get("pre_actions") or []:
            if isinstance(t, dict) and wc.tool_operation(t, ops):
                by_tool.setdefault(wc.tool_operation(t, ops), []).append((k, "engine"))
    for tool in sorted(by_tool):
        print(f"  TOOL {tool}: {len(by_tool[tool])} step(s)")
        for k, how in by_tool[tool][:6]:
            n = nodes[k]
            outs = [f"{t.get('target_node')} [{cond(t)}]" for t in n.get("transitions") or []]
            print(f"    {k} ({n.get('node_type')}, {how}, on_enter {oe(n)[:40]}) -> " + "; ".join(outs)[:400])
        if len(by_tool[tool]) > 6:
            print(f"    ... {len(by_tool[tool]) - 6} more")
    for k, n in nodes.items():
        if n.get("node_type") == "conversation":
            if (n.get("on_enter") or {}).get("type") == "silent" and not n.get("passthrough"):
                print(f"  SILENT-WAIT {k}")
            text = " ".join(str(n.get(x) or "") for x in ("task_message", "role_message")) + str((n.get("on_enter") or {}).get("prompt") or "")
            m = QUIET.search(text)
            if m and oe(n).startswith("llm"):
                print(f"  QUIET-PROMPT {k}: ...{text[max(0, m.start() - 70):m.end() + 30]}...".replace("\n", " "))
        if n.get("max_node_turns"):
            print(f"  CAP {k}: {n['max_node_turns']} turns -> {n.get('max_turn_transition')}")
        if n.get("node_type") == "code":
            print(f"  CODE {k}")
        text = str((n.get("on_enter") or {}).get("text") or "")
        if WORDS.search(text):
            print(f"  LINE {k} ({n.get('node_type')}{', pt' if n.get('passthrough') else ''}): {text[:110]}")
