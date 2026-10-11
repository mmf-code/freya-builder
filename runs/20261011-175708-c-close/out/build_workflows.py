"""Generate the workflows for brief-a-raw (one product) and brief-b-raw (one to three products).

    python3 out/build_workflows.py

Writes out/brief-a-raw.workflow.json, out/brief-b-raw.workflow.json and their contract files.
Every rule and value below comes from briefs/brief-a-raw.md (CP-4 as changed by memo OPS-2026-41, close code
list) and briefs/brief-b-raw.md (change notice CN-12), and tools/openapi.json.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = json.loads((ROOT / "tools/openapi.json").read_text())
SERVER = API["servers"][0]["url"].rstrip("/")

# Memo OPS-2026-41 item 1: the full holiday list.
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]

ALWAYS = {"operator": "always"}


def any_of(*checks):
    return {"logic": "or", "conditions": list(checks)}


def var(name, op, operand=None):
    c = {"variable": name, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return c


def is_true(name):
    return [var(name, "equals", "true"), var(name, "equals", "True")]


def always(target):
    return {"target_node": target, "description": "always", "condition": ALWAYS}


def tool_go(target, description):
    return {"target_node": target, "description": description, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": description}}


# ------------------------------------------------------------------ tools

def api_tool(name, description, fields, required, max_retries=0, post=None, mapping=None):
    """fields: {field: leaf spec}. customer_id is always baked from the call variable."""
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(fields)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": f"{SERVER}/{name}"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": props, "required": required},
            }},
        },
    }
    if post:
        t["post_process_code"] = post
    if mapping:
        t["response_mapping"] = mapping
    return t


HOOK_HEAD = "try:\n    if isinstance(result, dict):\n        result.pop('header', None)\n        d = result.get('data')\n        if not isinstance(d, dict):\n            d = dict()\n            result['data'] = d\n"
HOOK_TAIL = "except Exception:\n    pass\n"

VERIFY_POST = HOOK_HEAD + """        sc = result.get('status_code')
        if isinstance(sc, int) and sc >= 500:
            msg = 'The security service failed and nothing was checked. Call verify_identity again with the same answer.'
        elif d.get('all_verified') is True or str(d.get('all_verified')).lower() == 'true':
            msg = 'Both security answers passed.'
        elif d.get('hint') == 'day_month_swapped':
            msg = 'Day and month look swapped. Ask the customer to say the month of their birth as a word. This retry is not a wrong answer.'
        elif d.get('ok') is False or str(d.get('ok')).lower() == 'false':
            msg = 'The answer was not checked: ' + str(d.get('error') or 'unreadable') + '. If wrong answers are used up, the check has ended. Otherwise ask the customer to say it again clearly; for a date of birth ask for day, month as a word, and year.'
        elif d.get('verified') is True or str(d.get('verified')).lower() == 'true':
            msg = 'That answer is correct. If the date of birth has now passed, ask for the last four digits of the phone number on file. If both questions have been asked, ask again the one that has not passed yet.'
        else:
            left = d.get('wrong_answers_left')
            if str(left) == '0':
                msg = 'That answer is wrong and no wrong answers are left. The check has ended. Do not state anything about the account.'
            else:
                msg = 'That answer is wrong. Wrong answers left: ' + str(left) + '. Tell the customer it did not match and ask the same question again.'
        d['what_to_do_next'] = msg
""" + HOOK_TAIL

PROMISE_POST = HOOK_HEAD + """        ok = d.get('ok') is True or str(d.get('ok')).lower() == 'true'
        if ok:
            d['what_to_do_next'] = 'The promise is recorded for this product. You may now tell the customer it is recorded.'
        else:
            d['what_to_do_next'] = 'The promise was NOT recorded (' + str(d.get('error') or 'service error') + '). Never say it is recorded. If this is the first failure for this product, call create_promise once more now with the same product_id, amount and date, without asking the customer. If it already failed once before for this product, tell the customer you could not record the promise for it.'
""" + HOOK_TAIL

NOTE_POST = HOOK_HEAD + """        ok = d.get('ok') is True or str(d.get('ok')).lower() == 'true'
        if ok:
            d['what_to_do_next'] = 'The note is saved.'
        else:
            d['what_to_do_next'] = 'The note was NOT saved (' + str(d.get('error') or 'service error') + '). Call add_note once more with the same values.'
""" + HOOK_TAIL

CALLBACK_POST = HOOK_HEAD + """        ok = d.get('ok') is True or str(d.get('ok')).lower() == 'true'
        if ok:
            d['what_to_do_next'] = 'The callback is booked.'
        else:
            d['what_to_do_next'] = 'The callback was NOT booked (' + str(d.get('error') or 'service error') + '). Never say it is booked. Tell the person it could not be booked and ask once for another time inside the window.'
