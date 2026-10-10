"""Generate out/brief-a-raw.workflow.json from the Freya Bank brief (briefs/brief-a-raw.md)."""
import json
import pathlib

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
HERE = pathlib.Path(__file__).parent

# ------------------------------------------------------------------ code snippets (no double braces allowed)

SETUP_CODE = r'''
import datetime
try:
    HOL = set(['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'])
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    one = datetime.timedelta(days=1)
    raw = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        nowdt = datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        nowdt = datetime.datetime.fromisoformat(raw[:10] + 'T00:00')
    today = nowdt.date()

    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL

    def spoken(d):
        return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year)

    def label(d):
        return spoken(d) + ' (' + d.isoformat() + ')'

    def nth_bd(n):
        d = today
        c = 0
        while c < n:
            d = d + one
            if isbd(d):
                c += 1
        return d

    def next_bd(d):
        d = d + one
        while not isbd(d):
            d = d + one
        return d

    vars['today_iso'] = today.isoformat()
    vars['today_spoken'] = spoken(today)
    vars['now_time'] = nowdt.strftime('%H:%M')

    # callback window: today or the next business day, 10:00 to 19:00 both included, later than now
    nbd = next_bd(today)
    lines = []
    t = nowdt.time()
    if t < datetime.time(10, 0):
        lines.append('Today, ' + label(today) + ': from 10:00 to 19:00, both included.')
    elif t < datetime.time(19, 0):
        lines.append('Today, ' + label(today) + ': any time later than ' + nowdt.strftime('%H:%M') + ' and no later than 19:00.')
    else:
        lines.append('Today, ' + label(today) + ': no time left, today is not possible.')
    lines.append('The next business day, ' + label(nbd) + ': from 10:00 to 19:00, both included.')
    lines.append('Every other day or time is outside the window. Weekends and bank holidays other than today are outside the window.')
    vars['callback_window'] = '\n'.join(lines)
    vars['callback_next_bd'] = label(nbd)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['setup_state'] = 'error'
    vars['today_iso'] = str(vars.get('now') or '')[:10]
    vars['today_spoken'] = str(vars.get('now') or '')[:10]
    vars['now_time'] = str(vars.get('now') or '')[11:16]
    vars['callback_window'] = 'Today from 10:00 to 19:00 (later than now) or the next business day from 10:00 to 19:00.'
    vars['callback_next_bd'] = 'the next business day'
'''

