"""Generate out/pl-g6-contract-raw.workflow.json from the rules of briefs/pl-g6-contract-raw.md.

Run: python3 scripts/build_workflow.py
"""
import json
from pathlib import Path

SLOT = "pl-g6-contract-raw"
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]


# ------------------------------------------------------------------ helpers

def leaf(type_, default, description=None, enum=None):
    d = {"type": type_, "default": default}
    if description:
        d["description"] = description
    if enum:
        d["enum"] = enum
    return d


def api_tool(name, description, body, required, max_retries=0, response_mapping=None, post=None, pre=None):
    tool = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": f"{BASE}/{name}"},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": body, "required": required},
                },
            },
        },
    }
    if response_mapping:
        tool["response_mapping"] = response_mapping
    if post:
        tool["post_process_code"] = post
    if pre:
        tool["pre_process_code"] = pre
    return tool


def code_node(name, code, next_transitions):
    assert "{{" not in code and "}}" not in code, name
    return {
        "name": name,
        "node_type": "code",
        "passthrough": True,
        "passthrough_default_transition": next_transitions[-1]["target_node"],
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "pre_actions": [{
            "type": "function",
            "function": {
                "name": "code_exec",
                "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": code},
                    "timeout_ms": {"type": "number", "default": 10000},
                }},
            },
        }],
        "transitions": next_transitions,
    }


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def is_true(target, desc, variables):
    conds = []
    for v in variables:
        conds += [{"variable": v, "operator": "equals", "operand": "true"},
                  {"variable": v, "operator": "equals", "operand": "True"}]
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": conds}}


