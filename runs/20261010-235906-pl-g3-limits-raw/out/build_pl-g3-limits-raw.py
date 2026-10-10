"""Generate out/pl-g3-limits-raw.workflow.json and its contract. Run from the kit folder."""
import json
from pathlib import Path

SLOT = "pl-g3-limits-raw"
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
BRIEF = f"briefs/{SLOT}.md"

# ------------------------------------------------------------------ code snippet (no double braces allowed)
FACTS_CODE = r'''
import json, re, datetime
HOL = set(['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'])
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)

def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL

def say(d):
    return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'

def money(x):
    return '%.2f' % x

def num(x):
    try:
        return float(str(x).replace(',', '').strip())
    except Exception:
        return None

def parse_products():
    raw = vars.get('products')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            try:
                raw = json.loads(raw.replace("'", '"').replace('True', 'true').replace('False', 'false').replace('None', 'null'))
            except Exception:
                raw = None
    if isinstance(raw, dict):
        raw = raw.get('products') if isinstance(raw.get('products'), list) else [raw]
    if isinstance(raw, list) and raw:
        return [p for p in raw if isinstance(p, dict)]
    found = dict()
    for k in list(vars.keys()):
        m = re.search(r'products(?:\.|\[)(\d+)\]?\.(\w+)$', str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    return [found[i] for i in sorted(found)]

try:
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?', str(vars.get('now') or '').strip())
    today = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    now_min = int(m.group(4) or 0) * 60 + int(m.group(5) or 0)

    def nth_bd(n):
        d, c = today, 0
        while c < n:
            d = d + ONE
            if isbd(d):
                c += 1
        return d

    def next_bd(d):
        d = d + ONE
        while not isbd(d):
            d = d + ONE
        return d

    def last_bd_of_week(d):
        monday = d - datetime.timedelta(days=d.weekday())
        for i in (4, 3, 2, 1, 0):
            x = monday + datetime.timedelta(days=i)
            if isbd(x):
                return x
        return None

    dl = dict(early=nth_bd(12), late=nth_bd(7))
    a1 = last_bd_of_week(today)
    if a1 is None or a1 <= today:
        a1 = last_bd_of_week(today + datetime.timedelta(days=7))
    monday = today - datetime.timedelta(days=today.weekday())
    nmonday = monday + datetime.timedelta(days=7)

    cal = []
    d = today
    end = dl['early'] + datetime.timedelta(days=10)
    while d <= end:
        if isbd(d):
            tag = 'business day'
        elif d.isoformat() in HOL:
            tag = 'bank holiday, not allowed; next business day is ' + say(next_bd(d))
        else:
            tag = 'weekend, not allowed; next business day is ' + say(next_bd(d))
        if d == today:
            tag = 'TODAY, ' + tag
        cal.append('- ' + say(d) + ': ' + tag)
        d = d + ONE

    vars['date_facts'] = '\n'.join([
        'Today is ' + say(today) + ', time ' + '%02d:%02d' % (now_min // 60, now_min % 60) + '.',
        'This week runs from ' + say(monday) + ' to ' + say(monday + datetime.timedelta(days=6)) + '.',
        'Next week runs from ' + say(nmonday) + ' to ' + say(nmonday + datetime.timedelta(days=6)) + '.',
        '"This <weekday>" is that day in this week. "Next <weekday>" is that day in next week.',
        'Calendar:',
    ] + cal)

    lines = []
    t_start = max(600, now_min + 1)
    if t_start <= 1140:
        lines.append('- today, ' + say(today) + ', from ' + '%02d:%02d' % (t_start // 60, t_start % 60) + ' to 19:00')
    nb = next_bd(today)
    lines.append('- the next business day, ' + say(nb) + ', from 10:00 to 19:00')
    vars['callback_facts'] = 'A callback can be booked only in these windows (both ends included):\n' + '\n'.join(lines) + '\nAny other day or time is outside the window.'

    names = dict(credit_card='credit card', personal_loan='personal loan', car_loan='car loan')
    products = parse_products()
    blocks = []
    first = True
    for i, p in enumerate(products):
        kind = str(p.get('type') or '')
        word = names.get(kind, kind.replace('_', ' ') or 'product')
        if kind == 'credit_card' and p.get('card_last4'):
            word = 'credit card ending ' + str(p.get('card_last4'))
        due = num(p.get('past_due')) or 0.0
        late = int(num(p.get('days_late')) or 0)
        band = 'early' if late <= 7 else 'late'
        ask = min(due, 2000.0)
        if kind == 'credit_card':
            floor = num(p.get('minimum_payment'))
        elif kind == 'car_loan' and today >= datetime.date(2026, 10, 9):
            floor = float(int(due / 2))
        else:
            floor = num(p.get('instalment_amount'))
        if floor is None:
            floor = ask
        floor = min(floor, ask)
        deadline = dl[band]
        allowed = []
        d = today
        while d <= deadline:
            if isbd(d):
                allowed.append(say(d))
            d = d + ONE
        b = ['Product ' + str(i + 1) + ': ' + word + ' (product_id ' + str(p.get('product_id')) + ').',
             'Past-due amount: ' + money(due) + '. Days late: ' + str(late) + ' (' + band + ' band).',
             'Amount to ask for first: ' + money(ask) + '.']
        if due > 2000.0:
            b.append('The past-due amount is above 2000.00: ask for 2000.00 and say the rest stays overdue. Never record more than 2000.00.')
        b += ['Floor (lowest amount that can be recorded): ' + money(floor) + '. Accept any amount from ' + money(floor) + ' to ' + money(ask) + '.',
              'Deadline (latest promise date): ' + say(deadline) + '.',
              'Allowed promise dates: ' + '; '.join(allowed) + '.',
              'Attempt 1 offer: ' + money(ask) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much) on ' + say(a1) + '.']
        if band == 'late':
            b.append('Attempt 2 offer: the floor ' + money(floor) + ' on the deadline ' + say(deadline) + '.')
        else:
            b.append('Attempt 2: none. Early band: after attempt 1 is refused, stop.')
        blocks.append('\n'.join(b))
        if first:
            first = False
            vars['band'] = band
            vars['debt_statement'] = ('I am calling from the collections team about a late payment on your ' + word +
                '. The past-due amount is ' + money(due) + ' euros, and it is ' + str(late) + ' days late.' +
                (' I can ask you for 2000.00 euros of it now; the rest stays overdue.' if due > 2000.0 else '') +
                ' Can you make this payment today?')
    vars['product_count'] = len(products)
    if blocks:
        vars['account_facts'] = '\n\n'.join(blocks)
    else:
        vars['account_facts'] = 'The account details are not available here. Read them from the get_account result in the conversation and apply the rules.'
    vars['facts_state'] = 'ok'
except Exception:
    vars['facts_state'] = 'error'
    if not vars.get('date_facts'):
        vars['date_facts'] = 'Work out dates from now: ' + str(vars.get('now'))
    if not vars.get('callback_facts'):
        vars['callback_facts'] = 'Callback window: today or the next business day, 10:00 to 19:00, later than now (' + str(vars.get('now')) + ').'
    if not vars.get('account_facts'):
        vars['account_facts'] = 'The account details are not available here. Read them from the get_account result in the conversation and apply the rules.'
'''
assert "{{" not in FACTS_CODE and "}}" not in FACTS_CODE