ACCOUNT_CODE = r'''
import datetime
import json
import re
try:
    HOL = set(['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'])
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    one = datetime.timedelta(days=1)

    def parse_list(p):
        if isinstance(p, str):
            s = p.strip()
            for cand in (s, s.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null')):
                try:
                    p = json.loads(cand)
                    break
                except Exception:
                    pass
        if isinstance(p, dict):
            if isinstance(p.get('products'), list):
                p = p.get('products')
            else:
                p = [p]
        if isinstance(p, list) and p and isinstance(p[0], dict):
            return p
        return None

    products = None
    for key in ('products', 'load_account_response.data.products', 'get_account_response.data.products'):
        if products is None and key in vars:
            products = parse_list(vars.get(key))
    if products is None:
        items = dict()
        for k in list(vars.keys()):
            m = re.search(r'products(?:\.|\[)(\d+)\]?\.(\w+)$', str(k))
            if m:
                items.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
        if items:
            products = [items[i] for i in sorted(items)]
    if not products:
        raise ValueError('no products')
    p = products[0]

    def num(x):
        try:
            return float(str(x).replace(',', ''))
        except Exception:
            return None

    def money(x):
        if x is None:
            return ''
        if abs(x - round(x)) < 0.005:
            return '{:,.0f}'.format(x)
        return '{:,.2f}'.format(x)

    def plain(x):
        if x is None:
            return ''
        if abs(x - round(x)) < 0.005:
            return str(int(round(x)))
        return '{:.2f}'.format(x)

    ptype = str(p.get('type') or '')
    last4 = str(p.get('card_last4') or '').strip()
    if ptype == 'credit_card':
        words = 'credit card ending ' + last4 if last4 else 'credit card'
        floor = num(p.get('minimum_payment'))
        floor_name = 'minimum payment'
    elif ptype == 'car_loan':
        words = 'car loan'
        floor = num(p.get('instalment_amount'))
        floor_name = 'instalment'
    else:
        words = 'personal loan'
        floor = num(p.get('instalment_amount'))
        floor_name = 'instalment'
    past_due = num(p.get('past_due'))
    try:
        days_late = int(float(str(p.get('days_late'))))
    except Exception:
        days_late = 0
    if past_due is None:
        raise ValueError('no past_due')
    if floor is None or floor > past_due:
        floor = past_due

    raw = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        nowdt = datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        nowdt = datetime.datetime.fromisoformat(raw[:10] + 'T00:00')
    today = nowdt.date()

    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL

    def spoken(d):
        return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year)

    def label(d):
        return spoken(d) + ' (' + d.isoformat() + ')'

    def nth_bd(n):
        d = today
        c = 0
        while c < n:
            d = d + one
            if isbd(d):
                c += 1
        return d

    def next_bd(d):
        d = d + one
        while not isbd(d):
            d = d + one
        return d

    if days_late <= 7:
        stage = 'early'
        deadline = nth_bd(12)
        attempts = 1
    else:
        stage = 'late'
        deadline = nth_bd(7)
        attempts = 2

    monday = today - datetime.timedelta(days=today.weekday())

    def last_bd_of_week(mon):
        best = None
        for i in range(7):
            d = mon + datetime.timedelta(days=i)
            if isbd(d):
                best = d
        return best

    a1 = last_bd_of_week(monday)
    if a1 is None or a1 <= today:
        a1 = last_bd_of_week(monday + datetime.timedelta(days=7))
    if a1 is None or a1 > deadline:
        a1 = deadline

    cal = []
    d = today
    end = deadline + datetime.timedelta(days=4)
    while d <= end:
        tag = 'today, ' if d == today else ''
        if d <= deadline and isbd(d):
            s = 'valid PTP date'
        elif d <= deadline:
            why = 'weekend' if d.weekday() >= 5 else 'bank holiday'
            s = why + ', not a valid PTP date; offer the next business day, ' + label(next_bd(d)) + ', instead'
        else:
            s = 'after the deadline, cannot be recorded; say the latest date you can record is ' + label(deadline) + ' and offer it'
        cal.append('- ' + label(d) + ': ' + tag + s)
        d = d + one
    phrases = []
    for i in range(7):
        this_d = monday + datetime.timedelta(days=i)
        next_d = this_d + datetime.timedelta(days=7)
        phrases.append('- "this ' + DAYS[i] + '" = ' + label(this_d) + ('  (already past, not possible)' if this_d < today else '') + '; "next ' + DAYS[i] + '" = ' + label(next_d))

    vars['product_id'] = str(p.get('product_id') or '')
    vars['product_words'] = words
    vars['past_due_text'] = money(past_due)
    vars['past_due_plain'] = plain(past_due)
    vars['floor_text'] = money(floor)
    vars['floor_plain'] = plain(floor)
    vars['floor_name'] = floor_name
    vars['days_late_n'] = str(days_late)
    vars['stage'] = stage
    vars['attempts_allowed'] = str(attempts)
    vars['deadline_label'] = label(deadline)
    vars['deadline_iso'] = deadline.isoformat()
    vars['attempt1_label'] = label(a1)
    vars['attempt1_iso'] = a1.isoformat()
    vars['today_label'] = label(today)
    vars['today_is_bd'] = 'yes' if isbd(today) else 'no'
    vars['ptp_calendar'] = '\n'.join(cal)
    vars['weekday_phrases'] = '\n'.join(phrases)
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_state'] = 'error'
    vars['account_error'] = str(e)[:200]
'''

# ------------------------------------------------------------------ hooks

STRIP_HEADER = "    if isinstance(result, dict):\n        result.pop('header', None)\n"

VERIFY_POST = '''try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            v = str(d.get('verified')).lower() == 'true'
            allv = str(d.get('all_verified')).lower() == 'true'
            ok = str(d.get('ok')).lower() != 'false'
            left = d.get('wrong_answers_left')
            if allv:
                msg = 'Both security answers passed. Say nothing more about security.'
            elif d.get('hint') == 'day_month_swapped':
                msg = 'The day and the month look swapped. This is NOT a wrong answer. Ask the customer to say the month of their birth as a word, then call verify_identity again with the corrected date.'
            elif not ok:
                msg = 'The answer could not be read and was not counted as wrong. Ask the customer to repeat the same answer.'
            elif v:
                msg = 'This answer is correct. Now ask the security question that has not passed yet: the date of birth first, then the last four digits of the phone number on file. Ask only one question.'
            elif str(left) == '0':
                msg = 'No tries are left. Say nothing about the account.'
            else:
                msg = 'This answer does not match our records. Tell the customer it does not match and ask the same question once more. Do not reveal the right answer.'
            d['what_to_do_next'] = msg
except Exception:
    pass
'''

