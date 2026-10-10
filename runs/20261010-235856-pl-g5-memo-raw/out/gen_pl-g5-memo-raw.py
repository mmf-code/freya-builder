"""Generate the body workflow and closing plan for briefs/pl-g5-memo-raw.md.

Then lower it:  python3 tools/lower.py out/pl-g5-memo-raw.body.json out/pl-g5-memo-raw.plan.json \
    --tools tools/openapi.json -o out/pl-g5-memo-raw.workflow.json --contract out/pl-g5-memo-raw.contract.json
"""
import json
from pathlib import Path

SLOT = "pl-g5-memo-raw"
BRIEF = f"briefs/{SLOT}.md"
BASE_URL = "https://freya-bank-mock.freyavoice.workers.dev/v1"
OUT = Path(__file__).resolve().parent

# ---------------------------------------------------------------- helpers

def ev(quote, source=BRIEF):
    return [{"source": source, "quote": quote}]


def var_is(name, value):
    return {"logic": "or", "conditions": [{"variable": name, "operator": "equals", "operand": value}]}


def bool_true(name):
    return {"logic": "or", "conditions": [
        {"variable": name, "operator": "equals", "operand": "true"},
        {"variable": name, "operator": "equals", "operand": "True"}]}


def gt(name, n):
    return {"logic": "or", "conditions": [{"variable": name, "operator": "greater_than", "operand": n}]}


def lt(name, n):
    return {"logic": "or", "conditions": [{"variable": name, "operator": "less_than", "operand": n}]}


def any_result(tool):
    return {"logic": "or", "conditions": [
        {"variable": f"{tool}_success_count", "operator": "greater_than", "operand": 0},
        {"variable": f"{tool}_failure_count", "operator": "greater_than", "operand": 0}]}


def tr(target, desc, cond, tool_call=False):
    t = {"target_node": target, "description": desc, "condition": cond}
    if tool_call:
        t["is_tool_call"] = True
    return t


ALWAYS = {"operator": "always"}


def api_tool(name, path, fields, required, description, retries=0):
    """fields: {field: spec}; spec holds type/description/enum/default."""
    return {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": BASE_URL + path},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": fields, "required": required},
            }},
        },
    }


CID = {"type": "string", "default": "{{customer_id}}"}


def code_node(name, code, nxt):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {
            "name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {
                "code": {"type": "string", "default": code},
                "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": [tr(nxt, "always", ALWAYS)],
    }


def ext(name, desc, enum=None, conf=0.6):
    e = {"name": name, "type": "string", "description": desc, "min_confidence": conf}
    if enum:
        e["enum_values"] = enum
    return e


def conv(name, task, on_enter, transitions, tools=None, extraction=None, max_turns=15, cap_target="close:refused"):
    n = {"name": name, "node_type": "conversation", "task_message": task, "on_enter": on_enter,
         "transitions": transitions, "max_node_turns": max_turns, "max_turn_transition": cap_target}
    if tools:
        n["tools"] = tools
    if extraction:
        n["extraction_schema"] = extraction
    return n


# ---------------------------------------------------------------- code

HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]

