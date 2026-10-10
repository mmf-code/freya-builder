import json
import tempfile
import unittest
from pathlib import Path

from builder.ingest import ingest_json, ingest_text, iter_sentences, json_pointer, load_brief, split_sentences

MD = """# Title

Intro line one
continues here. Second sentence.

## Rules

- First rule.
- Second rule
  wraps here.
1. Numbered rule.

| Situation | Action |
|---|---|
| A | B |

```json
{"x": 1}
```

> Quoted line.
"""


class TextIngestTest(unittest.TestCase):
    def setUp(self):
        self.brief = ingest_text(MD, doc="t.md")
        self.by_text = {s.text: s for s in self.brief.segments}

    def test_headings_build_section_path(self):
        self.assertEqual(self.by_text["Title"].ref.section, ("Title",))
        self.assertEqual(self.by_text["Rules"].ref.section, ("Title", "Rules"))
        self.assertEqual(self.by_text["First rule."].ref.section, ("Title", "Rules"))

    def test_heading_of_higher_level_pops_stack(self):
        brief = ingest_text("## A\n\n# B\n\ntext", doc="t.md")
        self.assertEqual(brief.segments[-1].ref.section, ("B",))

    def test_paragraph_joins_wrapped_lines_and_keeps_line_range(self):
        seg = self.by_text["Intro line one continues here. Second sentence."]
        self.assertEqual((seg.kind, seg.ref.locator), ("paragraph", "L3-L4"))

    def test_list_items_including_continuation_and_numbered(self):
        self.assertEqual(self.by_text["First rule."].ref.locator, "L8")
        self.assertEqual(self.by_text["Second rule wraps here."].ref.locator, "L9-L10")
        self.assertEqual(self.by_text["Numbered rule."].kind, "list_item")

    def test_table_rows_without_separator(self):
        rows = [s.text for s in self.brief.segments if s.kind == "table_row"]
        self.assertEqual(rows, ["Situation | Action", "A | B"])

    def test_code_is_kept_but_not_prose(self):
        code = [s for s in self.brief.segments if s.kind == "code"]
        self.assertEqual([c.text for c in code], ['{"x": 1}'])
        self.assertEqual(list(iter_sentences(code[0])), [])

    def test_blockquote_marker_stripped(self):
        self.assertIn("Quoted line.", self.by_text)

    def test_sentences_carry_parent_locator_and_quote(self):
        sentences = [s for s in self.brief.sentences() if s.ref.locator == "L3-L4"]
        self.assertEqual([s.text for s in sentences], ["Intro line one continues here.", "Second sentence."])
        self.assertEqual(sentences[1].ref.quote, "Second sentence.")

    def test_text_at(self):
        self.assertEqual(self.brief.text_at("L8"), "First rule.")
        self.assertIsNone(self.brief.text_at("L999"))


class SentenceSplitTest(unittest.TestCase):
    def test_abbreviations_do_not_split(self):
        self.assertEqual(split_sentences("Call Dr. Smith today. Done."), ["Call Dr. Smith today.", "Done."])

    def test_lowercase_after_period_does_not_split(self):
        self.assertEqual(split_sentences("Use e.g. a PIN. Stop."), ["Use e.g. a PIN.", "Stop."])

    def test_no_terminal_punctuation(self):
        self.assertEqual(split_sentences("Quote a renewal premium"), ["Quote a renewal premium"])


class JsonIngestTest(unittest.TestCase):
    def test_every_leaf_is_addressable_by_json_pointer(self):
        data = {"a": {"b": ["x. Y.", 3, True]}, "we/ird": "z"}
        brief = ingest_json(data, doc="t.json")
        got = {s.ref.locator: (s.kind, s.text, s.keys) for s in brief.segments}
        self.assertEqual(
            got,
            {
                "#/a/b/0": ("value", "x. Y.", ("a", "b")),
                "#/a/b/1": ("number", "3", ("a", "b")),
                "#/a/b/2": ("scalar", "true", ("a", "b")),
                "#/we~1ird": ("value", "z", ("we/ird",)),
            },
        )

    def test_pointer_escaping(self):
        self.assertEqual(json_pointer(("a~b", "c/d", 0)), "#/a~0b/c~1d/0")

    def test_any_top_level_shape(self):
        self.assertEqual([s.text for s in ingest_json(["one", "two"], doc="t.json").segments], ["one", "two"])
        self.assertEqual([s.ref.locator for s in ingest_json("just text", doc="t.json").segments], ["#"])


class LoadBriefTest(unittest.TestCase):
    def test_format_by_extension(self):
        with tempfile.TemporaryDirectory() as d:
            for name, content, fmt in [
                ("a.md", "# H\n\ntext", "markdown"),
                ("a.txt", "text", "text"),
                ("a.json", json.dumps({"k": "v"}), "json"),
            ]:
                path = Path(d) / name
                path.write_text(content, encoding="utf-8")
                brief = load_brief(path)
                self.assertEqual((brief.doc, brief.format), (name, fmt))


if __name__ == "__main__":
    unittest.main()
