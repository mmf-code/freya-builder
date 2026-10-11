"""Generate the body workflow and closing plan for briefs/rehearsal-a.md, for tools/lower.py.

    python3 build/gen.py   # writes out/rehearsal-a.body.json and out/rehearsal-a.plan.json
"""
import json
from pathlib import Path

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
SLOT = "rehearsal-a"
BRIEF = "briefs/rehearsal-a.md"
API = "tools/openapi.json"

# ------------------------------------------------------------------ code (no double braces anywhere)

DATE_LIB = r'''
import datetime
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def words(d):
    return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year)
def nth_bd(start, n):
    d = start
    c = 0
    while c < n:
        d = d + datetime.timedelta(days=1)
        if isbd(d):
            c += 1
    return d
def next_bd_from(d):
    while not isbd(d):
        d = d + datetime.timedelta(days=1)
    return d
def last_bd_of_week(d):
    monday = d - datetime.timedelta(days=d.weekday())
    x = monday + datetime.timedelta(days=4)
    while x >= monday:
        if isbd(x):
            return x
        x = x - datetime.timedelta(days=1)
    return None
def get_now():
    s = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        return datetime.datetime.fromisoformat(s[:16])
    except Exception:
        return datetime.datetime.fromisoformat(s[:10] + 'T09:00')
'''

SETUP_CODE = DATE_LIB + r'''
try:
    nowdt = get_now()
    today = nowdt.date()
    hhmm = nowdt.strftime('%H:%M')
    nbd = nth_bd(today, 1)
    vars['today_iso'] = today.isoformat()
    vars['today_words'] = words(today)
    vars['now_time'] = hhmm
    lines = []
    if hhmm < '19:00':
        start = '10:00' if hhmm < '10:00' else 'any time later than ' + hhmm
        lines.append('- Today, ' + words(today) + ' (date ' + today.isoformat() + '): from ' + start + ' up to 19:00 included.')
    else:
        lines.append('- Today, ' + words(today) + ': no slot left (it is already ' + hhmm + ').')
    lines.append('- Next business day, ' + words(nbd) + ' (date ' + nbd.isoformat() + '): from 10:00 to 19:00, both included.')
    lines.append('- Any other day, or any time before 10:00 or after 19:00, is outside the window.')
    vars['callback_window'] = '\n'.join(lines)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['today_iso'] = str(vars.get('now') or '')[:10]
    vars['today_words'] = str(vars.get('now') or '')[:10]
    vars['now_time'] = str(vars.get('now') or '')[11:16]
    vars['callback_window'] = '- Today later than now, or the next business day, from 10:00 to 19:00 both included.'
    vars['setup_state'] = 'error ' + str(e)
'''

