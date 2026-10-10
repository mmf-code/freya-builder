"""Generate the Freya Bank collections workflow for Brief A or Brief B.

Usage: python3 builder/build_workflow.py A out/brief-a.workflow.json
       python3 builder/build_workflow.py B out/brief-b.workflow.json
"""
import json
import sys

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]

# ---------------------------------------------------------------- code snippets
# No double braces anywhere in these snippets.

SETUP_CODE = r'''
import datetime, json
HOL = set(HOLIDAYS_JSON)
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def fmt(d):
    return d.isoformat() + " (" + d.strftime("%A") + " " + str(d.day) + " " + d.strftime("%B") + ")"
try:
    try:
        nowdt = datetime.datetime.fromisoformat(str(vars.get("now") or "")[:16])
    except Exception:
        nowdt = datetime.datetime.now()
    today = nowdt.date()
    def nth_bd(n):
        d = today
        c = 0
        while c < n:
            d = d + datetime.timedelta(days=1)
            if isbd(d):
                c += 1
        return d
    def next_bd(d):
        d = d + datetime.timedelta(days=1)
        while not isbd(d):
            d = d + datetime.timedelta(days=1)
        return d
    monday = today - datetime.timedelta(days=today.weekday())
    def last_bd_week(mon):
        for i in range(4, -1, -1):
            d = mon + datetime.timedelta(days=i)
            if isbd(d):
                return d
        return None
    lbw = last_bd_week(monday)
    if lbw is None or lbw <= today:
        lbw = last_bd_week(monday + datetime.timedelta(days=7))
    de = nth_bd(12)
    dl = nth_bd(7)
    nbd = next_bd(today)
    vars["today_iso"] = today.isoformat()
    vars["today_text"] = fmt(today)
    vars["now_time"] = nowdt.strftime("%H:%M")
    vars["deadline_early"] = de.isoformat()
    vars["deadline_late"] = dl.isoformat()
    vars["attempt1_date"] = lbw.isoformat()
    vars["attempt1_text"] = fmt(lbw)
    vars["next_bd_iso"] = nbd.isoformat()
    lines = []
    for i in range(0, 50):
        d = today + datetime.timedelta(days=i)
        w = (d - monday).days // 7
        wk = ["this week", "next week", "the week after next"][w] if w < 3 else ""
        if d.isoformat() in HOL:
            st = "BANK HOLIDAY, not a business day"
        elif d.weekday() >= 5:
            st = "weekend, not a business day"
        else:
            st = "business day"
        tag = " TODAY" if i == 0 else ""
        lines.append("- " + fmt(d) + tag + ": " + st + (", " + wk if wk else ""))
    vars["calendar"] = "\n".join(lines)
    cb = []
    if nowdt.hour < 19:
        start = max(nowdt.strftime("%H:%M"), "10:00")
        cb.append("today " + fmt(today) + ": a time later than " + nowdt.strftime("%H:%M") + " and from " + start + " to 19:00")
    cb.append("the next business day " + fmt(nbd) + ": from 10:00 to 19:00, both included")
    vars["callback_window"] = "; or ".join(cb)
    vars["setup_state"] = "ready"
except Exception as e:
    vars["setup_state"] = "error"
    vars["calendar"] = "unavailable"
    vars["today_text"] = str(vars.get("now"))
    vars["callback_window"] = "today or the next business day, 10:00 to 19:00"
'''.replace("HOLIDAYS_JSON", json.dumps(HOLIDAYS))

