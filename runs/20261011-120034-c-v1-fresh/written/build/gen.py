"""Generate the Freya workflows for brief-a-raw (one product) and brief-b-raw (one to three products).

    python3 build/gen.py

Writes out/brief-a-raw.workflow.json, out/brief-b-raw.workflow.json and their contracts.
Every rule value below comes from briefs/brief-a-raw.md (with memo OPS-2026-41 applied) and briefs/brief-b-raw.md.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = json.loads((ROOT / "tools/openapi.json").read_text())
SERVER = API["servers"][0]["url"].rstrip("/")

# ---------------------------------------------------------------- brief values
# CP-4 2.5 a + memo item 1: full holiday list.
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]
# CP-4 2.5 b + memo item 3: early 1-7 -> 12th business day, 1 attempt; late 8-45 -> 7th business day, 2 attempts.
EARLY_MAX_DAYS, EARLY_BD, EARLY_ATTEMPTS = 7, 12, 1
LATE_BD, LATE_ATTEMPTS = 7, 2
# CP-4 2.2 b + memo item 2: callback today or next business day, 10:00-19:00 inclusive, later than now.
CB_START, CB_END = "10:00", "19:00"


# ---------------------------------------------------------------- helpers

def body_field(typ, default, description=None, enum=None):
    f = {"type": typ, "default": default}
    if description:
        f["description"] = description
    if enum:
        f["enum"] = enum
    return f


def api_tool(name, path, fields, description, required=None, retries=0, post=None):
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": SERVER + path},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": fields, "required": required or []},
                },
            },
        },
    }
    if post:
        t["post_process_code"] = post
    return t


def cond_var(var, op, operand=None):
    c = {"variable": var, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return {"logic": "or", "conditions": [c]}


def cond_any(*checks):
    return {"logic": "or", "conditions": [{"variable": v, "operator": o, "operand": x} for v, o, x in checks]}


def go(target, description, condition):
    return {"target_node": target, "description": description, "condition": condition}


def tool_go(target, description):
    return {"target_node": target, "description": description, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": description}}


ALWAYS = {"operator": "always"}

POST_PREFIX = (
    "try:\n"
    "    if isinstance(result, dict):\n"
    "        result.pop('header', None)\n"
    "        d = result.get('data')\n"
    "        if not isinstance(d, dict):\n"
    "            d = dict(ok=False, error='service_failed')\n"
    "            result['data'] = d\n"
)
POST_SUFFIX = "except Exception:\n    pass\n"

VERIFY_POST = POST_PREFIX + (
    "        left = d.get('wrong_answers_left')\n"
    "        if d.get('all_verified') is True:\n"
    "            msg = 'Both security answers are verified.'\n"
    "        elif d.get('hint') == 'day_month_swapped':\n"
    "            msg = 'Day and month look swapped. This is NOT a wrong answer. Ask the customer to say the month of their date of birth as a word, then call verify_identity again.'\n"
    "        elif d.get('ok') is False or d.get('verified') is None:\n"
    "            msg = 'The answer could not be checked (not readable, or the service failed). This is NOT a wrong answer. Ask the customer to repeat it; for the date of birth ask for the day, the month as a word, and the year.'\n"
    "        elif d.get('verified') is True:\n"
    "            msg = 'This answer is correct. Now ask for the last four digits of the phone number on file.'\n"
    "        elif left is not None and str(left) in ('0', '0.0'):\n"
    "            msg = 'Wrong answer. No tries are left. Do not mention any account or amount.'\n"
    "        else:\n"
    "            msg = 'Wrong answer. Ask the same question again. Wrong answers left: ' + str(left) + '.'\n"
    "        d['what_to_do_next'] = msg\n"
) + POST_SUFFIX

PROMISE_POST = POST_PREFIX + (
    "        if d.get('ok') is True:\n"
    "            d['what_to_do_next'] = 'The promise is recorded.'\n"
    "        else:\n"
    "            d['what_to_do_next'] = 'NOT recorded. If this was the first failure for this product, call create_promise once more with exactly the same values. If it was the second failure, tell the customer you could not record this promise. Never say it is recorded.'\n"
) + POST_SUFFIX

NOTE_POST = POST_PREFIX + (
    "        if d.get('ok') is True:\n"
    "            d['what_to_do_next'] = 'The note is saved.'\n"
    "        else:\n"
    "            d['what_to_do_next'] = 'The note was NOT saved. Call add_note once more with the same values.'\n"
) + POST_SUFFIX

CALLBACK_POST = POST_PREFIX + (
    "        if d.get('ok') is True:\n"
    "            d['what_to_do_next'] = 'The callback is booked.'\n"
    "        else:\n"
    "            d['what_to_do_next'] = 'The callback was NOT booked. Call schedule_callback once more with the same values. Never say it is booked unless a result says so.'\n"
) + POST_SUFFIX

# ---------------------------------------------------------------- code steps
# Shared date arithmetic. No functions (the sandbox may run the snippet with separate globals and locals),
# no double braces.
DATE_CODE = """import datetime, json
HOL = set(%(hol)s)
NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
ONE = datetime.timedelta(days=1)
raw = str(vars.get('now') or '').strip()
try:
    nowdt = datetime.datetime.fromisoformat(raw[:16])
