"""Generate out/pl-g5-memo-raw.workflow.json from the rules of briefs/pl-g5-memo-raw.md.

Effective policy (the memo OM-3 of 3 February 2026 predates the CP-4 extract of 2 March 2026 and is replaced by it;
memo OM-17 of 9 October 2026 changes the extract):
  - callbacks: today or the next business day, 09:00 to 17:00 inclusive, later than `now`
  - deadline: early band (1-7 days late) 12th business day after today; late band (8-45) 6th business day
"""
import json
import pathlib

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
SLOT = "pl-g5-memo-raw"

# ------------------------------------------------------------------ code shared by code steps

DATE_HELPERS = r'''
import datetime
import json
import re
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
def parse_now(raw):
    raw = str(raw or '').strip().replace(' ', 'T')
    try:
        return datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        return datetime.datetime.fromisoformat(raw[:10] + 'T00:00')
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def kind(d):
    if d.isoformat() in HOL:
        return 'bank holiday, not a business day'
    if d.weekday() >= 5:
        return 'weekend, not a business day'
    return 'business day'
def nth_bd(start, n):
    d = start
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
def fmt(d):
    return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + d.strftime('%B %Y') + ' (' + d.isoformat() + ')'
def last_bd_of_week(monday):
    d = monday + datetime.timedelta(days=4)
    while d >= monday and not isbd(d):
        d = d - datetime.timedelta(days=1)
    return d if d >= monday else None
NOW = parse_now(vars.get('now'))
TODAY = NOW.date()
MONDAY = TODAY - datetime.timedelta(days=TODAY.weekday())
'''

SETUP_CODE = DATE_HELPERS + r'''
try:
    vars['today_text'] = fmt(TODAY) + ', ' + kind(TODAY)
    vars['now_time'] = NOW.strftime('%H:%M')
    lines = []
    for i in range(0, 35):
        d = TODAY + datetime.timedelta(days=i)
        lines.append(fmt(d) + ': ' + kind(d) + (' (today)' if i == 0 else ''))
    vars['calendar_text'] = '\n'.join(lines)
    words = []
    for i in range(7):
        this_d = MONDAY + datetime.timedelta(days=i)
        next_d = this_d + datetime.timedelta(days=7)
        words.append('"this ' + DAYS[i] + '" = ' + fmt(this_d) + ('' if this_d >= TODAY else ' (already past)') + '; "next ' + DAYS[i] + '" = ' + fmt(next_d))
    vars['weekday_words_text'] = '\n'.join(words)
    slots = []
    start = datetime.datetime.combine(TODAY, datetime.time(9, 0))
    end = datetime.datetime.combine(TODAY, datetime.time(17, 0))
    if NOW < end:
        first = start if NOW < start else NOW + datetime.timedelta(minutes=1)
        slots.append('today, ' + fmt(TODAY) + ', from ' + first.strftime('%H:%M') + ' to 17:00')
    nb = next_bd(TODAY)
    slots.append(fmt(nb) + ', from 09:00 to 17:00')
    vars['callback_slots_text'] = '; or '.join(slots)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['setup_state'] = 'error'
    vars['today_text'] = str(vars.get('now'))
    vars['now_time'] = ''
    vars['calendar_text'] = 'not available'
    vars['weekday_words_text'] = 'not available'
    vars['callback_slots_text'] = 'today or the next business day, from 09:00 to 17:00, later than now (' + str(vars.get('now')) + ')'
'''