PROMISE_POST = '''try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            if str(d.get('ok')).lower() == 'true':
                d['what_to_do_next'] = 'The promise is recorded.'
            else:
                d['what_to_do_next'] = 'The promise was NOT recorded. Never say it is recorded.'
except Exception:
    pass
'''

CALLBACK_POST = '''try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            if str(d.get('ok')).lower() == 'true':
                d['what_to_do_next'] = 'The callback is booked.'
            else:
                d['what_to_do_next'] = 'The callback was NOT booked. Say that the booking did not work. Call schedule_callback once more with the same date and time. If it fails again, say you could not book it and end the call as not reached, no callback.'
except Exception:
    pass
'''

GENERIC_POST = '''try:
    if isinstance(result, dict):
        result.pop('header', None)
except Exception:
    pass
'''

# ------------------------------------------------------------------ builders


def api_tool(name, path, body, description="", required=None, retries=0, post=GENERIC_POST):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(body)
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description or name,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": BASE + path},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": props, "required": ["customer_id"] + (required or [])},
                },
            },
        },
    }
    if post:
        t["post_process_code"] = post
    return t


def cond_true(var):
    return {"logic": "or", "conditions": [
        {"variable": var, "operator": "equals", "operand": "true"},
        {"variable": var, "operator": "equals", "operand": "True"}]}


def cond_false_or_fail(var, failvar):
    return {"logic": "or", "conditions": [
        {"variable": var, "operator": "equals", "operand": "false"},
        {"variable": var, "operator": "equals", "operand": "False"},
        {"variable": failvar, "operator": "greater_than", "operand": 0}]}


def go(target, description):
    return {"target_node": target, "description": description,
            "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": description}}


ALWAYS = lambda t: {"target_node": t, "description": "always", "condition": {"operator": "always"}}

NODES = {}


def conv(key, task, transitions, tools=None, on_enter=None, max_turns=20, cap_target=None, first_only=True, extra=None):
    n = {
        "name": key,
        "node_type": "conversation",
        "task_message": task,
        "tools": tools or [],
        "transitions": transitions,
        "max_node_turns": max_turns,
        "max_turn_transition": cap_target,
        "on_enter_first_entry_only": first_only,
    }
    if on_enter:
        n["on_enter"] = on_enter
    if extra:
        n.update(extra)
    NODES[key] = n


# ------------------------------------------------------------------ close steps (the only steps with close_call)

GOODBYE = "Thank you for your time. Goodbye."
CLOSES = {
    # key: (outcome, reason, spoken line)
    "close_promise": ("promise", None, "Thank you for your time, {{title}} {{last_name}}. Goodbye."),
    "close_paid": ("paid", None, "Thank you for letting us know, {{title}} {{last_name}}. Goodbye."),
    "close_transferred_restructuring": ("transferred", "restructuring", GOODBYE),
    "close_transferred_human": ("transferred", "human", GOODBYE),
    "close_transferred_support": ("transferred", "support", GOODBYE),
    "close_no_promise_refused": ("no_promise", "refused", GOODBYE),
    "close_no_promise_hardship": ("no_promise", "hardship", GOODBYE),
    "close_no_promise_dispute": ("no_promise", "dispute", GOODBYE),
    "close_no_promise_service_error": ("no_promise", "service_error",
        "I am sorry, I could not record your promise because of a technical problem, so nothing has been recorded. Thank you for your time. Goodbye."),
    "close_account_unavailable": ("no_promise", "service_error",
        "I am sorry, I cannot access the account details right now because of a technical problem. Thank you for your time. Goodbye."),
    "close_not_verified_failed": ("not_verified", "failed",
        "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye."),
    "close_not_verified_declined": ("not_verified", "declined", GOODBYE),
    "close_not_reached_callback": ("not_reached", "callback", "Thank you, we will call back at that time. Goodbye."),
    "close_not_reached_no_callback": ("not_reached", "no_callback", GOODBYE),
    "close_not_reached_wrong_number": ("not_reached", "wrong_number", "Thank you, and sorry for the trouble. Goodbye."),
    "close_not_reached_deceased": ("not_reached", "deceased", "I am sorry for your loss. Thank you for your time. Goodbye."),
    "close_not_reached_unclear": ("not_reached", "unclear", GOODBYE),
}

