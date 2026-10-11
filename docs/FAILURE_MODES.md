# Failure modes: source, evidence, detector, action (2026-10-11)

One table from symptom to cause, so that a known error is not paid for twice. Every row names its evidence and the
check that finds it again. Sources: the run records under `runs/`, the Persona Lab raw records
(`tools/persona_lab/results/`, git-ignored), the independent audit of 2026-10-11 (bundle of commit fe8bd5b; its
claims were re-checked against the raw records), and EVRE (last section).

## Six sources of a failed or misleading result

Classify a failure before acting on it. The action depends on the source, not on the symptom.

| Source | Typical sign | Action |
|---|---|---|
| Builder skill or helper | The same defect in every call of every build of that configuration | Fix in the skill or helper; find it with a static or transcript check |
| Agent at runtime | The agent does it in some calls, not others | Carry the rule in structure (step, route, fixed line, code); measure with repeats and a persona that triggers it |
| Judge | The verdict does not follow from the transcript (passes a violation, fails a compliant call) | Read the transcript; never optimize to one verdict; avoid wording that triggers a known misjudgement |
| Simulator persona | The persona's act never fired | The call did not test the hypothesis; do not count it as evidence for it |
| Platform | Sandbox errors, silent stalls, API 503, runs reset to "inconclusive" | Exclude only by evidence fixed in advance; keep clean failures |
| Our own inputs and fixtures | A test brief or answer key contradicts itself | Fix or void the fixture; do not rank builders on it |

## Catalog

`policy_audit` is `tools/evaluation/policy_audit.py`; its counts over the 72 Persona Lab calls are in
`docs/PERSONA_LAB_P_RESULTS.md`.

| # | Failure | Source | Mechanism | Evidence | Detector | Action, status |
|---|---|---|---|---|---|---|
| 1 | Goodbye and "recorded" spoken after `close_call` (Brief A rule 47) | Helper `builder/lower.py:328`, deterministic | The closing line is the `on_enter` text of the `api_request` step whose `pre_actions` run the terminal tool; the call record puts the line after the tool | lowering agents: 24/24 Persona Lab calls, 21 judge PASS. Blind lowering-precedence: 39/39 official calls (`runs/20261010-212547-blind-prec-ab/eval/policy_audit.txt`) | `SPEECH_AFTER_CLOSE` | `reference` and `reference-v2` say the goodbye in a separate step before the terminal step (blind-ref 0/24). `lower.py` stays frozen until after the final; any lowering skill inherits the defect |
| 2 | Product skipped, or attempt 2 dropped, after a refusal said before the product's turn (V09) | Skill: per-item attempts held in prompt prose; runtime variance | The early refusal is taken as the product's outcome | V09: 8 of 9 calls deviate on three agents from two skills; public-ref r2 judge PASS on a skip | `ITEM_SKIPPED`, `ATTEMPTS_SHORT` | `reference-v2` rule; measure V09 x3 |
| 3 | "Can you pay today?" asked again per product (Brief B rule 4) | Build variance (public-ref build) | The first ask sits inside the per-product loop | public-ref 6 calls, lowering 1, blind-ref 0 | `TODAY_AGAIN` | `reference-v2` rule |
| 4 | Product order follows the customer's request instead of `get_account` order (Brief B rule 4) | Build variance | Same as 3 | V07: blind-ref 1/3, public-ref 3/3, lowering 3/3, all judge PASS | `ORDER` | `reference-v2` rule |
| 5 | "This call is recorded" in the greeting judged as an early "recorded" (Brief A rules 1 and 37) | Judge, triggered by our wording | The judge applies PUB-10's check to the disclosure | blind-ref: V06 2/3 FAIL, official PUB-10 1/3; agents that said "we are recording" never hit it | `RECORDED_IN_GREETING` | `reference-v2` rule: a reserved word stays out of fixed lines |
| 6 | Text-message sentence (and the "recorded" confirmation) missing after recorded promises (Brief A rules 37, 38) | Runtime variance, frequent after several writes | After the writes the agent says only "One moment, please", then goodbye | Blind reference agent: 5 of 9 official B calls (`runs/20261010-212550-blind-ref-ab/eval/policy_audit.txt`); Persona Lab 1 of 63 promise calls; all judge PASS | `SMS_MISSING` | `reference-v2` rule: word-for-word sentences as written; a fixed line after the last write removes the variance |
| 7 | Wrong weekday ("Thursday 30 October 2026", a Friday) | Build (date label) | The weekday was written by the model, not computed | lowering V08 3/3, judge PASS | `WEEKDAY` | Labels from code (`now`-based); `dryrun.py` with dated samples |
| 8 | Account step sends real customers down the "cannot see your account" path | Skill: in-build check loop without customers | A chat test with a made-up id fails at the bank; the builder "fixed" the account step | selfcheck: A 3/10 (`runs/20261010-223940-blind-selfcheck-ab/RESULT.md`) | Official runs | No in-build fixing on signals that real calls do not produce; selfcheck rejected |
| 9 | Build over 30 minutes | Skill complexity | Counted rules and attempt ladders as graph structure | counted-rules 1902 s, ladder 1882 s | `summary.json` build time | Keep skills short; structure only where it is cheap |
| 10 | Sandbox errors, silent stalls, API key 503, dashboard resets finished runs to "inconclusive" | Platform | | `runs/20261010-161811-candidate-ab/eval/OUTAGE.md`, `docs/PLATFORM_NOTES.md`, simulation c14ee185 | `classify.py`, Persona Lab triage `INFRA_CONFIRMED`, the call's `successCriteriaResult` | Exclusion rule in `docs/EVAL_PROTOCOL.md` |
| 11 | Test fixture contradicts itself | Our fixture | g3 sets attempts to 2/3 in the table, while rule 30 still names only attempt 1 and attempt 2 | `tools/persona_lab/generated/blind/g3-limits-raw/inputs/pl-g3-limits-raw.md` | Manual review | g3's attempts result is void for both skills; fix the fixture after the final |
| 12 | Raw Brief B says "two or three products" in the e-mail and "one to three" in the notice | Our mutation | Rewording changed a fact | `briefs/mutations/brief-b-raw.md:15-19` vs `:29-33` | Manual review | No effect on official scoring; fix after the final |
| 13 | The builder can read the repository outside its workspace | Runner isolation | kitrun sets the working directory; nothing blocks `cd ..` | g7 build listed the repo root and `runs/`; its grep failed, no file content was read | Search the trace for paths outside `workspace/` | Accepted risk; check each final trace |
| 14 | A result of one configuration reported as another | Our reporting | The official 12/13 came from `reference-fb88831` (practice access), not from `reference`; "A 10/10 every customer 3/3" is the rerun triple after a stall, with PUB-07 3/5 and PUB-05 4/5 over all clean runs | `runs/20261010-161811-candidate-ab/summary.json`, `eval/a-official-3reps.log` | Configuration identity in every result row | Docs corrected 2026-10-11 |
| 15 | "recorded" said before the write returned (Brief A rule 37) | Wording in prompts (read-back "I have ... recorded. Do you confirm?", "We have recorded those payments" before `create_promise`) | The model uses the reserved word for a planned write | Blind reference: 1 of 30 official A calls; blind lowering-precedence: 5 of 9 official B calls | `RECORDED_EARLY` | `reference-v2` rule: a reserved word is used for nothing but the event |

