"""Combine run_cases result files per customer and classify each failed call from its own error events.

    python classify.py REPO RESULTS.json [RESULTS.json ...] [--json OUT]

A failure counts as infrastructure only when the call's error events carry a sandbox, DNS or backend error. Silence or
a stall without such an event stays an agent failure here. Raw result files are not changed."""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# Platform failures only. A bank answer such as {'ok': False, 'error': 'service unavailable'} is a scripted test
# condition (PUB-10 "Tool failure"), not infrastructure, so generic HTTP words are not matched here.
INFRA = re.compile(r"snekbox|Sandbox did not return|Name or service not known|Cannot connect to host|Temporary failure in name resolution"
                   r"|maximum recursion depth", re.I)

p = argparse.ArgumentParser()
p.add_argument("repo", type=Path)
p.add_argument("results", nargs="+", type=Path)
p.add_argument("--json", type=Path)
a = p.parse_args()
sys.path.insert(0, str(a.repo))
from builder.kitrun import load_env  # noqa: E402

os.environ.update(load_env(a.repo / "docs/build-the-builder/env.sh"))
sys.path.insert(0, str(a.repo / "docs/build-the-builder"))
import freya  # noqa: E402


def errors_of(call_id):
    out = []
    for m in freya.get_call(call_id).get("messages", []) if call_id else []:
        text = m.get("message") or ""
        if m.get("role") == "system" and "error" in text.lower():
            try:
                ev = json.loads(text)
                text = f"{ev.get('event')}: {ev.get('function')}: {str(ev.get('error') or ev.get('message') or ev)[:160]}"
            except ValueError:
                text = text[:160]
            out.append(text)
    return out


per = defaultdict(list)
detail = []
for f in a.results:
    r = json.loads(f.read_text())
    for rep, run in enumerate(r.get("all_rows") or [r["rows"]], 1):
        for row in run:
            errs = [] if row["pass"] else errors_of(row.get("call_id"))
            infra = [e for e in errs if INFRA.search(e)]
            kind = "pass" if row["pass"] else ("infrastructure" if infra else "agent")
            per[row["id"]].append(kind)
            detail.append({"file": f.name, "rep": rep, "id": row["id"], "kind": kind, "failed": row.get("failed"), "tools": row.get("tools"),
                           "errors": len(errs), "infra_examples": infra[:2], "call_id": row.get("call_id")})
print(f"{'case':8} {'runs':28} all-pass  without-infra")
strict = clean = 0
for cid in sorted(per):
    k = per[cid]
    ok = all(x == "pass" for x in k)
    ok_clean = all(x != "agent" for x in k) and any(x == "pass" for x in k)
    strict += ok
    clean += ok_clean
    print(f"{cid:8} {' '.join(x[:5] for x in k):28} {'yes' if ok else 'no':9} {'yes' if ok_clean else 'no'}")
print(f"\ncustomers passing every run: {strict}/{len(per)} (raw); excluding runs with confirmed infrastructure errors: {clean}/{len(per)}")
for d in detail:
    if d["kind"] != "pass":
        print(f"  {d['file']} rep {d['rep']} {d['id']} {d['kind'].upper()} errors={d['errors']} {d['infra_examples'][:1]} | failed: {str(d['failed'])[:200]} | tools: {d['tools']}")
if a.json:
    a.json.write_text(json.dumps(detail, indent=1))
