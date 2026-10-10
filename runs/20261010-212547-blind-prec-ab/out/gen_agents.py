"""Generate the body and closing plan for brief-a-raw (one product) and brief-b-raw (one to three products).

    python3 out/gen_agents.py

Writes out/<slot>.body.json and out/<slot>.closing.json for both slots.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
SERVER = "https://freya-bank-mock.freyavoice.workers.dev/v1"
A, B = "briefs/brief-a-raw.md", "briefs/brief-b-raw.md"
API = "tools/openapi.json"

# ------------------------------------------------------------------ code snippets (no double braces allowed)

SETUP_CODE = r'''
import datetime
import re
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def addbd(d, n):
    k = 0
    x = d
    while k < n:
        x = x + datetime.timedelta(days=1)
        if isbd(x):
            k += 1
    return x
def sp(d):
    return DN[d.weekday()] + ' ' + str(d.day) + ' ' + MN[d.month - 1] + ' ' + str(d.year)
def lastbd(monday):
    x = monday + datetime.timedelta(days=4)
    while x > monday and not isbd(x):
        x = x - datetime.timedelta(days=1)
    return x
raw = str(vars.get('now') or '').strip()
try:
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?', raw)
    today = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    hh = int(m.group(4)) if m.group(4) else 0
    mi = int(m.group(5)) if m.group(5) else 0
    nowt = '%02d:%02d' % (hh, mi)
    monday = today - datetime.timedelta(days=today.weekday())
    prop = lastbd(monday)
    if today >= prop:
        prop = lastbd(monday + datetime.timedelta(days=7))
    dl_early = addbd(today, 12)
    dl_late = addbd(today, 7)
    nbd = addbd(today, 1)
    L = []
    L.append('Now: ' + sp(today) + ' (' + today.isoformat() + '), ' + nowt + '. Today is ' + ('a business day.' if isbd(today) else 'NOT a business day.'))
    L.append('Bank holidays: ' + ', '.join(HOL) + '. Business days are Monday to Friday except these holidays.')
    L.append('Calendar (business day = valid PTP day if not after the deadline):')
    for k in range(0, 36):
        d = today + datetime.timedelta(days=k)
        if d < monday + datetime.timedelta(days=7):
            wk = 'this week'
        elif d < monday + datetime.timedelta(days=14):
            wk = 'next week'
        else:
            wk = 'later'
        if d.isoformat() in HOL:
            kind = 'BANK HOLIDAY'
        elif d.weekday() >= 5:
            kind = 'weekend'
        else:
            kind = 'business day'
        tag = ' (today)' if k == 0 else ''
        L.append('- ' + d.isoformat() + ' ' + DN[d.weekday()] + tag + ', ' + wk + ': ' + kind)
    L.append('"this <weekday>" means that weekday in the current week (Monday to Sunday); "next <weekday>" means that weekday in the following calendar week:')
    for i in range(7):
        t = monday + datetime.timedelta(days=i)
        n = monday + datetime.timedelta(days=7 + i)
        past = ' (already past)' if t < today else ''
        L.append('- this ' + DN[i] + ' = ' + t.isoformat() + past + '; next ' + DN[i] + ' = ' + n.isoformat())
    vars['date_facts'] = '\n'.join(L)
    C = []
    if nowt < '19:00':
        if nowt < '10:00':
            C.append('Today ' + sp(today) + ' (' + today.isoformat() + '): from 10:00 to 19:00, both included.')
        else:
            C.append('Today ' + sp(today) + ' (' + today.isoformat() + '): any time later than ' + nowt + ' and no later than 19:00.')
    else:
        C.append('Today: no time is left (it is already ' + nowt + ').')
    C.append('Next business day ' + sp(nbd) + ' (' + nbd.isoformat() + '): from 10:00 to 19:00, both included.')
    C.append('Any other day, or any time before 10:00 or after 19:00, is outside the window.')
    vars['cb_facts'] = '\n'.join(C)
    vars['today_iso'] = today.isoformat()
    vars['dl_early_iso'] = dl_early.isoformat()
    vars['dl_early_sp'] = sp(dl_early)
    vars['dl_late_iso'] = dl_late.isoformat()
    vars['dl_late_sp'] = sp(dl_late)
    vars['prop_iso'] = prop.isoformat()
    vars['prop_sp'] = sp(prop)
    vars['date_state'] = 'known'
except Exception:
    vars['date_facts'] = 'Date facts could not be computed. The current date and time is ' + raw + '.'
    vars['cb_facts'] = 'Today later than ' + raw + ' up to 19:00, or the next business day from 10:00 to 19:00, both included.'
    vars['date_state'] = 'unknown'
'''

PREPARE_CODE = r'''
import json
import re
def num(v):
    try:
        return float(v)
    except Exception:
        return None
def money(v):
    f = num(v)
    if f is None:
        return str(v)
    return '%.2f' % f
def get_products():
    for key in ('products', 'load_account_response.data.products', 'get_account_response.data.products'):
        v = vars.get(key)
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                v = None
        if isinstance(v, dict):
            v = v.get('products')
        if isinstance(v, list) and v:
            return v
    found = dict()
    for k in list(vars.keys()):
        m = re.match(r'^(?:[A-Za-z_]+_response\.data\.)?products\.(\d+)\.(\w+)$', str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    return [found[i] for i in sorted(found)]
title = str(vars.get('title') or '')
last = str(vars.get('last_name') or '')
try:
    items = [p for p in get_products() if isinstance(p, dict)][:3]
    lines = []
    sentences = []
    for i in range(1, 4):
        vars['pid_' + str(i)] = ''
    for idx, p in enumerate(items):
        i = idx + 1
        t = str(p.get('type') or '')
        if t == 'credit_card':
            name = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            flabel = 'minimum payment'
        elif t == 'car_loan':
            name = 'car loan'
            floor = p.get('instalment_amount')
            flabel = 'instalment'
        else:
            name = 'personal loan'
            floor = p.get('instalment_amount')
            flabel = 'instalment'
        dlate = int(num(p.get('days_late')) or 0)
        early = dlate <= 7
        dl_iso = vars.get('dl_early_iso') if early else vars.get('dl_late_iso')
        dl_sp = vars.get('dl_early_sp') if early else vars.get('dl_late_sp')
        att = 1 if early else 2
        prop_iso = str(vars.get('prop_iso') or '')
        prop_sp = str(vars.get('prop_sp') or '')
        if dl_iso and prop_iso and prop_iso > str(dl_iso):
            prop_iso = str(dl_iso)
            prop_sp = str(dl_sp)
        amt = money(p.get('past_due'))
        fl = money(floor)
        days = str(dlate) + (' day' if dlate == 1 else ' days')
        pid = str(p.get('product_id') or '')
        vars['pid_' + str(i)] = pid
        vars['name_' + str(i)] = name
        lines.append('Product ' + str(i) + ': ' + name + ' (product_id ' + pid + '). Past-due amount ' + amt + ', ' + days + ' late. Stage: ' + ('early' if early else 'late') + '. PTP deadline: ' + str(dl_sp) + ' (' + str(dl_iso) + '); no PTP date may be after it. Floor (' + flabel + '): ' + fl + '. Persuasion attempts allowed: ' + str(att) + '.')
        lines.append('  Attempt 1 offer: ' + amt + ' (or the floor ' + fl + ' if the customer already said the full amount is too much) on ' + prop_sp + ' (' + prop_iso + ').')
        if att == 2:
            lines.append('  Attempt 2 offer: the floor ' + fl + ' on the deadline ' + str(dl_sp) + ' (' + str(dl_iso) + ').')
        else:
            lines.append('  No attempt 2 for this product: after a flat refusal of attempt 1 it ends without a PTP.')
        if len(items) == 1:
            sentences.append('I am calling from the collections team about a late payment on your ' + name + '. The past-due amount is ' + amt + ', and it is ' + days + ' late.')
        else:
            sentences.append('Your ' + name + ' has a past-due amount of ' + amt + ' and is ' + days + ' late.')
    vars['product_count'] = len(items)
    vars['account_facts'] = '\n'.join(lines) if lines else 'No product data could be read. Use the get_account result above.'
    if len(items) == 1:
        vars['opening_line'] = 'Thank you, ' + title + ' ' + last + ', you are verified. ' + sentences[0] + ' Can you make this payment today?'
    elif len(items) > 1:
        vars['opening_line'] = 'Thank you, ' + title + ' ' + last + ', you are verified. I am calling from the collections team about late payments on ' + str(len(items)) + ' products. ' + ' '.join(sentences) + ' Can you pay all of them today?'
    else:
        vars['opening_line'] = 'Thank you, you are verified. Tell the customer, from the get_account result, that you are calling from the collections team about a late payment, name each product, its past-due amount and days late, and ask if they can pay today.'
except Exception:
    vars['product_count'] = 0
    vars['account_facts'] = 'No product data could be read. Use the get_account result above.'
    vars['opening_line'] = 'Thank you, you are verified. Tell the customer, from the get_account result, that you are calling from the collections team about a late payment, name each product, its past-due amount and days late, and ask if they can pay today.'
'''

VERIFY_HOOK = r'''
try:
    d = result.get('data') if isinstance(result, dict) else None
    if isinstance(result, dict):
        result.pop('header', None)
    if isinstance(d, dict):
        left = d.get('wrong_answers_left')
        if str(d.get('all_verified')).lower() == 'true':
            d['what_to_do_next'] = 'Both answers passed. Say nothing yet; the account is being loaded.'
        elif d.get('ok') is False or str(d.get('ok')).lower() == 'false':
            d['what_to_do_next'] = 'The answer could not be read and was not counted. Ask for the same answer again; for a date, ask for the day, the month as a word, and the year.'
        elif d.get('hint') == 'day_month_swapped':
            d['what_to_do_next'] = 'Day and month look swapped. This is not a wrong answer. Ask the customer to say the date of birth again with the month as a word.'
        elif str(d.get('verified')).lower() == 'true':
            d['what_to_do_next'] = 'That answer is correct. Now ask for the last four digits of the phone number on file.'
        elif str(left) == '0':
            d['what_to_do_next'] = 'No attempts are left. Do not ask anything more.'
        else:
            d['what_to_do_next'] = 'That answer is wrong. Wrong answers left: ' + str(left) + '. Tell the customer it did not match and ask the same question again.'
except Exception:
    pass
'''

for _c in (SETUP_CODE, PREPARE_CODE, VERIFY_HOOK):
    assert "{{" not in _c and "}}" not in _c


# ------------------------------------------------------------------ helpers

def leaf(typ, default, desc="", enum=None):
    d = {"type": typ, "default": default}
    if desc:
        d["description"] = desc
    if enum:
        d["enum"] = enum
    return d


def api_tool(name, path, fields, desc, retries=0, post=None):
    t = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": retries},
         "function": {"name": name, "handler": "__function__:api_call", "description": desc,
                      "parameters": {"type": "object", "properties": {
                          "url": leaf("string", SERVER + "/" + path), "method": leaf("string", "POST"),
                          "headers": {"type": "object", "properties": {"Content-Type": leaf("string", "application/json")}},
                          "body": {"type": "object", "properties": fields,
                                   "required": [k for k in fields if k != "customer_id"]}}}}}
    if post:
        t["post_process_code"] = post
    return t


CID = leaf("string", "{{customer_id}}")


def code_node(name, code, nxt):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {
                "name": "code_exec", "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": [always(nxt)]}


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def det(target, desc, *alts):
    conds = [a[0] if len(a) == 1 else {"logic": "and", "conditions": list(a)} for a in alts]
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": conds}}


def v(name, op, operand=None):
    c = {"variable": name, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return c


def tc(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def end_tool(cid):
    """Name of the transition tool the model sees for close:<cid> after lowering (precedence router in front)."""
    return "transition_to_end_" + "".join(c if c.isalnum() else "_" for c in cid).strip("_")


def conv(name, task, tools=(), transitions=(), on_enter=None, max_turns=20, max_target=None, first_only=False):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": list(tools),
         "transitions": list(transitions), "max_node_turns": max_turns}
    if max_target:
        n["max_turn_transition"] = max_target
    if on_enter:
        n["on_enter"] = on_enter
    if first_only:
        n["on_enter_first_entry_only"] = True
    return n


def ok_true(var):
    return [[v(var, "equals", "true")], [v(var, "equals", "True")]]


# ------------------------------------------------------------------ tools

VERIFY = api_tool("verify_identity", "verify_identity", {
    "customer_id": CID,
    "field": leaf("string", "{{field}}", "Which question this answer is for: date_of_birth or phone_last4.", ["date_of_birth", "phone_last4"]),
    "answer": leaf("string", "{{answer}}", "date_of_birth as YYYY-MM-DD (numbers-only dates are day, month, year); phone_last4 as four digits."),
}, "Check one security answer. CALL it every time the customer gives a date of birth or the last four phone digits, one answer per call.",
    post=VERIFY_HOOK)

GET_ACCOUNT = api_tool("get_account", "get_account", {"customer_id": CID}, "Get the late products.", retries=2)

CALLBACK = api_tool("schedule_callback", "schedule_callback", {
    "customer_id": CID,
    "date": leaf("string", "{{date}}", "Callback date, YYYY-MM-DD. Only today or the next business day, from the callback window."),
    "time": leaf("string", "{{time}}", "Callback time, HH:MM 24 hour, from 10:00 to 19:00 and later than now."),
}, "Book a callback. CALL it as soon as the person gives a day and time that is inside the callback window.")


def transfer(queue, when):
    return api_tool("transfer_" + {"restructuring": "restructuring", "general": "human", "support": "support"}[queue],
                    "transfer_to_agent", {"customer_id": CID, "queue": leaf("string", queue, "", [queue])},
                    "Transfer the call to the " + queue + " queue. CALL it " + when)


T_RESTR = transfer("restructuring", "when the customer asks for a new payment plan or lower instalments. Describe no plan yourself.")
T_HUMAN = transfer("general", "when the customer insists on speaking to a person after you asked once whether you can help first.")
T_SUPPORT = transfer("support", "when a customer in hardship (illness, death in the family, job loss) accepts your offer to connect them with the customer support team.")


def create_promise(i, single):
    name = "create_promise" if single else f"create_promise_{i}"
    which = "the product" if single else f"product {i} (in the account facts order)"
    return api_tool(name, "create_promise", {
        "customer_id": CID,
        "product_id": leaf("string", "{{pid_%d}}" % i, f"product_id of {which}."),
        "amount": leaf("number", "{{amount}}", "The confirmed PTP amount, a number."),
        "date": leaf("string", "{{date}}", "The confirmed PTP date, YYYY-MM-DD."),
    }, f"Record the PTP for {which}. CALL it only after the customer said a clear yes to the read-back. One call per message.")


def add_note(i):
    return api_tool(f"add_note_{i}", "add_note", {
        "customer_id": CID,
        "product_id": leaf("string", "{{pid_%d}}" % i, f"product_id of product {i}."),
        "reason": leaf("string", "{{reason}}", "Why product %d ended without a PTP. One of: refused, hardship, dispute, paid, service_error." % i,
                       ["refused", "hardship", "dispute", "paid", "service_error"]),
    }, f"Leave the note for product {i} (in the account facts order) when it ends without a recorded PTP. "
       f"CALL it only in this recording step, at most once, and never for a product that has no product {i}.")


# ------------------------------------------------------------------ prompts

SYSTEM = """You are Freya Bank's digital assistant on an outbound call to {{title}} {{first_name}} {{last_name}}. Speak English. Keep each turn to one to three short sentences. Address the customer as {{title}} {{last_name}}.

