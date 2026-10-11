# Persona Lab P layer: three agents, eight personas, three reps

Run 2026-10-10 21:46-22:27 UTC (2026-10-11 00:46-01:27 local). 72 calls, one simulation at a time, through
`tools.persona_lab.cli run --live`. These are diagnostics on public customers with adversarial behaviour, not
official or hidden-benchmark scores.

## Agents (unchanged during the comparison)

| Candidate | Agent / workflow | Published version | Export sha256 (all runs) | Official base results |
|---|---|---|---|---|
| blind-ref (reference skill, raw A+B, one agent) | 9bd08f14 / 910582e9 | 1 | 614dad60a15e | A 8/10, B 3/3; PUB-10 1/3 |
| public-ref A (reference-fb88831) | 6a9597ac / fbf21573 | 2 | 1d716daddcb2 | A 10/10 every customer 3/3 |
| public-ref B | 3aa5a39a / 0b8ba909 | 2 | b6bf15bf2410 | PUB-12 0/3 |
| lowering A | b2df668d / 2bf37061 | 4 | 65843e33a598 | A 3/3 every customer |
| lowering B | d6e35cf9 / 01369047 | 4 | c396e579abd8 | PUB-12 2/3 |

Each workflow had one export hash across all its runs; versions and `updatedAt` were the same before and after.

Raw records (ledger, judge, transcript with tool events, simulation and iteration ids, workflow export hash,
persona key) are in `tools/persona_lab/results/` (git-ignored, local only):
`20261011-004613-blindref`, `-005003-publicref`, `-005451-lowering` (rep 1) and
`20261011-010021-blindref-reps23`, `-011127-publicref-reps23`, `-011947-lowering-reps23` (reps 2 and 3).
Persona ids: `state/persona_lab/personas.json`; the same eight personas served all three candidates.

## Results (official layer: ledger scorer + judge)

| Variant (base) | Behaviour | blind-ref | public-ref | lowering |
|---|---|---|---|---|
| V09 (PUB-12) | refuses the personal loan before its turn, annoyed at re-offers | **1/3** | **1/3** (behaviour 0/3) | **0/3** |
| V06 (PUB-10) | "put it in twice" after a failed write | **1/3** | 3/3 | 3/3 |
| V07 (PUB-11) | "start with the car loan", "how much all together?" | 3/3 | 3/3 | 3/3 |
| V01 (PUB-01) | date of birth and phone split over turns, aside | 3/3 | 3/3 | 3/3 |
| V08 (PUB-13) | date in words, distractor date, "latest date?" | 3/3 | 3/3 | 3/3 |
| V04 (PUB-07) | corrected date lands on a holiday, "which day?" | 3/3 | 3/3 | 3/3 |
| V12 (PUB-02) | husband guesses "her loan", presses | 3/3 | 3/3 | 3/3 |
| V02 (PUB-01) | "what is this about?" before the first answer | 3/3 | 3/3 | 3/3 |
| Calls passed | | 20/24 | 22/24 | 21/24 |
| Personas 3/3 | | 6/8 | 7/8 | 7/8 |

INFRA_CONFIRMED 0, INCONCLUSIVE 0. Every non-pass is a judge failure with a correct ledger (`JUDGE_ONLY`); the
ledger can not see attempt counts or wording.

## Failures

### V09: per-product attempts after an out-of-turn refusal (all three agents)

Brief B rule 4: the "all of them today?" question is not an attempt; each product starts at attempt 1 in
`get_account` order. Brief A rule 30: a late-band product gets attempt 1 (full amount, last business day of the
week) and attempt 2 (floor on the deadline). Expected: personal loan 2 attempts, car loan 1.

| Call | What the agent did | Judge |
|---|---|---|
| blind-ref r1 | accepted the early refusal, never offered the personal loan | fail |
| blind-ref r2 | persona garbled its refusal; attempt 1 on the loan, then skipped attempt 2 after "I already told you no" | fail |
| blind-ref r3 | attempt 1 (1320 Friday) and attempt 2 (440 on 23 October) despite the refusal | pass (correct) |
| public-ref r1 | accepted the refusal, never offered the loan; re-asked "today?" per product; notes before the promise | fail |
| public-ref r2 | same as r1: never offered the loan, "today?" per product | **pass (judge miss)** |
| public-ref r3 | same; car loan asked three times (today, Friday, again) | fail |
| lowering r1-r3 | accepted the refusal, never offered the loan | fail x3 |

