import unittest

from builder.dryrun import dry_run


def code_step(code):
    return {"node_type": "code", "passthrough": True, "pre_actions": [{"type": "function", "function": {
        "name": "code_exec", "handler": "__function__:code_exec",
        "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code}}}}}]}


WF = {"initial_node": "setup", "nodes": {
    "setup": code_step("import datetime\nd = datetime.date.fromisoformat(vars['now'][:10])\nvars['weekday'] = d.strftime('%A')"),
    "prepare": code_step("vars['label'] = vars['weekday'] + ' / ' + str(len(vars['items']))"),
    "broken": code_step("vars['x'] = 1 / 0"),
}}


class DryRunTest(unittest.TestCase):
    def test_steps_share_vars_in_order_and_report_what_they_write(self):
        report = dry_run(WF, {"now": "2026-10-16T09:00", "items": [1, 2]}, ["setup", "prepare"])
        self.assertEqual([r["written"] for r in report], [{"weekday": "Friday"}, {"label": "Friday / 2"}])

    def test_an_exception_is_reported_and_writes_nothing(self):
        report = dry_run(WF, {"now": "2026-10-16T09:00", "items": []}, ["broken"])
        self.assertEqual(report[0]["written"], {})
        self.assertIn("ZeroDivisionError", report[0]["error"])


if __name__ == "__main__":
    unittest.main()