PREPARE_CODE = DATE_LIB + r'''
import json
def money(x):
    try:
        v = float(x)
    except Exception:
        return str(x)
    if abs(v - round(v)) < 0.005:
        return '{:,}'.format(int(round(v)))
    return '{:,.2f}'.format(v)
def find_products():
    for key in ('products', 'fetch_account_response.data.products', 'get_account_response.data.products'):
        p = vars.get(key)
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = None
        if isinstance(p, list) and p:
            return p
    rows = dict()
    for k, v in list(vars.items()):
        for prefix in ('products.', 'fetch_account_response.data.products.', 'get_account_response.data.products.'):
            if isinstance(k, str) and k.startswith(prefix):
                rest = k[len(prefix):].split('.', 1)
                if len(rest) == 2 and rest[0].isdigit():
                    rows.setdefault(int(rest[0]), dict())[rest[1]] = v
    return [rows[i] for i in sorted(rows)]
try:
    nowdt = get_now()
    today = nowdt.date()
    products = find_products()
    vars['product_count'] = min(len(products), 1)
    vars['account_state'] = 'ok' if products else 'empty'
    for idx, p in enumerate(products[:1]):
        n = str(idx + 1)
        typ = str(p.get('type') or '')
        if typ == 'credit_card':
            text = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        elif typ == 'car_loan':
            text = 'car loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        else:
            text = 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        days_late = int(float(p.get('days_late') or 0))
        if days_late <= 7:
            stage, nth, allowed = 'early', 12, 2
        else:
            stage, nth, allowed = 'late', 7, 3
        deadline = nth_bd(today, nth)
        first = last_bd_of_week(today)
        if first is None or first <= today:
            first = last_bd_of_week(today + datetime.timedelta(days=7))
        vars['p' + n + '_id'] = str(p.get('product_id') or '')
        vars['p' + n + '_text'] = text
        vars['p' + n + '_past_due'] = money(p.get('past_due'))
        vars['p' + n + '_days_late'] = str(days_late)
        vars['p' + n + '_floor'] = money(floor)
        vars['p' + n + '_floor_name'] = floor_name
        vars['p' + n + '_stage'] = stage
        vars['p' + n + '_attempts_allowed'] = allowed
        vars['p' + n + '_persuasions'] = str(allowed - 1)
        vars['p' + n + '_deadline'] = deadline.isoformat()
        vars['p' + n + '_deadline_words'] = words(deadline)
        vars['p' + n + '_first_date'] = first.isoformat()
        vars['p' + n + '_first_date_words'] = words(first)
        monday = today - datetime.timedelta(days=today.weekday())
        labels = ['THIS WEEK', 'NEXT WEEK', 'THE WEEK AFTER NEXT', 'THREE WEEKS FROM NOW', 'FOUR WEEKS FROM NOW']
        out = []
        w = 0
        while w < len(labels):
            ws = monday + datetime.timedelta(days=7 * w)
            if ws > deadline + datetime.timedelta(days=7):
                break
            out.append(labels[w] + ':')
            for k in range(7):
                d = ws + datetime.timedelta(days=k)
                if d < today:
                    st = 'past, not allowed'
                elif d > deadline:
                    st = 'AFTER THE DEADLINE, not allowed'
                elif d.weekday() >= 5:
                    st = 'weekend, offer the next business day ' + words(next_bd_from(d)) + ' instead'
                elif d.isoformat() in HOL:
                    st = 'bank holiday, offer the next business day ' + words(next_bd_from(d)) + ' instead'
                else:
                    st = 'ALLOWED'
                if d == today:
                    st = 'TODAY, ' + st
                if d == deadline:
                    st = st + ', THE DEADLINE'
                out.append('  ' + words(d) + ' = ' + d.isoformat() + ': ' + st)
            w += 1
        vars['p' + n + '_calendar'] = '\n'.join(out)
except Exception as e:
    vars['account_state'] = 'error ' + str(e)
    if 'product_count' not in vars:
        vars['product_count'] = 0
'''

# ------------------------------------------------------------------ hooks

VERIFY_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        sc = result.get('status_code')
        if not isinstance(d, dict):
            result['what_to_do_next'] = 'The security service failed and nothing was checked. Tell the customer there was a technical problem, ask for the same answer again and call verify_identity again.'
        else:
            left = d.get('wrong_answers_left')
            if d.get('hint') == 'day_month_swapped':
                d['what_to_do_next'] = 'The day and the month look swapped. This is NOT a wrong answer. Ask the customer to say their date of birth again with the month as a word, then call verify_identity again.'
            elif str(d.get('all_verified')).lower() == 'true':
                d['what_to_do_next'] = 'Both answers passed. Identity is verified.'
            elif str(d.get('ok')).lower() == 'false':
                d['what_to_do_next'] = 'The service could not read the answer. It is NOT a wrong answer. Ask the customer to repeat it, then call verify_identity again with a valid value (date as YYYY-MM-DD, phone as four digits).'
            elif str(d.get('verified')).lower() == 'true':
                d['what_to_do_next'] = 'This answer is correct. Now ask for the last four digits of the phone number on file.'
            elif str(left) == '0':
                d['what_to_do_next'] = 'Three wrong answers. The security check has failed. Do not mention any account detail.'
            else:
                d['what_to_do_next'] = 'This answer is wrong. Do not reveal or hint at the correct value. Say it did not match and ask the same question again. Wrong answers left in total: ' + str(left) + '.'
except Exception:
    pass