# ------------------------------------------------------------------ helpers
def api_tool(name, op, description, fields, required=(), max_retries=0):
    body = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    body.update(fields)
    return {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": max_retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": f"{BASE}/{op}"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": body, "required": list(required)},
            }},
        },
    }


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


ALWAYS = {"operator": "always"}

# ------------------------------------------------------------------ tools
VERIFY = api_tool(
    "verify_identity", "verify_identity",
    "Check ONE security answer. CALL it every time the customer gives a date of birth or the last four digits of the phone number. "
    "One call per answer, never two in one message.",
    {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
               "description": "Which answer this is. One of: date_of_birth, phone_last4."},
     "answer": {"type": "string", "default": "{{answer}}",
                "description": "date_of_birth: the date as YYYY-MM-DD (a date given only in numbers is day, then month, then year). phone_last4: exactly four digits."}},
    ["field", "answer"])

CREATE_PROMISE = api_tool(
    "create_promise", "create_promise",
    "Record a payment promise for one product. CALL it only after you read back product, amount and date, asked \"Do you confirm?\" "
    "and the customer clearly said yes. The amount and date must follow the account facts.",
    {"product_id": {"type": "string", "default": "{{promise_product_id}}", "description": "product_id from the account facts, copied exactly."},
     "amount": {"type": "number", "default": "{{promise_amount}}", "description": "The confirmed amount, a number like 250.00. Never above 2000.00."},
     "date": {"type": "string", "default": "{{promise_date}}", "description": "The confirmed date as YYYY-MM-DD. Must be an allowed promise date."}},
    ["product_id", "amount", "date"])

