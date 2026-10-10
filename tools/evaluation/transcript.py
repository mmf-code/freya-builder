"""Print the dialogue of one simulated call with tool calls and step changes. Read-only API use."""
import json
import os
import sys
from pathlib import Path

repo, call_id = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(repo))
from builder.kitrun import load_env  # noqa: E402

os.environ.update(load_env(repo / "docs/build-the-builder/env.sh"))
sys.path.insert(0, str(repo / "docs/build-the-builder"))
import freya  # noqa: E402

for m in freya.get_call(call_id).get("messages", []):
    role, text, t = m.get("role"), m.get("message") or "", m.get("secondsFromStart")
    if role == "system":
        try:
            ev = json.loads(text)
        except ValueError:
            continue
        if ev.get("event") == "function_call_start" and ev.get("function") != "code_exec":
            print(f"  [{t:6.1f}] TOOL {ev.get('function')} {json.dumps(ev.get('args'))[:160]}")
        elif ev.get("event") == "route_evaluated" and ev.get("matched") and ev.get("from_node") != ev.get("target"):
            print(f"  [{t:6.1f}] STEP {ev.get('from_node')} -> {ev.get('target')}")
    elif role in ("user", "assistant", "bot"):
        print(f"[{(t or 0):6.1f}] {role.upper()}: {text[:400]}")