SETUP_CODE = r'''import datetime
HOL = set(HOLIDAYS_LIST)
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
def spoken(d):
    return DAYS[d.weekday()] + ", " + str(d.day) + " " + MONTHS[d.month - 1] + " " + str(d.year)
def is_bd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def nth_bd(d, n):
    c = 0
    while c < n:
        d = d + datetime.timedelta(days=1)
        if is_bd(d):
            c += 1
    return d
try:
    raw = str(vars.get("now") or "").strip().replace(" ", "T")
    now = datetime.datetime.fromisoformat(raw[:16])
    today = now.date()
    vars["today_iso"] = today.isoformat()
    vars["today_text"] = spoken(today)
    vars["now_time"] = now.strftime("%H:%M")
    nbd = nth_bd(today, 1)
    vars["next_bd_iso"] = nbd.isoformat()
    vars["next_bd_text"] = spoken(nbd)
    # callback window (memo OM-17): 09:00 to 17:00 both included, today or next business day, later than now
    start = now + datetime.timedelta(minutes=1)
    if start.time() < datetime.time(9, 0):
        start = datetime.datetime.combine(today, datetime.time(9, 0))
    if start.date() == today and start.time() <= datetime.time(17, 0):
        today_slot = "today, " + spoken(today) + " (" + today.isoformat() + "), from " + start.strftime("%H:%M") + " to 17:00"
    else:
        today_slot = ""
    nbd_slot = spoken(nbd) + " (" + nbd.isoformat() + "), from 09:00 to 17:00"
    if today_slot:
        vars["callback_text"] = today_slot + "; or " + nbd_slot + ". Both ends are included. Nothing earlier than " + start.strftime("%H:%M") + " today."
    else:
        vars["callback_text"] = nbd_slot + " only. Both ends are included. No callback is possible today any more."
    # calendar
    monday = today - datetime.timedelta(days=today.weekday())
    rows = []
    for i in range(0, 28):
        d = today + datetime.timedelta(days=i)
        wk = (d - monday).days // 7
        label = ["this week", "next week", "week after next", "in three weeks"][min(wk, 3)]
        kind = "business day" if is_bd(d) else ("bank holiday" if d.isoformat() in HOL else "weekend")
        tag = "TODAY, " if i == 0 else ""
        rows.append(DAYS[d.weekday()] + " " + d.isoformat() + " (" + tag + label + ", " + kind + ")")
    vars["calendar_text"] = "; ".join(rows)
    # deadlines: early band 12th business day, late band 6th business day (memo OM-17)
    for band, n in (("early", 12), ("late", 6)):
        dl = nth_bd(today, n)
        vars["deadline_" + band + "_iso"] = dl.isoformat()
        vars["deadline_" + band + "_text"] = spoken(dl)
        ok = []
        d = today
        while d <= dl:
            if is_bd(d):
                ok.append(DAYS[d.weekday()][:3] + " " + d.isoformat())
            d = d + datetime.timedelta(days=1)
        vars["valid_" + band + "_text"] = ", ".join(ok)
    # attempt 1: last business day of this week; if today is that day (or it is past), last business day of next week
    def last_bd_of_week(mon):
        d = mon + datetime.timedelta(days=6)
        while not is_bd(d) and d >= mon:
            d = d - datetime.timedelta(days=1)
        return d if d >= mon else None
    a1 = last_bd_of_week(monday)
    if a1 is None or a1 <= today:
        a1 = last_bd_of_week(monday + datetime.timedelta(days=7))
    vars["attempt1_iso"] = a1.isoformat()
    vars["attempt1_text"] = spoken(a1)
    vars["dates_state"] = "ok"
except Exception as e:
    vars["dates_state"] = "error"
'''.replace("HOLIDAYS_LIST", json.dumps(HOLIDAYS))

ACCOUNT_CODE = r'''import json, re
def as_list(v):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return None
    if isinstance(v, dict):
        if isinstance(v.get("data"), dict):
            v = v["data"].get("products")
        else:
            v = v.get("products")
    if isinstance(v, list) and v and isinstance(v[0], dict):
        return v
    return None
def money(x):
    s = "{:,.2f}".format(float(x))
    return s[:-3] if s.endswith(".00") else s
def num(x):
    f = float(x)
    return str(int(f)) if f == int(f) else str(round(f, 2))
try:
    prods = as_list(vars.get("products"))
    if prods is None:
        for k in list(vars.keys()):
            if "products" in str(k) or str(k).endswith("_response") or str(k).endswith("_response.data"):
                prods = as_list(vars.get(k))
                if prods:
                    break
    if prods is None:
        items = dict()
        for k, v in list(vars.items()):
            m = re.search(r"products(?:\.|\[)(\d+)\]?\.(\w+)$", str(k))
            if m:
                items.setdefault(int(m.group(1)), dict())[m.group(2)] = v
        prods = [items[i] for i in sorted(items)] if items else None
    p = prods[0]
    kind = str(p.get("type") or "")
    if kind == "credit_card":
        phrase = "credit card ending " + str(p.get("card_last4") or "")
        floor = p.get("minimum_payment")
        floor_name = "minimum payment"
    else:
        phrase = "personal loan" if kind == "personal_loan" else "car loan"
        floor = p.get("instalment_amount")
        floor_name = "instalment amount"
    days = int(float(p.get("days_late")))
    band = "early" if days <= 7 else "late"
    vars["product_id"] = str(p.get("product_id"))
    vars["product_phrase"] = phrase
    vars["past_due"] = num(p.get("past_due"))
    vars["past_due_text"] = money(p.get("past_due"))
    vars["floor"] = num(floor)
    vars["floor_text"] = money(floor)
    vars["floor_name"] = floor_name
    vars["days_late"] = str(days)
    vars["band"] = band
    vars["attempts_allowed"] = 1 if band == "early" else 2
    vars["deadline_iso"] = vars.get("deadline_" + band + "_iso")
    vars["deadline_text"] = vars.get("deadline_" + band + "_text")
    vars["valid_dates_text"] = vars.get("valid_" + band + "_text")
    vars["facts_state"] = "ok" if vars.get("dates_state") == "ok" else "error"
except Exception as e:
    vars["facts_state"] = "error"
'''

for c in (SETUP_CODE, ACCOUNT_CODE):
    assert "{{" not in c and "}}" not in c

