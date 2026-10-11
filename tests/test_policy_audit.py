import importlib.util
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("policy_audit", Path(__file__).resolve().parent.parent / "tools/evaluation/policy_audit.py")
pa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pa)

URL = "https://bank.example/v1/"
CASE = {"variables": {"now": "2026-10-14T11:00"}}
PRODUCTS = [{"product_id": "p1", "type": "credit_card", "past_due": 510, "minimum_payment": 153, "days_late": 16},
            {"product_id": "p2", "type": "personal_loan", "past_due": 1320, "instalment_amount": 440, "days_late": 16},
            {"product_id": "p3", "type": "car_loan", "past_due": 140, "instalment_amount": 46, "days_late": 7}]


def say(t, text):
    return {"role": "assistant", "secondsFromStart": t, "message": text}


def hear(t, text):
    return {"role": "user", "secondsFromStart": t, "message": text}


def tool(t, name, ok=True, done=0.1):
    start = {"event": "function_call_start", "function": "api_call", "args": {"url": URL + name}}
    end = {"event": "function_call_complete", "function": "api_call", "result": {"status": "success", "data": {"ok": ok}}}
    return [{"role": "system", "secondsFromStart": t, "message": json.dumps(start)},
            {"role": "system", "secondsFromStart": t + done, "message": json.dumps(end)}]


def codes(msgs, ledger=None):
    return sorted({f["code"] for f in pa.audit(CASE, ledger or {}, msgs)})


class PolicyAuditTest(unittest.TestCase):
    def test_goodbye_after_close_is_flagged(self):
        msgs = [say(0, "Hello, this is Freya Bank's digital assistant; we keep a recording of this call.")]
        msgs += tool(5, "close_call") + [say(5.2, "Thank you for your time. Goodbye.")]
        self.assertEqual(codes(msgs), ["NO_GOODBYE", "SPEECH_AFTER_CLOSE"])

    def test_clean_promise_close(self):
        msgs = [say(0, "Hello, this call is being monitored."), say(3, "Do you confirm?")] + tool(4, "create_promise")
        msgs += [say(4.3, "Your promise is recorded. You will receive a text message confirming this promise. Goodbye.")]
        msgs += tool(5, "close_call")
        self.assertEqual(codes(msgs), [])

    def test_recorded_in_greeting_early_and_missing_sms(self):
        msgs = [say(0, "Hello, and this call is recorded."), say(3, "Your payment is recorded, one moment.")]
        msgs += tool(4, "create_promise") + [say(4.3, "Thank you. Goodbye.")] + tool(5, "close_call")
        self.assertEqual(codes(msgs), ["RECORDED_EARLY", "RECORDED_IN_GREETING", "SMS_MISSING"])

    def test_negated_recorded_is_not_early(self):
        msgs = [say(0, "Hi."), say(3, "Sorry, the promise was not recorded. I will try again.")]
        self.assertNotIn("RECORDED_EARLY", codes(msgs))

    def test_skipped_product_and_today_asked_again(self):
        ledger = {"calls": [{"tool": "get_account", "result": {"ok": True, "products": PRODUCTS}}],
                  "promises": [{"product_id": "p1"}], "notes": [{"product_id": "p2", "reason": "refused"},
                                                                {"product_id": "p3", "reason": "refused"}]}
        msgs = tool(1, "get_account") + [
            say(2, "Can you pay all of them today?"), hear(3, "Not the personal loan, forget it."),
            say(4, "For your credit card, can you pay 510 today?"), hear(5, "Tomorrow."),
            say(6, "Fine. For your car loan, can you pay 140 on Friday 16 October?"), hear(7, "No.")]
        self.assertEqual(codes(msgs, ledger), ["ITEM_SKIPPED", "TODAY_AGAIN"])

    def test_weekday_mismatch(self):
        self.assertEqual(pa.weekday_findings("on Thursday 30 October 2026", pa.dt.date(2026, 10, 14)),
                         ["'Thursday 30 October 2026' is a Friday"])
        self.assertEqual(pa.weekday_findings("Friday, 2026-10-16 and Friday, October 16th", pa.dt.date(2026, 10, 14)), [])


if __name__ == "__main__":
    unittest.main()
