import copy
import json
import tempfile
import unittest
from pathlib import Path

from builder.workflow_check import check, load_operations, sandbox_exposure

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


ALWAYS = {"operator": "always"}
CODE = {"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec", "parameters": {"type": "object", "properties": {
    "code": {"type": "string", "default": "vars['next'] = 'again'"}}}}}


def step(kind, routes, pre=None):
    """A passthrough action step; routes are (target, condition) in priority order."""
    return {"node_type": kind, "passthrough": True, "pre_actions": [pre or (CODE if kind == "code" else tool("lookup", CID))],
            "transitions": [{"target_node": t, "description": t, "condition": c} for t, c in routes]}


def counter(step_name, kind, op, n):
    return {"variable": f"{step_name}_{kind}_count", "operator": op, "operand": n}


def any_of(*checks):
    return {"logic": "or", "conditions": list(checks)}


def all_of(*checks):
    return {"logic": "or", "conditions": [{"logic": "and", "conditions": list(checks)}]}


AGAIN = any_of({"variable": "next", "operator": "equals", "operand": "again"})
LOOP = {  # pick (code) -> call (bank) -> pick, ending at wrap_up: the shape of the candidate2 per-item loop
    "initial_node": "talk",
    "nodes": {
        "talk": {"node_type": "conversation", "tools": [], "transitions": [{"target_node": "pick", "description": "go", "condition": ALWAYS}]},
        "pick": step("code", [("call", AGAIN), ("wrap_up", ALWAYS)]),
        "call": step("api_request", [("pick", ALWAYS)]),
        "wrap_up": GOOD["nodes"]["wrap_up"],
        "end": END,
    },
}


def loops(wf):
    return [f for f in run(wf) if f.code == "E-ENGINE-LOOP"]


class BoundedExecutionTest(unittest.TestCase):
    def test_engine_loop_selected_by_code_is_an_error(self):
        found = loops(LOOP)
        self.assertEqual(len(found), 1)
        self.assertIn("call -> pick -> call", found[0].message)

    def test_exit_on_both_counters_of_a_step_on_the_loop_bounds_it(self):
        wf = copy.deepcopy(LOOP)
        guard = any_of(counter("call", "success", "greater_than", 3), counter("call", "failure", "greater_than", 3))
        wf["nodes"]["pick"]["transitions"].insert(0, {"target_node": "wrap_up", "description": "cap", "condition": guard})
        self.assertEqual(loops(wf), [])
        writes = [f for f in run(wf) if f.code == "W-LOOP-WRITE"]
        self.assertTrue(writes and "about 7 times" in writes[0].message and "not proven" in writes[0].message)

    def test_one_counter_is_not_a_bound(self):
        # HTTP 200 with ok:false counts as a success, so a cap on failures alone never stops that loop.
        wf = copy.deepcopy(LOOP)
        wf["nodes"]["pick"]["transitions"].insert(0, {"target_node": "wrap_up", "description": "cap", "condition": any_of(counter("call", "failure", "greater_than", 3))})
        self.assertEqual(len(loops(wf)), 1)

    def test_exit_must_be_checked_before_the_loop_edge(self):
        wf = copy.deepcopy(LOOP)
        guard = any_of(counter("call", "success", "greater_than", 3), counter("call", "failure", "greater_than", 3))
        wf["nodes"]["pick"]["transitions"].insert(1, {"target_node": "wrap_up", "description": "cap", "condition": guard})
        self.assertEqual(len(loops(wf)), 1)

    def test_counter_of_a_step_off_the_loop_and_code_variables_do_not_count(self):
        wf = copy.deepcopy(LOOP)
        guard = any_of(counter("other", "success", "greater_than", 3), counter("other", "failure", "greater_than", 3),
                       {"variable": "attempts", "operator": "greater_than", "operand": 3})
        wf["nodes"]["pick"]["transitions"].insert(0, {"target_node": "wrap_up", "description": "cap", "condition": guard})
        self.assertEqual(len(loops(wf)), 1)

    def test_retry_while_both_counters_are_below_a_limit_is_bounded(self):
        wf = copy.deepcopy(LOOP)
        wf["nodes"]["pick"]["transitions"][0]["condition"] = all_of(
            AGAIN["conditions"][0], counter("call", "success", "less_than", 2), counter("call", "failure", "less_than", 2))
        self.assertEqual(loops(wf), [])
        wf["nodes"]["pick"]["transitions"].insert(0, {"target_node": "call", "description": "unguarded", "condition": AGAIN})
        self.assertEqual(len(loops(wf)), 1)

    def test_loop_through_a_step_that_waits_for_the_customer_is_allowed(self):
        wf = copy.deepcopy(LOOP)
        wf["nodes"]["call"]["transitions"] = [{"target_node": "talk", "description": "back", "condition": ALWAYS}]
        wf["nodes"]["talk"]["transitions"] = [{"target_node": "pick", "description": "go", "condition": AGAIN},
                                              {"target_node": "talk", "description": "stay", "condition": ALWAYS}]
        self.assertEqual(loops(wf), [])

    def test_passthrough_self_loop_is_an_error(self):
        wf = copy.deepcopy(LOOP)
        wf["nodes"]["pick"]["transitions"] = [{"target_node": "pick", "description": "again", "condition": AGAIN}, {"target_node": "wrap_up", "description": "x", "condition": ALWAYS}]
        self.assertIn("pick -> pick", loops(wf)[0].message)

    def test_unreachable_step_is_a_warning_and_hooks_are_counted(self):
        wf = copy.deepcopy(GOOD)
        wf["nodes"]["orphan"] = {"node_type": "conversation", "tools": [], "transitions": [{"target_node": "wrap_up", "description": "x", "condition": ALWAYS}]}
        wf["nodes"]["talk"]["tools"][0] = tool("lookup", CID, pre="vars['cid'] = str(vars.get('cid'))")
        found = run(wf)
        self.assertEqual(codes(found), [])
        self.assertEqual(codes(found, "warning"), ["W-UNREACHABLE"])
        exposure = sandbox_exposure(wf, load_operations(API))
        self.assertEqual((exposure["hooks"], exposure["hooks_on_bank_tools"]), (1, 1))
        self.assertEqual(sandbox_exposure(LOOP, load_operations(API))["code_steps_in_engine_loops"], 1)

    def test_kit_complete_example_has_no_engine_loop(self):
        # The official example: a conversation step that loops on itself, and a passthrough lookup with a failure exit.
        text = (KIT / "docs" / "workflow-format.md").read_text()
        example = json.loads(text.split("## Complete example")[1].split("```json")[1].split("```")[0])
        found = [f for f in check(example, API) if f.code in ("E-ENGINE-LOOP", "W-UNREACHABLE")]
        self.assertEqual(found, [])


