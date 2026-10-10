"""Generate out/pl-g7-multi-raw.workflow.json and its contract from the rules of briefs/pl-g7-multi-raw.md."""
import json
from pathlib import Path

SLOT = "pl-g7-multi-raw"
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"
OUT = Path(__file__).resolve().parent

# ------------------------------------------------------------------ shared date code (runs in code steps)
DATE_CODE = r'''
import datetime
def _parse_now(s):
    s = str(s or '').strip().replace(' ', 'T')
    for cut in (19, 16):
        try:
            return datetime.datetime.fromisoformat(s[:cut])
        except Exception:
            pass
    try:
        return datetime.datetime.fromisoformat(s[:10] + 'T09:00')
    except Exception:
        return datetime.datetime(2026, 10, 14, 11, 0)
NOW = _parse_now(vars.get('now'))
TODAY = NOW.date()
_hol = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
# Operations memo OM-17 (9 October 2026): 21 October is a holiday, 26 October is a business day.
if TODAY >= datetime.date(2026, 10, 9):
    _hol = [h for h in _hol if h != '2026-10-26'] + ['2026-10-21']
HOL = set(_hol)
ONE = datetime.timedelta(days=1)
def isbiz(d):
    return d.weekday() < 5 and d.isoformat() not in HOL
def nth_biz(n):
    d = TODAY
    k = 0
    while k < n:
        d = d + ONE
        if isbiz(d):
            k += 1
    return d
def next_biz_after(d):
    d = d + ONE
    while not isbiz(d):
        d = d + ONE
    return d
def spoken(d):
    return d.strftime('%A') + ', ' + str(d.day) + ' ' + d.strftime('%B') + ' ' + str(d.year)
def last_biz_of_week(monday):
    for i in range(4, -1, -1):
        d = monday + datetime.timedelta(days=i)
        if isbiz(d):
            return d
    return None
MONDAY = TODAY - datetime.timedelta(days=TODAY.weekday())
_a1 = last_biz_of_week(MONDAY)
if _a1 is None or _a1 <= TODAY:
    _a1 = last_biz_of_week(MONDAY + datetime.timedelta(days=7))
ATTEMPT1 = _a1
'''

SETUP_CODE = DATE_CODE + r'''
try:
    lines = []
    lines.append('Today is ' + spoken(TODAY) + ' (' + TODAY.isoformat() + '), time now ' + NOW.strftime('%H:%M') + '. Today is ' + ('a business day.' if isbiz(TODAY) else 'NOT a business day.'))
    lines.append('Bank holidays (not business days): ' + ', '.join(sorted(HOL)) + '. Business days are Monday to Friday except these holidays.')
    lines.append('Calendar (week = Monday to Sunday):')
    k = 0
    for i in range(0, 26):
        d = TODAY + datetime.timedelta(days=i)
        if i > 0 and isbiz(d):
            k += 1
        wk = (d - datetime.timedelta(days=d.weekday()) - MONDAY).days // 7
        week = 'this week' if wk == 0 else ('next week' if wk == 1 else 'week +' + str(wk))
        if i == 0:
            kind = 'TODAY, ' + ('business day' if isbiz(d) else ('bank holiday' if d.isoformat() in HOL else 'weekend'))
        elif isbiz(d):
            kind = 'business day number ' + str(k) + ' after today'
        elif d.isoformat() in HOL:
            kind = 'BANK HOLIDAY, not a business day'
        else:
            kind = 'weekend, not a business day'
        lines.append('- ' + d.isoformat() + ' ' + spoken(d) + ' [' + week + '] ' + kind)
    vars['date_facts'] = '\n'.join(lines)
    nb = next_biz_after(TODAY)
    vars['today_iso'] = TODAY.isoformat()
    vars['today_spoken'] = spoken(TODAY)
    vars['now_time'] = NOW.strftime('%H:%M')
    vars['next_biz_iso'] = nb.isoformat()
    vars['next_biz_spoken'] = spoken(nb)
    cb = []
    cb.append('Allowed callback slots: a time from 10:00 to 19:00 (both included) on either of these two days only:')
    if NOW.strftime('%H:%M') < '19:00':
        cb.append('- today, ' + spoken(TODAY) + ' (' + TODAY.isoformat() + '), but only at a time later than ' + NOW.strftime('%H:%M') + ' and not before 10:00')
    else:
        cb.append('- today is no longer possible (it is after 19:00)')
    cb.append('- the next business day, ' + spoken(nb) + ' (' + nb.isoformat() + '), from 10:00 to 19:00')
    cb.append('Any other day (for example later in the week, a weekend or a holiday) or any other time is outside the window.')
    vars['callback_facts'] = '\n'.join(cb)
    vars['setup_state'] = 'ok'
except Exception as e:
    vars['date_facts'] = 'Date facts unavailable.'
    vars['callback_facts'] = 'Callback window: today or the next business day, 10:00 to 19:00.'
    vars['setup_state'] = 'error'
'''

