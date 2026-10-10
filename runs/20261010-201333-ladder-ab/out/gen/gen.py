"""Generate out/<slot>.body.json and out/<slot>.closing.json for brief-a and brief-b.

Run from the kit folder: python3 out/gen/gen.py
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "out"
BANK = "https://freya-bank-mock.freyavoice.workers.dev/v1"
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]  # brief A, section 7


# ------------------------------------------------------------------ helpers

def when(*checks):
    return {"logic": "or", "conditions": [checks[0] if len(checks) == 1 else {"logic": "and", "conditions": list(checks)}]}


def any_of(*alts):
    out = []
    for a in alts:
        out.append(a[0] if len(a) == 1 else {"logic": "and", "conditions": list(a)})
    return {"logic": "or", "conditions": out}


def v(name, op, operand=None):
    d = {"variable": name, "operator": op}
    if operand is not None:
        d["operand"] = operand
    return d


def is_true(name):
    return [[v(name, "equals", "true")], [v(name, "equals", "True")]]


def tr(target, desc, cond):
    return {"target_node": target, "description": desc, "condition": cond}


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def tool_tr(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def body_field(ftype, default, desc=None, enum=None):
    d = {"type": ftype, "default": default}
    if desc:
        d["description"] = desc
    if enum:
        d["enum"] = enum
    return d


def api_tool(name, path, fields, required, desc, retries=0):
    return {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": retries},
            "function": {"name": name, "handler": "__function__:api_call", "description": desc,
                         "parameters": {"type": "object", "properties": {
                             "url": {"type": "string", "default": BANK + path},
                             "method": {"type": "string", "default": "POST"},
                             "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                             "body": {"type": "object", "properties": fields, "required": required}}}}}


def code_node(name, code, nxt_transitions):
    return {"name": name, "node_type": "code", "passthrough": True,
            "passthrough_default_transition": nxt_transitions[-1]["target_node"],
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                                              "parameters": {"type": "object", "properties": {
                                                                  "code": {"type": "string", "default": code},
                                                                  "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": nxt_transitions}


def api_node(name, tool, transitions, mapping=None, say=None):
    return {"name": name, "node_type": "api_request", "passthrough": True,
            "passthrough_default_transition": transitions[-1]["target_node"],
            "on_enter": {"type": "tts", "text": say} if say else {"type": "silent"},
            "disable_inactivity_monitor": True, "pre_actions": [tool],
            "response_mapping": mapping or [], "transitions": transitions}


def router(name, transitions):
    return {"name": name, "node_type": "conversation", "passthrough": True,
            "passthrough_default_transition": transitions[-1]["target_node"],
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "task_message": "Do not call a tool in this turn.", "transitions": transitions}


def ext(name, desc, enum=None, etype="string", pattern=None, conf=0.6):
    d = {"name": name, "type": etype, "description": desc, "min_confidence": conf}
    if enum:
        d["enum_values"] = enum
    if pattern:
        d["validation_pattern"] = pattern
        d["max_retries"] = 1
    return d


# ------------------------------------------------------------------ code (no braces pairs, no comprehensions over locals)

DATE_CODE = """import datetime
HOL = __HOLIDAYS__
def _isbd(d, HOL=HOL):
    return d.weekday() < 5 and d.isoformat() not in HOL
def _say(d):
    return d.strftime('%A') + ' ' + str(d.day) + ' ' + d.strftime('%B %Y')
def _nth(start, n, isbd=_isbd, td=datetime.timedelta):
    d = start
    k = 0
    while k < n:
        d = d + td(days=1)
        if isbd(d):
            k += 1
    return d
def _lastbd(monday, isbd=_isbd, td=datetime.timedelta):
    for k in (4, 3, 2, 1, 0):
        d = monday + td(days=k)
        if isbd(d):
            return d
    return None
raw = str(vars.get('now') or '').strip()
try:
    now = datetime.datetime.strptime(raw[:16], '%Y-%m-%dT%H:%M')
except Exception:
    try:
        now = datetime.datetime.strptime(raw[:10], '%Y-%m-%d')
    except Exception:
        now = datetime.datetime.utcnow()
today = now.date()
monday = today - datetime.timedelta(days=today.weekday())
lbw = _lastbd(monday)
if lbw is None or lbw <= today:
    lbw = _lastbd(monday + datetime.timedelta(days=7))
dl_early = _nth(today, 12)
dl_late = _nth(today, 7)
nbd = _nth(today, 1)
"""

SETUP_CODE = DATE_CODE + """try:
    vars['today_iso'] = today.isoformat()
    vars['today_say'] = _say(today)
    vars['now_time'] = now.strftime('%H:%M')
    lines = []
    for k in range(0, 45):
        d = today + datetime.timedelta(days=k)
        if d.isoformat() in HOL:
            kind = 'bank holiday, NOT a business day'
        elif d.weekday() >= 5:
            kind = 'weekend, NOT a business day'
        else:
            kind = 'business day'
        wk = ''
        m = d - datetime.timedelta(days=d.weekday())
        if m == monday:
            wk = ', this week'
        elif m == monday + datetime.timedelta(days=7):
            wk = ', next week'
        tag = ' (TODAY)' if k == 0 else ''
        lines.append(_say(d) + ' = ' + d.isoformat() + ': ' + kind + wk + tag)
    vars['calendar_text'] = '\\n'.join(lines)
    slots = []
    if now.strftime('%H:%M') < '19:00':
        start = max(now.strftime('%H:%M'), '10:00')
        slots.append('today, ' + _say(today) + ' (' + today.isoformat() + '), later than ' + now.strftime('%H:%M') + ' and from ' + start + ' to 19:00')
    slots.append('the next business day, ' + _say(nbd) + ' (' + nbd.isoformat() + '), from 10:00 to 19:00')
    vars['callback_text'] = ' or '.join(slots)
    rel = ['Today: ' + _say(today) + ' (' + today.isoformat() + ').',
           'Tomorrow: ' + _say(today + datetime.timedelta(days=1)) + ' (' + (today + datetime.timedelta(days=1)).isoformat() + ').',
           'The day after tomorrow: ' + _say(today + datetime.timedelta(days=2)) + ' (' + (today + datetime.timedelta(days=2)).isoformat() + ').']
    wk1 = []
    wk2 = []
    for k in range(0, 7):
        d1 = monday + datetime.timedelta(days=k)
        d2 = monday + datetime.timedelta(days=k + 7)
        wk1.append('this ' + d1.strftime('%A') + ' = ' + _say(d1) + ' (' + d1.isoformat() + ')')
        wk2.append('next ' + d2.strftime('%A') + ' = ' + _say(d2) + ' (' + d2.isoformat() + ')')
    rel.append('This week: ' + '; '.join(wk1) + '.')
    rel.append('Next week: ' + '; '.join(wk2) + '.')
    vars['relative_dates'] = ' '.join(rel)
    vars['tomorrow_say'] = _say(today + datetime.timedelta(days=1))
    vars['date_state'] = 'ok'
