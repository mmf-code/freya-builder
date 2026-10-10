"""Generate out/pl-g7-multi-raw.body.json and out/pl-g7-multi-raw.closing.json from the brief's rules."""
import json
from pathlib import Path

SLOT = "pl-g7-multi-raw"
BRIEF = f"briefs/{SLOT}.md"
OUT = Path(__file__).parent
API = json.load(open("tools/openapi.json"))
BASE = API["servers"][0]["url"].rstrip("/")
MAX_PRODUCTS = 3


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def any_of(target, desc, *checks):
    return {"target_node": target, "description": desc, "condition": {"logic": "or", "conditions": list(checks)}}


def all_of(*checks):
    return {"logic": "and", "conditions": list(checks)}


def v(var, op, operand=None):
    c = {"variable": var, "operator": op}
    if operand is not None:
        c["operand"] = operand
    return c


def is_true(var):
    return [v(var, "equals", "true"), v(var, "equals", "True")]


def tool_call(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def api_tool(name, path, description, fields, post=None, retries=0):
    tool = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name, "handler": "__function__:api_call", "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": f"{BASE}/{path}"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "properties": fields, "required": list(fields)}}}},
    }
    if post:
        tool["post_process_code"] = post
    return tool


CID = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}


def hook(lines):
    """A post-hook that sets data.what_to_do_next from the bank answer. lines: python statements setting msg."""
    body = "\n".join("        " + l for l in lines)
    return ("try:\n    if isinstance(result, dict):\n        result.pop('header', None)\n        d = result.get('data')\n"
            "        if not isinstance(d, dict):\n            d = dict()\n            result['data'] = d\n"
            "        msg = ''\n" + body + "\n        d['what_to_do_next'] = msg\nexcept Exception:\n    pass\n")


VERIFY_POST = hook([
    "if d.get('all_verified') is True:",
    "    msg = 'Both security answers passed. Say nothing yet.'",
    "elif d.get('hint') == 'day_month_swapped':",
    "    msg = 'Day and month seem swapped. Ask the customer to say the month of their birth as a word, then call verify_identity again. This is not a wrong answer.'",
    "elif d.get('verified') is True:",
    "    msg = 'This answer is correct. If it was the date of birth, now ask for the last four digits of the phone number on file.'",
    "elif d.get('verified') is False:",
    "    left = d.get('wrong_answers_left')",
    "    if left == 0:",
    "        msg = 'No attempts left. Do not state anything about the account.'",
    "    else:",
    "        msg = 'This answer is wrong. Wrong answers left: ' + str(left) + '. Ask the same question again.'",
    "else:",
    "    msg = 'The answer could not be checked. Ask the customer to repeat it, then call verify_identity again.'",
])

CALLBACK_POST = hook([
    "if d.get('ok') is True:",
    "    msg = 'The callback is booked.'",
    "else:",
    "    msg = 'The callback was NOT booked. Do not say it was. Check the date and time format and try once more.'",
])

TRANSFER_POST = hook([
    "if d.get('ok') is True:",
    "    msg = 'The transfer is done.'",
    "else:",
    "    msg = 'The transfer did NOT go through. Do not say it did. Try once more.'",
])


def promise_post(i):
    return hook([
        "if d.get('ok') is True:",
        f"    msg = 'The promise for product {i} is recorded. Continue with the next agreed product, then add the notes for products without a promise.'",
        "else:",
        f"    msg = 'The promise for product {i} was NOT recorded. Never say it was. If this was the first failure for product {i}, call create_promise_{i} again once. If it already failed before, tell the customer you could not record this promise, and later give product {i} the reason service_error.'",
    ])


def note_post(i):
    return hook([
        "if d.get('ok') is True:",
        f"    msg = 'Note for product {i} saved. Add the notes for any other product still without a recorded promise.'",
        "else:",
        f"    msg = 'The note for product {i} was not saved. Call add_note_{i} again once.'",
    ])


# ---------------------------------------------------------------- code snippets (no double braces)

