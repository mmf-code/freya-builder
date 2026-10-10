"""Offline: does the contract layer catch a builder output that is stale against a changed tool API?

For each mutation of the OpenAPI file, re-lower the builder's own body and plan and run the checker. A detected
mutation is one that produces a lowering rejection or a checker error (warnings are listed apart)."""
import copy
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1])
RUN = ROOT / sys.argv[2]
sys.path.insert(0, str(ROOT))
from builder.lower import LoweringError, lower  # noqa: E402
from builder.workflow_check import check  # noqa: E402

API = json.loads((ROOT / "docs/build-the-builder/tools/openapi.json").read_text())


def schema(api, op):
    return api["paths"][f"/{op}"]["post"]["requestBody"]["content"]["application/json"]["schema"]


def rename_path(api, old, new):
    api["paths"][f"/{new}"] = api["paths"].pop(f"/{old}")


def m_rename_terminal(api):
    rename_path(api, "close_call", "finish_call")


def m_outcome_value(api):
    e = schema(api, "close_call")["properties"]["outcome"]["enum"]
    e[e.index("no_promise")] = "no_ptp"


def m_field_rename(api):
    p = schema(api, "create_promise")
    p["properties"]["amount_due"] = p["properties"].pop("amount")
    p["required"] = ["amount_due" if f == "amount" else f for f in p.get("required", [])]


def m_new_required(api):
    p = schema(api, "add_note")
    p["properties"]["channel"] = {"type": "string", "enum": ["phone"]}
    p.setdefault("required", []).append("channel")


def m_server(api):
    api["servers"] = [{"url": "https://bank.example.org/v2"}]


def m_queue_value(api):
    e = schema(api, "transfer_to_agent")["properties"]["queue"].get("enum")
    if e:
        e[e.index("general")] = "front_desk"


MUTATIONS = [("terminal tool renamed", m_rename_terminal), ("close outcome value renamed", m_outcome_value),
             ("create_promise field renamed", m_field_rename), ("add_note gets a new required field", m_new_required),
             ("server URL changed", m_server), ("transfer queue value renamed", m_queue_value)]

for slot in (sys.argv[3:] or ["brief-a", "brief-b"]):
    ws = RUN / "workspace"
    body = json.loads((ws / "out" / f"{slot}.body.json").read_text())
    plan = json.loads((ws / "out" / f"{slot}.closing.json").read_text())
    print(f"\n== {slot} ({RUN.name})")
    for label, mutate in MUTATIONS:
        api = copy.deepcopy(API)
        mutate(api)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "tools").mkdir()
            (base / "tools" / "openapi.json").write_text(json.dumps(api))
            (base / "briefs").mkdir()
            for b in (ws / "briefs").iterdir():
                (base / "briefs" / b.name).write_text(b.read_text())
            try:
                wf, contract = lower(body, plan, api, base)
            except LoweringError as e:
                print(f"  {label:38} DETECTED by the lowering: {e.problems[0][:110]} (+{len(e.problems) - 1})")
                continue
            found = check(wf, api, contract, base)
        errs = Counter(f.code for f in found if f.level == "error")
        warns = Counter(f.code for f in found if f.level == "warning" and f.code.startswith("E-"))
        verdict = "DETECTED by the checker" if errs else ("only WARNINGS (a code hook downgrades them)" if warns else "NOT DETECTED")
        print(f"  {label:38} {verdict}: errors {dict(errs) or '-'}, downgraded {dict(warns) or '-'}")
