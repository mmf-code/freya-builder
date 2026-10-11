"""Generate the brief-a-raw and brief-b-raw workflows and contracts into out/.

    python3 scripts/gen_workflows.py
"""
import itertools
import json
from pathlib import Path

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
OUT = Path(__file__).resolve().parent.parent / "out"

# ------------------------------------------------------------------ runtime code (no double braces allowed)

DATE_CODE = r'''
import datetime, json, re
HOLIDAYS = set(['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'])
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

def is_bd(d):
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS

def add_bd(d, n):
    x = d
    k = 0
    while k < n:
        x = x + datetime.timedelta(days=1)
        if is_bd(x):
            k += 1
    return x

def next_bd(d):
    return add_bd(d, 1)

def spoken(d):
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'

def last_bd_of_week(d):
    monday = d - datetime.timedelta(days=d.weekday())
    best = None
    for i in range(7):
        x = monday + datetime.timedelta(days=i)
        if is_bd(x):
            best = x
    return best

def money(v):
    try:
        f = float(v)
    except Exception:
        return str(v)
    if abs(f - round(f)) < 0.005:
        return format(int(round(f)), ',')
    return format(f, ',.2f')

def num(v):
    try:
        return float(v)
    except Exception:
        return None

try:
    raw_now = str(vars.get('now') or '').strip()
    try:
        now_dt = datetime.datetime.fromisoformat(raw_now[:16])
    except Exception:
        now_dt = datetime.datetime.fromisoformat(raw_now[:10] + 'T09:00')
    today = now_dt.date()
    hhmm = now_dt.strftime('%H:%M')
    vars['today_iso'] = today.isoformat()

    lines = []
    lines.append('Today is ' + spoken(today) + ', time now ' + hhmm + '. Today is ' + ('a business day.' if is_bd(today) else 'NOT a business day.'))
    lines.append('Business days are Monday to Friday except the bank holidays 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01.')
    monday = today - datetime.timedelta(days=today.weekday())
    this_parts = []
    next_parts = []
    for i in range(7):
        a = monday + datetime.timedelta(days=i)
        b = a + datetime.timedelta(days=7)
        this_parts.append('this ' + WD[i] + ' = ' + a.isoformat())
        next_parts.append('next ' + WD[i] + ' = ' + b.isoformat())
    lines.append('"This <weekday>" means the day in the current week (Monday to Sunday): ' + '; '.join(this_parts) + '.')
    lines.append('"Next <weekday>" means the day in the following calendar week: ' + '; '.join(next_parts) + '.')
    cal = []
    for i in range(0, 29):
        d = today + datetime.timedelta(days=i)
        if d.isoformat() in HOLIDAYS:
            kind = 'bank holiday, not a business day'
        elif d.weekday() >= 5:
            kind = 'weekend, not a business day'
        else:
            kind = 'business day'
        tag = ' (today)' if i == 0 else ''
        cal.append(d.isoformat() + ' ' + WD[d.weekday()] + tag + ': ' + kind)
    lines.append('Calendar:\n' + '\n'.join(cal))
    lbd = last_bd_of_week(today)
    if lbd is None or lbd <= today:
        lbd = last_bd_of_week(today + datetime.timedelta(days=7))
    vars['first_offer_date'] = lbd.isoformat()
    vars['date_facts'] = '\n'.join(lines)

    nbd = next_bd(today)
    cb = []
    if hhmm < '19:00':
        start = 'after ' + hhmm if hhmm >= '10:00' else 'from 10:00'
        cb.append('today ' + spoken(today) + ', at a time ' + start + ' and no later than 19:00')
    cb.append(spoken(nbd) + ', at any time from 10:00 to 19:00 (both included)')
    vars['callback_facts'] = ('A callback can be booked ONLY at one of these times: ' + '; or '.join(cb) +
        '. The time now is ' + hhmm + ' on ' + spoken(today) + '. Any other day or time is outside the window.')
except Exception as e:
    vars['date_facts'] = 'Date facts could not be computed. Today is ' + str(vars.get('now'))
    vars['callback_facts'] = 'A callback can be booked today or on the next business day, from 10:00 to 19:00, later than now (' + str(vars.get('now')) + ').'
    vars['first_offer_date'] = ''

def parse_products():
    for k in ('products', 'load_account_response.data.products', 'get_account_response.data.products'):
        v = vars.get(k)
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                try:
                    v = json.loads(v.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
                except Exception:
                    v = None
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    items = dict()
    for k in list(vars.keys()):
        m = re.search(r'products\.(\d+)\.(\w+)$', str(k))
        if m:
            items.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    return [items[i] for i in sorted(items)]

try:
    prods = parse_products()[:3]
    vars['product_count'] = str(len(prods))
    if prods:
        today = datetime.date.fromisoformat(vars.get('today_iso'))
        first_offer = datetime.date.fromisoformat(vars.get('first_offer_date'))
        blocks = []
        for i, p in enumerate(prods, 1):
            t = str(p.get('type') or '')
            if t == 'credit_card':
                label = 'credit card ending ' + str(p.get('card_last4') or '')
                floor = num(p.get('minimum_payment'))
                floor_name = 'minimum payment'
            elif t == 'personal_loan':
                label = 'personal loan'
                floor = num(p.get('instalment_amount'))
                floor_name = 'instalment amount'
            else:
                label = 'car loan'
                floor = num(p.get('instalment_amount'))
                floor_name = 'instalment amount'
            past_due = num(p.get('past_due'))
            try:
                days = int(float(p.get('days_late')))
            except Exception:
                days = 0
            early = days <= 7
            deadline = add_bd(today, 12 if early else 7)
            attempts = 1 if early else 2
            allowed = []
            d = today
            while d <= deadline:
                if is_bd(d):
                    allowed.append(d.isoformat() + ' ' + WD[d.weekday()][:3])
                d = d + datetime.timedelta(days=1)
            pid = str(p.get('product_id') or '')
            vars['prod' + str(i) + '_id'] = pid
            vars['prod' + str(i) + '_label'] = label
            b = []
            b.append('PRODUCT ' + str(i) + ': ' + label + ' (product_id ' + pid + ').')
            b.append('- Past-due amount (full amount): ' + money(past_due) + '. Days late: ' + str(days) + '.')
            b.append('- Stage: ' + ('early (1-7 days late)' if early else 'late (8-45 days late)') + '. Persuasion attempts allowed: ' + str(attempts) + '.')
            b.append('- Floor (' + floor_name + '): ' + money(floor) + '. Accepted amounts: from ' + money(floor) + ' up to ' + money(past_due) + ', both included.')
            b.append('- PTP deadline: ' + spoken(deadline) + '. Latest date that can be recorded.')
            b.append('- Allowed PTP dates (business days from today up to the deadline): ' + ', '.join(allowed) + '.')
            b.append('- Persuasion attempt 1: propose the full amount ' + money(past_due) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much) on ' + spoken(first_offer) + '.')
            if not early:
                b.append('- Persuasion attempt 2: propose the floor ' + money(floor) + ' on the deadline ' + spoken(deadline) + '.')
            else:
                b.append('- There is no second persuasion attempt for this product.')
            b.append('- In the tool call send amount as a plain number (for example ' + str(past_due) + ') and date as YYYY-MM-DD.')
            blocks.append('\n'.join(b))
        vars['account_facts'] = '\n\n'.join(blocks)
    else:
        vars['account_facts'] = 'The product details could not be prepared. Read them from the get_account result.'
except Exception as e:
    vars['account_facts'] = 'The product details could not be prepared. Read them from the get_account result.'
'''


