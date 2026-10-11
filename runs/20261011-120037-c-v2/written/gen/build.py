"""Generate the workflows for brief-a-raw (one product) and brief-b-raw (one to three products).

Every rule and value here is taken from briefs/brief-a-raw.md (Contact Policy CP-4, memo OPS-2026-41, close code
list) and, for slot brief-b-raw, from briefs/brief-b-raw.md (change notice CN-12), which extends that material.

    python3 gen/build.py            # writes out/brief-a-raw.workflow.json and out/brief-b-raw.workflow.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
OUT = Path(__file__).resolve().parent.parent / "out"

# ---------------------------------------------------------------- policy values (CP-4 as changed by OPS-2026-41)
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]  # memo item 1
EARLY_MAX_DAYS = 7          # CP-4 2.5 b: 1-7 early
EARLY_DEADLINE_BD = 12      # 12th business day after today
LATE_DEADLINE_BD = 7        # memo item 3: 7th business day after today
EARLY_ATTEMPTS = 1
LATE_ATTEMPTS = 2
CB_START, CB_END = "10:00", "19:00"  # CP-4 2.2 b and memo item 2: today or next business day


# ---------------------------------------------------------------- helpers

def api_tool(name, path, fields, description, retries=0, post=None, mapping=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(fields)
    required = [k for k, v in fields.items() if v.pop("_required", True)]
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
                    "url": {"type": "string", "default": f"{BASE}/{path}"},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": props, "required": required},
                },
            },
        },
    }
    if post:
        t["post_process_code"] = post
    if mapping:
        t["response_mapping"] = mapping
    return t


def cond_or(*checks):
    return {"logic": "or", "conditions": list(checks)}


def eq(var, val):
    return {"variable": var, "operator": "equals", "operand": val}


def is_true(var):
    return [eq(var, "true"), eq(var, "True")]


def is_false(var):
    return [eq(var, "false"), eq(var, "False")]


def gt(var, n):
    return {"variable": var, "operator": "greater_than", "operand": n}


def tool_tr(target, intent):
    return {"target_node": target, "description": intent, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": intent}}


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


GENERIC_POST = """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') is True:
            d['what_to_do_next'] = 'Done: the bank accepted this call. Now speak to the customer or call the next tool. Never end your turn with nothing.'
        else:
            msg = 'FAILED: the bank did not carry this out. Nothing was saved. If this is the first failure of this action, call the same tool again once with the same values. If it already failed once, tell the customer plainly that it could not be done.'
            if isinstance(d, dict):
                d['what_to_do_next'] = msg
            else:
                result['what_to_do_next'] = msg
except Exception:
    pass
"""

PROMISE_POST = """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') is True:
            d['what_to_do_next'] = 'SAVED: this promise is now in the bank system. Continue with your task. Never end your turn with nothing.'
        else:
            msg = 'NOT SAVED: the promise was not stored. If this is the first failure for this product, call create_promise again now with exactly the same product_id, amount and date. If it already failed once for this product, do not try again: tell the customer you could not record the promise for it.'
            if isinstance(d, dict):
                d['what_to_do_next'] = msg
            else:
                result['what_to_do_next'] = msg
except Exception:
    pass
"""

VERIFY_POST = """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            left = d.get('wrong_answers_left')
            if d.get('all_verified') is True:
                t = 'Both answers are correct. The customer is verified.'
            elif d.get('hint') == 'day_month_swapped':
                t = 'Day and month look swapped. This is NOT a wrong answer. Ask the customer to say the month of their date of birth as a word, then call verify_identity again.'
            elif d.get('ok') is False:
                t = 'The answer could not be read. It does NOT count as a wrong answer. Ask the customer to say it again clearly.'
            elif d.get('verified') is True:
                t = 'Correct. Now ask for the last four digits of the phone number on file. Do not ask for the date of birth again.'
            elif left == 0:
                t = 'Wrong answer and no tries are left. Say nothing about any debt.'
            else:
                t = 'Wrong answer. Do not reveal or hint at the right answer. Ask the same question again.'
            d['what_to_do_next'] = t
        else:
            result['what_to_do_next'] = 'The check did not run because of a technical problem. Nothing was counted. Call verify_identity again with the same answer.'
except Exception:
    pass
"""


def setup_code():
    return f"""import datetime
HOL = {json.dumps(HOLIDAYS)}
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
def fmt(d):
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + d.strftime('%B %Y') + ' (' + d.isoformat() + ')'
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def next_bd(d):
    x = d + datetime.timedelta(days=1)
    while not isbd(x):
        x = x + datetime.timedelta(days=1)
    return x
