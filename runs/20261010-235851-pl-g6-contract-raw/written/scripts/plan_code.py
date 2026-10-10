import json
import re
import datetime

HOLIDAYS = ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01']
DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MAX_ITEMS = 2


def is_business(d):
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def next_business(d):
    x = d + datetime.timedelta(days=1)
    while not is_business(x):
        x = x + datetime.timedelta(days=1)
    return x


def nth_business_after(d, n):
    x = d
    for _ in range(n):
        x = next_business(x)
    return x


def last_business_of_week(monday):
    for k in range(4, -1, -1):
        x = monday + datetime.timedelta(days=k)
        if is_business(x):
            return x
    return None


def say_date(d):
    return DAY_NAMES[d.weekday()] + ' ' + d.isoformat()


def money(v):
    try:
        return '%.2f euros' % float(v)
    except Exception:
        return str(v) + ' euros'


def read_products():
    p = vars.get('products')
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except Exception:
            try:
                import ast
                p = ast.literal_eval(p)
            except Exception:
                p = None
    if isinstance(p, dict):
        p = p.get('products')
    if isinstance(p, list):
        found = [x for x in p if isinstance(x, dict)]
        if found:
            return found
    items = dict()
    for k, v in list(vars.items()):
        m = re.match(r'^.*products\.(\d+)\.(\w+)$', str(k))
        if m:
            items.setdefault(int(m.group(1)), dict())[m.group(2)] = v
    return [items[i] for i in sorted(items)]


try:
    raw_now = str(vars.get('now') or '')
    try:
        now = datetime.datetime.fromisoformat(raw_now[:16])
    except Exception:
        now = datetime.datetime.utcnow()
    today = now.date()
    monday = today - datetime.timedelta(days=today.weekday())
    next_monday = monday + datetime.timedelta(days=7)
    this_last = last_business_of_week(monday)
    if this_last is None or this_last <= today:
        attempt1_day = last_business_of_week(next_monday)
    else:
        attempt1_day = this_last
    deadline_early = nth_business_after(today, 12)
    deadline_late = nth_business_after(today, 7)

    def calendar(deadline):
        lines = []
        last = deadline + datetime.timedelta(days=10)
        x = today
        while x <= last:
            if x < next_monday:
                week = 'this week'
            elif x < next_monday + datetime.timedelta(days=7):
                week = 'next week'
            else:
                week = 'later'
            tag = say_date(x) + ' (' + week + ('' if x != today else ', today') + '): '
            if x > deadline:
                tag += 'after the deadline, cannot be recorded; offer the deadline ' + say_date(deadline)
            elif not is_business(x):
                why = 'bank holiday' if x.weekday() < 5 else 'weekend'
                nb = next_business(x)
                if nb > deadline:
                    tag += why + ', not allowed; the next business day is after the deadline, so offer the deadline ' + say_date(deadline)
                else:
                    tag += why + ', not allowed; offer the next business day ' + say_date(nb)
            else:
                tag += 'allowed'
            lines.append('- ' + tag)
            x = x + datetime.timedelta(days=1)
        return '\n'.join(lines)

    now_hm = now.strftime('%H:%M')
    nbd = next_business(today)
    if now.hour < 19:
        today_slot = 'today ' + say_date(today) + ' at a time later than ' + now_hm + ' and not later than 19:00 (and not earlier than 10:00)'
    else:
        today_slot = 'today is no longer possible (it is after 19:00)'
    vars['callback_facts'] = (
        'Now: ' + say_date(today) + ' ' + now_hm + '.\n'
        'A callback can be booked only for: ' + today_slot + ', or ' + say_date(nbd) +
        ' (the next business day) from 10:00 to 19:00, both included. No other day and no other time.\n'
        'Send date as YYYY-MM-DD and slot_time as HH:MM (24 hour).')

    products = read_products()
    vars['product_count'] = min(len(products), MAX_ITEMS)
    for n in range(1, MAX_ITEMS + 1):
        si = str(n)
        if n > len(products):
            vars['product_id_' + si] = ''
            vars['offers_' + si] = 0
            vars['facts_' + si] = 'No product.'
            for a in range(1, 4):
                vars['offer_' + si + '_' + str(a)] = 'No product.'
            continue
        p = products[n - 1]
        kind = str(p.get('type') or '')
        if kind == 'credit_card':
            name = 'credit card ending ' + str(p.get('card_last4') or '')
            floor = p.get('minimum_payment')
            floor_name = 'minimum payment'
        elif kind == 'car_loan':
            name = 'car loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment amount'
        else:
            name = 'personal loan'
            floor = p.get('instalment_amount')
            floor_name = 'instalment amount'
        try:
            days = int(float(p.get('days_late')))
        except Exception:
            days = 0
        late = days >= 8
        deadline = deadline_late if late else deadline_early
        band = 'late (8 to 45 days)' if late else 'early (1 to 7 days)'
        attempts = 2 if late else 1
        vars['product_id_' + si] = str(p.get('product_id') or '')
        vars['offers_' + si] = 1 + attempts
        past_due = money(p.get('past_due'))
        floor_s = money(floor)
        vars['facts_' + si] = (
            'Product: ' + name + ' (product_id ' + str(p.get('product_id') or '') + ').\n'
            'Past-due amount (the full amount): ' + past_due + '. Days late: ' + str(days) + '.\n'
            'Floor (' + floor_name + '): ' + floor_s + '. The lowest amount you may record.\n'
            'Band: ' + band + '. Persuasion attempts allowed: ' + str(attempts) + '.\n'
            'Today: ' + say_date(today) + '. Deadline (latest promise date): ' + say_date(deadline) + '.\n'
            'Attempt 1 day (last business day of this week, or of next week if today is that day): ' + say_date(attempt1_day) + '.\n'
            'Calendar from today. Only days marked allowed can be recorded:\n' + calendar(deadline))
        intro = ''
        if n > 1:
            intro = 'The previous product is finished. If a promise was just recorded, first say: "Your promise is recorded. You will receive a text message confirming this promise." Then '
        vars['offer_' + si + '_1'] = (
            intro + 'Say you are calling from the collections team about a late payment on the customer\'s ' + name +
            '. State the past-due amount of ' + past_due + ' and that it is ' + str(days) + ' days late. Then ask exactly: "Can you make this payment today?"')
        vars['offer_' + si + '_2'] = (
            'Persuasion attempt 1. Propose paying the full past-due amount of ' + past_due + ' on ' + say_date(attempt1_day) +
            '. If the customer already said the full amount is too much, propose the floor of ' + floor_s + ' on ' + say_date(attempt1_day) +
            ' instead and say that the rest stays overdue. Ask if they can do that.')
        vars['offer_' + si + '_3'] = (
            'Persuasion attempt 2, the last one. Propose the floor of ' + floor_s + ' on the deadline ' + say_date(deadline) +
            '. Say that the rest stays overdue. Ask if they can do that.')
    vars['plan_state'] = 'ready' if products else 'no_products'
except Exception as e:
    vars['plan_state'] = 'error'
    vars['product_count'] = 0
    vars['callback_facts'] = 'Ask when the customer can be reached between 10:00 and 19:00 today or on the next business day.'