SCHEDULE = api_tool(
    "schedule_callback", "schedule_callback",
    "Book a callback. CALL it as soon as the person on the line names a day and time inside the callback window.",
    {"date": {"type": "string", "default": "{{callback_date}}", "description": "Callback date as YYYY-MM-DD."},
     "time": {"type": "string", "default": "{{callback_time}}", "description": "Callback time as HH:MM, 24 hour, from 10:00 to 19:00."}},
    ["date", "time"])


def transfer(queue, when_text):
    return api_tool(f"transfer_{queue}", "transfer_to_agent", f"Hand the call to the {queue} queue. CALL it {when_text}",
                    {"queue": {"type": "string", "enum": [queue], "default": queue, "description": f"Always {queue}."}})


T_GENERAL = transfer("general", "only when the customer asked for a human, you asked once whether you can help, and they still insist.")
T_SUPPORT = transfer("support", "only when a customer who mentioned illness, a death in the family or job loss accepts your offer to connect them with the customer support team.")
T_RESTRUCT = transfer("restructuring", "as soon as the customer asks for a new payment plan or lower instalments. Do not describe any plan.")

# ------------------------------------------------------------------ closings (engine runs close_call, then hangs up)
BYE = "Thank you for your time. Goodbye."
CLOSINGS = {
    "promise": ("promise", None, "Your promise is recorded. You will receive a text message confirming this promise. " + BYE),
    "paid": ("paid", None, "Thank you for letting me know. Payments can take one business day to appear. " + BYE),
    "transferred_restructuring": ("transferred", "restructuring", "Thank you. A colleague will continue with you now. Goodbye."),
    "transferred_human": ("transferred", "human", "Thank you. A colleague will continue with you now. Goodbye."),
    "transferred_support": ("transferred", "support", "Thank you. A colleague from customer support will continue with you now. Goodbye."),
    "refused": ("no_promise", "refused", "I understand. " + BYE),
    "hardship": ("no_promise", "hardship", "I understand. Take care. " + BYE),
    "dispute": ("no_promise", "dispute", "I understand, thank you for telling me. " + BYE),
    "service_error": ("no_promise", "service_error", "I am sorry, I could not record your promise because of a technical problem. " + BYE),
    "account_error": ("no_promise", "service_error", "I am sorry, I cannot reach your account details right now because of a technical problem. " + BYE),
    "transfer_error": ("no_promise", "service_error", "I am sorry, I could not connect you to a colleague because of a technical problem. " + BYE),
    "failed": ("not_verified", "failed", "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch. " + BYE),
    "declined": ("not_verified", "declined", "I understand. " + BYE),
    "callback": ("not_reached", "callback", "Thank you, we will call back then. Goodbye."),
    "no_callback": ("not_reached", "no_callback", BYE),
    "wrong_number": ("not_reached", "wrong_number", "I apologise for the trouble. " + BYE),
    "deceased": ("not_reached", "deceased", "I am sorry for your loss. Thank you, goodbye."),
    "unclear": ("not_reached", "unclear", BYE),
}

