"""Generate out/pl-g3-limits-raw.body.json and out/pl-g3-limits-raw.closing.json for brief pl-g3-limits-raw."""
import json
from pathlib import Path

SLOT = "pl-g3-limits-raw"
BRIEF = f"briefs/{SLOT}.md"
API = "tools/openapi.json"
SERVER = "https://freya-bank-mock.freyavoice.workers.dev/v1"


def api_tool(name, path, fields, required, desc, max_retries=0, post="", mapping=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(fields)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": desc,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": SERVER + path},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": props, "required": ["customer_id"] + required},
            }},
        },
    }
    if post:
        t["post_process_code"] = post
    if mapping:
        t["response_mapping"] = mapping
    return t


def code_node(key, code, nxt, transitions=None):
    return {
        "name": key, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code},
                             "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": (transitions or []) + [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}],
    }


def eq(var, val):
    return {"variable": var, "operator": "equals", "operand": val}


def any_of(*conds):
    return {"logic": "or", "conditions": list(conds)}


def all_of(*conds):
    return {"logic": "or", "conditions": [{"logic": "and", "conditions": list(conds)}]}


def is_true(var):
    return any_of(eq(var, "true"), eq(var, "True"))


def gt(var, n):
    return {"variable": var, "operator": "greater_than", "operand": n}


def tr(target, desc, cond):
    return {"target_node": target, "description": desc, "condition": cond}


def tool_tr(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


# ---------------------------------------------------------------- post hooks
POST_VERIFY = r"""
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        def low(x):
            return str(x).strip().lower()
        if not isinstance(d, dict):
            result['data'] = {'what_to_do_next': 'The check did not run because of a technical problem. Nothing was counted. Ask the customer to repeat the same answer, then call verify_identity again.'}
        else:
            left = d.get('wrong_answers_left')
            if low(d.get('all_verified')) == 'true':
                msg = 'Both security answers are verified. Ask no more security questions.'
            elif d.get('hint') == 'day_month_swapped':
                msg = 'Day and month look swapped. This does not count as a wrong answer. Ask the customer to say the date of birth again with the month as a word.'
            elif left is not None and low(left) == '0':
                msg = 'The security check has ended. Say nothing about the account.'
            elif low(d.get('verified')) == 'true':
                msg = 'This answer is correct. Now ask for the last four digits of the phone number on file.'
            elif low(d.get('ok')) == 'false' and low(d.get('verified')) != 'false':
                msg = 'The answer could not be read. It does not count as a wrong answer. Ask for the same answer again. For the date of birth ask for day, month and year.'
            else:
                msg = 'This answer does not match. Tell the customer it did not match and ask the same question again.'
            d['what_to_do_next'] = msg
except Exception:
    pass
"""

POST_PROMISE = r"""
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        ok = isinstance(d, dict) and str(d.get('ok')).strip().lower() == 'true'
        if not isinstance(d, dict):
            d = {}
            result['data'] = d
        if ok:
            d['what_to_do_next'] = 'The promise is recorded.'
        else:
            d['what_to_do_next'] = 'The promise was NOT recorded. Never say it is recorded. Call create_promise once more now with exactly the same values.'
except Exception:
    pass
"""

POST_TRANSFER = r"""
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        ok = isinstance(d, dict) and str(d.get('ok')).strip().lower() == 'true'
        if not isinstance(d, dict):
            d = {}
            result['data'] = d
        if ok:
            d['what_to_do_next'] = 'The transfer is done.'
        else:
            d['what_to_do_next'] = 'The transfer did NOT work. Tell the customer you could not connect them right now, and continue helping.'
except Exception:
    pass
"""


def transfer_tool(queue, when):
    return api_tool(f"transfer_{queue}", "/transfer_to_agent",
                    {"queue": {"type": "string", "enum": [queue], "default": queue}}, ["queue"],
                    f"Hand the call to the {queue} team. CALL it {when}", post=POST_TRANSFER)


VERIFY = api_tool(
    "verify_identity", "/verify_identity",
    {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
               "description": "Which question this answer is for: date_of_birth or phone_last4."},
     "answer": {"type": "string", "default": "{{answer}}",
                "description": "date_of_birth: the date as YYYY-MM-DD, converted from what the customer said. A date given only as numbers is day, then month, then year. phone_last4: exactly four digits."}},
    ["field", "answer"],
    "Check one security answer. CALL it every time the customer answers a security question, once per answer.",
    post=POST_VERIFY)

PROMISE = api_tool(
    "create_promise", "/create_promise",
    {"product_id": {"type": "string", "default": "{{product_id}}"},
     "amount": {"type": "number", "default": "{{promise_amount}}", "description": "The confirmed amount in euros, for example 250.00."},
     "date": {"type": "string", "default": "{{promise_date}}", "description": "The confirmed date as YYYY-MM-DD."}},
    ["product_id", "amount", "date"],
    "Record the payment promise. CALL it only after you read back product, amount and date, asked 'Do you confirm?' and the customer clearly said yes.",
    post=POST_PROMISE)

