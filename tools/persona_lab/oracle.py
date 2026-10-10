"""A parameterized reference reading of the public date and amount rules.

This is our own reading of Brief A sections 7 and 8, made a function of its parameters. It derives the values a
policy mutation should produce (deadlines under a new calendar, the floor under a new per-product rule). It is not
the bank's scorer and it scores no agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

WEEKEND = (5, 6)


@dataclass(frozen=True)
class Band:
    name: str
    min_days: int
    max_days: int
    deadline_business_days: int
    attempts: int


@dataclass(frozen=True)
class Policy:
    holidays: tuple[date, ...]
    bands: tuple[Band, ...]
    floors: dict = field(default_factory=dict)            # product type -> field name, or "half_past_due"
    identity_fields: tuple[str, ...] = ("date_of_birth", "phone_last4")
    wrong_answer_limit: int = 3
    callback_window: tuple[str, str] = ("10:00", "19:00")
    max_promise_amount: float | None = None
    deadline_cap_by_type: dict = field(default_factory=dict)   # product type -> max business days, any band

    def with_(self, **kw) -> "Policy":
        return replace(self, **kw)


def d(s: str) -> date:
    return date.fromisoformat(s)


BRIEF_A = Policy(
    holidays=tuple(map(d, ("2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"))),
    bands=(Band("early", 1, 7, 12, 1), Band("late", 8, 45, 7, 2)),
    floors={"credit_card": "minimum_payment", "personal_loan": "instalment_amount", "car_loan": "instalment_amount"},
)


def is_business_day(p: Policy, day: date) -> bool:
    return day.weekday() not in WEEKEND and day not in p.holidays


def next_business_day(p: Policy, day: date) -> date:
    """The first business day strictly after `day`."""
    day += timedelta(days=1)
    while not is_business_day(p, day):
        day += timedelta(days=1)
    return day


def nth_business_day_after(p: Policy, today: date, n: int) -> date:
    day = today
    for _ in range(n):
        day = next_business_day(p, day)
    return day


def band(p: Policy, days_late: int) -> Band:
    for b in p.bands:
        if b.min_days <= days_late <= b.max_days:
            return b
    raise ValueError(f"no band for {days_late} days late")


def deadline(p: Policy, today: date, days_late: int, product_type: str | None = None) -> date:
    n = band(p, days_late).deadline_business_days
    cap = p.deadline_cap_by_type.get(product_type)
    return nth_business_day_after(p, today, min(n, cap) if cap else n)


def promise_date_ok(p: Policy, today: date, days_late: int, day: date, product_type: str | None = None) -> bool:
    return today <= day <= deadline(p, today, days_late, product_type) and is_business_day(p, day)


def date_to_offer(p: Policy, today: date, days_late: int, asked: date, product_type: str | None = None) -> date:
    """Brief A rules 20 and 23: a non-business day inside the deadline moves to the next business day; a day after
    the deadline is answered with the deadline."""
    last = deadline(p, today, days_late, product_type)
    if asked > last:
        return last
    if not is_business_day(p, asked):
        nxt = next_business_day(p, asked)
        return nxt if nxt <= last else last
    return asked


def floor(p: Policy, product: dict) -> float:
    rule = p.floors[product["type"]]
    if rule == "half_past_due":
        return float(int(product["past_due"] / 2))      # "half of past_due, rounded down to whole euros"
    return float(product[rule])


def callback_ok(p: Policy, now: datetime, day: date, hhmm: str) -> bool:
    start, end = p.callback_window
    if not (start <= hhmm <= end):
        return False
    if day == now.date():
        return hhmm > now.strftime("%H:%M")
    return day == next_business_day(p, now.date())


def deadlines_at(p: Policy, now: str) -> dict:
    """The deadline of every band at `now`: the facts a mutated brief should change and nothing else."""
    today = datetime.fromisoformat(now).date()
    return {b.name: nth_business_day_after(p, today, b.deadline_business_days).isoformat() for b in p.bands}