try:
    raw = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        nowdt = datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        nowdt = datetime.datetime.fromisoformat(raw[:10] + 'T09:00')
    today = nowdt.date()
    nowhm = nowdt.strftime('%H:%M')
    def nth_bd(n):
        d = today
        c = 0
        while c < n:
            d = d + datetime.timedelta(days=1)
            if isbd(d):
                c = c + 1
        return d
    def last_bd_of_week(d):
        monday = d - datetime.timedelta(days=d.weekday())
        for i in [4, 3, 2, 1, 0]:
            x = monday + datetime.timedelta(days=i)
            if isbd(x):
                return x
        return None
    first = last_bd_of_week(today)
    if first is None or first <= today:
        first = last_bd_of_week(today + datetime.timedelta(days=7))
    early_deadline = nth_bd({EARLY_DEADLINE_BD})
    late_deadline = nth_bd({LATE_DEADLINE_BD})
    def valid_dates(deadline):
        out = []
        d = today
        while d <= deadline:
            if isbd(d):
                out.append(fmt(d))
            d = d + datetime.timedelta(days=1)
        return '; '.join(out)
    vars['early_deadline_iso'] = early_deadline.isoformat()
    vars['early_deadline_text'] = fmt(early_deadline)
    vars['late_deadline_iso'] = late_deadline.isoformat()
    vars['late_deadline_text'] = fmt(late_deadline)
    vars['early_first_text'] = fmt(min(first, early_deadline))
    vars['late_first_text'] = fmt(min(first, late_deadline))
    vars['early_valid_text'] = valid_dates(early_deadline)
    vars['late_valid_text'] = valid_dates(late_deadline)
    monday = today - datetime.timedelta(days=today.weekday())
    lines = []
    lines.append('Today is ' + fmt(today) + ', time now ' + nowhm + '. Today is ' + ('a business day.' if isbd(today) else 'NOT a business day.'))
    lines.append('Bank holidays: ' + ', '.join(HOL) + '. Business days are Monday to Friday except these holidays.')
    lines.append('Week table ("this <weekday>" = current week, "next <weekday>" = the following calendar week):')
    for i in range(7):
        a = monday + datetime.timedelta(days=i)
        b = monday + datetime.timedelta(days=i + 7)
        lines.append('- this ' + WD[i] + ' = ' + fmt(a) + '; next ' + WD[i] + ' = ' + fmt(b))
    lines.append('Calendar from today (non-business days show the next business day):')
    end = max(early_deadline, late_deadline) + datetime.timedelta(days=14)
    d = today
    while d <= end:
        if isbd(d):
            lines.append('- ' + fmt(d) + ': business day')
        else:
            kind = 'bank holiday' if d.isoformat() in HOL else 'weekend'
            lines.append('- ' + fmt(d) + ': ' + kind + ', next business day ' + fmt(next_bd(d)))
        d = d + datetime.timedelta(days=1)
    vars['date_facts'] = chr(10).join(lines)
    cb = []
    if nowhm < '{CB_END}':
        if nowhm < '{CB_START}':
            cb.append('today ' + fmt(today) + ': from {CB_START} to {CB_END}, both included')
        else:
            cb.append('today ' + fmt(today) + ': only a time later than ' + nowhm + ', up to {CB_END} included')
    nb = next_bd(today)
    cb.append('next business day ' + fmt(nb) + ': from {CB_START} to {CB_END}, both included')
    vars['callback_facts'] = 'Allowed callback slots: ' + ' OR '.join(cb) + '. Nothing else is allowed (no other day, no time before {CB_START} or after {CB_END}).'
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Date facts unavailable.'
    vars['callback_facts'] = 'Callback facts unavailable.'
    vars['setup_state'] = 'error'
"""


def prepare_code():
    return f"""import json
import re
WORDS = dict(credit_card='credit card', personal_loan='personal loan', car_loan='car loan')
def money(x):
    try:
        f = float(x)
    except Exception:
        return str(x)
    if f == int(f):
        return format(int(f), ',')
    return format(f, ',.2f')
