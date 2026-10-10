"""Writes out/pl-g3-limits-raw.body.json and out/pl-g3-limits-raw.plan.json for tools/lower.py."""
import json
from pathlib import Path

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
BRIEF = "briefs/pl-g3-limits-raw.md"
OUT = Path(__file__).parent

HEADERS = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}


def api_tool(name, description, body_props, required, retries=0, post_hook="", mapping=None):
    tool = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": f"{BASE}/{name}"},
                "method": {"type": "string", "default": "POST"},
                "headers": HEADERS,
                "body": {"type": "object", "properties": body_props, "required": required},
            }},
        },
    }
    if post_hook:
        tool["post_process_code"] = post_hook
    if mapping:
        tool["response_mapping"] = mapping
    return tool


def cid():
    return {"type": "string", "default": "{{customer_id}}"}


def tc(target, description):
    """Tool-call transition: the dialogue model moves by calling transition_to_<target>."""
    return {"target_node": target, "description": description, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": description}}


def when(*checks):
    return {"logic": "or", "conditions": list(checks)}


def var(name, op, operand=None):
    c = {"variable": name, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return c


def code_node(name, code, nxt_transitions, default_next):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": default_next,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {
            "name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {
                "code": {"type": "string", "default": code},
                "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": nxt_transitions,
    }


# ------------------------------------------------------------------ code

COMMON = r'''
import datetime
import math
import json
import re
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)
def fmt(d):
    return DN[d.weekday()] + ' ' + str(d.day) + ' ' + MN[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def nextbd(d):
    d = d + ONE
    while not isbd(d):
        d = d + ONE
    return d
def parse_now():
    raw = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        return datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(raw[:10] + 'T12:00')
    except Exception:
        return datetime.datetime.utcnow()
'''

SETUP_CODE = COMMON + r'''
try:
    now = parse_now()
    today = now.date()
    vars['today_iso'] = today.isoformat()
    vars['today_text'] = fmt(today) + ', time ' + now.strftime('%H:%M')
    nb = nextbd(today)
    lines = []
    hm = now.strftime('%H:%M')
    if hm < '19:00':
        start = '10:00' if hm < '10:00' else 'later than ' + hm
        lines.append('- Today, ' + fmt(today) + ': from ' + start + ' up to 19:00 included.')
    else:
        lines.append('- Today is no longer possible (it is after 19:00).')
    lines.append('- The next business day, ' + fmt(nb) + ': from 10:00 to 19:00, both included.')
    lines.append('- Any other day, or a time before 10:00 or after 19:00, is outside the window.')
    vars['callback_window'] = '\n'.join(lines)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['today_iso'] = str(vars.get('now') or '')[:10]
    vars['today_text'] = str(vars.get('now') or '')
    vars['callback_window'] = '- Today from 10:00 to 19:00 (later than now), or the next business day from 10:00 to 19:00.'
    vars['setup_state'] = 'error'
'''

PREPARE_CODE = COMMON + r'''
def as_list(p):
    if isinstance(p, str):
        s = p.strip()
        try:
            p = json.loads(s)
        except Exception:
            try:
                p = json.loads(s.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
            except Exception:
                p = None
    if isinstance(p, dict) and 'products' in p:
        p = p.get('products')
    if isinstance(p, list):
        return [x for x in p if isinstance(x, dict)]
    return []
def flat_products():
    found = dict()
    pat = re.compile(r'^(?:get_account_response\.data\.|get_account_response\.)?products(?:\.|\[)(\d+)\]?\.(\w+)$')
    for k in list(vars.keys()):
        m = pat.match(str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    return [found[i] for i in sorted(found)]
def num(x, default=0.0):
    try:
        return float(str(x).replace(',', ''))
    except Exception:
        return default
def money(x):
    return '%.2f euros' % x
try:
    now = parse_now()
    today = now.date()
    prods = as_list(vars.get('products'))
    if not prods:
        prods = as_list(vars.get('get_account_response.data.products'))
    if not prods:
        prods = flat_products()
    prods = prods[:3]
    monday = today - datetime.timedelta(days=today.weekday())
    def last_bd_of_week(mon):
        d = mon + datetime.timedelta(days=4)
        while d >= mon and not isbd(d):
            d = d - ONE
        return d if d >= mon else None
    for idx, p in enumerate(prods):
        i = str(idx + 1)
        ptype = str(p.get('type') or '')
        past_due = num(p.get('past_due'))
        days_late = int(num(p.get('days_late'), 0))
        if ptype == 'credit_card':
            label = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = num(p.get('minimum_payment'), past_due)
            floor_why = 'the minimum payment'
        elif ptype == 'car_loan':
            label = 'car loan'
            floor = float(math.floor(past_due / 2.0))
            floor_why = 'half of the past-due amount, rounded down to whole euros'
        else:
            label = 'personal loan'
            floor = num(p.get('instalment_amount'), past_due)
            floor_why = 'the instalment amount'
        cap = min(past_due, 2000.0)
        floor = min(floor, cap)
        early = days_late <= 7
        n = 12 if early else 7
        d = today
        k = 0
        while k < n:
            d = d + ONE
            if isbd(d):
                k += 1
        deadline = d
        allowed = 2 if early else 3
        valid = []
        d = today
        while d <= deadline:
            if isbd(d):
                valid.append(DN[d.weekday()] + ' ' + d.isoformat())
            d = d + ONE
        a1 = last_bd_of_week(monday)
        if a1 is None or a1 <= today:
            a1 = last_bd_of_week(monday + datetime.timedelta(days=7))
        if a1 is None or a1 > deadline:
            a1 = deadline
        def status(x):
            if x < today:
                return 'in the past, not valid'
            if x > deadline:
                return 'after the deadline: offer the deadline ' + deadline.isoformat() + ' instead'
            if not isbd(x):
                nb = nextbd(x)
                if nb > deadline:
                    return 'not a business day, and the next business day is after the deadline: offer the deadline ' + deadline.isoformat()
                return 'not a business day: offer the next business day ' + DN[nb.weekday()] + ' ' + nb.isoformat()
            return 'valid'
        cal = []
        d = today
        end = deadline + datetime.timedelta(days=14)
        while d <= end:
            cal.append('  ' + d.isoformat() + ' ' + DN[d.weekday()] + ': ' + status(d))
            d = d + ONE
        wk = []
        for j in range(7):
            this_d = monday + datetime.timedelta(days=j)
            next_d = this_d + datetime.timedelta(days=7)
            wk.append('  this ' + DN[j] + ' = ' + this_d.isoformat() + ' (' + status(this_d) + '); next ' + DN[j] + ' = ' + next_d.isoformat() + ' (' + status(next_d) + ')')
        over = past_due > 2000.0
        facts = []
        facts.append('Product: ' + label + ' (product_id ' + str(p.get('product_id') or '') + ').')
        facts.append('Past-due amount: ' + money(past_due) + '. Days late: ' + str(days_late) + '.')
        if over:
            facts.append('Full amount to ask for: 2000.00 euros. That is the most one promise may be; the past-due amount is higher, so say the rest stays overdue.')
        else:
            facts.append('Full amount to ask for: ' + money(cap) + ' (the whole past-due amount).')
        facts.append('Floor, the lowest amount you may record: ' + money(floor) + ' (' + floor_why + ').')
        facts.append('Amounts you may record: from ' + money(floor) + ' up to ' + money(cap) + ', both included. Nothing below the floor, nothing above ' + money(cap) + '.')
        facts.append('Deadline, the latest promise date: ' + fmt(deadline) + '.')
        facts.append('Valid promise dates (business days from today to the deadline): ' + ', '.join(valid) + '.')
        facts.append('Bank holidays (never valid): ' + ', '.join(HOL) + '. Saturdays and Sundays are never valid.')
        facts.append('"This <weekday>" is in the current week, "next <weekday>" is in the following calendar week:')
        facts.extend(wk)
        facts.append('Calendar from today (anything later than this list is after the deadline):')
        facts.extend(cal)
        vars['p' + i + '_id'] = str(p.get('product_id') or '')
        vars['p' + i + '_label'] = label
        vars['allowed_' + i] = allowed
        vars['facts_' + i] = '\n'.join(facts)
        rest = ' Say that the rest stays overdue.' if over else ''
        intro = 'Say that you are calling from the collections team about a late payment. ' if idx == 0 else 'Now move on to the next late product. '
        vars['offer_' + i + '_1'] = (intro + 'Name the product in words: "' + label + '". State the past-due amount, ' + money(past_due)
            + ', and that it is ' + str(days_late) + ' days late. Ask for the full amount, ' + money(cap) + '.' + rest
            + ' Then ask exactly: "Can you make this payment today?"')
        vars['offer_' + i + '_2'] = ('Persuasion attempt 1. Propose paying ' + money(cap) + ' on ' + fmt(a1) + '.' + rest
            + ' If the customer already said the full amount is too much, propose the floor, ' + money(floor)
            + ', on ' + fmt(a1) + ' instead and say the rest stays overdue.')
        vars['offer_' + i + '_3'] = ('Persuasion attempt 2. Propose paying the floor amount, ' + money(floor)
            + ', on the deadline, ' + fmt(deadline) + '. Say the rest stays overdue.')
    vars['item_count'] = len(prods)
    vars['products_state'] = 'ready' if prods else 'none'
except Exception as e:
    vars['item_count'] = 0
    vars['products_state'] = 'none'
'''

# ------------------------------------------------------------------ hooks

VERIFY_HOOK = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            def t(x):
                return str(x).lower() == 'true'
            left = d.get('wrong_answers_left')
            if t(d.get('all_verified')):
                msg = 'Both answers are verified.'
            elif d.get('hint') == 'day_month_swapped':
                msg = 'The day and the month look swapped. Ask the customer to say the month of their birth as a word, then call verify_identity again. This retry does not count as a wrong answer.'
            elif str(d.get('ok')).lower() == 'false' and not t(d.get('verified')) and left is None:
                msg = 'The answer could not be checked and did not count as a wrong answer. Ask the customer to say it again, then call verify_identity again.'
            elif t(d.get('verified')):
                msg = 'Correct. If this was the date of birth, now ask for the last four digits of the phone number on file. Do not mention the account yet.'
            else:
                msg = 'Wrong answer. Wrong answers left: ' + str(left) + '. Say the answer did not match and ask the same question again.'
            d['what_to_do_next'] = msg
        else:
            result['what_to_do_next'] = 'The check did not work for a technical reason and nothing was counted. Ask the customer to repeat the answer, then call verify_identity again.'
except Exception:
    pass
'''

PROMISE_HOOK = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        okv = isinstance(d, dict) and str(d.get('ok')).lower() == 'true'
        msg = 'The promise is recorded.' if okv else 'Recording FAILED. Nothing was recorded. Do not say it is recorded. If this is the first failure, tell the customer there was a problem and call create_promise once more now with the same values.'
        if isinstance(d, dict):
            d['what_to_do_next'] = msg
        else:
            result['what_to_do_next'] = msg
except Exception:
    pass
'''

CALLBACK_HOOK = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        okv = isinstance(d, dict) and str(d.get('ok')).lower() == 'true'
        msg = 'The callback is booked.' if okv else 'The callback was NOT booked. Do not say it is booked.'
        if isinstance(d, dict):
            d['what_to_do_next'] = msg
        else:
            result['what_to_do_next'] = msg
except Exception:
    pass
'''

# ------------------------------------------------------------------ prompts

SYSTEM = """You are the digital assistant of Freya Bank on an outbound phone call. Speak English. Keep every turn to one or two short, plain sentences. Avoid technical words: never say "tool", "system", "variable", "step" or "transition" to the customer.

Call facts: you are calling {{title}} {{last_name}} (first name {{first_name}}). Address the customer as "{{title}} {{last_name}}". Today is {{today_text}}. Use only this date; never use any other clock.

Rules that hold during the whole call:
- Until the identity check has passed, never say "collections", "debt", "payment", "late", "overdue", the product, an amount or why you are calling. This holds for everyone, relatives included.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam: say they can verify the call by phoning Freya Bank's customer service number, then continue.
- If asked something you cannot answer from the information you were given: say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any other term.
- When a rule says to call a tool, call it; saying you will do it is not enough. Call at most one tool per message.
- After every tool result, either speak to the customer or call the next tool. Never end a turn with nothing. If a result contains what_to_do_next, follow it.
- The closing tools (their names start with transition_to_end_, transition_to_close_ or transition_to_transfer_) end or hand over the call. When you call one of them, do not say goodbye yourself; the goodbye is said for you."""

OPENING_TASK = """You have just said: "Hello, this is the digital assistant of Freya Bank. This call is recorded. Am I speaking with {{title}} {{last_name}}?" Your only job now is to find out whether {{title}} {{last_name}} is on the line.

- Only "yes", "that's me", "speaking", or the customer saying their own name counts as confirmation. "Hello", "go ahead", "who is this" do not count.
- When the person confirms: call transition_to_security at once, without other words.
- If the answer is not a confirmation: ask "Am I speaking with {{title}} {{last_name}}?" once more. If the person asked a question, answer it first in one sentence (who you are: Freya Bank's digital assistant; robot or scam questions as in the general rules), then ask. That ask is the second ask. Never say why you are calling.
- If after the second ask it is still not a confirmation: call transition_to_end_unclear.
- If the person says they are someone else (a relative, a colleague) or that {{title}} {{last_name}} is not available: call transition_to_third_party, without other words.
- If the person says the number does not belong to {{title}} {{last_name}} or they do not know them: call transition_to_end_wrong_number.
- If the person says {{title}} {{last_name}} has died: call transition_to_end_deceased with no other words.
- If the person says for the second time that they do not want to talk: call transition_to_end_declined.
- If the person asks for a human: ask once whether you can help first. If they insist: call transition_to_transfer_general.
Do not call any other tool in this step."""

THIRD_PARTY_TASK = """Someone other than {{title}} {{last_name}} is on the line. Do not say why you are calling. Say nothing about any account, even if they ask or offer to pay. They may not answer security questions. Your job is to find out when {{title}} {{last_name}} can be reached.

Allowed callback times:
{{callback_window}}

- When the person names a day and a time inside the window: call schedule_callback with date as YYYY-MM-DD and time as HH:MM (24 hour). Then say the callback is booked only if the result says so.
- If they name only a day or only a time, ask for the missing part.
- If they name a day or a time outside the window: tell them the times you can offer and ask once for another time. If the second answer is also outside the window, or they cannot give a time: call transition_to_end_no_callback. Never schedule outside the window.
- If they say the number does not belong to {{title}} {{last_name}}: call transition_to_end_wrong_number.
- If they say {{title}} {{last_name}} has died: call transition_to_end_deceased with no other words.
- If {{title}} {{last_name}} comes to the phone in person: call transition_to_opening.
Call no tool other than these."""

SECURITY_TASK = """{{title}} {{last_name}} confirmed who they are. Now check identity with two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. You have already asked for the date of birth.

- Date of birth: convert whatever the customer says to YYYY-MM-DD and call verify_identity with field date_of_birth. A date said only as numbers is day, then month, then year (for example 03/04/1985 is 1985-04-03). If you are unsure of the year, ask for it before calling.
- Phone: collect all four digits (the customer may say them in parts), then call verify_identity with field phone_last4 and the four digits.
- Call verify_identity once for each answer. Never guess an answer. Follow what_to_do_next in the result.
- If an answer is wrong, you may ask the same question again.
- If the customer will not answer, or asks what the call is about instead of answering: the first time, explain in one sentence that these questions protect their account, and ask again. Do not say what the call is about. The second time they refuse or ask: call transition_to_end_declined.
- If the customer says for the second time that they do not want to talk: call transition_to_end_declined.
- If the customer asks for a human: ask once whether you can help first. If they insist: call transition_to_transfer_general.
Never mention the account, an amount, a product or collections in this step."""

NEGOTIATE_TASK = """The customer's identity is verified. You are handling late product {i} of {{item_count}}.

PRODUCT FACTS
{{facts_{i}}}

YOUR OFFER IN THIS STEP
{{offer_{i}_{a}}}

HOW TO WORK
1. When you enter this step, make the offer above. If create_promise just recorded a promise for an earlier product, first say that promise is recorded and say: "You will receive a text message confirming this promise." Before an attempt, check the conversation: if the customer has mentioned illness, a death in the family or job loss, follow rule 6 and make no offer.
2. Never ask "how much can you pay?". You propose every amount. Never repeat an offer the customer already refused.
3. Dates the customer proposes are never a refusal. Use the PRODUCT FACTS calendar:
   - valid date: accept it.
   - Saturday, Sunday or bank holiday not after the deadline: offer the next business day.
   - a date after the deadline: say the latest date you can record is the deadline and offer it.
   - a date in the past: say it must be today or later.
   - a vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
   - "this <weekday>" and "next <weekday>" are listed in the facts. Use them exactly.
4. Amounts the customer proposes are never a refusal:
   - from the floor up to the full amount, both included: accept it.
   - below the floor: say it cannot be recorded and offer the floor once.
   - above the full amount you may ask for: you may record at most that amount; say the rest stays overdue.
   - if the customer says the full amount is too much: offer the floor once and say the rest stays overdue.
5. Confirming: read back the product, the amount and the date, and ask "Do you confirm?". Only after a clear yes, call create_promise with amount as a number (for example 120.5) and date as YYYY-MM-DD. If the customer changes the date or the amount, check the new value with rules 3 and 4 and read back again.
   - Say the promise is recorded only after create_promise returns ok true. If it fails, say there was a problem and call create_promise once more with the same values.
   - A recorded promise cannot be changed or cancelled in this call; if asked, say they can change it in the mobile app.
6. Hardship: if the customer mentions illness, a death in the family or job loss, say one short sentence of sympathy, make no offer and no persuasion, and offer to connect them with the customer support team. If they accept: call transition_to_transfer_support. If they decline: call transition_to_end_hardship. If they still name a date or an amount themselves, handle it with rules 3 to 5. This rule comes before any offer and before the payment plan rule.
7. Other things the customer says:
   - They already paid this amount: call transition_to_end_paid (do not take a promise).
   - The debt is not theirs, they never had this product, or the product was closed or paid off in the past: do not argue, call transition_to_end_dispute.
   - They ask for a new payment plan or lower instalments: do not describe any plan, call transition_to_transfer_restructuring.
   - They ask for a human: ask once whether you can help first. If they insist: call transition_to_transfer_general.
   - They say for the second time that they do not want to talk: call transition_to_end_refused.
8. Only these tools exist here: create_promise and the transition tools named above."""


def promise_tool(i_placeholder=True):
    return api_tool(
        "create_promise",
        "Record the payment promise for this product. CALL it only after the customer said a clear yes to your read-back of product, amount and date.",
        {
            "customer_id": cid(),
            "product_id": {"type": "string", "default": "{{p{i}_id}}"},
            "amount": {"type": "number", "default": "{{amount}}", "description": "The confirmed amount in euros, as a number, for example 120.5."},
            "date": {"type": "string", "default": "{{date}}", "description": "The confirmed payment date as YYYY-MM-DD."},
        },
        ["amount", "date"],
        retries=0,
        post_hook=PROMISE_HOOK,
        mapping=[{"path": "data.promise_id", "variable": "promise_id_{i}"}],
    )


def transfer_node(name, queue, line, ok_close):
    return {
        "name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "close:transfer_failed",
        "on_enter": {"type": "tts", "text": line}, "disable_inactivity_monitor": True,
        "pre_actions": [api_tool("transfer_to_agent", "Hand the call to a person.",
                                 {"customer_id": cid(),
                                  "queue": {"type": "string", "enum": [queue], "default": queue}},
                                 ["queue"], retries=0)],
        "response_mapping": [],
        "transitions": [
            {"target_node": ok_close, "description": "The transfer worked",
             "condition": when(var("transfer_to_agent_response.data.ok", "equals", "true"),
                               var("transfer_to_agent_response.data.ok", "equals", "True"))},
            {"target_node": "close:transfer_failed", "description": "always", "condition": {"operator": "always"}},
        ],
    }


nodes = {
    "setup": code_node("setup", SETUP_CODE,
                       [{"target_node": "opening", "description": "always", "condition": {"operator": "always"}}], "opening"),
    "opening": {
        "name": "opening", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Hello, this is the digital assistant of Freya Bank. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
        "task_message": OPENING_TASK,
        "max_node_turns": 8, "max_turn_transition": "close:unclear",
        "transitions": [
            tc("security", "The person confirmed they are the customer (yes, that's me, speaking, or their own name)."),
            tc("third_party", "Someone other than the customer answered, or the customer is not available."),
            tc("close:wrong_number", "The person says the number does not belong to the customer."),
            tc("close:deceased", "The person says the customer has died."),
            tc("close:unclear", "After the second ask it is still not confirmed who is on the line."),
            tc("close:declined", "The person said for the second time that they do not want to talk."),
            tc("transfer_general", "The person insists on speaking to a human after you asked once whether you can help."),
        ],
    },
    "third_party": {
        "name": "third_party", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "When would be a good time to reach {{title}} {{last_name}}?"},
        "task_message": THIRD_PARTY_TASK,
        "tools": [api_tool("schedule_callback",
                           "Book a callback. CALL it as soon as the person names a day and a time that are inside the allowed callback window.",
                           {"customer_id": cid(),
                            "date": {"type": "string", "default": "{{date}}", "description": "Callback date as YYYY-MM-DD."},
                            "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24 hour, from 10:00 to 19:00."}},
                           ["date", "time"], post_hook=CALLBACK_HOOK)],
        "max_node_turns": 8, "max_turn_transition": "close:no_callback",
        "transitions": [
            {"target_node": "close:callback", "description": "The callback was booked",
             "condition": when(var("schedule_callback_success_count", "greater_than", 0))},
            {"target_node": "close:callback_failed", "description": "Booking the callback failed",
             "condition": when(var("schedule_callback_failure_count", "greater_than", 0))},
            tc("close:no_callback", "The person gave a second time outside the window, or cannot give a time."),
            tc("close:wrong_number", "The person says the number does not belong to the customer."),
            tc("close:deceased", "The person says the customer has died."),
            tc("opening", "The customer came to the phone in person."),
        ],
    },
    "security": {
        "name": "security", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you. To protect your account, I need to ask you two security questions. First, what is your date of birth?"},
        "task_message": SECURITY_TASK,
        "tools": [api_tool("verify_identity",
                           "Check one security answer. CALL it once for every answer the customer gives: field date_of_birth with the date as YYYY-MM-DD, or field phone_last4 with four digits.",
                           {"customer_id": cid(),
                            "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                                      "description": "Which question this answers. One of: date_of_birth, phone_last4."},
                            "answer": {"type": "string", "default": "{{answer}}",
                                       "description": "date_of_birth as YYYY-MM-DD (numbers only are day, month, year); phone_last4 as four digits."}},
                           ["field", "answer"], post_hook=VERIFY_HOOK)],
        "max_node_turns": 16, "max_turn_transition": "close:declined",
        "transitions": [
            {"target_node": "load_account", "description": "Both security answers verified",
             "condition": when(var("verify_identity_response.data.all_verified", "equals", "true"),
                               var("verify_identity_response.data.all_verified", "equals", "True"))},
            {"target_node": "close:failed", "description": "No wrong answers left",
             "condition": when(var("verify_identity_response.data.wrong_answers_left", "equals", "0"))},
            tc("close:declined", "The customer refused the security questions a second time, or asked a second time what the call is about instead of answering, or said twice they do not want to talk."),
            tc("transfer_general", "The customer insists on speaking to a human after you asked once whether you can help."),
        ],
    },
    "load_account": {
        "name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare",
        "on_enter": {"type": "tts", "text": "Thank you, your identity is confirmed."}, "disable_inactivity_monitor": True,
        "pre_actions": [api_tool("get_account", "Get the late products.", {"customer_id": cid()}, [], retries=2)],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [
            {"target_node": "prepare", "description": "The account was loaded",
             "condition": when(var("load_account_success_count", "greater_than", 0))},
            {"target_node": "close:account_error", "description": "always", "condition": {"operator": "always"}},
        ],
    },
    "prepare": code_node("prepare", PREPARE_CODE, [
        {"target_node": "close:account_error", "description": "No product could be read",
         "condition": when(var("products_state", "not_equals", "ready"))},
        {"target_node": "item:first", "description": "always", "condition": {"operator": "always"}},
    ], "item:first"),
    "negotiate": {
        "name": "negotiate", "node_type": "conversation",
        "task_message": NEGOTIATE_TASK,
        "tools": [promise_tool()],
        "extraction_schema": [{
            "name": "refused_{i}_{a}", "type": "string", "enum_values": ["yes", "no"], "min_confidence": 0.6,
            "description": ("yes only when the customer's latest message flatly refuses the agent's current offer or gives a non-answer to it, "
                            "with no date and no amount of their own: for example a plain no to paying today, a no to the floor amount, "
                            "or a no to the deadline after asking for a later date. "
                            "no in every other case: the customer names any date or amount, says yes, asks a question, changes a value at the read-back, "
                            "says the amount is too much (before the floor was offered), mentions illness, a death in the family or job loss, "
                            "says they already paid, disputes the debt, asks for a plan or a human."),
        }],
        "max_node_turns": 20, "max_turn_transition": "close:refused",
        "transitions": [
            {"target_node": "item:next", "description": "The promise for this product is recorded",
             "condition": when(var("promise_id_{i}", "is_set"))},
            {"target_node": "close:service_error", "description": "create_promise failed twice",
             "condition": when(var("create_promise_failure_count", "greater_than", 1))},
            tc("transfer_support", "The customer mentioned hardship and accepted to be connected with the customer support team."),
            tc("close:hardship", "The customer mentioned hardship and declined the customer support team."),
            tc("close:paid", "The customer says they already paid this past-due amount."),
            tc("close:dispute", "The customer says the debt or product is not theirs, or was closed or paid off in the past."),
            tc("transfer_restructuring", "The customer asks for a new payment plan or lower instalments."),
            tc("transfer_general", "The customer insists on speaking to a human after you asked once whether you can help."),
            tc("close:refused", "The customer said for the second time that they do not want to talk."),
        ],
    },
    "transfer_support": transfer_node("transfer_support", "support",
                                      "One moment, I am connecting you with our customer support team.", "close:transferred_support"),
    "transfer_restructuring": transfer_node("transfer_restructuring", "restructuring",
                                            "One moment, I am connecting you with a colleague who can talk about this.", "close:transferred_restructuring"),
    "transfer_general": transfer_node("transfer_general", "general",
                                      "One moment, I am connecting you with a colleague.", "close:transferred_human"),
}

body = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

BYE = "Thank you for your time. Goodbye."


def ev(quote, source=BRIEF):
    return [{"source": source, "quote": quote}]


plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]},
    "fields": {"customer_id": "{{customer_id}}"},
    "closings": {
        "promise": {"set": {"outcome": "promise"}, "say": "Your payment promise is recorded. You will receive a text message confirming this promise. " + BYE,
                    "evidence": ev("Outcome: promise; Reason: none; When: at least one promise was recorded")},
        "paid": {"set": {"outcome": "paid"}, "say": "Thank you. Payments can take one business day to appear. " + BYE,
                 "evidence": ev("\"I already paid\": say that payments can take one business day to appear, take no promise, and close as `paid`.")},
        "transferred_support": {"set": {"outcome": "transferred", "reason": "support"}, "say": BYE,
                                "evidence": ev("call `transfer_to_agent` with queue `support` and close as `transferred` / `support`.")},
        "transferred_restructuring": {"set": {"outcome": "transferred", "reason": "restructuring"}, "say": BYE,
                                      "evidence": ev("Call `transfer_to_agent` with queue `restructuring` and close as `transferred` / `restructuring`.")},
        "transferred_human": {"set": {"outcome": "transferred", "reason": "human"}, "say": BYE,
                              "evidence": ev("call `transfer_to_agent` with queue `general` and close as `transferred` / `human`.")},
        "transfer_failed": {"set": {"outcome": "no_promise", "reason": "service_error"},
                            "say": "I am sorry, I could not connect you right now. You can call Freya Bank customer service. " + BYE,
                            "evidence": ev("If it fails again, say you could not record it and close as `no_promise` / `service_error`.")},
        "refused": {"set": {"outcome": "no_promise", "reason": "refused"}, "say": BYE,
                    "evidence": ev("Close as `no_promise` / `refused`.")},
        "hardship": {"set": {"outcome": "no_promise", "reason": "hardship"}, "say": BYE,
                     "evidence": ev("If they decline, close as `no_promise` / `hardship`.")},
        "dispute": {"set": {"outcome": "no_promise", "reason": "dispute"}, "say": "I understand. " + BYE,
                    "evidence": ev("Close as `no_promise` / `dispute`.")},
        "service_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                          "say": "I am sorry, I could not record your promise because of a technical problem. " + BYE,
                          "evidence": ev("If it fails again, say you could not record it and close as `no_promise` / `service_error`.")},
        "account_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                          "say": "I am sorry, I cannot reach your account details right now because of a technical problem. " + BYE,
                          "evidence": ev("If it fails again, say you could not record it and close as `no_promise` / `service_error`.")},
        "failed": {"set": {"outcome": "not_verified", "reason": "failed"},
                   "say": "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. " + BYE,
                   "evidence": ev("Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`.")},
        "declined": {"set": {"outcome": "not_verified", "reason": "declined"}, "say": "I understand. " + BYE,
                     "evidence": ev("If they still decline, close as `not_verified` / `declined`.")},
        "callback": {"set": {"outcome": "not_reached", "reason": "callback"}, "say": "Thank you, we will call back then. Goodbye.",
                     "evidence": ev("Call `schedule_callback` with the date and the time, then close as `not_reached` / `callback`.")},
        "no_callback": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "say": BYE,
                        "evidence": ev("If that is also outside it, do not schedule. Close as `not_reached` / `no_callback`.")},
        "callback_failed": {"set": {"outcome": "not_reached", "reason": "no_callback"},
                            "say": "I am sorry, I could not book the callback. " + BYE,
                            "evidence": ev("If that is also outside it, do not schedule. Close as `not_reached` / `no_callback`.")},
        "wrong_number": {"set": {"outcome": "not_reached", "reason": "wrong_number"}, "say": "I am sorry for the trouble. " + BYE,
                         "evidence": ev("If the person says the number does not belong to the customer, close as `not_reached` / `wrong_number`.")},
        "deceased": {"set": {"outcome": "not_reached", "reason": "deceased"}, "say": "I am sorry for your loss. Thank you. Goodbye.",
                     "evidence": ev("say \"I am sorry for your loss.\", ask nothing else, and close as `not_reached` / `deceased`.")},
        "unclear": {"set": {"outcome": "not_reached", "reason": "unclear"}, "say": BYE,
                    "evidence": ev("If it is still unclear after the second ask, close as `not_reached` / `unclear`.")},
    },
    "precedence": [{
        "closing": "promise",
        "when": [{"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}],
        "keep": ["transferred_support", "transferred_restructuring", "transferred_human"],
        "evidence": ev("If a transfer follows a recorded promise, close as `transferred` with that transfer's reason."),
    }],
    "ladder": {
        "template": "negotiate", "done": "close:refused",
        "items": {"count": "item_count", "max": 3, "evidence": ev("One promise per product.")},
        "attempts": {"allowed": "allowed_{i}", "max": 3, "evidence": ev("Persuasion attempts: 3")},
        "refusal": "refused_{i}_{a}",
    },
}

slot = "pl-g3-limits-raw"
(OUT / f"{slot}.body.json").write_text(json.dumps(body, indent=1) + "\n")
(OUT / f"{slot}.plan.json").write_text(json.dumps(plan, indent=1) + "\n")
print("ok")