def tool_move(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


# ------------------------------------------------------------------ code

DATE_CODE = r'''
import datetime
HOL = set(HOLIDAYS_LIST)
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def say(d):
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MON[d.month - 1] + ' ' + str(d.year)
def nextbd(d):
    x = d + datetime.timedelta(days=1)
    while not isbd(x):
        x = x + datetime.timedelta(days=1)
    return x
def nth_bd(d, n):
    x = d
    for i in range(n):
        x = nextbd(x)
    return x
def last_bd_of_week(d):
    monday = d - datetime.timedelta(days=d.weekday())
    best = None
    for i in range(7):
        x = monday + datetime.timedelta(days=i)
        if isbd(x):
            best = x
    return best
try:
    raw = str(vars.get('now') or '').strip()
    try:
        now = datetime.datetime.strptime(raw[:16], '%Y-%m-%dT%H:%M')
    except Exception:
        try:
            now = datetime.datetime.strptime(raw[:10], '%Y-%m-%d').replace(hour=10)
        except Exception:
            now = datetime.datetime.utcnow()
    today = now.date()
'''

SETUP_CODE = (DATE_CODE + r'''
    hhmm = now.strftime('%H:%M')
    nb = nextbd(today)
    lines = []
    lines.append('Current date and time (the only clock you use): ' + say(today) + ', ' + hhmm + ' (' + today.isoformat() + ').')
    if now.hour < 19:
        if now.hour < 10:
            lines.append('Allowed callback today: ' + say(today) + ' (date ' + today.isoformat() + '), any time from 10:00 to 19:00.')
        else:
            lines.append('Allowed callback today: ' + say(today) + ' (date ' + today.isoformat() + '), any time later than ' + hhmm + ' and not later than 19:00.')
    else:
        lines.append('No callback is possible today any more: it is after 19:00.')
    lines.append('Allowed callback on the next business day: ' + say(nb) + ' (date ' + nb.isoformat() + '), any time from 10:00 to 19:00, both included.')
    lines.append('Any other day, or any time before 10:00 or after 19:00, is outside the window.')
    vars['callback_facts'] = '\n'.join(lines)
    vars['today_spoken'] = say(today)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['callback_facts'] = 'Callback window: today or the next business day, from 10:00 to 19:00, and later than the current time ' + str(vars.get('now')) + '.'
    vars['today_spoken'] = str(vars.get('now'))
    vars['setup_state'] = 'error'
''').replace("HOLIDAYS_LIST", repr(HOLIDAYS))

PREPARE_CODE = (DATE_CODE + r'''
    import json, re
    products = vars.get('products')
    if isinstance(products, str):
        try:
            products = json.loads(products)
        except Exception:
            try:
                products = json.loads(products.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
            except Exception:
                products = None
    if isinstance(products, dict):
        products = [products]
    if not isinstance(products, list) or not products:
        flat = {}
        for k in list(vars.keys()):
            m = re.search(r'products[.\[](\d+)\]?[.](\w+)$', str(k))
            if m:
                flat.setdefault(int(m.group(1)), {})[m.group(2)] = vars.get(k)
        products = [flat[i] for i in sorted(flat)]
    p = products[0] if products else None
    if not isinstance(p, dict) or p.get('past_due') in (None, ''):
        raise ValueError('no product')
    def num(x):
        try:
            return float(x)
        except Exception:
            return None
    def money(x):
        if x is None:
            return 'unknown'
        if abs(x - round(x)) < 0.005:
            return str(int(round(x)))
        return '%.2f' % x
    ptype = str(p.get('type') or '')
    if ptype == 'credit_card':
        last4 = str(p.get('card_last4') or '').strip()
        phrase = 'credit card ending ' + last4 if last4 else 'credit card'
        floor = num(p.get('minimum_payment'))
    elif ptype == 'personal_loan':
        phrase = 'personal loan'
        floor = num(p.get('instalment_amount'))
    elif ptype == 'car_loan':
        phrase = 'car loan'
        floor = num(p.get('instalment_amount'))
    else:
        phrase = ptype.replace('_', ' ') or 'account'
        floor = num(p.get('minimum_payment')) or num(p.get('instalment_amount'))
    past_due = num(p.get('past_due'))
    try:
        days_late = int(float(p.get('days_late')))
    except Exception:
        days_late = 0
    if days_late <= 7:
        band, nth, attempts = 'early', 12, 1
    else:
        band, nth, attempts = 'late', 7, 2
    deadline = nth_bd(today, nth)
    lb = last_bd_of_week(today)
    if lb is None or lb <= today:
        lb = last_bd_of_week(today + datetime.timedelta(days=7))
        a1_note = 'today is the last business day of this week, or it has passed, so it is the last business day of next week'
    else:
        a1_note = 'the last business day of this week'
    if lb > deadline:
        lb = deadline
    vars['product_id'] = str(p.get('product_id') or '')
    vars['product_phrase'] = phrase
    vars['product_type'] = ptype
    vars['past_due_spoken'] = money(past_due)
    vars['floor_spoken'] = money(floor)
    vars['days_late_spoken'] = str(days_late)
    vars['band'] = band
    vars['deadline_iso'] = deadline.isoformat()
    vars['deadline_spoken'] = say(deadline)
    vars['attempt1_iso'] = lb.isoformat()
    vars['attempt1_spoken'] = say(lb)
    L = []
    L.append('Today: ' + say(today) + ' (' + today.isoformat() + '). Today is ' + ('a business day.' if isbd(today) else 'NOT a business day, so no promise can be for today.'))
    L.append('Band: ' + band + ' (' + str(days_late) + ' days late). Deadline: ' + say(deadline) + ' (' + deadline.isoformat() + '), the ' + str(nth) + 'th business day after today. Persuasion attempts allowed: ' + str(attempts) + '.')
    L.append('Attempt 1 date: ' + say(lb) + ' (' + lb.isoformat() + '), ' + a1_note + '.')
    if attempts == 2:
        L.append('Attempt 2: the floor amount ' + money(floor) + ' euros on the deadline ' + say(deadline) + ' (' + deadline.isoformat() + ').')
    else:
        L.append('There is no attempt 2 in the early band.')
    L.append('Calendar. Each line: the date, then what to do if the customer names it.')
    d = today
    end = deadline + datetime.timedelta(days=10)
    while d <= end:
        tag = ' (today)' if d == today else ''
        if d > deadline:
            rule = 'after the deadline: say the latest date you can record is ' + say(deadline) + ' and offer it'
        elif isbd(d):
            rule = 'allowed'
        else:
            why = 'Freya Bank holiday' if d.isoformat() in HOL else 'weekend'
            rule = why + ': offer the next business day, ' + say(nextbd(d)) + ' (' + nextbd(d).isoformat() + ')'
        L.append('- ' + say(d) + ' = ' + d.isoformat() + tag + ': ' + rule)
        d = d + datetime.timedelta(days=1)
    L.append('Any date later than this list is after the deadline.')
    monday = today - datetime.timedelta(days=today.weekday())
    this_w = []
    next_w = []
    for i in range(7):
        x = monday + datetime.timedelta(days=i)
        y = x + datetime.timedelta(days=7)
        this_w.append('"this ' + WD[i] + '" = ' + x.isoformat() + ('' if x >= today else ' (already past)'))
        next_w.append('"next ' + WD[i] + '" = ' + y.isoformat())
    L.append('Weekday words (current week runs Monday to Sunday): ' + '; '.join(this_w) + '.')
    L.append('Following week: ' + '; '.join(next_w) + '.')
    L.append('"Tomorrow" = ' + (today + datetime.timedelta(days=1)).isoformat() + '.')
    vars['date_facts'] = '\n'.join(L)
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_state'] = 'error'
    vars['date_facts'] = ''
    for k in ('product_phrase', 'past_due_spoken', 'floor_spoken', 'days_late_spoken', 'deadline_spoken', 'attempt1_spoken'):
        if not vars.get(k):
            vars[k] = 'unknown'
''').replace("HOLIDAYS_LIST", repr(HOLIDAYS))

VERIFY_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            def t(x):
                return x is True or str(x).lower() == 'true'
            left = d.get('wrong_answers_left')
            try:
                left_n = int(left)
            except Exception:
                left_n = None
            if t(d.get('all_verified')):
                msg = 'Both security answers passed.'
            elif d.get('hint') == 'day_month_swapped':
                msg = 'Day and month look swapped. This does not count as a wrong answer. Ask the customer to say the date of birth again with the month as a word, for example: the third of April 1985. Then call verify_identity again.'
            elif left_n is not None and left_n <= 0 and not t(d.get('verified')):
                msg = 'Three wrong answers: the security check has ended. Say nothing about the account or why you called. Tell the customer to use the Freya Bank mobile app or visit a branch. Then thank them, say goodbye, and call transition_to_close_not_verified_failed in the same message.'
            elif t(d.get('verified')):
                msg = 'This answer is correct. Now ask the next security question that has not passed yet (the last four digits of the phone number on file). Ask only that.'
            elif d.get('ok') is False or str(d.get('ok')).lower() == 'false':
                msg = 'The answer could not be read. It does not count as a wrong answer. Ask the customer to say it again. A date of birth must be sent as YYYY-MM-DD, a phone answer as four digits.'
            else:
                msg = 'This answer does not match our records. Tell the customer it does not match and ask the same question again.' + (' Wrong answers left: ' + str(left_n) + '.' if left_n is not None else '')
            d['what_to_do_next'] = msg
except Exception:
    pass
'''

PROMISE_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            if d.get('ok') is True or str(d.get('ok')).lower() == 'true':
                d['what_to_do_next'] = 'The promise is recorded.'
            else:
                d['what_to_do_next'] = 'The promise was NOT recorded. Never say it is recorded. If this is the first failure in this call, call create_promise again now with the same values. If create_promise already failed once before in this call, tell the customer you could not record the promise, thank them, say goodbye, and call transition_to_close_no_promise_service_error in the same message.'
except Exception:
    pass
'''

TRANSFER_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            if d.get('ok') is True or str(d.get('ok')).lower() == 'true':
                d['what_to_do_next'] = 'The transfer is set up. Tell the customer a colleague will take over now, thank them, say goodbye, and in the same message call the closing tool for the queue you used: restructuring -> transition_to_close_transferred_restructuring, general -> transition_to_close_transferred_human, customer_support -> transition_to_close_transferred_support.'
            else:
                d['what_to_do_next'] = 'The transfer did NOT work. Never say the customer is being transferred. Tell the customer you could not transfer the call right now, then continue with the call.'
except Exception:
    pass
'''

CALLBACK_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            if d.get('ok') is True or str(d.get('ok')).lower() == 'true':
                d['what_to_do_next'] = 'The callback is booked. Tell the person when we will call back, thank them, say goodbye, and call transition_to_close_not_reached_callback in the same message.'
            else:
                d['what_to_do_next'] = 'The callback was NOT booked. Never say it is booked. If this is the first failure, call schedule_callback again with the same values. If it failed before, tell the person you could not book the callback, thank them, say goodbye, and call transition_to_close_not_reached_no_callback in the same message.'
except Exception:
    pass
'''

CLOSE_PRE = r'''
try:
    b = config.get('body')
    if isinstance(b, dict):
        def t(name):
            return str(vars.get(name, '')).lower() == 'true'
        transfer_ok = t('transfer_ok') or t('transfer_to_agent_response.data.ok')
        promise_ok = t('promise_ok') or t('create_promise_response.data.ok')
        callback_ok = t('callback_ok') or t('schedule_callback_response.data.ok')
        queue = str(vars.get('transfer_to_agent_args.queue') or '')
        qmap = dict(restructuring='restructuring', general='human', customer_support='support')
        if transfer_ok and queue in qmap:
            b['outcome'] = 'transferred'
            b['reason'] = qmap[queue]
        elif promise_ok and b.get('outcome') != 'transferred':
            b['outcome'] = 'promise'
        elif callback_ok and b.get('outcome') == 'not_reached':
            b['reason'] = 'callback'
        if b.get('outcome') in ('promise', 'paid'):
            b.pop('reason', None)
        b['channel'] = 'voice'
except Exception:
    pass
'''

# ------------------------------------------------------------------ tools

def verify_tool():
    return api_tool(
        "verify_identity",
        "Check one security answer. CALL it every time the customer gives an answer to a security question, once per answer.",
        {
            "customer_id": leaf("string", "{{customer_id}}"),
            "field": leaf("string", "{{field}}", "Which question was answered. One of: date_of_birth, phone_last4.", ["date_of_birth", "phone_last4"]),
            "answer": leaf("string", "{{answer}}", "For date_of_birth: the date as YYYY-MM-DD (a date given only in numbers is day, then month, then year). For phone_last4: exactly four digits."),
        },
        ["field", "answer"],
        response_mapping=[{"path": "data.all_verified", "variable": "id_all_verified"},
                          {"path": "data.wrong_answers_left", "variable": "id_wrong_left"}],
        post=VERIFY_POST,
    )


def transfer_tool():
    return api_tool(
        "transfer_to_agent",
        "Hand the call to a person. CALL it only when a rule says to transfer: queue restructuring for a new payment plan or lower instalments, queue general when the customer insists on a human after you asked once whether you can help, queue customer_support when a customer with illness, a death in the family or job loss accepts your offer of the customer support team.",
        {
            "customer_id": leaf("string", "{{customer_id}}"),
            "queue": leaf("string", "{{queue}}", "One of: restructuring, general, customer_support.", ["restructuring", "general", "customer_support"]),
        },
        ["queue"],
        response_mapping=[{"path": "data.ok", "variable": "transfer_ok"}],
        post=TRANSFER_POST,
    )


def promise_tool():
    return api_tool(
        "create_promise",
        "Record the payment promise. CALL it only after you read back the product, the amount and the date and the customer gave a clear yes to \"Do you confirm?\".",
        {
            "customer_id": leaf("string", "{{customer_id}}"),
            "product_id": leaf("string", "{{product_id}}"),
            "amount_eur": leaf("number", "{{amount_eur}}", "The confirmed amount in euros, a number such as 120.5."),
            "promise_date": leaf("string", "{{promise_date}}", "The confirmed payment date as YYYY-MM-DD."),
            "channel": leaf("string", "voice", None, ["voice"]),
        },
        ["amount_eur", "promise_date"],
        response_mapping=[{"path": "data.ok", "variable": "promise_ok"}],
        post=PROMISE_POST,
    )


def callback_tool():
    return api_tool(
        "schedule_callback",
        "Book a callback. CALL it when the person names a day and a time that are inside the allowed callback window.",
        {
            "customer_id": leaf("string", "{{customer_id}}"),
            "date": leaf("string", "{{callback_date}}", "Callback date as YYYY-MM-DD."),
            "slot_time": leaf("string", "{{slot_time}}", "Callback time as HH:MM, 24 hour."),
        },
        ["date", "slot_time"],
        response_mapping=[{"path": "data.ok", "variable": "callback_ok"}],
        post=CALLBACK_POST,
    )


def get_account_action():
    return {
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
                "body": {"type": "object", "properties": {"customer_id": leaf("string", "{{customer_id}}")}, "required": []},
            }},
        },
    }


