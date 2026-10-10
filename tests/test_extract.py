import unittest

from builder.extract import extract, normalize_key, parse_sentence, requirement_id
from builder.ingest import ingest_json, ingest_text
from builder.model import Counter, Termination


def reqs(text):
    return extract(ingest_text(text, doc="t.md"))


def one(text):
    found = reqs(text)
    assert len(found) == 1, found
    return found[0]


class ModalityTest(unittest.TestCase):
    def test_must_not_with_actor(self):
        r = one("The assistant must not disclose the balance.")
        self.assertEqual((r.modality, r.actor, r.forbidden_actions), ("must_not", "the assistant", ["disclose the balance"]))

    def test_never_imperative(self):
        r = one("Never ask for the PIN.")
        self.assertEqual((r.modality, r.actor, r.forbidden_actions), ("must_not", None, ["ask for the PIN"]))

    def test_may_goes_to_allowed(self):
        r = one("The assistant may explain the process.")
        self.assertEqual((r.modality, r.allowed_actions), ("may", ["explain the process"]))

    def test_should_and_should_not(self):
        self.assertEqual(one("The assistant should summarise.").required_actions, ["summarise"])
        self.assertEqual(one("It should not speculate.").forbidden_actions, ["speculate"])

    def test_passive_subject_is_the_action(self):
        r = one("Sharing internal scores is not allowed.")
        self.assertEqual((r.modality, r.actor, r.forbidden_actions), ("must_not", None, ["sharing internal scores"]))

    def test_passive_required_with_trailing_condition(self):
        r = one("Verification is required before any change.")
        self.assertEqual((r.modality, r.required_actions, r.preconditions), ("must", ["verification"], ["before any change"]))

    def test_must_always_strips_adverb(self):
        self.assertEqual(one("The assistant must always verify identity.").required_actions, ["verify identity"])

    def test_implicit_imperative_is_flagged(self):
        r = one("Confirm you are speaking to the account holder.")
        self.assertEqual(r.modality, "must")
        self.assertIn("implicit imperative", r.notes)


class NonNormativeTest(unittest.TestCase):
    def test_descriptive_sentences_are_skipped(self):
        for text in [
            "Replacement items are sent to the address on file.",
            "Transfer requests are handled by the back office.",
            "Use of personal data is described elsewhere.",
            "The caller may be upset.",
            "When customers call, they are often upset.",
        ]:
            with self.subTest(text=text):
                self.assertIsNone(parse_sentence(text))


class ConditionTest(unittest.TestCase):
    def test_trailing_condition(self):
        r = one("The assistant must verify identity before discussing account details.")
        self.assertEqual((r.required_actions, r.preconditions), (["verify identity"], ["before discussing account details"]))

    def test_leading_condition_ignores_cue_inside_condition(self):
        r = one("If the caller cannot verify, transfer the call to a human agent.")
        self.assertEqual((r.modality, r.preconditions), ("must", ["If the caller cannot verify"]))

    def test_leading_condition_with_inner_commas(self):
        r = one("If the caller is upset, confused, or asks for a human, transfer the call to a supervisor.")
        self.assertEqual(r.preconditions, ["If the caller is upset, confused, or asks for a human"])
        self.assertEqual(r.required_actions, ["transfer the call to a supervisor"])

    def test_leading_condition_with_explicit_actor(self):
        r = one("When the caller asks, the assistant should explain the fee.")
        self.assertEqual((r.modality, r.actor, r.preconditions), ("should", "the assistant", ["When the caller asks"]))

    def test_reporting_verb_keeps_object_clause(self):
        r = one("Tell the caller when the item will arrive.")
        self.assertEqual((r.required_actions, r.preconditions), (["tell the caller when the item will arrive"], []))

    def test_restrictive_only_is_noted(self):
        r = one("Only discuss the case with the account holder.")
        self.assertTrue(any("only" in n for n in r.notes))


class CounterTest(unittest.TestCase):
    def test_threshold_in_condition(self):
        r = one("After three failed verification attempts, the assistant must end the call.")
        self.assertEqual(r.counters, [Counter("failed verification attempts", 3, "threshold")])

    def test_max_names_the_limited_activity(self):
        r = one("The caller may retry up to two times.")
        self.assertEqual(r.counters, [Counter("retry", 2, "max")])

    def test_twice_and_digits(self):
        self.assertEqual(one("Ask at most twice.").counters, [Counter("ask", 2, "max")])
        self.assertEqual(one("The assistant should ask no more than 5 questions.").counters, [Counter("questions", 5, "max")])

    def test_unrelated_numbers_are_not_counters(self):
        self.assertEqual(one("Verify the last four digits of the account.").counters, [])

    def test_counter_from_json_key(self):
        brief = ingest_json({"limits": {"max_call_attempts": 3, "maxCallbackOffers": 2, "timeout_seconds": 30}}, doc="t.json")
        got = [r.counters for r in extract(brief)]
        self.assertEqual(got, [[Counter("call attempts", 3, "max")], [Counter("callback offers", 2, "max")]])


class TerminationTest(unittest.TestCase):
    def test_end_with_condition(self):
        r = one("End the call after the caller confirms.")
        self.assertEqual(r.terminations, [Termination("end", "end the call", ["after the caller confirms"])])

    def test_handoff(self):
        r = one("If the caller asks for a human, transfer the call to a human agent.")
        self.assertEqual([t.kind for t in r.terminations], ["handoff"])

    def test_transfer_of_money_is_not_a_handoff(self):
        self.assertEqual(one("Transfer funds to a savings account when asked.").terminations, [])

    def test_forbidden_termination_is_not_a_termination(self):
        r = one("Do not end the call while a block is pending.")
        self.assertEqual((r.forbidden_actions, r.terminations), (["end the call"], []))


class JsonKeyHintTest(unittest.TestCase):
    def test_key_supplies_modality_for_bare_phrases(self):
        r = extract(ingest_json({"prohibited": ["Quote a premium"]}, doc="t.json"))[0]
        self.assertEqual((r.modality, r.forbidden_actions), ("must_not", ["quote a premium"]))
        self.assertIn("modality from key 'prohibited'", r.notes)

    def test_explicit_cue_beats_key(self):
        r = parse_sentence("The assistant may quote list prices", keys=("prohibited",))
        self.assertEqual(r.modality, "may")

    def test_normalize_key(self):
        self.assertEqual(normalize_key("maxCallAttempts"), "max call attempts")
        self.assertEqual(normalize_key("must_not-do"), "must not do")


class StructureTest(unittest.TestCase):
    def test_semicolon_clauses_become_separate_requirements(self):
        found = reqs("Verify identity; never ask for the PIN.")
        self.assertEqual([r.modality for r in found], ["must", "must_not"])
        self.assertEqual({r.source.locator for r in found}, {"L1"})

    def test_compound_rule_is_flagged(self):
        r = one("The assistant must verify identity and never reveal the PIN.")
        self.assertTrue(any("several normative cues" in n for n in r.notes))

    def test_ids_are_content_hashes_and_duplicates_get_suffix(self):
        found = reqs("- Never ask for the PIN.\n- Never ask for the PIN.")
        base = requirement_id("Never ask for the PIN.")
        self.assertEqual([r.id for r in found], [base, f"{base}-2"])


if __name__ == "__main__":
    unittest.main()
