"""Triage simulated calls against public-brief rules that the ledger cannot see and the judge has missed. Pure by default.

    python3 -I tools/evaluation/policy_audit.py PATH [PATH ...] [--json OUT] [--review REVIEW.json]
    python3 -I tools/evaluation/policy_audit.py --fetch REPO RESULTS.json [...] [--json OUT] [--save DIR]

PATH is a Persona Lab raw record (`tools/persona_lab/results/<run>/raw/*.json`) or a directory holding them. With
`--fetch`, each RESULTS.json is a `run_cases.py --out` file: the call transcripts and ledgers are read from Freya and
the bank (read-only) and the case comes from the kit's public test set; the verdict is then the kit's PASS/FAIL
(ledger and judge together). `--save DIR` keeps the fetched records for a later run without the API.

This is a triage tool, not a scorer. Every finding names the sentence and time it fired on and is a claim to read and
confirm. `--review` takes {"<call_id>|<code>": "confirmed" | "false_positive" | "unclear"}; the summary counts each
status apart, and only confirmed findings are policy violations. No finding does not mean the call follows the brief:
each check covers one rule, and only in the calls where it applies (the "checked" counts).

| Code | Class | Rule | Fires when |
|---|---|---|---|
| NO_GOODBYE | violation | A47 | nothing the agent said before `close_call` started contains "goodbye" or "bye" |
| NO_THANKS | violation | A47 | nothing said before `close_call` contains "thank" |
| RECORDED_EARLY | violation | A37 | "recorded" claimed (not negated, not future) before the write it names returned `ok: true`: the named product's write, all started promise writes for a plural claim, else the first promise |
| SMS_MISSING | violation | A38 | after the first recorded promise no sentence says a text message will come (a negated one does not count) |
| TODAY_AGAIN | violation | B4 | several products, and more than one question that ends by asking to pay today |
| ORDER | violation | B4 | several products, and a later product is asked before an earlier one the customer had not settled |
| ITEM_SKIPPED | violation | B4/A30 | several products, and one closed with a `refused` note got no offer of its own |
| ATTEMPTS_SHORT, ATTEMPTS_OVER | violation | A30/A31/B5 | offers for a product closed without a promise differ from its band's attempts |
| WEEKDAY | violation | A section 7 | a spoken weekday does not match the date it names |
| SMS_NOT_VERBATIM | wording | A38 | the text-message sentence is there but not the brief's exact sentence |
| RECORDED_IN_GREETING | judge risk | A1 | the first line says "recorded" about the call; A1 allows it, the judge has failed it as an early "recorded" |
| SPEECH_AFTER_CLOSE | observation | (A47) | the agent speaks after `close_call` started; A47 itself asks only for thanks and goodbye before it |

A product ask is a question sentence that names one product's past-due amount or floor and no other product's past-due
amount (or follows a sentence about that one product only, as in "... 75.00 past due. Can you pay that today?").
An offer is a product ask that does not end by asking about today and is not a repeat of the previous offer right
after a customer question. Bands: 1 to 7 days late early (1 attempt), 8 to 45 late (2), Brief A rule 18.

Not checked at all: attempts on products that end with a promise, amounts and dates against the rules, identity and
third-party rules, callbacks, transfers, honesty beyond "recorded", anything heard in audio rather than the transcript.

Persona triggers (Persona Lab V06, V07, V09): whether the customer behaviour the persona exists for happened. A call
whose trigger did not happen did not test the persona's hypothesis.
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
_UNITS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth"]
ORDINALS = {w: i + 1 for i, w in enumerate(_UNITS + ["tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
                                                     "sixteenth", "seventeenth", "eighteenth", "nineteenth"])}
ORDINALS.update({"twentieth": 20, "thirtieth": 30})
ORDINALS.update({f"twenty{sep}{w}": 21 + i for i, w in enumerate(_UNITS) for sep in ("-", " ")})
ORDINALS.update({f"thirty{sep}first": 31 for sep in ("-", " ")})
WD = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
MO = r"(" + "|".join(MONTHS) + r")"
ORD = r"(" + "|".join(sorted(ORDINALS, key=len, reverse=True)) + r")"
YEAR = r"(?:,?\s+(\d{4}))?"
DATE_PATTERNS = [   # (pattern, order of the day/month/year groups)
    (re.compile(WD + r",?\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?\s+" + MO + YEAR, re.I), "dmy"),
    (re.compile(WD + r",?\s+" + MO + r"\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?" + YEAR, re.I), "mdy"),
    (re.compile(WD + r",?\s+(\d{4})-(\d{2})-(\d{2})", re.I), "ymd"),
    (re.compile(WD + r",?\s+(?:the\s+)?" + ORD + r"(?:\s+of)?\s+" + MO + YEAR, re.I), "Dmy"),
    (re.compile(WD + r",?\s+" + MO + r"\s+(?:the\s+)?" + ORD + YEAR, re.I), "mDy"),
]
RECORDED = re.compile(r"\brecorded\b", re.I)
NEGATED = re.compile(r"(\bnot\b|n't\b|\bnothing\b|\bnever\b|\bunable\b|\bcannot\b|\bfailed\b)[^.?!]*\brecorded\b", re.I)
FUTURE = re.compile(r"\b(will|would|can|could|once|after|when|until|before|going to|to be)\b[^.?!]*\brecorded\b", re.I)
PLURAL = re.compile(r"\b(promises|payments|all|both|those|them|these)\b", re.I)
SMS = re.compile(r"text message|\bsms\b", re.I)
SMS_NEG = re.compile(r"(\bnot\b|n't\b|\bno\b|\bnever\b)[^.?!]*(text message|\bsms\b)", re.I)
SMS_EXACT = "you will receive a text message confirming this promise"
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
TODAY_ASK = re.compile(r"\btoday\b(?:,?\s*(?:please|(?:mr|ms|mrs|miss|dr)\.?\s+\w+))*\s*\?$", re.I)
NEG = re.compile(r"\b(not|cannot|never|no)\b|n't\b", re.I)
NAMES = {"credit_card": r"\bcard\b", "personal_loan": r"\bpersonal\b", "car_loan": r"\bcar\b"}
WHEN = r"\b(today|tomorrow|" + "|".join(MONTHS + DAYS) + r"|\d{1,2}(st|nd|rd|th)|[a-z]+tieth|[a-z]+teenth)\b"

CLASS = {"NO_GOODBYE": "violation", "NO_THANKS": "violation", "RECORDED_EARLY": "violation", "SMS_MISSING": "violation",
         "TODAY_AGAIN": "violation", "ORDER": "violation", "ITEM_SKIPPED": "violation", "ATTEMPTS_SHORT": "violation",
         "ATTEMPTS_OVER": "violation", "WEEKDAY": "violation", "SMS_NOT_VERBATIM": "wording",
         "RECORDED_IN_GREETING": "judge risk", "SPEECH_AFTER_CLOSE": "observation"}
# The checks that apply in a call, by the condition that makes them apply.
GROUPS = {"close": ("NO_GOODBYE", "NO_THANKS", "SPEECH_AFTER_CLOSE"), "always": ("RECORDED_EARLY", "RECORDED_IN_GREETING"),
          "promise": ("SMS_MISSING", "SMS_NOT_VERBATIM"), "multi": ("TODAY_AGAIN", "ORDER"),
          "unpromised": ("ITEM_SKIPPED", "ATTEMPTS_SHORT", "ATTEMPTS_OVER"), "dates": ("WEEKDAY",)}


def bank_tool(ev: dict) -> str | None:
    """The bank tool behind a tool event: the URL's last path segment, else the function name."""
    args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
    url = str(args.get("url") or "")
    if url:
        return url.rstrip("/").rsplit("/", 1)[-1]
    return ev.get("function")


