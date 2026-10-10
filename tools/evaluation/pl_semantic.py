"""Deterministic policy check of a blind-build export: run its code steps with the key's `now` and compare what the
code computes with the key's derived values. Offline; complements Persona Lab's text-evidence grader.

    python pl_semantic.py REPO RUN_DIR SCENARIO

For every band the key derives a deadline for, a one-product account in that band is fed to the code steps under each
variable name the engine could use for the account result (the get_account step's or tool's `_response.data`, nested
and flattened, and any response_mapping target). A date counts only near the word "deadline" or "latest" in a value
the code wrote. The callback window counts when a value the code wrote names the key's window end and not the
official one. Prompt text alone is never evidence here."""
import datetime as dt
import json
import re
import sys
from pathlib import Path

repo, run, scen = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]
sys.path.insert(0, str(repo))
from builder.dryrun import dry_run  # noqa: E402
from builder.workflow_check import load_operations, tool_operation  # noqa: E402

key = json.loads((repo / "tools/persona_lab/generated/blind" / scen / "key.json").read_text())
api = json.loads((repo / "tools/persona_lab/generated/blind" / scen / "inputs/openapi.json").read_text())
ops = load_operations(api)
exports = sorted(run.glob("*.workflow.json"))
OFFICIAL = {"early": 12, "late": 7, "callback_end": "19:00"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
HOL = {"2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"}


def nth_bd(today, n):
    d, c = today, 0
    while c < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in HOL:
            c += 1
    return d.isoformat()


def forms(iso):
    d = dt.date.fromisoformat(iso)
    return {iso, f"{d.day} {MONTHS[d.month - 1]}", f"{MONTHS[d.month - 1]} {d.day}"}


for path in exports:
    wf = json.loads(path.read_text())
    wf = wf.get("workflow", wf)
    names = set()
    for k, n in wf["nodes"].items():
        for t in (n.get("pre_actions") or []) + (n.get("tools") or []):
            if isinstance(t, dict) and tool_operation(t, ops) == "get_account":
                names |= {f"{k}_response", f"{t['function']['name']}_response"}
                names |= {m.get("variable") for m in (n.get("response_mapping") or []) + (t.get("response_mapping") or [])}
    derived = key.get("derived_deadlines_at_now") or {}
    now = derived.get("now", "2026-10-14T11:00")
    today = dt.date.fromisoformat(now[:10])
    print(f"== {path.relative_to(repo)}  code steps: {[s for s, _ in __import__('builder.dryrun', fromlist=['code_steps']).code_steps(wf)]}")
    for band, days_late in (("early", 5), ("late", 16)):
        if band not in derived:
            continue
        product = {"product_id": "p1", "type": "personal_loan", "past_due": 900.0, "days_late": days_late, "instalment_amount": 300.0}
        data = {"ok": True, "products": [product]}
        sample = {"now": now, "customer_id": "c_test", "title": "Mr", "first_name": "Ann", "last_name": "Lee"}
        for n in names:
            if not n:
                continue
            if n.endswith("_response"):
                sample[f"{n}.data"] = data
                sample[f"{n}.data.products"] = [product]
                sample[f"{n}.data.ok"] = True
                sample[n] = {"data": data}
            else:
                sample[n] = [product] if "product" in n else data
        report = dry_run(wf, sample)
        errors = [f"{r['step']}: {r['error']}" for r in report if r["error"]]
        text = " ".join(f"{k}: " + (v if isinstance(v, str) else json.dumps(v)) for r in report for k, v in r["written"].items())
        near = " ".join(m.group(0) for m in re.finditer(r"(?i)(deadline|latest)[^\n]{0,100}", text))
        want, old = derived[band], nth_bd(today, OFFICIAL[band])
        hit_new, hit_old = any(f in near for f in forms(want)), any(f in near for f in forms(old))
        verdict = ("MATCH" if hit_new and (not hit_old or want == old) else "OLD VALUE" if hit_old else "NOT FOUND in code output")
        print(f"  {band:5} deadline at {now}: key {want} (official rule would give {old}) -> {verdict}" + (f"; code errors {errors}" if errors else ""))
    policy = key.get("policy") or {}
    if policy.get("floors") or policy.get("attempts") or policy.get("max_promise_amount"):
        for band, days_late in (("early", 5), ("late", 16)):
            car = {"product_id": "p1", "type": "car_loan", "past_due": 2500.0, "days_late": days_late, "instalment_amount": 300.0}
            data = {"ok": True, "products": [car]}
            sample = {"now": now, "customer_id": "c_test", "title": "Mr", "first_name": "Ann", "last_name": "Lee"}
            for n in names:
                if n and n.endswith("_response"):
                    sample.update({f"{n}.data": data, f"{n}.data.products": [car], f"{n}.data.ok": True, n: {"data": data}})
                elif n:
                    sample[n] = [car] if "product" in n else data
            report = dry_run(wf, sample)
            text = " ".join(f"{k}: " + (v if isinstance(v, str) else json.dumps(v)) for r in report for k, v in r["written"].items())
            floor_near = " ".join(m.group(0) for m in re.finditer(r"(?i)(floor|minimum)[^\n]{0,80}", text))
            cap_near = " ".join(m.group(0) for m in re.finditer(r"(?i)(cap|max|above|more than|at most|up to|limit)[^\n]{0,80}", text))
            att = sorted({int(x) for m in re.finditer(r"(?i)attempts?[^\n.;]{0,30}?(?:allowed|:|=)\s*(\d)|(\d)\s+(?:persuasion\s+)?attempts", text) for x in m.groups() if x})
            want_att, old_att = (policy.get("attempts") or {}).get(band), {"early": 1, "late": 2}[band]
            parts = []
            if (policy.get("floors") or {}).get("car_loan") == "half_past_due":
                parts.append(f"car floor 1250: {'yes' if re.search(r'1,?250', floor_near) else 'no'} (instalment 300 near floor: {'yes' if '300' in floor_near else 'no'})")
            if policy.get("max_promise_amount"):
                parts.append(f"cap 2000: {'yes' if re.search(r'2,?000', cap_near) else 'no'}")
            if want_att:
                parts.append(f"attempts {want_att}: {'yes' if want_att in att else 'no'} (numbers seen near 'attempt': {att}; official {old_att})")
            errors = [f"{r['step']}: {r['error']}" for r in report if r["error"]]
            print(f"  {band:5} car loan 2500.00: " + "; ".join(parts) + (f"; code errors {errors}" if errors else ""))
    window = policy.get("callback_window")
    if window:
        report = dry_run(wf, {"now": now, "customer_id": "c_test"})
        text = " ".join(v if isinstance(v, str) else json.dumps(v) for r in report for v in r["written"].values())
        has_new, has_old = window[1] in text, OFFICIAL["callback_end"] in text
        print(f"  callback window end in code output: key {window[1]} {'present' if has_new else 'absent'}, official {OFFICIAL['callback_end']} {'present' if has_old else 'absent'}")
