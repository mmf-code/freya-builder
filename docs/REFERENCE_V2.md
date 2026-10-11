# reference-v2: the one candidate, its experiment and the switch rule

Status 2026-10-11 05:00 UTC+3: protocol revision 2 written after the second outside review; not built, not measured.
The final uses `builder/skills/reference` unless the switch rule below passes before the freeze.

## What it is

`builder/skills/reference-v2/SKILL.md`, sha256 `999681cea4e0`, is `reference` (`7659a7bd2e6c`, byte-identical copy)
plus four general instructions. Same helpers, same step 6 (no practice test when the brief has no practice customers).
`diff builder/skills/reference/SKILL.md builder/skills/reference-v2/SKILL.md` shows the whole change.

| Added instruction | Targets (`docs/FAILURE_MODES.md`) | Evidence for the target |
|---|---|---|
| Say what the brief wants said before the terminal tool in a step before the terminal step; no spoken line in the terminal step | #1 | Both measured lowering-family builds put the farewell in `lower.py`'s `say` and spoke it after `close_call`; reference builds chose an earlier step, but nothing in `reference` requires it |
| Items taken one at a time each get all their own steps when their turn comes; an earlier statement about an item does not shorten them, unless the brief says so; named exceptions still apply | #2 | V09 skip in three agents from two skills; the trigger is the timing of the refusal, not the case |
| A question asked once for all items is asked before the per-item steps, not inside them | #3, #4 | "today?" re-asked per product and order lost in two builds |
| A word-for-word sentence is said as written; a word reserved for an event appears in no fixed line, including the greeting | #5, #6, #15 | The greeting cost blind-ref V06 2/3 and PUB-10 1/3; the text-message sentence is missing in 5 of 9 official B calls of the blind reference agent |

These are instructions. The builder may still carry them in prompt text, and no check enforces them: v2 asks for
separate steps, it does not guarantee them. Kept out on purpose: an in-build check loop (#8), a checker change (the
builder runs the checker, so changing it changes what the builder does), anything with a case id, a brief value or a
bank name.

Risks to look for in the transcripts (inference, not observed): a refused offer or product reopened, more attempts
than the band allows; a fixed confirmation line spoken although the write failed; a valid out-of-turn correction
ignored; the recording disclosure paraphrased into something that no longer says the call is recorded (Brief A rule 1).

## How we switch

The final runs one skill path, written in `docs/FINAL_RUNBOOK.md`. Switching means changing that one path to
`builder/skills/reference-v2` after the switch rule passes, at one commit, and freezing it with the runner and helpers.
If the rule fails, is not finished, or the platform is unstable, nothing changes.

## Runner version

