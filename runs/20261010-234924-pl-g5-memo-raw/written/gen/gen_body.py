"""Generate out/pl-g5-memo-raw.body.json and out/pl-g5-memo-raw.closing.json."""
import json
from pathlib import Path

SLOT = "pl-g5-memo-raw"
BRIEF = f"briefs/{SLOT}.md"
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
HEADERS = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}


def api_tool(name, path, body_props, required, description, post=None, retries=0):
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BASE + path},
                "method": {"type": "string", "default": "POST"},
                "headers": HEADERS,
                "body": {"type": "object", "properties": body_props, "required": required},
            }},
        },
    }
    if post:
        t["post_process_code"] = post
    return t


CID = {"type": "string", "default": "{{customer_id}}"}


def hook(ok_text, fail_text, extra=""):
    """Post-hook that adds a what_to_do_next line to the result."""
    return (
        "try:\n"
        "    if isinstance(result, dict):\n"
        "        result.pop('header', None)\n"
        "        d = result.get('data')\n"
        "        if not isinstance(d, dict):\n"
        "            d = dict()\n"
        "            result['data'] = d\n"
        "        ok = d.get('ok') is True or str(d.get('ok')).lower() == 'true'\n"
        f"{extra}"
        f"        if 'what_to_do_next' not in d:\n"
        f"            d['what_to_do_next'] = {ok_text!r} if ok else {fail_text!r}\n"
        "except Exception:\n"
        "    pass\n"
    )


VERIFY_EXTRA = (
    "        hint = str(d.get('hint') or '')\n"
    "        ver = d.get('verified') is True or str(d.get('verified')).lower() == 'true'\n"
    "        allv = d.get('all_verified') is True or str(d.get('all_verified')).lower() == 'true'\n"
    "        left = d.get('wrong_answers_left')\n"
    "        if hint == 'day_month_swapped':\n"
    "            d['what_to_do_next'] = 'The day and the month look swapped. Ask the customer to say the month of their birth as a word, for example March. This retry does not count as a wrong answer.'\n"
    "        elif ok and allv:\n"
    "            d['what_to_do_next'] = 'Both answers are verified. Say only: Thank you, you are verified.'\n"
    "        elif ok and ver:\n"
    "            d['what_to_do_next'] = 'Correct. Now ask the second question: the last four digits of the phone number on file.'\n"
    "        elif ok and not ver:\n"
    "            d['what_to_do_next'] = 'This answer is wrong. Wrong answers left: ' + str(left) + '. Tell the customer the answer did not match and ask the same question again. Do not give hints.'\n"
    "        elif not ok and d.get('error'):\n"
    "            d['what_to_do_next'] = 'The answer could not be checked (' + str(d.get('error')) + '). It does not count as a wrong answer. Ask the customer to repeat the same answer clearly.'\n"
    "        elif not ok:\n"
    "            d['what_to_do_next'] = 'The check service failed and nothing was checked. Say there was a technical problem and ask for the same answer again.'\n"
)

verify_tool = api_tool(
    "verify_identity", "/verify_identity",
    {
        "customer_id": CID,
        "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                  "description": "Which question this answer is for. One of: date_of_birth, phone_last4."},
        "answer": {"type": "string", "default": "{{answer}}",
                   "description": "For date_of_birth: the date as YYYY-MM-DD, converted from what the customer said. A date given only as numbers is day, then month, then year. For phone_last4: exactly four digits."},
    },
    ["field", "answer"],
    "Check one security answer. CALL it every time the customer answers a security question, once per answer.",
    post=hook("", "", VERIFY_EXTRA),
)


def transfer_tool(name, queue, when):
    return api_tool(
        name, "/transfer_to_agent",
        {"customer_id": CID, "queue": {"type": "string", "enum": [queue], "default": queue}},
        [],
        f"Hand the call to a person in the {queue} team. CALL it {when}",
        post=hook("The transfer is done. Say nothing more.",
                  "The transfer failed. Tell the customer it did not work and call this tool once more."),
    )


T_GENERAL = transfer_tool("transfer_general", "general",
                          "only when the customer asked for a human, you asked once whether you can help first, and they still insist.")
T_RESTRUCT = transfer_tool("transfer_restructuring", "restructuring",
                           "when the customer asks for a new payment plan or lower instalments. Do not describe any plan.")
