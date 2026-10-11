# Builder candidates (state at 2026-10-11, 17:45 UTC+3)

There is one runner. Every candidate below runs the kit's example builder `examples/agent_builder.py` unchanged
(Claude Agent SDK, model `claude-opus-5-5`) through `builder/kitrun.py`; the candidates differ only in the skill text
and in which helper tools kitrun copies into the workspace. They are skill variants, not independent builders.

## How a candidate is run

```
.venv/bin/python -m builder.kitrun BRIEF.md [BRIEF.md] --tools OPENAPI.json --label NAME \
    --skill builder/skills/<candidate> --state state/<unique-dir> --minutes 30
```

- `--skill DIR` replaces the kit's `build-phone-agent` skill in a fresh copy of the kit (`runs/<stamp>-<label>/workspace`)
  and adds `tools/check_workflow.py` (= `builder/workflow_check.py`), `tools/lower.py` and `tools/dryrun.py`.
  Without `--skill` the kit builder runs with the kit's own skill.
- `--state DIR` keeps the run's Freya slot and persona ids apart. Without it every run shares `state/`, and two runs
  on the same brief file name update the same Freya workflow. Always pass a fresh directory for experiments.
- Practice customers are given only for briefs identical to a kit brief. A changed brief gets none, as a hidden one.
- kitrun writes `trace.txt`, `trace.jsonl`, `summary.json`, the export of every saved workflow, static checks with the
  builder's contract, and (for lowering skills) whether the saved endings are the lowered ones. The skill's sha256
  prefix is in `summary.json`.

## Candidates

