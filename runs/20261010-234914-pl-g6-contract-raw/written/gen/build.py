"""Generate out/<slot>.body.json and out/<slot>.closing.json for briefs/pl-g6-contract-raw.md."""
import json
from pathlib import Path

SLOT = "pl-g6-contract-raw"
BRIEF = "briefs/pl-g6-contract-raw.md"
API = "tools/openapi.json"
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
OUT = Path("out")

# ------------------------------------------------------------------ code (no double braces allowed)

HELPERS = r'''
import datetime, re, json
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def fmt(d):
    return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + d.strftime('%B') + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
def nth_bd(start, n):
    d = start
    k = 0
    while k < n:
        d = d + datetime.timedelta(days=1)
        if isbd(d):
            k += 1
    return d
def parse_now():
    raw = str(vars.get('now') or '').strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?', raw)
    today = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    hh = int(m.group(4) or 0)
    mm = int(m.group(5) or 0)
    return today, hh, mm
def valid_dates(today, deadline):
    out = []
    d = today
    while d <= deadline:
        if isbd(d):
            out.append(fmt(d))
        d = d + datetime.timedelta(days=1)
    return out
def attempt1_date(today):
    monday = today - datetime.timedelta(days=today.weekday())
    week = [monday + datetime.timedelta(days=i) for i in range(5)]
    bds = [d for d in week if isbd(d)]
    if bds and bds[-1] > today:
        return bds[-1]
    nxt = [d + datetime.timedelta(days=7) for d in week]
    bds = [d for d in nxt if isbd(d)]
    return bds[-1] if bds else nth_bd(today, 5)
'''

SETUP_CODE = HELPERS + r'''
try:
    today, hh, mm = parse_now()
    monday = today - datetime.timedelta(days=today.weekday())
    lines = []
    for i in range(7):
        a = monday + datetime.timedelta(days=i)
        b = a + datetime.timedelta(days=7)
        lines.append('this ' + DAYS[i] + ' = ' + fmt(a) + '; next ' + DAYS[i] + ' = ' + fmt(b))
    cal = []
    for i in range(0, 24):
        d = today + datetime.timedelta(days=i)
        kind = 'business day' if isbd(d) else ('Freya Bank holiday, not a business day' if d.isoformat() in HOL else 'weekend, not a business day')
        cal.append(fmt(d) + ': ' + kind)
    vars['today_text'] = fmt(today) + ', time ' + '%02d:%02d' % (hh, mm)
    vars['week_table'] = 'Week table (weeks run Monday to Sunday): ' + ' | '.join(lines)
    vars['calendar_text'] = 'Calendar from today: ' + ' | '.join(cal)
    nbd = nth_bd(today, 1)
    parts = []
    if (hh, mm) < (19, 0):
        start = '10:00' if (hh, mm) < (10, 0) else ('%02d:%02d' % (hh, mm)) + ' (strictly later than now)'
        parts.append('today, ' + fmt(today) + ', from ' + start + ' to 19:00')
    else:
        parts.append('today is no longer possible, it is after 19:00')
    parts.append('the next business day, ' + fmt(nbd) + ', from 10:00 to 19:00')
    vars['callback_facts'] = 'Allowed callback times, both ends included: ' + '; or '.join(parts) + '. Every other day or time is outside the window. Today is ' + fmt(today) + ' and the time now is ' + '%02d:%02d' % (hh, mm) + '.'
    vars['dates_state'] = 'known'
except Exception as e:
    vars['today_text'] = str(vars.get('now') or '')
    vars['week_table'] = 'Work out weekdays from the current date yourself.'
    vars['calendar_text'] = 'Business days are Monday to Friday, except 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01.'
    vars['callback_facts'] = 'A callback is allowed today or the next business day, from 10:00 to 19:00, and later than now (' + str(vars.get('now') or '') + ').'
    vars['dates_state'] = 'unknown'
'''