def timeline(messages: list[dict]) -> list[dict]:
    """Agent lines, customer lines and bank tool starts/results in recorded order. Writes keep their product_id."""
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
                args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
                body = args.get("body") if isinstance(args.get("body"), dict) else args
                item = (bank_tool(ev), body.get("product_id"))
                open_.setdefault(ev["function"], []).append(item)
                out.append({"t": t, "kind": "start", "tool": item[0], "product": item[1]})
            elif ev.get("event") in ("function_call_complete", "function_call_error"):
                tool, product = open_[ev["function"]].pop(0) if open_.get(ev["function"]) else (bank_tool(ev), None)
                res = ev.get("result") if isinstance(ev.get("result"), dict) else {}
                data = res.get("data") if isinstance(res.get("data"), dict) else res
                ok = ev.get("event") == "function_call_complete" and bool(data.get("ok"))
                out.append({"t": t, "kind": "result", "tool": tool, "product": product, "ok": ok})
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


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def products_of(ledger: dict) -> list[dict]:
    for c in ledger.get("calls") or []:
        if c.get("tool") == "get_account" and (c.get("result") or {}).get("ok"):
            return (c["result"].get("products") or [])
    return []


def floor(p: dict) -> float | None:
    v = p.get("minimum_payment") if p.get("type") == "credit_card" else p.get("instalment_amount")
    return round(float(v), 2) if v is not None else None