## Why known errors kept costing us

1. **What we measured could not see them.** The ledger sees writes; the judge gives one verdict per call. 27 of the
   72 Persona Lab calls were judge PASS and still broke a brief rule (`policy_audit`, greeting wording not counted);
   on the stored official calls, 6 of 39 for the blind reference agent and 32 of 39 for blind lowering-precedence.
   Every such deviation was found by reading transcripts by hand, late, and some only by the outside audit.
2. **A change set held several changes.** selfcheck added a check loop and three rules at once; when it fell to 6/13
   the cause could only be inferred (the loop). One change set per candidate, compared with a fresh build of the
   baseline, keeps the cause visible.
3. **Results of different configurations were merged in the docs.** Practice access, helper versions and reruns change
   the configuration; a reader took the best number for the frozen skill.
4. **Single-build differences were read as skill differences.** Wilson 95% intervals: 11/13 is 0.58-0.96, 9/13 is
   0.42-0.87, 6/13 is 0.23-0.71. All overlap. Counts from one build per skill cannot rank skills; mechanisms can.
5. **A shared helper spreads its defect.** `lower.py` is copied into every `--skill` workspace and wrote the closing
   line after the terminal tool for every lowering skill. The static checker proves graph properties; it cannot see
   what is spoken when.
6. **Rules held in prose hold most of the time.** Three repeats on the official customers rarely show a 1-in-3
   failure; a persona built to trigger it (V09) does.

## Engineering preference

How to carry a brief rule into the agent, in order of preference:

1. **Graph structure the engine enforces**: a separate step, a route on a tool result, the terminal tool alone in its
   step, a fixed `on_enter` line. Deterministic and checkable statically. Use it for the order of actions, for
   sentences said at a fixed point, and for closing.
