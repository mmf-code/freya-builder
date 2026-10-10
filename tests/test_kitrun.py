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