# ---------------------------------------------------------------- prompts

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. Keep every turn to one or two short sentences and ask one question at a time.
Rules that hold in every step:
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue with the current question.
- If asked whether this call is a scam: say they can verify the call by phoning Freya Bank's customer service number, then continue.
- Never invent figures, dates or reasons. If a question cannot be answered from the information in this step, say you do not have that information.
- Never offer a discount, a waiver, an instalment plan or any term you were not given.
- Never say that something is recorded, booked or transferred unless a tool result says ok true. If a tool fails, say so honestly.
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- Call at most one tool per message.
- Do not say goodbye and do not end the call yourself. The system ends the call."""

NO_PURPOSE = ("Do not say why you are calling. Do not mention collections, debt, a late payment, a payment or any product. "
              "If asked what the call is about, say you can explain once the security questions are answered.")

DECLINE_RULE = ("If the customer does not want to answer, or asks what the call is about instead of answering, explain once "
                "that these questions protect their account, and ask the same question again. Explain this only once in the call.")

ID_EXTRACTION = [
    ext("id_declined",
        "yes when, in the latest message, the customer refuses to answer the security question or asks what the call is about instead of answering, "
        "AND earlier in the call the assistant already explained that the security questions protect the account. Otherwise no.",
        ["yes", "no"]),
    ext("stop_talking",
        "yes when the customer has now said at least twice in this call that they do not want to talk (for example 'I don't want to talk', "
        "'leave me alone', 'stop calling me'). Otherwise no.", ["yes", "no"]),
]

NEG_FACTS = """Facts (from the bank, use them exactly):
- Product: {{product_phrase}}. Past-due amount: {{past_due_text}} (number {{past_due}}). Floor amount ({{floor_name}}): {{floor_text}} (number {{floor}}). Days late: {{days_late}}.
- Today: {{today_text}} ({{today_iso}}).
- Deadline: {{deadline_text}} ({{deadline_iso}}). No promise date may be after it.
- Dates you may record (business days from today up to the deadline): {{valid_dates_text}}.
- Calendar (weeks run Monday to Sunday): {{calendar_text}}."""

NEG_RULES = """How to handle the customer's answer:
Amounts
- You propose every amount. Never ask how much the customer can pay.
- Any amount from {{floor_text}} up to {{past_due_text}}, both included, can be accepted.
- If the customer says the full amount is too much, offer the floor amount {{floor_text}} once, and say that the rest stays overdue.
- If the customer offers less than {{floor_text}}, say that amount cannot be recorded and offer {{floor_text}} once.
Dates
- A promise date must be one of the dates you may record.
- If the customer names a weekend day or a bank holiday that is not after the deadline, offer the next business day from the list.
- If the customer asks for a date after the deadline, say the latest date you can record is {{deadline_text}} and offer it.
- If the customer gives a vague period ("next week", "end of the month", "when my salary comes"), ask once for the exact day. If they still give none, propose {{deadline_text}}.
- "Next <weekday>" means that weekday in the following calendar week; "this <weekday>" means the one in the current week. Look the day up in the calendar.
Confirming and recording
- When the amount and the date are both acceptable, read back the product, the amount and the date, and ask "Do you confirm?".
- Only after a clear yes, call create_promise with amount as a number and date as YYYY-MM-DD. If the customer changes the amount or the date instead, check the new value with these rules and read back again.
- If create_promise does not return ok true, call it once more with the same values. Do not say the promise is recorded; the system says it after a successful result.
- One promise only. Never offer a discount, waiver or instalment plan.
- Do not repeat an offer the customer already refused."""

REFUSAL_DESC = ("yes when the customer's latest message is a flat refusal of the assistant's latest offer: a no to paying with no date and no amount proposed "
                "(a no to paying today with no other date or amount counts), a refusal of the floor amount after it was offered, a refusal of the deadline "
                "after it was offered, or no real answer to the offer. no when the customer proposes or accepts any date or any amount, says only that the "
                "full amount is too much, asks a question, confirms, or says anything else.")

INTENT_DESC = ("What the customer's latest message raises. already_paid: says they already paid this past-due amount. dispute: says the debt is not "
               "theirs, they never had this product, or the product was closed or paid off in the past. hardship: mentions illness, a death in the family "
               "or job loss (hardship wins over restructuring). restructuring: asks for a new payment plan, to pay in instalments, or for lower "
               "instalments. none: anything else.")


def create_promise_tool():
    return api_tool("create_promise", "/create_promise", {
        "customer_id": CID,
        "product_id": {"type": "string", "default": "{{product_id}}"},
        "amount": {"type": "number", "default": "{{amount}}", "description": "The confirmed amount, as a number, e.g. 120.5."},
        "date": {"type": "string", "default": "{{date}}", "description": "The confirmed payment date, YYYY-MM-DD."},
    }, ["amount", "date"], "Record the payment promise. CALL it right after the customer clearly says yes to your read-back of product, amount and date. Call it once more if it fails.")


def neg_extraction(k):
    return [
        ext(f"refusal_{k}", REFUSAL_DESC, ["yes", "no"]),
        ext("customer_intent", INTENT_DESC, ["none", "already_paid", "dispute", "hardship", "restructuring"]),
        ext("stop_talking", "yes when the customer has now said at least twice in this call that they do not want to talk. Otherwise no.", ["yes", "no"]),
    ]


def neg_common_transitions():
    return [
        tr("close:promise", "the promise was recorded", gt("create_promise_success_count", 0)),
        tr("close:service_error", "the promise failed twice", gt("create_promise_failure_count", 1)),
        tr("close:refused", "does not want to talk, said twice", var_is("stop_talking", "yes")),
        tr("close:paid", "already paid", var_is("customer_intent", "already_paid")),
        tr("close:dispute", "disputes the debt", var_is("customer_intent", "dispute")),
        tr("hardship", "hardship", var_is("customer_intent", "hardship")),
        tr("transfer_restructuring", "wants a new plan", var_is("customer_intent", "restructuring")),
    ]


# ---------------------------------------------------------------- nodes

nodes = {}

nodes["setup"] = code_node("setup", SETUP_CODE, "opening")

OPEN_ENUM = ["confirmed", "someone_else", "wrong_number", "deceased", "unclear"]
OPEN_DESC = ("Who answered, judged from the person's latest message. confirmed: only if they say yes, that's me, speaking, or say the customer's own name "
             "as theirs. someone_else: they say they are not the customer, or the customer is not available or not at home, or they are a relative or "
             "someone else. wrong_number: the number does not belong to the customer or they do not know the customer. deceased: the customer has died. "
             "unclear: anything else, including hello, go ahead, who is this, or a question.")

nodes["opening"] = conv(
    "opening",
    "You have greeted the person and asked whether you are speaking with {{title}} {{last_name}}. Do not call a tool in this turn. " + NO_PURPOSE,
    {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    [
        tr("dob_1", "confirmed", var_is("line_1", "confirmed")),
        tr("third_party", "someone else", var_is("line_1", "someone_else")),
        tr("close:wrong_number", "wrong number", var_is("line_1", "wrong_number")),
        tr("close:deceased", "deceased", var_is("line_1", "deceased")),
        tr("opening_2", "unclear, ask a second time", ALWAYS),
    ],
    extraction=[ext("line_1", OPEN_DESC, OPEN_ENUM)], max_turns=4, cap_target="close:unclear")

nodes["opening_2"] = conv(
    "opening_2",
    "The person has not confirmed who they are yet. Do not call a tool in this turn. " + NO_PURPOSE +
    " Answer a question they asked, briefly, then ask exactly: \"Am I speaking with {{title}} {{last_name}}?\"",
    {"type": "llm", "prompt": "The person did not clearly confirm who they are. If they asked a question, answer it in one short sentence "
                              "(who is calling: Freya Bank's digital assistant; robot or AI: you are Freya Bank's digital assistant; scam: they can verify the call "
                              "by phoning Freya Bank's customer service number). Do not say why you are calling. Then ask exactly: "
                              "\"Am I speaking with {{title}} {{last_name}}?\" Do not call a tool."},
    [
        tr("dob_1", "confirmed", var_is("line_2", "confirmed")),
        tr("third_party", "someone else", var_is("line_2", "someone_else")),
        tr("close:wrong_number", "wrong number", var_is("line_2", "wrong_number")),
        tr("close:deceased", "deceased", var_is("line_2", "deceased")),
        tr("close:unclear", "still unclear after the second ask", ALWAYS),
    ],
    extraction=[ext("line_2", OPEN_DESC, OPEN_ENUM)], max_turns=3, cap_target="close:unclear")

# third party ---------------------------------------------------------------

def schedule_tool():
    return api_tool("schedule_callback", "/schedule_callback", {
        "customer_id": CID,
        "date": {"type": "string", "default": "{{date}}", "description": "Callback date, YYYY-MM-DD."},
        "time": {"type": "string", "default": "{{time}}", "description": "Callback time, HH:MM, 24 hour."},
    }, ["date", "time"], "Book a callback. CALL it as soon as the person names a day and time inside the allowed callback window. Call it once more if it fails.")


TP_TASK = ("You are speaking with someone who is not {{title}} {{last_name}}. Do not say why you are calling and say nothing about any account, even if asked "
           "or if the person offers to pay or answer questions for the customer; say you can only discuss it with {{title}} {{last_name}}. "
           "Never ask this person security questions.\n"
           "Your goal: find out when {{title}} {{last_name}} can be reached.\n"
           "Allowed callback window: {{callback_text}}\n"
           "Today is {{today_text}} ({{today_iso}}), the time is {{now_time}}. Calendar: {{calendar_text}}\n"
           "- If the person names a day and time inside the window, call schedule_callback with date YYYY-MM-DD and time HH:MM. If only a time or only a day is given, ask for the missing part.\n"
           "- If schedule_callback does not return ok true, call it once more.\n")

TP_EXTRACTION = [ext("tp_status",
                     "wrong_number: the person says the number does not belong to the customer or they do not know the customer. deceased: says the customer has died. "
                     "refuses: will not say when the customer can be reached or does not know at all. none: anything else.",
                     ["none", "wrong_number", "deceased", "refuses"])]

TP_COMMON = [
    tr("close:callback", "callback booked", gt("schedule_callback_success_count", 0)),
    tr("close:callback_failed", "booking failed twice", gt("schedule_callback_failure_count", 1)),
    tr("close:wrong_number", "wrong number", var_is("tp_status", "wrong_number")),
    tr("close:deceased", "deceased", var_is("tp_status", "deceased")),
]

nodes["third_party"] = conv(
    "third_party",
    TP_TASK + "- If the day or time the person names is outside the window, call transition_to_third_party_2 (do not book it).",
    {"type": "llm", "prompt": "The person is not the customer. Do not say why you are calling. In one short sentence, ask when {{title}} {{last_name}} can be reached. Do not call a tool."},
    TP_COMMON + [
        tr("close:no_callback", "will not give a time", var_is("tp_status", "refuses")),
        tr("third_party_2", "The person named a day or a time outside the allowed callback window. Call this instead of booking.",
           {"operator": "matches_intent", "description": "The person named a callback day or time outside the allowed window"}, tool_call=True),
    ],
    tools=[schedule_tool()], extraction=TP_EXTRACTION, max_turns=8, cap_target="close:no_callback")

nodes["third_party_2"] = conv(
    "third_party_2",
    TP_TASK + "- This is the last try. If the person again names a day or time outside the window, or none, call transition_to_close_no_callback_2 (do not book it).",
    {"type": "llm", "prompt": "Say briefly that this time is not possible, and ask once for another time. Name the window: {{callback_text}} Do not call a tool."},
    TP_COMMON + [
        tr("close:no_callback", "will not give a time", var_is("tp_status", "refuses")),
        tr("close:no_callback_2", "The person again named a day or time outside the allowed callback window, or gave none. Call this instead of booking.",
           {"operator": "matches_intent", "description": "Second time outside the window"}, tool_call=True),
    ],
    tools=[schedule_tool()], extraction=TP_EXTRACTION, max_turns=6, cap_target="close:no_callback")

# identity ------------------------------------------------------------------

N_DOB, N_PHONE = 5, 4

DOB_TASK = ("Current question: the customer's date of birth. " + NO_PURPOSE + "\n"
            "When the customer says their date of birth, call {tool} with answer as YYYY-MM-DD. Convert spoken dates yourself. "
            "If the date is given only as numbers, read it as day, then month, then year (05/03/1985 is 1985-03-05). If the year is missing, ask for it.\n"
            + DECLINE_RULE + "\nDo not call any other tool.")

PHONE_TASK = ("Current question: the last four digits of the phone number the bank has on file. " + NO_PURPOSE + "\n"
              "When the customer says them, call {tool} with answer as exactly four digits (convert words to digits).\n"
              + DECLINE_RULE + "\nDo not call any other tool.")

RETRY_PROMPT = ("Look at the result of the last security check. If it has hint day_month_swapped: ask the customer to say their {what} again with the month "
                "as a word, without saying the answer was wrong. If it says ok false or could not read the value: ask them to repeat it in full. If verified is "
                "false: say it does not match our records and ask again. If there was a service error: apologise and ask again. One or two sentences. "
                "Do not call a tool in this message.")


def verify_tool(name, field, desc):
    return api_tool(name, "/verify_identity", {
        "customer_id": CID,
        "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": field},
        "answer": {"type": "string", "default": "{{answer}}", "description": desc},
    }, ["answer"], f"Check the customer's answer. CALL it every time the customer gives this answer.")


ID_COMMON = [
    tr("close:declined", "declined twice", var_is("id_declined", "yes")),
    tr("close:declined", "does not want to talk", var_is("stop_talking", "yes")),
]

for k in range(1, N_DOB + 1):
    tool = f"verify_dob_{k}"
    nxt = f"dob_{k + 1}" if k < N_DOB else "close:failed"
    on_enter = ({"type": "tts", "text": "Thank you. I need to ask two security questions first. What is your date of birth?"} if k == 1
                else {"type": "llm", "prompt": RETRY_PROMPT.format(what="date of birth")})
    nodes[f"dob_{k}"] = conv(
        f"dob_{k}", DOB_TASK.format(tool=tool), on_enter,
        [
            tr("phone_1", "date of birth verified", bool_true(f"{tool}_response.data.verified")),
            tr("close:failed", "no wrong answers left", lt(f"{tool}_response.data.wrong_answers_left", 1)),
            tr(nxt, "answer not accepted, ask again", any_result(tool)),
        ] + ID_COMMON,
        tools=[verify_tool(tool, "date_of_birth", "The date of birth as YYYY-MM-DD.")],
        extraction=ID_EXTRACTION, max_turns=6, cap_target="close:declined")

for k in range(1, N_PHONE + 1):
    tool = f"verify_phone_{k}"
    nxt = f"phone_{k + 1}" if k < N_PHONE else "close:failed"
    on_enter = ({"type": "tts", "text": "Thank you. And what are the last four digits of the phone number we have on file for you?"} if k == 1
                else {"type": "llm", "prompt": RETRY_PROMPT.format(what="last four phone digits")})
    nodes[f"phone_{k}"] = conv(
        f"phone_{k}", PHONE_TASK.format(tool=tool), on_enter,
        [
            tr("fetch_account", "both answers verified", {"logic": "or", "conditions":
                bool_true(f"{tool}_response.data.all_verified")["conditions"] + bool_true(f"{tool}_response.data.verified")["conditions"]}),
            tr("close:failed", "no wrong answers left", lt(f"{tool}_response.data.wrong_answers_left", 1)),
            tr(nxt, "answer not accepted, ask again", any_result(tool)),
        ] + ID_COMMON,
        tools=[verify_tool(tool, "phone_last4", "Exactly four digits.")],
        extraction=ID_EXTRACTION, max_turns=6, cap_target="close:declined")

# account -------------------------------------------------------------------

nodes["fetch_account"] = {
    "name": "fetch_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "account_facts",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [api_tool("get_account", "/get_account", {"customer_id": CID}, [], "Get the late products.", retries=2)],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [
        tr("close:account_error", "the lookup failed", gt("fetch_account_failure_count", 0)),
        tr("account_facts", "always", ALWAYS),
    ],
}
nodes["account_facts"] = code_node("account_facts", ACCOUNT_CODE, "facts_check")
nodes["facts_check"] = {
    "name": "facts_check", "node_type": "conversation", "passthrough": True, "passthrough_default_transition": "close:account_error",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "task_message": "Do not call a tool in this turn.",
    "transitions": [
        tr("neg_0", "facts ready", var_is("facts_state", "ok")),
        tr("close:account_error", "always", ALWAYS),
    ],
}

# negotiation ---------------------------------------------------------------

NEG_TASK_HEAD = "The customer is verified. You are on a collections call about a late payment.\n" + NEG_FACTS + "\n"

nodes["neg_0"] = conv(
    "neg_0",
    NEG_TASK_HEAD + "You asked whether the customer can make the full payment of {{past_due_text}} today.\n" + NEG_RULES,
    {"type": "tts", "text": "Thank you, {{title}} {{last_name}}. I am calling from the Freya Bank collections team about a late payment on your {{product_phrase}}. "
                            "The past-due amount is {{past_due_text}}, and it is {{days_late}} days late. Can you make this payment today?"},
    neg_common_transitions() + [tr("neg_1", "flat refusal, persuasion attempt 1", var_is("refusal_0", "yes"))],
    tools=[create_promise_tool()], extraction=neg_extraction(0), max_turns=20)

nodes["neg_1"] = conv(
    "neg_1",
    NEG_TASK_HEAD + "Persuasion attempt 1 is running: you proposed paying on {{attempt1_text}} ({{attempt1_iso}}), the full past-due amount "
    "{{past_due_text}}, or the floor {{floor_text}} if the customer had already said the full amount is too much.\n" + NEG_RULES,
    {"type": "llm", "prompt": "The customer refused. Make persuasion attempt 1 now, in one or two sentences: ask whether they can pay on {{attempt1_text}}. "
                              "Propose the full past-due amount of {{past_due_text}}; but if the customer already said the full amount is too much, propose the "
                              "floor amount {{floor_text}} instead and say the rest stays overdue. Do not ask how much they can pay. Do not call a tool."},
    neg_common_transitions() + [
        tr("neg_2", "refused attempt 1, late band has attempt 2", {"logic": "or", "conditions": [{"logic": "and", "conditions": [
            {"variable": "refusal_1", "operator": "equals", "operand": "yes"},
            {"variable": "attempts_allowed", "operator": "greater_than", "operand": 1}]}]}),
        tr("close:refused", "refused, attempts used up", var_is("refusal_1", "yes")),
    ],
    tools=[create_promise_tool()], extraction=neg_extraction(1), max_turns=20)

nodes["neg_2"] = conv(
    "neg_2",
    NEG_TASK_HEAD + "Persuasion attempt 2, the last one, is running: you proposed the floor amount {{floor_text}} on the deadline {{deadline_text}}.\n" + NEG_RULES,
    {"type": "llm", "prompt": "The customer refused again. Make persuasion attempt 2, the last one, in one or two sentences: propose paying the floor amount "
                              "{{floor_text}} on {{deadline_text}}, and say the rest stays overdue. Do not call a tool."},
    neg_common_transitions() + [tr("close:refused", "refused, attempts used up", var_is("refusal_2", "yes"))],
    tools=[create_promise_tool()], extraction=neg_extraction(2), max_turns=20)

nodes["hardship"] = conv(
    "hardship",
    NEG_TASK_HEAD + "The customer mentioned a hardship (illness, a death in the family or job loss). Make no persuasion attempt and do not propose amounts or dates. "
    "You offered to connect them with the customer support team. If the customer themselves names a payment date or amount, handle it with these rules and record it:\n"
    + NEG_RULES,
    {"type": "tts", "text": "I am very sorry to hear that. Would you like me to connect you with our customer support team?"},
    [
        tr("close:promise", "the promise was recorded", gt("create_promise_success_count", 0)),
        tr("close:service_error", "the promise failed twice", gt("create_promise_failure_count", 1)),
        tr("transfer_support", "accepts support", var_is("support_choice", "accept")),
        tr("close:hardship", "declines support", var_is("support_choice", "decline")),
        tr("close:paid", "already paid", var_is("customer_intent", "already_paid")),
        tr("close:dispute", "disputes", var_is("customer_intent", "dispute")),
    ],
    tools=[create_promise_tool()],
    extraction=[
        ext("support_choice", "accept: the customer accepts being connected to the customer support team. decline: the customer declines it and does not "
                              "name a payment date or amount. none: anything else.", ["none", "accept", "decline"]),
        ext("customer_intent", INTENT_DESC, ["none", "already_paid", "dispute", "hardship", "restructuring"]),
    ],
    max_turns=15, cap_target="close:hardship")

# transfers -----------------------------------------------------------------

def transfer_node(name, queue, closing):
    return {
        "name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "close:transfer_error",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [api_tool("transfer_to_agent", "/transfer_to_agent", {
            "customer_id": CID, "queue": {"type": "string", "enum": ["restructuring", "general", "support"], "default": queue}}, [],
            "Hand the call to a person.")],
        "response_mapping": [],
        "transitions": [
            tr(closing, "transferred", gt(f"{name}_success_count", 0)),
            tr("close:transfer_error", "always", ALWAYS),
        ],
    }


nodes["transfer_restructuring"] = transfer_node("transfer_restructuring", "restructuring", "close:transferred_restructuring")
nodes["transfer_support"] = transfer_node("transfer_support", "support", "close:transferred_support")
nodes["transfer_general"] = transfer_node("transfer_general", "general", "close:transferred_human")

# global: request for a human ---------------------------------------------

human_ok_from = [k for k in nodes if k.startswith(("dob_", "phone_", "neg_")) or k == "hardship"]

global_nodes = {
    "human_request": {
        "name": "human_request", "node_type": "conversation",
        "description": "The customer asks to speak to a human",
        "condition": {"operator": "matches_intent", "description": "The customer asks to speak to a human, a real person, an agent or an operator"},
        "on_enter": {"type": "llm", "prompt": "The customer asked for a person. If earlier in this call you already asked whether you can help instead, say you will "
                                              "connect them with a colleague now. Otherwise ask once, in one sentence, whether you can help them with something first. "
                                              "Do not call a tool."},
        "task_message": "The customer asked for a person. Ask once whether you can help first. Do not call a tool in this turn.",
        "extraction_schema": [ext("human_insist", "yes when the customer still wants or accepts a human, real person or agent after being asked whether "
                                                  "the assistant can help. no when they are happy to continue with the assistant.", ["yes", "no"])],
        "transitions": [
            tr("transfer_general", "insists on a person", var_is("human_insist", "yes")),
            tr("__previous__", "continue", ALWAYS),
        ],
        "excluded_nodes": [],  # filled after lowering: every step except human_ok_from
    }
}

body = {"initial_node": "setup", "system_prompt": SYSTEM, "nodes": nodes, "global_nodes": global_nodes,
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}

# ---------------------------------------------------------------- closing plan

BYE = " Thank you for your time, {{title}} {{last_name}}. Goodbye."
closings = {
    "promise": ({"outcome": "promise"}, "Your payment promise is recorded. You will receive a text message confirming this promise." + BYE,
                "at least one promise was recorded"),
    "paid": ({"outcome": "paid"}, "Thank you for letting me know. Payments can take one business day to appear on your account." + BYE,
             "\"I already paid\": say that payments can take one business day to appear, take no promise, and close as `paid`."),
    "transferred_restructuring": ({"outcome": "transferred", "reason": "restructuring"},
                                  "Thank you. You are now being connected with our restructuring team. Goodbye.",
                                  "Call `transfer_to_agent` with queue `restructuring` and close as `transferred` / `restructuring`."),
    "transferred_support": ({"outcome": "transferred", "reason": "support"},
                            "Thank you. You are now being connected with our customer support team. Take care. Goodbye.",
                            "If they accept, call `transfer_to_agent` with queue `support` and close as `transferred` / `support`."),
    "transferred_human": ({"outcome": "transferred", "reason": "human"},
                          "Thank you. You are now being connected with a colleague. Goodbye.",
                          "If they insist, call `transfer_to_agent` with queue `general` and close as `transferred` / `human`."),
    "transfer_error": ({"outcome": "no_promise", "reason": "service_error"},
                       "I am sorry, I could not connect you because of a technical problem. Please call Freya Bank's customer service." + BYE,
                       "If it fails again, say you could not record it and close as `no_promise` / `service_error`."),
    "refused": ({"outcome": "no_promise", "reason": "refused"}, "I understand." + BYE,
                "Do not repeat an offer the customer already refused. Close as `no_promise` / `refused`."),
    "hardship": ({"outcome": "no_promise", "reason": "hardship"}, "I understand. Take care." + BYE,
                 "If they decline, close as `no_promise` / `hardship`."),
    "dispute": ({"outcome": "no_promise", "reason": "dispute"}, "I understand, thank you for telling me. I will not take a payment promise today." + BYE,
                "\"This debt is not mine\" or \"I never had this product\": do not argue and do not take a promise. Close as `no_promise` / `dispute`."),
    "service_error": ({"outcome": "no_promise", "reason": "service_error"},
                      "I am sorry, I could not record your promise because of a technical problem." + BYE,
                      "If it fails again, say you could not record it and close as `no_promise` / `service_error`."),
    "account_error": ({"outcome": "no_promise", "reason": "service_error"},
                      "I am sorry, I cannot open your account details right now because of a technical problem. Nothing has been recorded." + BYE,
                      "If it fails again, say you could not record it and close as `no_promise` / `service_error`."),
    "failed": ({"outcome": "not_verified", "reason": "failed"},
               "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch." + BYE,
               "After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`."),
    "declined": ({"outcome": "not_verified", "reason": "declined"}, "I understand." + BYE,
                 "If they still decline, close as `not_verified` / `declined`."),
    "callback": ({"outcome": "not_reached", "reason": "callback"}, "Thank you, the callback is booked. Goodbye.",
                 "Call `schedule_callback` with the date and the time, then close as `not_reached` / `callback`."),
    "callback_failed": ({"outcome": "not_reached", "reason": "no_callback"},
                        "I am sorry, I could not book that callback because of a technical problem. We will try again another time. Thank you, goodbye.",
                        "Close as `not_reached` / `no_callback`."),
    "no_callback": ({"outcome": "not_reached", "reason": "no_callback"}, "Thank you, we will try again another time. Goodbye.",
                    "Close as `not_reached` / `no_callback`."),
    "no_callback_2": ({"outcome": "not_reached", "reason": "no_callback"}, "I am sorry, I cannot book that time. Thank you, we will try again another time. Goodbye.",
                      "Close as `not_reached` / `no_callback`."),
    "wrong_number": ({"outcome": "not_reached", "reason": "wrong_number"}, "I apologise for the trouble. Thank you, goodbye.",
                     "If the person says the number does not belong to the customer, close as `not_reached` / `wrong_number`."),
    "deceased": ({"outcome": "not_reached", "reason": "deceased"}, "I am sorry for your loss. Thank you for your time. Goodbye.",
                 "say \"I am sorry for your loss.\", ask nothing else, and close as `not_reached` / `deceased`."),
    "unclear": ({"outcome": "not_reached", "reason": "unclear"}, "I am sorry, I could not confirm who I am speaking with. Thank you for your time. Goodbye.",
                "If it is still unclear after the second ask, close as `not_reached` / `unclear`."),
}

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]},
    "fields": {"customer_id": "{{customer_id}}"},
    "closings": {cid: {"set": s, "say": say, "evidence": ev(q)} for cid, (s, say, q) in closings.items()},
    "precedence": [{"closing": "promise", "when": [{"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0}],
                    "keep": ["transferred_restructuring", "transferred_support", "transferred_human"],
                    "evidence": ev("If a transfer follows a recorded promise, close as `transferred` with that transfer's reason.")}],
}

(OUT / f"{SLOT}.body.json").write_text(json.dumps(body, indent=1) + "\n")
(OUT / f"{SLOT}.plan.json").write_text(json.dumps(plan, indent=1) + "\n")
(OUT / f"{SLOT}.human_ok.json").write_text(json.dumps(human_ok_from) + "\n")
print("ok")