# Shared: turn a product list into facts. Used in the get_account post-hook and in the backup code node.
FACTS_FN = r'''
import json, datetime
def money(x):
    try:
        return "%.2f" % float(x)
    except Exception:
        return str(x)
def build_facts(products, v, multi):
    de = str(v.get("deadline_early") or "")
    dl = str(v.get("deadline_late") or "")
    def dtext(s):
        try:
            d = datetime.date.fromisoformat(s)
            return s + " (" + d.strftime("%A") + " " + str(d.day) + " " + d.strftime("%B") + ")"
        except Exception:
            return s
    pf = []
    lines = []
    sent = []
    for i, p in enumerate(products):
        if not isinstance(p, dict):
            continue
        t = str(p.get("type") or "")
        if t == "credit_card":
            name = "credit card ending " + str(p.get("card_last4") or "")
            floor = p.get("minimum_payment")
            fname = "minimum payment"
        elif t == "personal_loan":
            name = "personal loan"
            floor = p.get("instalment_amount")
            fname = "instalment amount"
        elif t == "car_loan":
            name = "car loan"
            floor = p.get("instalment_amount")
            fname = "instalment amount"
        else:
            name = t.replace("_", " ")
            floor = p.get("minimum_payment") or p.get("instalment_amount")
            fname = "floor"
        try:
            dlate = int(p.get("days_late") or 0)
        except Exception:
            dlate = 0
        early = dlate <= 7
        deadline = de if early else dl
        att = 1 if early else 2
        pid = str(p.get("product_id") or ("p" + str(i + 1)))
        pf.append(dict(product_id=pid, name=name, past_due=p.get("past_due"), floor=floor, deadline=deadline, attempts=att, days_late=dlate))
        lines.append("- product_id " + pid + ": " + name + ". Full past-due amount " + money(p.get("past_due")) + ". " + str(dlate) + " days late, " + ("early" if early else "late") + " band. Floor (" + fname + ") " + money(floor) + ". Deadline (latest promise date) " + dtext(deadline) + ". Persuasion attempts allowed: " + str(att) + ". After a flat refusal, attempt 1 = " + money(p.get("past_due")) + " on " + dtext(str(v.get("attempt1_date") or "")) + " (or the floor offer on that date if they said the full amount is too much)" + ("; attempt 2 = floor " + money(floor) + " on the deadline " + dtext(deadline) + "." if att == 2 else "; there is NO attempt 2 for this product: after a second refusal, stop and move on."))
        sent.append((name, money(p.get("past_due")), dlate))
    v["pf_json"] = json.dumps(pf)
    v["product_count"] = str(len(pf))
    v["account_facts"] = "\n".join(lines) if lines else "No late product was returned."
    title = str(v.get("title") or "")
    last = str(v.get("last_name") or "")
    if not sent:
        v["debt_statement"] = "Thank you, you are verified. I am sorry, I cannot see your account details at the moment."
        v["account_state"] = "empty"
        return
    if len(sent) == 1:
        n, a, d = sent[0]
        v["debt_statement"] = "Thank you, " + title + " " + last + ", you are verified. I am calling from the collections team about a late payment on your " + n + ". The past-due amount is " + a + ", and it is " + str(d) + " days late. Can you make this payment today?"
    else:
        parts = ["Thank you, " + title + " " + last + ", you are verified. I am calling from the collections team about late payments."]
        for n, a, d in sent:
            parts.append("Your " + n + " has a past-due amount of " + a + " and is " + str(d) + " days late.")
        parts.append("Can you pay all of them today?")
        v["debt_statement"] = " ".join(parts)
    v["account_state"] = "ready"
'''

GET_ACCOUNT_POST = FACTS_FN + r'''
try:
    if isinstance(result, dict):
        result.pop("header", None)
        d = result.get("data")
        if isinstance(d, dict) and isinstance(d.get("products"), list):
            vars["products_json"] = json.dumps(d.get("products"))
            build_facts(d.get("products"), vars, MULTI)
except Exception:
    pass
'''

ACCOUNT_CODE = FACTS_FN + r'''
import re
try:
    if str(vars.get("account_state") or "") != "ready":
        prods = None
        for key in ["products_json", "products"]:
            val = vars.get(key)
            if isinstance(val, list):
                prods = val
            elif isinstance(val, str) and val.strip().startswith("["):
                try:
                    prods = json.loads(val)
                except Exception:
                    prods = None
            if prods:
                break
        if not prods:
            found = dict()
            for k in list(vars.keys()):
                m = re.search(r"products[\.\[](\d+)\]?\.(\w+)$", str(k))
                if m:
                    idx = int(m.group(1))
                    if idx not in found:
                        found[idx] = dict()
                    found[idx][m.group(2)] = vars.get(k)
            prods = [found[i] for i in sorted(found.keys())]
        build_facts(prods or [], vars, MULTI)
except Exception as e:
    vars["account_state"] = "error"
    vars["account_facts"] = "Account details unavailable."
    vars["debt_statement"] = "Thank you, you are verified. I am sorry, I cannot see your account details at the moment."
'''