nodes = {}
for cid, (outcome, reason, line) in CLOSINGS.items():
    fields = {"outcome": {"type": "string", "enum": [outcome], "default": outcome}}
    if reason:
        fields["reason"] = {"type": "string", "default": reason}
    tool = api_tool("close_call", "close_call", "Record how the call ended.", fields, ["outcome"], max_retries=2)
    nodes[f"close_{cid}"] = {
        "name": f"close_{cid}", "node_type": "api_request", "passthrough": True,
        "passthrough_default_transition": "hang_up", "disable_inactivity_monitor": True,
        "on_enter": {"type": "tts", "text": line},
        "pre_actions": [tool], "response_mapping": [],
        "transitions": [go("hang_up", "always", ALWAYS)],
    }
nodes["hang_up"] = {
    "name": "hang_up", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "transitions": [], "terminal": {"type": "function", "function": {
        "name": "call_closed", "handler": "__function__:end_call",
        "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
}

# Routers: after verification, a recorded promise wins over a no-promise ending (CC-2 table: "at least one promise was recorded").
PROMISE_DONE = var("create_promise_success_count", "greater_than", 0)
for cid in ("refused", "hardship", "dispute", "service_error", "transfer_error", "paid"):
    nodes[f"end_{cid}"] = {
        "name": f"end_{cid}", "node_type": "conversation", "passthrough": True,
        "passthrough_default_transition": f"close_{cid}", "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True, "task_message": "Do not call a tool in this turn.",
        "transitions": [go("close_promise", "a promise was already recorded", when(PROMISE_DONE)),
                        go(f"close_{cid}", "always", ALWAYS)],
    }

# ------------------------------------------------------------------ shared prompt text
SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is fictional; all data is synthetic. Speak English. Keep each turn to one or two short, plain sentences. Avoid technical words.

Call variables: customer {{title}} {{first_name}} {{last_name}}. Current date and time (use this, never the real clock): {{now}}.

Rules that hold in every step:
- Before identity is verified, never say "collections", "debt", "payment", the product or why you are calling. This applies to anyone on the line, including relatives.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked "Is this a scam?": say they can verify this call by phoning Freya Bank's customer service number, then continue.
- If you cannot answer a question from the tool results, say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any term not given to you.
- Call at most one tool per message. Never combine a bank tool and a transition tool in one message.
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- If a tool result shows ok false or an error, it did not work. Say so plainly. Never say something is recorded or booked unless the tool returned ok true.
- Never say goodbye yourself. When the call must end, call the matching transition tool; the closing words are said for you."""

HUMAN_RULE = ("If the customer asks for a human: ask once whether you can help first. If they insist, call transfer_general. "
              "If a transfer fails, say so and try once more.")

NEGOTIATION_RULES = """ACCOUNT FACTS (computed for you; trust them):
{{account_facts}}

DATE FACTS:
{{date_facts}}

RULES FOR THE PROMISE
Amounts:
- Always ask for the "amount to ask for first" before anything else. Never ask "how much can you pay?". You propose every amount.
- If the customer says the full amount is too much, offer the floor, once, and say the rest stays overdue.
- If the customer proposes an amount from the floor up to the amount to ask for, both included, accept it. Below the floor: say it cannot be recorded and offer the floor once. Never record more than 2000.00 in one promise.
Dates:
- A promise date must be one of the allowed promise dates (today or later, a business day, not after the deadline).
- If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day shown in the calendar.
- If the customer names a date after the deadline, say the latest date you can record is the deadline and offer the deadline.
- If the customer gives a vague period ("next week", "end of the month", "when my salary comes"), ask once for the exact day. If they still give none, propose the deadline.
- "Next <weekday>" is that weekday in next week. "This <weekday>" is the one in this week.
- A date or an amount the customer proposes is never a refusal. Handle it with these rules.
Confirming:
- Read back the product, the amount and the date, then ask exactly "Do you confirm?". Call create_promise only after a clear yes.
- If the customer changes the date or the amount at this point, check it against these rules and read it back again.
- If create_promise fails, say so and call it once more with the same values.
- One promise per product. If there are several products, handle them one after the other.
Other situations:
- "I already paid" (this past-due amount): call transition_to_end_paid.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise, call transition_to_end_dispute.
- Request for a new payment plan or lower instalments: do not describe any plan; call transfer_restructuring.
- Illness, a death in the family or job loss: call transition_to_hardship (no persuasion).
- """ + HUMAN_RULE + """
- If the customer says twice that they do not want to talk, call transition_to_end_refused."""

NEG_TOOLS = [CREATE_PROMISE, T_RESTRUCT, T_GENERAL, T_SUPPORT]


def reply_schema(name):
    return [{
        "name": name, "type": "string", "min_confidence": 0.7,
        "enum_values": ["refusal", "hardship", "paid", "dispute", "other"],
        "description": (
            "How the customer's LATEST message answers the agent's latest offer. "
            "hardship: mentions illness, a death in the family or job loss. "
            "paid: says they already paid this past-due amount. "
            "dispute: says the debt is not theirs, they never had the product, or it was closed or paid off in the past. "
            "refusal: a flat no or a non-answer to the offer just made (for example 'no', 'I can't', 'not today') that names no date and no amount "
            "and gives none of the reasons above; also a no to the floor offer or to the deadline offer. "
            "other: anything else, including any date or amount the customer proposes, 'too much' said about the full amount the first time, "
            "questions, a yes, requests for a plan or a human."),
    }]


def neg_transitions(reply, on_refusal):
    single = [
        when(var("product_count", "equals", 1), PROMISE_DONE),
        when(var("product_count", "equals", 2), var("create_promise_success_count", "greater_than", 1)),
        when(var("product_count", "equals", 3), var("create_promise_success_count", "greater_than", 2)),
        when(var("product_count", "is_not_set"), PROMISE_DONE),
    ]
    out = [
        go("close_promise", "every product has a recorded promise", {"logic": "or", "conditions": [c["conditions"][0] for c in single]}),
        go("end_service_error", "create_promise failed twice", when(var("create_promise_failure_count", "greater_than", 1))),
        go("close_transferred_support", "transferred to support", when(var("transfer_support_success_count", "greater_than", 0))),
        go("close_transferred_restructuring", "transferred to restructuring", when(var("transfer_restructuring_success_count", "greater_than", 0))),
        go("close_transferred_human", "transferred to a human", when(var("transfer_general_success_count", "greater_than", 0))),
        go("end_transfer_error", "a transfer failed twice", any_of(
            var("transfer_support_failure_count", "greater_than", 1),
            var("transfer_restructuring_failure_count", "greater_than", 1),
            var("transfer_general_failure_count", "greater_than", 1))),
    ]
    if reply:
        out += [
            go("hardship", "customer mentioned hardship", when(var(reply, "equals", "hardship"))),
            go("end_paid", "customer already paid", when(var(reply, "equals", "paid"))),
            go("end_dispute", "customer disputes the debt", when(var(reply, "equals", "dispute"))),
        ]
        out += on_refusal(reply)
    return out


def tool_exits(hardship=True):
    t = [tool_go("end_paid", "The customer says they already paid this past-due amount."),
         tool_go("end_dispute", "The customer says the debt or product is not theirs, or that it was closed or paid off in the past."),
         tool_go("end_refused", "The customer said twice that they do not want to talk, or every allowed offer was refused.")]
    if hardship:
        t.insert(0, tool_go("hardship", "The customer mentioned illness, a death in the family or job loss."))
    return t


# ------------------------------------------------------------------ steps
nodes["setup"] = {
    "name": "setup", "node_type": "code", "passthrough": True, "passthrough_default_transition": "opening",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                     "parameters": {"type": "object", "properties": {
                         "code": {"type": "string", "default": FACTS_CODE},
                         "timeout_ms": {"type": "number", "default": 10000}}}}}],
    "transitions": [go("opening", "always", ALWAYS)],
}

nodes["opening"] = {
    "name": "opening", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": True,
    "task_message": """You have asked whether you are speaking with {{title}} {{last_name}}. Your only job in this step is to find out who is on the line.
- Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead" and "who is this" do not.
- If it is not confirmed, ask "Am I speaking with {{title}} {{last_name}}?" once more. If the customer asked a question, answer it first (you are Freya Bank's digital assistant; for a scam worry, they can phone Freya Bank's customer service number); the ask that follows is the second ask.
- If it is still unclear after the second ask, call transition_to_close_unclear.
- If the person declines to talk twice before confirming, call transition_to_close_declined.
- Do not say why you are calling.
- """ + HUMAN_RULE + """
Use only the tools listed for this step.""",
    "extraction_schema": [{
        "name": "party", "type": "string", "min_confidence": 0.7,
        "enum_values": ["customer", "other_person", "wrong_number", "deceased", "unclear"],
        "description": ("Who answered, from the person's latest message. customer: they confirm with 'yes', 'that's me', 'speaking' or the customer's own name "
                        "({{first_name}} {{last_name}}). other_person: someone else answers, says the customer is not available or is a relative. "
                        "wrong_number: the number does not belong to the customer. deceased: says the customer has died. "
                        "unclear: anything else, such as 'hello', 'go ahead', 'who is this', or a question."),
    }],
    "tools": [T_GENERAL],
    "max_node_turns": 8, "max_turn_transition": "close_unclear",
    "transitions": [
        go("close_transferred_human", "transferred to a human", when(var("transfer_general_success_count", "greater_than", 0))),
        go("close_transfer_error", "transfer failed twice", when(var("transfer_general_failure_count", "greater_than", 1))),
        go("identity", "the customer confirmed", when(var("party", "equals", "customer"))),
        go("close_deceased", "customer has died", when(var("party", "equals", "deceased"))),
        go("close_wrong_number", "wrong number", when(var("party", "equals", "wrong_number"))),
        go("third_party", "someone else answered", when(var("party", "equals", "other_person"))),
        tool_go("close_unclear", "It is still unclear who is on the line after asking twice."),
        tool_go("close_declined", "The person declined to talk twice before confirming who they are."),
    ],
}

nodes["third_party"] = {
    "name": "third_party", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Do not say why you are calling. Ask when {{title}} {{last_name}} can be reached."},
    "on_enter_first_entry_only": True,
    "task_message": """Someone other than {{title}} {{last_name}} is on the line.
- Do not say why you are calling. Say nothing about any account, even if they offer to pay or to answer security questions. Do not ask them security questions.
- Ask when {{title}} {{last_name}} can be reached.

{{callback_facts}}

- When the person names a day and a time inside a window, call schedule_callback with the date (YYYY-MM-DD) and the time (HH:MM). If it fails, say so and try once more.
- If the day or time is outside the windows, ask once for another time inside them (you may say which times work). If the second answer is also outside, call transition_to_close_no_callback. If they will not give a time, call transition_to_close_no_callback.
- If the person says the number does not belong to the customer, call transition_to_close_wrong_number.
- If the person says the customer has died, call transition_to_close_deceased at once and ask nothing else.""",
    "extraction_schema": [{
        "name": "tp_status", "type": "string", "min_confidence": 0.8,
        "enum_values": ["wrong_number", "deceased", "other"],
        "description": "wrong_number: the person says this number does not belong to the customer. deceased: says the customer has died. other: anything else.",
    }],
    "tools": [SCHEDULE],
    "max_node_turns": 10, "max_turn_transition": "close_no_callback",
    "transitions": [
        go("close_callback", "callback booked", when(var("schedule_callback_success_count", "greater_than", 0))),
        go("close_no_callback", "booking failed twice", when(var("schedule_callback_failure_count", "greater_than", 1))),
        go("close_deceased", "customer has died", when(var("tp_status", "equals", "deceased"))),
        go("close_wrong_number", "wrong number", when(var("tp_status", "equals", "wrong_number"))),
        tool_go("close_no_callback", "No callback time inside the window after asking once more, or the person will not give a time."),
        tool_go("close_wrong_number", "The number does not belong to the customer."),
        tool_go("close_deceased", "The customer has died."),
    ],
}

nodes["identity"] = {
    "name": "identity", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Thank the customer briefly. Say you need to ask two security questions, and ask for their date of birth."},
    "on_enter_first_entry_only": True,
    "task_message": """The customer confirmed who they are. Check identity before anything else. Do not say why you are calling yet.
- Ask two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
- CALL verify_identity for every answer: field date_of_birth with the date as YYYY-MM-DD, or field phone_last4 with four digits. Convert spoken dates yourself. Read a date given only as numbers as day, then month, then year (05/03/1985 is 1985-03-05).
- If the result has hint "day_month_swapped", ask the customer to say the month as a word, then verify again. This does not count as a wrong answer.
- If the result says verified false, tell the customer it did not match and ask the same question again.
- If verified true for the date of birth, ask for the last four digits of the phone number.
- If ok is false or the call failed, the answer was not checked: say so and ask again.
- If the customer does not want to answer, or asks what the call is about instead of answering, explain once that the questions protect their account. If they refuse again or ask again, call transition_to_close_declined.
- If the customer says twice that they do not want to talk, call transition_to_close_declined.
- """ + HUMAN_RULE,
    "tools": [VERIFY, T_GENERAL],
    "max_node_turns": 16, "max_turn_transition": "close_declined",
    "transitions": [
        go("fetch_account", "both answers verified", any_of(
            var("verify_identity_response.data.all_verified", "equals", "true"),
            var("verify_identity_response.data.all_verified", "equals", "True"))),
        go("close_failed", "three wrong answers", when(var("verify_identity_response.data.wrong_answers_left", "equals", "0"))),
        go("close_transferred_human", "transferred to a human", when(var("transfer_general_success_count", "greater_than", 0))),
        go("close_transfer_error", "transfer failed twice", when(var("transfer_general_failure_count", "greater_than", 1))),
        tool_go("close_declined", "The customer refused the security questions a second time, or asked a second time what the call is about instead of answering."),
    ],
}

nodes["fetch_account"] = {
    "name": "fetch_account", "node_type": "api_request", "passthrough": True,
    "passthrough_default_transition": "prepare", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [api_tool("get_account", "get_account", "Get the late products.", {}, [], max_retries=2)],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [
        go("prepare", "products received", when(var("products", "is_set"))),
        go("close_account_error", "account lookup failed", when(var("fetch_account_failure_count", "greater_than", 0))),
        go("prepare", "always", ALWAYS),
    ],
}

nodes["prepare"] = {**nodes["setup"], "name": "prepare", "passthrough_default_transition": "offer_today",
                    "transitions": [go("offer_today", "always", ALWAYS)]}

nodes["offer_today"] = {
    "name": "offer_today", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Thank the customer for confirming. Then say this, in your own short words if needed: {{debt_statement}} "
                 "If that sentence shows a placeholder, use the account facts instead: say you are calling from the collections team about a late payment, "
                 "name the product in words, state the past-due amount and the days late, and ask \"Can you make this payment today?\""},
    "on_enter_first_entry_only": True,
    "task_message": """The customer is verified. You stated the debt and asked "Can you make this payment today?" for the amount to ask for first.
If the customer agrees to pay today, use today's date. Follow the rules below.

""" + NEGOTIATION_RULES,
    "extraction_schema": reply_schema("today_reply"),
    "tools": NEG_TOOLS,
    "max_node_turns": 16, "max_turn_transition": "end_refused",
    "transitions": neg_transitions("today_reply", lambda r: [go("attempt1", "flat refusal", when(var(r, "equals", "refusal")))]) + tool_exits(),
}

nodes["attempt1"] = {
    "name": "attempt1", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Make persuasion attempt 1 from the account facts: propose the attempt 1 amount (the full amount to ask for, or the floor if the customer already said the full amount is too much) on the attempt 1 date. Ask whether they can pay that."},
    "on_enter_first_entry_only": True,
    "task_message": """The customer is verified and refused to pay today. You made persuasion attempt 1 (the attempt 1 offer in the account facts). Do not repeat an offer the customer already refused.

""" + NEGOTIATION_RULES,
    "extraction_schema": reply_schema("a1_reply"),
    "tools": NEG_TOOLS,
    "max_node_turns": 16, "max_turn_transition": "end_refused",
    "transitions": neg_transitions("a1_reply", lambda r: [
        go("attempt2", "refused, late band", when(var(r, "equals", "refusal"), var("band", "equals", "late"))),
        go("end_refused", "refused, attempts used up", when(var(r, "equals", "refusal")))]) + tool_exits(),
}

nodes["attempt2"] = {
    "name": "attempt2", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Make persuasion attempt 2 from the account facts: propose the floor amount on the deadline date. Ask whether they can pay that."},
    "on_enter_first_entry_only": True,
    "task_message": """The customer is verified and refused twice. You made persuasion attempt 2 (the floor on the deadline). This is the last attempt. Do not repeat an offer the customer already refused.

""" + NEGOTIATION_RULES,
    "extraction_schema": reply_schema("a2_reply"),
    "tools": NEG_TOOLS,
    "max_node_turns": 16, "max_turn_transition": "end_refused",
    "transitions": neg_transitions("a2_reply", lambda r: [go("end_refused", "refused the last attempt", when(var(r, "equals", "refusal")))]) + tool_exits(),
}

nodes["hardship"] = {
    "name": "hardship", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Say one short sentence of sympathy. Then offer to connect the customer with the customer support team. Make no persuasion attempt."},
    "on_enter_first_entry_only": True,
    "task_message": """The customer mentioned illness, a death in the family or job loss. Make no persuasion attempt and propose no amount or date.
- If they accept the offer to connect them with customer support, call transfer_support. If it fails, say so and try once more.
- If they decline and name no date or amount, call transition_to_end_hardship.
- If the customer names a date or an amount themselves, record a promise under the rules below.

""" + NEGOTIATION_RULES.replace("- Illness, a death in the family or job loss: call transition_to_hardship (no persuasion).\n", ""),
    "extraction_schema": [{
        "name": "hardship_reply", "type": "string", "min_confidence": 0.7,
        "enum_values": ["declines", "other"],
        "description": ("declines: the customer's latest message says no to being connected with customer support and names no payment date and no amount. "
                        "other: anything else, including a yes, a question, or any date or amount."),
    }],
    "tools": NEG_TOOLS,
    "max_node_turns": 12, "max_turn_transition": "end_hardship",
    "transitions": neg_transitions(None, None) + [
        go("end_hardship", "declined support", when(var("hardship_reply", "equals", "declines"))),
        tool_go("end_hardship", "The customer declined to be connected with customer support and named no date or amount."),
    ] + tool_exits(hardship=False),
}

workflow = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    "global_nodes": {},
    "nodes": nodes,
}

contract = {
    "terminal_tools": [{"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."},
    ]}],
    "every_call_ends_with_terminal": True,
}

Path(f"out/{SLOT}.workflow.json").write_text(json.dumps(workflow, indent=1, ensure_ascii=False) + "\n")
Path(f"out/{SLOT}.contract.json").write_text(json.dumps(contract, indent=1) + "\n")
print("written")