T_GENERAL = transfer_tool("general", "only when the customer asks for a human, you asked once whether you can help, and they still insist.")
T_SUPPORT = transfer_tool("support", "only when the customer mentioned illness, a death in the family or job loss and accepted your offer to connect them with the customer support team.")
T_RESTR = transfer_tool("restructuring", "as soon as the customer asks for a new payment plan or lower instalments.")

# ---------------------------------------------------------------- code
SETUP = r"""
import datetime
try:
    HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
    DN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    MN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    raw = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        nowdt = datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        nowdt = datetime.datetime.fromisoformat(raw[:10] + 'T09:00')
    today = nowdt.date()
    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL
    def sp(d):
        return DN[d.weekday()] + ' ' + str(d.day) + ' ' + MN[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
    def nth_bd(n):
        d = today
        c = 0
        while c < n:
            d = d + datetime.timedelta(days=1)
            if isbd(d):
                c += 1
        return d
    def last_bd_of_week(monday):
        best = None
        for k in range(5):
            d = monday + datetime.timedelta(days=k)
            if isbd(d):
                best = d
        return best
    mon = today - datetime.timedelta(days=today.weekday())
    a1 = last_bd_of_week(mon)
    if a1 is None or a1 <= today:
        a1 = last_bd_of_week(mon + datetime.timedelta(days=7))
    nbd = nth_bd(1)
    vars['today_iso'] = today.isoformat()
    vars['today_spoken'] = sp(today)
    vars['today_is_bd'] = 'yes' if isbd(today) else 'no'
    vars['now_hhmm'] = nowdt.strftime('%H:%M')
    vars['next_bd_iso'] = nbd.isoformat()
    vars['next_bd_spoken'] = sp(nbd)
    vars['deadline_early_iso'] = nth_bd(12).isoformat()
    vars['deadline_late_iso'] = nth_bd(7).isoformat()
    vars['a1_iso'] = a1.isoformat()
    vars['a1_spoken'] = sp(a1)
    lines = []
    for k in range(7):
        lines.append('this ' + DN[k] + ' = ' + sp(mon + datetime.timedelta(days=k)))
    for k in range(7):
        lines.append('next ' + DN[k] + ' = ' + sp(mon + datetime.timedelta(days=7 + k)))
    vars['week_table'] = '; '.join(lines)
    cal = []
    for k in range(0, 31):
        d = today + datetime.timedelta(days=k)
        tag = 'business day' if isbd(d) else ('Freya Bank holiday' if d.isoformat() in HOL else 'weekend')
        cal.append(sp(d) + ': ' + tag)
    vars['calendar'] = '; '.join(cal)
    if isbd(today) and nowdt.strftime('%H:%M') < '19:00':
        vars['cb_window'] = 'today ' + sp(today) + ' from ' + max('10:00', nowdt.strftime('%H:%M')) + ' to 19:00 (later than now), or ' + sp(nbd) + ' from 10:00 to 19:00'
    else:
        vars['cb_window'] = sp(nbd) + ' from 10:00 to 19:00'
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['setup_state'] = 'error'
    for k in ['today_iso', 'today_spoken', 'today_is_bd', 'now_hhmm', 'next_bd_iso', 'next_bd_spoken', 'deadline_early_iso', 'deadline_late_iso', 'a1_iso', 'a1_spoken', 'week_table', 'calendar', 'cb_window']:
        if k not in vars:
            vars[k] = 'unknown'
"""


def check_callback_code(day_keys, time_keys):
    return r"""
import datetime, re
try:
    HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
    DN = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    def first(keys):
        for k in keys:
            v = vars.get(k)
            if v is not None and str(v).strip() != '':
                return str(v).strip()
        return ''
    raw = str(vars.get('now') or '').strip().replace(' ', 'T')
    nowdt = datetime.datetime.fromisoformat(raw[:16])
    today = nowdt.date()
    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL
    nbd = today + datetime.timedelta(days=1)
    while not isbd(nbd):
        nbd = nbd + datetime.timedelta(days=1)
    day = first(DAYKEYS).lower()
    tim = first(TIMEKEYS).lower()
    d = None
    if 'after tomorrow' in day:
        d = today + datetime.timedelta(days=2)
    elif 'today' in day or 'tonight' in day or 'this afternoon' in day or 'this evening' in day:
        d = today
    elif 'tomorrow' in day:
        d = today + datetime.timedelta(days=1)
    else:
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', day)
        if m:
            d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        else:
            for k in range(7):
                if DN[k] in day:
                    delta = (k - today.weekday()) % 7
                    if delta == 0:
                        delta = 7
                    if 'next' in day and today + datetime.timedelta(days=delta) < today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(days=7):
                        delta += 7
                    d = today + datetime.timedelta(days=delta)
    t = None
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?', tim)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        ap = (m.group(3) or '').replace('.', '')
        if ap == 'pm' and h < 12:
            h += 12
        if ap == 'am' and h == 12:
            h = 0
        if 0 <= h <= 23 and 0 <= mi <= 59:
            t = datetime.time(h, mi)
    ok = False
    if d is not None and t is not None:
        dt = datetime.datetime.combine(d, t)
        in_hours = datetime.time(10, 0) <= t <= datetime.time(19, 0)
        ok = in_hours and dt > nowdt and (d == today or d == nbd)
    if ok:
        vars['cb_ok'] = 'yes'
        vars['cb_date_ok'] = d.isoformat()
        vars['cb_time_ok'] = t.strftime('%H:%M')
    else:
        vars['cb_ok'] = 'no'
except Exception:
    vars['cb_ok'] = 'no'
""".replace("DAYKEYS", repr(day_keys)).replace("TIMEKEYS", repr(time_keys))


