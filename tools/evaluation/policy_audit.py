"""Check simulated calls against public-brief rules that the ledger cannot see and the judge has missed. Pure by default.

    python3 -I tools/evaluation/policy_audit.py PATH [PATH ...] [--json OUT]
    python3 -I tools/evaluation/policy_audit.py --fetch REPO RESULTS.json [...] [--json OUT]

PATH is a Persona Lab raw record (`tools/persona_lab/results/<run>/raw/*.json`) or a directory holding them. With
`--fetch`, each RESULTS.json is a `run_cases.py --out` file: the call transcripts and ledgers are read from Freya and
the bank (read-only) and the case comes from the kit's public test set.

The checks encode Brief A and Brief B (A28, A30, A31, A37, A38, A47, B4, B5) and serve evaluation only; nothing here
goes into a builder. Text checks are heuristics: every finding prints the sentence it fired on, so a reader can
confirm it. They do not replace the official scorer or the judge.

| Code | Rule | Fires when |
|---|---|---|
| SPEECH_AFTER_CLOSE | A47 | the agent speaks after `close_call` started (recorded order) |
| NO_GOODBYE | A47 | nothing the agent said before `close_call` contains "goodbye" or "bye" |
| RECORDED_IN_GREETING | A1/A37 | the first line contains "recorded"; allowed by A1, but the judge has failed it as an early "recorded" |
| RECORDED_EARLY | A37 | "recorded" (not negated) before the first `create_promise` with `ok: true` |
| SMS_MISSING | A38 | a promise was recorded and no later line mentions a text message |
| TODAY_AGAIN | A28/B4 | after `get_account`, more than one question about paying today |
| ITEM_SKIPPED | B4/A30 | a product closed without a promise got no offer of its own |
| ATTEMPTS_SHORT, ATTEMPTS_OVER | A30/A31/B5 | offers for a product closed without a promise differ from its band's attempts |
| ORDER | B4 | the first offers per product do not follow `get_account` order |
| WEEKDAY | A dates | a spoken weekday does not match the date it names |

A product ask is a question sentence that names one product's past-due amount or floor and no other product's past-due
amount; ORDER uses the first ask per product. An offer is a product ask that does not end by asking about today. Bands: 1 to 7 days late early (1 attempt), 8 to 45 late (2), Brief A rule 18.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
WD = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
MO = r"(" + "|".join(MONTHS) + r")"
DATE_PATTERNS = [
    re.compile(WD + r",?\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?\s+" + MO + r"(?:,?\s+(\d{4}))?", re.I),
    re.compile(WD + r",?\s+" + MO + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", re.I),
    re.compile(WD + r",?\s+(\d{4})-(\d{2})-(\d{2})", re.I),
]
RECORDED = re.compile(r"\brecorded\b", re.I)
NEGATED = re.compile(r"\b(not|n't|nothing|never|unable|could not|couldn't|cannot)\b[^.?!]*\brecorded\b", re.I)
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
TODAY_ASK = re.compile(r"\btoday\b(?:,\s*\w+\.?\s+\w+)?\s*\?$", re.I)   # "... today?", "... today, Ms Lin?"


def bank_tool(ev: dict) -> str | None:
    """The bank tool behind a tool event: the URL's last path segment, else the function name."""
    args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
    url = str(args.get("url") or "")
    if url:
        return url.rstrip("/").rsplit("/", 1)[-1]
    return ev.get("function")


