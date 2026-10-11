# freya-builder

> Final (2026-10-11): run the builder with `python3 builder/build.py CASE_FOLDER MOCK_URL --skill DIR --label NAME`.
> `build.py` converts the case documents to text, reads the tool API from the mock, and runs `builder/kitrun.py` with
> a skill from `builder/skills/`. The bank mock is in `mock/` (Cloudflare Workers) and is not part of the builder.
> Steps: `docs/FINAL_LIVE.md`. Candidates and results: `docs/BUILDERS.md`. Status: `docs/STATUS.md`.
> The paragraphs below describe the pre-kit utilities.

Freya Build the Builder hackathon workspace. The official **v3 kit is now vendored**
unchanged under `docs/build-the-builder/`. Start with **`docs/START_HERE.md`**
and use **`docs/CLAUDE_LEAD_BRIEF.md`** for Claude Code. The original `builder/`
modules are schema-independent *pre-kit utilities*, not a complete Phone Agent Builder.

The code turns a brief into a structured, source-traceable requirement set,
validates it locally, and diffs JSON documents without knowing their schema.
Stdlib only. Python 3.11 or later.

**Run the official sample from `docs/build-the-builder/`, not from the repo root.**

## Layout

| Path | Purpose |
| --- | --- |
| `builder/ingest.py` | Brief to segments. Markdown, plain text or arbitrary JSON. Each segment has a locator (`L12`, `L3-L5`, `#/a/0`). |
| `builder/model.py` | Requirement IR: modality, actor, preconditions, required/allowed/forbidden actions, counters, terminations, source ref. Our format. |
| `builder/lexicon.py` | English cue words as data. Another language means another `Lexicon`, not new code. |
| `builder/extract.py` | Deterministic heuristic extractor. Adds review notes where it guesses. |
| `builder/validate.py` | IR checks, cross-rule conflicts, traceability and coverage against briefs. |
| `builder/jsondiff.py` | Schema-agnostic JSON diff, shape extraction, shape diff, text report. |
| `briefs/synthetic/` | Invented banking and insurance briefs (two Markdown, one JSON). |
| `tests/` | Unit, invariant, golden snapshot and CLI tests. |
| `docs/INTEGRATION_CHECKLIST.md` | Steps for when the official material arrives. |
| `docs/FINDINGS.md` | Verified results, open assumptions, known limits, incoming sourced claims. |
| `inputs/official/`, `inputs/chrome/` | Drop zones for the official document and Claude in Chrome findings. |

## Commands

```sh
python3 -m unittest                                   # all tests
python3 -m builder extract BRIEF... [-o reqs.json]    # requirement IR as JSON
python3 -m builder validate BRIEF... [-r reqs.json]   # findings; exit 1 on errors
python3 -m builder diff OLD.json NEW.json [--id-key K] [--ignore GLOB] [--structural-only] [--shape] [--json]
python3 -m builder shape FILE.json                    # every path pattern with its JSON types
UPDATE_GOLDEN=1 python3 -m unittest tests.test_golden # accept reviewed extractor output
```

`diff` exits 1 when the files differ, like `diff(1)`.

## Secrets and cloud runs

Secrets never go into git. `docs/build-the-builder/env.sh` is git-ignored and only exists on a local machine.

- **Local:** `cp docs/build-the-builder/env.example docs/build-the-builder/env.sh` and fill it in.
- **Cloud (Claude Code on the web):** set `FREYA_API_KEY`, `FREYA_BANK_TEAM_KEY` and `ANTHROPIC_API_KEY`
  as environment variables in the cloud environment settings, and `scripts/setup.sh` as its setup script.
  `FREYA_API_URL` is optional.

`builder.kitrun` and `scripts/run_kit_builder.sh` read `env.sh` when it exists, else the environment.

## Finding codes

Errors (`E-*`) break the IR or traceability. Warnings (`W-*`) need a decision.
Info (`I-*`) is review material.

| Code | Meaning |
| --- | --- |
| `E-ID-EMPTY`, `E-ID-DUP` | Missing or duplicate requirement id. |
| `E-MODALITY`, `E-STATEMENT`, `E-SOURCE` | Invalid modality, empty statement, incomplete source ref. |
| `E-ACTION-CONTRADICTION` | One requirement permits and forbids the same action. |
| `E-COUNTER`, `E-TERMINATION` | Malformed counter or termination. |
| `E-TRACE-DOC`, `E-TRACE-LOCATOR`, `E-TRACE-QUOTE` | Source ref does not resolve to the quoted text in the given brief. |
| `W-CONFLICT` | Two requirements permit and forbid the same action under the same conditions. |
| `W-COVERAGE` | A normative sentence in the brief has no requirement. |
| `W-UNCONDITIONAL-TERMINATION` | End or handoff without any condition. |
| `W-NO-ACTION` | No action and no counter parsed. |
| `I-CONDITIONAL-CONFLICT` | Same action permitted and forbidden under different conditions. A workflow must order them. |
| `I-UNCLASSIFIED` | A list entry produced no requirement. Check it is really descriptive. |
| `I-REVIEW` | Extractor notes: implicit imperative, modality from a JSON key, compound rule, and so on. |