""" + HOOK_TAIL


def verify_tool():
    return api_tool(
        "verify_identity",
        "Check one security answer. CALL it every time the customer gives a date of birth or the last four phone digits, once per answer.",
        {
            "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                      "description": "Which question was answered. One of: date_of_birth, phone_last4."},
            "answer": {"type": "string", "default": "{{answer}}",
                       "description": "date_of_birth as YYYY-MM-DD (numbers-only dates are day, month, year). phone_last4 as exactly four digits."},
        },
        ["field", "answer"], post=VERIFY_POST)


def promise_tool():
    return api_tool(
        "create_promise",
        "Record one payment promise for one product. CALL it only after the customer gave a clear yes to the read-back. One call per product.",
        {
            "product_id": {"type": "string", "default": "{{product_id}}",
                           "description": "The product_id exactly as written in ACCOUNT, for example p1. Never invent one."},
            "amount": {"type": "number", "default": "{{amount}}", "description": "The agreed amount as a number, for example 150.5."},
            "date": {"type": "string", "format": "date", "default": "{{date}}", "description": "The agreed payment date as YYYY-MM-DD."},
        },
        ["product_id", "amount", "date"], post=PROMISE_POST)


def note_tool():
    reasons = ["refused", "hardship", "dispute", "paid", "service_error"]
    return api_tool(
        "add_note",
        "Record why one product ended without a promise. CALL it once for every product that has no recorded promise. Never on a transfer.",
        {
            "product_id": {"type": "string", "default": "{{product_id}}",
                           "description": "The product_id exactly as written in ACCOUNT, for example p2."},
            "reason": {"type": "string", "enum": reasons, "default": "{{reason}}",
                       "description": "One of: refused, hardship, dispute, paid, service_error."},
        },
        ["product_id", "reason"], post=NOTE_POST)


def callback_tool():
    return api_tool(
        "schedule_callback",
        "Book a callback for the customer. CALL it as soon as the person names a day and a time that are inside the callback window.",
        {
            "date": {"type": "string", "format": "date", "default": "{{date}}", "description": "Callback date as YYYY-MM-DD."},
            "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24-hour clock."},
        },
        ["date", "time"], post=CALLBACK_POST)


def engine_call(name, fields, max_retries=0):
    """A tool run by the engine in pre_actions: every field baked."""
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    for k, v in fields.items():
        props[k] = {"type": "string", "default": v}
        enum = API["paths"][f"/{name}"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"][k].get("enum")
        if enum:
            assert v in enum, (name, k, v)
            props[k]["enum"] = [v]
    return {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name, "handler": "__function__:api_call", "description": name,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": f"{SERVER}/{name}"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": props, "required": []},
            }},
        },
    }


def code_node(name, code, target, fallback_transitions=None):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": target,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {
            "name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {
                "code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": (fallback_transitions or []) + [always(target)],
    }


# ------------------------------------------------------------------ code steps

SETUP_CODE = r'''import datetime
HOL = set(HOLIDAY_LIST)
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MO = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
def fmt(d):
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MO[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def nth_bd(start, n):
    d = start
    c = 0
    while c < n:
        d = d + datetime.timedelta(days=1)
        if isbd(d):
            c += 1
    return d
try:
    raw = str(vars.get('now') or '').strip()
    try:
        nowdt = datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        nowdt = datetime.datetime.fromisoformat(raw[:10] + 'T09:00')
    today = nowdt.date()
    hhmm = nowdt.strftime('%H:%M')
    one = datetime.timedelta(days=1)
    next_bd = nth_bd(today, 1)
    dl_early = nth_bd(today, EARLY_N)
    dl_late = nth_bd(today, LATE_N)
    monday = today - datetime.timedelta(days=today.weekday())
    this_week = [monday + datetime.timedelta(days=i) for i in range(5)]
    next_week = [monday + datetime.timedelta(days=7 + i) for i in range(5)]
    later_this = [d for d in this_week if isbd(d) and d > today]
    bd_this = [d for d in this_week if isbd(d)]
    bd_next = [d for d in next_week if isbd(d)]
    if later_this:
        first_offer = later_this[-1]
    else:
        first_offer = bd_next[-1] if bd_next else nth_bd(today, 5)
    vars['today_iso'] = today.isoformat()
    vars['today_text'] = fmt(today)
    vars['now_hhmm'] = hhmm
    vars['next_bd_iso'] = next_bd.isoformat()
    vars['dl_early_iso'] = dl_early.isoformat()
    vars['dl_late_iso'] = dl_late.isoformat()
    vars['first_offer_iso'] = first_offer.isoformat()
    lines = []
    lines.append('Now: ' + fmt(today) + ', ' + hhmm + '. Today is ' + ('a business day.' if isbd(today) else 'NOT a business day.'))
    lines.append('Business days are Monday to Friday, except the bank holidays ' + ', '.join(sorted(HOL)) + '.')
    lines.append('Early-stage PTP deadline (EARLY_WORD business day after today): ' + fmt(dl_early) + '.')
    lines.append('Late-stage PTP deadline (LATE_WORD business day after today): ' + fmt(dl_late) + '.')
    lines.append('Last business day of this week: ' + (fmt(bd_this[-1]) if bd_this else 'none') + '. Last business day of next week: ' + (fmt(bd_next[-1]) if bd_next else 'none') + '.')
    lines.append('First persuasion attempt date: ' + fmt(first_offer) + '.')
    lines.append('Weekday words: "this <weekday>" is the day in the current week (Monday to Sunday), "next <weekday>" is the day in the following calendar week:')
    for i in range(7):
        lines.append('- this ' + WD[i] + ' = ' + (monday + datetime.timedelta(days=i)).isoformat() + ', next ' + WD[i] + ' = ' + (monday + datetime.timedelta(days=7 + i)).isoformat())
    lines.append('Calendar (use it, never work out weekdays yourself):')
    end = max(dl_early, next_week[-1]) + datetime.timedelta(days=7)
    d = today
    while d <= end:
        if isbd(d):
            kind = 'business day'
        elif d.isoformat() in HOL:
            kind = 'bank holiday, NOT a business day'
        else:
            kind = 'weekend, NOT a business day'
        tag = ''
        if d == today:
            tag = ' (today)'
        elif d == today + one:
            tag = ' (tomorrow)'
        lines.append('- ' + fmt(d) + ': ' + kind + tag)
        d = d + one
    vars['date_facts'] = '\n'.join(lines)
    cb = []
    if hhmm < '19:00':
        start = '10:00' if hhmm < '10:00' else 'a time later than ' + hhmm
        cb.append('Today, ' + fmt(today) + ': from ' + start + ' up to 19:00 included.')
    else:
        cb.append('Today, ' + fmt(today) + ': no time left (it is already ' + hhmm + ').')
    cb.append('Next business day, ' + fmt(next_bd) + ': from 10:00 to 19:00, both included.')
    cb.append('No other day is allowed. Tomorrow counts only if tomorrow is ' + next_bd.isoformat() + '.')
    vars['callback_facts'] = 'It is now ' + hhmm + ' on ' + fmt(today) + '. A callback may be booked only:\n- ' + '\n- '.join(cb)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Date facts unavailable. Today is ' + str(vars.get('now')) + '.'
    vars['callback_facts'] = 'It is now ' + str(vars.get('now')) + '. A callback may be booked for today or the next business day, between 10:00 and 19:00 included, later than now.'
    vars['setup_state'] = 'error'
'''

ACCOUNT_CODE = r'''import datetime
import json
import re
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MO = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
def fmt(iso):
    d = datetime.date.fromisoformat(str(iso)[:10])
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MO[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
def money(x):
    try:
        return '{:,.2f}'.format(float(x))
    except Exception:
        return str(x)
def as_list(v):
    if isinstance(v, str):
        s = v.strip()
        try:
            v = json.loads(s)
        except Exception:
            try:
                import ast
                v = ast.literal_eval(s)
            except Exception:
                return None
    if isinstance(v, dict):
        v = v.get('products', v.get('data'))
        if isinstance(v, dict):
            v = v.get('products')
    if isinstance(v, list) and v and all(isinstance(p, dict) for p in v):
        return v
    return None
try:
    prods = None
    for key in ['products', 'get_account_response.data.products', 'load_account_response.data.products', 'get_account_response.data', 'load_account_response.data']:
        prods = as_list(vars.get(key))
        if prods:
            break
    if not prods:
        found = dict()
        pat = re.compile(r'products\.(\d+)\.(\w+)$')
        for k in list(vars.keys()):
            m = pat.search(str(k))
            if m:
                found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
        prods = [found[i] for i in sorted(found)] if found else None
    if not prods:
        raise ValueError('no products')
    prods = prods[:3]
    facts = []
    sentences = []
    for i, p in enumerate(prods, 1):
        pid = str(p.get('product_id'))
        typ = str(p.get('type'))
        if typ == 'credit_card':
            words = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        elif typ == 'car_loan':
            words = 'car loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        else:
            words = 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        days = int(float(p.get('days_late') or 0))
        if days <= 7:
            stage = 'early'
            attempts = 1
            deadline = vars.get('dl_early_iso')
        else:
            stage = 'late'
            attempts = 2
            deadline = vars.get('dl_late_iso')
        first = vars.get('first_offer_iso')
        if first and deadline and str(first) > str(deadline):
            first = deadline
        due = money(p.get('past_due'))
        fl = money(floor)
        vars['p' + str(i) + '_id'] = pid
        vars['p' + str(i) + '_words'] = words
        lines = ['Product ' + str(i) + ': product_id ' + pid + ', ' + words + '.',
                 '  Past due (full amount): ' + due + '. Days late: ' + str(days) + ', ' + stage + ' stage.',
                 '  Floor (' + floor_name + '): ' + fl + '. Accept any amount from ' + fl + ' to ' + due + ', both included.',
                 '  PTP deadline: ' + fmt(deadline) + '. A PTP date must be today or later, a business day, and not after this deadline.',
                 '  Persuasion attempts allowed: ' + str(attempts) + '.',
                 '  Attempt 1: propose ' + due + ' (or the floor ' + fl + ' if the customer already said the full amount is too much) on ' + fmt(first) + '.']
        if attempts == 2:
            lines.append('  Attempt 2: propose the floor ' + fl + ' on the deadline ' + fmt(deadline) + '.')
        else:
            lines.append('  There is no second attempt for this product.')
        facts.append('\n'.join(lines))
        dword = ' day late' if days == 1 else ' days late'
        sentences.append('Your ' + words + ' has a past-due amount of ' + due + ' and is ' + str(days) + dword + '.')
    n = len(prods)
    vars['product_count'] = n
    vars['account_facts'] = str(n) + ' late product(s), in the order to discuss them:\n' + '\n'.join(facts)
    who = str(vars.get('title') or '') + ' ' + str(vars.get('last_name') or '')
    if n == 1:
        head = 'Thank you, ' + who.strip() + ', your identity is verified. I am calling from the Freya Bank collections team about a late payment. '
        ask = ' Can you make this payment today?'
    else:
        head = 'Thank you, ' + who.strip() + ', your identity is verified. I am calling from the Freya Bank collections team about late payments on ' + str(n) + ' products. '
        ask = ' Can you make all of these payments today?'
    vars['overdue_statement'] = head + ' '.join(sentences) + ask
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_facts'] = 'Account details unavailable.'
    vars['overdue_statement'] = 'Thank you.'
    vars['account_state'] = 'error'
'''

ORDINAL = {5: "5th", 7: "7th", 12: "12th"}


def setup_code():
    # CP-4 2.5 b: early 12th business day; late 7th per memo OPS-2026-41 item 3.
    return (SETUP_CODE.replace("HOLIDAY_LIST", repr(HOLIDAYS)).replace("EARLY_N", "12").replace("LATE_N", "7")
            .replace("EARLY_WORD", ORDINAL[12]).replace("LATE_WORD", ORDINAL[7]))


# ------------------------------------------------------------------ prompts

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. Keep every turn to one or two short sentences and ask one question at a time.
The customer is {{title}} {{first_name}} {{last_name}}. Address the customer as {{title}} {{last_name}}.

Rules for every step:
- Never improvise. Never offer a discount, a waiver, an instalment plan, a payment plan or any term that is not in your instructions.
- If asked something your instructions and tool results do not answer, say you do not have that information. Never invent figures, dates or reasons.
- If asked whether this call is a scam: say they can verify the call by phoning Freya Bank's customer service number, then go on.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then go on.
- Never say that something is recorded, booked, saved or done unless its tool result says so. If a tool call fails, say so honestly.
- After every tool result, either speak to the customer or call the next tool. Never end a turn with nothing. When a tool result contains what_to_do_next, follow it.
- Tools whose names start with transition_to_ move the call on. When a rule says to call one, call it; saying it is not enough. Call a transition tool alone, never together with another tool in the same message. When you call a transition tool that leads to bye_, route_, transfer_ or wrap_up, do not say goodbye yourself: the closing words are spoken for you.
- Use only the tools of the current step."""

