"""Generate the workflows for brief-a-raw (one product) and brief-b-raw (one to three products).

    python3 builder/gen_workflows.py

Writes out/brief-a-raw.workflow.json, out/brief-b-raw.workflow.json and their contracts.
"""
import json
import sys
from pathlib import Path

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
OUT = Path(__file__).resolve().parent.parent / "out"

# Holiday calendar after memo OPS-2026-41 item 1.
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]

# ------------------------------------------------------------------ code snippets (no double braces allowed)

HELPERS = r'''
import datetime, json
HOLIDAYS = set(__HOLIDAYS__)
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)

def parse_now():
    s = str(vars.get('now') or '').strip()
    try:
        return datetime.datetime.fromisoformat(s[:16])
    except Exception:
        pass
    try:
        return datetime.datetime.strptime(s[:10], '%Y-%m-%d')
    except Exception:
        return None

def is_bd(d):
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS

def nth_bd_after(d, n):
    c = 0
    x = d
    while c < n:
        x = x + ONE
        if is_bd(x):
            c += 1
    return x

def next_bd_after(d):
    x = d + ONE
    while not is_bd(x):
        x = x + ONE
    return x

def spoken(d):
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year)

def lab(d):
    return spoken(d) + ' (' + d.isoformat() + ')'

def last_bd_of_week(d):
    mon = d - datetime.timedelta(days=d.weekday())
    for i in range(6, -1, -1):
        x = mon + datetime.timedelta(days=i)
        if is_bd(x):
            return x
    return None

def attempt1_date(today):
    x = last_bd_of_week(today)
    if x is None or x <= today:
        x = last_bd_of_week(today + datetime.timedelta(days=7))
    return x

def money(v):
    try:
        return '{:,.2f}'.format(float(v))
    except Exception:
        return str(v)

def num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except Exception:
        return v
'''.replace("__HOLIDAYS__", repr(HOLIDAYS))

SETUP_CODE = HELPERS + r'''
try:
    now = parse_now()
    today = now.date()
    vars['today_iso'] = today.isoformat()
    vars['today_spoken'] = spoken(today)
    hhmm = now.strftime('%H:%M')
    mon = today - datetime.timedelta(days=today.weekday())
    weeks = ['this week', 'next week', 'the week after next']
    lines = []
    for i in range(21):
        d = mon + datetime.timedelta(days=i)
        w = weeks[i // 7]
        if d < today:
            st = 'past, not allowed'
        elif is_bd(d):
            st = 'business day' + (' (TODAY)' if d == today else '')
        else:
            kind = 'bank holiday' if d.isoformat() in HOLIDAYS else 'weekend'
            st = kind + ', not a business day; next business day: ' + lab(next_bd_after(d)) + (' (TODAY)' if d == today else '')
        lines.append('- ' + d.isoformat() + ' ' + WD[d.weekday()] + ', ' + w + ': ' + st)
    names = []
    for k in range(7):
        t = mon + datetime.timedelta(days=k)
        n = t + datetime.timedelta(days=7)
        names.append('"this ' + WD[k] + '" = ' + t.isoformat() + ', "next ' + WD[k] + '" = ' + n.isoformat())
    vars['date_facts'] = ('Today is ' + lab(today) + ', time ' + hhmm + '. Weeks run Monday to Sunday. Bank holidays: ' + ', '.join(sorted(HOLIDAYS)) + '.\n'
                          + '\n'.join(lines) + '\nWeekday names: ' + '; '.join(names) + '.')
    nbd = next_bd_after(today)
    if now.hour < 19:
        tpart = 'today, ' + lab(today) + ', at a time later than ' + hhmm + ' and no later than 19:00 (and not before 10:00)'
    else:
        tpart = 'not today any more (it is after 19:00)'
    vars['callback_facts'] = ('A callback can be booked ' + tpart + ', or on the next business day, ' + lab(nbd)
                              + ', from 10:00 to 19:00, both included. Any other day or time is outside the window. "Tomorrow" is '
                              + lab(today + ONE) + '.')
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Current date and time: ' + str(vars.get('now'))
    vars['callback_facts'] = 'Today or the next business day, from 10:00 to 19:00, later than now (' + str(vars.get('now')) + ').'
    vars['today_spoken'] = str(vars.get('now'))
    vars['setup_state'] = 'error ' + str(e)
'''

