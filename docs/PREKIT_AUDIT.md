# Earlier pre-kit code: verified audit on official v3 inputs

**Audited on 2026-10-10** from `freya-builder.zip` without modifying the original project source or test files.

## What works

- `python3 -m unittest discover -s tests -q` -> **89 tests passed** (local dry run, around 0.05 seconds).
- Ingest supports Markdown, plain text and JSON, preserving source line locators or JSON pointers.
- Requirement IR, source-trace validator, JSON structural diff and synthetic briefs are useful reusable utilities.
- **None of the 89 tests exercises live Freya API, live workflow execution, real ledger scoring or semantic fidelity of the official A/B briefs.**

## Tested against actual kit briefs

| Source | Rule numbering | Heuristic `extract` output | `I-UNCLASSIFIED` | Reported `error` / `warning` |
|---|---:|---:|---:|---:|
| Official Brief A | 47 rules | 66 fragments | 14 | 0 / 1 |
| Official Brief B | 11 modifications | 7 fragments | 5 | 0 / 0 |
| A+B together | 58 numbered clauses total | 73 fragments | 19 | 0 / 1 |

**These numbers are NOT recall scores.** A single numbered policy can split into multiple extracted fragments; some fragments can be irrelevant (e.g. "Read all of it"), and some complex clauses are dropped or flattened. The current completeness heuristic uses substantially the same lexicon as the extractor; a clean validation status can therefore be misleading.

Examples of unclassified, high-impact rules:

- A L32: third-party callback day/time window.
- A L41: three wrong security answers total.
- A L55: delinquency band/deadline table (not fully represented by current requirement IR).
- A L71: credit card versus loan floor selection.
- A L79–81: persuasion counting and date choices.
- A L106: one last `close_call` with correct outcome/reason.
- B L11: per-product delinquency band/deadline.
- B L13: persuasion attempt count per product.
- B L14: one date proposal can produce different valid dates for different products.
- B L17: disputed/already-paid status of one product does not end multi-product call.

Run the audit again with:

```bash
python3 -m builder extract docs/build-the-builder/briefs/brief-a.md -o /tmp/a-req.json
python3 -m builder extract docs/build-the-builder/briefs/brief-b.md -o /tmp/b-req.json
python3 -m builder validate docs/build-the-builder/briefs/brief-a.md docs/build-the-builder/briefs/brief-b.md
```

## Decisions

- **KEEP** existing code/tests unchanged during first integration.
- **DO NOT** use current regex output as sole policy compiler input. Semantic parser must read the original brief texts, tables, exceptions, precedence/memos, and dynamic OpenAPI.
- Treat `I-UNCLASSIFIED` as a **review blocker** during official policy compilation, not as an ignorable info message.
- The old `docs/FINDINGS.md` and `docs/INTEGRATION_CHECKLIST.md` describe an earlier preparation phase and should not drive the current event integration.