def code_node(name, target, transitions=None):
    tr = list(transitions or []) + [always(target)]
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": target,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{
            "type": "function",
            "function": {
                "name": "code_exec", "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": DATE_CODE},
                    "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": tr,
    }


GATE_CODE = "gate_ok = 1\n"


def gate_node(name, routes, default):
    node = code_node(name, default, routes)
    node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"] = GATE_CODE
    return node


# ------------------------------------------------------------------ helpers

def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def c(var, op, operand=None):
    d = {"variable": var, "operator": op}
    if operand is not None:
        d["operand"] = operand
    return d


def any_of(*checks):
    return {"logic": "or", "conditions": list(checks)}


def all_of(*checks):
    return {"logic": "and", "conditions": list(checks)}


def route(target, desc, *alternatives):
    return {"target_node": target, "description": desc, "condition": any_of(*alternatives)}


def tool_tr(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def field(typ, default=None, description=None, enum=None):
    f = {"type": typ}
    if default is not None:
        f["default"] = default
    if description:
        f["description"] = description
    if enum:
        f["enum"] = enum
    return f


CID = field("string", "{{customer_id}}")


def post_hook(ok_msg, fail_msg):
    return (
        "try:\n"
        "    if isinstance(result, dict):\n"
        "        result.pop('header', None)\n"
        "        d = result.get('data')\n"
        "        ok = isinstance(d, dict) and d.get('ok') is True\n"
        f"        msg = {ok_msg!r} if ok else {fail_msg!r}\n"
        "        if isinstance(d, dict):\n"
        "            d['what_to_do_next'] = msg\n"
        "        else:\n"
        "            result['what_to_do_next'] = msg\n"
        "except Exception:\n"
        "    pass\n"
    )


VERIFY_HOOK = (
    "try:\n"
    "    if isinstance(result, dict):\n"
    "        result.pop('header', None)\n"
    "        d = result.get('data')\n"
    "        if isinstance(d, dict):\n"
    "            left = d.get('wrong_answers_left')\n"
    "            if d.get('all_verified') is True:\n"
    "                msg = 'Both security answers passed. The customer is verified.'\n"
    "            elif d.get('hint') == 'day_month_swapped':\n"
    "                msg = 'Day and month look swapped. This is NOT a wrong answer. Ask the customer to say the month of birth as a word, then call verify_identity again.'\n"
    "            elif d.get('verified') is True:\n"
    "                msg = 'This answer passed. If it was the date of birth, now ask for the last four digits of the phone number on file.'\n"
    "            elif left == 0 or str(left) == '0':\n"
    "                msg = 'Three wrong answers. The security check has ended. Do not ask again and do not mention the account.'\n"
    "            elif d.get('ok') is False:\n"
    "                msg = 'The answer could not be read. It does not count as wrong. Ask the customer to say it again.'\n"
    "            else:\n"
    "                msg = 'This answer is wrong. Ask the same question once more.'\n"
    "            d['what_to_do_next'] = msg\n"
    "        else:\n"
    "            result['what_to_do_next'] = 'The check could not be done. Ask the customer to repeat the answer and call verify_identity again.'\n"
    "except Exception:\n"
    "    pass\n"
)


def api_tool(name, op, body, description="", required=None, max_retries=0, post=None, mapping=None):
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name, "handler": "__function__:api_call", "description": description,
            "parameters": {"type": "object", "properties": {
                "url": field("string", f"{BASE}/{op}"),
                "method": field("string", "POST"),
                "headers": {"type": "object", "properties": {"Content-Type": field("string", "application/json")}},
                "body": {"type": "object", "properties": {"customer_id": CID, **body},
                         "required": required or []},
            }},
        },
    }
    if post:
        t["post_process_code"] = post
    if mapping:
        t["response_mapping"] = mapping
    return t