VERIFY_POST = r'''
try:
    if isinstance(result, dict):
        result.pop("header", None)
        d = result.get("data")
        if isinstance(d, dict):
            left = d.get("wrong_answers_left")
            if d.get("all_verified") is True:
                vars["id_state"] = "verified"
                msg = "Both security answers are verified. Do not say anything about the account yet."
            elif left is not None and str(left) == "0":
                vars["id_state"] = "failed"
                msg = "The identity check has FAILED and is over. Do not ask any more questions and say nothing about the account. Tell the customer you could not verify their identity and that they can use the Freya Bank mobile app or visit a branch. Thank them, say goodbye, and in the same message call close_call with outcome not_verified and reason failed."
            elif d.get("hint") == "day_month_swapped":
                msg = "The day and the month look swapped. This does NOT count as a wrong answer. Ask the customer to say their date of birth again with the month as a word, for example 14 March 1988."
            elif d.get("ok") is False:
                msg = "The answer could not be read (" + str(d.get("error") or "") + "). This is not a wrong answer. Ask the customer to repeat the same answer."
            elif d.get("verified") is True:
                msg = "Correct. Now ask for the last four digits of the phone number on file."
            elif d.get("verified") is False:
                msg = "This answer is WRONG. Wrong answers left: " + str(left) + ". Do not say what the right answer is. Ask the SAME question again."
            else:
                msg = "Unexpected result. Ask the customer to repeat the answer."
            d["what_to_do_next"] = msg
except Exception:
    pass
'''

PROMISE_PRE = r'''
import json
try:
    b = config.get("body")
    if isinstance(b, dict):
        pid = str(b.get("product_id") or "")
        try:
            pf = json.loads(str(vars.get("pf_json") or "[]"))
        except Exception:
            pf = []
        for p in pf:
            if str(p.get("product_id")) == pid:
                dl = str(p.get("deadline") or "")
                if dl and str(b.get("date") or "") > dl:
                    b["date"] = dl
                try:
                    if float(b.get("amount")) > float(p.get("past_due")):
                        b["amount"] = float(p.get("past_due"))
                except Exception:
                    pass
        vars["last_promise_pid"] = pid
except Exception:
    pass
'''

PROMISE_POST_A = r'''
import json
try:
    if isinstance(result, dict):
        result.pop("header", None)
        d = result.get("data")
        if not isinstance(d, dict):
            d = dict()
            result["data"] = d
        pid = str(vars.get("last_promise_pid") or "")
        if d.get("ok") is True:
            n = int(vars.get("promise_count") or 0) + 1
            vars["promise_count"] = str(n)
            done = str(vars.get("promised_pids") or "")
            vars["promised_pids"] = (done + "," + pid).strip(",")
            d["what_to_do_next"] = DONE_MSG
        else:
            key = "promise_fail_" + pid
            f = int(vars.get(key) or 0) + 1
            vars[key] = str(f)
            if f < 2:
                d["what_to_do_next"] = "The promise was NOT recorded. Do not tell the customer it is recorded. Call create_promise once more right now, with exactly the same product_id, amount and date."
            else:
                vars["service_error_pids"] = (str(vars.get("service_error_pids") or "") + "," + pid).strip(",")
                d["what_to_do_next"] = FAIL2_MSG
except Exception:
    pass
'''

DONE_A = '"The promise is recorded. Now say exactly: You will receive a text message confirming this promise. Then thank the customer, say goodbye, and in the same message call close_call with outcome promise."'
FAIL2_A = '"The promise could NOT be recorded after two tries. Tell the customer honestly that you could not record the promise. Do not say it is recorded. Then thank the customer, say goodbye, and in the same message call close_call with outcome no_promise and reason service_error."'
DONE_B = '"This promise is recorded. If more agreed promises still need to be recorded, call create_promise for the next one now. When all agreed promises are recorded, say exactly: You will receive a text message confirming this promise. Then continue with the remaining products, or wrap up."'
FAIL2_B = '"This promise could NOT be recorded after two tries. Do not say it is recorded. Tell the customer you could not record the promise for this product. Then record any other agreed promises. When you wrap up, call add_note for this product with reason service_error."'

TRANSFER_POST = r'''
try:
    if isinstance(result, dict):
        result.pop("header", None)
        d = result.get("data")
        if isinstance(d, dict):
            q = str(vars.get("last_transfer_queue") or "")
            if d.get("ok") is True:
                vars["transfer_queue"] = q
                r = dict(restructuring="restructuring", general="human", support="support").get(q, "human")
                d["what_to_do_next"] = "The transfer is arranged. Tell the customer a colleague will take over now. Do not add any note. Thank them, say goodbye, and in the same message call close_call with outcome transferred and reason " + r + "."
            else:
                d["what_to_do_next"] = "The transfer did not work. Tell the customer honestly that the transfer failed. Call transfer_to_agent once more."
except Exception:
    pass
'''

TRANSFER_PRE = r'''
try:
    b = config.get("body")
    if isinstance(b, dict):
        vars["last_transfer_queue"] = str(b.get("queue") or "")
except Exception:
    pass
'''

NOTE_PRE = r'''
import json
try:
    b = config.get("body")
    if isinstance(b, dict):
        try:
            notes = json.loads(str(vars.get("notes_json") or "[]"))
        except Exception:
            notes = []
        notes.append([str(b.get("product_id") or ""), str(b.get("reason") or "")])
        vars["notes_json"] = json.dumps(notes)
except Exception:
    pass
'''

