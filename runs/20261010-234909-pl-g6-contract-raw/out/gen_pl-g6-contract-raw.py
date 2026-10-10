"""Generate out/pl-g6-contract-raw.workflow.json from briefs/pl-g6-contract-raw.md and tools/openapi.json."""
import json
from pathlib import Path

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
SLOT = "pl-g6-contract-raw"

# ----------------------------------------------------------------- helpers

def body_field(typ, default, description="", enum=None):
    spec = {"type": typ, "default": default}
    if description:
        spec["description"] = description
    if enum:
        spec["enum"] = enum
    return spec


def api_tool(name, path, description, fields, required, max_retries=0, mapping=None):
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
                    "url": {"type": "string", "default": f"{BASE}/{path}"},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": fields, "required": required},
                },
            },
        },
    }
    if mapping:
        tool["response_mapping"] = mapping
    return tool


def cond_or(*conds):
    return {"logic": "or", "conditions": list(conds)}


def c(var, op, operand=None):
    d = {"variable": var, "operator": op}
    if operand is not None:
        d["operand"] = operand
    return d


def is_true(*vars_):
    out = []
    for v in vars_:
        out += [c(v, "equals", "true"), c(v, "equals", "True")]
    return out


def tool_transition(target, description):
    return {"target_node": target, "description": description, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": description}}


def code_node(name, code, target):
    return {
        "name": name,
        "node_type": "code",
        "passthrough": True,
        "passthrough_default_transition": target,
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
        "transitions": [{"target_node": target, "description": "always", "condition": {"operator": "always"}}],
    }


# ----------------------------------------------------------------- code (no double braces anywhere)

CODE_COMMON = r'''
import datetime, json, re
HOL = set(['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'])
NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY = datetime.timedelta(days=1)

def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL

def label(d):
    return NAMES[d.weekday()] + ' ' + d.isoformat()

def nth_bd(start, n):
    d = start
    k = 0
    while k < n:
        d = d + DAY
        if isbd(d):
            k += 1
    return d

def last_bd_of_week(mon):
    d = mon + datetime.timedelta(days=4)
    while d >= mon and not isbd(d):
        d = d - DAY
    if d >= mon:
        return d
    return None

def money(x):
    x = round(float(x), 2)
    if abs(x - round(x)) < 0.005:
        return str(int(round(x)))
    return '%.2f' % x

def tag(d, today):
    t = []
    if d < today:
        t.append('already past')
    if d == today:
        t.append('today')
    if d.isoformat() in HOL:
        t.append('bank holiday, not a business day')
    elif d.weekday() >= 5:
        t.append('weekend, not a business day')
    if t:
        return ' (' + ', '.join(t) + ')'
    return ''

raw = str(vars.get('now') or '').strip().replace(' ', 'T')
try:
    now = datetime.datetime.fromisoformat(raw[:16])
except Exception:
    try:
        now = datetime.datetime.fromisoformat(raw[:10] + 'T00:00')
    except Exception:
        now = datetime.datetime(2026, 10, 14, 11, 0)
today = now.date()
'''

CODE_DATES = CODE_COMMON + r'''
try:
    vars['today_text'] = label(today) + (' (a business day)' if isbd(today) else ' (not a business day)')
    vars['now_time'] = now.strftime('%H:%M')
    nbd = nth_bd(today, 1)
    vars['next_bd_text'] = label(nbd)
    lines = []
    start = now + datetime.timedelta(minutes=1)
    t10 = datetime.datetime.combine(today, datetime.time(10, 0))
    t19 = datetime.datetime.combine(today, datetime.time(19, 0))
    if start < t10:
        start = t10
    if start <= t19:
        lines.append('Today, ' + label(today) + ': any time from ' + start.strftime('%H:%M') + ' to 19:00.')
    else:
        lines.append('Today, ' + label(today) + ': nothing is left (it is after 19:00).')
    lines.append('Next business day, ' + label(nbd) + ': any time from 10:00 to 19:00.')
    lines.append('Every other day, and every time outside these windows, is outside the allowed window.')
    vars['callback_window'] = '\n'.join(lines)
    mon = today - datetime.timedelta(days=today.weekday())
    wk = ['tomorrow = ' + label(today + DAY) + tag(today + DAY, today)]
    for i in range(7):
        d = mon + datetime.timedelta(days=i)
        wk.append('this ' + NAMES[i] + ' = ' + d.isoformat() + tag(d, today))
    for i in range(7):
        d = mon + datetime.timedelta(days=7 + i)
        wk.append('next ' + NAMES[i] + ' = ' + d.isoformat() + tag(d, today))
    vars['week_table'] = '\n'.join(wk)
    a1 = last_bd_of_week(mon)
    if a1 is None or a1 <= today:
        a1 = last_bd_of_week(mon + datetime.timedelta(days=7))
        if a1 is None:
            a1 = last_bd_of_week(mon + datetime.timedelta(days=14))
    vars['attempt1_text'] = label(a1)
    vars['account_state'] = 'not_loaded'
except Exception as e:
    vars['today_text'] = raw
    vars['now_time'] = raw[11:16]
    vars['next_bd_text'] = 'unknown'
    vars['callback_window'] = 'unknown'
    vars['week_table'] = 'unknown'
    vars['attempt1_text'] = 'unknown'
    vars['account_state'] = 'not_loaded'
'''

CODE_ACCOUNT = CODE_COMMON + r'''
def load_products():
    for key in ('products', 'load_account_response.data.products', 'get_account_response.data.products'):
        v = vars.get(key)
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                try:
                    v = json.loads(v.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
                except Exception:
                    v = None
        if isinstance(v, list) and v:
            return v
    found = dict()
    pat = re.compile(r'products(?:\.|\[)(\d+)\]?\.([A-Za-z_0-9]+)$')
    for k in list(vars.keys()):
        m = pat.search(str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars[k]
    return [found[i] for i in sorted(found)]

try:
    prods = [p for p in load_products() if isinstance(p, dict) and p.get('past_due') is not None]
    p = prods[0]
    ptype = str(p.get('type') or '')
    past_due = float(p.get('past_due'))
    days_late = int(float(p.get('days_late')))
    if ptype == 'credit_card':
        words = 'credit card ending ' + str(p.get('card_last4') or '')
        floor = p.get('minimum_payment')
        floor_label = 'minimum payment'
    elif ptype == 'personal_loan':
        words = 'personal loan'
        floor = p.get('instalment_amount')
        floor_label = 'instalment amount'
    elif ptype == 'car_loan':
        words = 'car loan'
        floor = p.get('instalment_amount')
        floor_label = 'instalment amount'
    else:
        words = ptype.replace('_', ' ')
        floor = p.get('minimum_payment') or p.get('instalment_amount')
        floor_label = 'minimum amount'
    floor = float(floor) if floor is not None else past_due
    if days_late <= 7:
        band = 'early (1 to 7 days late)'
        deadline = nth_bd(today, 12)
        attempts = 1
    else:
        band = 'late (8 to 45 days late)'
        deadline = nth_bd(today, 7)
        attempts = 2
    valid = []
    d = today
    while d <= deadline:
        if isbd(d):
            valid.append(label(d))
        d = d + DAY
    vars['product_id'] = str(p.get('product_id') or '')
    vars['product_words'] = words
    vars['past_due_text'] = money(past_due)
    vars['days_late'] = str(days_late)
    vars['floor_text'] = money(floor)
    vars['floor_label'] = floor_label
    vars['band'] = band
    vars['deadline_text'] = label(deadline)
    vars['max_attempts'] = str(attempts)
    vars['valid_dates_text'] = ', '.join(valid)
    vars['today_is_bd'] = 'yes' if isbd(today) else 'no'
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_state'] = 'error'
'''

CODE_PRE_CLOSE = r'''
def truthy(v):
    return str(v).strip().lower() == 'true'

def num(v):
    try:
        return float(v)
    except Exception:
        return 0.0

try:
    facts = []
    outcome = ''
    reason = ''
    verified = truthy(vars.get('verify_identity_response.data.all_verified'))
    facts.append('Identity verified: ' + ('yes' if verified else 'no'))
    wl = vars.get('verify_identity_response.data.wrong_answers_left')
    id_failed = (not verified) and wl is not None and str(wl).strip() != '' and num(wl) < 1
    if id_failed:
        facts.append('The identity check FAILED after three wrong answers.')
    t_ok = truthy(vars.get('transfer_ok'))
    tg_ok = truthy(vars.get('transfer_general_ok'))
    queue = str(vars.get('transfer_to_agent_args.queue') or '')
    p_ok = truthy(vars.get('promise_ok'))
    p_tries = num(vars.get('create_promise_success_count')) + num(vars.get('create_promise_failure_count'))
    cb_ok = truthy(vars.get('callback_ok'))
    acct = str(vars.get('account_state') or '')
    if p_ok:
        facts.append('A payment promise WAS recorded.')
    elif p_tries > 0:
        facts.append('create_promise was tried ' + str(int(p_tries)) + ' time(s) and NO promise was recorded.')
    if cb_ok:
        facts.append('A callback WAS booked for ' + str(vars.get('schedule_callback_args.date') or '') + ' at ' + str(vars.get('schedule_callback_args.slot_time') or '') + '.')
    if acct == 'error':
        facts.append('The account details could not be loaded.')
    if t_ok and queue in ('restructuring', 'general', 'customer_support'):
        facts.append('The call WAS transferred to the ' + queue + ' queue.')
        outcome = 'transferred'
        reason = 'restructuring' if queue == 'restructuring' else ('human' if queue == 'general' else 'support')
    elif tg_ok:
        facts.append('The call WAS transferred to a person (general queue).')
        outcome = 'transferred'
        reason = 'human'
    elif t_ok:
        facts.append('The call WAS transferred to a person.')
        outcome = 'transferred'
    elif p_ok:
        outcome = 'promise'
    elif cb_ok:
        outcome = 'not_reached'
        reason = 'callback'
    elif id_failed:
        outcome = 'not_verified'
        reason = 'failed'
    elif verified and acct == 'error':
        outcome = 'no_promise'
        reason = 'service_error'
    elif verified and p_tries >= 2:
        outcome = 'no_promise'
        reason = 'service_error'
    if outcome:
        vars['outcome'] = outcome
        facts.append('The close outcome is already set to: ' + outcome + ((' / ' + reason) if reason else ''))
    if reason:
        vars['reason'] = reason
    vars['close_facts'] = '\n'.join(['- ' + f for f in facts])
except Exception as e:
    vars['close_facts'] = '- (no facts available; decide from the conversation)'
'''

# ----------------------------------------------------------------- tools

def transfer_general_tool():
    return api_tool(
        "transfer_general", "transfer_to_agent",
        "Hand the call to a person. CALL it only when the customer asked for a human, you asked once whether you can help, and they insist.",
        {"customer_id": body_field("string", "{{customer_id}}"),
         "queue": body_field("string", "general", enum=["general"])},
        ["customer_id", "queue"], mapping=[{"path": "data.ok", "variable": "transfer_general_ok"}])


def transfer_tool():
    return api_tool(
        "transfer_to_agent", "transfer_to_agent",
        "Hand the call to a person. CALL it with queue restructuring when the customer asks for a new payment plan or lower instalments; "
        "with queue customer_support when a customer in hardship accepts your offer to connect them with the customer support team; "
        "with queue general when the customer insists on a human after you asked once whether you can help.",
        {"customer_id": body_field("string", "{{customer_id}}"),
         "queue": body_field("string", "{{queue}}", "One of: restructuring, general, customer_support.",
                             enum=["restructuring", "general", "customer_support"])},
        ["customer_id", "queue"], mapping=[{"path": "data.ok", "variable": "transfer_ok"}])


verify_tool = api_tool(
    "verify_identity", "verify_identity",
    "Check one security answer. CALL it every time the customer gives an answer to a security question, one answer per call.",
    {"customer_id": body_field("string", "{{customer_id}}"),
     "field": body_field("string", "{{field}}", "date_of_birth or phone_last4.", enum=["date_of_birth", "phone_last4"]),
     "answer": body_field("string", "{{answer}}",
                          "For date_of_birth: the date as YYYY-MM-DD (convert from words; a date said only in numbers is day, then month, then year). For phone_last4: exactly four digits.")},
    ["customer_id", "field", "answer"])

callback_tool = api_tool(
    "schedule_callback", "schedule_callback",
    "Book a callback. CALL it as soon as the person gives a day and time inside the allowed callback window.",
    {"customer_id": body_field("string", "{{customer_id}}"),
     "date": body_field("string", "{{date}}", "The callback date, YYYY-MM-DD."),
     "slot_time": body_field("string", "{{slot_time}}", "The callback time, HH:MM, 24 hour clock, from 10:00 to 19:00.")},
    ["customer_id", "date", "slot_time"], mapping=[{"path": "data.ok", "variable": "callback_ok"}])

promise_tool = api_tool(
    "create_promise", "create_promise",
    "Record the payment promise. CALL it only after you read back product, amount and date and the customer clearly said yes to 'Do you confirm?'.",
    {"customer_id": body_field("string", "{{customer_id}}"),
     "product_id": body_field("string", "{{product_id}}"),
     "channel": body_field("string", "voice", enum=["voice"]),
     "amount_eur": body_field("number", "{{amount_eur}}", "The confirmed amount in euros, a number such as 120.5."),
     "promise_date": body_field("string", "{{promise_date}}", "The confirmed date, YYYY-MM-DD, one of the valid promise dates.")},
    ["customer_id", "product_id", "amount_eur", "promise_date", "channel"],
    mapping=[{"path": "data.ok", "variable": "promise_ok"}])

REASONS = ["refused", "hardship", "dispute", "service_error", "failed", "declined", "callback", "no_callback",
           "wrong_number", "deceased", "unclear", "restructuring", "human", "support"]

close_tool = api_tool(
    "close_call", "close_call",
    "Record how the call ended. CALL it exactly once, in the same message as your goodbye. It is the last thing you do.",
    {"customer_id": body_field("string", "{{customer_id}}"),
     "channel": body_field("string", "voice", enum=["voice"]),
     "outcome": body_field("string", "{{outcome}}",
                           "One of: promise, paid, transferred, no_promise, not_verified, not_reached. See the table in your instructions.",
                           enum=["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"]),
     "reason": body_field("string", "{{reason}}",
                          "Leave it out for promise and paid. Otherwise one reason that belongs to the outcome: "
                          "transferred: restructuring, human, support. no_promise: refused, hardship, dispute, service_error. "
                          "not_verified: failed, declined. not_reached: callback, no_callback, wrong_number, deceased, unclear.",
                          enum=REASONS)},
    ["customer_id", "outcome", "channel"], mapping=[{"path": "data.ok", "variable": "close_ok"}])

get_account_action = {
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
            "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}}, "required": ["customer_id"]},
        }},
    },
}