except Exception:
    try:
        nowdt = datetime.datetime.fromisoformat(raw[:10] + 'T09:00')
    except Exception:
        nowdt = datetime.datetime(2026, 10, 14, 11, 0)
today = nowdt.date()
bds = []
d = today
while len(bds) < 40:
    d = d + ONE
    if d.weekday() < 5 and d.isoformat() not in HOL:
        bds.append(d)
monday = today - datetime.timedelta(days=today.weekday())
first = None
for wk in (0, 7):
    c = monday + datetime.timedelta(days=wk + 4)
    while c >= monday + datetime.timedelta(days=wk) and (c.weekday() >= 5 or c.isoformat() in HOL):
        c = c - ONE
    if c >= monday + datetime.timedelta(days=wk) and c > today:
        first = c
        break
dl_early = bds[%(early_bd)d - 1]
dl_late = bds[%(late_bd)d - 1]
""" % {"hol": json.dumps(HOLIDAYS), "early_bd": EARLY_BD, "late_bd": LATE_BD}

SETUP_CODE = DATE_CODE + """try:
    lines = []
    lines.append('Today is ' + NAMES[today.weekday()] + ' ' + today.isoformat() + ', time now ' + nowdt.strftime('%%H:%%M') + '.')
    lines.append('Business days are Monday to Friday except bank holidays. Bank holidays: ' + ', '.join(sorted(HOL)) + '.')
    lines.append('Day by day (date, weekday, status):')
    end = dl_early + datetime.timedelta(days=10)
    d = today
    while d <= end:
        tag = ''
        if d == today:
            tag = ' (today)'
        elif d == today + ONE:
            tag = ' (tomorrow)'
        if d.weekday() >= 5 or d.isoformat() in HOL:
            nb = d + ONE
            while nb.weekday() >= 5 or nb.isoformat() in HOL:
                nb = nb + ONE
            kind = 'bank holiday' if d.isoformat() in HOL else 'weekend'
            lines.append('- ' + d.isoformat() + ' ' + NAMES[d.weekday()] + tag + ': NOT a business day (' + kind + '); next business day ' + nb.isoformat() + ' ' + NAMES[nb.weekday()])
        else:
            lines.append('- ' + d.isoformat() + ' ' + NAMES[d.weekday()] + tag + ': business day')
        d = d + ONE
    lines.append('Weekday words ("this X" = the X of the current week, Monday to Sunday; "next X" = the X of the following calendar week):')
    for i in range(7):
        a = monday + datetime.timedelta(days=i)
        b = monday + datetime.timedelta(days=7 + i)
        lines.append('- this ' + NAMES[i] + ' = ' + a.isoformat() + ('  (already past)' if a < today else '') + '; next ' + NAMES[i] + ' = ' + b.isoformat())
    vars['date_facts'] = chr(10).join(lines)
    nbd = bds[0]
    now_hm = nowdt.strftime('%%H:%%M')
    parts = []
    if now_hm < '%(cb_end)s':
        if now_hm >= '%(cb_start)s':
            parts.append('today, ' + NAMES[today.weekday()] + ' ' + today.isoformat() + ', at a time strictly later than ' + now_hm + ' and no later than %(cb_end)s')
        else:
            parts.append('today, ' + NAMES[today.weekday()] + ' ' + today.isoformat() + ', from %(cb_start)s to %(cb_end)s, both included')
    else:
        parts.append('today is no longer possible (it is after %(cb_end)s)')
    parts.append('the next business day, ' + NAMES[nbd.weekday()] + ' ' + nbd.isoformat() + ', from %(cb_start)s to %(cb_end)s, both included')
    vars['callback_rules'] = 'A callback can be booked only for: ' + '; or '.join(parts) + '. Every other day or time is outside the window. Tomorrow is ' + NAMES[(today + ONE).weekday()] + ' ' + (today + ONE).isoformat() + '.'
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Today: ' + str(vars.get('now'))
    vars['callback_rules'] = 'A callback can be booked only for today or the next business day, from %(cb_start)s to %(cb_end)s, later than now (' + str(vars.get('now')) + ').'
    vars['setup_state'] = 'error'
