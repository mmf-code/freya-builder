"""Generate out/pl-g3-limits-raw.body.json and .closing.json from the brief's rules."""
import json
from pathlib import Path

SLOT = "pl-g3-limits-raw"
BRIEF = "briefs/pl-g3-limits-raw.md"
API = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
OUT = Path(__file__).parent


def leaf(typ, default, desc=None, enum=None):
    d = {"type": typ, "default": default}
    if desc:
        d["description"] = desc
    if enum:
        d["enum"] = enum
    return d


def api_tool(name, desc, body, required, retries=0, post=None):
    t = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": retries},
         "function": {"name": name, "handler": "__function__:api_call", "description": desc,
                      "parameters": {"type": "object", "properties": {
                          "url": {"type": "string", "default": API + name},
                          "method": {"type": "string", "default": "POST"},
                          "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                          "body": {"type": "object", "properties": body, "required": required}}}}}
    if post:
        t["post_process_code"] = post
    return t


def cond(*checks):
    return {"logic": "or", "conditions": [checks[0] if len(checks) == 1 else {"logic": "and", "conditions": list(checks)}]}


def anyof(*checks):
    return {"logic": "or", "conditions": list(checks)}


def v(name, op, operand=None):
    c = {"variable": name, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return c


def tt(target, desc):
    """Tool-call transition chosen by the dialogue model."""
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def code_node(name, code, nxt, transitions=None):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                                              "parameters": {"type": "object", "properties": {
                                                                  "code": {"type": "string", "default": code},
                                                                  "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": (transitions or []) + [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}]}


def api_node(name, tool, nxt, transitions, mapping=None):
    return {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [tool],
            "response_mapping": mapping or [], "suppress_tool_results": True,
            "transitions": transitions + [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}]}


# ------------------------------------------------------------------ code (no double braces anywhere)

DATES = r'''
import datetime, json, re, math
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
hol = set(datetime.date.fromisoformat(h) for h in HOL)
raw = str(vars.get('now') or '').strip().replace(' ', 'T')
try:
    nowdt = datetime.datetime.fromisoformat(raw[:16])
except Exception:
    nowdt = datetime.datetime.fromisoformat(raw[:10] + 'T00:00')
today = nowdt.date()
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
def isbd(d):
    return d.weekday() < 5 and d not in hol
def spoken(d):
    return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
def nth_bd(n):
    d = today
    k = 0
    while k < n:
        d = d + datetime.timedelta(days=1)
        if isbd(d):
            k += 1
    return d
monday = today - datetime.timedelta(days=today.weekday())
next_monday = monday + datetime.timedelta(days=7)
def week_lines(start, label):
    out = []
    for j in range(7):
        d = start + datetime.timedelta(days=j)
        kind = 'business day' if isbd(d) else ('Freya Bank holiday' if d in hol else 'weekend')
        out.append('- ' + label + ' ' + DAYS[j] + ': ' + spoken(d) + ', ' + kind)
    return out
def last_bd_of_week(start):
    best = None
    for j in range(5):
        d = start + datetime.timedelta(days=j)
        if isbd(d):
            best = d
    return best
'''

SETUP = DATES + r'''
try:
    lines = ['Today is ' + spoken(today) + ', time now ' + nowdt.strftime('%H:%M') + '. Today is ' + ('a business day.' if isbd(today) else 'not a business day.')]
    lines.append('Freya Bank holidays: ' + ', '.join(HOL) + '. Business days are Monday to Friday except these holidays.')
    lines += week_lines(monday, 'this')
    lines += week_lines(next_monday, 'next')
    vars['date_facts'] = '\n'.join(lines)
    nbd = nth_bd(1)
    cb = []
    t = nowdt + datetime.timedelta(minutes=1)
    if nowdt.strftime('%H:%M') < '19:00':
        start = t.strftime('%H:%M') if t.strftime('%H:%M') > '10:00' else '10:00'
        cb.append('today, ' + spoken(today) + ', from ' + start + ' to 19:00')
    cb.append('the next business day, ' + spoken(nbd) + ', from 10:00 to 19:00')
    vars['callback_window'] = ' or '.join(cb) + ' (both ends included).'
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Date facts unavailable.'
    vars['callback_window'] = 'today or the next business day, from 10:00 to 19:00, later than now.'
    vars['setup_state'] = 'error'
'''

PREPARE = DATES + r'''
def money(x):
    return '{:,.2f}'.format(x) + ' euros'
try:
    prods = None
    p = vars.get('products')
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            p = None
    if isinstance(p, list) and p:
        prods = p
    if prods is None:
        items = dict()
        for k, val in list(vars.items()):
            m = re.search(r'products\.(\d+)\.(\w+)$', str(k))
            if m:
                items.setdefault(int(m.group(1)), dict())[m.group(2)] = val
        prods = [items[k] for k in sorted(items)]
    prods = [x if isinstance(x, dict) else json.loads(x) for x in prods]
    pr = prods[0]
    ptype = str(pr.get('type') or '')
    past_due = round(float(pr.get('past_due')), 2)
    days_late = int(float(pr.get('days_late')))
    if ptype == 'credit_card':
        words = 'credit card ending ' + str(pr.get('card_last4') or '')
        floor = float(pr.get('minimum_payment') if pr.get('minimum_payment') is not None else past_due)
        floor_why = 'the minimum payment of the card'
    elif ptype == 'car_loan':
        words = 'car loan'
        floor = float(math.floor(past_due / 2.0))
        floor_why = 'half of the past-due amount, rounded down to whole euros (car loan rule)'
    else:
        words = 'personal loan'
        floor = float(pr.get('instalment_amount') if pr.get('instalment_amount') is not None else past_due)
        floor_why = 'the monthly instalment of the loan'
    cap = 2000.00
    ask = min(past_due, cap)
    floor = round(min(floor, ask), 2)
    capped = past_due > cap
    if days_late <= 7:
        band, deadline, allowed = 'early', nth_bd(12), 2
    else:
        band, deadline, allowed = 'late', nth_bd(7), 3
    valid = []
    d = today
    while d <= deadline:
        if isbd(d):
            valid.append(d)
        d = d + datetime.timedelta(days=1)
    eow = last_bd_of_week(monday)
    if eow is None or eow <= today:
        eow = last_bd_of_week(next_monday)
    if eow is None or eow > deadline:
        eow = deadline
    vars['product_count'] = 1
    vars['product_id_1'] = str(pr.get('product_id') or '')
    vars['allowed_1'] = allowed
    vars['product_words'] = words
    f = []
    f.append('Product: ' + words + '. Product id for create_promise: ' + str(pr.get('product_id')) + '.')
    f.append('Past-due amount: ' + money(past_due) + '. Days late: ' + str(days_late) + '.')
    if capped:
        f.append('One promise may not be above 2,000.00 euros. The past-due amount is higher, so the full amount you ask for is ' + money(ask) + ', and you must say that the rest stays overdue.')
    else:
        f.append('Full amount to ask for: ' + money(ask) + ' (the whole past-due amount).')
    f.append('Floor (lowest amount you may record): ' + money(floor) + ', which is ' + floor_why + '.')
    f.append('Amounts you may record: from ' + money(floor) + ' up to ' + money(ask) + ', both included. Never record more than ' + money(ask) + ' or less than ' + money(floor) + '.')
    f.append('Deadline (latest promise date): ' + spoken(deadline) + '.')
    f.append('Valid promise dates, the only dates you may record (business days from today to the deadline): ' + '; '.join(spoken(x) for x in valid) + '.')
    f.append('Persuasion offer 1 date (last business day of this week, or of next week if today is that day): ' + spoken(eow) + '.')
    vars['account_facts'] = '\n'.join(f)
    today_word = 'today, ' + spoken(today) if isbd(today) else 'on the next business day, ' + spoken(nth_bd(1))
    s1 = ('State the debt now, in two short sentences: say that you are calling from the collections team about a late payment on the customer\'s ' + words
          + ', that the past-due amount is ' + money(past_due) + ' and that it is ' + str(days_late) + ' days late.')
    if capped:
        s1 += ' Then say that you can take a promise for ' + money(ask) + ' now and that the rest stays overdue.'
    s1 += ' Then ask exactly: "Can you make this payment today?" (for ' + money(ask) + ', ' + today_word + ').'
    s2 = ('The customer refused your last offer. This is persuasion attempt 1. Acknowledge briefly and propose paying '
          + money(ask) + ' on ' + spoken(eow) + '. If the customer already said earlier that the full amount is too much, propose the floor '
          + money(floor) + ' on that date instead. Ask if they can do that.')
    s3 = ('The customer refused again. This is persuasion attempt 2, the last one. Acknowledge briefly and propose paying the floor amount '
          + money(floor) + ' on the deadline, ' + spoken(deadline) + '. Ask if they can do that.')
    vars['stage_1_1'] = s1
    vars['stage_1_2'] = s2
    vars['stage_1_3'] = s3
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_state'] = 'error'
    vars['account_facts'] = 'Account facts unavailable.'
'''

assert "{{" not in SETUP + PREPARE and "}}" not in SETUP + PREPARE

VERIFY_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            def t(x):
                return str(x).lower() == 'true'
            if t(d.get('all_verified')):
                msg = 'Both answers are verified.'
            elif d.get('hint') == 'day_month_swapped':
                msg = 'Day and month look swapped. Ask the customer to say the month of birth as a word, then call verify_identity again. This does not count as a wrong answer.'
            elif str(d.get('ok')).lower() == 'false' and d.get('verified') is None:
                msg = 'The answer could not be read and was not counted. Ask for the same answer again. Send a date of birth as YYYY-MM-DD.'
            elif t(d.get('verified')):
                msg = 'Correct. Now ask for the last four digits of the phone number on file.'
            elif str(d.get('wrong_answers_left')) == '0':
                msg = 'No attempts are left. Do not ask again.'
            else:
                msg = 'That answer did not match. Tell the customer it did not match and ask the same question again.'
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
            if str(d.get('ok')).lower() == 'true':
                d['what_to_do_next'] = 'The promise is recorded.'
            else:
                d['what_to_do_next'] = 'The promise was NOT recorded. Never say it is recorded. Tell the customer it did not go through and call create_promise once more with the same values now.'
except Exception:
    pass
'''

# ------------------------------------------------------------------ tools

def t_verify():
    return api_tool("verify_identity",
                    "Check one security answer. CALL it every time the customer gives an answer to a security question, one answer per call.",
                    {"customer_id": leaf("string", "{{customer_id}}"),
                     "field": leaf("string", "{{field}}", "Which question was answered. One of: date_of_birth, phone_last4.", ["date_of_birth", "phone_last4"]),
                     "answer": leaf("string", "{{answer}}", "date_of_birth as YYYY-MM-DD (numbers only: read as day, then month, then year); phone_last4 as exactly four digits.")},
                    ["field", "answer"], post=VERIFY_POST)


def t_promise():
    return api_tool("create_promise",
                    "Record the payment promise. CALL it only after you read back the product, amount and date and the customer said a clear yes to 'Do you confirm?'.",
                    {"customer_id": leaf("string", "{{customer_id}}"),
                     "product_id": leaf("string", "{{product_id_1}}"),
                     "amount": leaf("number", "{{amount}}", "The confirmed amount in euros, a number such as 250.00. Within the allowed range."),
                     "date": leaf("string", "{{date}}", "The confirmed promise date as YYYY-MM-DD. Must be one of the valid promise dates.")},
                    ["amount", "date"], post=PROMISE_POST)


def t_callback():
    return api_tool("schedule_callback",
                    "Book a callback for the customer. CALL it as soon as the person gives a day and time inside the allowed callback window.",
                    {"customer_id": leaf("string", "{{customer_id}}"),
                     "date": leaf("string", "{{date}}", "Callback date as YYYY-MM-DD."),
                     "time": leaf("string", "{{time}}", "Callback time as HH:MM, 24 hour, from 10:00 to 19:00.")},
                    ["date", "time"])


def t_transfer(queue):
    return api_tool("transfer_to_agent", "Hand the call to a person.",
                    {"customer_id": leaf("string", "{{customer_id}}"), "queue": leaf("string", queue, None, [queue])}, ["queue"])


# ------------------------------------------------------------------ prompts

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call to {{title}} {{last_name}} ({{first_name}} {{last_name}}). Speak English.
Style: keep every turn to one to three short, plain sentences. No technical words. One question at a time.
Always:
- If asked whether you are a robot or an AI, say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam, say they can verify this call by phoning Freya Bank's customer service number, then continue.
- If asked something the information you have does not answer, say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any term you were not given.
- Never say something is recorded or booked unless the tool result says ok: true.
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- Do not say goodbye unless your instructions say so; closing words are said for you when the call ends."""

PRE_VERIFY = ("Identity is not verified yet. Do not say why you are calling. Never say the words collections, debt, payment, or name any product. "
              "If asked what the call is about, say you can explain once you have confirmed you are speaking with the right person.")

GREET1_EXTRACT = {
    "name": "party_1", "type": "string", "min_confidence": 0.5,
    "enum_values": ["confirmed", "someone_else", "wrong_number", "deceased", "declined", "human", "unclear"],
    "description": ("Classify ONLY the latest message of the person on the line, answering 'Am I speaking with {{title}} {{last_name}}?'. "
                    "confirmed: they say yes, that's me, speaking, or say the customer's own name as theirs. "
                    "someone_else: they are another person (relative, partner, colleague) and the customer is not available or not them. "
                    "wrong_number: the number does not belong to the customer / they do not know this person. "
                    "deceased: they say the customer has died. "
                    "declined: they say they do not want to talk. "
                    "human: they ask to speak to a person / human agent. "
                    "unclear: anything else, such as hello, go ahead, who is this, a question, or no answer.")}


def greet2_extract():
    e = dict(GREET1_EXTRACT)
    e["name"] = "party_2"
    return e


def party_routes(var, unclear_target, declined_target, human_target):
    r = [
        {"target_node": "identity", "description": "The customer confirmed who they are", "condition": cond(v(var, "equals", "confirmed"))},
        {"target_node": "close:not_reached/deceased", "description": "The customer has died", "condition": cond(v(var, "equals", "deceased"))},
        {"target_node": "close:not_reached/wrong_number", "description": "Wrong number", "condition": cond(v(var, "equals", "wrong_number"))},
        {"target_node": "third_party", "description": "Someone else answered", "condition": cond(v(var, "equals", "someone_else"))},
        {"target_node": declined_target, "description": "Does not want to talk", "condition": cond(v(var, "equals", "declined"))},
        {"target_node": human_target, "description": "Asks for a human", "condition": cond(v(var, "equals", "human"))},
        {"target_node": unclear_target, "description": "Still unclear", "condition": cond(v(var, "equals", "unclear"))},
    ]
    return r


HUMAN_DESC = ("The customer asks for a human again AFTER you already asked once whether you can help them first. "
              "Call this without saying anything else.")

NEG_RULES = """Account facts:
{{account_facts}}

Calendar:
{{date_facts}}

Current stage: {{stage_{i}_{a}}}

Tool rule: create_promise is your only tool. Call it only after a clear yes to "Do you confirm?". Product, amount and date must follow the rules below.

Amounts:
- You propose every amount. Never ask how much they can pay.
- If the customer says the full amount is too much, offer the floor once, and say the rest stays overdue.
- If the customer proposes an amount from the floor up to the full amount to ask for (both included), accept it. Below the floor: say it cannot be recorded and offer the floor once. Never record above the full amount to ask for.
Dates:
- A promise date must be one of the valid promise dates listed in the account facts. Use the calendar to turn words like "Friday", "this Friday" (this week) or "next Friday" (following calendar week) into a date.
- If the customer names a weekend day or a holiday that is not after the deadline, offer the next valid business day after it.
- If the customer names a date after the deadline, say the latest date you can record is the deadline and offer the deadline.
- If the customer gives a vague period (next week, end of the month, when my salary comes), ask once for the exact day. If they still give none, propose the deadline.
- A date or an amount the customer proposes is never a refusal. Work with it under these rules.
Confirming:
- When amount and date are agreed, read back the product, the amount and the date and ask "Do you confirm?". If they change the amount or date, check the new value and read back again.
- After a clear yes, call create_promise with the exact amount (number) and date (YYYY-MM-DD).
- If create_promise does not return ok: true, say it did not go through and call it once more right away with the same values. Never say the promise is recorded unless the result says ok: true.
- One promise per product. A recorded promise cannot be changed in this call; if asked, say they can change it in the mobile app.
Other situations:
- If the customer asks for a human the first time, ask once whether you can help them first.
- Never repeat an offer the customer already refused."""

REFUSAL_EXTRACT = {
    "name": "refused_{i}_{a}", "type": "string", "enum_values": ["yes", "no"], "min_confidence": 0.6,
    "description": ("Judge ONLY the customer's latest message against the agent's latest offer. "
                    "yes: a flat refusal or a non-answer to the offer: 'no', 'I can't', 'not today', 'no I can't do that' with no date and no amount; "
                    "or a refusal of the floor amount the agent offered after 'too much'; or a refusal of the deadline date the agent offered. "
                    "no: anything else, including: they accept; they propose any date or amount (even a wrong one); they say the full amount is too much "
                    "(without refusing the floor); they give a vague time like next week or salary day; they ask a question; they mention illness, "
                    "a death in the family or job loss; they say they already paid; they dispute the debt; they ask for a payment plan or a person; "
                    "they confirm or change a read-back.")}

HARDSHIP_DESC = ("The customer mentions illness, a death in the family or job loss. Call this right away without persuading and without "
                 "saying anything else.")
PAID_DESC = ("The customer says they already paid this past-due amount. Not a claim that the product was closed or paid off in the past. "
             "Call this without saying anything else.")
DISPUTE_DESC = ("The customer says this debt is not theirs, they never had this product, or the product was closed or paid off in the past. "
                "Do not argue. Call this without saying anything else.")
RESTRUCT_DESC = ("The customer asks for a new payment plan, a restructuring or lower instalments. Do not describe any plan. "
                 "Call this without saying anything else.")
NOTALK_DESC = ("The customer has now said for the second time that they do not want to talk. Call this without saying anything else.")

nodes = {}

nodes["setup"] = code_node("setup", SETUP, "greet")

nodes["greet"] = {
    "name": "greet", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": True,
    "task_message": PRE_VERIFY + " No tool call is allowed in this turn.",
    "extraction_schema": [GREET1_EXTRACT],
    "transitions": party_routes("party_1", "greet_again", "greet_again", "greet_again")[:4]
    + [{"target_node": "greet_again", "description": "not confirmed yet", "condition": {"operator": "always"}}],
}

nodes["greet_again"] = {
    "name": "greet_again", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "task_message": (PRE_VERIFY + "\nThe person on the line has not confirmed who they are. If they asked a question, answer it first in one short sentence "
                     "(you are Freya Bank's digital assistant; for scam worries they can phone Freya Bank's customer service number). "
                     "If they asked for a person, ask once whether you can help them first. If they said they do not want to talk, say it will only take a moment. "
                     "Then ask again: \"Am I speaking with {{title}} {{last_name}}?\". No tool call is allowed in this turn."),
    "extraction_schema": [greet2_extract()],
    "max_node_turns": 2, "max_turn_transition": "close:not_reached/unclear",
    "transitions": party_routes("party_2", "close:not_reached/unclear", "close:not_verified/declined", "transfer_human"),
}

nodes["third_party"] = {
    "name": "third_party", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "task_message": ("You are speaking with someone other than {{title}} {{last_name}}. Say nothing about why you are calling: no account, debt, payment or product, "
                     "even if they offer to pay or ask. They may not answer security questions. Ask when {{title}} {{last_name}} can be reached.\n"
                     "Calendar:\n{{date_facts}}\n"
                     "Allowed callback times: {{callback_window}}\n"
                     "- When the person gives a day and time inside the allowed window, call schedule_callback with the date (YYYY-MM-DD) and time (HH:MM). "
                     "If they give only a day, ask for a time; if only a time, assume today if it fits, else ask.\n"
                     "- If the day or time is outside the window, ask once for another time inside it. Tell them the allowed window.\n"
                     "- After a tool result with ok: true you may say the callback is booked. If it fails, say it could not be booked and try once more.\n"
                     "Only schedule_callback may be called."),
    "tools": [t_callback()],
    "extraction_schema": [{"name": "tp_status", "type": "string", "enum_values": ["deceased", "wrong_number", "other"], "min_confidence": 0.6,
                           "description": "From the latest message only. deceased: says the customer has died. wrong_number: says this number does not belong to the customer. other: anything else."}],
    "max_node_turns": 8, "max_turn_transition": "close:not_reached/no_callback",
    "transitions": [
        {"target_node": "close:not_reached/callback", "description": "callback booked", "condition": cond(v("schedule_callback_success_count", "greater_than", 0))},
        {"target_node": "close:not_reached/no_callback_error", "description": "callback booking failed twice", "condition": cond(v("schedule_callback_failure_count", "greater_than", 1))},
        {"target_node": "close:not_reached/deceased", "description": "customer died", "condition": cond(v("tp_status", "equals", "deceased"))},
        {"target_node": "close:not_reached/wrong_number", "description": "wrong number", "condition": cond(v("tp_status", "equals", "wrong_number"))},
        tt("close:not_reached/no_callback",
           "The person gave a second day or time that is still outside the allowed callback window after you asked once for another time, or refuses to give any time. "
           "Call this without saying anything else."),
    ],
}

nodes["identity"] = {
    "name": "identity", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you. For your security I need to ask two quick questions. What is your date of birth?"},
    "on_enter_first_entry_only": True,
    "task_message": (PRE_VERIFY + "\nAsk two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file.\n"
                     "- Call verify_identity for every answer: field date_of_birth with the date as YYYY-MM-DD, whatever way it was said. "
                     "A date said only as numbers is day, then month, then year. Field phone_last4 with four digits.\n"
                     "- Follow what_to_do_next in the tool result. A wrong answer may be asked again.\n"
                     "- If the result has hint day_month_swapped, ask the customer to say the month as a word, then check again.\n"
                     "- If the customer does not want to answer, or asks what the call is about instead of answering, explain once that these questions protect their account, and ask again.\n"
                     "- If they ask for a person the first time, ask once whether you can help them first.\n"
                     "Only verify_identity may be called."),
    "tools": [t_verify()],
    "max_node_turns": 14, "max_turn_transition": "close:not_verified/declined",
    "transitions": [
        {"target_node": "fetch_account", "description": "both answers verified",
         "condition": anyof(v("verify_identity_response.data.all_verified", "equals", "true"), v("verify_identity_response.data.all_verified", "equals", "True"))},
        {"target_node": "close:not_verified/failed", "description": "no wrong answers left",
         "condition": cond(v("verify_identity_response.data.wrong_answers_left", "equals", "0"))},
        tt("close:not_verified/declined",
           "The customer refuses to answer a security question, or asks what the call is about instead of answering, for the SECOND time, after you already explained "
           "once that the questions protect their account; or says for the second time that they do not want to talk. Call this without saying anything else."),
        tt("transfer_human", HUMAN_DESC),
    ],
}

nodes["fetch_account"] = api_node("fetch_account", api_tool("get_account", "Get the late products.", {"customer_id": leaf("string", "{{customer_id}}")}, [], retries=2),
                                  "prepare_account", [], mapping=[{"path": "data.products", "variable": "products"}])

nodes["prepare_account"] = code_node("prepare_account", PREPARE, "close:no_promise/service_error_account",
                                     [{"target_node": "item:first", "description": "account facts ready", "condition": cond(v("account_state", "equals", "ok"))}])

nodes["negotiate"] = {
    "name": "negotiate", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "task_message": "The customer {{title}} {{last_name}} is verified. Follow the current stage in your first message in this step.\n\n" + NEG_RULES,
    "tools": [t_promise()],
    "extraction_schema": [REFUSAL_EXTRACT],
    "max_node_turns": 14, "max_turn_transition": "close:no_promise/refused",
    "transitions": [
        {"target_node": "close:promise", "description": "promise recorded", "condition": cond(v("create_promise_success_count", "greater_than", 0))},
        {"target_node": "close:no_promise/service_error", "description": "promise failed twice", "condition": cond(v("create_promise_failure_count", "greater_than", 1))},
        tt("hardship", HARDSHIP_DESC),
        tt("close:paid", PAID_DESC),
        tt("close:no_promise/dispute", DISPUTE_DESC),
        tt("transfer_restructuring", RESTRUCT_DESC),
        tt("transfer_human", HUMAN_DESC),
        tt("close:no_promise/refused_talk", NOTALK_DESC),
    ],
}

nodes["hardship"] = {
    "name": "hardship", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "task_message": ("The customer mentioned illness, a death in the family or job loss. In your first message: say one short sentence of sympathy and offer to connect "
                     "them with the customer support team. Make no persuasion attempt and do not ask for a payment.\n"
                     "If the customer themselves names a date or an amount, you may record a promise under the rules below.\n\n" + NEG_RULES.replace("Current stage: {{stage_{i}_{a}}}\n\n", "")),
    "tools": [t_promise()],
    "extraction_schema": [{"name": "support_answer", "type": "string", "enum_values": ["accept", "decline", "other"], "min_confidence": 0.6,
                           "description": ("Latest customer message only, about the offer to connect them with the customer support team. accept: yes, connect me. "
                                           "decline: no thanks, and they name no payment date or amount. other: anything else, including naming a date or amount.")}],
    "max_node_turns": 10, "max_turn_transition": "close:no_promise/hardship",
    "transitions": [
        {"target_node": "close:promise", "description": "promise recorded", "condition": cond(v("create_promise_success_count", "greater_than", 0))},
        {"target_node": "close:no_promise/service_error", "description": "promise failed twice", "condition": cond(v("create_promise_failure_count", "greater_than", 1))},
        {"target_node": "transfer_support", "description": "accepts support", "condition": cond(v("support_answer", "equals", "accept"))},
        {"target_node": "close:no_promise/hardship", "description": "declines support", "condition": cond(v("support_answer", "equals", "decline"))},
        tt("close:paid", PAID_DESC),
        tt("close:no_promise/dispute", DISPUTE_DESC),
        tt("transfer_restructuring", RESTRUCT_DESC),
        tt("transfer_human", HUMAN_DESC),
    ],
}

for q, cid in (("support", "transferred/support"), ("restructuring", "transferred/restructuring"), ("general", "transferred/human")):
    name = {"support": "transfer_support", "restructuring": "transfer_restructuring", "general": "transfer_human"}[q]
    nodes[name] = api_node(name, t_transfer(q), "close:" + cid, [])

body = {"initial_node": "setup", "system_prompt": SYSTEM, "nodes": nodes, "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}

# ------------------------------------------------------------------ closing plan

Q_PROMISE = "Outcome: promise; Reason: none; When: at least one promise was recorded"
Q_PAID = "Outcome: paid; Reason: none; When: rule 39"
Q_TR = "Outcome: transferred; Reason: restructuring`, `human`, `support; When: rules 41, 42, 32"
Q_NP = "Outcome: no_promise; Reason: refused`, `hardship`, `dispute`, `service_error; When: rules 31 and 45, 32, 40, 37"
Q_NV = "Outcome: not_verified; Reason: failed`, `declined; When: rules 14, 15"
Q_NR = "Outcome: not_reached; Reason: callback`, `no_callback`, `wrong_number`, `deceased`, `unclear; When: rules 6, 7, 8, 9, 3"


def ev(q):
    return [{"source": BRIEF, "quote": q}]


BYE = "Thank you for your time. Goodbye."
closings = {
    "promise": {"set": {"outcome": "promise"}, "evidence": ev(Q_PROMISE),
                "say": "Your payment promise is recorded. You will receive a text message confirming this promise. Thank you, {{title}} {{last_name}}. Goodbye."},
    "paid": {"set": {"outcome": "paid"}, "evidence": ev(Q_PAID),
             "say": "Thank you for letting me know. Payments can take one business day to appear, so I will not take a promise today. " + BYE},
    "transferred/restructuring": {"set": {"outcome": "transferred", "reason": "restructuring"}, "evidence": ev(Q_TR),
                                  "say": "Thank you. I am passing you to a colleague in our restructuring team now. Goodbye."},
    "transferred/human": {"set": {"outcome": "transferred", "reason": "human"}, "evidence": ev(Q_TR),
                          "say": "Thank you. I am passing you to a colleague now. Goodbye."},
    "transferred/support": {"set": {"outcome": "transferred", "reason": "support"}, "evidence": ev(Q_TR),
                            "say": "Thank you. I am passing you to our customer support team now. Take care. Goodbye."},
    "no_promise/refused": {"set": {"outcome": "no_promise", "reason": "refused"}, "evidence": ev(Q_NP),
                           "say": "I understand. " + BYE},
    "no_promise/refused_talk": {"set": {"outcome": "no_promise", "reason": "refused"}, "evidence": ev(Q_NP),
                                "say": "I understand. " + BYE},
    "no_promise/hardship": {"set": {"outcome": "no_promise", "reason": "hardship"}, "evidence": ev(Q_NP),
                            "say": "I understand. Take care. " + BYE},
    "no_promise/dispute": {"set": {"outcome": "no_promise", "reason": "dispute"}, "evidence": ev(Q_NP),
                           "say": "I understand. I will not take a payment promise today. " + BYE},
    "no_promise/service_error": {"set": {"outcome": "no_promise", "reason": "service_error"}, "evidence": ev(Q_NP),
                                 "say": "I am sorry, I could not record your promise because of a system problem. It is not recorded. " + BYE},
    "no_promise/service_error_account": {"set": {"outcome": "no_promise", "reason": "service_error"}, "evidence": ev(Q_NP),
                                         "say": "I am sorry, I cannot reach your account details right now because of a system problem. " + BYE},
    "not_verified/failed": {"set": {"outcome": "not_verified", "reason": "failed"}, "evidence": ev(Q_NV),
                            "say": "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch. " + BYE},
    "not_verified/declined": {"set": {"outcome": "not_verified", "reason": "declined"}, "evidence": ev(Q_NV),
                              "say": "I understand. Without the security questions I cannot continue. " + BYE},
    "not_reached/callback": {"set": {"outcome": "not_reached", "reason": "callback"}, "evidence": ev(Q_NR),
                             "say": "Thank you, we will call back then. Goodbye."},
    "not_reached/no_callback": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "evidence": ev(Q_NR),
                                "say": "I understand, I will not book a callback. " + BYE},
    "not_reached/no_callback_error": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "evidence": ev(Q_NR),
                                      "say": "I am sorry, I could not book the callback because of a system problem. " + BYE},
    "not_reached/wrong_number": {"set": {"outcome": "not_reached", "reason": "wrong_number"}, "evidence": ev(Q_NR),
                                 "say": "I am sorry for the trouble. " + BYE},
    "not_reached/deceased": {"set": {"outcome": "not_reached", "reason": "deceased"}, "evidence": ev(Q_NR),
                             "say": "I am sorry for your loss. Thank you, goodbye."},
    "not_reached/unclear": {"set": {"outcome": "not_reached", "reason": "unclear"}, "evidence": ev(Q_NR),
                            "say": "I am sorry, I could not confirm who I am speaking with. " + BYE},
}

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]},
    "fields": {"customer_id": "{{customer_id}}"},
    "closings": closings,
    "precedence": [
        {"closing": "promise", "when": [v("create_promise_success_count", "greater_than", 0)],
         "keep": ["transferred/restructuring", "transferred/human", "transferred/support"],
         "evidence": ev(Q_PROMISE) + ev("If a transfer follows a recorded promise, close as `transferred` with that transfer's reason.")},
        {"closing": "not_verified/failed", "when": [v("verify_identity_response.data.wrong_answers_left", "equals", "0")], "keep": [],
         "evidence": ev("After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`.")},
    ],
    "ladder": {"template": "negotiate", "done": "close:no_promise/refused",
               "items": {"count": "product_count", "max": 1, "evidence": ev("Freya Bank calls customers who are 1 to 45 days late on one product.")},
               "attempts": {"allowed": "allowed_{i}", "max": 3, "evidence": ev("days_late: 1 to 7; Band: early; Deadline: the 12th business day after today; Persuasion attempts: 2")
                            + ev("days_late: 8 to 45; Band: late; Deadline: the 7th business day after today; Persuasion attempts: 3")},
               "refusal": "refused_{i}_{a}"},
}

(OUT / f"{SLOT}.body.json").write_text(json.dumps(body, indent=1) + "\n")
(OUT / f"{SLOT}.closing.json").write_text(json.dumps(plan, indent=1) + "\n")
print("written")