# ----------------------------------------------------------------- prompts

SYSTEM = """You are the digital assistant of Freya Bank on an outbound phone call. Speak English. Keep every turn to one or two short, plain sentences. Avoid technical words: never say "tool", "system", "API", "variable", "step" or "transition".

Rules that hold in every step:
- Address the customer as {{title}} {{last_name}}.
- Before the identity check has passed, never say "collections", "debt", "payment", "late", "overdue", any amount or the product, to anyone, relatives included. If asked what the call is about, say you can only discuss it with {{title}} {{last_name}} after a short security check.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked "Is this a scam?": say they can verify this call by phoning Freya Bank's customer service number, then continue.
- If asked something you cannot answer from what you were given: say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any term you were not given.
- Never say something is recorded, booked or done unless the matching action returned ok true. If an action fails, say so plainly.
- Call at most one action per message. After every action result, either speak to the customer or call the next action. Never end a turn with nothing.
- When a rule says to call an action, call it. Saying you did it is not enough.
- Today and now are given in your instructions. Never use any other date."""

OPENING_TASK = """You have already said: "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?" That was the first ask.

Your job: find out whether {{title}} {{last_name}} ({{first_name}} {{last_name}}) is on the line. Say nothing about why you are calling.

What counts as confirmation: only "yes", "that's me", "speaking", or the customer's own name. "Hello", "go ahead", "who is this" and similar do NOT count.

Decide on every customer message:
- Confirmed: call transition_to_identity at once, with no text.
- Not a confirmation and not one of the cases below: first answer any question they asked (robot or AI, scam, who is calling), then ask again exactly "Am I speaking with {{title}} {{last_name}}?". That is the second ask. There are only two asks in total.
- Still unclear after the second ask: say "I am sorry, I could not confirm who I am speaking with." and call transition_to_pre_close in the same message.
- Someone else answered (a relative, a colleague, "he is not here", "she is busy"): call transition_to_third_party at once, with no text.
- The person says this number does not belong to the customer, or there is nobody of that name: call transition_to_pre_close, with no text.
- The person says the customer has died: say exactly "I am sorry for your loss." and nothing else, and call transition_to_pre_close in the same message.
- The person says for the second time that they do not want to talk: call transition_to_pre_close, with no text.
- The person asks for a human: ask once whether you can help first. If they insist, call transfer_general."""