Rules for the whole call:
- Never offer a discount, a waiver, an instalment plan or any term that is not in your instructions.
- If you are asked something your instructions and tool results cannot answer, say you do not have that information. Never invent figures, dates or reasons.
- "Is this a scam?": say they can verify the call by phoning Freya Bank's customer service number, then go on.
- "Am I talking to a robot / an AI?": say you are Freya Bank's digital assistant, then go on.
- When your instructions say to call a tool, call it. Saying you did it is not enough. Call one tool per message. After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- Never say that something is recorded, booked or transferred unless that tool returned ok: true. If a tool fails, say so.
- A tool whose name starts with transition_to_end_ ends the call; a thank-you and goodbye are played after it. Call it with no text of your own unless the instructions ask you to say something first.
- The current date and time is {{now}}. Work every date out from it, never from your own clock."""

PRE_VERIFY = ("Until identity is verified, never say \"collections\", \"debt\", \"payment\", or the product, and never say why you are calling, "
              "to anyone, relatives included. If asked why you are calling, say you can only discuss it with {{title}} {{last_name}} after a short security check.")

HUMAN_RULE = ("If the person asks for a human, ask once whether you can help first. If they insist, call transfer_human.")

OPENING_TASK = f"""Your only job now is to find out who answered. You already said that you are Freya Bank's digital assistant, that the call is recorded, and asked "Am I speaking with {{{{title}}}} {{{{last_name}}}}?".
{PRE_VERIFY}

