"""Write out/<slot>.body.json and out/<slot>.closing.json for brief-a-raw (one product) and brief-b-raw (1-3 products).

Every rule here comes from briefs/brief-a-raw.md (Documents 1-4) and, for brief-b-raw only, briefs/brief-b-raw.md
(Documents 5-6). Tool URLs and fields come from tools/openapi.json.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = json.loads((ROOT / "tools/openapi.json").read_text())
SERVER = API["servers"][0]["url"]
A = "briefs/brief-a-raw.md"
B = "briefs/brief-b-raw.md"
OA = "tools/openapi.json"

# ------------------------------------------------------------------ calendar (CP-4 2.5 a as changed by OPS-2026-41 item 1)
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]

DATE_HELPERS = """import datetime, json, re
HOL = set(%s)
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def nth_bd(d, n):
    x = d
    c = 0
    while c < n:
        x = x + ONE
        if isbd(x):
            c += 1
    return x
def next_bd_from(d):
    x = d
    while not isbd(x):
        x = x + ONE
    return x
def say(d):
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MN[d.month - 1] + ' ' + str(d.year)
def full(d):
    return say(d) + ' (' + d.isoformat() + ')'
def last_bd_of_week(d):
    x = d + datetime.timedelta(days=4 - d.weekday())
    while not isbd(x):
        x = x - ONE
    return x
def parse_now():
    raw = str(vars.get('now') or '').strip()
    m = re.match(r'(\\d{4})-(\\d{2})-(\\d{2})(?:[T ](\\d{1,2}):(\\d{2}))?', raw)
    if m:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        hh = int(m.group(4)) if m.group(4) else 0
        mm = int(m.group(5)) if m.group(5) else 0
        return d, hh, mm
    t = datetime.datetime.utcnow()
    return t.date(), t.hour, t.minute
today, hh, mm = parse_now()
early_deadline = nth_bd(today, 12)
late_deadline = nth_bd(today, 7)
first_try = last_bd_of_week(today)
if first_try <= today:
    first_try = last_bd_of_week(today + datetime.timedelta(days=7))
""" % json.dumps(HOLIDAYS)

SETUP_CODE = DATE_HELPERS + """try:
    vars['today_iso'] = today.isoformat()
    vars['today_say'] = say(today)
    vars['now_time'] = '%02d:%02d' % (hh, mm)
    lines = []
    for k in range(0, 36):
        d = today + datetime.timedelta(days=k)
        tag = ' (today)' if k == 0 else ''
        if isbd(d):
            lines.append(d.isoformat() + ' ' + WD[d.weekday()] + tag + ': business day')
        else:
            why = 'bank holiday' if d.isoformat() in HOL else 'weekend'
            lines.append(d.isoformat() + ' ' + WD[d.weekday()] + tag + ': ' + why + ', NOT a business day; next business day is ' + full(next_bd_from(d)))
    vars['calendar_text'] = '\\n'.join(lines)
    monday = today - datetime.timedelta(days=today.weekday())
    wl = []
    for i in range(7):
        this_d = monday + datetime.timedelta(days=i)
        next_d = this_d + datetime.timedelta(days=7)
        note = ' (in the past, cannot be used)' if this_d < today else ''
        wl.append('"this ' + WD[i] + '" = ' + full(this_d) + note + '; "next ' + WD[i] + '" = ' + full(next_d))
    vars['weekday_text'] = '\\n'.join(wl)
    nbd = nth_bd(today, 1)
    cb = []
    if hh < 19:
        start = 'from 10:00' if (hh, mm) < (10, 0) else ('any time later than %02d:%02d' % (hh, mm))
        cb.append('Today, ' + full(today) + ': ' + start + ' up to 19:00 included.')
    else:
        cb.append('Today is no longer possible (it is after 19:00).')
    cb.append('Next business day, ' + full(nbd) + ': from 10:00 up to 19:00 included.')
    cb.append('Any other day, or any time before 10:00 or after 19:00, is outside the window.')
    vars['callback_text'] = ' '.join(cb)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['setup_state'] = 'error'
    vars['calendar_text'] = 'Calendar not available.'
"""

PREPARE_CODE_TMPL = DATE_HELPERS + """def money(x):
    try:
        return '%.2f' % float(x)
    except Exception:
        return str(x)
def as_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip().startswith('['):
        try:
            return json.loads(v)
        except Exception:
            try:
                import ast
                return ast.literal_eval(v)
            except Exception:
                return None
    return None
def find_products():
    for key in ('products', 'load_account_response.data.products', 'get_account_response.data.products'):
        got = as_list(vars.get(key))
        if got:
            return got
    found = dict()
    pat = re.compile(r'products[.\\[](\\d+)\\]?\\.(\\w+)$')
    for k, v in list(vars.items()):
        m = pat.search(str(k))
        if m and ('load_account' in str(k) or 'get_account' in str(k) or str(k).startswith('products')):
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = v
    return [found[i] for i in sorted(found)]
