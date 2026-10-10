import copy
import json
import tempfile
import unittest
from pathlib import Path

from builder.lower import SYMBOL, LoweringError, lower, step_name
from builder.workflow_check import check, tool_operation, load_operations
from tests.test_workflow_check import API, CID, LOG, ROOT, tool

QUOTE = "Nothing is accepted after it."
BRIEF = ("Close as `no` / `busy` when the customer has no time. Close as `ok` after a recorded result. "
         "A customer has up to three items. An early item gets one attempt, a late item two.")
PLAN = {"terminal": {"tool": "finish", "evidence": [{"source": "api.json", "quote": QUOTE}]},
        "fields": {"cid": "{{cid}}"},
        "closings": {"ok": {"set": {"result": "ok"}, "evidence": [{"source": "brief.md", "quote": "Close as `ok` after a recorded result."}]},
                     "no/busy": {"set": {"result": "no"}, "say": "Goodbye.", "evidence": [{"source": "brief.md", "quote": "Close as `no` / `busy`"}]}}}
BODY = {"initial_node": "talk", "nodes": {"talk": {
    "node_type": "conversation", "tools": [tool("lookup", CID), LOG], "max_node_turns": 20, "max_turn_transition": SYMBOL + "no/busy",
    "transitions": [{"target_node": SYMBOL + "ok", "description": "done", "condition": {"logic": "or", "conditions": [{"variable": "log_reason_success_count", "operator": "greater_than", "operand": 0}]}},
                    {"target_node": SYMBOL + "no/busy", "description": "no time", "is_tool_call": True, "condition": {"operator": "matches_intent", "description": "no time"}}]}}}


def run(body=BODY, plan=PLAN, api=API):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "api.json").write_text(json.dumps(api))
        (Path(d) / "brief.md").write_text(BRIEF)
        wf, contract = lower(body, plan, api, Path(d))
        return wf, contract, check(wf, api, contract, Path(d))


def problems(body=BODY, plan=PLAN):
    try:
        run(body, plan)
    except LoweringError as e:
        return " | ".join(e.problems)
    return ""


class LoweringTest(unittest.TestCase):
    def test_endings_are_written_and_pass_the_checker(self):
        wf, contract, found = run()
        self.assertEqual([f for f in found if f.level == "error"], [])
        self.assertEqual(sorted(wf["nodes"]), ["close_no_busy", "close_ok", "hang_up", "talk"])
        self.assertEqual(wf["nodes"]["talk"]["max_turn_transition"], "close_no_busy")
        self.assertEqual(wf["nodes"]["close_no_busy"]["on_enter"], {"type": "tts", "text": "Goodbye."})
        sent = wf["nodes"]["close_ok"]["pre_actions"][0]["function"]["parameters"]["properties"]
        self.assertEqual(sent["url"]["default"], "https://bank.example/v1/finish")
        self.assertEqual(sent["body"]["properties"]["result"], {"type": "string", "default": "ok", "enum": ["ok"]})

    def test_same_plan_gives_the_same_workflow(self):
        reordered = {**PLAN, "closings": dict(reversed(list(PLAN["closings"].items())))}
        self.assertEqual(json.dumps(run()[0], sort_keys=True), json.dumps(run(plan=reordered)[0], sort_keys=True))

    def test_terminal_tool_in_a_body_step_is_rejected(self):
        body = copy.deepcopy(BODY)
        body["nodes"]["talk"]["tools"].append(tool("finish", CID))
        self.assertIn("offers or runs the terminal tool finish", problems(body))

    def test_values_must_come_from_the_tool_api_or_the_evidence(self):
        plan = copy.deepcopy(PLAN)
        plan["closings"]["ok"]["set"]["result"] = "done"
        self.assertIn("'done' is not one of", problems(plan=plan))
        plan = copy.deepcopy(PLAN)
        plan["closings"]["ok"]["evidence"][0]["quote"] = "Close as `ok` always."
        self.assertIn("every evidence quote must appear", problems(plan=plan))
        plan = copy.deepcopy(PLAN)
        plan["fields"] = {}
        self.assertIn("required fields ['cid']", problems(plan=plan))

    def test_endings_with_the_same_values_stay_distinct(self):
        plan = copy.deepcopy(PLAN)
        plan["closings"]["busy_again"] = {**copy.deepcopy(PLAN["closings"]["no/busy"]), "say": "Another farewell."}
        body = copy.deepcopy(BODY)
        body["nodes"]["talk"]["transitions"].append({"target_node": SYMBOL + "busy_again", "description": "x", "condition": {"operator": "always"}})
        wf = run(body, plan)[0]
        self.assertEqual(wf["nodes"]["close_busy_again"]["on_enter"]["text"], "Another farewell.")
        self.assertEqual(wf["nodes"]["close_no_busy"]["on_enter"]["text"], "Goodbye.")
        plan["closings"]["no_busy"] = plan["closings"]["no/busy"]
        self.assertIn("same step name 'close_no_busy'", problems(plan=plan))

    def test_undeclared_closing_and_written_end_steps_are_rejected(self):
        body = copy.deepcopy(BODY)
        body["nodes"]["talk"]["transitions"][0]["target_node"] = SYMBOL + "maybe"
        body["nodes"]["bye"] = {"node_type": "end_call", "transitions": []}
        found = problems(body)
        self.assertIn("undeclared closing 'maybe'", found)
        self.assertIn("'bye' is an end_call step", found)


