"""Thin live adapter over the kit runner. Dry run unless `live=True`.

It reuses the kit's `run_cases.run_once` (sessions, simulation, judge, ledger scoring) unchanged. On top it adds:
its own persona store (state/persona_lab/personas.json), one variant per public case per simulation, the raw ledger,
judge row and call transcript of every call, and a triage verdict per call.
"""
from __future__ import annotations

import glob
import json
import os
import time
from pathlib import Path

from .common import GEN, KIT, RESULTS, ROOT, STATE, sha256, write_json
from .triage import triage

SHORTLIST = ["V09", "V06", "V07", "V01", "V08", "V04", "V12", "V02"]


def load_compiled() -> tuple[dict, dict, dict]:
    d = GEN / "personas"
    manifest = json.loads((d / "manifest.json").read_text())["variants"]
    personas = json.loads((d / "personas.json").read_text())
    cases = {}
    for c in json.loads((d / "cases.json").read_text()):
        cases[c["style"][3:]] = c
    return manifest, personas, cases


def select(manifest: dict, spec: str) -> list[str]:
    if spec == "shortlist":
        return [v for v in SHORTLIST if v in manifest]
    if spec == "all":
        return sorted(manifest, key=lambda v: manifest[v]["rank"])
    out = [v.strip() for v in spec.split(",") if v.strip()]
    unknown = [v for v in out if v not in manifest]
    if unknown:
        raise SystemExit(f"unknown variants: {unknown}")
    return out


def batches(manifest: dict, chosen: list[str]) -> list[dict]:
    """Simulations to run: one brief (so one agent) each, and each public case at most once per simulation."""
    out = []
    for v in sorted(chosen, key=lambda v: manifest[v]["rank"]):
        m = manifest[v]
        for b in out:
            if b["brief"] == m["brief"] and m["base_case"] not in b["cases"]:
                b["variants"].append(v)
                b["cases"].add(m["base_case"])
                break
        else:
            out.append({"brief": m["brief"], "variants": [v], "cases": {m["base_case"]}})
    return [{"brief": b["brief"], "variants": b["variants"]} for b in out]


def plan_text(manifest: dict, chosen: list[str], agents: dict, store: dict) -> str:
    lines = []
    for i, b in enumerate(batches(manifest, chosen), 1):
        lines.append(f"simulation {i}: brief {b['brief']} agent {agents.get(b['brief']) or '(missing --agent-' + b['brief'].lower() + ')'}")
        for v in b["variants"]:
            m = manifest[v]
            known = "persona exists" if m["persona_key"] in store else "persona will be created"
            lines.append(f"  {v} rank {m['rank']} {m['base_case']} {m['layer']:<10} {','.join(m['families'])} | {known}")
    return "\n".join(lines)


def baseline(case_id: str) -> list[str]:
    """This case's official results already on disk (runs/*/eval/*.json), for attribution."""
    out = []
    for f in sorted(glob.glob(str(ROOT / "runs" / "*" / "eval" / "*.json"))):
        try:
            r = json.loads(Path(f).read_text())
        except ValueError:
            continue
        if not isinstance(r, dict):           # e.g. eval/classified.json is a list of per-call rows
            continue
        for x in r.get("final") or []:
            if x.get("id") == case_id:
                out.append(f"{Path(f).parent.parent.name}/{Path(f).name}: {x['passes']}/{x['runs']}")
    return out