T_SUPPORT = transfer_tool("transfer_support", "support",
                          "when the customer mentioned illness, a death in the family or job loss, you offered the customer support team, and they accepted.")

callback_tool = api_tool(
    "schedule_callback", "/schedule_callback",
    {
        "customer_id": CID,
        "date": {"type": "string", "default": "{{date}}", "description": "Callback date as YYYY-MM-DD. Must be one of the allowed callback days."},
        "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24 hour, inside the allowed window."},
    },
    ["date", "time"],
    "Book a callback for the customer. CALL it as soon as the person names a day and time that are inside the allowed callback window.",
    post=hook("The callback is booked. Say nothing more.",
              "The callback was NOT booked. Do not say it is booked. Say there was a technical problem and call schedule_callback once more with the same values."),
)

promise_tool = api_tool(
    "create_promise", "/create_promise",
    {
        "customer_id": CID,
        "product_id": {"type": "string", "default": "{{product_id}}"},
        "amount": {"type": "number", "default": "{{amount}}", "description": "The confirmed amount, a number from the floor up to the full past-due amount."},
        "date": {"type": "string", "default": "{{date}}", "description": "The confirmed payment date as YYYY-MM-DD. Must be one of the allowed promise dates."},
    },
    ["amount", "date"],
    "Record the payment promise. CALL it only after you read back the product, amount and date, asked 'Do you confirm?' and the customer clearly said yes. Call it at most once per answer; after a failure call it once more.",
    post=hook("The promise is recorded.",
              "The promise was NOT recorded. Do not say it is recorded. Tell the customer it did not work and call create_promise once more right now with the same amount and date."),
)

SETUP_CODE = r'''import datetime
try:
    HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
    raw = str(vars.get('now') or '').strip()
    try:
        nowdt = datetime.datetime.strptime(raw[:16], '%Y-%m-%dT%H:%M')
    except Exception:
        nowdt = datetime.datetime.strptime(raw[:10], '%Y-%m-%d')
    today = nowdt.date()
    now_hm = nowdt.strftime('%H:%M')

    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL

    def nth_bd(n):
        d = today
        c = 0
        while c < n:
            d = d + datetime.timedelta(days=1)
            if isbd(d):
                c += 1
        return d

    def spoken(d):
        return d.strftime('%A') + ' ' + str(d.day) + ' ' + d.strftime('%B %Y')

    memo = today >= datetime.date(2026, 10, 9)
    late_n = 6 if memo else 7
    early_n = 12
    cb_start = '09:00' if memo else '10:00'
    cb_end = '17:00' if memo else '19:00'
    next_bd = nth_bd(1)
    vars['today_iso'] = today.isoformat()
    vars['today_spoken'] = spoken(today)
    vars['now_time'] = now_hm
    vars['deadline_early_iso'] = nth_bd(early_n).isoformat()
    vars['deadline_late_iso'] = nth_bd(late_n).isoformat()
    vars['cb_start'] = cb_start
    vars['cb_end'] = cb_end
    if now_hm < cb_end:
        first = cb_start if now_hm < cb_start else 'any time later than ' + now_hm
        today_line = 'Today, ' + spoken(today) + ' (' + today.isoformat() + '): from ' + first + ' up to ' + cb_end + ', both included.'
    else:
        today_line = 'Today is no longer possible: the window ended at ' + cb_end + '.'
    vars['callback_facts'] = ('Now: ' + spoken(today) + ', ' + now_hm + '.\n'
        + 'Allowed callback slots (nothing else can be booked):\n'
        + '- ' + today_line + '\n'
        + '- Next business day, ' + spoken(next_bd) + ' (' + next_bd.isoformat() + '): from ' + cb_start + ' up to ' + cb_end + ', both included.\n'
        + 'Any other day, or a time before ' + cb_start + ' or after ' + cb_end + ', is outside the window.')
    monday = today - datetime.timedelta(days=today.weekday())
    lines = []
    for k in range(0, 21):
        d = monday + datetime.timedelta(days=k)
        if d < today:
            continue
        if d.isoformat() in HOL:
            kind = 'Freya Bank holiday, not a business day'
        elif d.weekday() >= 5:
            kind = 'weekend, not a business day'
        else:
            kind = 'business day'
        if k < 7:
            label = 'this ' + d.strftime('%A')
        elif k < 14:
            label = 'next ' + d.strftime('%A')
        else:
            label = 'in two weeks'
        tag = ' (today)' if d == today else ''
        lines.append('- ' + d.isoformat() + ' ' + spoken(d) + tag + ': ' + kind + '; "' + label + '"')
    vars['calendar'] = '\n'.join(lines)
    sunday = monday + datetime.timedelta(days=6)
    d = sunday
    while not isbd(d):
        d = d - datetime.timedelta(days=1)
    if d <= today:
        d = sunday + datetime.timedelta(days=7)
        while not isbd(d):
            d = d - datetime.timedelta(days=1)
    vars['attempt1_iso'] = d.isoformat()
    vars['attempt1_spoken'] = spoken(d)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['setup_state'] = 'error'
    vars['callback_facts'] = 'Date facts unavailable.'
    vars['calendar'] = 'Date facts unavailable.'
'''

