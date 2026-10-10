"""Classify one simulated call from its raw record. Pure; no network.

Verdicts:
- PASS              ledger matches (official layer) and the judge passed
- AGENT_FAIL        a failure with no platform evidence; modes name the general failure family
- INFRA_CONFIRMED   explicit platform evidence: sandbox/function errors, platform error events, a failed simulation
- INCONCLUSIVE      no verdict, no transcript, or a stall with no error event. Silence alone is never called an outage
Diagnostics (layer "diagnostic") get modes from invariants only; their ledger and judge results are information.
"""
from __future__ import annotations

import json
import re

from builder.callaudit import audit_case

WRITES = ("create_promise", "add_note", "schedule_callback", "transfer_to_agent")
INFRA = re.compile(r"snekbox|sandbox|failed to reach|timed? ?out|econnreset|502|503|504|internal server error|maximum recursion", re.I)


def events(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages or []:
        if m.get("role") != "system":
            continue
        try:
            ev = json.loads(m.get("message") or "{}")
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def infra_evidence(record: dict) -> list[str]:
    ev = []
    if record.get("simulation_status") not in (None, "completed"):
        ev.append(f"simulation status {record['simulation_status']}")
    for e in events(record.get("messages")):
        text = json.dumps(e)
        if e.get("event") in ("function_call_error", "error") and INFRA.search(text):
            ev.append(f"{e.get('event')}: {text[:160]}")
    return ev


def invariant_modes(case: dict, ledger: dict, messages: list[dict]) -> list[str]:
    """Behaviour that is wrong under any brief of this family, whatever the expected ledger says."""
    modes = []
    calls = ledger.get("calls") or []
    if any(c["tool"] in ("get_account", "create_promise") and (c.get("result") or {}).get("error") == "identity not verified" for c in calls):
        modes.append("AUTH_ORDER")
    seen_ok = set()
    for c in calls:
        if c["tool"] not in WRITES:
            continue
        sig = (c["tool"], json.dumps(c.get("args") or c.get("request") or {}, sort_keys=True))
        if sig in seen_ok and sig[1] != "{}":
            modes.append("BLIND_RETRY")
            break
        if (c.get("result") or {}).get("ok"):
            seen_ok.add(sig)
    if case["expected"]["outcome"] in ("not_reached", "no_contact", "unreached") and any(c["tool"] in ("verify_identity", "get_account") for c in calls):
        modes.append("THIRD_PARTY_AUTH")
    audit = audit_case({"id": case["id"], "pass": None}, "close_call", ledger, messages or [])
    if audit["terminal_calls"] != 1 or not audit["terminal_last"]:
        modes.append("TERMINAL_ORDER")
    if audit["overlapping_terminal"] or audit["rejected_after_terminal"]:
        modes.append("TERMINAL_RACE")
    return modes


def ledger_modes(case: dict, ledger: dict) -> list[str]:
    exp, modes = case["expected"], []
    if (ledger.get("outcome"), ledger.get("reason")) != (exp["outcome"], exp.get("reason")):
        modes.append("OUTCOME_ENUM")
    got = {}
    for p in ledger.get("promises") or []:
        got.setdefault(p["product_id"], []).append(p)
    want = {p["product_id"]: p for p in exp["promises"]}
    for pid, ps in got.items():
        if len(ps) > 1:
            modes.append("DUPLICATE_WRITE")
        if pid not in want:
            modes.append("PER_PRODUCT_STATE")
            continue
        if round(float(ps[0]["amount"]), 2) != round(float(want[pid]["amount"]), 2):
            modes.append("AMOUNT")
        if ps[0]["date"] != want[pid]["date"]:
            modes.append("DATE")
    if set(want) - set(got):
        modes.append("MISSING_PROMISE")
    nk = lambda n: (n.get("product_id"), n["reason"])
    if sorted(map(nk, ledger.get("notes") or [])) != sorted(map(nk, exp["notes"])):
        modes.append("NOTES")
    if sorted((c["date"], c["time"]) for c in ledger.get("callbacks") or []) != sorted((c["date"], c["time"]) for c in exp["callbacks"]):
        modes.append("CALLBACK")
    if sorted(t["queue"] for t in ledger.get("transfers") or []) != sorted(t["queue"] for t in exp["transfers"]):
        modes.append("ROUTING")
    return modes


def triage(record: dict) -> dict:
    """record: {variant, layer, case, ledger, judge{outcome, reason}, messages, simulation_status, ended}"""
    case, ledger, judge = record["case"], record.get("ledger") or {}, record.get("judge") or {}
    msgs = record.get("messages") or []
    inv = invariant_modes(case, ledger, msgs) if ledger else []
    led = ledger_modes(case, ledger) if ledger and record["layer"] == "official" else []
    pending = judge.get("outcome") in (None, "queued", "running")
    judge_ok = judge.get("outcome") == "pass"
    modes = sorted(set(inv + led))
    if record["layer"] == "official" and ledger and not modes and not judge_ok and not pending:
        modes = ["JUDGE_ONLY"]
    infra = infra_evidence(record)
    stall = record.get("ended") == "customer-ended-call" and not any(e.get("event") == "function_call_start" for e in events(msgs))
    if not modes and judge_ok:
        verdict = "PASS"
    elif infra:
        verdict = "INFRA_CONFIRMED"
    elif not ledger or pending or stall:
        verdict = "INCONCLUSIVE"              # a stall without an error event is a reason to repeat, not proof of anything
    else:
        verdict = "AGENT_FAIL"
    if record["layer"] == "diagnostic" and verdict == "AGENT_FAIL" and not inv:
        verdict = "INFO"                      # a diagnostic fails only on an invariant
    return {"variant": record["variant"], "case": case["id"], "layer": record["layer"], "verdict": verdict,
            "modes": modes, "infra_evidence": infra, "stall_without_error": stall,
            "judge": (judge.get("outcome"), " ".join(str(judge.get("reason") or "").split())[:300])}
