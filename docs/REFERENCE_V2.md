# reference-v2: the one candidate, its experiment and the switch rule

Status 2026-10-11 04:25 UTC+3: written, not built, not measured; stage 0 (read-only baseline) done. The final uses `builder/skills/reference` unless
the gate below passes before the freeze.

## What it is

`builder/skills/reference-v2/SKILL.md`, sha256 `999681cea4e0`, is `reference` (`7659a7bd2e6c`, byte-identical copy)
plus four general rules. Same runner, same helpers, same step 6 (no practice test when the brief has no practice
customers). `diff builder/skills/reference/SKILL.md builder/skills/reference-v2/SKILL.md` shows the whole change.

| Added rule | Targets (`docs/FAILURE_MODES.md`) | Why it is a rule and not a fix of one case |
|---|---|---|
| Say what the brief wants said before the terminal tool in a step before the terminal step; no spoken line in the terminal step | #1 | Every lowering build did this wrong (24/24 calls); reference builds did it right by the builder's choice, so a new build could still get it wrong |
| Items taken one at a time each get all their own steps when their turn comes; an earlier statement about an item does not shorten them, unless the brief says so; named exceptions still apply | #2 | V09 skip in three agents from two skills; the trigger is the timing of the refusal, not the case |
| A question asked once for all items is asked before the per-item steps, not inside them | #3, #4 | "today?" re-asked per product and order lost in two builds |
| A word-for-word sentence is said as written; a word reserved for an event appears in no fixed line, including the greeting | #5, #6, #15 | The greeting cost blind-ref V06 2/3 and PUB-10 1/3; the text-message sentence is missing in 5 of 9 official B calls of the blind reference agent |

Kept out on purpose: an in-build check loop (selfcheck regressed with one, #8), a checker change (the checker is part
of the frozen configuration), anything with a case id, a brief value or a bank name.

Risks to watch in the transcripts: the greeting must still say that the call is recorded in other words (Brief A rule
1); the per-item rule must not make the agent repeat an offer the customer refused on its turn (`ATTEMPTS_OVER`);
build time (reference blind: 887 s).

## How we switch

The final runs one skill path, written in `docs/FINAL_RUNBOOK.md`. Switching means changing that one path to
`builder/skills/reference-v2` after the gate passes, at one commit, and freezing it with the helpers. No other part
of the runbook changes. If the gate fails, is not finished, or the platform is unstable, nothing changes.

## Experiment (uses Freya; run only with approval)

Pre-registered here before any run. One commit for both arms; a fresh `--state` per build; one simulation at a time.

| Stage | What | Cost |
|---|---|---|
| 0 | `policy_audit --fetch` on the stored official calls of the blind reference and blind precedence agents (call ids in their `eval/*.json`). Read-only; gives the official-customer baseline of deviations the judge did not see. **Done, result below** | ~5 min, no simulation |
| 1 | Two blind builds from `briefs/mutations/brief-a-raw.md` + `brief-b-raw.md`, no practice customers: `reference` (v1-fresh) and `reference-v2`. They can run side by side: a no-practice build starts no simulation | 15-25 min |
| 2 | Each agent: official A x1, B x1, Persona Lab V09, V07, V06 x1. Stop here if v2 is 3 or more customers below v1-fresh, or shows a defect in every call that v1-fresh does not | ~25 min |
| 3 | Complete to three runs: A x3, B x3, V09 x3, V07 x3, V06 x3 per agent (96 calls in all) | ~50 min |
| 4 | `policy_audit` on every call of both agents; read the greeting of each agent once | ~10 min |

### Stage 0 result (2026-10-11 04:20 UTC+3, read-only)

`policy_audit --fetch` on the 39 stored official calls of each blind agent; output in
`runs/20261010-212550-blind-ref-ab/eval/policy_audit.txt` and `runs/20261010-212547-blind-prec-ab/eval/policy_audit.txt`.

| Finding | blind reference | blind lowering-precedence |
|---|---|---|
| Goodbye after `close_call` (`SPEECH_AFTER_CLOSE`) | 0/39 | **39/39** |
| No text-message sentence after recorded promises (`SMS_MISSING`) | **5 of 9 B calls** (all judge PASS; after the writes the agent says only "One moment, please" and goodbye) | 0 |
| "recorded" before the write returned (`RECORDED_EARLY`) | 1 (A, "a payment of 540 recorded ... Do you confirm?") | 5 of 9 B calls |
| More offers than the band allows (`ATTEMPTS_OVER`) | 0 | 2 (PUB-12, judge FAIL) |
| "this call is recorded" in the greeting | 39/39 | 39/39 |
| Judge PASS calls with a finding (greeting not counted) | 6 | 32 |

Read: precedence's closing defect is confirmed in calls, not only in its export. The reference build's hidden weakness
on the official customers is the confirmation after several promises; v2's word-for-word rule targets it, so the
switch rule below now counts it. Amended at 04:20, after stage 0 and before any v1-fresh or v2 run.

v1-fresh is also the replication the outside audit asked for: a second blind build of `reference`, so we see how far
two builds of the same skill differ.

## Switch rule (all must hold, else the final stays on `reference`)

1. Official A+B customers 3/3: v2 at least v1-fresh minus 1. One customer is within build-to-build noise; this is a
   non-inferiority test, not a claim that v2 scores higher.
2. Mechanisms: over all calls of stages 2 and 3, the `policy_audit` findings `ITEM_SKIPPED`, `ATTEMPTS_SHORT`,
   `TODAY_AGAIN`, `ORDER`, `RECORDED_IN_GREETING`, `RECORDED_EARLY` and `SMS_MISSING` together are fewer for v2 than
   for v1-fresh, and at least 2 of 3 V09 calls of v2 have none of them.
3. No new deterministic defect: no finding in every v2 call of a kind that v1-fresh does not have; the greeting still
   discloses the recording.
4. v2's build takes at most 20 minutes.
5. Runs with platform evidence (`docs/EVAL_PROTOCOL.md`) are repeated; clean failures stay in the count.

What the result can not say: whether v2 scores higher on hidden briefs, or a one- or two-customer difference.
What it can say: whether a fresh v2 build loses the four targeted defects without breaking the official runs.

## Not planned

- A lowering or lowering-precedence build: both carry defect #1 through `lower.py`, and precedence's attempts lead on
  g3 is void (#11).
- New personas or new rules after the experiment starts.
- Any edit of `reference`, `workflow_check.py`, `lower.py`, `dryrun.py` or `kitrun.py` before the final.
