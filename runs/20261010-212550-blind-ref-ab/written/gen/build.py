"""Generate the phone agent workflow for briefs/brief-a-raw.md + briefs/brief-b-raw.md.

    python3 gen/build.py out/brief-b-raw.workflow.json

All rules come from the two briefs and tools/openapi.json.
"""
import json
import sys

BANK = "https://freya-bank-mock.freyavoice.workers.dev/v1"
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]  # CP-4 2.5 a + OPS-2026-41 item 1


# ---------------------------------------------------------------- python run inside the workflow

DATE_LIB = r'''
import datetime, json, re
HOL = set(HOLIDAYS_LIST)
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

def parse_now():
    raw = str(vars.get('now') or '').strip()
    try:
        dt = datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        try:
            dt = datetime.datetime.combine(datetime.date.fromisoformat(raw[:10]), datetime.time(12, 0))
        except Exception:
            dt = datetime.datetime(2026, 10, 14, 11, 0)
    return dt

def is_bd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL

def add_bd(d, n):
    c = 0
    x = d
    while c < n:
        x = x + datetime.timedelta(days=1)
        if is_bd(x):
            c += 1
    return x

def next_bd_on_or_after(d):
    x = d
    while not is_bd(x):
        x = x + datetime.timedelta(days=1)
    return x

def next_bd_after(d):
    return next_bd_on_or_after(d + datetime.timedelta(days=1))

def last_bd_of_week(monday):
    best = None
    for i in range(7):
        x = monday + datetime.timedelta(days=i)
        if is_bd(x):
            best = x
    return best

def label(d):
    return DAYS[d.weekday()] + ' ' + d.isoformat()

NOW = parse_now()
TODAY = NOW.date()
NOW_HM = NOW.strftime('%H:%M')
MONDAY = TODAY - datetime.timedelta(days=TODAY.weekday())
'''

SETUP_CODE = DATE_LIB + r'''
try:
    vars['today_text'] = label(TODAY) + ', time ' + NOW_HM
    nbd = next_bd_after(TODAY)
    lines = []
    if NOW_HM < '19:00':
        if NOW_HM < '10:00':
            lines.append('- Today, ' + label(TODAY) + ': from 10:00 to 19:00.')
        else:
            lines.append('- Today, ' + label(TODAY) + ': any time later than ' + NOW_HM + ' and no later than 19:00.')
    else:
        lines.append('- Today: no time is left in the window.')
    lines.append('- ' + label(nbd) + ' (next business day): from 10:00 to 19:00.')
    lines.append('- Any other day, or any time before 10:00 or after 19:00, is outside the window.')
    vars['callback_window'] = chr(10).join(lines)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['today_text'] = str(vars.get('now') or '')
    vars['callback_window'] = 'today or the next business day, from 10:00 to 19:00, later than now'
    vars['setup_state'] = 'error'
'''

