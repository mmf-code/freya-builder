import json
import tempfile
import unittest
from pathlib import Path

from builder.kitrun import ROOT, load_env, resolve_env, redact, render_trace, scrub, secrets_of, summarize_trace

BASELINE = ROOT / "runs" / "20261010-kit-builder-brief-a" / "trace.sanitized.jsonl"


class EnvTest(unittest.TestCase):
    def test_parses_export_lines_quotes_and_comments(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "env.sh"
            f.write_text('export FREYA_API_KEY=fak_abcdefgh12345   # from the dashboard\n'
                         "export FREYA_API_URL='https://example.test'\n# a comment\n\nPLAIN_TOKEN=\"tok_123456789\"\n")
            env = load_env(f)
        self.assertEqual(env, {"FREYA_API_KEY": "fak_abcdefgh12345", "FREYA_API_URL": "https://example.test", "PLAIN_TOKEN": "tok_123456789"})
        self.assertEqual(set(secrets_of(env)), {"FREYA_API_KEY", "PLAIN_TOKEN"})

    def test_resolve_env_uses_environment_without_env_file(self):
        with tempfile.TemporaryDirectory() as d:
            env = resolve_env(Path(d) / "env.sh", {"FREYA_API_KEY": "fak_fromenv12345", "PATH": "/bin"})
        self.assertEqual(env, {"FREYA_API_KEY": "fak_fromenv12345"})

    def test_resolve_env_prefers_env_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "env.sh"
            f.write_text("export FREYA_API_KEY=fak_fromfile12345\n")
            env = resolve_env(f, {"FREYA_API_KEY": "fak_fromenv12345", "FREYA_BANK_TEAM_KEY": "team_fromenv12345"})
        self.assertEqual(env, {"FREYA_API_KEY": "fak_fromfile12345", "FREYA_BANK_TEAM_KEY": "team_fromenv12345"})

    def test_scrub_redacts_outputs_but_not_the_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir, ws = Path(d), Path(d) / "workspace"
            (run_dir / "out").mkdir(parents=True)
            ws.mkdir()
            (run_dir / "out" / "a.workflow.json").write_text('{"h": "fak_abcdefgh12345"}')
            (run_dir / "clean.txt").write_text("nothing here")
            (ws / "raw.jsonl").write_text("fak_abcdefgh12345")
            leaks = scrub(run_dir, ws, {"FREYA_API_KEY": "fak_abcdefgh12345"})
            self.assertEqual(leaks, ["out/a.workflow.json"])
            self.assertEqual((run_dir / "out" / "a.workflow.json").read_text(), '{"h": "<redacted:FREYA_API_KEY>"}')
            self.assertEqual((ws / "raw.jsonl").read_text(), "fak_abcdefgh12345")

    def test_redact_removes_secret_values_and_repo_path(self):
        text = redact(f"key fak_abcdefgh12345 at {ROOT}/runs/x", {"FREYA_API_KEY": "fak_abcdefgh12345"})
        self.assertEqual(text, "key <redacted:FREYA_API_KEY> at <repo>/runs/x")


@unittest.skipUnless(BASELINE.exists(), "baseline run not present")
class BaselineTraceTest(unittest.TestCase):
    """The preserved kit-builder run on Brief A: 5/10, one fix, then 10/10, $1.60."""

    @classmethod
    def setUpClass(cls):
        records = [json.loads(l) for l in BASELINE.read_text().splitlines()]
        cls.s = summarize_trace(records)

    def test_finds_both_practice_runs(self):
        self.assertEqual([(t["passed"], t["total"]) for t in self.s["tests"]], [(5, 10), (10, 10)])
        self.assertTrue(all(t["simulation_id"] for t in self.s["tests"]))
        self.assertEqual(len(self.s["tests"][0]["fail_lines"]), 5)

    def test_finds_saves_and_written_files(self):
        self.assertEqual({s["workflow_id"][:8] for s in self.s["saves"]}, {"cc703d9f"})
        self.assertIn("/tmp/brief_a_gen/gen.py", self.s["written"])

    def test_every_model_call_has_model_and_purpose(self):
        self.assertEqual(len(self.s["model_calls"]), 19)
        for c in self.s["model_calls"]:
            self.assertEqual(c["model"], "claude-opus-5-5")
            self.assertTrue(c["purpose"])
        self.assertAlmostEqual(self.s["result"]["total_cost_usd"], 1.60, places=2)

    def test_rendered_trace_lists_hidden_helper_model(self):
        info = {"run": "x", "start": "s", "end": "e", "seconds": 1, "limit_minutes": 30, "timed_out": False, "exit_code": 0,
                "builder": "b", "builder_model": "m", "agent_model": {"provider": "p", "model": "q"}, "repo_commit": "c", "repo_dirty": False,
                "inputs": {"briefs": [{"name": "brief-a.md", "sha256": "0" * 64}], "tools": {"name": "openapi.json", "sha256": "1" * 64}},
                "freya": [], "tests": self.s["tests"], "written": self.s["written"], "cost_usd": 1.6, "num_turns": 23,
                "model_usage": self.s["result"]["model_usage"], "model_calls": self.s["model_calls"]}
        text = render_trace(info)
        self.assertIn("claude-haiku-5-5", text)
        self.assertIn("not in the message log", text)
        self.assertIn("10 / 10 passed", text)


if __name__ == "__main__":
    unittest.main()


class CandidateSkillTest(unittest.TestCase):
    def test_skill_overlay_and_checker_in_workspace_only(self):
        from builder.kitrun import KIT, make_workspace
        kit_skill = KIT / ".claude" / "skills" / "build-phone-agent" / "SKILL.md"
        before = kit_skill.read_text()
        with tempfile.TemporaryDirectory() as d:
            skill = Path(d) / "skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: build-phone-agent\n---\ncandidate")
            ws = make_workspace(Path(d) / "run", [KIT / "briefs" / "brief-a.md"], KIT / "tools" / "openapi.json", skill)
            self.assertEqual((ws / ".claude" / "skills" / "build-phone-agent" / "SKILL.md").read_text().splitlines()[-1], "candidate")
            self.assertTrue((ws / "tools" / "check_workflow.py").is_file())
            self.assertEqual(sorted(p.name for p in (ws / "briefs").iterdir()), ["brief-a.md"])
        self.assertEqual(kit_skill.read_text(), before)

    @unittest.skipUnless((ROOT / "runs" / "20261010-154045-kit-ab" / "brief-b.workflow.json").exists(), "A+B run not present")
    def test_check_exports_reports_the_shared_terminal_step(self):
        import shutil
        from builder.kitrun import KIT, check_exports
        with tempfile.TemporaryDirectory() as d:
            run_dir, ws = Path(d), Path(d) / "workspace"
            (ws / "tools").mkdir(parents=True)
            (ws / "out").mkdir()
            shutil.copy2(KIT / "tools" / "openapi.json", ws / "tools" / "openapi.json")
            shutil.copy2(ROOT / "runs" / "20261010-154045-kit-ab" / "brief-b.workflow.json", run_dir / "brief-b.workflow.json")
            self.assertEqual(check_exports(run_dir, ws, [{"slot": "brief-b"}])[0]["errors"], [])   # no contract: ordering not checked
            (ws / "out" / "brief-b.contract.json").write_text(json.dumps({"terminal_tools": [{"tool": "close_call", "evidence": [
                {"source": "tools/openapi.json", "quote": "Always the last tool call."}]}]}))
            errors = check_exports(run_dir, ws, [{"slot": "brief-b"}])[0]["errors"]
            self.assertTrue(any("E-TERMINAL-SHARED" in e and "negotiate" in e for e in errors))


