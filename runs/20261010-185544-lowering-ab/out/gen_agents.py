"""Write out/<slot>.body.json and out/<slot>.closing.json for brief-a (one product) and brief-b (up to three)."""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1/"
A, B = "briefs/brief-a.md", "briefs/brief-b.md"
API = "tools/openapi.json"

# ------------------------------------------------------------------ code run in the sandbox (no double braces)

DATE_CODE = r'''
import datetime
HOL = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
ONE = datetime.timedelta(days=1)
def isbd(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def nice(d):
    return DAYS[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year) + ' (' + d.isoformat() + ')'
def nth_bd(d, n):
    c = 0
    x = d
    while c < n:
        x = x + ONE
        if isbd(x):
            c += 1
    return x
def next_bd(d):
    x = d + ONE
    while not isbd(x):
        x = x + ONE
    return x
def last_bd_of_week(mon):
    for i in range(4, -1, -1):
        d = mon + datetime.timedelta(days=i)
        if isbd(d):
            return d
    return None
try:
    now = datetime.datetime.fromisoformat(str(vars.get('now') or '')[:16])
except Exception:
    now = datetime.datetime(2026, 10, 14, 11, 0)
today = now.date()
monday = today - datetime.timedelta(days=today.weekday())
deadline_early = nth_bd(today, 12)
deadline_late = nth_bd(today, 7)
a1 = last_bd_of_week(monday)
if a1 is None or a1 <= today:
    a1 = last_bd_of_week(monday + datetime.timedelta(days=7))
nbd = next_bd(today)
'''

SETUP_CODE = DATE_CODE + r'''
try:
    lines = []
    lines.append('Now: ' + nice(today) + ', time ' + now.strftime('%H:%M') + '. Use this, never the real clock.')
    lines.append('This week: Monday ' + monday.isoformat() + ' to Sunday ' + (monday + datetime.timedelta(days=6)).isoformat() + '. Next week: Monday ' + (monday + datetime.timedelta(days=7)).isoformat() + ' to Sunday ' + (monday + datetime.timedelta(days=13)).isoformat() + '.')
    cb = 'Callback window: '
    if isbd(today) and now.hour < 19:
        start = now + datetime.timedelta(minutes=1)
        cb += 'today ' + nice(today) + ' from ' + max(start.strftime('%H:%M'), '10:00') + ' to 19:00, or '
    cb += 'the next business day ' + nice(nbd) + ' from 10:00 to 19:00 (both included). Any other day or time is outside the window.'
    lines.append(cb)
    vars['date_facts'] = '\n'.join(lines)
    vars['callback_window'] = cb
except Exception:
    vars['date_facts'] = 'Now: ' + str(vars.get('now'))
    vars['callback_window'] = 'today or the next business day, 10:00 to 19:00, later than now'
'''