NO_REASON = "Until identity is verified you never say \"collections\", \"debt\", \"payment\", \"overdue\" or the name of any product, and you never say why you are calling, to anyone, relatives included. If asked why you call, say you can only discuss it with {{title}} {{last_name}} personally."

OPENING_TASK = f"""The opening sentence and the question "Am I speaking with {{{{title}}}} {{{{last_name}}}}?" were already said. Your only job: find out whether the person on the line is {{{{title}}}} {{{{first_name}}}} {{{{last_name}}}}.
{NO_REASON}

- Only "yes", "that's me", "speaking" or the customer saying their own name confirms. Then call transition_to_security at once, with no text.
- "Hello", "go ahead", "who is this" or any other unclear reply does not confirm. Ask once more: "Am I speaking with {{{{title}}}} {{{{last_name}}}}?" If after this second ask it is still unclear, call transition_to_bye_unclear.
- If the person asks a robot or scam question instead of answering, answer it first; the ask that follows counts as the second ask.
- Someone else answered (a relative, a colleague, "he is not here", "she is busy", "can I take a message"): call transition_to_third_party, with no text.
- The person says this number does not belong to {{{{first_name}}}} {{{{last_name}}}}: call transition_to_bye_wrong_number.
- The person says the customer has died: call transition_to_bye_deceased with no text at all. Do not say anything yourself.
- The person says twice that they do not want to talk: call transition_to_bye_declined.
- The person asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
Do not call any bank tool in this step."""

