"""Blind scenarios: edits apply, both forms carry the right values, no practice customers leak into a build."""
import json
import tempfile
import unittest
from pathlib import Path

from builder import kitrun
from tools.persona_lab import blind
from tools.persona_lab.common import KIT, sha256


class BlindBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.index = blind.build(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_scenario_has_both_forms(self):
        dirs = {i["dir"] for i in self.index}
        for s in blind.SCENARIOS:
            self.assertIn(f"{s['id']}-clean", dirs)
            self.assertIn(f"{s['id']}-raw", dirs)

    def test_inputs_expose_no_practice_customers(self):
        for i in self.index:
            briefs = sorted((self.out / i["dir"] / "inputs").glob("*.md"))
            with self.subTest(i["dir"]):
                self.assertTrue(briefs)
                self.assertEqual(kitrun.practice_cases(briefs), [])

    def test_input_names_do_not_take_kit_slots(self):
        # kitrun slots are brief file names; brief-a.md would overwrite the main session's agent
        for i in self.index:
            for p in (self.out / i["dir"] / "inputs").glob("*.md"):
                self.assertTrue(p.name.startswith("pl-"), p)

    def test_key_is_not_an_input(self):
        for i in self.index:
            names = {p.name for p in (self.out / i["dir"] / "inputs").iterdir()}
            self.assertNotIn("key.json", names)
            text = "\n".join(p.read_text() for p in (self.out / i["dir"] / "inputs").glob("*.md"))
            self.assertNotIn("probe", text.lower())

    def test_clean_form_is_the_edited_public_brief(self):
        public = blind.public_briefs()
        for s in blind.SCENARIOS:
            edited = blind.apply_edits(public, s["edits"])
            for doc in s["docs"]:
                text = (self.out / f"{s['id']}-clean" / "inputs" / f"pl-{s['id']}-clean-{doc}.md").read_text()
                with self.subTest(s["id"], doc=doc):
                    self.assertEqual(text, edited[doc])
                    if any(e["doc"] == doc for e in s["edits"]):
                        self.assertNotEqual(text, public[doc])

    def test_raw_form_keeps_old_text_and_announces_memo_edits(self):
        for s in blind.SCENARIOS:
            text = (self.out / f"{s['id']}-raw" / "inputs" / f"pl-{s['id']}-raw.md").read_text()
            self.assertIn("Operations memo OM-17", text)
            self.assertIn("Close code list", text)
            for e in s["edits"]:
                if e["via"] == "memo" and e["memo"]:
                    with self.subTest(s["id"], memo=e["memo"][:40]):
                        self.assertIn(e["memo"], text)

    def test_memo_precedence_scenario_has_both_superseded_values(self):
        text = (self.out / "g5-memo-raw" / "inputs" / "pl-g5-memo-raw.md").read_text()
        self.assertIn("10:00 to 19:00", text)      # the extract, superseded by the newer memo
        self.assertIn("until 20:00", text)         # the older memo, superseded by the extract
        self.assertIn("09:00 to 17:00", text)      # what applies

    def test_openapi_mutations_and_stale_record(self):
        key = json.loads((self.out / "g6-contract-clean" / "key.json").read_text())
        api = json.loads((self.out / "g6-contract-clean" / "inputs" / "openapi.json").read_text())
        promise = api["paths"]["/create_promise"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertIn("promise_date", promise["properties"])
        self.assertNotIn("date", promise["properties"])
        self.assertIn("channel", promise["required"])
        self.assertEqual(sorted(key["stale_api"]["create_promise"]["fields"]), ["amount", "date"])
        self.assertEqual(key["stale_api"]["transfer_to_agent"]["enum"], {"queue": ["support"]})
        self.assertEqual(sorted(api["paths"]), sorted(blind.public_openapi()["paths"]))   # the seven tool names stay

    def test_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory() as t:
            again = blind.build(Path(t))
            for i in again:
                for p in (Path(t) / i["dir"]).rglob("*"):
                    if not p.is_file():
                        continue
                    q = self.out / i["dir"] / p.relative_to(Path(t) / i["dir"])
                    if p.name == "key.json":          # its build command names the output directory
                        a, b = json.loads(p.read_text()), json.loads(q.read_text())
                        a.pop("build"), b.pop("build")
                        self.assertEqual(a, b, p)
                    else:
                        self.assertEqual(sha256(p.read_bytes()), sha256(q.read_bytes()), p)

    def test_anchor_must_exist_once(self):
        with self.assertRaises(ValueError):
            blind.apply_edits({"a": "x y x"}, [blind.E("a", "x", "z")])
        with self.assertRaises(ValueError):
            blind.apply_edits({"a": "x"}, [blind.E("a", "missing", "z")])

    def test_public_briefs_untouched(self):
        self.assertEqual(blind.public_briefs()["a"], (KIT / "briefs" / "brief-a.md").read_text())


if __name__ == "__main__":
    unittest.main()