ACCOUNT_CODE = DATE_HELPERS + r'''
def money(x):
    try:
        v = float(x)
    except Exception:
        return str(x)
    return ('%.2f' % v) if abs(v - round(v)) > 1e-9 else str(int(round(v)))
def products_from_vars():
    for key in ('products', 'load_account_response.data.products'):
        p = vars.get(key)
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = None
        if isinstance(p, dict):
            p = [p]
        if isinstance(p, list) and p:
            return [x for x in p if isinstance(x, dict)]
    resp = vars.get('load_account_response')
    if isinstance(resp, dict):
        d = resp.get('data')
        if isinstance(d, dict) and isinstance(d.get('products'), list) and d.get('products'):
            return [x for x in d.get('products') if isinstance(x, dict)]
    pat = re.compile(r'^(?:products|load_account_response\.data\.products)(?:\.|\[)(\d+)\]?\.(\w+)$')
    found = dict()
    for k in list(vars.keys()):
        m = pat.match(str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    return [found[i] for i in sorted(found)]
try:
    prods = products_from_vars()
    p = prods[0]
    ptype = str(p.get('type') or '')
    if ptype == 'credit_card':
        words = 'credit card ending ' + str(p.get('card_last4') or '')
        floor = p.get('minimum_payment')
        floor_name = 'the minimum payment'
    elif ptype == 'car_loan':
        words = 'car loan'
        floor = p.get('instalment_amount')
        floor_name = 'one instalment'
    else:
        words = 'personal loan'
        floor = p.get('instalment_amount')
        floor_name = 'one instalment'
    days_late = int(float(p.get('days_late')))
    past_due = float(p.get('past_due'))
    if days_late <= 7:
        band = 'early'
        deadline = nth_bd(TODAY, 12)
        attempts = 1
    else:
        band = 'late'
        deadline = nth_bd(TODAY, 6)
        attempts = 2
    valid = []
    d = TODAY
    while d <= deadline:
        if isbd(d):
            valid.append(fmt(d))
        d = d + datetime.timedelta(days=1)
    lb = last_bd_of_week(MONDAY)
    if lb is None or lb <= TODAY:
        lb = last_bd_of_week(MONDAY + datetime.timedelta(days=7))
    if lb > deadline:
        lb = deadline
    vars['product_words'] = words
    vars['product_type'] = ptype
    vars['product_id_text'] = str(p.get('product_id') or '')
    if len(prods) == 1 and p.get('product_id'):
        vars['product_id'] = str(p.get('product_id'))
    vars['past_due_text'] = money(past_due)
    vars['floor_text'] = money(floor)
    vars['floor_name'] = floor_name
    vars['days_late'] = str(days_late)
    vars['band'] = band
    vars['attempts'] = str(attempts)
    vars['deadline_text'] = fmt(deadline)
    vars['deadline_iso'] = deadline.isoformat()
    vars['valid_dates_text'] = '\n'.join(valid) if valid else 'none'
    vars['attempt1_text'] = fmt(lb)
    vars['today_is_business_day'] = 'yes' if isbd(TODAY) else 'no'
    other = ''
    if len(prods) > 1:
        other = ' Other late products in the record: ' + '; '.join(str(x.get('type')) + ' ' + str(x.get('product_id')) + ' past due ' + money(x.get('past_due')) for x in prods[1:])
    vars['other_products_text'] = other
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_state'] = 'error'
'''

# ------------------------------------------------------------------ tool builders

HEADERS = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}


def api_tool(name, path, description, body_props, required, post_hook="", max_retries=0):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(body_props)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": BASE + path},
                    "method": {"type": "string", "default": "POST"},
                    "headers": HEADERS,
                    "body": {"type": "object", "properties": props, "required": required},
                },
            },
        },
    }
    if post_hook:
        t["post_process_code"] = post_hook
    return t


def hook(body):
    """A post-hook that drops headers and adds a what_to_do_next line built from `d` (the API body)."""
    return (
        "try:\n"
        "    if isinstance(result, dict):\n"
        "        result.pop('header', None)\n"
        "        d = result.get('data')\n"
        "        if not isinstance(d, dict):\n"
        "            d = dict()\n"
        "            result['data'] = d\n"
        "            d['ok'] = False\n"
        "            d['error'] = 'service failure'\n"
        + "\n".join("        " + line for line in body.strip("\n").split("\n")) + "\n"
        "except Exception:\n"
        "    pass\n"
    )


VERIFY_HOOK = hook(r'''
left = d.get('wrong_answers_left')
if d.get('hint') == 'day_month_swapped':
    msg = 'The day and the month seem to be the other way round. Ask the customer to say the month of their birth as a word, then call the tool again. This retry is not counted as a wrong answer.'
elif d.get('all_verified') is True:
    msg = 'Both security answers are correct.'
elif d.get('verified') is True:
    msg = 'Correct. Ask the next security question.'
elif d.get('ok') is False and not (isinstance(left, int) and left <= 0):
    msg = 'The answer could not be checked (' + str(d.get('error') or 'not readable') + '). It is not counted as a wrong answer. Ask the customer to say it again.'
elif isinstance(left, int) and left <= 0:
    msg = 'Three wrong answers. The identity check has failed. Do not state any account detail.'
else:
    msg = 'Wrong answer. Wrong answers left: ' + str(left) + '. Say that it does not match our records and ask the same question again.'
d['what_to_do_next'] = msg
''')