NOTE_POST = r'''
try:
    if isinstance(result, dict):
        result.pop("header", None)
        d = result.get("data")
        if isinstance(d, dict):
            if d.get("ok") is True:
                d["what_to_do_next"] = "The note is saved. Call add_note for the next product without a promise, or, if all are noted, thank the customer, say goodbye and call close_call."
            else:
                d["what_to_do_next"] = "The note was not saved. Call add_note once more with the same values."
except Exception:
    pass
'''

CLOSE_PRE = r'''
import json
try:
    b = config.get("body")
    if isinstance(b, dict):
        out = str(b.get("outcome") or "")
        rsn = str(b.get("reason") or "")
        tq = str(vars.get("transfer_queue") or "")
        pc = int(vars.get("promise_count") or 0)
        if tq:
            out = "transferred"
            rsn = dict(restructuring="restructuring", general="human", support="support").get(tq, rsn)
        elif pc > 0:
            out = "promise"
        elif str(vars.get("id_state") or "") == "failed":
            out = "not_verified"
            rsn = "failed"
        elif MULTI and out in ("no_promise", "paid", "promise"):
            try:
                notes = json.loads(str(vars.get("notes_json") or "[]"))
            except Exception:
                notes = []
            if notes:
                first = dict()
                for pid, r in notes:
                    if pid not in first:
                        first[pid] = r
                order = sorted(first.keys())
                try:
                    pf = json.loads(str(vars.get("pf_json") or "[]"))
                    order = [str(p.get("product_id")) for p in pf if str(p.get("product_id")) in first] + [k for k in sorted(first.keys()) if k not in [str(p.get("product_id")) for p in pf]]
                    allp = [str(p.get("product_id")) for p in pf]
                except Exception:
                    allp = order
                nonpaid = [first[k] for k in order if first[k] != "paid"]
                if not nonpaid and all(k in first for k in allp):
                    out = "paid"
                elif nonpaid:
                    out = "no_promise"
                    rsn = nonpaid[0]
        elif (not MULTI) and (str(vars.get("service_error_pids") or "") or int(vars.get("create_promise_failure_count") or 0) >= 2) and out in ("no_promise", "promise"):
            out = "no_promise"
            rsn = "service_error"
        b["outcome"] = out
        if out in ("promise", "paid"):
            b.pop("reason", None)
        else:
            b["reason"] = rsn
except Exception:
    pass
'''

GENERIC_POST = r'''
try:
    if isinstance(result, dict):
        result.pop("header", None)
        d = result.get("data")
        if isinstance(d, dict):
            d["what_to_do_next"] = OKMSG if d.get("ok") is True else FAILMSG
except Exception:
    pass
'''


def sub(code, multi):
    code = code.replace("MULTI", "True" if multi else "False")
    assert "{{" not in code and "}}" not in code, "double braces in code"
    return code


# ---------------------------------------------------------------- tool builders

def api_tool(name, desc, body_props, required, pre="", post="", write=True):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(body_props)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": 0 if write else 2},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": f"{BASE}/{name}"},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": props, "required": required},
                },
            },
        },
    }
    if pre:
        t["pre_process_code"] = pre
    if post:
        t["post_process_code"] = post
    return t


def close_tool(multi):
    return api_tool(
        "close_call",
        "End the call record. CALL it exactly once, as the very last action, in the same message in which you thank the customer and say goodbye. Never call any tool after it.",
        {
            "outcome": {"type": "string", "enum": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"], "default": "{{outcome}}",
                        "description": "One of: promise, paid, transferred, no_promise, not_verified, not_reached."},
            "reason": {"type": "string", "enum": ["restructuring", "human", "support", "refused", "hardship", "dispute", "service_error", "failed", "declined", "callback", "no_callback", "wrong_number", "deceased", "unclear"],
                       "default": "{{reason}}",
                       "description": "transferred: restructuring, human or support. no_promise: refused, hardship, dispute or service_error. not_verified: failed or declined. not_reached: callback, no_callback, wrong_number, deceased or unclear. Leave it out for promise and paid."},
        },
        ["outcome"],
        pre=sub(CLOSE_PRE, multi),
        post=sub(GENERIC_POST.replace("OKMSG", '"Closed."').replace("FAILMSG", '"Closed."'), multi),
    )


