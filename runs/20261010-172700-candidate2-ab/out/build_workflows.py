"""Generate the Brief A and Brief B workflows.

    python3 out/build_workflows.py

Writes out/brief-a.workflow.json and out/brief-b.workflow.json.
Values (holidays, bands, outcomes, sentences) come from briefs/brief-a.md and briefs/brief-b.md.
Design: the model reports what the customer said through code_exec tools. Code keeps the counted state
(attempts, offers, deadlines) and decides the next allowed action. Every bank write except verify_identity
runs in an engine step with baked values. close_call runs in its own step, followed only by end_call.
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent
BASE = "https://freya-bank-mock.freyavoice.workers.dev/v1"

# From Brief A section 7.
HOLIDAYS = ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"]
# (min days_late, max days_late, band, deadline business days, persuasion attempts)
BANDS = [[1, 7, "early", 12, 1], [8, 45, "late", 7, 2]]

LIB = r'''
import json, datetime, re
HOLIDAYS = __HOLIDAYS__
BANDS = __BANDS__
MULTI = __MULTI__
NOTES = __NOTES__
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

def now_dt(V):
    s = str(V.get('now') or '').strip().replace(' ', 'T')
    try:
        return datetime.datetime.fromisoformat(s[:16])
    except Exception:
        pass
    try:
        return datetime.datetime.fromisoformat(s[:10] + 'T00:00')
    except Exception:
        return datetime.datetime.now()

def isbiz(d):
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS

def add_biz(d, n):
    x = d
    c = 0
    while c < n:
        x = x + datetime.timedelta(days=1)
        if isbiz(x):
            c += 1
    return x

def next_biz_from(d):
    x = d
    while not isbiz(x):
        x = x + datetime.timedelta(days=1)
    return x

def next_biz_after(d):
    return next_biz_from(d + datetime.timedelta(days=1))

def last_biz_of_week(d):
    mon = d - datetime.timedelta(days=d.weekday())
    x = mon + datetime.timedelta(days=4)
    while x >= mon and not isbiz(x):
        x = x - datetime.timedelta(days=1)
    return x if x >= mon else None

def attempt1_date(today):
    x = last_biz_of_week(today)
    if x is None or x <= today:
        x = last_biz_of_week(today + datetime.timedelta(days=7))
    return x

def speak(d):
    if isinstance(d, str):
        d = datetime.date.fromisoformat(d[:10])
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MONTHS[d.month - 1] + ' ' + str(d.year)

def money(x):
    return format(float(x), ',.2f')

def pdate(s):
    s = str(s or '').strip()
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None

def pnum(x):
    try:
        if x is None or str(x).strip() == '':
            return None
        return float(str(x).replace(',', '').replace('$', '').strip())
    except Exception:
        return None

def is_true(x):
    return str(x).strip().lower() == 'true'

def load(V):
    try:
        return json.loads(V.get('state_json') or '')
    except Exception:
        return dict(products=[], today_done=False, talk=0, hardship=False, hardship_done=False)

def save(V, st):
    V['state_json'] = json.dumps(st)

def today_of(V):
    return now_dt(V).date()
'''

SETUP = r'''
def main(V):
    n = now_dt(V)
    t = n.date()
    V['today_iso'] = t.isoformat()
    lines = ['CALENDAR (today is ' + speak(t) + ', time ' + n.strftime('%H:%M') + '):']
    mon = t - datetime.timedelta(days=t.weekday())
    for i in range(0, 35):
        d = mon + datetime.timedelta(days=i)
        if d < t:
            continue
        wk = (d - mon).days // 7
        label = 'this week' if wk == 0 else ('next week' if wk == 1 else ('week after next' if wk == 2 else 'in ' + str(wk) + ' weeks'))
        kind = 'business day' if isbiz(d) else ('bank holiday' if d.isoformat() in HOLIDAYS else 'weekend')
        tag = ' (today)' if d == t else (' (tomorrow)' if d == t + datetime.timedelta(days=1) else '')
        lines.append('- ' + d.isoformat() + ' ' + WD[d.weekday()] + tag + ', ' + label + ', ' + kind)
    lines.append('"Next <weekday>" means that weekday in next week. "This <weekday>" means the one in this week.')
    V['date_facts'] = '\n'.join(lines)
    V['next_biz_iso'] = next_biz_after(t).isoformat()
    V['next_biz_spoken'] = speak(next_biz_after(t))
    V['route'] = 'start'
    V['stage'] = 'opening'
    V['contact_text'] = 'Wait for the answer to your question.'
    V['id_text'] = 'Ask for the date of birth first.'
    V['state_text'] = ''
    V['closing_line'] = 'Thank you for your time. Goodbye.'
    V['final_outcome'] = 'no_promise'
    V['final_reason'] = 'refused'
    save(V, dict(products=[], today_done=False, talk=0, hardship=False, hardship_done=False, unclear=0, cb_bad=0, declines=0))
'''

CONTACT = r'''
def main(V, P):
    st = load(V)
    ev = str(P.get('result') or '').strip()
    t = today_of(V)
    n = now_dt(V)
    title = str(V.get('title') or '') + ' ' + str(V.get('last_name') or '')
    if ev == 'confirmed':
        V['route'] = 'identity'
        V['stage'] = 'identity'
    elif ev == 'not_confirmed':
        st['unclear'] = st.get('unclear', 0) + 1
        if st['unclear'] >= 2:
            V['ending'] = 'unclear'
            V['route'] = 'end'
        else:
            V['contact_text'] = 'NEXT ACTION: if they asked something, answer it in one sentence. Then ask once more: "Am I speaking with ' + title + '?". This is the last time you may ask.'
    elif ev == 'callback_time':
        d = pdate(P.get('date'))
        tm = str(P.get('time') or '').strip()
        m = re.match(r'^(\d{1,2})[:.]?(\d{2})?$', tm)
        ok = False
        hhmm = ''
        if d is not None and m:
            hh = int(m.group(1))
            mm = int(m.group(2) or 0)
            hhmm = '%02d:%02d' % (hh, mm)
            mins = hh * 60 + mm
            when = datetime.datetime(d.year, d.month, d.day, hh, mm)
            if (d == t or d == next_biz_after(t)) and 600 <= mins <= 1140 and when > n:
                ok = True
        if ok:
            V['cb_date'] = d.isoformat()
            V['cb_time'] = hhmm
            V['cb_spoken'] = speak(d) + ' at ' + hhmm
            V['ending'] = 'callback'
            V['route'] = 'callback'
        else:
            st['cb_bad'] = st.get('cb_bad', 0) + 1
            if st['cb_bad'] >= 2:
                V['ending'] = 'no_callback'
                V['route'] = 'end'
            else:
                win = 'today between now and 19:00' if n.hour < 19 else ''
                nb = speak(next_biz_after(t)) + ' between 10:00 and 19:00'
                V['contact_text'] = 'NEXT ACTION: say that time is not possible. Ask once for another time: ' + (win + ' or ' if win else '') + nb + '.'
    elif ev == 'no_callback':
        V['ending'] = 'no_callback'
        V['route'] = 'end'
    elif ev == 'wrong_number':
        V['ending'] = 'wrong_number'
        V['route'] = 'end'
    elif ev == 'deceased':
        V['ending'] = 'deceased'
        V['route'] = 'end'
    elif ev == 'refuses_to_talk':
        st['declines'] = st.get('declines', 0) + 1
        if st['declines'] >= 2:
            V['ending'] = 'declined'
            V['route'] = 'end'
        else:
            V['contact_text'] = 'NEXT ACTION: say it will only take a moment and ask again whether you are speaking with ' + title + '.'
    elif ev == 'transfer_human':
        V['transfer_queue'] = 'general'
        V['ending'] = 'transfer'
        V['route'] = 'transfer'
    save(V, st)
'''

IDEV = r'''
def main(V, P):
    st = load(V)
    ev = str(P.get('event') or '').strip()
    if ev == 'declines':
        st['declines'] = st.get('declines', 0) + 1
        if st['declines'] >= 2:
            V['ending'] = 'declined'
            V['route'] = 'end'
        else:
            V['id_text'] = 'NEXT ACTION: explain once, in one sentence, that these questions protect their account. Then ask the security question again. Do not say what the call is about.'
    elif ev == 'transfer_human':
        V['transfer_queue'] = 'general'
        V['ending'] = 'transfer'
        V['route'] = 'transfer'
    save(V, st)
'''

PREPARE = r'''
def label_of(p):
    t = str(p.get('type') or '')
    if t == 'credit_card':
        return 'credit card ending ' + str(p.get('card_last4') or '')
    return t.replace('_', ' ') or 'product'

def get_products(V):
    raw = V.get('products')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = None
    if isinstance(raw, dict):
        raw = raw.get('products')
    if isinstance(raw, list) and raw:
        return [x for x in raw if isinstance(x, dict)]
    found = dict()
    for k in list(V.keys()):
        m = re.search(r'products[.\[](\d+)\]?\.(\w+)$', str(k))
        if m:
            found.setdefault(int(m.group(1)), dict())[m.group(2)] = V.get(k)
    return [found[i] for i in sorted(found)]

def main(V):
    t = today_of(V)
    prods = get_products(V)
    out = []
    for i, p in enumerate(prods[:3]):
        try:
            dl = int(float(p.get('days_late') or 0))
            past = float(p.get('past_due') or 0)
            fl = p.get('minimum_payment') if str(p.get('type')) == 'credit_card' else p.get('instalment_amount')
            if fl is None:
                fl = p.get('minimum_payment') or p.get('instalment_amount') or past
            fl = float(fl)
            band = BANDS[-1]
            for b in BANDS:
                if b[0] <= dl <= b[1]:
                    band = b
            dead = add_biz(t, band[3])
            out.append(dict(n=i + 1, id=str(p.get('product_id') or ('p' + str(i + 1))), label=label_of(p), past_due=past,
                            floor=fl, days_late=dl, band=band[2], deadline=dead.isoformat(), max_att=band[4], att=0,
                            offer=dict(amount=past, date=t.isoformat(), kind='today'), refused=[], too_much=False,
                            floor_offered=False, below_offered=False, vague_asked=False, status='open', reason='',
                            agreed=None, adjusted=False, rec='', rec_fail=0, note_done=False, note_fail=0, msg=''))
        except Exception:
            pass
    st = load(V)
    st['products'] = out
    st['today_done'] = False
    st['talk'] = 0
    save(V, st)
    V['stage'] = 'negotiate'
    if not out:
        V['ending'] = 'account_error'
        V['route'] = 'end'
        return
    V['route'] = 'stay'
    if len(out) == 1:
        p = out[0]
        V['debt_text'] = ('Thank you, you are verified. I am calling from the collections team about a late payment on your ' + p['label'] +
                          '. The past-due amount is ' + money(p['past_due']) + ' and it is ' + str(p['days_late']) + ' days late. Can you make this payment today?')
    else:
        parts = ['Thank you, you are verified. I am calling from the collections team about late payments on ' + str(len(out)) + ' products.']
        for p in out:
            parts.append('Your ' + p['label'] + ' has ' + money(p['past_due']) + ' past due and is ' + str(p['days_late']) + ' days late.')
        parts.append('Can you pay all of them today?')
        V['debt_text'] = ' '.join(parts)
    render(V, st)
'''

ENGINE = r'''
def okey(a, d):
    return format(float(a), '.2f') + '|' + str(d)

def set_offer(p, amount, d, kind, msg):
    p['offer'] = dict(amount=round(float(amount), 2), date=str(d), kind=kind)
    p['msg'] = msg
    p['status'] = 'open'
    p['ask_only'] = False

def next_attempt(p, t):
    dead = datetime.date.fromisoformat(p['deadline'])
    while True:
        n = p['att'] + 1
        if n > p['max_att']:
            p['status'] = 'ended'
            p['reason'] = 'refused'
            p['offer'] = None
            p['msg'] = ''
            return
        p['att'] = n
        if n == 1:
            amt = p['floor'] if p['too_much'] else p['past_due']
            d = attempt1_date(t)
            if d > dead:
                d = dead
        else:
            amt = p['floor']
            d = dead
        if okey(amt, d.isoformat()) in p['refused']:
            continue
        what = 'the floor amount' if amt == p['floor'] and amt != p['past_due'] else 'the full past-due amount'
        extra = ' Say that the rest stays overdue.' if amt != p['past_due'] else ''
        set_offer(p, amt, d.isoformat(), 'attempt' + str(n), 'Persuasion attempt ' + str(n) + ': propose ' + what + ' on this date.' + extra)
        return

def refuse(p, t):
    if p.get('status') == 'agreed' and p.get('agreed'):
        p['refused'].append(okey(p['agreed']['amount'], p['agreed']['date']))
        p['agreed'] = None
    elif p.get('offer'):
        p['refused'].append(okey(p['offer']['amount'], p['offer']['date']))
    p['status'] = 'open'
    next_attempt(p, t)

def agree(p, amt, d, adjusted=False):
    p['ask_only'] = False
    p['status'] = 'agreed'
    p['agreed'] = dict(amount=round(float(amt), 2), date=str(d))
    p['adjusted'] = adjusted
    p['msg'] = ''

def too_much(p, t):
    p['too_much'] = True
    if not p['floor_offered'] and p['floor'] < p['past_due']:
        p['floor_offered'] = True
        d = p['offer']['date'] if p.get('offer') else t.isoformat()
        set_offer(p, p['floor'], d, 'floor', 'The customer said the full amount is too much: offer the floor amount, once, and say that the rest stays overdue.')
    else:
        refuse(p, t)

def vague(p, t):
    if not p['vague_asked']:
        p['vague_asked'] = True
        p['msg'] = 'The customer gave a vague period: ask once for the exact day. Do not propose a date or an amount yet.'
        p['status'] = 'open'
        p['ask_only'] = True
    else:
        amt = p['offer']['amount'] if p.get('offer') else p['past_due']
        set_offer(p, amt, p['deadline'], 'vague_deadline', 'The customer still gave no exact day: propose the latest date you can record.')

def propose(p, amount, d, t, group):
    p['ask_only'] = False
    base_amt = p['past_due']
    base_d = t
    if p.get('status') == 'agreed' and p.get('agreed'):
        base_amt = p['agreed']['amount']
        base_d = datetime.date.fromisoformat(p['agreed']['date'])
    elif p.get('offer'):
        base_amt = p['offer']['amount']
        base_d = datetime.date.fromisoformat(p['offer']['date'])
    amt = amount if (amount is not None and amount > 0 and not group) else base_amt
    dd = d if d is not None else base_d
    msgs = []
    problem = False
    if amt > p['past_due'] + 0.005:
        amt = p['past_due']
    if amt < p['floor'] - 0.005:
        if p['below_offered']:
            refuse(p, t)
            return
        p['below_offered'] = True
        amt = p['floor']
        problem = True
        msgs.append('Say that amount cannot be recorded and offer the floor amount, once.')
    dead = datetime.date.fromisoformat(p['deadline'])
    adjusted = False
    if dd < t:
        dd = t
        problem = True
        msgs.append('The date must be today or later: offer today.')
    elif dd > dead:
        if group and MULTI:
            dd = dead
            adjusted = True
        else:
            dd = dead
            problem = True
            msgs.append('Say that the latest date you can record is ' + speak(dead) + ' and offer it.')
    elif not isbiz(dd):
        dd = next_biz_from(dd)
        problem = True
        msgs.append('The day the customer named is not a business day: offer the next business day.')
    if problem:
        set_offer(p, amt, dd.isoformat(), 'counter', ' '.join(msgs))
    else:
        agree(p, amt, dd.isoformat(), adjusted)

def render(V, st):
    prods = st['products']
    title = str(V.get('title') or '') + ' ' + str(V.get('last_name') or '')
    lines = ['PRODUCTS, in the order the bank returned them:']
    for p in prods:
        s = p['status']
        if s == 'open':
            sd = 'open, persuasion attempts used ' + str(p['att']) + ' of ' + str(p['max_att'])
        elif s == 'agreed':
            sd = 'agreed, not yet confirmed: ' + money(p['agreed']['amount']) + ' on ' + speak(p['agreed']['date'])
        elif s == 'confirmed':
            sd = 'confirmed, being recorded'
        else:
            sd = 'closed without promise (' + str(p['reason']) + ')'
        lines.append('- product ' + str(p['n']) + ': ' + p['label'] + '. Past due ' + money(p['past_due']) + ', ' + str(p['days_late']) +
                     ' days late, floor amount ' + money(p['floor']) + ', latest allowed promise date ' + speak(p['deadline']) + ' (' + p['deadline'] + '). Status: ' + sd + '.')
    opn = [p for p in prods if p['status'] == 'open']
    agr = [p for p in prods if p['status'] == 'agreed']
    if st.get('hardship') and not st.get('hardship_done') and opn:
        lines.append('NEXT ACTION: say one short sentence of sympathy, make no payment offer, and ask whether the customer wants to be connected with the customer support team. If yes: event transfer with queue support. If no: event declines_support. If the customer names a date or an amount themselves: event proposes.')
        phase = 'hardship'
    elif opn and not st.get('today_done'):
        q = 'Can you pay all of them today?' if len(prods) > 1 else 'Can you make this payment today?'
        lines.append('NEXT ACTION: you asked "' + q + '". Wait for the answer and report it with update. If they say yes for everything: event accepts, product all.')
        phase = 'today'
    elif opn:
        p = opn[0]
        o = p.get('offer')
        lines.append('CURRENT PRODUCT: product ' + str(p['n']) + ', ' + p['label'] + '.')
        if o and not p.get('ask_only'):
            lines.append('NEXT ACTION (new): ' + (p['msg'] + ' ' if p['msg'] else '') + 'Offer exactly ' + money(o['amount']) + ' for the ' + p['label'] + ' on ' + speak(o['date']) +
                         ', and ask whether the customer can pay that. Offer nothing else.')
        else:
            lines.append('NEXT ACTION: ' + p['msg'])
        if len(prods) > 1:
            lines.append('Talk about this product only. Do not ask about paying today again.')
        phase = 'negotiate'
    elif agr:
        items = []
        for p in agr:
            it = p['label'] + ': ' + money(p['agreed']['amount']) + ' on ' + speak(p['agreed']['date'])
            if p.get('adjusted'):
                it += ' (this is the latest date allowed for this product, so it is recorded on that date instead of the date named)'
            items.append(it)
        lines.append('NEXT ACTION: read back, in one message, every promise below, then ask "Do you confirm?". On a clear yes: event confirms, product all.')
        for it in items:
            lines.append('  * ' + it)
        phase = 'readback'
    else:
        phase = 'done'
    st['phase'] = phase
    V['state_text'] = '\n'.join(lines)
    V['phase'] = phase

def apply(V, st, P):
    t = today_of(V)
    prods = st['products']
    ev = str(P.get('event') or '').strip()
    which = str(P.get('product') or 'all').strip().lower()
    amount = pnum(P.get('amount'))
    d = pdate(P.get('date'))
    live = [p for p in prods if p['status'] in ('open', 'agreed')]
    opn = [p for p in prods if p['status'] == 'open']
    if which in ('all', '', 'none'):
        targets = live
        group = len(prods) > 1
    else:
        try:
            k = int(re.sub(r'\D', '', which) or '0')
        except Exception:
            k = 0
        targets = [p for p in prods if p['n'] == k] or (opn[:1] if opn else live[:1])
        group = False
    if ev == 'transfer':
        q = str(P.get('queue') or 'general')
        if q not in ('restructuring', 'general', 'support'):
            q = 'general'
        V['transfer_queue'] = q
        V['ending'] = 'transfer'
        V['route'] = 'transfer'
        return
    if ev == 'refuses_to_talk':
        st['talk'] = st.get('talk', 0) + 1
        if st['talk'] >= 2:
            for p in live:
                p['status'] = 'ended'
                p['reason'] = 'refused'
            V['route'] = 'wrapup'
        return
    if ev == 'hardship':
        st['hardship'] = True
        return
    if ev == 'declines_support':
        st['hardship_done'] = True
        for p in [p for p in prods if p['status'] == 'open']:
            p['status'] = 'ended'
            p['reason'] = 'hardship'
        return
    if ev == 'confirms':
        if not opn:
            for p in prods:
                if p['status'] == 'agreed':
                    p['status'] = 'confirmed'
        return
    if not st.get('today_done') and ev in ('accepts', 'proposes', 'vague_date', 'full_too_much', 'refuses', 'paid', 'dispute'):
        st['today_done'] = True
        if not (ev == 'accepts' and which in ('all', '', 'none')):
            for p in prods:
                if p['status'] == 'open' and p.get('offer') and p['offer'].get('kind') == 'today' and p not in targets:
                    next_attempt(p, t)
    for p in targets:
        if ev == 'accepts':
            if p['status'] == 'open' and p.get('offer'):
                agree(p, p['offer']['amount'], p['offer']['date'])
        elif ev == 'proposes':
            if st.get('hardship'):
                st['hardship_done'] = True
            propose(p, amount, d, t, group)
        elif ev == 'vague_date':
            vague(p, t)
        elif ev == 'full_too_much':
            too_much(p, t)
        elif ev == 'refuses':
            refuse(p, t)
        elif ev in ('paid', 'dispute'):
            p['status'] = 'ended'
            p['reason'] = ev
            p['agreed'] = None
'''

UPDATE = r'''
def main(V, P):
    st = load(V)
    apply(V, st, P)
    render(V, st)
    prods = st['products']
    if V.get('route') not in ('transfer', 'wrapup'):
        if any(p['status'] == 'confirmed' for p in prods) and not any(p['status'] in ('open', 'agreed') for p in prods):
            V['route'] = 'wrapup'
        elif st.get('phase') == 'done':
            V['route'] = 'wrapup'
        else:
            V['route'] = 'stay'
    save(V, st)
'''

PICK = r'''
def main(V):
    V['next_step'] = 'finish'
    if str(V.get('rec_pending')) == 'yes':
        V['rec_pending'] = 'no'
        after_rec(V)
    if str(V.get('note_pending')) == 'yes':
        V['note_pending'] = 'no'
        after_note(V)
    st = load(V)
    prods = st.get('products') or []
    V['rec_ok'] = 'pending'
    V['note_ok'] = 'pending'
    for i, p in enumerate(prods):
        if p['status'] == 'confirmed' and p['rec'] not in ('ok', 'failed'):
            V['rec_idx'] = i
            V['rec_pid'] = p['id']
            V['rec_amount'] = p['agreed']['amount']
            V['rec_date'] = p['agreed']['date']
            V['next_step'] = 'record'
            V['rec_pending'] = 'yes'
            return
    if NOTES:
        for i, p in enumerate(prods):
            if p['rec'] != 'ok' and not p['note_done']:
                if p['rec'] == 'failed':
                    r = 'service_error'
                elif p['status'] == 'ended' and p['reason']:
                    r = p['reason']
                else:
                    r = 'refused'
                p['reason'] = r
                save(V, st)
                V['note_idx'] = i
                V['note_pid'] = p['id']
                V['note_reason'] = r
                V['next_step'] = 'note'
                V['note_pending'] = 'yes'
                return
    V['next_step'] = 'finish'
    final(V)
'''

AFTER_REC = r'''
def after_rec(V):
    st = load(V)
    i = int(float(V.get('rec_idx') or 0))
    p = st['products'][i]
    if is_true(V.get('rec_ok')):
        p['rec'] = 'ok'
    else:
        p['rec_fail'] = p.get('rec_fail', 0) + 1
        if p['rec_fail'] >= 2:
            p['rec'] = 'failed'
            p['reason'] = 'service_error'
    save(V, st)
'''

AFTER_NOTE = r'''
def after_note(V):
    st = load(V)
    i = int(float(V.get('note_idx') or 0))
    p = st['products'][i]
    if is_true(V.get('note_ok')):
        p['note_done'] = True
    else:
        p['note_fail'] = p.get('note_fail', 0) + 1
        if p['note_fail'] >= 2:
            p['note_done'] = True
    save(V, st)
'''

FINAL = r'''
def final(V):
    st = load(V)
    prods = st.get('products') or []
    end = str(V.get('ending') or '')
    name = (str(V.get('title') or '') + ' ' + str(V.get('last_name') or '')).strip()
    bye = 'Thank you for your time, ' + name + '. Goodbye.'
    o, r, line = 'no_promise', 'refused', bye
    stage = str(V.get('stage') or '')
    if end == 'transfer':
        q = str(V.get('transfer_queue') or 'general')
        if is_true(V.get('xfer_ok')):
            o, r = 'transferred', dict(restructuring='restructuring', general='human', support='support').get(q, 'human')
            line = 'I am connecting you now. Thank you for your time. Goodbye.'
        else:
            o, r = 'no_promise', 'service_error'
            line = 'I am sorry, I could not transfer the call. Please call Freya Bank customer service. Goodbye.'
    elif end == 'callback':
        if is_true(V.get('cb_ok')):
            o, r = 'not_reached', 'callback'
            line = 'Thank you, we will call back on ' + str(V.get('cb_spoken') or '') + '. Goodbye.'
        else:
            o, r = 'not_reached', 'no_callback'
            line = 'I am sorry, I could not book the callback. Thank you for your time. Goodbye.'
    elif end in ('no_callback', 'wrong_number', 'unclear'):
        o, r = 'not_reached', end
        line = 'I apologise for the inconvenience. Goodbye.' if end == 'wrong_number' else 'Thank you for your time. Goodbye.'
    elif end == 'deceased':
        o, r = 'not_reached', 'deceased'
        line = 'I am sorry for your loss. Goodbye.'
    elif end == 'failed':
        o, r = 'not_verified', 'failed'
        line = 'I am sorry, I could not verify your identity, so I cannot discuss the account. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye.'
    elif end == 'declined' or (not prods and stage in ('opening', 'identity')):
        if stage == 'opening' and end != 'declined':
            o, r = 'not_reached', 'unclear'
        else:
            o, r = 'not_verified', 'declined'
        line = 'I understand. Thank you for your time. Goodbye.'
    elif end == 'account_error':
        o, r = 'no_promise', 'service_error'
        line = 'I am sorry, I cannot reach the account details right now. Please use the Freya Bank mobile app or visit a branch. Thank you for your time. Goodbye.'
    else:
        rec = [p for p in prods if p.get('rec') == 'ok']
        failed = [p for p in prods if p.get('rec') == 'failed']
        parts = []
        for p in rec:
            parts.append('Your promise to pay ' + money(p['agreed']['amount']) + ' for the ' + p['label'] + ' on ' + speak(p['agreed']['date']) + ' is recorded.')
        for p in failed:
            parts.append('I am sorry, I could not record the promise for the ' + p['label'] + '.')
        if rec:
            o, r = 'promise', ''
            parts.append('You will receive a text message confirming this promise.')
        else:
            reasons = []
            for p in prods:
                if p.get('rec') == 'failed':
                    reasons.append('service_error')
                elif p['status'] == 'ended' and p.get('reason'):
                    reasons.append(p['reason'])
                else:
                    reasons.append('refused')
            if reasons and all(x == 'paid' for x in reasons):
                o, r = 'paid', ''
            else:
                o = 'no_promise'
                r = [x for x in reasons if x != 'paid'][0] if reasons else 'refused'
            if 'paid' in reasons:
                parts.append('Payments can take one business day to appear.')
        parts.append(bye)
        line = ' '.join(parts)
    V['final_outcome'] = o
    V['final_reason'] = r
    V['closing_line'] = line
    V['close_kind'] = 'plain' if o in ('promise', 'paid') else 'reason'

def main(V):
    final(V)
'''


def code(body, multi, notes, call):
    src = LIB.replace("__HOLIDAYS__", json.dumps(HOLIDAYS)).replace("__BANDS__", json.dumps(BANDS))
    src = src.replace("__MULTI__", "True" if multi else "False").replace("__NOTES__", "True" if notes else "False")
    src += body
    # exec() may run with separate globals and locals: publish the definitions so functions can see each other.
    src += "\ntry:\n    globals().update(locals())\nexcept Exception:\n    pass\n"
    src += "try:\n    " + call + "\nexcept Exception as _e:\n    vars['code_error'] = str(_e)[:300]\n"
    assert "{{" not in src and "}}" not in src, "code must not contain double braces"
    return src


def code_step(name, src, target, on_enter=None):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": target,
        "on_enter": on_enter or {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "config": {"timeoutMs": 15000, "maxRetries": 2}, "function": {"name": "code_exec", "handler": "__function__:code_exec",
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": src}, "timeout_ms": {"type": "number", "default": 15000}}}}}],
        "transitions": [{"target_node": target, "description": "always", "condition": {"operator": "always"}}],
    }


def eq(var, val):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": val}]}


def is_true_cond(var):
    return {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": "true"},
                                          {"variable": var, "operator": "equals", "operand": "True"}]}


def api_tool(op, fields, required, desc="", pre=None, post=None, retries=0):
    props = {"url": {"type": "string", "default": f"{BASE}/{op}"}, "method": {"type": "string", "default": "POST"},
             "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
             "body": {"type": "object", "properties": {"customer_id": {"type": "string", "default": "{{customer_id}}"}, **fields},
                      "required": required}}
    t = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": retries},
         "function": {"name": op, "handler": "__function__:api_call", "description": desc,
                      "parameters": {"type": "object", "properties": props}}}
    if pre:
        t["pre_process_code"] = pre
    if post:
        t["post_process_code"] = post
    return t


def api_step(name, tool, mapping, target):
    return {
        "name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": target,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "pre_actions": [tool],
        "response_mapping": mapping,
        "transitions": [{"target_node": target, "description": "always", "condition": {"operator": "always"}}],
    }


def code_tool(name, desc, src, props, required):
    return {"type": "function", "config": {"timeoutMs": 15000, "maxRetries": 2},
            "function": {"name": name, "handler": "__function__:code_exec", "description": desc,
                         "parameters": {"type": "object", "properties": {
                             "code": {"type": "string", "default": src},
                             "timeout_ms": {"type": "number", "default": 15000}, **props}, "required": required}}}


VERIFY_POST = r'''try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            left = d.get('wrong_answers_left')
            if d.get('all_verified') in (True, 'true', 'True'):
                w = 'Both answers are verified. Do not ask anything else about identity.'
            elif d.get('hint') == 'day_month_swapped':
                w = 'The day and the month look swapped. Ask the customer to say the month of birth as a word. This retry is not a wrong answer.'
            elif d.get('ok') in (False, 'false', 'False') and d.get('verified') is None:
                w = 'The answer could not be read. Ask the customer to repeat it. This is not a wrong answer.'
            elif d.get('verified') in (True, 'true', 'True'):
                w = 'Correct. Now ask for the last four digits of the phone number on file.'
            elif left is not None and str(left) in ('0', '0.0'):
                w = 'No tries are left. Say nothing more about identity.'
            else:
                w = 'Wrong answer. Say it does not match our records and ask the same question again.'
            d['what_to_do_next'] = w
    elif result is None:
        pass
except Exception:
    pass
'''

REC_PRE = r'''try:
    b = config.get('body')
    if isinstance(b, dict):
        b['product_id'] = str(vars.get('rec_pid'))
        b['amount'] = round(float(vars.get('rec_amount')), 2)
        b['date'] = str(vars.get('rec_date'))[:10]
except Exception:
    pass
'''

NOTE_PRE = r'''try:
    b = config.get('body')
    if isinstance(b, dict):
        b['product_id'] = str(vars.get('note_pid'))
        b['reason'] = str(vars.get('note_reason'))
except Exception:
    pass
'''

CLOSE_PRE = r'''try:
    b = config.get('body')
    if isinstance(b, dict):
        o = str(b.get('outcome') or '')
        if o in ('promise', 'paid') or not str(b.get('reason') or '').strip() or '{' in str(b.get('reason')):
            b.pop('reason', None)
except Exception:
    pass
'''

SYSTEM = """You are Freya Bank's digital assistant on an outbound phone call. Speak English. Keep every turn to one or two short sentences. Address the customer as {{title}} {{last_name}}.
Rules for the whole call:
- If asked whether you are a robot or an AI: say you are Freya Bank's digital assistant, then continue.
- If asked whether this call is a scam: say they can verify the call by phoning Freya Bank's customer service number, then continue.
- If asked something you cannot answer from the information in this prompt: say you do not have that information. Never invent figures, dates or reasons.
- Never offer a discount, a waiver, an instalment plan, a payment plan or any other term.
- Never ask the customer how much they can pay. You propose every amount.
- Never say goodbye and never end the call yourself. When the call must end, call the tool named in the task. The closing sentence is said for you.
- Call at most one tool per message. After a tool result, read the task again and say the next thing to the customer. If a tool returns an error, call it again once with the same arguments.
- Never say that something is recorded, booked or transferred. The system says that after it is done."""


def build(multi):
    notes = multi
    C = lambda body, call: code(body, multi, notes, call)
    nprod = 3 if multi else 1
    product_enum = [str(i) for i in range(1, nprod + 1)] + ["all"]

    contact_tool = code_tool(
        "contact_update",
        "CALL it every time the person on the line answers, with what they said. It decides the next action.",
        C(CONTACT, "main(vars, params)"),
        {"result": {"type": "string", "enum": ["confirmed", "not_confirmed", "callback_time", "no_callback", "wrong_number",
                                                "deceased", "refuses_to_talk", "transfer_human"],
                    "description": "confirmed | not_confirmed | callback_time | no_callback | wrong_number | deceased | refuses_to_talk | transfer_human"},
         "date": {"type": "string", "description": "callback_time only: the day as YYYY-MM-DD, from the calendar"},
         "time": {"type": "string", "description": "callback_time only: the time as HH:MM, 24 hour"}},
        ["result"])

    id_tool = code_tool(
        "id_update",
        "CALL it when the customer declines a security question, asks what the call is about instead of answering, says they do not want to talk, or insists on a human.",
        C(IDEV, "main(vars, params)"),
        {"event": {"type": "string", "enum": ["declines", "transfer_human"], "description": "declines | transfer_human"}},
        ["event"])

    verify_tool = api_tool(
        "verify_identity",
        {"field": {"type": "string", "enum": ["date_of_birth", "phone_last4"], "default": "{{field}}",
                   "description": "Which question was answered: date_of_birth or phone_last4."},
         "answer": {"type": "string", "default": "{{answer}}",
                    "description": "date_of_birth as YYYY-MM-DD (numbers only: day, then month, then year). phone_last4 as four digits."}},
        ["field", "answer"],
        "Check one security answer. CALL it every time the customer answers a security question, once per answer.")

    update_tool = code_tool(
        "update",
        "CALL it after every customer answer about paying, with the product and the event. It keeps the attempts and decides the next action.",
        C(ENGINE + UPDATE, "main(vars, params)"),
        {"product": {"type": "string", "enum": product_enum,
                     "description": "The product number from STATE (" + ", ".join(product_enum[:-1]) + "), or all when the answer is about every product."},
         "event": {"type": "string", "enum": ["accepts", "proposes", "vague_date", "full_too_much", "refuses", "hardship", "declines_support",
                                              "paid", "dispute", "confirms", "refuses_to_talk", "transfer"],
                   "description": "What the customer said. See the task."},
         "date": {"type": "string", "description": "proposes only: the date the customer named, YYYY-MM-DD from the calendar"},
         "amount": {"type": "number", "description": "proposes only: the amount the customer named"},
         "queue": {"type": "string", "enum": ["restructuring", "general", "support"], "description": "transfer only: restructuring, general or support"}},
        ["product", "event"])

    nodes = {}
    nodes["setup"] = code_step("setup", C(SETUP, "main(vars)"), "opening")

    nodes["opening"] = {
        "name": "opening", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with {{title}} {{last_name}}?"},
        "on_enter_first_entry_only": True,
        "task_message": """You said you are a digital assistant calling from Freya Bank, that the call is recorded, and asked whether you are speaking with {{title}} {{last_name}}.