PROMISE_HOOK = hook(r'''
if d.get('ok') is True:
    d['what_to_do_next'] = 'The promise is recorded.'
else:
    d['what_to_do_next'] = 'The promise was NOT recorded (' + str(d.get('error') or 'error') + '). Never say it is recorded. If this is the first failure, call create_promise once more now with the same amount and date.'
''')

CALLBACK_HOOK = hook(r'''
if d.get('ok') is True:
    d['what_to_do_next'] = 'The callback is booked.'
else:
    d['what_to_do_next'] = 'The callback was NOT booked (' + str(d.get('error') or 'error') + '). Never say it is booked. If this is the first failure, call schedule_callback once more with the same date and time. If it failed twice, say you could not book the callback and call transition_to_farewell_no_callback.'
''')

TRANSFER_HOOK = hook(r'''
if d.get('ok') is True:
    d['what_to_do_next'] = 'The transfer is done.'
else:
    d['what_to_do_next'] = 'The transfer did NOT go through (' + str(d.get('error') or 'error') + '). Never say the customer is being connected. If this is the first failure, call the same transfer tool once more. If it failed twice, tell the customer you could not connect them.'
''')


def verify_tool(name, field, answer_desc):
    return api_tool(
        name, "/verify_identity",
        "Check the customer's " + ("date of birth" if field == "date_of_birth" else "last four phone digits")
        + ". CALL it every time the customer gives an answer to this question, one call per answer.",
        {
            "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": field},
            "answer": {"type": "string", "default": "{{answer}}", "description": answer_desc},
        },
        ["customer_id", "field", "answer"], VERIFY_HOOK)


DOB_DESC = ("The date of birth as YYYY-MM-DD, whatever way the customer said it. Convert words to digits. "
            "A date given only as numbers is read as day, then month, then year (for example 03/07/1985 is 1985-07-03).")
PHONE_DESC = "Exactly four digits, the last four digits of the phone number on file, as the customer said them."


def transfer_tool(name, queue, trigger):
    return api_tool(
        name, "/transfer_to_agent", trigger,
        {"queue": {"type": "string", "enum": ["restructuring", "general", "support"], "default": queue}},
        ["customer_id", "queue"], TRANSFER_HOOK)


TRANSFER_HUMAN = transfer_tool(
    "transfer_human", "general",
    "Hand the call to a person (general queue). CALL it only when the customer asked for a human, you asked once whether you can help instead, and they still insist. "
    "In the same message tell them you are connecting them now.")
TRANSFER_SUPPORT = transfer_tool(
    "transfer_support", "support",
    "Hand the call to the customer support team. CALL it only when the customer mentioned illness, a death in the family or job loss, you offered the support team and they accepted. "
    "In the same message tell them you are connecting them now.")
TRANSFER_RESTRUCTURING = transfer_tool(
    "transfer_restructuring", "restructuring",
    "Hand the call to the restructuring team. CALL it when the customer asks for a new payment plan or lower instalments. Do not describe any plan. "
    "In the same message tell them you are connecting them now.")

CREATE_PROMISE = api_tool(
    "create_promise", "/create_promise",
    "Record the payment promise. CALL it only after you read back the product, the amount and the date, asked \"Do you confirm?\" and the customer gave a clear yes.",
    {
        "product_id": {"type": "string", "default": "{{product_id}}", "description": "The product_id from the facts, copied unchanged."},
        "amount": {"type": "number", "default": "{{amount}}", "description": "The agreed amount, a number, from the floor up to the full past-due amount."},
        "date": {"type": "string", "default": "{{date}}", "description": "The agreed payment date as YYYY-MM-DD. Must be one of the valid promise dates."},
    },
    ["customer_id", "product_id", "amount", "date"], PROMISE_HOOK)

SCHEDULE_CALLBACK = api_tool(
    "schedule_callback", "/schedule_callback",
    "Book a callback for the customer. CALL it as soon as the person on the line names a day and time inside the allowed callback window.",
    {
        "date": {"type": "string", "default": "{{date}}", "description": "Callback date as YYYY-MM-DD: today or the next business day."},
        "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24 hour, from 09:00 to 17:00 and later than now."},
    },
    ["customer_id", "date", "time"], CALLBACK_HOOK)


def is_true(var):
    return {"logic": "or", "conditions": [
        {"variable": var, "operator": "equals", "operand": "true"},
        {"variable": var, "operator": "equals", "operand": "True"}]}