THIRD_PARTY_TASK = f"""Someone other than {{{{title}}}} {{{{last_name}}}} is on the line. You say nothing beyond the opening sentence about who you are, and you never say why you are calling. You never ask this person security questions and never tell them anything about the account, even if they offer to pay.
{NO_REASON}
Ask when {{{{title}}}} {{{{last_name}}}} can be reached.

CALLBACK WINDOW:
{{{{callback_facts}}}}

- When the person names a day and a time inside the window, call schedule_callback with the date as YYYY-MM-DD and the time as HH:MM on the 24-hour clock ("3 pm" is 15:00, "half past ten" is 10:30). If they name only a time, it means today; if they name only a day, ask for the time.
- If only a vague time is given ("later", "in the afternoon"), ask for an exact time. That is not yet an offer outside the window.
- If the day or time offered is outside the window, say you can only arrange a call back within the window, and ask once for another time. If the next time offered is outside the window too, or they cannot give one, call transition_to_bye_no_callback. Never book a time outside the window.
- If schedule_callback fails, say it could not be booked and follow what_to_do_next.
- The person says the number does not belong to {{{{first_name}}}} {{{{last_name}}}}: call transition_to_bye_wrong_number.
- The person says the customer has died: call transition_to_bye_deceased with no text at all.
- If {{{{title}}}} {{{{last_name}}}} comes to the phone and confirms being them: call transition_to_security.
Do not call any tool other than schedule_callback and the transition tools."""