def verify_tool():
    return api_tool(
        "verify_identity",
        "Check one security answer. CALL it every time the customer gives an answer to a security question, one call per answer. Then follow what_to_do_next in the result.",
        {
            "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}", "description": "date_of_birth or phone_last4."},
            "answer": {"type": "string", "default": "{{answer}}", "description": "date_of_birth: YYYY-MM-DD, converted from what the customer said. A date given only as numbers is day, then month, then year. phone_last4: exactly four digits."},
        },
        ["field", "answer"],
        post=sub(VERIFY_POST, False),
    )


def transfer_tool(allowed):
    return api_tool(
        "transfer_to_agent",
        "Hand the call to a person. CALL it only in the cases the instructions name. Queue: " + ", ".join(allowed) + ".",
        {"queue": {"type": "string", "enum": allowed, "default": "{{queue}}", "description": "One of: " + ", ".join(allowed) + "."}},
        ["queue"],
        pre=sub(TRANSFER_PRE, False),
        post=sub(TRANSFER_POST, False),
    )


def callback_tool():
    return api_tool(
        "schedule_callback",
        "Book a callback for the customer. CALL it as soon as the person on the line gives a time inside the allowed window.",
        {
            "date": {"type": "string", "default": "{{date}}", "description": "YYYY-MM-DD"},
            "time": {"type": "string", "default": "{{time}}", "description": "HH:MM, 24 hour"},
        },
        ["date", "time"],
        post=sub(GENERIC_POST.replace("OKMSG", '"The callback is booked. Tell the person, thank them, say goodbye and in the same message call close_call with outcome not_reached and reason callback."').replace(
            "FAILMSG", '"The callback was NOT booked. Do not say it is booked. Call schedule_callback once more with the same values."'), False),
    )


def promise_tool(multi):
    post = PROMISE_POST_A.replace("DONE_MSG", DONE_B if multi else DONE_A).replace("FAIL2_MSG", FAIL2_B if multi else FAIL2_A)
    return api_tool(
        "create_promise",
        "Record one payment promise for one product. CALL it only after the customer said a clear yes to the read-back. One call per product.",
        {
            "product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id exactly as in the account facts, for example p1."},
            "amount": {"type": "number", "default": "{{amount}}", "description": "The agreed amount."},
            "date": {"type": "string", "default": "{{date}}", "description": "The agreed date, YYYY-MM-DD."},
        },
        ["product_id", "amount", "date"],
        pre=sub(PROMISE_PRE, multi),
        post=sub(post, multi),
    )


def note_tool():
    return api_tool(
        "add_note",
        "Record why one product ended without a promise. CALL it only while wrapping up, once for each product without a recorded promise. Never call it if the call is transferred.",
        {
            "product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id exactly as in the account facts."},
            "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "default": "{{reason}}", "description": "One of: refused, hardship, dispute, paid, service_error."},
        },
        ["product_id", "reason"],
        pre=sub(NOTE_PRE, True),
        post=sub(NOTE_POST, True),
    )


# ---------------------------------------------------------------- nodes

def to_end():
    return {"target_node": "end", "description": "The call record was closed",
            "condition": {"logic": "or", "conditions": [{"variable": "close_call_success_count", "operator": "greater_than", "operand": 0}]}}


def conv(name, task, tools, transitions, on_enter=None, extraction=None):
    n = {
        "name": name,
        "node_type": "conversation",
        "task_message": task,
        "tools": tools,
        "transitions": transitions,
        "max_node_turns": 60,
    }
    if on_enter:
        n["on_enter"] = on_enter
    if extraction:
        n["extraction_schema"] = extraction
    return n


SYSTEM = """You are the digital assistant of Freya Bank, on an outbound phone call. Speak English. Keep every turn to one to three short sentences. Ask one question at a time.

Call facts:
- Customer: {{title}} {{first_name}} {{last_name}}. Address them as {{title}} {{last_name}}.
- Now: {{today_text}}, {{now_time}}. All date rules use this date, never your own clock.

Rules for the whole call:
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing. Call one tool per message. When a tool result has what_to_do_next, do exactly that.
- Never say something is recorded, booked or done unless the tool result says ok true.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam: say they can verify the call by phoning Freya Bank's customer service number, then continue.
- If asked something the facts and tools do not answer: say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any other term.
- To end the call: thank the customer and say goodbye, and in that same message call close_call. close_call is always the last tool call."""

PRE_ID_RULE = "Before identity is verified you must not say why you are calling. Never say \"collections\", \"debt\", \"payment\", \"overdue\", \"loan\", \"card\" or anything about an account. If asked what the call is about, say you can explain once the security check is done."