HELPERS = r'''
import json, re, datetime
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
HOL = set(['2026-10-21', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'])
ONE = datetime.timedelta(days=1)
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def fmt(d):
    return DAYS[d.weekday()] + ' ' + d.isoformat()
def nth_bd(start, n):
    d = start
    c = 0
    while c < n:
        d = d + ONE
        if isbd(d):
            c += 1
    return d
def last_bd_of_week(d):
    f = d + datetime.timedelta(days=4 - d.weekday())
    while not isbd(f):
        f = f - ONE
    return f
def money(x):
    try:
        x = float(x)
    except Exception:
        return str(x)
    return str(int(x)) if x == int(x) else '%.2f' % x
now_s = str(vars.get('now') or '')
try:
    today = datetime.date.fromisoformat(now_s[:10])
except Exception:
    today = datetime.date.today()
now_hm = now_s[11:16] if len(now_s) >= 16 else '00:00'
'''

SETUP = HELPERS + r'''
try:
    vars['today_text'] = fmt(today) + (' (a business day)' if isbd(today) else ' (not a business day)')
    vars['now_time'] = now_hm
    nb = nth_bd(today, 1)
    parts = []
    if now_hm < '19:00':
        start = '10:00' if now_hm < '10:00' else 'any time later than ' + now_hm
        parts.append('today, ' + fmt(today) + ', from ' + start + ' up to 19:00')
    parts.append('the next business day, ' + fmt(nb) + ', from 10:00 to 19:00, both included')
    vars['callback_window'] = ' OR '.join(parts) + '. No other day or time is allowed.'
except Exception:
    vars['today_text'] = now_s
    vars['now_time'] = now_hm
    vars['callback_window'] = 'today or the next business day, from 10:00 to 19:00, later than now.'
'''

PREPARE = HELPERS + r'''
def as_list(p):
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            try:
                import ast
                p = ast.literal_eval(p)
            except Exception:
                p = None
    if isinstance(p, dict) and 'products' in p:
        p = p.get('products')
    return p if isinstance(p, list) else None
def load_products():
    p = as_list(vars.get('products'))
    if p:
        return p
    for k in list(vars.keys()):
        if str(k).endswith('products'):
            p = as_list(vars.get(k))
            if p:
                return p
    found = dict()
    for k in list(vars.keys()):
        m = re.search(r'products(?:\.|\[)(\d+)\]?\.(\w+)$', str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    return [found[i] for i in sorted(found)]
try:
    prods = [x for x in (load_products() or []) if isinstance(x, dict)][:3]
    blocks = []
    sentences = []
    for n, p in enumerate(prods, 1):
        t = str(p.get('type') or '')
        if t == 'credit_card':
            label = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        else:
            label = 'car loan' if t == 'car_loan' else 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment amount'
        try:
            dl = int(float(p.get('days_late')))
        except Exception:
            dl = 0
        early = dl <= 7
        deadline = nth_bd(today, 12 if early else 7)
        car_note = ''
        if t == 'car_loan':
            cap = nth_bd(today, 5)
            if cap < deadline:
                deadline = cap
                car_note = ' (car loan cap: 5th business day)'
        a1 = last_bd_of_week(today)
        if a1 <= today:
            a1 = last_bd_of_week(today + datetime.timedelta(days=7))
        if a1 > deadline:
            a1 = deadline
        valid = []
        d = today
        while d <= deadline:
            if isbd(d):
                valid.append(fmt(d))
            d = d + ONE
        past = money(p.get('past_due'))
        fl = money(floor)
        vars['p' + str(n) + '_id'] = str(p.get('product_id') or '')
        vars['p' + str(n) + '_label'] = label
        lines = ['PRODUCT ' + str(n) + ': ' + label + ' (tools: create_promise_' + str(n) + ', add_note_' + str(n) + ')',
                 '  past-due amount (full amount): ' + past,
                 '  days late: ' + str(dl) + ' (' + ('early' if early else 'late') + ' band)',
                 '  floor (' + floor_name + '): ' + fl,
                 '  deadline (latest promise date): ' + fmt(deadline) + car_note,
                 '  persuasion attempts allowed: ' + ('1' if early else '2'),
                 '  attempt 1 offer: ' + past + ' (or the floor ' + fl + ' if the customer already said the full amount is too much) on ' + fmt(a1),
                 '  attempt 2 offer: ' + ('none, this product allows only one attempt' if early else 'the floor ' + fl + ' on ' + fmt(deadline)),
                 '  valid promise dates: ' + ', '.join(valid)]
        blocks.append('\n'.join(lines))
        sentences.append('Your ' + label + ' is ' + str(dl) + ' days late, with a past-due amount of ' + past + '.')
    k = len(prods)
    vars['product_count'] = str(k)
    vars['p_facts'] = '\n\n'.join(blocks) if blocks else 'No product data.'
    if k == 1:
        vars['debt_statement'] = 'Thank you, you are verified. I am calling from the collections team about a late payment. ' + sentences[0] + ' Can you make this payment today?'
    elif k > 1:
        vars['debt_statement'] = 'Thank you, you are verified. I am calling from the collections team about late payments on ' + str(k) + ' of your products. ' + ' '.join(sentences) + ' Can you pay all of them today?'
    else:
        vars['debt_statement'] = ''
    monday = today - datetime.timedelta(days=today.weekday())
    cal = []
    for i in range(0, 22):
        d = today + datetime.timedelta(days=i)
        kind = 'business day' if isbd(d) else ('bank holiday' if d.isoformat() in HOL else 'weekend')
        cal.append(fmt(d) + (' (today)' if i == 0 else '') + ': ' + kind)
    words = []
    for w in range(7):
        this_d = monday + datetime.timedelta(days=w)
        words.append('"this ' + DAYS[w] + '" = ' + this_d.isoformat() + ', "next ' + DAYS[w] + '" = ' + (this_d + datetime.timedelta(days=7)).isoformat())
    vars['calendar_facts'] = 'Today: ' + fmt(today) + '. Bank holidays: 2026-10-21, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01 (26 October is a normal business day).\n' + '\n'.join(cal) + '\nWeekday words (weeks run Monday to Sunday): ' + '; '.join(words)
except Exception as e:
    vars['product_count'] = '0'
    vars['p_facts'] = 'No product data.'
    vars['debt_statement'] = ''
    vars['calendar_facts'] = ''
'''