ACCOUNT_CODE = HELPERS + r'''
def as_list(p):
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            try:
                p = json.loads(p.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
            except Exception:
                p = None
    if isinstance(p, dict) and isinstance(p.get('products'), list):
        p = p.get('products')
    if isinstance(p, list) and p and all(isinstance(x, dict) for x in p):
        return p
    return None

def flat(prefix):
    items = []
    for i in range(6):
        base = prefix + '.' + str(i) + '.'
        row = dict()
        for k in list(vars.keys()):
            if isinstance(k, str) and k.startswith(base):
                row[k[len(base):]] = vars.get(k)
        if row:
            items.append(row)
        else:
            break
    return items or None

def products():
    for key in ('products', 'load_account_response.data.products', 'load_account_response.data', 'load_account_response'):
        got = as_list(vars.get(key))
        if got:
            return got
    resp = vars.get('load_account_response')
    if isinstance(resp, dict):
        got = as_list((resp.get('data') or dict()).get('products') if isinstance(resp.get('data'), dict) else None)
        if got:
            return got
    for prefix in ('load_account_response.data.products', 'products'):
        got = flat(prefix)
        if got:
            return got
    return None

try:
    now = parse_now()
    today = now.date()
    prods = products()
    if not prods:
        raise ValueError('no products')
    facts = []
    sentences = []
    listing = []
    for i, p in enumerate(prods):
        pid = str(p.get('product_id'))
        typ = str(p.get('type'))
        if typ == 'credit_card':
            name = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        elif typ == 'car_loan':
            name = 'car loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        else:
            name = 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        past_due = p.get('past_due')
        if floor is None or str(floor) == '':
            floor = past_due
        days = int(float(p.get('days_late') or 0))
        if days <= 7:
            stage, nth, attempts = 'early', 12, 1
        else:
            stage, nth, attempts = 'late', 7, 2
        deadline = nth_bd_after(today, nth)
        a1 = attempt1_date(today)
        if a1 > deadline:
            a1 = deadline
        valid = []
        d = today
        while d <= deadline:
            if is_bd(d):
                valid.append(d.isoformat() + ' ' + WD[d.weekday()][:3])
            d = d + ONE
        f = []
        f.append('Product ' + str(i + 1) + ': ' + name + ' (product_id ' + pid + ').')
        f.append('- Full past-due amount: ' + money(past_due) + ' (send as ' + str(num(past_due)) + '). Days late: ' + str(days) + '.')
        f.append('- Floor (' + floor_name + '): ' + money(floor) + ' (send as ' + str(num(floor)) + ').')
        f.append('- Stage: ' + stage + '. Persuasion attempts allowed: ' + str(attempts) + '.')
        f.append('- PTP deadline (' + str(nth) + 'th business day after today): ' + lab(deadline) + '. Nothing after it can be recorded.')
        f.append('- Valid PTP dates (business days from today to the deadline): ' + ', '.join(valid) + '.')
        f.append('- Persuasion attempt 1: propose ' + money(past_due) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much) on ' + lab(a1) + '.')
        if attempts >= 2:
            f.append('- Persuasion attempt 2: propose the floor ' + money(floor) + ' on the deadline, ' + lab(deadline) + '.')
        else:
            f.append('- No persuasion attempt 2 (early stage). When attempt 1 is refused, stop.')
        facts.append('\n'.join(f))
        sentences.append('Your ' + name + ' has a past-due amount of ' + money(past_due) + ' and is ' + str(days) + ' day' + ('' if days == 1 else 's') + ' late.')
        listing.append(str(i + 1) + '. product_id ' + pid + ': ' + name)
        if i == 0:
            vars['first_product_id'] = pid
    vars['product_facts'] = '\n\n'.join(facts)
    vars['product_list'] = '; '.join(listing)
    vars['product_count'] = str(len(prods))
    ask = 'Can you make this payment today?' if len(prods) == 1 else 'Can you pay all of them today?'
    vars['statement_text'] = ' '.join(sentences) + ' ' + ask
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_state'] = 'failed'
    vars['account_error'] = str(e)
'''

# ------------------------------------------------------------------ tool builders

def api_tool(name, path, body_fields, required, description="", config=None, post=None, pre=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(body_fields)
    t = {
        "type": "function",
        "config": config or {"timeoutMs": 12000, "maxRetries": 0},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": BASE + path},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": props, "required": required},
                },
            },
        },
    }
    if post:
        t["post_process_code"] = post
    if pre:
        t["pre_process_code"] = pre
    return t


def hook(body):
    """A post-hook that drops headers and adds what_to_do_next to result['data']."""
    return ("try:\n"
            "    if isinstance(result, dict):\n"
            "        result.pop('header', None)\n"
            "        d = result.get('data')\n"
            "        if not isinstance(d, dict):\n"
            "            d = dict()\n"
            "            d['ok'] = False\n"
            "            d['error'] = 'service failed, status ' + str(result.get('status_code'))\n"
            "            result['data'] = d\n"
            "        ok = str(d.get('ok')).lower() == 'true'\n"
            + "\n".join("        " + line for line in body.strip("\n").split("\n")) + "\n"
            "except Exception:\n"
            "    pass\n")


VERIFY_HOOK = hook('''
left = d.get('wrong_answers_left')
if str(d.get('all_verified')).lower() == 'true':
    d['what_to_do_next'] = 'Both security answers are verified.'
elif d.get('hint') == 'day_month_swapped':
    d['what_to_do_next'] = 'Not verified yet: the day and month seem swapped. Ask the customer to say the month of birth as a word, then call verify_identity again. This retry is not a wrong answer.'
elif str(d.get('verified')).lower() == 'true':
    d['what_to_do_next'] = 'This answer is correct. Now ask for the last four digits of the phone number on file (if that is the question still open).'
elif str(left) == '0':
    d['what_to_do_next'] = 'Three wrong answers: the check has ended. Do not state anything about the account.'
elif str(d.get('verified')).lower() == 'false':
    d['what_to_do_next'] = 'This answer is wrong. Wrong answers left: ' + str(left) + '. Ask the same question again, without any hint.'
elif not ok:
    d['what_to_do_next'] = 'The answer could not be checked (' + str(d.get('error')) + '). It does not count as wrong. Ask the customer to repeat it, for a date of birth as day, month and year.'
''')

