"""Invariants over every brief in briefs/synthetic/.

These must hold for any brief, so new briefs (including the official one,
once it is copied into a test location) can be added without new test code.
"""
import json
import re
import unittest
from pathlib import Path

from builder import extract as extract_module
from builder import lexicon as lexicon_module
from builder.extract import extract
from builder.ingest import ingest_json, ingest_text, load_brief
from builder.model import dump_requirements, load_requirements
from builder.validate import validate

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = sorted((ROOT / "briefs" / "synthetic").glob("*.*"))


class PerBriefInvariantsTest(unittest.TestCase):
    def test_there_are_briefs(self):
        self.assertGreaterEqual(len(BRIEFS), 3)

    def test_invariants(self):
        for path in BRIEFS:
            with self.subTest(brief=path.name):
                brief = load_brief(path)
                reqs = extract(brief)
                self.assertTrue(reqs)

                # Deterministic.
                self.assertEqual([r.to_dict() for r in extract(load_brief(path))], [r.to_dict() for r in reqs])

                # Unique ids.
                self.assertEqual(len({r.id for r in reqs}), len(reqs))

                # Lossless serialization.
                self.assertEqual(load_requirements(dump_requirements(reqs)), reqs)

                # Traceable and complete: no errors, no uncovered normative sentence.
                findings = validate(reqs, [brief])
                self.assertEqual([f for f in findings if f.level != "info"], [])

                # Every requirement quotes the brief verbatim (whitespace-normalized).
                raw = " ".join(brief.raw.split())
                for r in reqs:
                    if brief.format != "json":
                        self.assertIn(" ".join(r.source.quote.split()), raw, r.id)


class GeneralizationTest(unittest.TestCase):
    """Each synthetic domain exercises every part of the IR."""

    def test_each_brief_fills_every_field_kind(self):
        for path in BRIEFS:
            with self.subTest(brief=path.name):
                reqs = extract(load_brief(path))
                for field in ("preconditions", "required_actions", "allowed_actions", "forbidden_actions", "counters", "terminations"):
                    self.assertTrue(any(getattr(r, field) for r in reqs), f"{path.name}: no {field}")

    def test_extractor_has_no_domain_vocabulary(self):
        domain = re.compile(r"\b(?:bank\w*|card|insur\w*|claims?|policyholder|freya)\b", re.I)
        for module in (extract_module, lexicon_module):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertEqual(domain.findall(source), [], module.__name__)


class IdStabilityTest(unittest.TestCase):
    def test_unrelated_markdown_insertion_keeps_ids(self):
        path = ROOT / "briefs" / "synthetic" / "banking_lost_card.md"
        text = path.read_text(encoding="utf-8")
        before = {r.id: r.statement for r in extract(ingest_text(text, doc=path.name))}
        edited = text.replace("## Purpose", "## Background\n\nThis paragraph is new. It has no rules.\n\n## Purpose", 1)
        after = {r.id: r.statement for r in extract(ingest_text(edited, doc=path.name))}
        self.assertEqual(after, before)

    def test_unrelated_json_key_keeps_ids(self):
        path = ROOT / "briefs" / "synthetic" / "insurance_home_renewal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        before = {r.id for r in extract(ingest_json(data, doc=path.name))}
        after = {r.id for r in extract(ingest_json({"version": "2", **data}, doc=path.name))}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
