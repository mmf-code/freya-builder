"""Generate out/brief-a.workflow.json from Brief A. Run from the kit folder."""
import json, sys

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"

# ---------------------------------------------------------------- code snippets (no double braces allowed)
FACTS_CODE = r'''
import datetime, json, re
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def nbd(d, n):
    k = 0
    x = d
    while k < n:
        x = x + datetime.timedelta(days=1)
        if isbd(x):
            k += 1
    return x
def say(d):
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MON[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
def money(x):
    f = float(x)
    if abs(f - round(f)) < 0.001:
        return str(int(round(f)))
    return '%.2f' % f
def as_list(val):
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except Exception:
            try:
                import ast
                val = ast.literal_eval(val)
            except Exception:
                val = None
    if isinstance(val, dict) and isinstance(val.get('products'), list):
        val = val.get('products')
    if isinstance(val, list) and len(val) > 0:
        return val
    return None
def find_products(v):
    for k in ['products', 'get_account_response.data.products', 'load_account_response.data.products', 'get_account_response.data', 'load_account_response.data']:
        got = as_list(v.get(k))
        if got:
            return got
    items = dict()
    for k in list(v.keys()):
        m = re.search(r'products\.(\d+)\.(\w+)$', str(k))
        if m:
            items.setdefault(int(m.group(1)), dict())[m.group(2)] = v.get(k)
    return [items[i] for i in sorted(items)]

# ---- now
now = None
try:
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?', str(vars.get('now') or ''))
    if m:
        now = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4) or 9), int(m.group(5) or 0))
except Exception:
    now = None
if now is None:
    now = datetime.datetime.now()
today = now.date()
hhmm = '%02d:%02d' % (now.hour, now.minute)
vars['today_text'] = say(today) + ', time ' + hhmm

# ---- callback window (rule 6)
try:
    nb = nbd(today, 1)
    lines = ['Now: ' + say(today) + ', ' + hhmm + '.']
    if now.hour < 19:
        if now.hour < 10:
            lines.append('Allowed today: ' + say(today) + ' from 10:00 to 19:00.')
        else:
            lines.append('Allowed today: ' + say(today) + ' at a time later than ' + hhmm + ' and no later than 19:00.')
    else:
        lines.append('Today is no longer possible: it is past 19:00.')
    lines.append('Allowed on the next business day: ' + say(nb) + ' from 10:00 to 19:00 (both included).')
    lines.append('Every other day, and every time before 10:00 or after 19:00, is OUTSIDE the window.')
    vars['callback_facts'] = '\n'.join(lines)
except Exception:
    vars['callback_facts'] = 'Callback window: today or the next business day, 10:00 to 19:00, later than now.'

# ---- account facts
try:
    prods = find_products(vars)
    p = prods[0] if prods else None
    if not isinstance(p, dict) or p.get('past_due') in (None, ''):
        raise ValueError('no product')
    typ = str(p.get('type') or '')
    if typ == 'credit_card':
        label = 'credit card ending ' + str(p.get('card_last4') or '')
        floor = p.get('minimum_payment')
        floor_name = 'minimum payment'
    elif typ == 'car_loan':
        label = 'car loan'
        floor = p.get('instalment_amount')
        floor_name = 'instalment amount'
    else:
        label = 'personal loan'
        floor = p.get('instalment_amount')
        floor_name = 'instalment amount'
    past_due = float(p.get('past_due'))
    floor = float(floor) if floor not in (None, '') else past_due
    days_late = int(float(p.get('days_late') or 0))
    if days_late <= 7:
        band = 'early'
        deadline = nbd(today, 12)
        attempts = 1
    else:
        band = 'late'
        deadline = nbd(today, 7)
        attempts = 2
    monday = today - datetime.timedelta(days=today.weekday())
    def last_bd_of_week(mon):
        best = None
        for i in range(5):
            d = mon + datetime.timedelta(days=i)
            if isbd(d):
                best = d
        return best
    a1 = last_bd_of_week(monday)
    if a1 is None or a1 <= today:
        a1 = last_bd_of_week(monday + datetime.timedelta(days=7))
    if a1 is None or a1 > deadline:
        a1 = deadline
    vars['product_id'] = str(p.get('product_id') or 'p1')
    vars['product_label'] = label
    vars['past_due_text'] = money(past_due)
    vars['floor_text'] = money(floor)
    vars['days_late_text'] = str(days_late)
    vars['deadline_text'] = say(deadline)
    vars['attempt1_text'] = say(a1)
    vars['band'] = band
    vars['attempts_allowed'] = str(attempts)
    vars['promise_rules'] = json.dumps(dict(today=today.isoformat(), deadline=deadline.isoformat(), floor=floor, full=past_due, holidays=HOL))
    cal = []
    d = today
    end = deadline + datetime.timedelta(days=10)
    while d <= end:
        if d.isoformat() in HOL:
            st = 'Freya Bank holiday, NOT a business day'
        elif d.weekday() >= 5:
            st = 'weekend, NOT a business day'
        else:
            st = 'business day'
        if d > deadline:
            st = st + ', AFTER THE DEADLINE'
        elif isbd(d):
            st = st + ', can be recorded'
        tag = ''
        if d == today:
            tag = ' [today]'
        elif d < monday + datetime.timedelta(days=7):
            tag = ' [this ' + WD[d.weekday()] + ']'
        elif d < monday + datetime.timedelta(days=14):
            tag = ' [next ' + WD[d.weekday()] + ']'
        cal.append('- ' + say(d) + tag + ': ' + st)
        d = d + datetime.timedelta(days=1)
    f = []
    f.append('Today: ' + say(today) + '.')
    f.append('Product: ' + label + ' (product_id ' + vars['product_id'] + ').')
    f.append('Full past-due amount: ' + money(past_due) + '. Days late: ' + str(days_late) + '.')
    f.append('Floor (' + floor_name + '): ' + money(floor) + '. No amount below the floor can be recorded.')
    f.append('Band: ' + band + '. Persuasion attempts allowed: ' + str(attempts) + '.')
    f.append('DEADLINE (latest date that can be recorded): ' + say(deadline) + '.')
    f.append('Attempt 1 date (last business day of this week, or of next week if today is that day): ' + say(a1) + '.')
    if attempts == 2:
        f.append('Attempt 2: the floor amount ' + money(floor) + ' on the deadline ' + say(deadline) + '.')
    else:
        f.append('There is NO attempt 2 in the early band.')
    f.append('"This <weekday>" is the day in the current calendar week (Monday to Sunday). "Next <weekday>" is that weekday in the following calendar week.')
    f.append('Calendar:')
    f.extend(cal)
    vars['account_facts'] = '\n'.join(f)
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_state'] = 'error'
    vars['account_facts'] = 'Account data could not be loaded.'
    for k in ['product_id', 'product_label', 'past_due_text', 'floor_text', 'days_late_text', 'deadline_text', 'attempt1_text', 'band', 'attempts_allowed']:
        if not vars.get(k):
            vars[k] = ''
'''

