"""Generate the brief A and brief B workflows. Usage: python3 out/gen.py"""
import json
from pathlib import Path

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
OUT = Path(__file__).parent

HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]

SETUP_CODE = r'''
import datetime
try:
    HOL = set(['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'])
    raw = str(vars.get('now') or '').strip()
    now = datetime.datetime.fromisoformat(raw[:16])
    today = now.date()
    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL
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
    def last_bd_of_week(d):
        sunday = d + datetime.timedelta(days=6 - d.weekday())
        x = sunday
        monday = sunday - datetime.timedelta(days=6)
        while not isbd(x) and x > monday:
            x = x - datetime.timedelta(days=1)
        return x
    def fmt(d):
        return d.strftime('%A %d %B %Y') + ' (' + d.isoformat() + ')'
    lw = last_bd_of_week(today)
    if lw <= today:
        lw = last_bd_of_week(today + datetime.timedelta(days=7))
    early_deadline = nth_bd(12)
    late_deadline = nth_bd(7)
    vars['today_iso'] = today.isoformat()
    vars['now_time'] = now.strftime('%H:%M')
    vars['early_deadline'] = early_deadline.isoformat()
    vars['late_deadline'] = late_deadline.isoformat()
    vars['first_attempt_date'] = lw.isoformat()
    cb_next = next_bd(today)
    vars['callback_next_bd'] = cb_next.isoformat()
    lines = []
    lines.append('Now: ' + today.strftime('%A %d %B %Y') + ', ' + now.strftime('%H:%M') + '. Today is ' + today.isoformat() + ('' if isbd(today) else ' (not a business day)') + '.')
    lines.append('Early stage (1-7 days late) PTP deadline: ' + fmt(early_deadline) + '.')
    lines.append('Late stage (8-45 days late) PTP deadline: ' + fmt(late_deadline) + '.')
    lines.append('First persuasion attempt date (last business day of this week, or of next week if today is that day or later): ' + fmt(lw) + '. If this is after a product deadline, use that deadline instead.')
    lines.append('Callback window: today ' + today.isoformat() + ' or the next business day ' + cb_next.isoformat() + ', from 10:00 to 19:00 both included, and later than now (' + now.strftime('%H:%M') + ' today).')
    monday = today - datetime.timedelta(days=today.weekday())
    lines.append('Calendar (this week starts ' + monday.isoformat() + '; "this <weekday>" = this week, "next <weekday>" = the week after):')
    d = monday
    end = max(early_deadline, lw) + datetime.timedelta(days=7)
    while d <= end:
        tag = 'business day'
        if d.isoformat() in HOL:
            tag = 'BANK HOLIDAY, not a business day'
        elif d.weekday() > 4:
            tag = 'weekend, not a business day'
        wk = 'this week' if (d - monday).days < 7 else ('next week' if (d - monday).days < 14 else 'later')
        mark = ''
        if d < today:
            mark = ' [past]'
        elif d == today:
            mark = ' [today]'
        lines.append('- ' + d.isoformat() + ' ' + d.strftime('%A') + ', ' + wk + ': ' + tag + mark)
        d = d + datetime.timedelta(days=1)
    vars['date_facts'] = chr(10).join(lines)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Date facts unavailable: ' + str(e)
    vars['setup_state'] = 'error'
    vars['early_deadline'] = ''
    vars['late_deadline'] = ''
    vars['first_attempt_date'] = ''
'''