SECURITY_TASK = f"""{{{{title}}}} {{{{last_name}}}} confirmed who they are. Verify their identity with two questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
{NO_REASON}

Tool rules:
- Call verify_identity once for every answer the customer gives. For the date of birth send field date_of_birth and the date as YYYY-MM-DD, whatever way the customer said it ("the fifth of March nineteen eighty" is 1980-03-05). A date given only in numbers is read as day, then month, then year ("05/03/1980" and "5 3 80" are 1980-03-05). For the phone send field phone_last4 and exactly four digits.
- If the customer gives an answer in pieces, wait until it is complete before you call the tool.
- Follow what_to_do_next in each result. A wrong answer may be asked again. If the result says day and month look swapped, ask them to say the month as a word; that retry is not a wrong answer.
- Three wrong answers in total end the check. When the result says no wrong answers are left, call transition_to_bye_failed. Never state anything about the account.

Other situations:
- The customer does not want to answer, or asks what the call is about instead of answering: the first time, explain once that these questions protect their account, and ask the question again. The second time (another refusal or another such question), call transition_to_bye_declined.
- The customer says twice that they do not want to talk: call transition_to_bye_declined.
- The customer asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
Do not call any tool other than verify_identity and the transition tools."""

PTP_RULES = """HOW TO GET A PTP (promise to pay)
1. A date or an amount that the customer proposes is never a refusal. Check it under the date and amount rules below.
2. A flat refusal or a non-answer uses one persuasion attempt of that product. "No" to paying today, with no date and no amount, is a flat refusal. Refusing an offer you made is a flat refusal.
   - Attempt 1: propose the amount and date given as Attempt 1 in ACCOUNT (the full past-due amount, or the floor if the customer already said the full amount is too much).
   - Attempt 2 (late stage only): propose the floor amount on the product's deadline.
   - When the product's attempts are used up, stop. Never repeat an offer the customer already refused, and never invent another offer.
3. AMOUNTS: ask for the full past-due amount first. Never ask "how much can you pay?"; you propose every amount yourself.
   - If the customer says the full amount is too much, offer the floor once and say that the rest stays overdue. Refusing the floor is a flat refusal.
   - An amount the customer proposes from the floor up to the full amount, both included, is accepted.
   - An amount below the floor: say it cannot be recorded and offer the floor once. If they do not accept it, that is a flat refusal.
   - If the customer names only a date, the amount is the full past-due amount unless the floor was already agreed.
4. DATES: a PTP date must be today or later, a business day, and not after the product's deadline. Read weekdays and dates only from CALENDAR.
   - A weekend day or a bank holiday that is not after the deadline: offer the next business day.
   - "Next <weekday>" means that weekday in the following calendar week; "this <weekday>" means the one in the current week. Use the table in CALENDAR.
   - A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still name none, propose the deadline.
   - A date after the deadline: say the latest date you can record is the deadline, and offer it. Refusing the deadline is a flat refusal.
5. HARDSHIP: illness, a death in the family or job loss: say one short sentence of sympathy and make no persuasion attempt. Offer to connect them with the customer support team. This comes before the persuasion rules. If they still name a date or an amount themselves, handle it as a normal PTP.
6. ALREADY PAID: "I already paid" this past-due amount: tell them payments can take one business day to appear. No PTP. A claim that the product was closed or paid off in the past is a dispute, not a payment.
7. DISPUTE: "this debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no PTP.
8. A recorded PTP cannot be changed or cancelled in this call; if asked, say they can change it in the mobile app."""

A_NEGOTIATE_TASK = """The customer is verified. You already told them what is overdue and asked "Can you make this payment today?". Now get a promise to pay (PTP) under the rules below and record it.

ACCOUNT:
{{account_facts}}

TOOL AND STEP RULES (when a rule says to call a tool, call it):
- create_promise: call it only after you read back the product in words, the amount and the date, asked "Do you confirm?", and got a clear yes. Use the product_id from ACCOUNT, the amount as a number and the date as YYYY-MM-DD. If the customer changes the date or the amount at the read-back, check the new value under the rules and read back again. Only one PTP for this product. Do not say goodbye after the result: the next words are spoken for you.
- If create_promise fails, follow what_to_do_next.
- transition_to_transfer_support: the customer in hardship accepted to be connected with the customer support team.
- transition_to_bye_hardship: the customer in hardship declined the customer support team and named no date or amount.
- transition_to_transfer_restructuring: the customer asks for a new payment plan or lower instalments. Describe no plan, just say you will connect them.
- transition_to_transfer_general: the customer asks for a human; first ask once whether you can help. If they insist, call it.
- transition_to_bye_paid: the customer says they already paid this past-due amount (say first that payments can take one business day to appear).
- transition_to_bye_dispute: dispute as in rule 7.
- transition_to_bye_refused: the persuasion attempts are used up, or the customer said twice that they do not want to talk.

""" + PTP_RULES + """

CALENDAR:
{{date_facts}}"""