ACCOUNT_CODE = DATE_CODE + r'''
import json
import re
def parse(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        s = v.strip()
        try:
            x = json.loads(s)
            if isinstance(x, list):
                return x
            if isinstance(x, dict) and isinstance(x.get('products'), list):
                return x['products']
        except Exception:
            pass
        try:
            import ast
            x = ast.literal_eval(s)
            if isinstance(x, list):
                return x
        except Exception:
            pass
    if isinstance(v, dict) and isinstance(v.get('products'), list):
        return v['products']
    return None
products = None
for key in ['products_json', 'products']:
    if products is None:
        products = parse(vars.get(key))
if products is None:
    for k in list(vars.keys()):
        if k.endswith('data.products') or k.endswith('data.products_json'):
            products = parse(vars.get(k))
            if products:
                break
if products is None:
    rows = dict()
    for k in list(vars.keys()):
        m = re.search(r'data\.products[\.\[](\d+)\]?\.(\w+)$', k)
        if m:
            rows.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    if rows:
        products = [rows[i] for i in sorted(rows)]
def num(x):
    try:
        return float(x)
    except Exception:
        return 0.0
def money(x):
    return '%.2f' % num(x)
try:
    if not products:
        raise ValueError('no products')
    title = str(vars.get('title') or '')
    last = str(vars.get('last_name') or '')
    facts = []
    spoken = []
    for i, p in enumerate(products):
        t = str(p.get('type') or '')
        if t == 'credit_card':
            name = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = num(p.get('minimum_payment'))
            floor_name = 'minimum payment'
        elif t == 'car_loan':
            name = 'car loan'
            floor = num(p.get('instalment_amount'))
            floor_name = 'instalment amount'
        else:
            name = 'personal loan'
            floor = num(p.get('instalment_amount'))
            floor_name = 'instalment amount'
        dl = int(num(p.get('days_late')))
        if dl <= 7:
            band, deadline, attempts = 'early', deadline_early, 1
        else:
            band, deadline, attempts = 'late', deadline_late, 2
        a1d = a1 if a1 <= deadline else deadline
        f = ('Product ' + str(i + 1) + ': product_id ' + str(p.get('product_id')) + ', ' + name +
             '. Past-due amount (full amount) ' + money(p.get('past_due')) + ', ' + str(dl) + ' days late. Band ' + band +
             '. Deadline (latest promise date) ' + nice(deadline) + '. Persuasion attempts allowed: ' + str(attempts) + ' (then stop for this product)' +
             '. Floor (' + floor_name + ') ' + money(floor) + '. Attempt 1: propose ' +
             ('the full amount ' + money(p.get('past_due'))) + ' (or the floor ' + money(floor) +
             ' if the customer already said the full amount is too much) on ' + nice(a1d) + '.')
        if attempts == 2:
            f += ' Attempt 2: propose the floor ' + money(floor) + ' on the deadline ' + nice(deadline) + '.'
        else:
            f += ' No attempt 2 for this product.'
        facts.append(f)
        spoken.append((name, money(p.get('past_due')), dl))
    cal = []
    dls = []
    for i, p in enumerate(products):
        dl0 = int(num(p.get('days_late')))
        dls.append(deadline_early if dl0 <= 7 else deadline_late)
    end = max(dls) + datetime.timedelta(days=10)
    d = today
    while d <= end:
        if isbd(d):
            tag = 'business day'
        elif d.isoformat() in HOL:
            tag = 'Freya Bank HOLIDAY, not a business day'
        else:
            tag = 'weekend, not a business day'
        acts = []
        for i in range(len(products)):
            dd = dls[i]
            if d > dd:
                a = 'after the deadline, offer the deadline ' + nice(dd)
            elif not isbd(d):
                a = 'offer the next business day ' + nice(next_bd(d))
            else:
                a = 'can be recorded'
            if d == dd:
                a += ' (this is the deadline)'
            acts.append(('product ' + str(i + 1) + ': ' if len(products) > 1 else '') + a)
        cal.append(nice(d) + (' TODAY' if d == today else '') + ', ' + tag + ' -> ' + '; '.join(acts))
        d = d + ONE
    cal.append('Any date before today cannot be recorded. Any date after ' + nice(end) + ' is after every deadline: offer the deadline.')
    vars['account_facts'] = '\n'.join(facts)
    vars['calendar'] = '\n'.join(cal)
    vars['product_count'] = str(len(products))
    vars['first_product_id'] = str(products[0].get('product_id'))
    who = (title + ' ' + last).strip()
    if len(spoken) == 1:
        n, amt, dl = spoken[0]
        vars['debt_statement'] = ('Thank you, ' + who + ', you are verified. I am calling from the collections team about a late payment on your ' +
                                  n + '. The past-due amount is ' + amt + ', and it is ' + str(dl) + ' days late. Can you make this payment today?')
    else:
        parts = ['Your ' + n + ' has ' + amt + ' past due and is ' + str(dl) + ' days late.' for (n, amt, dl) in spoken]
        vars['debt_statement'] = ('Thank you, ' + who + ', you are verified. I am calling from the collections team about late payments on ' +
                                  str(len(spoken)) + ' products. ' + ' '.join(parts) + ' Can you pay all of them today?')
    vars['account_state'] = 'ok'
except Exception:
    vars['account_facts'] = 'Read the products from the get_account result in the conversation. Deadlines: days_late 1 to 7 gives ' + nice(deadline_early) + '; days_late 8 to 45 gives ' + nice(deadline_late) + '. Attempt 1 date: ' + nice(a1) + '.'
    vars['calendar'] = 'Holidays: ' + ', '.join(HOL) + '. Business days are Monday to Friday except these.'
    vars['product_count'] = '0'
    vars['debt_statement'] = ''
    vars['account_state'] = 'unparsed'
'''

GET_ACCOUNT_POST = r'''
try:
    import json
    result.pop('header', None)
    d = result.get('data')
    if isinstance(d, dict) and isinstance(d.get('products'), list):
        d['products_json'] = json.dumps(d['products'])
except Exception:
    pass
'''

VERIFY_POST = r'''
try:
    result.pop('header', None)
    d = result.get('data')
    if not isinstance(d, dict):
        d = dict()
        result['data'] = d
    left = d.get('wrong_answers_left')
    if str(d.get('all_verified')).lower() == 'true':
        d['verify_state'] = 'verified'
        d['what_to_do_next'] = 'Both answers are correct. Identity is verified.'
    elif str(left) == '0':
        d['verify_state'] = 'failed'
        d['what_to_do_next'] = 'Three wrong answers. The check has ended. Say nothing about the account.'
    elif d.get('hint') == 'day_month_swapped':
        d['verify_state'] = 'retry'
        d['what_to_do_next'] = 'Day and month look swapped. Ask the customer to say the month of birth as a word, then call verify_identity again. This retry is not a wrong answer.'
    elif str(d.get('verified')).lower() == 'true':
        d['verify_state'] = 'next'
        d['what_to_do_next'] = 'Correct. Now ask for the last four digits of the phone number on file.'
    elif str(d.get('verified')).lower() == 'false':
        d['verify_state'] = 'wrong'
        d['what_to_do_next'] = 'That answer is wrong. Wrong answers left: ' + str(left) + '. Ask the same question again. Do not hint at the right answer.'
    else:
        d['verify_state'] = 'unreadable'
        d['what_to_do_next'] = 'The answer was not accepted because it could not be read. It is not a wrong answer. Ask the same question again.'
except Exception:
    pass
'''