def timeline(messages: list[dict]) -> list[dict]:
    """Agent lines, customer lines and bank tool starts/results in recorded order."""
    out, open_ = [], {}
    for m in messages or []:
        t = m.get("secondsFromStart") or 0.0
        role = m.get("role")
        if role in ("assistant", "bot") and (m.get("message") or "").strip():
            out.append({"t": t, "kind": "say", "text": m["message"].strip()})
        elif role == "user" and (m.get("message") or "").strip():
            out.append({"t": t, "kind": "hear", "text": m["message"].strip()})
        elif role == "system":
            try:
                ev = json.loads(m.get("message") or "{}")
            except ValueError:
                continue
            if not isinstance(ev, dict) or ev.get("function") in (None, "code_exec", "end_call"):
                continue
            if ev.get("event") == "function_call_start":
                tool = bank_tool(ev)
                open_.setdefault(ev["function"], []).append(tool)
                out.append({"t": t, "kind": "start", "tool": tool})
            elif ev.get("event") in ("function_call_complete", "function_call_error"):
                tool = (open_.get(ev["function"]) or [bank_tool(ev)]).pop(0) if open_.get(ev["function"]) else bank_tool(ev)
                res = ev.get("result") if isinstance(ev.get("result"), dict) else {}
                data = res.get("data") if isinstance(res.get("data"), dict) else res
                ok = ev.get("event") == "function_call_complete" and bool(data.get("ok"))
                out.append({"t": t, "kind": "result", "tool": tool, "ok": ok})
    return out


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+|\n+", text) if s.strip()]


def numbers(text: str) -> set[float]:
    out = set()
    for raw in NUM.findall(re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)):
        try:
            out.add(round(float(raw.replace(",", "")), 2))
        except ValueError:
            pass
    return out


def products_of(ledger: dict) -> list[dict]:
    for c in ledger.get("calls") or []:
        if c.get("tool") == "get_account" and (c.get("result") or {}).get("ok"):
            return (c["result"].get("products") or [])
    return []


def floor(p: dict) -> float | None:
    v = p.get("minimum_payment") if p.get("type") == "credit_card" else p.get("instalment_amount")
    return round(float(v), 2) if v is not None else None


def weekday_findings(text: str, now: dt.date) -> list[str]:
    found = []
    for i, pat in enumerate(DATE_PATTERNS):
        for m in pat.finditer(text):
            try:
                if i == 0:
                    day, month, year = int(m.group(2)), MONTHS.index(m.group(3).lower()) + 1, m.group(4)
                elif i == 1:
                    month, day, year = MONTHS.index(m.group(2).lower()) + 1, int(m.group(3)), m.group(4)
                else:
                    year, month, day = m.group(2), int(m.group(3)), int(m.group(4))
                y = int(year) if year else (now.year + 1 if month < now.month else now.year)
                date = dt.date(y, month, day)
            except ValueError:
                continue
            if DAYS[date.weekday()] != m.group(1).lower():
                found.append(f"'{m.group(0)}' is a {DAYS[date.weekday()].capitalize()}")
    return found