PREPARE_CODE = DATE_CODE + r'''
import json, re
def _load(v):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            try:
                import ast
                v = ast.literal_eval(v)
            except Exception:
                return None
    return v
def _find_products():
    for key in ('products', 'get_account_response.data.products', 'load_account_response.data.products'):
        v = _load(vars.get(key))
        if isinstance(v, list) and v:
            return v
    for key in ('get_account_response.data', 'load_account_response.data', 'get_account_response', 'load_account_response'):
        v = _load(vars.get(key))
        if isinstance(v, dict):
            if isinstance(v.get('products'), list) and v.get('products'):
                return v.get('products')
            dd = v.get('data')
            if isinstance(dd, dict) and isinstance(dd.get('products'), list) and dd.get('products'):
                return dd.get('products')
    rows = dict()
    pat = re.compile(r'products\.(\d+)\.(\w+)$')
    for k in list(vars.keys()):
        m = pat.search(str(k))
        if m:
            rows.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
    if rows:
        return [rows[i] for i in sorted(rows)]
    return []
def _num(x):
    try:
        return float(x)
    except Exception:
        return None
def amt(x):
    return format(float(x), ',.2f')
try:
    prods = _find_products()
    items = []
    for p in prods[:3]:
        if not isinstance(p, dict):
            continue
        t = str(p.get('type') or '')
        pid = str(p.get('product_id') or '')
        if not pid:
            continue
        if t == 'credit_card':
            label = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = _num(p.get('minimum_payment'))
            floor_name = 'minimum payment'
        elif t == 'car_loan':
            label = 'car loan'
            floor = _num(p.get('instalment_amount'))
            floor_name = 'instalment amount'
        else:
            label = 'personal loan'
            floor = _num(p.get('instalment_amount'))
            floor_name = 'instalment amount'
        due = _num(p.get('past_due')) or 0.0
        if floor is None or floor > due:
            floor = due
        try:
            late = int(float(p.get('days_late')))
        except Exception:
            late = 0
        if late <= 7:
            band = 'early'
            attempts = 1
            deadline = nth_biz(12)
        else:
            band = 'late'
            attempts = 2
            deadline = nth_biz(7)
        if t == 'car_loan':
            cap = nth_biz(5)
            if cap < deadline:
                deadline = cap
        a1 = ATTEMPT1 if ATTEMPT1 <= deadline else deadline
        items.append(dict(pid=pid, label=label, due=due, floor=floor, floor_name=floor_name, late=late,
                          band=band, attempts=attempts, deadline=deadline, a1=a1))
    if not items:
        raise ValueError('no products')
    facts = []
    stmt = []
    for n, it in enumerate(items, 1):
        s = 'PRODUCT ' + str(n) + ': product_id ' + it['pid'] + ', ' + it['label'] + '. Past-due amount ' + amt(it['due']) + ', ' + str(it['late']) + ' days late. '
        s += 'Band ' + it['band'] + ', persuasion attempts allowed: ' + str(it['attempts']) + '. '
        s += 'Floor (' + it['floor_name'] + '): ' + amt(it['floor']) + '. Any amount from ' + amt(it['floor']) + ' to ' + amt(it['due']) + ' (both included) can be accepted. '
        s += 'Deadline (latest date that can be recorded): ' + spoken(it['deadline']) + ' = ' + it['deadline'].isoformat() + '. Allowed promise dates: business days from today ' + TODAY.isoformat() + ' to ' + it['deadline'].isoformat() + '. '
        s += 'Attempt 1 offer: ' + amt(it['due']) + ' (or the floor ' + amt(it['floor']) + ' if the customer already said the full amount is too much) on ' + spoken(it['a1']) + ' = ' + it['a1'].isoformat() + '. '
        if it['attempts'] >= 2:
            s += 'Attempt 2 offer: the floor ' + amt(it['floor']) + ' on the deadline ' + spoken(it['deadline']) + ' = ' + it['deadline'].isoformat() + '.'
        else:
            s += 'No attempt 2 for this product (early band).'
        facts.append(s)
        stmt.append('Your ' + it['label'] + ' has ' + amt(it['due']) + ' past due and is ' + str(it['late']) + ' days late.')
    if len(items) == 1:
        opening = 'I am calling from the collections team about a late payment. ' + ' '.join(stmt) + ' Can you make this payment today?'
        vars['today_question'] = 'Can you make this payment today?'
    else:
        opening = 'I am calling from the collections team about late payments on ' + str(len(items)) + ' products. ' + ' '.join(stmt) + ' Can you pay all of them today?'
        vars['today_question'] = 'Can you pay all of them today?'
    vars['account_facts'] = '\n'.join(facts)
    vars['debt_statement'] = opening
    vars['product_count'] = len(items)
    vars['product_ids'] = ', '.join(it['pid'] for it in items)
    vars['account_state'] = 'ready'
except Exception as e:
    vars['account_facts'] = 'Account details unavailable.'
    vars['debt_statement'] = ''
    vars['product_count'] = 0
    vars['product_ids'] = ''
    vars['account_state'] = 'error'
'''