FACTS_CODE = r'''import datetime, json
try:
    HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']

    def as_list(v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                return None
        if isinstance(v, dict) and 'products' in v:
            v = as_list(v.get('products'))
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
        return None

    prods = None
    for key in ['products', 'account_response.data.products', 'get_account_response.data.products', 'account_response.data', 'get_account_response.data']:
        prods = as_list(vars.get(key))
        if prods:
            break
    if not prods:
        for prefix in ['products', 'account_response.data.products', 'get_account_response.data.products']:
            items = []
            i = 0
            while i < 10:
                kp = prefix + '.' + str(i) + '.'
                found = dict()
                for k in list(vars.keys()):
                    if str(k).startswith(kp):
                        found[str(k)[len(kp):]] = vars[k]
                if not found:
                    break
                items.append(found)
                i += 1
            if items:
                prods = items
                break
    if not prods:
        for k in list(vars.keys()):
            cand = as_list(vars[k])
            if cand and 'past_due' in cand[0]:
                prods = cand
                break
    p = prods[0]

    def num(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    def fmt(x):
        return str(int(x)) if float(x) == int(x) else ('%.2f' % x)

    ptype = str(p.get('type') or '')
    past_due = num(p.get('past_due'))
    days_late = int(num(p.get('days_late')))
    if ptype == 'credit_card':
        words = 'credit card ending ' + str(p.get('card_last4') or '')
        floor = num(p.get('minimum_payment'))
        floor_name = 'minimum payment'
    else:
        words = 'personal loan' if ptype == 'personal_loan' else 'car loan'
        floor = num(p.get('instalment_amount'))
        floor_name = 'instalment amount'
    late = days_late >= 8
    deadline = datetime.date.fromisoformat(str(vars.get('deadline_late_iso') if late else vars.get('deadline_early_iso')))
    today = datetime.date.fromisoformat(str(vars.get('today_iso')))

    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL

    def spoken(d):
        return d.strftime('%A') + ' ' + str(d.day) + ' ' + d.strftime('%B %Y')

    valid = []
    d = today
    while d <= deadline:
        if isbd(d):
            valid.append('- ' + d.isoformat() + ' ' + spoken(d) + (' (today)' if d == today else ''))
        d = d + datetime.timedelta(days=1)
    a1 = datetime.date.fromisoformat(str(vars.get('attempt1_iso')))
    if a1 > deadline:
        a1 = deadline
    vars['product_id'] = str(p.get('product_id') or '')
    vars['product_words'] = words
    vars['past_due_text'] = fmt(past_due)
    vars['floor_text'] = fmt(floor)
    vars['floor_name'] = floor_name
    vars['days_late_text'] = str(days_late)
    vars['deadline_iso'] = deadline.isoformat()
    vars['deadline_spoken'] = spoken(deadline)
    vars['valid_dates'] = '\n'.join(valid) if valid else '- none'
    vars['product_count'] = 1
    vars['attempts_allowed_1'] = 3 if late else 2
    vars['band_text'] = ('late band: ' + str(days_late) + ' days late, 2 persuasion attempts') if late else ('early band: ' + str(days_late) + ' days late, 1 persuasion attempt')
    vars['stage_1_1_text'] = ('No persuasion attempt is used yet. If you have not stated the debt yet, say you are calling from the collections team about a late payment on the '
        + words + ': ' + fmt(past_due) + ' past due, ' + str(days_late) + ' days late. Then ask exactly: "Can you make this payment today?"')
    vars['stage_1_2_text'] = ('The customer gave a flat refusal. Use persuasion attempt 1 now: propose paying the full past-due amount of ' + fmt(past_due)
        + ' (or the ' + floor_name + ' of ' + fmt(floor) + ' if the customer already said the full amount is too much) on ' + spoken(a1) + ' (' + a1.isoformat() + '). '
        + 'Do not ask about paying today again.'
        + ('' if late else ' This is the only persuasion attempt.'))
    vars['stage_1_3_text'] = ('The customer refused again. Use persuasion attempt 2, the last one: propose the ' + floor_name + ' of ' + fmt(floor)
        + ' on the deadline, ' + spoken(deadline) + ' (' + deadline.isoformat() + '). Say the rest stays overdue. Do not repeat any other offer the customer already refused.')
    vars['account_state'] = 'ok' if vars['product_id'] else 'missing'
except Exception as e:
    vars['account_state'] = 'missing'
    vars['product_count'] = 0
    vars['attempts_allowed_1'] = 0
'''

