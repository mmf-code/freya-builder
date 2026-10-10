"""Generate the Freya workflows for Brief A (one product) and Brief B (up to three products).

    python3 builder/build.py            -> out/brief-a.workflow.json, out/brief-b.workflow.json and contracts

Everything brief-specific is in BRIEF below, taken from briefs/brief-a.md and briefs/brief-b.md.
Tool URLs and fields come from tools/openapi.json.
"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = json.load(open(ROOT / "tools/openapi.json"))
SERVER = API["servers"][0]["url"].rstrip("/")
BRIEF_A = (ROOT / "briefs/brief-a.md").read_text()

# ------------------------------------------------------------------ brief facts (from brief-a.md section 7)
hol_line = [l for l in BRIEF_A.splitlines() if "holidays" in l.lower()][0]
HOLIDAYS = re.findall(r"\d{4}-\d{2}-\d{2}", hol_line)
BANDS = [  # (min days_late, max days_late, band, nth business day after today, persuasion attempts)
    (1, 7, "early", 12, 1),
    (8, 45, "late", 7, 2),
]
CB_FROM, CB_TO = "10:00", "19:00"

CLOSES = [  # (outcome, reason) from the outcome table, rule 46
    ("promise", ""), ("paid", ""),
    ("transferred", "restructuring"), ("transferred", "human"), ("transferred", "support"),
    ("no_promise", "refused"), ("no_promise", "hardship"), ("no_promise", "dispute"), ("no_promise", "service_error"),
    ("not_verified", "failed"), ("not_verified", "declined"),
    ("not_reached", "callback"), ("not_reached", "no_callback"), ("not_reached", "wrong_number"),
    ("not_reached", "deceased"), ("not_reached", "unclear"),
]


def cname(outcome, reason):
    return "close_" + outcome + ("_" + reason if reason else "")


# ------------------------------------------------------------------ helpers
def leaf(type_, default, description=None, enum=None):
    d = {"type": type_, "default": default}
    if description:
        d["description"] = description
    if enum:
        d["enum"] = enum
    return d


def api_tool(name, path, body, description, required=None, retries=0, post=None, pre=None):
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
                    "url": {"type": "string", "default": SERVER + path},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": body, "required": required or []},
                },
            },
        },
    }
    if post:
        t["post_process_code"] = post
    if pre:
        t["pre_process_code"] = pre
    return t


def cid():
    return leaf("string", "{{customer_id}}")


def any_true(var_list):
    conds = []
    for v in var_list:
        conds += [{"variable": v, "operator": "equals", "operand": "true"},
                  {"variable": v, "operator": "equals", "operand": "True"}]
    return {"logic": "or", "conditions": conds}


def tool_tr(target, description):
    return {"target_node": target, "description": description, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": description}}


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


HOOK_HEAD = "try:\n    if isinstance(result, dict):\n        result.pop('header', None)\n        d = result.get('data')\n        if not isinstance(d, dict):\n            d = dict()\n            result['data'] = d\n        T = (True, 'true', 'True')\n"
HOOK_TAIL = "        d['what_to_do_next'] = msg\nexcept Exception:\n    pass\n"


def simple_hook(ok_msg, fail_msg):
    return (HOOK_HEAD
            + "        if d.get('ok') in T:\n            msg = " + repr(ok_msg) + "\n"
            + "        else:\n            msg = " + repr(fail_msg) + "\n" + HOOK_TAIL)


VERIFY_HOOK = (HOOK_HEAD + """        left = d.get('wrong_answers_left')
        if d.get('hint') == 'day_month_swapped':
            msg = 'Day and month look swapped. Ask the customer to say the date of birth again with the month as a word. This does not count as a wrong answer.'
        elif d.get('all_verified') in T:
            msg = 'Both security answers are verified.'
        elif d.get('ok') is False or d.get('ok') == 'false' or ('verified' not in d):
            msg = 'This answer was NOT checked (the service could not read it). It is not a wrong answer. Ask the customer to say it again; for a date ask for the day, the month as a word, and the year.'
        elif d.get('verified') in T:
            msg = 'Correct. If this was the date of birth, now ask for the last four digits of the phone number on file.'
        elif str(left) == '0':
            msg = 'Wrong answer. No attempts are left.'
        else:
            msg = 'Wrong answer. Say it does not match and ask the SAME question again. Give no hint and say nothing about the account.'