ACCOUNT = r"""
import datetime, json, re, math
try:
    HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
    DN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    MN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    def sp(d):
        return DN[d.weekday()] + ' ' + str(d.day) + ' ' + MN[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL
    def products():
        p = vars.get('products')
        if isinstance(p, str):
            s = p.strip()
            try:
                p = json.loads(s)
            except Exception:
                try:
                    p = json.loads(s.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
                except Exception:
                    p = None
        if isinstance(p, dict):
            p = [p]
        if isinstance(p, list) and p and isinstance(p[0], dict):
            return p
        out = {}
        for k, v in list(vars.items()):
            m = re.match(r'^(?:get_account_response\.data\.products|products)\.(\d+)\.(\w+)$', str(k))
            if m:
                out.setdefault(int(m.group(1)), {})[m.group(2)] = v
        return [out[i] for i in sorted(out)]
    def num(x):
        try:
            return float(x)
        except Exception:
            return None
    def money(x):
        return '%.2f' % x
    ps = products()
    pr = ps[0]
    typ = str(pr.get('type') or '')
    past_due = num(pr.get('past_due'))
    days = int(float(pr.get('days_late')))
    if typ == 'credit_card':
        phrase = 'credit card ending ' + str(pr.get('card_last4') or '')
        floor_amt = num(pr.get('minimum_payment'))
    elif typ == 'car_loan':
        phrase = 'car loan'
        floor_amt = float(math.floor(past_due / 2.0))
    else:
        phrase = 'personal loan'
        floor_amt = num(pr.get('instalment_amount'))
    ask = min(past_due, 2000.0)
    if floor_amt is None:
        floor_amt = ask
    floor_amt = min(floor_amt, ask)
    raw = str(vars.get('now') or '').strip().replace(' ', 'T')
    today = datetime.datetime.fromisoformat(raw[:16]).date()
    if days <= 7:
        band = 'early'
        n = 12
        attempts = 2
    else:
        band = 'late'
        n = 7
        attempts = 3
    d = today
    c = 0
    while c < n:
        d = d + datetime.timedelta(days=1)
        if isbd(d):
            c += 1
    deadline = d
    valid = []
    d = today
    while d <= deadline:
        if isbd(d):
            valid.append(sp(d))
        d = d + datetime.timedelta(days=1)
    mon = today - datetime.timedelta(days=today.weekday())
    def lbd(m0):
        best = None
        for k in range(5):
            x = m0 + datetime.timedelta(days=k)
            if isbd(x):
                best = x
        return best
    a1 = lbd(mon)
    if a1 is None or a1 <= today:
        a1 = lbd(mon + datetime.timedelta(days=7))
    cap_note = ''
    if past_due > 2000.0:
        cap_note = ' The past-due amount is above 2000.00 euros, so ask for 2000.00 euros and say that the rest stays overdue.'
    vars['product_id'] = str(pr.get('product_id') or '')
    vars['product_phrase'] = phrase
    vars['past_due_text'] = money(past_due)
    vars['ask_amount'] = money(ask)
    vars['floor_amount'] = money(floor_amt)
    vars['days_late_text'] = str(days)
    vars['band'] = band
    vars['deadline_spoken'] = sp(deadline)
    vars['valid_dates'] = '; '.join(valid)
    vars['item_count'] = 1
    vars['attempts_allowed_1'] = attempts
    facts = []
    facts.append('Product: ' + phrase + ' (product_id ' + vars['product_id'] + ').')
    facts.append('Past-due amount: ' + money(past_due) + ' euros. Days late: ' + str(days) + '.')
    facts.append('Full amount to ask for: ' + money(ask) + ' euros.' + cap_note)
    facts.append('Floor (lowest amount you may accept or offer): ' + money(floor_amt) + ' euros.')
    facts.append('Highest amount you may record: ' + money(ask) + ' euros.')
    facts.append('Band: ' + band + '. Deadline (latest promise date): ' + sp(deadline) + '.')
    facts.append('The ONLY valid promise dates: ' + '; '.join(valid) + '.')
    facts.append('Persuasion attempt 1 date: ' + sp(a1) + '.')
    if len(ps) > 1:
        facts.append('Note: get_account returned more than one product; handle only this one.')
    vars['acct_facts'] = '\n'.join(facts)
    vars['offer_intro_1'] = ('Say that you are calling from the collections team about a late payment on your ' + phrase + '. Say that ' + money(past_due) + ' euros is past due and the payment is ' + str(days) + ' days late.' + cap_note + ' Then ask exactly: "Can you make this payment today?" (the payment is ' + money(ask) + ' euros).')
    vars['offer_intro_2'] = ('The customer did not agree. Make persuasion attempt 1: propose paying ' + money(ask) + ' euros by ' + sp(a1) + '. If the customer already said the full amount is too much, propose the floor of ' + money(floor_amt) + ' euros by ' + sp(a1) + ' instead and say that the rest stays overdue. One or two short sentences.')
    vars['offer_intro_3'] = ('The customer did not agree. Make persuasion attempt 2, the last one: propose paying the floor of ' + money(floor_amt) + ' euros on ' + sp(deadline) + ', and say that the rest stays overdue. One or two short sentences.')
    vars['acct_state'] = 'ok' if vars['product_id'] and past_due is not None else 'missing'
except Exception as e:
    vars['acct_state'] = 'missing'
    vars['item_count'] = 1
    vars['attempts_allowed_1'] = 2
    for k in ['acct_facts', 'offer_intro_1', 'offer_intro_2', 'offer_intro_3', 'product_id', 'valid_dates', 'deadline_spoken', 'ask_amount', 'floor_amount', 'product_phrase']:
        if k not in vars:
            vars[k] = ''
"""