PREP_CODE = DATE_LIB + r'''
def num(v):
    try:
        return float(v)
    except Exception:
        return None

def money(v):
    if v is None:
        return '?'
    if abs(v - round(v)) < 0.005:
        return str(int(round(v)))
    return '%.2f' % v

def find_products():
    raw = vars.get('products')
    if isinstance(raw, str):
        s = raw.strip()
        try:
            raw = json.loads(s)
        except Exception:
            try:
                import ast
                raw = ast.literal_eval(s)
            except Exception:
                raw = None
    if isinstance(raw, dict) and isinstance(raw.get('products'), list):
        raw = raw.get('products')
    if isinstance(raw, list) and raw:
        return [p for p in raw if isinstance(p, dict)]
    found = dict()
    pat = re.compile(r'products(?:\.|\[)(\d+)\]?\.(\w+)$')
    for k in list(vars.keys()):
        m = pat.search(str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    return [found[i] for i in sorted(found)]

try:
    prods = find_products()
    deadline_early = add_bd(TODAY, 12)
    deadline_late = add_bd(TODAY, 7)
    lbd = last_bd_of_week(MONDAY)
    if lbd is None or lbd <= TODAY:
        lbd = last_bd_of_week(MONDAY + datetime.timedelta(days=7))
    plan = []
    say = []
    ids = []
    max_deadline = TODAY
    for i, p in enumerate(prods):
        pid = str(p.get('product_id') or ('p' + str(i + 1)))
        ids.append(pid)
        typ = str(p.get('type') or '')
        if typ == 'credit_card':
            name = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = num(p.get('minimum_payment'))
            floor_name = 'minimum payment'
        elif typ == 'car_loan':
            name = 'car loan'
            floor = num(p.get('instalment_amount'))
            floor_name = 'instalment'
        else:
            name = 'personal loan'
            floor = num(p.get('instalment_amount'))
            floor_name = 'instalment'
        due = num(p.get('past_due'))
        try:
            late = int(float(p.get('days_late')))
        except Exception:
            late = 0
        if late <= 7:
            stage = 'early'
            deadline = deadline_early
            attempts = 1
        else:
            stage = 'late'
            deadline = deadline_late
            attempts = 2
        if deadline > max_deadline:
            max_deadline = deadline
        a1 = lbd if lbd <= deadline else deadline
        say.append('Your ' + name + ' has a past-due amount of ' + money(due) + ' and is ' + str(late) + ' days late.')
        t = []
        t.append('Product ' + str(i + 1) + ': ' + name + ' (product_id ' + pid + ')')
        t.append('  - full past-due amount: ' + money(due) + '; days late: ' + str(late) + ' (stage: ' + stage + ')')
        t.append('  - floor (' + floor_name + '): ' + money(floor))
        t.append('  - PTP deadline: ' + label(deadline) + '. No PTP date after this day.')
        t.append('  - persuasion attempts: ' + str(attempts))
        t.append('  - attempt 1 offer: the full amount ' + money(due) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much) on ' + label(a1))
        if attempts > 1:
            t.append('  - attempt 2 offer: the floor ' + money(floor) + ' on ' + label(deadline))
        else:
            t.append('  - no attempt 2 (early stage): after the second flat refusal, stop')
        plan.append(chr(10).join(t))
    rows = []
    end = max_deadline + datetime.timedelta(days=8)
    d = TODAY
    while d <= end:
        tags = []
        if d == TODAY:
            tags.append('today')
        if d == TODAY + datetime.timedelta(days=1):
            tags.append('tomorrow')
        if d > TODAY and d < MONDAY + datetime.timedelta(days=7):
            tags.append('this ' + DAYS[d.weekday()])
        if d >= MONDAY + datetime.timedelta(days=7) and d < MONDAY + datetime.timedelta(days=14):
            tags.append('next ' + DAYS[d.weekday()])
        if is_bd(d):
            kind = 'business day'
        elif d.isoformat() in HOL:
            kind = 'BANK HOLIDAY, not a business day; offer ' + label(next_bd_on_or_after(d))
        else:
            kind = 'weekend, not a business day; offer ' + label(next_bd_on_or_after(d))
        rows.append(label(d) + ' | ' + (', '.join(tags) if tags else '-') + ' | ' + kind)
        d = d + datetime.timedelta(days=1)
    n = len(prods)
    vars['product_count'] = str(n)
    vars['product_plan'] = (chr(10) + chr(10)).join(plan)
    vars['date_table'] = chr(10).join(rows)
    vars['today_text'] = label(TODAY) + ', time ' + NOW_HM
    vars['holiday_text'] = ', '.join(sorted(HOL))
    vars['single_product_id'] = ids[0] if ids else 'p1'
    if n == 1:
        opener = 'Thank you, you are verified. I am calling from the collections team about a late payment. ' + say[0] + ' Can you make this payment today?'
    else:
        opener = 'Thank you, you are verified. I am calling from the collections team about late payments on ' + str(n) + ' products. ' + ' '.join(say) + ' Can you pay all of them today?'
    vars['overdue_text'] = opener
    vars['account_state'] = 'ok' if n > 0 else 'error'
except Exception as e:
    vars['account_state'] = 'error'
    vars['product_count'] = '0'
    vars['product_plan'] = ''
    vars['date_table'] = ''
    vars['overdue_text'] = ''
    vars['single_product_id'] = 'p1'
'''


def code_with(lib_code):
    code = lib_code.replace("HOLIDAYS_LIST", json.dumps(HOLIDAYS))
    assert "{{" not in code and "}}" not in code, "code must not contain double braces"
    return code


# ---------------------------------------------------------------- building blocks

def cond_or(*checks):
    return {"logic": "or", "conditions": list(checks)}


def cond_and(*checks):
    return {"logic": "and", "conditions": list(checks)}


def eq(var, val):
    return {"variable": var, "operator": "equals", "operand": val}


def is_true(var):
    return [eq(var, "true"), eq(var, "True")]


def gt(var, val):
    return {"variable": var, "operator": "greater_than", "operand": val}


ALWAYS = {"operator": "always"}


def tr(target, desc, condition):
    return {"target_node": target, "description": desc, "condition": condition}