for key, (outcome, reason, line) in CLOSES.items():
    body = {"outcome": {"type": "string", "enum": [outcome], "default": outcome}}
    if reason:
        body["reason"] = {"type": "string", "default": reason}
    NODES[key] = {
        "name": key,
        "node_type": "api_request",
        "passthrough": True,
        "passthrough_default_transition": "hangup",
        "on_enter": {"type": "tts", "text": line},
        "disable_inactivity_monitor": True,
        "pre_actions": [api_tool("close_call", "/close_call", body, "Close the call.", ["outcome"], retries=2, post=None)],
        "transitions": [ALWAYS("hangup")],
    }

NODES["hangup"] = {
    "name": "hangup",
    "node_type": "end_call",
    "on_enter": {"type": "silent"},
    "disable_inactivity_monitor": True,
    "transitions": [],
    "terminal": {"type": "function", "function": {
        "name": "call_closed", "handler": "__function__:end_call",
        "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
}

# ------------------------------------------------------------------ transfer steps

TRANSFERS = {
    "transfer_restructuring": ("restructuring", "close_transferred_restructuring",
                               "I am connecting you now with our team that handles payment plans."),
    "transfer_human": ("general", "close_transferred_human", "I am connecting you now with a colleague."),
    "transfer_support": ("support", "close_transferred_support", "I am connecting you now with our customer support team."),
}
for key, (queue, close, line) in TRANSFERS.items():
    NODES[key] = {
        "name": key,
        "node_type": "api_request",
        "passthrough": True,
        "passthrough_default_transition": close,
        "on_enter": {"type": "tts", "text": line},
        "disable_inactivity_monitor": True,
        "pre_actions": [api_tool("transfer_to_agent", "/transfer_to_agent",
                                 {"queue": {"type": "string", "enum": [queue], "default": queue}},
                                 "Hand the call to a person.", ["queue"], retries=1, post=None)],
        "transitions": [ALWAYS(close)],
    }

# ------------------------------------------------------------------ setup and opening

NODES["setup"] = {
    "name": "setup",
    "node_type": "code",
    "passthrough": True,
    "passthrough_default_transition": "opening",
    "on_enter": {"type": "silent"},
    "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "function": {
        "name": "code_exec", "handler": "__function__:code_exec",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "default": SETUP_CODE},
            "timeout_ms": {"type": "number", "default": 10000}}}}}],
    "transitions": [ALWAYS("opening")],
}

T_HUMAN = go("transfer_human",
             "The person asked for a human, a person or an agent, you already asked once whether you can help them first, and they insist on a person.")