def parse(p):
    if isinstance(p, str):
        s = p.strip()
        try:
            return json.loads(s)
        except Exception:
            try:
                return json.loads(s.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
            except Exception:
                return None
    return p
try:
    prods = None
    for key in ['products', 'load_account_response.data.products', 'get_account_response.data.products']:
        cand = parse(vars.get(key))
        if isinstance(cand, list) and cand:
            prods = cand
            break
    if not prods:
        items = dict()
        for k in list(vars.keys()):
            m = re.match(r'^(?:(?:load_account|get_account)_response[.]data[.])?products[.](\\d+)[.](\\w+)$', str(k))
            if m:
                items.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
        prods = [items[i] for i in sorted(items)]
    prods = [p for p in prods if isinstance(p, dict)][:3]
    sentences = []
    ids = []
    for i in range(3):
        n = str(i + 1)
        if i >= len(prods):
            for f in ['id', 'words', 'past_due', 'past_due_text', 'days_late', 'facts', 'floor_text']:
                vars['p' + n + '_' + f] = ''
            continue
        p = prods[i]
        typ = str(p.get('type') or '')
        words = WORDS.get(typ, typ.replace('_', ' '))
        if typ == 'credit_card' and p.get('card_last4'):
            words = 'credit card ending ' + str(p.get('card_last4'))
        if typ == 'credit_card':
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        else:
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        try:
            days = int(float(p.get('days_late')))
        except Exception:
            days = 0
        stage = 'early' if days <= {EARLY_MAX_DAYS} else 'late'
        dl_text = vars.get(stage + '_deadline_text')
        first_text = vars.get(stage + '_first_text')
        valid = vars.get(stage + '_valid_text')
        attempts = {EARLY_ATTEMPTS} if stage == 'early' else {LATE_ATTEMPTS}
        pid = str(p.get('product_id') or '')
        ids.append(pid)
        facts = []
        facts.append('Product ' + n + ': ' + words + ' (product_id ' + pid + ').')
        facts.append('Full past-due amount: ' + money(p.get('past_due')) + '. Days late: ' + str(days) + '. Stage: ' + stage + '.')
        facts.append('Floor (' + floor_name + '): ' + money(floor) + '.')
        facts.append('PTP deadline: ' + str(dl_text) + '. Persuasion attempts for this product: ' + str(attempts) + '.')
        facts.append('First persuasion attempt: the full amount ' + money(p.get('past_due')) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much) on ' + str(first_text) + '.')
        if attempts > 1:
            facts.append('Second persuasion attempt: the floor ' + money(floor) + ' on the deadline ' + str(dl_text) + '.')
        else:
            facts.append('There is no second persuasion attempt for this product.')
        facts.append('Valid PTP dates for this product (nothing else may be accepted): ' + str(valid) + '.')
        vars['p' + n + '_id'] = pid
        vars['p' + n + '_words'] = words
        vars['p' + n + '_past_due'] = p.get('past_due')
        vars['p' + n + '_past_due_text'] = money(p.get('past_due'))
        vars['p' + n + '_days_late'] = str(days)
        vars['p' + n + '_floor_text'] = money(floor)
        vars['p' + n + '_facts'] = chr(10).join(facts)
        sentences.append('Your ' + words + ' has a past-due amount of ' + money(p.get('past_due')) + ' and is ' + str(days) + ' days late.')
    vars['product_count'] = len(prods)
    vars['product_ids_text'] = ', '.join(ids)
    vars['products_sentences'] = ' '.join(sentences)
    vars['all_facts'] = chr(10).join([str(vars.get('p' + str(i + 1) + '_facts')) for i in range(len(prods))])
    vars['today_question'] = 'Can you make this payment today?' if len(prods) == 1 else 'Can you pay all of them today?'
    vars['account_state'] = 'ok' if prods else 'empty'
except Exception as e:
    vars['account_state'] = 'error'
    vars['product_count'] = 0
"""


def code_node(name, code, nxt, extra=None):
    trs = (extra or []) + [always(nxt)]
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code},
                                                                          "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": trs,
    }


def conv(name, task, tools=None, transitions=None, on_enter=None, max_turns=30, cap_target=None, first_only=False):
    n = {"name": name, "node_type": "conversation", "task_message": task, "transitions": transitions or [],
         "max_node_turns": max_turns}
    if tools:
        n["tools"] = tools
    if on_enter:
        n["on_enter"] = on_enter
    if cap_target:
        n["max_turn_transition"] = cap_target
    if first_only:
        n["on_enter_first_entry_only"] = True
    return n


def say(name, text, nxt):
    """Passthrough step with a fixed spoken line, then the next step."""
    return {"name": name, "node_type": "conversation", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "tts", "text": text}, "task_message": "Say nothing more. No tool call is allowed.",
            "disable_inactivity_monitor": True, "transitions": [always(nxt)]}


def close_node(name, outcome, reason):
    fields = {"outcome": {"type": "string", "enum": [outcome], "default": outcome, "_required": True}}
    if reason:
        fields["reason"] = {"type": "string", "default": reason, "_required": False}
    tool = api_tool("close_call", "close_call", fields, "End the call.", retries=2)
    return {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "end",
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [tool],
            "transitions": [always("end")]}


def transfer_node(name, queue, ok_next, fail_next):
    tool = api_tool("transfer_to_agent", "transfer_to_agent",
                    {"queue": {"type": "string", "enum": [queue], "default": queue}}, "Hand the call to a person.", retries=1)
    return {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": ok_next,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [tool],
            "transitions": [
                {"target_node": fail_next, "description": "transfer failed",
                 "condition": cond_or(gt(f"{name}_failure_count", 0), *is_false(f"{name}_response.data.ok"),
                                      *is_false("transfer_to_agent_response.data.ok"))},
                always(ok_next)]}


# ---------------------------------------------------------------- tools offered to the model

def verify_tool():
    return api_tool("verify_identity", "verify_identity", {
        "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                  "description": "Which question this answer is for: date_of_birth or phone_last4."},
        "answer": {"type": "string", "default": "{{answer}}",
                   "description": "date_of_birth: the date as YYYY-MM-DD (a date said only in numbers is day, then month, then year). phone_last4: exactly four digits."},
    }, "Check one security answer. CALL it every time the customer gives a complete answer to the current security question. One answer per call.",
        post=VERIFY_POST)


def callback_tool():
    return api_tool("schedule_callback", "schedule_callback", {
        "date": {"type": "string", "default": "{{cb_date}}", "description": "Callback date as YYYY-MM-DD. Must be one of the allowed callback days."},
        "time": {"type": "string", "default": "{{cb_time}}", "description": "Callback time as HH:MM, 24 hour, inside the allowed window."},
    }, "Book a callback. CALL it as soon as the person names a day and time that is inside the allowed callback slots. Never call it for a time outside them.",
        post=GENERIC_POST)


def promise_tool(baked_pid):
    fields = {}
    if baked_pid:
        fields["product_id"] = {"type": "string", "default": "{{p1_id}}"}
    else:
        fields["product_id"] = {"type": "string", "default": "{{product_id}}",
                                "description": "product_id of the product, copied exactly from the product facts (for example p1)."}
    fields["amount"] = {"type": "number", "default": "{{amount}}", "description": "Promised amount, a number, as confirmed by the customer."}
    fields["date"] = {"type": "string", "default": "{{date}}", "description": "Promised payment date as YYYY-MM-DD, as confirmed by the customer."}
    return api_tool("create_promise", "create_promise", fields,
                    "Record one payment promise for one product. CALL it only after the customer answered a clear yes to \"Do you confirm?\" after the read-back.",
                    post=PROMISE_POST)


def note_tool():
    return api_tool("add_note", "add_note", {
        "product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id copied exactly from the product facts (for example p2)."},
        "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "default": "{{reason}}",
                   "description": "Why this product ended without a promise. One of: refused, hardship, dispute, paid, service_error."},
    }, "Leave a note for ONE product that ended without a recorded promise. CALL it once for each such product, after all promises are handled. Never call it when the call is being transferred.",
        post=GENERIC_POST)


# ---------------------------------------------------------------- prompt text

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. Keep every turn to one to three short sentences. Address the customer as {{title}} {{last_name}}.
Rules for the whole call:
- No improvising. Never offer a discount, a waiver, an instalment plan or any term that is not in your instructions.
- If the customer asks something your information does not answer, say you do not have that information. Never invent figures, dates or reasons.
- "Is this a scam?": say they can verify this call by phoning Freya Bank's customer service number, then go on.
- "Am I talking to a robot / an AI?": say you are Freya Bank's digital assistant, then go on.
- Call at most one tool per message. After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- When a tool fails, say so honestly. Never say or suggest something is saved or done when the tool did not return ok.
- Never say the word "recorded" or claim a promise is in place unless create_promise returned ok:true for it.
- When you move on by calling a transition_to_... tool, call it alone, with no text, unless your task says otherwise. The next step speaks for you.
- Every date rule works from the date facts given to you, never from your own idea of today."""

PRE_VERIFY = "Until the identity check has passed, never say \"collections\", \"debt\", \"payment\", the product, any amount, or why you are calling, to anyone, relatives included. If asked why you are calling, say you can only discuss that with {{title}} {{last_name}} after a short security check."

OPENING = f"""The opening line was already spoken: you introduced yourself as Freya Bank's digital assistant, said the call is kept as an audio recording, and asked "Am I speaking with {{{{title}}}} {{{{last_name}}}}?". That was the first ask.
{PRE_VERIFY}
Decide who answered:
- Only "yes", "that's me", "speaking" or the customer's own name ({{{{first_name}}}} or {{{{last_name}}}}) confirm. Then call transition_to_security.
- "Hello", "go ahead", "who is this" or anything unclear do NOT confirm: ask "Am I speaking with {{{{title}}}} {{{{last_name}}}}?" once more. If the person asks a robot or scam question, answer it first (see the general rules); the ask that follows counts as the second ask.
- If it is still unclear after the second ask, call transition_to_goodbye_not_reached_unclear.
- Someone else answered (a relative, a colleague, "he is not here"): call transition_to_third_party.
- "This number does not belong to that person" / wrong number: call transition_to_goodbye_not_reached_wrong_number.
- The customer has died: call transition_to_goodbye_not_reached_deceased with no text (the next step says the condolence).
- The person says twice that they do not want to talk: call transition_to_goodbye_not_verified_declined.
- The person asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_human.
No bank tool is available in this step."""

THIRD_PARTY = f"""Someone other than {{{{title}}}} {{{{last_name}}}} answered. Say nothing beyond the opening and never say why you are calling. A relative may not answer security questions and is told nothing about the account, even if they offer to pay.
Your only job: find out when {{{{title}}}} {{{{last_name}}}} can be reached, and book a callback.
{{{{callback_facts}}}}
Date facts:
{{{{date_facts}}}}
Rules:
- When the person names a day and time inside the allowed slots, call schedule_callback with that date (YYYY-MM-DD) and time (HH:MM). After it returns ok, the call moves on by itself.
- If the first time offered is outside the allowed slots, say you can only book later today or the next business day between {CB_START} and {CB_END}, and ask once for another time. If the second time is outside too, book nothing and call transition_to_goodbye_not_reached_no_callback.
- If they give no time at all after you asked twice, call transition_to_goodbye_not_reached_no_callback.
- If schedule_callback fails, try it once more; if it fails again, say you could not book the callback and call transition_to_goodbye_not_reached_no_callback.
- "This number does not belong to that person": call transition_to_goodbye_not_reached_wrong_number.
- The customer has died: call transition_to_goodbye_not_reached_deceased with no text.
- If the person now says they are {{{{title}}}} {{{{last_name}}}} after all, call transition_to_security.
{PRE_VERIFY}"""

SECURITY = f"""The customer confirmed who they are. Run the security check. Two questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
- Call verify_identity once for each complete answer: field date_of_birth with the date as YYYY-MM-DD, field phone_last4 with four digits. Convert spoken dates yourself ("fifth of March nineteen eighty" -> 1980-03-05). A date given only in numbers is day, then month, then year ("05/03/1980" -> 1980-03-05). If an answer is incomplete (for example only day and month, or two digits), ask for the missing part before calling the tool.
- Follow what_to_do_next in each result. A wrong answer may be asked again. A day_month_swapped hint means: ask them to say the month as a word; that is not a wrong answer.
- Never tell the customer the right answer or what is on file.
- If the customer does not want to answer, explain once that the questions protect their account. Asking what the call is about instead of answering counts as declining. On the second refusal or second such question, call transition_to_goodbye_not_verified_declined.
- The customer says twice they do not want to talk: call transition_to_goodbye_not_verified_declined.
- The customer asks for a human: ask once whether you can help first. If they insist, call transition_to_transfer_human.
{PRE_VERIFY}"""

AMOUNT_DATE_RULES = """Amount rules:
- Ask for the full past-due amount first. Never ask "how much can you pay?"; you propose every amount yourself.
- If the customer says the full amount is too much: offer the floor, once, and say that the rest stays overdue. A customer who refuses the floor has given a flat refusal.
- An amount the customer proposes from the floor up to the full amount, both included, is accepted. Below the floor: say that amount cannot be accepted and offer the floor once; if they do not accept it, that is a flat refusal.
Date rules (use only the product's valid PTP dates and the date facts):
- A PTP date must be today or later, a business day, and not after the product's deadline.
- A weekend day or bank holiday that is not after the deadline: offer the next business day from the calendar.
- A date after the deadline: say the latest date you can accept is the deadline and offer it. A customer who refuses the deadline has given a flat refusal.
- A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still name none, propose the deadline.
- "next <weekday>" and "this <weekday>": take the date from the week table. Never guess.
Persuasion rules:
- A date or an amount the customer proposes is never a refusal; handle it with the rules above.
- A flat refusal or a non-answer uses one persuasion attempt. "No" to paying today, with no date and no amount, is a flat refusal.
- First attempt: the full amount, or the floor if the customer already said the full amount is too much, on the product's first-attempt date.
- Second attempt (late stage only): the floor on the deadline.
- When the product's attempts are used up, stop. Never repeat an offer the customer already refused. Never invent other offers."""

HARDSHIP_A = """Hardship (illness, a death in the family, job loss): say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. Accepts: call transition_to_transfer_support. Declines: call transition_to_goodbye_no_promise_hardship. If they still name a date or an amount themselves, handle it as a PTP. This comes before the persuasion rules."""


def negotiate_a():
    return f"""The customer is verified. The opening of this step already told them about the late payment and asked "Can you make this payment today?".
Product facts:
{{{{p1_facts}}}}
Date facts:
{{{{date_facts}}}}

Goal: get a promise to pay (PTP) inside the rules below, or end correctly.
{AMOUNT_DATE_RULES}

Confirming: when an amount and a date are agreed and valid, read back the product ({{{{p1_words}}}}), the amount and the date, and ask exactly "Do you confirm?". Call create_promise (amount as a number, date as YYYY-MM-DD) only after a clear yes. If they change the date or amount, check it with the rules and read back again. Yes to paying today means the full amount today, if today is a valid PTP date.
If create_promise fails, call it once more with the same values. If it fails again, call transition_to_goodbye_no_promise_service_error with no text (the next step tells the customer).

{HARDSHIP_A}
Other requests:
- New payment plan or lower instalments: describe no plan and call transition_to_transfer_restructuring.
- A human: ask once whether you can help first. If they insist, call transition_to_transfer_human.
- "I already paid" (this past-due amount): take no PTP and call transition_to_goodbye_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no PTP, call transition_to_goodbye_no_promise_dispute.
- Attempts used up, or the customer said twice they do not want to talk: call transition_to_goodbye_no_promise_refused.
Never say the promise is recorded yourself; the next step does that after create_promise returned ok."""


POST_PROMISE_A = """The promise was just saved and the customer was told so and asked if there is anything else.
- Nothing else, thanks, goodbye: call transition_to_goodbye_promise.
- They want to change or cancel the promise: say it cannot be changed in this call, but they can change it in the mobile app. Then ask if there is anything else.
- New payment plan or lower instalments: call transition_to_transfer_restructuring.
- A human: ask once whether you can help first. If they insist, call transition_to_transfer_human.
- Illness, a death in the family or job loss: one sentence of sympathy, offer the customer support team; if they accept, call transition_to_transfer_support; if not, call transition_to_goodbye_promise.
No bank tool is available in this step."""


# ---------------------------------------------------------------- brief B prompts

def product_b(k):
    return f"""The customer is verified and has heard every late product. They did not agree to pay everything today, so you now take the products one at a time, in order. This step is ONLY about product {k}. Do not ask about paying today again.
Product facts:
{{{{p{k}_facts}}}}
All products (for reference only):
{{{{all_facts}}}}
Date facts:
{{{{date_facts}}}}

Start this product at its first persuasion attempt: name the product and propose the full amount on the product's first-attempt date, unless the customer already named a date or an amount for this product or for everything; then check that proposal with the rules below. What the customer said earlier about this product (a refusal, a wish to start with another product) does not shorten its steps. Attempts are counted for this product only.
{AMOUNT_DATE_RULES}
One date for everything: if the customer named one date for all products and it is after this product's deadline, this product gets its own deadline; say so clearly. Products whose deadline allows the date keep it.

Do NOT read back, ask "Do you confirm?" or call any bank tool in this step. The read-back of all products comes later.
This product is finished when one of these is true. Then call transition_to_next_product. In that same message you may say one short sentence that closes this product (for example, for a dispute, that you will note it; for paid, that payments can take one business day to appear), but do not start the next product yourself:
- An amount and a date for it are agreed and valid (it gets a PTP).
- Its attempts are used up (it ends as refused).
- The customer says it is not theirs, they never had it, or it was closed or paid off in the past (dispute): do not argue, take no PTP for it.
- The customer already paid this past-due amount (paid): take no PTP for it.
Ending the product round early: if the customer says twice they do not want to talk, call transition_to_wrap_up (the remaining products end as refused).
Hardship (illness, a death in the family, job loss): one short sentence of sympathy, no persuasion attempt, offer to connect them with the customer support team. Accepts: call transition_to_transfer_support. Declines: call transition_to_wrap_up (products without a PTP end as hardship). If they still name a date or an amount themselves, it is a PTP.
New payment plan or lower instalments: describe no plan, call transition_to_transfer_restructuring.
A human: ask once whether you can help first. If they insist, call transition_to_transfer_human."""


PRESENT_B = """The customer is verified. The opening of this step already stated every late product and asked whether they can pay all of them today.
All products:
{{all_facts}}
Date facts:
{{date_facts}}
Decide:
- Yes, all of them today (and today is a valid PTP date for every product): call transition_to_wrap_up. Each product then gets a PTP for its full amount today.
- No, or only some, or they name another date or amount: call transition_to_product_1. Do not negotiate here.
- Hardship (illness, a death in the family, job loss): one short sentence of sympathy, no persuasion, offer the customer support team. Accepts: call transition_to_transfer_support. Declines: call transition_to_wrap_up.
- New payment plan or lower instalments: call transition_to_transfer_restructuring.
- A human: ask once whether you can help first. If they insist, call transition_to_transfer_human.
- They say twice they do not want to talk: call transition_to_wrap_up.
- They say all products are not theirs or already paid: call transition_to_product_1 (each product is handled on its own).
No bank tool is available in this step."""


WRAP_B = """The product round is over. Now finish every product. Use the whole conversation so far to know how each product ended.
All products:
{{all_facts}}
Date facts:
{{date_facts}}
Product ids: {{product_ids_text}}.

Do these in order. One tool call per message.
1. If at least one product has an agreed PTP: read ALL agreed PTPs back together in one message (product, amount, date; if a product's date was moved to its own deadline, say so), and ask exactly "Do you confirm?". Wait for a clear yes. If they change a date or an amount, check it against that product's rules (valid PTP dates, floor to full amount) and read everything back again. If they withdraw a PTP, that product ends as refused.
2. After the yes, call create_promise once for each agreed product, one at a time, with its product_id, amount (number) and date (YYYY-MM-DD). If a call fails, call it once more with the same values; if it fails again, that product ends as service_error. Promises already recorded stay.
3. Tell the customer which promises are recorded (only those that returned ok) and say: "You will receive a text message confirming this promise." For a product that failed twice, say you could not record its promise.
4. For EVERY product without a recorded PTP, call add_note with its product_id and one reason: refused (attempts used up, withdrew, or did not want to talk), hardship, dispute, paid, or service_error. Also do this when no product got a PTP.
5. Then call the matching goodbye transition, with no text:
   - at least one PTP recorded: transition_to_goodbye_promise
   - no PTP recorded and every product noted paid: transition_to_goodbye_paid
   - otherwise transition_to_goodbye_no_promise_<reason> with the reason of the FIRST product, in the order listed above, whose note is not paid (refused, hardship, dispute or service_error).
Transfers: if the customer asks for a new payment plan or lower instalments, call transition_to_transfer_restructuring at once and add no notes (agreed but unrecorded PTPs are not recorded). A human: ask once whether you can help first; if they insist, call transition_to_transfer_human with no notes. A recorded PTP cannot be changed or cancelled in this call; they can change it in the mobile app.
Never say a promise is recorded unless create_promise returned ok:true for it."""


# ---------------------------------------------------------------- assemble

CODES = {
    # key: (outcome, reason, farewell)
    "promise": ("promise", "", "Thank you for your time, {{title}} {{last_name}}. Goodbye."),
    "paid": ("paid", "", "Thank you for letting me know, {{title}} {{last_name}}. Payments can take one business day to appear. Thank you for your time. Goodbye."),
    "no_promise_refused": ("no_promise", "refused", "I understand. Thank you for your time, {{title}} {{last_name}}. Goodbye."),
    "no_promise_hardship": ("no_promise", "hardship", "I understand. Thank you for your time, {{title}} {{last_name}}, and take care. Goodbye."),
    "no_promise_dispute": ("no_promise", "dispute", "I understand. Thank you for telling me, {{title}} {{last_name}}. Thank you for your time. Goodbye."),
    "not_verified_failed": ("not_verified", "failed", "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye."),
    "not_verified_declined": ("not_verified", "declined", "I understand. Thank you for your time. Goodbye."),
    "not_reached_callback": ("not_reached", "callback", "Thank you, we will call back at that time. Goodbye."),
    "not_reached_no_callback": ("not_reached", "no_callback", "Thank you for your time. Goodbye."),
    "not_reached_wrong_number": ("not_reached", "wrong_number", "I apologise for the inconvenience. Thank you for your time. Goodbye."),
    "not_reached_deceased": ("not_reached", "deceased", "I am sorry for your loss. Thank you, goodbye."),
    "not_reached_unclear": ("not_reached", "unclear", "Thank you for your time. Goodbye."),
}


def build(slot: str, multi: bool) -> dict:
    nodes = {}
    codes = dict(CODES)
    if multi:
        codes["no_promise_service_error"] = ("no_promise", "service_error", "Thank you for your time, {{title}} {{last_name}}. Goodbye.")
    else:
        codes["no_promise_service_error"] = ("no_promise", "service_error",
                                             "I am sorry, I could not record your promise because of a technical problem. Thank you for your time, {{title}} {{last_name}}. Goodbye.")
    codes["account_error"] = ("no_promise", "service_error",
                              "I am sorry, I cannot reach your details right now because of a technical problem. Thank you for your time. Goodbye.")

    # goodbye (fixed line) -> close (terminal, close_call only) -> end
    for key, (outcome, reason, line) in codes.items():
        nodes[f"goodbye_{key}"] = say(f"goodbye_{key}", line, f"close_{key}")
        nodes[f"close_{key}"] = close_node(f"close_{key}", outcome, reason)
    for q, reason in (("restructuring", "restructuring"), ("support", "support"), ("general", "human")):
        nodes[f"transfer_{reason}"] = transfer_node(f"transfer_{reason}", q, f"goodbye_transferred_{reason}", f"goodbye_transfer_failed_{reason}")
        nodes[f"goodbye_transferred_{reason}"] = say(f"goodbye_transferred_{reason}",
                                                     "I am connecting you now. Thank you for your time. Goodbye.", f"close_transferred_{reason}")
        nodes[f"goodbye_transfer_failed_{reason}"] = say(f"goodbye_transfer_failed_{reason}",
                                                         "I am sorry, I could not connect you right now. You can reach a person through Freya Bank's customer service number. Thank you for your time. Goodbye.",
                                                         f"close_transferred_{reason}")
        nodes[f"close_transferred_{reason}"] = close_node(f"close_transferred_{reason}", "transferred", reason)
    nodes["end"] = {"name": "end", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                    "transitions": [], "terminal": {"type": "function", "function": {
                        "name": "call_closed", "handler": "__function__:end_call",
                        "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}

    nodes["setup"] = code_node("setup", setup_code(), "opening")

    nodes["opening"] = conv("opening", OPENING, transitions=[
        tool_tr("security", "The person confirmed they are the customer"),
        tool_tr("third_party", "Someone other than the customer answered"),
        tool_tr("goodbye_not_reached_unclear", "Still unclear who answered after the second ask"),
        tool_tr("goodbye_not_reached_wrong_number", "The number does not belong to the customer"),
        tool_tr("goodbye_not_reached_deceased", "The customer has died"),
        tool_tr("goodbye_not_verified_declined", "The person said twice they do not want to talk"),
        tool_tr("transfer_human", "The person insisted on talking to a human"),
    ], on_enter={"type": "tts", "text": "Hello, this is Freya Bank's digital assistant calling, and this call is kept as an audio recording. Am I speaking with {{title}} {{last_name}}?"},
        first_only=True, max_turns=8, cap_target="goodbye_not_reached_unclear")

    nodes["third_party"] = conv("third_party", THIRD_PARTY, tools=[callback_tool()], transitions=[
        {"target_node": "goodbye_not_reached_callback", "description": "The callback was booked",
         "condition": cond_or(*is_true("schedule_callback_response.data.ok"))},
        tool_tr("goodbye_not_reached_no_callback", "No callback time inside the allowed window, or booking failed twice"),
        tool_tr("goodbye_not_reached_wrong_number", "The number does not belong to the customer"),
        tool_tr("goodbye_not_reached_deceased", "The customer has died"),
        tool_tr("security", "The person now confirms they are the customer"),
    ], on_enter={"type": "tts", "text": "Thank you. When would be a good time to reach {{title}} {{last_name}}?"},
        first_only=True, max_turns=12, cap_target="goodbye_not_reached_no_callback")

    nodes["security"] = conv("security", SECURITY, tools=[verify_tool()], transitions=[
        {"target_node": "load_account", "description": "Both security answers verified",
         "condition": cond_or(*is_true("verify_identity_response.data.all_verified"))},
        {"target_node": "goodbye_not_verified_failed", "description": "No wrong answers left",
         "condition": cond_or(eq("verify_identity_response.data.wrong_answers_left", "0"))},
        tool_tr("goodbye_not_verified_declined", "The customer declined the security questions twice or does not want to talk"),
        tool_tr("transfer_human", "The customer insisted on talking to a human"),
    ], on_enter={"type": "tts", "text": "Thank you. Before we continue, I need to ask two short security questions. What is your date of birth?"},
        first_only=True, max_turns=16, cap_target="goodbye_not_verified_declined")

    get_account = api_tool("get_account", "get_account", {}, "Get the late products.", retries=2)
    after_prepare = "present"
    nodes["load_account"] = {
        "name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare_account",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [get_account],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [
            {"target_node": "goodbye_account_error", "description": "The account lookup failed",
             "condition": cond_or(gt("load_account_failure_count", 0), *is_false("load_account_response.data.ok"),
                             *is_false("get_account_response.data.ok"))},
            always("prepare_account")]}
    nodes["prepare_account"] = code_node("prepare_account", prepare_code(), after_prepare, extra=[
        {"target_node": "goodbye_account_error", "description": "No product could be read",
         "condition": cond_or({"variable": "account_state", "operator": "not_equals", "operand": "ok"})}])

    if not multi:
        nodes["present"] = conv("present", negotiate_a(), tools=[promise_tool(baked_pid=True)], transitions=[
            {"target_node": "post_promise", "description": "The promise was saved",
             "condition": cond_or(*is_true("create_promise_response.data.ok"))},
            {"target_node": "goodbye_no_promise_service_error", "description": "create_promise failed twice",
             "condition": cond_or(gt("create_promise_failure_count", 1))},
            tool_tr("goodbye_no_promise_service_error", "create_promise failed twice"),
            tool_tr("goodbye_no_promise_refused", "Persuasion attempts used up, or the customer said twice they do not want to talk"),
            tool_tr("goodbye_paid", "The customer already paid"),
            tool_tr("goodbye_no_promise_dispute", "The customer disputes the debt"),
            tool_tr("goodbye_no_promise_hardship", "Hardship, the customer declined the support team"),
            tool_tr("transfer_support", "Hardship, the customer accepted the support team"),
            tool_tr("transfer_restructuring", "The customer wants a new payment plan or lower instalments"),
            tool_tr("transfer_human", "The customer insisted on talking to a human"),
        ], on_enter={"type": "tts", "text": "Thank you, {{title}} {{last_name}}, your identity is confirmed. I am calling from the collections team about a late payment on your {{p1_words}}. The past-due amount is {{p1_past_due_text}}, and it is {{p1_days_late}} days late. Can you make this payment today?"},
            first_only=True, max_turns=30, cap_target="goodbye_no_promise_refused")
        nodes["post_promise"] = conv("post_promise", POST_PROMISE_A, transitions=[
            tool_tr("goodbye_promise", "Nothing else, the customer is done"),
            tool_tr("transfer_restructuring", "The customer wants a new payment plan or lower instalments"),
            tool_tr("transfer_human", "The customer insisted on talking to a human"),
            tool_tr("transfer_support", "Hardship, the customer accepted the support team"),
        ], on_enter={"type": "tts", "text": "Thank you. Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
            first_only=True, max_turns=6, cap_target="goodbye_promise")
    else:
        transfers = [
            tool_tr("transfer_support", "Hardship, the customer accepted the support team"),
            tool_tr("transfer_restructuring", "The customer wants a new payment plan or lower instalments"),
            tool_tr("transfer_human", "The customer insisted on talking to a human"),
        ]
        nodes["present"] = conv("present", PRESENT_B, transitions=[
            tool_tr("wrap_up", "The customer will pay all products today, or the product round is skipped"),
            tool_tr("product_1", "Take the products one at a time"),
        ] + transfers, on_enter={"type": "tts", "text": "Thank you, {{title}} {{last_name}}, your identity is confirmed. I am calling from the collections team about late payments. {{products_sentences}} {{today_question}}"},
            first_only=True, max_turns=8, cap_target="product_1")
        for k in (1, 2, 3):
            nodes[f"product_{k}"] = conv(f"product_{k}", product_b(k), transitions=[
                tool_tr(f"after_product_{k}", f"Product {k} is finished"),
                tool_tr("wrap_up", "End the product round early"),
            ] + transfers, on_enter={"type": "llm", "prompt": f"Start product {k} now as your task says. Do not call any tool in this message."},
                first_only=True, max_turns=20, cap_target=f"after_product_{k}")
            # tool-call transition names are transition_to_<node>; rename for the prompt
            nodes[f"product_{k}"]["task_message"] = nodes[f"product_{k}"]["task_message"].replace(
                "transition_to_next_product", f"transition_to_after_product_{k}")
            nxt = f"product_{k + 1}" if k < 3 else "wrap_up"
            trs = []
            if k < 3:
                trs.append({"target_node": nxt, "description": f"There is a product {k + 1}",
                            "condition": cond_or(gt("product_count", k))})
            trs.append(always("wrap_up"))
            nodes[f"after_product_{k}"] = {"name": f"after_product_{k}", "node_type": "conversation", "passthrough": True,
                                            "passthrough_default_transition": "wrap_up", "on_enter": {"type": "silent"},
                                            "task_message": "Say nothing. No tool call is allowed.",
                                            "disable_inactivity_monitor": True, "transitions": trs}
        nodes["wrap_up"] = conv("wrap_up", WRAP_B, tools=[promise_tool(baked_pid=False), note_tool()], transitions=[
            tool_tr("goodbye_promise", "At least one promise was recorded and all notes are done"),
            tool_tr("goodbye_paid", "No promise recorded and every product was noted paid"),
            tool_tr("goodbye_no_promise_refused", "No promise recorded; first non-paid note is refused"),
            tool_tr("goodbye_no_promise_hardship", "No promise recorded; first non-paid note is hardship"),
            tool_tr("goodbye_no_promise_dispute", "No promise recorded; first non-paid note is dispute"),
            tool_tr("goodbye_no_promise_service_error", "No promise recorded; first non-paid note is service_error"),
            tool_tr("transfer_restructuring", "The customer wants a new payment plan or lower instalments"),
            tool_tr("transfer_human", "The customer insisted on talking to a human"),
        ], on_enter={"type": "llm", "prompt": "Start step 1 of your task now (or step 4 if no product has an agreed PTP; then call add_note for the first product)."},
            first_only=True, max_turns=20, cap_target="goodbye_no_promise_refused")

    return {
        "initial_node": "setup",
        "system_prompt": SYSTEM,
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    }


def contract(slot: str) -> dict:
    return {
        "terminal_tools": [{"tool": "close_call", "evidence": [
            {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
            {"source": "briefs/brief-a-raw.md", "quote": "Every call ends with exactly one `close_call`, as the last tool call, with an outcome and, where the list gives one, a reason."},
        ]}],
        "every_call_ends_with_terminal": True,
    }


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for slot, multi in (("brief-a-raw", False), ("brief-b-raw", True)):
        (OUT / f"{slot}.workflow.json").write_text(json.dumps(build(slot, multi), indent=1))
        (OUT / f"{slot}.contract.json").write_text(json.dumps(contract(slot), indent=1))
        print("wrote", slot)