ACCOUNT_CODE = r'''
import json, datetime
try:
    prods = vars.get('products')
    if isinstance(prods, str):
        try:
            prods = json.loads(prods)
        except Exception:
            prods = None
    if not isinstance(prods, list):
        d = vars.get('get_account_response.data.products')
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except Exception:
                d = None
        prods = d if isinstance(d, list) else None
    if not isinstance(prods, list):
        prods = []
        i = 0
        while i < 3:
            k = 'products.' + str(i) + '.'
            k2 = 'get_account_response.data.products.' + str(i) + '.'
            p = {}
            for f in ['product_id', 'type', 'card_last4', 'past_due', 'days_late', 'minimum_payment', 'instalment_amount']:
                v = vars.get(k + f)
                if v is None:
                    v = vars.get(k2 + f)
                if v is not None:
                    p[f] = v
            if p.get('product_id'):
                prods.append(p)
            i += 1
    early = vars.get('early_deadline') or ''
    late = vars.get('late_deadline') or ''
    first = vars.get('first_attempt_date') or ''
    def money(x):
        try:
            return '%.2f' % float(x)
        except Exception:
            return str(x)
    lines = []
    n = 0
    for p in prods:
        if not isinstance(p, dict):
            continue
        n += 1
        t = str(p.get('type') or '')
        if t == 'credit_card':
            words = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        elif t == 'car_loan':
            words = 'car loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        else:
            words = 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        try:
            dl = int(float(p.get('days_late')))
        except Exception:
            dl = 0
        if dl <= 7:
            stage = 'early'
            deadline = early
            attempts = 1
        else:
            stage = 'late'
            deadline = late
            attempts = 2
        fa = first
        if fa and deadline and fa > deadline:
            fa = deadline
        s = ('Product ' + str(n) + ': product_id ' + str(p.get('product_id')) + ', say it as "' + words + '". Past-due amount ' + money(p.get('past_due')) +
             ', ' + str(dl) + ' days late. Stage ' + stage + '. Floor (' + floor_name + ') ' + money(floor) +
             '. PTP deadline ' + deadline + ' (latest date that can be recorded). Persuasion attempts allowed: ' + str(attempts) +
             '. Attempt 1: propose ' + ('the full amount ' + money(p.get('past_due')) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much)') + ' on ' + fa + '.')
        if attempts == 2:
            s += ' Attempt 2: propose the floor ' + money(floor) + ' on the deadline ' + deadline + '.'
        else:
            s += ' No second attempt.'
        lines.append(s)
    vars['product_count'] = str(n)
    if n == 0:
        vars['account_state'] = 'empty'
        vars['account_facts'] = 'No account data could be loaded.'
    else:
        vars['account_state'] = 'ok'
        vars['account_facts'] = chr(10).join(lines)
except Exception as e:
    vars['account_state'] = 'error'
    vars['product_count'] = '0'
    vars['account_facts'] = 'No account data could be loaded.'
'''

VERIFY_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            left = d.get('wrong_answers_left')
            if d.get('all_verified') is True:
                d['what_to_do_next'] = 'Both security answers passed. Thank the customer briefly.'
            elif d.get('hint') == 'day_month_swapped':
                d['what_to_do_next'] = 'Day and month were swapped. This is NOT a wrong answer. Ask the customer to say their date of birth again with the month as a word.'
            elif d.get('ok') is False:
                d['what_to_do_next'] = 'The answer could not be read. This is NOT a wrong answer. Ask the same question again.'
            elif d.get('verified') is True:
                d['what_to_do_next'] = 'This answer passed. Now ask the next security question: the last four digits of the phone number on file.'
            elif left is not None and int(left) <= 0:
                d['what_to_do_next'] = 'Three wrong answers: the security check has failed. Do NOT state the debt or anything about the account. Tell the customer to use the Freya Bank mobile app or visit a branch, then call transition_to_close_call.'
            else:
                d['what_to_do_next'] = 'Wrong answer. Do not say why the bank is calling. Ask the same question again.'
    else:
        result = {'data': {'what_to_do_next': 'The check service failed. Ask the same question again.'}}
except Exception:
    pass
'''

PROMISE_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') is True:
            d['what_to_do_next'] = 'The PTP was saved. Tell the customer it is recorded, then say: "You will receive a text message confirming this promise."'
        else:
            if not isinstance(d, dict):
                d = {}
                result['data'] = d
            d['what_to_do_next'] = 'FAILED: the PTP was NOT saved. Never say it is recorded. If this is the first failure for this product, call create_promise once more with the same values. If it already failed once before, tell the customer you could not record the PTP.'
except Exception:
    pass
'''

GENERIC_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') is True:
            d['what_to_do_next'] = 'Done. Tell the customer in one sentence, then continue as your instructions say.'
        else:
            if not isinstance(d, dict):
                d = {}
                result['data'] = d
            d['what_to_do_next'] = 'This action FAILED and was not carried out. Tell the customer so, honestly.'
except Exception:
    pass