PROMISE_HOOK = hook('''
if ok:
    d['what_to_do_next'] = 'This promise is recorded.'
else:
    d['what_to_do_next'] = 'This promise is NOT recorded (' + str(d.get('error')) + '). If this is the first failure for this product, call create_promise again now with the same values, without asking the customer. If it already failed once for this product, tell the customer you could not record it. Never say it is recorded.'
''')

CALLBACK_HOOK = hook('''
if ok:
    d['what_to_do_next'] = 'The callback is booked.'
else:
    d['what_to_do_next'] = 'The callback is NOT booked (' + str(d.get('error')) + '). If this is the first failure, call schedule_callback again now with the same values. Never say it is booked.'
''')

NOTE_HOOK = hook('''
if ok:
    d['what_to_do_next'] = 'The note is saved.'
else:
    d['what_to_do_next'] = 'The note is NOT saved (' + str(d.get('error')) + '). Call add_note once more with the same values.'
''')


def verify_tool():
    return api_tool("verify_identity", "/verify_identity", {
        "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                  "description": "Which question this answer is for. One of: date_of_birth, phone_last4."},
        "answer": {"type": "string", "default": "{{answer}}",
                   "description": "date_of_birth as YYYY-MM-DD (numbers only are read day, month, year). phone_last4 as four digits."},
    }, ["customer_id", "field", "answer"],
        "Check one security answer. CALL it every time the customer gives an answer to a security question, one answer per call.",
        post=VERIFY_HOOK)


def promise_tool(multi):
    fields = {
        "amount": {"type": "number", "default": "{{amount}}", "description": "Agreed amount as a number, for example 412.5."},
        "date": {"type": "string", "default": "{{date}}", "description": "Agreed payment date as YYYY-MM-DD."},
    }
    if multi:
        fields["product_id"] = {"type": "string", "default": "{{product_id}}",
                                "description": "product_id exactly as in the account facts, for example p1. Copy it unchanged."}
    else:
        fields["product_id"] = {"type": "string", "default": "{{first_product_id}}"}
    desc = ("Record one PTP for one product. CALL it only after the customer gave a clear yes to the read-back. "
            + ("Call it once for each product with an agreed PTP." if multi else "One PTP per product."))
    return api_tool("create_promise", "/create_promise", fields, ["customer_id", "product_id", "amount", "date"], desc, post=PROMISE_HOOK)


def callback_tool():
    return api_tool("schedule_callback", "/schedule_callback", {
        "date": {"type": "string", "default": "{{date}}", "description": "Callback date as YYYY-MM-DD, inside the window."},
        "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24 hour, inside the window."},
    }, ["customer_id", "date", "time"],
        "Book a callback. CALL it as soon as the person names a day and time inside the callback window.", post=CALLBACK_HOOK)


def note_tool():
    return api_tool("add_note", "/add_note", {
        "product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id exactly as in the product list, for example p2."},
        "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "default": "{{reason}}",
                   "description": "Why the product ended without a PTP. One of: refused, hardship, dispute, paid, service_error."},
    }, ["customer_id", "product_id", "reason"],
        "Record why one product ended without a PTP. CALL it once for every product without a recorded PTP.", post=NOTE_HOOK)


# ------------------------------------------------------------------ node builders

def ttrans(target, when):
    return {"target_node": target, "description": when, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": when}}


def vtrans(target, desc, conds):
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": conds}}


def eq_bool(var, val="true"):
    return [{"variable": var, "operator": "equals", "operand": val}, {"variable": var, "operator": "equals", "operand": val.capitalize()}]


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def code_node(name, code, target, extra=None):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": target,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": (extra or []) + [always(target)],
    }


def action_node(name, tool, transitions, fallback, mapping=None):
    n = {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": fallback,
         "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [tool],
         "transitions": transitions + [always(fallback)]}
    if mapping:
        n["response_mapping"] = mapping
    return n


def say_node(name, text, target):
    return {"name": name, "node_type": "conversation", "passthrough": True, "passthrough_default_transition": target,
            "on_enter": {"type": "tts", "text": text}, "disable_inactivity_monitor": True,
            "task_message": "Say nothing more. No tool call is allowed in this turn.",
            "transitions": [always(target)]}


def close_node(name, outcome, reason=None):
    body = {"outcome": {"type": "string", "enum": [outcome], "default": outcome}}
    req = ["customer_id", "outcome"]
    if reason:
        body["reason"] = {"type": "string", "default": reason}
    tool = api_tool(name, "/close_call", body, req, "End the call with the bank.", config={"timeoutMs": 12000, "maxRetries": 2})
    return action_node(name, tool, [], "hang_up")