""" + HOOK_TAIL)

PROMISE_HOOK = simple_hook(
    "The promise IS recorded.",
    "FAILED: the promise was NOT recorded. If this is the first failure for this product, call create_promise again now with exactly the same values. If it already failed once before for this product, do not try again: tell the customer you could not record it.")


# ------------------------------------------------------------------ code
SETUP_CODE = r'''import datetime
try:
    HOL = set(HOLIDAYS_LIST)
    BANDS = BANDS_LIST
    s = str(vars.get('now') or '').strip().replace(' ', 'T')
    try:
        now = datetime.datetime.fromisoformat(s[:16])
    except Exception:
        now = datetime.datetime.fromisoformat(s[:10] + 'T09:00')
    today = now.date()
    one = datetime.timedelta(days=1)
    def isbd(d):
        return d.weekday() < 5 and d.isoformat() not in HOL
    def nth_bd(n):
        d = today
        c = 0
        while c < n:
            d = d + one
            if isbd(d):
                c += 1
        return d
    def sp(d):
        return d.strftime('%A ') + str(d.day) + d.strftime(' %B %Y') + ' (' + d.isoformat() + ')'
    def last_bd(mon):
        for i in range(4, -1, -1):
            d = mon + datetime.timedelta(days=i)
            if isbd(d):
                return d
        return None
    monday = today - datetime.timedelta(days=today.weekday())
    a1 = last_bd(monday)
    if a1 is None or a1 <= today:
        a1 = last_bd(monday + datetime.timedelta(days=7))
    vars['attempt1_date'] = sp(a1)
    vars['attempt1_iso'] = a1.isoformat()
    for b in BANDS:
        dl = nth_bd(b[3])
        vars['deadline_' + b[2]] = dl.isoformat()
        vars['deadline_' + b[2] + '_spoken'] = sp(dl)
    nbd = today + one
    while not isbd(nbd):
        nbd = nbd + one
    lines = []
    lines.append('Today is ' + sp(today) + ', time ' + now.strftime('%H:%M') + '. Today is ' + ('a business day.' if isbd(today) else 'NOT a business day.'))
    lines.append('Bank holidays (not business days): ' + ', '.join(sorted(HOL)) + '. Weekends are not business days.')
    for b in BANDS:
        lines.append('Deadline for the ' + b[2] + ' band (' + str(b[0]) + ' to ' + str(b[1]) + ' days late): ' + sp(nth_bd(b[3])) + ' = the ' + str(b[3]) + 'th business day after today.')
    lines.append('Persuasion attempt 1 date (last business day of this week, or of next week if today is that day): ' + sp(a1) + '.')
    names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    nextmon = monday + datetime.timedelta(days=7)
    this_l = []
    next_l = []
    for i in range(7):
        this_l.append('this ' + names[i] + ' = ' + (monday + datetime.timedelta(days=i)).isoformat())
        next_l.append('next ' + names[i] + ' = ' + (nextmon + datetime.timedelta(days=i)).isoformat())
    lines.append('Weekday words ("this X" = current week, "next X" = following calendar week): ' + '; '.join(this_l) + '; ' + '; '.join(next_l) + '.')
    lines.append('Calendar:')
    for i in range(0, 50):
        d = today + datetime.timedelta(days=i)
        wk = (d - monday).days // 7
        tag = ['this week', 'next week', 'the week after next'][wk] if wk < 3 else ''
        st = 'business day' if isbd(d) else ('HOLIDAY, not a business day' if d.isoformat() in HOL else 'weekend, not a business day')
        lines.append('  ' + d.isoformat() + ' ' + names[d.weekday()] + ' ' + str(d.day) + d.strftime(' %B') + ' - ' + st + ((' - ' + tag) if tag else '') + (' - TODAY' if i == 0 else ''))
    vars['date_facts'] = '\n'.join(lines)
    cb = 'Allowed callback slots: today ' + sp(today) + ' at a time later than ' + now.strftime('%H:%M') + ' and from CB_FROM to CB_TO (both included), or the next business day ' + sp(nbd) + ' from CB_FROM to CB_TO (both included). Anything else is outside the window. "Tomorrow" means ' + (today + one).isoformat() + '.'
    vars['callback_facts'] = cb
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Date facts unavailable: ' + str(e)
    vars['callback_facts'] = 'Callback facts unavailable.'
    vars['attempt1_date'] = ''
    vars['setup_state'] = 'error'
'''.replace("HOLIDAYS_LIST", repr(HOLIDAYS)).replace("BANDS_LIST", repr(BANDS)).replace("CB_FROM", CB_FROM).replace("CB_TO", CB_TO)

ACCOUNT_CODE = r'''import json, re
try:
    BANDS = BANDS_LIST
    MULTI = MULTI_FLAG
    p = vars.get('products')
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            p = None
    if not isinstance(p, list):
        rows = dict()
        for k in list(vars.keys()):
            m = re.search(r'products\.(\d+)\.(\w+)$', str(k))
            if m:
                rows.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
        p = [rows[i] for i in sorted(rows)] if rows else None
    if not isinstance(p, list) or not p:
        raise ValueError('no products')
    def num(x):
        try:
            return float(x)
        except Exception:
            return 0.0
    def money(x):
        return '%.2f' % num(x)
    facts = []
    says = []
    for i, pr in enumerate(p):
        if not isinstance(pr, dict):
            continue
        t = str(pr.get('type') or '')
        pid = str(pr.get('product_id') or ('p' + str(i + 1)))
        if t == 'credit_card':
            name = 'credit card ending ' + str(pr.get('card_last4') or '')
            floor = pr.get('minimum_payment')
            fname = 'minimum payment'
        else:
            name = t.replace('_', ' ')
            floor = pr.get('instalment_amount')
            fname = 'instalment amount'
        dl = int(num(pr.get('days_late')))
        band = None
        for b in BANDS:
            if b[0] <= dl <= b[1]:
                band = b
        if band is None:
            band = BANDS[-1] if dl > BANDS[-1][1] else BANDS[0]
        dls = vars.get('deadline_' + band[2] + '_spoken') or ''
        dli = vars.get('deadline_' + band[2]) or ''
        a1 = vars.get('attempt1_date') or ''
        a1i = vars.get('attempt1_iso') or ''
        if a1i and dli and a1i > dli:
            a1 = dls
        att = 'Attempt 1: propose ' + money(pr.get('past_due')) + ' (or the floor ' + money(floor) + ' if the customer already said the full amount is too much) on ' + a1 + '.'
        if band[4] >= 2:
            att += ' Attempt 2: propose the floor ' + money(floor) + ' on the deadline ' + dls + '.'
        else:
            att += ' No attempt 2 (only 1 persuasion attempt in this band).'
        facts.append('- product_id ' + pid + ': ' + name + '. Past due ' + money(pr.get('past_due')) + ', ' + str(dl) + ' days late, ' + band[2] + ' band. Floor (' + fname + '): ' + money(floor) + '. Latest promise date (deadline): ' + dls + '. Persuasion attempts allowed: ' + str(band[4]) + '. ' + att)
        if MULTI:
            says.append('Your ' + name + ' has a past-due amount of ' + money(pr.get('past_due')) + ' and is ' + str(dl) + ' days late.')
        else:
            says.append('I am calling from the collections team about a late payment on your ' + name + '. The past-due amount is ' + money(pr.get('past_due')) + ', and it is ' + str(dl) + ' days late.')
    if MULTI:
        head = 'I am calling from the collections team about late payments on ' + ('your account.' if len(says) == 1 else str(len(says)) + ' of your products.')
        vars['debt_statement'] = head + ' ' + ' '.join(says)
    else:
        vars['debt_statement'] = ' '.join(says)
    vars['account_facts'] = '\n'.join(facts)
    vars['product_count'] = str(len(facts))
    vars['account_state'] = 'ok'
except Exception as e:
    vars['account_facts'] = 'Account could not be loaded.'
    vars['debt_statement'] = ''
    vars['product_count'] = '0'
    vars['account_state'] = 'error'
'''.replace("BANDS_LIST", repr(BANDS))


def code_node(name, code, nxt, extra_transitions=None):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": code},
                             "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": (extra_transitions or []) + [always(nxt)],
    }


def wrap_node(name, text, nxt):
    """A fixed spoken line, then straight on to a close step."""
    return {
        "name": name, "node_type": "conversation", "on_enter": {"type": "tts", "text": text},
        "on_enter_first_entry_only": True, "passthrough": True, "passthrough_default_transition": nxt,
        "disable_inactivity_monitor": True,
        "task_message": "Say only a short goodbye. No tool call is allowed in this turn.",
        "transitions": [always(nxt)],
    }


# ------------------------------------------------------------------ tools
def t_verify(field, name, desc):
    return api_tool(name, "/verify_identity", {
        "customer_id": cid(),
        "field": leaf("string", field, enum=["date_of_birth", "phone_last4"]),
        "answer": leaf("string", "{{" + name + "_answer}}", desc),
    }, required=["answer"], post=VERIFY_HOOK,
        description="CALL it every time the customer gives an answer to the " + ("date of birth" if field == "date_of_birth" else "phone digits") + " question. One call per answer.")


def t_transfer(queue, when):
    return api_tool("transfer_" + queue, "/transfer_to_agent", {
        "customer_id": cid(), "queue": leaf("string", queue, enum=["restructuring", "general", "support"])},
        description="Hands the call to the " + queue + " team. CALL it " + when + " In the same message, first tell the customer you are transferring them, thank them and say goodbye.",
        post=simple_hook("The transfer is done. Say nothing more.", "The transfer FAILED. Tell the customer the transfer did not work."))


T_CALLBACK = api_tool("schedule_callback", "/schedule_callback", {
    "customer_id": cid(),
    "date": leaf("string", "{{callback_date}}", "Callback date as YYYY-MM-DD."),
    "time": leaf("string", "{{callback_time}}", "Callback time as HH:MM, 24 hour."),
}, required=["date", "time"],
    description="Books a callback for the customer. CALL it as soon as the person who answered names a day and time that is inside the allowed callback window.",
    post=simple_hook("The callback IS booked.", "The callback was NOT booked. Tell the person it could not be booked."))

T_PROMISE = api_tool("create_promise", "/create_promise", {
    "customer_id": cid(),
    "product_id": leaf("string", "{{promise_product_id}}", "product_id from the account facts, for example p1. Copy it exactly."),
    "amount": leaf("number", "{{promise_amount}}", "The confirmed amount, a number like 420.00."),
    "date": leaf("string", "{{promise_date}}", "The confirmed payment date as YYYY-MM-DD."),
}, required=["product_id", "amount", "date"], post=PROMISE_HOOK,
    description="Records one payment promise for one product. CALL it only after the customer said a clear yes to the read-back. One call per product.")

T_NOTE = api_tool("add_note", "/add_note", {
    "customer_id": cid(),
    "product_id": leaf("string", "{{note_product_id}}", "product_id from the account facts, for example p2. Copy it exactly."),
    "reason": leaf("string", "{{note_reason}}", "Why this product has no promise. One of: refused, hardship, dispute, paid, service_error.",
                   enum=["refused", "hardship", "dispute", "paid", "service_error"]),
}, required=["product_id", "reason"],
    description="Records why one product ended without a promise. CALL it once for each product that has no recorded promise, unless the call is transferred.",
    post=simple_hook("The note IS recorded.", "The note was NOT recorded. Call add_note again once with the same values."))

T_GET_ACCOUNT = api_tool("get_account", "/get_account", {"customer_id": cid()}, description="Get the late products.", retries=2)


def close_node(outcome, reason):
    body = {"customer_id": cid(), "outcome": leaf("string", outcome, enum=[outcome])}
    if reason:
        body["reason"] = leaf("string", reason)
    tool = api_tool("close_call", "/close_call", body, description="Record how the call ended.", retries=2)
    n = cname(outcome, reason)
    return {
        "name": n, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "hang_up",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [tool], "response_mapping": [], "transitions": [always("hang_up")],
    }


# ------------------------------------------------------------------ prompts
SYSTEM = """You are the digital assistant of Freya Bank, on an outbound phone call. Speak English. Keep every turn to one to three short sentences. Address the customer as {{title}} {{last_name}}.