- Only "yes", "that's me", "speaking" or the customer's own name confirm. Then call transition_to_security with no text.
- "Hello", "go ahead", "who is this" and similar do not confirm. Ask once more: "Am I speaking with {{{{title}}}} {{{{last_name}}}}?". If the person asked a robot or scam question instead, answer it first; the ask that follows counts as the second ask. If it is still unclear after the second ask, call {end_tool('not_reached/unclear')}.
- Someone else answered (for example a relative or colleague), and the number is the customer's: call transition_to_third_party with no text.
- The person says this number does not belong to that person: call {end_tool('not_reached/wrong_number')}.
- The person says the customer has died: call {end_tool('not_reached/deceased')} at once. The goodbye that follows says "I am sorry for your loss." Ask nothing else.
- The person says a second time that they do not want to talk: call {end_tool('not_verified/declined')}.
- {HUMAN_RULE}
Call no other tool in this step."""

THIRD_TASK = f"""Someone other than {{{{title}}}} {{{{last_name}}}} is on the line. Say nothing beyond the opening sentence and do not say why you are calling. Ask no security questions and tell them nothing about any account, even if they offer to pay.
Ask when {{{{title}}}} {{{{last_name}}}} can be reached.

Callback window (the only times you may book):
{{{{cb_facts}}}}