| Skill dir | Source commit | sha256 | What it adds | Status |
|---|---|---|---|---|
| (none: kit skill) | kit v3 | n/a | nothing | Reference from the kit |
| `reference` | 92a695a | 7659a7bd2e6c | Terminal-tool ordering in the graph, static check before every save, no practice test when the brief has none | **Recommended** |
| `reference-v2` | 2026-10-11 | 999681cea4e0 | `reference` + four general rules: closing speech before the terminal step, per-item steps not shortened by early statements, a once-for-all question outside the item loop, word-for-word sentences and reserved words | Not used: failed the switch rule on 2026-10-11 (`docs/REFERENCE_V2.md`, "Healthy rounds"); its closing and greeting are kept for after the final |
| `reference-v3` | 55188de | 62c464d98486 | `reference-v2` + dates and per-item attempt plans computed in code, priority cases checked first | Not used: goes silent after a write (`docs/FAILURE_MODES.md` #17) |
| `reference-fb88831` | fb88831 | 8b8e4ba58d1f | `reference` without the no-practice rule of step 6: always runs the practice test. Built the best official agents (A 6a9597ac) | Kept to reproduce run 161811 |
| `counted-rules` | d4bc3c1 | 5d6669717e9e | Counted and ordered rules kept in code steps | Rejected: timed out; design multiplied sandbox exposure |
| `lowering` | 959453c | ad17c5b808d7 | Endings declared in a plan and written by `tools/lower.py` | Experimental; the measured builds said thanks and goodbye after `close_call` (below) |
| `lowering-precedence` | 4e8f616 | c401cbfb82b2 | `lowering` + endings decided by tool results (`precedence`) | Experimental; the measured build has the same closing steps and the same defect |
| `ladder` | 8fc6afc | b53b9768aef7 | `lowering` + counted attempts per item as steps | Rejected: timed out |
| `selfcheck` | 95d4d00 | 64896af74fcb | `reference` + a no-practice check loop and three general rules | Rejected: regressed in blind test |

Old paths in run records: `builder/skills/build-phone-agent/` held fb88831, then 92a695a, then d4bc3c1 (now
`counted-rules/`). `builder/skills/build-phone-agent-lowering/` held the lowering skill (959453c), then the ladder
(8fc6afc), then lowering only again (2bfad75), then lowering + precedence (4e8f616, now `lowering-precedence/`).
`build-phone-agent-selfcheck/` is now `selfcheck/`. The blind reference run used a scratchpad copy of 92a695a. In
every case the sha256 in the run's `summary.json` identifies the skill.

Tool versions: kitrun copies the repo's current `workflow_check.py`, `lower.py` and `dryrun.py` into every `--skill`
workspace, whatever the skill uses, and builders do read them (the blind reference build read `lower.py`). Runs used
the tools of their commit: lowering runs before 4e8f616 had no `precedence`; the precedence run used `lower.py`
before 49de20a (one unreachable router, a warning); runs before 0000450 had no `dryrun.py`.

## All builds in order (2026-10-10 to 2026-10-11)

Times are local (UTC+3), from the run stamp. "A" and "B" are the official customers (10 and 3); a customer counts
only if it passed every run, and the column says how many runs that is. "Closing" is `closing_check.py` on the export:
SPEAKS means a line is spoken after the terminal tool (#1); "model" means the model calls `close_call` itself, which
the static check does not judge. Policy findings: **confirmed** were read and marked; the rest are unreviewed triage
counts (calls with the finding / calls where it applied), claims to read, not results.

| # | Run (time) | Skill (sha256) | Inputs, practice | Build | A | B | Personas | Closing | Policy findings | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `20261010-kit-builder-brief-a` | kit skill | official A, before kitrun | ? | not measured | - | - | - | - | Historical |
| 2 | `154045-kit-ab` (15:40) | kit skill | official A+B, practice | 976 s | not measured | 2/3 (3 runs; PUB-12 2/3) | - | no contract | unreviewed: `WEEKDAY` 1/9 | Kit baseline |
| 3 | `161811-candidate-ab` (16:18) | `reference-fb88831` (8b8e4ba58d1f) | official A+B, practice | 654 s | 10/10 (rerun triple; clean runs before 9/10, 8/10) | 2/3 (PUB-12 0/3) | P layer "public-ref": 22/24 calls, 7/8 personas | clean | unreviewed: `RECORDED_EARLY` 1/39, `TODAY_AGAIN` 2/9, `ORDER` 1/9, `ATTEMPTS_SHORT` 1/3, `ATTEMPTS_OVER` 1/3 | Best official result (12/13), but it used practice customers; in hidden-brief mode it is `reference` |
| 4 | `171132-candidate-a-raw` (17:11) | `reference` (7659a7bd2e6c) | raw A, none | 348 s | 5/10 over 3 runs (one run with sandbox errors; 9/10 and 10/10 in the others) | - | - | **SPEAKS** | unreviewed: `NO_GOODBYE` 30/30, `NO_THANKS` 2/30 | First blind `reference` build |
| 5 | `172700-candidate2-ab` (17:27) | `counted-rules` (5d6669717e9e) | official A+B, practice | 1902 s, **timed out** | - | - | - | SPEAKS | - | Rejected |
| 6 | `185544-lowering-ab` (18:55) | `lowering` (ad17c5b808d7) | official A+B, practice | 1382 s | 10/10 (3 runs) | 2/3 (PUB-12 2/3) | P layer: 21/24, 7/8 | **SPEAKS** | `NO_GOODBYE` 24/24 persona calls (read); official unreviewed: `NO_GOODBYE` 39/39, `ATTEMPTS_OVER` 1/3, `WEEKDAY` 2/24 | Experimental; closing defect |
| 7 | `201333-ladder-ab` (20:13) | `ladder` (b53b9768aef7) | official A+B, practice | 1882 s, **timed out** | - | - | - | SPEAKS | - | Rejected |
| 8 | `204555-blind-raw-ab` (20:45) | `lowering` (ad17c5b808d7) | raw A+B, none | 404 s | 6/10 (3 runs) | 2/3 | - | **SPEAKS** | unreviewed: `NO_GOODBYE` 6/39, `SMS_MISSING` 5/24, `ATTEMPTS_OVER` 3/3 | Blind 8/13 |
| 9 | `212547-blind-prec-ab` (21:25) | `lowering-precedence` (c401cbfb82b2) | raw A+B, none | 501 s | 8/10 (3 runs) | 1/3 | - | **SPEAKS** | unreviewed: `NO_GOODBYE` 37/39, `RECORDED_EARLY` 5/9 B, `ATTEMPTS_OVER` 2 | Blind 9/13 |
| 10 | `212550-blind-ref-ab` (21:25) | `reference` (7659a7bd2e6c) | raw A+B, none | 887 s | 8/10 (3 runs) | 3/3 | P layer "blind-ref": 20/24, 6/8 (V09 1/3, V06 1/3) | clean | **confirmed**: `SMS_MISSING` 5/9 B, `RECORDED_EARLY` 1/30; greeting judge risk 39/39 | **Best blind result (11/13)** |
| 11 | `223940-blind-selfcheck-ab` (22:39) | `selfcheck` (64896af74fcb) | raw A+B, none | 856 s | 3/10 (3 runs) | 3/3 | - | model | unreviewed: `ATTEMPTS_SHORT` 3/3, `RECORDED_EARLY` 1/39, `TODAY_AGAIN` 1/9, `WEEKDAY` 1/19 | Rejected (6/13) |
| 12-25 | `234909` to `001313` (23:49-00:13) | `reference` x7, `lowering-precedence` x7 | Persona Lab blind scenarios g3, g5, g6, g7, none | 370-695 s | - | - | graded offline (table below) | reference: 4 clean, 3 SPEAKS; precedence: 7 SPEAKS | - | Generalization check |
| 26 | `20261011-120034-c-v1-fresh` (12:00) | `reference` (7659a7bd2e6c) | raw A+B, none | 550 s, accepted | 7/10 (3 runs) | 3/3 | V09 FAIL, V07 PASS, V06 PASS (not triggered) | **SPEAKS** | **confirmed**: `NO_GOODBYE` 39/39, `NO_THANKS` 3/39, `ITEM_SKIPPED` V09; greeting judge risk 39/39 | Today's baseline, 10/13 |
| 27 | `120037-c-v2` (12:00) | `reference-v2` (999681cea4e0) | raw A+B, none | 563 s, accepted | 9/10 (3 runs) | 1/3 | V09 FAIL, V07 PASS, V06 PASS (not triggered) | clean | **confirmed**: `RECORDED_EARLY` 2/39 + V09, `ATTEMPTS_OVER` 1/2, `TODAY_AGAIN` V09, `ORDER` V07 | 10/13; failed the switch rule |
| 28 | `130830-c-v3` (13:08) | `reference-v3` (62c464d98486) | raw A+B, none | 705 s, accepted | 6/10 (2 runs) | 3/3 (1 valid run) | V09, V07, V06 PASS | clean | **confirmed**: `SMS_MISSING` 2/13 (silent after the write, #17) | 9/13; build defect |
| 29 | `150036-final-rehearsal-a` (15:00) | `reference` (7659a7bd2e6c) | rehearsal of the final runbook on raw A, none | 1033 s, accepted | not measured | - | - | **SPEAKS** | - | Runbook rehearsal |

Which builders are good, in short:

- `reference` is the best skill we measured without practice customers: 11/13 (row 10) and 10/13 (row 26) on
  separate builds, no timeout, no in-build fixing. Its builds differ: 6 of 11 speak the goodbye after `close_call`
  (rows 4, 26, 29 and three scenario builds), 5 do not. The final runs it twice per brief and submits a clean build.
- `reference-fb88831` gave the best official agent (12/13), with practice customers the final does not have.
- `reference-v2` matched `reference` on customers (10/13) with no closing or greeting defect and PUB-05 3/3, but
  broke confirmation and attempt rules; it is the source of the next candidates after the final.
- `lowering`, `lowering-precedence`, `counted-rules`, `ladder`, `selfcheck`, `reference-v3`: not used (closing defect,
  timeouts, a blind regression, a silent-after-write defect).

## Open questions and tests not done

| Gap | Why it matters | Cost | When |
|---|---|---|---|
| V06 ("put it in twice") never triggered in the 2026-10-11 persona calls (0 of 3 arms) | The greeting-word judge risk of `reference` (P layer V06 1/3) is unmeasured on today's builds | 3 persona calls per agent, ~5 min | Optional before the final; needs approval |
| V09 ran once per agent today | `ITEM_SKIPPED` on `reference` (#2) is known, but its rate on today's build is one call | 3 calls, ~5 min | After the final |
| The unreviewed official findings of rows 2, 3, 4, 6, 8, 9, 11 | Counts are triage until read; row 3's `ATTEMPTS_OVER` and `RECORDED_EARLY` would say whether the 12/13 agent had the same weak spots | reading, no Freya | After the final |
| Two or three builds per final brief | Two builds give a clean closing about 7 times in 10, three about 8 in 10 (if independent at 6 of 11) | build time in parallel, no simulation | Decide before 20:00 |
| `reference` vs `reference-v2` | Equal on customers; the rule chose `reference` on confirmed violations the kit judge passed once. An outside reader may weigh the closing and greeting defects higher | no test settles it now: the rule was fixed before the run | Recorded in `docs/REFERENCE_V2.md` |
| Hidden-brief behaviour | Persona Lab g3-g7 are graded offline only; g3's attempts are void (fixture) | - | Not measurable before the final |

## Measured results

Official = the kit's practice customers with `tools/run_cases.py`; a customer counts only when all three runs pass.
Blind = built from `briefs/mutations/brief-a-raw.md` + `brief-b-raw.md` with no practice customers, then the final
export evaluated on the official customers (valid because the raw briefs keep the official policy and contract).

| Run | Skill | Inputs | Build | Customers 3/3 |
|---|---|---|---|---|
| 20261010-161811-candidate-ab | fb88831 | official A+B | 654 s | A 10/10 (rerun triple; earlier clean runs 9/10, 8/10), B 2/3 |
| 20261010-185544-lowering-ab | lowering | official A+B | 1382 s | A 10/10, B 2/3 |
| 20261010-172700-candidate2-ab | counted-rules | official A+B | 1902 s, timed out | not measured (outage) |
| 20261010-201333-ladder-ab | ladder | official A+B | 1882 s, timed out | not measured |
| 20261010-171132-candidate-a-raw | reference | raw A | 348 s | A 5/10 raw (9/10, 10/10 in runs without sandbox errors) |
| 20261010-212550-blind-ref-ab | reference | raw A+B | 887 s | **A 8/10, B 3/3 (11/13)**; one combined agent |
| 20261010-212547-blind-prec-ab | lowering-precedence | raw A+B | 501 s | A 8/10, B 1/3 (9/13) |
| 20261010-204555-blind-raw-ab | lowering | raw A+B | 404 s | A 6/10, B 2/3 (8/13) |
| 20261010-223940-blind-selfcheck-ab | selfcheck | raw A+B | 856 s | A 3/10, B 3/3 (6/13) |

One build per row. Builds of the same skill differ widely, so a gap of one or two customers between rows is within
build-to-build variation. Wilson 95% intervals: 11/13 0.58-0.96, 9/13 0.42-0.87, 8/13 0.36-0.82, 6/13 0.23-0.71; all
overlap, so the blind rows do not rank the skills. The case for `reference` rests on mechanisms (`docs/FAILURE_MODES.md`):
no timeout, no in-build fixing on false signals, and the goodbye before `close_call`. The runs of the evening have a `RESULT.md` with the failures and their evidence; the
earlier ones keep their notes in `eval/` (`candidate-ab/eval/OUTAGE.md`, `candidate-a-raw/eval/RESULT.md`), in
`docs/STATUS.md` and in the commit messages. `kit-builder-brief-a` predates kitrun and has no `summary.json`.

## Persona Lab blind scenarios (2026-10-10/11, reference vs lowering-precedence)

Changed brief and tool API, no practice customers, fresh state per build, graded offline: `tools.persona_lab.cli
grade` (contract and text evidence) and `tools/evaluation/pl_semantic.py` / `show_written.py` (what the code
computes). No simulation can score these: the bank knows only the public contract and customers.

| Scenario | reference | lowering-precedence |
|---|---|---|
| g6-contract-raw (fields, required `channel`, queue value) | 2 of 2 builds send the new contract | 2 of 2 |
| g5-memo-raw (newer memo: late deadline 6th business day, callback until 17:00) | 2 of 2 compute the memo values | 2 of 2 (applied from the memo's date on) |
| g3-limits-raw (car floor half, cap 2000, attempts 2/3) | floor and cap 2 of 2; attempts void (fixture) | floor and cap 2 of 2; attempts void (fixture) |
| g7-multi-raw (holiday moved, car-loan deadline cap, note reason renamed) | 1 of 1 | 1 of 1 |

g3 attempts are void for both skills: the scenario sets attempts to 2/3 in the table, but its rule 30 still defines
only attempt 1 and attempt 2, so a build that kept 1/2 followed the rule text. (Recorded before the fixture was found:
reference 1 of 2 builds changed the attempts, lowering-precedence 2 of 2 through the `lower.py` ladder.)

All 14 builds: 370-695 s, static check 0 errors, no trace reads `tools/persona_lab`. The g7 build listed the repository
root and `runs/` with `ls`; its `grep` failed and no file content was read. Nothing stops a builder from leaving its
workspace. Two strong text probes fired on
correct date-guarded memo handling (g5 19:00, g7 26 October); read the code before trusting a STALE on raw forms.
Caveat: kitrun puts `lower.py` in every `--skill` workspace and builders read it; one reference build copied the
ladder pattern without lowering. The measured reference configuration therefore includes `lower.py` in the
workspace, as the final runbook does.

## Persona Lab behavioural runs (2026-10-11, P layer)

Eight personas, three reps, on blind-ref (9bd08f14), public-ref (6a9597ac/3aa5a39a) and lowering
(b2df668d/d6e35cf9): 20/24, 22/24, 21/24 calls; no infrastructure failure. V09 (refusal before the product's turn)
fails on all three agents (1/3, 1/3 of which one is a judge miss, 0/3); blind-ref also loses V06 to "this call is
recorded" in its greeting. Details, judge-missed deviations and a platform observation: `docs/PERSONA_LAB_P_RESULTS.md`.

Found afterwards (two outside reviews, re-checked with timestamps): the lowering agents say no goodbye before
`close_call` in 24/24 calls (Brief A rule 47), 21 of them judge PASS. Cause: the builder put the farewell in the
closing `say` field, an option the lowering skills offer (`builder/skills/lowering/SKILL.md:56`), and
`builder/lower.py:328` makes it the `on_enter` line of the `api_request` step that runs the terminal tool. The blind
lowering-precedence agent has no goodbye before `close_call` in 37/39 of its stored official calls and speaks after it
in all 39; reference builds say the goodbye in an earlier step (0/24 Persona Lab, 0/39 official). The blind reference
agent instead leaves out the text-message sentence in 5 of 9 official B calls (judge PASS, read and confirmed).
`tools/evaluation/policy_audit.py` finds these and the other judge-missed deviations in stored calls, as findings to
read.

## Tools the skills use

| File | Used by | What it does |
|---|---|---|
| `builder/workflow_check.py` | all skills (as `tools/check_workflow.py`), kitrun | Static checks: tool contract against the OpenAPI file, terminal ordering, unbounded engine loops (`E-ENGINE-LOOP`), unreachable steps, sandbox exposure count |
| `builder/lower.py` | lowering, lowering-precedence, ladder | Writes terminal steps, routes and precedence routers from a closing plan |
| `builder/dryrun.py` | selfcheck | Runs a workflow's code steps on sample variables |
| `tools/persona_lab/` | evaluation only | Blind scenarios g1-g7 with answer keys, offline export grader, persona variants |
| `tools/evaluation/` | evaluation only | Official runs, per-customer merge with infrastructure labels, re-export, semantic checks, transcript rule checks (`policy_audit.py`) |
