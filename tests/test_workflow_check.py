import copy
import json
import tempfile
import unittest
from pathlib import Path

from builder.workflow_check import check

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "docs" / "build-the-builder"
BASE = "https://bank.example/v1"

# A made-up tool API: names and fields are not the event's, so nothing here depends on one brief.
API = {
    "servers": [{"url": BASE}],
    "paths": {
        "/lookup": {"post": {"requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "properties": {"cid": {"type": "string"}}, "required": ["cid"]}}}}}},
        "/log_reason": {"post": {"requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "properties": {"cid": {"type": "string"}, "code": {"type": "string", "enum": ["x", "y"]}},
            "required": ["cid", "code"]}}}}}},
        "/finish": {"post": {"summary": "Ends the session. Nothing is accepted after it.", "requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "properties": {"cid": {"type": "string"}, "result": {"type": "string", "enum": ["ok", "no"]}},
            "required": ["cid", "result"]}}}}}},
    },
}


def tool(op, fields, pre=""):
    t = {"type": "function", "function": {"name": op, "handler": "__function__:api_call", "parameters": {"type": "object", "properties": {
        "url": {"type": "string", "default": f"{BASE}/{op}"}, "method": {"type": "string", "default": "POST"},
        "body": {"type": "object", "properties": fields}}}}}
    if pre:
        t["pre_process_code"] = pre
    return t


CID = {"cid": {"type": "string", "default": "{{cid}}"}}
LOG = tool("log_reason", {**CID, "code": {"type": "string", "enum": ["x", "y"], "default": "{{code}}"}})
FIN = tool("finish", {**CID, "result": {"type": "string", "enum": ["ok", "no"], "default": "{{result}}"}})
END = {"node_type": "end_call", "transitions": [], "terminal": {"type": "function", "function": {"name": "done", "handler": "__function__:end_call"}}}
TO_WRAP = {"target_node": "wrap_up", "description": "done", "is_tool_call": True, "condition": {"operator": "always"}}
FINISHED = {"target_node": "end", "description": "finished", "condition": {"logic": "or", "conditions": [{"variable": "finish_success_count", "operator": "greater_than", "operand": 0}]}}

# Terminal tool alone in its own step, which leads only to end_call: the shape the checker should accept.
GOOD = {
    "initial_node": "talk",
    "nodes": {
        "talk": {"node_type": "conversation", "tools": [tool("lookup", CID), LOG], "transitions": [TO_WRAP]},
        "wrap_up": {"node_type": "conversation", "tools": [FIN], "transitions": [FINISHED]},
        "end": END,
    },
}
CONTRACT = {"terminal_tools": [{"tool": "finish", "evidence": [{"source": "api.json", "quote": "Nothing is accepted after it."}]}],
            "every_call_ends_with_terminal": True}


def run(wf, contract=CONTRACT):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "api.json").write_text(json.dumps(API))
        return check(wf, API, contract, Path(d))


def codes(findings, level="error"):
    return sorted({f.code for f in findings if f.level == level})