2. **A code step** for computed values: dates, deadlines, amounts, weekday labels. Check with `dryrun.py` on `now`
   samples.
3. **Prompt prose** for judgement inside the conversation: classifying a customer's answer, handling an interruption.
   It varies between calls; measure it with repeats and a persona that triggers it.

Structure costs build time (counted-rules and ladder timed out), so it goes where the rule is about order or a fixed
sentence. Counts and per-item loops stay in prose with an explicit rule and are measured with `policy_audit`.

How to measure:

- Deterministic transcript checks first (`policy_audit`), then the judge. A judge verdict is one observation.
- Keep every call's transcript, ledger and events for every run, so a new check can be applied to old runs.
- Compare a candidate with a fresh build of the baseline in the same session, on the same customers, with the same
  judge. Write the decision rule before the run.
- Decide on mechanisms (a defect present in every call, gone in the candidate) and on non-inferiority of the official
  runs, not on a one- or two-customer difference.
- Exclude a run only on platform evidence named in advance; never replace a clean failure with a rerun.

How to change the builder:

- One change set per candidate, in its own skill directory; the frozen baseline stays byte-identical.
- The configuration is the skill sha256, the helpers kitrun copies (`workflow_check.py`, `lower.py`, `dryrun.py`), the
  runner commit and practice access. Change none of them between the measured run and the final.
- A fix found on one persona is written in general terms: no case id, no brief value, no bank name. Kit rule: nothing
  from a final brief goes into the builder.

## Borrowed from EVRE

EVRE (`mmf-code/evre-hybrid-ai-simulator`, read at `origin/master` f9d78669, equal to GitHub master on 2026-10-10;
the local working tree differs, so read master). Two ideas were already in use before today: graph lowering
(`lower.py`) and persona programs (`tools/persona_lab/acts.py`).

| EVRE mechanism | Where | Applied here |
|---|---|---|
| The model reports observations with verbatim quotes; code checks each quote (exact substring, speaker, turn window, "before" a given turn) and an ordered decision table gives the verdict; a missing component is "unclear", never "absent" | `lib/server/observedMeasurement/verify.ts`, `decision.ts` | `policy_audit` prints the sentence and time behind every finding; speak-then-act is an order check on recorded times |
| An out-of-turn event raises an interrupt, runs one repair step, and the run resumes at the item the engine had scheduled; shortcut exits are blocked until a beat's minimum turns (the "G1" fix: an early threshold skipped the whole arc) | `lib/server/cueResponseProgression.ts`, `lib/server/beatStateMachine.ts:1326-1340` | The V09 rule in `reference-v2`: an early statement about an item does not shorten that item's steps |
| Prompt counts ("2-4 rules") were ignored by the model; the count became a coverage check on the model's own output | `docs/reports/2026-08-09-reconvergence-is-a-capability-gap.md` | Same lesson as V09: a count held in prose needs a check (`ATTEMPTS_SHORT`, `ATTEMPTS_OVER`) |
| Small samples: matched cells, Wilson 95% intervals, no improvement claimed when intervals overlap, a held-out brief, the same judge model on both sides | `docs/reports/2026-08-05-graph-plan-rewrite-acceptance.md`, `researchHarness/comparisonPolicy.ts` | Decision rule in `docs/EVAL_PROTOCOL.md` and `docs/REFERENCE_V2.md` |
| Judge calibration gates: the same input judged 10 times (flip rate at most 5%), trap and control inputs; deterministic, versioned re-scoring of stored transcripts | `lib/shared/competency/measurement/calibration.ts`, `evre-audn-eval/docs/experiments/audn-measurement-design.md` (branch `exp/audn-eval`) | `policy_audit` re-scores stored calls; a judge stability probe is not built (the Freya judge is not ours to re-run) |
| Runs that ended in error or with an empty transcript are never scored; quarantine is an append-only decision; retryable and deterministic failures are separate classes | `researchHarness/simulationResultPolicy.ts`, `messageIssues.ts`, `scenarioAuthoring/failureTaxonomy.ts` | Exclusion rule in `docs/EVAL_PROTOCOL.md`; the six sources above |
| Compiler checks on generated graphs: every consumed flag has a producer on a path to it, two unconditional exits from one node, every node reaches a terminal, ambiguous route ties, impossible thresholds; a failure names the phase to repair | `lib/server/scenarioAuthoring/compiler.ts`, `routingDecidability.ts`, `specPhases.ts` | Candidates for `workflow_check.py` after the final: "variable read before any step sets it" and "two `always` transitions" are cheap. Not added now: the checker is part of the frozen configuration |