# ---------------------------------------------------------------- hooks
HOOK_HEAD = "try:\n    if isinstance(result, dict):\n        result.pop('header', None)\n        d = result.get('data')\n        if not isinstance(d, dict):\n            d = dict()\n            result['data'] = d\n"
HOOK_TAIL = "except Exception:\n    pass\n"

def truthy(expr):
    return f"(str({expr}).lower() == 'true')"

VERIFY_POST = HOOK_HEAD + f"""        if {truthy("d.get('all_verified')")}:
            msg = 'Both answers are correct. The customer is verified.'
        elif d.get('hint') == 'day_month_swapped':
            msg = 'Day and month look swapped. This does NOT count as a wrong answer. Ask the customer to say their date of birth again, with the month as a word.'
        elif str(d.get('ok')).lower() == 'false' and 'verified' not in d:
            msg = 'The answer could not be read and was NOT counted. Ask the same question again. For a date of birth ask for the day, the month as a word, and the year.'
        elif 'ok' not in d and 'verified' not in d:
            msg = 'The service failed and nothing was checked. Say there was a short technical problem and call verify_identity again with the same field and answer.'
        elif {truthy("d.get('verified')")}:
            msg = 'This answer is correct. Now ask the next security question: the last four digits of the phone number on file. Do not ask the date of birth again.'
        else:
            left = d.get('wrong_answers_left')
            if str(left) == '0':
                msg = 'Third wrong answer. The check has ended.'
            else:
                msg = 'WRONG answer. Tell the customer it does not match and ask the SAME question again. Wrong answers left: ' + str(left) + '.'
        d['what_to_do_next'] = msg
""" + HOOK_TAIL