THIRD_PARTY_TASK = """The person on the line is not {{title}} {{last_name}}. Do not say why you are calling, and say nothing about any account, even if they offer to pay or to answer questions for the customer. They may not answer security questions. Your only job: find a time when {{title}} {{last_name}} can be reached, and book a callback.

Now: {{today_text}}, {{now_time}}.
Allowed callback window (inclusive, and only later than now):
{{callback_window}}
Weekday words:
{{week_table}}

How to handle it:
- Ask when {{title}} {{last_name}} can be reached.
- When they give a day and a time inside the window: call schedule_callback with date (YYYY-MM-DD) and slot_time (HH:MM, 24 hour). If they give a time with no day, take today when that time is still allowed today, else ask which day.
- When the day or time is outside the window: say which times are possible and ask once for another time. If the second answer is also outside the window, or they cannot give a time, do not book: say you will try again another time and call transition_to_pre_close in the same message.
- If schedule_callback returns ok false or an error: the callback is NOT booked. Say so, and try once more if they give a valid time; otherwise call transition_to_pre_close.
- The person says the number does not belong to the customer: call transition_to_pre_close, with no text.
- The person says the customer has died: say exactly "I am sorry for your loss." and nothing else, and call transition_to_pre_close in the same message.
- The person now says they are {{title}} {{last_name}} themself: call transition_to_identity, with no text.
- The person asks for a human: ask once whether you can help first. If they insist, call transfer_general."""