def api_node(name, tool, transitions, mapping=None):
    n = {
        "name": name, "node_type": "api_request", "passthrough": True,
        "passthrough_default_transition": transitions[-1]["target_node"],
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [tool], "transitions": transitions,
    }
    if mapping:
        n["response_mapping"] = mapping
    return n


def say_node(name, text, target_or_routes):
    """Passthrough conversation step with a fixed line, then routes on."""
    if isinstance(target_or_routes, str):
        trs = [always(target_or_routes)]
    else:
        trs = target_or_routes
    return {
        "name": name, "node_type": "conversation", "passthrough": True,
        "passthrough_default_transition": trs[-1]["target_node"],
        "on_enter": {"type": "tts", "text": text},
        "task_message": "Say the fixed line. Do not call any tool in this turn.",
        "disable_inactivity_monitor": True,
        "transitions": trs,
    }


def conv(name, task, tools=None, transitions=None, on_enter=None, extraction=None, max_turns=None, cap_target=None):
    n = {"name": name, "node_type": "conversation", "task_message": task, "transitions": transitions or []}
    if tools:
        n["tools"] = tools
    n["on_enter"] = on_enter or {"type": "llm"}
    n["on_enter_first_entry_only"] = True
    if extraction:
        n["extraction_schema"] = extraction
    if max_turns:
        n["max_node_turns"] = max_turns
        n["max_turn_transition"] = cap_target
    return n


CLOSES = [
    ("promise", None), ("paid", None),
    ("transferred", "restructuring"), ("transferred", "human"), ("transferred", "support"),
    ("no_promise", "refused"), ("no_promise", "hardship"), ("no_promise", "dispute"), ("no_promise", "service_error"),
    ("not_verified", "failed"), ("not_verified", "declined"),
    ("not_reached", "callback"), ("not_reached", "no_callback"), ("not_reached", "wrong_number"),
    ("not_reached", "deceased"), ("not_reached", "unclear"),
]
OUTCOMES = ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"]


def close_key(outcome, reason):
    return f"close_{outcome}" + (f"_{reason}" if reason else "")


def close_node(outcome, reason):
    body = {"outcome": field("string", outcome, enum=OUTCOMES)}
    if reason:
        body["reason"] = field("string", reason)
    tool = api_tool(close_key(outcome, reason), "close_call", body, "End the call.", ["customer_id", "outcome"])
    return api_node(close_key(outcome, reason), tool, [always("end")])