PROMISE_POST_A = r'''
try:
    result.pop('header', None)
    d = result.get('data')
    if not isinstance(d, dict):
        d = dict(ok=False)
        result['data'] = d
    if str(d.get('ok')).lower() == 'true':
        d['what_to_do_next'] = 'The promise is recorded.'
    else:
        d['what_to_do_next'] = 'The promise was NOT recorded. Tell the customer it did not go through. Never say it is recorded.'
except Exception:
    pass
'''

PROMISE_POST_B = r'''
try:
    result.pop('header', None)
    d = result.get('data')
    if not isinstance(d, dict):
        d = dict(ok=False)
        result['data'] = d
    if str(d.get('ok')).lower() == 'true':
        d['what_to_do_next'] = 'This promise is recorded. Call create_promise for the next confirmed product, if any is left.'
    else:
        d['what_to_do_next'] = ('This promise was NOT recorded. If this is the first failure for this product, call create_promise once more with exactly the same values. '
                                'If it already failed once before, do not try again: this product gets an add_note with reason service_error at the end, and you tell the customer you could not record it.')
except Exception:
    pass
'''

PLAIN_POST = r'''
try:
    result.pop('header', None)
    d = result.get('data')
    if isinstance(d, dict):
        d['what_to_do_next'] = 'Done.' if str(d.get('ok')).lower() == 'true' else 'This did NOT go through. Tell the customer.'
except Exception:
    pass
'''

for c in (SETUP_CODE, ACCOUNT_CODE):
    assert "{{" not in c and "}}" not in c

# ------------------------------------------------------------------ helpers

HEADERS = {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}


def api_tool(name, path, desc, fields, required, retries=0, post=None, mapping=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(fields)
    t = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": retries},
         "function": {"name": name, "handler": "__function__:api_call", "description": desc,
                      "parameters": {"type": "object", "properties": {
                          "url": {"type": "string", "default": BASE + path},
                          "method": {"type": "string", "default": "POST"},
                          "headers": HEADERS,
                          "body": {"type": "object", "properties": props, "required": required}}}}}
    if post:
        t["post_process_code"] = post
    if mapping:
        t["response_mapping"] = mapping
    return t


def verify_tool():
    return api_tool("verify_identity", "verify_identity",
                    "Check ONE security answer. CALL it every time the customer gives a date of birth or the last four phone digits. Then follow what_to_do_next in the result.",
                    {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                               "description": "Which question was answered. One of: date_of_birth, phone_last4."},
                     "answer": {"type": "string", "default": "{{answer}}",
                                "description": "date_of_birth as YYYY-MM-DD (a date said only in numbers is day, then month, then year). phone_last4 as exactly four digits."}},
                    ["field", "answer"], post=VERIFY_POST, mapping=[{"path": "data.verify_state", "variable": "verify_state"}])


def transfer_tool(queue, when):
    return api_tool("transfer_" + queue, "transfer_to_agent",
                    "Hand the call to the " + queue + " team. CALL it " + when + " Call no other tool in the same message.",
                    {"queue": {"type": "string", "enum": [queue], "default": queue}}, ["queue"], post=PLAIN_POST)


def promise_tool(multi):
    return api_tool("create_promise", "create_promise",
                    ("Record ONE payment promise for one product. CALL it only after the customer said a clear yes to the read-back. "
                     + ("Call it once per confirmed product, one call per message." if multi else "Call it once.")),
                    {"product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id from the account facts, for example p1."},
                     "amount": {"type": "number", "default": "{{amount}}", "description": "The agreed amount, a number such as 420.0."},
                     "date": {"type": "string", "default": "{{date}}", "description": "The agreed payment date as YYYY-MM-DD."}},
                    ["product_id", "amount", "date"], post=PROMISE_POST_B if multi else PROMISE_POST_A)


def note_tool():
    return api_tool("add_note", "add_note",
                    "Record why ONE product ends without a promise. CALL it at the end of the call, once per product without a recorded promise, one call per message. Never on a call that is transferred.",
                    {"product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id from the account facts."},
                     "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "default": "{{reason}}",
                                "description": "One of: refused, hardship, dispute, paid, service_error."},
                     "text": {"type": "string", "default": "{{text}}", "description": "One short sentence on what the customer said."}},
                    ["product_id", "reason"], post=PLAIN_POST)


def callback_tool():
    return api_tool("schedule_callback", "schedule_callback",
                    "Book a callback for the customer. CALL it as soon as the person gives a day and a time inside the callback window.",
                    {"date": {"type": "string", "default": "{{date}}", "description": "Callback day as YYYY-MM-DD."},
                     "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24 hour."}},
                    ["date", "time"], post=PLAIN_POST)