def audit(case: dict, ledger: dict, messages: list[dict]) -> list[dict]:
    tl = timeline(messages)
    says = [e for e in tl if e["kind"] == "say"]
    find = []

    def add(code, rule, t, text):
        find.append({"code": code, "rule": rule, "t": round(t, 2), "text": text[:220]})

    close_t = next((e["t"] for e in tl if e["kind"] == "start" and e["tool"] == "close_call"), None)
    if close_t is not None:
        for e in says:
            if e["t"] >= close_t:
                add("SPEECH_AFTER_CLOSE", "A47", e["t"], e["text"])
        if not any(re.search(r"\b(good ?bye|bye)\b", e["text"], re.I) for e in says if e["t"] < close_t):
            add("NO_GOODBYE", "A47", close_t, "no goodbye before close_call")

    promise_ok_t = next((e["t"] for e in tl if e["kind"] == "result" and e["tool"] == "create_promise" and e["ok"]), None)
    if says and RECORDED.search(says[0]["text"]):
        add("RECORDED_IN_GREETING", "A1/A37", says[0]["t"], says[0]["text"])
    for e in says[1:]:
        for s in sentences(e["text"]):
            if RECORDED.search(s) and not NEGATED.search(s) and (promise_ok_t is None or e["t"] < promise_ok_t):
                if promise_ok_t is not None or re.search(r"promise|payment|pay\b", s, re.I):
                    add("RECORDED_EARLY", "A37", e["t"], s)
    if promise_ok_t is not None and not any(re.search(r"text message|\bsms\b", e["text"], re.I) for e in says if e["t"] >= promise_ok_t):
        add("SMS_MISSING", "A38", promise_ok_t, "no text-message sentence after the recorded promise")

    acct_t = next((e["t"] for e in tl if e["kind"] == "result" and e["tool"] == "get_account" and e["ok"]), None)
    prods = products_of(ledger)
    if acct_t is not None:
        today_qs = [(e["t"], s) for e in says if e["t"] >= acct_t for s in sentences(e["text"]) if TODAY_ASK.search(s)]
        if len(today_qs) > 1:
            for t, s in today_qs[1:]:
                add("TODAY_AGAIN", "A28/B4", t, s)

    if prods and acct_t is not None:
        past = {p["product_id"]: round(float(p["past_due"]), 2) for p in prods}
        asks = {p["product_id"]: [] for p in prods}      # every question about one product, today asks included
        offers = {p["product_id"]: [] for p in prods}    # the same without today asks: the persuasion attempts
        for e in says:
            if e["t"] < acct_t or (close_t is not None and e["t"] >= close_t):
                continue
            def named(nums):                             # a past-due match wins over a floor match (amounts can coincide)
                by_past = [p["product_id"] for p in prods if past[p["product_id"]] in nums]
                return by_past or [p["product_id"] for p in prods if floor(p) in nums]
            whole = named(numbers(e["text"]))
            for s in sentences(e["text"]):
                if not s.endswith("?"):
                    continue
                nums = numbers(s)
                hit = named(nums)
                other = [pid for pid in past if past[pid] in nums and pid not in hit]
                if not hit and not nums and len(whole) == 1:
                    hit = whole                          # "The car loan has 75.00 past due. Can you pay that today?"
                if len(hit) == 1 and not other:
                    asks[hit[0]].append((e["t"], s))
                    if not TODAY_ASK.search(s):
                        offers[hit[0]].append((e["t"], s))
        promised = {p["product_id"] for p in ledger.get("promises") or []}
        refused_notes = {n.get("product_id") for n in ledger.get("notes") or [] if n.get("reason") == "refused"}
        single_refused = len(prods) == 1 and (ledger.get("outcome"), ledger.get("reason")) == ("no_promise", "refused")
        for p in prods:
            pid = p["product_id"]
            if pid in promised or not (pid in refused_notes or single_refused):
                continue
            want = 1 if int(p.get("days_late") or 0) <= 7 else 2
            got = len(offers[pid])
            label = f"{p.get('type')} {pid}: {got} offer(s), band wants {want}"
            if got == 0 and len(prods) > 1:
                add("ITEM_SKIPPED", "B4/A30", acct_t, label)
            elif got < want:
                add("ATTEMPTS_SHORT", "A30/B5", offers[pid][-1][0] if got else acct_t, label + (f"; last: {offers[pid][-1][1]}" if got else ""))
            elif got > want:
                add("ATTEMPTS_OVER", "A31", offers[pid][-1][0], label + f"; extra: {offers[pid][-1][1]}")
        if len(prods) > 1:
            # Out of order: a later product is asked before an earlier one is asked, or an earlier product gets a
            # promise without ever being asked on its own after a later one was asked first (Brief B rule 4).
            # Skipped when the customer first named one date for everything (Brief B rule 6 handles that case).
            hears = [e for e in tl if e["kind"] == "hear"]
            one_date = re.compile(r"\b(both|all|everything)\b.*\b(" + "|".join(MONTHS + DAYS) + r"|tomorrow|\d{1,2}(st|nd|rd|th)|first|second|third|[a-z]+tieth|[a-z]+teenth)\b", re.I)
            ids = [p["product_id"] for p in prods]
            for pj in sorted((x for x in ids if asks[x]), key=lambda x: asks[x][0][0]):
                j, tj = ids.index(pj), asks[pj][0][0]
                if any(h["t"] <= tj and one_date.search(h["text"]) for h in hears):
                    continue
                late = [pi for pi in ids[:j] if (asks[pi] and asks[pi][0][0] > tj) or (not asks[pi] and pi in promised)]
                if late:
                    add("ORDER", "B4", tj, f"{prods[j].get('type')} asked before {', '.join(prods[ids.index(x)].get('type') for x in late)}: {asks[pj][0][1]}")
                    break

    now_raw = str(((case.get("variables") or {}).get("now")) or "2026-10-14")[:10]
    now = dt.date.fromisoformat(now_raw)
    for e in says:
        for f in weekday_findings(e["text"], now):
            add("WEEKDAY", "A7", e["t"], f)
    return find