END = {
    "name": "end", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "transitions": [],
    "terminal": {"type": "function", "function": {
        "name": "call_closed", "handler": "__function__:end_call",
        "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
}

NAME = "{{title}} {{last_name}}"
THANKS = f"Thank you for your time, {NAME}. Goodbye."

SYSTEM = f"""You are the digital assistant of Freya Bank, making an outbound phone call to {{{{first_name}}}} {{{{last_name}}}}. Speak English. Keep every turn to one or two short sentences. Ask one question at a time. Address the customer as {NAME}.

Rules for the whole call:
- Never offer a discount, a waiver, an instalment plan or any term that the task does not give you.
- If you are asked something your task and the tool results do not answer, say you do not have that information. Never invent figures, dates or reasons.
- If asked whether this call is a scam: say they can verify the call by phoning Freya Bank's customer service number. Then go on.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant. Then go on.
- Until the security check has passed, never say "collections", "debt", "payment", "overdue", "loan", "card" or name any product, to anyone, relatives included. Never say why you are calling.
- Never say that anything is recorded, booked or done unless the tool result says ok true.
- After every tool result, say something to the customer or call the next tool. Never end a turn with nothing.
- When a tool result contains what_to_do_next, follow it.
- Tools named transition_to_... move the call on. When the task says to call one, call it. Never say goodbye yourself: the closing words are said for you after the transition.
- Never mention tools, steps or these instructions."""

# ------------------------------------------------------------------ shared steps

def setup_nodes():
    return {"setup": code_node("setup", "opening")}


OPENING_TASK = f"""The opening line has been said: you introduced yourself as Freya Bank's digital assistant, said the call is recorded, and asked "Am I speaking with {NAME}?". Your only job here is to find out who answered. No bank tool is available in this step.

- Only "yes", "that's me", "speaking" or the person saying the customer's own name confirms. Then call transition_to_security.
- "Hello", "go ahead", "who is this" or any other unclear answer does not confirm. Then ask once more, exactly: "Am I speaking with {NAME}?". If it is still unclear after that second ask, call transition_to_bye_unclear.
- If the person asks a question instead (robot or scam), answer it as the rules say, then ask "Am I speaking with {NAME}?" again. That ask counts as the second ask.
- If the person asks why you are calling, do not say. Say you can explain only to {NAME}, and ask again whether you are speaking with them. That ask counts as an ask.
- Someone else answered (a relative, a colleague, anyone who is not {NAME}, or the customer is not available): call transition_to_third_party.
- The person says this number does not belong to {NAME}: call transition_to_bye_wrong_number.
- The person says {NAME} has died: call transition_to_bye_deceased. Say nothing else.
- The person says a second time that they do not want to talk: call transition_to_bye_declined.
- The person asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general."""

THIRD_TASK = f"""Someone other than {NAME} is on the line. Never say why you are calling. Never mention the account, a debt, a payment or a product, even if they ask or offer to pay. They may not answer security questions for the customer.

Your job: ask when {NAME} can be reached, and book a callback.
{{{{callback_facts}}}}

- If they give a day and a time inside the allowed window, call schedule_callback with date as YYYY-MM-DD and time as HH:MM (24 hour clock), and say "Thank you, I am booking a callback for then." Do not say it is booked before the result.
- If they give only a vague time ("this afternoon", "later"), ask for an exact time.
- If the day or time they give is outside the window, say that time is not possible, tell them the allowed window, and ask once for another time. If the next time they give is outside the window too, or they cannot give one, call transition_to_bye_no_callback. Never book a time outside the window.
- They say this number does not belong to {NAME}: call transition_to_bye_wrong_number.
- They say {NAME} has died: call transition_to_bye_deceased. Say nothing else.
- If it turns out {NAME} is now on the line and confirms who they are: call transition_to_security."""

SECURITY_TASK = f"""{NAME} has confirmed who they are. You must pass the security check before you say anything about why you are calling.

Ask two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. Call verify_identity once for each answer, and say a short sentence such as "Thank you, one moment." with each call.
- field date_of_birth: answer as YYYY-MM-DD, whatever way the customer said it. A date given only in numbers is read as day, then month, then year (for example 05/03/1985 is 1985-03-05).
- field phone_last4: exactly four digits.
- A wrong answer: ask the same question again.
- If the result says day and month look swapped: ask the customer to say the month of birth as a word. That is not a wrong answer.
- If the customer does not want to answer, or asks what the call is about instead of answering: explain once that these questions protect their account, and ask again. If they refuse a second time, or ask a second time instead of answering, call transition_to_bye_declined.
- If the customer says a second time that they do not want to talk: call transition_to_bye_declined.
- If the customer asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general."""

PROMISE_RULES = """GETTING A PROMISE TO PAY (PTP). A PTP is one amount and one date for one product.
Amounts:
- Ask for the full past-due amount first. Never ask "how much can you pay?". Propose every amount yourself.
- If the customer says the full amount is too much: offer the floor, once, and say that the rest stays overdue. If they refuse the floor, that is a flat refusal.
- An amount the customer proposes from the floor up to the full amount, both included, is accepted.
- An amount below the floor: say it cannot be recorded and offer the floor once. If they do not accept it, that is a flat refusal.
- If the customer names only a date, the amount is the full amount (or the floor if they already said the full amount is too much and accepted the floor). If they name only an amount, ask on which day they will pay it.
Dates:
- A PTP date must be one of the product's allowed PTP dates: today or later, a business day, not after the product's deadline. Use the calendar; never compute dates yourself.
- The customer names a weekend day or a bank holiday that is not after the deadline: offer the next business day.
- The customer names a date after the deadline: say the latest date you can record is the deadline, name it, and offer it. If they refuse the deadline, that is a flat refusal.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still name none, propose the deadline.
- "This <weekday>" and "next <weekday>": use the table in the date facts. "Next Friday" said on a Friday is the Friday of the following week.
Persuasion:
- A date or an amount the customer proposes is never a refusal; handle it with the rules above.
- A flat refusal or a non-answer uses one persuasion attempt. "No" to paying today, with no date and no amount, is a flat refusal.
- Make the persuasion attempts exactly as listed for the product (attempt 1, then attempt 2 only for a late-stage product). Each attempt is one short reason to pay plus the listed proposal.
- When the product's attempts are used up and the customer refuses again, stop. Never repeat an offer the customer already refused.
Hardship (illness, a death in the family, job loss): this comes before persuasion and before a request for a new plan. Say one short sentence of sympathy, make no persuasion attempt, and offer to connect the customer with the customer support team. If they accept, call transition_to_transfer_support. If the customer still names a date or an amount themselves, handle it as a PTP."""

OTHER_RULES = """OTHER REQUESTS:
- A request for a new payment plan or lower instalments: describe no plan, call transition_to_transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
- Asked whether the bank can change or cancel a recorded PTP: it cannot be changed in this call; they can change it in the mobile app."""

READBACK = """CONFIRMING AND RECORDING:
- Read back the product (in words), the amount and the date (weekday, day, month and year), and ask "Do you confirm?".
- Only after a clear yes, call the create_promise tool, and say "Thank you, I am recording it now." with the call. Never say it is recorded before the result arrives.
- If the customer changes the date or the amount at this point, check the new value with the rules above and read back again.
- If a create_promise result says it was not recorded, call the same tool once more with the same values. Never say it is recorded when the result says it was not."""


def create_tool(k):
    return api_tool(
        f"create_promise_p{k}", "create_promise",
        {"product_id": field("string", f"{{{{prod{k}_id}}}}", "product_id of product " + str(k) + " in the account facts."),
         "amount": field("number", "{{amount}}", f"Agreed amount for product {k}, a plain number such as 1250.5."),
         "date": field("string", "{{date}}", f"Agreed date for product {k}, as YYYY-MM-DD.")},
        f"Record the promise to pay for PRODUCT {k} of the account facts. CALL it only after the customer clearly said yes to your read-back. One call per product.",
        ["customer_id", "product_id", "amount", "date"])


def note_tool(k):
    return api_tool(
        f"add_note_p{k}", "add_note",
        {"product_id": field("string", f"{{{{prod{k}_id}}}}", "product_id of product " + str(k)),
         "reason": field("string", "{{reason}}", "Why product " + str(k) + " ended without a promise. One of: refused, hardship, dispute, paid, service_error.",
                         ["refused", "hardship", "dispute", "paid", "service_error"])},
        f"Record why PRODUCT {k} ended without a recorded promise. CALL it once for product {k} if it has no recorded promise.",
        ["customer_id", "product_id", "reason"])


def common_nodes(cap_unclear="bye_unclear"):
    verify = api_tool(
        "verify_identity", "verify_identity",
        {"field": field("string", "{{field}}", "Which question this answer is for: date_of_birth or phone_last4.", ["date_of_birth", "phone_last4"]),
         "answer": field("string", "{{answer}}", "date_of_birth as YYYY-MM-DD; phone_last4 as four digits.")},
        "Check one security answer. CALL it every time the customer answers a security question.",
        ["customer_id", "field", "answer"], post=VERIFY_HOOK)
    callback = api_tool(
        "schedule_callback", "schedule_callback",
        {"date": field("string", "{{date}}", "Callback date as YYYY-MM-DD, inside the allowed window."),
         "time": field("string", "{{time}}", "Callback time as HH:MM, 24 hour clock, inside the allowed window.")},
        "Book a callback for the customer. CALL it as soon as the person gives a day and time inside the allowed window.",
        ["customer_id", "date", "time"])

    get_acc = api_tool("get_account", "get_account", {}, "Get the late products.", ["customer_id"], max_retries=2)

    n = {}
    n["opening"] = conv(
        "opening", OPENING_TASK,
        transitions=[
            tool_tr("security", "The person confirmed they are the customer"),
            tool_tr("third_party", "Someone other than the customer answered"),
            tool_tr("bye_wrong_number", "The number does not belong to the customer"),
            tool_tr("bye_deceased", "The person says the customer has died"),
            tool_tr("bye_unclear", "Still unclear who answered after the second ask"),
            tool_tr("bye_declined", "The person said twice they do not want to talk"),
            tool_tr("transfer_general", "The person insisted on talking to a human"),
        ],
        on_enter={"type": "tts", "text": f"Hello, this is the digital assistant of Freya Bank, and this call is recorded. Am I speaking with {NAME}?"},
        max_turns=6, cap_target=cap_unclear)
    n["third_party"] = conv(
        "third_party", THIRD_TASK, tools=[callback],
        transitions=[
            route("bye_callback", "The callback was booked", c("schedule_callback_success_count", "greater_than", 0)),
            route("bye_callback_failed", "Booking failed twice", c("schedule_callback_failure_count", "greater_than", 1)),
            tool_tr("bye_no_callback", "No time inside the window after asking once more"),
            tool_tr("bye_wrong_number", "The number does not belong to the customer"),
            tool_tr("bye_deceased", "The person says the customer has died"),
            tool_tr("security", "The customer is now on the line and confirmed who they are"),
        ],
        on_enter={"type": "llm", "prompt": f"Do not say why you are calling. Ask, in one short sentence, when {NAME} can be reached, unless the person already said it; then handle what they said."},
        max_turns=8, cap_target="bye_no_callback")
    n["security"] = conv(
        "security", SECURITY_TASK, tools=[verify],
        transitions=[
            route("load_account", "Both security answers passed",
                  c("verify_identity_response.data.all_verified", "equals", "true"),
                  c("verify_identity_response.data.all_verified", "equals", "True")),
            route("bye_failed", "Three wrong answers",
                  c("verify_identity_response.data.wrong_answers_left", "equals", "0")),
            tool_tr("bye_declined", "The customer refused the security questions twice or does not want to talk"),
            tool_tr("transfer_general", "The customer insisted on talking to a human"),
        ],
        on_enter={"type": "tts", "text": "Thank you. Before I go on, I need to ask two security questions. What is your date of birth?"},
        max_turns=14, cap_target="bye_declined")
    n["load_account"] = api_node(
        "load_account", get_acc,
        [route("bye_account_error", "The account could not be loaded",
               all_of(c("load_account_failure_count", "greater_than", 0), c("load_account_success_count", "less_than", 1))),
         always("prep_account")],
        mapping=[{"path": "data.products", "variable": "products"}])

    # transfers: engine step, then a spoken line on success, then close
    for queue, reason in (("restructuring", "restructuring"), ("general", "human"), ("support", "support")):
        key = f"transfer_{queue}"
        tool = api_tool(key, "transfer_to_agent", {"queue": field("string", queue, enum=["restructuring", "general", "support"])},
                        "Hand the call to a person.", ["customer_id", "queue"], max_retries=1)
        n[key] = api_node(key, tool, [
            route(f"transferred_{queue}", "Transfer done", c(f"{key}_success_count", "greater_than", 0)),
            always(f"transfer_failed_{queue}")])
        n[f"transferred_{queue}"] = say_node(f"transferred_{queue}", f"I am connecting you now. Thank you for your time, {NAME}. Goodbye.", close_key("transferred", reason))
        n[f"transfer_failed_{queue}"] = say_node(f"transfer_failed_{queue}", f"I am sorry, I could not connect you right now. You can reach a colleague on Freya Bank's customer service number. Thank you for your time, {NAME}. Goodbye.", close_key("transferred", reason))

    byes = {
        "bye_callback": ("Thank you, we will call back then. Goodbye.", ("not_reached", "callback")),
        "bye_callback_failed": ("I am sorry, I could not book the callback. Thank you for your time. Goodbye.", ("not_reached", "no_callback")),
        "bye_no_callback": ("Thank you for your time. Goodbye.", ("not_reached", "no_callback")),
        "bye_wrong_number": ("Thank you, and sorry for the trouble. Goodbye.", ("not_reached", "wrong_number")),
        "bye_deceased": ("I am sorry for your loss. Thank you for your time. Goodbye.", ("not_reached", "deceased")),
        "bye_unclear": ("Thank you for your time. Goodbye.", ("not_reached", "unclear")),
        "bye_declined": ("I understand. Without the security questions I cannot go on. Thank you for your time. Goodbye.", ("not_verified", "declined")),
        "bye_failed": ("I am sorry, I could not verify your identity, so I cannot go on. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye.", ("not_verified", "failed")),
        "bye_account_error": (f"I am sorry, I cannot reach your account details right now. Thank you for your time, {NAME}. Goodbye.", ("no_promise", "service_error")),
    }
    for key, (text, (o, r)) in byes.items():
        n[key] = say_node(key, text, close_key(o, r))
    for o, r in CLOSES:
        n[close_key(o, r)] = close_node(o, r)
    n["end"] = END
    return n


NEGOTIATE_ENTER_A = """Say that you are calling from the Freya Bank collections team about a late payment. Then, in one sentence, name the product in words, its past-due amount and how many days late it is, from the account facts. Then ask exactly: "Can you make this payment today?" Do not call a tool in this turn."""


def negotiate_task(multi):
    head = f"""{NAME} passed the security check. You may now talk about the late payment.

DATE FACTS:
{{{{date_facts}}}}

ACCOUNT FACTS (from get_account):
{{{{account_facts}}}}

"""
    if not multi:
        flow = """FLOW: You stated what is overdue and asked "Can you make this payment today?". If the customer says yes, the PTP is the full amount today. Then work towards one PTP with the rules below.

"""
        ends = """ENDING WITHOUT A PROMISE (call the tool; say at most one short sentence, never goodbye):
- The customer says they already paid this past-due amount: call transition_to_bye_paid. Take no PTP.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no PTP, call transition_to_bye_dispute.
- Hardship and the customer declines the support team: call transition_to_bye_hardship.
- The persuasion attempts are used up and the customer refused again: call transition_to_bye_refused.
- The customer says a second time that they do not want to talk: call transition_to_bye_refused.

"""
    else:
        flow = """FLOW FOR SEVERAL PRODUCTS:
- You stated every late product, one sentence each, and asked whether the customer can pay all of them today. If yes, each PTP is that product's full amount today.
- If not, take the products one at a time, in the order of the account facts (PRODUCT 1 first). Do not ask about paying today again for each product. Each product starts at its own persuasion attempt 1; attempts are counted separately per product, and each product has its own deadline and floor.
- If the customer names one date for everything and that date is after the deadline of a product, that product gets its own deadline and you say so in the read-back; the other products keep the customer's date.
- "I already paid" about one product: say that payments can take one business day to appear, take no PTP for it, and go on with the next product.
- "Not mine", "never had it", or closed or paid off in the past, about one product: do not argue, take no PTP for it, go on with the next product.
- Hardship and the customer declines the support team: make no persuasion attempt for any remaining product; those products end without a PTP unless the customer names a date or an amount themselves.
- A product whose attempts are used up and that the customer refused again ends without a PTP; go on with the next product.
- If the customer says a second time that they do not want to talk, every remaining product ends without a PTP.

WHEN EVERY PRODUCT IS SETTLED:
- If at least one product has an agreed PTP: read back all agreed PTPs together (product in words, amount, date) and ask one "Do you confirm?". After a clear yes, call create_promise_pN for each product with an agreed PTP, in one message, saying "Thank you, I am recording them now." Never call it for a product without an agreed PTP.
- If no product has an agreed PTP: call transition_to_wrap_up. Say at most one short sentence, never goodbye.

"""
        ends = ""
    return head + flow + PROMISE_RULES + "\n\n" + READBACK + "\n\n" + OTHER_RULES + "\n\n" + ends + \
        "No other tool is available. Never invent a product_id, an amount or a date: take them from the facts above."


def negotiate_a():
    t = negotiate_task(False)
    return conv(
        "negotiate", t, tools=[create_tool(1)],
        transitions=[
            route("after_promise", "The promise was recorded", c("create_promise_p1_success_count", "greater_than", 0)),
            route("bye_service_error", "Recording failed twice", c("create_promise_p1_failure_count", "greater_than", 1)),
            tool_tr("transfer_support", "Hardship: the customer accepted the support team"),
            tool_tr("transfer_restructuring", "The customer asked for a new payment plan or lower instalments"),
            tool_tr("transfer_general", "The customer insisted on a human"),
            tool_tr("bye_paid", "The customer already paid the past-due amount"),
            tool_tr("bye_dispute", "The customer disputes the debt or the product"),
            tool_tr("bye_hardship", "Hardship: the customer declined the support team"),
            tool_tr("bye_refused", "Attempts used up, or the customer said twice they do not want to talk"),
        ],
        on_enter={"type": "llm", "prompt": NEGOTIATE_ENTER_A},
        max_turns=40, cap_target="bye_refused")


AFTER_TASK = f"""The customer's promise to pay is recorded and you told them they will receive a text message. Ask whether there is anything else you can help with, and handle the answer. No bank tool is available in this step.
- Nothing else, or a thank you: call transition_to_bye_promise.
- The customer wants to change or cancel the promise: say it cannot be changed in this call and that they can change it in the mobile app. Then ask whether there is anything else.
- A new payment plan or lower instalments: describe no plan, call transition_to_transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
- Illness, a death in the family or job loss: one short sentence of sympathy, then offer the customer support team. If they accept, call transition_to_transfer_support; if not, call transition_to_bye_promise."""


def build_a():
    n = {}
    n.update(setup_nodes())
    n.update(common_nodes())
    n["prep_account"] = code_node("prep_account", "negotiate")
    n["negotiate"] = negotiate_a()
    n["after_promise"] = conv(
        "after_promise", AFTER_TASK,
        transitions=[
            tool_tr("bye_promise", "Nothing else"),
            tool_tr("transfer_restructuring", "The customer asked for a new payment plan or lower instalments"),
            tool_tr("transfer_general", "The customer insisted on a human"),
            tool_tr("transfer_support", "Hardship: the customer accepted the support team"),
        ],
        on_enter={"type": "tts", "text": "Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
        max_turns=8, cap_target="bye_promise")
    byes = {
        "bye_promise": (THANKS, ("promise", None)),
        "bye_paid": (f"Thank you for letting me know. Payments can take one business day to appear. Thank you for your time, {NAME}. Goodbye.", ("paid", None)),
        "bye_dispute": (f"I understand. Thank you for your time, {NAME}. Goodbye.", ("no_promise", "dispute")),
        "bye_hardship": (f"I understand. Thank you for your time, {NAME}. Goodbye.", ("no_promise", "hardship")),
        "bye_refused": (f"I understand. Thank you for your time, {NAME}. Goodbye.", ("no_promise", "refused")),
        "bye_service_error": (f"I am sorry, I could not record your promise. Thank you for your time, {NAME}. Goodbye.", ("no_promise", "service_error")),
    }
    for key, (text, (o, r)) in byes.items():
        n[key] = say_node(key, text, close_key(o, r))
    return finish(n)


# ------------------------------------------------------------------ brief B

NEGOTIATE_ENTER_B = """Say that you are calling from the Freya Bank collections team about late payments. Then state every late product from the account facts, in the given order, one sentence per product: the product in words, its past-due amount and how many days late it is. Then ask whether the customer can make all of these payments today. Do not call a tool in this turn."""


def create_done(n_products):
    """DNF: every product is not called, succeeded or failed twice; at least one was called."""
    groups = []
    for combo in itertools.product(("none", "ok", "fail"), repeat=n_products):
        if all(x == "none" for x in combo):
            continue
        checks = []
        for k, x in enumerate(combo, 1):
            if x == "none":
                checks.append(c(f"create_promise_p{k}_args.amount", "is_not_set"))
            elif x == "ok":
                checks.append(c(f"create_promise_p{k}_success_count", "greater_than", 0))
            else:
                checks.append(c(f"create_promise_p{k}_failure_count", "greater_than", 1))
        groups.append(all_of(*checks))
    return groups


def notes_done(n_products):
    groups = []
    for combo in itertools.product(("promise", "note", "notefail"), repeat=n_products):
        checks = []
        for k, x in enumerate(combo, 1):
            if x == "promise":
                checks.append(c(f"create_promise_p{k}_success_count", "greater_than", 0))
            elif x == "note":
                checks.append(c(f"add_note_p{k}_success_count", "greater_than", 0))
            else:
                checks.append(c(f"add_note_p{k}_failure_count", "greater_than", 1))
        groups.append(all_of(*checks))
    return groups


def close_routes(n_products):
    out = [route(close_key("promise", None), "At least one promise recorded",
                 *[c(f"create_promise_p{k}_success_count", "greater_than", 0) for k in range(1, n_products + 1)])]
    out.append(route(close_key("paid", None), "Every product noted paid",
                     all_of(*[c(f"add_note_p{k}_args.reason", "equals", "paid") for k in range(1, n_products + 1)])))
    for reason in ("refused", "hardship", "dispute", "service_error"):
        alts = []
        for k in range(1, n_products + 1):
            checks = [c(f"add_note_p{j}_args.reason", "equals", "paid") for j in range(1, k)]
            checks.append(c(f"add_note_p{k}_args.reason", "equals", reason))
            alts.append(all_of(*checks) if len(checks) > 1 else checks[0])
        out.append(route(close_key("no_promise", reason), f"First product not noted paid has reason {reason}", *alts))
    out.append(always(close_key("no_promise", "refused")))
    return out


AFTER_B_ENTER = """Tell the customer the result of the recording, from the create_promise results: for each product whose result was ok true, say its promise is recorded; for each product whose recording failed twice, say you could not record its promise. If at least one promise is recorded, say: "You will receive a text message confirming this promise." Then ask whether there is anything else you can help with. Do not call a tool in this turn."""

AFTER_B_TASK = f"""The recording of the agreed promises is done; you told the customer which were recorded and which, if any, could not be recorded. Ask whether there is anything else you can help with, and handle the answer. No bank tool is available in this step.
- Nothing else, or a thank you: call transition_to_wrap_up.
- The customer wants to change or cancel a recorded promise: say it cannot be changed in this call and that they can change it in the mobile app. Then ask whether there is anything else.
- A new payment plan or lower instalments: describe no plan, call transition_to_transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
- Illness, a death in the family or job loss: one short sentence of sympathy, then offer the customer support team. If they accept, call transition_to_transfer_support; if not, call transition_to_wrap_up."""

NOTES_TASK = """The conversation about the products is over. For every product of the account facts that has NO recorded promise (no create_promise result with ok true for it), call its add_note tool once, with exactly one reason:
- paid: the customer said they already paid that product's past-due amount.
- dispute: the customer said it is not theirs, they never had it, or it was closed or paid off in the past.
- hardship: illness, a death in the family or job loss, and the customer declined the support team.
- service_error: an agreed promise for that product could not be recorded (create_promise failed twice).
- refused: any other product without a promise (refused, attempts used up, did not want to talk).
Never call add_note for a product with a recorded promise. Call all needed add_note tools in one message, and say "Thank you, one moment." with them. If a result says a note was not recorded, call that tool once more.

ACCOUNT FACTS:
{{account_facts}}"""


def build_b():
    n = {}
    n.update(setup_nodes())
    n.update(common_nodes())
    n["prep_account"] = code_node("prep_account", "negotiate_3", [
        route("negotiate_1", "One product", c("product_count", "equals", "1")),
        route("negotiate_2", "Two products", c("product_count", "equals", "2")),
    ])
    # prep_account: the always route is negotiate_3 (three products, or unknown count)
    for N in (1, 2, 3):
        ks = range(1, N + 1)
        wrap = f"wrap_up_{N}"
        n[f"negotiate_{N}"] = conv(
            f"negotiate_{N}", negotiate_task(True).replace("create_promise_pN", "create_promise_p<number>"),
            tools=[create_tool(k) for k in ks],
            transitions=[
                route(f"after_record_{N}", "Every promise call finished", *create_done(N)),
                tool_tr(f"after_record_{N}", "Every create_promise result for the agreed products is in"),
                tool_tr("transfer_support", "Hardship: the customer accepted the support team"),
                tool_tr("transfer_restructuring", "The customer asked for a new payment plan or lower instalments"),
                tool_tr("transfer_general", "The customer insisted on a human"),
                {**tool_tr(wrap, "Every product is settled and none has an agreed promise"), "target_node": wrap},
            ],
            on_enter={"type": "llm", "prompt": NEGOTIATE_ENTER_B},
            max_turns=50, cap_target=wrap)
        # rename the wrap-up transition tool to a stable name in the prompt
        n[f"negotiate_{N}"]["task_message"] = n[f"negotiate_{N}"]["task_message"].replace("transition_to_wrap_up", f"transition_to_{wrap}")
        n[f"negotiate_{N}"]["task_message"] += (f"\n\nAfter the create_promise results for all agreed products are in (each ok true, or failed twice), "
            f"if the call has not moved on by itself, call transition_to_after_record_{N}. Never call it in the same message as create_promise.")
        n[f"after_record_{N}"] = conv(
            f"after_record_{N}", AFTER_B_TASK.replace("transition_to_wrap_up", f"transition_to_{wrap}"),
            transitions=[
                tool_tr(wrap, "Nothing else"),
                tool_tr("transfer_restructuring", "The customer asked for a new payment plan or lower instalments"),
                tool_tr("transfer_general", "The customer insisted on a human"),
                tool_tr("transfer_support", "Hardship: the customer accepted the support team"),
            ],
            on_enter={"type": "llm", "prompt": AFTER_B_ENTER},
            max_turns=8, cap_target=wrap)
        n[wrap] = gate_node(wrap, [
            route(f"bye_final_{N}", "Every product has a recorded promise",
                  all_of(*[c(f"create_promise_p{k}_success_count", "greater_than", 0) for k in ks]) if N > 1
                  else c("create_promise_p1_success_count", "greater_than", 0)),
        ], f"write_notes_{N}")
        n[f"write_notes_{N}"] = conv(
            f"write_notes_{N}", NOTES_TASK, tools=[note_tool(k) for k in ks],
            transitions=[route(f"bye_final_{N}", "Every product has a promise or a note", *notes_done(N))],
            on_enter={"type": "llm", "prompt": "Say \"Thank you, one moment.\" and, in the same message, call add_note for every product without a recorded promise, as the task says."},
            max_turns=3, cap_target=f"bye_final_{N}")
        n[f"bye_final_{N}"] = say_node(f"bye_final_{N}", THANKS, close_routes(N))
    return finish(n)


def finish(nodes):
    return {
        "initial_node": "setup",
        "system_prompt": SYSTEM,
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr",
                           "now": "2026-10-14T11:00"},
    }


def contract(extra):
    return {
        "terminal_tools": [{"tool": "close_call", "evidence": [
            {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
            {"source": "briefs/brief-a-raw.md", "quote": "Every call ends with exactly one `close_call`, as the last tool call, with an outcome and, where the list gives one, a reason."},
        ] + extra}],
        "every_call_ends_with_terminal": True,
    }


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    (OUT / "brief-a-raw.workflow.json").write_text(json.dumps(build_a(), indent=1))
    (OUT / "brief-b-raw.workflow.json").write_text(json.dumps(build_b(), indent=1))
    (OUT / "brief-a-raw.contract.json").write_text(json.dumps(contract([]), indent=1))
    (OUT / "brief-b-raw.contract.json").write_text(json.dumps(contract([
        {"source": "briefs/brief-b-raw.md", "quote": "The close code list still applies."}]), indent=1))
    print("written")