class TerminalOrderingTest(unittest.TestCase):
    def test_isolated_terminal_step_passes(self):
        self.assertEqual(codes(run(GOOD)), [])

    def test_terminal_offered_with_another_bank_tool_is_an_error(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["talk"]["tools"].append(FIN)
        wf["nodes"]["talk"]["transitions"] = [FINISHED]
        self.assertIn("E-TERMINAL-SHARED", codes(run(wf)))

    def test_bank_tool_reachable_after_terminal_step_is_an_error(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["wrap_up"]["transitions"] = [FINISHED, {"target_node": "talk", "description": "back", "condition": {"operator": "always"}}]
        self.assertIn("E-TERMINAL-AFTER", codes(run(wf)))

    def test_global_interrupt_with_bank_tool_counts_as_reachable(self):
        wf = copy.deepcopy(GOOD)
        wf["global_nodes"] = {"interrupt": {"node_type": "conversation", "tools": [LOG], "condition": {"operator": "matches_intent", "description": "x"},
                                            "excluded_nodes": ["end"], "transitions": [{"target_node": "__previous__", "description": "back", "condition": {"operator": "always"}}]}}
        self.assertIn("E-TERMINAL-AFTER", codes(run(wf)))
        wf["global_nodes"]["interrupt"]["excluded_nodes"] = ["end", "wrap_up"]
        self.assertNotIn("E-TERMINAL-AFTER", codes(run(wf)))

    def test_end_call_entered_without_terminal_step_is_an_error(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["talk"]["max_node_turns"] = 20
        wf["nodes"]["talk"]["max_turn_transition"] = "end"
        self.assertIn("E-TERMINAL-BYPASS", codes(run(wf)))
        self.assertEqual(codes(run(wf, {**CONTRACT, "every_call_ends_with_terminal": False})), [])

    def test_contract_quote_must_be_in_its_source(self):
        bad = {"terminal_tools": [{"tool": "finish", "evidence": [{"source": "api.json", "quote": "Always the very last call."}]}]}
        self.assertIn("E-CONTRACT-EVIDENCE", codes(run(GOOD, bad)))
        self.assertIn("E-CONTRACT-TOOL", codes(run(GOOD, {"terminal_tools": [{"tool": "nope", "evidence": [{"source": "api.json", "quote": "Nothing is accepted after it."}]}]})))

    def test_without_contract_ordering_is_not_checked(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["talk"]["tools"].append(FIN)
        self.assertEqual(codes(check(wf, API, None)), [])


class ToolContractTest(unittest.TestCase):
    def test_fields_enums_and_required_come_from_the_tool_api(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["talk"]["tools"][1] = tool("log_reason", {**CID, "code": {"type": "string", "enum": ["x", "z"]}, "extra": {"type": "string"}})
        wf["nodes"]["wrap_up"]["tools"][0] = tool("finish", {**CID})
        found = codes(run(wf))
        self.assertIn("E-TOOL-ENUM", found)
        self.assertIn("E-TOOL-FIELD", found)
        self.assertIn("E-TOOL-REQUIRED", found)

    def test_fixed_value_outside_enum_and_unknown_url(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["talk"]["tools"][1] = tool("log_reason", {**CID, "code": {"type": "string", "default": "w"}})
        wf["nodes"]["talk"]["tools"].append(tool("transfer", CID))
        found = codes(run(wf))
        self.assertIn("E-TOOL-ENUM", found)
        self.assertIn("E-TOOL-UNKNOWN", found)

    def test_a_pre_hook_turns_field_findings_into_warnings(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["wrap_up"]["tools"][0] = tool("finish", {**CID, "code_word": {"type": "string"}}, pre="config['body']['result'] = 'ok'")
        found = run(wf)
        self.assertNotIn("E-TOOL-FIELD", codes(found))
        self.assertIn("E-TOOL-FIELD", codes(found, "warning"))


class GraphTest(unittest.TestCase):
    def test_platform_rules(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["talk"]["transitions"].append({"target_node": "missing", "description": "x", "condition": {"operator": "always"}})
        wf["nodes"]["calc"] = {"node_type": "code", "passthrough": True, "transitions": [{"target_node": "talk", "description": "x", "condition": {"operator": "is_set", "variable": "a"}}],
                               "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec", "parameters": {"type": "object", "properties": {
                                   "code": {"type": "string", "default": "vars['a'] = {'b': {'c': 1}}"}}}}}], "tools": [LOG]}
        wf["nodes"]["talk"]["role_message"] = None
        found = codes(run(wf))
        for code in ("E-REF", "E-PASSTHROUGH", "E-CODE-BRACES", "E-PLACEMENT", "E-NULL"):
            self.assertIn(code, found)

    def test_export_nulls_are_platform_defaults(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["talk"]["max_turn_transition"] = None
        self.assertIn("E-NULL", codes(run(wf)))
        self.assertNotIn("E-NULL", codes(run({"workflow_id": "w", "workflow": wf})))


@unittest.skipUnless((ROOT / "runs" / "20261010-154045-kit-ab" / "brief-b.workflow.json").exists(), "A+B run not present")
class ObservedFailureTest(unittest.TestCase):
    """The B agent that wrote add_note after close_call (PUB-05, PUB-08, PUB-12) offers both in one step."""

    def test_flags_the_shared_terminal_step(self):
        wf = json.loads((ROOT / "runs" / "20261010-154045-kit-ab" / "brief-b.workflow.json").read_text())
        api = json.loads((KIT / "tools" / "openapi.json").read_text())
        contract = {"terminal_tools": [{"tool": "close_call", "evidence": [{"source": "tools/openapi.json", "quote": "Always the last tool call. Nothing is accepted after it."}]}],
                    "every_call_ends_with_terminal": True}
        shared = [f for f in check(wf, api, contract, KIT) if f.code == "E-TERMINAL-SHARED"]
        self.assertIn("negotiate", {f.where for f in shared})
        self.assertTrue(any("add_note" in f.message for f in shared))


if __name__ == "__main__":
    unittest.main()