PROMISE_POST = HOOK_HEAD + f"""        if {truthy("d.get('ok')")}:
            d['what_to_do_next'] = 'The promise IS recorded.'
        else:
            n = 1
            try:
                n = int(vars.get('cp_fail_n') or 0) + 1
                vars['cp_fail_n'] = str(n)
            except Exception:
                n = 1
            if n <= 1:
                d['what_to_do_next'] = 'The promise was NOT recorded (first failure). Do not say it is recorded. Call create_promise once more right now with the same amount and date.'
            else:
                d['what_to_do_next'] = 'The promise was NOT recorded again (second failure). Tell the customer you could not record the promise. Thank them, say goodbye, and call close_call with no_promise/service_error.'
""" + HOOK_TAIL

CALLBACK_POST = HOOK_HEAD + f"""        if {truthy("d.get('ok')")}:
            d['what_to_do_next'] = 'The callback IS booked. Tell the person when we will call back, thank them, say goodbye, and call close_call with not_reached/callback.'
        else:
            d['what_to_do_next'] = 'The callback was NOT booked. Do not say it is booked. If this is the first failure, call schedule_callback once more with the same date and time. If it failed twice, say you could not book the callback, thank them, say goodbye and call close_call with not_reached/no_callback.'
""" + HOOK_TAIL

TRANSFER_POST = HOOK_HEAD + f"""        if {truthy("d.get('ok')")}:
            d['what_to_do_next'] = 'The transfer IS accepted. Tell the customer you are transferring them now, thank them, say goodbye, and call close_call with transferred and the reason that matches the queue (restructuring, human for general, support).'
        else:
            d['what_to_do_next'] = 'The transfer did NOT work. Do not say it worked. If this is the first failure, call transfer_to_agent once more with the same queue. If it failed twice, tell the customer you could not transfer the call right now.'
""" + HOOK_TAIL

PROMISE_PRE = """try:
    b = config.get('body')
    if isinstance(b, dict):
        pid = str(vars.get('product_id') or '').strip()
        cur = str(b.get('product_id') or '').strip()
        if pid:
            b['product_id'] = pid
        elif not cur or cur.startswith('{'):
            b['product_id'] = 'p1'
except Exception:
    pass
"""

CLOSE_PRE = """try:
    b = config.get('body')
    if isinstance(b, dict):
        c = str(b.pop('close_code', '') or '').strip()
        if c:
            parts = c.split('/')
            b['outcome'] = parts[0]
            if len(parts) > 1 and parts[1]:
                b['reason'] = parts[1]
            else:
                b.pop('reason', None)
except Exception:
    pass
"""

for name, code in [("facts", FACTS_CODE), ("verify", VERIFY_POST), ("promise", PROMISE_POST), ("cb", CALLBACK_POST), ("tr", TRANSFER_POST), ("close", CLOSE_PRE), ("ppre", PROMISE_PRE)]:
    assert "{{" not in code and "}}" not in code, name
    compile(code, name, "exec")

# ---------------------------------------------------------------- tool builders
HEADERS = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}

def api_tool(name, desc, fields, required, retries=0, post=None, pre=None, url_name=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(fields)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": desc,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": f"{BASE}/{url_name or name}"},
                "method": {"type": "string", "default": "POST"},
                "headers": HEADERS,
                "body": {"type": "object", "properties": props, "required": required},
            }},
        },
    }
    if post: t["post_process_code"] = post
    if pre: t["pre_process_code"] = pre
    return t

def verify_tool():
    return api_tool("verify_identity",
        "Check ONE security answer. CALL it every time the customer gives an answer to a security question, right away, before you say anything about the answer.",
        {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                   "description": "Which question was answered. One of: date_of_birth, phone_last4."},
         "answer": {"type": "string", "default": "{{answer}}",
                    "description": "date_of_birth: always YYYY-MM-DD (convert spoken dates; a date said only as numbers is day, then month, then year). phone_last4: exactly four digits."}},
        ["field", "answer"], post=VERIFY_POST)

def promise_tool():
    return api_tool("create_promise",
        "Record the payment promise. CALL it only after you read back product, amount and date and the customer clearly said yes. Never call it twice for a recorded promise.",
        {"amount": {"type": "number", "default": "{{promise_amount}}", "description": "The confirmed amount, a number."},
         "date": {"type": "string", "default": "{{promise_date}}", "description": "The confirmed payment date as YYYY-MM-DD, copied from the calendar."}},
        ["amount", "date"], post=PROMISE_POST, pre=PROMISE_PRE)

