"""Snapshot of extractor output per synthetic brief.

Lexicon changes (for example after the official brief arrives) show up here
as a readable structural diff. To accept new output after reviewing it:

    UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden
"""
import json
import os
import unittest
from pathlib import Path

from builder.extract import extract
from builder.ingest import load_brief
from builder.jsondiff import diff, format_report

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = sorted((ROOT / "briefs" / "synthetic").glob("*.*"))
GOLDEN = Path(__file__).resolve().parent / "golden"


class GoldenTest(unittest.TestCase):
    def test_extraction_matches_golden(self):
        for path in BRIEFS:
            with self.subTest(brief=path.name):
                actual = [r.to_dict() for r in extract(load_brief(path))]
                golden = GOLDEN / f"{path.stem}.requirements.json"
                if os.environ.get("UPDATE_GOLDEN"):
                    golden.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    continue
                self.assertTrue(golden.exists(), f"missing {golden.name}; run with UPDATE_GOLDEN=1")
                changes = diff(json.loads(golden.read_text(encoding="utf-8")), actual, id_keys=("id",))
                self.assertEqual(changes, [], "\n" + format_report(changes, title=path.name))


if __name__ == "__main__":
    unittest.main()
