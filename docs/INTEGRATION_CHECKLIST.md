> **Historical pre-kit notes.** The official v3 starter kit is now present. For current decisions read [`START_HERE.md`](START_HERE.md) and [`PREKIT_AUDIT.md`](PREKIT_AUDIT.md).

# Integration checklist

Use this when official material arrives. Record every answer in
`docs/FINDINGS.md` with its source. Do not change the IR until a mapping step
shows a concrete gap.

## 1. Official document arrives

- [ ] Save it unchanged in `inputs/official/`. Log file name, date and sender in FINDINGS.
- [ ] If it is PDF or DOCX, convert a copy to `.md` or `.txt`. Keep the original.
- [ ] Run `python3 -m builder validate <brief>`. Read every `W-*` and `I-UNCLASSIFIED`.
- [ ] Language check. If the brief is not English, add a `Lexicon` in `builder/lexicon.py`. Do not edit `extract.py` for this.
- [ ] Extend the lexicon for missed verbs or cues. Add a unit test per addition. Re-run the golden test.
- [ ] Copy a sanitized excerpt to `briefs/` so the invariant tests cover it.
- [ ] Extract the judging criteria into a list. Map each one to a test or a validator check.
- [ ] List every term the document defines (node, step, state, tool, variable, handoff, ...). Map each one to an IR field, or mark it as a gap.

## 2. Starter kit arrives

- [ ] Record its version or commit hash in FINDINGS.
- [ ] Run its own tests and validators first, unmodified. Record the result.
- [ ] Keep it vendored and unedited. Put our glue in `builder/adapters/<kit>.py`.
- [ ] Note what it already provides: validation, simulation, deployment, evaluation. Do not rebuild those.
- [ ] Note authentication, rate limits and environment setup only from its docs. No speculative API wiring.

## 3. Workflow schema or sample workflows arrive

- [ ] Save samples in `inputs/official/`. Run `python3 -m builder shape <sample>`. Save the output next to the sample.
- [ ] Find the identity key of list items (nodes, edges, tools). Pass it to `diff` with `--id-key`.
- [ ] Find volatile fields (timestamps, generated ids). Pass them to `diff` with `--ignore`.
- [ ] Answer the open questions below from the schema, not from guesses.
- [ ] Write the IR-to-workflow generator only now, as a separate module. The IR stays schema-free.
- [ ] Add one validator check per schema rule the document states.
- [ ] After each generated workflow version, run `diff --structural-only` against the previous one.

## 4. Claude in Chrome findings arrive

- [ ] Save raw notes in `inputs/chrome/` with date and source URLs.
- [ ] Add each claim to the Sourced claims table in FINDINGS. Status: unverified until the official document or the kit confirms it.
- [ ] Never treat a Chrome finding as schema truth while it contradicts the official document.

## Open questions to answer from official sources

1. What format and language does the brief use?
2. Is a workflow a graph (nodes and edges), a linear script, or a state machine?
3. How are global policies attached: once per workflow, or per node?
4. How does a workflow express counters and retries?
5. How does a workflow express ending a call and handing off to a human?
6. Which actions or tools may a workflow call? Is there a fixed list?
7. Does the kit validate workflows? Does it simulate conversations?
8. What is the submission format, and how is a submission judged?
9. Do requirements carry official ids? If yes, keep them in `Requirement.extra` and diff on them.