GATE_CODE = "vars['gate_passed'] = 'yes'\n"

# ------------------------------------------------------------------ hooks
VERIFY_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            left = d.get('wrong_answers_left')
            try:
                left = int(left) if left is not None else None
            except Exception:
                left = None
            if d.get('all_verified') is True or str(d.get('all_verified')).lower() == 'true':
                msg = 'Both answers are verified.'
            elif d.get('hint') == 'day_month_swapped':
                msg = 'Day and month look swapped. This is NOT counted as a wrong answer. Ask the customer to say the date of birth again with the month as a word (for example 5 March 1980), then call verify_identity again.'
            elif d.get('verified') is True or str(d.get('verified')).lower() == 'true':
                msg = 'This answer is correct. If this was the date of birth, now ask for the last four digits of the phone number on file. Say nothing about the account yet.'
            elif left is not None and left <= 0:
                msg = 'CHECK FAILED: no answers left. Do not state any debt or account detail. Say you could not verify their identity, that they can use the Freya Bank mobile app or visit a branch, thank them and say goodbye, and in that same message call transition_to_close_not_verified_failed.'
            elif d.get('ok') is False or str(d.get('ok')).lower() == 'false':
                msg = 'The answer could not be checked and was not counted. Ask the same question again and call verify_identity with the new answer (date of birth as YYYY-MM-DD).'
            else:
                msg = 'Wrong answer. Say it does not match our records and ask the same question again.'
                if left is not None:
                    msg += ' Wrong answers left in total: ' + str(left) + '.'
            d['what_to_do_next'] = msg
        else:
            result['what_to_do_next'] = 'The check service did not answer. Say there was a technical problem and ask the same question again.'
except Exception:
    pass
'''

GENERIC_POST = r'''
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        ok = isinstance(d, dict) and (d.get('ok') is True or str(d.get('ok')).lower() == 'true')
        if isinstance(d, dict):
            d['what_to_do_next'] = '__OK__' if ok else '__FAIL__'
        else:
            result['what_to_do_next'] = '__FAIL__'
except Exception:
    pass
'''

def post_hook(ok_msg, fail_msg):
    return GENERIC_POST.replace("'__OK__'", repr(ok_msg)).replace("'__FAIL__'", repr(fail_msg))

CALLBACK_PRE = DATE_CODE + r'''
try:
    b = config.get('body')
    good = False
    if isinstance(b, dict):
        ds = str(b.get('date') or '').strip()[:10]
        tm = str(b.get('time') or '').strip()
        if len(tm) == 4 and tm[1] == ':':
            tm = '0' + tm
            b['time'] = tm
        d = datetime.date.fromisoformat(ds)
        hhmm = tm[:5]
        in_window = '10:00' <= hhmm <= '19:00' and len(hhmm) == 5 and hhmm[2] == ':'
        if d == TODAY:
            good = in_window and hhmm > NOW.strftime('%H:%M')
        elif d == next_biz_after(TODAY):
            good = in_window
    if not good:
        config['url'] = str(config.get('url') or '').rsplit('/', 1)[0] + '/callback_outside_allowed_window'
except Exception:
    try:
        config['url'] = str(config.get('url') or '').rsplit('/', 1)[0] + '/callback_outside_allowed_window'
    except Exception:
        pass