In the seven failing calls the ledger (one promise, two `refused` notes) is right and the judge fails; in public-ref
r2 both pass although the behaviour is the same as in the failures. The persona performed the early refusal in all nine calls; the "annoyed" act fires only when the
agent re-offers, so its absence marks the skip. Generalizable: the same skip in three builds from two skills, on a
persona that differs from PUB-12 only by when the refusal comes. The base PUB-12 passes 3/3 for blind-ref officially,
so the weakness is the trigger (refusal before the product's turn), not the case.

### V06: "this call is recorded" in the greeting (blind-ref only)

All three blind-ref calls: one silent retry after "service unavailable, nothing was recorded", exactly one promise,
"recorded" said only after `ok: true`. The judge passed r1 ("standard legal disclosure") and failed r2 and r3 on the
greeting "this call is recorded" against the PUB-10 check "agent does not say 'recorded' before a successful call".
The same cause explains blind-ref's official PUB-10 1/3. public-ref ("we are recording this call") and lowering ("we
keep a recording of this call") never hit it. No public check requires the literal words; Brief A rule 1 asks only
to say that the call is recorded.

The persona's act ("put it in twice") needs the agent to say the write failed. blind-ref and public-ref retried
silently, so the act never fired: their V06 runs test the base PUB-10 path only. lowering announced the failure in
all three calls, the persona pressed, and lowering still retried once with no duplicate write: the hypothesis was
tested only on lowering, and it held.

## Deviations the judge did not penalize (ledger correct, all PASS)

| Deviation | blind-ref | public-ref | lowering |
|---|---|---|---|
| V07: first per-product ask follows the customer's "car loan first", not `get_account` order (Brief B rule 4) | 1/3 | 3/3 | 3/3 |
| "Can you pay that today?" re-asked per product (Brief B rule 4), V07/V09 calls | 0 | 6 calls | 1 call |
| V08: says "Thursday 30 October" (a Friday); ledger date correct | 0/3 | 0/3 | 3/3 |
| V07: answers "how much all together?" with one product's amount instead of the total | 1/3 | 0/3 | 0/3 |

Counted from the stored transcripts (V07 order by the amount offered in the first ask after the request).

## Platform and simulator observations

- Simulation `c14ee185` (blind-ref rep 2, A batch): after completion and after the runner read pass/fail/pass, the
  iteration runs for V01, V06, V12 were reset to `inconclusive` with `endedAt` empty and `startedAt` at the moment the
  next simulation started (22:06:44-50). The calls' own `successCriteriaResult` and transcripts are identical to the
  stored records. The stored verdicts stand. Same pattern once before (`ca87d44d`, 20:23). If official scoring reads
  iteration runs, this is a platform risk to report.
- Model latency: nine records with a median slowest agent turn above 10 s; eight passed, and the one failure (lowering
  V09) matches its two fast failures.
- Simulator artifacts that did not change a verdict: a persona repeating a cut-off sentence six times, the user
  token "探案", a leaked "**I cannot pay today" fragment.

## Reading

- Best on these personas: public-ref by calls (22/24), but its one V09 pass is a judge miss, and it has the most
  judge-unpenalized rule deviations. blind-ref has the cleanest rule compliance (order kept 2/3, no "today?" re-ask,
  the only correct V09 run) and loses two calls to its greeting wording. lowering is solid on single-product personas
  and 0/3 on V09, with a deterministic weekday error.
- The differences between candidates are mostly build-to-build variation (wording, retry announcement), not skill:
  blind-ref and public-ref come from nearly the same skill.
- Two findings recur across builds and are cheap to state in general terms:
  1. A volunteered or out-of-turn refusal is an input to that item's step, not a replacement for it: every item
     still gets its own attempt sequence when its turn comes, and attempt 2 is not skipped because the customer is
     annoyed.
  2. Words that a brief allows only after an event (here "recorded") should not appear earlier in any form, including
     a mandated disclosure; paraphrase the disclosure.
- Neither is proven to improve the Builder until a build with the change passes the official A and B runs and V09/V06
  three times each.

## Found after this write-up (2026-10-11 morning)

An independent audit of the stored calls, re-checked here against the raw records with their timestamps, found what
the judge passed and this write-up missed. `tools/evaluation/policy_audit.py` now checks every stored call; it
reproduces the counts above and these:

| Finding (`policy_audit` code) | Rule | blind-ref | public-ref | lowering |
|---|---|---|---|---|
| Goodbye spoken after `close_call` started (`SPEECH_AFTER_CLOSE`) | A47 | 0/24 | 0/24 | **24/24** (21 judge PASS) |
| "recorded" in the greeting (`RECORDED_IN_GREETING`) | A1/A37 | 24/24 | 0/24 | 0/24 |
| No text-message sentence after a recorded promise (`SMS_MISSING`) | A38 | 1 (V08 r1, judge PASS) | 0 | 0 |
| Product skipped (`ITEM_SKIPPED`) or attempt 2 dropped (`ATTEMPTS_SHORT`) | B4/A30 | 1 + 1 | 3 | 3 |
| "today?" asked again (`TODAY_AGAIN`) | A28/B4 | 0 | 6 | 1 |
| First per-product ask out of `get_account` order (`ORDER`) | B4 | 1 | 3 | 3 |
| Weekday does not match the date (`WEEKDAY`) | dates | 0 | 0 | 3 |

27 of the 72 calls are judge PASS with at least one finding (the greeting finding not counted).

The lowering close order is deterministic: `builder/lower.py:328` puts the closing line on the `api_request` step whose
`pre_actions` run `close_call`, and the call record has the line after the tool (V01 r1: `close_call` at 15.48 s, the
goodbye at 15.59 s). The blind lowering-precedence agent was not run here, but its export has the same closing steps.
The line "lowering is solid on single-product personas" in "Reading" holds for the ledger and the judge, not for the
brief.

Labels: the `-reps23` batches store their reps as 1 and 2; they are reps 2 and 3 of each cell (`policy_audit` and the
tables here use 1 to 3).

## Limits

Three reps per cell; 1/3 against 0/3 is not a reliable difference. A persona is a prompt to the simulator, not a
script. Public customers only; the final has hidden briefs and customers. Diagnostics D01 and D02 were not run.

## Tooling change

`tools/persona_lab/runner.py` `baseline()` skipped JSON files that are lists (`runs/*/eval/classified.json`); before
the fix the report step crashed after the raw records were written.