""" % {"cb_start": CB_START, "cb_end": CB_END}

PREPARE_CODE = DATE_CODE + """try:
    prods = vars.get('products')
    if prods is None:
        prods = vars.get('get_account_response.data.products')
    if isinstance(prods, str):
        try:
            prods = json.loads(prods)
        except Exception:
            try:
                prods = json.loads(prods.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
            except Exception:
                prods = None
    if isinstance(prods, dict):
        prods = [prods[k] for k in sorted(prods)]
    if not isinstance(prods, list) or not prods:
        rebuilt = []
        for i in range(3):
            item = dict()
            for pre in ('get_account_response.data.products.' + str(i) + '.', 'products.' + str(i) + '.', 'get_account_response.data.products[' + str(i) + '].'):
                for k in list(vars.keys()):
                    if str(k).startswith(pre):
                        item[str(k)[len(pre):]] = vars[k]
            if item:
                rebuilt.append(item)
        prods = rebuilt
    prods = [p for p in prods if isinstance(p, dict)][:3]
    sentences = []
    blocks = []
    ids = []
    for i, p in enumerate(prods):
        typ = str(p.get('type') or '')
        if typ == 'credit_card':
            words = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        elif typ == 'car_loan':
            words = 'car loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        else:
            words = 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        due = float(p.get('past_due'))
        late = int(float(p.get('days_late')))
        floor = float(floor) if floor not in (None, '') else due
        early = late <= %(early_max)d
        dl = dl_early if early else dl_late
        att = %(early_att)d if early else %(late_att)d
        a1 = first if first is not None and first <= dl else dl
        pid = str(p.get('product_id'))
        ids.append(pid)
        due_s = '%%.2f' %% due
        floor_s = '%%.2f' %% floor
        sentences.append('Your ' + words + ' has a past-due amount of ' + due_s + ' and is ' + str(late) + ' day' + ('' if late == 1 else 's') + ' late.')
        b = []
        b.append('PRODUCT ' + str(i + 1) + ': ' + words + ' (product_id ' + pid + ')')
        b.append('- full past-due amount: ' + due_s)
        b.append('- days late: ' + str(late) + ', stage: ' + ('early' if early else 'late'))
        b.append('- floor (' + floor_name + '): ' + floor_s)
        b.append('- PTP deadline (latest date that can be recorded): ' + dl.isoformat() + ' ' + NAMES[dl.weekday()])
        b.append('- persuasion attempts allowed: ' + str(att))
        b.append('- attempt 1: propose ' + due_s + ' (or the floor ' + floor_s + ' if the customer already said the full amount is too much) on ' + a1.isoformat() + ' ' + NAMES[a1.weekday()])
        if att >= 2:
            b.append('- attempt 2: propose the floor ' + floor_s + ' on the deadline ' + dl.isoformat() + ' ' + NAMES[dl.weekday()])
        else:
            b.append('- no attempt 2: after attempt 1 is refused, stop')
        blocks.append(chr(10).join(b))
    if prods:
        many = len(prods) > 1
        vars['intro_text'] = ('Thank you, your identity is confirmed. I am calling from the Freya Bank collections team about ' + ('late payments. ' if many else 'a late payment. ') + ' '.join(sentences) + (' Can you make all of these payments today?' if many else ' Can you make this payment today?'))
        vars['products_text'] = (chr(10) + chr(10)).join(blocks)
        vars['product_count'] = len(prods)
        vars['p1_product_id'] = ids[0]
        vars['acct_state'] = 'ok'
    else:
        vars['acct_state'] = 'error'
except Exception as e:
    vars['acct_state'] = 'error'
""" % {"early_max": EARLY_MAX_DAYS, "early_att": EARLY_ATTEMPTS, "late_att": LATE_ATTEMPTS}

for _c in (SETUP_CODE, PREPARE_CODE, VERIFY_POST, PROMISE_POST, NOTE_POST, CALLBACK_POST):
    assert "{{" not in _c and "}}" not in _c


def code_node(name, code, ok_var, ok_target, fail_target):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": fail_target,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code},
                             "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [go(ok_target, "the step worked", cond_var(ok_var, "equals", "ok")),
                        go(fail_target, "always", ALWAYS)],
    }


# ---------------------------------------------------------------- closings

GOODBYE = "Thank you for your time, {{title}} {{last_name}}. Goodbye."


def closings(multi):
    c = {
        # name: (outcome, reason or None, farewell spoken before close_call)
        "close_promise": ("promise", None,
                          ("You will receive a text message confirming this promise. " + GOODBYE) if multi else
                          ("Your promise to pay is recorded. You will receive a text message confirming this promise. " + GOODBYE)),
        "close_paid": ("paid", None, "Thank you for letting us know. Payments can take one business day to appear. " + GOODBYE),
        "close_transferred_restructuring": ("transferred", "restructuring", ""),
        "close_transferred_human": ("transferred", "human", ""),
        "close_transferred_support": ("transferred", "support", ""),
        "close_no_promise_refused": ("no_promise", "refused", GOODBYE),
        "close_no_promise_hardship": ("no_promise", "hardship", GOODBYE),
        "close_no_promise_dispute": ("no_promise", "dispute", GOODBYE),
        "close_no_promise_service_error": ("no_promise", "service_error",
                                           GOODBYE if multi else
                                           "I am sorry, I could not record your promise to pay because of a technical problem. " + GOODBYE),
        "close_account_unavailable": ("no_promise", "service_error",
                                      "I am sorry, I cannot reach your account details right now because of a technical problem. " + GOODBYE),
        "close_not_verified_failed": ("not_verified", "failed",
                                      "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye."),
        "close_not_verified_declined": ("not_verified", "declined", "I understand. Thank you for your time. Goodbye."),
        "close_not_reached_callback": ("not_reached", "callback", "Thank you, the callback is booked. Goodbye."),
        "close_not_reached_no_callback": ("not_reached", "no_callback", "Thank you for your time. Goodbye."),
        "close_not_reached_wrong_number": ("not_reached", "wrong_number", "I apologise for the inconvenience. Thank you, goodbye."),
        "close_not_reached_deceased": ("not_reached", "deceased", "I am sorry for your loss. Thank you, goodbye."),
        "close_not_reached_unclear": ("not_reached", "unclear", "Thank you. Goodbye."),
    }
    nodes = {}
    for key, (outcome, reason, say) in c.items():
        fields = {"customer_id": body_field("string", "{{customer_id}}"),
                  "outcome": body_field("string", outcome, enum=[outcome])}
        if reason:
            fields["reason"] = body_field("string", reason)
        tool = api_tool("close_call", "/close_call", fields, "Record how the call ended.", required=[], retries=2)
        nodes[key] = {
            "name": key, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "hang_up",
            "disable_inactivity_monitor": True,
            "on_enter": {"type": "tts", "text": say} if say else {"type": "silent"},
            "pre_actions": [tool], "response_mapping": [],
            "transitions": [go("hang_up", "always", ALWAYS)],
        }
    nodes["hang_up"] = {
        "name": "hang_up", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "transitions": [], "terminal": {"type": "function", "function": {
            "name": "call_closed", "handler": "__function__:end_call",
            "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
    }
    return nodes


TRANSFERS = {
    # node: (queue, closing, line spoken before the transfer)
    "transfer_restructuring": ("restructuring", "close_transferred_restructuring",
                               "I will connect you with our team that handles payment plans. " + GOODBYE),
    "transfer_support": ("support", "close_transferred_support",
                         "I will connect you with our customer support team now. " + GOODBYE),
    "transfer_general": ("general", "close_transferred_human",
                         "I will connect you with a colleague now. " + GOODBYE),
}


def transfer_nodes():
    nodes = {}
    for key, (queue, close, say) in TRANSFERS.items():
        tool = api_tool("transfer_to_agent", "/transfer_to_agent",
                        {"customer_id": body_field("string", "{{customer_id}}"),
                         "queue": body_field("string", queue, enum=[queue])},
                        "Hand the call to a person.", required=[], retries=1)
        nodes[key] = {
            "name": key, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": close,
            "disable_inactivity_monitor": True, "on_enter": {"type": "tts", "text": say},
            "pre_actions": [tool], "response_mapping": [],
            "transitions": [go(close, "always", ALWAYS)],
        }
    return nodes


# ---------------------------------------------------------------- prompts

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call to {{title}} {{last_name}} (first name {{first_name}}). Speak English. Keep each turn to one or two short sentences and ask one question at a time. Address the customer as {{title}} {{last_name}}.

Rules for the whole call:
- When a rule says to call a tool, call the tool. Saying that you did something is not enough.
- After every tool result, speak to the person or call the next tool. Never end a turn with nothing.
- Never say that something is recorded, booked or transferred unless a tool result says so. If a tool call failed, say so.
- No improvising: never offer a discount, a waiver, an instalment plan or any term that is not in your instructions.
- If asked something your instructions and tool results do not answer, say you do not have that information. Never invent figures, dates or reasons.
- If asked whether this call is a scam: say they can verify the call by phoning Freya Bank's customer service number, then go on.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then go on.
- Tools named transition_to_close_... and transition_to_transfer_... end the call. The thank-you and goodbye are spoken automatically right after them, so do not say goodbye yourself; you may call them with no text or with one short sentence that the current instructions ask for."""

OPENING_LINE = "Hello, this is the digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"

OPENING_TASK = """The opening line (digital assistant of Freya Bank, call recorded, "Am I speaking with {{title}} {{last_name}}?") has been said. Your only job now is to find out whether {{title}} {{last_name}} is on the line. No bank tool is available here.

Until identity is verified, never say "collections", "debt", "payment", any product or why you are calling, to anyone, relatives included. If asked what the call is about, say you can explain only to {{title}} {{last_name}} in person.

Decide from the reply:
- Only "yes", "that's me", "speaking" or the customer's own name confirm. Then call transition_to_security.
- "Hello", "go ahead", "who is this" or any other unclear reply does not confirm. Ask once more: "Am I speaking with {{title}} {{last_name}}?" If it is still unclear after that second ask, call transition_to_close_not_reached_unclear.
- If they ask a question instead (robot or scam), answer it first; the ask that follows counts as the second ask.
- Someone else answered (a relative, a colleague, anyone who is not the customer): call transition_to_third_party.
- "This number does not belong to that person" / wrong number: call transition_to_close_not_reached_wrong_number.
- The customer has died: call transition_to_close_not_reached_deceased with no text and ask nothing else.
- The person says for the second time that they do not want to talk: call transition_to_close_not_verified_declined."""

THIRD_PARTY_TASK = """You are speaking with someone who is not {{title}} {{last_name}}. Say nothing beyond the opening sentence: never say why you are calling, never mention collections, debt, payment, a product or an account, even if they ask or offer to pay. Never ask them security questions. Your job: ask when {{title}} {{last_name}} can be reached, and book a callback.

{{callback_rules}}

- A day and time inside that window: call schedule_callback with date as YYYY-MM-DD and time as HH:MM (24-hour clock).
- A day or a time outside the window: say that time is not possible and ask once for another time within the window. If the next answer is also outside the window, or they cannot give any time, call transition_to_close_not_reached_no_callback.
- If schedule_callback fails twice, say you could not book the callback and call transition_to_close_not_reached_no_callback.
- "This number does not belong to that person": call transition_to_close_not_reached_wrong_number.
- "The customer has died": call transition_to_close_not_reached_deceased with no text and ask nothing else.
- If {{title}} {{last_name}} now comes to the phone: call transition_to_opening."""

SECURITY_ENTRY = "Thank you. Before we go on, I need to ask you two security questions. First, what is your date of birth?"

SECURITY_TASK = """Security check. Ask two questions, one at a time: first the date of birth, then the last four digits of the phone number on file. Call verify_identity once for every answer: field date_of_birth with the date as YYYY-MM-DD, field phone_last4 with four digits. Follow the what_to_do_next line of each result.

Date of birth: convert whatever the customer says into YYYY-MM-DD. A date given only in numbers is day, then month, then year: "05/03/1980" or "5 3 80" is 1980-03-05. A two-digit year means 19xx. If the result says day and month look swapped, ask the customer to say the month as a word; that retry is not a wrong answer.

Three wrong answers in total end the check. Never mention any account, debt, payment, collections or product during this step.

- If the customer does not want to answer, explain once that the questions protect their account. Asking what the call is about instead of answering counts as declining; answer it the same way, once. A second refusal or a second such question: call transition_to_close_not_verified_declined.
- The customer says for the second time that they do not want to talk: call transition_to_close_not_verified_declined.
- The customer asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
- The person turns out not to be {{title}} {{last_name}}: call transition_to_third_party."""

PTP_RULES = """PTP RULES

Amounts:
- Propose every amount yourself. Never ask "how much can you pay?".
- Start with the full past-due amount.
- If the customer says the full amount is too much: offer the floor amount once, for the date being discussed, and say that the rest stays overdue. Refusing the floor is a flat refusal.
- An amount the customer proposes from the floor up to the full amount, both included, is accepted.
- An amount below the floor: say it cannot be recorded and offer the floor once. If they do not accept it, that is a flat refusal.

Dates (always read dates from the CALENDAR, never work them out yourself):
- A PTP date must be today or later, a business day, and not after that product's deadline.
- The customer names a weekend day or bank holiday that is not after the deadline: offer the next business day shown in the calendar.
- The customer names a date after the deadline: say the latest date you can record is the deadline and offer it. Refusing the deadline is a flat refusal.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still name none, propose the deadline.
- "next <weekday>" and "this <weekday>": use the weekday lines of the calendar.

Persuasion:
- A date or an amount that the customer proposes is never a refusal; handle it with the rules above.
- A flat refusal or a non-answer uses one persuasion attempt. "No" to paying today, with no date and no amount, is a flat refusal.
- Attempt 1: propose the attempt 1 offer from the product facts (full amount, or the floor if the customer already said the full amount is too much).
- Attempt 2 (late stage only): propose the floor amount on the deadline.
- When the allowed attempts are used up and the customer refuses again, stop. Never repeat an offer the customer already refused.

Confirming:
- When amount and date are agreed, read back the product, the amount and the date and ask "Do you confirm?". Only a clear yes counts. If the customer changes the date or the amount, check the new value with the rules above and read back again.

Hardship (illness, a death in the family, job loss): one short sentence of sympathy and no persuasion attempt. Offer to connect them with the customer support team. This comes before persuasion and before the new-plan rule. If they still name a date or an amount themselves, take the PTP under the rules above."""

NEGOTIATE_A = """The customer is verified. You have already told them what is overdue and asked "Can you make this payment today?". Now get a promise to pay (PTP). No bank tool is available in this step; you only talk and, when the outcome is clear, call one transition tool.

PRODUCT FACTS
{{products_text}}

CALENDAR
{{date_facts}}

""" + PTP_RULES + """

WHAT TO CALL
- The customer gave a clear yes to the read-back: call transition_to_record. Do not say the PTP is recorded.
- Attempts used up and still refused, or the customer says for the second time that they do not want to talk: call transition_to_close_no_promise_refused.
- Hardship, and they accept the support team: call transition_to_transfer_support. They decline: call transition_to_close_no_promise_hardship.
- A request for a new payment plan or lower instalments: describe no plan and call transition_to_transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
- "I already paid" (this past-due amount): take no PTP and call transition_to_close_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no PTP, call transition_to_close_no_promise_dispute."""

NEGOTIATE_B = """The customer is verified. You have already told them every late product and asked whether they can pay all of them today. Now get a promise to pay (PTP) per product. No bank tool is available in this step; you only talk and, when the outcome is clear, call one transition tool.

PRODUCT FACTS (in the order the bank returned them)
{{products_text}}

CALENDAR
{{date_facts}}

""" + PTP_RULES + """

MORE THAN ONE PRODUCT
- If the customer can pay all of them today, each product's PTP is its full amount, today.
- If not, take the products one at a time, in the order of the product facts. Do not ask about today again for each product. Each product starts at persuasion attempt 1: open it by proposing its attempt 1 offer.
- Every product has its own stage, deadline, floor and attempt count. Count persuasion attempts separately for each product.
- If the customer names one date for everything and that date is after the deadline of one product, that product goes on its own deadline, and the read-back says so. The other products keep the named date.
- "I already paid" about one product: say payments can take one business day to appear; no PTP for it. "Not mine", "never had it", or closed or paid off in the past about one product: do not argue, no PTP for it. Then go on with the other products.
- Hardship, and they decline the support team: make no more persuasion attempts. Every product without an agreed PTP ends as hardship, except products that already ended as paid, dispute or refused.
- The customer says for the second time that they do not want to talk: stop. Every product not yet settled ends as refused.
- When every product is settled (agreed PTP, refused, hardship, dispute or paid): if at least one PTP is agreed, read all agreed PTPs back together in one message (product, amount and date for each) and ask once "Do you confirm?". Only a clear yes counts. If the customer changes something, check it and read back again.

WHAT TO CALL
- Every product is settled, and the customer gave a clear yes to the read-back, or no PTP was agreed: call transition_to_wrap_up. Do not say anything is recorded.
- Hardship, and they accept the support team: call transition_to_transfer_support.
- A request for a new payment plan or lower instalments: describe no plan and call transition_to_transfer_restructuring. Agreed PTPs are then not recorded.
- A request for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general."""

RECORD_A = """The customer confirmed the read-back of the PTP. Call create_promise now with the amount (a number) and the date (YYYY-MM-DD) exactly as read back and confirmed. Do not say the PTP is recorded before the result says so.

If the result says it was not recorded, call create_promise once more with the same values. If it fails again, say you could not record the PTP.

If the customer changes the amount or the date before you have called create_promise, call transition_to_negotiate.

PRODUCT FACTS
{{products_text}}"""

WRAP_UP_B = """Every product is settled. Record the results now. Read the conversation to see how each product ended.

PRODUCT FACTS (in the order the bank returned them)
{{products_text}}

Steps:
1. For every product with a confirmed PTP: call create_promise with its product_id, the amount (a number) and the date (YYYY-MM-DD), exactly as read back and confirmed. One call per product; you may make them in one message.
2. A create_promise that fails: call it once more with the same values. If it fails again, that product ends as service_error. PTPs already recorded stay.
3. Tell the customer the result. Say a PTP is recorded only for a product whose create_promise returned ok true. For a product that failed twice, say you could not record its PTP.
4. For every product that ends without a recorded PTP, call add_note once with its product_id and one reason: refused, hardship, dispute, paid or service_error. Do this also when no product has a PTP.
5. When all those results are in, call exactly one close tool (never in the same message as create_promise or add_note):
   - at least one PTP recorded: transition_to_route_promise
   - no PTP recorded and every product noted paid: transition_to_route_paid
   - otherwise transition_to_route_no_promise_<reason>, with the note reason of the FIRST product in the product facts order whose note is not paid (refused, hardship, dispute or service_error).

If the customer asks to change or cancel a recorded PTP: it cannot be changed in this call; they can change it in the mobile app.
Transfers add no notes at all: if the customer now asks for a new payment plan or lower instalments, call transition_to_transfer_restructuring without any add_note. If they insist on a human after you asked once whether you can help, call transition_to_transfer_general without any add_note."""


# ---------------------------------------------------------------- workflow

def build(multi):
    verify = api_tool("verify_identity", "/verify_identity", {
        "customer_id": body_field("string", "{{customer_id}}"),
        "field": body_field("string", "{{field}}", "Which question this answer is for: date_of_birth or phone_last4.", ["date_of_birth", "phone_last4"]),
        "answer": body_field("string", "{{answer}}", "date_of_birth as YYYY-MM-DD (day, then month, then year when said in numbers); phone_last4 as four digits."),
    }, "Check one security answer. CALL it every time the customer gives an answer to a security question.",
        required=["field", "answer"], post=VERIFY_POST)
    verify["response_mapping"] = [{"path": "data.all_verified", "variable": "id_all_verified"},
                                  {"path": "data.wrong_answers_left", "variable": "id_wrong_left"}]
    callback = api_tool("schedule_callback", "/schedule_callback", {
        "customer_id": body_field("string", "{{customer_id}}"),
        "date": body_field("string", "{{date}}", "Callback date as YYYY-MM-DD, inside the allowed window."),
        "time": body_field("string", "{{time}}", "Callback time as HH:MM, 24-hour clock, inside the allowed window."),
    }, "Book a callback. CALL it as soon as the person gives a day and time inside the allowed window.",
        required=["date", "time"], post=CALLBACK_POST)
    promise_fields = {
        "customer_id": body_field("string", "{{customer_id}}"),
        "product_id": body_field("string", "{{p1_product_id}}" if not multi else "{{product_id}}",
                                 "product_id exactly as written in the product facts."),
        "amount": body_field("number", "{{amount}}", "The confirmed amount, a number."),
        "date": body_field("string", "{{date}}", "The confirmed date as YYYY-MM-DD."),
    }
    promise = api_tool("create_promise", "/create_promise", promise_fields,
                       "Record one payment promise for one product. CALL it only after the customer said a clear yes to the read-back.",
                       required=["product_id", "amount", "date"], post=PROMISE_POST)
    note = api_tool("add_note", "/add_note", {
        "customer_id": body_field("string", "{{customer_id}}"),
        "product_id": body_field("string", "{{product_id}}", "product_id exactly as written in the product facts."),
        "reason": body_field("string", "{{reason}}", "Why the product ended without a PTP. One of: refused, hardship, dispute, paid, service_error.",
                             ["refused", "hardship", "dispute", "paid", "service_error"]),
    }, "Record why one product ended without a recorded PTP. CALL it once for every such product, never on a transfer.",
        required=["product_id", "reason"], post=NOTE_POST)
    get_account = api_tool("get_account", "/get_account", {"customer_id": body_field("string", "{{customer_id}}")},
                           "Get the late products.", required=[], retries=2)

    gt = lambda v, n: cond_var(v, "greater_than", n)
    nodes = {
        "setup": code_node("setup", SETUP_CODE, "setup_state", "opening", "opening"),
        "opening": {
            "name": "opening", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": OPENING_LINE},
            "task_message": OPENING_TASK, "tools": [],
            "max_node_turns": 8, "max_turn_transition": "close_not_reached_unclear",
            "transitions": [
                tool_go("security", "The person confirmed they are the customer"),
                tool_go("third_party", "Someone other than the customer answered"),
                tool_go("close_not_reached_wrong_number", "The number does not belong to the customer"),
                tool_go("close_not_reached_deceased", "The customer has died"),
                tool_go("close_not_reached_unclear", "Still unclear who answered after the second ask"),
                tool_go("close_not_verified_declined", "The person said twice they do not want to talk"),
            ],
        },
        "third_party": {
            "name": "third_party", "node_type": "conversation", "task_message": THIRD_PARTY_TASK, "tools": [callback],
            "max_node_turns": 10, "max_turn_transition": "close_not_reached_no_callback",
            "transitions": [
                go("close_not_reached_callback", "The callback was booked", gt("schedule_callback_success_count", 0)),
                go("close_not_reached_no_callback", "Booking the callback failed twice", gt("schedule_callback_failure_count", 1)),
                tool_go("close_not_reached_no_callback", "No time inside the callback window"),
                tool_go("close_not_reached_wrong_number", "The number does not belong to the customer"),
                tool_go("close_not_reached_deceased", "The customer has died"),
                tool_go("opening", "The customer came to the phone"),
            ],
        },
        "security": {
            "name": "security", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": SECURITY_ENTRY},
            "task_message": SECURITY_TASK, "tools": [verify],
            "max_node_turns": 16, "max_turn_transition": "close_not_verified_declined",
            "transitions": [
                go("get_account", "Both security answers are verified", cond_any(
                    ("verify_identity_response.data.all_verified", "equals", "true"),
                    ("verify_identity_response.data.all_verified", "equals", "True"),
                    ("id_all_verified", "equals", "true"),
                    ("id_all_verified", "equals", "True"))),
                go("close_not_verified_failed", "Three wrong answers", cond_any(
                    ("verify_identity_response.data.wrong_answers_left", "equals", "0"),
                    ("id_wrong_left", "equals", "0"))),
                tool_go("close_not_verified_declined", "The customer refused the security questions"),
                tool_go("transfer_general", "The customer insisted on a human"),
                tool_go("third_party", "The person is not the customer"),
            ],
        },
        "get_account": {
            "name": "get_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare",
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [get_account],
            "response_mapping": [{"path": "data.products", "variable": "products"}],
            "transitions": [go("prepare", "always", ALWAYS)],
        },
        "prepare": code_node("prepare", PREPARE_CODE, "acct_state", "negotiate", "close_account_unavailable"),
    }
    transfers_from = [tool_go("transfer_restructuring", "The customer asked for a new payment plan or lower instalments"),
                      tool_go("transfer_support", "Hardship and the customer accepted the support team"),
                      tool_go("transfer_general", "The customer insisted on a human")]
    if not multi:
        nodes["negotiate"] = {
            "name": "negotiate", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": "{{intro_text}}"}, "on_enter_first_entry_only": True,
            "task_message": NEGOTIATE_A, "tools": [],
            "max_node_turns": 40, "max_turn_transition": "close_no_promise_refused",
            "transitions": [
                tool_go("record", "The customer said a clear yes to the read-back of the PTP"),
                tool_go("close_paid", "The customer already paid"),
                tool_go("close_no_promise_dispute", "The customer disputes the debt"),
                tool_go("close_no_promise_hardship", "Hardship and the customer declined the support team"),
                tool_go("close_no_promise_refused", "Attempts used up or the customer said twice they do not want to talk"),
            ] + transfers_from,
        }
        nodes["record"] = {
            "name": "record", "node_type": "conversation", "task_message": RECORD_A, "tools": [promise],
            "max_node_turns": 6, "max_turn_transition": "close_no_promise_service_error",
            "transitions": [
                go("close_promise", "The promise is recorded", gt("create_promise_success_count", 0)),
                go("close_no_promise_service_error", "create_promise failed twice", gt("create_promise_failure_count", 1)),
                tool_go("negotiate", "The customer changed the amount or the date before recording"),
            ],
        }
    else:
        nodes["negotiate"] = {
            "name": "negotiate", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": "{{intro_text}}"}, "on_enter_first_entry_only": True,
            "task_message": NEGOTIATE_B, "tools": [],
            "max_node_turns": 60, "max_turn_transition": "wrap_up",
            "transitions": [tool_go("wrap_up", "Every product is settled and the read-back, if any, is confirmed")] + transfers_from,
        }
        routes = ["promise", "paid", "no_promise_refused", "no_promise_hardship", "no_promise_dispute", "no_promise_service_error"]
        nodes["wrap_up"] = {
            "name": "wrap_up", "node_type": "conversation", "task_message": WRAP_UP_B, "tools": [promise, note],
            "max_node_turns": 20, "max_turn_transition": "route_no_promise_refused",
            "transitions": [tool_go("route_" + r, "Close the call as " + r.replace("_", " ")) for r in routes]
            + [tool_go("transfer_restructuring", "The customer asked for a new payment plan or lower instalments"),
               tool_go("transfer_general", "The customer insisted on a human")],
        }
        # E: promise whenever at least one PTP was recorded. A recorded promise wins over the model's choice.
        for r in routes:
            fallback = "close_no_promise_service_error" if r == "promise" else "close_" + r
            nodes["route_" + r] = {
                "name": "route_" + r, "node_type": "conversation", "passthrough": True,
                "passthrough_default_transition": fallback, "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                "task_message": "Do not call a tool in this turn.",
                "transitions": [go("close_promise", "At least one promise was recorded", gt("create_promise_success_count", 0)),
                                go(fallback, "always", ALWAYS)],
            }
    nodes.update(transfer_nodes())
    nodes.update(closings(multi))
    return {
        "initial_node": "setup",
        "system_prompt": SYSTEM,
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr",
                           "now": "2026-10-14T11:00"},
    }


def contract(slot):
    ev = [{"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
          {"source": "briefs/brief-a-raw.md", "quote": "Every call ends with exactly one `close_call`, as the last tool call, with an outcome and, where the list gives one, a reason."}]
    if slot == "brief-b-raw":
        ev.append({"source": "briefs/brief-b-raw.md", "quote": "The close code list still applies."})
    return {"terminal_tools": [{"tool": "close_call", "evidence": ev}], "every_call_ends_with_terminal": True}


if __name__ == "__main__":
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    for slot, multi in (("brief-a-raw", False), ("brief-b-raw", True)):
        (out / f"{slot}.workflow.json").write_text(json.dumps(build(multi), indent=1, ensure_ascii=False) + "\n")
        (out / f"{slot}.contract.json").write_text(json.dumps(contract(slot), indent=1) + "\n")
        print("wrote", slot)