conv("opening",
     """You have just said that you are Freya Bank's digital assistant, that the call is recorded, and asked "Am I speaking with {{title}} {{last_name}}?".
Your only job in this step is to find out who answered. Do not call any bank tool in this step.

Strict rule: do not say "collections", "debt", "payment", "late", "overdue" or the name of any product, and do not say why you are calling. This holds for everyone, relatives included.

Confirmation:
- Only "yes", "that's me", "speaking", "it is", or the person saying the customer's own name ({{first_name}} {{last_name}}) confirm. Then call transition_to_security at once, with no other text.
- "Hello", "go ahead", "who is this", "what is this about" or anything else do not confirm. Then ask once more: "Am I speaking with {{title}} {{last_name}}?"
- If it is still unclear after that second ask, say a short thank you and call transition_to_close_not_reached_unclear.
- If the person asks whether this is a robot or an AI: say it is Freya Bank's digital assistant. If they ask whether this is a scam: say they can verify the call by phoning Freya Bank's customer service number. After answering, ask "Am I speaking with {{title}} {{last_name}}?" once more. That ask counts as the second ask.

Other answers:
- Someone else answered (for example "he is not here", "this is his wife", "no, I am his son"): call transition_to_someone_else with no other text.
- The number does not belong to {{title}} {{last_name}} (wrong number, never heard of them): call transition_to_close_not_reached_wrong_number.
- The person says {{title}} {{last_name}} has died: do not ask anything. Call transition_to_close_not_reached_deceased with no other text; the condolence is said for you.
- The person says twice that they do not want to talk: call transition_to_close_not_verified_declined.
- A request for a human: ask once whether you can help first. If they insist, call transition_to_transfer_human.

Never end a turn without speaking or calling a transition.""",
     [go("security", "The person confirmed they are the customer: yes, that's me, speaking, or they said the customer's own name."),
      go("someone_else", "Someone other than the customer answered the phone."),
      go("close_not_reached_wrong_number", "The number does not belong to the customer."),
      go("close_not_reached_deceased", "The person says the customer has died."),
      go("close_not_reached_unclear", "It is still unclear who answered after the second ask."),
      go("close_not_verified_declined", "The person said twice that they do not want to talk."),
      T_HUMAN],
     on_enter={"type": "tts", "text": "Hello, this is the digital assistant calling from Freya Bank. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
     max_turns=8, cap_target="close_not_reached_unclear")

conv("someone_else",
     """Someone other than {{title}} {{last_name}} is on the phone. Say nothing about why you are calling and nothing about any account, even if they ask, even if they offer to pay or to answer questions for the customer. Do not say "collections", "debt", "payment" or a product name. Do not ask them security questions.

Ask when {{title}} {{last_name}} can be reached. Current time: {{now}}.
Allowed callback times (the only ones you may book):
{{callback_window}}

Rules:
- When they name a day and a time inside the allowed window, call schedule_callback with the date as YYYY-MM-DD and the time as HH:MM (24 hour). If they give only a vague time ("this afternoon", "later"), ask for an exact time.
- If the day or time they name is outside the window, say you can only arrange a call back today or on {{callback_next_bd}} between 10:00 and 19:00, and ask once for another time.
- If the second time they name is also outside the window, or they cannot give any time, book nothing; say a short thank you and call transition_to_close_not_reached_no_callback.
- If they say the number does not belong to that person: call transition_to_close_not_reached_wrong_number.
- If they say the customer has died: call transition_to_close_not_reached_deceased with no other text.
- If the person now says that they are in fact {{title}} {{last_name}}: call transition_to_security.
- A request for a human: ask once whether you can help first; if they insist, call transition_to_transfer_human.
- If the schedule_callback result is not ok, say the booking did not work, try once more, and if it fails again say you could not book it and call transition_to_close_not_reached_no_callback. Never say a callback is booked unless the tool returned ok true.
- Robot or AI question: you are Freya Bank's digital assistant. Scam question: they can verify the call by phoning Freya Bank's customer service number.

One or two short sentences per turn. After every tool result, speak or call the next tool.""",
     [{"target_node": "close_not_reached_callback", "description": "The callback was booked",
       "condition": cond_true("schedule_callback_response.data.ok")},
      go("close_not_reached_no_callback", "No callback time inside the allowed window was given after asking once more, or booking failed twice."),
      go("close_not_reached_wrong_number", "The number does not belong to the customer."),
      go("close_not_reached_deceased", "The person says the customer has died."),
      go("security", "The person says they are in fact the customer."),
      T_HUMAN],
     tools=[api_tool("schedule_callback", "/schedule_callback", {
         "date": {"type": "string", "default": "{{callback_date}}", "description": "Callback day as YYYY-MM-DD. Must be inside the allowed window."},
         "time": {"type": "string", "default": "{{callback_time}}", "description": "Callback time as HH:MM, 24 hour, from 10:00 to 19:00."},
     }, "Book a callback. CALL it as soon as the person names a day and time inside the allowed window. Never call it for a time outside the window.",
         ["date", "time"], retries=0, post=CALLBACK_POST)],
     on_enter={"type": "llm", "prompt": "Without saying why you are calling, ask politely when {{title}} {{last_name}} can be reached."},
     max_turns=10, cap_target="close_not_reached_no_callback")

# ------------------------------------------------------------------ security

conv("security",
     """The person confirmed they are {{title}} {{last_name}}. Your only job here is the security check. You know nothing about the account yet. Do not say "collections", "debt", "payment" or a product name.

Ask two questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
- CALL verify_identity for every answer the customer gives: field date_of_birth or phone_last4. One call per message.
- Send a date of birth as YYYY-MM-DD, however the customer said it. A date given only in numbers is read as day, then month, then year (for example 03/04/1985 is 1985-04-03). Convert spoken dates ("the fifth of March eighty-five" is 1985-03-05).
- The phone answer is four digits.
- Each tool result has a what_to_do_next line. Do what it says.
- A wrong answer may be asked again. Do not reveal the right answer.

If the customer does not want to answer, or asks what the call is about instead of answering: explain once that these questions protect their account, and ask again. If they refuse a second time or ask a second time what the call is about, say a short thank you and call transition_to_close_not_verified_declined. If they say twice that they do not want to talk, do the same.
A request for a human: ask once whether you can help first; if they insist, call transition_to_transfer_human.
Robot or AI question: you are Freya Bank's digital assistant, then continue. Scam question: they can verify the call by phoning Freya Bank's customer service number, then continue.

One or two short sentences per turn. After every tool result, speak or call the next tool. Never end a turn with nothing.""",
     [{"target_node": "load_account", "description": "Both security answers passed",
       "condition": cond_true("verify_identity_response.data.all_verified")},
      {"target_node": "close_not_verified_failed", "description": "Three wrong answers",
       "condition": {"logic": "or", "conditions": [
           {"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"}]}},
      go("close_not_verified_declined", "The customer refused the security questions a second time, or asked a second time what the call is about instead of answering, or said twice they do not want to talk."),
      T_HUMAN],
     tools=[api_tool("verify_identity", "/verify_identity", {
         "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                   "description": "Which question this answer is for: date_of_birth or phone_last4."},
         "answer": {"type": "string", "default": "{{answer}}",
                    "description": "date_of_birth as YYYY-MM-DD (numbers-only dates are day, month, year). phone_last4 as four digits."},
     }, "Check one security answer. CALL it every time the customer answers a security question, one answer per call.",
         ["field", "answer"], retries=0, post=VERIFY_POST)],
     on_enter={"type": "tts", "text": "Thank you. Before we continue, I need to verify your identity. Could you please tell me your date of birth?"},
     max_turns=14, cap_target="close_not_verified_declined")

# ------------------------------------------------------------------ account

NODES["load_account"] = {
    "name": "load_account",
    "node_type": "api_request",
    "passthrough": True,
    "passthrough_default_transition": "account_facts",
    "on_enter": {"type": "silent"},
    "disable_inactivity_monitor": True,
    "pre_actions": [api_tool("get_account", "/get_account", {}, "Get the late products.", [], retries=2, post=None)],
    "response_mapping": [{"path": "data.products", "variable": "products"}, {"path": "data.ok", "variable": "account_ok"}],
    "transitions": [ALWAYS("account_facts")],
}

NODES["account_facts"] = {
    "name": "account_facts",
    "node_type": "code",
    "passthrough": True,
    "passthrough_default_transition": "promise",
    "on_enter": {"type": "silent"},
    "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "function": {
        "name": "code_exec", "handler": "__function__:code_exec",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "default": ACCOUNT_CODE},
            "timeout_ms": {"type": "number", "default": 10000}}}}}],
    "transitions": [
        {"target_node": "close_account_unavailable", "description": "The account could not be read",
         "condition": {"logic": "or", "conditions": [{"variable": "account_state", "operator": "equals", "operand": "error"}]}},
        ALWAYS("promise")],
}