'''


def body_tool(name, desc, fields, required, post=None, mapping=None, retries=0):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    for f, spec in fields.items():
        leaf = dict(spec)
        leaf["default"] = "{{" + name + "_" + f + "}}"
        props[f] = leaf
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
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
    if post:
        t["post_process_code"] = post
    if mapping:
        t["response_mapping"] = mapping
    return t


def verify_tool():
    return body_tool(
        "verify_identity",
        "CALL it every time the customer answers a security question, once per answer. field is date_of_birth or phone_last4. "
        "answer: for date_of_birth the date as YYYY-MM-DD (a date said only in numbers is day, then month, then year); for phone_last4 four digits.",
        {
            "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "description": "One of: date_of_birth, phone_last4."},
            "answer": {"type": "string", "description": "date_of_birth as YYYY-MM-DD, phone_last4 as four digits."},
        },
        ["field", "answer"], post=VERIFY_POST)


def transfer_tool(queues):
    return body_tool(
        "transfer_to_agent",
        "CALL it to hand the call to a person. queue: restructuring (new payment plan or lower instalments), support (hardship, customer accepted the support team), general (customer insists on a human after you asked once if you can help). After the result, call transition_to_close_call.",
        {"queue": {"type": "string", "enum": queues, "description": "One of: " + ", ".join(queues) + "."}},
        ["queue"], post=GENERIC_POST)


def callback_tool():
    return body_tool(
        "schedule_callback",
        "CALL it to book a callback once the person gave a day and time inside the allowed window. date YYYY-MM-DD, time HH:MM (24 hour).",
        {
            "date": {"type": "string", "description": "Callback date, YYYY-MM-DD."},
            "time": {"type": "string", "description": "Callback time, HH:MM, 24 hour."},
        },
        ["date", "time"], post=GENERIC_POST)


def promise_tool():
    return body_tool(
        "create_promise",
        "CALL it only after the customer said a clear yes to the read-back. One call per product, one call per message. product_id copied exactly from the account facts, amount a number, date YYYY-MM-DD.",
        {
            "product_id": {"type": "string", "description": "product_id copied exactly from the account facts."},
            "amount": {"type": "number", "description": "Agreed amount."},
            "date": {"type": "string", "description": "Agreed date, YYYY-MM-DD."},
        },
        ["product_id", "amount", "date"], post=PROMISE_POST)


def note_tool():
    return body_tool(
        "add_note",
        "CALL it once for every product that ends without a recorded PTP, with that product's product_id and one reason: refused, hardship, dispute, paid or service_error. Never call it when the call is transferred.",
        {
            "product_id": {"type": "string", "description": "product_id copied exactly from the account facts."},
            "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "description": "One of: refused, hardship, dispute, paid, service_error."},
            "text": {"type": "string", "description": "One short sentence on what happened."},
        },
        ["product_id", "reason"], post=GENERIC_POST)


CLOSE_PRE = "try:\n    b = config.get('body')\n    if isinstance(b, dict) and b.get('outcome') in ('promise', 'paid'):\n        b.pop('reason', None)\nexcept Exception:\n    pass\n"


def close_tool():
    t = body_tool(
        "close_call",
        "CALL it exactly once, after your thank-you and goodbye, to end the call with the outcome and reason that match what happened.",
        {
            "outcome": {"type": "string", "enum": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"],
                        "description": "One of: promise, paid, transferred, no_promise, not_verified, not_reached."},
            "reason": {"type": "string", "enum": ["restructuring", "human", "support", "refused", "hardship", "dispute", "service_error",
                                                   "failed", "declined", "callback", "no_callback", "wrong_number", "deceased", "unclear"],
                       "description": "Required except for promise and paid. One of: restructuring, human, support, refused, hardship, dispute, service_error, failed, declined, callback, no_callback, wrong_number, deceased, unclear."},
        },
        ["outcome"])
    t["pre_process_code"] = CLOSE_PRE
    return t


def to_close(desc):
    return {"target_node": "close", "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def bool_true(var):
    return {"logic": "or", "conditions": [
        {"variable": var, "operator": "equals", "operand": "true"},
        {"variable": var, "operator": "equals", "operand": "True"}]}


def conv(name, task, tools, transitions, on_enter=None, extra=None):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": tools,
         "transitions": transitions, "max_node_turns": 40, "max_turn_transition": "close"}
    if on_enter:
        n["on_enter"] = on_enter
    if extra:
        n.update(extra)
    return n


def code_node(name, code, nxt):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                             "parameters": {"type": "object", "properties": {
                                 "code": {"type": "string", "default": code},
                                 "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}]}


SYSTEM_COMMON = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. One or two short sentences per turn. The customer is addressed as {{title}} {{last_name}}.
Rules for the whole call:
- No improvising. Never offer a discount, a waiver, an instalment plan or any term that is not in your instructions.
- If asked something you have no information for, say you do not have that information. Never invent figures, dates or reasons.
- "Is this a scam?": say they can verify the call by phoning Freya Bank's customer service number, then go on with the current step.
- "Am I talking to a robot / an AI?": say you are Freya Bank's digital assistant, then go on with the current step.
- Until the customer has passed both security questions, never say "collections", "debt", "payment", "overdue", "late" or name any product, to anyone.
- The word "recorded" is used only to say a payment promise was recorded after the system confirmed it. Never claim anything is done unless a tool result confirmed it. If a tool call fails, say so.
- Call at most one tool per message. After every tool result, speak to the customer or call the next tool; never end a turn with nothing.
- When a rule says to use a tool, call the tool; saying it is not enough.
Dates (worked out from the call's current time, never from the real clock):
{{date_facts}}"""


def build(slot, multi):
    nodes = {}
    nodes["setup"] = code_node("setup", SETUP_CODE, "opening")

    nodes["opening"] = conv(
        "opening",
        """You opened the call and asked: "Am I speaking with {{title}} {{last_name}}?". Your job here is only to find out who answered. The only tool here is transfer_to_agent, for a customer who insists on a human.
- Only "yes", "that's me", "speaking" or the customer's own name confirm. Then call transition_to_security at once.
- "Hello", "go ahead", "who is this" or anything unclear does not confirm: ask "Am I speaking with {{title}} {{last_name}}?" once more. If after that second ask it is still unclear, thank them, say goodbye and call transition_to_close_call (not reached, unclear).
- If they ask a robot or scam question instead, answer it first; the ask that follows counts as the second ask.
- If someone else answered (a relative, a colleague, "he is not here"), call transition_to_third_party. Say nothing about why you are calling.
- "This number does not belong to that person": thank them, say goodbye and call transition_to_close_call (wrong number).
- "The customer has died": say exactly "I am sorry for your loss.", ask nothing else, and call transition_to_close_call (deceased).
- If they say they do not want to talk: ask once whether you can continue; if they refuse a second time, say goodbye and call transition_to_close_call (declined).
- If they ask why you are calling, say you can explain once you have confirmed you are speaking with the right person.
- If they ask for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general, then call transition_to_close_call.""",
        [transfer_tool(["general"])],
        [
            {"target_node": "security", "description": "The person confirmed they are the customer", "is_tool_call": True,
             "condition": {"operator": "matches_intent", "description": "The person confirmed they are the customer"}},
            {"target_node": "third_party", "description": "Someone other than the customer answered", "is_tool_call": True,
             "condition": {"operator": "matches_intent", "description": "Someone other than the customer answered"}},
            to_close("The call must end now: unclear after the second ask, wrong number, deceased, refused to talk twice, or transferred to a human"),
        ],
        on_enter={"type": "tts", "text": "Hello, this is the digital assistant calling from Freya Bank, and we keep a recording of this call. Am I speaking with {{title}} {{last_name}}?"},
        extra={"on_enter_first_entry_only": True})

    nodes["third_party"] = conv(
        "third_party",
        """Someone other than {{title}} {{last_name}} is on the line. Say nothing beyond who you are and never say why you are calling. A relative may not answer security questions and is told nothing about the account, even if they offer to pay.
Ask when {{title}} {{last_name}} can be reached.
Callback rule: a callback can be booked only today or on the next business day (see the callback window in the dates), from 10:00 to 19:00 both included, and later than now. Convert what the person says to a date YYYY-MM-DD and a time HH:MM.
- Inside the window: call schedule_callback with that date and time. After it succeeds, thank them, say goodbye and call transition_to_close_call (not reached, callback). If it fails, say you could not book it, then say goodbye and call transition_to_close_call.
- Outside the window: ask once for another time inside the window, naming the allowed window. If the second time is outside too, book nothing, thank them, say goodbye and call transition_to_close_call (not reached, no callback).
- "This number does not belong to that person": say goodbye and call transition_to_close_call (wrong number).
- "The customer has died": say exactly "I am sorry for your loss.", ask nothing else, and call transition_to_close_call (deceased).
- If it turns out the customer is on the line after all and confirms, call transition_to_security.""",
        [callback_tool()],
        [
            {"target_node": "security", "description": "The customer themselves is now on the line and confirmed", "is_tool_call": True,
             "condition": {"operator": "matches_intent", "description": "The customer themselves is now on the line and confirmed"}},
            to_close("The call must end now: callback handled, no callback, wrong number or deceased"),
        ],
        on_enter={"type": "llm"},
        extra={"on_enter_first_entry_only": True})

    nodes["security"] = conv(
        "security",
        """The customer confirmed who they are. Run the security check. Do not say why you are calling yet.
1. Ask for their date of birth. Call verify_identity with field date_of_birth and the date as YYYY-MM-DD, whatever way they said it. A date given only in numbers is day, then month, then year.
2. When it passes, ask for the last four digits of the phone number on file. Call verify_identity with field phone_last4.
Follow the what_to_do_next line of every verify_identity result. Ask one question at a time.
- A day_month_swapped hint or an unreadable answer is not a wrong answer: ask them to say the month as a word.
- After three wrong answers: do not state the debt; tell them to use the Freya Bank mobile app or a branch, thank them, say goodbye and call transition_to_close_call (not verified, failed).
- If they do not want to answer: explain once that the questions protect their account. Asking what the call is about instead of answering counts as declining. If they decline a second time, thank them, say goodbye and call transition_to_close_call (not verified, declined).
- If they ask for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general, then call transition_to_close_call.""",
        [verify_tool(), transfer_tool(["general"])],
        [
            {"target_node": "load_account", "description": "Both security answers passed",
             "condition": bool_true("verify_identity_response.data.all_verified")},
            to_close("The call must end now: security failed, declined, or transferred to a human"),
        ],
        on_enter={"type": "llm", "prompt": "Thank the customer and ask for their date of birth, for security. Do not say why you are calling."},
        extra={"on_enter_first_entry_only": True})

    nodes["load_account"] = {
        "name": "load_account", "node_type": "api_request", "passthrough": True,
        "passthrough_default_transition": "prepare_account", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{
            "type": "function", "config": {"timeoutMs": 12000, "maxRetries": 2},
            "function": {"name": "get_account", "handler": "__function__:api_call", "description": "Get the late products.",
                         "parameters": {"type": "object", "properties": {
                             "url": {"type": "string", "default": f"{BASE}/get_account"},
                             "method": {"type": "string", "default": "POST"},
                             "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                             "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}}, "required": ["customer_id"]}}}}}],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [{"target_node": "prepare_account", "description": "always", "condition": {"operator": "always"}}]}
    nodes["prepare_account"] = code_node("prepare_account", SETUP_CODE + ACCOUNT_CODE, "negotiate")

    if not multi:
        neg_task = """The customer passed security. Account facts (worked out in code, use them exactly):
{{account_facts}}
If no account data could be loaded, say you cannot see the account details right now, thank them, say goodbye and call transition_to_close_call.

Tool rules first: call create_promise only after a clear yes to the read-back. Call transfer_to_agent for the transfer cases below, then transition_to_close_call. Call transition_to_close_call when the call must end, after your thank-you and goodbye.

1. Say you are calling from the collections team about a late payment, name the product in words as given in the facts, and state the past-due amount and how many days late it is. Then ask exactly: "Can you make this payment today?"
2. Amounts: you propose every amount yourself; never ask "how much can you pay?". Start with the full past-due amount. If the customer says the full amount is too much, offer the floor once and say the rest stays overdue. An amount the customer names from the floor up to the full amount (both included) is accepted. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept it, that is a flat refusal.
3. Dates: a PTP date must be today or later, a business day (see the calendar), and not after the product's deadline. A weekend day or holiday not after the deadline: offer the next business day. A date after the deadline: say the latest date you can record is the deadline and offer it; refusing it is a flat refusal. Vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day; if still none, propose the deadline. "Next <weekday>" = that weekday in the following calendar week; "this <weekday>" = in the current week (use the calendar).
4. A date or amount the customer proposes is never a refusal. A flat refusal or non-answer ("no" to paying today with no date and no amount) uses one persuasion attempt. Use the attempts exactly as listed in the facts (early stage: one attempt; late stage: two). When the attempts are used up, stop; never repeat an offer already refused. Then thank them, say goodbye and call transition_to_close_call (no promise, refused).
5. Confirm: read back the product, the amount and the date and ask "Do you confirm?". Call create_promise only after a clear yes. If they change the date or amount, check it again under rules 2 and 3 and read back again. One PTP per product. After a recorded PTP, a request to change or cancel it: they can do that in the mobile app.
6. create_promise result: follow what_to_do_next. On success say it is recorded and say "You will receive a text message confirming this promise." If it fails, call it once more; if it fails again, say you could not record the PTP (close as no promise, service error). Then thank them, say goodbye and call transition_to_close_call.
7. Hardship (illness, a death in the family, job loss): one short sentence of sympathy, no persuasion. Offer to connect them with the customer support team. Accept: transfer_to_agent queue support, then transition_to_close_call. Decline: thank them, say goodbye, transition_to_close_call (no promise, hardship). If they still name a date or amount themselves, handle it as a PTP.
8. New payment plan or lower instalments: describe no plan; call transfer_to_agent queue restructuring, then transition_to_close_call.
9. Asks for a human: ask once whether you can help first. If they insist: transfer_to_agent queue general, then transition_to_close_call.
10. "I already paid": tell them payments can take one business day to appear; no PTP; thank them, say goodbye, transition_to_close_call (paid).
11. "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: no arguing, no PTP; thank them, say goodbye, transition_to_close_call (no promise, dispute).
12. Says twice they do not want to talk: thank them, say goodbye, transition_to_close_call (no promise, refused)."""
        neg_tools = [promise_tool(), transfer_tool(["restructuring", "general", "support"])]
    else:
        neg_task = """The customer passed security. Account facts, one line per late product, in get_account order (worked out in code, use them exactly; each product has its own stage, deadline, floor and attempts):
{{account_facts}}
If no account data could be loaded, say you cannot see the account details right now, thank them, say goodbye and call transition_to_close_call.

Tool rules first: one tool per message. create_promise only after the single confirmation of the full read-back, once per product. add_note once for every product that ends without a recorded PTP, before you end the call, except on a transfer. transfer_to_agent for the transfer cases, then transition_to_close_call. transition_to_close_call only when all notes are done, after your thank-you and goodbye.

1. Say you are calling from the collections team about late payments. Before asking anything, state every late product, one sentence per product: the product in words as in the facts, its past-due amount and how many days late it is.
2. First ask covers all products at once: can they pay all of them today? If not, take the products one at a time in the order of the facts; do not ask about today again for each. Every product starts at its first persuasion attempt; attempts are counted per product.
3. Amounts per product: you propose every amount; never ask "how much can you pay?". Start with the full past-due amount. If the full amount is too much, offer that product's floor once and say the rest stays overdue. An amount from the floor up to the full amount (both included) is accepted. Below the floor: say it cannot be recorded and offer the floor once; not accepted = flat refusal.
4. Dates per product: today or later, a business day (see the calendar), not after that product's deadline. Weekend day or holiday not after the deadline: offer the next business day. A date after the deadline: say the latest date you can record is the deadline and offer it; refusing it is a flat refusal. Vague period: ask once for the exact day; if still none, propose the deadline. "Next <weekday>" = the following calendar week; "this <weekday>" = the current week. If the customer names one date for everything and it is after one product's deadline, that product goes on its own deadline and the read-back says so; the others keep the named date.
5. A date or amount the customer proposes is never a refusal. A flat refusal or non-answer uses one attempt for that product. Use the attempts listed in the facts for that product. When a product's attempts are used up, stop for that product (no PTP, reason refused) and go to the next. Never repeat an offer already refused.
6. Dispute ("not mine", "never had it", closed or paid off in the past) or "I already paid" (payments can take one business day to appear) about one product: no arguing, no PTP for it; it gets note reason dispute or paid; go on with the other products.
7. Hardship (illness, a death in the family, job loss): one short sentence of sympathy, no persuasion. Offer the customer support team. Accept: transfer_to_agent queue support (no notes), then transition_to_close_call. Decline: the remaining products without a PTP get note reason hardship. If they still name a date or amount themselves, handle it as a PTP.
8. Confirm: when every product is settled, read all agreed PTPs back together (product, amount, date for each) and ask once "Do you confirm?". After a clear yes, call create_promise once for each agreed product, one per message. If they change something, check it again and read back again. One PTP per product. A recorded PTP cannot be changed or cancelled in this call; they can use the mobile app.
9. create_promise results: follow what_to_do_next. On success say it is recorded. If one fails, call it once more for that product; if it fails again, say you could not record that PTP; PTPs already recorded stay; that product gets note reason service_error. After the recorded PTPs, say "You will receive a text message confirming this promise."
10. Notes: for every product that ends without a recorded PTP, call add_note with its product_id and one reason (refused, hardship, dispute, paid or service_error). This applies also when no product gets a PTP. Never add a note when the call is transferred, neither before nor after the transfer.
11. New payment plan or lower instalments: describe no plan; do not record PTPs not yet recorded; no notes; transfer_to_agent queue restructuring, then transition_to_close_call.
12. Asks for a human: ask once whether you can help first. If they insist: no notes; transfer_to_agent queue general, then transition_to_close_call.
13. Says twice they do not want to talk: every product without a PTP gets note reason refused; then thank them, say goodbye, transition_to_close_call."""
        neg_tools = [promise_tool(), note_tool(), transfer_tool(["restructuring", "general", "support"])]

    nodes["negotiate"] = conv("negotiate", neg_task, neg_tools,
                              [to_close("All bank actions for this call are done and the call must end now")],
                              on_enter={"type": "llm"}, extra={"on_enter_first_entry_only": True, "max_node_turns": 60})

    if not multi:
        close_rules = """Pick exactly one outcome and reason from the whole conversation:
- promise: at least one PTP was recorded (create_promise returned ok), and no transfer followed.
- paid: the customer already paid.
- transferred + restructuring / human / support: a transfer_to_agent call was made to that queue (restructuring, general = human, support). A transfer after a recorded PTP still closes as transferred.
- no_promise + refused: persuasion attempts used up, or said twice they do not want to talk after security.
- no_promise + hardship: hardship, declined the support team.
- no_promise + dispute: not mine, never had it, closed or paid off in the past.
- no_promise + service_error: create_promise failed twice (or account data could not be loaded).
- not_verified + failed: three wrong security answers.
- not_verified + declined: refused the security questions, or did not want to talk before verification.
- not_reached + callback: a callback was booked. not_reached + no_callback: no time inside the window. not_reached + wrong_number. not_reached + deceased. not_reached + unclear: still unclear who answered after the second ask."""
    else:
        close_rules = """Pick exactly one outcome and reason from the whole conversation:
- transferred + restructuring / human / support: a transfer_to_agent call was made to that queue (restructuring, general = human, support). This wins over everything else.
- promise: at least one PTP was recorded (create_promise returned ok) and no transfer happened.
- When no PTP was recorded after security: if every product was noted paid, outcome paid. Otherwise no_promise with the reason of the first product, in account order, whose note is not paid (refused, hardship, dispute or service_error).
- not_verified + failed: three wrong security answers. not_verified + declined: refused the security questions, or did not want to talk before verification.
- not_reached + callback: a callback was booked. not_reached + no_callback: no time inside the window. not_reached + wrong_number. not_reached + deceased. not_reached + unclear: still unclear who answered after the second ask."""
    nodes["close"] = conv(
        "close",
        "The conversation is over. No other action is possible now. If you have not yet thanked the customer and said goodbye, do it in one short sentence. Then call close_call exactly once.\n"
        + close_rules + "\nDo not say anything was recorded or booked unless a tool result confirmed it.",
        [close_tool()],
        [{"target_node": "end", "description": "close_call returned",
          "condition": {"logic": "or", "conditions": [
              {"variable": "close_call_success_count", "operator": "greater_than", "operand": 0},
              {"variable": "close_call_failure_count", "operator": "greater_than", "operand": 0}]}}],
        on_enter={"type": "llm"},
        extra={"on_enter_first_entry_only": True, "max_node_turns": 3, "max_turn_transition": "end"})

    nodes["end"] = {"name": "end", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                    "transitions": [], "terminal": {"type": "function", "function": {
                        "name": "call_closed", "handler": "__function__:end_call",
                        "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}

    wf = {"initial_node": "setup", "system_prompt": SYSTEM_COMMON, "nodes": nodes, "global_nodes": {},
          "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}
    (OUT / f"{slot}.workflow.json").write_text(json.dumps(wf, indent=1))

    contract = {"terminal_tools": [{"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": f"briefs/brief-a-raw.md", "quote": "Every call ends with exactly one `close_call`, as the last tool call, with an outcome and, where the list gives one,"}]}],
        "every_call_ends_with_terminal": True}
    (OUT / f"{slot}.contract.json").write_text(json.dumps(contract, indent=1))


build("brief-a-raw", False)
build("brief-b-raw", True)
