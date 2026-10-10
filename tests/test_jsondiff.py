"""The fixtures here are generic JSON, not a guess at any workflow schema."""
import unittest

from builder.jsondiff import Change, diff, format_report, shape, shape_diff, summarize


class DiffTest(unittest.TestCase):
    def test_identical(self):
        doc = {"a": [1, {"b": None}], "c": True}
        self.assertEqual(diff(doc, doc), [])

    def test_scalar_change_add_remove(self):
        changes = diff({"a": 1, "b": 2}, {"a": 3, "c": 4})
        self.assertEqual(
            changes,
            [Change("changed", "$.a", 1, 3), Change("removed", "$.b", 2, None), Change("added", "$.c", None, 4)],
        )

    def test_type_change_is_structural(self):
        changes = diff({"t": 30}, {"t": "30s"})
        self.assertEqual(changes, [Change("type_changed", "$.t", 30, "30s")])
        self.assertTrue(changes[0].structural)

    def test_bool_is_not_a_number_but_int_float_are_equal(self):
        self.assertEqual([c.kind for c in diff({"x": 1}, {"x": True})], ["type_changed"])
        self.assertEqual(diff({"x": 1}, {"x": 1.0}), [])

    def test_keyed_list_insert_does_not_cascade(self):
        old = {"items": [{"id": "a", "v": 1}, {"id": "b", "v": 2}]}
        new = {"items": [{"id": "x", "v": 0}, {"id": "a", "v": 1}, {"id": "b", "v": 5}]}
        self.assertEqual(
            diff(old, new),
            [Change("added", '$.items[id="x"]', None, {"id": "x", "v": 0}), Change("changed", '$.items[id="b"].v', 2, 5)],
        )

    def test_keyed_list_reorder(self):
        old = {"items": [{"name": "a"}, {"name": "b"}]}
        new = {"items": [{"name": "b"}, {"name": "a"}]}
        self.assertEqual(diff(old, new), [Change("reordered", "$.items", ["a", "b"], ["b", "a"])])

    def test_custom_id_key(self):
        old = [{"uid": 1, "v": "x"}]
        new = [{"uid": 1, "v": "y"}]
        self.assertEqual(diff(old, new, id_keys=("uid",)), [Change("changed", "$[uid=1].v", "x", "y")])

    def test_duplicate_ids_fall_back_to_alignment(self):
        old = [{"id": "a", "v": 1}, {"id": "a", "v": 2}]
        new = [{"id": "a", "v": 1}, {"id": "a", "v": 3}]
        self.assertEqual(diff(old, new), [Change("changed", "$[1].v", 2, 3)])

    def test_unkeyed_list_alignment(self):
        self.assertEqual(diff(["a", "b", "c"], ["a", "x", "b", "c"]), [Change("added", "$[1]", None, "x")])
        self.assertEqual(diff(["a", "b", "c"], ["a", "c"]), [Change("removed", "$[1]", "b", None)])

    def test_ignore_globs(self):
        old = {"meta": {"updatedAt": "1"}, "nodes": [{"id": "a", "updatedAt": "1", "v": 1}]}
        new = {"meta": {"updatedAt": "2"}, "nodes": [{"id": "a", "updatedAt": "2", "v": 2}]}
        self.assertEqual(diff(old, new, ignore=["*.updatedAt"]), [Change("changed", '$.nodes[id="a"].v', 1, 2)])

    def test_odd_keys_are_quoted(self):
        self.assertEqual(diff({"a b": 1}, {"a b": 2}), [Change("changed", '$["a b"]', 1, 2)])


class ShapeTest(unittest.TestCase):
    def test_shape_collapses_list_indices(self):
        doc = {"nodes": [{"id": "a", "next": None}, {"id": "b", "next": "a"}]}
        self.assertEqual(
            shape(doc),
            {"$": ["object"], "$.nodes": ["array"], "$.nodes[*]": ["object"], "$.nodes[*].id": ["string"], "$.nodes[*].next": ["null", "string"]},
        )

    def test_shape_diff_folds_subtrees_and_ignores_values(self):
        old = {"nodes": [{"id": "a"}], "v": 1}
        new = {"nodes": [{"id": "b", "tools": [{"name": "t"}]}], "v": "1", "extra": {"k": 1}}
        self.assertEqual(
            shape_diff(old, new),
            [
                Change("path_added", "$.extra", None, ["object"]),
                Change("path_added", "$.nodes[*].tools", None, ["array"]),
                Change("types_changed", "$.v", ["number"], ["string"]),
            ],
        )


class ReportTest(unittest.TestCase):
    def test_summary_and_lines(self):
        changes = diff({"a": 1, "b": [1]}, {"a": 2, "b": "x", "c": 3})
        self.assertEqual(summarize(changes), {"added": 1, "changed": 1, "type_changed": 1})
        report = format_report(changes)
        self.assertTrue(report.startswith("3 changes (2 structural, 1 value)"))
        self.assertIn("  ~ $.a: 1 -> 2", report)
        self.assertIn("  ! $.b: array [1] -> string \"x\"", report)
        self.assertIn("  + $.c = 3", report)

    def test_long_values_are_truncated(self):
        report = format_report([Change("added", "$.x", None, "y" * 200)], width=20)
        self.assertIn('"yyyyyyyyyyyyyyyy...', report)


if __name__ == "__main__":
    unittest.main()