'''

PROMISE_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and str(d.get('ok')).lower() == 'true':
            d['what_to_do_next'] = 'The promise is recorded.'
        else:
            msg = 'The promise was NOT recorded. Never say it is recorded. If this is the first failure: tell the customer it did not go through and that you are trying once more, and call create_promise again right away with exactly the same values. If it already failed before, say nothing about a retry.'
            if isinstance(d, dict):
                d['what_to_do_next'] = msg
            else:
                result['what_to_do_next'] = msg
except Exception:
    pass
'''

CALLBACK_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and str(d.get('ok')).lower() == 'true':
            d['what_to_do_next'] = 'The callback is booked.'
        else:
            msg = 'The callback was NOT booked. Never say it is booked. Tell the person it did not go through and call schedule_callback once more with the same date and time.'
            if isinstance(d, dict):
                d['what_to_do_next'] = msg
            else:
                result['what_to_do_next'] = msg
except Exception:
    pass
'''

# ------------------------------------------------------------------ helpers

HEADERS = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}


def api_tool(name, body_props, required, description, max_retries=0, post=None):
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": f"{BASE}/{name}"},
                "method": {"type": "string", "default": "POST"},
                "headers": HEADERS,
                "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}, **body_props},
                         "required": required},
            }},
        },
    }
    if post:
        t["post_process_code"] = post
    return t


def code_node(name, code, nxt):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}],
    }


def tc(target, description):
    """Tool-call transition the dialogue model triggers."""
    return {"target_node": target, "description": description, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": description}}


def var_or(*checks):
    return {"logic": "or", "conditions": [{"variable": v, "operator": o, "operand": x} for v, o, x in checks]}


def bool_true(var):
    return [(var, "equals", "true"), (var, "equals", "True")]


CLOSE_NOTE = ("When a rule tells you to end the call, call the matching transition tool. You may say one short last sentence in the same "
              "message (for example the sympathy sentence), but do NOT say goodbye or thank-you yourself: the system says the thank-you and "
              "goodbye right after.")

# ------------------------------------------------------------------ prompts

SYSTEM = """You are Freya Bank's digital assistant, on an outbound phone call. Speak English. Keep every turn to one or two short sentences. Ask one question at a time.

The customer you are calling: {{title}} {{first_name}} {{last_name}}. Address them as {{title}} {{last_name}}.
Today is {{today_words}}, the time is {{now_time}}. Use this date, never the real clock.

Rules for the whole call:
- Before identity is verified, never mention collections, a debt, a payment, an amount, a product or the reason for the call, to anyone, relatives included.
- Never improvise. Never offer a discount, a waiver, an instalment plan or any term that is not in your instructions.
- If asked something you have no information for, say you do not have that information. Never invent figures, dates or reasons.
- "Is this a scam?": say they can verify this call by phoning Freya Bank's customer service number, then go on.
- "Am I talking to a robot / an AI?": say you are Freya Bank's digital assistant, then go on.
- Never say that something is recorded, booked or transferred unless the tool result says so.
- Call at most one tool per message. After every tool result, speak to the customer or call the next tool; never end a turn with nothing.
- Never say goodbye or end the conversation in words only: the call ends only through the transition tools, and the system then says thank-you and goodbye."""

IDENTITY_TASK = f"""Your only job in this step: find out whether the person on the line is {{{{title}}}} {{{{last_name}}}}. You have already said the opening line and asked "Am I speaking with {{{{title}}}} {{{{last_name}}}}?".

Rules:
- Only "yes", "that's me", "speaking" or the customer's own name confirm. Then call transition_to_security at once, with no text.
- "Hello", "go ahead", "who is this?" or anything else unclear does NOT confirm: ask once more "Am I speaking with {{{{title}}}} {{{{last_name}}}}?". If it is still unclear after this second ask, call transition_to_close_not_reached_unclear.
- If the person asks a robot or scam question instead of answering, answer it (see the global rules) and ask again; that ask counts as the second ask.
- If the person says they are someone else, or that {{{{title}}}} {{{{last_name}}}} is not available, call transition_to_third_party with no text.
- If the person says this number does not belong to {{{{title}}}} {{{{last_name}}}}, call transition_to_close_not_reached_wrong_number.
- If the person says {{{{title}}}} {{{{last_name}}}} has died: say only "I am sorry for your loss." and call transition_to_close_not_reached_deceased in the same message. Ask nothing else.
- If the person asks for a human: ask once whether you can help them first. If they insist, call transition_to_transfer_general.
- If they say twice that they do not want to talk, call transition_to_close_not_verified_declined.
- Never say why you are calling. {CLOSE_NOTE}
Do not call any other tool in this step."""

THIRD_PARTY_TASK = f"""Someone other than {{{{title}}}} {{{{last_name}}}} is on the line. Say nothing about why you are calling, even if asked or if they offer to pay; say you can only speak with {{{{title}}}} {{{{last_name}}}}. They may not answer security questions and you tell them nothing about any account.

Your job: ask when {{{{title}}}} {{{{last_name}}}} can be reached, and book a callback.

Callback window (the only times you may book):
{{{{callback_window}}}}

Rules:
- When the person names a day and an exact time inside the window, say you will arrange the callback for that day and time, and call schedule_callback with date (YYYY-MM-DD) and time (HH:MM, 24 hour). If they give only a vague time ("this afternoon"), ask for an exact time.
- If the day or time they name is outside the window, say so and ask once for another time inside the window. If the second time is also outside the window, book nothing and call transition_to_close_not_reached_no_callback.
- If they cannot or will not give any time, call transition_to_close_not_reached_no_callback.
- If they say this number does not belong to {{{{title}}}} {{{{last_name}}}}, call transition_to_close_not_reached_wrong_number.
- If they say {{{{title}}}} {{{{last_name}}}} has died: say only "I am sorry for your loss." and call transition_to_close_not_reached_deceased in the same message.
- If {{{{title}}}} {{{{last_name}}}} comes to the phone now, call transition_to_identity.
{CLOSE_NOTE}"""

SECURITY_TASK = f"""The customer confirmed who they are. Your job in this step: the security check. You have already asked for the date of birth.

Rules:
- Two questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
- Call verify_identity for every answer: field "date_of_birth" with the answer as YYYY-MM-DD, or field "phone_last4" with four digits. Convert whatever the customer said: "fourth of March nineteen eighty" is 1980-03-04. A date said only in numbers is read as day, then month, then year: "04/03/1980" is 1980-03-04. Two-part numbers ("forty-eight, twenty-one") are joined: 4821.
- Follow the what_to_do_next line of every verify_identity result. A wrong answer may be asked again. Never reveal or hint at the correct value.
- If the customer will not answer, or asks what the call is about instead of answering, explain once that these questions protect their account and ask again. If they refuse again or ask again what it is about, call transition_to_close_not_verified_declined.
- If they ask for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
- Do not mention the reason for the call, a debt, a payment or a product. {CLOSE_NOTE}"""

NEGOTIATE_TASK = """The customer passed security. You are in STEP {a} of the payment conversation for this product.

FACTS (the only figures you may use):
- Product: {{p{i}_text}} (product_id {{p{i}_id}}).
- Past-due amount (the full amount): {{p{i}_past_due}}. Days late: {{p{i}_days_late}}.
- Floor amount ({{p{i}_floor_name}}): {{p{i}_floor}}.
- Stage: {{p{i}_stage}}. Persuasion attempts allowed: {{p{i}_persuasions}}.
- Latest promise date (deadline): {{p{i}_deadline_words}} ({{p{i}_deadline}}).
- Date for the first persuasion attempt: {{p{i}_first_date_words}} ({{p{i}_first_date}}).
- Today: {{today_words}} ({{today_iso}}).
- Calendar (weeks start on Monday; "this <weekday>" is in THIS WEEK, "next <weekday>" is in NEXT WEEK):
{{p{i}_calendar}}

WHAT TO SAY IN EACH STEP
- STEP 1, first message: say you are calling from Freya Bank's collections team about a late payment on the {{p{i}_text}}, that {{p{i}_past_due}} is past due and that it is {{p{i}_days_late}} days late. Then ask exactly: "Can you make this payment today?"
- STEP 2, first message: this is the first persuasion attempt. Propose paying the full amount {{p{i}_past_due}} on {{p{i}_first_date_words}}. If the customer already said the full amount is too much, propose the floor {{p{i}_floor}} on that date instead, and say the rest stays overdue.
- STEP 3, first message: this is the second and last persuasion attempt. Propose the floor {{p{i}_floor}} on the deadline {{p{i}_deadline_words}}, and say the rest stays overdue.
- Never repeat an offer the customer already refused. If the offer of your step was already refused earlier in the call, call transition_to_close_no_promise_refused.

HANDLING WHAT THE CUSTOMER SAYS (in every step)
- A date or an amount the customer proposes is never a refusal. Check it:
  - Dates: only dates marked ALLOWED in the calendar can be recorded. A weekend day or bank holiday on or before the deadline: offer the next business day shown in the calendar. A date after the deadline: say the latest date you can record is {{p{i}_deadline_words}} and offer it. A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day; if they still name none, propose the deadline.
  - Amounts: never ask "how much can you pay?"; you propose every amount. Any amount from {{p{i}_floor}} up to {{p{i}_past_due}}, both included, is accepted. Below {{p{i}_floor}}: say it cannot be recorded and offer the floor once. If the customer says the full amount is too much: offer the floor {{p{i}_floor}} once, and say the rest stays overdue.
  - If they agree to pay but name no date, use today when they agreed to "today", otherwise ask for the day.
- Confirmation: when amount and date are both valid, read back the product, the amount and the date, and ask "Do you confirm?". Call create_promise only after a clear yes, with amount as a number and date as YYYY-MM-DD. If they change the date or amount instead, check the new value and read back again. Do not say the promise is recorded: the system confirms it after the tool result. Follow the what_to_do_next line of the create_promise result.
- Illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transition_to_transfer_support. If they decline, call transition_to_close_no_promise_hardship. If they still name a date or an amount themselves, handle it as a promise.
- A new payment plan or lower instalments: describe no plan; say you will connect them with the team that handles this and call transition_to_transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transition_to_transfer_general.
- "I already paid" (this past-due amount): say payments can take one business day to appear, take no promise, and call transition_to_close_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise, and call transition_to_close_no_promise_dispute.
- If the customer says twice that they do not want to talk, call transition_to_close_no_promise_refused.
""" + CLOSE_NOTE

AFTER_PROMISE_TASK = f"""The promise to pay has just been recorded, and you have told the customer so and asked if there is anything else.

Rules:
- A recorded promise cannot be changed or cancelled in this call. If they ask, say they can change it in the Freya Bank mobile app.
- A new payment plan or lower instalments: describe no plan; call transition_to_transfer_restructuring.
- Illness, a death in the family or job loss, and they accept the support team: call transition_to_transfer_support.
- A request for a human: ask once whether you can help first; if they insist, call transition_to_transfer_general.
- When there is nothing else, call transition_to_close_promise.
{CLOSE_NOTE}"""

# ------------------------------------------------------------------ nodes

verify_tool = api_tool("verify_identity", {
    "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{vi_field}}",
              "description": "Which answer this is. One of: date_of_birth, phone_last4."},
    "answer": {"type": "string", "default": "{{vi_answer}}",
               "description": "date_of_birth as YYYY-MM-DD (day, then month, then year when said in numbers). phone_last4 as exactly four digits."},
}, ["field", "answer"], "Check one security answer. CALL it every time the customer gives their date of birth or the last four digits of their phone number.",
    post=VERIFY_POST)

promise_tool = api_tool("create_promise", {
    "product_id": {"type": "string", "default": "{{p{i}_id}}", "description": "The product id."},
    "amount": {"type": "number", "default": "{{ptp_amount}}", "description": "The confirmed amount, as a number, between the floor and the past-due amount."},
    "date": {"type": "string", "default": "{{ptp_date}}", "description": "The confirmed payment date, YYYY-MM-DD, a date marked ALLOWED in the calendar."},
}, ["product_id", "amount", "date"], "Record the payment promise. CALL it only right after the customer answered a clear yes to your read-back of product, amount and date.",
    post=PROMISE_POST)

callback_tool = api_tool("schedule_callback", {
    "date": {"type": "string", "default": "{{cb_date}}", "description": "Callback day, YYYY-MM-DD, inside the callback window."},
    "time": {"type": "string", "default": "{{cb_time}}", "description": "Callback time, HH:MM 24 hour, inside the callback window."},
}, ["date", "time"], "Book a callback. CALL it as soon as the person named a day and an exact time inside the callback window.",
    post=CALLBACK_POST)


def transfer_node(queue, closing):
    name = f"transfer_{queue}"
    t = api_tool("transfer_to_agent", {"queue": {"type": "string", "enum": [queue], "default": queue}}, ["queue"],
                 "Hand the call to a person.", max_retries=1)
    return name, {
        "name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": f"close:{closing}",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [t], "response_mapping": [],
        "transitions": [{"target_node": f"close:{closing}", "description": "always", "condition": {"operator": "always"}}],
    }


nodes = {}
nodes["setup"] = code_node("setup", SETUP_CODE, "identity")
nodes["identity"] = {
    "name": "identity", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, this is Freya Bank's digital assistant calling. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": False,
    "task_message": IDENTITY_TASK, "tools": [],
    "max_node_turns": 6, "max_turn_transition": "close:not_reached_unclear",
    "transitions": [
        tc("security", "The person clearly confirmed they are the customer: yes, that's me, speaking, or the customer's own name."),
        tc("third_party", "Someone else answered, or the customer is not available."),
        tc("close:not_reached_wrong_number", "The number does not belong to the customer."),
        tc("close:not_reached_deceased", "The person says the customer has died. Say only: I am sorry for your loss."),
        tc("close:not_reached_unclear", "Still unclear who answered after asking a second time."),
        tc("close:not_verified_declined", "The person said twice that they do not want to talk."),
        tc("transfer_general", "The person insists on speaking with a human after you asked once whether you can help."),
    ],
}
nodes["third_party"] = {
    "name": "third_party", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Without saying why you are calling, ask politely when {{title}} {{last_name}} can be reached."},
    "on_enter_first_entry_only": True,
    "task_message": THIRD_PARTY_TASK, "tools": [callback_tool],
    "max_node_turns": 10, "max_turn_transition": "close:not_reached_no_callback",
    "transitions": [
        {"target_node": "close:not_reached_callback", "description": "The callback was booked",
         "condition": var_or(*bool_true("schedule_callback_response.data.ok"))},
        {"target_node": "close:not_reached_no_callback", "description": "Booking failed twice",
         "condition": var_or(("schedule_callback_failure_count", "greater_than", 1))},
        tc("close:not_reached_no_callback", "No time inside the callback window after asking once more, or no time given."),
        tc("close:not_reached_wrong_number", "The number does not belong to the customer."),
        tc("close:not_reached_deceased", "The customer has died. Say only: I am sorry for your loss."),
        tc("identity", "The customer has now come to the phone."),
    ],
}
nodes["security"] = {
    "name": "security", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you. Before we continue, I need to ask two security questions. Could you please tell me your date of birth?"},
    "on_enter_first_entry_only": True,
    "task_message": SECURITY_TASK, "tools": [verify_tool],
    "max_node_turns": 14, "max_turn_transition": "close:not_verified_declined",
    "transitions": [
        {"target_node": "fetch_account", "description": "Both security answers passed",
         "condition": var_or(*bool_true("verify_identity_response.data.all_verified"))},
        {"target_node": "close:not_verified_failed", "description": "Three wrong answers",
         "condition": var_or(("verify_identity_response.data.wrong_answers_left", "equals", "0"))},
        tc("close:not_verified_declined", "The customer refused the security questions again after you explained why they are asked, or asked again what the call is about."),
        tc("transfer_general", "The customer insists on speaking with a human after you asked once whether you can help."),
    ],
}
nodes["fetch_account"] = {
    "name": "fetch_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "suppress_tool_results": True,
    "pre_actions": [api_tool("get_account", {}, [], "Get the late products.", max_retries=2)],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [
        {"target_node": "close:no_promise_service_error_account", "description": "The account could not be read",
         "condition": var_or(("fetch_account_failure_count", "greater_than", 0), ("get_account_failure_count", "greater_than", 0))},
        {"target_node": "prepare", "description": "always", "condition": {"operator": "always"}},
    ],
}
nodes["prepare"] = code_node("prepare", PREPARE_CODE, "item:first")
nodes["negotiate"] = {
    "name": "negotiate", "node_type": "conversation",
    "on_enter": {"type": "llm"}, "on_enter_first_entry_only": True,
    "task_message": NEGOTIATE_TASK, "tools": [promise_tool],
    "extraction_schema": [{
        "name": "refused_{i}_{a}", "type": "string", "enum_values": ["yes", "no"], "min_confidence": 0.7,
        "description": ("'yes' only when the customer's LATEST message is a flat refusal of the payment offer the assistant just made, or no answer to it: "
                        "for example 'no', 'I can't', 'not interested', 'no' to paying today without naming a date or amount, or declining the floor amount "
                        "or the deadline date the assistant offered. 'no' in every other case: the customer names a date or an amount of their own, accepts, "
                        "asks a question, says the full amount is too much, mentions illness, a death in the family or job loss, disputes the debt, says they "
                        "already paid, asks for a new plan or a person, or answers no to a read-back."),
    }],
    "max_node_turns": 20, "max_turn_transition": "close:no_promise_refused",
    "transitions": [
        {"target_node": "after_promise", "description": "The promise was recorded",
         "condition": var_or(*bool_true("create_promise_response.data.ok"))},
        {"target_node": "close:no_promise_service_error", "description": "create_promise failed twice",
         "condition": var_or(("create_promise_failure_count", "greater_than", 1))},
        tc("close:paid", "The customer says they already paid this past-due amount."),
        tc("close:no_promise_dispute", "The customer says the debt is not theirs, they never had the product, or it was closed or paid off in the past."),
        tc("close:no_promise_hardship", "Hardship (illness, death in the family, job loss) and the customer declined the support team."),
        tc("transfer_support", "Hardship and the customer accepted to be connected with the customer support team."),
        tc("transfer_restructuring", "The customer asks for a new payment plan or lower instalments."),
        tc("transfer_general", "The customer insists on a human after you asked once whether you can help."),
        tc("close:no_promise_refused", "The customer said twice they do not want to talk, or the offer of this step was already refused."),
    ],
}
nodes["after_promise"] = {
    "name": "after_promise", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you. Your promise to pay is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
    "on_enter_first_entry_only": True,
    "task_message": AFTER_PROMISE_TASK, "tools": [],
    "max_node_turns": 6, "max_turn_transition": "close:promise",
    "transitions": [
        tc("close:promise", "The customer needs nothing else."),
        tc("transfer_restructuring", "The customer asks for a new payment plan or lower instalments."),
        tc("transfer_support", "Hardship and the customer accepted the customer support team."),
        tc("transfer_general", "The customer insists on a human after you asked once whether you can help."),
    ],
}
for q, c in (("general", "transferred_human"), ("support", "transferred_support"), ("restructuring", "transferred_restructuring")):
    k, n = transfer_node(q, c)
    nodes[k] = n

body = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

# ------------------------------------------------------------------ closing plan

BYE = "Thank you for your time. Goodbye."


def ev(quote, source=BRIEF):
    return [{"source": source, "quote": quote}]


closings = {
    "promise": {"set": {"outcome": "promise"}, "say": BYE, "evidence": ev("| `promise` | (none) | at least one PTP was recorded |")},
    "paid": {"set": {"outcome": "paid"}, "say": "Payments can take one business day to appear. " + BYE,
             "evidence": ev("| `paid` | (none) | the customer already paid (CP-4 2.8 e) |")},
    "transferred_restructuring": {"set": {"outcome": "transferred", "reason": "restructuring"}, "say": BYE,
                                  "evidence": ev("| `transferred` | `restructuring` | new plan or lower instalments (2.8 c) |")},
    "transferred_human": {"set": {"outcome": "transferred", "reason": "human"}, "say": BYE,
                          "evidence": ev("| `transferred` | `human` | the customer insisted on a person (2.8 d) |")},
    "transferred_support": {"set": {"outcome": "transferred", "reason": "support"}, "say": BYE,
                            "evidence": ev("| `transferred` | `support` | hardship, customer accepted the support team (2.7 d) |")},
    "no_promise_refused": {"set": {"outcome": "no_promise", "reason": "refused"}, "say": BYE,
                           "evidence": ev("| `no_promise` | `refused` | attempts used up, or said twice they do not want to talk (2.7 c, 2.8 g) |")},
    "no_promise_hardship": {"set": {"outcome": "no_promise", "reason": "hardship"}, "say": BYE,
                            "evidence": ev("| `no_promise` | `hardship` | hardship, customer declined the support team (2.7 d) |")},
    "no_promise_dispute": {"set": {"outcome": "no_promise", "reason": "dispute"}, "say": BYE,
                           "evidence": ev("| `no_promise` | `dispute` | not mine, never had it, closed or paid off in the past (2.8 f) |")},
    "no_promise_service_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                 "say": "I am sorry, I could not record your promise to pay. " + BYE,
                                 "evidence": ev("| `no_promise` | `service_error` | `create_promise` failed twice (2.8 b) |")},
    "no_promise_service_error_account": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                         "say": "I am sorry, I cannot access your account details right now. " + BYE,
                                         "evidence": ev("| `no_promise` | `service_error` | `create_promise` failed twice (2.8 b) |")},
    "not_verified_failed": {"set": {"outcome": "not_verified", "reason": "failed"},
                            "say": "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. " + BYE,
                            "evidence": ev("| `not_verified` | `failed` | three wrong security answers (2.3 d) |")},
    "not_verified_declined": {"set": {"outcome": "not_verified", "reason": "declined"}, "say": BYE,
                              "evidence": ev("| `not_verified` | `declined` | refused the security questions, or did not want to talk before verification (2.3 e, 2.8 g) |")},
    "not_reached_callback": {"set": {"outcome": "not_reached", "reason": "callback"}, "say": "We will call back at that time. " + BYE,
                             "evidence": ev("| `not_reached` | `callback` | callback booked (2.2 b, memo item 2) |")},
    "not_reached_no_callback": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "say": BYE,
                                "evidence": ev("| `not_reached` | `no_callback` | no time inside the window (2.2 c) |")},
    "not_reached_wrong_number": {"set": {"outcome": "not_reached", "reason": "wrong_number"}, "say": "Thank you for letting us know. Goodbye.",
                                 "evidence": ev("| `not_reached` | `wrong_number` | the number is not the customer's (2.2 d) |")},
    "not_reached_deceased": {"set": {"outcome": "not_reached", "reason": "deceased"}, "say": BYE,
                             "evidence": ev("| `not_reached` | `deceased` | the customer has died (2.2 e) |")},
    "not_reached_unclear": {"set": {"outcome": "not_reached", "reason": "unclear"}, "say": BYE,
                            "evidence": ev("| `not_reached` | `unclear` | still unclear who answered after the second ask (2.1 c) |")},
}

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": API, "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`, as the last tool call, with an outcome and, where the list gives one, a reason."},
    ]},
    "fields": {"customer_id": "{{customer_id}}"},
    "closings": closings,
    "ladder": {
        "template": "negotiate", "done": "close:no_promise_refused",
        "items": {"count": "product_count", "max": 1, "evidence": ev("customers who are 1 to 45 days past due on one product")},
        "attempts": {"allowed": "p{i}_attempts_allowed", "max": 3, "evidence": ev("| 8-45 | late | 5th business day after today | 2 |")},
        "refusal": "refused_{i}_{a}",
    },
}

Path("out").mkdir(exist_ok=True)
Path(f"out/{SLOT}.body.json").write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
Path(f"out/{SLOT}.plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
print("wrote body and plan")