def weekday_findings(text: str, now: dt.date) -> list[str]:
    found, seen = [], set()
    for pat, order in DATE_PATTERNS:
        for m in pat.finditer(text):
            g = dict(zip(order, m.groups()[1:4]))
            try:
                day = ORDINALS[g["D"].lower()] if "D" in g else int(g["d"])
                month = MONTHS.index(g["m"].lower()) + 1 if not g["m"].isdigit() else int(g["m"])
                y = int(g["y"]) if g.get("y") else (now.year + 1 if month < now.month else now.year)
                date = dt.date(y, month, day)
            except (ValueError, KeyError):
                continue
            if DAYS[date.weekday()] != m.group(1).lower() and m.span() not in seen:
                seen.add(m.span())
                found.append(f"'{m.group(0)}' is a {DAYS[date.weekday()].capitalize()}")
    return found


def named_products(text: str, prods: list[dict]) -> list[str]:
    """Products a sentence names, by type word or by amount (a past-due match wins over a floor match)."""
    nums = numbers(text)
    by_name = [p["product_id"] for p in prods if NAMES.get(p.get("type")) and re.search(NAMES[p["type"]], text, re.I)]
    by_past = [p["product_id"] for p in prods if round(float(p["past_due"]), 2) in nums]
    return sorted(set(by_name) | set(by_past or [p["product_id"] for p in prods if floor(p) in nums]))


def trigger(variant: str | None, tl: list[dict], first_ask: dict) -> bool | None:
    """Whether the behaviour a Persona Lab persona exists for happened in this call; None for other calls."""
    hears = [e for e in tl if e["kind"] == "hear"]
    if variant == "V07":
        return any(re.search(r"start with the car loan", h["text"], re.I) for h in hears)
    if variant == "V06":
        return any(re.search(r"\btwice\b", h["text"], re.I) for h in hears)
    if variant == "V09":
        limit = first_ask.get("personal_loan")
        for i, h in enumerate(hears):
            if limit is not None and h["t"] > limit:
                break
            refusal = re.search(r"not paying|forget it|won't pay", h["text"], re.I)
            about = re.search(r"personal", h["text"], re.I) or (i and re.search(r"personal", hears[i - 1]["text"], re.I))
            if refusal and about:
                return True
        return False
    return None


