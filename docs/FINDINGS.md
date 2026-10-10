> **Historical pre-kit notes.** The official v3 starter kit is now present. For current decisions read [`START_HERE.md`](START_HERE.md) and [`PREKIT_AUDIT.md`](PREKIT_AUDIT.md).

# Findings

Three kinds of entries, kept apart:

- **Field observations**: what we ran here and saw. Reproducible from this repo.
- **Sourced claims**: statements from the official document, the starter kit or Claude in Chrome. Each names its source.
- **Assumptions**: what the code currently assumes about Freya. Unverified until a sourced claim confirms it.

## Field observations

Date: 2026-10-10. Python 3.14.5 on macOS. No dependencies.

| ID | Observation | Consequence |
| --- | --- | --- |
| F-01 | `python3 -m unittest`: 89 tests pass in about 0.03 s. | Baseline for later changes. |
| F-02 | The three synthetic briefs yield 17 (banking), 20 (motor claim) and 11 (home renewal JSON) requirements. Validation gives 0 errors and 0 warnings. | The extractor and validator agree on all three domains. |
| F-03 | The validator found a real rule interaction in `insurance_motor_fnol.md`. R-613fdda8 ends the call after the emergency instruction. R-5ce0b2d4 forbids ending the call before a claim reference exists. In an emergency there is no claim reference. | Briefs can contain rules that collide in edge cases. A workflow needs explicit precedence. Safety rules should win. Expect the same in the official brief. |
| F-04 | `banking_lost_card.md` has a similar but orderable pair: R-9dd5c689 (end after the caller confirms) and R-2df731a0 (do not end while a block is pending). | `I-CONDITIONAL-CONFLICT` lists these pairs. Treat each as a workflow ordering decision. |
| F-05 | A missing verb ("discuss") silently dropped an imperative rule in a test. The coverage check missed it because it uses the same lexicon. | Added `I-UNCLASSIFIED` for list entries with no requirement. On the official brief, review every one of them. |
| F-06 | Counter subjects are sometimes bare. "If the policy cannot be found after two attempts" gives subject `attempts`. | Name counters by hand or with a model pass before mapping them to workflow state. |
| F-07 | Requirement ids are content hashes. Rewording a rule gives a new id. A diff of two extractions then shows remove plus add, not a field change. | Intended. If official requirement ids exist, store them in `extra` and diff on them. |
| F-08 | In JSON briefs, a key like `prohibited` supplies the modality for bare phrases. A key like `max_call_attempts` becomes a counter. Only the value's own key counts. A parent key such as `limits` does not. | Parent-key inference was dropped because it turned `timeout_seconds: 600` into a fake counter. |
| F-09 | Two rules were edited in a copy of the banking brief and the copy was re-extracted. `diff --shape` against the golden file reported 0 changes. Plain `diff` reported 2 removed and 2 added requirements. | `diff --shape` separates schema drift from content drift. |

## Known limits of the heuristic extractor

- English only. Another language needs its own `Lexicon`.
- Imperatives are detected through a closed verb list. See F-05.
- Table rows are ingested but not interpreted.
- A compound rule ("verify X and never say Y") becomes one requirement with a review note. Semicolon clauses are split.
- A leading condition without a comma is not separated from the actor. It gets a review note.
- "Ask ... if ..." and "tell ... when ..." keep the clause as part of the action, not as a condition. This avoids false conditions but loses some real ones.
- Durations and deadlines ("within 30 days", timeouts) are not modelled.
- Actions are kept as phrases. "The PIN, the CVV, or the password" stays one forbidden action.

## Assumptions about Freya (unverified)

| ID | Assumption | Where it lives | Check against | Impact if wrong |
| --- | --- | --- | --- | --- |
| A-01 | The brief is prose (Markdown, text, or convertible PDF/DOCX) or JSON. | `ingest.py` | Official document | Add an ingester. The IR stays the same. |
| A-02 | The brief is in English. | `lexicon.py` | Official document | Add a `Lexicon`. |
| A-03 | Workflows are JSON. | `jsondiff.py` | Starter kit, schema | The diff module would need a YAML or other loader only. |
| A-04 | Workflow list items carry an identity key such as `id`, `key` or `name`. | `jsondiff.DEFAULT_ID_KEYS` | Sample workflows | Diff falls back to sequence alignment. It stays correct but gets noisier. Set `--id-key`. |
| A-05 | A conversation ends by ending the call or handing off. | `model.TERMINATION_KINDS` | Official document | Add a termination kind. |

## Sourced claims

Fill this from `inputs/official/` and `inputs/chrome/`. Status is one of:
unverified, verified, contradicted.

| ID | Claim | Source (doc + section, or URL) | Retrieved | Status | Affects |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