def opening_node():
    task = f"""You have just said that you are a digital assistant calling from Freya Bank, that you record the call, and asked whether you are speaking with {{{{title}}}} {{{{last_name}}}}.
{PRE_ID_RULE}

Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead", "who is this" do not.
- If the reply is not a confirmation, answer any question first (robot: you are Freya Bank's digital assistant; scam: they can verify by phoning Freya Bank's customer service number; who is calling: Freya Bank's digital assistant), then ask once more: "Am I speaking with {{{{title}}}} {{{{last_name}}}}?". That is the second ask.
- If it is still unclear after the second ask, thank them, say goodbye and call close_call with outcome not_reached and reason unclear.
- If the person says twice that they do not want to talk, thank them, say goodbye and call close_call with outcome not_verified and reason declined.
- If the person asks for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
No other tool call is allowed here."""
    return conv(
        "opening", task, [close_tool(MULTI_FLAG[0]), transfer_tool(["general"])],
        [
            to_end(),
            {"target_node": "identity", "description": "The customer confirmed who they are",
             "condition": {"logic": "or", "conditions": [{"variable": "party", "operator": "equals", "operand": "customer"}]}},
            {"target_node": "third_party", "description": "Someone else answered",
             "condition": {"logic": "or", "conditions": [
                 {"variable": "party", "operator": "equals", "operand": "someone_else"},
                 {"variable": "party", "operator": "equals", "operand": "wrong_number"},
                 {"variable": "party", "operator": "equals", "operand": "deceased"}]}},
        ],
        on_enter={"type": "tts", "text": "Hello, this is a digital assistant calling from Freya Bank. Please note that we record this call. Am I speaking with {{title}} {{last_name}}?"},
        extraction=[{
            "name": "party", "type": "string",
            "enum_values": ["customer", "someone_else", "wrong_number", "deceased"],
            "description": "Who answered. customer: the person clearly confirms they are the customer, with yes, that's me, speaking, or their own name. someone_else: the person says they are someone else (a relative, a colleague) or that the customer is not available. wrong_number: the number does not belong to the customer. deceased: the customer has died. Leave empty for hello, go ahead, who is this, a question, or anything unclear.",
            "min_confidence": 0.6,
        }],
    )


def third_party_node():
    task = f"""The person on the line is not {{{{title}}}} {{{{last_name}}}}.
Never say why you are calling. Say nothing about any account, debt, payment, product or amount, even if they ask or offer to pay. They may not answer security questions. If asked, say only that it is a personal matter for {{{{title}}}} {{{{last_name}}}}.

- If the person says the customer has died: say exactly "I am sorry for your loss.", ask nothing else, say goodbye and call close_call with outcome not_reached and reason deceased.
- If the person says the number does not belong to the customer: apologise, say goodbye and call close_call with outcome not_reached and reason wrong_number.
- Otherwise ask when {{{{title}}}} {{{{last_name}}}} can be reached.
  Allowed callback window: {{{{callback_window}}}}.
  If they give a day and time inside the window, call schedule_callback with the date (YYYY-MM-DD) and the time (HH:MM). "Tomorrow" means the next calendar day; check it is a business day in the calendar. "Morning around eleven" is 11:00.
  If they give only a day, ask for a time. If they offer a day or time outside the window, explain the window and ask once for another time. If that one is also outside the window, do not schedule: thank them, say goodbye and call close_call with outcome not_reached and reason no_callback.
  After the callback is booked, thank them, say goodbye and call close_call with outcome not_reached and reason callback.

Calendar:
{{{{calendar}}}}"""
    return conv("third_party", task, [callback_tool(), close_tool(MULTI_FLAG[0])], [to_end()])


def identity_node():
    task = f"""The customer confirmed who they are. Now run the security check.
{PRE_ID_RULE}

1. Ask for their date of birth. When they answer, call verify_identity with field date_of_birth and the date as YYYY-MM-DD. Convert words to numbers yourself. A date given only as numbers is day, then month, then year (05/03/1990 is 1990-03-05).
2. When the date of birth is verified, ask for the last four digits of the phone number on file. Call verify_identity with field phone_last4 and the four digits.
After every result, do what what_to_do_next says. Ask only the question that is still open; never ask again a question that already passed.

If the customer does not want to answer, or asks what the call is about instead of answering: explain once that these questions protect their account, and ask again. If they refuse a second time or ask a second time what the call is about, thank them, say goodbye and call close_call with outcome not_verified and reason declined.
If the customer asks for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
If the identity check fails, tell them to use the Freya Bank mobile app or a branch, thank them, say goodbye and call close_call with outcome not_verified and reason failed."""
    return conv(
        "identity", task, [verify_tool(), close_tool(MULTI_FLAG[0]), transfer_tool(["general"])],
        [
            to_end(),
            {"target_node": "load_account", "description": "Both security answers verified",
             "condition": {"logic": "or", "conditions": [
                 {"variable": "id_state", "operator": "equals", "operand": "verified"},
                 {"variable": "verify_identity_response.data.all_verified", "operator": "equals", "operand": "true"},
                 {"variable": "verify_identity_response.data.all_verified", "operator": "equals", "operand": "True"}]}},
        ],
        on_enter={"type": "llm", "prompt": "Thank the customer and say that before you continue you need to ask two security questions. Ask for their date of birth. Do not say why you are calling."},
    )


