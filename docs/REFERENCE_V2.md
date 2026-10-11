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

Both arms run with the runner of commit `560ccfe` (kitrun's acceptance decision hardened in `7e4e2a0`; its trust
boundary tightened in `c077158`, `0c59ba3` and `560ccfe` after security reviews; see `docs/FAILURE_MODES.md` #16). What the builder sees is unchanged since `fe8bd5b`: workspace layout, skill handling and helpers
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

## Revision 3: a third arm, reference-v3 (2026-10-11 12:50, before any v3 build or call)

`builder/skills/reference-v3/SKILL.md` (sha256 `62c464d98486`) is `reference-v2` plus two general instructions taken
from the best measured build (blind reference of 2026-10-10, 11/13, PUB-07 3/3 and PUB-12 3/3):

| Added instruction | Why |
|---|---|
| Work out every date, weekday and count in a code step and give them to the prompt as text: a table of the coming days (words a customer may use, allowed or not, the day to offer instead) and per item its stage, attempts and what each attempt offers, with an explicit "no further attempt" | That build had exactly these tables (`date_table`, `product_plan`) by its own choice. Builds without them failed PUB-07 (holiday, then next business day) 11 of 25 calls and PUB-12 (attempts per band) 11 of 22 over all stored official runs |
| Cases the brief puts before others (hardship, dispute) are checked first on every customer answer | PUB-05 (job loss, then persuasion anyway) failed in both arms of stage 2 with the right text in the prompt; the order of checks was not stated |

Measurement when the platform is healthy (API probe under 5 s): build v3 with a fresh `--state`; then rounds of
official A and B for v1-fresh, v2 and v3, interleaved, until each has three runs (v2's void B run is repeated); then
V09, V07, V06 per agent as time allows. Each of v2 and v3 is judged against v1-fresh by the switch rule above. If both
pass, the one with fewer confirmed violations wins, then the one with more official customers 3/3; a tie goes to v2
(the smaller change). If neither passes, `reference` stays. Measurement stops at 17:00 whatever is done.

Stage 2 so far (one run each, slow platform: median slowest agent turn 9-18 s against 2 s on 2026-10-10): v1-fresh
A 9/10, B 1/3; v2 A 7/10, B void (403 on reading the simulation, then the simulation hung); personas not started
(API outage 12:38-12:46).

## Outcome: stopped at 14:28, not enough data; the final uses `reference`

The simulation service failed most of the afternoon: create requests answered 504, polls 503 and 504, two simulations
hung (cancelled with `POST /api/v2/simulations/{id}/cancel`), one never started its calls. Ten official runs were lost
to it; each log is kept as `*-void*.log` in the arm's `eval/`, and runs stopped by hand as `*-stopped.log`. No persona
run started.

| Arm | Build | Official A | Official B | Personas |
|---|---|---|---|---|
| v1-fresh (`reference`) | accepted, 550 s | 9/10 (one run; PUB-05 hardship) | 1/3 (one run; PUB-12 not closed, PUB-13 card date) | none |
| v2 | accepted, 563 s | 7/10 (one run; PUB-03 identity loop, PUB-05, PUB-06 floor twice) | none (three attempts lost to the platform) | none |
| v3 | accepted, 705 s | none | none | none |

The agent was slow in every completed run (median slowest turn 9 to 18 s, against 2 s on 2026-10-10), which the kit
warns lowers scores. With one run per customer and no personas, no criterion of the switch rule can be applied: by rule
7 the final stays on `reference`. What did come out: a fresh `reference` build put the goodbye on the terminal step
(defect #1, which the 2026-10-10 build avoided by chance), and v2 and v3 built the per-product and separate goodbye
steps they ask for (static reading of the exports).

## Healthy rounds, 2026-10-11 16:10-17:15: the switch rule fails; the final uses `reference`

The organisers called the services stable at about 16:00. Official A and B were run twice per arm (rounds h1, h2,
interleaved, one simulation at a time), then V09, V07, V06 once per arm, then a third official round for v1-fresh and
v2 only (approved at 16:45; v3 left out after its build defect below). Files: `runs/<arm>/eval/c-{a,b}-official-h{1,2,3}.*`,
`policy_review-h.json` and `policy_audit-h.txt` (official), `policy_review-persona-h.json` and
`policy_audit-persona-h.txt` (personas); persona records in `tools/persona_lab/results/*-c-v{1,2,3}-h`.

The platform was slow in most runs: median slowest agent turn per run 3 to 29 s, over 5 s in 11 of 15 valid runs
(2 s on 2026-10-10). The kit warns that this lowers scores; it hit all arms.

D1, official (a customer counts only if it passed every run):

| Arm | A h1 | B h1 | A h2 | B h2 | A h3 | B h3 | Customers 3/3 | Failing customers and why |
|---|---|---|---|---|---|---|---|---|
| v1-fresh (`reference`) | 9/10 | 3/3 | 7/10 | 3/3 | 8/10 | 3/3 | **10/13** (A 7/10, B 3/3) | PUB-05 0/3 (hardship: refused instead of hardship, persuasion after the job loss, support offered twice), PUB-10 1/3 (h2: judge says "recorded" before the write, the transcript has it after the successful retry, a judge error; h3: "this call is recorded" in the greeting judged as an early "recorded", #5), PUB-06 2/3 (no "the rest stays overdue" note) |
| v2 | 10/10 | 1/3 | 9/10 | 2/3 | 10/10 | 1/3 | **10/13** (A 9/10, B 1/3) | PUB-12 0/3 (h1, h3 two asks for the one-attempt car loan; h2 silent call), PUB-13 1/3 (h1 silent call, h3 loan date 16 instead of 23 October), PUB-03 2/3 (security check not ended at the third wrong answer) |
| v3 | 8/10 | void | 8/10 | 3/3 | - | - | 9/13 from two A runs and one B run | PUB-01 1/2 and PUB-10 1/2 (silent after the write, #17), PUB-05 1/2 (support offered twice), PUB-06 1/2 |

v3's B h1 is void by the platform rule (`docs/EVAL_PROTOCOL.md`): two of its three calls went silent after the
customer's first answer, with no tool call and no model output. Four silent calls without any error event happened in
all, all in v2 and v3 (none in v1-fresh's 39), each right after entering a step with `on_enter_first_entry_only`
true; v1-fresh's opening step has it false. That link is a hypothesis: v2 and v3 passed the same opening step in 50
A calls without a stall. The two in v2 are one call of three in their runs, so they stay as failures.

D2, confirmed `policy_audit` findings over calls where the check applied (every violation finding read and marked):

| Mechanism | v1-fresh (39 calls) | v2 (39) | v3 (23) |
|---|---|---|---|
| `NO_GOODBYE` (A47) | **39/39** | 0/37 | 0/21 |
| `NO_THANKS` (A47) | 3/39 | 0/37 | 0/21 |
| `RECORDED_EARLY` (A37) | 0/39 | **2/39** ("I have recorded your promise/payment ..." before the first write; one kit PASS, one kit FAIL) | 0/23 |
| `ATTEMPTS_OVER` | 0/5 | **1/2** (car loan 7 days late, two offers; kit FAIL) | 0/1 |
| `SMS_MISSING` (A38) | 0/24 | 0/22 | **2/13** (silent after the write) |
| `ATTEMPTS_SHORT`, `ITEM_SKIPPED`, `TODAY_AGAIN`, `ORDER`, `WEEKDAY` | 0 (one `ATTEMPTS_SHORT` read as a false positive) | 0 | 0 |
| Bank-record failures (a `failed` entry not starting with "conversation:") | 2 | 3 | 2 |
| "this call is recorded" in the greeting (judge risk, apart; unreviewed) | 39/39 | 0/39 | 0/23 |

D3, personas, one call each (judge verdict, then confirmed findings):

| Persona | Triggered | v1-fresh | v2 | v3 |
|---|---|---|---|---|
| V09 (refuses the personal loan before its turn) | 1/1 in every arm | FAIL; `ITEM_SKIPPED` (no offer for the personal loan), `NO_GOODBYE` | FAIL (two asks for the one-attempt car loan); `RECORDED_EARLY` ("I have recorded your payment ... Goodbye." before the write), `TODAY_AGAIN`. The V09 target held: two offers for the personal loan | PASS, no finding |
| V07 ("start with the car loan") | 1/1 in every arm | PASS; `NO_GOODBYE` | PASS; `ORDER` (car loan asked first) | PASS, no finding |
| V06 ("put it in twice") | 0/1 in every arm, unexercised | PASS; `NO_GOODBYE` | PASS | PASS |

Rule check for v2 (v3 fails rule 2 on `SMS_MISSING` and on bank-record failures, and has the build defect below):

| Criterion | Result |
|---|---|
| 1 Floor (at least 10/13 3/3 and at least v1-fresh minus 1) | Met: 10/13 against 10/13 |
| 2 No regression | **Veto**: `RECORDED_EARLY` 2 against 0, `ATTEMPTS_OVER` 1 against 0, bank-record failures 3 against 2 |
| 3 Improvement | Not met: calls with a confirmed finding on the targeted mechanisms, official and personas, v2 3 (`RECORDED_EARLY` x2, one of them with `TODAY_AGAIN`; `ORDER`) against v1-fresh 1 (`ITEM_SKIPPED`); V09 ran once per arm, so "triggered in 2 of 3" cannot hold |
| 4 Greeting | Met ("kept as an audio recording") |
| 5 Build | Met (563 s, accepted) |

By rules 2 and 3 the final stays on `reference`. What v2 did fix is real and is kept for after the final: no goodbye
after `close_call`, no "recorded" in the greeting, PUB-05 3/3 against 0/3, the V09 personal loan offered twice, PUB-10 3/3 against 1/3 (both v1-fresh failures there are judge errors or the greeting word). What
it broke is in the brief's confirmation and attempt rules: "recorded" said before the write in three calls (two of
them kit PASS), two asks for a one-attempt product in both PUB-12 runs that got that far. Four rules in one change set brought new
failures; after the final, one rule per candidate.

v3's build defect (`docs/FAILURE_MODES.md` #17): its `record_promise` step is a conversation step told to say nothing;
after `create_promise` the model returned no speakable content and the call went silent (3 of 10 calls of A h1, 1 of 10
of A h2).

What this means for the final: `reference` stays, and v1-fresh shows its weak spot again, the goodbye after the
terminal tool in every call (#1). Half of the stored `reference` builds have it and half do not, and it is visible in
the export, so the final runs two builds per brief and submits a clean one (`docs/FINAL_RUNBOOK.md`,
`tools/evaluation/closing_check.py`; decided 2026-10-11 16:40).

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
  borderline stays on `reference`; runner `560ccfe`.