except Exception as e:
    vars['date_state'] = 'error'
    vars['calendar_text'] = 'not available'
    vars['callback_text'] = 'today or the next business day, from 10:00 to 19:00'
    vars['today_say'] = raw
    vars['relative_dates'] = 'Today: ' + raw
    vars['tomorrow_say'] = 'the day after ' + raw
"""

PREPARE_CODE = DATE_CODE + """import json
import re
def _money(x):
    x = float(x)
    if abs(x - round(x)) < 0.0001:
        return str(int(round(x)))
    return '%.2f' % x
prods = vars.get('products')
if isinstance(prods, str):
    try:
        prods = json.loads(prods)
    except Exception:
        prods = None
if isinstance(prods, dict):
    prods = prods.get('products')
if not isinstance(prods, list) or not prods:
    for key in ('fetch_account_response.data.products', 'get_account_response.data.products'):
        val = vars.get(key)
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                val = None
        if isinstance(val, list) and val:
            prods = val
            break
if not isinstance(prods, list) or not prods:
    found = dict()
    for key in list(vars.keys()):
        m = re.search(r'products\\.(\\d+)\\.(\\w+)$', str(key))
        if m:
            idx = int(m.group(1))
            if idx not in found:
                found[idx] = dict()
            found[idx][m.group(2)] = vars[key]
    prods = []
    for idx in sorted(found.keys()):
        prods.append(found[idx])
names = dict(credit_card='credit card', personal_loan='personal loan', car_loan='car loan')
statement = []
summary = []
count = 0
try:
    for p in prods[:__MAX__]:
        if not isinstance(p, dict):
            continue
        count += 1
        i = count
        ptype = str(p.get('type') or '')
        name = names.get(ptype, ptype.replace('_', ' '))
        if ptype == 'credit_card':
            name = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_kind = 'minimum payment'
        else:
            floor = p.get('instalment_amount')
            floor_kind = 'instalment amount'
        due = float(p.get('past_due') or 0)
        floor = float(floor if floor is not None else due)
        days = int(float(p.get('days_late') or 0))
        if days <= 7:
            band = 'early'
            dl = dl_early
            allowed = 1
        else:
            band = 'late'
            dl = dl_late
            allowed = 2
        vars['p%d_id' % i] = str(p.get('product_id') or ('p%d' % i))
        vars['p%d_name' % i] = name
        vars['p%d_due' % i] = _money(due)
        vars['p%d_floor' % i] = _money(floor)
        vars['p%d_deadline_iso' % i] = dl.isoformat()
        vars['p%d_deadline_say' % i] = _say(dl)
        vars['attempts_%d' % i] = allowed
        vars['p%d_facts' % i] = ('Product: ' + name + '. Full past-due amount: ' + _money(due) + '. Days late: ' + str(days)
            + ' (' + band + ' band). Floor (' + floor_kind + '): ' + _money(floor)
            + '. Deadline, the latest promise date you may record: ' + _say(dl) + ' (' + dl.isoformat() + ').')
        vars['offer_%d_1' % i] = ('Ask whether the customer can pay the full past-due amount of ' + _money(due) + ' on ' + _say(lbw)
            + '. If the customer already said in this call that the full amount is too much, ask instead for the ' + floor_kind + ' of '
            + _money(floor) + ' on ' + _say(lbw) + ', and say that the rest stays overdue.')
        vars['offer_%d_2' % i] = ('Ask whether the customer can pay the ' + floor_kind + ' of ' + _money(floor) + ' on ' + _say(dl)
            + ', the latest date you can record for this product. Say that the rest stays overdue.')
        statement.append('Your ' + name + ' has a past-due amount of ' + _money(due) + ' and is ' + str(days) + ' days late.')
        summary.append(str(i) + '. ' + vars['p%d_facts' % i])
    vars['product_count'] = count
    vars['debt_statement'] = ' '.join(statement)
    vars['products_summary'] = '\\n'.join(summary)
    vars['today_question'] = 'Can you make this payment today?' if count == 1 else 'Can you pay all of them today?'
    vars['attempt1_say'] = _say(lbw)
    vars['account_state'] = 'ok' if count > 0 else 'missing'
except Exception as e:
    vars['account_state'] = 'missing'
    vars['product_count'] = 0
k = count + 1
while k <= 3:
    vars['attempts_%d' % k] = 0
    vars['p%d_facts' % k] = 'none'
    vars['p%d_name' % k] = 'none'
    vars['offer_%d_1' % k] = 'none'
    vars['offer_%d_2' % k] = 'none'
    k += 1
"""

REVIEW_CODE = """def _s(x):
    return str(x if x is not None else '').strip().lower()
cnt = 0
try:
    cnt = int(float(vars.get('product_count') or 0))
except Exception:
    cnt = 0
hard = _s(vars.get('support_answer')) == 'decline'
agreed = 'no'
for i in range(1, cnt + 1):
    try:
        allowed = int(float(vars.get('attempts_%d' % i) or 1))
    except Exception:
        allowed = 1
    refused_final = _s(vars.get('refusal_%d_%d' % (i, allowed))) == 'yes'
    res = _s(vars.get('result_%d' % i))
    if refused_final:
        continue
    if res == 'agreed' or (res == '' and not hard):
        agreed = 'yes'
