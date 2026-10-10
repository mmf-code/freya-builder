import json
import unittest

from builder.callaudit import audit_case


def ev(event, fn, t):
    return {"role": "system", "secondsFromStart": t, "message": json.dumps({"event": event, "function": fn})}


class CallAuditTest(unittest.TestCase):
    def test_concurrent_note_and_terminal_are_flagged(self):
        ledger = {"calls": [{"tool": "lookup", "result": {"ok": True}}, {"tool": "finish", "result": {"ok": True}},
                            {"tool": "log", "result": {"ok": False, "error": "the call is already closed"}}]}
        msgs = [ev("function_call_start", "log", 1.0), ev("function_call_start", "finish", 1.01),
                ev("function_call_complete", "finish", 1.5), ev("function_call_complete", "log", 1.6)]
        r = audit_case({"id": "c", "pass": False}, "finish", ledger, msgs)
        self.assertFalse(r["terminal_last"])
        self.assertEqual(r["rejected_after_terminal"], ["log"])
        self.assertEqual(r["overlapping_terminal"], ["log"])

    def test_sequential_calls_are_clean(self):
        ledger = {"calls": [{"tool": "log", "result": {"ok": True}}, {"tool": "finish", "result": {"ok": True}}]}
        msgs = [ev("function_call_start", "log", 1.0), ev("function_call_complete", "log", 1.2),
                ev("function_call_start", "finish", 2.0), ev("function_call_complete", "finish", 2.3)]
        r = audit_case({"id": "c", "pass": True}, "finish", ledger, msgs)
        self.assertEqual((r["terminal_last"], r["rejected_after_terminal"], r["overlapping_terminal"], r["terminal_calls"]), (True, [], [], 1))


if __name__ == "__main__":
    unittest.main()
