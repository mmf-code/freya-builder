"""Does a fresh Builder output adapt to the changed contract and policy?

Runs on every blind build on disk: kitrun runs labelled `pl-<scenario>` (see tools/persona_lab/README.md) and files
in tools/persona_lab/results/blind/<scenario>/. Skips when there is none. Offline: contract and text evidence only,
no ledger score.
"""
import unittest

from tools.persona_lab import grade


class FreshExportTest(unittest.TestCase):
    def test_fresh_exports_follow_the_new_contract(self):
        found = grade.fresh_exports()
        if not found:
            self.skipTest("no blind build yet: run kitrun on tools/persona_lab/generated/blind/<scenario>/inputs")
        for export, scn in found:
            with self.subTest(export=str(export)):
                r = grade.grade_paths(export, scn)
                self.assertTrue(r["contract"]["pass"], grade.render(r))
                self.assertEqual(r["strong_stale"], [], grade.render(r))
                self.assertEqual(r["leak"], [], grade.render(r))


if __name__ == "__main__":
    unittest.main()