# ---------------------------------------------------------------- prompts
SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is fictional and all data is synthetic.
Speak English. Use one or two short sentences per turn. Ask one question at a time. Avoid technical words.
Address the customer as {{title}} {{last_name}}.
Current date and time: {{now}} ({{today_spoken}}). Use this, never the real clock.
Tool rules: call one tool per message. After every tool result, speak to the customer or call the next tool. Never end a turn with nothing. When a tool result has what_to_do_next, follow it. If a tool call fails, say so; never say something is recorded or done when it is not.
If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
If asked "is this a scam?": say they can verify the call by phoning Freya Bank's customer service number, then continue.
If asked something the tools do not tell you: say you do not have that information. Never invent figures, dates or reasons.
Never offer a discount, a waiver, an instalment plan or any term not given to you."""

PRE_ID = ("Before identity is verified you must NOT say 'collections', 'debt', 'payment', or name any product or account detail, "
          "to anyone. If asked why you are calling, say you can explain only to {{title}} {{last_name}} after a short security check.")

CONFIRM_ENUM = ["confirmed", "someone_else", "wrong_number", "deceased", "unclear"]
CONFIRM_DESC = ("Who answered, judged from the person's latest message only. confirmed: the person said yes, that's me, speaking, "
                "or gave the customer's own name ({{first_name}} {{last_name}}). someone_else: another person answered (relative, colleague) "
                "and the customer is not on the line. wrong_number: the number does not belong to the customer / they do not know this person. "
                "deceased: the customer has died. unclear: anything else, such as hello, go ahead, who is this, a question, or what is this about.")


def opening_node(key, var, on_enter, unclear_target):
    return {
        "name": key, "node_type": "conversation", "on_enter": on_enter,
        "task_message": (PRE_ID + "\nYour only job here: find out whether you are speaking with {{title}} {{last_name}}. "
                         "Answer a question from the person briefly first, then ask \"Am I speaking with {{title}} {{last_name}}?\". "
                         "Do not call a tool in this turn."),
        "extraction_schema": [{"name": var, "type": "string", "enum_values": CONFIRM_ENUM, "description": CONFIRM_DESC, "min_confidence": 0.6}],
        "transitions": [
            tr("identity", "the customer confirmed who they are", any_of(eq(var, "confirmed"))),
            tr("close:not_reached/deceased", "the customer has died", any_of(eq(var, "deceased"))),
            tr("close:not_reached/wrong_number", "wrong number", any_of(eq(var, "wrong_number"))),
            tr("third_party", "someone else answered", any_of(eq(var, "someone_else"))),
            tr(unclear_target, "still unclear", {"operator": "always"}),
        ],
    }


def identity_node(key, decline_var, on_enter, decline_target, extra_task):
    return {
        "name": key, "node_type": "conversation", "on_enter": on_enter,
        "task_message": (
            PRE_ID + "\n" + extra_task +
            "Verify identity with two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. "
            "Call verify_identity after each answer, with field date_of_birth or phone_last4. Convert the date of birth to YYYY-MM-DD whatever way it was said; "
            "a date given only as numbers is day, then month, then year (03/04/1985 is 1985-04-03). "
            "A wrong answer may be asked again. If the result says day and month are swapped, ask for the date of birth with the month said as a word. "
            "Do not answer the security questions for the customer and do not hint at the answers. "
            "If the customer asks for a human: ask once whether you can help first; if they insist, call transfer_general. "
            "If the customer refuses to answer or asks what the call is about, do not explain the reason for the call."),
        "tools": [VERIFY, T_GENERAL],
        "extraction_schema": [{"name": decline_var, "type": "string", "enum_values": ["yes", "no"], "min_confidence": 0.6,
                               "description": ("Judge only the customer's latest message. yes: the customer refuses to answer the security question, "
                                               "says they do not want to talk, or asks what the call is about instead of answering. "
                                               "no: anything else, including an answer, a request to repeat, a question whether this is a robot or a scam, or a request for a human.")}],
        "max_node_turns": 16, "max_turn_transition": "close:not_verified/declined",
        "transitions": [
            tr("get_account", "both security answers verified", is_true("verify_identity_response.data.all_verified")),
            tr("close:not_verified/failed", "three wrong answers, the check has ended",
               any_of(eq("verify_identity_response.data.wrong_answers_left", "0"))),
            tr("close:transferred/human", "transferred to a human", any_of(gt("transfer_general_success_count", 0))),
            tr(decline_target, "the customer declined", any_of(eq(decline_var, "yes"))),
        ],
    }


def third_party_node(key, day, tim, event, on_enter, check_node, retry_text):
    return {
        "name": key, "node_type": "conversation", "on_enter": on_enter,
        "task_message": (
            "Someone other than {{title}} {{last_name}} is on the line. Do not say why you are calling and say nothing beyond: you are a digital assistant calling from Freya Bank and the call is recorded. "
            "Never mention collections, debt, payment, a product or any account detail, even if the person is a relative or offers to pay; politely say you can only speak with {{title}} {{last_name}}. "
            "Do not ask security questions. " + retry_text +
            "Ask for one exact day and one exact clock time. If the person gives a vague time such as 'in the afternoon', ask for the exact time. "
            "Allowed callback times: " "{{cb_window}}" ". Do not call a tool in this turn."),
        "extraction_schema": [
            {"name": day, "type": "string", "min_confidence": 0.6,
             "description": "The day the person says the customer can be reached, as one word: today, tomorrow, day after tomorrow, a weekday name (prefix 'next ' if they said next), or a calendar date as YYYY-MM-DD. Empty if not said."},
            {"name": tim, "type": "string", "min_confidence": 0.6, "validation_pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$",
             "description": "The exact clock time the person named, 24-hour HH:MM (3 pm is 15:00, half past ten in the morning is 10:30). Empty if no exact time was said."},
            {"name": event, "type": "string", "enum_values": ["wrong_number", "deceased", "refuses", "none"], "min_confidence": 0.6,
             "description": "From the person's latest message only. wrong_number: the number does not belong to the customer. deceased: the customer has died. refuses: the person will not give any time or does not know when. none: anything else."},
        ],
        "max_node_turns": 8, "max_turn_transition": "close:not_reached/no_callback",
        "transitions": [
            tr("close:not_reached/deceased", "the customer has died", any_of(eq(event, "deceased"))),
            tr("close:not_reached/wrong_number", "wrong number", any_of(eq(event, "wrong_number"))),
            tr("close:not_reached/no_callback", "no time given", any_of(eq(event, "refuses"))),
            tr(check_node, "a day and a time were given",
               all_of({"variable": day, "operator": "is_set"}, {"variable": tim, "operator": "is_set"})),
        ],
    }


NEGOTIATE_TASK = """The customer {{title}} {{last_name}} is verified. You are on offer {a} of the payment talk.
Account facts:
{{acct_facts}}
Current offer {a}: {{offer_intro_{a}}}