Do not say why you are calling. Never mention collections, a debt, a payment, an amount, an account or a product, to anyone, even if a relative asks or offers to pay. If asked why you call, say you can only discuss it with {{title}} {{last_name}} in person.

Report every answer with contact_update:
- confirmed: only a clear "yes", "that's me", "speaking", or the customer's own name ({{first_name}} {{last_name}}).
- not_confirmed: anything else that does not confirm, such as "hello", "go ahead", "who is this", or a question.
TURN ORDER: call contact_update ALONE, with no text in that message. After the result, reply in one message: answer their question if they asked one, then do what the NEXT ACTION below says (or, for someone else on the line, ask when the customer can be reached). Never end a turn silent.
- Someone else answered (a relative, a colleague): do not call the tool yet. Ask when {{title}} {{last_name}} can be reached. When they name a day and a time: callback_time with date and time. Convert "tomorrow morning around eleven" to tomorrow's date and 11:00.
- no_callback: they will not give any time.
- wrong_number: the number does not belong to the customer.
- deceased: the customer has died. Say nothing yourself; the system says the right sentence.
- refuses_to_talk: they do not want to talk.
- transfer_human: they insist on a human after you asked once whether you can help.
Never call contact_update twice for the same answer.

{{contact_text}}

{{date_facts}}
Next business day: {{next_biz_spoken}} ({{next_biz_iso}}).""",
        "tools": [contact_tool],
        "max_node_turns": 10, "max_turn_transition": "finalize",
        "transitions": [
            {"target_node": "identity", "description": "confirmed", "condition": eq("route", "identity")},
            {"target_node": "callback_api", "description": "callback", "condition": eq("route", "callback")},
            {"target_node": "transfer_api", "description": "transfer", "condition": eq("route", "transfer")},
            {"target_node": "finalize", "description": "end", "condition": eq("route", "end")},
        ],
    }

    nodes["identity"] = {
        "name": "identity", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "Thank you. Before we continue, I need to ask two security questions. What is your date of birth?"},
        "on_enter_first_entry_only": True,
        "task_message": """The person said they are {{title}} {{last_name}}. Check identity now. Still do not say why you are calling and do not mention collections, a debt, a payment or a product.