B_NEGOTIATE_TASK = """The customer is verified. You already told them every late product and asked whether they can make all of these payments today. Now get promises to pay (PTP) under the rules below and record them.

ACCOUNT:
{{account_facts}}

ORDER OF THE CALL (several products):
- The first ask covered all products at once. If the customer cannot pay all of them today, take the products one at a time, in the order of ACCOUNT. Do not ask about today again for each product. Every product starts at its Attempt 1.
- Each product has its own stage, deadline, floor and number of persuasion attempts. Count attempts separately for each product.
- If the customer names one date for everything and that date is after the deadline of a product, that product gets its own deadline and the read-back says so. The other products keep the date the customer named.
- A dispute or an "I already paid" about one product does not end the call: tell them you have taken note of it for that product, and go on with the next product.
- When every product has an agreed PTP or has ended without one, read ALL agreed PTPs back together (product in words, amount, date for each) and ask once "Do you confirm?". After a clear yes, call create_promise once for each agreed product. If the customer changes a date or an amount at the read-back, check it under the rules and read back again.
- After the create_promise results: tell the customer which PTPs are recorded and which could not be recorded. If at least one is recorded, say: "You will receive a text message confirming this promise." Then call transition_to_wrap_up.
- If no product got an agreed PTP, call transition_to_wrap_up as soon as the last product has ended.

TOOL AND STEP RULES (when a rule says to call a tool, call it):
- create_promise: one call per product, only after the joint read-back got a clear yes. Use the product_id from ACCOUNT, the amount as a number and the date as YYYY-MM-DD. If a call fails, follow what_to_do_next: try once more for that product; if it fails again, say you could not record that PTP. PTPs already recorded stay.
- transition_to_wrap_up: every product has ended (recorded, failed twice, refused, hardship declined, dispute or paid). Call it only after all create_promise results have arrived.
- transition_to_transfer_support: the customer in hardship accepted to be connected with the customer support team.
- transition_to_transfer_restructuring: the customer asks for a new payment plan or lower instalments. Describe no plan. PTPs already recorded stay; PTPs agreed but not yet recorded are not recorded.
- transition_to_transfer_general: the customer asks for a human; first ask once whether you can help. If they insist, call it.
- If the customer in hardship declines the support team, that product and the remaining products without a PTP end as hardship, unless the customer names a date or amount themselves.
- If the customer says twice that they do not want to talk, the remaining products end as refused: call transition_to_wrap_up (after recording any PTP already confirmed).

""" + PTP_RULES + """

CALENDAR:
{{date_facts}}"""

B_WRAP_TASK = """The conversation about the products is over. Do not ask the customer anything more.

ACCOUNT:
{{account_facts}}

Step 1: for every product in ACCOUNT that has NO recorded promise (create_promise did not return ok for it), call add_note with that product's product_id and one reason:
- refused: the customer refused, the attempts were used up, or the customer did not want to talk
- hardship: hardship, and the customer declined the support team
- dispute: not theirs, never had it, or closed or paid off in the past
- paid: the customer already paid this past-due amount
- service_error: create_promise failed twice for it
Never add a note for a product with a recorded promise. Make all add_note calls together in one message, with no text. If every product has a recorded promise, skip step 1.

Step 2: after all add_note results have arrived (or at once if no note was needed), call exactly one transition:
- transition_to_route_promise: at least one promise was recorded in this call.
- transition_to_route_paid: no promise was recorded and every product was noted paid.
- otherwise the reason of the FIRST product in ACCOUNT order whose note is not paid: transition_to_route_refused, transition_to_route_hardship, transition_to_route_dispute or transition_to_route_service_error.
Do not say anything to the customer in this step; the closing words are spoken for you."""


# ------------------------------------------------------------------ endings

def close_node(key, outcome, reason=None):
    fields = {"outcome": outcome}
    if reason:
        fields["reason"] = reason
    return {
        "name": key, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "hang_up",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [engine_call("close_call", fields, max_retries=2)],
        "response_mapping": [], "transitions": [always("hang_up")],
    }


def say_node(key, text, target):
    return {
        "name": key, "node_type": "conversation", "passthrough": True, "passthrough_default_transition": target,
        "on_enter": {"type": "tts", "text": text}, "disable_inactivity_monitor": True,
        "task_message": "Do not call a tool in this turn.", "transitions": [always(target)],
    }


THANKS = "Thank you for your time, {{title}} {{last_name}}. Goodbye."


