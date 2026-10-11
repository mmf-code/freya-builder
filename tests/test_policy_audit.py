import importlib.util
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("policy_audit", Path(__file__).resolve().parent.parent / "tools/evaluation/policy_audit.py")
pa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pa)

URL = "https://bank.example/v1/"
CASE = {"variables": {"now": "2026-10-14T11:00"}}
CARD = {"product_id": "p1", "type": "credit_card", "past_due": 510, "minimum_payment": 153, "days_late": 16}
LOAN = {"product_id": "p2", "type": "personal_loan", "past_due": 1320, "instalment_amount": 440, "days_late": 16}
CAR = {"product_id": "p3", "type": "car_loan", "past_due": 140, "instalment_amount": 46, "days_late": 7}


def say(t, text):
    return {"role": "assistant", "secondsFromStart": t, "message": text}


def hear(t, text):
    return {"role": "user", "secondsFromStart": t, "message": text}


def tool(t, name, ok=True, done=0.1, product=None):
    body = {"product_id": product} if product else {}
    start = {"event": "function_call_start", "function": name, "args": {"url": URL + name, "body": body}}
    end = {"event": "function_call_complete", "function": name, "result": {"status": "success", "data": {"ok": ok}}}
    return [{"role": "system", "secondsFromStart": t, "message": json.dumps(start)},
            {"role": "system", "secondsFromStart": t + done, "message": json.dumps(end)}]


def account(*products, **extra):
    return {"calls": [{"tool": "get_account", "result": {"ok": True, "products": list(products)}}], **extra}


def run(msgs, ledger=None, case=CASE):
    return pa.audit(case, ledger or {}, msgs)


def codes(msgs, ledger=None, case=CASE):
    return sorted({f["code"] for f in run(msgs, ledger, case)["findings"]})


class ClosingTest(unittest.TestCase):
    def test_goodbye_after_close_is_flagged(self):
        msgs = [say(0, "Hello, this is Freya Bank's digital assistant; we keep a recording of this call.")]
        msgs += tool(5, "close_call") + [say(5.2, "Thank you for your time. Goodbye.")]
        self.assertEqual(codes(msgs), ["NO_GOODBYE", "NO_THANKS", "SPEECH_AFTER_CLOSE"])

    def test_goodbye_before_close_then_more_speech_is_only_an_observation(self):
        msgs = [say(0, "Hello."), say(4, "Thank you for your time. Goodbye.")] + tool(5, "close_call") + [say(5.2, "Bye.")]
        found = run(msgs)["findings"]
        self.assertEqual([(f["code"], f["class"]) for f in found], [("SPEECH_AFTER_CLOSE", "observation")])

    def test_clean_promise_close(self):
        msgs = [say(0, "Hello, this call is being monitored."), say(3, "Do you confirm?")] + tool(4, "create_promise", product="p1")
        msgs += [say(4.3, "Your promise is recorded. You will receive a text message confirming this promise. Thank you. Goodbye.")]
        msgs += tool(5, "close_call")
        self.assertEqual(codes(msgs), [])


class RecordedTest(unittest.TestCase):
    def test_greeting_disclosure_is_a_judge_risk_not_a_violation(self):
        found = run([say(0, "Hello, and this call is recorded.")])["findings"]
        self.assertEqual([(f["code"], f["class"]) for f in found], [("RECORDED_IN_GREETING", "judge risk")])

    def test_greeting_claiming_a_promise_is_early(self):
        self.assertIn("RECORDED_EARLY", codes([say(0, "Hello, your promise is recorded.")]))

    def test_early_claim_and_missing_sms(self):
        msgs = [say(0, "Hello, and this call is recorded."), say(3, "Your payment is recorded, one moment.")]
        msgs += tool(4, "create_promise", product="p1") + [say(4.3, "Thank you. Goodbye.")] + tool(5, "close_call")
        self.assertEqual(codes(msgs), ["RECORDED_EARLY", "RECORDED_IN_GREETING", "SMS_MISSING"])

    def test_negated_future_and_contracted_forms_are_not_claims(self):
        for line in ("Sorry, the promise was not recorded. I will try again.", "It hasn't been recorded yet.",
                     "Your promise will be recorded after you confirm."):
            self.assertNotIn("RECORDED_EARLY", codes([say(0, "Hi."), say(3, line)]), line)

    def test_second_product_claimed_before_its_own_write(self):
        msgs = tool(1, "get_account") + tool(4, "create_promise", product="p1")
        msgs += [say(4.5, "Your car loan payment is recorded.")] + tool(6, "create_promise", product="p3")
        self.assertIn("RECORDED_EARLY", codes(msgs, account(CARD, CAR)))