- When the person gives a day and time inside the window, call schedule_callback with date YYYY-MM-DD and time HH:MM. Turn "this afternoon at three" into today and 15:00. If the call fails, say so and call it once more.
- If they offer a day or a time outside the window (or only a vague time), say which times are possible and ask once for another time. If the next answer is outside the window too, or they cannot give one, call {end_tool('not_reached/no_callback')}.
- The number does not belong to the customer: call {end_tool('not_reached/wrong_number')}.
- The customer has died: call {end_tool('not_reached/deceased')} at once and ask nothing else.
- The person turns out to be {{{{title}}}} {{{{last_name}}}} after all: call transition_to_security.
- {HUMAN_RULE}"""

SECURITY_TASK = f"""Security check. {PRE_VERIFY} Never state any debt here.

Ask two questions, one at a time: first the date of birth, then the last four digits of the phone number on file. Call verify_identity for every answer, with field date_of_birth or phone_last4. Follow the what_to_do_next line of each result.
- A date of birth is sent as YYYY-MM-DD, whatever way the customer said it. A date given only in numbers is day, then month, then year: "03/04/1985" is 1985-04-03.
- A day_month_swapped hint is not a wrong answer: ask them to say the date again with the month as a word, and send it again.
- After a wrong answer, say it did not match and ask the same question again.
- If the customer does not want to answer, or asks what the call is about instead of answering, explain once that these questions protect their account, and ask again. At the second refusal or the second such question, call {end_tool('not_verified/declined')}.
- If the customer says a second time that they do not want to talk, call {end_tool('not_verified/declined')}.
- {HUMAN_RULE}
- When both answers pass, or when no attempts are left, the next step starts by itself. Do not say goodbye."""

PTP_RULES = """How to get a promise to pay (PTP). Follow every rule; never improvise.
Amounts:
- You propose every amount yourself. Never ask "how much can you pay?". Start with the full past-due amount.
- If the customer says the full amount is too much, offer the floor once and say that the rest stays overdue. If they refuse the floor, that is a flat refusal.
- An amount the customer proposes from the floor up to the full amount, both included, is accepted. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept it, that is a flat refusal.
Dates:
- A PTP date must be today or later, a business day, and not after that product's deadline. Use the calendar in the date facts.
- A weekend day or bank holiday that is not after the deadline: offer the next business day.
- A date after the deadline: say the latest date you can record is the deadline and offer it. Refusing the deadline is a flat refusal.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still name none, propose the deadline.
- "next <weekday>" and "this <weekday>": use the lines in the date facts. "Next Friday" said on a Friday is the Friday of the following week.
Persuasion:
- A date or an amount the customer proposes is never a refusal; handle it with the rules above.
- A flat refusal or a non-answer uses one persuasion attempt. "No" to paying today, with no date and no amount, is a flat refusal.
- Attempt 1: offer the attempt 1 line of the product (the full amount, or the floor if the customer already said the full amount is too much, on the attempt 1 date).
- Attempt 2, late stage only: offer the floor on the deadline.
- When the product's attempts are used up and the customer still refuses, stop. Never repeat an offer the customer already refused.
Hardship (illness, a death in the family, job loss): say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_support. If the customer still names a date or an amount themselves, take it as a PTP under the rules above.
Read-back: read back the product, the amount and the date and ask "Do you confirm?". Only a clear yes confirms. If the customer changes the date or the amount, check the new value with the rules above and read back again.
Other requests:
- A new payment plan or lower instalments: describe no plan and call transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_human.
- A recorded PTP cannot be changed or cancelled in this call; they can change it in the mobile app.
- If a transfer tool fails, say so and call it once more."""

FACTS = """Account facts (computed from get_account; trust them):
{{account_facts}}