THIRD_PARTY_ENTER = "Do not say why you are calling. In one short sentence, ask when {{title}} {{last_name}} can be reached. No action in this turn."

IDENTITY_TASK = """The customer said they are {{title}} {{last_name}}. Check their identity with two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. Do not say why you are calling yet.

For every answer, call verify_identity:
- field date_of_birth, answer as YYYY-MM-DD, whatever way they said it. A date said only in numbers is day, then month, then year: "05 03 1980" or "5/3/80" is 1980-03-05. "the third of May nineteen eighty-two" is 1982-05-03.
- field phone_last4, answer as exactly four digits. Join digits said in parts.

Read each result:
- ok false or an error: the answer was not checked and it does not count. Ask the same question again.
- hint "day_month_swapped": ask them to say the month of their birth as a word, for example "the fifth of March". This does not count as a wrong answer.
- verified true for the date of birth: ask for the last four digits of the phone number on file.
- verified false: say the answer does not match our records and ask the same question again. Never reveal the right answer.

Refusals:
- If they do not want to answer, or ask what the call is about instead of answering: explain once that these questions protect their account, and ask again.
- At the second refusal or the second such question: call transition_to_pre_close, with no text.
- If they say for the second time that they do not want to talk: call transition_to_pre_close, with no text.
- If they ask for a human: ask once whether you can help first. If they insist, call transfer_general.
- If they say the customer has died or that this is the wrong number: call transition_to_pre_close (say "I am sorry for your loss." first for a death)."""