SYSTEM = """You are the digital assistant of Freya Bank, on an outbound phone call. Speak English. Keep every turn to one or two short sentences. Ask one question at a time.
Rules for the whole call:
- If asked whether you are a robot or an AI, say you are Freya Bank's digital assistant, then continue.
- If asked "Is this a scam?", say they can verify the call by phoning Freya Bank's customer service number, then continue.
- Until the current task says the identity is verified, never say why you are calling and never say the words collections, debt, payment, loan, card or the product.
- Never invent figures, dates, reasons or terms. If you cannot answer from the facts you were given, say you do not have that information.
- Never offer a discount, a waiver, an instalment plan or any term not given to you.
- Say an action is done only after its tool returned ok. If a tool result has what_to_do_next, follow it.
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- Do not name a currency; say amounts as numbers.
- Customer: {{title}} {{first_name}} {{last_name}}. Address them as {{title}} {{last_name}}."""


def xfer_close(tool, cid):
    return {"target_node": f"close:{cid}", "description": f"{tool} succeeded",
            "condition": {"logic": "or", "conditions": [{"variable": f"{tool}_success_count", "operator": "greater_than", "operand": 0}]}}


def tool_trans(cid, desc):
    return {"target_node": f"close:{cid}", "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def eq(var, *vals):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": v} for v in vals]}


def who_schema(name):
    return [{
        "name": name, "type": "string",
        "enum_values": ["confirmed", "someone_else", "wrong_number", "deceased", "unclear"],
        "description": ("Who answered, judged from the person's latest message only. "
                        "confirmed: they said yes, that's me, speaking, or gave the customer's own name. "
                        "someone_else: another person (a relative, a colleague) and the customer is not available or they are not the customer. "
                        "wrong_number: they say this number does not belong to the customer or they do not know the customer. "
                        "deceased: they say the customer has died. "
                        "unclear: anything else, such as hello, go ahead, who is this, a question, or no clear answer."),
        "min_confidence": 0.5,
    }]


def who_routes(name, unclear_target):
    return [
        {"target_node": "identity", "description": "the customer confirmed", "condition": eq(name, "confirmed")},
        {"target_node": "third_party", "description": "someone else answered", "condition": eq(name, "someone_else")},
        {"target_node": "close:not_reached/wrong_number", "description": "wrong number", "condition": eq(name, "wrong_number")},
        {"target_node": "close:not_reached/deceased", "description": "customer died", "condition": eq(name, "deceased")},
        {"target_node": unclear_target, "description": "still unclear", "condition": {"operator": "always"}},
    ]


nodes = {}

nodes["setup"] = {
    "name": "setup", "node_type": "code", "passthrough": True, "passthrough_default_transition": "opening",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                     "parameters": {"type": "object", "properties": {
                         "code": {"type": "string", "default": SETUP_CODE},
                         "timeout_ms": {"type": "number", "default": 10000}}}}}],
    "transitions": [{"target_node": "opening", "description": "always", "condition": {"operator": "always"}}],
}