def ok_cond(var):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": "true"},
                                          {"variable": var, "operator": "equals", "operand": "True"}]}


def count_cond(var, n=0):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "greater_than", "operand": n}]}


def tc(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def det(target, desc, cond):
    return {"target_node": target, "description": desc, "condition": cond}


def conv(name, task, tools, transitions, on_enter, cap, cap_target, first_only=True):
    return {"name": name, "node_type": "conversation", "task_message": task, "tools": tools, "transitions": transitions,
            "on_enter": on_enter, "on_enter_first_entry_only": first_only, "max_node_turns": cap, "max_turn_transition": cap_target}


NO_TOOL_GOODBYE = ("To end the call, CALL the matching transition_to_close_... tool. The goodbye is spoken automatically after it, "
                   "so do not say goodbye yourself.")

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. One or two short sentences per turn. Address the customer as {{title}} {{last_name}}.

Rules for every turn:
- If asked whether you are a robot or an AI, say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam, say they can verify the call by phoning Freya Bank's customer service number, then continue.
- If asked something the tools do not tell you, say you do not have that information. Never invent figures, dates or reasons.
- When a rule says to use a tool, call the tool. Saying you did it is not enough. Call at most one tool per message.
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- Follow what_to_do_next in a tool result.
- Never say that something is recorded, booked or transferred unless the tool result says it worked."""

# ------------------------------------------------------------------ shared steps


def shared_nodes():
    human = "if the person asks for a human: first ask once whether you can help; CALL transfer_general only if they ask again."
    opening = conv(
        "opening",
        """You opened the call and asked whether you are speaking with {{title}} {{last_name}} ({{first_name}} {{last_name}}). You must find out who is on the line. No tool call except the ones named here.

Before identity is verified you must NOT say why you are calling. Never say "collections", "debt", "payment", "account details" or name any product. If asked what the call is about, say you can only discuss it with {{title}} {{last_name}} personally.

Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead", "who is this" do not count: ask once more "Am I speaking with {{title}} {{last_name}}?". If the person asks a question, answer it first; the ask after it is your second ask.

Endings and moves (CALL the tool, do not just say it):
- Clear confirmation: CALL transition_to_identity.
- Someone else answered (a relative, a colleague, anyone who is not the customer): CALL transition_to_third_party.
- The number does not belong to the customer: CALL transition_to_close_not_reached_wrong_number.
- The person says the customer has died: CALL transition_to_close_not_reached_deceased. Ask nothing else.
- Still unclear after your second ask: CALL transition_to_close_not_reached_unclear.
- The person says twice that they do not want to talk: CALL transition_to_close_not_verified_declined.
- Human request: """ + human + "\n" + NO_TOOL_GOODBYE,
        [transfer_tool("general", "only when the person insisted on a human after you asked once whether you can help.")],
        [det("close:transferred/human", "transfer done", count_cond("transfer_general_success_count")),
         tc("identity", "The person clearly confirmed they are the customer ({{title}} {{last_name}}) with yes, that's me, speaking or their own name."),
         tc("third_party", "Someone other than the customer answered, for example a relative, and the customer is not on the line."),
         tc("close:not_reached/wrong_number", "The person says this number does not belong to the customer."),
         tc("close:not_reached/deceased", "The person says the customer has died."),
         tc("close:not_reached/unclear", "Identity is still unclear after the second ask."),
         tc("close:not_verified/declined", "The person said twice that they do not want to talk.")],
        {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and we keep a recording of this call. Am I speaking with {{title}} {{last_name}}?"},
        10, "close:not_reached/unclear")

    third = conv(
        "third_party",
        """Someone other than {{title}} {{last_name}} is on the line. Tools: schedule_callback only.

Say NOTHING about why you are calling: no bank matter, no product, no amount, no debt, no payment. Even if the person asks or offers to pay, say you can only speak with {{title}} {{last_name}} personally. Never ask this person security questions and never tell them anything about the account.

Ask when {{title}} {{last_name}} can be reached.
{{callback_window}}
{{date_facts}}
- If the person gives a day and a time inside the window: CALL schedule_callback with the date (YYYY-MM-DD) and time (HH:MM). "Tomorrow" means the day after today. If they give a day but no time, ask for a time.
- If the day or time is outside the window: ask once for another time inside the window, saying it must be today or the next business day between 10:00 and 19:00. If the second answer is also outside it, or they cannot say: CALL transition_to_close_not_reached_no_callback.
- If they say the number does not belong to the customer: CALL transition_to_close_not_reached_wrong_number.
- If they say the customer has died: say "I am sorry for your loss." and CALL transition_to_close_not_reached_deceased. Ask nothing else.
""" + NO_TOOL_GOODBYE,
        [callback_tool()],
        [det("close:not_reached/callback", "callback booked", ok_cond("schedule_callback_response.data.ok")),
         tc("close:not_reached/no_callback", "The person twice gave a time outside the callback window, or cannot give a time."),
         tc("close:not_reached/wrong_number", "The person says this number does not belong to the customer."),
         tc("close:not_reached/deceased", "The person says the customer has died.")],
        {"type": "llm", "prompt": "Do not say why you are calling. Politely ask when {{title}} {{last_name}} can be reached, today or tomorrow between 10:00 and 19:00. No tool call in this turn."},
        12, "close:not_reached/no_callback")

    identity = conv(
        "identity",
        """The person confirmed they are {{title}} {{last_name}}. Verify identity with two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. Tools: verify_identity, transfer_general.

Before verification you must NOT say why you are calling: never say "collections", "debt", "payment" or name a product.

- After each answer CALL verify_identity with field date_of_birth or phone_last4. Send a date of birth as YYYY-MM-DD, whatever way it was said. A date said only in numbers is day, then month, then year (12/07/1991 is 1991-07-12).
- Follow what_to_do_next in the result. A wrong answer may be asked again: ask the SAME question again, not the other one. Never reveal the right answer.
- If the result says day and month look swapped, ask the customer to say the month as a word, then call verify_identity again.
- If the customer will not answer, or asks what the call is about instead of answering: the first time, explain once that the questions protect their account and ask again. The second time: CALL transition_to_close_not_verified_declined.
- The customer says twice they do not want to talk: CALL transition_to_close_not_verified_declined.
- Human request: """ + human + "\n" + NO_TOOL_GOODBYE,
        [verify_tool(), transfer_tool("general", "only when the customer insisted on a human after you asked once whether you can help.")],
        [det("load_account", "both answers verified",
             {"logic": "or", "conditions": ok_cond("verify_identity_response.data.all_verified")["conditions"] +
              [{"variable": "verify_state", "operator": "equals", "operand": "verified"}]}),
         det("close:not_verified/failed", "three wrong answers",
             {"logic": "or", "conditions": [{"variable": "verify_state", "operator": "equals", "operand": "failed"},
                                            {"variable": "verify_identity_response.data.wrong_answers_left", "operator": "equals", "operand": "0"}]}),
         det("close:transferred/human", "transfer done", count_cond("transfer_general_success_count")),
         tc("close:not_verified/declined", "The customer refused the security questions a second time after the explanation, asked a second time what the call is about instead of answering, or said twice they do not want to talk.")],
        {"type": "tts", "text": "Thank you. Before we continue, I need to ask you two security questions. First, what is your date of birth?"},
        16, "close:not_verified/declined")

    setup = {"name": "setup", "node_type": "code", "passthrough": True, "passthrough_default_transition": "opening",
             "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
             "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                                               "parameters": {"type": "object", "properties": {
                                                                   "code": {"type": "string", "default": SETUP_CODE},
                                                                   "timeout_ms": {"type": "number", "default": 10000}}}}}],
             "transitions": [{"target_node": "opening", "description": "always", "condition": {"operator": "always"}}]}

    get_account = api_tool("get_account", "get_account", "Get the late products.", {}, [], retries=2, post=GET_ACCOUNT_POST)
    load = {"name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare_account",
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "suppress_tool_results": False,
            "pre_actions": [get_account],
            "response_mapping": [{"path": "data.products", "variable": "products"}, {"path": "data.products_json", "variable": "products_json"}],
            "transitions": [{"target_node": "prepare_account", "description": "always", "condition": {"operator": "always"}}]}

    prepare = {"name": "prepare_account", "node_type": "code", "passthrough": True, "passthrough_default_transition": "negotiate",
               "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
               "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                                                 "parameters": {"type": "object", "properties": {
                                                                     "code": {"type": "string", "default": ACCOUNT_CODE},
                                                                     "timeout_ms": {"type": "number", "default": 10000}}}}}],
               "transitions": [{"target_node": "negotiate", "description": "account facts ready",
                                "condition": {"logic": "or", "conditions": [{"variable": "account_state", "operator": "equals", "operand": "ok"}]}},
                               {"target_node": "negotiate_raw", "description": "always", "condition": {"operator": "always"}}]}
    return {"setup": setup, "opening": opening, "third_party": third, "identity": identity, "load_account": load, "prepare_account": prepare}


DEBT_ENTRY = {"type": "llm", "prompt": "Say exactly this, word for word: \"{{debt_statement}}\". If the quoted text is empty, say instead: you are verified, you are calling from the collections team about a late payment, name each product in words (credit card ending in its last four digits, personal loan or car loan), its past-due amount and how many days late it is, then ask whether they can make this payment today. No tool call in this turn."}

COMMON_RULES = """AMOUNTS
- Ask for the full past-due amount first. Never ask "how much can you pay?" or anything like it. You propose every amount, even if the customer says "you tell me".
- Full amount too much: offer the floor, once, and in the same sentence say \"The rest stays overdue.\" (for example: \"I can record the minimum payment of <floor>; the rest stays overdue.\") If they refuse the floor, that is a flat refusal.
- The customer proposes an amount from the floor up to the full amount (both included): accept it. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept, that is a flat refusal.

DATES (look up every date the customer names in the CALENDAR below and do exactly what its line says; never work out dates yourself)
- A promise date must be today or later, a business day, and not after the product's deadline.
- A weekend day or holiday that is not after the deadline: offer the next business day.
- A date after the deadline: say the latest date you can record is the deadline (say it) and offer it. If they refuse the deadline, that is a flat refusal.
- A vague period ("next week", "the week after next", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
- "Next <weekday>" is that weekday in the following calendar week. "This <weekday>" is the one in the current week. "Tomorrow" is the day after today.

REFUSALS AND PERSUASION
- A date or an amount the customer proposes is never a refusal. Handle it with the rules above.
- A flat refusal or a non-answer uses one persuasion attempt. A no to paying today with no date and no amount is a flat refusal.
- Attempt 1 and attempt 2 are given in the account facts. Attempt 2 exists only for late-band products. Make each attempt once.
- Never repeat an offer the customer already refused.
- The floor is offered in only two cases: once when the customer says the full amount is too much, and as attempt 2 of a late-band product. A plain no to an offer is NOT "too much": it is a flat refusal and uses the next attempt.
- When a product's attempts are used up, stop asking about it at once. An early-band product gets exactly ONE offer after the first refusal, then you stop. A late-band product gets exactly two.

HARDSHIP (comes before persuasion and before restructuring)
- If the customer mentions illness, a death in the family or job loss: say one short sentence of sympathy, make NO persuasion attempt, and offer once to connect them with the customer support team. If they accept: CALL transfer_support. If they decline: the call ends with hardship (see ENDINGS). If they still name a date or an amount themselves, take the promise under the rules above.
- Never offer a discount, a waiver, an instalment plan or any other term. If asked for a discount, say you cannot offer one.

OTHER
- New payment plan or lower instalments: do not describe any plan. CALL transfer_restructuring.
- Human request: first ask once whether you can help; if they insist, CALL transfer_general.
- A recorded promise cannot be changed or cancelled in this call; they can change it in the mobile app.
"""


def negotiate_a():
    task = """The customer is verified. You stated the debt and asked whether they can pay today. Your job: get a payment promise that follows these rules. Tools: create_promise, transfer_restructuring, transfer_support, transfer_general.

ACCOUNT FACTS
{{account_facts}}

""" + COMMON_RULES + """
CONFIRM AND RECORD
- When the customer agrees an amount and a date, read back the product, the amount and the date (weekday, day and month), and ask "Do you confirm?". Call create_promise only after a clear yes.
- If they change the date or the amount at this point, check it against the rules and read it back again.
- In the read-back say "I will record ...". Never say "recorded" or "I have recorded" before the tool result. Do not say the promise is recorded; the system says it after a successful call.

ENDINGS (CALL the tool; do not only say it)
- The customer says they already paid this past-due amount: say payments can take one business day to appear, then CALL transition_to_close_paid.
- "This debt is not mine", "I never had this product", or a claim that the product was closed or paid off in the past: do not argue, take no promise, CALL transition_to_close_no_promise_dispute.
- All persuasion attempts for the product are used and the customer still refuses: CALL transition_to_close_no_promise_refused.
- The customer says twice that they do not want to talk: CALL transition_to_close_no_promise_refused.
- Hardship and the customer declined the support team and named no date or amount: CALL transition_to_close_no_promise_hardship.
""" + NO_TOOL_GOODBYE + """

CALENDAR
{{calendar}}
{{date_facts}}"""
    return conv("negotiate", task,
                [promise_tool(False), transfer_tool("restructuring", "when the customer asks for a new payment plan or lower instalments."),
                 transfer_tool("support", "when a customer in hardship (illness, death in the family, job loss) accepts your offer to connect them with the customer support team."),
                 transfer_tool("general", "only when the customer insisted on a human after you asked once whether you can help.")],
                [det("close:promise", "promise recorded", ok_cond("create_promise_response.data.ok")),
                 det("promise_retry", "first create_promise failed",
                     {"logic": "or", "conditions": [{"variable": "create_promise_response.data.ok", "operator": "equals", "operand": "false"},
                                                    {"variable": "create_promise_response.data.ok", "operator": "equals", "operand": "False"},
                                                    {"variable": "create_promise_failure_count", "operator": "greater_than", "operand": 0}]}),
                 det("close:transferred/restructuring", "transfer done", count_cond("transfer_restructuring_success_count")),
                 det("close:transferred/support", "transfer done", count_cond("transfer_support_success_count")),
                 det("close:transferred/human", "transfer done", count_cond("transfer_general_success_count")),
                 tc("close:paid", "The customer says they already paid this past-due amount."),
                 tc("close:no_promise/dispute", "The customer says the debt is not theirs, never had the product, or the product was closed or paid off in the past."),
                 tc("close:no_promise/refused", "Every persuasion attempt is used and the customer still refuses, or the customer said twice they do not want to talk."),
                 tc("close:no_promise/hardship", "The customer in hardship declined the support team and named no date or amount.")],
                DEBT_ENTRY, 40, "close:no_promise/refused")


def promise_retry_a():
    fail2 = {"logic": "or", "conditions": [
        {"logic": "and", "conditions": [{"variable": "create_promise_success_count", "operator": "greater_than", "operand": 1},
                                        {"logic": "or", "conditions": [{"variable": "create_promise_response.data.ok", "operator": "equals", "operand": "false"},
                                                                       {"variable": "create_promise_response.data.ok", "operator": "equals", "operand": "False"}]}]},
        {"variable": "create_promise_failure_count", "operator": "greater_than", "operand": 1},
        {"logic": "and", "conditions": [{"variable": "create_promise_failure_count", "operator": "greater_than", "operand": 0},
                                        {"variable": "create_promise_success_count", "operator": "greater_than", "operand": 0},
                                        {"logic": "or", "conditions": [{"variable": "create_promise_response.data.ok", "operator": "equals", "operand": "false"},
                                                                       {"variable": "create_promise_response.data.ok", "operator": "equals", "operand": "False"},
                                                                       {"variable": "create_promise_response.data.ok", "operator": "is_not_set"}]}]}]}
    return conv("promise_retry",
                "The first create_promise call failed: the promise is NOT recorded. Tool: create_promise. Call create_promise once more with exactly the same product_id, amount and date the customer confirmed. Never say the promise is recorded; the system says it after a successful call. Whatever the customer says next, call create_promise now, in your next message.",
                [promise_tool(False)],
                [det("close:promise", "promise recorded on retry", ok_cond("create_promise_response.data.ok")),
                 det("close:no_promise/service_error", "second failure", fail2)],
                {"type": "tts", "text": "I am sorry, that did not go through, so nothing is saved yet. I will try once more now."},
                6, "close:no_promise/service_error")


def negotiate_b():
    task = """The customer is verified. You stated every late product and asked whether they can pay all of them today. Your job: get a payment promise for each product under these rules. Tools: create_promise, add_note, transfer_restructuring, transfer_support, transfer_general.

ACCOUNT FACTS (in get_account order; each product has its own band, deadline, floor and attempts)
{{account_facts}}

ORDER OF WORK
1. If they can pay all of them today in full, go to step 3 with today's date for every product.
2. If not, go through the products one by one, in the order above. Do not ask about today again for each product. Start each product at its attempt 1. Persuasion attempts are counted per product.
   - If the customer names one date for everything and it is after one product's deadline, that product gets its own deadline and the others keep the named date. Say so in the read-back.
   - A dispute ("not mine", "never had it", closed or paid off in the past) or an "already paid" claim on one product does not end the call: remember it for that product and continue with the others. For "already paid" say payments can take one business day to appear.
3. Read ALL agreed promises back together (product, amount, date with weekday) and ask once "Do you confirm?". Say "I will record ..."; never say "recorded" before a create_promise result says so. After a clear yes, CALL create_promise once per confirmed product, one per message, in the order above.
4. If a create_promise fails, call it once more with the same values. If it fails again, keep the others, tell the customer you could not record that one, and that product gets reason service_error.
5. Then, for every product WITHOUT a recorded promise, CALL add_note with its product_id and reason: refused, hardship, dispute, paid or service_error. One call per message. Do this also when no product got a promise. Never add a note before step 5.
6. Then say which promises are recorded (only those whose result said recorded) and end the call (ENDINGS).

""" + COMMON_RULES + """
TRANSFERS IN THIS CALL
- On any transfer (restructuring, support, human) add NO notes at all and call no create_promise for promises not yet recorded. Promises already recorded stay.

ENDINGS (only after every create_promise and add_note result is back, in a message with no other tool call; CALL the tool, do not only say it)
- At least one promise recorded: CALL transition_to_close_promise.
- No promise recorded and every product noted paid: CALL transition_to_close_paid.
- No promise recorded otherwise: use the reason of the FIRST product, in the order above, whose note is not paid: transition_to_close_no_promise_refused, transition_to_close_no_promise_hardship, transition_to_close_no_promise_dispute or transition_to_close_no_promise_service_error.
- The customer says twice they do not want to talk: note refused for every product without a promise, then end as above.
""" + NO_TOOL_GOODBYE + """

CALENDAR
{{calendar}}
{{date_facts}}"""
    return conv("negotiate", task,
                [promise_tool(True), note_tool(),
                 transfer_tool("restructuring", "when the customer asks for a new payment plan or lower instalments."),
                 transfer_tool("support", "when a customer in hardship (illness, death in the family, job loss) accepts your offer to connect them with the customer support team."),
                 transfer_tool("general", "only when the customer insisted on a human after you asked once whether you can help.")],
                [det("close:transferred/restructuring", "transfer done", count_cond("transfer_restructuring_success_count")),
                 det("close:transferred/support", "transfer done", count_cond("transfer_support_success_count")),
                 det("close:transferred/human", "transfer done", count_cond("transfer_general_success_count")),
                 tc("close:promise", "At least one promise is recorded and every create_promise and add_note call is done."),
                 tc("close:paid", "No promise is recorded and every product was noted paid; all notes are done."),
                 tc("close:no_promise/refused", "No promise recorded; the first product whose note is not paid was noted refused; all notes are done."),
                 tc("close:no_promise/hardship", "No promise recorded; the first product whose note is not paid was noted hardship; all notes are done."),
                 tc("close:no_promise/dispute", "No promise recorded; the first product whose note is not paid was noted dispute; all notes are done."),
                 tc("close:no_promise/service_error", "No promise recorded; the first product whose note is not paid was noted service_error; all notes are done.")],
                DEBT_ENTRY, 60, "close:no_promise/refused")


# ------------------------------------------------------------------ closing plans

TABLE = {
    "promise": "| `promise` | none | at least one promise was recorded |",
    "paid": "| `paid` | none | rule 39 |",
    "transferred": "`transferred` | `restructuring`, `human`, `support` | rules 41, 42, 32",
    "no_promise": "`no_promise` | `refused`, `hardship`, `dispute`, `service_error` | rules 31 and 45, 32, 40, 37",
    "not_verified": "`not_verified` | `failed`, `declined` | rules 14, 15",
    "not_reached": "`not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear` | rules 6, 7, 8, 9, 3",
}
BYE = "Thank you for your time, {{title}} {{last_name}}. Goodbye."


def closing(outcome, reason, say):
    c = {"set": {"outcome": outcome}, "evidence": [{"source": A, "quote": TABLE[outcome]}], "say": say}
    if reason:
        c["set"]["reason"] = reason
    return c


def plan(multi):
    cl = {
        "promise": closing("promise", None,
                           ("You will receive a text message confirming this promise. " + BYE) if multi else
                           ("Thank you, your promise is recorded. You will receive a text message confirming this promise. " + BYE)),
        "paid": closing("paid", None, BYE if multi else "Thank you for letting me know. Payments can take one business day to appear. " + BYE),
        "transferred/restructuring": closing("transferred", "restructuring", "I am transferring you to our restructuring team now. Thank you for your time. Goodbye."),
        "transferred/support": closing("transferred", "support", "I am transferring you to our customer support team now. Thank you for your time. Goodbye."),
        "transferred/human": closing("transferred", "human", "I am transferring you to a colleague now. Thank you for your time. Goodbye."),
        "no_promise/refused": closing("no_promise", "refused", BYE),
        "no_promise/hardship": closing("no_promise", "hardship", "I understand. Thank you for your time, and take care. Goodbye."),
        "no_promise/dispute": closing("no_promise", "dispute", "Thank you for letting me know. " + BYE),
        "no_promise/service_error": closing("no_promise", "service_error",
                                            BYE if multi else "I am sorry, I could not record your promise because of a technical problem. " + BYE),
        "not_verified/failed": closing("not_verified", "failed", "I am sorry, I could not verify your identity. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye."),
        "not_verified/declined": closing("not_verified", "declined", "I understand. Thank you for your time. Goodbye."),
        "not_reached/callback": closing("not_reached", "callback", "Thank you, we will call back then. Goodbye."),
        "not_reached/no_callback": closing("not_reached", "no_callback", "Thank you, we will try another time. Goodbye."),
        "not_reached/wrong_number": closing("not_reached", "wrong_number", "I apologise for the disturbance. Thank you, goodbye."),
        "not_reached/deceased": closing("not_reached", "deceased", "I am sorry for your loss. Thank you for your time. Goodbye."),
        "not_reached/unclear": closing("not_reached", "unclear", "I could not confirm who I am speaking with. Thank you for your time. Goodbye."),
    }
    if multi:
        for k in cl:
            cl[k]["evidence"].append({"source": B, "quote": "The outcome table of Brief A applies."})
    return {"terminal": {"tool": "close_call", "evidence": [
        {"source": API, "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": A, "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]},
        "fields": {"customer_id": "{{customer_id}}"}, "closings": cl}


def body(multi):
    nodes = shared_nodes()
    import copy
    nodes["negotiate"] = negotiate_b() if multi else negotiate_a()
    if not multi:
        nodes["promise_retry"] = promise_retry_a()
    raw = copy.deepcopy(nodes["negotiate"])
    raw["name"] = "negotiate_raw"
    nodes["negotiate_raw"] = raw
    nodes["negotiate"]["on_enter"] = {"type": "tts", "text": "{{debt_statement}}"}
    return {"initial_node": "setup", "system_prompt": SYSTEM, "nodes": nodes, "global_nodes": {},
            "test_variables": {"first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}


for slot, multi in (("brief-a", False), ("brief-b", True)):
    (OUT / f"{slot}.body.json").write_text(json.dumps(body(multi), indent=1) + "\n")
    (OUT / f"{slot}.closing.json").write_text(json.dumps(plan(multi), indent=1) + "\n")
print("written")