'''

# ------------------------------------------------------------------ builders
def api_tool(name, path, fields, description, required=None, retries=0, pre=None, post=None, mapping=None):
    props = {"customer_id": {"type": "string", "default": "{{customer_id}}"}}
    props.update(fields)
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
                    "url": {"type": "string", "default": BASE + path},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "required": required or [], "properties": props},
                },
            },
        },
    }
    if pre:
        t["pre_process_code"] = pre
    if post:
        t["post_process_code"] = post
    if mapping:
        t["response_mapping"] = mapping
    return t


def code_fn(code):
    return {"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
            "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code},
                                                            "timeout_ms": {"type": "number", "default": 10000}}}}}


def cond_or(*conds):
    return {"logic": "or", "conditions": list(conds)}


def gt0(var):
    return {"variable": var, "operator": "greater_than", "operand": 0}


def tool_tr(target, desc):
    return {"target_node": target, "description": desc, "is_tool_call": True,
            "condition": {"operator": "matches_intent", "description": desc}}


def conv(name, task, tools=None, transitions=None, on_enter=None, max_turns=30, max_target="", extraction=None, first_only=False):
    n = {"name": name, "node_type": "conversation", "task_message": task, "tools": tools or [],
         "transitions": transitions or [], "on_enter": on_enter or {"type": "llm"},
         "on_enter_first_entry_only": first_only, "max_node_turns": max_turns,
         "extraction_schema": extraction or [], "truncation_strategy": "keep_all", "interruptible": True}
    if max_target:
        n["max_turn_transition"] = max_target
    return n


def code_node(name, code, transitions):
    return {"name": name, "node_type": "code", "passthrough": True,
            "passthrough_default_transition": transitions[-1]["target_node"],
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [code_fn(code)], "transitions": transitions}


ALWAYS = lambda t: {"target_node": t, "description": "always", "condition": {"operator": "always"}}

# ------------------------------------------------------------------ tools
VERIFY = api_tool(
    "verify_identity", "/verify_identity",
    {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
               "description": "Which security answer this is: date_of_birth or phone_last4."},
     "answer": {"type": "string", "default": "{{answer}}",
                "description": "date_of_birth: the date as YYYY-MM-DD (numbers only given by the customer are day, then month, then year). phone_last4: exactly four digits."}},
    "Check one security answer. CALL it every time the customer gives an answer to a security question, one answer per call.",
    required=["field", "answer"], post=VERIFY_POST)

def transfer_tool(name, queue, when):
    return api_tool(name, "/transfer_to_agent",
                    {"queue": {"type": "string", "enum": ["restructuring", "general", "support"], "default": queue}},
                    when, required=["queue"])

T_HUMAN = transfer_tool("transfer_human", "general",
                        "Transfer the call to a person (queue general). CALL it only when the customer insists on a human after you asked once whether you can help. In the same message tell them you are connecting them now, thank them and say goodbye.")
T_RESTR = transfer_tool("transfer_restructuring", "restructuring",
                        "Transfer the call to the restructuring team. CALL it as soon as the customer asks for a new payment plan or lower instalments. Do not describe any plan. In the same message tell them you are connecting them to a colleague, thank them and say goodbye. Do not call add_note or create_promise together with it.")
T_SUPPORT = transfer_tool("transfer_support", "support",
                          "Transfer the call to the customer support team. CALL it only when a customer who mentioned illness, a death in the family or job loss accepts your offer to connect them with support. In the same message tell them you are connecting them, thank them and say goodbye.")

CALLBACK = api_tool(
    "schedule_callback", "/schedule_callback",
    {"date": {"type": "string", "default": "{{date}}", "description": "Callback date as YYYY-MM-DD. Only today or the next business day."},
     "time": {"type": "string", "default": "{{time}}", "description": "Callback time as HH:MM, 24 hour, from 10:00 to 19:00."}},
    "Book a callback for the customer. CALL it once the person names a day and time inside the allowed callback window.",
    required=["date", "time"], pre=CALLBACK_PRE,
    post=post_hook("Callback booked. Thank the person, say goodbye, and in that same message call transition_to_close_not_reached_callback.",
                   "NOT booked: the time is outside the allowed window or the service failed. Do not say it is booked. If you have not yet asked for another time, ask once for another time inside the window. Otherwise thank them, say goodbye and call transition_to_close_not_reached_no_callback."))

PROMISE = api_tool(
    "create_promise", "/create_promise",
    {"product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id from the account facts, for example p1. Copy it exactly."},
     "amount": {"type": "number", "default": "{{amount}}", "description": "The confirmed amount, a number like 1250.50."},
     "date": {"type": "string", "default": "{{date}}", "description": "The confirmed payment date as YYYY-MM-DD."}},
    "Record one payment promise for one product. CALL it only after the customer said a clear yes to the read-back. One call per product.",
    required=["product_id", "amount", "date"],
    post=post_hook("Promise recorded for this product.",
                   "NOT recorded. Do not say it is recorded. If this is the first failure for this product, call create_promise again once with the same values. If it already failed twice, tell the customer you could not record it and call add_note with reason service_error for this product."))

NOTE = api_tool(
    "add_note", "/add_note",
    {"product_id": {"type": "string", "default": "{{product_id}}", "description": "product_id from the account facts, for example p1. Copy it exactly."},
     "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "already_paid", "service_error"], "default": "{{reason}}",
                "description": "Why this product ended without a promise: refused, hardship, dispute, already_paid or service_error."},
     "text": {"type": "string", "default": "{{text}}", "description": "One short sentence on what the customer said."}},
    "Record why one product ended without a promise. CALL it once for every product that has no recorded promise, before you close the call. Never call it when the call is transferred.",
    required=["product_id", "reason"],
    post=post_hook("Note saved.", "The note was not saved. Call add_note again once with the same values."))

# ------------------------------------------------------------------ closing steps
CLOSINGS = {
    "close_promise": ("promise", ""),
    "close_paid": ("paid", ""),
    "close_transferred_restructuring": ("transferred", "restructuring"),
    "close_transferred_human": ("transferred", "human"),
    "close_transferred_support": ("transferred", "support"),
    "close_no_promise_refused": ("no_promise", "refused"),
    "close_no_promise_hardship": ("no_promise", "hardship"),
    "close_no_promise_dispute": ("no_promise", "dispute"),
    "close_no_promise_service_error": ("no_promise", "service_error"),
    "close_not_verified_failed": ("not_verified", "failed"),
    "close_not_verified_declined": ("not_verified", "declined"),
    "close_not_reached_callback": ("not_reached", "callback"),
    "close_not_reached_no_callback": ("not_reached", "no_callback"),
    "close_not_reached_wrong_number": ("not_reached", "wrong_number"),
    "close_not_reached_deceased": ("not_reached", "deceased"),
    "close_not_reached_unclear": ("not_reached", "unclear"),
}

nodes = {}
for key, (outcome, reason) in CLOSINGS.items():
    fields = {"outcome": {"type": "string", "enum": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"], "default": outcome}}
    if reason:
        fields["reason"] = {"type": "string", "default": reason}
    tool = api_tool("close_call", "/close_call", fields, "Record how the call ended.", required=["outcome"], retries=1)
    nodes[key] = {"name": key, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "end",
                  "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                  "pre_actions": [tool], "response_mapping": [], "transitions": [ALWAYS("end")]}

nodes["end"] = {"name": "end", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                "transitions": [], "terminal": {"type": "function", "function": {"name": "call_closed", "handler": "__function__:end_call",
                                                                                 "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}

# Gates for the endings after the account is stated: a recorded promise always wins (CC-2 / annex closing).
PROMISE_WINS = {"target_node": "close_promise", "description": "at least one promise was recorded",
                "condition": cond_or(gt0("create_promise_success_count"))}
for gate, target in [("gate_paid", "close_paid"), ("gate_refused", "close_no_promise_refused"),
                     ("gate_hardship", "close_no_promise_hardship"), ("gate_dispute", "close_no_promise_dispute"),
                     ("gate_service_error", "close_no_promise_service_error")]:
    nodes[gate] = code_node(gate, GATE_CODE, [PROMISE_WINS, ALWAYS(target)])
nodes["gate_promise"] = code_node("gate_promise", GATE_CODE, [
    PROMISE_WINS,
    {"target_node": "close_no_promise_service_error", "description": "promise calls failed",
     "condition": cond_or(gt0("create_promise_failure_count"))},
    ALWAYS("close_no_promise_refused")])

def transfer_routes(names):
    out = []
    for tname, target in names:
        out.append({"target_node": target, "description": tname + " done", "condition": cond_or(gt0(tname + "_success_count"))})
    return out

# ------------------------------------------------------------------ prompts
SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Freya Bank is calling the customer. Speak English. Keep every turn short: one or two short sentences, plain words, no technical words. Ask one question at a time.
Rules that hold in every step:
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this is a scam: say they can verify this call by phoning Freya Bank's customer service number, then continue.
- If you cannot answer a question from the information you have, say you do not have that information. Never invent figures, dates, reasons or terms.
- Never offer a discount, a waiver, an instalment plan or any term that is not in your instructions.
- After every tool result, speak to the customer or call the next tool. Never end a turn with nothing. Obey the what_to_do_next field of a tool result.
- Never say something is recorded, booked or saved unless the tool result says ok true.
- Never call a transition_to_... tool in the same message as another tool. Before calling a transition_to_close... tool, thank the customer and say goodbye in that same message.
- Never mention the words collections, debt, payment, amount or any product before the identity check has passed."""

OPENING_TASK = """You have just said: "Hello, this is Freya Bank's digital assistant. This call is recorded. Am I speaking with {{title}} {{last_name}}?"
Your only job is to find out who is on the line. Say nothing about why you are calling.
- Only "yes", "that's me", "speaking", or the person saying the customer's own name ({{first_name}} {{last_name}}) counts as confirmation. Then call transition_to_identity at once (no text needed).
- "Hello", "go ahead", "who is this" and similar are NOT confirmation. Answer any question first (who you are: Freya Bank's digital assistant), then ask again: "Am I speaking with {{title}} {{last_name}}?". That is the second ask. If the answer to the second ask is still not a confirmation, thank them, say goodbye and call transition_to_close_not_reached_unclear.
- If the person says they are someone else (a relative, a colleague) or that the customer is not available, call transition_to_third_party at once.
- If the person says this number does not belong to the customer, apologise, say goodbye and call transition_to_close_not_reached_wrong_number.
- If the person says the customer has died, say exactly "I am sorry for your loss." then a short goodbye, ask nothing else, and call transition_to_close_not_reached_deceased.
- If the person says they do not want to talk: say once that it only takes a moment. If they say it a second time, thank them, say goodbye and call transition_to_close_not_verified_declined.
- If they ask for a human: ask once whether you can help first. If they insist, call transfer_human.
No other tool is allowed here."""

THIRD_PARTY_TASK = """The person on the line is not {{title}} {{last_name}}. Do not say why you are calling and say nothing about any account, even if they ask or offer to pay. If asked, say only that you are Freya Bank's digital assistant and that the call is recorded. A relative may not answer security questions.
Ask when {{title}} {{last_name}} can be reached.
{{callback_facts}}
Now: {{now}}.
- When the person names a day and a time inside the allowed window, call schedule_callback with the date (YYYY-MM-DD) and the time (HH:MM, 24 hour). Turn words like "tomorrow afternoon at three" into an exact date and time; if only a vague time is given, ask for the exact time.
- If the day or time they name is outside the window, say you can only call back today or on {{next_biz_spoken}} between 10:00 and 19:00 and ask once for another time. If the second answer is also outside the window, or they cannot give a time, do not book: thank them, say goodbye and call transition_to_close_not_reached_no_callback.
- If they say the number does not belong to the customer: apologise, say goodbye, call transition_to_close_not_reached_wrong_number.
- If they say the customer has died: say exactly "I am sorry for your loss." then a short goodbye, ask nothing else, call transition_to_close_not_reached_deceased.
- If the customer {{title}} {{last_name}} comes to the phone and confirms who they are, call transition_to_identity.
- After schedule_callback, follow its what_to_do_next."""

IDENTITY_TASK = """The customer has confirmed who they are. Now verify identity with two security questions, one at a time. Say nothing about the reason for the call, the account, any product or any amount until both are verified.
1. Ask for their date of birth. Call verify_identity with field date_of_birth and the answer as YYYY-MM-DD, whatever way they said it. A date given only as numbers is day, then month, then year (for example 04/09/1985 is 1985-09-04).
2. When the date of birth is correct, ask for the last four digits of the phone number on file. Call verify_identity with field phone_last4 and four digits.
Call verify_identity every time they give an answer. Follow the what_to_do_next of each result. A wrong answer may be asked again; three wrong answers in total end the check.
- If they do not want to answer, or ask what the call is about instead of answering: explain once that these questions protect their account, and ask again. If they refuse again or ask again what it is about, thank them, say goodbye and call transition_to_close_not_verified_declined.
- If they say twice that they do not want to talk, thank them, say goodbye and call transition_to_close_not_verified_declined.
- If verification fails (no answers left): do not state any debt; tell them to use the Freya Bank mobile app or visit a branch, thank them, say goodbye and call transition_to_close_not_verified_failed.
- If they ask for a human: ask once whether you can help first. If they insist, call transfer_human.
- If someone says the customer has died or the number is wrong, follow the same handling as before: wrong number -> transition_to_close_not_reached_wrong_number; died -> say "I am sorry for your loss." and call transition_to_close_not_reached_deceased."""

ACCOUNT_TASK = """The customer is verified. You already said: "Thank you, that is verified. {{debt_statement}}"
ACCOUNT FACTS (in get_account order; use these numbers and ids exactly):
{{account_facts}}

DATE FACTS:
{{date_facts}}

TOOLS: create_promise (one per product, only after a clear yes to the read-back), add_note (one per product without a promise), transfer_restructuring, transfer_support, transfer_human. When a rule says to use a tool, call the tool; saying it is not enough.

HOW TO GET PROMISES
- You already asked "{{today_question}}". If the customer says yes, every product is promised for its full past-due amount on today {{today_iso}}; go to the read-back. Do not ask about today again later. If today is not a business day (see DATE FACTS), today cannot be recorded: offer the next business day instead.
- If not, go through the products one by one in the order above, each starting at its attempt 1. Persuasion attempts are counted per product.
- Never ask "how much can you pay?". You propose every amount. Ask for the full past-due amount first.
- A date or an amount the customer proposes is never a refusal: check it with the rules below.
- A flat refusal or a non-answer for a product uses one attempt. A no to paying today with no date and no amount is a flat refusal.
  Attempt 1: propose the attempt 1 offer of that product (full amount, or the floor if the customer already said the full amount is too much, on the attempt 1 date).
  Attempt 2 (late band only): propose the floor on that product's deadline.
  When the attempts of a product are used up, stop for that product: it is refused. Never repeat an offer the customer already refused. Move to the next product.
- Amounts: if the customer says the full amount is too much, offer the floor of that product once and say the rest stays overdue. If they refuse the floor, that is a flat refusal (uses an attempt). An amount from the floor up to the full past-due (both included) is accepted. Below the floor: say it cannot be recorded and offer the floor once; if they do not accept it, that is a flat refusal.
- Dates: a promise date must be today or later, a business day, and not after that product's deadline (see the calendar).
  A weekend day or holiday that is not after the deadline: offer the next business day.
  A date after the deadline: say the latest date you can record is the deadline (say it) and offer it. If they refuse the deadline, that is a flat refusal.
  A vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day. If they still give none, propose the deadline.
  "Next <weekday>" means that weekday in the following calendar week; "this <weekday>" means the one in the current week (use the week labels of the calendar).
  If the customer names one date for everything and it is after one product's deadline, that product gets its own deadline and you say so in the read-back; the other products keep the named date.
- If the customer mentions illness, a death in the family or job loss: say one short sentence of sympathy, make no persuasion attempt, and offer to connect them with the customer support team. If they accept, call transfer_support. If they decline, the products without a promise get reason hardship. If they still name a date or amount themselves, record that promise under the rules above.
- "I already paid" for a product: say payments can take one business day to appear; take no promise for that product (reason already_paid) and continue with the other products.
- "This is not mine", "I never had this product", or the product was closed or paid off in the past: do not argue, take no promise for that product (reason dispute) and continue with the others.
- A request for a new payment plan or lower instalments: do not describe any plan, call transfer_restructuring at once. Promises not yet recorded are not recorded. No notes.
- A request for a human: ask once whether you can help first. If they insist, call transfer_human. No notes.
- If the customer says twice that they do not want to talk: the remaining products are refused.

CONFIRM AND RECORD
- Read back all agreed promises together: for each product its name, amount and date (and say when a product was moved to its own deadline). Then ask "Do you confirm?".
- If they change a date or amount, check it again with the rules and read back again.
- Only after a clear yes, call create_promise once per agreed product (product_id, amount as a number, date as YYYY-MM-DD).
- Say a promise is recorded only for products whose result says ok true. If a create_promise fails, call it once more for that product. If it fails a second time, say you could not record that one; that product gets reason service_error. Promises that were recorded stay.
- After at least one recorded promise, say exactly: "You will receive a text message confirming this promise."
- A recorded promise cannot be changed or cancelled in this call; if asked, say they can change it in the mobile app.

CLOSING
- When every product is settled (promised, or ended without a promise), call add_note once for each product without a recorded promise, with its product_id and reason (refused, hardship, dispute, already_paid or service_error). Wait for the results.
- Never call add_note when the call is transferred (restructuring, support, human), before or after the transfer.
- Then, in a message with no other tool: thank the customer, say goodbye, and call exactly one of:
  transition_to_gate_promise if at least one promise was recorded;
  otherwise, if every product was noted already_paid: transition_to_gate_paid;
  otherwise take the reason of the FIRST product (in the order above) whose note is not already_paid, and call transition_to_gate_refused, transition_to_gate_hardship, transition_to_gate_dispute or transition_to_gate_service_error for that reason."""

UNAVAILABLE_TASK = """The account details could not be loaded because of a technical problem. Do not state any amount, product or date. Tell the customer you cannot access the details right now, apologise, thank them, say goodbye, and in that same message call transition_to_close_no_promise_service_error. No other tool is allowed."""

# ------------------------------------------------------------------ steps
nodes["setup"] = code_node("setup", SETUP_CODE, [ALWAYS("opening")])

nodes["opening"] = conv(
    "opening", OPENING_TASK, tools=[T_HUMAN],
    on_enter={"type": "tts", "text": "Hello, this is Freya Bank's digital assistant. This call is recorded. Am I speaking with {{title}} {{last_name}}?"},
    first_only=True, max_turns=12, max_target="close_not_reached_unclear",
    transitions=transfer_routes([("transfer_human", "close_transferred_human")]) + [
        tool_tr("identity", "The person confirmed they are the customer"),
        tool_tr("third_party", "Someone other than the customer answered"),
        tool_tr("close_not_reached_unclear", "Still no confirmation after the second ask"),
        tool_tr("close_not_reached_wrong_number", "The number does not belong to the customer"),
        tool_tr("close_not_reached_deceased", "The customer has died"),
        tool_tr("close_not_verified_declined", "The person said twice they do not want to talk"),
    ])

nodes["third_party"] = conv(
    "third_party", THIRD_PARTY_TASK, tools=[CALLBACK], max_turns=14, max_target="close_not_reached_no_callback",
    transitions=[
        tool_tr("close_not_reached_callback", "The callback was booked"),
        tool_tr("close_not_reached_no_callback", "No callback inside the window could be agreed"),
        tool_tr("close_not_reached_wrong_number", "The number does not belong to the customer"),
        tool_tr("close_not_reached_deceased", "The customer has died"),
        tool_tr("identity", "The customer came to the phone and confirmed who they are"),
    ])

nodes["identity"] = conv(
    "identity", IDENTITY_TASK, tools=[VERIFY, T_HUMAN], max_turns=20, max_target="close_not_verified_declined",
    on_enter={"type": "tts", "text": "Thank you. Before we continue, I need to ask two security questions. What is your date of birth?"},
    first_only=True,
    transitions=[{"target_node": "load_account", "description": "both security answers verified",
                  "condition": cond_or({"variable": "verify_identity_response.data.all_verified", "operator": "equals", "operand": "true"},
                                       {"variable": "verify_identity_response.data.all_verified", "operator": "equals", "operand": "True"})}]
    + transfer_routes([("transfer_human", "close_transferred_human")]) + [
        tool_tr("close_not_verified_failed", "The identity check failed after three wrong answers"),
        tool_tr("close_not_verified_declined", "The customer declined the security questions"),
        tool_tr("close_not_reached_wrong_number", "The number does not belong to the customer"),
        tool_tr("close_not_reached_deceased", "The customer has died"),
    ])

GET_ACCOUNT = api_tool("get_account", "/get_account", {}, "Get the late products.", retries=2)
nodes["load_account"] = {"name": "load_account", "node_type": "api_request", "passthrough": True,
                         "passthrough_default_transition": "prepare_account", "on_enter": {"type": "silent"},
                         "disable_inactivity_monitor": True, "pre_actions": [GET_ACCOUNT],
                         "response_mapping": [{"path": "data.products", "variable": "products"}],
                         "transitions": [ALWAYS("prepare_account")]}

nodes["prepare_account"] = code_node("prepare_account", PREPARE_CODE, [
    {"target_node": "account", "description": "products loaded",
     "condition": cond_or({"variable": "account_state", "operator": "equals", "operand": "ready"})},
    ALWAYS("account_unavailable")])

nodes["account"] = conv(
    "account", ACCOUNT_TASK, tools=[PROMISE, NOTE, T_RESTR, T_SUPPORT, T_HUMAN], max_turns=60, max_target="gate_refused",
    on_enter={"type": "tts", "text": "Thank you, that is verified. {{debt_statement}}"}, first_only=True,
    transitions=transfer_routes([("transfer_restructuring", "close_transferred_restructuring"),
                                 ("transfer_support", "close_transferred_support"),
                                 ("transfer_human", "close_transferred_human")]) + [
        tool_tr("gate_promise", "At least one promise was recorded and the call is finished"),
        tool_tr("gate_paid", "Every product was noted already_paid and the call is finished"),
        tool_tr("gate_refused", "No promise; the first product not already paid ended as refused"),
        tool_tr("gate_hardship", "No promise; the first product not already paid ended as hardship"),
        tool_tr("gate_dispute", "No promise; the first product not already paid ended as dispute"),
        tool_tr("gate_service_error", "No promise; the first product not already paid ended as service_error"),
    ])

nodes["account_unavailable"] = conv(
    "account_unavailable", UNAVAILABLE_TASK, max_turns=4, max_target="close_no_promise_service_error",
    transitions=[tool_tr("close_no_promise_service_error", "The account could not be loaded")])

workflow = {
    "initial_node": "setup",
    "system_prompt": SYSTEM,
    "nodes": nodes,
    "global_nodes": {},
    "test_variables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"},
}

(OUT / f"{SLOT}.workflow.json").write_text(json.dumps(workflow, indent=1))

contract = {
    "terminal_tools": [{"tool": "close_call", "evidence": [
        {"source": "tools/openapi.json", "quote": "End the call. Always the last tool call. Nothing is accepted after it."},
        {"source": f"briefs/{SLOT}.md", "quote": "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."}]}],
    "every_call_ends_with_terminal": True,
}
(OUT / f"{SLOT}.contract.json").write_text(json.dumps(contract, indent=1))
print("written")