NEGOTIATE_TASK = """The customer is verified. You already said: "I am calling from the collections team about a late payment on your {{product_words}}. The past-due amount is {{past_due_text}} euros, and it is {{days_late}} days late. Can you make this payment today?"

ACCOUNT
- Product: {{product_words}}
- Full past-due amount: {{past_due_text}} euros
- Floor ({{floor_label}}): {{floor_text}} euros
- Band: {{band}}. Persuasion attempts allowed: {{max_attempts}}
- Deadline, the latest date you may record: {{deadline_text}}
- Attempt 1 date: {{attempt1_text}}

DATES
- Today: {{today_text}}. Now: {{now_time}}.
- Valid promise dates (business days from today up to the deadline): {{valid_dates_text}}
- Only a date in that list can be recorded.
- Weekday words ("next X" is in the following calendar week, "this X" is in the current week):
{{week_table}}

GETTING THE PROMISE
1. Always ask for the full past-due amount first. Never ask how much they can pay. You propose every amount.
2. "Yes, today": full amount, today. If today is not in the valid list, offer the first valid date.
3. A date the customer names:
   - In the valid list: use it.
   - A weekend day or bank holiday not after the deadline: offer the next valid business day after it.
   - After the deadline: say the latest date you can record is {{deadline_text}} and offer it. If they refuse it, that is a flat refusal (rule 6).
   - Vague ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline {{deadline_text}}.
4. An amount:
   - The full amount is too much: offer the floor of {{floor_text}} euros, once, and say the rest stays overdue. If they refuse the floor, that is a flat refusal (rule 6).
   - The customer proposes an amount from {{floor_text}} up to {{past_due_text}} euros, both included: accept it.
   - Below {{floor_text}} euros: say it cannot be recorded and offer the floor once. If they do not accept, that is a flat refusal (rule 6).
5. A date or an amount the customer proposes is never a refusal. Handle it with rules 3 and 4.
6. A flat refusal or a non-answer uses one persuasion attempt. A no to paying today, with no date and no amount, is a flat refusal.
   - Attempt 1: propose {{attempt1_text}} for the full amount, or for the floor if they already said the full amount is too much.
   - Attempt 2, only when the attempts allowed are 2: propose the floor of {{floor_text}} euros on {{deadline_text}}.
   - When the attempts allowed are used up: stop. Do not repeat an offer they already refused. Call transition_to_pre_close, with a short neutral sentence.
7. Hardship (illness, a death in the family, job loss): say one short sentence of sympathy. Make no persuasion attempt. Offer to connect them with the customer support team. If they accept, call transfer_to_agent with queue customer_support. If they decline, call transition_to_pre_close. If they still name a date or an amount themselves, take the promise with rules 3 and 4.

CONFIRMING AND RECORDING
- Read back the product, the amount and the date, and ask "Do you confirm?". Call create_promise only after a clear yes, with amount_eur as a number and promise_date as YYYY-MM-DD.
- If they change the date or the amount at this point, check the new value with rules 3 and 4 and read it back again.
- If create_promise returns ok false or an error, the promise is NOT recorded. Call create_promise once more with the same values. If it fails again, say you could not record the promise and call transition_to_pre_close. Never say it is recorded unless ok is true.

OTHER THINGS CUSTOMERS SAY
- "I already paid" (this past-due amount): say payments can take one business day to appear. Take no promise. Call transition_to_pre_close.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise, call transition_to_pre_close.
- A new payment plan or lower instalments: do not describe any plan. Call transfer_to_agent with queue restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
- They say for the second time that they do not want to talk: call transition_to_pre_close."""