def var_cond(var, op, operand=None):
    c = {"variable": var, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return {"logic": "or", "conditions": [c]}


def to(target, desc, cond):
    return {"target_node": target, "description": desc, "condition": cond}


def tool_to(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


TRANSFER_ROUTES = [
    to("farewell_transferred_human", "The transfer to a person succeeded", is_true("transfer_human_response.data.ok")),
]
ALL_TRANSFER_ROUTES = TRANSFER_ROUTES + [
    to("farewell_transferred_support", "The transfer to support succeeded", is_true("transfer_support_response.data.ok")),
    to("farewell_transferred_restructuring", "The transfer to restructuring succeeded", is_true("transfer_restructuring_response.data.ok")),
]

# ------------------------------------------------------------------ prompts

SYSTEM_PROMPT = """You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is calling the customer. Speak English. Keep every turn to one or two short sentences. Ask one question at a time.

Call facts: customer {{title}} {{first_name}} {{last_name}}. Current date and time: {{now}} ({{today_text}}). All date rules use this date, never the real clock.

Rules that hold in every step:
- Until both security answers have been verified, never say "collections", "debt", "payment", "late", "amount" or the product, and never say why you are calling. This applies to everyone, including relatives.
- If someone asks whether you are a robot or an AI, say that you are Freya Bank's digital assistant, then continue with the current question.
- If someone asks "Is this a scam?", say they can verify this call by phoning Freya Bank's customer service number, then continue with the current question.
- If you are asked something you cannot answer from the tool results and the facts given to you, say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any other term.
- When a rule says to use a tool, call the tool. Saying that you did something is not doing it. Call one tool per message.
- After every tool result, follow its what_to_do_next and speak to the customer or call the next tool. Never end a turn with nothing.
- Never say something is recorded, booked or transferred unless the tool result says it worked.
- Tools named transition_to_farewell_... end the call: a fixed thank-you and goodbye is spoken for you after them. Call such a tool only when the rule says so, with no other tool in that message."""

OPENING_TASK = """You are on the line and have just introduced yourself and asked "Am I speaking with {{title}} {{last_name}}?". Find out who is on the line. Do not call any bank tool in this step except transfer_human.

- Only "yes", "that's me", "speaking" or the customer's own name confirms that the customer is on the line. "Hello", "go ahead" and "who is this" do not.
- If the answer does not confirm, ask "Am I speaking with {{title}} {{last_name}}?" once more. If the person asked a question (robot, AI, scam, who is calling), answer it in one sentence first; the ask that follows is the second ask. If it is still unclear after the second ask, call transition_to_farewell_unclear.
- Say nothing about why you are calling.
- If the person says this number does not belong to {{title}} {{last_name}} (wrong number), call transition_to_farewell_wrong_number.
- If the person says {{title}} {{last_name}} has died, call transition_to_farewell_deceased and say nothing yourself.
- If the person says twice that they do not want to talk, call transition_to_farewell_declined.
- If the person asks for a human: ask once whether you can help first. If they insist, call transfer_human."""

SOMEONE_ELSE_TASK = """The person on the line is not {{title}} {{last_name}}. Do not say why you are calling and say nothing about any account, even if they ask, offer to pay or say they are family. Do not ask them any security question. Ask when {{title}} {{last_name}} can be reached.

Allowed callback window: {{callback_slots_text}}. A callback must be today or the next business day, from 09:00 to 17:00 (both included), and later than now ({{now_time}}).
Calendar:
{{calendar_text}}

- When the person names a day and time inside the window, call schedule_callback with the date (YYYY-MM-DD) and the time (HH:MM, 24 hour). Do not read the booking back as done until the result says ok.
- If the person offers a day or time outside the window, say when callbacks are possible and ask once for another time. If the second answer is also outside the window, or they cannot give a time, do not book: call transition_to_farewell_no_callback.
- If the person says the number does not belong to the customer, call transition_to_farewell_wrong_number.
- If the person says the customer has died, call transition_to_farewell_deceased and say nothing yourself.
- If the person says that {{title}} {{last_name}} is now on the line or hands over the phone, call transition_to_opening."""

DOB_TASK = """{{title}} {{last_name}} confirmed who they are. You have asked for their date of birth as the first security question. You still may not say why you are calling.

- When the customer gives a date of birth, call verify_dob with it converted to YYYY-MM-DD. A date given only as numbers is day, then month, then year. Then follow what_to_do_next.
- A wrong answer may be asked again. Three wrong answers in total end the check.
- If the customer will not answer, or asks what the call is about instead of answering: the first time, explain that these questions protect their account and ask again. The second time (a second refusal or a second such question), call transition_to_farewell_declined.
- If the customer says twice that they do not want to talk, call transition_to_farewell_declined.
- If the customer asks for a human: ask once whether you can help first. If they insist, call transfer_human."""

PHONE_TASK = """The date of birth is verified. You have asked for the last four digits of the phone number on file. You still may not say why you are calling.

- When the customer gives four digits, call verify_phone with them. Then follow what_to_do_next.
- Wrong answers count together with any wrong date of birth: three in total end the check.
- If the customer will not answer, or asks what the call is about instead of answering: if you have not yet explained in this call that the questions protect their account, explain it once and ask again. Otherwise call transition_to_farewell_declined.
- If the customer says twice that they do not want to talk, call transition_to_farewell_declined.
- If the customer asks for a human: ask once whether you can help first. If they insist, call transfer_human."""

NEGOTIATE_TASK = """The customer is verified. You have stated the debt and asked "Can you make this payment today?". Your job: get a payment promise where you can, within the rules below.

FACTS (computed by the bank, use them exactly)
- Product: {{product_words}} (product_id {{product_id_text}}).{{other_products_text}}
- Full past-due amount: {{past_due_text}}. Floor amount: {{floor_text}} ({{floor_name}}).
- Days late: {{days_late}}. Band: {{band}}. Persuasion attempts allowed: {{attempts}}.
- Today: {{today_text}}.
- Deadline, the latest date you can record: {{deadline_text}}.
- Valid promise dates (today or later, business days, not after the deadline):
{{valid_dates_text}}
- Attempt 1 date: {{attempt1_text}}.
- Weekday words ("next <weekday>" is in the following calendar week, "this <weekday>" in the current week):
{{weekday_words_text}}
- Calendar:
{{calendar_text}}

TOOLS
- create_promise: only after the read-back and a clear yes.
- transfer_restructuring, transfer_support, transfer_human: only as the rules below say.
- transition_to_farewell_refused, transition_to_farewell_hardship, transition_to_farewell_dispute, transition_to_farewell_paid, transition_to_farewell_service_error: end the call as the rules say.

AMOUNTS
- Ask for the full past-due amount first. Never ask "how much can you pay?". You propose every amount.
- If the customer says the full amount is too much: offer the floor amount, once, and say the rest stays overdue. If they refuse the floor, that is a flat refusal.
- If the customer proposes an amount from {{floor_text}} up to {{past_due_text}}, both included, accept it. Below {{floor_text}}: say it cannot be recorded and offer the floor once; if they do not accept the floor, that is a flat refusal. Above {{past_due_text}}: the amount is {{past_due_text}}.

DATES
- A promise date must be one of the valid promise dates above.
- If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day.
- If the customer asks for a date after the deadline, say the latest date you can record is {{deadline_text}} and offer it. If they refuse the deadline, that is a flat refusal.
- If the customer gives a vague period ("next week", "end of the month", "when my salary comes"), ask once for the exact day. If they still give none, propose the deadline.
- A "yes" to paying today means today, if today is a valid promise date.
- A date or an amount the customer proposes is never a refusal. Handle it with these rules.

FLAT REFUSALS AND PERSUASION
- A flat refusal or a non-answer uses one persuasion attempt. A no to paying today with no date and no amount is a flat refusal.
- Attempt 1: propose the full past-due amount (or the floor if the customer already said the full amount is too much) on {{attempt1_text}}.
- Attempt 2, only when attempts allowed is 2: propose the floor amount {{floor_text}} on the deadline {{deadline_text}}.
- When a flat refusal comes and all {{attempts}} attempt(s) are used, stop. Do not repeat an offer the customer already refused. Call transition_to_farewell_refused.
- If the customer says twice that they do not want to talk, call transition_to_farewell_refused.

CONFIRMING
- Read back the product, the amount and the date, and ask "Do you confirm?". Call create_promise only after a clear yes.
- If the customer changes the date or the amount at this point, check the new value against these rules and read it back again.
- If create_promise fails, call it once more with the same values. Never say the promise is recorded unless the result says ok.

OTHER SITUATIONS (these come before persuasion)
- Illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_support. If they decline, call transition_to_farewell_hardship. If they still name a date or an amount themselves, record that promise under these rules.
- "I already paid" (this past-due amount): say that payments can take one business day to appear, take no promise, and call transition_to_farewell_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise, call transition_to_farewell_dispute.
- A request for a new payment plan or lower instalments: do not describe any plan; call transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_human.
- If a transfer fails twice, say you could not connect them. After a failed support transfer call transition_to_farewell_hardship; after a failed restructuring transfer call transition_to_farewell_service_error; after a failed human transfer continue helping."""

PROMISE_DONE_TASK = """The promise is recorded and you have said "You will receive a text message confirming this promise." and asked whether there is anything else.

- If the customer has nothing else, or says thanks or goodbye, call transition_to_farewell_promise.
- If they want to change or cancel the promise, say it cannot be changed in this call and they can change it in the mobile app. Then ask whether there is anything else.
- A request for a new payment plan or lower instalments: call transfer_restructuring. Illness, a death in the family or job loss: one sentence of sympathy, offer the customer support team, and call transfer_support if they accept. A request for a human: ask once whether you can help, and call transfer_human if they insist.
- If a transfer fails twice, say you could not connect them and call transition_to_farewell_promise.
- Do not take another promise."""

# ------------------------------------------------------------------ closings

# farewell id -> (spoken farewell, close step)
FAREWELLS = {
    "farewell_promise": ("Thank you for your time, {{title}} {{last_name}}. Goodbye.", "close_promise"),
    "farewell_paid": ("Thank you for letting me know. Payments can take one business day to appear. Thank you for your time. Goodbye.", "close_paid"),
    "farewell_transferred_restructuring": ("Thank you for your time. Goodbye.", "close_transferred_restructuring"),
    "farewell_transferred_human": ("Thank you for your time. Goodbye.", "close_transferred_human"),
    "farewell_transferred_support": ("Thank you for your time, and take care. Goodbye.", "close_transferred_support"),
    "farewell_refused": ("Thank you for your time. Goodbye.", "close_no_promise_refused"),
    "farewell_hardship": ("Thank you for your time, and take care. Goodbye.", "close_no_promise_hardship"),
    "farewell_dispute": ("Thank you for letting me know. Thank you for your time. Goodbye.", "close_no_promise_dispute"),
    "farewell_service_error": ("Thank you for your time. Goodbye.", "close_no_promise_service_error"),
    "farewell_promise_error": ("I am sorry, I could not record your promise because of a technical problem. Thank you for your time. Goodbye.", "close_no_promise_service_error"),
    "farewell_account_error": ("I am sorry, I cannot reach your account details right now because of a technical problem. Thank you for your time. Goodbye.", "close_no_promise_service_error"),
    "farewell_failed": ("I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye.", "close_not_verified_failed"),
    "farewell_declined": ("I understand. Thank you for your time. Goodbye.", "close_not_verified_declined"),
    "farewell_callback": ("Thank you, we will call back then. Goodbye.", "close_not_reached_callback"),
    "farewell_no_callback": ("Thank you for your time. Goodbye.", "close_not_reached_no_callback"),
    "farewell_wrong_number": ("Sorry for the inconvenience. Thank you for your time. Goodbye.", "close_not_reached_wrong_number"),
    "farewell_deceased": ("I am sorry for your loss. Thank you for your time. Goodbye.", "close_not_reached_deceased"),
    "farewell_unclear": ("Thank you for your time. Goodbye.", "close_not_reached_unclear"),
}

CLOSES = {
    "close_promise": ("promise", None),
    "close_paid": ("paid", None),
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

FAREWELL_DESC = {
    "farewell_promise": "The customer has nothing else after the recorded promise",
    "farewell_paid": "The customer says they already paid this past-due amount",
    "farewell_refused": "The customer flatly refused and all persuasion attempts are used, or said twice they do not want to talk",
    "farewell_hardship": "The customer mentioned illness, a death in the family or job loss and declined the support team",
    "farewell_dispute": "The customer says the debt or product is not theirs, or was closed or paid off in the past",
    "farewell_service_error": "A bank tool failed twice and nothing could be recorded",
    "farewell_declined": "The customer refused the security questions twice or said twice they do not want to talk, before verification",
    "farewell_no_callback": "No callback time inside the window was given after asking twice, or booking failed twice",
    "farewell_wrong_number": "The person says the number does not belong to the customer",
    "farewell_deceased": "The person says the customer has died",
    "farewell_unclear": "It is still unclear who is on the line after asking twice",
}


def end_node():
    return {
        "name": "hang_up", "node_type": "end_call", "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True, "transitions": [],
        "terminal": {"type": "function", "function": {
            "name": "call_closed", "handler": "__function__:end_call",
            "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
    }


def close_node(key, outcome, reason):
    body = {"outcome": {"type": "string", "enum": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"], "default": outcome}}
    if reason:
        body["reason"] = {"type": "string", "default": reason}
    tool = api_tool("close_call", "/close_call", "End the call record.", body, ["customer_id", "outcome"], max_retries=2)
    return {
        "name": key, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "hang_up",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [tool],
        "transitions": [to("hang_up", "always", {"operator": "always"})],
    }


def farewell_node(key, text, close):
    return {
        "name": key, "node_type": "conversation", "passthrough": True, "passthrough_default_transition": close,
        "on_enter": {"type": "tts", "text": text}, "disable_inactivity_monitor": True,
        "task_message": "Say goodbye. Do not call any tool in this turn.",
        "transitions": [to(close, "always", {"operator": "always"})],
    }


def code_node(key, code, transitions, default):
    return {
        "name": key, "node_type": "code", "passthrough": True, "passthrough_default_transition": default,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {
            "name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {
                "code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": transitions,
    }


def conv(key, task, tools, transitions, on_enter, max_turns, cap_target, extraction=None):
    n = {
        "name": key, "node_type": "conversation", "task_message": task, "tools": tools,
        "on_enter": on_enter, "on_enter_first_entry_only": False,
        "transitions": transitions, "max_node_turns": max_turns, "max_turn_transition": cap_target,
    }
    if extraction:
        n["extraction_schema"] = extraction
    return n


def build():
    nodes = {}
    nodes["setup"] = code_node("setup", SETUP_CODE, [to("opening", "always", {"operator": "always"})], "opening")

    nodes["opening"] = conv(
        "opening", OPENING_TASK, [TRANSFER_HUMAN],
        [
            to("ask_dob", "The customer confirmed they are on the line", var_cond("line_status", "equals", "confirmed")),
            to("someone_else", "Someone other than the customer answered", var_cond("line_status", "equals", "someone_else")),
        ] + TRANSFER_ROUTES + [
            tool_to("farewell_unclear", FAREWELL_DESC["farewell_unclear"]),
            tool_to("farewell_wrong_number", FAREWELL_DESC["farewell_wrong_number"]),
            tool_to("farewell_deceased", FAREWELL_DESC["farewell_deceased"]),
            tool_to("farewell_declined", FAREWELL_DESC["farewell_declined"]),
        ],
        {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
        8, "farewell_unclear",
        extraction=[{
            "name": "line_status", "type": "string", "enum_values": ["confirmed", "someone_else"], "min_confidence": 0.7,
            "description": ("Who answered the assistant's question 'Am I speaking with {{title}} {{last_name}}?'. "
                            "confirmed: the person clearly said yes, that's me, speaking, or their own name ({{first_name}} or {{last_name}}). "
                            "someone_else: the person said they are not the customer but someone else, for example a relative, a partner or a colleague, or that the customer is not available. "
                            "Leave empty for a greeting, 'go ahead', 'who is this', a question, a wrong number, a death, or anything unclear."),
        }],
    )

    nodes["someone_else"] = conv(
        "someone_else", SOMEONE_ELSE_TASK, [SCHEDULE_CALLBACK],
        [
            to("farewell_callback", "The callback was booked", is_true("schedule_callback_response.data.ok")),
            tool_to("farewell_no_callback", FAREWELL_DESC["farewell_no_callback"]),
            tool_to("farewell_wrong_number", FAREWELL_DESC["farewell_wrong_number"]),
            tool_to("farewell_deceased", FAREWELL_DESC["farewell_deceased"]),
            tool_to("opening", "The customer has come to the phone"),
        ],
        {"type": "llm", "prompt": "Reply in one short sentence to what the person said and ask when {{title}} {{last_name}} can be reached. Do not say why you are calling. If they said the customer has died or that the number is wrong, call the matching transition tool instead."},
        12, "farewell_no_callback",
    )

    nodes["ask_dob"] = conv(
        "ask_dob", DOB_TASK, [verify_tool("verify_dob", "date_of_birth", DOB_DESC), TRANSFER_HUMAN],
        [
            to("ask_phone", "The date of birth was verified", is_true("verify_dob_response.data.verified")),
            to("farewell_failed", "Three wrong answers", var_cond("verify_dob_response.data.wrong_answers_left", "less_than", 1)),
        ] + TRANSFER_ROUTES + [tool_to("farewell_declined", FAREWELL_DESC["farewell_declined"])],
        {"type": "tts", "text": "Thank you. Before we continue, I need to ask two security questions. What is your date of birth?"},
        15, "farewell_declined",
    )

    nodes["ask_phone"] = conv(
        "ask_phone", PHONE_TASK, [verify_tool("verify_phone", "phone_last4", PHONE_DESC), TRANSFER_HUMAN],
        [
            to("load_account", "Both answers were verified", {"logic": "or", "conditions": [
                {"variable": "verify_phone_response.data.all_verified", "operator": "equals", "operand": "true"},
                {"variable": "verify_phone_response.data.all_verified", "operator": "equals", "operand": "True"},
                {"variable": "verify_phone_response.data.verified", "operator": "equals", "operand": "true"},
                {"variable": "verify_phone_response.data.verified", "operator": "equals", "operand": "True"}]}),
            to("farewell_failed", "Three wrong answers", var_cond("verify_phone_response.data.wrong_answers_left", "less_than", 1)),
        ] + TRANSFER_ROUTES + [tool_to("farewell_declined", FAREWELL_DESC["farewell_declined"])],
        {"type": "tts", "text": "Thank you. What are the last four digits of the phone number we have on file for you?"},
        15, "farewell_declined",
    )

    get_account = api_tool("get_account", "/get_account", "Get the late products.", {}, ["customer_id"], max_retries=2)
    nodes["load_account"] = {
        "name": "load_account", "node_type": "api_request", "passthrough": True,
        "passthrough_default_transition": "prepare_account", "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True, "pre_actions": [get_account],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [to("prepare_account", "always", {"operator": "always"})],
    }
    nodes["prepare_account"] = code_node(
        "prepare_account", ACCOUNT_CODE,
        [to("negotiate", "The account facts are ready", var_cond("account_state", "equals", "ok")),
         to("farewell_account_error", "always", {"operator": "always"})],
        "farewell_account_error")

    nodes["negotiate"] = conv(
        "negotiate", NEGOTIATE_TASK, [CREATE_PROMISE, TRANSFER_RESTRUCTURING, TRANSFER_SUPPORT, TRANSFER_HUMAN],
        [
            to("promise_recorded", "The promise was recorded", is_true("create_promise_response.data.ok")),
            to("farewell_promise_error", "Recording the promise failed twice", var_cond("create_promise_failure_count", "greater_than", 1)),
        ] + ALL_TRANSFER_ROUTES + [
            tool_to("farewell_refused", FAREWELL_DESC["farewell_refused"]),
            tool_to("farewell_hardship", FAREWELL_DESC["farewell_hardship"]),
            tool_to("farewell_dispute", FAREWELL_DESC["farewell_dispute"]),
            tool_to("farewell_paid", FAREWELL_DESC["farewell_paid"]),
            tool_to("farewell_service_error", FAREWELL_DESC["farewell_service_error"]),
        ],
        {"type": "tts", "text": "Thank you, you are verified. I am calling from the collections team about a late payment on your {{product_words}}. The past-due amount is {{past_due_text}}, and it is {{days_late}} days late. Can you make this payment today?"},
        40, "farewell_refused",
    )

    nodes["promise_recorded"] = conv(
        "promise_recorded", PROMISE_DONE_TASK, [TRANSFER_RESTRUCTURING, TRANSFER_SUPPORT, TRANSFER_HUMAN],
        ALL_TRANSFER_ROUTES + [tool_to("farewell_promise", FAREWELL_DESC["farewell_promise"])],
        {"type": "tts", "text": "Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
        8, "farewell_promise",
    )

    for key, (text, close) in FAREWELLS.items():
        nodes[key] = farewell_node(key, text, close)
    for key, (outcome, reason) in CLOSES.items():
        nodes[key] = close_node(key, outcome, reason)
    nodes["hang_up"] = end_node()

    return {
        "initial_node": "setup",
        "system_prompt": SYSTEM_PROMPT,
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    }


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parent.parent
    out = root / "out" / (SLOT + ".workflow.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(build(), indent=1))
    print(out)