vars['any_agreed'] = agreed
"""

SUMMARIZE_CODE = """def _s(x):
    return str(x if x is not None else '').strip().lower()
cnt = 0
try:
    cnt = int(float(vars.get('product_count') or 0))
except Exception:
    cnt = 0
confirmed = _s(vars.get('confirm_answer')) == 'yes'
hard = _s(vars.get('support_answer')) == 'decline'
recorded = []
failed = []
reasons = []
for i in range(1, cnt + 1):
    ok = False
    if _s(vars.get('create_promise_%d_response.data.ok' % i)) == 'true':
        ok = True
    name = str(vars.get('p%d_name' % i) or 'product')
    vars['note_needed_%d' % i] = 'no'
    if ok:
        recorded.append(name)
        continue
    tried = False
    for key in ('create_promise_%d_success_count' % i, 'create_promise_%d_failure_count' % i):
        try:
            if float(vars.get(key) or 0) > 0:
                tried = True
        except Exception:
            pass
    try:
        allowed = int(float(vars.get('attempts_%d' % i) or 1))
    except Exception:
        allowed = 1
    refused_final = _s(vars.get('refusal_%d_%d' % (i, allowed))) == 'yes'
    res = _s(vars.get('result_%d' % i))
    if tried:
        reason = 'service_error'
        failed.append(name)
    elif res in ('dispute', 'paid') and not refused_final:
        reason = res
    elif hard:
        reason = 'hardship'
    else:
        reason = 'refused'
    vars['note_needed_%d' % i] = 'yes'
    vars['note_reason_%d' % i] = reason
    reasons.append(reason)
if recorded:
    outcome = 'promise'
elif reasons and all(r == 'paid' for r in reasons):
    outcome = 'paid'
else:
    outcome = 'refused'
    for r in reasons:
        if r != 'paid':
            outcome = r
            break
msg = ''
if recorded:
    if len(recorded) == 1:
        msg = 'Your promise for the ' + recorded[0] + ' is recorded.'
    else:
        msg = 'Your promises for the ' + ', the '.join(recorded[:-1]) + ' and the ' + recorded[-1] + ' are recorded.'
    msg += ' You will receive a text message confirming this promise.'
if failed:
    msg += ' I am sorry, I could not record the promise for the ' + ' and the '.join(failed) + ' because of a technical problem.'