LADDER = {"template": "offer", "done": "wrap",
          "items": {"count": "n_items", "max": 3, "evidence": [{"source": "brief.md", "quote": "A customer has up to three items."}]},
          "attempts": {"allowed": "tries_{i}", "max": 2, "evidence": [{"source": "brief.md", "quote": "An early item gets one attempt, a late item two."}]},
          "refusal": "no_{i}_{a}"}
LADDER_BODY = {"initial_node": "talk", "nodes": {
    "talk": {"node_type": "conversation", "tools": [], "transitions": [{"target_node": "item:first", "description": "go", "condition": {"operator": "always"}}]},
    "offer": {"node_type": "conversation", "task_message": "Item {i}: {{facts_{i}}}. Make attempt {a}: {{offer_{i}_{a}}}.", "tools": [LOG],
              "extraction_schema": [{"name": "no_{i}_{a}", "type": "string", "enum_values": ["yes", "no"], "description": "yes if the customer flatly refuses the offer", "min_confidence": 0.7}],
              "max_node_turns": 12, "max_turn_transition": SYMBOL + "no/busy",
              "transitions": [{"target_node": "item:next", "description": "agreed on item {i}", "is_tool_call": True, "condition": {"operator": "matches_intent", "description": "agreed"}},
                              {"target_node": "offer", "description": "stay", "condition": {"operator": "always"}}]},
    "wrap": {"node_type": "conversation", "tools": [], "transitions": [{"target_node": SYMBOL + "ok", "description": "done", "is_tool_call": True, "condition": {"operator": "matches_intent", "description": "done"}}]}}}


def holds(cond, v):
    if cond.get("operator") == "always":
        return True
    if "conditions" in cond:
        found = [holds(c, v) for c in cond["conditions"]]
        return all(found) if cond.get("logic") == "and" else any(found)
    x, o = v.get(cond.get("variable")), cond.get("operand")
    if x is None:
        return False
    return {"equals": lambda: str(x) == str(o), "greater_than": lambda: float(x) > float(o), "less_than": lambda: float(x) < float(o)}[cond["operator"]]()


def refuse_everything(wf, variables, stop="wrap"):
    """Steps visited when the customer refuses every offer: deterministic routes only, as the engine checks them first."""
    v, path, key = dict(variables), [], wf["initial_node"]
    while key != stop and len(path) < 60:
        node = wf["nodes"][key]
        path.append(key)
        for e in node.get("extraction_schema") or []:
            v[e["name"]] = "yes"
        key = next(t["target_node"] for t in node["transitions"] if not t.get("is_tool_call") and holds(t["condition"], v))
    return [p for p in path if p.startswith("offer_") and "_item_" not in p]