nodes["opening"] = {
    "name": "opening", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": True,
    "task_message": "You asked whether you are speaking with {{title}} {{last_name}}. Do not call a tool in this turn. Say nothing about why you are calling.",
    "extraction_schema": who_schema("who_first"),
    "max_node_turns": 3, "max_turn_transition": "opening_retry",
    "transitions": who_routes("who_first", "opening_retry"),
}

nodes["opening_retry"] = {
    "name": "opening_retry", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "on_enter_first_entry_only": True,
    "task_message": ("The person on the line has not yet confirmed who they are. If they asked a question, answer it first in one short sentence "
                     "(robot or AI: you are Freya Bank's digital assistant; scam: they can verify the call by phoning Freya Bank's customer service number; "
                     "who is calling: a digital assistant from Freya Bank). Then ask once more: \"Am I speaking with {{title}} {{last_name}}?\" "
                     "Do not say why you are calling. Do not call a tool in this turn."),
    "extraction_schema": who_schema("who_second"),
    "max_node_turns": 3, "max_turn_transition": "close:not_reached/unclear",
    "transitions": who_routes("who_second", "close:not_reached/unclear"),
}

nodes["third_party"] = {
    "name": "third_party", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "on_enter_first_entry_only": True,
    "task_message": ("You are speaking with someone who is not {{title}} {{last_name}}. Do not say why you are calling and say nothing about any account, "
                     "even if they ask, offer to pay or offer to answer questions for the customer. Ask when {{title}} {{last_name}} can be reached.\n\n"
                     "{{callback_facts}}\n\n"
                     "Rules:\n"
                     "- When the person names a day and a time inside the allowed slots, call schedule_callback with the date (YYYY-MM-DD) and the time (HH:MM). "
                     "If they give only a day, ask for a time; if only a time, it means today if that slot is allowed, otherwise ask for the day.\n"
                     "- If the day or time is outside the allowed slots, say so, tell them the allowed window, and ask once for another time.\n"
                     "- If the second proposal is also outside the window, or they cannot give a time, do not book; call transition_to_close_no_callback.\n"
                     "- If they say the number does not belong to the customer, call the wrong number transition.\n"
                     "- If they say the customer has died, call the deceased transition at once, without saying anything else.\n"
                     "- If the customer themself comes to the phone, call the customer-on-the-line transition.\n"
                     "- When you call a closing transition, do not say goodbye yourself; the farewell is played automatically.\n"
                     "Use schedule_callback only as described."),
    "tools": [callback_tool],
    "max_node_turns": 8, "max_turn_transition": "close:not_reached/no_callback",
    "transitions": [
        xfer_close("schedule_callback", "not_reached/callback"),
        tool_trans("not_reached/no_callback", "The person proposed a callback time outside the allowed window twice, or cannot or will not give a time, so no callback is booked."),
        tool_trans("not_reached/wrong_number", "The person says this phone number does not belong to the customer."),
        tool_trans("not_reached/deceased", "The person says the customer has died."),
        {"target_node": "opening_retry", "description": "The customer themself has now come to the phone.", "is_tool_call": True,
         "condition": {"operator": "matches_intent", "description": "The customer themself has now come to the phone."}},
    ],
}

nodes["identity"] = {
    "name": "identity", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you. Before we continue, I need to ask two security questions. What is your date of birth?"},
    "on_enter_first_entry_only": True,
    "task_message": ("You are checking the customer's identity. You must not say why you are calling until both questions pass.\n"
                     "- Question 1: date of birth. Question 2: the last four digits of the phone number on file. One at a time, in that order.\n"
                     "- Every time the customer answers a question, call verify_identity with field date_of_birth or phone_last4. "
                     "Convert a date of birth to YYYY-MM-DD whatever way it was said. A date given only as numbers is day, then month, then year (05/03/1985 is 1985-03-05).\n"
                     "- Follow what_to_do_next in the result. A wrong answer may be asked again.\n"
                     "- If the customer does not want to answer, or asks what the call is about instead of answering, explain once that these questions protect their account, and ask again. "
                     "If they refuse again or ask again what the call is about, call transition_to_close_declined (do not say goodbye yourself).\n"
                     "- If they say twice that they do not want to talk, call transition_to_close_declined.\n"
                     "- If they ask for a human, ask once whether you can help first. If they insist, call transfer_general.\n"
                     "Use only the tools named here."),
    "tools": [verify_tool, T_GENERAL],
    "max_node_turns": 16, "max_turn_transition": "close:not_verified/declined",
    "transitions": [
        {"target_node": "account", "description": "both answers verified",
         "condition": eq("verify_identity_response.data.all_verified", "true", "True")},
        {"target_node": "close:not_verified/failed", "description": "no wrong answers left",
         "condition": eq("verify_identity_response.data.wrong_answers_left", "0")},
        xfer_close("transfer_general", "transferred/human"),
        tool_trans("not_verified/declined", "The customer refused the security questions a second time after the explanation, asked a second time what the call is about instead of answering, or said twice they do not want to talk."),
    ],
}