FACTS = """Account facts (from the bank; these are the only figures you know):
- Product: {{product_words}}
- Full past-due amount: {{past_due_text}}
- Days late: {{days_late_n}}. Stage: {{stage}}.
- Floor amount (the {{floor_name}}): {{floor_text}}
- Today: {{today_label}}. Now: {{now}}.
- PTP deadline (latest date you can record): {{deadline_label}}
- Persuasion attempts allowed: {{attempts_allowed}}
- Date for the first persuasion attempt: {{attempt1_label}}

Calendar (use it for every date; never work out weekdays yourself):
{{ptp_calendar}}

Weekday phrases: "next <weekday>" is that weekday in the following calendar week, "this <weekday>" is the one in the current week:
{{weekday_phrases}}
"""

T_RESTR = go("transfer_restructuring", "The customer asks for a new payment plan, lower instalments or restructuring.")
T_SUPPORT = go("transfer_support", "The customer has a hardship (illness, a death in the family, job loss) and accepted to be connected with the customer support team.")

conv("promise",
     FACTS + """
You already said that you are calling from the collections team about the late payment, named the product, the amount and the days late, and asked "Can you make this payment today?".

Your job: get a promise to pay (PTP) for this product, inside the rules below, and record it with create_promise.

AMOUNTS
- Always propose amounts yourself. Never ask "how much can you pay?".
- The first amount is the full past-due amount, {{past_due_text}}.
- If the customer says the full amount is too much: offer the floor, {{floor_text}}, once, and say that the rest stays overdue.
- An amount the customer proposes from {{floor_text}} up to {{past_due_text}}, both included, is accepted.
- An amount below {{floor_text}}: say it cannot be recorded and offer {{floor_text}} once. If they do not accept it, that is a flat refusal.
- Never offer a discount, a waiver, an instalment plan, or any other term.

DATES
- A PTP date must be marked "valid PTP date" in the calendar: today or later, a business day, not after the deadline.
- A weekend day or holiday that is not after the deadline: offer the next business day shown in the calendar.
- A date after the deadline: say the latest date you can record is {{deadline_label}} and offer it. Refusing the deadline is a flat refusal.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still name no day, propose the deadline, {{deadline_label}}.

PERSUASION
- A date or an amount the customer proposes is never a refusal. Handle it with the rules above.
- A flat refusal or a non-answer uses one persuasion attempt. "No" to paying today, with no date and no amount, is a flat refusal.
- Attempt 1: propose the full amount {{past_due_text}} (or the floor {{floor_text}} if they already said the full amount is too much) on {{attempt1_label}}.
- Attempt 2, only when the stage is late: propose the floor {{floor_text}} on the deadline {{deadline_label}}.
- This customer has {{attempts_allowed}} attempt(s). When they are used up and the customer still refuses, stop. Do not repeat an offer they already refused. Thank them and call transition_to_close_no_promise_refused.

CONFIRM AND RECORD
- When the customer agrees to an amount and a date, read back the product, the amount and the date, and ask "Do you confirm?".
- Only after a clear yes, CALL create_promise with amount as a number (for example {{past_due_plain}} or {{floor_plain}}) and date as YYYY-MM-DD. Saying it is recorded is not enough; the tool must be called.
- If they change the date or the amount instead, check the new value with the rules above and read back again.
- Never say the promise is recorded unless create_promise returned ok true.

OTHER SITUATIONS (these come before persuasion)
- Illness, a death in the family or job loss: one short sentence of sympathy, no persuasion. Offer to connect them with the customer support team. If they accept, call transition_to_transfer_support. If they decline, call transition_to_close_no_promise_hardship. If they still name a date or an amount themselves, take the PTP under the rules above.
- New payment plan or lower instalments: describe no plan; call transition_to_transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transition_to_transfer_human.
- "I already paid" (this past-due amount): say payments can take one business day to appear, take no PTP, and call transition_to_close_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no PTP, call transition_to_close_no_promise_dispute.
- The customer says twice that they do not want to talk: call transition_to_close_no_promise_refused.
- A question the facts above cannot answer: say you do not have that information. Do not invent figures, dates or reasons.
- Robot or AI question: you are Freya Bank's digital assistant. Scam question: they can verify the call by phoning Freya Bank's customer service number. Then go on.

Address the customer as {{title}} {{last_name}}. One or two short sentences per turn. Call one tool per message. After every tool result, speak or call the next tool.""",
     [{"target_node": "promise_recorded", "description": "The promise was recorded",
       "condition": cond_true("create_promise_response.data.ok")},
      {"target_node": "promise_retry", "description": "Recording the promise failed",
       "condition": cond_false_or_fail("create_promise_response.data.ok", "create_promise_failure_count")},
      T_SUPPORT,
      go("close_no_promise_hardship", "The customer has a hardship and declined to be connected with the customer support team, and named no date or amount."),
      T_RESTR,
      T_HUMAN,
      go("close_paid", "The customer says they already paid this past-due amount."),
      go("close_no_promise_dispute", "The customer says the debt is not theirs, they never had the product, or it was closed or paid off in the past."),
      go("close_no_promise_refused", "All persuasion attempts are used up and the customer still refuses, or the customer said twice they do not want to talk.")],
     tools=[api_tool("create_promise", "/create_promise", {
         "product_id": {"type": "string", "default": "{{product_id}}"},
         "amount": {"type": "number", "default": "{{ptp_amount}}", "description": "Promised amount as a number, between the floor and the full past-due amount."},
         "date": {"type": "string", "default": "{{ptp_date}}", "description": "Promised payment date as YYYY-MM-DD, a valid PTP date from the calendar."},
     }, "Record the payment promise. CALL it only after the customer said a clear yes to your read-back of product, amount and date. Call it once.",
         ["product_id", "amount", "date"], retries=0, post=PROMISE_POST)],
     on_enter={"type": "tts", "text": "Thank you, {{title}} {{last_name}}, you are verified. I am calling from the collections team about a late payment on your {{product_words}}. The past-due amount is {{past_due_text}}, and it is {{days_late_n}} days late. Can you make this payment today?"},
     max_turns=30, cap_target="close_no_promise_refused")