AFTER_PROMISE_TASK = """A payment promise for the {{product_words}} is recorded. You already confirmed it and said a text message will follow.

- If they want to change or cancel the promise: say a recorded promise cannot be changed in this call, and that they can change it in the mobile app.
- A new payment plan or lower instalments: do not describe any plan. Call transfer_to_agent with queue restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_to_agent with queue general.
- Hardship they now mention: one short sentence of sympathy, then offer the customer support team; if they accept, call transfer_to_agent with queue customer_support.
- When they have nothing else, say no, or say goodbye: call transition_to_pre_close, with no text.
- Do not record another promise."""

WRAP_TASK = """The call is ending now. What is known:
{{close_facts}}

Write ONE short message and, in that same message, call close_call:
1. If needed, one closing sentence first:
   - the identity check failed after three wrong answers: tell them to use the Freya Bank mobile app or visit a branch. Say nothing about the account.
   - a callback was booked: confirm the day and time in a few words.
   - a transfer happened: say you are connecting them now.
   - the customer said they already paid and you did not yet say it: payments can take one business day to appear.
   - a promise could not be recorded: say you could not record it.
2. Then thank them and say goodbye.
3. Call close_call in the same message. Ask no question. Do not repeat information the customer was already given.

close_call outcome and reason (if the outcome is already set above, it is filled in for you; give only what is still asked):
- promise (no reason): at least one promise was recorded.
- paid (no reason): the customer said they already paid this past-due amount.
- transferred: restructuring (new plan or lower instalments), human (asked for a person), support (hardship, accepted customer support).
- no_promise: refused (said no after the persuasion attempts, or said twice they do not want to talk after the identity check passed), hardship (illness, death in the family or job loss, declined the support team), dispute (says the debt or product is not theirs, or was closed or paid off in the past), service_error (the promise could not be recorded, or the account could not be loaded).
- not_verified: failed (three wrong security answers), declined (refused the security questions, or said twice they do not want to talk, before the identity check passed).
- not_reached: callback (callback booked), no_callback (someone else answered and no valid callback time was given), wrong_number (the number does not belong to the customer), deceased (the customer has died), unclear (who was on the line stayed unclear after two asks).
Choose from the conversation. Leave reason out for promise and paid.

If you already said goodbye but did not call close_call yet, call it now with only a short goodbye. If close_call returned ok false, call it once more with a corrected reason."""

