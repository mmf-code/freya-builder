import unittest
from dataclasses import replace

from builder.extract import extract
from builder.ingest import ingest_text
from builder.model import Counter, Requirement, SourceRef, Termination
from builder.validate import validate


def req(id="R-1", modality="must", quote="Verify identity.", locator="L1", doc="b.md", **kw):
    kw.setdefault("required_actions", ["verify identity"])
    return Requirement(id=id, modality=modality, statement=quote, source=SourceRef(doc, locator, (), quote), **kw)


def codes(findings):
    return sorted(f.code for f in findings)


class RequirementChecksTest(unittest.TestCase):
    def test_clean_requirement_has_no_findings(self):
        self.assertEqual(validate([req()]), [])

    def test_duplicate_and_empty_ids(self):
        self.assertEqual(codes(validate([req(), req(), req(id="")])), ["E-ID-DUP", "E-ID-EMPTY"])

    def test_unknown_modality(self):
        self.assertEqual(codes(validate([req(modality="ought")])), ["E-MODALITY"])

    def test_missing_quote(self):
        r = req()
        r.source = replace(r.source, quote="")
        self.assertEqual(codes(validate([r])), ["E-SOURCE"])

    def test_same_action_permitted_and_forbidden(self):
        r = req(forbidden_actions=["Verify the identity"])
        self.assertEqual(codes(validate([r])), ["E-ACTION-CONTRADICTION"])

    def test_bad_counters(self):
        for counter in [Counter("x", 0, "max"), Counter("x", True, "max"), Counter("x", 2, "sometimes"), Counter(" ", 2, "max")]:
            with self.subTest(counter=counter):
                self.assertEqual(codes(validate([req(counters=[counter])])), ["E-COUNTER"])

    def test_termination_checks(self):
        self.assertEqual(codes(validate([req(terminations=[Termination("end", "end the call", [])])])), ["W-UNCONDITIONAL-TERMINATION"])
        self.assertEqual(codes(validate([req(terminations=[Termination("vanish", "x", ["if y"])])])), ["E-TERMINATION"])

    def test_no_action(self):
        self.assertEqual(codes(validate([req(required_actions=[])])), ["W-NO-ACTION"])

    def test_notes_become_review_info(self):
        self.assertEqual(codes(validate([req(notes=["implicit imperative"])])), ["I-REVIEW"])


class ConflictTest(unittest.TestCase):
    def test_unconditional_conflict_is_a_warning(self):
        a = req(id="A", required_actions=["end the call"])
        b = req(id="B", modality="must_not", required_actions=[], forbidden_actions=["end the call"])
        self.assertEqual(codes(validate([a, b])), ["W-CONFLICT"])

    def test_conditional_conflict_is_info(self):
        a = req(id="A", required_actions=["end the call"], preconditions=["after the caller confirms"])
        b = req(id="B", modality="must_not", required_actions=[], forbidden_actions=["end the call"], preconditions=["while pending"])
        self.assertEqual(codes(validate([a, b])), ["I-CONDITIONAL-CONFLICT"])


class BriefChecksTest(unittest.TestCase):
    def setUp(self):
        self.brief = ingest_text("- Verify identity.\n- Never ask for the PIN.\n- Cards arrive by post.\n", doc="b.md")

    def test_traceability(self):
        # Traceable; the PIN rule is uncovered and the descriptive bullet is unclassified.
        self.assertEqual(codes(validate([req(locator="L1")], [self.brief])), ["I-UNCLASSIFIED", "W-COVERAGE"])
        self.assertIn("E-TRACE-QUOTE", codes(validate([req(locator="L2")], [self.brief])))
        self.assertIn("E-TRACE-LOCATOR", codes(validate([req(locator="L9")], [self.brief])))
        self.assertIn("E-TRACE-DOC", codes(validate([req(doc="other.md")], [self.brief])))

    def test_coverage_counts_only_normative_sentences(self):
        findings = [f for f in validate([req()], [self.brief]) if f.code == "W-COVERAGE"]
        self.assertEqual(len(findings), 1)
        self.assertIn("Never ask for the PIN.", findings[0].message)

    def test_unclassified_list_items_are_surfaced(self):
        findings = [f for f in validate(extract(self.brief), [self.brief]) if f.code == "I-UNCLASSIFIED"]
        self.assertEqual([f.level for f in findings], ["info"])
        self.assertIn("Cards arrive by post.", findings[0].message)

    def test_extractor_output_covers_its_brief(self):
        findings = validate(extract(self.brief), [self.brief])
        self.assertEqual([f for f in findings if f.level != "info"], [])


if __name__ == "__main__":
    unittest.main()
