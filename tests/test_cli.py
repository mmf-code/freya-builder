import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from builder.__main__ import main

ROOT = Path(__file__).resolve().parent.parent
BANKING = str(ROOT / "briefs" / "synthetic" / "banking_lost_card.md")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue()


class CliTest(unittest.TestCase):
    def test_extract_then_validate_requirements_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "reqs.json"
            self.assertEqual(run("extract", BANKING, "-o", str(out))[0], 0)
            self.assertTrue(json.loads(out.read_text()))
            code, text = run("validate", BANKING, "-r", str(out))
            self.assertEqual(code, 0, text)

    def test_validate_exits_1_on_errors(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "reqs.json"
            bad.write_text(json.dumps([{"id": "X", "modality": "must", "statement": "s", "source": {"doc": "nope.md", "locator": "L1", "quote": "s"}}]))
            code, text = run("validate", BANKING, "-r", str(bad))
            self.assertEqual(code, 1)
            self.assertIn("E-TRACE-DOC", text)

    def test_diff_and_shape(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.json", Path(d) / "b.json"
            a.write_text(json.dumps({"nodes": [{"id": "n1", "v": 1}]}))
            b.write_text(json.dumps({"nodes": [{"id": "n1", "v": 2}]}))
            self.assertEqual(run("diff", str(a), str(a))[0], 0)
            code, text = run("diff", str(a), str(b), "--json")
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(text)["summary"], {"changed": 1})
            self.assertEqual(run("diff", str(a), str(b), "--structural-only")[0], 0)
            self.assertIn("$.nodes[*].v\tnumber", run("shape", str(a))[1])


if __name__ == "__main__":
    unittest.main()