def build(slot, multi):
    nodes = {}

    nodes["setup"] = code_node("setup", setup_code(), "opening")

    def bank_node(key, task, tools, transitions, on_enter, cap, cap_target, first_only=True, loop_prompt=None):
        n = {
            "name": key, "node_type": "conversation", "task_message": task, "tools": tools,
            "on_enter": on_enter, "on_enter_first_entry_only": first_only,
            "max_node_turns": cap, "max_turn_transition": cap_target, "transitions": transitions,
        }
        return n

    nodes["opening"] = bank_node(
        "opening", OPENING_TASK, [],
        [
            tool_go("security", "The person confirmed being the customer: yes, that's me, speaking, or said their own name."),
            tool_go("third_party", "Someone other than the customer answered the phone."),
            tool_go("bye_wrong_number", "The person says this number does not belong to the customer."),
            tool_go("bye_deceased", "The person says the customer has died."),
            tool_go("bye_unclear", "It is still unclear who answered after the second ask."),
            tool_go("bye_declined", "The person said twice that they do not want to talk."),
            tool_go("transfer_general", "The person insisted on talking to a human after being asked once whether you can help."),
        ],
        {"type": "tts", "text": "Hello, this is the digital assistant of Freya Bank calling. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
        8, "bye_unclear")

    nodes["third_party"] = bank_node(
        "third_party", THIRD_PARTY_TASK, [callback_tool()],
        [
            {"target_node": "bye_callback", "description": "The callback was booked",
             "condition": any_of(*is_true("schedule_callback_response.data.ok"))},
            tool_go("bye_no_callback", "No callback time inside the window after asking once more, or no time given."),
            tool_go("bye_wrong_number", "The person says this number does not belong to the customer."),
            tool_go("bye_deceased", "The person says the customer has died."),
            tool_go("security", "The customer came to the phone and confirmed being the customer."),
        ],
        {"type": "llm", "prompt": "If the person already said when the customer can be reached, check that time against the window and act on it. Otherwise ask, without saying why you are calling, when {{title}} {{last_name}} can be reached."},
        10, "bye_no_callback")

    nodes["security"] = bank_node(
        "security", SECURITY_TASK, [verify_tool()],
        [
            {"target_node": "load_account", "description": "Both security answers passed",
             "condition": any_of(*is_true("verify_identity_response.data.all_verified"))},
            {"target_node": "bye_failed", "description": "Three wrong answers in total",
             "condition": any_of(var("verify_identity_response.data.wrong_answers_left", "equals", "0"))},
            tool_go("bye_failed", "The tool result says no wrong answers are left; the check has ended."),
            tool_go("bye_declined", "The customer refused the security questions a second time, asked a second time what the call is about instead of answering, or said twice that they do not want to talk."),
            tool_go("transfer_general", "The customer insisted on talking to a human after being asked once whether you can help."),
        ],
        {"type": "tts", "text": "Thank you. Before I go on, I need to confirm your identity. Could you tell me your date of birth, please?"},
        14, "bye_declined")

    nodes["load_account"] = {
        "name": "load_account", "node_type": "api_request", "passthrough": True,
        "passthrough_default_transition": "prepare_account", "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "pre_actions": [api_tool("get_account", "Get the late products.", {}, [], max_retries=2)],
        "response_mapping": [{"path": "data.products", "variable": "products"}, {"path": "data.ok", "variable": "account_ok"}],
        "transitions": [always("prepare_account")],
    }
    # the get_account pre_action must not carry model-facing hooks; strip response_mapping kept at node level
    nodes["prepare_account"] = code_node(
        "prepare_account", ACCOUNT_CODE, "bye_account_error",
        [{"target_node": "negotiate", "description": "The account was read",
          "condition": any_of(var("account_state", "equals", "ok"))}])

    transfers = [
        tool_go("transfer_support", "The customer in hardship accepted to be connected with the customer support team."),
        tool_go("transfer_restructuring", "The customer asked for a new payment plan or lower instalments."),
        tool_go("transfer_general", "The customer insisted on talking to a human after being asked once whether you can help."),
    ]
    if not multi:
        neg_tools = [promise_tool()]
        neg_transitions = [
            {"target_node": "bye_promise", "description": "The promise was recorded",
             "condition": any_of(var("create_promise_success_count", "greater_than", 0))},
            {"target_node": "bye_service_error", "description": "create_promise failed twice",
             "condition": any_of(var("create_promise_failure_count", "greater_than", 1))},
        ] + transfers + [
            tool_go("bye_hardship", "The customer in hardship declined the customer support team and named no date or amount."),
            tool_go("bye_paid", "The customer already paid this past-due amount."),
            tool_go("bye_dispute", "The customer disputes the debt: not theirs, never had the product, or it was closed or paid off in the past."),
            tool_go("bye_refused", "The persuasion attempts are used up, or the customer said twice that they do not want to talk."),
        ]
        neg_task, cap_target = A_NEGOTIATE_TASK, "bye_refused"
    else:
        neg_tools = [promise_tool()]
        neg_transitions = transfers + [
            tool_go("wrap_up", "Every product has ended and all create_promise results have arrived."),
        ]
        neg_task, cap_target = B_NEGOTIATE_TASK, "wrap_up"
    nodes["negotiate"] = bank_node(
        "negotiate", neg_task, neg_tools, neg_transitions,
        {"type": "tts", "text": "{{overdue_statement}}"}, 60, cap_target)

    if multi:
        nodes["wrap_up"] = bank_node(
            "wrap_up", B_WRAP_TASK, [note_tool()],
            [tool_go("route_" + r, d) for r, d in [
                ("promise", "At least one promise was recorded in this call."),
                ("paid", "No promise was recorded and every product was noted paid."),
                ("refused", "No promise recorded; the first product not noted paid was noted refused."),
                ("hardship", "No promise recorded; the first product not noted paid was noted hardship."),
                ("dispute", "No promise recorded; the first product not noted paid was noted dispute."),
                ("service_error", "No promise recorded; the first product not noted paid was noted service_error."),
            ]],
            {"type": "llm", "prompt": "Make the add_note calls now, all in one message and with no text, or call the closing transition at once if no note is needed."},
            6, "route_refused")
        # CN-12 E: promise whenever at least one PTP was recorded (transfers excluded, they never pass here).
        for r in ["promise", "paid", "refused", "hardship", "dispute", "service_error"]:
            fallback = "bye_refused" if r == "promise" else "bye_" + r
            nodes["route_" + r] = {
                "name": "route_" + r, "node_type": "conversation", "passthrough": True,
                "passthrough_default_transition": fallback, "on_enter": {"type": "silent"},
                "disable_inactivity_monitor": True, "task_message": "Do not call a tool in this turn.",
                "transitions": [
                    {"target_node": "bye_promise", "description": "at least one promise recorded",
                     "condition": any_of(var("create_promise_success_count", "greater_than", 0))},
                    always(fallback)],
            }

    # farewells (thanks and goodbye before every close) and the close steps
    endings = {
        # key: (spoken line, outcome, reason)
        "promise": (("Your promise is recorded. " if not multi else "") + "You will receive a text message confirming this promise. " + THANKS, "promise", None),
        "paid": (("Payments can take one business day to appear. " if not multi else "") + THANKS, "paid", None),
        "refused": ("I understand. " + THANKS, "no_promise", "refused"),
        "hardship": ("I understand. " + THANKS, "no_promise", "hardship"),
        "dispute": ("I understand. " + THANKS, "no_promise", "dispute"),
        "service_error": (("I am sorry, I could not record your promise because of a technical problem. " if not multi else "") + THANKS, "no_promise", "service_error"),
        "failed": ("I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. " + THANKS, "not_verified", "failed"),
        "declined": ("I understand. Thank you for your time. Goodbye.", "not_verified", "declined"),
        "callback": ("Thank you, we will call back then. Goodbye.", "not_reached", "callback"),
        "no_callback": ("Thank you, we will try again another time. Goodbye.", "not_reached", "no_callback"),
        "wrong_number": ("I apologise for the inconvenience. Thank you, goodbye.", "not_reached", "wrong_number"),
        "deceased": ("I am sorry for your loss. Thank you, goodbye.", "not_reached", "deceased"),
        "unclear": ("Thank you. Goodbye.", "not_reached", "unclear"),
    }
    for key, (text, outcome, reason) in endings.items():
        close_key = "close_" + outcome + ("_" + reason if reason else "")
        nodes["bye_" + key] = say_node("bye_" + key, text, close_key)
        nodes[close_key] = close_node(close_key, outcome, reason)
    # get_account failed: say so, close as service error
    nodes["bye_account_error"] = say_node(
        "bye_account_error", "I am sorry, I cannot access your account details right now because of a technical problem. " + THANKS,
        "close_no_promise_service_error")

    teams = {"restructuring": "restructuring team", "general": "colleagues in customer service", "support": "customer support team"}
    queue_reason = {"restructuring": "restructuring", "general": "human", "support": "support"}
    for q, team in teams.items():
        key = "transfer_" + q
        close_key = "close_transferred_" + queue_reason[q]
        nodes[key] = {
            "name": key, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": close_key,
            "on_enter": {"type": "tts", "text": f"I am connecting you with our {team} now. Thank you for your time. Goodbye."},
            "disable_inactivity_monitor": True,
            "pre_actions": [engine_call("transfer_to_agent", {"queue": q}, max_retries=0)],
            "response_mapping": [{"path": "data.ok", "variable": key + "_ok"}],
            "transitions": [
                {"target_node": key + "_failed", "description": "the transfer failed",
                 "condition": any_of(var(key + "_failure_count", "greater_than", 0),
                                     var(key + "_ok", "equals", "false"), var(key + "_ok", "equals", "False"))},
                always(close_key)],
        }
        nodes[key + "_failed"] = say_node(
            key + "_failed", "I am sorry, the transfer did not go through. Please call Freya Bank's customer service number. Goodbye.", close_key)
        nodes[close_key] = close_node(close_key, "transferred", queue_reason[q])

    nodes["hang_up"] = {
        "name": "hang_up", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "transitions": [], "terminal": {"type": "function", "function": {
            "name": "call_closed", "handler": "__function__:end_call",
            "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
    }

    wf = {
        "initial_node": "setup",
        "system_prompt": SYSTEM,
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    }
    return wf


CONTRACT_EVIDENCE = [
    {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
    {"source": "briefs/brief-a-raw.md", "quote": "Every call ends with exactly one `close_call`, as the last tool call, with an outcome and, where the list gives one, a reason."},
]


def main():
    out = ROOT / "out"
    for slot, multi, extra in [("brief-a-raw", False, []),
                               ("brief-b-raw", True, [{"source": "briefs/brief-b-raw.md", "quote": "The close code list still applies."}])]:
        wf = build(slot, multi)
        (out / f"{slot}.workflow.json").write_text(json.dumps(wf, indent=1, ensure_ascii=False) + "\n")
        contract = {"terminal_tools": [{"tool": "close_call", "evidence": CONTRACT_EVIDENCE + extra}],
                    "every_call_ends_with_terminal": True}
        (out / f"{slot}.contract.json").write_text(json.dumps(contract, indent=1) + "\n")
        print("wrote", slot, len(wf["nodes"]), "steps")


if __name__ == "__main__":
    main()