conv("promise_retry",
     """Recording the promise failed on the first try. Nothing is recorded yet.
Tell the customer in one short sentence that recording did not work and that you are trying once more, and in the same message CALL create_promise_retry with exactly the same amount and date the customer confirmed (see the earlier create_promise call). Never say the promise is recorded unless create_promise_retry returned ok true.""",
     [{"target_node": "promise_recorded", "description": "The promise was recorded on the second try",
       "condition": cond_true("create_promise_retry_response.data.ok")},
      {"target_node": "close_no_promise_service_error", "description": "The second try failed too",
       "condition": cond_false_or_fail("create_promise_retry_response.data.ok", "create_promise_retry_failure_count")}],
     tools=[api_tool("create_promise_retry", "/create_promise", {
         "product_id": {"type": "string", "default": "{{product_id}}"},
         "amount": {"type": "number", "default": "{{retry_amount}}", "description": "The same amount as in the failed create_promise call."},
         "date": {"type": "string", "default": "{{retry_date}}", "description": "The same date as in the failed create_promise call, YYYY-MM-DD."},
     }, "Second and last try to record the promise. CALL it now, once, with the same amount and date.",
         ["product_id", "amount", "date"], retries=0, post=PROMISE_POST)],
     max_turns=3, cap_target="close_no_promise_service_error")

