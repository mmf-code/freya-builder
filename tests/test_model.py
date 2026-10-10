import unittest

from builder.model import Counter, Requirement, SourceRef, Termination, dump_requirements, load_requirements


def sample():
    return Requirement(
        id="R-1",
        modality="must",
        statement="After two attempts, transfer the call to a human agent.",
        source=SourceRef("b.md", "L3", ("Rules",), "After two attempts, transfer the call to a human agent."),
        preconditions=["After two attempts"],
        required_actions=["transfer the call to a human agent"],
        counters=[Counter("attempts", 2, "threshold")],
        terminations=[Termination("handoff", "transfer the call to a human agent", ["After two attempts"])],
        notes=["implicit imperative"],
    )


class RoundTripTest(unittest.TestCase):
    def test_dump_load_is_identity(self):
        reqs = [sample()]
        self.assertEqual(load_requirements(dump_requirements(reqs)), reqs)

    def test_minimal_dict_loads_with_defaults(self):
        r = Requirement.from_dict({"id": "X", "modality": "may", "statement": "s", "source": {"doc": "d", "locator": "L1"}})
        self.assertEqual((r.origin, r.counters, r.source.section), ("manual", [], ()))

    def test_unknown_keys_survive_in_extra(self):
        d = sample().to_dict() | {"rubric_ref": "J-4"}
        r = Requirement.from_dict(d)
        self.assertEqual(r.extra, {"rubric_ref": "J-4"})
        self.assertEqual(Requirement.from_dict(r.to_dict()), r)


if __name__ == "__main__":
    unittest.main()