def load_account_node(multi):
    return {
        "name": "load_account",
        "node_type": "api_request",
        "passthrough": True,
        "passthrough_default_transition": "account_facts",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "pre_actions": [{
            "type": "function",
            "config": {"timeoutMs": 12000, "maxRetries": 2},
            "function": {
                "name": "get_account",
                "handler": "__function__:api_call",
                "description": "Get the late products.",
                "parameters": {"type": "object", "properties": {
                    "url": {"type": "string", "default": f"{BASE}/get_account"},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}}, "required": []},
                }},
            },
            "post_process_code": sub(GET_ACCOUNT_POST, multi),
        }],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [{"target_node": "account_facts", "description": "always", "condition": {"operator": "always"}}],
    }


def account_code_node(multi):
    return {
        "name": "account_facts",
        "node_type": "code",
        "passthrough": True,
        "passthrough_default_transition": "negotiate",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "pre_actions": [{
            "type": "function",
            "function": {
                "name": "code_exec",
                "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": sub(ACCOUNT_CODE, multi)},
                    "timeout_ms": {"type": "number", "default": 10000},
                }},
            },
        }],
        "transitions": [{"target_node": "negotiate", "description": "always", "condition": {"operator": "always"}}],
    }


NEGOTIATE_COMMON = """The customer is verified. You already said: "{{debt_statement}}"

Account facts (product_id, full past-due amount, floor, deadline, attempts):
{{account_facts}}

Date facts:
- Today: {{today_text}}. Attempt 1 date (last business day of this week, or of next week if today is that day): {{attempt1_text}}.
- A promise date must be today or later, a business day, and not after that product's deadline.
- "Next <weekday>" is that weekday in the following calendar week. "This <weekday>" is the one in the current week. Use the week labels in the calendar.
- Calendar:
{{calendar}}

DATE RULES
- Weekend or bank holiday named, not after the deadline: say it is not a business day and offer the next business day from the calendar.
- A date after the deadline: say the latest date you can record is the deadline, and offer the deadline. If they refuse the deadline, that is a flat refusal.
- A vague period ("next week", "end of the month", "the week after next", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.

AMOUNT RULES
- Always ask for the full past-due amount first. Never ask how much they can pay. You propose every amount. If they say "you tell me", propose the amount yourself.
- If the full amount is too much: offer the floor, once, and say that the rest stays overdue. Make it one combined offer: the floor amount on the date the customer already named, or else on the attempt 1 date (example: "I can record the minimum payment of 90.00 on Friday 16 October; the rest stays overdue. Would that work?"). This offer counts as attempt 1. Name the floor amount only in this offer and, in the late band, in attempt 2. If they refuse the floor, that is a flat refusal.
- An amount from the floor up to the full amount, both included: accept it. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept, that is a flat refusal.

PERSUASION (count attempts per product)
- A date or an amount the customer proposes is never a refusal: handle it with the date and amount rules.
- A flat refusal or a non-answer uses one persuasion attempt. "No" to paying today with no date and no amount is a flat refusal.
- Attempt 1: propose the full past-due amount on the attempt 1 date. If they already said the full amount is too much, the combined floor offer above is attempt 1.
- Attempt 2, late band only: propose the floor amount on the product's deadline.
- When the allowed attempts are used up, stop. Never repeat an offer they already refused. A flat refusal never earns an extra floor offer: the floor comes only when they say the full amount is too much, or as attempt 2 in the late band. The exact offers for each product are listed in the account facts.

SPECIAL SITUATIONS
- Illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_to_agent with queue support. If they decline, the product ends as hardship. If they still name a date or an amount themselves, handle it as a promise.
- "I already paid" (this past-due amount): say payments can take one business day to appear. Take no promise for it.
- "This debt is not mine", "I never had this product", or a claim it was closed or paid off in the past: do not argue, take no promise. It is a dispute.
- A request for a new payment plan or lower instalments: describe no plan; call transfer_to_agent with queue restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
- If the customer says twice that they do not want to talk: it is a refusal.
- Never offer a discount, a waiver, an instalment plan or any other term.

CONFIRMING AND RECORDING
- Before recording, read back the product, the amount and the date and ask "Do you confirm?". Call create_promise only after a clear yes, with the product_id from the account facts, the amount as a number and the date as YYYY-MM-DD.
- If they change the date or amount at the read-back, check it again against the rules and read back again.
- A recorded promise cannot be changed or cancelled in this call. If asked, say they can change it in the mobile app.
- Say a promise is recorded only after create_promise returns ok true. If it fails or returns an error, say nothing about it being recorded and call create_promise once more right away with the same values. If the second call also fails, tell the customer honestly that you could not record the promise. Follow what_to_do_next when present.
- After a recorded promise say exactly: "You will receive a text message confirming this promise."
"""