class FailClosedTest(unittest.TestCase):
    def test_nothing_saved_missing_export_and_missing_contract_are_errors(self):
        import shutil
        from builder.kitrun import KIT, check_exports
        with tempfile.TemporaryDirectory() as d:
            run_dir, ws = Path(d), Path(d) / "workspace"
            (ws / "tools").mkdir(parents=True)
            (ws / "out").mkdir()
            shutil.copy2(KIT / "tools" / "openapi.json", ws / "tools" / "openapi.json")
            self.assertTrue(check_exports(run_dir, ws, [])[0]["errors"])
            self.assertTrue(check_exports(run_dir, ws, [{"slot": "x"}])[0]["errors"])
            (run_dir / "x.workflow.json").write_text(json.dumps({"workflow": {"initial_node": "e", "nodes": {"e": {"node_type": "end_call", "transitions": []}}}}))
            self.assertEqual(check_exports(run_dir, ws, [{"slot": "x"}])[0]["errors"], [])
            self.assertTrue(any("missing" in e for e in check_exports(run_dir, ws, [{"slot": "x"}], contract_required=True)[0]["errors"]))
            (ws / "out" / "x.contract.json").write_text("{not json")
            self.assertTrue(any("not valid JSON" in e for e in check_exports(run_dir, ws, [{"slot": "x"}])[0]["errors"]))