class SmsTest(unittest.TestCase):
    def _call(self, line):
        return tool(1, "create_promise", product="p1") + [say(1.5, line)]

    def test_negated_sentence_is_missing(self):
        self.assertIn("SMS_MISSING", codes(self._call("You will not receive a text message.")))

    def test_paraphrase_is_wording(self):
        found = run(self._call("You will receive a text message confirming these promises."))["findings"]
        self.assertEqual([(f["code"], f["class"]) for f in found], [("SMS_NOT_VERBATIM", "wording")])

    def test_exact_sentence(self):
        self.assertEqual(codes(self._call("Thank you. You will receive a text message confirming this promise.")), [])


class ProductsTest(unittest.TestCase):
    def test_skipped_product_and_today_asked_again(self):
        ledger = account(CARD, LOAN, CAR, promises=[{"product_id": "p1"}],
                         notes=[{"product_id": "p2", "reason": "refused"}, {"product_id": "p3", "reason": "refused"}])
        msgs = tool(1, "get_account") + [
            say(2, "Can you pay all of them today?"), hear(3, "Not the personal loan, forget it."),
            say(4, "For your credit card, can you pay 510 today?"), hear(5, "Tomorrow."),
            say(6, "Fine. For your car loan, can you pay 140 on Friday 16 October?"), hear(7, "No.")]
        self.assertEqual(codes(msgs, ledger), ["ITEM_SKIPPED", "TODAY_AGAIN"])

    def test_today_again_needs_several_products_and_accepts_please(self):
        single = account(CARD)
        msgs = tool(1, "get_account") + [say(2, "Can you make this payment today?"), hear(3, "Too much."),
                                         say(4, "Could you pay the minimum of 153 today?")]
        result = run(msgs, single)
        self.assertNotIn("TODAY_AGAIN", [f["code"] for f in result["findings"]])
        self.assertNotIn("TODAY_AGAIN", result["checked"])
        multi = tool(1, "get_account") + [say(2, "Can you pay all of them today?"), hear(3, "No."),
                                          say(4, "Can you pay the 140 for the car loan today, please?")]
        self.assertIn("TODAY_AGAIN", codes(multi, account(CARD, CAR)))

    def test_clarification_repeat_is_not_a_new_attempt(self):
        ledger = account(CARD, CAR, promises=[{"product_id": "p1"}], notes=[{"product_id": "p3", "reason": "refused"}])
        msgs = tool(1, "get_account") + [
            say(1.5, "For your credit card, can you pay 510 on Friday 16 October?"), hear(1.8, "Yes."),
            say(2, "For your car loan, can you pay 140 on Friday 16 October?"), hear(3, "Which date was that?"),
            say(4, "Can you pay 140 on Friday 16 October?"), hear(5, "No.")]
        self.assertEqual(codes(msgs, ledger), [])

    def test_negated_date_does_not_settle_an_earlier_product(self):
        ledger = account(CARD, LOAN, promises=[{"product_id": "p1"}, {"product_id": "p2"}])
        msgs = tool(1, "get_account") + [hear(2, "I can't pay the card tomorrow."),
                                         say(3, "For the personal loan, can you pay 1320 on Friday 16 October?")]
        self.assertIn("ORDER", codes(msgs, ledger))
        settled = tool(1, "get_account") + [hear(2, "I will pay the card tomorrow, but I am not paying the loan."),
                                            say(3, "For the personal loan, can you pay 1320 on Friday 16 October?")]
        self.assertNotIn("ORDER", codes(settled, ledger))


class WeekdayTest(unittest.TestCase):
    def test_numbers_iso_and_words(self):
        now = pa.dt.date(2026, 10, 14)
        self.assertEqual(pa.weekday_findings("on Thursday 30 October 2026", now), ["'Thursday 30 October 2026' is a Friday"])
        self.assertEqual(pa.weekday_findings("Friday, 2026-10-16 and Friday, October 16th", now), [])
        self.assertEqual(len(pa.weekday_findings("Thursday the thirtieth of October", now)), 1)
        self.assertEqual(pa.weekday_findings("Friday the twenty-third of October", now), [])


class TriggerTest(unittest.TestCase):
    def test_persona_behaviour_happened_or_not(self):
        v09 = dict(CASE, style="pl-V09")
        early = tool(1, "get_account") + [hear(2, "The personal loan, I'm not paying that, forget it."),
                                          say(3, "For the personal loan, can you pay 1320 on Friday 16 October?")]
        self.assertTrue(run(early, account(CARD, LOAN), v09)["trigger"])
        late = tool(1, "get_account") + [say(2, "For the personal loan, can you pay 1320 on Friday 16 October?"),
                                         hear(3, "The personal loan, I'm not paying that.")]
        self.assertFalse(run(late, account(CARD, LOAN), v09)["trigger"])
        self.assertFalse(run([hear(1, "Okay.")], {}, dict(CASE, style="pl-V06"))["trigger"])
        self.assertIsNone(run([hear(1, "Okay.")])["trigger"])


if __name__ == "__main__":
    unittest.main()