def tool_tr(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


HOOK_HEAD = (
    "try:\n"
    "    if isinstance(result, dict):\n"
    "        result.pop('header', None)\n"
    "        d = result.get('data')\n"
    "        if not isinstance(d, dict):\n"
    "            d = dict(ok=False, error='service failed')\n"
    "            result['data'] = d\n"
    "        good = d.get('ok') is True or str(d.get('ok')).lower() == 'true'\n"
)
HOOK_TAIL = "        d['what_to_do_next'] = msg\nexcept Exception:\n    pass\n"


def hook(body):
    code = HOOK_HEAD + body + HOOK_TAIL
    assert "{{" not in code and "}}" not in code
    return code


def bank_tool(name, path, description, fields, required, post=None, retries=0):
    props = {
        "url": {"type": "string", "default": BANK + path},
        "method": {"type": "string", "default": "POST"},
        "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
        "body": {"type": "object", "properties": dict(customer_id={"type": "string", "default": "{{customer_id}}"}, **fields),
                 "required": required},
    }
    t = {"type": "function", "config": {"timeoutMs": 15000, "maxRetries": retries},
         "function": {"name": name, "handler": "__function__:api_call", "description": description,
                      "parameters": {"type": "object", "properties": props}}}
    if post:
        t["post_process_code"] = post
    return t


VERIFY_HOOK = lambda tool, what: hook(
    "        if d.get('hint') == 'day_month_swapped':\n"
    "            msg = 'Not counted as a wrong answer: day and month look swapped. Ask the customer to say the month of their date of birth as a word, then call " + tool + " again.'\n"
    "        elif d.get('verified') is True or str(d.get('verified')).lower() == 'true':\n"
    "            msg = 'Correct.'\n"
    "        elif d.get('verified') is False or str(d.get('verified')).lower() == 'false':\n"
    "            msg = 'Wrong answer, it did not match. Wrong answers left: ' + str(d.get('wrong_answers_left')) + '. Tell the customer it did not match and ask for " + what + " again. Do not reveal any account detail.'\n"
    "        else:\n"
    "            msg = 'The answer could not be checked (not counted as wrong). Ask the customer to repeat " + what + ", then call " + tool + " again.'\n"
)

PROMISE_HOOK_SINGLE = hook(
    "        if good:\n"
    "            msg = 'The promise is recorded.'\n"
    "        else:\n"
    "            msg = 'NOT recorded: the service failed. Do not say it is recorded. If this was the first failure, call create_promise again right now with exactly the same amount and date.'\n"
)
PROMISE_HOOK_MULTI = hook(
    "        if good:\n"
    "            msg = 'This promise is recorded. Tell the customer the promise for this product is recorded and say: You will receive a text message confirming this promise. Then go on with the next step.'\n"
    "        else:\n"
    "            msg = 'NOT recorded: the service failed. Do not say it is recorded. If this was the first failure for this product, call create_promise again right now with the same product_id, amount and date. If it was the second failure for this product, tell the customer you could not record the promise for that product; that product later gets add_note with reason service_error.'\n"
)
TRANSFER_HOOK = hook(
    "        if good:\n"
    "            msg = 'Transferred.'\n"
    "        else:\n"
    "            msg = 'The transfer did NOT work. Tell the customer you could not connect them right now.'\n"
)
CALLBACK_HOOK = hook(
    "        if good:\n"
    "            msg = 'The callback is booked.'\n"
    "        else:\n"
    "            msg = 'NOT booked: the service failed. Call schedule_callback once more with the same date and time. Do not say it is booked.'\n"
)
NOTE_HOOK = hook(
    "        if good:\n"
    "            msg = 'Note saved. Continue with the next product that still needs a note, or finish.'\n"
    "        else:\n"
    "            msg = 'The note was NOT saved. Call add_note once more with the same product_id and reason.'\n"
)


def verify_tool(name, field, what):
    return bank_tool(
        name, "/verify_identity",
        f"Check the customer's {what}. CALL it every time the customer gives their {what}. One call per answer.",
        {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": field},
         "answer": {"type": "string", "default": "{{answer}}",
                    "description": "date_of_birth: the date as YYYY-MM-DD (numbers only are day, month, year). phone_last4: exactly four digits."}},
        ["answer"], post=VERIFY_HOOK(name, "their " + what))


def transfer_tool(queue, when):
    return bank_tool(
        "transfer_to_" + queue, "/transfer_to_agent",
        f"Hand the call to the {queue} queue. CALL it only when {when}. Never in the same message as another tool.",
        {"queue": {"type": "string", "enum": ["restructuring", "general", "support"], "default": queue}},
        [], post=TRANSFER_HOOK)


CREATE_SINGLE = bank_tool(
    "create_promise", "/create_promise",
    "Record the payment promise. CALL it only after the customer said a clear yes to your read-back of product, amount and date.",
    {"product_id": {"type": "string", "default": "{{single_product_id}}"},
     "amount": {"type": "number", "default": "{{amount}}", "description": "The confirmed amount, a number."},
     "date": {"type": "string", "default": "{{date}}", "description": "The confirmed payment date as YYYY-MM-DD."}},
    ["amount", "date"], post=PROMISE_HOOK_SINGLE)

CREATE_MULTI = bank_tool(
    "create_promise", "/create_promise",
    "Record one payment promise for one product. CALL it once per product, only after the customer gave one clear yes to the read-back of all promises.",
    {"product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id exactly as in the product list, for example p1."},
     "amount": {"type": "number", "default": "{{amount}}", "description": "The confirmed amount for this product, a number."},
     "date": {"type": "string", "default": "{{date}}", "description": "The confirmed payment date for this product as YYYY-MM-DD."}},
    ["product_id", "amount", "date"], post=PROMISE_HOOK_MULTI)