Date facts:
{{date_facts}}"""

ENTER_NEGOTIATE = {"type": "llm", "prompt": "Say exactly this, and nothing else: {{opening_line}}"}

A_NEGOTIATE = f"""The customer is verified. You already told them what is overdue and asked whether they can pay it today.

{FACTS}

{PTP_RULES}

Recording:
- After a clear yes to the read-back, call create_promise with the amount and the date (YYYY-MM-DD). Do not say it is recorded before the result is ok: true.
- If create_promise fails, tell the customer it did not work and call it once more with the same values.

Endings (call the tool; the goodbye is played after it):
- The product's persuasion attempts are used up and the customer still refuses, or the customer said twice that they do not want to talk: call {end_tool('no_promise/refused')}.
- Hardship and the customer declined the support team, with no date or amount of their own: call {end_tool('no_promise/hardship')}.
- The customer already paid this past-due amount: first tell them payments can take one business day to appear, take no PTP, then call {end_tool('paid')}.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no PTP, call {end_tool('no_promise/dispute')}."""

A_AFTER = """The PTP is recorded and you told the customer they will receive a text message confirming it.
- If the customer asks to change or cancel the PTP, say it cannot be changed in this call and that they can change it in the mobile app.
- A new payment plan or lower instalments: call transfer_restructuring. A request for a human: ask once whether you can help first; if they insist, call transfer_human.
- When the customer has nothing else, or says goodbye, call """ + end_tool("promise") + "."

B_NEGOTIATE = f"""The customer is verified. You already told them every late product, one sentence per product, and asked whether they can pay all of them today.

{FACTS}

Order of work:
- If the customer will pay all products today, the PTP for each product is its full past-due amount today.
- If not, take the products one at a time, in the order of the account facts. Do not ask about today again for each product. Each product has its own deadline, floor and number of persuasion attempts, and each starts at attempt 1. Count attempts per product.
- If the customer names one date for everything and it is after one product's deadline, that product gets its own deadline and the read-back says so. The other products keep the named date.
- A dispute or an "I already paid" about one product does not end the call. For "I already paid", tell them payments can take one business day to appear. Remember the outcome for that product, take no PTP for it, and go on with the next product.
- Hardship: no persuasion attempts on any remaining product; offer the support team once. Products the customer does not give a date or amount for end with outcome hardship.

{PTP_RULES}

When every product has an outcome (an agreed PTP, refused, hardship, dispute or already paid):
- If at least one PTP was agreed, read back all agreed PTPs together (product, amount, date) and ask once "Do you confirm?". After a clear yes, call transition_to_record with no text.
- If no PTP was agreed, call transition_to_record with no text.
- If the customer says twice that they do not want to talk, call transition_to_record with no text; every product without an agreed PTP ends as refused.
Do not record or note anything in this step, and do not say goodbye."""

B_RECORD = f"""Record the outcome of every product. Ask the customer nothing new.

{FACTS}