WRAP_LOOP = """{{close_facts}}
Call close_call now if you have not called it yet, with the outcome and reason from the conversation (see the earlier table). If close_call returned ok false, call it once more with a corrected reason. Say only a short goodbye."""

# ----------------------------------------------------------------- nodes

nodes = {}

nodes["setup"] = code_node("setup", CODE_DATES, "opening")

nodes["opening"] = {
    "name": "opening",
    "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": True,
    "task_message": OPENING_TASK,
    "tools": [transfer_general_tool()],
    "max_node_turns": 8,
    "max_turn_transition": "pre_close_auto",
    "transitions": [
        {"target_node": "pre_close_auto", "description": "The transfer to a person succeeded",
         "condition": cond_or(*is_true("transfer_general_ok"))},
        tool_transition("identity", "The person clearly confirmed they are the customer: said yes, that's me, speaking, or their own name"),
        tool_transition("third_party", "Someone other than the customer answered, for example a relative, or the customer is not available"),
        tool_transition("pre_close", "The call must end now: wrong number, the customer has died, still unclear after the second ask, or the person refused to talk twice"),
    ],
}

nodes["third_party"] = {
    "name": "third_party",
    "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": THIRD_PARTY_ENTER},
    "on_enter_first_entry_only": True,
    "task_message": THIRD_PARTY_TASK,
    "tools": [callback_tool, transfer_general_tool()],
    "max_node_turns": 10,
    "max_turn_transition": "pre_close_auto",
    "transitions": [
        {"target_node": "pre_close_auto", "description": "The callback was booked or the transfer succeeded",
         "condition": cond_or(*is_true("callback_ok", "transfer_general_ok"))},
        tool_transition("identity", "The person now says they are the customer themself"),
        tool_transition("pre_close", "The call must end now: no valid callback time, wrong number, or the customer has died"),
    ],
}

nodes["identity"] = {
    "name": "identity",
    "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you. Before we continue, I need to ask two short security questions. What is your date of birth?"},
    "on_enter_first_entry_only": True,
    "task_message": IDENTITY_TASK,
    "tools": [verify_tool, transfer_general_tool()],
    "max_node_turns": 14,
    "max_turn_transition": "pre_close_auto",
    "transitions": [
        {"target_node": "load_account", "description": "Both security answers verified",
         "condition": cond_or(*is_true("verify_identity_response.data.all_verified"))},
        {"target_node": "pre_close_auto", "description": "No wrong answers left, or the transfer succeeded",
         "condition": cond_or(
             {"logic": "and", "conditions": [
                 c("verify_identity_response.data.wrong_answers_left", "is_set"),
                 c("verify_identity_response.data.wrong_answers_left", "less_than", 1)]},
             *is_true("transfer_general_ok"))},
        tool_transition("pre_close", "The call must end now: the customer refused the security questions a second time, or refused to talk twice"),
    ],
}