ADD_NOTE = bank_tool(
    "add_note", "/add_note",
    "Record why one product ended without a promise. CALL it once for every product without a recorded promise, at the very end, never when the call is transferred.",
    {"product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id exactly as in the product list, for example p1."},
     "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "default": "{{reason}}",
                "description": "One of: refused, hardship, dispute, paid, service_error."}},
    ["product_id", "reason"], post=NOTE_HOOK)

CALLBACK = bank_tool(
    "schedule_callback", "/schedule_callback",
    "Book a callback for the customer. CALL it once, when the person names a day and time inside the callback window.",
    {"date": {"type": "string", "default": "{{callback_date}}", "description": "Callback date as YYYY-MM-DD."},
     "time": {"type": "string", "default": "{{callback_time}}", "description": "Callback time as HH:MM, 24 hour."}},
    ["date", "time"], post=CALLBACK_HOOK)

GET_ACCOUNT = bank_tool("get_account", "/get_account", "Get the late products.", {}, [], retries=2)


def ok_success(tool):
    """Tool returned ok: true at least once."""
    return cond_or(cond_and(gt(f"{tool}_success_count", 0), cond_or(*is_true(f"{tool}_response.data.ok"))))


def transfer_routes():
    return [
        tr("finish_transferred_restructuring", "Transferred to restructuring", ok_success("transfer_to_restructuring")),
        tr("finish_transferred_human", "Transferred to a person", ok_success("transfer_to_general")),
        tr("finish_transferred_support", "Transferred to support", ok_success("transfer_to_support")),
    ]


def conv(name, task, tools=None, transitions=None, on_enter=None, extraction=None, max_turns=None, cap_target=None, first_only=True):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": tools or [],
         "transitions": transitions or [], "on_enter": on_enter or {"type": "llm"},
         "on_enter_first_entry_only": first_only}
    if extraction:
        n["extraction_schema"] = extraction
    if max_turns:
        n["max_node_turns"] = max_turns
        n["max_turn_transition"] = cap_target
    return n


# ---------------------------------------------------------------- endings

# (finish step, close step, farewell). Farewell is spoken before close_call runs (Document 1 and 4).
CLOSES = {
    # close step: (outcome, reason)
    "close_promise": ("promise", ""),
    "close_paid": ("paid", ""),
    "close_transferred_restructuring": ("transferred", "restructuring"),
    "close_transferred_human": ("transferred", "human"),
    "close_transferred_support": ("transferred", "support"),
    "close_no_promise_refused": ("no_promise", "refused"),
    "close_no_promise_hardship": ("no_promise", "hardship"),
    "close_no_promise_dispute": ("no_promise", "dispute"),
    "close_no_promise_service_error": ("no_promise", "service_error"),
    "close_not_verified_failed": ("not_verified", "failed"),
    "close_not_verified_declined": ("not_verified", "declined"),
    "close_not_reached_callback": ("not_reached", "callback"),
    "close_not_reached_no_callback": ("not_reached", "no_callback"),
    "close_not_reached_wrong_number": ("not_reached", "wrong_number"),
    "close_not_reached_deceased": ("not_reached", "deceased"),
    "close_not_reached_unclear": ("not_reached", "unclear"),
}
BYE = "Thank you for your time. Goodbye."
FINISHES = {
    "finish_unclear": ("close_not_reached_unclear", BYE),
    "finish_wrong_number": ("close_not_reached_wrong_number", "Thank you for letting me know, and sorry for the trouble. Goodbye."),
    "finish_deceased": ("close_not_reached_deceased", "I am sorry for your loss. Thank you for your time. Goodbye."),
    "finish_callback": ("close_not_reached_callback", "Thank you, we will call back then. Goodbye."),
    "finish_no_callback": ("close_not_reached_no_callback", BYE),
    "finish_declined": ("close_not_verified_declined", "I understand. " + BYE),
    "finish_failed": ("close_not_verified_failed", "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. " + BYE),
    "finish_promise_recorded": ("close_promise", "Your promise is recorded. You will receive a text message confirming this promise. Thank you for your time, {{title}} {{last_name}}. Goodbye."),
    "finish_promise": ("close_promise", "Thank you for your time, {{title}} {{last_name}}. Goodbye."),
    "finish_paid": ("close_paid", "Thank you for letting me know. Payments can take one business day to appear. " + BYE),
    "finish_dispute": ("close_no_promise_dispute", "I understand. " + BYE),
    "finish_hardship": ("close_no_promise_hardship", "I understand. Thank you for your time, and take care. Goodbye."),
    "finish_refused": ("close_no_promise_refused", "I understand. " + BYE),
    "finish_service_error_single": ("close_no_promise_service_error", "I am sorry, I could not record your promise because of a technical problem. " + BYE),
    "finish_service_error": ("close_no_promise_service_error", BYE),
    "finish_tech_error": ("close_no_promise_service_error", "I am sorry, I cannot reach the account information right now because of a technical problem. " + BYE),
    "finish_transferred_restructuring": ("close_transferred_restructuring", "You are being connected now. Thank you, goodbye."),
    "finish_transferred_human": ("close_transferred_human", "You are being connected now. Thank you, goodbye."),
    "finish_transferred_support": ("close_transferred_support", "You are being connected now. Thank you, goodbye."),
}