MULTI = __MULTI__
try:
    prods = [p for p in (find_products() or []) if isinstance(p, dict)]
    facts = []
    sentences = []
    n = 0
    for p in prods[:3]:
        n += 1
        kind = str(p.get('type') or '')
        if kind == 'credit_card':
            words = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        elif kind == 'car_loan':
            words = 'car loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        else:
            words = 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment'
        try:
            late = int(float(p.get('days_late')))
        except Exception:
            late = 0
        stage = 'early' if late <= 7 else 'late'
        deadline = early_deadline if stage == 'early' else late_deadline
        tries = 1 if stage == 'early' else 2
        past = money(p.get('past_due'))
        fl = money(floor)
        pid = str(p.get('product_id') or '')
        vars['p' + str(n) + '_id'] = pid
        vars['p' + str(n) + '_attempts'] = tries
        t = []
        t.append('PRODUCT ' + str(n) + ': ' + words + ' (product_id ' + pid + ').')
        t.append('  Past-due (full) amount: ' + past + '. Days late: ' + str(late) + ', ' + stage + ' stage.')
        t.append('  Floor (' + floor_name + '): ' + fl + '. Amounts from ' + fl + ' up to ' + past + ' (both included) can be recorded; below ' + fl + ' cannot.')
        t.append('  PTP deadline: ' + full(deadline) + '. A PTP date must be a business day from today up to this deadline.')
        t.append('  Persuasion attempts allowed: ' + str(tries) + '.')
        t.append('  Attempt 1: ' + past + ' (or the floor ' + fl + ' if the customer already said the full amount is too much) on ' + full(first_try) + '.')
        if tries == 2:
            t.append('  Attempt 2: the floor ' + fl + ' on the deadline ' + full(deadline) + '.')
        else:
            t.append('  There is no attempt 2 for this product (early stage).')
        facts.append('\\n'.join(t))
        if MULTI and len(prods) > 1:
            sentences.append('Your ' + words + ' has ' + past + ' past due and is ' + str(late) + ' days late.')
        else:
            sentences.append('I am calling from the collections team about a late payment on your ' + words + '. The past-due amount is ' + past + ' and it is ' + str(late) + ' days late.')
    vars['product_count'] = n
    vars['product_facts'] = '\\n\\n'.join(facts)
    if MULTI and n > 1:
        vars['account_statement'] = 'I am calling from the collections team about late payments on ' + str(n) + ' products. ' + ' '.join(sentences)
        vars['today_ask'] = 'Can you pay all of them today?'
    else:
        vars['account_statement'] = ' '.join(sentences)
        vars['today_ask'] = 'Can you make this payment today?'
    vars['prep_state'] = 'ok' if n > 0 else 'no_products'
except Exception as e:
    vars['prep_state'] = 'error'
"""

for code in (SETUP_CODE, PREPARE_CODE_TMPL):
    assert "{{" not in code and "}}" not in code


def code_node(name, code, nxt, transitions=None):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code},
                             "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": (transitions or []) + [{"target_node": nxt, "description": "always", "condition": {"operator": "always"}}],
    }


def api_tool(name, op, description, fields, required, retries=0, post=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(fields)
    tool = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": retries},
            "function": {"name": name, "handler": "__function__:api_call", "description": description,
                         "parameters": {"type": "object", "properties": {
                             "url": {"type": "string", "default": SERVER + "/" + op},
                             "method": {"type": "string", "default": "POST"},
                             "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                             "body": {"type": "object", "properties": props, "required": required}}}}}
    if post:
        tool["post_process_code"] = post
    return tool


POST_GENERIC = """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') in (False, 'false', 'False'):
            d['what_to_do_next'] = 'This action FAILED and was NOT carried out. Tell the customer it did not work. Never say it was done.'
        elif not isinstance(d, dict):
            result['what_to_do_next'] = 'This action FAILED and was NOT carried out. Tell the customer it did not work. Never say it was done.'
except Exception:
    pass
"""

POST_VERIFY = """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if not isinstance(d, dict):
            result['what_to_do_next'] = 'The check did not work and nothing was counted. Ask the customer to repeat the same answer, then call verify_identity again.'
        elif d.get('all_verified') in (True, 'true', 'True'):
            d['what_to_do_next'] = 'Both answers are verified.'
        elif d.get('hint') == 'day_month_swapped':
            d['what_to_do_next'] = 'Not counted as a wrong answer: the day and the month look swapped. Ask the customer to say the month of birth as a word, then call verify_identity again.'
        elif str(d.get('wrong_answers_left')) == '0':
            d['what_to_do_next'] = 'Three wrong answers: the check has ended. Do not state anything about the account.'
        elif d.get('ok') in (False, 'false', 'False'):
            d['what_to_do_next'] = 'The answer could not be read and is not counted. Ask the customer to say it again, then call verify_identity again.'
        elif d.get('verified') in (True, 'true', 'True'):
            d['what_to_do_next'] = 'This answer is correct. If the last four digits of the phone number have not been checked yet, ask for them now.'
        else:
            d['what_to_do_next'] = 'This answer is wrong. Do not reveal the right answer. Ask the same question again.'
except Exception:
    pass