NEGOTIATE_A_END = """
CLOSING (thank the customer, say goodbye, and call close_call in the same message)
- Promise recorded: outcome promise.
- Already paid: outcome paid.
- Transfer done: outcome transferred, reason restructuring, human or support.
- Attempts used up / refusal: no_promise, refused. Hardship declined support: no_promise, hardship. Dispute: no_promise, dispute. create_promise failed twice: no_promise, service_error.
No other tool may come after close_call."""

NEGOTIATE_B_EXTRA = """
SEVERAL PRODUCTS (the account facts can list one to three products)
- You already asked whether they can pay all of them today. If yes, read back all of them for today and confirm once.
- If not: go through the products one by one, in the order of the account facts. Only agree on each product in this phase; do not read back, do not ask "Do you confirm?" and do not call create_promise until every product is handled. Do not ask about today again for each product. Start each product at attempt 1. The band, the deadline and the persuasion attempts are per product.
- If the customer names one date for everything and it is after one product's deadline, that product gets its own deadline and the others keep the named date. Say so in the read-back.
- The customer may promise some products and refuse others. A dispute or an "already paid" claim on one product does not end the call: continue with the others.
- When every product is handled: read all agreed promises back together in one read-back (product, amount and date for each) and ask "Do you confirm?" once. After the yes, call create_promise once per product, one call per message.
- Then, while wrapping up, call add_note once for each product without a recorded promise, with its reason: refused, hardship, dispute, paid or service_error. Do this also when no product got a promise.
- A restructuring request at any point: call transfer_to_agent with queue restructuring. Promises already recorded stay. Do not record promises that were agreed but not yet recorded. On any transfer (restructuring, support, human) do not call add_note at all, neither before nor after.

CLOSING (thank the customer, say goodbye, and call close_call in the same message, after all notes)
- At least one promise recorded: outcome promise (unless the call was transferred: outcome transferred with that reason).
- No promise recorded and every product noted paid: outcome paid.
- Otherwise: outcome no_promise with the reason of the first product, in account-facts order, whose note is not paid.
- Transfer done: outcome transferred, reason restructuring, human or support.
No other tool may come after close_call."""


def negotiate_node(multi):
    task = NEGOTIATE_COMMON + (NEGOTIATE_B_EXTRA if multi else NEGOTIATE_A_END)
    if not multi:
        task = task.replace("(count attempts per product)", "")
    tools = [promise_tool(multi), transfer_tool(["restructuring", "general", "support"]), close_tool(multi)]
    if multi:
        tools.insert(1, note_tool())
    return conv("negotiate", task, tools, [to_end()], on_enter={"type": "tts", "text": "{{debt_statement}}"})


def setup_node():
    return {
        "name": "setup",
        "node_type": "code",
        "passthrough": True,
        "passthrough_default_transition": "opening",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "pre_actions": [{
            "type": "function",
            "function": {
                "name": "code_exec",
                "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": sub(SETUP_CODE, False)},
                    "timeout_ms": {"type": "number", "default": 10000},
                }},
            },
        }],
        "transitions": [{"target_node": "opening", "description": "always", "condition": {"operator": "always"}}],
    }


def end_node():
    return {
        "name": "end",
        "node_type": "end_call",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {"type": "function", "function": {
            "name": "call_closed", "handler": "__function__:end_call",
            "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
    }


MULTI_FLAG = [False]


def build(brief):
    multi = brief.upper() == "B"
    MULTI_FLAG[0] = multi
    return {
        "initial_node": "setup",
        "system_prompt": SYSTEM,
        "nodes": {
            "setup": setup_node(),
            "opening": opening_node(),
            "third_party": third_party_node(),
            "identity": identity_node(),
            "load_account": load_account_node(multi),
            "account_facts": account_code_node(multi),
            "negotiate": negotiate_node(multi),
            "end": end_node(),
        },
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    }


if __name__ == "__main__":
    wf = build(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump(wf, f, indent=1)
    print("wrote", sys.argv[2])
