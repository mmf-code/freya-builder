"""Triage separates platform failures, stalls and agent failures, and names general failure modes."""
import copy
import json
import unittest

from tools.persona_lab.common import load_cases
from tools.persona_lab.triage import triage

CASES = load_cases()


def ev(event, fn=None, t=0.0, **extra):
    return {"role": "system", "secondsFromStart": t, "message": json.dumps({"event": event, "function": fn, **extra})}


def call(tool, **result):
    return {"tool": tool, "result": {"ok": True, **result}}


def good_ledger(case_id):
    exp = CASES[case_id]["expected"]
    calls = [call("verify_identity"), call("verify_identity"), call("get_account")]
    calls += [call("create_promise") for _ in exp["promises"]] + [call("close_call")]
    return {"outcome": exp["outcome"], "reason": exp["reason"], "promises": copy.deepcopy(exp["promises"]),
            "notes": exp["notes"], "callbacks": exp["callbacks"], "transfers": exp["transfers"], "calls": calls}


def record(case_id="PUB-10", layer="official", ledger=None, judge="pass", messages=None, **kw):
    msgs = messages if messages is not None else [ev("function_call_start", "create_promise", 1), ev("function_call_complete", "create_promise", 2),
                                                  ev("function_call_start", "close_call", 3), ev("function_call_complete", "close_call", 4)]
    return {"variant": "VX", "layer": layer, "case": CASES[case_id], "ledger": ledger if ledger is not None else good_ledger(case_id),
            "judge": {"outcome": judge, "reason": "r"}, "messages": msgs, "simulation_status": "completed", **kw}


class TriageTest(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(triage(record())["verdict"], "PASS")

    def test_duplicate_promise_is_an_agent_failure(self):
        led = good_ledger("PUB-10")
        led["promises"].append(dict(led["promises"][0]))
        t = triage(record(ledger=led, judge="fail"))
        self.assertEqual(t["verdict"], "AGENT_FAIL")
        self.assertIn("DUPLICATE_WRITE", t["modes"])

    def test_sandbox_error_is_infrastructure(self):
        led = good_ledger("PUB-10")
        led["outcome"] = "no_promise"
        msgs = record()["messages"] + [ev("function_call_error", "create_promise", 2, error="Failed to reach snekbox")]
        t = triage(record(ledger=led, judge="fail", messages=msgs))
        self.assertEqual(t["verdict"], "INFRA_CONFIRMED")
        self.assertTrue(t["infra_evidence"])

    def test_stall_without_error_is_inconclusive_not_infra(self):
        led = {"outcome": None, "reason": None, "promises": [], "notes": [], "callbacks": [], "transfers": [], "calls": []}
        t = triage(record(ledger=led, judge="fail", messages=[], ended="customer-ended-call"))
        self.assertEqual(t["verdict"], "INCONCLUSIVE")
        self.assertTrue(t["stall_without_error"])
        self.assertEqual(t["infra_evidence"], [])

    def test_pending_judge_is_inconclusive(self):
        self.assertEqual(triage(record(judge="running"))["verdict"], "INCONCLUSIVE")

    def test_judge_only_failure(self):
        t = triage(record(judge="fail"))
        self.assertEqual((t["verdict"], t["modes"]), ("AGENT_FAIL", ["JUDGE_ONLY"]))

    def test_terminal_not_last_and_overlap(self):
        led = good_ledger("PUB-10")
        led["calls"].append(call("add_note", error="the call is already closed"))
        msgs = [ev("function_call_start", "close_call", 1), ev("function_call_start", "add_note", 1.1),
                ev("function_call_complete", "add_note", 1.5), ev("function_call_complete", "close_call", 2)]
        t = triage(record(ledger=led, judge="fail", messages=msgs))
        self.assertIn("TERMINAL_ORDER", t["modes"])
        self.assertIn("TERMINAL_RACE", t["modes"])

    def test_identity_tools_on_third_party_case(self):
        led = good_ledger("PUB-02")
        t = triage(record("PUB-02", ledger=led, judge="fail"))
        self.assertIn("THIRD_PARTY_AUTH", t["modes"])

    def test_account_before_verification(self):
        led = good_ledger("PUB-01")
        led["calls"].insert(0, {"tool": "get_account", "result": {"ok": False, "error": "identity not verified"}})
        self.assertIn("AUTH_ORDER", triage(record("PUB-01", ledger=led, judge="fail"))["modes"])

    def test_wrong_date_and_notes_name_their_families(self):
        led = good_ledger("PUB-12")
        led["promises"][0]["date"] = "2026-10-16"
        led["notes"] = led["notes"][:1]
        modes = triage(record("PUB-12", ledger=led, judge="fail"))["modes"]
        self.assertIn("DATE", modes)
        self.assertIn("NOTES", modes)

    def test_diagnostic_ledger_mismatch_is_information(self):
        led = good_ledger("PUB-01")
        led["outcome"] = "no_promise"
        t = triage(record("PUB-01", layer="diagnostic", ledger=led, judge="fail"))
        self.assertEqual(t["verdict"], "INFO")

    def test_diagnostic_invariant_breach_is_a_failure(self):
        led = good_ledger("PUB-01")
        led["calls"].insert(0, {"tool": "get_account", "result": {"ok": False, "error": "identity not verified"}})
        t = triage(record("PUB-01", layer="diagnostic", ledger=led, judge="fail"))
        self.assertEqual((t["verdict"], t["modes"]), ("AGENT_FAIL", ["AUTH_ORDER"]))


if __name__ == "__main__":
    unittest.main()