CANDIDATE2 = ROOT / "runs" / "20261010-172700-candidate2-ab"


def unguarded(export):
    """candidate2 version 3, rebuilt from the version 4 export: undo the graph edits of builder trace step 027
    ("Add loop guard and code retries", trace.jsonl). Version 3 sent create_promise about 184 times in one call
    (results/a3.json, PUB-10). The step also changed code retries and one line of code; neither is part of the graph."""
    wf = copy.deepcopy(export)
    nodes = wf["workflow"]["nodes"]
    nodes["pick_next"]["transitions"] = [t for t in nodes["pick_next"]["transitions"] if t.get("description") != "loop guard"]
    for key in ("record_promise", "add_note_api"):
        if key in nodes:
            nodes[key]["response_mapping"] = [m for m in nodes[key]["response_mapping"] if m.get("variable") != "next_step"]
    return wf


@unittest.skipUnless(CANDIDATE2.exists(), "candidate2 run not present")
class ObservedLoopTest(unittest.TestCase):
    api = json.loads((KIT / "tools" / "openapi.json").read_text()) if KIT.exists() else {}

    def test_version_3_loop_is_flagged_and_version_4_guard_is_accepted(self):
        for brief, loops_v3 in (("brief-a", 1), ("brief-b", 2)):
            export = json.loads((CANDIDATE2 / f"{brief}.workflow.json").read_text())
            v3 = [f for f in check(unguarded(export), self.api) if f.code == "E-ENGINE-LOOP"]
            self.assertEqual(len(v3), loops_v3, brief)
            self.assertTrue(all("pick_next" in f.message and "(bank)" in f.message for f in v3))
            self.assertEqual([f for f in check(export, self.api) if f.code == "E-ENGINE-LOOP"], [], brief)

    def test_preserved_exports_get_no_new_errors(self):
        for path in sorted(ROOT.glob("runs/*/*.workflow.json")):
            found = check(json.loads(path.read_text()), self.api)
            self.assertEqual([f for f in found if f.code in ("E-ENGINE-LOOP", "W-UNREACHABLE")], [], path.parent.name)


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