nodes["load_account"] = {
    "name": "load_account",
    "node_type": "api_request",
    "passthrough": True,
    "passthrough_default_transition": "compute_account",
    "on_enter": {"type": "silent"},
    "disable_inactivity_monitor": True,
    "suppress_tool_results": True,
    "pre_actions": [get_account_action],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [{"target_node": "compute_account", "description": "always", "condition": {"operator": "always"}}],
}

nodes["compute_account"] = code_node("compute_account", CODE_ACCOUNT, "negotiate")
nodes["compute_account"]["transitions"] = [
    {"target_node": "negotiate", "description": "The account is loaded",
     "condition": cond_or(c("account_state", "equals", "ok"))},
    {"target_node": "pre_close_auto", "description": "always", "condition": {"operator": "always"}},
]
nodes["compute_account"]["passthrough_default_transition"] = "pre_close_auto"

nodes["negotiate"] = {
    "name": "negotiate",
    "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you, that is verified. I am calling from the collections team about a late payment on your {{product_words}}. The past-due amount is {{past_due_text}} euros, and it is {{days_late}} days late. Can you make this payment today?"},
    "on_enter_first_entry_only": True,
    "task_message": NEGOTIATE_TASK,
    "tools": [promise_tool, transfer_tool()],
    "max_node_turns": 40,
    "max_turn_transition": "pre_close_auto",
    "transitions": [
        {"target_node": "after_promise", "description": "The promise was recorded",
         "condition": cond_or(*is_true("promise_ok"))},
        {"target_node": "pre_close_auto", "description": "The transfer succeeded, or create_promise failed twice",
         "condition": cond_or(
             *is_true("transfer_ok"),
             c("create_promise_success_count", "greater_than", 1),
             c("create_promise_failure_count", "greater_than", 1),
             {"logic": "and", "conditions": [
                 c("create_promise_success_count", "greater_than", 0),
                 c("create_promise_failure_count", "greater_than", 0)]})},
        tool_transition("pre_close", "The call must end now: refusal after the persuasion attempts, already paid, dispute, hardship with support declined, refused to talk twice, or the promise could not be recorded"),
    ],
}

nodes["after_promise"] = {
    "name": "after_promise",
    "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you. Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
    "on_enter_first_entry_only": True,
    "task_message": AFTER_PROMISE_TASK,
    "tools": [transfer_tool()],
    "max_node_turns": 8,
    "max_turn_transition": "pre_close_auto",
    "transitions": [
        {"target_node": "pre_close_auto", "description": "The transfer succeeded", "condition": cond_or(*is_true("transfer_ok"))},
        tool_transition("pre_close", "The customer has nothing else, said no, or said goodbye"),
    ],
}

nodes["pre_close"] = code_node("pre_close", CODE_PRE_CLOSE, "wrap_up")
nodes["pre_close_auto"] = code_node("pre_close_auto", CODE_PRE_CLOSE, "wrap_up")

nodes["wrap_up"] = {
    "name": "wrap_up",
    "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "on_enter_first_entry_only": True,
    "task_message": WRAP_TASK,
    "tools": [close_tool],
    "max_node_turns": 3,
    "max_turn_transition": "end",
    "transitions": [
        {"target_node": "end", "description": "close_call answered",
         "condition": cond_or(
             *is_true("close_ok", "close_call_response.data.ok"),
             c("close_call_success_count", "greater_than", 1),
             c("close_call_failure_count", "greater_than", 1))},
    ],
}

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

workflow = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

assert "{{" not in CODE_DATES + CODE_ACCOUNT + CODE_PRE_CLOSE and "}}" not in CODE_DATES + CODE_ACCOUNT + CODE_PRE_CLOSE
out = Path(__file__).resolve().parent / f"{SLOT}.workflow.json"
out.write_text(json.dumps(workflow, indent=1))
print(out)