def audit(case: dict, ledger: dict, messages: list[dict]) -> dict:
    """{"findings": [...], "checked": [codes that applied], "trigger": bool | None} for one call."""
    tl = timeline(messages)
    says = [e for e in tl if e["kind"] == "say"]
    prods = products_of(ledger)
    find, checked = [], set(GROUPS["always"])

    def add(code, rule, t, text):
        find.append({"code": code, "class": CLASS[code], "rule": rule, "t": round(t, 2), "text": text[:220]})

    # Closing (A47).
    close_t = next((e["t"] for e in tl if e["kind"] == "start" and e["tool"] == "close_call"), None)
    if close_t is not None:
        checked.update(GROUPS["close"])
        before = [e for e in says if e["t"] < close_t]
        for e in says:
            if e["t"] >= close_t:
                add("SPEECH_AFTER_CLOSE", "(A47)", e["t"], e["text"])
        if not any(re.search(r"\b(good ?bye|bye)\b", e["text"], re.I) for e in before):
            add("NO_GOODBYE", "A47", close_t, "no goodbye before close_call")
        if not any(re.search(r"\bthank", e["text"], re.I) for e in before):
            add("NO_THANKS", "A47", close_t, "no thanks before close_call")

    # "recorded" (A1, A37).
    ok_at, started = {}, set()
    for e in tl:
        if e["kind"] == "start" and e["tool"] == "create_promise":
            started.add(e["product"])
        if e["kind"] == "result" and e["ok"] and e["tool"] in ("create_promise", "add_note"):
            ok_at.setdefault(e["product"], e["t"])
    promise_ok = sorted(e["t"] for e in tl if e["kind"] == "result" and e["tool"] == "create_promise" and e["ok"])
    first_ok = promise_ok[0] if promise_ok else None
    for i, e in enumerate(says):
        for s in sentences(e["text"]):
            if not RECORDED.search(s) or NEGATED.search(s) or FUTURE.search(s):
                continue
            about_promise = re.search(r"promise|payment|\bpay\b", s, re.I)
            if i == 0 and not about_promise:
                add("RECORDED_IN_GREETING", "A1", e["t"], s)
                continue
            names = named_products(s, prods)
            if names:
                early = any(ok_at.get(pid) is None or ok_at[pid] > e["t"] for pid in names)
            elif PLURAL.search(s) and started:
                early = any(ok_at.get(pid) is None or ok_at[pid] > e["t"] for pid in started)
            else:
                early = (first_ok is None or e["t"] < first_ok) and (first_ok is not None or bool(about_promise))
            if early:
                add("RECORDED_EARLY", "A37", e["t"], s)

    # Text-message sentence (A38).
    if first_ok is not None:
        checked.update(GROUPS["promise"])
        sms = [(e["t"], s) for e in says if e["t"] >= first_ok for s in sentences(e["text"]) if SMS.search(s) and not SMS_NEG.search(s)]
        if not sms:
            add("SMS_MISSING", "A38", first_ok, "no text-message sentence after the recorded promise")
        elif not any(SMS_EXACT in norm(s) for _, s in sms):
            add("SMS_NOT_VERBATIM", "A38", sms[0][0], sms[0][1])

    # Products (B4, A30, A31, B5).
    acct_t = next((e["t"] for e in tl if e["kind"] == "result" and e["tool"] == "get_account" and e["ok"]), None)
    first_ask = {}
    if prods and acct_t is not None:
        past = {p["product_id"]: round(float(p["past_due"]), 2) for p in prods}
        asks = {p["product_id"]: [] for p in prods}      # every question about one product, today asks included
        offers = {p["product_id"]: [] for p in prods}    # the same without today asks and clarification repeats
        last_hear, today_qs = "", []
        for e in tl:
            if e["kind"] == "hear":
                last_hear = e["text"]
            if e["kind"] != "say" or e["t"] < acct_t or (close_t is not None and e["t"] >= close_t):
                continue

            def amount_named(nums):
                by_past = [p["product_id"] for p in prods if past[p["product_id"]] in nums]
                return by_past or [p["product_id"] for p in prods if floor(p) in nums]
            whole = amount_named(numbers(e["text"]))
            for s in sentences(e["text"]):
                if not s.endswith("?"):
                    continue
                is_today = bool(TODAY_ASK.search(s)) and bool(re.search(r"\bpay(ing|ment)?\b", s, re.I))
                if is_today:
                    today_qs.append((e["t"], s))
                nums = numbers(s)
                hit = amount_named(nums)
                other = [pid for pid in past if past[pid] in nums and pid not in hit]
                if not hit and not nums and len(whole) == 1:
                    hit = whole                          # "The car loan has 75.00 past due. Can you pay that today?"
                if len(hit) == 1 and not other:
                    pid = hit[0]
                    asks[pid].append((e["t"], s))
                    repeat = offers[pid] and numbers(offers[pid][-1][1]) == nums and last_hear.rstrip().endswith("?")
                    if not TODAY_ASK.search(s) and not repeat:
                        offers[pid].append((e["t"], s))
        first_ask = {p.get("type"): asks[p["product_id"]][0][0] for p in prods if asks[p["product_id"]]}
        promised = {p["product_id"] for p in ledger.get("promises") or []}
        refused_notes = {n.get("product_id") for n in ledger.get("notes") or [] if n.get("reason") == "refused"}
        single_refused = len(prods) == 1 and (ledger.get("outcome"), ledger.get("reason")) == ("no_promise", "refused")
        for p in prods:
            pid = p["product_id"]
            if pid in promised or not (pid in refused_notes or single_refused):
                continue
            checked.update(GROUPS["unpromised"])
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
            checked.update(GROUPS["multi"])
            for t, s in today_qs[1:]:
                add("TODAY_AGAIN", "B4", t, s)
            # Out of order: a later product is asked before an earlier one is asked, or an earlier product gets a
            # promise without its own ask after a later one was asked first. Skipped while the customer had named one
            # date for everything (Brief B rule 6) or had settled the earlier product with a day; negated sentences
            # ("I can't pay the card tomorrow") settle nothing.
            hears = [e for e in tl if e["kind"] == "hear"]
            one_date = re.compile(r"\b(both|all|everything)\b[^.?!]*" + WHEN, re.I)

            def said(pattern, t):                        # in one clause without a negation ("..., but I'm not paying X")
                clauses = [c for h in hears if h["t"] <= t for s in sentences(h["text"]) for c in re.split(r",?\s+but\s+|;\s*", s)]
                return any(re.search(pattern, c, re.I) and not NEG.search(c) for c in clauses)

            def settled(p, t):
                return bool(NAMES.get(p.get("type"))) and said(NAMES[p["type"]] + r"[^.?!]*" + WHEN, t)

            ids = [p["product_id"] for p in prods]
            for pj in sorted((x for x in ids if asks[x]), key=lambda x: asks[x][0][0]):
                j, tj = ids.index(pj), asks[pj][0][0]
                if said(one_date.pattern, tj):
                    continue
                late = [pi for pi in ids[:j] if ((asks[pi] and asks[pi][0][0] > tj) or (not asks[pi] and pi in promised))
                        and not settled(prods[ids.index(pi)], tj)]
                if late:
                    add("ORDER", "B4", tj, f"{prods[j].get('type')} asked before {', '.join(prods[ids.index(x)].get('type') for x in late)}: {asks[pj][0][1]}")
                    break

    # Weekdays (Brief A section 7).
    now = dt.date.fromisoformat(str(((case.get("variables") or {}).get("now")) or "2026-10-14")[:10])
    for e in says:
        for f in weekday_findings(e["text"], now):
            add("WEEKDAY", "A section 7", e["t"], f)
        if any(pat.search(e["text"]) for pat, _ in DATE_PATTERNS):
            checked.update(GROUPS["dates"])

    variant = str(case.get("style") or "").removeprefix("pl-") or None
    return {"findings": find, "checked": sorted(checked), "trigger": trigger(variant, tl, first_ask), "variant": variant}


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
            judge = r.get("judge") or {}
            out.append({"label": label, "id": f"{r.get('variant')}-r{rep}", "call_id": (r.get("kit_row") or {}).get("call_id"),
                        "verdict": judge.get("outcome"), "verdict_source": "kit" if judge.get("note") else "judge",
                        "case": r["case"], "ledger": r.get("ledger") or {}, "messages": r["messages"]})
    return out