nodes["account"] = {
    "name": "account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "facts",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 2},
                     "function": {"name": "get_account", "handler": "__function__:api_call", "description": "Get the late products.",
                                  "parameters": {"type": "object", "properties": {
                                      "url": {"type": "string", "default": BASE + "/get_account"},
                                      "method": {"type": "string", "default": "POST"},
                                      "headers": HEADERS,
                                      "body": {"type": "object", "properties": {"customer_id": CID}, "required": []}}}}}],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "suppress_tool_results": True,
    "transitions": [{"target_node": "facts", "description": "always", "condition": {"operator": "always"}}],
}

nodes["facts"] = {
    "name": "facts", "node_type": "code", "passthrough": True, "passthrough_default_transition": "item:first",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                     "parameters": {"type": "object", "properties": {
                         "code": {"type": "string", "default": FACTS_CODE},
                         "timeout_ms": {"type": "number", "default": 10000}}}}}],
    "transitions": [
        {"target_node": "close:no_promise/service_error", "description": "account could not be read", "condition": eq("account_state", "missing")},
        {"target_node": "item:first", "description": "always", "condition": {"operator": "always"}},
    ],
}

NEGOTIATE_TASK = """The customer's identity is verified. Now handle the payment.

CURRENT STAGE: {{stage_{i}_{a}_text}}

Account facts:
- Product: {{product_words}} (product_id {{product_id}}). Past due: {{past_due_text}}. Days late: {{days_late_text}}. {{band_text}}.
- Floor ({{floor_name}}): {{floor_text}}. Full amount: {{past_due_text}}.
- Deadline: {{deadline_spoken}} ({{deadline_iso}}). Today: {{today_spoken}}.
Allowed promise dates (business days from today up to the deadline; no other date can be recorded):
{{valid_dates}}
Calendar:
{{calendar}}

Rules:
1. Ask for the full past-due amount first. Never ask how much they can pay; you propose every amount.
2. A date or amount the customer proposes is never a refusal. Accept an amount from {{floor_text}} up to {{past_due_text}}, both included. Below {{floor_text}}: say it cannot be recorded and offer the floor of {{floor_text}} once.
3. If the customer says the full amount is too much, offer the floor of {{floor_text}} once and say the rest stays overdue.
4. Dates: "next <weekday>" is that weekday in the following calendar week; "this <weekday>" is in the current week. Use the calendar. If they name a weekend day or a holiday not after the deadline, offer the next business day. If they name a date after the deadline, say the latest date you can record is {{deadline_spoken}} and offer it. If they give a vague period (next week, end of the month, when my salary comes), ask once for the exact day; if they still give none, propose the deadline.
5. When amount and date are agreed and valid, read back the product, the amount and the date and ask "Do you confirm?". Call create_promise only after a clear yes, with the amount and the date as YYYY-MM-DD. If they change the date or amount, check it again and read it back again.
6. Say the promise is recorded only after create_promise returns ok. If it fails, say so and call it once more.
7. If the customer mentions illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_support. If they decline, call transition_to_close_hardship. If they still name a date or amount themselves, record that promise under these rules.
8. "I already paid" (this past-due amount): say payments can take one business day to appear, take no promise, and call transition_to_close_paid.
9. "This debt is not mine", "I never had this product", or a claim that the product was closed or paid off in the past: do not argue, take no promise, call transition_to_close_dispute.
10. A request for a new payment plan or lower instalments: describe no plan, call transfer_restructuring.
11. A request for a human: ask once whether you can help first. If they insist, call transfer_general.
12. If the customer says twice that they do not want to talk, call transition_to_close_refused.
13. One promise only. A recorded promise cannot be changed or cancelled in this call; they can change it in the mobile app.
14. When you call a closing transition, do not say goodbye yourself; the farewell is played automatically.
When a rule says to call a tool, call it. One tool per message."""