Ask two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file.
After every answer call verify_identity with field and answer. Date of birth: send YYYY-MM-DD, whatever way it was said. A date given only as numbers is day, then month, then year (03/04/1985 is 1985-04-03). Phone: the four digits.
Read each result and then speak:
- all_verified true: say nothing more about identity.
- hint day_month_swapped: ask the customer to say the month of birth as a word. This retry is not a wrong answer.
- ok false without verified: the answer could not be read; ask them to repeat it.
- verified true for the date of birth: ask for the last four digits of the phone number on file.
- verified false: say it does not match our records and ask the same question again. Never say how many tries are left.
If a tool returns an error, call it again once with the same arguments.
If the customer will not answer, or asks what the call is about instead of answering, or says they do not want to talk: call id_update with event declines.
If they ask for a human: ask once whether you can help. If they insist: id_update with event transfer_human.
Call every tool ALONE, with no text in that message. After the result, always speak: answer any question they asked, then ask the next question. Never end a turn silent.

{{id_text}}""",
        "tools": [verify_tool, id_tool],
        "max_node_turns": 14, "max_turn_transition": "finalize",
        "transitions": [
            {"target_node": "load_account", "description": "both answers verified", "condition": is_true_cond("verify_identity_response.data.all_verified")},
            {"target_node": "id_failed", "description": "no tries left", "condition": {"logic": "or", "conditions": [
                {"logic": "and", "conditions": [
                    {"variable": "verify_identity_response.data.wrong_answers_left", "operator": "is_set"},
                    {"variable": "verify_identity_response.data.wrong_answers_left", "operator": "less_than", "operand": 1}]}]}},
            {"target_node": "transfer_api", "description": "transfer", "condition": eq("route", "transfer")},
            {"target_node": "finalize", "description": "end", "condition": eq("route", "end")},
        ],
    }

    nodes["id_failed"] = code_step("id_failed", C("\ndef main(V):\n    V['ending'] = 'failed'\n", "main(vars)"), "finalize")

    nodes["load_account"] = api_step("load_account", api_tool("get_account", {}, [], "The late products.", retries=2),
                                     [{"path": "data.products", "variable": "products"}, {"path": "data.ok", "variable": "acct_ok"}],
                                     "prepare")
    nodes["prepare"] = code_step("prepare", C(ENGINE + PREPARE, "main(vars)"), "negotiate")
    nodes["prepare"]["transitions"] = [
        {"target_node": "finalize", "description": "no account", "condition": eq("route", "end")},
        {"target_node": "negotiate", "description": "always", "condition": {"operator": "always"}}]

    events = """Events for update (one call per message, wait for the result before the next call):
