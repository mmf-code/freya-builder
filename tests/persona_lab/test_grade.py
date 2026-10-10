"""The export grader discriminates: a stale export fails the mutated contract, an adapted one passes.

This proves the grader. Whether the Builder adapts is measured by test_fresh_exports.py on real fresh builds.
"""
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from builder import workflow_check as wc
from tools.persona_lab import blind, grade
from tools.persona_lab.common import ROOT

OLD_A = ROOT / "runs" / "20261010-154045-kit-ab" / "brief-a.workflow.json"
OLD_B = ROOT / "runs" / "20261010-154045-kit-ab" / "brief-b.workflow.json"


def adapt(export: dict, openapi: dict, ops: list[dict], enum_map: dict) -> dict:
    """What a Builder that read the new contract would send: the scripted rewrite of an old export."""
    export = copy.deepcopy(export)
    wf = export.get("workflow", export)
    tools = wc.load_operations(openapi)
    for node in {**(wf.get("nodes") or {}), **(wf.get("global_nodes") or {})}.values():
        for t in [*(node.get("tools") or []), *(node.get("pre_actions") or [])]:
            op = wc.tool_operation(t, tools) if isinstance(t, dict) else None
            if not op:
                continue
            body = t["function"]["parameters"]["properties"].setdefault("body", {"type": "object", "properties": {}})
            props, req = body.setdefault("properties", {}), body.setdefault("required", [])
            for o in ops:
                if o["path"].strip("/") != op:
                    continue
                if o["op"] == "rename_field" and o["old"] in props:
                    props[o["new"]] = props.pop(o["old"])
                    body["required"] = [o["new"] if r == o["old"] else r for r in req]
                elif o["op"] == "add_field":
                    props[o["field"]] = {**o["schema"], "default": o["schema"]["enum"][0]}
                    body.setdefault("required", []).append(o["field"])
                elif o["op"] == "set_enum" and o["field"] in props:
                    spec = props[o["field"]]
                    if "enum" in spec:
                        spec["enum"] = [enum_map.get(v, v) for v in spec["enum"] if enum_map.get(v, v) in o["values"]]
                    if spec.get("default") in enum_map:
                        spec["default"] = enum_map[spec["default"]]
    text = json.dumps(export)
    for old, new in enum_map.items():
        text = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, text)
    return json.loads(text)


class GraderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        blind.build(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def scenario(self, name):
        d = self.out / name
        return json.loads((d / "key.json").read_text()), json.loads((d / "inputs" / "openapi.json").read_text())

    def test_stale_export_fails_renamed_contract(self):
        key, api = self.scenario("g6-contract-clean")
        r = grade.grade(json.loads(OLD_A.read_text()), key, api)
        self.assertFalse(r["contract"]["pass"])
        self.assertTrue(any(s.endswith("create_promise.date") for s in r["contract"]["stale_fields"]))
        self.assertTrue(any("queue=support" in s for s in r["contract"]["stale_enum"]))

    def test_adapted_export_passes_renamed_contract(self):
        key, api = self.scenario("g6-contract-clean")
        scn = next(s for s in blind.SCENARIOS if s["id"] == "g6-contract")
        new = adapt(json.loads(OLD_A.read_text()), api, scn["openapi"], {"support": "customer_support"})
        r = grade.grade(new, key, api)
        self.assertTrue(r["contract"]["pass"], grade.render(r))
        self.assertEqual(r["evidence"][0]["status"], "FOUND")

    def test_stale_and_adapted_outcome_enums(self):
        key, api = self.scenario("g4-outcomes-clean")
        old = json.loads(OLD_A.read_text())
        self.assertIn("outcome-not-reached", grade.grade(old, key, api)["strong_stale"])
        scn = next(s for s in blind.SCENARIOS if s["id"] == "g4-outcomes")
        new = adapt(old, api, scn["openapi"], {"not_reached": "no_contact", "not_verified": "identity_failed"})
        r = grade.grade(new, key, api)
        self.assertTrue(r["contract"]["pass"], grade.render(r))
        self.assertEqual(r["strong_stale"], [])

    def test_note_enum_rename_on_multi_product_export(self):
        key, api = self.scenario("g7-multi-clean")
        old = json.loads(OLD_B.read_text())
        self.assertFalse(grade.grade(old, key, api)["contract"]["pass"])
        scn = next(s for s in blind.SCENARIOS if s["id"] == "g7-multi")
        new = adapt(old, api, scn["openapi"], {"paid": "already_paid"})
        # the outcome `paid` of close_call is a different enum; the blanket rewrite breaks it, which the grader sees
        self.assertFalse(grade.grade(new, key, api)["contract"]["pass"])

    def test_unchanged_contract_passes_old_export(self):
        key, api = self.scenario("g1-calendar-clean")       # policy-only scenario, public contract
        r = grade.grade(json.loads(OLD_A.read_text()), key, api)
        self.assertTrue(r["contract"]["pass"], grade.render(r))
        self.assertIn("holiday-removed", r["strong_stale"])  # but the old export still knows the old calendar

    def test_add_note_required_only_for_multi_product(self):
        key, _ = self.scenario("g1-calendar-clean")
        self.assertNotIn("add_note", key["required_tools"])
        key, _ = self.scenario("g7-multi-clean")
        self.assertIn("add_note", key["required_tools"])

    def test_evidence_statuses(self):
        key = {"probes": [blind.found("f", ["alpha"], "x"), blind.stale("s", ["beta"], "y")], "stale_api": {}}
        wf = {"nodes": {"n": {"prompt": "Alpha and BETA"}}, "initial_node": "n"}
        r = grade.grade({"workflow": wf}, key, {"paths": {}})
        self.assertEqual([e["status"] for e in r["evidence"]], ["FOUND", "STALE"])
        self.assertEqual(r["strong_stale"], ["s"])

    def test_leak_ignores_terms_the_brief_itself_contains(self):
        wf = {"nodes": {"n": {"prompt": "Ask for Daniel Reyes. Case PUB-06: 637.50"}}, "initial_node": "n"}
        r = grade.grade({"workflow": wf}, {"probes": []}, {"paths": {}}, brief_text="Example: Daniel Reyes")
        self.assertNotIn("daniel reyes", r["leak"])
        self.assertIn("pub-06", r["leak"])
        self.assertIn("637.50", r["leak"])


if __name__ == "__main__":
    unittest.main()