def finish_node(name, close, text):
    return {"name": name, "node_type": "conversation", "task_message": "Say the closing line. No tool call is allowed in this turn.",
            "on_enter": {"type": "tts", "text": text}, "passthrough": True, "passthrough_default_transition": close,
            "tools": [], "transitions": [tr(close, "always", ALWAYS)]}


def close_node(name, outcome, reason):
    fields = {"outcome": {"type": "string", "enum": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"], "default": outcome}}
    if reason:
        fields["reason"] = {"type": "string", "default": reason}
    t = bank_tool("close_call", "/close_call", "End the call with its close code.", fields, [], retries=1)
    return {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "hangup",
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [t],
            "transitions": [tr("hangup", "always", ALWAYS)]}


# ---------------------------------------------------------------- prompts

SYSTEM = """You are Freya Bank's digital assistant, making an outbound call to {{title}} {{first_name}} {{last_name}}. Speak English. Keep every turn to one or two short sentences. Address the customer as {{title}} {{last_name}}.

Rules that hold everywhere:
- Until both security answers have passed, never say "collections", "debt", "payment", "overdue" or any product, to anyone, relatives included, and never say why you are calling.
- No improvising. Never offer a discount, a waiver, an instalment plan or any term the rules do not give you.
- If asked something you cannot answer from the facts you were given, say you do not have that information. Never invent figures, dates or reasons.
- "Is this a scam?": say they can verify this call by phoning Freya Bank's customer service number, then go on.
- "Am I talking to a robot / an AI?": say you are Freya Bank's digital assistant, then go on.
- When a rule says to call a tool, call the tool. Saying you did is not enough. Call one bank tool per message unless a rule says otherwise.
- Never say something is recorded, booked or done unless the tool result says ok true. If a tool fails, say so honestly.
- Tool results may contain "what_to_do_next": follow it.
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- Never say goodbye yourself; the closing line is said for you when the call ends.
- All dates work from the call's current date and time ({{now}}), never from any other clock."""

OPENING_LINE = "Hello, this is the digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"

WHO_VALUES = ["confirmed", "someone_else", "wrong_number", "deceased", "refuses", "question", "unclear"]
WHO_DESC = ("Who answered, judged from the person's latest message. "
            "confirmed: they said yes, that's me, speaking, or gave the customer's own name ({{first_name}} or {{last_name}}). "
            "someone_else: another person answered (a relative, a colleague, 'he is not here', 'she is out'). "
            "wrong_number: the number does not belong to that person, or they do not know the person. "
            "deceased: they say the customer has died. "
            "refuses: they say they do not want to talk. "
            "question: they ask who is calling, whether this is a robot or AI, or whether it is a scam. "
            "unclear: anything else, for example hello, go ahead, hm.")


def who_extraction(var):
    return [{"name": var, "type": "string", "enum_values": WHO_VALUES, "description": WHO_DESC, "min_confidence": 0.5}]


def who_routes(var, fallback):
    return [
        tr("security_dob", "The person confirmed they are the customer", cond_or(eq(var, "confirmed"))),
        tr("third_party", "Someone else answered", cond_or(eq(var, "someone_else"))),
        tr("finish_wrong_number", "Wrong number", cond_or(eq(var, "wrong_number"))),
        tr("finish_deceased", "The customer has died", cond_or(eq(var, "deceased"))),
    ] + fallback


RETRY_ENTER = """The person has not confirmed who they are. Do this in one or two short sentences, and say nothing about why you are calling:
- If they asked whether this is a robot or an AI, or who is calling, say you are Freya Bank's digital assistant.
- If they asked whether this is a scam, say they can verify this call by phoning Freya Bank's customer service number.
- If they said they do not want to talk, acknowledge it briefly.
Then ask exactly: "Am I speaking with {{title}} {{last_name}}?"
No tool call is allowed in this turn."""

THIRD_PARTY = """The person on the line is not {{title}} {{last_name}}. Say nothing beyond the opening: do not say why you are calling, never mention the account, a debt, a payment or a product, even if they ask or offer to pay. A relative may not answer security questions.
Ask when {{title}} {{last_name}} can be reached.

Callback window (only these times can be booked):
{{callback_window}}

- They name a day and a time inside the window: call schedule_callback with date YYYY-MM-DD and time HH:MM (24 hour). In that message say only "One moment, please."
- They name only a day inside the window, or only a time: ask for the missing part.
- Their day or time is outside the window: say when you can call back and ask once for another time. If the next answer is outside the window too, or they still give no time, call transition_to_finish_no_callback.
- The number does not belong to that person: call transition_to_finish_wrong_number.
- The customer has died: call transition_to_finish_deceased and say nothing else.
Book at most one callback."""

SECURITY_DOB_ENTER = "Thank you, {{title}} {{last_name}}. Before we go on, I need to ask two security questions. First, what is your date of birth?"
SECURITY_PHONE_ENTER = "Thank you. And what are the last four digits of the phone number we have on file for you?"

SECURITY_COMMON = """
If the customer does not want to answer, or asks what the call is about instead of answering: the first time, explain that these questions protect their account and ask again. If they decline a second time, or ask a second time what the call is about, call transition_to_finish_declined. Count refusals across both security questions.
If they say twice that they do not want to talk, call transition_to_finish_declined.
If they ask for a human: ask once whether you can help first. If they insist, call transfer_to_general.
Never say why you are calling and never mention any account detail during the security check."""

SECURITY_DOB = """You are checking the customer's identity. Ask for their date of birth.
When they give it, call verify_dob with the date as YYYY-MM-DD, whatever way they said it. A date given only in numbers is day, then month, then year: "05/03/1985" is 1985-03-05. A two-digit year such as 85 means 1985. If the date is incomplete, ask for the missing part before calling. In the message with the tool call say nothing else.
After a wrong answer, ask for the date of birth again.""" + SECURITY_COMMON

SECURITY_PHONE = """You are checking the customer's identity. The date of birth has passed. Ask for the last four digits of the phone number on file.
When you have exactly four digits (they may come in pieces; join them), call verify_phone with the four digits. In the message with the tool call say nothing else.
After a wrong answer, ask for the four digits again.""" + SECURITY_COMMON

DATE_RULES = """DATES
Today: {{today_text}}. Business days are Monday to Friday, except bank holidays ({{holiday_text}}).
Calendar. Look up every day the customer names here; do not work dates out yourself. "This <weekday>" and "next <weekday>" are labelled; "next Friday" is the Friday of the following calendar week.
{{date_table}}

A PTP date must be today or later, a business day, and not after the product's deadline.
- A weekend day or bank holiday that is not after the deadline: offer the business day the calendar shows for it.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still name none, propose the deadline."""

AMOUNT_RULES = """AMOUNTS
- Never ask "how much can you pay?". You propose every amount yourself. The first ask is always for the full past-due amount.
- The customer says the full amount is too much: offer the floor once, and say the rest stays overdue.
- An amount the customer proposes from the floor up to the full amount, both included, is accepted.
- Below the floor: say it cannot be recorded and offer the floor once. If they do not accept it, that is a flat refusal."""

ATTEMPT_RULES = """PERSUASION
- A date or an amount the customer proposes is never a refusal; check it with the rules above.
- A flat refusal is: "no" to paying today with no date and no amount, a refusal of an offer you made, refusing the deadline after asking for a later date, refusing the floor, or a non-answer. Each flat refusal uses one persuasion attempt of that product.
- After a flat refusal, if the product has an attempt left, make the next attempt offer from the product facts. If it has none left, stop: do not repeat an offer the customer already refused.
- Early stage: one attempt. Late stage: two attempts."""

SITUATIONS_SINGLE = """OTHER SITUATIONS
- "I already paid" (this past-due amount): no PTP. Call transition_to_finish_paid and say nothing else.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, no PTP. Call transition_to_finish_dispute and say nothing else.
- Illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_to_support. If they decline, call transition_to_finish_hardship. If they still name a date or an amount themselves, handle it as a PTP.
- A new payment plan or lower instalments: describe no plan and call transfer_to_restructuring.
- They ask for a human: ask once whether you can help first. If they insist, call transfer_to_general.
- They say twice that they do not want to talk: call transition_to_finish_refused.
- Attempts used up: call transition_to_finish_refused.
- Never call a transition_to_finish tool in the same message as another tool."""

NEGOTIATE_SINGLE = """The customer is verified. You have told them what is overdue and asked "Can you make this payment today?". Your job is to get a promise to pay (PTP) for this product, exactly by the rules below.

PRODUCT FACTS
{{product_plan}}

""" + DATE_RULES + """
- A date after the deadline: say the latest date you can record is the deadline and offer it.

""" + AMOUNT_RULES + """

""" + ATTEMPT_RULES + """

CONFIRMING AND RECORDING
- When you have an accepted amount and date, read back the product, the amount and the date and ask "Do you confirm?".
- Only after a clear yes, call create_promise with the amount and the date (YYYY-MM-DD). In that message say only "One moment, please."
- If the customer changes the date or the amount instead, check the new value with the rules and read back again.
- If create_promise fails, call it once more with the same values. Never say the promise is recorded unless the result says ok true.

""" + SITUATIONS_SINGLE

NEGOTIATE_MULTI = """The customer is verified. You have told them every late product and asked whether they can pay all of them today. Your job is to get a promise to pay (PTP) for each product, exactly by the rules below.

PRODUCT FACTS (in the order the bank gave them; each product has its own deadline, floor and attempts)
{{product_plan}}

ORDER OF WORK
1. If the customer can pay all products today, each PTP is the full amount today.
2. If not, take the products one at a time, in the order above. Do not ask about today again for each product. Every product starts at its first persuasion attempt. Count attempts separately per product.
3. If the customer names one date for everything and it is after the deadline of one product, that product is recorded on its own deadline; the others keep the date the customer named. Say so in the read-back.
4. "I already paid" (this past-due amount) or a dispute ("not mine", "never had it", closed or paid off in the past) about one product does not end the call: remember it for that product (no PTP) and go on with the next product. Tell a customer who already paid that payments can take one business day to appear.
5. When every product is settled, read back ALL agreed PTPs together (product, amount, date for each) and ask one "Do you confirm?". If the customer changes a date or amount, check it and read back again.
6. After the clear yes, call create_promise once for each agreed product, one product per message. In those messages say only "One moment, please." If create_promise fails for a product, call it once more with the same values; if it fails again, tell the customer it could not be recorded for that product.
7. Then call add_note once for every product that ends without a recorded PTP, one per message, with that product's product_id and one reason: refused (attempts used up or refused), hardship (hardship and declined support), dispute, paid, or service_error (create_promise failed twice). This also applies when no product gets a PTP.
8. Then finish (see FINISHING), in a message with no other tool call.

""" + DATE_RULES + """
- A date after the deadline of a product: say the latest date you can record for it is its deadline and offer it (when the customer named one date for everything, use rule 3 instead).

""" + AMOUNT_RULES + """
The floor and the full amount are per product.

""" + ATTEMPT_RULES + """
When a product's attempts are used up, that product ends with no PTP (reason refused) and you go on with the next product.

TRANSFERS (no notes at all on a transferred call, neither before nor after)
- A new payment plan or lower instalments: describe no plan and call transfer_to_restructuring. PTPs already recorded stay; agreed PTPs not yet recorded are not recorded.
- Illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_to_support. If they decline, the products without a PTP end with reason hardship. If they still name a date or an amount themselves, handle it as a PTP.
- They ask for a human: ask once whether you can help first. If they insist, call transfer_to_general.
- Never call add_note before or after a transfer.

FINISHING (only after all create_promise and add_note calls have returned)
- At least one create_promise returned ok true: call transition_to_finish_promise.
- No PTP recorded and every product was noted paid: call transition_to_finish_paid.
- Otherwise take the first product, in the order above, whose note is not paid, and use its reason: refused -> transition_to_finish_refused, hardship -> transition_to_finish_hardship, dispute -> transition_to_finish_dispute, service_error -> transition_to_finish_service_error.
- They say twice that they do not want to talk: the products without a PTP end with reason refused; add the notes, then finish.
- A recorded PTP cannot be changed or cancelled in this call; if they ask, say they can change it in the mobile app.
- Never call a transition_to_finish tool in the same message as another tool."""


# ---------------------------------------------------------------- workflow

def build():
    nodes = {}

    nodes["setup"] = {
        "name": "setup", "node_type": "code", "passthrough": True, "passthrough_default_transition": "opening",
        "on_enter": {"type": "silent"},
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code_with(SETUP_CODE)},
                             "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [tr("opening", "always", ALWAYS)],
    }

    nodes["opening"] = conv(
        "opening",
        "You asked whether you are speaking with {{title}} {{last_name}}. Wait for the answer. Say nothing about why you are calling. No tool call is allowed in this turn.",
        on_enter={"type": "tts", "text": OPENING_LINE},
        extraction=who_extraction("who_answered"),
        transitions=who_routes("who_answered", [tr("opening_retry", "Not yet confirmed: ask once more", ALWAYS)]),
        max_turns=4, cap_target="finish_unclear")

    nodes["opening_retry"] = conv(
        "opening_retry",
        RETRY_ENTER,
        on_enter={"type": "llm"},
        extraction=who_extraction("who_answered_2"),
        transitions=who_routes("who_answered_2", [
            tr("finish_declined", "They do not want to talk", cond_or(eq("who_answered_2", "refuses"))),
            tr("finish_unclear", "Still unclear after the second ask", ALWAYS)]),
        max_turns=3, cap_target="finish_unclear")

    nodes["third_party"] = conv(
        "third_party", THIRD_PARTY,
        tools=[CALLBACK],
        transitions=[
            tr("finish_callback", "The callback was booked", ok_success("schedule_callback")),
            tr("finish_no_callback", "Booking failed twice", cond_or(gt("schedule_callback_failure_count", 1))),
            tool_tr("finish_no_callback", "No time inside the callback window after asking once more for another time"),
            tool_tr("finish_wrong_number", "The number does not belong to the customer"),
            tool_tr("finish_deceased", "The person says the customer has died"),
        ],
        max_turns=10, cap_target="finish_no_callback")

    sec_tools_common = [transfer_tool("general", "the customer insisted on talking to a person after you asked once whether you can help")]
    nodes["security_dob"] = conv(
        "security_dob", SECURITY_DOB,
        on_enter={"type": "tts", "text": SECURITY_DOB_ENTER},
        tools=[verify_tool("verify_dob", "date_of_birth", "date of birth")] + sec_tools_common,
        transitions=[
            tr("security_phone", "Date of birth verified", cond_or(*is_true("verify_dob_response.data.verified"))),
            tr("finish_failed", "Three wrong answers", cond_or(eq("verify_dob_response.data.wrong_answers_left", "0"))),
            tr("finish_transferred_human", "Transferred to a person", ok_success("transfer_to_general")),
            tool_tr("finish_declined", "The customer declined the security questions a second time, or said twice they do not want to talk"),
        ],
        max_turns=12, cap_target="finish_declined")

    nodes["security_phone"] = conv(
        "security_phone", SECURITY_PHONE,
        on_enter={"type": "tts", "text": SECURITY_PHONE_ENTER},
        tools=[verify_tool("verify_phone", "phone_last4", "last four digits of the phone number")] + sec_tools_common,
        transitions=[
            tr("load_account", "Both answers verified", cond_or(*is_true("verify_phone_response.data.all_verified"), *is_true("verify_phone_response.data.verified"))),
            tr("finish_failed", "Three wrong answers", cond_or(eq("verify_phone_response.data.wrong_answers_left", "0"))),
            tr("finish_transferred_human", "Transferred to a person", ok_success("transfer_to_general")),
            tool_tr("finish_declined", "The customer declined the security questions a second time, or said twice they do not want to talk"),
        ],
        max_turns=12, cap_target="finish_declined")

    nodes["load_account"] = {
        "name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prep_account",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [GET_ACCOUNT],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [tr("prep_account", "always", ALWAYS)],
    }

    nodes["prep_account"] = {
        "name": "prep_account", "node_type": "code", "passthrough": True, "passthrough_default_transition": "negotiate_multi",
        "on_enter": {"type": "silent"},
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code_with(PREP_CODE)},
                             "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [
            tr("finish_tech_error", "Account could not be read", cond_or(eq("account_state", "error"))),
            tr("negotiate_single", "One product", cond_or(eq("product_count", "1"))),
            tr("negotiate_multi", "always", ALWAYS),
        ],
    }

    transfers = [
        transfer_tool("restructuring", "the customer asks for a new payment plan or lower instalments"),
        transfer_tool("general", "the customer insisted on talking to a person after you asked once whether you can help"),
        transfer_tool("support", "a customer in hardship (illness, death in the family, job loss) accepted your offer to connect them with the customer support team"),
    ]
    nodes["negotiate_single"] = conv(
        "negotiate_single", NEGOTIATE_SINGLE,
        on_enter={"type": "tts", "text": "{{overdue_text}}"},
        tools=[CREATE_SINGLE] + transfers,
        transitions=[
            tr("finish_promise_recorded", "The promise was recorded", ok_success("create_promise")),
            tr("finish_service_error_single", "create_promise failed twice", cond_or(gt("create_promise_failure_count", 1))),
        ] + transfer_routes() + [
            tool_tr("finish_paid", "The customer says they already paid this past-due amount"),
            tool_tr("finish_dispute", "The customer says the debt is not theirs, they never had the product, or it was closed or paid off in the past"),
            tool_tr("finish_hardship", "Customer in hardship declined the offer to connect with the support team and named no date or amount"),
            tool_tr("finish_refused", "Persuasion attempts used up, or the customer said twice they do not want to talk"),
        ],
        max_turns=40, cap_target="finish_refused")

    nodes["negotiate_multi"] = conv(
        "negotiate_multi", NEGOTIATE_MULTI,
        on_enter={"type": "tts", "text": "{{overdue_text}}"},
        tools=[CREATE_MULTI, ADD_NOTE] + transfers,
        transitions=transfer_routes() + [
            tool_tr("finish_promise", "All work is done and at least one promise was recorded"),
            tool_tr("finish_paid", "All work is done, no promise was recorded and every product was noted paid"),
            tool_tr("finish_refused", "All work is done, no promise recorded, and the first product whose note is not paid was noted refused"),
            tool_tr("finish_hardship", "All work is done, no promise recorded, and the first product whose note is not paid was noted hardship"),
            tool_tr("finish_dispute", "All work is done, no promise recorded, and the first product whose note is not paid was noted dispute"),
            tool_tr("finish_service_error", "All work is done, no promise recorded, and the first product whose note is not paid was noted service_error"),
        ],
        max_turns=60, cap_target="finish_refused")

    for name, (close, text) in FINISHES.items():
        nodes[name] = finish_node(name, close, text)
    for name, (outcome, reason) in CLOSES.items():
        nodes[name] = close_node(name, outcome, reason)
    nodes["hangup"] = {
        "name": "hangup", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {"type": "function", "function": {"name": "call_closed", "handler": "__function__:end_call",
                     "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
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
    out = sys.argv[1] if len(sys.argv) > 1 else "out/brief-b-raw.workflow.json"
    with open(out, "w") as f:
        json.dump(wf, f, indent=1)
    print("wrote", out, len(wf["nodes"]), "nodes")