1. For each product with a PTP the customer confirmed, in the order of the account facts, call its create_promise_<n> tool (n is the product number) with the confirmed amount and date (YYYY-MM-DD). One call per message. If a call fails, call it once more with the same values. If it fails twice, tell the customer that this PTP could not be recorded; that product ends with reason service_error. PTPs already recorded stay.
2. Then, for each product that ends without a recorded PTP, call its add_note_<n> tool once with one reason: refused, hardship, dispute, paid or service_error. Products with a recorded PTP get no note. Only products that exist in the account facts get a note.
3. Then tell the customer in one sentence which PTPs are recorded, if any, and call transition_to_finish_1 in the same message.
- A new payment plan or lower instalments: call transfer_restructuring at once and add no notes. A request for a human: ask once whether you can help first; if they insist, call transfer_human and add no notes.
Never say goodbye yourself; it is played after the call ends."""


# ------------------------------------------------------------------ bodies

def head_nodes(after_verify):
    tr_transfers_pre = [det("close:transferred/human", "transferred to a person", [v("transfer_human_success_count", "greater_than", 0)])]
    return {
        "setup": code_node("setup", SETUP_CODE, "opening"),
        "opening": conv("opening", OPENING_TASK, [T_HUMAN], tr_transfers_pre + [
            tc("security", "The person confirmed they are the customer: they said yes, that's me, speaking, or the customer's own name."),
            tc("third_party", "Someone other than the customer answered, and the number is the customer's."),
            tc("close:not_reached/wrong_number", "The person said this number does not belong to the customer."),
            tc("close:not_reached/deceased", "The person said the customer has died."),
            tc("close:not_reached/unclear", "After the second ask it is still unclear whether the customer is on the line."),
            tc("close:not_verified/declined", "The person said a second time that they do not want to talk."),
        ], on_enter={"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
            max_turns=8, max_target="close:not_reached/unclear", first_only=True),
        "third_party": conv("third_party", THIRD_TASK, [CALLBACK, T_HUMAN], [
            det("close:not_reached/callback", "callback booked", [v("schedule_callback_success_count", "greater_than", 0)]),
            det("close:transferred/human", "transferred to a person", [v("transfer_human_success_count", "greater_than", 0)]),
            tc("close:not_reached/no_callback", "No callback time inside the window after asking once for another time."),
            tc("close:not_reached/wrong_number", "The number does not belong to the customer."),
            tc("close:not_reached/deceased", "The customer has died."),
            tc("security", "The person on the line is the customer after all."),
        ], max_turns=10, max_target="close:not_reached/no_callback"),
        "security": conv("security", SECURITY_TASK, [VERIFY, T_HUMAN], [
            det("load_account", "both security answers passed",
                *ok_true("verify_identity_response.data.all_verified")),
            det("close:not_verified/failed", "no wrong answers left",
                [v("verify_identity_response.data.wrong_answers_left", "equals", "0")]),
            det("close:transferred/human", "transferred to a person", [v("transfer_human_success_count", "greater_than", 0)]),
            tc("close:not_verified/declined", "The customer refused the security questions a second time, asked a second time what the call is about instead of answering, or said twice they do not want to talk."),
        ], on_enter={"type": "tts", "text": "Thank you. Before I go on, I need to ask you two security questions. First, what is your date of birth?"},
            max_turns=14, max_target="close:not_verified/declined", first_only=True),
        "load_account": {
            "name": "load_account", "node_type": "api_request", "passthrough": True,
            "passthrough_default_transition": "prepare", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [GET_ACCOUNT], "response_mapping": [{"path": "data.products", "variable": "products"}],
            "transitions": [
                det("close:no_promise/account_error", "the account could not be loaded",
                    [v("load_account_failure_count", "greater_than", 0)]),
                always("prepare")]},
        "prepare": code_node("prepare", PREPARE_CODE, after_verify),
    }


TRANSFER_EXITS = [
    det("close:transferred/restructuring", "transferred to restructuring", [v("transfer_restructuring_success_count", "greater_than", 0)]),
    det("close:transferred/human", "transferred to a person", [v("transfer_human_success_count", "greater_than", 0)]),
    det("close:transferred/support", "transferred to support", [v("transfer_support_success_count", "greater_than", 0)]),
]


def body_a():
    nodes = head_nodes("negotiate")
    nodes["negotiate"] = conv("negotiate", A_NEGOTIATE, [create_promise(1, True), T_RESTR, T_HUMAN, T_SUPPORT], [
        det("after_promise", "the PTP was recorded", [v("create_promise_success_count", "greater_than", 0)]),
        det("close:no_promise/service_error", "create_promise failed twice", [v("create_promise_failure_count", "greater_than", 1)]),
        *TRANSFER_EXITS,
        tc("close:no_promise/refused", "Persuasion attempts are used up and the customer still refuses, or the customer said twice they do not want to talk."),
        tc("close:no_promise/hardship", "Hardship, and the customer declined the support team and gave no date or amount."),
        tc("close:paid", "The customer already paid this past-due amount, and you told them payments can take one business day to appear."),
        tc("close:no_promise/dispute", "The customer says the debt is not theirs, never had the product, or it was closed or paid off in the past."),
    ], on_enter=ENTER_NEGOTIATE, max_turns=40, max_target="close:no_promise/refused", first_only=True)
    nodes["after_promise"] = conv("after_promise", A_AFTER, [T_RESTR, T_HUMAN], [
        det("close:transferred/restructuring", "transferred to restructuring", [v("transfer_restructuring_success_count", "greater_than", 0)]),
        det("close:transferred/human", "transferred to a person", [v("transfer_human_success_count", "greater_than", 0)]),
        tc("close:promise", "The customer has nothing else or says goodbye."),
    ], on_enter={"type": "tts", "text": "Thank you, your promise is recorded. You will receive a text message confirming this promise."},
        max_turns=6, max_target="close:promise", first_only=True)
    return wf(nodes)


def body_b():
    nodes = head_nodes("negotiate")
    nodes["negotiate"] = conv("negotiate", B_NEGOTIATE, [T_RESTR, T_HUMAN, T_SUPPORT], [
        *TRANSFER_EXITS,
        tc("record", "Every product has an outcome and the customer confirmed the read-back of all agreed PTPs, or no PTP was agreed, or the customer said twice they do not want to talk."),
    ], on_enter=ENTER_NEGOTIATE, max_turns=60, max_target="record", first_only=True)
    nodes["record"] = conv("record", B_RECORD,
                           [create_promise(i, False) for i in (1, 2, 3)] + [add_note(i) for i in (1, 2, 3)] + [T_RESTR, T_HUMAN],
                           [det("close:transferred/restructuring", "transferred to restructuring", [v("transfer_restructuring_success_count", "greater_than", 0)]),
                            det("close:transferred/human", "transferred to a person", [v("transfer_human_success_count", "greater_than", 0)]),
                            tc("finish_1", "Every PTP is recorded or failed twice, every product without a recorded PTP has its note, and you told the customer which PTPs are recorded.")],
                           on_enter={"type": "llm", "prompt": "Start recording now: call the first tool your instructions require. Say nothing before it."},
                           max_turns=12, max_target="finish_1", first_only=True)
    # Close code (CN-12 E) when no PTP was recorded: the reason of the first product, in get_account order, whose
    # note is not paid; all paid -> paid. Precedence rules put promise and transfers first.
    for i in (1, 2, 3):
        nxt = f"finish_{i + 1}" if i < 3 else "finish_paid"
        nodes[f"finish_{i}"] = {
            "name": f"finish_{i}", "node_type": "conversation", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "task_message": "Do not call a tool in this turn.",
            "transitions": [det(f"close:no_promise/{r}", f"product {i} noted {r}", [v(f"add_note_{i}_args.reason", "equals", r)])
                            for r in ("refused", "hardship", "dispute", "service_error")] + [always(nxt)]}
    nodes["finish_paid"] = {
        "name": "finish_paid", "node_type": "conversation", "passthrough": True, "passthrough_default_transition": "close:no_promise/refused",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "task_message": "Do not call a tool in this turn.",
        "transitions": [det("close:paid", "every noted product is paid", [v("add_note_1_args.reason", "equals", "paid")]),
                        always("close:no_promise/refused")]}
    return wf(nodes)


def wf(nodes):
    return {"initial_node": "setup", "system_prompt": SYSTEM, "global_nodes": {}, "nodes": nodes,
            "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}


# ------------------------------------------------------------------ closing plans

def row(outcome, reason, used):
    return f"| `{outcome}` | `{reason}` | {used} |"


BYE = "Thank you for your time, {{title}} {{last_name}}. Goodbye."


def plan(brief, multi):
    ev = lambda q, src=brief: [{"source": src, "quote": q}]
    A_ = lambda q: [{"source": A, "quote": q}]
    closings = {
        "promise": {"set": {"outcome": "promise"},
                    "say": "You will receive a text message confirming this promise. " + BYE,
                    "evidence": A_("| `promise` | (none) | at least one PTP was recorded |")},
        "paid": {"set": {"outcome": "paid"}, "say": BYE,
                 "evidence": A_("| `paid` | (none) | the customer already paid (CP-4 2.8 e) |")},
        "transferred/restructuring": {"set": {"outcome": "transferred", "reason": "restructuring"},
                                      "say": "I am transferring you now. " + BYE,
                                      "evidence": A_(row("transferred", "restructuring", "new plan or lower instalments (2.8 c)"))},
        "transferred/human": {"set": {"outcome": "transferred", "reason": "human"},
                              "say": "I am transferring you now. " + BYE,
                              "evidence": A_(row("transferred", "human", "the customer insisted on a person (2.8 d)"))},
        "transferred/support": {"set": {"outcome": "transferred", "reason": "support"},
                                "say": "I am transferring you to the customer support team now. " + BYE,
                                "evidence": A_(row("transferred", "support", "hardship, customer accepted the support team (2.7 d)"))},
        "no_promise/refused": {"set": {"outcome": "no_promise", "reason": "refused"}, "say": BYE,
                               "evidence": A_(row("no_promise", "refused", "attempts used up, or said twice they do not want to talk (2.7 c, 2.8 g)"))},
        "no_promise/hardship": {"set": {"outcome": "no_promise", "reason": "hardship"}, "say": BYE,
                                "evidence": A_(row("no_promise", "hardship", "hardship, customer declined the support team (2.7 d)"))},
        "no_promise/dispute": {"set": {"outcome": "no_promise", "reason": "dispute"}, "say": BYE,
                               "evidence": A_(row("no_promise", "dispute", "not mine, never had it, closed or paid off in the past (2.8 f)"))},
        "no_promise/service_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                     "say": ("I am sorry for the technical problem. " if multi else
                                             "I am sorry, I could not record your promise because of a technical problem. ") + BYE,
                                     "evidence": A_(row("no_promise", "service_error", "`create_promise` failed twice (2.8 b)"))},
        "no_promise/account_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                     "say": "I am sorry, I cannot reach your account details because of a technical problem, so I cannot go on with this call. " + BYE,
                                     "evidence": A_(row("no_promise", "service_error", "`create_promise` failed twice (2.8 b)"))},
        "not_verified/failed": {"set": {"outcome": "not_verified", "reason": "failed"},
                                "say": "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. " + BYE,
                                "evidence": A_(row("not_verified", "failed", "three wrong security answers (2.3 d)"))},
        "not_verified/declined": {"set": {"outcome": "not_verified", "reason": "declined"}, "say": "I understand. Thank you for your time. Goodbye.",
                                  "evidence": A_(row("not_verified", "declined", "refused the security questions, or did not want to talk before verification (2.3 e, 2.8 g)"))},
        "not_reached/callback": {"set": {"outcome": "not_reached", "reason": "callback"},
                                 "say": "Thank you, we will call back at that time. Goodbye.",
                                 "evidence": A_(row("not_reached", "callback", "callback booked (2.2 b, memo item 2)"))},
        "not_reached/no_callback": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "say": "Thank you for your time. Goodbye.",
                                    "evidence": A_(row("not_reached", "no_callback", "no time inside the window (2.2 c)"))},
        "not_reached/wrong_number": {"set": {"outcome": "not_reached", "reason": "wrong_number"},
                                     "say": "I apologise for the inconvenience. Thank you for your time. Goodbye.",
                                     "evidence": A_(row("not_reached", "wrong_number", "the number is not the customer's (2.2 d)"))},
        "not_reached/deceased": {"set": {"outcome": "not_reached", "reason": "deceased"},
                                 "say": "I am sorry for your loss. Thank you for your time. Goodbye.",
                                 "evidence": A_(row("not_reached", "deceased", "the customer has died (2.2 e)"))},
        "not_reached/unclear": {"set": {"outcome": "not_reached", "reason": "unclear"}, "say": "Thank you for your time. Goodbye.",
                                "evidence": A_(row("not_reached", "unclear", "still unclear who answered after the second ask (2.1 c)"))},
    }
    transfer_ev = A_("If a transfer follows a recorded PTP, the call closes as `transferred` with that transfer's reason.")
    rules = []
    for cid, tool in (("transferred/restructuring", "transfer_restructuring"), ("transferred/human", "transfer_human"),
                      ("transferred/support", "transfer_support")):
        rules.append({"closing": cid, "when": [{"variable": f"{tool}_success_count", "operator": "greater_than", "operand": 0}],
                      "keep": [], "evidence": transfer_ev})
    keep_t = ["transferred/restructuring", "transferred/human", "transferred/support"]
    promise_ev = A_("| `promise` | (none) | at least one PTP was recorded |")
    if multi:
        promise_ev = promise_ev + [{"source": B, "quote": "`promise` is used whenever at least one PTP was recorded, except in the case of D1."}]
        for i in (1, 2, 3):
            rules.append({"closing": "promise", "when": [{"variable": f"create_promise_{i}_success_count", "operator": "greater_than", "operand": 0}],
                          "keep": keep_t, "evidence": promise_ev})
    else:
        rules.append({"closing": "promise", "when": [{"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}],
                      "keep": keep_t, "evidence": promise_ev})
    rules.append({"closing": "not_verified/failed",
                  "when": [{"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"}],
                  "keep": [], "evidence": A_("After three wrong answers the assistant does not state the debt, tells the customer to use the mobile app or a branch, and closes as not verified, failed.")})
    return {
        "terminal": {"tool": "close_call", "evidence": [
            {"source": API, "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
            {"source": A, "quote": "Every call ends with exactly one `close_call`, as the last tool call"}]},
        "fields": {"customer_id": "{{customer_id}}"},
        "closings": closings,
        "precedence": rules,
    }


if __name__ == "__main__":
    for slot, body, multi in (("brief-a-raw", body_a(), False), ("brief-b-raw", body_b(), True)):
        (OUT / f"{slot}.body.json").write_text(json.dumps(body, indent=1) + "\n")
        (OUT / f"{slot}.closing.json").write_text(json.dumps(plan(A if not multi else B, multi), indent=1) + "\n")
        print("wrote", slot)