def callback_tool():
    return api_tool("schedule_callback",
        "Book a callback for the customer. CALL it as soon as the person names a day and time that is inside the allowed callback window.",
        {"date": {"type": "string", "default": "{{callback_date}}", "description": "Callback date as YYYY-MM-DD."},
         "time": {"type": "string", "default": "{{callback_time}}", "description": "Callback time as HH:MM, 24 hour."}},
        ["date", "time"], post=CALLBACK_POST)

def transfer_tool(queues):
    return api_tool("transfer_to_agent",
        "Hand the call to a person. CALL it when the rules say to transfer. Queue meanings: restructuring = new payment plan or lower instalments; general = customer insists on a human; support = hardship and the customer accepted the support team.",
        {"queue": {"type": "string", "enum": queues, "default": "{{queue}}", "description": "One of: " + ", ".join(queues) + "."}},
        ["queue"], post=TRANSFER_POST)

def close_tool(codes, desc_extra):
    return api_tool("close_call",
        "End the call record. CALL it exactly once, as the very last action, in the same message as your thank-you and goodbye. " + desc_extra,
        {"close_code": {"type": "string", "enum": codes, "default": "{{close_code}}",
                        "description": "Outcome and reason. One of: " + ", ".join(codes) + "."}},
        ["close_code"], retries=1, pre=CLOSE_PRE)

CLOSED = {"logic": "or", "conditions": [
    {"variable": "close_call_success_count", "operator": "greater_than", "operand": 0},
    {"variable": "close_call_failure_count", "operator": "greater_than", "operand": 0}]}

def to_end():
    return {"target_node": "end", "description": "close_call was called", "condition": CLOSED}

def conv(name, task, tools, transitions, on_enter, extraction=None, first_only=False):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": tools,
         "transitions": transitions, "on_enter": on_enter, "max_node_turns": 60,
         "on_enter_first_entry_only": first_only}
    if extraction: n["extraction_schema"] = extraction
    return n

def code_node(name, nxt_transitions, default_next):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": default_next,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": FACTS_CODE}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": nxt_transitions}

def bank_close_node(name, code_outcome, code_reason, spoken, nxt="end"):
    """Engine-run close: fixed farewell line, then close_call with baked values."""
    body = {"customer_id": {"type": "string", "default": "{{customer_id}}"},
            "outcome": {"type": "string", "default": code_outcome}}
    if code_reason:
        body["reason"] = {"type": "string", "default": code_reason}
    return {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "tts", "text": spoken}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 1},
                "function": {"name": "close_call", "handler": "__function__:api_call", "description": "End the call record.",
                    "parameters": {"type": "object", "properties": {
                        "url": {"type": "string", "default": f"{BASE}/close_call"},
                        "method": {"type": "string", "default": "POST"}, "headers": HEADERS,
                        "body": {"type": "object", "properties": body, "required": []}}}}}],
            "transitions": [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}]}

# ---------------------------------------------------------------- prompts
SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. One or two short sentences per turn. Address the customer as {{title}} {{last_name}}.
All date rules use the call's current date and time, never the real clock: {{today_text}}.

Rules that hold in every step:
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked "is this a scam?": say they can verify this call by phoning Freya Bank's customer service number, then continue.
- If you cannot answer a question from the information you were given, say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any term not given to you.
- Never say something is recorded, booked or transferred unless the tool result says ok true.
- When a rule says to use a tool, call the tool. Call one tool per message. After every tool result, read its what_to_do_next and follow it: speak to the customer or call the next tool. Never end a turn with nothing.
- Ending: thank the customer and say goodbye, and in that same message call close_call. close_call is always the very last action. Never call it twice."""

OPENING_TASK = """Step: find out who is on the line. Nothing about the account is known or may be said here. Never say "collections", "debt", "payment", "loan", "card" or any product, to anyone, in this step.

You already said: "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"