conv("promise_recorded",
     """The promise to pay for the {{product_words}} is recorded. You have told the customer it is recorded and that a text message will confirm it, and asked whether there is anything else.
Do not call a bank tool in this step.
- Nothing else, or a thank you: call transition_to_close_promise with no other text.
- They want to change or cancel the promise: say it cannot be changed in this call, they can change it in the mobile app. Then ask if there is anything else.
- New payment plan or lower instalments: describe no plan; call transition_to_transfer_restructuring.
- A request for a human: ask once whether you can help first; if they insist, call transition_to_transfer_human.
- A question you cannot answer from what was said: say you do not have that information.""",
     [go("close_promise", "The customer needs nothing else."),
      T_RESTR, T_HUMAN],
     on_enter={"type": "tts", "text": "Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
     max_turns=6, cap_target="close_promise")

SYSTEM = """You are Freya Bank's digital assistant, making an outbound call. Speak English. Keep every turn to one or two short sentences.
Address the customer as {{title}} {{last_name}}.
Today's date and time is {{now}}. Use it for every date; never use another clock.
Never improvise: never offer a discount, a waiver, an instalment plan, or any term that is not in your instructions.
If asked something you cannot answer from your instructions or tool results, say you do not have that information. Never invent figures, dates or reasons.
If asked whether this is a scam: they can verify the call by phoning Freya Bank's customer service number. Then go on.
If asked whether you are a robot or an AI: you are Freya Bank's digital assistant. Then go on.
Never say something is recorded, booked or done unless the tool returned ok true. If a tool fails, say so.
When an instruction says to call a tool or a transition, call it; saying you did it is not enough. Call one tool per message. After every tool result, speak or call the next tool. Never end a turn with nothing.
Do not say goodbye yourself when you call a transition_to_close or transition_to_transfer tool: the closing words are spoken for you."""

WORKFLOW = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": NODES,
    "global_nodes": {},
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

# cap targets must be set; drop empty ones
for n in NODES.values():
    if n.get("max_turn_transition") is None:
        n.pop("max_turn_transition", None)
        n.pop("max_node_turns", None)

if __name__ == "__main__":
    (HERE / "brief-a-raw.workflow.json").write_text(json.dumps(WORKFLOW, indent=1))
    print("nodes:", len(NODES))