General rules:
- Never invent figures, dates, reasons or terms. If you cannot answer from what you know, say you do not have that information.
- Never offer a discount, a waiver, an instalment plan or any term the bank did not give you.
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked "is this a scam?": say they can verify the call by phoning Freya Bank's customer service number, then continue.
- Tools: when a rule says to call a tool, call it; saying you did is not enough. Never claim something is recorded, booked or transferred unless the tool result says so. If a tool result has what_to_do_next, follow it.
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.
- A transition_to_close_... tool ends the call: call it alone, never in the same message as another tool. In the same message, before calling it, say what the rule requires, then thank the customer and say goodbye.

Date facts (use these, never the real clock):
{{date_facts}}"""

OPENING_TASK = """You have just said you are a digital assistant calling from Freya Bank, that the call is being recorded, and asked "Am I speaking with {{title}} {{last_name}}?". Find out who is on the line. Before identity is verified, never say "collections", "debt", "payment", any amount or any product, and never say why you are calling - to anyone.

Rules:
1. Only "yes", "that's me", "speaking", or the customer's own name counts as confirmation. Then call transition_to_identity (say nothing else about the call).
2. "Hello", "go ahead", "who is this" and similar do not confirm. Answer any question first (robot/AI, scam: see general rules; "who is this": you are Freya Bank's digital assistant), then ask "Am I speaking with {{title}} {{last_name}}?" once more. If it is still unclear after this second ask, call transition_to_close_not_reached_unclear.
3. Someone else answered (a relative, a colleague, etc.): do not say why you are calling, even if they ask or offer to pay; say nothing about any account. Ask when {{title}} {{last_name}} can be reached.
   {{callback_facts}}
   - If they give a day and time inside the window: call schedule_callback with date YYYY-MM-DD and time HH:MM. "Around eleven" in the morning = 11:00. "Tomorrow morning" without a time: ask for the time.
   - If the time or day is outside the window: say when you can call back and ask once for another time. If the second answer is also outside, call transition_to_close_not_reached_no_callback.
   - If they will not give any time: call transition_to_close_not_reached_no_callback.
4. The number does not belong to the customer: call transition_to_close_not_reached_wrong_number.
5. The person says the customer has died: say exactly "I am sorry for your loss.", ask nothing else, and call transition_to_close_not_reached_deceased.
6. The customer says twice that they do not want to talk: call transition_to_close_not_verified_declined.
7. A request for a human: ask once whether you can help first. If they insist, call transfer_human."""

IDENTITY_TASK = """The customer confirmed who they are. Verify identity with two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. You know nothing about the account yet. Never say "collections", "debt", "payment", any amount or product before both answers pass.

- Date of birth: call verify_date_of_birth with the date as YYYY-MM-DD, whatever way the customer said it ("14 March 1988" -> 1988-03-14). A date given only as numbers is day, then month, then year (03/04/1990 -> 1990-04-03).
- Phone: call verify_phone_last4 with the four digits.
- Each answer is checked by a tool call. Follow what_to_do_next in the result. A wrong answer: ask the same question again (do not re-ask a question that already passed). Three wrong answers in total end the check; the system handles that.
- If the customer does not want to answer, or asks what the call is about instead of answering: explain once that the questions protect their account and ask again. If they refuse again or ask again what it is about, say you cannot continue without the check, thank them, say goodbye and call transition_to_close_not_verified_declined.
- A request for a human: ask once whether you can help first. If they insist, call transfer_human."""

NEGOTIATE_COMMON = """The customer is verified. You already told them about the late payment(s) and asked whether they can pay today (the line you said is above in the conversation).

Account facts (product_id, amounts, floors, deadlines, attempts):
{{account_facts}}

DATES
- A promise date must be today or later, a business day, and not after that product's deadline. Use the calendar in the date facts.
- Customer names a weekend day or a holiday that is not after the deadline: say it is not a business day and offer the next business day.
- Customer names a vague period ("next week", "the week after next", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
- "Next <weekday>" = that weekday in the following calendar week; "this <weekday>" = in the current week (see weekday words in the date facts).
- Customer asks for a date after the deadline: say the latest date you can record is the deadline (say the date) and offer it. If they refuse the deadline, that is a flat refusal.

AMOUNTS
- Ask for the full past-due amount first. Never ask "how much can you pay?" - you propose every amount.
- Full amount too much: offer the floor ONCE, in one sentence, and say that the rest stays overdue (e.g. "Could you pay the minimum payment of X? The rest stays overdue."). From then on never propose the full amount again. If the customer does not give a date ("you tell me", no answer), that is a non-answer: use attempt 1 with the floor amount on the attempt 1 date, without repeating the explanation. If they refuse the floor, that is a flat refusal.
- Customer proposes an amount from the floor up to the full amount (both included): accept it. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept it, that is a flat refusal.

PERSUASION
- A date or an amount the customer proposes is never a refusal; handle it with DATES and AMOUNTS.
- A flat refusal or a non-answer uses one persuasion attempt. A no to paying today with no date and no amount is a flat refusal. Use the attempt proposals in the account facts, in order. Never repeat an offer the customer already refused. When the product's attempts are used up and it is still refused, stop.
- Hardship (illness, a death in the family, job loss): say ONE short sentence of sympathy, make NO persuasion attempt, offer to connect them with the customer support team. Accept -> call transfer_support. Decline -> no promise, reason hardship. If they still name a date or an amount themselves, handle it as a promise.

OTHER
- "I already paid" (this past-due amount): say payments can take one business day to appear; take no promise for it.
- "This debt is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise; it is a dispute.
- A request for a new payment plan or lower instalments: do not describe any plan; call transfer_restructuring.
- A request for a human: ask once whether you can help first. If they insist, call transfer_human.
- The customer says twice that they do not want to talk: no promise, reason refused.
- A question you cannot answer from these facts: say you do not have that information."""

NEGOTIATE_A = NEGOTIATE_COMMON + """

CONFIRMING AND RECORDING
- When a date and amount are agreed, read back the product (in words), the amount and the date, and ask "Do you confirm?". Call create_promise only after a clear yes, with product_id, amount and date (YYYY-MM-DD).
- If the customer changes the date or amount at the read-back, check it again under DATES and AMOUNTS and read it back again.
- Never say the promise is recorded yourself before the tool result. If create_promise fails, call it once more with the same values. If it fails again, say you could not record the promise, thank them, say goodbye and call transition_to_close_no_promise_service_error.

ENDING (one of these, alone in its message, after your goodbye)
- already paid -> transition_to_close_paid
- refused after the attempts are used up, or twice does not want to talk -> transition_to_close_no_promise_refused
- hardship and declined support -> transition_to_close_no_promise_hardship
- dispute -> transition_to_close_no_promise_dispute"""

NEGOTIATE_B = NEGOTIATE_COMMON + """

SEVERAL PRODUCTS (this customer has {{product_count}} late product(s))
- You already asked whether they can pay all of them today. If yes, read back all products for today. If not, go through the products one by one, in the order of the account facts. Do not ask about today again for each product. Start each product at its attempt 1. Persuasion attempts are counted per product. Bands, floors and deadlines are per product.
- If the customer names one date for everything and it is after one product's deadline, that product gets its own deadline; say so in the read-back. The other products keep the named date.
- A dispute or "already paid" on one product does not end the call: note it and continue with the others.

CONFIRMING AND RECORDING
- When every product is settled (promise agreed, refused after its attempts, paid, dispute or hardship), read ALL agreed promises back together (product in words, amount, date for each) and ask "Do you confirm?" once. If they change something, check it and read back again.
- After a clear yes: call create_promise once per agreed product (product_id, amount, date YYYY-MM-DD). If one fails, call it once more for that product; if it fails again, keep the others and note that product service_error.
- Then, for each product WITHOUT a recorded promise, call add_note with that product_id and reason refused, hardship, dispute, paid or service_error. Do this even when no product has a promise.
- Only after all create_promise and add_note results are back: if at least one promise is recorded, say the promises are recorded and say "You will receive a text message confirming this promise.". Never say recorded for a promise whose tool call failed.
- Transfers (restructuring, support, human): make NO add_note calls at all, before or after. Promises already recorded stay; agreed but unrecorded promises are not recorded. Just call the transfer tool.

ENDING (one of these, alone in its message, after all notes and your goodbye)
- at least one promise recorded -> transition_to_close_promise
- no promise and every product noted paid -> transition_to_close_paid
- otherwise no promise: use the reason of the FIRST product, in account-facts order, whose note is not paid -> transition_to_close_no_promise_refused / _hardship / _dispute / _service_error"""


# ------------------------------------------------------------------ workflow
def build(multi):
    nodes = {}
    nodes["setup"] = code_node("setup", SETUP_CODE, "opening")

    nodes["opening"] = {
        "name": "opening", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and we are recording this call. Am I speaking with {{title}} {{last_name}}?"},
        "on_enter_first_entry_only": True,
        "task_message": OPENING_TASK,
        "tools": [T_CALLBACK, t_transfer("general", "only when the person insists on a human after you asked once whether you can help.")],
        "max_node_turns": 14, "max_turn_transition": "close_not_reached_unclear",
        "transitions": [
            {"target_node": "callback_booked", "description": "The callback was booked", "condition": any_true(["schedule_callback_response.data.ok"])},
            {"target_node": "close_transferred_human", "description": "Transferred to a human", "condition": any_true(["transfer_general_response.data.ok"])},
            tool_tr("identity", "The person on the line clearly confirmed that they are {{title}} {{last_name}} (yes, that's me, speaking, or their own name)."),
            tool_tr("close_not_reached_unclear", "Still unclear who is on the line after asking twice. Say goodbye first."),
            tool_tr("close_not_reached_no_callback", "Someone else answered and no callback time inside the window could be agreed. Say goodbye first."),
            tool_tr("close_not_reached_wrong_number", "The number does not belong to the customer. Say goodbye first."),
            tool_tr("close_not_reached_deceased", "The person said the customer has died, and you said 'I am sorry for your loss.'"),
            tool_tr("close_not_verified_declined", "The customer said twice that they do not want to talk. Say goodbye first."),
        ],
    }
    nodes["callback_booked"] = wrap_node("callback_booked", "Thank you, we will call back then. Have a good day, goodbye.", "close_not_reached_callback")

    nodes["identity"] = {
        "name": "identity", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you. Before we continue, I need to ask two security questions. What is your date of birth?"},
        "on_enter_first_entry_only": True,
        "task_message": IDENTITY_TASK,
        "tools": [
            t_verify("date_of_birth", "verify_date_of_birth", "The date of birth as YYYY-MM-DD."),
            t_verify("phone_last4", "verify_phone_last4", "The four digits."),
            t_transfer("general", "only when the customer insists on a human after you asked once whether you can help."),
        ],
        "max_node_turns": 20, "max_turn_transition": "close_not_verified_declined",
        "transitions": [
            {"target_node": "load_account", "description": "Both answers verified",
             "condition": any_true(["verify_phone_last4_response.data.all_verified", "verify_date_of_birth_response.data.all_verified"])},
            {"target_node": "verification_failed", "description": "No wrong answers left", "condition": {"logic": "or", "conditions": [
                {"variable": "verify_date_of_birth_response.data.wrong_answers_left", "operator": "equals", "operand": "0"},
                {"variable": "verify_phone_last4_response.data.wrong_answers_left", "operator": "equals", "operand": "0"}]}},
            {"target_node": "close_transferred_human", "description": "Transferred to a human", "condition": any_true(["transfer_general_response.data.ok"])},
            tool_tr("close_not_verified_declined", "The customer refused the security questions a second time (or asked again what the call is about instead of answering). Say goodbye first."),
        ],
    }
    nodes["verification_failed"] = wrap_node("verification_failed",
        "I am sorry, I could not verify your identity, so I cannot discuss your account. Please use the Freya Bank mobile app or visit a branch. Thank you for your time, goodbye.",
        "close_not_verified_failed")

    nodes["load_account"] = {
        "name": "load_account", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "prepare_account",
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [T_GET_ACCOUNT], "response_mapping": [{"path": "data.products", "variable": "products"}],
        "transitions": [always("prepare_account")],
    }
    nodes["prepare_account"] = code_node("prepare_account", ACCOUNT_CODE.replace("MULTI_FLAG", "True" if multi else "False"), "negotiate",
        [{"target_node": "account_error", "description": "Account not loaded", "condition": {"logic": "or", "conditions": [
            {"variable": "account_state", "operator": "equals", "operand": "error"}]}}])
    nodes["account_error"] = wrap_node("account_error",
        "Thank you, you are verified. I am sorry, I cannot access your account details right now, so I cannot record anything today. Thank you for your time, goodbye.",
        "close_no_promise_service_error")

    ask = "Can you pay all of them today?" if multi else "Can you make this payment today?"
    neg_tools = [T_PROMISE] + ([T_NOTE] if multi else []) + [
        t_transfer("restructuring", "when the customer asks for a new payment plan or lower instalments."),
        t_transfer("support", "when a customer in hardship (illness, death in the family, job loss) accepts your offer to connect them with the customer support team."),
        t_transfer("general", "only when the customer insists on a human after you asked once whether you can help."),
    ]
    trans = []
    if not multi:
        trans.append({"target_node": "promise_recorded", "description": "The promise was recorded", "condition": any_true(["create_promise_response.data.ok"])})
    trans += [
        {"target_node": "close_transferred_restructuring", "description": "Transferred to restructuring", "condition": any_true(["transfer_restructuring_response.data.ok"])},
        {"target_node": "close_transferred_support", "description": "Transferred to support", "condition": any_true(["transfer_support_response.data.ok"])},
        {"target_node": "close_transferred_human", "description": "Transferred to a human", "condition": any_true(["transfer_general_response.data.ok"])},
    ]
    if multi:
        trans.append(tool_tr("close_promise", "At least one promise was recorded and all create_promise and add_note results are back. Say goodbye first."))
    trans += [
        tool_tr("close_paid", "The customer already paid" + (" every product (all noted paid, no promise)" if multi else "") + ". Say goodbye first."),
        tool_tr("close_no_promise_refused", "No promise; refused after the persuasion attempts, or twice does not want to talk" + (" (first non-paid note is refused)" if multi else "") + ". Say goodbye first."),
        tool_tr("close_no_promise_hardship", "No promise; hardship and the customer declined the support team" + (" (first non-paid note is hardship)" if multi else "") + ". Say goodbye first."),
        tool_tr("close_no_promise_dispute", "No promise; the customer disputes the debt" + (" (first non-paid note is dispute)" if multi else "") + ". Say goodbye first."),
        tool_tr("close_no_promise_service_error", "No promise; create_promise failed twice" + (" (first non-paid note is service_error)" if multi else "") + ". Say goodbye first."),
    ]
    nodes["negotiate"] = {
        "name": "negotiate", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you, you are verified. {{debt_statement}} " + ask},
        "on_enter_first_entry_only": True,
        "task_message": NEGOTIATE_B if multi else NEGOTIATE_A,
        "tools": neg_tools,
        "max_node_turns": 40, "max_turn_transition": "close_no_promise_refused",
        "transitions": trans,
    }
    if not multi:
        nodes["promise_recorded"] = wrap_node("promise_recorded",
            "Thank you. Your payment promise is recorded. You will receive a text message confirming this promise. Thank you for your time, goodbye.",
            "close_promise")

    for o, r in CLOSES:
        nodes[cname(o, r)] = close_node(o, r)
    nodes["hang_up"] = {
        "name": "hang_up", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {"type": "function", "function": {"name": "call_closed", "handler": "__function__:end_call",
                     "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
    }
    return {
        "initial_node": "setup",
        "system_prompt": SYSTEM,
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
    }


def contract(slot):
    return {"terminal_tools": [{"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": "briefs/brief-a.md", "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."},
    ] + ([{"source": "briefs/brief-b.md", "quote": "The outcome table of Brief A applies."}] if slot == "brief-b" else [])}],
        "every_call_ends_with_terminal": True}


if __name__ == "__main__":
    (ROOT / "out").mkdir(exist_ok=True)
    for slot, multi in (("brief-a", False), ("brief-b", True)):
        json.dump(build(multi), open(ROOT / "out" / (slot + ".workflow.json"), "w"), indent=1)
        json.dump(contract(slot), open(ROOT / "out" / (slot + ".contract.json"), "w"), indent=1)
        print("wrote", slot)