refusal_desc = ("Judge ONLY the customer's latest message, as a reply to the agent's latest offer or question. "
                "yes: a flat refusal or a non-answer: they say no or will not pay, with no date, no amount and no counter-proposal; "
                "a no to paying today with no date and no amount; refusing the floor amount after the full amount was too much; refusing the deadline after asking for a later date. "
                "no: anything else, including proposing a date or an amount, saying the full amount is too much, accepting, asking a question, "
                "mentioning illness, a death in the family or job loss, saying they already paid, disputing the debt, asking for a plan or a human, or correcting a read-back.")

nodes["negotiate"] = {
    "name": "negotiate", "node_type": "conversation",
    "on_enter": {"type": "llm"},
    "task_message": NEGOTIATE_TASK,
    "tools": [promise_tool, T_RESTRUCT, T_SUPPORT, T_GENERAL],
    "extraction_schema": [{"name": "refused_{i}_{a}", "type": "string", "enum_values": ["yes", "no"],
                           "description": refusal_desc, "min_confidence": 0.6}],
    "max_node_turns": 14, "max_turn_transition": "close:no_promise/refused",
    "transitions": [
        {"target_node": "after_promise", "description": "promise recorded",
         "condition": {"logic": "or", "conditions": [{"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}]}},
        {"target_node": "close:no_promise/service_error", "description": "recording failed twice",
         "condition": {"logic": "or", "conditions": [{"variable": "create_promise_failure_count", "operator": "greater_than", "operand": 1}]}},
        xfer_close("transfer_restructuring", "transferred/restructuring"),
        xfer_close("transfer_support", "transferred/support"),
        xfer_close("transfer_general", "transferred/human"),
        tool_trans("paid", "The customer says they already paid this past-due amount."),
        tool_trans("no_promise/dispute", "The customer says the debt is not theirs, they never had this product, or the product was closed or paid off in the past."),
        tool_trans("no_promise/hardship", "The customer mentioned illness, a death in the family or job loss and declined the offer to connect with the customer support team, without naming a date or amount."),
        tool_trans("no_promise/refused", "The customer said for the second time that they do not want to talk."),
    ],
}

nodes["after_promise"] = {
    "name": "after_promise", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
    "on_enter_first_entry_only": True,
    "task_message": ("A promise is recorded. It cannot be changed or cancelled in this call; if asked, say they can change it in the mobile app. "
                     "If they ask for a new payment plan or lower instalments, call transfer_restructuring. If they ask for a human, ask once whether you can help; if they insist, call transfer_general. "
                     "If they mention illness, a death in the family or job loss and accept to be connected with customer support, call transfer_support. "
                     "Otherwise answer briefly and ask if there is anything else. Never invent information."),
    "tools": [T_RESTRUCT, T_SUPPORT, T_GENERAL],
    "extraction_schema": [{"name": "wrap_up", "type": "string", "enum_values": ["done", "more"],
                           "description": "done: the customer has nothing else, says no, thanks, goodbye or similar. more: they ask or say something that needs an answer.",
                           "min_confidence": 0.6}],
    "max_node_turns": 5, "max_turn_transition": "close:promise",
    "transitions": [
        xfer_close("transfer_restructuring", "transferred/restructuring"),
        xfer_close("transfer_support", "transferred/support"),
        xfer_close("transfer_general", "transferred/human"),
        {"target_node": "close:promise", "description": "nothing else", "condition": eq("wrap_up", "done")},
    ],
}

body = {"initial_node": "setup", "system_prompt": SYSTEM, "nodes": nodes, "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}


def ev(quote, source=BRIEF):
    return [{"source": source, "quote": quote}]


BYE = "Thank you for your time, {{title}} {{last_name}}. Goodbye."
closings = {
    "promise": {"set": {"outcome": "promise"}, "say": BYE, "evidence": ev("Outcome: promise; Reason: none; When: at least one promise was recorded")},
    "paid": {"set": {"outcome": "paid"}, "say": "Thank you for letting me know. Payments can take one business day to appear. " + BYE,
             "evidence": ev("take no promise, and close as `paid`.")},
    "transferred/restructuring": {"set": {"outcome": "transferred", "reason": "restructuring"}, "say": "I am connecting you now. Thank you, goodbye.",
                                  "evidence": ev("close as `transferred` / `restructuring`.")},
    "transferred/human": {"set": {"outcome": "transferred", "reason": "human"}, "say": "I am connecting you now. Thank you, goodbye.",
                          "evidence": ev("close as `transferred` / `human`.")},
    "transferred/support": {"set": {"outcome": "transferred", "reason": "support"}, "say": "I am connecting you now. Thank you, take care. Goodbye.",
                            "evidence": ev("close as `transferred` / `support`.")},
    "no_promise/refused": {"set": {"outcome": "no_promise", "reason": "refused"}, "say": "I understand. " + BYE,
                           "evidence": ev("Close as `no_promise` / `refused`.")},
    "no_promise/hardship": {"set": {"outcome": "no_promise", "reason": "hardship"}, "say": "I understand. Thank you for your time, and take care. Goodbye.",
                            "evidence": ev("If they decline, close as `no_promise` / `hardship`.")},
    "no_promise/dispute": {"set": {"outcome": "no_promise", "reason": "dispute"}, "say": "I understand. " + BYE,
                           "evidence": ev("Close as `no_promise` / `dispute`.")},
    "no_promise/service_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                 "say": "I am sorry, I could not record your promise because of a technical problem. " + BYE,
                                 "evidence": ev("say you could not record it and close as `no_promise` / `service_error`.")},
    "not_verified/failed": {"set": {"outcome": "not_verified", "reason": "failed"},
                            "say": "I am sorry, I cannot continue without verification. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye.",
                            "evidence": ev("Close as `not_verified` / `failed`.")},
    "not_verified/declined": {"set": {"outcome": "not_verified", "reason": "declined"}, "say": "I understand. Thank you for your time. Goodbye.",
                              "evidence": ev("close as `not_verified` / `declined`.")},
    "not_reached/callback": {"set": {"outcome": "not_reached", "reason": "callback"}, "say": "Thank you, we will call back then. Goodbye.",
                             "evidence": ev("then close as `not_reached` / `callback`.")},
    "not_reached/no_callback": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "say": "Thank you for your time. Goodbye.",
                                "evidence": ev("Close as `not_reached` / `no_callback`.")},
    "not_reached/wrong_number": {"set": {"outcome": "not_reached", "reason": "wrong_number"}, "say": "I apologise for the inconvenience. Thank you, goodbye.",
                                 "evidence": ev("close as `not_reached` / `wrong_number`.")},
    "not_reached/deceased": {"set": {"outcome": "not_reached", "reason": "deceased"}, "say": "I am sorry for your loss. Thank you for your time. Goodbye.",
                             "evidence": ev("close as `not_reached` / `deceased`.")},
    "not_reached/unclear": {"set": {"outcome": "not_reached", "reason": "unclear"}, "say": "Thank you for your time. Goodbye.",
                            "evidence": ev("close as `not_reached` / `unclear`.")},
}

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "It is the last tool call."}]},
    "fields": {"customer_id": "{{customer_id}}"},
    "closings": closings,
    "precedence": [
        {"closing": "promise", "when": [{"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}],
         "keep": ["transferred/restructuring", "transferred/human", "transferred/support"],
         "evidence": ev("Outcome: promise; Reason: none; When: at least one promise was recorded")
         + ev("If a transfer follows a recorded promise, close as `transferred` with that transfer's reason.")},
        {"closing": "not_verified/failed", "when": [{"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"}],
         "keep": [], "evidence": ev("After three wrong answers, do not state the debt.")},
    ],
    "ladder": {
        "template": "negotiate", "done": "close:no_promise/refused",
        "items": {"count": "product_count", "max": 1, "evidence": ev("1 to 45 days late on one product")},
        "attempts": {"allowed": "attempts_allowed_{i}", "max": 3,
                     "evidence": ev("Band: early; Deadline: the 12th business day after today; Persuasion attempts: 1")
                     + ev("A flat refusal or a non-answer uses one persuasion attempt.")
                     + ev("When the attempts are used up, stop.")},
        "refusal": "refused_{i}_{a}",
    },
}

Path(f"out/{SLOT}.body.json").write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
Path(f"out/{SLOT}.closing.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
print("written")