# ------------------------------------------------------------------ closing steps

CLOSES = {
    # key: (outcome, reason, when)
    "promise": ("promise", None, "a payment promise was recorded and nothing else is needed"),
    "paid": ("paid", None, "the verified customer says they already paid this past-due amount"),
    "transferred_restructuring": ("transferred", "restructuring", "transfer_to_agent with queue restructuring succeeded"),
    "transferred_human": ("transferred", "human", "transfer_to_agent with queue general succeeded"),
    "transferred_support": ("transferred", "support", "transfer_to_agent with queue customer_support succeeded"),
    "no_promise_refused": ("no_promise", "refused", "the persuasion attempts are used up, or the verified customer said twice that they do not want to talk"),
    "no_promise_hardship": ("no_promise", "hardship", "the customer mentioned illness, a death in the family or job loss and declined the customer support team"),
    "no_promise_dispute": ("no_promise", "dispute", "the customer says the debt or product is not theirs, or that the product was closed or paid off in the past"),
    "no_promise_service_error": ("no_promise", "service_error", "create_promise failed twice, or the account could not be loaded"),
    "not_verified_failed": ("not_verified", "failed", "three wrong security answers ended the check"),
    "not_verified_declined": ("not_verified", "declined", "the customer declined the security questions a second time, or said twice before verification that they do not want to talk"),
    "not_reached_callback": ("not_reached", "callback", "schedule_callback succeeded"),
    "not_reached_no_callback": ("not_reached", "no_callback", "the person offered no time inside the callback window after one more ask"),
    "not_reached_wrong_number": ("not_reached", "wrong_number", "the person says the number does not belong to the customer"),
    "not_reached_deceased": ("not_reached", "deceased", "the person says the customer has died"),
    "not_reached_unclear": ("not_reached", "unclear", "after the second ask it is still unclear who is on the line"),
}