def code_node(name, code, nxt, transitions):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                             "parameters": {"type": "object", "properties": {
                                 "code": {"type": "string", "default": code.strip() + "\n"},
                                 "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": transitions}


SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is calling the customer. Speak English. Keep each turn to one to three short sentences and plain words. Ask one question at a time.
Today is {{today_text}}, current time {{now_time}}. Use these for every date. Never use your own clock.

Rules that always hold:
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this call is a scam: say they can verify the call by phoning Freya Bank's customer service number, then continue.
- If asked something your information does not answer, say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan or any term you were not given.
- When a rule says to call a tool, call the tool. Saying you did it is not enough. Call at most one tool per message.
- After every tool result, read its what_to_do_next, then speak to the customer or call the next tool. Never end a turn with nothing.
- Never say something is recorded, booked or transferred unless the tool returned ok: true.
- Do not say goodbye yourself. The closing line is spoken automatically when the call ends."""

PRESENCE_DESC = ("Who answered, judged from the person's latest reply to 'Am I speaking with {{title}} {{last_name}}?'. "
                 "customer: a clear confirmation only: 'yes', 'that's me', 'speaking', or they give the customer's own name as theirs. "
                 "someone_else: another person answered (a relative, a colleague, 'he is not here', 'this is his wife'). "
                 "wrong_number: they say the number does not belong to the customer or they do not know the customer. "
                 "deceased: they say the customer has died. "
                 "not_clear: anything else, including 'hello', 'go ahead', 'who is this?', any question, or no answer.")


def presence_schema(name):
    return [{"name": name, "type": "string", "enum_values": ["customer", "someone_else", "wrong_number", "deceased", "not_clear"],
             "description": PRESENCE_DESC, "min_confidence": 0.6}]


def presence_routes(var, unclear_target):
    return [
        any_of("identity", "the customer confirmed", v(var, "equals", "customer")),
        any_of("third_party", "someone else answered", v(var, "equals", "someone_else")),
        any_of("close:wrong_number", "wrong number", v(var, "equals", "wrong_number")),
        any_of("close:deceased", "the customer has died", v(var, "equals", "deceased")),
        any_of(unclear_target, "not clear", v(var, "equals", "not_clear")),
    ]


QUIET = ("Do not mention collections, debt, payment, an account or any product. Do not call a tool in this turn.")

nodes = {}
nodes["setup"] = code_node("setup", SETUP, "opening", [always("opening")])

nodes["opening"] = {
    "name": "opening", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    "on_enter_first_entry_only": True,
    "task_message": f"You asked whether you are speaking with {{{{title}}}} {{{{last_name}}}}. If the person asks a question, answer it briefly, then ask: \"Am I speaking with {{{{title}}}} {{{{last_name}}}}?\" {QUIET}",
    "extraction_schema": presence_schema("presence"),
    "max_node_turns": 3, "max_turn_transition": "opening_again",
    "transitions": presence_routes("presence", "opening_again"),
}

nodes["opening_again"] = {
    "name": "opening_again", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "If the person asked a question, answer it in one short sentence first (robot or AI: you are Freya Bank's digital assistant; scam: they can verify the call by phoning Freya Bank's customer service number; who is calling: Freya Bank's digital assistant). Then ask: \"Am I speaking with {{title}} {{last_name}}?\" " + QUIET},
    "on_enter_first_entry_only": True,
    "task_message": f"This is your second and last ask. Answer a question briefly if there is one, then ask: \"Am I speaking with {{{{title}}}} {{{{last_name}}}}?\" {QUIET}",
    "extraction_schema": presence_schema("presence_again"),
    "max_node_turns": 2, "max_turn_transition": "close:unclear",
    "transitions": presence_routes("presence_again", "close:unclear"),
}

nodes["third_party"] = {
    "name": "third_party", "node_type": "conversation",
    "on_enter": {"type": "llm", "prompt": "Someone other than {{title}} {{last_name}} answered. Do not say why you are calling. Ask when {{title}} {{last_name}} can be reached. Do not call a tool in this turn."},
    "on_enter_first_entry_only": True,
    "task_message": """You are speaking with someone other than {{title}} {{last_name}}.
- Never say why you are calling. Say nothing beyond: you are a digital assistant calling from Freya Bank and the call is recorded. Say nothing about any account, debt, payment or product, even if they ask or offer to pay. Never ask them security questions.
- Your only goal: find when {{title}} {{last_name}} can be reached.
- Allowed callback times: {{callback_window}}
- When they give a day and an exact time inside the allowed times, call schedule_callback with date as YYYY-MM-DD and time as HH:MM (24 hour).
- If they give only a day, or a vague time such as "afternoon", ask for the exact time.
- If their proposal is outside the allowed times, say you can only call back at the allowed times, state them, and ask once for another time. If the next proposal is also outside them, end with the no-callback action. Do not book anything.
- If they say the number does not belong to the customer, end with the wrong-number action.
- If they say the customer has died, end with the deceased action at once, asking nothing else.
- If they say they are in fact {{title}} {{last_name}}, or hand the phone to them, use the customer-on-the-line action.""",
    "tools": [api_tool("schedule_callback", "schedule_callback",
                       "Book a callback. CALL it as soon as the person gives a day and an exact time inside the allowed callback times.",
                       {**CID,
                        "date": {"type": "string", "description": "Callback date as YYYY-MM-DD.", "default": "{{callback_date}}"},
                        "time": {"type": "string", "description": "Callback time as HH:MM, 24 hour.", "default": "{{callback_time}}"}},
                       CALLBACK_POST)],
    "max_node_turns": 12, "max_turn_transition": "close:no_callback",
    "transitions": [
        any_of("close:callback", "the callback is booked", v("schedule_callback_success_count", "greater_than", 0)),
        any_of("close:no_callback", "booking failed twice", v("schedule_callback_failure_count", "greater_than", 1)),
        tool_call("close:deceased", "The person said the customer has died."),
        tool_call("close:wrong_number", "The person said this number does not belong to the customer."),
        tool_call("close:no_callback", "The person's second proposed callback time is also outside the allowed times, or they will not give any time."),
        tool_call("opening_again", "The person says they are in fact the customer, or hands the phone to the customer."),
    ],
}

nodes["identity"] = {
    "name": "identity", "node_type": "conversation",
    "on_enter": {"type": "tts", "text": "Thank you. First I need to ask two security questions. What is your date of birth?"},
    "on_enter_first_entry_only": True,
    "task_message": """The person confirmed they are {{title}} {{last_name}}. You check their identity with two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
Before both pass, say nothing about collections, debt, payment, any product or the account. If asked what the call is about, the first time say you can explain after the security questions.
Tool rules:
- After every date-of-birth answer, call verify_identity with field date_of_birth and the date as YYYY-MM-DD, whatever way the customer said it. A date said only as numbers is day, then month, then year: "03/04/1985" is 1985-04-03. If the date is incomplete, ask for the missing part before calling.
- When the date of birth has passed, ask for the last four digits of the phone number on file. Call verify_identity with field phone_last4 and the four digits.
- Follow what_to_do_next in every result. After a wrong answer with attempts left, ask the same question again. A day_month_swapped hint: ask them to say the month as a word, then call again.
- If the customer will not answer, says they do not want to talk, or asks what the call is about instead of answering: the first time, explain once that these questions protect their account and ask again. The second time, use the declined action.
- If the customer asks for a human: the first time, ask once whether you can help. If they insist, call transfer_general.""",
    "tools": [
        api_tool("verify_identity", "verify_identity",
                 "Check one security answer. CALL it every time the customer gives a date of birth or the last four phone digits.",
                 {**CID,
                  "field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "description": "Which question this answers: date_of_birth or phone_last4.", "default": "{{verify_field}}"},
                  "answer": {"type": "string", "description": "date_of_birth as YYYY-MM-DD (numbers only: day, month, year). phone_last4 as four digits.", "default": "{{verify_answer}}"}},
                 VERIFY_POST),
        api_tool("transfer_general", "transfer_to_agent",
                 "Transfer the call to a person. CALL it only when the customer insists on a human after you asked once whether you can help.",
                 {**CID, "queue": {"type": "string", "enum": ["general"], "default": "general"}}, TRANSFER_POST),
    ],
    "max_node_turns": 20, "max_turn_transition": "close:declined",
    "transitions": [
        any_of("fetch_account", "both answers verified", *is_true("verify_identity_response.data.all_verified")),
        any_of("close:failed", "no wrong answers left", v("verify_identity_response.data.wrong_answers_left", "equals", "0")),
        any_of("close:human", "transferred", v("transfer_general_success_count", "greater_than", 0), v("transfer_general_failure_count", "greater_than", 1)),
        tool_call("close:declined", "The customer refused the security questions a second time (or asked again what the call is about instead of answering, or said again they do not want to talk), after you already explained once that the questions protect their account."),
    ],
}

nodes["fetch_account"] = {
    "name": "fetch_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare",
    "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
    "pre_actions": [api_tool("get_account", "get_account", "The customer's late products.", dict(CID), retries=2)],
    "response_mapping": [{"path": "data.products", "variable": "products"}],
    "transitions": [always("prepare")],
}

nodes["prepare"] = code_node("prepare", PREPARE, "close:account_unavailable", [
    any_of("negotiate_1", "one product", v("product_count", "equals", "1")),
    any_of("negotiate_2", "two products", v("product_count", "equals", "2")),
    any_of("negotiate_3", "three products", v("product_count", "equals", "3")),
    always("close:account_unavailable"),
])


def negotiate_prompt(k):
    today_q = "pay all of them today" if k > 1 else "make this payment today"
    ids = ", ".join(str(i) for i in range(1, k + 1))
    return f"""The customer is verified. You already named every late product and asked whether they can {today_q}.

PRODUCTS, in this order:
{{{{p_facts}}}}

CALENDAR:
{{{{calendar_facts}}}}

GETTING PROMISES
1. You propose every amount. Never ask how much they can pay. A promise is one product, one amount, one date.
2. If they say yes to paying today, each promise is the full past-due amount dated today (today must be a valid promise date). Go to step 11.
3. If they say no to today with no date and no amount, do not ask about today again. Go through the products one at a time, in the order above. Start each product at its attempt 1 offer. If the customer flatly refuses or does not answer, make the attempt 2 offer if that product has one. If that product has no attempts left, stop: it gets no promise, reason refused. Never repeat an offer already refused. Then move to the next product.
4. A date or an amount the customer proposes is never a refusal. Check it against that product's facts:
   - Dates: the date must be one of the product's valid promise dates. A weekend day or holiday not after the deadline: offer the next business day. A date after the deadline: say the latest date you can record is the deadline and offer it; if they refuse it, that is a flat refusal. A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day; if they still give none, propose the deadline. Resolve "this <weekday>" and "next <weekday>" with the calendar.
   - Amounts: from the floor up to the full past-due amount, both included: accept. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept, that is a flat refusal. "The full amount is too much": offer the floor once and say the rest stays overdue; if they refuse it, that is a flat refusal.
5. If they name one date for everything and it is after one product's deadline, that product uses its own deadline. Say so in the read-back. The other products keep the named date.
6. Illness, a death in the family or job loss: say one short sentence of sympathy and make no persuasion attempt. Offer to connect them with the customer support team. If they accept, call transfer_support. If they decline, every product not yet agreed gets reason hardship. If they still name a date or an amount themselves, handle it as a promise.
7. "I already paid" for a product: say payments can take one business day to appear. That product gets no promise, reason already_paid. Continue with the other products.
8. "This is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue. That product gets no promise, reason dispute. Continue with the other products.
9. A request for a new payment plan or lower instalments: do not describe any plan. Call transfer_restructuring at once. Do not record agreed promises that are not yet recorded. Add no notes.
10. A request for a human: the first time, ask once whether you can help. If they insist, call transfer_general. Add no notes. If they say twice that they do not want to talk, every product without a promise gets reason refused; go to step 11.

CONFIRMING AND RECORDING
11. When every product is either agreed or has a no-promise reason: if at least one product is agreed, read ALL agreed promises back together (product, amount, date) and ask "Do you confirm?". If they change a date or an amount, check it again with step 4 and read back again. If no product is agreed, go to step 13.
12. After a clear yes, call create_promise_N for each agreed product, one per message, where N is the product number. If one fails, call it once more. If it fails again, tell the customer you could not record that promise; that product gets reason service_error. A recorded promise cannot be changed or cancelled in this call; they can change it in the mobile app.
13. Last, call add_note_N for every product without a recorded promise, with its reason. Never add a note before all promises are recorded, and never add a note when the call is transferred.
Products here: {ids}. Use only the tools of these products."""


def resolved(i):
    return [v(f"create_promise_{i}_success_count", "greater_than", 0), v(f"add_note_{i}_success_count", "greater_than", 0)]


def negotiate(k):
    tools = []
    for i in range(1, k + 1):
        tools.append(api_tool(f"create_promise_{i}", "create_promise",
                              f"Record the payment promise for product {i}. CALL it only after the customer gave a clear yes to the read-back.",
                              {**CID, "product_id": {"type": "string", "default": f"{{{{p{i}_id}}}}"},
                               "amount": {"type": "number", "description": f"Agreed amount for product {i}, a number.", "default": f"{{{{promise_amount_{i}}}}}"},
                               "date": {"type": "string", "description": f"Agreed date for product {i}, YYYY-MM-DD.", "default": f"{{{{promise_date_{i}}}}}"}},
                              promise_post(i)))
    for i in range(1, k + 1):
        tools.append(api_tool(f"add_note_{i}", "add_note",
                              f"Record why product {i} ended without a promise. CALL it only at the very end, after all promises are recorded, for product {i} if it has no recorded promise. Never call it when the call is transferred.",
                              {**CID, "product_id": {"type": "string", "default": f"{{{{p{i}_id}}}}"},
                               "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "already_paid", "service_error"],
                                          "description": "One of: refused, hardship, dispute, already_paid, service_error.", "default": f"{{{{note_reason_{i}}}}}"}},
                              note_post(i)))
    tools.append(api_tool("transfer_restructuring", "transfer_to_agent",
                          "Transfer to the restructuring team. CALL it at once when the customer asks for a new payment plan or lower instalments.",
                          {**CID, "queue": {"type": "string", "enum": ["restructuring"], "default": "restructuring"}}, TRANSFER_POST))
    tools.append(api_tool("transfer_support", "transfer_to_agent",
                          "Transfer to the customer support team. CALL it when a customer in hardship accepts your offer to connect them with support.",
                          {**CID, "queue": {"type": "string", "enum": ["support"], "default": "support"}}, TRANSFER_POST))
    tools.append(api_tool("transfer_general", "transfer_to_agent",
                          "Transfer to a person. CALL it only when the customer insists on a human after you asked once whether you can help.",
                          {**CID, "queue": {"type": "string", "enum": ["general"], "default": "general"}}, TRANSFER_POST))

    tr = []
    for tool, cid in (("transfer_restructuring", "restructuring"), ("transfer_support", "support"), ("transfer_general", "human")):
        tr.append(any_of(f"close:{cid}", f"transferred ({cid})", v(f"{tool}_success_count", "greater_than", 0), v(f"{tool}_failure_count", "greater_than", 1)))

    # every product resolved: one AND group per combination of (promise or note) per product
    combos = [[]]
    for i in range(1, k + 1):
        combos = [c + [r] for c in combos for r in resolved(i)]
    some_promise = [c for c in combos if any("create_promise" in x["variable"] for x in c)]
    partial = []
    for c in some_promise:
        for j, x in enumerate(c, 1):
            if x["variable"].startswith("add_note_"):
                partial.append(all_of(*c, v(f"add_note_{j}_args.reason", "equals", "service_error")))
    tr.append(any_of("close:promise_partial", "promises recorded, one failed", *partial) if partial else None)
    tr.append(any_of("close:promise", "at least one promise recorded and every product resolved", *[all_of(*c) for c in some_promise]))
    tr = [t for t in tr if t]
    all_notes = [v(f"add_note_{i}_success_count", "greater_than", 0) for i in range(1, k + 1)]
    # no promise: reason of the first product whose note is not already_paid
    for i in range(1, k + 1):
        earlier_paid = [v(f"add_note_{j}_args.reason", "equals", "already_paid") for j in range(1, i)]
        for reason in ("refused", "hardship", "dispute", "service_error"):
            tr.append(any_of(f"close:{reason}", f"no promise, first reason {reason}",
                             all_of(*all_notes, *earlier_paid, v(f"add_note_{i}_args.reason", "equals", reason))))
    tr.append(any_of("close:paid", "every product already paid",
                     all_of(*all_notes, *[v(f"add_note_{j}_args.reason", "equals", "already_paid") for j in range(1, k + 1)])))
    return {
        "name": f"negotiate_{k}", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "{{debt_statement}}"}, "on_enter_first_entry_only": True,
        "task_message": negotiate_prompt(k),
        "tools": tools,
        "max_node_turns": 60, "max_turn_transition": "close:refused",
        "transitions": tr,
    }


for k in range(1, MAX_PRODUCTS + 1):
    nodes[f"negotiate_{k}"] = negotiate(k)

body = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "test_variables": {"first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}


def ev(quote, source=BRIEF):
    return [{"source": source, "quote": quote}]


BYE = "Thank you for your time. Goodbye."
closings = {
    "promise": {"set": {"outcome": "promise"}, "say": "Your promise is recorded. You will receive a text message confirming this promise. " + BYE,
                "evidence": ev("Outcome: promise; Reason: none; When: at least one promise was recorded")},
    "promise_partial": {"set": {"outcome": "promise"},
                        "say": "The other promises are recorded, but one promise could not be recorded because of a technical problem. You will receive a text message confirming this promise. " + BYE,
                        "evidence": ev("If one `create_promise` fails twice, keep the promises that were recorded")},
    "paid": {"set": {"outcome": "paid"}, "say": "Payments can take one business day to appear. " + BYE, "evidence": ev("close as `paid`")},
    "restructuring": {"set": {"outcome": "transferred", "reason": "restructuring"}, "say": "I am transferring you now. " + BYE,
                      "evidence": ev("close as `transferred` / `restructuring`")},
    "support": {"set": {"outcome": "transferred", "reason": "support"}, "say": "I am transferring you now. " + BYE,
                "evidence": ev("close as `transferred` / `support`")},
    "human": {"set": {"outcome": "transferred", "reason": "human"}, "say": "I am transferring you now. " + BYE,
              "evidence": ev("close as `transferred` / `human`")},
    "refused": {"set": {"outcome": "no_promise", "reason": "refused"}, "say": BYE, "evidence": ev("Close as `no_promise` / `refused`.")},
    "hardship": {"set": {"outcome": "no_promise", "reason": "hardship"}, "say": "Take care. " + BYE, "evidence": ev("close as `no_promise` / `hardship`")},
    "dispute": {"set": {"outcome": "no_promise", "reason": "dispute"}, "say": "Thank you for letting us know. " + BYE, "evidence": ev("Close as `no_promise` / `dispute`")},
    "service_error": {"set": {"outcome": "no_promise", "reason": "service_error"}, "say": "I am sorry that I could not record your promise. " + BYE,
                      "evidence": ev("close as `no_promise` / `service_error`")},
    "account_unavailable": {"set": {"outcome": "no_promise", "reason": "service_error"},
                            "say": "I am sorry, I cannot reach your account details right now. " + BYE,
                            "evidence": ev("close as `no_promise` / `service_error`")},
    "failed": {"set": {"outcome": "not_verified", "reason": "failed"},
               "say": "I am sorry, I could not verify your identity, so I cannot continue. Please use the Freya Bank mobile app or visit a branch. " + BYE,
               "evidence": ev("Close as `not_verified` / `failed`")},
    "declined": {"set": {"outcome": "not_verified", "reason": "declined"}, "say": "I understand. " + BYE,
                 "evidence": ev("close as `not_verified` / `declined`")},
    "callback": {"set": {"outcome": "not_reached", "reason": "callback"}, "say": "Thank you, we will call back then. Goodbye.",
                 "evidence": ev("close as `not_reached` / `callback`")},
    "no_callback": {"set": {"outcome": "not_reached", "reason": "no_callback"}, "say": BYE,
                    "evidence": ev("Close as `not_reached` / `no_callback`")},
    "wrong_number": {"set": {"outcome": "not_reached", "reason": "wrong_number"}, "say": "Sorry for the trouble. " + BYE,
                     "evidence": ev("close as `not_reached` / `wrong_number`")},
    "deceased": {"set": {"outcome": "not_reached", "reason": "deceased"}, "say": "I am sorry for your loss. Thank you. Goodbye.",
                 "evidence": ev("close as `not_reached` / `deceased`")},
    "unclear": {"set": {"outcome": "not_reached", "reason": "unclear"}, "say": BYE, "evidence": ev("close as `not_reached` / `unclear`")},
}

KEEP_TRANSFERS = ["restructuring", "support", "human", "promise_partial"]
precedence = [
    {"closing": "promise", "when": [v(f"create_promise_{i}_success_count", "greater_than", 0)], "keep": KEEP_TRANSFERS,
     "evidence": ev("With several products, `promise` wins whenever at least one promise was recorded, except rule 10 above.")}
    for i in range(1, MAX_PRODUCTS + 1)
] + [
    {"closing": "failed", "when": [v("verify_identity_response.data.wrong_answers_left", "equals", "0")], "keep": ["human"],
     "evidence": ev("After three wrong answers, do not state the debt.")},
]

plan = {
    "terminal": {"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": BRIEF, "quote": "Every call ends with exactly one `close_call`"}]},
    "fields": {"customer_id": "{{customer_id}}"},
    "closings": closings,
    "precedence": precedence,
}

(OUT / f"{SLOT}.body.json").write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
(OUT / f"{SLOT}.closing.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n")
print("written")