Rules:
- You propose every amount. Never ask "how much can you pay?". Ask for the full amount first.
- If the customer says the full amount is too much: offer the floor once and say the rest stays overdue.
- If the customer proposes an amount from the floor up to the highest recordable amount, accept it. Below the floor: say it cannot be recorded and offer the floor once.
- A date or an amount the customer proposes is never a refusal. A promise date must be one of the valid promise dates listed above.
  - A weekend day or holiday not after the deadline: offer the next valid business day.
  - A date after the deadline: say the latest date you can record is the deadline, and offer the deadline.
  - A vague period (next week, end of month, when my salary comes): ask once for the exact day; if still none, propose the deadline.
  - "next <weekday>" is that weekday in the following calendar week, "this <weekday>" is in the current week: {{week_table}}.
  - "today" is {{today_spoken}}.
- Never repeat an offer the customer already refused.
- Confirming: read back the product, the amount and the date and ask "Do you confirm?". Call create_promise only after a clear yes. If the customer changes the date or amount, check the new value and read it back again.
- Say the promise is recorded only after create_promise returns ok true. If it fails, call it once more with the same values.
- Illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_support. If they decline, thank them, say goodbye and call transition_to the hardship ending. If they still name a date or amount themselves, handle it as a promise.
- A request for a new payment plan or lower instalments: do not describe any plan; call transfer_restructuring.
- A request for a human: ask once whether you can help first; if they insist, call transfer_general.
- "I already paid" (this past-due amount): say payments can take one business day to appear, take no promise, thank them, say goodbye and take the paid ending.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise, thank them, say goodbye and take the dispute ending.
- If the customer says for the second time that they do not want to talk: thank them, say goodbye and take the not-talking ending.
- When you take an ending, say your thank-you and goodbye in the same message."""

REFUSAL_DESC = ("Judge ONLY the customer's latest message, as an answer to the agent's latest offer. yes: a flat refusal or a non-answer to the offer "
                "(no / I can't / not today, with no date and no amount of their own; a refusal of the floor amount; a refusal of the deadline date; "
                "'I don't know' with nothing else). no: anything else, including any date or amount the customer proposes, 'the full amount is too much', "
                "a vague period such as next week, a question, agreement, a mention of illness, a death in the family or job loss, "
                "a request for a human or a new plan, 'I already paid', or 'this is not my debt'.")

negotiate = {
    "name": "negotiate", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "{{offer_intro_{a}}} Do not call a tool in this message."},
    "task_message": NEGOTIATE_TASK,
    "tools": [PROMISE, T_SUPPORT, T_RESTR, T_GENERAL],
    "extraction_schema": [{"name": "refused_{i}_{a}", "type": "string", "enum_values": ["yes", "no"], "min_confidence": 0.6,
                           "description": REFUSAL_DESC}],
    "max_node_turns": 20, "max_turn_transition": "close:no_promise/refused",
    "transitions": [
        tr("promise_done", "the promise was recorded", any_of(gt("create_promise_success_count", 0))),
        tr("close:no_promise/service_error", "create_promise failed twice", any_of(gt("create_promise_failure_count", 1))),
        tr("close:transferred/support", "transferred to support", any_of(gt("transfer_support_success_count", 0))),
        tr("close:transferred/restructuring", "transferred to restructuring", any_of(gt("transfer_restructuring_success_count", 0))),
        tr("close:transferred/human", "transferred to a human", any_of(gt("transfer_general_success_count", 0))),
        tool_tr("close:paid", "The customer says they already paid this past-due amount. You said payments can take one business day to appear and said goodbye."),
        tool_tr("close:no_promise/dispute", "The customer says the debt is not theirs, they never had the product, or it was closed or paid off in the past. You did not argue and said goodbye."),
        tool_tr("close:no_promise/hardship", "The customer mentioned illness, a death in the family or job loss and declined the transfer to customer support. You said goodbye."),
        tool_tr("close:no_promise/not_talking", "The customer said for the second time that they do not want to talk. You said goodbye."),
    ],
}

promise_done = {
    "name": "promise_done", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
    "task_message": ("A payment promise was recorded. A recorded promise cannot be changed or cancelled in this call; if asked, say they can change it in the mobile app. "
                     "A request for a new payment plan or lower instalments: call transfer_restructuring. A request for a human: ask once whether you can help first; if they insist, call transfer_general. "
                     "Illness, a death in the family or job loss: one short sentence of sympathy, and offer the customer support team; if they accept, call transfer_support. "
                     "Answer other questions briefly. Do not take another promise."),
    "tools": [T_RESTR, T_GENERAL, T_SUPPORT],
    "max_node_turns": 6, "max_turn_transition": "close:promise",
    "transitions": [
        tr("close:transferred/support", "transferred to support", any_of(gt("transfer_support_success_count", 0))),
        tr("close:transferred/restructuring", "transferred to restructuring", any_of(gt("transfer_restructuring_success_count", 0))),
        tr("close:transferred/human", "transferred to a human", any_of(gt("transfer_general_success_count", 0))),
        tr("close:promise", "nothing else", {"operator": "matches_intent",
           "description": "The customer has nothing else: says no, no thanks, that's all, thank you, or goodbye, and asks for nothing new."}),
    ],
}

get_account = {
    "name": "get_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "account_facts",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 2},
                     "function": {"name": "get_account", "handler": "__function__:api_call", "description": "Get the late products.",
                                  "parameters": {"type": "object", "properties": {
                                      "url": {"type": "string", "default": SERVER + "/get_account"},
                                      "method": {"type": "string", "default": "POST"},
                                      "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                                      "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}}, "required": ["customer_id"]}}}}}],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "suppress_tool_results": True,
    "transitions": [tr("account_facts", "always", {"operator": "always"})],
}

schedule = {
    "name": "schedule_callback", "node_type": "api_request", "passthrough": True,
    "passthrough_default_transition": "close:not_reached/callback_failed",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 1},
                     "function": {"name": "schedule_callback", "handler": "__function__:api_call", "description": "Book a callback.",
                                  "parameters": {"type": "object", "properties": {
                                      "url": {"type": "string", "default": SERVER + "/schedule_callback"},
                                      "method": {"type": "string", "default": "POST"},
                                      "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                                      "body": {"type": "object", "properties": {
                                          "customer_id": {"type": "string", "default": "{{customer_id}}"},
                                          "date": {"type": "string", "default": "{{cb_date_ok}}"},
                                          "time": {"type": "string", "default": "{{cb_time_ok}}"}},
                                          "required": ["customer_id", "date", "time"]}}}}}],
    "response_mapping": [{"path": "data.ok", "variable": "cb_booked"}],
    "transitions": [
        tr("close:not_reached/callback", "the callback was booked",
           any_of(eq("cb_booked", "true"), eq("cb_booked", "True"),
                  eq("schedule_callback_response.data.ok", "true"), eq("schedule_callback_response.data.ok", "True"))),
        tr("close:not_reached/callback_failed", "always", {"operator": "always"}),
    ],
}

nodes = {
    "setup": code_node("setup", SETUP, "opening"),
    "opening": opening_node("opening", "who_1", {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"}, "opening_retry"),
    "opening_retry": opening_node("opening_retry", "who_2", {"type": "llm", "prompt": (
        "If the person asked a question, answer it briefly first (robot or AI: you are Freya Bank's digital assistant; scam: they can verify the call by phoning Freya Bank's customer service number; "
        "why you call: you can explain only to {{title}} {{last_name}}). Then ask exactly once: \"Am I speaking with {{title}} {{last_name}}?\" Do not call a tool.")},
        "close:not_reached/unclear"),
    "identity": identity_node("identity", "id_decline_1",
                              {"type": "tts", "text": "Thank you. Before we continue, I need to ask two security questions. What is your date of birth?"},
                              "identity_2", ""),
    "identity_2": identity_node("identity_2", "id_decline_2",
                                {"type": "llm", "prompt": "Explain once, in one sentence, that these questions protect their account. Then ask again the security question that is still open. Do not call a tool in this message."},
                                "close:not_verified/declined",
                                "You already explained once that the questions protect the account; do not explain again. "),
    "third_party": third_party_node("third_party", "cb_day", "cb_time", "tp_event",
                                    {"type": "llm", "prompt": "Do not say why you are calling. Ask when {{title}} {{last_name}} can be reached, one exact day and time. If the person already said a day and time, repeat them and ask if that is right. Do not call a tool."},
                                    "check_callback_1", ""),
    "check_callback_1": code_node("check_callback_1", check_callback_code(["cb_day"], ["cb_time"]), "third_party_retry",
                                  [tr("schedule_callback", "the time is in the window", any_of(eq("cb_ok", "yes")))]),
    "third_party_retry": third_party_node("third_party_retry", "cb_day2", "cb_time2", "tp_event2",
                                          {"type": "llm", "prompt": "Say that this time is not possible. Say we can call {{cb_window}}, and ask once for another day and time. Do not say why you are calling. Do not call a tool."},
                                          "check_callback_2",
                                          "The first time offered was outside the allowed window; you are asking once for another time. "),
    "check_callback_2": code_node("check_callback_2", check_callback_code(["cb_day2", "cb_day"], ["cb_time2", "cb_time"]), "close:not_reached/no_callback",
                                  [tr("schedule_callback", "the time is in the window", any_of(eq("cb_ok", "yes")))]),
    "schedule_callback": schedule,
    "get_account": get_account,
    "account_facts": code_node("account_facts", ACCOUNT, "item:first",
                               [tr("close:no_promise/account_error", "the account could not be read", any_of(eq("acct_state", "missing")))]),
    "negotiate": negotiate,
    "promise_done": promise_done,
}
# The third_party retry path: its own "a day and a time" transition should fire on either new field.
nodes["third_party_retry"]["transitions"][3]["condition"] = any_of(
    {"variable": "cb_time2", "operator": "is_set"}, {"variable": "cb_day2", "operator": "is_set"})
# get_account failure: route before account_facts
nodes["get_account"]["transitions"].insert(0, tr("close:no_promise/account_error", "get_account failed",
                                                 any_of(gt("get_account_failure_count", 0))))

body = {"initial_node": "setup", "system_prompt": SYSTEM, "nodes": nodes, "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}


def ev(quote, source=BRIEF):
    return [{"source": source, "quote": quote}]


Q_TABLE_NP = "Outcome: no_promise; Reason: refused`, `hardship`, `dispute`, `service_error"
Q_TABLE_NV = "Outcome: not_verified; Reason: failed`, `declined"
Q_TABLE_NR = "Outcome: not_reached; Reason: callback`, `no_callback`, `wrong_number`, `deceased`, `unclear"
Q_TABLE_TR = "Outcome: transferred; Reason: restructuring`, `human`, `support"
BYE = " Thank you for your time. Goodbye."

closings = {
    "promise": {"set": {"outcome": "promise"}, "say": "Thank you for your time. Goodbye.",
                "evidence": ev("Outcome: promise; Reason: none; When: at least one promise was recorded")},
    "paid": {"set": {"outcome": "paid"}, "evidence": ev("Outcome: paid; Reason: none; When: rule 39")},
    "transferred/restructuring": {"set": {"outcome": "transferred", "reason": "restructuring"}, "say": "I am connecting you now." + BYE, "evidence": ev(Q_TABLE_TR)},
    "transferred/human": {"set": {"outcome": "transferred", "reason": "human"}, "say": "I am connecting you now." + BYE, "evidence": ev(Q_TABLE_TR)},
    "transferred/support": {"set": {"outcome": "transferred", "reason": "support"}, "say": "I am connecting you now." + BYE, "evidence": ev(Q_TABLE_TR)},
    "no_promise/refused": {"set": {"outcome": "no_promise", "reason": "refused"}, "say": "I understand." + BYE, "evidence": ev(Q_TABLE_NP)},
    "no_promise/not_talking": {"set": {"outcome": "no_promise", "reason": "refused"}, "evidence": ev(Q_TABLE_NP)},
    "no_promise/hardship": {"set": {"outcome": "no_promise", "reason": "hardship"}, "evidence": ev(Q_TABLE_NP)},
    "no_promise/dispute": {"set": {"outcome": "no_promise", "reason": "dispute"}, "evidence": ev(Q_TABLE_NP)},
    "no_promise/service_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                 "say": "I am sorry, I could not record your promise because of a technical problem." + BYE, "evidence": ev(Q_TABLE_NP)},
    "no_promise/account_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                 "say": "I am sorry, I cannot reach your account details right now because of a technical problem." + BYE, "evidence": ev(Q_TABLE_NP)},
    "not_verified/failed": {"set": {"outcome": "not_verified", "reason": "failed"},
                            "say": "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch." + BYE, "evidence": ev(Q_TABLE_NV)},
    "not_verified/declined": {"set": {"outcome": "not_verified", "reason": "declined"},
                              "say": "I understand. Without the security questions I cannot continue." + BYE, "evidence": ev(Q_TABLE_NV)},
    "not_reached/callback": {"set": {"outcome": "not_reached", "reason": "callback"}, "say": "Thank you, we will call back at that time. Goodbye.", "evidence": ev(Q_TABLE_NR)},
    "not_reached/callback_failed": {"set": {"outcome": "not_reached", "reason": "no_callback"},
                                    "say": "I am sorry, I could not book the callback because of a technical problem." + BYE, "evidence": ev(Q_TABLE_NR)},
    "not_reached/no_callback": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "say": "Thank you for your time. Goodbye.", "evidence": ev(Q_TABLE_NR)},
    "not_reached/wrong_number": {"set": {"outcome": "not_reached", "reason": "wrong_number"}, "say": "I apologise for the trouble. Thank you, goodbye.", "evidence": ev(Q_TABLE_NR)},
    "not_reached/deceased": {"set": {"outcome": "not_reached", "reason": "deceased"}, "say": "I am sorry for your loss. Thank you, goodbye.", "evidence": ev(Q_TABLE_NR)},
    "not_reached/unclear": {"set": {"outcome": "not_reached", "reason": "unclear"}, "say": "I could not confirm who I am speaking with. Thank you, goodbye.", "evidence": ev(Q_TABLE_NR)},
}

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": API, "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]},
    "fields": {"customer_id": "{{customer_id}}"},
    "closings": closings,
    "ladder": {"template": "negotiate", "done": "close:no_promise/refused",
               "items": {"count": "item_count", "max": 1, "evidence": ev("Freya Bank calls customers who are 1 to 45 days late on one product.")},
               "attempts": {"allowed": "attempts_allowed_{i}", "max": 3,
                            "evidence": ev("days_late: 8 to 45; Band: late; Deadline: the 7th business day after today; Persuasion attempts: 3")},
               "refusal": "refused_{i}_{a}"},
    "precedence": [
        {"closing": "not_verified/failed",
         "when": [{"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"},
                  {"variable": "verify_identity_response.data.all_verified", "operator": "not_equals", "operand": "true"},
                  {"variable": "verify_identity_response.data.all_verified", "operator": "not_equals", "operand": "True"}],
         "keep": [], "evidence": ev("After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`.")},
        {"closing": "promise", "when": [{"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}],
         "keep": ["transferred/restructuring", "transferred/human", "transferred/support"],
         "evidence": ev("If a transfer follows a recorded promise, close as `transferred` with that transfer's reason.")
                     + ev("Outcome: promise; Reason: none; When: at least one promise was recorded")},
    ],
}

Path("out").mkdir(exist_ok=True)
Path(f"out/{SLOT}.body.json").write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
Path(f"out/{SLOT}.closing.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
print("written")