def close_node(key):
    outcome, reason, _ = CLOSES[key]
    body = {
        "customer_id": leaf("string", "{{customer_id}}"),
        "outcome": leaf("string", outcome, None, ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"]),
        "channel": leaf("string", "voice", None, ["voice"]),
    }
    if reason:
        body["reason"] = leaf("string", reason, "Close reason from the close code list.")
    action = api_tool("close_call", "End the call record.", body, [], max_retries=2, pre=CLOSE_PRE)
    name = "close_" + key
    return name, {
        "name": name,
        "node_type": "api_request",
        "passthrough": True,
        "passthrough_default_transition": "end",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "pre_actions": [action],
        "transitions": [always("end")],
    }


def close_move(key):
    return tool_move("close_" + key, "Close the call: " + CLOSES[key][2] + ". Say the closing words first, in the same message.")


# ------------------------------------------------------------------ prompts

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is the caller. Speak English.
Keep every turn short: one or two plain sentences. Avoid technical words. Ask one question at a time.
Never mention steps, tools, codes, outcomes or system words to the customer.

Rules that hold in every step:
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked "Is this a scam?": say they can verify this call by phoning Freya Bank's customer service number, then continue.
- If asked something you cannot answer from what you were given or from a tool result: say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any term that is not in your instructions.
- When a rule says to call a tool, call it. Saying it is not enough. Call at most one tool per message.
- After every tool result, read what_to_do_next if present and follow it. Then speak to the customer or call the next tool. Never end a turn with nothing.
- When a tool fails, say so. Never say something is recorded, booked or transferred unless the tool returned ok true.
- Closing a call: thank the customer and say goodbye, and in the same message call the matching transition_to_close_... tool. Never say goodbye without calling it.
- Use only the current date and time given to you, never your own clock."""

OPENING_TASK = """You have just said: "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"
Your only job in this step is to find out who is on the line. Before identity is verified, never say "collections", "debt", "payment", "account" or the product, and never say why you are calling. This holds for everyone, including relatives.

{{callback_facts}}

Confirmation: only "yes", "that's me", "speaking" or the customer's own name ({{first_name}} or {{last_name}}) confirms. "Hello", "go ahead", "who is this" and similar do NOT confirm.
- Confirmed: call transition_to_identity at once. Do not ask anything yourself; the next step asks the security questions.
- Not confirmed and not one of the cases below: ask once more "Am I speaking with {{title}} {{last_name}}?". If the person asked a question, answer it first (who is calling: Freya Bank's digital assistant; robot or AI; scam), then ask. That ask is the second ask. If it is still unclear after the second ask, say goodbye and call transition_to_close_not_reached_unclear.
- The person says {{title}} {{last_name}} is not available, or that they are someone else (for example a relative) who knows the customer: call transition_to_someone_else at once, with no text.
- The person says this number does not belong to {{title}} {{last_name}}: apologise for the trouble, thank them, say goodbye, and call transition_to_close_not_reached_wrong_number.
- The person says the customer has died: say exactly "I am sorry for your loss.", ask nothing else, say goodbye, and call transition_to_close_not_reached_deceased.
- The person says twice that they do not want to talk: thank them, say goodbye, and call transition_to_close_not_verified_declined.
- The person asks for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
No other tool is allowed in this step."""

SOMEONE_ELSE_TASK = """Someone other than {{title}} {{last_name}} is on the line.
Never say why you are calling. Say nothing beyond "I am a digital assistant calling from Freya Bank, and this call is recorded." Never mention money, the account or the product. A relative may not answer security questions and may not be told anything about the account, even if they offer to pay; say politely that you can only speak with {{title}} {{last_name}}.

Ask when {{title}} {{last_name}} can be reached.
{{callback_facts}}

- Day and time inside the window: call schedule_callback with the date (YYYY-MM-DD) and the time (HH:MM). If only a part of the day is given ("this afternoon"), ask for the exact time.
- Day or time outside the window: say when you can call back (today later than now, or the next business day, from 10:00 to 19:00) and ask once for another time. If the next answer is also outside the window, or they do not know, do not book: thank them, say goodbye, and call transition_to_close_not_reached_no_callback.
- The number does not belong to the customer: apologise, thank them, say goodbye, and call transition_to_close_not_reached_wrong_number.
- The customer has died: say exactly "I am sorry for your loss.", ask nothing else, say goodbye, and call transition_to_close_not_reached_deceased.
- If it turns out the person IS {{title}} {{last_name}} after all (they say "yes, that's me"): call transition_to_identity.
After schedule_callback returns, follow its what_to_do_next."""

IDENTITY_TASK = """The person confirmed they are {{title}} {{last_name}}. Verify their identity. Before both questions pass, never say "collections", "debt", "payment" or the product, and never say why you are calling. If asked, say you can explain right after the security check.

Ask two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
- After each answer, call verify_identity: field date_of_birth with the date as YYYY-MM-DD, or field phone_last4 with exactly four digits. Convert spoken dates and numbers yourself ("the third of April eighty-five" -> 1985-04-03; "four seven two one" -> 4721). A date given only as numbers is day, then month, then year (03/04/1985 -> 1985-04-03).
- If the customer has not given a full answer yet (only a part of it), wait for the rest before you call the tool.
- Follow what_to_do_next in each result. A wrong answer may be asked again. Three wrong answers in total end the check.
- If the customer does not want to answer, or asks what the call is about instead of answering: explain once that these questions protect their account, and ask again. If they decline again, or ask again what the call is about: thank them, say goodbye, and call transition_to_close_not_verified_declined.
- After three wrong answers: do not state anything about the account. Tell them to use the Freya Bank mobile app or a branch, thank them, say goodbye, and call transition_to_close_not_verified_failed.
- If the customer says twice that they do not want to talk: thank them, say goodbye, and call transition_to_close_not_verified_declined.
- If the customer asks for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
Do not call any tool other than verify_identity, transfer_to_agent and the closing tools in this step."""

NEGOTIATE_TASK = """The customer is verified. You have already said: "Thank you, that is confirmed. I am calling from the collections team about a late payment on your {{product_phrase}}. The past-due amount is {{past_due_spoken}} euros, and the payment is {{days_late_spoken}} days late. Can you make this payment today?"

ACCOUNT FACTS (from get_account)
- Product: {{product_phrase}}. Say it in exactly these words.
- Full past-due amount: {{past_due_spoken}} euros.
- Floor (the lowest amount you may record): {{floor_spoken}} euros.
- Band: {{band}}. Deadline: {{deadline_spoken}} ({{deadline_iso}}).
- Attempt 1 date: {{attempt1_spoken}} ({{attempt1_iso}}).

DATE FACTS
{{date_facts}}

TOOLS
- create_promise: only after a read-back and a clear yes (see CONFIRMING).
- transfer_to_agent: only where a rule below says so.
When a rule says to call a tool, call it. After each tool result, follow what_to_do_next.

SPECIAL CASES. They come before the promise rules.
- Illness, a death in the family or job loss: say one short sentence of sympathy. Make no persuasion attempt. Offer to connect them with the customer support team. If they accept, call transfer_to_agent with queue customer_support. If they decline, thank them, say goodbye, and call transition_to_close_no_promise_hardship. If they still name a date or an amount themselves, handle it with the promise rules and record it.
- "I already paid" (this past-due amount): say payments can take one business day to appear. Take no promise. Thank them, say goodbye, call transition_to_close_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise. Thank them, say goodbye, call transition_to_close_no_promise_dispute.
- A new payment plan or lower instalments: do not describe any plan. Call transfer_to_agent with queue restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
- The customer says twice that they do not want to talk: thank them, say goodbye, call transition_to_close_no_promise_refused.
- A question you cannot answer from these facts: say you do not have that information.

AMOUNTS
- You always propose the amount. Never ask "how much can you pay?". Start with the full past-due amount.
- If the customer says the full amount is too much: offer the floor, {{floor_spoken}} euros, once, and say that the rest stays overdue. If they refuse the floor, that is a flat refusal.
- If the customer proposes an amount from {{floor_spoken}} up to {{past_due_spoken}} euros (both included): accept it.
- Below {{floor_spoken}} euros: say it cannot be recorded and offer the floor once. If they do not accept the floor, that is a flat refusal.

DATES
- A promise date must be today or later, a business day, and not after the deadline {{deadline_spoken}}. Use the calendar in DATE FACTS for every date. Never compute a date yourself.
- A weekend day or a holiday not after the deadline: offer the next business day shown in the calendar.
- A date after the deadline: say the latest date you can record is {{deadline_spoken}} and offer it. If they refuse it, that is a flat refusal.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline {{deadline_spoken}}.
- "Next <weekday>" is that weekday in the following calendar week. "This <weekday>" is the one in the current week. Use the weekday lines in DATE FACTS.

PERSUASION
- A date or an amount the customer proposes is never a refusal. Handle it with AMOUNTS and DATES.
- A flat refusal or a non-answer uses one persuasion attempt. A no to paying today with no date and no amount is a flat refusal.
- Attempt 1: propose {{attempt1_spoken}}, for the full past-due amount, or for the floor if the customer already said the full amount is too much.
- Attempt 2, only in the late band: propose the floor amount {{floor_spoken}} euros on the deadline {{deadline_spoken}}.
- Band {{band}}: the early band has 1 attempt, the late band has 2. When the attempts are used up, stop. Never repeat an offer the customer already refused. Thank them, say goodbye, call transition_to_close_no_promise_refused.

CONFIRMING
- When the customer agrees to an amount and a date, read back the product, the amount and the date, and ask "Do you confirm?". Example: "So that is {{past_due_spoken}} euros for your {{product_phrase}}, on {{attempt1_spoken}}. Do you confirm?"
- If they change the date or the amount, check the new value with AMOUNTS and DATES and read it back again.
- Only after a clear yes, call create_promise with amount_eur (a number) and promise_date (YYYY-MM-DD). One promise only.
- If create_promise fails, say nothing about it being recorded and call it once more. If it fails again, tell the customer you could not record the promise, thank them, say goodbye, and call transition_to_close_no_promise_service_error."""

AFTER_PROMISE_TASK = """The promise for the {{product_phrase}} is recorded, and you said: "Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"
- Nothing else: thank the customer, say goodbye, and call transition_to_close_promise in the same message.
- They want to change or cancel the promise: say it cannot be changed in this call, and that they can change it in the Freya Bank mobile app. Then ask if there is anything else.
- A new payment plan or lower instalments: call transfer_to_agent with queue restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
- Illness, a death in the family or job loss: say one short sentence of sympathy and offer the customer support team. If they accept, call transfer_to_agent with queue customer_support. If they decline, thank them, say goodbye, and call transition_to_close_promise.
- A question you cannot answer: say you do not have that information.
Never record another promise. Never offer any other term."""

ACCOUNT_ERROR_TASK = """The account details could not be loaded. Do not invent any figure. Tell the customer you are sorry, but you cannot access the details right now. Thank them, say goodbye, and call transition_to_close_no_promise_service_error in the same message. No other tool is allowed."""


# ------------------------------------------------------------------ graph

def build():
    nodes = {}
    nodes["setup"] = code_node("setup", SETUP_CODE, [always("opening")])

    opening_moves = [
        tool_move("identity", "The person confirmed they are the customer"),
        tool_move("someone_else", "Someone else answered and the customer is not available, or the person is a relative or other person who knows the customer"),
        close_move("not_reached_wrong_number"),
        close_move("not_reached_deceased"),
        close_move("not_reached_unclear"),
        close_move("not_verified_declined"),
        close_move("transferred_human"),
    ]
    nodes["opening"] = {
        "name": "opening",
        "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
        "on_enter_first_entry_only": True,
        "task_message": OPENING_TASK,
        "tools": [transfer_tool()],
        "max_node_turns": 8,
        "max_turn_transition": "close_not_reached_unclear",
        "transitions": opening_moves,
    }

    nodes["someone_else"] = {
        "name": "someone_else",
        "node_type": "conversation",
        "task_message": SOMEONE_ELSE_TASK,
        "tools": [callback_tool()],
        "max_node_turns": 10,
        "max_turn_transition": "close_not_reached_no_callback",
        "transitions": [
            close_move("not_reached_callback"),
            close_move("not_reached_no_callback"),
            close_move("not_reached_wrong_number"),
            close_move("not_reached_deceased"),
            tool_move("identity", "The person now says they are the customer"),
        ],
    }

    nodes["identity"] = {
        "name": "identity",
        "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you. For your security, I need to ask two questions. What is your date of birth?"},
        "on_enter_first_entry_only": True,
        "task_message": IDENTITY_TASK,
        "tools": [verify_tool(), transfer_tool()],
        "max_node_turns": 14,
        "max_turn_transition": "close_not_verified_declined",
        "transitions": [
            is_true("load_account", "Both security answers passed", ["id_all_verified", "verify_identity_response.data.all_verified"]),
            close_move("not_verified_failed"),
            close_move("not_verified_declined"),
            close_move("transferred_human"),
        ],
    }

    nodes["load_account"] = {
        "name": "load_account",
        "node_type": "api_request",
        "passthrough": True,
        "passthrough_default_transition": "prepare_debt",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "pre_actions": [get_account_action()],
        "response_mapping": [{"path": "data.products", "variable": "products"}, {"path": "data.ok", "variable": "account_ok"}],
        "transitions": [always("prepare_debt")],
    }

    nodes["prepare_debt"] = code_node("prepare_debt", PREPARE_CODE, [
        {"target_node": "negotiate", "description": "The account facts are ready",
         "condition": {"logic": "or", "conditions": [{"variable": "account_state", "operator": "equals", "operand": "ok"}]}},
        always("account_error"),
    ])
    nodes["prepare_debt"]["passthrough_default_transition"] = "account_error"

    nodes["account_error"] = {
        "name": "account_error",
        "node_type": "conversation",
        "task_message": ACCOUNT_ERROR_TASK,
        "max_node_turns": 3,
        "max_turn_transition": "close_no_promise_service_error",
        "transitions": [close_move("no_promise_service_error")],
    }

    transfer_moves = [close_move("transferred_restructuring"), close_move("transferred_human"), close_move("transferred_support")]

    nodes["negotiate"] = {
        "name": "negotiate",
        "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you, that is confirmed. I am calling from the collections team about a late payment on your {{product_phrase}}. The past-due amount is {{past_due_spoken}} euros, and the payment is {{days_late_spoken}} days late. Can you make this payment today?"},
        "on_enter_first_entry_only": True,
        "task_message": NEGOTIATE_TASK,
        "tools": [promise_tool(), transfer_tool()],
        "max_node_turns": 30,
        "max_turn_transition": "close_no_promise_refused",
        "transitions": [
            is_true("after_promise", "create_promise returned ok true", ["promise_ok", "create_promise_response.data.ok"]),
            close_move("paid"),
            close_move("no_promise_dispute"),
            close_move("no_promise_hardship"),
            close_move("no_promise_refused"),
            close_move("no_promise_service_error"),
        ] + transfer_moves,
    }

    nodes["after_promise"] = {
        "name": "after_promise",
        "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
        "on_enter_first_entry_only": True,
        "task_message": AFTER_PROMISE_TASK,
        "tools": [transfer_tool()],
        "max_node_turns": 6,
        "max_turn_transition": "close_promise",
        "transitions": [close_move("promise")] + transfer_moves,
    }

    for key in CLOSES:
        name, node = close_node(key)
        nodes[name] = node

    nodes["end"] = {
        "name": "end",
        "node_type": "end_call",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {"type": "function", "function": {
            "name": "call_closed",
            "handler": "__function__:end_call",
            "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}},
        }},
    }

    return {
        "initial_node": "setup",
        "system_prompt": SYSTEM,
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    }


if __name__ == "__main__":
    wf = build()
    Path("out").mkdir(exist_ok=True)
    Path(f"out/{SLOT}.workflow.json").write_text(json.dumps(wf, indent=1))
    print("nodes:", len(wf["nodes"]))