def _env() -> None:
    """Credentials from the kit's env.sh or the environment, into os.environ. Values are never printed."""
    from builder.kitrun import resolve_env
    for k, v in resolve_env(KIT / "env.sh", dict(os.environ)).items():
        os.environ.setdefault(k, v)
    missing = [k for k in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY") if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"missing settings: {missing}")


def run(chosen: list[str], agents: dict, reps: int = 1, live: bool = False, workflows: dict | None = None,
        out: Path | None = None) -> Path | None:
    manifest, personas, cases = load_compiled()
    store_file = STATE / "personas.json"
    store = json.loads(store_file.read_text()) if store_file.exists() else {}
    print(plan_text(manifest, chosen, agents, store))
    todo = batches(manifest, chosen)
    if missing := sorted({b["brief"] for b in todo} - {k for k, v in agents.items() if v}):
        raise SystemExit(f"no agent for brief {missing}")
    if not live:
        print("\ndry run: nothing was sent. Add --live when the simulation queue is free.")
        return None
    _env()
    from .common import kit_path
    kit_path()
    import freya                                  # reads FREYA_API_KEY at import, so only after _env()
    import run_cases
    from score import http
    out = out or RESULTS / time.strftime("%Y%m%d-%H%M%S")
    new = [v for v in chosen if manifest[v]["persona_key"] not in store]
    if new:
        made = freya.create_personas([personas[v] for v in new])["personas"]
        store.update({manifest[v]["persona_key"]: p["id"] for v, p in zip(new, made)})
        write_json(store_file, store)
    versions = {}
    for brief, wid in (workflows or {}).items():
        if wid:
            path = out / f"workflow-{brief}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            freya.export_workflow(wid, str(path))
            versions[brief] = {"workflow_id": wid, "export_sha256": sha256(path.read_bytes())}
    records = []
    for rep in range(1, reps + 1):
        for b in todo:
            vs = b["variants"]
            bcases = [cases[v] for v in vs]
            ids = {cases[v]["id"]: store[manifest[v]["persona_key"]] for v in vs}
            rows, sim_id, it_id, status, took, med = run_cases.run_once(agents[b["brief"]], bcases, ids)
            judge = {r["personaId"]: r for r in freya.get_iteration(sim_id, it_id)["runs"]}
            for v, row in zip(vs, rows):
                ledger = http("/v1/practice/ledger/" + row["customer_id"])
                call = freya.get_call(row["call_id"]) if row.get("call_id") else {}
                j = judge.get(ids[row["id"]], {})
                rec = {"variant": v, "layer": manifest[v]["layer"], "rep": rep, "case": cases[v], "agent_id": agents[b["brief"]],
                       "workflow": versions.get(b["brief"]), "simulation_id": sim_id, "iteration_id": it_id,
                       "simulation_status": status, "kit_row": row, "ledger": ledger,
                       "judge": {"outcome": j.get("outcome"), "reason": j.get("reason")},
                       "messages": call.get("messages", []), "ended": call.get("endedReason"),
                       "median_slowest_turn_s": med, "spec_hash": manifest[v]["spec_hash"], "persona_key": manifest[v]["persona_key"]}
                rec["triage"] = triage(rec)
                write_json(out / "raw" / f"{v}-r{rep}.json", rec)
                records.append(rec)
                print(f"{v} r{rep} {rec['triage']['verdict']} {rec['triage']['modes']}")
    write_json(out / "report.json", report(out))
    print(render_report(json.loads((out / "report.json").read_text())))
    return out


def report(out: Path) -> dict:
    """Per variant: verdicts over reps, failure modes, the base case's stored official results."""
    per, modes = {}, {}
    for f in sorted((out / "raw").glob("*.json")):
        rec = json.loads(f.read_text())
        t = rec.get("triage") or triage(rec)
        p = per.setdefault(rec["variant"], {"case": rec["case"]["id"], "layer": rec["layer"], "verdicts": [], "modes": []})
        p["verdicts"].append(t["verdict"])
        p["modes"] += t["modes"]
        if t["verdict"] == "AGENT_FAIL":
            for m in t["modes"]:
                modes.setdefault(m, set()).add(rec["variant"])
    for v, p in per.items():
        fails, counted = p["verdicts"].count("AGENT_FAIL"), sum(x in ("PASS", "AGENT_FAIL") for x in p["verdicts"])
        p["reading"] = ("no countable run" if not counted else
                        "reproducible failure: act on it" if fails >= 2 else
                        "single failure: may be stochastic, repeat before acting" if fails == 1 else "passed every counted run")
        p["baseline"] = baseline(p["case"])
    return {"variants": per, "modes": {m: sorted(v) for m, v in sorted(modes.items())},
            "note": "official layer: kit ledger scorer + judge on public customers. Diagnostics: invariants only."}


def render_report(r: dict) -> str:
    lines = ["failures by mode:"] + ([f"  {m}: {', '.join(v)}" for m, v in r["modes"].items()] or ["  none"])
    lines.append("variants:")
    for v, p in r["variants"].items():
        lines.append(f"  {v} {p['case']} {p['layer']}: {' '.join(p['verdicts'])} -> {p['reading']}; modes {sorted(set(p['modes'])) or '-'}")
        lines.append(f"     baseline {p['case']}: {'; '.join(p['baseline']) or 'none on disk'}")
    return "\n".join(lines)