- Only "yes", "that's me", "speaking" or the customer's own name confirms identity. "Hello", "go ahead", "who is this" and similar do NOT confirm.
- If the reply does not confirm: if it contains a question, answer it briefly first (robot/AI or scam rules; "who is this" = Freya Bank's digital assistant; "what is it about" = you can explain only to {{title}} {{last_name}}). Then ask again once: "Am I speaking with {{title}} {{last_name}}?". That is the second and last ask.
- If after the second ask it is still not confirmed and the person does not say they are someone else: thank them, say goodbye and call close_call with not_reached/unclear.
- If the person says twice that they do not want to talk: thank them, say goodbye and call close_call with not_verified/declined.
- If the person asks for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general, then follow the result.
Do not ask security questions in this step."""

THIRD_PARTY_TASK = """Step: someone other than {{title}} {{last_name}} answered. You must not say why you are calling, and you may say nothing about any account, even if the person is a relative, offers to pay, or offers to answer security questions. If asked why, say you can only discuss that with {{title}} {{last_name}} personally.

Callback window:
{{callback_facts}}

Handle the person's message:
- They say the customer has died: say exactly "I am sorry for your loss." Ask nothing else. Say goodbye and call close_call with not_reached/deceased.
- They say this number does not belong to the customer (wrong number): apologise, thank them, say goodbye and call close_call with not_reached/wrong_number.
- Otherwise ask when {{title}} {{last_name}} can be reached (a day and a time).
  - A day and a time inside the window: call schedule_callback with the date (YYYY-MM-DD) and time (HH:MM, 24 hour), then follow the result. Turn "3 pm" into 15:00 and "tomorrow" into the date from the window facts.
  - Only a day or only a vague time: ask for the missing part.
  - Outside the window (another day, before 10:00, after 19:00, or not later than now): say that time is not possible, explain the window briefly, and ask ONCE for another time. If the second answer is also outside the window or they cannot give one: do not schedule. Thank them, say goodbye and call close_call with not_reached/no_callback."""

IDENTITY_TASK = """Step: security check. {{title}} {{last_name}} confirmed who they are. Do not say anything about the reason for the call, the account, a debt, a payment or a product in this step.

- Ask two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
- Each time the customer answers, call verify_identity right away (field date_of_birth with the answer as YYYY-MM-DD, or field phone_last4 with four digits). Convert any spoken date to YYYY-MM-DD. A date given only as numbers is day, then month, then year (so 03/04/1985 is 1985-04-03).
- Follow what_to_do_next in the result. A wrong answer may be asked again. If the result says day and month look swapped, ask them to say the month as a word.
- If the customer does not want to answer, or asks what the call is about instead of answering: explain once that these questions protect their account, and ask again. If they refuse again or ask again what it is about: thank them, say goodbye and call close_call with not_verified/declined.
- If the customer says twice they do not want to talk: thank them, say goodbye and call close_call with not_verified/declined.
- If the customer asks for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general, then follow the result."""

NEGOTIATE_TASK = """Step: the customer is verified. You already said: "I am calling from the collections team about a late payment on your {{product_label}}. The past-due amount is {{past_due_text}}, and it is {{days_late_text}} days late. Can you make this payment today?"

ACCOUNT FACTS (use only these numbers and dates):
{{account_facts}}

TOOLS: create_promise (only after a clear yes to the read-back), transfer_to_agent, close_call.

FIRST check the customer's message for these. They come before everything else:
A. Illness, a death in the family, or job loss: say one short sentence of sympathy. Make NO persuasion attempt. Offer to connect them with the customer support team. If they accept: call transfer_to_agent with queue support, then close with transferred/support. If they decline: thank, goodbye, close_call with no_promise/hardship. If they still name a date or an amount themselves, handle it as a promise under the date and amount rules.
B. "I already paid" (this past-due amount): say payments can take one business day to appear. Take no promise. Thank, goodbye, close_call with paid.
C. "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise. Thank, goodbye, close_call with no_promise/dispute.
D. They ask for a new payment plan or lower instalments: do not describe any plan. Call transfer_to_agent with queue restructuring, then close with transferred/restructuring.
E. They ask for a human: ask once whether you can help first. If they insist: transfer_to_agent with queue general, then close with transferred/human.
F. They say twice that they do not want to talk: thank, goodbye, close_call with no_promise/refused.

GETTING THE PROMISE
- The agent proposes every amount. Never ask "how much can you pay?". The first offer is always the full past-due amount {{past_due_text}}.
- Any date or amount the customer proposes is never a refusal. Check it with the date and amount rules.
- Yes to paying today: if today is a business day, read back the full amount for today.

DATE RULES (look every date up in the calendar above; never compute dates yourself)
- A promise date must be today or later, a business day ("can be recorded" in the calendar), and not after the deadline.
- A weekend day or holiday that is not after the deadline: offer the next business day after it.
- A date after the deadline: say the latest date you can record is the deadline, {{deadline_text}}, and offer it. If they refuse the deadline, that is a flat refusal.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
- "This Friday" / "next Friday": use the [this ...] / [next ...] tags in the calendar.

AMOUNT RULES
- Floor = {{floor_text}}. Full = {{past_due_text}}.
- They say the full amount is too much: offer the floor ONCE and say that the rest stays overdue. If they refuse the floor, that is a flat refusal.
- They propose an amount from the floor up to the full amount (both included): accept it.
- Below the floor: say that amount cannot be recorded and offer the floor once. If they do not accept the floor, that is a flat refusal.

PERSUASION ({{attempts_allowed}} attempt(s) allowed, band {{band}})
- A flat refusal or a non-answer uses one attempt. A no to paying today with no date and no amount is a flat refusal.
- Attempt 1: propose the full amount {{past_due_text}} (or the floor {{floor_text}} if they already said the full amount is too much) on {{attempt1_text}}.
- Attempt 2 (late band only): propose the floor {{floor_text}} on the deadline {{deadline_text}}.
- When the allowed attempts are used up and they refuse again: stop. Do not repeat an offer they already refused. Thank, goodbye, close_call with no_promise/refused.

CONFIRMING
- Read back the product, the amount and the date (weekday and date) and ask "Do you confirm?". Call create_promise only after a clear yes, with amount as a number and date as YYYY-MM-DD from the calendar.
- If they change the date or amount at this point, check the new value with the rules and read it back again.
- If create_promise fails, follow what_to_do_next: try once more; if it fails again, say you could not record it and close with no_promise/service_error. Never say it is recorded unless the result says ok true."""

AFTER_PROMISE_TASK = """Step: the promise is recorded and you already told the customer: "Your promise is recorded. You will receive a text message confirming this promise."
- If the customer wants to change or cancel the promise: say it cannot be changed in this call, and that they can change it in the mobile app.
- If they ask for a new payment plan or lower instalments: call transfer_to_agent with queue restructuring, then close with transferred/restructuring. If they insist on a human: transfer_to_agent with queue general, then close with transferred/human.
- Otherwise: thank the customer, say goodbye and call close_call with promise. Do not make another promise."""

ACCOUNT_ERROR_TASK = """Step: the account details could not be loaded. Do not state any amount or date. Say there is a technical problem and you cannot discuss the account right now. Thank the customer, say goodbye and call close_call with no_promise/service_error."""

# ---------------------------------------------------------------- nodes
def eqtrue(var):
    return [{"variable": var, "operator": "equals", "operand": "true"},
            {"variable": var, "operator": "equals", "operand": "True"}]

nodes = {}
nodes["prepare"] = code_node("prepare", [{"target_node": "opening", "description": "always", "condition": {"operator": "always"}}], "opening")

nodes["opening"] = conv("opening", OPENING_TASK,
    [close_tool(["not_reached/unclear", "not_verified/declined", "transferred/human"], "Codes here: not_reached/unclear (identity still not confirmed after the second ask), not_verified/declined (said twice they do not want to talk), transferred/human (after a successful transfer)."),
     transfer_tool(["general"])],
    [{"target_node": "identity", "description": "The customer confirmed they are the person asked for",
      "condition": {"logic": "or", "conditions": [{"variable": "speaker", "operator": "equals", "operand": "customer"}]}},
     {"target_node": "third_party", "description": "Someone else answered",
      "condition": {"logic": "or", "conditions": [{"variable": "speaker", "operator": "equals", "operand": "someone_else"}]}},
     to_end()],
    {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    extraction=[{"name": "speaker", "type": "string", "enum_values": ["customer", "someone_else"], "min_confidence": 0.6,
        "description": "Who answered the phone, judged from the person's LATEST message only. 'customer' ONLY if that message explicitly confirms they are {{title}} {{first_name}} {{last_name}}: yes, that's me, speaking, or they say their own name. 'someone_else' if they say they are a different person, the customer is not there or not available, this is the wrong number, or the customer has died. Leave EMPTY for hello, go ahead, who is this, what is this about, or any other unclear reply."}],
    first_only=True)

nodes["third_party"] = conv("third_party", THIRD_PARTY_TASK,
    [callback_tool(),
     close_tool(["not_reached/callback", "not_reached/no_callback", "not_reached/wrong_number", "not_reached/deceased"], "Codes here: not_reached/callback (after a booked callback), not_reached/no_callback, not_reached/wrong_number, not_reached/deceased.")],
    [to_end()], {"type": "llm"})

nodes["identity"] = conv("identity", IDENTITY_TASK,
    [verify_tool(),
     close_tool(["not_verified/declined", "not_verified/failed", "transferred/human"], "Codes here: not_verified/declined (refused twice), transferred/human (after a successful transfer)."),
     transfer_tool(["general"])],
    [{"target_node": "load_account", "description": "Both security answers verified",
      "condition": {"logic": "or", "conditions": eqtrue("verify_identity_response.data.all_verified")}},
     {"target_node": "identity_failed", "description": "Three wrong answers",
      "condition": {"logic": "or", "conditions": [{"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"}]}},
     to_end()],
    {"type": "llm", "prompt": "Thank {{title}} {{last_name}}. If their last message asked a question, answer it briefly within the rules (do not say why you are calling). Then say that for security you need to ask two questions, and ask for their date of birth. Do not call a tool in this turn."},
    first_only=True)

nodes["identity_failed"] = bank_close_node("identity_failed", "not_verified", "failed",
    "I am sorry, I could not verify your identity, so I cannot continue with this call. Please use the Freya Bank mobile app or visit a branch. Thank you for your time, goodbye.")

nodes["load_account"] = {"name": "load_account", "node_type": "api_request", "passthrough": True,
    "passthrough_default_transition": "compute_account", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 2},
        "function": {"name": "get_account", "handler": "__function__:api_call", "description": "Get the late products.",
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": f"{BASE}/get_account"}, "method": {"type": "string", "default": "POST"},
                "headers": HEADERS,
                "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}}, "required": []}}}}}],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "suppress_tool_results": True,
    "transitions": [{"target_node": "compute_account", "description": "always", "condition": {"operator": "always"}}]}

nodes["compute_account"] = code_node("compute_account", [
    {"target_node": "negotiate", "description": "Account facts ready",
     "condition": {"logic": "or", "conditions": [{"variable": "account_state", "operator": "equals", "operand": "ok"}]}},
    {"target_node": "account_error", "description": "always", "condition": {"operator": "always"}}], "account_error")

NEG_CODES = ["paid", "no_promise/refused", "no_promise/hardship", "no_promise/dispute", "no_promise/service_error",
             "transferred/restructuring", "transferred/human", "transferred/support"]
nodes["negotiate"] = conv("negotiate", NEGOTIATE_TASK,
    [promise_tool(), transfer_tool(["restructuring", "general", "support"]),
     close_tool(NEG_CODES, "Codes here: paid (customer already paid), no_promise/refused, no_promise/hardship, no_promise/dispute, no_promise/service_error (create_promise failed twice), transferred/restructuring, transferred/human, transferred/support (each only after a successful transfer to that queue).")],
    [{"target_node": "after_promise", "description": "The promise was recorded",
      "condition": {"logic": "or", "conditions": eqtrue("create_promise_response.data.ok")}},
     to_end()],
    {"type": "tts", "text": "Thank you, {{title}} {{last_name}}, you are verified. I am calling from the collections team about a late payment on your {{product_label}}. The past-due amount is {{past_due_text}}, and it is {{days_late_text}} days late. Can you make this payment today?"},
    first_only=True)

nodes["after_promise"] = conv("after_promise", AFTER_PROMISE_TASK,
    [transfer_tool(["restructuring", "general"]),
     close_tool(["promise", "transferred/restructuring", "transferred/human"], "Codes here: promise (normal end), transferred/restructuring or transferred/human only after a successful transfer.")],
    [to_end()],
    {"type": "tts", "text": "Thank you. Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
    first_only=True)

nodes["account_error"] = conv("account_error", ACCOUNT_ERROR_TASK,
    [close_tool(["no_promise/service_error"], "Code here: no_promise/service_error.")],
    [to_end()], {"type": "llm"})

nodes["end"] = {"name": "end", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "transitions": [], "terminal": {"type": "function", "function": {"name": "call_closed", "handler": "__function__:end_call",
        "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}

wf = {"initial_node": "prepare", "system_prompt": SYSTEM, "nodes": nodes, "global_nodes": {},
      "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}

json.dump(wf, open(sys.argv[1], "w"), indent=1)
print("written", sys.argv[1], len(nodes), "nodes")