class PracticeCasesTest(unittest.TestCase):
    """A build sees practice customers only for kit briefs identical to its inputs."""

    def test_selection_follows_brief_identity(self):
        from builder.kitrun import KIT, practice_cases
        a, b = KIT / "briefs" / "brief-a.md", KIT / "briefs" / "brief-b.md"
        self.assertEqual({c["brief"] for c in practice_cases([a])}, {"A"})
        self.assertEqual({c["brief"] for c in practice_cases([a, b])}, {"A", "B"})
        with tempfile.TemporaryDirectory() as d:
            changed = Path(d) / "brief-a.md"                      # same name, one byte different: an unknown brief
            changed.write_text(a.read_text() + "\n")
            self.assertEqual(practice_cases([changed]), [])

    def test_workspace_holds_only_the_selected_customers(self):
        from builder.kitrun import KIT, make_workspace
        with tempfile.TemporaryDirectory() as d:
            hidden = Path(d) / "brief-x.md"
            hidden.write_text("# Another bank\n")
            ws = make_workspace(Path(d) / "run", [hidden], KIT / "tools" / "openapi.json")
            self.assertEqual(json.loads((ws / "public-test-set.json").read_text()), [])
            ws2 = make_workspace(Path(d) / "run2", [KIT / "briefs" / "brief-a.md"], KIT / "tools" / "openapi.json")
            self.assertEqual({c["brief"] for c in json.loads((ws2 / "public-test-set.json").read_text())}, {"A"})


