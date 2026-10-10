"""Persona specs compile into fair, frozen, kit-compatible personas; unfair specs are refused."""
import copy
import tempfile
import unittest
from pathlib import Path

from tools.persona_lab import personas, runner
from tools.persona_lab.common import load_cases


def spec(**kw):
    s = {"id": "T1", "layer": "official", "base_case": "PUB-07", "rank": 1, "seed": 1, "families": ["x"],
         "hypothesis": "h", "proves": "p", "does_not_prove": "n", "expected_agent": ["e"],
         "conditions": {"c": "the caller asks for the exact day"},
         "acts": [{"id": "a", "use": "distractor", "max": 1, "args": {"text": "that your cousin's wedding is on the 30th"}}],
         "rules": [{"when": ["c"], "acts": ["a"], "priority": 1}], "escalation": [], "ordering": [],
         "distractors": [{"value": "30", "role": "irrelevant"}]}
    s.update(kw)
    return s


class CompileTest(unittest.TestCase):
    def setUp(self):
        self.cases = load_cases()

    def test_all_shipped_variants_are_valid(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(personas.compile_all(Path(t))["problems"], {})

    def test_frozen_fields_equal_base_and_block_follows_kit_rules(self):
        for s in personas.load_specs():
            case, rendered, errs = personas.compile_spec(s, self.cases)
            with self.subTest(s["id"]):
                self.assertEqual(errs, [])
                self.assertEqual(personas.frozen_part(case), personas.frozen_part(self.cases[s["base_case"]]))
                prompt = rendered["persona"]["prompt"]
                self.assertGreater(prompt.index("HOW YOU BEHAVE"), prompt.index("RULES:"))
                self.assertTrue(rendered["meta"]["persona_key"].startswith(s["base_case"] + ":"))
                self.assertEqual(rendered["meta"]["ledger_scored"], s["layer"] == "official")

    def test_compilation_is_deterministic(self):
        s = personas.load_specs()[0]
        a = personas.compile_spec(s, self.cases)[1]["meta"]
        b = personas.compile_spec(copy.deepcopy(s), self.cases)[1]["meta"]
        self.assertEqual(a, b)

    def test_valid_spec(self):
        self.assertEqual(personas.compile_spec(spec(), self.cases)[2], [])

    def test_undeclared_number_is_refused(self):
        errs = personas.compile_spec(spec(distractors=[]), self.cases)[2]
        self.assertTrue(any("number 30" in e for e in errs), errs)

    def test_distractor_equal_to_a_fact_is_refused(self):
        s = spec(distractors=[{"value": "540", "role": "irrelevant"}])
        s["acts"][0]["args"]["text"] = "that the rent is 540"
        self.assertTrue(any("distractor 540 equals a fact" in e for e in personas.compile_spec(s, self.cases)[2]))

    def test_correcting_a_security_answer_is_refused(self):
        s = spec(acts=[{"id": "a", "use": "self_correct", "max": 1, "args": {"what": "your date of birth", "wrong": "x", "wrong_said": "x", "right_said": "y"}}])
        self.assertTrue(any("security answer" in e for e in personas.compile_spec(s, self.cases)[2]))

    def test_lint(self):
        s = spec(ordering=[{"before": "a", "after": "b"}, {"before": "b", "after": "a"}],
                 acts=[{"id": "a", "use": "distractor", "max": 0, "args": {"text": "x"}}, {"id": "b", "use": "nope", "args": {}}],
                 rules=[{"when": ["missing"], "acts": ["a"]}])
        errs = personas.lint(s)
        for needle in ("max must be at least 1", "unknown act type nope", "unknown condition missing", "b: no rule", "cycle"):
            self.assertTrue(any(needle in e for e in errs), (needle, errs))


class BatchTest(unittest.TestCase):
    def test_one_variant_per_case_and_one_brief_per_simulation(self):
        manifest = {
            "V1": {"rank": 1, "brief": "A", "base_case": "PUB-01"}, "V2": {"rank": 2, "brief": "A", "base_case": "PUB-01"},
            "V3": {"rank": 3, "brief": "B", "base_case": "PUB-12"}, "V4": {"rank": 4, "brief": "A", "base_case": "PUB-07"}}
        b = runner.batches(manifest, list(manifest))
        self.assertEqual(b, [{"brief": "A", "variants": ["V1", "V4"]}, {"brief": "A", "variants": ["V2"]}, {"brief": "B", "variants": ["V3"]}])


if __name__ == "__main__":
    unittest.main()
