"""Pick the run to submit among several kitrun runs of one final brief: accepted, and no line spoken after the terminal tool.

    python3 -I tools/evaluation/closing_check.py REPO TOOLS_JSON RUN_DIR [RUN_DIR ...]

TOOLS_JSON is the brief's tool API file; its sha256 must be the one each run's summary.json recorded. Per run: kitrun's
acceptance, and per workflow kitrun exported (sha256 checked against summary.json) the steps that speak after a
terminal tool of the run's contract (`out/<slot>.contract.json`):
  - a step that runs the terminal tool as a pre_action and has a spoken on_enter (tts with text, llm or audio): the
    engine runs pre_actions on entry and speaks afterwards (docs/FAILURE_MODES.md #1);
  - a step entered from such a step by its own transitions that speaks;
  - an engine step (not a conversation step) that speaks and enters a terminal step by its own transitions: the next
    step's pre_actions run before its line is out (2026-10-11, v1-fresh transfer: the line logged after close_call);
    a conversation step that speaks and passes through to the terminal step is fine (0 NO_GOODBYE in the
    reference-v2 and blind reference calls, which close that way);
  - an end_call step that speaks on entry or has a farewell (message_mode other than "none").
Steps where the model calls the terminal tool itself (tools of a conversation step) are counted, not judged.

Pick: an accepted run with no such step; between equals, the shorter build (the kit's tie-break). Exit 0 with a pick,
1 when no run was accepted. Reads files only, no Freya call."""
import hashlib
import json
import sys
from pathlib import Path

repo, tools_path, run_dirs = Path(sys.argv[1]), Path(sys.argv[2]), [Path(p) for p in sys.argv[3:]]
sys.path.insert(0, str(repo))
from builder import workflow_check as wc  # noqa: E402

tools_bytes = tools_path.read_bytes()
ops = wc.load_operations(json.loads(tools_bytes))


def speaks(on_enter: dict | None) -> bool:
    kind = (on_enter or {}).get("type", "llm")
    return kind in ("llm", "audio") or (kind == "tts" and bool(str(on_enter.get("text") or "").strip()))


def own_targets(node: dict) -> set[str]:
    out = {t.get("target_node") for t in node.get("transitions") or [] if isinstance(t, dict)}
    return {x for x in out | {node.get("passthrough_default_transition"), node.get("max_turn_transition")} if x}


def after_terminal(wf: dict, terminal: set[str]) -> tuple[list[str], int, int]:
    """Steps that speak after the terminal tool, steps that run it, steps that offer it to the model."""
    nodes = wc._all_nodes(wf)
    runs = {k for k, n in nodes.items()
            if {wc.tool_operation(t, ops) for t in n.get("pre_actions") or [] if isinstance(t, dict)} & terminal}
    offers = {k for k, n in nodes.items()
              if {wc.tool_operation(t, ops) for t in n.get("tools") or [] if isinstance(t, dict)} & terminal}
    bad = {k for k in runs if speaks(nodes[k].get("on_enter"))}
    bad |= {x for k in runs for x in own_targets(nodes[k]) if x in nodes and nodes[x].get("node_type") != "end_call"
            and speaks(nodes[x].get("on_enter"))}
    bad |= {k for k, n in nodes.items() if n.get("node_type") not in ("conversation", "end_call")
            and own_targets(n) & runs and speaks(n.get("on_enter"))}
    for k, n in nodes.items():
        if n.get("node_type") == "end_call":
            props = (((n.get("terminal") or {}).get("function") or {}).get("parameters") or {}).get("properties") or {}
            mode = (props.get("message_mode") or {}).get("default", "none")
            if speaks(n.get("on_enter")) or mode != "none":
                bad.add(k)
    return sorted(bad), len(runs), len(offers)


candidates = []
for run in run_dirs:
    s = json.loads((run / "summary.json").read_text())
    acc = s.get("acceptance") or {}
    accepted = acc.get("accepted") is True and s.get("exit_code") == 0
    problems, speaking = [], []
    if s["inputs"]["tools"]["sha256"] != hashlib.sha256(tools_bytes).hexdigest():
        problems.append(f"{tools_path.name} is not the tool API this run used")
    for f in s.get("freya") or []:
        path = run / str(f.get("export"))
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != f.get("export_sha256"):
            problems.append(f"{f['slot']}: export missing or not the one kitrun recorded")
            continue
        cpath = run / "out" / f"{f['slot']}.contract.json"
        terminal = {t.get("tool") for t in (json.loads(cpath.read_text()) if cpath.is_file() else {}).get("terminal_tools") or []}
        if not terminal:
            problems.append(f"{f['slot']}: no contract with a terminal tool")
            continue
        exported = json.loads(path.read_text())
        bad, n_runs, n_offers = after_terminal(exported.get("workflow", exported), terminal)
        speaking += bad
        print(f"{run.name} {f['slot']}: terminal {sorted(terminal)} run in {n_runs} steps, offered to the model in {n_offers}; "
              f"speaking after it: {len(bad)}" + (f" {bad[:6]}{' ...' if len(bad) > 6 else ''}" if bad else ""))
    if not s.get("freya"):
        problems.append("no workflow exported")
    for p in problems:
        print(f"{run.name}: {p}")
    clean = not speaking and not problems
    print(f"{run.name}: exit {s.get('exit_code')}, {'accepted' if accepted else 'NOT accepted'}, {s.get('seconds')} s, "
          f"closing {'CLEAN' if clean else ('UNCHECKED' if problems else 'SPEAKS AFTER TERMINAL')}")
    if accepted and not problems:
        candidates.append((not clean, s.get("seconds") or 0, run.name))

if not candidates:
    print("pick: none (no accepted run with checked exports); run again with a new --state")
    sys.exit(1)
pick = min(candidates)
print(f"pick: {pick[2]} ({'closing clean' if not pick[0] else 'closing speaks after the terminal tool: no clean accepted run'}, {pick[1]} s)")