ACCOUNT_CODE = HELPERS + r'''
def money(x):
    v = float(x)
    return ('%.2f' % v) + ' euros'
def num(x):
    v = float(x)
    return ('%.2f' % v).rstrip('0').rstrip('.')
def products_list():
    p = vars.get('products')
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            p = None
    if isinstance(p, list) and p:
        return p
    items = dict()
    for k, v in list(vars.items()):
        m = re.search(r'products(?:\.|\[)(\d+)\]?\.(\w+)$', str(k))
        if m:
            items.setdefault(int(m.group(1)), dict())[m.group(2)] = v
    return [items[i] for i in sorted(items)]
try:
    prods = products_list()
    p = prods[0]
    kind = str(p.get('type') or '')
    if kind == 'credit_card':
        words = 'credit card ending ' + str(p.get('card_last4') or '')
        floor = p.get('minimum_payment')
    elif kind == 'car_loan':
        words = 'car loan'
        floor = p.get('instalment_amount')
    else:
        words = 'personal loan'
        floor = p.get('instalment_amount')
    past_due = float(p.get('past_due'))
    days_late = int(float(p.get('days_late')))
    if floor is None or str(floor) == '':
        floor = past_due
    floor = float(floor)
    today, hh, mm = parse_now()
    late = days_late >= 8
    deadline = nth_bd(today, 7 if late else 12)
    a1 = attempt1_date(today)
    vars['product_words'] = words
    vars['past_due_text'] = money(past_due) + ' (number for the tool: ' + num(past_due) + ')'
    vars['floor_text'] = money(floor) + ' (number for the tool: ' + num(floor) + ')'
    vars['days_late_text'] = str(days_late)
    vars['band'] = 'late' if late else 'early'
    vars['deadline_text'] = fmt(deadline)
    vars['valid_dates_text'] = ' | '.join(valid_dates(today, deadline))
    vars['attempt1_text'] = ('propose paying the full past due amount of ' + money(past_due) + ' on ' + fmt(a1)
                             + '. If the customer already said the full amount is too much, propose instead the minimum amount of '
                             + money(floor) + ' on ' + fmt(a1) + ' and say that the rest stays overdue')
    vars['attempt2_text'] = ('propose paying the minimum amount of ' + money(floor) + ' on ' + fmt(deadline)
                             + ', and say that the rest stays overdue')
    if p.get('product_id'):
        vars['product_id'] = str(p.get('product_id'))
    vars['account_state'] = 'known'
except Exception as e:
    vars['product_words'] = 'product named in the get_account result'
    vars['past_due_text'] = 'past_due from the get_account result'
    vars['floor_text'] = 'minimum_payment for a credit card, instalment_amount for a loan, from the get_account result'
    vars['days_late_text'] = 'days_late from the get_account result'
    vars['band'] = 'early'
    vars['deadline_text'] = 'the 12th business day after today if days_late is 1 to 7, the 7th business day after today if days_late is 8 to 45'
    vars['valid_dates_text'] = 'business days from today up to the deadline'
    vars['attempt1_text'] = 'propose paying the full past due amount on the last business day of this week (next week if today is that day)'
    vars['attempt2_text'] = 'propose paying the minimum amount on the deadline, and say that the rest stays overdue'
    vars['account_state'] = 'unknown'
'''

# ------------------------------------------------------------------ helpers


def headers():
    return {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}


def api_tool(name, path, desc, body_props, required, retries=0):
    return {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": desc,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BASE + path},
                "method": {"type": "string", "default": "POST"},
                "headers": headers(),
                "body": {"type": "object", "properties": body_props, "required": required},
            }},
        },
    }


CID = {"type": "string", "default": "{{customer_id}}"}


def verify_tool(field, what):
    return api_tool("verify_identity", "/verify_identity",
                    f"Check the customer's {what}. CALL it every time the customer gives this answer, before you say anything about it.",
                    {"customer_id": CID,
                     "field": {"type": "string", "enum": [field], "default": field},
                     "answer": {"type": "string", "default": "{{answer}}",
                                "description": "For date_of_birth: the date as YYYY-MM-DD. A date said only in numbers is day, then month, then year. For phone_last4: exactly four digits."}},
                    ["customer_id", "field", "answer"])


def transfer_tool(name, queue, when):
    return api_tool(name, "/transfer_to_agent", f"Hand the call to a person in the {queue} team. CALL it {when}",
                    {"customer_id": CID, "queue": {"type": "string", "enum": [queue], "default": queue}},
                    ["customer_id", "queue"])


T_RESTRUCT = transfer_tool("transfer_restructuring", "restructuring",
                           "when the customer asks for a new payment plan or lower instalments, unless they mentioned illness, a death in the family or job loss. Do not describe any plan.")
T_GENERAL = transfer_tool("transfer_general", "general",
                          "only when the customer asks for a human a second time, after you asked once whether you can help them first.")
T_SUPPORT = transfer_tool("transfer_support", "customer_support",
                          "when the customer accepts your offer to connect them with the customer support team.")

CREATE_PROMISE = api_tool(
    "create_promise", "/create_promise",
    "Record the payment promise. CALL it only after you read back the product, the amount and the date and the customer clearly said yes to 'Do you confirm?'. If it fails, CALL it once more with the same values.",
    {"customer_id": CID,
     "product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id from the get_account result."},
     "amount_eur": {"type": "number", "default": "{{amount_eur}}", "description": "The confirmed amount in euros, as a number, for example 412.5."},
     "promise_date": {"type": "string", "default": "{{promise_date}}", "description": "The confirmed date as YYYY-MM-DD."},
     "channel": {"type": "string", "enum": ["voice"], "default": "voice"}},
    ["customer_id", "product_id", "amount_eur", "promise_date", "channel"])

