"""Blind-generalization scenarios: policy and tool-contract mutations of the public briefs.

Each scenario edits the public brief texts with anchored replacements (every anchor must occur, and occur exactly
once unless the edit says `all`), optionally mutates the OpenAPI file, and renders two forms:

- clean: the edits applied inline to the brief(s)
- raw:   one bank-material document (e-mail, policy extract with page noise, an older superseded memo and a newer
         memo); edits marked `via: "memo"` stay old in the extract and are announced in the newer memo

The Builder gets only `inputs/`. `key.json` (probes, derived deadlines, contract changes) is for the grader.
Nothing here predicts an official score: the bank mock only knows the public contract and the public customers.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from . import oracle
from .common import GEN, KIT, ROOT, sha256, write_json

NOW = "2026-10-14T11:00"
EXTRACT_DATE = "2 March 2026"
OLD_MEMO_DATE = "3 February 2026"
NEW_MEMO_DATE = "9 October 2026"

A_HOLIDAYS = "Freya Bank holidays: 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01."
A_EARLY = "| 1 to 7 | early | the 12th business day after today | 1 |"
A_LATE = "| 8 to 45 | late | the 7th business day after today | 2 |"
TOOLS = ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call")
A_FICTION = "Freya Bank is fictional. Every customer, debt and payment here is synthetic."


def E(doc, anchor, new, via="inline", memo=None, all=False):
    return {"doc": doc, "anchor": anchor, "new": new, "via": via, "memo": memo, "all": all}


def found(pid, any_, why, strong=False):
    return {"id": pid, "kind": "found", "any": any_, "strong": strong, "why": why}


def stale(pid, any_, why, strong=True):
    return {"id": pid, "kind": "stale", "any": any_, "strong": strong, "why": why}


SCENARIOS = [
    {
        "id": "g1-calendar", "docs": ["a"],
        "family": "deadlines and holidays",
        "edits": [
            E("a", A_HOLIDAYS, "Freya Bank holidays: 2026-10-19, 2026-10-23, 2026-11-11, 2026-12-25, 2027-01-01.", via="memo",
              memo="The Freya Bank holiday list for the rest of 2026 is now: 2026-10-19, 2026-10-23, 2026-11-11, 2026-12-25 and 2027-01-01. 26 October is a normal business day."),
            E("a", A_EARLY, "| 1 to 7 | early | the 9th business day after today | 1 |"),
            E("a", A_LATE, "| 8 to 45 | late | the 5th business day after today | 2 |"),
        ],
        "policy": {"holidays": ["2026-10-19", "2026-10-23", "2026-11-11", "2026-12-25", "2027-01-01"], "deadline_business_days": {"early": 9, "late": 5}},
        "probes": [
            found("holiday-new", ["2026-10-19", "19 october", "october 19"], "a new holiday is known"),
            stale("holiday-removed", ["2026-10-26"], "26 October is no longer a holiday"),
            stale("early-deadline-old", ["12th business day", "twelfth business day", "12 business days"], "early deadline was 12, now 9", strong=False),
            found("early-deadline-new", ["9th business day", "ninth business day", "9 business days"], "early deadline 9"),
            found("late-deadline-new", ["5th business day", "fifth business day", "5 business days"], "late deadline 5"),
        ],
    },
    {
        "id": "g2-identity", "docs": ["a"],
        "family": "authentication rules + verify_identity enum",
        "edits": [
            E("a", "first the date of birth, then the last four digits of the phone number on file. Call `verify_identity` with the answer. Send a date of birth as `YYYY-MM-DD`, whatever way the customer said it. The service rejects anything it cannot read as a date. Read a date given only as numbers as day, then month, then year.",
              "first the postcode of the registered address, then the year of birth. Call `verify_identity` with the answer. Send a postcode in capitals without spaces. Send a year of birth as four digits.", via="memo",
              memo="Security questions change today: ask first for the postcode of the registered address, then for the year of birth. The date of birth and the phone digits are no longer asked. Postcodes go to the service in capitals without spaces; years as four digits."),
            E("a", "13. If the customer gives day and month the other way round, `verify_identity` returns `hint: \"day_month_swapped\"`. Ask them to say the month as a word. That retry does not count as a wrong answer.",
              "13. A postcode given with spaces or in lower case is normalized before the call. That is not a wrong answer.", via="memo",
              memo="The day/month-swap retry no longer exists. A postcode said with spaces or in lower case is normalized before the call and is not a wrong answer."),
            E("a", "Three wrong answers in total end the check", "Two wrong answers in total end the check", via="memo",
              memo="Two wrong answers in total now end the security check, whichever question they were on."),
            E("a", "14. After three wrong answers", "14. After two wrong answers", via="memo"),
        ],
        "openapi": [
            {"op": "set_enum", "path": "/verify_identity", "field": "field", "values": ["postcode", "birth_year"]},
            {"op": "set_description", "path": "/verify_identity", "field": "answer", "text": "For postcode: capitals, no spaces. For birth_year: four digits."},
        ],
        "policy": {"identity_fields": ["postcode", "birth_year"], "wrong_answer_limit": 2},
        "probes": [
            found("auth-postcode", ["postcode"], "the new first question"),
            found("auth-year", ["birth_year", "year of birth"], "the new second question"),
            stale("auth-dob-field", ["date_of_birth"], "date of birth is no longer a verify_identity field"),
            stale("auth-phone-field", ["phone_last4"], "phone digits are no longer a verify_identity field"),
            stale("auth-old-wording", ["date of birth", "last four digits"], "old questions mentioned", strong=False),
            stale("auth-swap-hint", ["day_month_swapped"], "the swap hint is gone", strong=False),
        ],
    },
    {
        "id": "g3-limits", "docs": ["a"],
        "family": "per-product floors, attempts and amount cap",
        "edits": [
            E("a", "25. The **floor** is `minimum_payment` for a credit card and `instalment_amount` for a personal loan or a car loan.",
              "25. The **floor** is `minimum_payment` for a credit card, `instalment_amount` for a personal loan, and half of `past_due`, rounded down to whole euros, for a car loan.", via="memo",
              memo="For car loans the floor is now half of the past-due amount, rounded down to whole euros. Credit cards and personal loans keep their floors."),
            E("a", "If the customer does not accept the floor, treat it as a flat refusal (rule 30).",
              "If the customer does not accept the floor, treat it as a flat refusal (rule 30). No single promise may be above 2000.00 for one product; if the past-due amount is higher, ask for 2000.00 and say the rest stays overdue."),
            E("a", A_EARLY, "| 1 to 7 | early | the 12th business day after today | 2 |"),
            E("a", A_LATE, "| 8 to 45 | late | the 7th business day after today | 3 |"),
        ],
        "policy": {"floors": {"credit_card": "minimum_payment", "personal_loan": "instalment_amount", "car_loan": "half_past_due"}, "attempts": {"early": 2, "late": 3}, "max_promise_amount": 2000.0},
        "probes": [
            found("floor-car-half", ["half of", "half the", "/ 2", "* 0.5", "/2"], "car-loan floor is half of past due"),
            found("cap-2000", ["2000", "2,000"], "per-promise cap"),
        ],
    },
    {
        "id": "g4-outcomes", "docs": ["a"],
        "family": "outcome table + close_call enums",
        "edits": [
            E("a", "| `not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear` | rules 6, 7, 8, 9, 3 |",
              "| `not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear`, `language` | rules 6, 7, 8, 8a, 9, 3 |"),
            E("a", "8. If the person says the number does not belong to the customer, close as `not_reached` / `wrong_number`.",
              "8. If the person says the number does not belong to the customer, close as `not_reached` / `wrong_number`.\n8a. If the person on the line cannot speak English, do not continue in another language. Close as `not_reached` / `language`."),
            E("a", "not_reached", "no_contact", all=True, via="memo",
              memo="The close code `not_reached` is renamed `no_contact`, and `not_verified` is renamed `identity_failed`. The reasons stay the same. A new reason `language` closes a call where the person cannot speak English."),
            E("a", "not_verified", "identity_failed", all=True, via="memo"),
        ],
        "openapi": [
            {"op": "set_enum", "path": "/close_call", "field": "outcome", "values": ["promise", "paid", "transferred", "no_promise", "identity_failed", "no_contact"]},
            {"op": "set_enum", "path": "/close_call", "field": "reason", "values": ["restructuring", "human", "support", "refused", "hardship", "dispute", "service_error", "failed", "declined", "callback", "no_callback", "wrong_number", "deceased", "unclear", "language"]},
        ],
        "policy": {"outcomes_renamed": {"not_reached": "no_contact", "not_verified": "identity_failed"}, "reason_added": "language"},
        "probes": [
            found("outcome-no-contact", ["no_contact"], "renamed outcome"),
            found("outcome-identity-failed", ["identity_failed"], "renamed outcome"),
            found("reason-language", ["language"], "new reason"),
            stale("outcome-not-reached", ["not_reached"], "removed outcome value"),
            stale("outcome-not-verified", ["not_verified"], "removed outcome value"),
        ],
    },
    {
        "id": "g5-memo", "docs": ["a"],
        "family": "memo precedence: newer memo wins, older memo loses",
        "old_memo": "Callbacks may be booked until 20:00 on weekdays. Car-loan customers late 8 days or more get the 10th business day as their deadline.",
        "edits": [
            E("a", "from 10:00 to 19:00, both included", "from 09:00 to 17:00, both included", via="memo",
              memo="Callbacks are now booked only from 09:00 to 17:00, both included, today or the next business day."),
            E("a", A_LATE, "| 8 to 45 | late | the 6th business day after today | 2 |", via="memo",
              memo="The deadline for customers 8 to 45 days late is now the 6th business day after today. The early band is unchanged."),
        ],
        "policy": {"callback_window": ["09:00", "17:00"], "deadline_business_days": {"early": 12, "late": 6}},
        "probes": [
            found("callback-new-end", ["17:00", "5 pm", "5pm"], "new callback end"),
            stale("callback-old-end", ["19:00", "7 pm", "7pm"], "the extract's end time is superseded"),
            stale("old-memo-decoy", ["20:00", "8 pm", "10th business day", "tenth business day"], "the older memo is superseded by the extract"),
            found("late-deadline-new", ["6th business day", "sixth business day", "6 business days"], "new late deadline"),
            stale("late-deadline-old", ["7th business day", "seventh business day", "7 business days"], "old late deadline", strong=False),
        ],
    },
    {
        "id": "g6-contract", "docs": ["a"],
        "family": "OpenAPI field renames, new required field, enum values",
        "edits": [E("a", A_FICTION, A_FICTION + " The tool API was revised in October 2026; its file is the only source for field names.")],
        "openapi": [
            {"op": "rename_field", "path": "/create_promise", "old": "date", "new": "promise_date"},
            {"op": "rename_field", "path": "/create_promise", "old": "amount", "new": "amount_eur"},
            {"op": "add_field", "path": "/create_promise", "field": "channel", "schema": {"type": "string", "enum": ["voice"]}, "required": True},
            {"op": "rename_field", "path": "/schedule_callback", "old": "time", "new": "slot_time"},
            {"op": "set_enum", "path": "/transfer_to_agent", "field": "queue", "values": ["restructuring", "general", "customer_support"]},
            {"op": "add_field", "path": "/close_call", "field": "channel", "schema": {"type": "string", "enum": ["voice"]}, "required": True},
        ],
        "policy": {},
        "probes": [
            found("queue-new", ["customer_support"], "renamed queue value"),
        ],
    },
    {
        "id": "g7-multi", "docs": ["a", "b"],
        "family": "multi-product: per-type deadline cap, note enum rename",
        "edits": [
            E("a", A_HOLIDAYS, "Freya Bank holidays: 2026-10-21, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01.", via="memo",
              memo="21 October 2026 is a bank holiday. 26 October is a normal business day."),
            E("b", "Two products of the same customer can have different deadlines.",
              "Two products of the same customer can have different deadlines. A car loan's deadline is never later than the 5th business day after today, whatever its band.", via="memo",
              memo="Car loans: the deadline is never later than the 5th business day after today, whatever the band."),
            E("b", "reason: `refused`, `hardship`, `dispute`, `paid` or `service_error`", "reason: `refused`, `hardship`, `dispute`, `already_paid` or `service_error`"),
            E("b", "if every product is noted `paid`, close as `paid`", "if every product is noted `already_paid`, close as `paid`"),
            E("b", "whose note is not `paid`", "whose note is not `already_paid`"),
        ],
        "openapi": [
            {"op": "set_enum", "path": "/add_note", "field": "reason", "values": ["refused", "hardship", "dispute", "already_paid", "service_error"]},
        ],
        "policy": {"holidays": ["2026-10-21", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"], "deadline_cap_by_type": {"car_loan": 5}},
        "probes": [
            found("note-already-paid", ["already_paid"], "renamed note reason"),
            found("car-cap", ["5th business day", "fifth business day", "5 business days"], "car-loan cap"),
            found("holiday-21", ["2026-10-21", "21 october", "october 21"], "new holiday"),
            stale("holiday-removed", ["2026-10-26"], "26 October is no longer a holiday"),
        ],
    },
]


# ---------------------------------------------------------------- brief edits

def apply_edits(texts: dict[str, str], edits: list[dict], only_inline: bool = False) -> dict[str, str]:
    out = dict(texts)
    for e in edits:
        if only_inline and e["via"] == "memo":
            continue
        t = out[e["doc"]]
        n = t.count(e["anchor"])
        if n == 0 or (n > 1 and not e["all"]):
            raise ValueError(f"anchor occurs {n} times in brief {e['doc']}: {e['anchor'][:70]!r}")
        out[e["doc"]] = t.replace(e["anchor"], e["new"])
    return out


def public_briefs() -> dict[str, str]:
    return {k: (KIT / "briefs" / f"brief-{k}.md").read_text() for k in ("a", "b")}


def _table_to_lines(lines: list[str]) -> list[str]:
    out, header = [], None
    for ln in lines:
        cells = [c.strip().strip("`") for c in ln.strip().strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if header is None:
            header = cells
            continue
        out.append("  * " + "; ".join(f"{h}: {c}" for h, c in zip(header, cells)))
    return out


def to_extract(text: str, title: str, page_every: int = 14) -> str:
    """A brief as a pasted policy extract: other headings, lettered clauses, tables flattened, page noise."""
    src = text.splitlines()[1:]
    lines, table, page = [], [], 1
    for ln in src + [""]:
        if ln.startswith("|"):
            table.append(ln)
            continue
        if table:
            lines += _table_to_lines(table)
            table = []
        m = re.match(r"## (\d+)\. (.*)", ln)
        if m:
            lines.append(f"SECTION {m.group(1)}  {m.group(2).upper()}")
            continue
        if ln.startswith("## "):
            lines.append(ln[3:].upper())
            continue
        if ln.startswith("Freya Bank is fictional."):
            continue
        lines.append(re.sub(r"^(\d+[a-z]?)\. ", r"(\1) ", ln))
    out = [f"{title} (version of {EXTRACT_DATE})", ""]
    for i, ln in enumerate(lines, 1):
        out.append(ln.replace("**", ""))
        if i % page_every == 0:
            page += 1
            out += ["", f"--- CP-4 / internal / page {page} ---", ""]
    return "\n".join(out).strip() + "\n"


def render_raw(scn: dict, texts: dict[str, str]) -> str:
    inline = apply_edits(texts, scn["edits"], only_inline=True)
    memo = [e["memo"] for e in scn["edits"] if e["via"] == "memo" and e["memo"]]
    cut = inline["a"].index("## 12. Closing")
    policy_a, codes_a = inline["a"][:cut], inline["a"][cut:]     # the close codes travel as their own document
    old = scn.get("old_memo") or "Agents should keep calls short and avoid technical words."
    parts = [
        "# Freya Bank: material for the collections assistant",
        "",
        "Freya Bank is fictional. Every customer, debt and payment here is synthetic.",
        "",
        "From: Collections Operations, Freya Bank",
        "To: Digital assistant team",
        "Subject: what the assistant needs",
        "",
        "Hello, below is everything we have: the policy extract, two operations memos and the close code list. "
        "Memos change the extract from their date on; anything dated before the extract is replaced by it. "
        "The tool API file you already have is the reference for tool fields.",
        "",
        "Thanks, Collections Operations",
        "",
        "---",
        "",
        f"Operations memo OM-3, {OLD_MEMO_DATE}",
        "",
        old,
        "",
        "---",
        "",
        to_extract(policy_a, "Contact Policy CP-4, extract for outbound collections calls"),
    ]
    if "b" in scn["docs"]:
        parts += ["---", "", to_extract(inline["b"], "Contact Policy CP-4, annex M: customers late on several products")]
    parts += ["---", "", to_extract("# close codes\n" + codes_a, "Close code list CC-2")]
    parts += ["---", "", f"Operations memo OM-17, {NEW_MEMO_DATE}", "", "With immediate effect:", ""]
    parts += [f"- {m}" for m in memo] or ["- No changes."]
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------- OpenAPI mutations

def _schema(spec: dict, path: str) -> dict:
    return spec["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]


def mutate_openapi(spec: dict, ops: list[dict]) -> tuple[dict, dict]:
    """Returns the mutated spec and what became stale: {tool: {"fields": [...], "enum": {field: [values]}}}."""
    spec = copy.deepcopy(spec)
    stale_: dict = {}
    for op in ops:
        tool = op["path"].strip("/")
        s = _schema(spec, op["path"])
        props, req = s["properties"], s.setdefault("required", [])
        rec = stale_.setdefault(tool, {"fields": [], "enum": {}})
        if op["op"] == "rename_field":
            props[op["new"]] = props.pop(op["old"])
            if op["old"] in req:
                req[req.index(op["old"])] = op["new"]
            rec["fields"].append(op["old"])
        elif op["op"] == "add_field":
            props[op["field"]] = op["schema"]
            if op.get("required"):
                req.append(op["field"])
        elif op["op"] == "set_enum":
            removed = [v for v in props[op["field"]].get("enum", []) if v not in op["values"]]
            props[op["field"]]["enum"] = list(op["values"])
            if removed:
                rec["enum"][op["field"]] = removed
        elif op["op"] == "set_description":
            props[op["field"]]["description"] = op["text"]
        else:
            raise ValueError(op["op"])
    return spec, {k: v for k, v in stale_.items() if v["fields"] or v["enum"]}


def public_openapi() -> dict:
    return json.loads((KIT / "tools" / "openapi.json").read_text())


# ---------------------------------------------------------------- policy key

def policy_for(scn: dict) -> oracle.Policy:
    p, kw = scn.get("policy", {}), {}
    base = oracle.BRIEF_A
    if "holidays" in p:
        kw["holidays"] = tuple(map(oracle.d, p["holidays"]))
    if "deadline_business_days" in p or "attempts" in p:
        dl, at = p.get("deadline_business_days", {}), p.get("attempts", {})
        kw["bands"] = tuple(oracle.Band(b.name, b.min_days, b.max_days, dl.get(b.name, b.deadline_business_days), at.get(b.name, b.attempts)) for b in base.bands)
    for k in ("floors", "deadline_cap_by_type", "max_promise_amount", "wrong_answer_limit"):
        if k in p:
            kw[k] = p[k]
    if "identity_fields" in p:
        kw["identity_fields"] = tuple(p["identity_fields"])
    if "callback_window" in p:
        kw["callback_window"] = tuple(p["callback_window"])
    return base.with_(**kw)


def _rel(p: Path) -> str:
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def build(out: Path = GEN / "blind") -> list[dict]:
    texts, api = public_briefs(), public_openapi()
    index = []
    for scn in SCENARIOS:
        clean = apply_edits(texts, scn["edits"])
        spec, stale_api = mutate_openapi(api, scn.get("openapi", []))
        forms = {"clean": {f"pl-{scn['id']}-clean-{k}.md": clean[k] for k in scn["docs"]},
                 "raw": {f"pl-{scn['id']}-raw.md": render_raw(scn, texts)}}
        pol = policy_for(scn)
        for form, files in forms.items():
            d = out / f"{scn['id']}-{form}"
            for name, body in files.items():
                (d / "inputs").mkdir(parents=True, exist_ok=True)
                (d / "inputs" / name).write_text(body)
            write_json(d / "inputs" / "openapi.json", spec)
            briefs = " ".join(f"{_rel(d)}/inputs/{n}" for n in files)
            key = {
                "scenario": scn["id"], "form": form, "family": scn["family"],
                "scoring": "offline contract validation and text evidence only; no ledger score, no official prediction",
                "inputs": {n: sha256(b.encode()) for n, b in files.items()} | {"openapi.json": sha256(spec)},
                "openapi_ops": scn.get("openapi", []), "stale_api": stale_api,
                "policy": scn.get("policy", {}), "derived_deadlines_at_now": {"now": NOW, **oracle.deadlines_at(pol, NOW)},
                "probes": scn["probes"],
                "required_tools": [t for t in TOOLS if t != "add_note" or "b" in scn["docs"]],
                "edits": [{"doc": e["doc"], "via": e["via"] if form == "raw" else "inline", "new": e["new"][:160]} for e in scn["edits"]],
                "build": f".venv/bin/python -m builder.kitrun {briefs} --tools {_rel(d)}/inputs/openapi.json --label pl-{scn['id']}-{form}",
            }
            write_json(d / "key.json", key)
            index.append({"dir": d.name, "scenario": scn["id"], "form": form, "family": scn["family"], "build": key["build"]})
    write_json(out / "index.json", index)
    return index
