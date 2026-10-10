"""Generate out/pl-g5-memo-raw.body.json and out/pl-g5-memo-raw.closing.json."""
import json
from pathlib import Path

SLOT = "pl-g5-memo-raw"
BRIEF = f"briefs/{SLOT}.md"
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"


def api_tool(name, desc, fields, required, mapping=None, retries=0):
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
                "url": {"type": "string", "default": f"{BASE}/{name}"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": props, "required": required},
            }},
        },
    }
    if mapping:
        t["response_mapping"] = mapping
    return t


def var(name, op, operand=None):
    c = {"variable": name, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return c


def when(*checks):
    return {"logic": "or", "conditions": [checks[0] if len(checks) == 1 else {"logic": "and", "conditions": list(checks)}]}


def is_true(name):
    return {"logic": "or", "conditions": [var(name, "equals", "true"), var(name, "equals", "True")]}


def det(target, desc, cond):
    return {"target_node": target, "description": desc, "condition": cond}


def tool_tr(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def code_node(name, code, nxt):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {
            "name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {
                "code": {"type": "string", "default": code},
                "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [always(nxt)],
    }


def ext(name, desc, enum=None, typ="string", conf=0.6):
    e = {"name": name, "type": typ, "description": desc, "min_confidence": conf}
    if enum:
        e["enum_values"] = enum
    return e


HELPERS = r'''
import datetime
import json
import re
HOL = set(['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'])
DN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)
def parse_now(raw):
    raw = str(raw or '').strip().replace(' ', 'T')
    try:
        return datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        try:
            return datetime.datetime.fromisoformat(raw[:10] + 'T00:00')
        except Exception:
            return datetime.datetime(2026, 10, 14, 11, 0)
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def nextbd(d):
    d = d + ONE
    while not isbd(d):
        d = d + ONE
    return d
def nth_bd_after(d, n):
    k = 0
    while k < n:
        d = d + ONE
        if isbd(d):
            k += 1
    return d
def say(d):
    return DN[d.weekday()] + ' ' + str(d.day) + ' ' + MN[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
def money(x):
    try:
        f = float(x)
    except Exception:
        return str(x)
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return '%.2f' % f
'''

SETUP_CODE = HELPERS + r'''
try:
    now = parse_now(vars.get('now'))
    today = now.date()
    hm = now.strftime('%H:%M')
    nb = nextbd(today)
    lines = []
    lines.append('Current date and time: ' + say(today) + ', ' + hm + '. Use this, never the real clock.')
    if hm < '17:00':
        start = '09:00' if hm < '09:00' else hm
        lines.append('Today ' + say(today) + ': a callback time must be later than ' + hm + ', from ' + start + ' up to 17:00 (17:00 included, 09:00 is the earliest).')
    else:
        lines.append('Today ' + say(today) + ': no callback is possible any more, it is after 17:00.')
    lines.append('Next business day ' + say(nb) + ': any time from 09:00 to 17:00, both included.')
    lines.append('No other day is allowed. No time before 09:00 or after 17:00 is allowed. Tomorrow is ' + say(today + ONE) + '.')
    vars['callback_facts'] = '\n'.join(lines)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['callback_facts'] = 'Callbacks: today (later than now) or the next business day, from 09:00 to 17:00, both included.'
    vars['setup_state'] = 'error'
'''

ACCOUNT_CODE = HELPERS + r'''
def read_products():
    prods = vars.get('products')
    if isinstance(prods, str):
        try:
            prods = json.loads(prods)
        except Exception:
            prods = None
    if isinstance(prods, dict):
        prods = [prods]
    if isinstance(prods, list):
        return [p for p in prods if isinstance(p, dict)]
    found = dict()
    for k in list(vars.keys()):
        m = re.search(r'products\.(\d+)\.(\w+)$', str(k))
        if m:
            n = int(m.group(1))
            if n not in found:
                found[n] = dict()
            found[n][m.group(2)] = vars.get(k)
    return [found[n] for n in sorted(found)]
try:
    now = parse_now(vars.get('now'))
    today = now.date()
    prods = read_products()
    n = len(prods)
    vars['product_count'] = n
    ws = today - datetime.timedelta(days=today.weekday())
    cal = ['Today is ' + say(today) + '. Tomorrow is ' + say(today + ONE) + '.']
    for k in range(7):
        cal.append('this ' + DN[k] + ' = ' + say(ws + datetime.timedelta(days=k)) + '; next ' + DN[k] + ' = ' + say(ws + datetime.timedelta(days=7 + k)))
    this_week = [ws + datetime.timedelta(days=k) for k in range(7)]
    next_week = [ws + datetime.timedelta(days=7 + k) for k in range(7)]
    lbd_this = max([d for d in this_week if isbd(d)] or [today])
    if lbd_this <= today:
        eow = max([d for d in next_week if isbd(d)])
    else:
        eow = lbd_this
    summary = []
    for i in range(1, 4):
        if i > n:
            vars['attempts_' + str(i)] = 0
            vars['product_id_' + str(i)] = ''
            vars['facts_' + str(i)] = 'No product.'
            for a in range(1, 4):
                vars['offer_' + str(i) + '_' + str(a)] = 'No product.'
            continue
        p = prods[i - 1]
        typ = str(p.get('type') or '')
        if typ == 'credit_card':
            words = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'the minimum payment'
        elif typ == 'car_loan':
            words = 'car loan'
            floor = p.get('instalment_amount')
            floor_name = 'the instalment amount'
        else:
            words = 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'the instalment amount'
        full = p.get('past_due')
        try:
            late = int(float(p.get('days_late')))
        except Exception:
            late = 8
        if late <= 7:
            band, deadline, attempts = 'early', nth_bd_after(today, 12), 1
        else:
            band, deadline, attempts = 'late', nth_bd_after(today, 6), 2
        e = eow if eow <= deadline else deadline
        valid = []
        d = today
        while d <= deadline:
            if isbd(d):
                valid.append(say(d))
            d = d + ONE
        vars['attempts_' + str(i)] = attempts + 1
        vars['product_id_' + str(i)] = str(p.get('product_id') or '')
        f = []
        f.append('Product: ' + words + ' (product_id ' + str(p.get('product_id') or '') + ').')
        f.append('Full past-due amount: ' + money(full) + '. Days late: ' + str(late) + '.')
        f.append('Floor (lowest amount you may record, ' + floor_name + '): ' + money(floor) + '.')
        f.append('Any amount from ' + money(floor) + ' up to ' + money(full) + ', both included, may be recorded. Nothing below ' + money(floor) + ' and nothing above ' + money(full) + '.')
        f.append('Deadline (latest promise date you may record): ' + say(deadline) + '.')
        f.append('Today is ' + ('a business day, so paying today is allowed.' if isbd(today) else 'not a business day, so today cannot be the promise date.'))
        f.append('The ONLY promise dates you may record: ' + '; '.join(valid) + '.')
        f.append('Bank holidays (not business days): 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01. Saturdays and Sundays are not business days.')
        f.append('Calendar ("this <weekday>" is in the current week, "next <weekday>" is in the following calendar week):')
        f.extend(cal)
        vars['facts_' + str(i)] = '\n'.join(f)
        summary.append(vars['facts_' + str(i)])
        lead = ''
        if i > 1:
            lead = 'If a promise for the previous product was just recorded, first say: "Your promise is recorded. You will receive a text message confirming this promise." Then say there is another late product. '
        vars['offer_' + str(i) + '_1'] = lead + 'Say that you are calling from the collections team about a late payment on the customer\'s ' + words + '. Say the past-due amount is ' + money(full) + ' and that it is ' + str(late) + ' days late. Then ask exactly: "Can you make this payment today?"'
        vars['offer_' + str(i) + '_2'] = 'The customer refused. This is persuasion attempt 1. Propose that they pay the full past-due amount of ' + money(full) + ' on ' + say(e) + '. Only if the customer already said the full amount is too much, propose the floor ' + money(floor) + ' on ' + say(e) + ' instead and say that the rest stays overdue. Do not repeat an offer the customer already refused.'
        vars['offer_' + str(i) + '_3'] = 'The customer refused again. This is persuasion attempt 2, the last one. Propose the floor amount ' + money(floor) + ' on the deadline, ' + say(deadline) + ', and say that the rest stays overdue. Do not repeat an offer the customer already refused.'
    vars['account_summary'] = '\n\n'.join(summary) if summary else 'No product details are available.'
    vars['account_state'] = 'ok' if n > 0 else 'empty'
except Exception as ex:
    vars['product_count'] = 0
    vars['account_summary'] = 'No product details are available.'
    vars['account_state'] = 'error'
'''

for c in (SETUP_CODE, ACCOUNT_CODE):
    assert "{{" not in c and "}}" not in c

OPENING_LINE = ("Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. "
                "Am I speaking with {{title}} {{last_name}}?")

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. Keep every turn to one or two short sentences and ask one question at a time.
The customer is {{title}} {{last_name}} (first name {{first_name}}). Address them as {{title}} {{last_name}}.
The current date and time is {{now}}. All date rules use this value, never the real clock.
Always:
- If asked whether you are a robot or an AI, say you are Freya Bank's digital assistant, then continue.
- If asked "Is this a scam?", say they can verify the call by phoning Freya Bank's customer service number, then continue.
- If asked something the information you were given does not answer, say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any term not given to you.
- Never say something is recorded or booked unless the tool returned ok true. If a tool fails, say so.
- After every tool result, speak to the person or call the next tool. Never end a turn with nothing.
- Do not say goodbye unless your current task tells you to; the farewell is said automatically when the call ends."""

nodes = {}

nodes["setup"] = code_node("setup", SETUP_CODE, "opening")

nodes["opening"] = {
    "name": "opening", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": OPENING_LINE}, "on_enter_first_entry_only": True,
    "task_message": (
        "You asked whether you are speaking with {{title}} {{last_name}}. Your only job is to find out who is on the line. No tool call is allowed in this turn.\n"
        "- Before identity is verified, never say why you are calling. Never say \"collections\", \"debt\", \"payment\", \"account\" or any product. This holds for everyone, relatives too.\n"
        "- Only \"yes\", \"that's me\", \"speaking\" or the customer's own name confirms. \"Hello\", \"go ahead\" and \"who is this\" do not.\n"
        "- If the answer is unclear, answer any question first (who you are: Freya Bank's digital assistant; you can explain once you speak with {{title}} {{last_name}}), then ask once more: \"Am I speaking with {{title}} {{last_name}}?\". This is the second and last ask.\n"
        "- If after your second ask it is still unclear, call transition_to_close_not_reached_unclear."),
    "extraction_schema": [ext("who_answered",
        "Who is on the line, from the person's latest message. customer: they confirm with yes, that's me, speaking, or the customer's own name. "
        "someone_else: they are not the customer (a relative, a colleague, someone who says the customer is not available or not here). "
        "wrong_number: they say this number does not belong to the customer or they do not know the customer. "
        "deceased: they say the customer has died. Leave empty for hello, go ahead, who is this, questions or anything unclear.",
        ["customer", "someone_else", "wrong_number", "deceased"])],
    "max_node_turns": 3, "max_turn_transition": "close:not_reached/unclear",
    "transitions": [
        det("close:not_reached/deceased", "the customer has died", when(var("who_answered", "equals", "deceased"))),
        det("close:not_reached/wrong_number", "wrong number", when(var("who_answered", "equals", "wrong_number"))),
        det("identity", "the customer confirmed", when(var("who_answered", "equals", "customer"))),
        det("third_party", "someone else answered", when(var("who_answered", "equals", "someone_else"))),
        tool_tr("close:not_reached/unclear", "You asked twice whether you are speaking with the customer and it is still not confirmed."),
        tool_tr("close:not_verified/declined", "The person has said for the second time that they do not want to talk."),
    ],
}

handover_cond = "A different person"
nodes["handover"] = {
    "name": "handover", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": OPENING_LINE},
    "task_message": (
        "Someone new came to the phone. Find out whether this is {{title}} {{last_name}}. No tool call is allowed in this turn.\n"
        "- Never say why you are calling. Never say \"collections\", \"debt\", \"payment\", \"account\" or any product.\n"
        "- Only \"yes\", \"that's me\", \"speaking\" or the customer's own name confirms. If unclear, answer a question first, then ask once more. If still unclear after that, call transition_to_close_not_reached_unclear."),
    "extraction_schema": [ext("handover_who",
        "From the latest message. customer: they confirm with yes, that's me, speaking, or the customer's own name. not_customer: they say they are not the customer. Empty otherwise.",
        ["customer", "not_customer"])],
    "max_node_turns": 3, "max_turn_transition": "close:not_reached/unclear",
    "transitions": [
        det("identity", "the customer confirmed", when(var("handover_who", "equals", "customer"))),
        det("third_party", "not the customer", when(var("handover_who", "equals", "not_customer"))),
        tool_tr("close:not_reached/unclear", "You asked twice and it is still not confirmed that this is the customer."),
    ],
}

nodes["third_party"] = {
    "name": "third_party", "node_type": "conversation",
    "on_enter": {"type": "llm"}, "on_enter_first_entry_only": True,
    "task_message": (
        "The person on the line is not {{title}} {{last_name}}. Ask when {{title}} {{last_name}} can be reached.\n"
        "- Never say why you are calling. Say nothing beyond who you are. Never say \"collections\", \"debt\", \"payment\", \"account\" or any product. "
        "This person may not answer security questions and may not be told anything about any account, even if they offer to pay. If they offer to pay or ask why, say you can only speak with {{title}} {{last_name}}.\n"
        "- If the person says the customer has died, say exactly \"I am sorry for your loss.\" and ask nothing else.\n"
        "CALLBACK RULES\n{{callback_facts}}\n"
        "- When the person gives a day and a time inside these rules, CALL schedule_callback with the date as YYYY-MM-DD and the time as HH:MM (24 hour). Do not ask for confirmation first.\n"
        "- If the day or time is outside the rules, say it is not possible and ask once for another time within the allowed window (name the window). If the second answer is also outside, or they cannot give a time, call transition_to_close_not_reached_no_callback. Do not schedule.\n"
        "- If schedule_callback fails, call it once more with the same values. If it fails again, say you could not book the callback and call transition_to_close_not_reached_no_callback.\n"
        "- If the customer comes to the phone, call transition_to_handover."),
    "tools": [api_tool("schedule_callback",
        "Book a callback. CALL it as soon as the person gives a day and time inside the callback rules.",
        {"date": {"type": "string", "description": "Callback date as YYYY-MM-DD.", "default": "{{date}}"},
         "time": {"type": "string", "description": "Callback time as HH:MM, 24 hour, from 09:00 to 17:00.", "default": "{{time}}"}},
        ["date", "time"])],
    "extraction_schema": [ext("third_party_news",
        "From the latest message only. deceased: the person says the customer has died. wrong_number: the person says this number does not belong to the customer. Empty otherwise.",
        ["deceased", "wrong_number"])],
    "max_node_turns": 8, "max_turn_transition": "close:not_reached/no_callback",
    "transitions": [
        det("close:not_reached/callback", "callback booked", when(var("schedule_callback_success_count", "greater_than", 0))),
        det("close:not_reached/deceased", "the customer has died", when(var("third_party_news", "equals", "deceased"))),
        det("close:not_reached/wrong_number", "wrong number", when(var("third_party_news", "equals", "wrong_number"))),
        tool_tr("handover", "The customer has come to the phone."),
        tool_tr("close:not_reached/no_callback", "No callback can be booked: the second proposed time is also outside the allowed window, the person cannot give a time, or booking failed twice."),
    ],
}

nodes["identity"] = {
    "name": "identity", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you, {{title}} {{last_name}}. For security I need to ask two questions. First, what is your date of birth?"},
    "on_enter_first_entry_only": True,
    "task_message": (
        "Verify the customer's identity with two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file.\n"
        "TOOL RULES\n"
        "- Every time the customer gives an answer, CALL verify_identity at once. field date_of_birth with the date as YYYY-MM-DD, or field phone_last4 with four digits.\n"
        "- Convert any spoken date to YYYY-MM-DD yourself. A date given only as numbers is day, then month, then year (\"05/03/1985\" is 1985-03-05).\n"
        "- If the result has hint day_month_swapped, ask the customer to say the month as a word, then call verify_identity again. That retry is not a wrong answer.\n"
        "- If verified is false, tell them the answer did not match and ask the same question again.\n"
        "- If verified is true and the phone number has not been checked yet, ask for the last four digits of the phone number on file.\n"
        "- If ok is false because the date could not be read, ask them to say the date again.\n"
        "OTHER RULES\n"
        "- Before identity is verified, never say why you are calling. Never say \"collections\", \"debt\", \"payment\", \"account\" details or any product.\n"
        "- If the customer does not want to answer, or asks what the call is about instead of answering, explain once that these questions protect their account and ask again. "
        "If they refuse a second time or ask a second such question, call transition_to_close_not_verified_declined.\n"
        "- If they ask for a human, ask once whether you can help first. If they insist, call transition_to_transfer_general.\n"
        "- If the tool says no attempts are left, call transition_to_close_not_verified_failed."),
    "tools": [api_tool("verify_identity",
        "Check one security answer. CALL it every time the customer answers a security question.",
        {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "description": "Which question: date_of_birth or phone_last4.", "default": "{{field}}"},
         "answer": {"type": "string", "description": "date_of_birth as YYYY-MM-DD; phone_last4 as four digits.", "default": "{{answer}}"}},
        ["field", "answer"])],
    "max_node_turns": 14, "max_turn_transition": "close:not_verified/declined",
    "transitions": [
        det("fetch_account", "both answers verified", is_true("verify_identity_response.data.all_verified")),
        det("close:not_verified/failed", "three wrong answers", when(var("verify_identity_response.data.wrong_answers_left", "equals", 0))),
        tool_tr("close:not_verified/declined", "The customer refused the security questions a second time, or asked a second time what the call is about instead of answering, or said twice they do not want to talk."),
        tool_tr("transfer_general", "The customer insists on speaking to a human after you asked once whether you can help."),
        tool_tr("close:not_verified/failed", "The identity check reports that no attempts are left."),
    ],
}

nodes["fetch_account"] = {
    "name": "fetch_account", "node_type": "api_request", "passthrough": True,
    "passthrough_default_transition": "account_facts", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [api_tool("get_account", "Get the late products.", {}, [], retries=2)],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [
        det("close:no_promise/account_error", "lookup failed", when(var("fetch_account_failure_count", "greater_than", 0))),
        always("account_facts"),
    ],
}

nodes["account_facts"] = code_node("account_facts", ACCOUNT_CODE, "item:first")

NEGOTIATE_TASK = """The customer is verified. You are discussing a late payment.

WHAT TO DO NOW
{{offer_{i}_{a}}}

ACCOUNT FACTS
{{facts_{i}}}

TOOL RULES
- When the customer has agreed to a valid amount and a valid date, read back the product, the amount and the date and ask "Do you confirm?". After a clear yes, CALL create_promise in that same turn with amount and date (YYYY-MM-DD). Saying it is recorded is not enough, and never say it is recorded yourself.
- If create_promise fails once, call it again at once with the same values.

AMOUNTS
- Start with the full past-due amount. Never ask how much the customer can pay. You propose every amount.
- If the customer says the full amount is too much, offer the floor once and say that the rest stays overdue.
- If the customer proposes an amount from the floor up to the full amount, accept it. Below the floor: say it cannot be recorded and offer the floor once.

DATES
- A promise date must be one of the dates you may record (see the facts). Paying today means today's date.
- "Next <weekday>" is that weekday in the following calendar week; "this <weekday>" is in the current week. Use the calendar in the facts.
- If the customer names a weekend day or a bank holiday that is not after the deadline, offer the next business day.
- If the customer asks for a date after the deadline, say the latest date you can record is the deadline and offer it.
- For a vague period ("next week", "end of the month", "when my salary comes"), ask once for the exact day. If they still give none, propose the deadline.
- A date or an amount the customer proposes is never a refusal. Handle it with these rules.
- If the customer changes the date or amount at the read-back, check the new value and read back again.

OTHER
- Never offer a discount, a waiver, an instalment plan or any other term.
- If the customer asks for a human, ask once whether you can help first. If they insist, call transition_to_transfer_general.
- If the customer says for the second time in this call that they do not want to talk, call transition_to_close_no_promise_refused.
- No tool other than create_promise and the transitions named above is allowed."""

nodes["negotiate"] = {
    "name": "negotiate", "node_type": "conversation",
    "on_enter": {"type": "llm"}, "on_enter_first_entry_only": True,
    "task_message": NEGOTIATE_TASK,
    "tools": [api_tool("create_promise",
        "Record a payment promise. CALL it only right after the customer said a clear yes to your read-back of product, amount and date.",
        {"product_id": {"type": "string", "default": "{{product_id_{i}}}"},
         "amount": {"type": "number", "description": "The confirmed amount, a number from the floor up to the full past-due amount.", "default": "{{amount}}"},
         "date": {"type": "string", "description": "The confirmed promise date as YYYY-MM-DD.", "default": "{{date}}"}},
        ["amount", "date"],
        mapping=[{"path": "data.promise_id", "variable": "promise_{i}"}])],
    "extraction_schema": [ext("reply_{i}_{a}",
        "Classify ONLY the customer's latest message. "
        "yes: a flat refusal or a non-answer: says no to paying today without naming any date or amount; refuses the amount, the floor, the date or the deadline the agent just offered without proposing a date or an amount of their own; says no to the read-back without a new value; says they will not pay; or says they do not want to talk. "
        "hardship: mentions illness, a death in the family or losing their job. "
        "paid: says they already paid this past-due amount. "
        "dispute: says the debt is not theirs, they never had this product, or the product was closed or paid off in the past. "
        "plan: asks for a new payment plan, restructuring or lower instalments. "
        "other: anything else, including every message that names a date or an amount, agreement, the full amount being too much, and questions.",
        ["yes", "hardship", "paid", "dispute", "plan", "other"])],
    "max_node_turns": 20, "max_turn_transition": "close:no_promise/refused",
    "transitions": [
        det("item:next", "promise recorded for this product", when(var("promise_{i}", "is_set"))),
        det("close:no_promise/service_error", "create_promise failed twice", when(var("create_promise_failure_count", "greater_than", 1))),
        det("hardship", "hardship mentioned", when(var("reply_{i}_{a}", "equals", "hardship"))),
        det("close:paid", "already paid", when(var("reply_{i}_{a}", "equals", "paid"))),
        det("close:no_promise/dispute", "dispute", when(var("reply_{i}_{a}", "equals", "dispute"))),
        det("transfer_restructuring", "new plan requested", when(var("reply_{i}_{a}", "equals", "plan"))),
        tool_tr("transfer_general", "The customer insists on speaking to a human after you asked once whether you can help."),
        tool_tr("close:no_promise/refused", "The customer has said for the second time in this call that they do not want to talk."),
    ],
}

nodes["after_items"] = {
    "name": "after_items", "node_type": "conversation", "passthrough": True,
    "passthrough_default_transition": "close:no_promise/refused", "on_enter": {"type": "silent"},
    "disable_inactivity_monitor": True, "task_message": "Do not call a tool in this turn.",
    "transitions": [
        det("wrap_up", "a promise was recorded", when(var("create_promise_success_count", "greater_than", 0))),
        always("close:no_promise/refused"),
    ],
}

nodes["wrap_up"] = {
    "name": "wrap_up", "node_type": "conversation",
    "on_enter": {"type": "llm"}, "on_enter_first_entry_only": True,
    "task_message": (
        "create_promise returned ok true. First say exactly: \"Your promise is recorded. You will receive a text message confirming this promise.\" Then ask whether there is anything else.\n"
        "- A recorded promise cannot be changed or cancelled in this call. If asked, say they can change it in the mobile app.\n"
        "- If they ask for a new payment plan or lower instalments, do not describe a plan; call transition_to_transfer_restructuring.\n"
        "- If they ask for a human, ask once whether you can help first. If they insist, call transition_to_transfer_general.\n"
        "- When there is nothing else, thank them and call transition_to_close_promise.\n"
        "No other tool is allowed."),
    "max_node_turns": 4, "max_turn_transition": "close:promise",
    "transitions": [
        tool_tr("transfer_restructuring", "The customer asks for a new payment plan or lower instalments."),
        tool_tr("transfer_general", "The customer insists on speaking to a human after you asked once whether you can help."),
        tool_tr("close:promise", "The customer has nothing else; the call can end."),
    ],
}

nodes["hardship"] = {
    "name": "hardship", "node_type": "conversation",
    "on_enter": {"type": "llm"}, "on_enter_first_entry_only": True,
    "task_message": (
        "The customer mentioned illness, a death in the family or job loss. Say one short sentence of sympathy. Make no persuasion attempt and do not ask for a payment. "
        "Offer to connect them with the customer support team.\n"
        "- If they accept, call transition_to_transfer_support.\n"
        "- If they decline, call transition_to_close_no_promise_hardship.\n"
        "- Only if the customer themselves names a date or an amount: check it against the facts below (amount from the floor up to the full amount, date among the dates you may record), read back product, amount and date, ask \"Do you confirm?\", and after a clear yes CALL create_promise. If it fails once, call it again with the same values.\n"
        "ACCOUNT FACTS\n{{account_summary}}"),
    "tools": [api_tool("create_promise",
        "Record a payment promise. CALL it only right after the customer said a clear yes to your read-back.",
        {"product_id": {"type": "string", "description": "product_id from the account facts, copied exactly.", "default": "{{hardship_product_id}}"},
         "amount": {"type": "number", "description": "The confirmed amount.", "default": "{{amount}}"},
         "date": {"type": "string", "description": "The confirmed promise date as YYYY-MM-DD.", "default": "{{date}}"}},
        ["product_id", "amount", "date"],
        mapping=[{"path": "data.promise_id", "variable": "hardship_promise"}])],
    "max_node_turns": 10, "max_turn_transition": "close:no_promise/hardship",
    "transitions": [
        det("wrap_up", "promise recorded", when(var("hardship_promise", "is_set"))),
        det("close:no_promise/service_error", "create_promise failed twice", when(var("create_promise_failure_count", "greater_than", 1))),
        tool_tr("transfer_support", "The customer accepts being connected with the customer support team."),
        tool_tr("close:no_promise/hardship", "The customer declines being connected with the customer support team."),
    ],
}


def transfer(name, queue, closing):
    return {
        "name": name, "node_type": "api_request", "passthrough": True,
        "passthrough_default_transition": "close:no_promise/transfer_error",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [api_tool("transfer_to_agent", "Hand the call to a person.",
                                 {"queue": {"type": "string", "enum": [queue], "default": queue}}, ["queue"])],
        "response_mapping": [],
        "transitions": [
            det(closing, "transfer done", when(var(f"{name}_success_count", "greater_than", 0))),
            always("close:no_promise/transfer_error"),
        ],
    }


nodes["transfer_general"] = transfer("transfer_general", "general", "close:transferred/human")
nodes["transfer_support"] = transfer("transfer_support", "support", "close:transferred/support")
nodes["transfer_restructuring"] = transfer("transfer_restructuring", "restructuring", "close:transferred/restructuring")

body = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    "global_nodes": {},
    "nodes": nodes,
}

ROW = {
    "promise": "Outcome: promise; Reason: none; When: at least one promise was recorded",
    "paid": "Outcome: paid; Reason: none; When: rule 39",
    "transferred": "Outcome: transferred; Reason: restructuring`, `human`, `support; When: rules 41, 42, 32",
    "no_promise": "Outcome: no_promise; Reason: refused`, `hardship`, `dispute`, `service_error; When: rules 31 and 45, 32, 40, 37",
    "not_verified": "Outcome: not_verified; Reason: failed`, `declined; When: rules 14, 15",
    "not_reached": "Outcome: not_reached; Reason: callback`, `no_callback`, `wrong_number`, `deceased`, `unclear; When: rules 6, 7, 8, 9, 3",
}
BYE = "Thank you for your time. Goodbye."


def closing(outcome, reason, say):
    s = {"outcome": outcome}
    if reason:
        s["reason"] = reason
    return {"set": s, "say": say, "evidence": [{"source": BRIEF, "quote": ROW[outcome]}]}


closings = {
    "promise": closing("promise", None, BYE),
    "paid": closing("paid", None, "Thank you for letting me know. Payments can take one business day to appear, so no promise is needed. " + BYE),
    "transferred/restructuring": closing("transferred", "restructuring", "Thank you. I am transferring you to a colleague now. Goodbye."),
    "transferred/human": closing("transferred", "human", "Thank you. I am transferring you to a colleague now. Goodbye."),
    "transferred/support": closing("transferred", "support", "Thank you. I am transferring you to the customer support team now. Goodbye."),
    "no_promise/refused": closing("no_promise", "refused", "I understand. " + BYE),
    "no_promise/hardship": closing("no_promise", "hardship", "I understand. Thank you for your time, and take care. Goodbye."),
    "no_promise/dispute": closing("no_promise", "dispute", "I understand, I will not take a promise today. " + BYE),
    "no_promise/service_error": closing("no_promise", "service_error", "I am sorry, I could not record your promise because of a technical problem. " + BYE),
    "no_promise/transfer_error": closing("no_promise", "service_error", "I am sorry, I could not connect you to a colleague because of a technical problem. " + BYE),
    "no_promise/account_error": closing("no_promise", "service_error", "I am sorry, I cannot reach the account details right now because of a technical problem. " + BYE),
    "not_verified/failed": closing("not_verified", "failed", "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch. " + BYE),
    "not_verified/declined": closing("not_verified", "declined", "I understand. " + BYE),
    "not_reached/callback": closing("not_reached", "callback", "Thank you, we will call back then. Goodbye."),
    "not_reached/no_callback": closing("not_reached", "no_callback", BYE),
    "not_reached/wrong_number": closing("not_reached", "wrong_number", "I apologise for the inconvenience. Thank you, goodbye."),
    "not_reached/deceased": closing("not_reached", "deceased", "I am sorry for your loss. Thank you, goodbye."),
    "not_reached/unclear": closing("not_reached", "unclear", BYE),
}

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]},
    "fields": {"customer_id": "{{customer_id}}"},
    "closings": closings,
    "precedence": [
        {"closing": "promise", "when": [var("create_promise_success_count", "greater_than", 0)],
         "keep": ["transferred/restructuring", "transferred/human", "transferred/support"],
         "evidence": [{"source": BRIEF, "quote": ROW["promise"]},
                      {"source": BRIEF, "quote": "If a transfer follows a recorded promise, close as `transferred` with that transfer's reason."}]},
        {"closing": "not_verified/failed", "when": [var("verify_identity_response.data.wrong_answers_left", "equals", 0)],
         "keep": [],
         "evidence": [{"source": BRIEF, "quote": "After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`."}]},
    ],
    "ladder": {
        "template": "negotiate", "done": "after_items",
        "items": {"count": "product_count", "max": 3,
                  "evidence": [{"source": BRIEF, "quote": "One promise per product."}]},
        "attempts": {"allowed": "attempts_{i}", "max": 3,
                     "evidence": [{"source": BRIEF, "quote": "Persuasion attempts: 2"},
                                  {"source": BRIEF, "quote": "A flat refusal or a non-answer uses one persuasion attempt."}]},
        "refusal": "reply_{i}_{a}",
    },
}

Path(f"out/{SLOT}.body.json").write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
Path(f"out/{SLOT}.closing.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
print("written")