SCHEDULE = api_tool(
    "schedule_callback", "/schedule_callback",
    "Book a callback for the customer. CALL it as soon as the person gives a day and a time that are inside the allowed window.",
    {"customer_id": CID,
     "date": {"type": "string", "default": "{{callback_date}}", "description": "Callback day as YYYY-MM-DD."},
     "slot_time": {"type": "string", "default": "{{slot_time}}", "description": "Callback time as HH:MM, 24 hour clock."}},
    ["customer_id", "date", "slot_time"])


def var(name, op, operand=None):
    c = {"variable": name, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return c


def when(*checks):
    return {"logic": "or", "conditions": [checks[0] if len(checks) == 1 else {"logic": "and", "conditions": list(checks)}]}


def any_of(*checks):
    return {"logic": "or", "conditions": list(checks)}


def go(target, desc, cond):
    return {"target_node": target, "description": desc, "condition": cond}


def tool_go(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def true_of(v):
    return any_of(var(v, "equals", "true"), var(v, "equals", "True"))


def enum_field(name, values, desc, conf=0.6):
    return {"name": name, "type": "string", "enum_values": values, "description": desc, "min_confidence": conf}


def conv(name, task, transitions, tools=None, on_enter=None, extraction=None, max_turns=None, cap_to=None, first_only=False):
    n = {"name": name, "node_type": "conversation", "task_message": task, "transitions": transitions}
    if tools:
        n["tools"] = tools
    n["on_enter"] = on_enter or {"type": "llm"}
    if first_only:
        n["on_enter_first_entry_only"] = True
    if extraction:
        n["extraction_schema"] = extraction
    if max_turns:
        n["max_node_turns"] = max_turns
        n["max_turn_transition"] = cap_to
    return n


def code_node(name, code, nxt):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                             "parameters": {"type": "object", "properties": {
                                 "code": {"type": "string", "default": code},
                                 "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": [go(nxt, "always", {"operator": "always"})]}


NO_TOOL = "No other tool call is allowed in this step."
SPEAK = "After every tool result, speak to the customer or call the next tool. Never end a turn with nothing."
NO_BYE = "Do not say goodbye yourself: when the call ends, a closing line is spoken for you."

SYSTEM = (
    "You are Freya Bank's digital assistant, on an outbound phone call. Speak English. Keep every turn to one or two short sentences. "
    "Use plain words, no technical words, no tool names, no variable names. Address the customer as {{title}} {{last_name}}. "
    "Now is {{now}}. All date rules use this, never the real clock.\n"
    "Rules for the whole call:\n"
    "- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.\n"
    "- If asked whether this is a scam: say they can verify the call by phoning Freya Bank's customer service number, then continue.\n"
    "- If you cannot answer a question from the tool results, say you do not have that information. Never invent figures, dates or reasons.\n"
    "- Never offer a discount, a waiver, an instalment plan or any other term.\n"
    "- Until the identity check has passed, never say 'collections', 'debt', 'payment', an amount or the product, to anyone, relatives included.\n"
    "- Call at most one tool per message. " + SPEAK + "\n"
    "- Never say something is recorded, booked or transferred unless the tool returned ok: true. If a tool fails, say so.\n"
    "- " + NO_BYE
)

# ------------------------------------------------------------------ nodes

nodes = {}

nodes["setup"] = code_node("setup", SETUP_CODE, "opening")

OPEN_ENUM = ["confirmed", "someone_else", "wrong_number", "deceased", "unclear"]
OPEN_DESC = ("Who answered the question 'Am I speaking with {{title}} {{last_name}}?'. "
             "confirmed: only 'yes', 'that's me', 'speaking' or the customer's own name. "
             "someone_else: the person is not the customer but knows them (for example a relative, or the customer is not available). "
             "wrong_number: the person says this number does not belong to the customer or they do not know them. "
             "deceased: the person says the customer has died. "
             "unclear: anything else, such as 'hello', 'go ahead', 'who is this', a question, or no clear answer.")


def opening_routes(var_name, unclear_target):
    return [
        go("identity_dob", "the customer confirmed who they are", when(var(var_name, "equals", "confirmed"))),
        go("close:not_reached/deceased", "the customer has died", when(var(var_name, "equals", "deceased"))),
        go("close:not_reached/wrong_number", "wrong number", when(var(var_name, "equals", "wrong_number"))),
        go("third_party", "someone else answered", when(var(var_name, "equals", "someone_else"))),
        go(unclear_target, "identity of the person still unclear", when(var(var_name, "equals", "unclear"))),
        T_GO_HUMAN,
    ]


T_GO_HUMAN = go("close:transferred/human", "a transfer to a person in the general team succeeded",
                when(var("transfer_general_success_count", "greater_than", 0)))

nodes["opening"] = conv(
    "opening",
    "You asked whether you are speaking with {{title}} {{last_name}}. Do not say why you are calling. "
    "If the person asks a question, answer it briefly (who you are: Freya Bank's digital assistant), then ask once more: "
    "'Am I speaking with {{title}} {{last_name}}?'. If the person asks for a human, ask once whether you can help first; if they insist, call transfer_general. "
    + NO_TOOL,
    opening_routes("who_1", "opening_retry"),
    tools=[T_GENERAL],
    on_enter={"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    first_only=True,
    extraction=[enum_field("who_1", OPEN_ENUM, OPEN_DESC)],
    max_turns=4, cap_to="close:not_reached/unclear")

nodes["opening_retry"] = conv(
    "opening_retry",
    "The person has not yet confirmed who they are. Do not say why you are calling. "
    "If they asked a question, answer it briefly first: you are Freya Bank's digital assistant; if they ask about a scam, say they can verify the call by phoning Freya Bank's customer service number. "
    "Then ask exactly once more: 'Am I speaking with {{title}} {{last_name}}?'. Do not ask a third time. "
    "If the person asks for a human, ask once whether you can help first; if they insist, call transfer_general. " + NO_TOOL,
    opening_routes("who_2", "close:not_reached/unclear"),
    tools=[T_GENERAL],
    first_only=True,
    extraction=[enum_field("who_2", OPEN_ENUM, OPEN_DESC.replace("the question", "the second ask of the question"))],
    max_turns=3, cap_to="close:not_reached/unclear")

nodes["third_party"] = conv(
    "third_party",
    "The person on the line is not {{title}} {{last_name}}. Never say why you are calling, never mention money, an account, collections or a product. "
    "Do not ask security questions. If they offer to pay or ask what it is about, say you can only speak with {{title}} {{last_name}} in person.\n"
    "Ask when {{title}} {{last_name}} can be reached.\n"
    "{{callback_facts}}\n"
    "- If the person gives a day and an exact time inside the allowed window, call schedule_callback with the date as YYYY-MM-DD and the time as HH:MM.\n"
    "- If they give a day but no exact time, ask for the time.\n"
    "- If the day or time is outside the window, say so, tell them the allowed times and ask once for another time.\n"
    "- If the second time is also outside the window, or they will not give a time, do not schedule; end the call with the no-callback transition.\n"
    "- If schedule_callback fails, call it once more with the same values.\n"
    "- If the person says the customer has died, say nothing and end the call with the deceased transition at once.\n"
    + NO_BYE,
    [
        go("close:not_reached/callback", "the callback was booked", when(var("schedule_callback_success_count", "greater_than", 0))),
        go("close:not_reached/callback_failed", "the callback could not be booked twice", when(var("schedule_callback_failure_count", "greater_than", 1))),
        go("close:not_reached/deceased", "the customer has died", when(var("third_status", "equals", "deceased"))),
        go("close:not_reached/wrong_number", "wrong number", when(var("third_status", "equals", "wrong_number"))),
        T_GO_HUMAN,
        tool_go("close:not_reached/no_callback",
                "The person gave a second day or time that is also outside the allowed callback window, after you already asked once for another time, or they refuse to give any time for a callback."),
    ],
    tools=[SCHEDULE, T_GENERAL],
    extraction=[enum_field("third_status", ["deceased", "wrong_number", "other"],
                           "deceased: the person says the customer has died. wrong_number: the person says this number does not belong to the customer. other: anything else.")],
    max_turns=10, cap_to="close:not_reached/no_callback")

DECLINE_GO = tool_go(
    "close:not_verified/declined",
    "The customer refused a security question, or asked what the call is about instead of answering, or said they do not want to talk, for the second time, after you already explained once that the questions protect their account.")

ID_COMMON = (
    "The customer confirmed who they are. You are doing the security check. You do not know why the bank is calling; never mention the debt, payment, collections or the product.\n"
    "- If the customer does not want to answer, or asks what the call is about instead of answering, explain once that these questions protect their account, and ask the question again. "
    "If they refuse or ask again a second time, end the call with the declined transition.\n"
    "- If the customer asks for a human, ask once whether you can help first; if they insist, call transfer_general.\n"
    "- " + SPEAK + "\n"
)

nodes["identity_dob"] = conv(
    "identity_dob",
    ID_COMMON +
    "Question now: the date of birth. When the customer gives it, convert it to YYYY-MM-DD and call verify_identity at once. "
    "A date said only in numbers is day, then month, then year (05/03/1985 is 1985-03-05).\n"
    "- If the result has hint day_month_swapped: ask the customer to say the month as a word, then call verify_identity again with the new answer.\n"
    "- If the result is ok false (the date could not be read): ask the customer to say the date again, with the month as a word.\n"
    "- If verified is false: say the answer does not match and ask for the date of birth again.",
    [
        go("load_account", "both answers verified", true_of("verify_identity_response.data.all_verified")),
        go("close:not_verified/failed", "no wrong answers left", when(var("verify_identity_response.data.wrong_answers_left", "equals", 0))),
        go("identity_phone", "date of birth verified", true_of("verify_identity_response.data.verified")),
        T_GO_HUMAN,
        DECLINE_GO,
    ],
    tools=[verify_tool("date_of_birth", "date of birth"), T_GENERAL],
    on_enter={"type": "tts", "text": "Thank you. Before we continue, I need to ask you two security questions. What is your date of birth?"},
    first_only=True,
    max_turns=14, cap_to="close:not_verified/declined")

nodes["identity_phone"] = conv(
    "identity_phone",
    ID_COMMON +
    "The date of birth is verified. Question now: the last four digits of the phone number on file. When the customer gives four digits, call verify_identity at once.\n"
    "- If verified is false: say the answer does not match and ask for the last four digits again.\n"
    "- If the customer gives more or fewer than four digits, ask for exactly the last four.",
    [
        go("load_account", "both answers verified", true_of("verify_identity_response.data.all_verified")),
        go("close:not_verified/failed", "no wrong answers left", when(var("verify_identity_response.data.wrong_answers_left", "equals", 0))),
        T_GO_HUMAN,
        DECLINE_GO,
    ],
    tools=[verify_tool("phone_last4", "last four digits of the phone number"), T_GENERAL],
    on_enter={"type": "tts", "text": "Thank you. And what are the last four digits of the phone number we have on file for you?"},
    first_only=True,
    max_turns=12, cap_to="close:not_verified/declined")

nodes["load_account"] = {
    "name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "account_facts",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [api_tool("get_account", "/get_account", "Get the late products.", {"customer_id": CID}, ["customer_id"], retries=2)],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [
        go("account_facts", "the account was loaded", when(var("load_account_success_count", "greater_than", 0))),
        go("close:no_promise/account_error", "the account could not be loaded", when(var("load_account_failure_count", "greater_than", 0))),
        go("account_facts", "always", {"operator": "always"}),
    ],
}

nodes["account_facts"] = code_node("account_facts", ACCOUNT_CODE, "ask_today")

# ------------------------------------------------------------------ negotiation

NEGOTIATE = (
    "The customer is verified. You are calling from the collections team about a late payment. Get a payment promise where you can.\n"
    "ACCOUNT: {{product_words}}. Past due amount: {{past_due_text}}. Days late: {{days_late_text}}. Minimum amount (the floor): {{floor_text}}.\n"
    "DATES: today is {{today_text}}. The latest date you can record (the deadline) is {{deadline_text}}. "
    "Valid promise dates (business days from today to the deadline): {{valid_dates_text}}.\n"
    "{{calendar_text}}\n"
    "{{week_table}}\n"
    "TOOLS: create_promise records the promise. transfer_restructuring for a new payment plan or lower instalments. transfer_general only if the customer insists on a human. "
    "When a rule says to call a tool, call it; do not only talk about it.\n"
    "AMOUNTS:\n"
    "- You propose every amount. Never ask how much the customer can pay. Start with the full past due amount.\n"
    "- If the customer says the full amount is too much, offer the floor once and say the rest stays overdue.\n"
    "- An amount the customer proposes from the floor up to the full amount, both included, is accepted. Below the floor: say it cannot be recorded and offer the floor once.\n"
    "DATES:\n"
    "- A promise date must be one of the valid promise dates above.\n"
    "- A weekend day or a holiday that is not after the deadline: offer the next business day.\n"
    "- A date after the deadline: say the latest date you can record is the deadline, and offer the deadline.\n"
    "- A vague period ('next week', 'end of the month', 'when my salary comes'): ask once for the exact day. If they still give none, propose the deadline.\n"
    "- 'Next <weekday>' is that weekday in the following calendar week; 'this <weekday>' is the one in the current week. Use the week table.\n"
    "CONFIRMING:\n"
    "- When amount and date are both valid, read back the product, the amount and the date, and ask 'Do you confirm?'.\n"
    "- Call create_promise only after a clear yes, with amount_eur as a number and promise_date as YYYY-MM-DD.\n"
    "- If the customer changes the date or the amount, check the new value with the rules above and read it back again.\n"
    "- If create_promise fails, call it once more with the same values at once. Never say it is recorded before it returns ok: true.\n"
    "OTHER:\n"
    "- A request for a new payment plan or lower instalments: do not describe any plan; call transfer_restructuring.\n"
    "- A request for a human: ask once whether you can help first. If they insist, call transfer_general.\n"
    "- Never offer a discount, a waiver, an instalment plan or any other term. Do not repeat an offer the customer already refused.\n"
    "- " + NO_BYE
)

REFUSAL_DESC = (
    "yes: the customer flatly refuses the offer the agent made last, or gives a non-answer to it, and names no date and no amount of their own. "
    "A plain no to paying today is yes. Refusing the minimum amount after it was offered is yes. Refusing the deadline after it was offered is yes. "
    "Saying they do not want to talk is yes. "
    "no: the customer accepts, proposes a date or an amount of any kind, gives a vague period, asks a question, "
    "or says the full amount is too much before the minimum amount was offered. "
    "Also no when the customer says they already paid, that the debt is not theirs, mentions illness, a death in the family or job loss, or asks for a payment plan or a human."
)

TOPIC_DESC = (
    "already_paid: the customer says they have already paid this past due amount. "
    "dispute: the customer says the debt is not theirs, they never had this product, or the product was closed or paid off in the past. "
    "hardship: the customer mentions illness, a death in the family or job loss. "
    "none: anything else, including a promise to pay later."
)


def negotiation_routes(refusal_var, refusal_routes):
    return [
        go("promise_done", "the promise was recorded", when(var("create_promise_success_count", "greater_than", 0))),
        go("close:no_promise/service_error", "the promise could not be recorded twice",
           when(var("create_promise_failure_count", "greater_than", 1))),
        go("close:transferred/restructuring", "transferred to restructuring", when(var("transfer_restructuring_success_count", "greater_than", 0))),
        T_GO_HUMAN,
        go("hardship", "the customer mentioned hardship", when(var("topic", "equals", "hardship"))),
        go("close:paid", "the customer already paid", when(var("topic", "equals", "already_paid"))),
        go("close:no_promise/dispute", "the customer disputes the debt", when(var("topic", "equals", "dispute"))),
    ] + refusal_routes


def negotiation_node(name, entry, refusal_var, refusal_routes):
    return conv(
        name, NEGOTIATE + "\nTHIS STAGE: " + entry,
        negotiation_routes(refusal_var, refusal_routes),
        tools=[CREATE_PROMISE, T_RESTRUCT, T_GENERAL],
        on_enter={"type": "llm", "prompt": entry},
        first_only=True,
        extraction=[enum_field(refusal_var, ["yes", "no"], REFUSAL_DESC),
                    enum_field(refusal_var.replace("refusal", "no_talk"), ["yes", "no"],
                               "yes: in this message the customer says they do not want to talk, or want to end the conversation. no: anything else."),
                    enum_field("topic", ["already_paid", "dispute", "hardship", "none"], TOPIC_DESC)],
        max_turns=16, cap_to="close:no_promise/refused")


nodes["ask_today"] = negotiation_node(
    "ask_today",
    "The identity check has just passed. Say that you are calling from the collections team about a late payment on the customer's {{product_words}}: "
    "the past due amount is {{past_due_text}} and it is {{days_late_text}} days late (say the amount in words, without the tool number). "
    "Then ask exactly: 'Can you make this payment today?'.",
    "refusal_0",
    [go("attempt_1", "the customer refused to pay today", any_of(var("refusal_0", "equals", "yes"), var("no_talk_0", "equals", "yes")))])

nodes["attempt_1"] = negotiation_node(
    "attempt_1",
    "The customer did not agree to pay. Make one persuasion attempt now: {{attempt1_text}}. Ask whether they can do that. Say amounts in words, without the tool number.",
    "refusal_1",
    [go("attempt_2", "refused, a second attempt is allowed in the late band, and the customer has not said twice they do not want to talk",
        any_of({"logic": "and", "conditions": [var("refusal_1", "equals", "yes"), var("band", "equals", "late"), var("no_talk_1", "not_equals", "yes")]},
               {"logic": "and", "conditions": [var("no_talk_1", "equals", "yes"), var("band", "equals", "late"), var("no_talk_0", "not_equals", "yes")]})),
     go("close:no_promise/refused", "refused, no attempts left", any_of(var("refusal_1", "equals", "yes"), var("no_talk_1", "equals", "yes")))])

nodes["attempt_2"] = negotiation_node(
    "attempt_2",
    "The customer refused again. Make the last persuasion attempt now: {{attempt2_text}}. Ask whether they can do that. Say amounts in words, without the tool number.",
    "refusal_2",
    [go("close:no_promise/refused", "refused the last attempt", any_of(var("refusal_2", "equals", "yes"), var("no_talk_2", "equals", "yes")))])

nodes["hardship"] = conv(
    "hardship",
    NEGOTIATE.split("TOOLS:")[0] +
    "The customer mentioned illness, a death in the family or job loss. Make no persuasion attempt and propose no amount or date.\n"
    "- First say one short sentence of sympathy, then offer to connect them with the customer support team.\n"
    "- If they accept, call transfer_support at once.\n"
    "- If the customer names a date or an amount themselves, handle it: the amount must be from the floor up to the full past due amount, the date one of the valid promise dates. "
    "Read back the product, the amount and the date, ask 'Do you confirm?', and call create_promise only after a clear yes. If it fails, call it once more.\n"
    "- A request for a human: ask once whether you can help first; if they insist, call transfer_general.\n- " + NO_BYE,
    [
        go("promise_done", "the promise was recorded", when(var("create_promise_success_count", "greater_than", 0))),
        go("close:no_promise/service_error", "the promise could not be recorded twice",
           when(var("create_promise_failure_count", "greater_than", 1))),
        go("close:transferred/support", "transferred to customer support", when(var("transfer_support_success_count", "greater_than", 0))),
        T_GO_HUMAN,
        go("close:no_promise/hardship", "the customer declined the support team", when(var("support_answer", "equals", "declined"))),
    ],
    tools=[T_SUPPORT, CREATE_PROMISE, T_GENERAL],
    on_enter={"type": "llm", "prompt": "Say one short sentence of sympathy. Then offer to connect the customer with the customer support team. Do not mention any payment."},
    first_only=True,
    extraction=[enum_field("support_answer", ["accepted", "declined", "undecided"],
                           "The customer's answer to the offer to connect them with the customer support team. accepted: yes. "
                           "declined: no, they do not want to be connected, and they name no payment date or amount. undecided: anything else.")],
    max_turns=10, cap_to="close:no_promise/hardship")

nodes["promise_done"] = conv(
    "promise_done",
    "The payment promise for the {{product_words}} is recorded. One promise per product: a recorded promise cannot be changed or cancelled in this call; "
    "if the customer asks, say they can change it in the mobile app. Do not record another promise.\n"
    "- A request for a new payment plan or lower instalments: do not describe a plan; call transfer_restructuring.\n"
    "- If the customer mentions illness, a death in the family or job loss: one sentence of sympathy, offer the customer support team; if they accept, call transfer_support.\n"
    "- A request for a human: ask once whether you can help first; if they insist, call transfer_general.\n"
    "- Otherwise ask whether there is anything else.\n- " + NO_BYE,
    [
        go("close:transferred/restructuring", "transferred to restructuring", when(var("transfer_restructuring_success_count", "greater_than", 0))),
        go("close:transferred/support", "transferred to customer support", when(var("transfer_support_success_count", "greater_than", 0))),
        T_GO_HUMAN,
        go("close:promise", "nothing else", when(var("after_promise", "equals", "done"))),
    ],
    tools=[T_RESTRUCT, T_SUPPORT, T_GENERAL],
    on_enter={"type": "tts", "text": "Thank you, your promise is recorded. You will receive a text message confirming this promise. Is there anything else I can help you with?"},
    first_only=True,
    extraction=[enum_field("after_promise", ["done", "more"],
                           "done: the customer has nothing else, says no, thanks or goodbye. more: the customer asks or wants something else.")],
    max_turns=8, cap_to="close:promise")

body = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    "nodes": nodes,
}

# ------------------------------------------------------------------ closing plan


def ev(quote, source=BRIEF):
    return [{"source": source, "quote": quote}]


BYE = " Thank you for your time. Goodbye."
closings = {
    "promise": {"set": {"outcome": "promise"}, "say": "Thank you for your time, {{title}} {{last_name}}. Goodbye.",
                "evidence": ev("Outcome: promise; Reason: none; When: at least one promise was recorded")},
    "paid": {"set": {"outcome": "paid"}, "say": "Thank you for letting me know. A payment can take one business day to appear." + BYE,
             "evidence": ev("Outcome: paid; Reason: none; When: rule 39")},
    "transferred/restructuring": {"set": {"outcome": "transferred", "reason": "restructuring"}, "say": "I am transferring you now. Thank you, goodbye.",
                                  "evidence": ev("Call `transfer_to_agent` with queue `restructuring` and close as `transferred` / `restructuring`.")},
    "transferred/human": {"set": {"outcome": "transferred", "reason": "human"}, "say": "I am transferring you now. Thank you, goodbye.",
                          "evidence": ev("call `transfer_to_agent` with queue `general` and close as `transferred` / `human`.")},
    "transferred/support": {"set": {"outcome": "transferred", "reason": "support"}, "say": "I am transferring you now. Thank you, goodbye.",
                            "evidence": ev("call `transfer_to_agent` with queue `support` and close as `transferred` / `support`.")},
    "no_promise/refused": {"set": {"outcome": "no_promise", "reason": "refused"}, "say": "I understand." + BYE,
                           "evidence": ev("Do not repeat an offer the customer already refused. Close as `no_promise` / `refused`.")},
    "no_promise/hardship": {"set": {"outcome": "no_promise", "reason": "hardship"}, "say": "I understand. Take care." + BYE,
                            "evidence": ev("If they decline, close as `no_promise` / `hardship`.")},
    "no_promise/dispute": {"set": {"outcome": "no_promise", "reason": "dispute"}, "say": "I understand, thank you for telling me." + BYE,
                           "evidence": ev("do not argue and do not take a promise. Close as `no_promise` / `dispute`.")},
    "no_promise/service_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                 "say": "I am sorry, I could not record your promise because of a technical problem." + BYE,
                                 "evidence": ev("If it fails again, say you could not record it and close as `no_promise` / `service_error`.")},
    "no_promise/account_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                 "say": "I am sorry, I cannot open your account details right now because of a technical problem." + BYE,
                                 "evidence": ev("Reason: refused`, `hardship`, `dispute`, `service_error; When: rules 31 and 45, 32, 40, 37")},
    "not_verified/failed": {"set": {"outcome": "not_verified", "reason": "failed"},
                            "say": "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch." + BYE,
                            "evidence": ev("Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`.")},
    "not_verified/declined": {"set": {"outcome": "not_verified", "reason": "declined"},
                              "say": "I understand. Without the security questions I cannot continue." + BYE,
                              "evidence": ev("If they still decline, close as `not_verified` / `declined`.")},
    "not_reached/callback": {"set": {"outcome": "not_reached", "reason": "callback"}, "say": "Thank you, we will call back then." + BYE,
                             "evidence": ev("Call `schedule_callback` with the date and the time, then close as `not_reached` / `callback`.")},
    "not_reached/callback_failed": {"set": {"outcome": "not_reached", "reason": "no_callback"},
                                    "say": "I am sorry, I could not book the callback because of a technical problem." + BYE,
                                    "evidence": ev("If that is also outside it, do not schedule. Close as `not_reached` / `no_callback`.")},
    "not_reached/no_callback": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "say": "I understand." + BYE,
                                "evidence": ev("If that is also outside it, do not schedule. Close as `not_reached` / `no_callback`.")},
    "not_reached/wrong_number": {"set": {"outcome": "not_reached", "reason": "wrong_number"}, "say": "I apologise for the trouble." + BYE,
                                 "evidence": ev("If the person says the number does not belong to the customer, close as `not_reached` / `wrong_number`.")},
    "not_reached/deceased": {"set": {"outcome": "not_reached", "reason": "deceased"}, "say": "I am sorry for your loss. Thank you, goodbye.",
                             "evidence": ev("say \"I am sorry for your loss.\", ask nothing else, and close as `not_reached` / `deceased`.")},
    "not_reached/unclear": {"set": {"outcome": "not_reached", "reason": "unclear"}, "say": "I am sorry, I could not confirm who I am speaking with." + BYE,
                            "evidence": ev("If it is still unclear after the second ask, close as `not_reached` / `unclear`.")},
}

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": API, "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]},
    "fields": {"customer_id": "{{customer_id}}", "channel": "voice"},
    "closings": closings,
    "precedence": [
        {"closing": "promise", "when": [var("create_promise_success_count", "greater_than", 0)],
         "keep": ["transferred/restructuring", "transferred/human", "transferred/support"],
         "evidence": ev("If a transfer follows a recorded promise, close as `transferred` with that transfer's reason.")
         + ev("Outcome: promise; Reason: none; When: at least one promise was recorded")},
        {"closing": "not_verified/failed", "when": [var("verify_identity_response.data.wrong_answers_left", "equals", 0)],
         "keep": ["transferred/human"],
         "evidence": ev("After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`.")},
    ],
}

OUT.mkdir(exist_ok=True)
(OUT / f"{SLOT}.body.json").write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
(OUT / f"{SLOT}.closing.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
print("written")