def fetch_records(repo: Path, results: list[Path], save: Path | None = None) -> list[dict]:
    """run_cases --out files -> records, reading each call and ledger from the API (read-only). With `save`, each
    record is also written as SAVE/<results file stem>/raw/<case>-r<rep>.json, readable as a PATH later."""
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
                rec = {"label": f.stem, "id": f"{row['id']}-r{rep}", "call_id": row.get("call_id"),
                       "verdict": "pass" if row.get("pass") else "fail", "verdict_source": "kit", "case": cases.get(row["id"], {}),
                       "ledger": http("/v1/practice/ledger/" + row["customer_id"]), "messages": msgs}
                out.append(rec)
                if save:
                    d = save / f.stem / "raw"
                    d.mkdir(parents=True, exist_ok=True)
                    (d / f"{rec['id']}.json").write_text(json.dumps(
                        {"variant": row["id"], "rep": rep, "case": rec["case"], "ledger": rec["ledger"], "messages": msgs,
                         "kit_row": row, "judge": {"outcome": rec["verdict"], "note": "kit PASS/FAIL: ledger and judge"}}, indent=1))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--fetch", type=Path, metavar="REPO", help="treat PATHS as run_cases --out files and read calls from the API")
    p.add_argument("--json", type=Path, help="write all findings to this file")
    p.add_argument("--save", type=Path, metavar="DIR", help="with --fetch: also store each fetched record under DIR")
    p.add_argument("--review", type=Path, help='JSON {"<call_id>|<code>": "confirmed" | "false_positive" | "unclear"}')
    a = p.parse_args(argv)
    review = json.loads(a.review.read_text()) if a.review else {}
    records = fetch_records(a.fetch, a.paths, a.save) if a.fetch else load_records(a.paths)
    rows = []
    for r in records:
        res = audit(r["case"], r["ledger"], r["messages"])
        for f in res["findings"]:
            f["status"] = review.get(f"{r['call_id']}|{f['code']}", "unreviewed")
        rows.append({k: r[k] for k in ("label", "id", "call_id", "verdict", "verdict_source")} | res)
    for x in rows:
        if x["findings"]:
            print(f"{x['label']} {x['id']} {x['verdict_source']}={x['verdict']} call={str(x['call_id'])[:8]}")
            for f in x["findings"]:
                print(f"    {f['code']:<20} {f['class']:<11} {f['status']:<14} t={f['t']:<7} {f['text']}")
    labels = sorted({x["label"] for x in rows})
    n = {lab: sum(1 for x in rows if x["label"] == lab) for lab in labels}
    print("\nCalls with a finding / calls where the check applied, per label (calls in brackets):")
    print("| code | class | " + " | ".join(f"{lab} ({n[lab]})" for lab in labels) + " |")
    print("|---|---|" + "---|" * len(labels))
    for code in CLASS:
        cells = []
        for lab in labels:
            mine = [x for x in rows if x["label"] == lab]
            hit = sum(1 for x in mine if any(f["code"] == code for f in x["findings"]))
            cells.append(f"{hit}/{sum(1 for x in mine if code in x['checked'])}")
        print(f"| {code} | {CLASS[code]} | " + " | ".join(cells) + " |")
    trig = [x for x in rows if x["trigger"] is not None]
    if trig:
        print("\nPersona triggers (calls where the persona's behaviour happened / calls of that persona):")
        for lab in labels:
            for v in sorted({x["variant"] for x in trig if x["label"] == lab}):
                mine = [x for x in trig if x["label"] == lab and x["variant"] == v]
                print(f"  {lab} {v}: {sum(1 for x in mine if x['trigger'])}/{len(mine)}")
    viol = lambda x, statuses: any(f["class"] == "violation" and f["status"] in statuses for f in x["findings"])
    passed = [x for x in rows if x["verdict"] == "pass"]
    print(f"\n{len(rows)} calls. PASS calls with a violation-class finding: {sum(viol(x, ('unreviewed', 'unclear', 'confirmed')) for x in passed)}"
          f" (confirmed {sum(viol(x, ('confirmed',)) for x in passed)}, unreviewed or unclear the rest). "
          "A finding is a claim to read; no finding is not compliance.")
    if a.json:
        a.json.write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