Both arms run with the runner of commit `0c59ba3` (kitrun's acceptance decision hardened in `7e4e2a0`; its trust
boundary tightened in `c077158` and `0c59ba3` after security reviews; see `docs/FAILURE_MODES.md` #16). What the builder sees is unchanged since `fe8bd5b`: workspace layout, skill handling and helpers
(`workflow_check.py`, `lower.py`, `dryrun.py`) are byte-identical. Earlier measurements used the earlier runner; the
comparison is between the two new arms only.

## Experiment (uses Freya; run only with approval)

One commit for both arms; a fresh `--state` per build; one simulation at a time. This protocol is frozen at the commit
that adds revision 2, before any candidate call; later amendments are listed at the end with their time.

| Stage | What | Cost |
|---|---|---|
| 0 | Read-only audit of the stored official calls of the blind reference and blind precedence agents. **Done, below** | no simulation |
| 1 | Two blind builds from `briefs/mutations/brief-a-raw.md` + `brief-b-raw.md`, no practice customers: `reference` (v1-fresh) and `reference-v2`. Side by side is fine: a no-practice build starts no simulation | 15-25 min |
| 2 | Each agent: official A x1, B x1, Persona Lab V09, V07, V06 x1. Stop if v2 is 3 or more customers below v1-fresh, or if a veto mechanism (rule 2) is confirmed in every v2 call where it applies | ~25 min |
| 3 | Complete to three runs: A x3, B x3, V09 x3, V07 x3, V06 x3 per agent (96 calls; 18 to 30 simulations, depending on whether the personas share a batch) | ~50 min |
| 4 | `policy_audit` on every call (`--fetch ... --save`, then offline), every violation and wording finding read and marked in a `--review` file; the greeting of each agent read once; findings with no detector read in a sample of detector-negative calls | ~20 min |

v1-fresh is also the replication the first outside audit asked for: a second blind build of `reference`.

### Stage 0 result (2026-10-11, read-only; regenerated offline at 7e4e2a0)

Output: `runs/20261010-212550-blind-ref-ab/eval/policy_audit.txt` (with `policy_review.json`) and
`runs/20261010-212547-blind-prec-ab/eval/policy_audit.txt`. The verdict is the kit's PASS/FAIL (bank record and judge).

| Finding | Class | blind reference | blind lowering-precedence |
|---|---|---|---|
| No goodbye before `close_call` (`NO_GOODBYE`, A47) | violation | 0/39 | 37/39 (unreviewed) |
| No thanks before `close_call` (`NO_THANKS`, A47) | violation | 0/39 | 3/39 (unreviewed) |
| No text-message sentence after recorded promises (`SMS_MISSING`, A38) | violation | **5 of 9 B calls, confirmed** (after the writes only "One moment, please", then goodbye) | 0 |
| "recorded" before the write returned (`RECORDED_EARLY`, A37) | violation | 1, confirmed (read-back "a payment of 540 recorded ... Do you confirm?") | 5 of 9 B calls (unreviewed) |
| More offers than the band allows (`ATTEMPTS_OVER`) | violation | 0 | 2 (PUB-12, kit FAIL) |
| Text-message sentence not word for word (`SMS_NOT_VERBATIM`) | wording | 1, confirmed ("confirming these") | 0 |
| "this call is recorded" in the greeting | judge risk | 39/39 | 39/39 |
| Agent speech after `close_call` started | observation | 0/39 | 39/39 |
| PASS calls with a violation-class finding | | 6 (all confirmed) | 32 (unreviewed) |

Read: the reference build's hidden weakness on the official customers is the confirmation after several promises.
The precedence agent breaks A47 in 37 of 39 calls; in the other two it says goodbye before `close_call` and speaks
again afterwards, and both have an early "recorded".

## Switch rule (revision 2)

Report three dimensions apart, for v1-fresh and v2:

- **D1, official customers**: A (10) and B (3) apart, a customer counts only with 3 of 3 runs.
- **D2, confirmed policy violations**: per mechanism, calls with a confirmed violation-class finding over calls where
  the check applied. Wording (`SMS_NOT_VERBATIM`) and judge risk (`RECORDED_IN_GREETING`) are reported apart and are
  never added to violations. An unreviewed or unclear finding is not a violation and not a clean call either.
- **D3, persona behaviour**: per persona, calls where its trigger happened. An untriggered call is "unexercised": it
  counts neither for nor against.

v2 replaces `reference` only if all of these hold:

1. **Floor (D1)**: v2 has at least 10 of 13 customers 3/3 and at least v1-fresh minus 1. This is an engineering
   tolerance fixed in advance, not a statistical test; the absolute floor (blind reference 11/13 minus one) stops a
   weak v1-fresh build from carrying a weak v2 through.
2. **No regression (D1, D2)**: for each of these, v2 has no more calls than v1-fresh: official calls that fail a
   bank-record check (a `failed` entry not starting with "conversation:"); confirmed `NO_GOODBYE` or `NO_THANKS`;
   confirmed `RECORDED_EARLY`; confirmed `SMS_MISSING`; confirmed `ATTEMPTS_OVER`; confirmed `WEEKDAY`. One more call
   in any of them vetoes v2.
3. **Improvement (D2, D3)**: on the targeted mechanisms (`ITEM_SKIPPED`, `ATTEMPTS_SHORT`, `TODAY_AGAIN`, `ORDER`,
   `SMS_MISSING`, `RECORDED_EARLY`), v2 has fewer calls with a confirmed finding than v1-fresh, and V09 is triggered
   in at least 2 of 3 v2 calls with no confirmed `ITEM_SKIPPED` or `ATTEMPTS_SHORT` in any triggered call.
4. **Greeting**: v2's greeting still says that the call is recorded (Brief A rule 1), read by hand.
5. **Build**: v2's build is accepted by kitrun (exit 0) in at most 20 minutes.
6. **Platform**: runs with platform evidence (`docs/EVAL_PROTOCOL.md`) are repeated; clean failures stay in the count.
7. **Borderline**: a criterion that holds only through a tie or an unclear review counts as not met; `reference` stays.

What the result can not say: whether v2 scores higher on hidden briefs, which of the four instructions helped, or a
one- or two-customer difference. What it can say: whether one fresh v2 build loses the targeted defects without a
regression against one fresh reference build under the same runner, inputs and judge.

## Not planned

- A lowering or lowering-precedence build: both carry defect #1 when the builder uses `say`, and precedence's
  attempts lead on g3 is void (#11).
- New personas, new rules or a new builder architecture before the final.
- Any edit of `reference`, the helpers or `kitrun.py` between the experiment and the final.

## Amendments

- Revision 1 (2026-10-11 04:20): `RECORDED_EARLY` and `SMS_MISSING` added to the mechanisms after stage 0, before any
  candidate call.
- Revision 2 (2026-10-11 05:00): rewritten after the second outside review, before any candidate call: three
  dimensions, confirmed findings only, greeting apart, per-mechanism veto, absolute floor, triggered personas only,
  borderline stays on `reference`; runner `0c59ba3`.