"""

POST_PROMISE = """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict) and d.get('ok') in (True, 'true', 'True'):
            d['what_to_do_next'] = 'This promise IS recorded.'
        else:
            msg = 'This promise was NOT recorded. If this is the first failure for this product, call create_promise once more now with the same values, without asking the customer. If it has now failed twice for this product, tell the customer you could not record this promise. Never say it is recorded.'
            if isinstance(d, dict):
                d['what_to_do_next'] = msg
            else:
                result['what_to_do_next'] = msg
except Exception:
    pass
"""


def verify_tool():
    return api_tool("verify_identity", "verify_identity",
                    "Check one security answer. CALL it every time the customer gives an answer to a security question, one answer per call.",
                    {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                               "description": "Which question was answered. One of: date_of_birth, phone_last4."},
                     "answer": {"type": "string", "default": "{{answer}}",
                                "description": "date_of_birth as YYYY-MM-DD (convert from words; numbers only means day, month, year). phone_last4 as four digits."}},
                    ["field", "answer"], post=POST_VERIFY)


def transfer_tool(name, queue, when):
    return api_tool(name, "transfer_to_agent", when,
                    {"queue": {"type": "string", "enum": [queue], "default": queue}}, ["queue"])


def promise_tool():
    return api_tool("create_promise", "create_promise",
                    "Record one payment promise (PTP) for one product. CALL it only after you read the PTP back and the customer clearly said yes.",
                    {"product_id": {"type": "string", "default": "{{product_id}}", "description": "The product_id from the account facts, copied exactly (for example p1)."},
                     "amount": {"type": "number", "default": "{{amount}}", "description": "The confirmed amount, a number."},
                     "date": {"type": "string", "default": "{{date}}", "description": "The confirmed payment date as YYYY-MM-DD."}},
                    ["product_id", "amount", "date"], post=POST_PROMISE)


def note_tool():
    return api_tool("add_note", "add_note",
                    "Record why one product ended without a promise. CALL it once for every product that ends without a PTP, except when the call is transferred.",
                    {"product_id": {"type": "string", "default": "{{note_product_id}}", "description": "The product_id from the account facts, copied exactly."},
                     "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "default": "{{note_reason}}",
                                "description": "One of: refused, hardship, dispute, paid, service_error."}},
                    ["product_id", "reason"])


def callback_tool():
    return api_tool("schedule_callback", "schedule_callback",
                    "Book a callback for the customer. CALL it only for a day and time inside the allowed callback window.",
                    {"date": {"type": "string", "default": "{{callback_date}}", "description": "Callback date as YYYY-MM-DD."},
                     "time": {"type": "string", "default": "{{callback_time}}", "description": "Callback time as HH:MM, 24 hour."}},
                    ["date", "time"])


def when_all(*checks):
    return {"logic": "or", "conditions": [checks[0] if len(checks) == 1 else {"logic": "and", "conditions": list(checks)}]}


def var(v, op, operand=None):
    c = {"variable": v, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return c


def is_true(v):
    return {"logic": "or", "conditions": [var(v, "equals", "true"), var(v, "equals", "True")]}


def ok_count(tool):
    return when_all(var(tool + "_success_count", "greater_than", 0))


def tool_t(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def det(target, desc, cond):
    return {"target_node": target, "description": desc, "condition": cond}


def stay(node):
    return {"target_node": node, "description": "keep going", "condition": {"operator": "always"}}


TOOL_RULES = ("Tool rules: when a rule says to call a tool, call it; saying it is not enough. Call one tool per message. "
              "After every tool result, speak to the customer or call the next tool; never end a turn with nothing. "
              "Read what_to_do_next in a tool result and follow it.")

HUMAN_RULE = ("If the customer asks for a human or a person: the first time, ask once whether you can help them first. "
              "If they insist, call transfer_general.")


def system_prompt(multi):
    s = (
        "You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is fictional and all data is synthetic. Speak English. "
        "Keep every turn to one or two short sentences. Address the customer as {{title}} {{last_name}}.\n"
        "Call facts: customer {{first_name}} {{last_name}} ({{title}}). Current date and time: {{now}}. All dates work from this value, never from a real clock.\n"
        "Rules for the whole call:\n"
        "- Never improvise. Never offer a discount, a waiver, an instalment plan or any term the bank's policy does not give you.\n"
        "- If asked something you have no tool or fact for, say you do not have that information. Never invent figures, dates or reasons.\n"
        "- If asked whether this is a scam: say they can verify the call by phoning Freya Bank's customer service number, then go on.\n"
        "- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then go on.\n"
        "- Never say something is recorded, booked or transferred unless the tool result shows it worked. If a tool fails, say so.\n"
        "- Before identity is verified, never say collections, debt, payment, amount or the product, to anyone.\n"
        "- When a call ends, thank the customer and say goodbye.\n"
        "- Write only the words you say on the phone. No lists, no markdown, no stage directions.\n"
    )
    return s


OPENING_LINE = "Hello, this is Freya Bank's digital assistant calling, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"


def build(multi):
    nodes = {}
    sources = [A] + ([B] if multi else [])

    nodes["setup"] = code_node("setup", SETUP_CODE, "opening")

    # ------------------------------------------------------------ opening (CP-4 2.1, 2.2 d-e, 2.8 d, 2.8 g)
    nodes["opening"] = {
        "name": "opening", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": OPENING_LINE}, "on_enter_first_entry_only": True,
        "task_message": (
            "You have said that you are Freya Bank's digital assistant, that the call is recorded, and asked: \"Am I speaking with {{title}} {{last_name}}?\"\n"
            "Your only job here is to learn who answered. Do not say why you are calling.\n"
            "- Only \"yes\", \"that's me\", \"speaking\" or the customer's own name confirm. \"Hello\", \"go ahead\" and \"who is this\" do not confirm: then ask once more, \"Am I speaking with {{title}} {{last_name}}?\".\n"
            "- If they ask whether this is a scam or a robot, answer it in one sentence and ask again; that ask counts as your second ask.\n"
            "- If it is still unclear after your second ask, thank them, say goodbye and call transition_to_close_unclear.\n"
            "- If they say twice that they do not want to talk, thank them, say goodbye and call transition_to_close_declined.\n"
            "- " + HUMAN_RULE + "\n" + TOOL_RULES),
        "tools": [transfer_tool("transfer_general", "general", "Transfer the call to a person, queue general. CALL it only when the customer insists on a human after you asked once whether you can help.")],
        "extraction_schema": [{
            "name": "who_answered", "type": "string",
            "enum_values": ["confirmed", "someone_else", "wrong_number", "deceased", "unclear"],
            "description": ("Who answered, from the latest answer. confirmed: they said yes, that's me, speaking, or the customer's name. "
                            "someone_else: they said they are not the customer but know them (a relative, partner, colleague), or the customer is not available. "
                            "wrong_number: they said this number does not belong to that person or they do not know them. "
                            "deceased: they said the customer has died. unclear: anything else, such as hello, go ahead, who is this, or a question."),
            "min_confidence": 0.7}],
        "max_node_turns": 8, "max_turn_transition": "close:unclear",
        "transitions": [
            det("close:deceased", "the customer has died", when_all(var("who_answered", "equals", "deceased"))),
            det("close:wrong_number", "wrong number", when_all(var("who_answered", "equals", "wrong_number"))),
            det("security", "the customer confirmed", when_all(var("who_answered", "equals", "confirmed"))),
            det("third_party", "someone else answered", when_all(var("who_answered", "equals", "someone_else"))),
            det("close:human", "transferred to a person", ok_count("transfer_general")),
            tool_t("close:unclear", "Still unclear who answered after the second ask, and you said goodbye."),
            tool_t("close:declined", "The person said twice they do not want to talk, and you said goodbye."),
            stay("opening"),
        ],
    }

    # ------------------------------------------------------------ third party (CP-4 2.2, memo item 2)
    nodes["third_party"] = {
        "name": "third_party", "node_type": "conversation",
        "task_message": (
            "Someone other than {{title}} {{last_name}} answered. Say nothing about why you are calling, nothing about any account, and do not ask security questions. "
            "If they offer to pay or ask what it is about, say you can only speak with {{title}} {{last_name}}.\n"
            "Ask when {{title}} {{last_name}} can be reached.\n"
            "Allowed callback window: {{callback_text}}\n"
            "- If they give a day and time inside the window, call schedule_callback with the date (YYYY-MM-DD) and time (HH:MM). Do not say it is booked until the tool result shows ok true.\n"
            "- If they give only a vague time such as \"this afternoon\", ask for an exact time.\n"
            "- If the first day or time they give is outside the window, say so and ask once for another time inside it. If the second one is also outside, or they cannot give one, book nothing: thank them, say goodbye and call transition_to_close_no_callback.\n"
            "- If they say this number does not belong to that person, thank them, say goodbye and call transition_to_close_wrong_number.\n"
            "- If they say the customer has died, call transition_to_close_deceased at once, saying nothing yourself.\n"
            + TOOL_RULES),
        "tools": [callback_tool()],
        "extraction_schema": [{
            "name": "third_party_news", "type": "string", "enum_values": ["deceased", "wrong_number", "none"],
            "description": "deceased: the latest message says the customer has died. wrong_number: it says this number does not belong to the customer. none: anything else.",
            "min_confidence": 0.8}],
        "max_node_turns": 10, "max_turn_transition": "close:no_callback",
        "transitions": [
            det("close:deceased", "the customer has died", when_all(var("third_party_news", "equals", "deceased"))),
            det("close:callback", "callback booked", {"logic": "or", "conditions": [
                var("schedule_callback_response.data.ok", "equals", "true"), var("schedule_callback_response.data.ok", "equals", "True")]}),
            tool_t("close:no_callback", "No callback time inside the window after asking once more, and you said goodbye."),
            tool_t("close:wrong_number", "The number does not belong to the customer, and you said goodbye."),
            tool_t("close:deceased", "The person said the customer has died."),
            stay("third_party"),
        ],
    }

    # ------------------------------------------------------------ security (CP-4 2.3)
    nodes["security"] = {
        "name": "security", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you. Before we go on, I need to ask you two security questions. What is your date of birth?"},
        "on_enter_first_entry_only": True,
        "task_message": (
            "Verify the customer's identity with two questions, one at a time: first the date of birth, then the last four digits of the phone number on file. "
            "You do not know why the bank is calling yet; say nothing about any account, debt or payment.\n"
            "- Call verify_identity for every answer. For the date of birth send YYYY-MM-DD whatever way they said it; a date said only in numbers is day, then month, then year (\"05/03/1988\" is 1988-03-05). For the phone send four digits.\n"
            "- If the result says the day and month look swapped, ask them to say the month as a word. That retry is not a wrong answer.\n"
            "- A wrong answer may be asked again. Never reveal a right answer.\n"
            "- If the customer does not want to answer, or asks what the call is about instead of answering: the first time, explain once that the questions protect their account and ask again. "
            "If they refuse a second time or ask a second such question, thank them, say goodbye and call transition_to_close_declined.\n"
            "- If they say twice they do not want to talk, thank them, say goodbye and call transition_to_close_declined.\n"
            "- " + HUMAN_RULE + "\n" + TOOL_RULES),
        "tools": [verify_tool(), transfer_tool("transfer_general", "general", "Transfer the call to a person, queue general. CALL it only when the customer insists on a human after you asked once whether you can help.")],
        "max_node_turns": 16, "max_turn_transition": "close:declined",
        "transitions": [
            det("load_account", "both answers verified", is_true("verify_identity_response.data.all_verified")),
            det("close:failed", "three wrong answers", when_all(var("verify_identity_response.data.wrong_answers_left", "equals", "0"))),
            det("close:human", "transferred to a person", ok_count("transfer_general")),
            tool_t("close:declined", "The customer refused the security questions a second time, or asked a second time what the call is about instead of answering, and you said goodbye."),
            stay("security"),
        ],
    }

    # ------------------------------------------------------------ account (CP-4 2.4 a)
    nodes["load_account"] = {
        "name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 2},
                         "function": {"name": "get_account", "handler": "__function__:api_call", "description": "Get the late products.",
                                      "parameters": {"type": "object", "properties": {
                                          "url": {"type": "string", "default": SERVER + "/get_account"},
                                          "method": {"type": "string", "default": "POST"},
                                          "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                                          "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}}, "required": ["customer_id"]}}}}}],
        "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [{"target_node": "prepare", "description": "always", "condition": {"operator": "always"}}],
    }
    nodes["prepare"] = code_node("prepare", PREPARE_CODE_TMPL.replace("__MULTI__", "True" if multi else "False"), "collect_fallback", [
        det("collect", "facts ready", when_all(var("prep_state", "equals", "ok"))),
        det("close:account_error", "no products came back", when_all(var("prep_state", "equals", "no_products"))),
    ])

    # ------------------------------------------------------------ collect (CP-4 2.4 b - 2.8; CN-12 for multi)
    facts_block = (
        "ACCOUNT FACTS (worked out by the bank's systems from get_account and the policy; use these values and never compute your own):\n{{product_facts}}\n\n"
        "DATE FACTS: Today is {{today_say}} ({{today_iso}}), time {{now_time}}.\nCalendar from today:\n{{calendar_text}}\n"
        "Weekday words:\n{{weekday_text}}\n")
    fallback_facts = (
        "ACCOUNT FACTS: read the products from the get_account result in the conversation (product_id, type, card_last4, past_due, days_late, minimum_payment for cards, instalment_amount for loans). "
        "Business days are Monday to Friday except the bank holidays " + ", ".join(HOLIDAYS) + ". "
        "Days late 1-7: early stage, PTP deadline the 12th business day after today, 1 persuasion attempt. Days late 8-45: late stage, deadline the 7th business day after today, 2 attempts. "
        "The floor is minimum_payment for a credit card and instalment_amount for a loan. Today is the date in {{now}}.\n")

    date_rules = (
        "PTP DATE RULES:\n"
        "- A PTP date must be today or later, a business day (see the calendar), and not after that product's deadline.\n"
        "- A weekend day or bank holiday that is not after the deadline: offer the next business day shown in the calendar.\n"
        "- \"next <weekday>\" means that weekday in the following calendar week; \"this <weekday>\" means the one in the current week. Use the weekday words list.\n"
        "- A vague period (\"next week\", \"end of the month\", \"when my salary comes\"): ask once for the exact day. If they still name none, propose the deadline.\n"
        "- A date after the deadline: say the latest date you can record is the deadline and offer it. Refusing the deadline is a flat refusal.\n"
        "PTP AMOUNT RULES:\n"
        "- Ask for the full past-due amount first. Never ask \"how much can you pay?\"; you propose every amount yourself.\n"
        "- If they say the full amount is too much, offer the floor once and say that the rest stays overdue. Refusing the floor is a flat refusal.\n"
        "- An amount they propose from the floor up to the full amount (both included) is accepted. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept, that is a flat refusal.\n"
        "- A date or amount the customer proposes is never a refusal; check it with these rules. If they give a date but no amount, propose the full amount on that date. If they give an amount but no date, ask on which day.\n"
        "PERSUASION:\n"
        "- \"No\" to paying today, with no date and no amount, is a flat refusal. A flat refusal or a non-answer uses one persuasion attempt.\n"
        "- On the first flat refusal make attempt 1 as written in the facts. On the second flat refusal, make attempt 2 only if the product has one (late stage). When a flat refusal comes and no attempt is left, stop: never repeat an offer they already refused.\n"
        "- Illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. "
        "If they accept, call transfer_support. If they decline, end as hardship. If they still name a date or an amount themselves, take the PTP under these rules.\n")

    other_rules_common = (
        "OTHER REQUESTS:\n"
        "- A new payment plan or lower instalments: describe no plan, say you will connect them with the team that handles this, and call transfer_restructuring.\n"
        "- " + HUMAN_RULE + "\n"
        "- A recorded PTP cannot be changed or cancelled in this call; they can change it in the mobile app.\n")

    if not multi:
        task = (
            "The customer is verified. You told them what is overdue and asked \"Can you make this payment today?\". Get a payment promise (PTP) under the rules below, record it, or end the call the right way.\n\n"
            + TOOL_RULES + "\n\n" + "{FACTS}" + "\n" + date_rules +
            "CONFIRMING AND RECORDING:\n"
            "- When an amount and a date pass the rules, read back the product in words, the amount and the date, and ask \"Do you confirm?\". If they change the date or amount, check it again and read it back again.\n"
            "- Only after a clear yes, call create_promise with the product_id, the amount and the date (YYYY-MM-DD).\n"
            "- If create_promise fails, call it once more with the same values. If it fails again, say you could not record the promise and call transition_to_close_service_error.\n"
            "- Never say the promise is recorded yourself; the system confirms it when the tool result shows ok true.\n"
            + other_rules_common +
            "ENDINGS (call the transition only after any bank tool call you needed is done; say a short thank you first):\n"
            "- Attempts used up, or they said twice they do not want to talk: transition_to_close_refused.\n"
            "- Hardship and they declined the support team, with no PTP: transition_to_close_hardship.\n"
            "- \"This debt is not mine\", \"I never had this product\", or the product was closed or paid off in the past: do not argue, take no PTP, transition_to_close_dispute.\n"
            "- \"I already paid\" this past-due amount: take no PTP, transition_to_close_paid.\n")
        tools = [promise_tool(),
                 transfer_tool("transfer_restructuring", "restructuring", "Transfer the call, queue restructuring. CALL it when the customer asks for a new payment plan or lower instalments."),
                 transfer_tool("transfer_support", "support", "Transfer the call, queue support. CALL it when a customer with illness, a death in the family or job loss accepts the support team."),
                 transfer_tool("transfer_general", "general", "Transfer the call to a person, queue general. CALL it only when the customer insists on a human after you asked once whether you can help.")]
        transitions = [
            det("promise_done", "the promise is recorded", is_true("create_promise_response.data.ok")),
            det("close:service_error", "create_promise failed twice", when_all(var("create_promise_failure_count", "greater_than", 1))),
            det("close:restructuring", "transferred to restructuring", ok_count("transfer_restructuring")),
            det("close:support", "transferred to support", ok_count("transfer_support")),
            det("close:human", "transferred to a person", ok_count("transfer_general")),
            tool_t("close:refused", "Persuasion attempts are used up, or the customer said twice they do not want to talk. You thanked them."),
            tool_t("close:hardship", "The customer has hardship (illness, a death in the family, job loss), declined the support team and gave no PTP."),
            tool_t("close:dispute", "The customer says the debt is not theirs, never had the product, or the product was closed or paid off in the past."),
            tool_t("close:paid", "The customer says they already paid this past-due amount."),
            tool_t("close:service_error", "create_promise failed twice and you told the customer the promise could not be recorded."),
        ]
    else:
        task = (
            "The customer is verified. You told them every late product and asked whether they can pay (all of) it today. Get payment promises (PTPs) under the rules below, record them, note the rest, and end the call the right way.\n\n"
            + TOOL_RULES + "\n\n" + "{FACTS}" + "\n"
            "SEVERAL PRODUCTS (when there is more than one product):\n"
            "- Each product has its own past-due amount, floor, stage, deadline and persuasion attempts; count attempts separately per product.\n"
            "- If they cannot pay everything today, take the products one at a time in the order of the facts. Do not ask about today again for each product. Every product starts at its own attempt 1 on its first flat refusal.\n"
            "- If they name one date for everything and it is after one product's deadline, that product gets its own deadline and the read-back says so; the others keep the date they named.\n"
            "- A dispute or an \"I already paid\" about one product does not end the call: remember it for that product and go on with the others.\n"
            "- A promise for one product and a refusal for another is fine.\n\n"
            + date_rules +
            "CONFIRMING AND RECORDING:\n"
            "- When every product is settled (a PTP agreed, refused, disputed, paid or hardship), read back all agreed PTPs together (product in words, amount, date) and ask once \"Do you confirm?\". If they change something, check it and read back again.\n"
            "- After a clear yes, call create_promise once for each agreed product, one call per message, in the order of the facts. If a call fails, call it once more for that product. If it fails again, tell the customer that this promise could not be recorded; that product then ends without a PTP, reason service_error. PTPs already recorded stay.\n"
            "- Say a PTP is recorded only after its tool result shows ok true. After recording, say: \"You will receive a text message confirming this promise.\"\n"
            "- Then, for every product that ended without a PTP, call add_note with that product_id and one reason: refused, hardship, dispute, paid or service_error. Do this even when no product got a PTP.\n"
            "- Never call add_note when the call is transferred, neither before nor after the transfer.\n"
            + other_rules_common +
            "- A request for a new plan or lower instalments transfers the call at once: PTPs already recorded stay, PTPs agreed but not yet recorded are not recorded.\n"
            "ENDINGS (call the transition only after every create_promise and add_note call is done; thank the customer first):\n"
            "- At least one PTP recorded: transition_to_close_promise.\n"
            "- No PTP recorded and every product noted paid: transition_to_close_paid.\n"
            "- No PTP recorded otherwise: take the first product, in the order of the facts, whose note is not paid, and use its reason: "
            "refused -> transition_to_close_refused, hardship -> transition_to_close_hardship, dispute -> transition_to_close_dispute, service_error -> transition_to_close_service_error.\n"
            "- If they say twice they do not want to talk, the products without a PTP end as refused (note them first).\n")
        tools = [promise_tool(), note_tool(),
                 transfer_tool("transfer_restructuring", "restructuring", "Transfer the call, queue restructuring. CALL it when the customer asks for a new payment plan or lower instalments."),
                 transfer_tool("transfer_support", "support", "Transfer the call, queue support. CALL it when a customer with illness, a death in the family or job loss accepts the support team."),
                 transfer_tool("transfer_general", "general", "Transfer the call to a person, queue general. CALL it only when the customer insists on a human after you asked once whether you can help.")]
        transitions = [
            det("close:restructuring", "transferred to restructuring", ok_count("transfer_restructuring")),
            det("close:support", "transferred to support", ok_count("transfer_support")),
            det("close:human", "transferred to a person", ok_count("transfer_general")),
            tool_t("close:promise", "At least one PTP is recorded, every create_promise and add_note call is done, and you thanked the customer."),
            tool_t("close:paid", "No PTP recorded, every product was noted paid with add_note, and you thanked the customer."),
            tool_t("close:refused", "No PTP recorded, all notes are added, and the first product (in order) not noted paid was noted refused."),
            tool_t("close:hardship", "No PTP recorded, all notes are added, and the first product (in order) not noted paid was noted hardship."),
            tool_t("close:dispute", "No PTP recorded, all notes are added, and the first product (in order) not noted paid was noted dispute."),
            tool_t("close:service_error", "No PTP recorded, all notes are added, and the first product (in order) not noted paid was noted service_error."),
        ]

    collect = {
        "name": "collect", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you, {{title}} {{last_name}}, you are verified. {{account_statement}} {{today_ask}}"},
        "on_enter_first_entry_only": True,
        "task_message": task.replace("{FACTS}", facts_block),
        "tools": tools,
        "max_node_turns": 45, "max_turn_transition": "close:refused",
        "transitions": transitions + [stay("collect")],
    }
    nodes["collect"] = collect
    fb = json.loads(json.dumps(collect))
    fb["name"] = "collect_fallback"
    fb["on_enter"] = {"type": "llm", "prompt": "Thank the customer for verifying. Say you are calling from the collections team about a late payment, name every late product in words (credit card ending in its last four digits, personal loan or car loan) with its past-due amount and days late, one sentence per product. Then ask \"Can you make this payment today?\" (with several products: \"Can you pay all of them today?\")."}
    fb["task_message"] = task.replace("{FACTS}", fallback_facts)
    fb["transitions"] = [dict(t, target_node=("collect_fallback" if t["target_node"] == "collect" else t["target_node"])) for t in fb["transitions"]]
    nodes["collect_fallback"] = fb

    if not multi:
        nodes["promise_done"] = {
            "name": "promise_done", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": "Thank you. Your payment promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
            "on_enter_first_entry_only": True,
            "task_message": (
                "The payment promise is recorded. Answer any last question briefly.\n"
                "- The promise cannot be changed or cancelled in this call; they can change it in the mobile app.\n"
                "- A new payment plan or lower instalments: describe no plan and call transfer_restructuring.\n"
                "- " + HUMAN_RULE + "\n"
                "- When they have nothing else, call transition_to_close_promise.\n" + TOOL_RULES),
            "tools": [transfer_tool("transfer_restructuring", "restructuring", "Transfer the call, queue restructuring. CALL it when the customer asks for a new payment plan or lower instalments."),
                      transfer_tool("transfer_general", "general", "Transfer the call to a person, queue general. CALL it only when the customer insists on a human after you asked once whether you can help.")],
            "max_node_turns": 8, "max_turn_transition": "close:promise",
            "transitions": [
                det("close:restructuring", "transferred to restructuring", ok_count("transfer_restructuring")),
                det("close:human", "transferred to a person", ok_count("transfer_general")),
                tool_t("close:promise", "The customer has nothing else to ask."),
                stay("promise_done"),
            ],
        }

    body = {"initial_node": "setup", "system_prompt": system_prompt(multi), "nodes": nodes, "global_nodes": {},
            "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}
    return body


# ------------------------------------------------------------------ closing plans (Document 4, CN-12 E)
BYE = "Thank you for your time, {{title}} {{last_name}}. Goodbye."
CODE_ROW = {
    "promise": ("promise", None, "| `promise` | (none) | at least one PTP was recorded |"),
    "paid": ("paid", None, "| `paid` | (none) | the customer already paid (CP-4 2.8 e) |"),
    "restructuring": ("transferred", "restructuring", "| `transferred` | `restructuring` | new plan or lower instalments (2.8 c) |"),
    "human": ("transferred", "human", "| `transferred` | `human` | the customer insisted on a person (2.8 d) |"),
    "support": ("transferred", "support", "| `transferred` | `support` | hardship, customer accepted the support team (2.7 d) |"),
    "refused": ("no_promise", "refused", "| `no_promise` | `refused` | attempts used up, or said twice they do not want to talk (2.7 c, 2.8 g) |"),
    "hardship": ("no_promise", "hardship", "| `no_promise` | `hardship` | hardship, customer declined the support team (2.7 d) |"),
    "dispute": ("no_promise", "dispute", "| `no_promise` | `dispute` | not mine, never had it, closed or paid off in the past (2.8 f) |"),
    "service_error": ("no_promise", "service_error", "| `no_promise` | `service_error` | `create_promise` failed twice (2.8 b) |"),
    "account_error": ("no_promise", "service_error", "| `no_promise` | `service_error` | `create_promise` failed twice (2.8 b) |"),
    "failed": ("not_verified", "failed", "| `not_verified` | `failed` | three wrong security answers (2.3 d) |"),
    "declined": ("not_verified", "declined", "| `not_verified` | `declined` | refused the security questions, or did not want to talk before verification (2.3 e, 2.8 g) |"),
    "callback": ("not_reached", "callback", "| `not_reached` | `callback` | callback booked (2.2 b, memo item 2) |"),
    "no_callback": ("not_reached", "no_callback", "| `not_reached` | `no_callback` | no time inside the window (2.2 c) |"),
    "wrong_number": ("not_reached", "wrong_number", "| `not_reached` | `wrong_number` | the number is not the customer's (2.2 d) |"),
    "deceased": ("not_reached", "deceased", "| `not_reached` | `deceased` | the customer has died (2.2 e) |"),
    "unclear": ("not_reached", "unclear", "| `not_reached` | `unclear` | still unclear who answered after the second ask (2.1 c) |"),
}


def says(multi):
    return {
        "promise": ("You will receive a text message confirming your promise. " if multi else "") + BYE,
        "paid": "Thank you. Payments can take one business day to appear. " + BYE,
        "restructuring": "I am connecting you now. " + BYE,
        "human": "I am connecting you now. Thank you, goodbye.",
        "support": "I am connecting you with our customer support team now. " + BYE,
        "refused": BYE,
        "hardship": BYE,
        "dispute": "Thank you for letting me know. " + BYE,
        "service_error": BYE,
        "account_error": "I am sorry, I cannot reach your account details right now because of a technical problem. " + BYE,
        "failed": "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye.",
        "declined": "Thank you for your time. Goodbye.",
        "callback": "Thank you, we will call back then. Goodbye.",
        "no_callback": "Thank you for your time. Goodbye.",
        "wrong_number": "I apologise for the inconvenience. Thank you, goodbye.",
        "deceased": "I am sorry for your loss. Goodbye.",
        "unclear": "Thank you for your time. Goodbye.",
    }


def plan(multi):
    closings = {}
    s = says(multi)
    for cid, (outcome, reason, row) in CODE_ROW.items():
        values = {"outcome": outcome}
        if reason:
            values["reason"] = reason
        ev = [{"source": A, "quote": row}]
        if multi and cid in ("promise", "paid", "refused", "hardship", "dispute", "service_error"):
            ev.append({"source": B, "quote": "With more than one product, `promise` is used whenever at least one PTP was recorded, except in the case of D1."})
        closings[cid] = {"set": values, "say": s[cid], "evidence": ev}
    return {
        "terminal": {"tool": "close_call", "evidence": [
            {"source": OA, "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
            {"source": A, "quote": "Every call ends with exactly one `close_call`, as the last tool call"}]},
        "fields": {"customer_id": "{{customer_id}}"},
        "closings": closings,
    }


if __name__ == "__main__":
    out = ROOT / "out"
    for slot, multi in (("brief-a-raw", False), ("brief-b-raw", True)):
        (out / f"{slot}.body.json").write_text(json.dumps(build(multi), indent=1, ensure_ascii=False) + "\n")
        (out / f"{slot}.closing.json").write_text(json.dumps(plan(multi), indent=1, ensure_ascii=False) + "\n")
    print("written")
