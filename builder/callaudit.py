"""Audit the tool-call order of a practice run: was the terminal tool the last bank call, and did anything overlap it?

    python3 -m builder.callaudit RESULTS.json [RESULTS.json ...] --terminal TOOL [--json]

RESULTS.json is a run_cases.py --out file. For every case the bank's ledger gives the order the bank accepted calls in,
and the call transcript gives when each tool call started and finished. Needs the kit's env (FREYA_API_KEY,
FREYA_BANK_TEAM_KEY). This measures runtime behaviour of the calls that were made; it proves nothing about other calls.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent / "docs" / "build-the-builder"


def audit_case(row: dict, terminal: str, ledger: dict, messages: list[dict]) -> dict:
    calls = [c["tool"] for c in ledger.get("calls", [])]
    rejected = [c["tool"] for c in ledger.get("calls", []) if "closed" in str((c.get("result") or {}).get("error", ""))]
    spans, open_ = [], {}
    for m in messages:
        if m.get("role") != "system":
            continue
        try:
            ev = json.loads(m.get("message") or "{}")
        except ValueError:
            continue
        fn, t = ev.get("function"), m.get("secondsFromStart")
        if not fn or t is None or fn in ("end_call", "code_exec"):
            continue
        if ev.get("event") == "function_call_start":
            open_.setdefault(fn, []).append(t)
        elif ev.get("event") == "function_call_complete" and open_.get(fn):
            spans.append((fn, open_[fn].pop(0), t))
    term = [s for s in spans if s[0] == terminal]
    overlaps = sorted({s[0] for s in spans if s[0] != terminal for t in term if s[1] < t[2] and t[1] < s[2]})
    return {"id": row["id"], "pass": row["pass"], "tools": calls, "terminal_calls": calls.count(terminal),
            "terminal_last": bool(calls) and calls[-1] == terminal, "rejected_after_terminal": rejected, "overlapping_terminal": overlaps}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("results", nargs="+", type=Path)
    p.add_argument("--terminal", required=True, help="the terminal tool's name, as the run's contract declares it")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    sys.path[:0] = [str(KIT), str(KIT / "tools")]
    import freya
    from score import http
    rows = []
    for f in a.results:
        r = json.loads(f.read_text())
        for rep, run in enumerate(r.get("all_rows") or [r["rows"]], 1):
            for row in run:
                led = http("/v1/practice/ledger/" + row["customer_id"])
                msgs = freya.get_call(row["call_id"]).get("messages", []) if row.get("call_id") else []
                rows.append({"file": f.name, "rep": rep, **audit_case(row, a.terminal, led, msgs)})
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        for x in rows:
            flag = "" if x["terminal_last"] and not x["rejected_after_terminal"] and not x["overlapping_terminal"] and x["terminal_calls"] == 1 else "  <-- ORDER"
            print(f"{x['file']} rep {x['rep']} {x['id']} {'PASS' if x['pass'] else 'FAIL'} | terminal x{x['terminal_calls']}, last={x['terminal_last']}, "
                  f"rejected after: {x['rejected_after_terminal'] or '-'}, overlapping: {x['overlapping_terminal'] or '-'}{flag}")
        bad = [x for x in rows if x["rejected_after_terminal"] or x["overlapping_terminal"] or not x["terminal_last"]]
        print(f"\n{len(rows)} calls, {len(bad)} with an ordering problem around {a.terminal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