def hang_up():
    return {"name": "hang_up", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "transitions": [], "terminal": {"type": "function", "function": {
                "name": "call_closed", "handler": "__function__:end_call",
                "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}


def transfer_node(name, queue, ok_target, fail_target):
    tool = api_tool(name, "/transfer_to_agent", {
        "queue": {"type": "string", "enum": [queue], "default": queue}}, ["customer_id", "queue"],
        "Hand the call to a person.", config={"timeoutMs": 12000, "maxRetries": 1})
    ok = ([{"variable": name + "_success_count", "operator": "greater_than", "operand": 0}]
          + eq_bool(name + "_response.data.ok"))
    return action_node(name, tool, [vtrans(ok_target, "the transfer succeeded", ok)], fail_target)


# ------------------------------------------------------------------ prompts

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is calling the customer. Speak English. Keep every turn to one or two short sentences and ask one question at a time.

Call facts: the customer is {{title}} {{first_name}} {{last_name}}; address them as {{title}} {{last_name}}. The current date and time is {{now}}. Every date rule works from this date, never from any other clock.

Rules for the whole call:
- Never improvise. Never offer a discount, a waiver, an instalment plan or any term that is not in your instructions.
- If you are asked something your tools and instructions cannot answer, say you do not have that information. Never invent figures, dates or reasons.
- "Is this a scam?": say they can verify this call by phoning Freya Bank's customer service number, then go on.
- "Am I talking to a robot / an AI?": say you are Freya Bank's digital assistant, then go on.
- Never say that anything is recorded, booked or done unless the tool result says so.
- When an instruction says to use a tool, call the tool; saying it is not enough. After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- Tools whose names start with transition_to_ end the current stage. Call such a tool alone, never in the same message as another tool. Never say goodbye yourself: the thanks and goodbye are spoken for you after the stage ends."""

IDENTIFY = """Stage: find out who answered. Your opening line already said that you are Freya Bank's digital assistant, that the call is recorded, and asked "Am I speaking with {{title}} {{last_name}}?".

Until the person is confirmed, never say why you are calling and never say "collections", "debt", "payment", "loan", "card" or any product, to anyone, relatives included. If asked what the call is about, say you can explain once you are speaking with {{title}} {{last_name}}.

Decide from what the person says:
- Only "yes", "that's me", "speaking", or the person saying the customer's own name confirm. Then call transition_to_security.
- "Hello", "go ahead", "who is this" or any unclear answer do not confirm. Ask once more: "Am I speaking with {{title}} {{last_name}}?" (to "who is this", first say you are Freya Bank's digital assistant). If it is still unclear after this second ask, call transition_to_goodbye_unclear.
- If the person asks a question instead (robot or scam), answer it as the general rules say and ask again; that ask counts as the second ask.
- Someone else answered (the customer is out, a relative, a colleague): call transition_to_arrange_callback. Do not say why you are calling.
- The number does not belong to the customer: call transition_to_goodbye_wrong_number.
- The customer has died: call transition_to_goodbye_deceased and say nothing yourself; the condolence is spoken for you.
- The person says a second time that they do not want to talk: call transition_to_goodbye_declined_unverified. After the first time, ask once more.
- The person asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_human_unverified.
No other tool call is allowed in this stage."""

SECURITY = """Stage: security check. {{title}} {{last_name}} confirmed who they are. Still never say why you are calling, and never mention collections, a debt, a payment or a product.

Two questions, one at a time: first the date of birth, then the last four digits of the phone number on file. Your opening line in this stage already asked for the date of birth.
- Call verify_identity once for every answer, with field date_of_birth or phone_last4.
- date_of_birth: send YYYY-MM-DD, whatever way the customer said it. A date given only in numbers is day, then month, then year: "05 03 1980" or "5/3/1980" is 1980-03-05. "The fifth of March nineteen eighty" is 1980-03-05. If the customer corrects themselves or gives it in parts, use the complete, corrected answer.
- phone_last4: the four digits, even when said in parts or in words.
- Follow what_to_do_next in each tool result. A wrong answer is asked again. If the result says the day and month seem swapped, ask the customer to say the month as a word; that retry is not a wrong answer. Never reveal the right answer and never say the customer is verified before the tool result says so.
- If the customer does not want to answer, or asks what the call is about instead of answering, explain once that these questions protect their account, and ask again. If they refuse again or ask again what the call is about, call transition_to_goodbye_declined_unverified. If they say twice that they do not want to talk, call it too.
- The customer asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_human_unverified."""

CALLBACK = """Stage: someone other than {{title}} {{last_name}} answered. Say nothing beyond your opening sentence: never say why you are calling, never mention collections, a debt, a payment or a product, and tell them nothing about any account, even if they offer to pay or to answer questions for the customer. A relative may not answer security questions.

Ask when {{title}} {{last_name}} can be reached.

Callback window: {{callback_facts}}

- If they name a day and time inside the window, call schedule_callback with the date (YYYY-MM-DD) and time (HH:MM, 24 hour). "This afternoon at 3" is 15:00 today.
- If the day or the time is outside the window, ask once for another time and say when calls are possible. If the second answer is outside the window too, or they give no time, call transition_to_goodbye_no_callback. Never book a time outside the window.
- If schedule_callback fails once, call it again with the same values. Never say the callback is booked unless the result says so.
- The number does not belong to the customer: call transition_to_goodbye_wrong_number.
- The customer has died: call transition_to_goodbye_deceased and say nothing yourself."""

DATE_RULES = """Dates. A PTP date must be one of the valid PTP dates of that product (today or later, a business day, not after the product's deadline). Use the calendar to turn what the customer says into a date.
- "This <weekday>" is that weekday in the current week. "Next <weekday>" is that weekday in the following calendar week (so "next Friday" said on a Friday is the Friday of the following week). "Tomorrow" is the day after today.
- A weekend day or a bank holiday that is not after the deadline: say it is not a business day and offer the next business day.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still name none, propose the deadline.
- A date after the deadline: say the latest date you can record is the deadline, and offer the deadline. If they refuse the deadline, that is a flat refusal.

Amounts. You propose every amount yourself. Never ask "how much can you pay?".
- Ask for the full past-due amount first.
- If they say the full amount is too much: offer the floor once, and say that the rest stays overdue. Refusing the floor is a flat refusal.
- An amount the customer proposes from the floor up to the full amount, both included, is accepted. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept it, that is a flat refusal.
- If they give a date but no amount, the amount is the full past-due amount (or the floor if they already said the full amount is too much). If they give an amount but no date, ask on which date they can pay it.

Refusals and persuasion.
- A date or an amount the customer proposes is never a refusal; handle it with the rules above.
- A flat refusal or a non-answer uses one persuasion attempt. "No" to paying today, with no date and no amount, is a flat refusal.
- Persuasion attempt 1: propose the offer given as attempt 1 in the product facts (full amount, or the floor if they already said the full amount is too much, on the attempt 1 date).
- Persuasion attempt 2, late stage only: propose the floor on the deadline.
- When the attempts allowed for a product are used up and the customer still refuses, stop. Never repeat an offer the customer already refused.

Hardship (illness, a death in the family, job loss): say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transition_to_transfer_support. If they still name a date or an amount themselves, handle it as a PTP."""

NEGOTIATE_A = """Stage: {{title}} {{last_name}} passed security. Your opening line in this stage already said you are calling from the collections team about a late payment, named the product, the past-due amount and the days late, and asked "Can you make this payment today?".

Account facts (worked out for you; use them exactly):
{{product_facts}}

Calendar:
{{date_facts}}

Your goal is a promise to pay (PTP): an amount and a date that follow the rules below. "Yes" to paying today means the full amount today.

""" + DATE_RULES + """ If they decline the support team, call transition_to_goodbye_hardship.

Confirm and record.
- When you have an amount and a date that pass the rules, read back the product, the amount and the date, and ask "Do you confirm?".
- Call create_promise only after a clear yes, with the amount as a number and the date as YYYY-MM-DD. If the customer changes the date or the amount instead, check the new value with the rules and read it back again.
- If create_promise fails, call it once more with the same values without asking the customer. Never say the promise is recorded unless the result says so.

Endings (each one is a tool; call it alone):
- Attempts used up and the customer still refuses, or the customer said twice that they do not want to talk: transition_to_goodbye_refused.
- "I already paid": tell them payments can take one business day to appear, take no PTP, then call transition_to_goodbye_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no PTP, call transition_to_goodbye_dispute.
- A new payment plan or lower instalments: describe no plan, call transition_to_transfer_restructuring.
- A human: ask once whether you can help first. If they insist, call transition_to_transfer_human.
- Hardship and they accept the support team: transition_to_transfer_support. They decline: transition_to_goodbye_hardship."""

NEGOTIATE_B = """Stage: {{title}} {{last_name}} passed security. Your opening line in this stage already said you are calling from the collections team about a late payment, stated every late product with its past-due amount and days late, and asked whether they can pay (all of them) today.

Account facts, in the order the bank returned them (worked out for you; use them exactly; each product has its own deadline, attempts and floor):
{{product_facts}}

Calendar:
{{date_facts}}

Your goal is a promise to pay (PTP) for each product: an amount and a date that follow the rules below.

Order of work.
- "Yes" to paying everything today means a PTP for every product, full amount, today.
- If not, take the products one at a time, in the order listed, and do not ask about today again for each product. Every product starts at persuasion attempt 1. Persuasion attempts are counted separately for each product.
- Each product ends either with an agreed PTP or without one, for one reason: refused, hardship, dispute or paid. Keep track of this for every product.
- When the customer names one date for everything and that date is after the deadline of a product, that product gets its own deadline as its date, and the read-back says so. The other products keep the date the customer named.
- "I already paid" about a product: tell them payments can take one business day to appear, take no PTP for it, and go on with the next product. "Not mine", "never had it", or closed or paid off in the past: do not argue, take no PTP for it, and go on.

""" + DATE_RULES + """ If they decline the support team, the products without an agreed PTP end as hardship, unless the customer names a date or an amount for them.
- If the customer says twice that they do not want to talk, every product without an agreed PTP ends as refused.

Confirm and record.
- When every product has an agreed PTP or has ended without one, read back all agreed PTPs together (product, amount, date) and ask one "Do you confirm?". If no product has an agreed PTP, skip this and the next point.
- After a clear yes, call create_promise once for each product with an agreed PTP. If the customer changes a date or an amount instead, check the new value with the rules and read back again.
- If create_promise fails for a product, call it once more for that product with the same values. If it fails again, that product ends as service_error; PTPs already recorded stay. Never say a PTP is recorded unless its result says so.
- When all create_promise results are back, tell the customer which PTPs are recorded (and which could not be recorded), then call transition_to_wrap_up in a separate message. Also call transition_to_wrap_up when every product ended without a PTP.

Transfers (each one is a tool; call it alone):
- A new payment plan or lower instalments: describe no plan, call transition_to_transfer_restructuring. PTPs agreed but not yet recorded are not recorded.
- A human: ask once whether you can help first. If they insist, call transition_to_transfer_human.
- Hardship and they accept the support team: transition_to_transfer_support."""

WRAP_UP = """Stage: closing the call. This stage is tool calls only; do not ask the customer anything.

Products, in the order the bank returned them: {{product_list}}

1. Look at the conversation. For every product that ended without a recorded PTP, call add_note once with that product's product_id and one reason:
   - refused: the customer refused, the persuasion attempts were used up, or they did not want to talk;
   - hardship: illness, a death in the family or job loss, and they declined the support team;
   - dispute: not theirs, never had it, or closed or paid off in the past;
   - paid: they already paid it;
   - service_error: create_promise failed twice for it.
   Never add a note for a product with a recorded PTP. If an add_note fails, call it once more.
2. When the notes are saved (or none were needed), call exactly one ending:
   - at least one PTP was recorded: transition_to_goodbye_promise;
   - no PTP recorded and every product was noted paid: transition_to_goodbye_paid;
   - otherwise take the first product in the list order whose note is not paid, and use its reason: refused -> transition_to_goodbye_refused, hardship -> transition_to_goodbye_hardship, dispute -> transition_to_goodbye_dispute, service_error -> transition_to_goodbye_service_error.
If the last thing that happened is a failed transfer, first tell the customer in one sentence that you could not connect them."""


def conv(name, task, tools=None, transitions=None, on_enter=None, first_only=False, max_turns=None, cap_target=None):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": tools or [],
         "transitions": transitions or [], "on_enter": on_enter or {"type": "llm"}}
    if first_only:
        n["on_enter_first_entry_only"] = True
    if max_turns:
        n["max_node_turns"] = max_turns
        n["max_turn_transition"] = cap_target
    return n


def build(multi):
    bye = "Thank you for your time, {{title}} {{last_name}}. Goodbye."
    nodes = {}
    nodes["setup"] = code_node("setup", SETUP_CODE, "identify")

    nodes["identify"] = conv("identify", IDENTIFY, [], [
        ttrans("security", "The person confirmed they are the customer (yes, that's me, speaking, or the customer's own name)."),
        ttrans("arrange_callback", "Someone other than the customer answered."),
        ttrans("goodbye_wrong_number", "The number does not belong to the customer."),
        ttrans("goodbye_deceased", "The person says the customer has died."),
        ttrans("goodbye_unclear", "Still unclear who answered after the second ask."),
        ttrans("goodbye_declined_unverified", "The person said twice that they do not want to talk."),
        ttrans("transfer_human_unverified", "The person insists on talking to a human after being asked once whether you can help."),
    ], {"type": "tts", "text": "Hello, this is Freya Bank's digital assistant calling, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
        True, 12, "goodbye_unclear")

    nodes["security"] = conv("security", SECURITY, [verify_tool()], [
        vtrans("load_account", "Both security answers are verified", eq_bool("verify_identity_response.data.all_verified")),
        vtrans("goodbye_failed", "Three wrong answers", [{"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"}]),
        ttrans("goodbye_declined_unverified", "The customer refused the security questions a second time, or said twice that they do not want to talk."),
        ttrans("transfer_human_unverified", "The customer insists on talking to a human after being asked once whether you can help."),
    ], {"type": "tts", "text": "Thank you, {{title}} {{last_name}}. Before I go on, I need to ask two security questions. First, what is your date of birth?"},
        True, 16, "goodbye_declined_unverified")

    nodes["arrange_callback"] = conv("arrange_callback", CALLBACK, [callback_tool()], [
        vtrans("goodbye_callback", "The callback is booked",
               [{"variable": "schedule_callback_success_count", "operator": "greater_than", "operand": 0}] + eq_bool("schedule_callback_response.data.ok")),
        vtrans("goodbye_callback_failed", "Booking failed twice",
               [{"variable": "schedule_callback_failure_count", "operator": "greater_than", "operand": 1}]),
        ttrans("goodbye_no_callback", "No time inside the window after asking once more, or no time given."),
        ttrans("goodbye_wrong_number", "The number does not belong to the customer."),
        ttrans("goodbye_deceased", "The person says the customer has died."),
    ], {"type": "llm", "prompt": "Do not repeat your opening. If the person already named a time, handle it; otherwise ask when {{title}} {{last_name}} can be reached."},
        True, 10, "goodbye_no_callback")

    nodes["load_account"] = action_node("load_account", api_tool("load_account", "/get_account", {}, ["customer_id"], "Get the late products.",
                                                                  config={"timeoutMs": 12000, "maxRetries": 2}),
                                        [], "account_facts", mapping=[{"path": "data.products", "variable": "products"}])
    nodes["account_facts"] = code_node("account_facts", ACCOUNT_CODE, "goodbye_account_error",
                                       [vtrans("negotiate", "Account facts ready", [{"variable": "account_state", "operator": "equals", "operand": "ok"}])])

    opening = {"type": "tts", "text": "Thank you, {{title}} {{last_name}}. I am calling from the collections team about a late payment. {{statement_text}}"}
    if multi:
        nodes["negotiate"] = conv("negotiate", NEGOTIATE_B, [promise_tool(True)], [
            ttrans("wrap_up", "All create_promise results are back and reported, or every product ended without a PTP."),
            ttrans("transfer_support", "Hardship: the customer accepted the customer support team."),
            ttrans("transfer_restructuring", "The customer asks for a new payment plan or lower instalments."),
            ttrans("transfer_human", "The customer insists on a human after being asked once whether you can help."),
        ], opening, True, 50, "wrap_up")
        nodes["wrap_up"] = conv("wrap_up", WRAP_UP, [note_tool()], [
            ttrans("goodbye_promise", "At least one PTP was recorded."),
            ttrans("goodbye_paid", "No PTP recorded and every product was noted paid."),
            ttrans("goodbye_refused", "No PTP recorded; the first product not noted paid was noted refused."),
            ttrans("goodbye_hardship", "No PTP recorded; the first product not noted paid was noted hardship."),
            ttrans("goodbye_dispute", "No PTP recorded; the first product not noted paid was noted dispute."),
            ttrans("goodbye_service_error", "No PTP recorded; the first product not noted paid was noted service_error."),
        ], {"type": "llm"}, False, 8, "goodbye_refused")
    else:
        nodes["negotiate"] = conv("negotiate", NEGOTIATE_A, [promise_tool(False)], [
            vtrans("goodbye_promise", "The promise is recorded",
                   [{"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}] + eq_bool("create_promise_response.data.ok")),
            vtrans("goodbye_promise_failed", "create_promise failed twice",
                   [{"variable": "create_promise_failure_count", "operator": "greater_than", "operand": 1}]),
            ttrans("goodbye_refused", "Persuasion attempts used up and the customer still refuses, or said twice they do not want to talk."),
            ttrans("goodbye_paid", "The customer says they already paid this amount."),
            ttrans("goodbye_dispute", "The customer says the debt is not theirs, never had the product, or it was closed or paid off in the past."),
            ttrans("goodbye_hardship", "Hardship and the customer declined the support team."),
            ttrans("transfer_support", "Hardship: the customer accepted the customer support team."),
            ttrans("transfer_restructuring", "The customer asks for a new payment plan or lower instalments."),
            ttrans("transfer_human", "The customer insists on a human after being asked once whether you can help."),
        ], opening, True, 40, "goodbye_refused")

    # transfers
    fail_verified = "transfer_failed_notice" if multi else None
    nodes["transfer_support"] = transfer_node("transfer_support", "support", "goodbye_transferred_support",
                                              fail_verified or "goodbye_transfer_failed_support")
    nodes["transfer_restructuring"] = transfer_node("transfer_restructuring", "restructuring", "goodbye_transferred_restructuring",
                                                    fail_verified or "goodbye_transfer_failed")
    nodes["transfer_human"] = transfer_node("transfer_human", "general", "goodbye_transferred_human",
                                            fail_verified or "goodbye_transfer_failed")
    nodes["transfer_human_unverified"] = transfer_node("transfer_human_unverified", "general", "goodbye_transferred_human",
                                                       "goodbye_transfer_failed_unverified")
    connecting = "I am connecting you now. Thank you for your time, {{title}} {{last_name}}. Goodbye."
    nodes["goodbye_transferred_support"] = say_node("goodbye_transferred_support", connecting, "close_transferred_support")
    nodes["goodbye_transferred_restructuring"] = say_node("goodbye_transferred_restructuring", connecting, "close_transferred_restructuring")
    nodes["goodbye_transferred_human"] = say_node("goodbye_transferred_human", connecting, "close_transferred_human")
    sorry_tx = "I am sorry, I could not connect you right now. "
    if multi:
        nodes["transfer_failed_notice"] = say_node("transfer_failed_notice", "I am sorry, I could not connect you right now.", "wrap_up")
    else:
        nodes["goodbye_transfer_failed_support"] = say_node("goodbye_transfer_failed_support", sorry_tx + bye, "close_no_promise_hardship")
        nodes["goodbye_transfer_failed"] = say_node("goodbye_transfer_failed", sorry_tx + bye, "close_no_promise_service_error")
    nodes["goodbye_transfer_failed_unverified"] = say_node("goodbye_transfer_failed_unverified", sorry_tx + bye, "close_not_verified_declined")

    # goodbyes
    if multi:
        nodes["goodbye_promise"] = say_node("goodbye_promise", "You will receive a text message confirming this promise. " + bye, "close_promise")
        nodes["goodbye_paid"] = say_node("goodbye_paid", bye, "close_paid")
        nodes["goodbye_service_error"] = say_node("goodbye_service_error", bye, "close_no_promise_service_error")
    else:
        nodes["goodbye_promise"] = say_node("goodbye_promise", "Your promise to pay is recorded. You will receive a text message confirming this promise. " + bye, "close_promise")
        nodes["goodbye_paid"] = say_node("goodbye_paid", "Thank you for letting me know. Payments can take one business day to appear. " + bye, "close_paid")
        nodes["goodbye_promise_failed"] = say_node("goodbye_promise_failed", "I am sorry, I could not record your promise because of a technical problem. " + bye, "close_no_promise_service_error")
    nodes["goodbye_refused"] = say_node("goodbye_refused", "I understand. " + bye, "close_no_promise_refused")
    nodes["goodbye_hardship"] = say_node("goodbye_hardship", "I understand. " + bye, "close_no_promise_hardship")
    nodes["goodbye_dispute"] = say_node("goodbye_dispute", "I understand. " + bye, "close_no_promise_dispute")
    nodes["goodbye_account_error"] = say_node("goodbye_account_error", "I am sorry, I cannot access your account details right now. " + bye, "close_no_promise_service_error")
    nodes["goodbye_failed"] = say_node("goodbye_failed", "I am sorry, I could not verify your identity, so I cannot go on. Please use the Freya Bank mobile app or visit a branch. " + bye, "close_not_verified_failed")
    nodes["goodbye_declined_unverified"] = say_node("goodbye_declined_unverified", "I understand. Thank you for your time. Goodbye.", "close_not_verified_declined")
    nodes["goodbye_callback"] = say_node("goodbye_callback", "Thank you, the callback is booked. Thank you for your help. Goodbye.", "close_not_reached_callback")
    nodes["goodbye_callback_failed"] = say_node("goodbye_callback_failed", "I am sorry, I could not book the callback. Thank you for your help. Goodbye.", "close_not_reached_no_callback")
    nodes["goodbye_no_callback"] = say_node("goodbye_no_callback", "Thank you for your help. Goodbye.", "close_not_reached_no_callback")
    nodes["goodbye_wrong_number"] = say_node("goodbye_wrong_number", "I apologise for the inconvenience. Thank you for your time. Goodbye.", "close_not_reached_wrong_number")
    nodes["goodbye_deceased"] = say_node("goodbye_deceased", "I am sorry for your loss. Thank you for your time. Goodbye.", "close_not_reached_deceased")
    nodes["goodbye_unclear"] = say_node("goodbye_unclear", "Thank you for your time. Goodbye.", "close_not_reached_unclear")

    # terminal steps: close_call alone, then hang up
    closes = {
        "close_promise": ("promise", None), "close_paid": ("paid", None),
        "close_transferred_support": ("transferred", "support"),
        "close_transferred_restructuring": ("transferred", "restructuring"),
        "close_transferred_human": ("transferred", "human"),
        "close_no_promise_refused": ("no_promise", "refused"), "close_no_promise_hardship": ("no_promise", "hardship"),
        "close_no_promise_dispute": ("no_promise", "dispute"), "close_no_promise_service_error": ("no_promise", "service_error"),
        "close_not_verified_failed": ("not_verified", "failed"), "close_not_verified_declined": ("not_verified", "declined"),
        "close_not_reached_callback": ("not_reached", "callback"), "close_not_reached_no_callback": ("not_reached", "no_callback"),
        "close_not_reached_wrong_number": ("not_reached", "wrong_number"), "close_not_reached_deceased": ("not_reached", "deceased"),
        "close_not_reached_unclear": ("not_reached", "unclear"),
    }
    for k, (o, r) in closes.items():
        nodes[k] = close_node(k, o, r)
    nodes["hang_up"] = hang_up()

    return {
        "initial_node": "setup",
        "system_prompt": SYSTEM,
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    }


def contract(extra=None):
    ev = [{"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
          {"source": "briefs/brief-a-raw.md", "quote": "Every call ends with exactly one `close_call`, as the last tool call, with an outcome and, where the list gives one, a reason."}]
    return {"terminal_tools": [{"tool": "close_call", "evidence": ev + (extra or [])}], "every_call_ends_with_terminal": True}


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for slot, multi, extra in (("brief-a-raw", False, None),
                               ("brief-b-raw", True, [{"source": "briefs/brief-b-raw.md", "quote": "The close code list still applies."}])):
        (OUT / f"{slot}.workflow.json").write_text(json.dumps(build(multi), indent=1))
        (OUT / f"{slot}.contract.json").write_text(json.dumps(contract(extra), indent=1))
        print("wrote", slot)