class LadderTest(unittest.TestCase):
    def lowered(self, ladder=LADDER, body=LADDER_BODY):
        return run(body, {**PLAN, "ladder": ladder})

    def test_each_item_gets_exactly_its_allowed_attempts(self):
        wf, _, found = self.lowered()
        self.assertEqual([f for f in found if f.level == "error"], [])
        self.assertEqual([f.code for f in found if f.code in ("W-UNREACHABLE", "W-LOOP-WRITE")], [])
        self.assertEqual(refuse_everything(wf, {"n_items": 3, "tries_1": 2, "tries_2": 1, "tries_3": 2}),
                         ["offer_1_1", "offer_1_2", "offer_2_1", "offer_3_1", "offer_3_2"])
        self.assertEqual(refuse_everything(wf, {"n_items": 1, "tries_1": 1}), ["offer_1_1"])

    def test_template_is_filled_in_per_item_and_attempt(self):
        wf = self.lowered()[0]
        step = wf["nodes"]["offer_2_1"]
        self.assertEqual(step["task_message"], "Item 2: {{facts_2}}. Make attempt 1: {{offer_2_1}}.")
        self.assertEqual(step["extraction_schema"][0]["name"], "no_2_1")
        self.assertEqual([t["target_node"] for t in step["transitions"]], ["offer_2_2", "offer_item_3", "offer_item_3", "offer_2_1"])
        self.assertEqual(wf["nodes"]["offer_3_2"]["transitions"][0]["target_node"], "wrap")
        self.assertEqual(wf["nodes"]["talk"]["transitions"][0]["target_node"], "offer_item_1")
        self.assertEqual(step["max_turn_transition"], "close_no_busy")

    def test_ladder_mistakes_are_rejected(self):
        bad = {**LADDER, "refusal": "no_{i}", "attempts": {**LADDER["attempts"], "allowed": "tries"}}
        found = problems(LADDER_BODY, {**PLAN, "ladder": bad})
        self.assertIn("refusal must contain {i} and {a}", found)
        self.assertIn("attempts.allowed must contain {i}", found)
        self.assertIn("item:next and item:first need a ladder", problems(LADDER_BODY, PLAN))


CANDIDATE_A = ROOT / "runs" / "20261010-161811-candidate-ab" / "out" / "brief-a.workflow.json"


@unittest.skipUnless(CANDIDATE_A.exists(), "candidate run not present")
class ReproducesMeasuredWorkflowTest(unittest.TestCase):
    """The closing of the best measured A workflow (agent 6a9597ac, 10/10 and every customer 3/3) is what the
    lowering writes from a 16-entry plan. The plan is read back from that workflow here; a model writing it is untested."""

    def test_lowering_rebuilds_the_preserved_workflow(self):
        kit = ROOT / "docs" / "build-the-builder"
        api = json.loads((kit / "tools" / "openapi.json").read_text())
        ops = load_operations(api)
        original = json.loads(CANDIDATE_A.read_text())
        body = copy.deepcopy(original)
        ids, closings = {}, {}
        brief = (kit / "briefs" / "brief-a.md").read_text().splitlines()
        for key, node in original["nodes"].items():
            pre = [t for t in node.get("pre_actions") or [] if tool_operation(t, ops) == "close_call"]
            if pre or node.get("node_type") == "end_call":
                del body["nodes"][key]
            if pre:
                sent = pre[0]["function"]["parameters"]["properties"]["body"]["properties"]
                values = {f: sent[f]["default"] for f in ("outcome", "reason") if f in sent}
                cid = "/".join(values.values())
                quote = next(l.strip() for l in brief if all(f"`{v}`" in l for v in values.values()))
                ids[key], closings[cid] = cid, {"set": values, "evidence": [{"source": "briefs/brief-a.md", "quote": quote}]}
        text = json.dumps(body)
        for key, cid in ids.items():
            text = text.replace(f'"{key}"', f'"{SYMBOL}{cid}"')
        plan = {"terminal": {"tool": "close_call", "evidence": [{"source": "tools/openapi.json", "quote": "Always the last tool call."}]},
                "fields": {"customer_id": "{{customer_id}}"}, "closings": closings}
        lowered, contract = lower(json.loads(text), plan, api, kit)
        expected = json.dumps(original)
        for key, cid in ids.items():
            expected = expected.replace(f'"{key}"', f'"{step_name(cid)}"')
        self.assertEqual(json.loads(expected)["nodes"], lowered["nodes"])
        self.assertEqual([f for f in check(lowered, api, contract, kit) if f.level == "error"], [])


if __name__ == "__main__":
    unittest.main()