def load_records(paths: list[Path]) -> list[dict]:
    out = []
    for p in paths:
        files = sorted(p.glob("raw/*.json")) or sorted(p.glob("*.json")) if p.is_dir() else [p]
        for f in files:
            r = json.loads(f.read_text())
            if not isinstance(r, dict) or "messages" not in r:
                continue
            group = f.parent.parent.name if f.parent.name == "raw" else f.parent.name
            # Persona Lab "-reps23" batches number their reps 1 and 2; they are reps 2 and 3 of the cell.
            rep = int(r.get("rep") or 1) + (1 if group.endswith("reps23") else 0)
            label = re.sub(r"^\d{8}-\d{6}-", "", group).removesuffix("-reps23")
            out.append({"label": label, "id": f"{r.get('variant')}-r{rep}", "call_id": (r.get("kit_row") or {}).get("call_id"),
                        "judge": (r.get("judge") or {}).get("outcome"), "case": r["case"], "ledger": r.get("ledger") or {},
                        "messages": r["messages"]})
    return out


def fetch_records(repo: Path, results: list[Path]) -> list[dict]:
    """run_cases --out files -> records, reading each call and ledger from the API (read-only)."""
    import os
    sys.path.insert(0, str(repo))
    from builder.kitrun import load_env
    kit = repo / "docs/build-the-builder"
    os.environ.update(load_env(kit / "env.sh"))
    sys.path[:0] = [str(kit), str(kit / "tools")]
    import freya
    from score import http
    data = json.loads((kit / "public-test-set.json").read_text())
    cases = {c["id"]: c for c in (data["cases"] if isinstance(data, dict) else data)}
    out = []
    for f in results:
        r = json.loads(f.read_text())
        for rep, run in enumerate(r.get("all_rows") or [r["rows"]], 1):
            for row in run:
                msgs = freya.get_call(row["call_id"]).get("messages", []) if row.get("call_id") else []
                out.append({"label": f.stem, "id": f"{row['id']}-r{rep}", "call_id": row.get("call_id"),
                            "judge": "pass" if row.get("pass") else "fail", "case": cases.get(row["id"], {}),
                            "ledger": http("/v1/practice/ledger/" + row["customer_id"]), "messages": msgs})
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--fetch", type=Path, metavar="REPO", help="treat PATHS as run_cases --out files and read calls from the API")
    p.add_argument("--json", type=Path, help="write all findings to this file")
    a = p.parse_args(argv)
    records = fetch_records(a.fetch, a.paths) if a.fetch else load_records(a.paths)
    rows = []
    for r in records:
        rows.append({k: r[k] for k in ("label", "id", "call_id", "judge")} | {"findings": audit(r["case"], r["ledger"], r["messages"])})
    for x in rows:
        if x["findings"]:
            print(f"{x['label']} {x['id']} judge={x['judge']} call={str(x['call_id'])[:8]}")
            for f in x["findings"]:
                print(f"    {f['code']:<20} {f['rule']:<7} t={f['t']:<7} {f['text']}")
    labels = sorted({x["label"] for x in rows})
    codes = sorted({f["code"] for x in rows for f in x["findings"]})
    print("\nCalls with each finding (calls audited per label in brackets):")
    print("| code | " + " | ".join(f"{l} ({sum(1 for x in rows if x['label'] == l)})" for l in labels) + " |")
    print("|---|" + "---|" * len(labels))
    for c in codes:
        cells = [sum(1 for x in rows if x["label"] == l and any(f["code"] == c for f in x["findings"])) for l in labels]
        print(f"| {c} | " + " | ".join(map(str, cells)) + " |")
    judged = [x for x in rows if x["judge"] == "pass" and any(f["code"] not in ("RECORDED_IN_GREETING",) for f in x["findings"])]
    print(f"\n{len(rows)} calls; {len(judged)} judge-passed calls carry a finding other than RECORDED_IN_GREETING.")
    if a.json:
        a.json.write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