class LoweringWorkspaceTest(unittest.TestCase):
    """The builder's workspace runs tools/lower.py on a plan quoted from the brief, and kitrun can tell lowered endings
    from hand-written ones."""

    PLAN = {"terminal": {"tool": "close_call", "evidence": [{"source": "tools/openapi.json", "quote": "Always the last tool call."}]},
            "fields": {"customer_id": "{{customer_id}}"},
            "closings": {
                "promise": {"set": {"outcome": "promise"}, "evidence": [{"source": "briefs/brief-a.md", "quote": "| `promise` | none | at least one promise was recorded |"}]},
                "no_promise/service_error": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                             "say": "I could not record your promise. Goodbye.",
                                             "evidence": [{"source": "briefs/brief-a.md", "quote": "close as `no_promise` / `service_error`"}]},
                "account_unavailable": {"set": {"outcome": "no_promise", "reason": "service_error"},
                                        "say": "I cannot reach the account details right now. Goodbye.",
                                        "evidence": [{"source": "briefs/brief-a.md", "quote": "close as `no_promise` / `service_error`"}]}}}
    BODY = {"initial_node": "talk", "nodes": {"talk": {
        "node_type": "conversation", "tools": [], "max_node_turns": 30, "max_turn_transition": "close:no_promise/service_error",
        "transitions": [{"target_node": "close:promise", "description": "A promise was recorded", "is_tool_call": True,
                         "condition": {"operator": "matches_intent", "description": "A promise was recorded"}},
                        {"target_node": "close:account_unavailable", "description": "account error",
                         "condition": {"logic": "or", "conditions": [{"variable": "account_state", "operator": "equals", "operand": "error"}]}}]}}}

    def workspace(self, d):
        from builder.kitrun import KIT, make_workspace
        skill = Path(d) / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: build-phone-agent\n---\nx")
        ws = make_workspace(Path(d) / "run", [KIT / "briefs" / "brief-a.md"], KIT / "tools" / "openapi.json", skill, Path(d) / "state")
        (ws / "out").mkdir()
        (ws / "out" / "brief-a.closing.json").write_text(json.dumps(self.PLAN))
        return ws

    def lower(self, ws, body):
        import subprocess
        (ws / "out" / "brief-a.body.json").write_text(json.dumps(body))
        return subprocess.run(["python3", "tools/lower.py", "out/brief-a.body.json", "out/brief-a.closing.json", "--tools", "tools/openapi.json",
                               "-o", "out/brief-a.workflow.json", "--contract", "out/brief-a.contract.json"], cwd=ws, capture_output=True, text=True)

    def test_plan_from_the_brief_becomes_the_endings_of_the_saved_workflow(self):
        import subprocess
        from builder.kitrun import check_exports
        with tempfile.TemporaryDirectory() as d:
            ws = self.workspace(d)
            done = self.lower(ws, self.BODY)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            wf = json.loads((ws / "out" / "brief-a.workflow.json").read_text())
            self.assertEqual(sorted(k for k in wf["nodes"] if k != "talk"),
                             ["close_account_unavailable", "close_no_promise_service_error", "close_promise", "hang_up"])
            talk = wf["nodes"]["talk"]
            self.assertEqual([t["target_node"] for t in talk["transitions"]], ["close_promise", "close_account_unavailable"])
            self.assertEqual(talk["max_turn_transition"], "close_no_promise_service_error")
            check = subprocess.run(["python3", "tools/check_workflow.py", "out/brief-a.workflow.json", "--tools", "tools/openapi.json",
                                    "--contract", "out/brief-a.contract.json"], cwd=ws, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout)
            run_dir = Path(d) / "run"
            (run_dir / "brief-a.workflow.json").write_text(json.dumps({"workflow": wf}))
            entry = check_exports(run_dir, ws, [{"slot": "brief-a"}], contract_required=True)[0]
            self.assertEqual(entry["errors"], [])
            self.assertTrue(entry["lowering"].startswith("matches"), entry["lowering"])
            wf["nodes"]["close_promise"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]["outcome"]["default"] = "paid"
            (run_dir / "brief-a.workflow.json").write_text(json.dumps({"workflow": wf}))
            self.assertIn("values differ", check_exports(run_dir, ws, [{"slot": "brief-a"}], contract_required=True)[0]["lowering"])

    def test_hand_written_terminal_tool_is_rejected(self):
        from builder.workflow_check import load_operations
        with tempfile.TemporaryDirectory() as d:
            ws = self.workspace(d)
            op = load_operations(json.loads((ws / "tools" / "openapi.json").read_text()))["close_call"]
            body = json.loads(json.dumps(self.BODY))
            body["nodes"]["talk"]["tools"] = [{"type": "function", "function": {"name": "close_call", "handler": "__function__:api_call", "parameters": {
                "type": "object", "properties": {"url": {"type": "string", "default": op["servers"][0] + op["path"]}, "method": {"type": "string", "default": "POST"}}}}}]
            done = self.lower(ws, body)
            self.assertEqual(done.returncode, 1)
            self.assertIn("REJECTED step 'talk' offers or runs the terminal tool close_call", done.stdout)
            self.assertFalse((ws / "out" / "brief-a.workflow.json").exists())