vars['final_message'] = msg.strip()
vars['outcome_key'] = outcome
"""


# ------------------------------------------------------------------ prompts

PRE_VERIFY = ("Identity is not verified yet. Do not say why you are calling. Do not say the words collections, debt, payment, "
              "amount, late, or name any product, even if asked, and even to a relative. If asked what the call is about, say you can "
              "explain only to {{title}} {{last_name}} after a short security check.")

SYSTEM = ("You are the digital assistant of Freya Bank on an outbound phone call. Speak English. Use one or two short spoken "
          "sentences per turn, no lists, no markdown. The customer is {{title}} {{first_name}} {{last_name}}; address them as "
          "{{title}} {{last_name}}. The current date and time is {{now}}; today is {{today_say}}. Use only this date, never your own clock or any "
          "other date you may know. Every relative date (tomorrow, Friday, next week) is counted from {{today_say}}.\n"
          "DATE FACTS: {{relative_dates}}\n"
          "- Always say a date with weekday, day, month and year, for example 'Friday 16 October 2026'.\n"
          "- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.\n"
          "- If asked whether you are a robot or an AI, say you are Freya Bank's digital assistant, then continue.\n"
          "- If asked whether this is a scam, say they can verify the call by phoning Freya Bank's customer service number, then continue.\n"
          "- If you cannot answer a question from the facts given to you, say you do not have that information. Never invent figures, dates or reasons.\n"
          "- Never offer a discount, a waiver, an instalment plan, a payment plan or any term not given to you.\n"
          "- Never say that anything is recorded, booked or transferred unless a tool result in this conversation shows it.\n"
          "- When you call a tool whose name starts with transition_to_, you may say one short sentence, but do not say goodbye: "
          "the closing words are spoken for you.")

NEGOTIATE = """Rules for dates. Today is {{today_say}} and tomorrow is {{tomorrow_say}}; take every date from the DATE FACTS and the calendar, never from your own clock. Business days are Monday to Friday except the bank holidays in the calendar.
- A promise date must be today or later, a business day, and not after the product's deadline.
- If the customer names a weekend day or a bank holiday that is not after the deadline, offer the next business day.
- If the customer names a date after the deadline, say the latest date you can record is the deadline and offer the deadline.
- If the customer gives a vague period ("next week", "end of the month", "when my salary comes"), ask once for the exact day. If they still give no day, propose the deadline.
- "Next <weekday>" means that weekday in the following calendar week. "This <weekday>" means the one in the current week. Look the date up in the calendar.
Rules for amounts.
- Never ask how much the customer can pay. You propose every amount. The full past-due amount comes first.
- If the customer says the full amount is too much, offer the floor once and say that the rest stays overdue.
- An amount the customer proposes from the floor up to the full amount, both included, is accepted. Below the floor: say it cannot be recorded and offer the floor once.
- A date or an amount the customer proposes is never a refusal: handle it with these rules.
- Do not repeat an offer the customer already refused.
- Keep what is settled. Once the customer said the full amount is too much, never propose the full amount again. The floor is offered only once: after that, do not name or offer it again as a new offer. If the customer then names a date or says when they can pay, the amount is the floor and only the date is open: check the date with the date rules and, if it is allowed, treat it as agreed.
- Once the customer accepted an amount, only the date is open; once they accepted a date, only the amount is open.
Other things the customer may say.
- Illness, a death in the family or job loss: this is handled for you. Make no offer in reply to it.
- "I already paid": say payments can take one business day to appear.
- "This is not mine", "I never had this product", or a claim it was closed or paid off in the past: do not argue."""

CALENDAR = "Calendar (date = ISO date: kind):\n{{calendar_text}}"

HUMAN = ("The customer asks for a human agent or a real person again after you already asked once whether you can help them "
         "yourself, and insists on a person.")
TALK_REFUSAL = "The customer has now said for the second time in this call that they do not want to talk."


# ------------------------------------------------------------------ body

def build(slot, multi):
    max_items = 3 if multi else 1
    n = {}

    n["setup"] = code_node("setup", SETUP_CODE.replace("__HOLIDAYS__", json.dumps(HOLIDAYS)), [always("opening")])

    line_status = ext("line_status",
                      "Who is on the line, judged only from the person's last message. 'confirmed': they clearly confirm they are "
                      "{{title}} {{last_name}} with yes, that's me, speaking, or their own name. 'someone_else': another person answered "
                      "(a relative, a colleague) or the customer is not available. 'wrong_number': they say the number does not belong to "
                      "{{first_name}} {{last_name}} or they do not know that person. 'deceased': they say {{first_name}} {{last_name}} has died. "
                      "'unclear': anything else, such as hello, go ahead, who is this, or a question.",
                      ["confirmed", "someone_else", "wrong_number", "deceased", "unclear"])

    n["opening"] = {
        "name": "opening", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Hello, this is the digital assistant calling from Freya Bank. Please note that we record this call. Am I speaking with {{title}} {{last_name}}?"},
        "on_enter_first_entry_only": True,
        "task_message": ("You have said you are Freya Bank's digital assistant, that we record this call, and asked whether you are speaking with "
                         "{{title}} {{last_name}}. " + PRE_VERIFY + "\nOnly yes, that's me, speaking, or their own name confirms. If the answer is "
                         "not a confirmation, answer any question they asked first, then ask once more: 'Am I speaking with {{title}} {{last_name}}?'. "
                         "Do not call any tool except the transition tools."),
        "extraction_schema": [line_status],
        "max_node_turns": 3, "max_turn_transition": "close:not_reached/unclear",
        "transitions": [
            tr("identity", "the customer confirmed who they are", when(v("line_status", "equals", "confirmed"))),
            tr("close:not_reached/deceased", "the customer has died", when(v("line_status", "equals", "deceased"))),
            tr("close:not_reached/wrong_number", "wrong number", when(v("line_status", "equals", "wrong_number"))),
            tr("third_party", "someone else answered", when(v("line_status", "equals", "someone_else"))),
            tool_tr("close:not_reached/unclear", "You have already asked twice whether you are speaking with the customer and the person's latest answer is still not a clear confirmation (yes, that's me, speaking, or their own name)."),
            tool_tr("transfer_general", HUMAN),
            tool_tr("close:not_verified/declined", TALK_REFUSAL),
        ]}

    callback_tool = api_tool("schedule_callback", "/schedule_callback", {
        "customer_id": body_field("string", "{{customer_id}}"),
        "date": body_field("string", "{{date}}", "Callback date as YYYY-MM-DD."),
        "time": body_field("string", "{{time}}", "Callback time as HH:MM, 24 hour clock."),
    }, ["date", "time"], "Book a callback for the customer. CALL it as soon as the person names a day and time inside the allowed window.")
    callback_tool["response_mapping"] = [{"path": "data.ok", "variable": "callback_ok"}]

    n["third_party"] = {
        "name": "third_party", "node_type": "conversation",
        "task_message": ("You are speaking with someone who is not {{title}} {{last_name}}. Say nothing beyond your opening sentence about who you are. "
                         "Do not say why you are calling and do not mention the bank account, any product, amount, debt or payment. Do not ask or accept "
                         "security answers. If they ask what it is about or offer to pay, say you can only speak with {{title}} {{last_name}}.\n"
                         "Ask when {{title}} {{last_name}} can be reached. Allowed callback times: " + "{{callback_text}}" + ". Both 10:00 and 19:00 are allowed.\n"
                         "- When the person names a day and time inside that window, call schedule_callback with the date (YYYY-MM-DD) and the time (HH:MM). "
                         "'Tomorrow' means the day after today in the calendar; 'morning around eleven' means 11:00.\n"
                         "- If the day or time is outside the window, ask once for another time within it.\n"
                         "- If the second time is also outside the window, do not book anything.\n"
                         "- If schedule_callback fails, say you could not book the callback.\n" + CALENDAR),
        "tools": [callback_tool],
        "extraction_schema": [line_status],
        "max_node_turns": 8, "max_turn_transition": "close:not_reached/no_callback",
        "transitions": [
            tr("close:not_reached/callback", "the callback was booked", any_of(*is_true("callback_ok"), *is_true("schedule_callback_response.data.ok"))),
            tr("close:not_reached/deceased", "the customer has died", when(v("line_status", "equals", "deceased"))),
            tr("close:not_reached/wrong_number", "wrong number", when(v("line_status", "equals", "wrong_number"))),
            tool_tr("close:not_reached/no_callback", "The person has named a time outside the allowed callback window twice, or cannot name any time, so no callback can be booked."),
            tool_tr("identity", "The person now says they are {{title}} {{last_name}} themself."),
        ]}

    verify_tool = api_tool("verify_identity", "/verify_identity", {
        "customer_id": body_field("string", "{{customer_id}}"),
        "field": body_field("string", "{{field}}", "Which answer this is: date_of_birth or phone_last4.", ["date_of_birth", "phone_last4"]),
        "answer": body_field("string", "{{answer}}", "For date_of_birth the date as YYYY-MM-DD, converted from what the customer said "
                             "(a date said only in numbers is day, then month, then year). For phone_last4 exactly four digits."),
    }, ["field", "answer"], "Check one security answer. CALL it every time the customer gives an answer to a security question.")

    n["identity"] = {
        "name": "identity", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you. Before we continue, I need to ask two security questions. What is your date of birth?"},
        "on_enter_first_entry_only": True,
        "task_message": ("You are checking the customer's identity. " + PRE_VERIFY + "\n"
                         "Ask two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. "
                         "Call verify_identity once for every answer the customer gives, right away, even when the answer comes together with a question or a complaint: check the answer first, then reply. Send a date of birth as YYYY-MM-DD whatever way it was said; a date said only in numbers "
                         "is day, then month, then year. If the customer gives only part of an answer, ask for the rest before calling the tool.\n"
                         "- If the result has verified false, say the answer did not match and ask the same question again.\n"
                         "- If the result has hint day_month_swapped, ask the customer to say the month of their birth as a word; this is not a wrong answer.\n"
                         "- If the date of birth passed, ask for the last four digits of the phone number.\n"
                         "- If the customer does not want to answer, or asks what the call is about instead of answering, explain once that the "
                         "questions protect their account, and ask again.\n"
                         "Never tell the customer anything about an account or the reason for the call in this step."),
        "tools": [verify_tool],
        "max_node_turns": 14, "max_turn_transition": "close:not_verified/declined",
        "transitions": [
            tr("fetch_account", "both answers verified", any_of(*is_true("verify_identity_response.data.all_verified"))),
            tr("close:not_verified/failed", "three wrong answers", when(v("verify_identity_response.data.wrong_answers_left", "equals", "0"))),
            tool_tr("close:not_verified/declined", "After you explained once that the security questions protect the account, the customer again refuses to answer, "
                    "or again asks what the call is about instead of answering, or says for the second time that they do not want to talk."),
            tool_tr("transfer_general", HUMAN),
        ]}

    n["fetch_account"] = api_node("fetch_account", api_tool("fetch_account", "/get_account", {
        "customer_id": body_field("string", "{{customer_id}}")}, [], "Get the late products.", retries=2),
        [always("prepare")], mapping=[{"path": "data.products", "variable": "products"}])

    n["prepare"] = code_node("prepare", PREPARE_CODE.replace("__HOLIDAYS__", json.dumps(HOLIDAYS)).replace("__MAX__", str(max_items)), [
        tr("state_debt", "account read", when(v("account_state", "equals", "ok"))),
        always("close:no_promise/service_error_account")])

    def transfer(name, queue, closing):
        n[name] = api_node(name, api_tool(name, "/transfer_to_agent", {
            "customer_id": body_field("string", "{{customer_id}}"),
            "queue": body_field("string", queue, enum=[queue])}, ["queue"], "Hand the call to a person."),
            [always(closing)])

    transfer("transfer_general", "general", "close:transferred/human")
    transfer("transfer_support", "support", "close:transferred/support")
    transfer("transfer_restructuring", "restructuring", "close:transferred/restructuring")

    intents = ["none", "hardship", "restructuring"] + ([] if multi else ["dispute", "paid"])
    intent_desc = ("What the customer's last message is about. 'hardship': they mention illness, a death in the family, or losing their job. "
                   "'restructuring': they ask for a new payment plan, a restructuring, or lower instalments. ")
    if not multi:
        intent_desc += ("'dispute': they say the debt or the product is not theirs, they never had it, or it was closed or paid off in the past. "
                        "'paid': they say they have already paid this past-due amount. ")
    intent_desc += "'none': anything else."

    def intent_routes(var, hardship_target="hardship"):
        out = [tr(hardship_target, "hardship", when(v(var, "equals", "hardship"))),
               tr("transfer_restructuring", "restructuring request", when(v(var, "equals", "restructuring")))]
        if not multi:
            out += [tr("close:no_promise/dispute", "dispute", when(v(var, "equals", "dispute"))),
                    tr("close:paid", "already paid", when(v(var, "equals", "paid")))]
        return out

    after_talk_refusal = "summarize" if multi else "close:no_promise/refused"

    # state the debt and ask about today
    if multi:
        today_ext = ext("today_answer",
                        "How the customer's last message answers the question about paying all late products today. 'not_all': they say no "
                        "or give a non-answer, or they say they can pay only some products, or they say a product is not theirs or already "
                        "paid, or they say the full amounts are too much, or they refuse a deadline you offered for a date they named. "
                        "'other': they agree, ask a question, or name one date or one plan for all the products.",
                        ["not_all", "other"])
        today_routes = [tr("item:first", "not everything today", when(v("today_answer", "equals", "not_all")))]
        state_task = ("The customer is verified. You have said you are calling from the collections team about a late payment, named every late product "
                      "and asked whether they can pay all of them today.\nLate products, in order:\n{{products_summary}}\n\n"
                      "If the customer agrees to pay everything today (the full past-due amount of every product, today {{today_say}}), call the agreement tool.\n"
                      "If the customer names one date for everything: check it with the date rules for each product. If the date is after one product's deadline, "
                      "that product goes on its own deadline and the others keep the named date; tell the customer. When they agree to these dates with the full "
                      "amounts, call the agreement tool.\nDo not ask about today again.\n\n" + NEGOTIATE + "\n\n" + CALENDAR)
        agree_desc = "The customer has agreed to pay every late product, each with an amount and a date that the rules allow."
    else:
        today_ext = ext("today_refusal",
                        "'yes' only when the customer's last message is a flat refusal or a non-answer: a no to paying with no date and no amount "
                        "of their own, or a refusal of the deadline you offered, or a refusal of the floor amount you offered. 'no' for everything else: "
                        "agreeing, naming any date or amount (even a vague one), saying the full amount is too much, asking a question, mentioning "
                        "illness, a death or job loss, saying it is paid or not theirs, asking for a plan or a person.",
                        ["yes", "no"])
        today_routes = [tr("item:first", "flat refusal", when(v("today_refusal", "equals", "yes")))]
        state_task = ("The customer is verified. You have said you are calling from the collections team about a late payment, stated the product, the "
                      "past-due amount and the days late, and asked: 'Can you make this payment today?'.\n{{p1_facts}}\n\n"
                      "If the customer agrees to pay the full amount today ({{today_say}}), or agrees to an amount and a date that the rules allow, "
                      "call the agreement tool.\nIf the customer says the full amount is too much, offer the floor today once and say the rest stays overdue.\n\n"
                      + NEGOTIATE + "\n\n" + CALENDAR)
        agree_desc = "The customer has agreed to pay an amount and a date that the rules allow."

    n["state_debt"] = {
        "name": "state_debt", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you, that is verified. I am calling from the collections team about a late payment. {{debt_statement}} {{today_question}}"},
        "on_enter_first_entry_only": True,
        "task_message": state_task + "\nDo not call any tool except the transition tools.",
        "extraction_schema": [today_ext, ext("intent_state", intent_desc, intents)],
        "max_node_turns": 14, "max_turn_transition": "item:first",
        "transitions": intent_routes("intent_state") + today_routes + [
            tool_tr("confirm", agree_desc),
            tool_tr("transfer_general", HUMAN),
            tool_tr(after_talk_refusal, TALK_REFUSAL),
        ]}

    # ladder template: item {i}, attempt {a}
    settle = ("The customer has settled this product: they agreed to an amount and a date that the rules allow"
              + (", or they said it is not theirs (or was closed or paid off in the past), or they said it is already paid." if multi else "."))
    tmpl_ext = [ext("refusal_{i}_{a}",
                    "'yes' only when the agent's last message made an offer (an amount and a date) and the customer's reply flatly refuses that offer, "
                    "or is a non-answer to it, with no date "
                    "and no amount of their own; also 'yes' when they refuse the deadline offered after asking for a later date, or refuse the floor "
                    "amount offered. 'no' for everything else. Not a refusal: agreeing, naming any date or amount (even a vague one or one outside "
                    "the rules), saying the full amount is too much, asking a question, mentioning illness, a death or job loss, saying it is paid or "
                    "not theirs, asking for a plan or a person.", ["yes", "no"]),
                ext("intent_{i}_{a}", intent_desc, intents)]
    if multi:
        tmpl_ext.append(ext("result_{i}",
                            "The state of the product being discussed now ({{p{i}_name}}), from the customer's last message. 'agreed': they accept an "
                            "amount and a date for it. 'dispute': they say it is not theirs, they never had it, or it was closed or paid off in the past. "
                            "'paid': they say they already paid this past-due amount. Leave empty otherwise.", ["agreed", "dispute", "paid"]))
    tmpl_task = ("The customer is verified. You are now discussing this product:\n{{p{i}_facts}}\n\n"
                 "YOUR OFFER IN THIS STEP: {{offer_{i}_{a}}}\n"
                 "Make this offer in your first message in this step, as one short question. Do not mention other offers and do not count attempts.\n")
    if multi:
        tmpl_task += ("If this is a new product, first say in a few words that you are now asking about the {{p{i}_name}}. Before making the offer: "
                      "if earlier in this call the customer already said this product is not theirs or already paid, or already agreed an amount and a date "
                      "for it, do not make the offer: ask one short yes/no question to check that, and when they answer, call the tool that moves on. "
                      "If the customer told you earlier about illness, a death in the family or job loss, make no offer.\n")
    tmpl_task += ("Then handle the customer's answer with the rules below. When the product is settled, call the tool that moves on.\n\n"
                  + NEGOTIATE + "\n\n" + CALENDAR + "\nDo not call any tool except the transition tools.")
    n["ladder"] = {
        "name": "ladder", "node_type": "conversation",
        "on_enter": {"type": "llm", "prompt": ("Your next message must make this offer now, as one short question, and nothing else: {{offer_{i}_{a}}} "
                                               + ("Start with a few words saying you are now asking about the {{p{i}_name}}. Exception: if earlier in this call the customer "
                                                  "already proposed their own date or amount for this product, or said it is not theirs or already paid, do not "
                                                  "make the offer: check their proposal with the rules and ask one short question to confirm it (or to confirm "
                                                  "the claim) instead. "
                                                  if multi else "") + "Do not respond to anything else first.")},
        "task_message": tmpl_task,
        "extraction_schema": tmpl_ext,
        "max_node_turns": 12, "max_turn_transition": "item:next",
        "transitions": intent_routes("intent_{i}_{a}") + [
            tool_tr("item:next", settle),
            tool_tr("transfer_general", HUMAN),
            tool_tr(after_talk_refusal, TALK_REFUSAL),
        ]}

    # after the ladder
    if multi:
        n["review"] = code_node("review", REVIEW_CODE, [
            tr("confirm", "something was agreed", when(v("any_agreed", "equals", "yes"))), always("summarize")])
    else:
        n["after_offers"] = router("after_offers", [
            tr("close:no_promise/refused", "attempts used up",
               any_of([v("refusal_1_1", "equals", "yes"), v("attempts_1", "less_than", 2)], [v("refusal_1_2", "equals", "yes")])),
            always("confirm")])

    # hardship
    n["hardship"] = {
        "name": "hardship", "node_type": "conversation",
        "task_message": ("The customer mentioned illness, a death in the family or job loss. Say one short sentence of sympathy and offer to connect them "
                         "with the customer support team. Make no payment offer and do not try to persuade them.\n"
                         "If the customer themself names a payment date or amount, handle it with these rules:\n"
                         + ("{{products_summary}}" if multi else "{{p1_facts}}") + "\n" + NEGOTIATE + "\n\n" + CALENDAR +
                         "\nDo not call any tool except the transition tools."),
        "extraction_schema": [ext("support_answer",
                                  "'accept' when the customer's last message accepts being connected to the customer support team. 'decline' when "
                                  "they decline it and do not name a payment date or amount themselves. Leave empty otherwise.",
                                  ["accept", "decline"])],
        "max_node_turns": 6, "max_turn_transition": "review" if multi else "close:no_promise/hardship",
        "transitions": [
            tr("transfer_support", "accepts support", when(v("support_answer", "equals", "accept"))),
            tr("review" if multi else "close:no_promise/hardship", "declines support", when(v("support_answer", "equals", "decline"))),
            tool_tr("confirm", "The customer themself named a payment amount and date that the rules allow and agreed to it."),
            tool_tr("transfer_restructuring", "The customer asks for a new payment plan, a restructuring or lower instalments."),
            tool_tr("transfer_general", HUMAN),
        ]}

    # confirmation and recording: the dialogue model calls the promise tool after the yes; routing reads its results
    def promise_tool(name, i, which):
        t = api_tool(name, "/create_promise", {
            "customer_id": body_field("string", "{{customer_id}}"),
            "product_id": body_field("string", "{{p%d_id}}" % i),
            "amount": body_field("number", "{{promise_amount_%d}}" % i, "The confirmed amount for %s, a plain number such as 420 or 103.5." % which),
            "date": body_field("string", "{{promise_date_%d}}" % i, "The confirmed date for %s as YYYY-MM-DD." % which)},
            ["product_id", "amount", "date"],
            "Record the payment promise for %s. CALL it only right after the customer said a clear yes to your read-back. "
            "If it fails, CALL it once more with the same values." % which)
        return t

    def ok(name):
        return [*is_true(name + "_response.data.ok")]

    def failed_twice(name):
        f, s, r = name + "_failure_count", name + "_success_count", name + "_response.data.ok"
        alts = [[v(f, "greater_than", 1)]]
        for bad in ("false", "False"):
            alts.append([v(s, "greater_than", 1), v(r, "equals", bad)])
            alts.append([v(f, "greater_than", 0), v(s, "greater_than", 0), v(r, "equals", bad)])
        return alts

    confirm_ext = [ext("confirm_answer",
                       "'no' only when the customer's last message withdraws and says they do not want to promise anything after all. "
                       "Leave empty otherwise.", ["no"]),
                   ext("intent_confirm", "'restructuring': the customer's last message asks for a new payment plan, a "
                       "restructuring or lower instalments. 'none': anything else.", ["none", "restructuring"])]
    rules_after = ("\nMake no new offer in this step for a product the customer refused, disputed or said is paid.\nIf the customer changes the date or the amount, check the new value with the rules below and read everything back again "
                   "with 'Do you confirm?'.\nNever say yourself that a promise is recorded, noted, saved or done, and never say goodbye in this "
                   "step: after a successful result the system tells the customer. If a promise tool fails, you may say there was a technical "
                   "problem and that you are trying again.\n\n" + NEGOTIATE + "\n\n" + CALENDAR)
    if multi:
        tools = [promise_tool("create_promise_%d" % i, i, "product %d of the list (the {{p%d_name}})" % (i, i)) for i in (1, 2, 3)]
        task = ("The customer is verified and has agreed to payment promises. Read back all agreed promises together, in the order of the products "
                "below: for each product its name, the amount and the date (weekday, day, month, year). If a product goes on its own deadline "
                "because the date the customer named is after it, say so. Products without an agreement are not read back. Then ask exactly: "
                "'Do you confirm?'. Ask for one confirmation for all of them.\nProducts (number. facts):\n{{products_summary}}\n"
                "After a clear yes, call the promise tool of every agreed product in the same message, without speaking first: create_promise_1 for "
                "product 1, create_promise_2 for product 2, create_promise_3 for product 3, each with the amount and the date (YYYY-MM-DD) you read "
                "back. If one fails, call that product's tool once more with the same values, without saying anything else." + rules_after)
        import itertools

        def settled(i):
            t = "create_promise_%d" % i
            s_, f_, r_ = t + "_success_count", t + "_failure_count", t + "_response.data.ok"
            return {"ok": [v(r_, "equals", "true")], "f2": [v(f_, "greater_than", 1)], "s2": [v(s_, "greater_than", 1)],
                    "fs": [v(f_, "greater_than", 0), v(s_, "greater_than", 0)], "never": [v(s_, "is_not_set"), v(f_, "is_not_set")]}
        alts = []
        for combo in itertools.product(*[list(settled(i).items()) for i in (1, 2, 3)]):
            if all(k == "never" for k, _ in combo):
                continue
            alts.append([c for _, checks in combo for c in checks])
        routes = [tr("summarize", "every called promise tool is settled: ok, or tried twice", any_of(*alts))]
        no_target = "summarize"
    else:
        tools = [promise_tool("create_promise", 1, "the {{p1_name}}")]
        task = ("The customer is verified and has agreed to a payment promise. Read back the product, the amount and the date (weekday, day, month, "
                "year) the customer agreed to in this call, then ask exactly: 'Do you confirm?'.\n{{p1_facts}}\n"
                "After a clear yes, call create_promise right away, without speaking first, with the amount and the date (YYYY-MM-DD) you read back. "
                "If it fails, call it once more with the same values." + rules_after)
        routes = [tr("close:promise", "recorded", any_of(*ok("create_promise"))),
                  tr("close:no_promise/service_error", "failed twice", any_of(*failed_twice("create_promise")))]
        no_target = "close:no_promise/refused"
    n["confirm"] = {
        "name": "confirm", "node_type": "conversation",
        "on_enter": {"type": "llm", "prompt": "Your next message is the read-back of what the customer agreed in this call, ending with 'Do you confirm?'. "
                                              "Make no new offer. A product the customer refused, disputed or said is paid gets no promise and is not "
                                              "read back."},
        "on_enter_first_entry_only": True,
        "task_message": task,
        "tools": tools,
        "extraction_schema": confirm_ext,
        "max_node_turns": 8, "max_turn_transition": no_target,
        "transitions": routes + [
            tr("transfer_restructuring", "restructuring", when(v("intent_confirm", "equals", "restructuring"))),
            tr(no_target, "withdrawn", when(v("confirm_answer", "equals", "no"))),
            tool_tr("transfer_general", HUMAN),
            tool_tr(after_talk_refusal, TALK_REFUSAL),
        ]}

    if multi:
        n["summarize"] = code_node("summarize", SUMMARIZE_CODE, [always("note_gate_1")])
        for i in (1, 2, 3):
            nxt = "note_gate_%d" % (i + 1) if i < 3 else "route_outcome"
            n["note_gate_%d" % i] = router("note_gate_%d" % i, [
                tr("note_%d" % i, "note needed", when(v("note_needed_%d" % i, "equals", "yes"), v("note_reason_%d" % i, "is_set"))),
                always(nxt)])
            n["note_%d" % i] = api_node("note_%d" % i, api_tool("note_%d" % i, "/add_note", {
                "customer_id": body_field("string", "{{customer_id}}"),
                "product_id": body_field("string", "{{p%d_id}}" % i),
                "reason": body_field("string", "{{note_reason_%d}}" % i, enum=["refused", "hardship", "dispute", "paid", "service_error"])},
                ["product_id", "reason"], "Record why this product has no promise."), [always(nxt)])
        n["route_outcome"] = router("route_outcome", [
            tr("close:promise", "promise", when(v("outcome_key", "equals", "promise"))),
            tr("close:paid", "paid", when(v("outcome_key", "equals", "paid"))),
            tr("close:no_promise/dispute", "dispute", when(v("outcome_key", "equals", "dispute"))),
            tr("close:no_promise/hardship", "hardship", when(v("outcome_key", "equals", "hardship"))),
            tr("close:no_promise/service_error", "service error", when(v("outcome_key", "equals", "service_error"))),
            tr("close:no_promise/refused", "refused", when(v("outcome_key", "equals", "refused"))),
            tr("close:promise/plain", "code did not run but a promise was recorded",
               any_of(*ok("create_promise_1"), *ok("create_promise_2"), *ok("create_promise_3"))),
            always("close:no_promise/refused")])

    return {"initial_node": "setup", "system_prompt": SYSTEM, "nodes": n, "global_nodes": {},
            "test_variables": {"first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}


# ------------------------------------------------------------------ closing plan

A = "briefs/brief-a.md"
API = "tools/openapi.json"
ROW = {
    "promise": "| `promise` | none | at least one promise was recorded |",
    "paid": "| `paid` | none | rule 39 |",
    "transferred": "| `transferred` | `restructuring`, `human`, `support` | rules 41, 42, 32 |",
    "no_promise": "| `no_promise` | `refused`, `hardship`, `dispute`, `service_error` | rules 31 and 45, 32, 40, 37 |",
    "not_verified": "| `not_verified` | `failed`, `declined` | rules 14, 15 |",
    "not_reached": "| `not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear` | rules 6, 7, 8, 9, 3 |",
}
BYE = " Thank you for your time. Goodbye."


def closing(outcome, reason, say):
    c = {"set": {"outcome": outcome}, "say": say, "evidence": [{"source": A, "quote": ROW[outcome]}]}
    if reason:
        c["set"]["reason"] = reason
    return c


def plan(multi):
    closings = {
        "promise": closing("promise", None, ("{{final_message}}" + BYE) if multi else
                           "Your promise is recorded. You will receive a text message confirming this promise." + BYE),
        "paid": closing("paid", None, "Thank you. Payments can take one business day to appear." + BYE),
        "transferred/restructuring": closing("transferred", "restructuring", "I am connecting you with our restructuring team now." + BYE),
        "transferred/human": closing("transferred", "human", "I am connecting you with a colleague now." + BYE),
        "transferred/support": closing("transferred", "support", "I am connecting you with our customer support team now." + BYE),
        "no_promise/refused": closing("no_promise", "refused", "I understand." + BYE),
        "no_promise/hardship": closing("no_promise", "hardship", "I understand. Take care." + BYE),
        "no_promise/dispute": closing("no_promise", "dispute", ("I understand, I have noted that." if multi else
                                                                "I understand. I will not take a payment promise today.") + BYE),
        "no_promise/service_error": closing("no_promise", "service_error",
                                            ("I am sorry, I could not record your promise because of a technical problem." if not multi else "{{final_message}}") + BYE),
        "no_promise/service_error_account": closing("no_promise", "service_error",
                                                    "I am sorry, I cannot reach your account details right now because of a technical problem." + BYE),
        "not_verified/failed": closing("not_verified", "failed", "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch." + BYE),
        "not_verified/declined": closing("not_verified", "declined", "I understand." + BYE),
        "not_reached/callback": closing("not_reached", "callback", "Thank you, we will call back then." + BYE),
        "not_reached/no_callback": closing("not_reached", "no_callback", "I understand." + BYE),
        "not_reached/wrong_number": closing("not_reached", "wrong_number", "I apologise for the inconvenience." + BYE),
        "not_reached/deceased": closing("not_reached", "deceased", "I am sorry for your loss. Goodbye."),
        "not_reached/unclear": closing("not_reached", "unclear", "I am sorry, I could not confirm who I am speaking with." + BYE),
    }
    if multi:
        closings["promise/plain"] = closing("promise", None, "Your promise is recorded. You will receive a text message confirming this promise." + BYE)
    p = {"terminal": {"tool": "close_call", "evidence": [
        {"source": API, "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": A, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]},
        "fields": {"customer_id": "{{customer_id}}"},
        "closings": closings,
        "ladder": {"template": "ladder", "done": "review" if multi else "after_offers",
                   "items": {"count": "product_count", "max": 3 if multi else 1,
                             "evidence": [{"source": "briefs/brief-b.md", "quote": "`get_account` returns one to three products."}] if multi else
                             [{"source": A, "quote": "Freya Bank calls customers who are 1 to 45 days late on one product."}]},
                   "attempts": {"allowed": "attempts_{i}", "max": 2,
                                "evidence": [{"source": A, "quote": "| 1 to 7 | early | the 12th business day after today | 1 |"},
                                             {"source": A, "quote": "| 8 to 45 | late | the 7th business day after today | 2 |"}]
                                + ([{"source": "briefs/brief-b.md", "quote": "Persuasion attempts are counted per product."}] if multi else [])},
                   "refusal": "refusal_{i}_{a}"}}
    return p


for slot, multi in (("brief-a", False), ("brief-b", True)):
    (OUT / f"{slot}.body.json").write_text(json.dumps(build(slot, multi), indent=1) + "\n")
    (OUT / f"{slot}.closing.json").write_text(json.dumps(plan(multi), indent=1) + "\n")
    print("wrote", slot)