- accepts: the customer agrees to the offer you just made (the one in NEXT ACTION).
- proposes: the customer names their own date and/or amount. Fill date (YYYY-MM-DD) and/or amount. A date or an amount the customer names is never a refusal.
- vague_date: a vague period without an exact day ("next week", "end of the month", "when my salary comes").
- full_too_much: the full amount is too much, with no amount named.
- refuses: a flat no, a non-answer, or a no to the offer with no date and no amount of their own.
- hardship: the customer mentions illness, a death in the family or job loss.
- declines_support: after hardship, they do not want to be connected with the support team.
- paid: they say they already paid this past-due amount.
- dispute: "this debt is not mine", "I never had this product", or the product was closed or paid off in the past.
- confirms: a clear yes to the read-back.
- refuses_to_talk: they say they do not want to talk.
- transfer: queue restructuring when they ask for a new payment plan or lower instalments (do not describe any plan); queue general when they insist on a human after you asked once whether you can help; queue support when they accept the support team after hardship.
When the customer talks about several products in one answer, report the first one, wait for the result, then report the next."""

    if multi:
        events += "\nWhen the customer names one date for every product, use product all with that date."

    nodes["negotiate"] = {
        "name": "negotiate", "node_type": "conversation",
        "on_enter": {"type": "tts", "text": "{{debt_text}}"},
        "on_enter_first_entry_only": True,
        "task_message": """The customer is verified. You already stated the late payment and asked the first question.

