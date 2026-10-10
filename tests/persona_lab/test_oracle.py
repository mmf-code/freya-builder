"""The reference oracle reproduces the public expectations and changes only what a mutation changes."""
import unittest
from datetime import date, datetime

from tools.persona_lab import blind, oracle
from tools.persona_lab.common import load_cases

TODAY = date(2026, 10, 14)
A = oracle.BRIEF_A


class PublicExpectationsTest(unittest.TestCase):
    def test_band_deadlines(self):
        self.assertEqual(oracle.deadlines_at(A, "2026-10-14T11:00"), {"early": "2026-11-02", "late": "2026-10-23"})

    def test_public_promise_dates_are_reproduced(self):
        cases = load_cases()
        self.assertEqual(oracle.date_to_offer(A, TODAY, 14, date(2026, 11, 6)), date(2026, 10, 23))   # PUB-04
        self.assertEqual(oracle.date_to_offer(A, TODAY, 5, date(2026, 10, 26)), date(2026, 10, 27))   # PUB-07 holiday
        p13 = cases["PUB-13"]["products"]
        self.assertEqual(oracle.date_to_offer(A, TODAY, p13[0]["days_late"], date(2026, 10, 30)), date(2026, 10, 30))
        self.assertEqual(oracle.date_to_offer(A, TODAY, p13[1]["days_late"], date(2026, 10, 30)), date(2026, 10, 23))
        self.assertEqual(oracle.floor(A, cases["PUB-06"]["products"][0]), 637.5)

    def test_callback_window(self):
        now = datetime(2026, 10, 14, 11, 0)
        self.assertTrue(oracle.callback_ok(A, now, date(2026, 10, 15), "11:00"))                       # PUB-02
        self.assertFalse(oracle.callback_ok(A, now, date(2026, 10, 15), "19:30"))
        self.assertFalse(oracle.callback_ok(A, now, date(2026, 10, 14), "10:30"))                      # before now


class MetamorphicTest(unittest.TestCase):
    def test_calendar_change_moves_dates_only(self):
        p = blind.policy_for(next(s for s in blind.SCENARIOS if s["id"] == "g1-calendar"))
        self.assertEqual(oracle.deadlines_at(p, "2026-10-14T11:00"), {"early": "2026-10-29", "late": "2026-10-22"})
        self.assertTrue(oracle.is_business_day(p, date(2026, 10, 26)))
        self.assertEqual((p.identity_fields, p.wrong_answer_limit, p.floors, p.callback_window),
                         (A.identity_fields, A.wrong_answer_limit, A.floors, A.callback_window))

    def test_memo_override_changes_late_band_only(self):
        p = blind.policy_for(next(s for s in blind.SCENARIOS if s["id"] == "g5-memo"))
        self.assertEqual(oracle.deadline(p, TODAY, 3), oracle.deadline(A, TODAY, 3))
        self.assertLess(oracle.deadline(p, TODAY, 20), oracle.deadline(A, TODAY, 20))
        self.assertTrue(oracle.callback_ok(p, datetime(2026, 10, 14, 11), date(2026, 10, 15), "09:30"))
        self.assertFalse(oracle.callback_ok(p, datetime(2026, 10, 14, 11), date(2026, 10, 15), "18:00"))

    def test_per_type_cap_applies_to_its_product_only(self):
        p = blind.policy_for(next(s for s in blind.SCENARIOS if s["id"] == "g7-multi"))
        car, card = oracle.deadline(p, TODAY, 3, "car_loan"), oracle.deadline(p, TODAY, 3, "credit_card")
        self.assertEqual(car, oracle.nth_business_day_after(p, TODAY, 5))
        self.assertGreater(card, car)

    def test_per_type_floor_applies_to_its_product_only(self):
        p = blind.policy_for(next(s for s in blind.SCENARIOS if s["id"] == "g3-limits"))
        self.assertEqual(oracle.floor(p, {"type": "car_loan", "past_due": 1250.0, "instalment_amount": 400.0}), 625.0)
        self.assertEqual(oracle.floor(p, {"type": "personal_loan", "past_due": 1250.0, "instalment_amount": 400.0}), 400.0)
        self.assertEqual(oracle.deadlines_at(p, "2026-10-14T11:00"), oracle.deadlines_at(A, "2026-10-14T11:00"))

    def test_identity_change_leaves_dates_alone(self):
        p = blind.policy_for(next(s for s in blind.SCENARIOS if s["id"] == "g2-identity"))
        self.assertEqual(p.identity_fields, ("postcode", "birth_year"))
        self.assertEqual(p.wrong_answer_limit, 2)
        self.assertEqual(oracle.deadlines_at(p, "2026-10-14T11:00"), oracle.deadlines_at(A, "2026-10-14T11:00"))


if __name__ == "__main__":
    unittest.main()