Use the update tool after every customer answer about paying. The system keeps the offers and the attempts. Do only the NEXT ACTION below. Offer only the amount and the date it names. Never make another offer, never repeat an offer the customer refused, never ask how much they can pay.
If the customer changes the date or the amount at the read-back, report it with proposes.
TURN ORDER: when the customer answers, first call update ALONE, with no text in that message. When the result comes back, reply in one message: answer any question they asked (robot, scam, information), then do the new NEXT ACTION. Never end a turn silent. Do not say goodbye.
The NEXT ACTION always reflects the latest update. Any offer you made before it is no longer valid; do not repeat it.

""" + events + """

STATE:
{{state_text}}

{{date_facts}}""",
        "tools": [update_tool],
        "max_node_turns": 40, "max_turn_transition": "pick_next",
        "transitions": [
            {"target_node": "transfer_api", "description": "transfer", "condition": eq("route", "transfer")},
            {"target_node": "pick_next", "description": "wrap up", "condition": eq("route", "wrapup")},
        ],
    }

    nodes["pick_next"] = code_step("pick_next", C(AFTER_REC + AFTER_NOTE + FINAL + PICK, "main(vars)"), "close_reason")
    guard = {"logic": "or", "conditions": [
        {"variable": "record_promise_success_count", "operator": "greater_than", "operand": 6},
        {"variable": "record_promise_failure_count", "operator": "greater_than", "operand": 6},
        {"variable": "add_note_api_success_count", "operator": "greater_than", "operand": 6},
        {"variable": "add_note_api_failure_count", "operator": "greater_than", "operand": 6}]}
    nodes["pick_next"]["transitions"] = [
        {"target_node": "close_reason", "description": "loop guard", "condition": guard},
        {"target_node": "record_promise", "description": "record", "condition": eq("next_step", "record")},
        {"target_node": "add_note_api", "description": "note", "condition": eq("next_step", "note")},
        {"target_node": "close_plain", "description": "no reason", "condition": eq("close_kind", "plain")},
        {"target_node": "close_reason", "description": "always", "condition": {"operator": "always"}}]

    rec_tool = api_tool("create_promise",
                        {"product_id": {"type": "string", "default": "{{rec_pid}}"},
                         "amount": {"type": "number", "default": "{{rec_amount}}"},
                         "date": {"type": "string", "default": "{{rec_date}}"}},
                        ["product_id", "amount", "date"], "Record one confirmed promise.")
    nodes["record_promise"] = api_step("record_promise", rec_tool, [{"path": "data.ok", "variable": "rec_ok"}, {"path": "data.ok", "variable": "next_step"}], "pick_next")

    if notes:
        note_tool = api_tool("add_note",
                             {"product_id": {"type": "string", "default": "{{note_pid}}"},
                              "reason": {"type": "string", "enum": ["refused", "hardship", "dispute", "paid", "service_error"], "default": "{{note_reason}}"}},
                             ["product_id", "reason"], "Note why a product ended without a promise.")
        nodes["add_note_api"] = api_step("add_note_api", note_tool, [{"path": "data.ok", "variable": "note_ok"}, {"path": "data.ok", "variable": "next_step"}], "pick_next")
    else:
        nodes["pick_next"]["transitions"] = [t for t in nodes["pick_next"]["transitions"] if t["target_node"] != "add_note_api"]

    nodes["callback_api"] = api_step("callback_api", api_tool("schedule_callback",
                                     {"date": {"type": "string", "default": "{{cb_date}}"}, "time": {"type": "string", "default": "{{cb_time}}"}},
                                     ["date", "time"], "Book the callback."), [{"path": "data.ok", "variable": "cb_ok"}], "finalize")
    nodes["transfer_api"] = api_step("transfer_api", api_tool("transfer_to_agent",
                                     {"queue": {"type": "string", "enum": ["restructuring", "general", "support"], "default": "{{transfer_queue}}"}},
                                     ["queue"], "Hand the call to a person."), [{"path": "data.ok", "variable": "xfer_ok"}], "finalize")

    nodes["finalize"] = code_step("finalize", C(FINAL, "main(vars)"), "close_reason")
    nodes["finalize"]["transitions"] = [
        {"target_node": "close_plain", "description": "no reason", "condition": eq("close_kind", "plain")},
        {"target_node": "close_reason", "description": "always", "condition": {"operator": "always"}}]
    outcome_field = {"type": "string", "enum": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"],
                     "default": "{{final_outcome}}"}
    for key, fields in (("close_reason", {"outcome": outcome_field, "reason": {"type": "string", "default": "{{final_reason}}"}}),
                        ("close_plain", {"outcome": outcome_field})):
        nodes[key] = api_step(key, api_tool("close_call", fields, ["outcome"], "End the call record."), [], "end")
        nodes[key]["on_enter"] = {"type": "tts", "text": "{{closing_line}}"}
    nodes["end"] = {
        "name": "end", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
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



if __name__ == "__main__":
    for slot, multi in (("brief-a", False), ("brief-b", True)):
        (OUT / f"{slot}.workflow.json").write_text(json.dumps(build(multi), indent=1))
        print("wrote", slot)
