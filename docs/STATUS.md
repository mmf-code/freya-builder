# Status (updated 2026-10-11 05:07 UTC+3)

Branch `builder-integration` on GitHub. Read with `docs/START_HERE.md`, `docs/PLATFORM_NOTES.md` and
`docs/EVAL_PROTOCOL.md`.

## Handoff, 2026-10-11 05:07 UTC+3

- Final builder unchanged: `--skill builder/skills/reference` (sha256 `7659a7bd2e6c`) with a fresh `--state` per
  run; commands in `docs/FINAL_RUNBOOK.md`. Freeze the skill and the helpers kitrun copies until the final.
- Done since 00:30: the Persona Lab P layer (72 calls, `docs/PERSONA_LAB_P_RESULTS.md`) and an independent audit of
  the evidence (bundle of fe8bd5b). Its claims were re-checked against the raw records; the corrections are below and
  in the docs.
- Corrections:
  1. The official 12/13 (A 10/10, B 2/3) belongs to `reference-fb88831`, built with practice customers. `reference`
     itself is measured blind only: 11/13 from one build.
  2. That A 10/10 is the rerun triple after a stalled run. The two earlier clean runs had 9/10 and 8/10; over all
     five clean runs PUB-07 passed 3/5 and PUB-05 4/5.
  3. The g3 attempts comparison is void: the fixture contradicts itself (`docs/FAILURE_MODES.md` #11).
  4. The measured lowering-family builds said thanks and goodbye only after `close_call`: they used the closing `say`
     field, which `builder/lower.py:328` puts on the step that runs the tool. lowering 24/24 Persona Lab calls (21 judge
     PASS), blind lowering-precedence 37/39 official calls. A lowering build without `say` would not have it.
  5. Blind results of one build per skill (11, 9, 8, 6 of 13) overlap in their 95% intervals; they do not rank skills.
- New, not yet measured: `builder/skills/reference-v2` (reference + four general rules), the transcript checker
  `tools/evaluation/policy_audit.py` (with `tests/test_policy_audit.py`), `docs/FAILURE_MODES.md` (failure catalog,
  engineering preference, what we took from EVRE) and `docs/REFERENCE_V2.md` (experiment and switch rule).
- Stage 0 of that experiment done at 04:20 (read-only `policy_audit --fetch` on the stored official calls): the
  blind lowering-precedence agent has no goodbye before `close_call` in 37/39 calls; the blind reference agent leaves
  out the text-message sentence in 5 of 9 official B calls (judge PASS, read and confirmed). Table in
  `docs/REFERENCE_V2.md`.
- Done by 05:07, after a second outside review (A and B of its plan, no Freya use):
  - A, runner acceptance (`builder/kitrun.py`, commits 7e4e2a0, c077158, 0c59ba3, 560ccfe, the last three after
    security reviews; what the builder sees is unchanged): a run is accepted only with a successful SDK result as the
    last record of the trace read through the handle opened at its creation and confirmed by agent_builder.py's
    "done:" line, unchanged inputs, a valid contract checked against the inputs as read into memory before the build, exported workflows with their sha256, and the time limit counted
    to the end of the checks; the whole process group is stopped. `docs/FAILURE_MODES.md` #16.
  - B, measurement: `policy_audit` is a triage with classes, coverage, persona triggers and review statuses; its false
    positives and negatives from the review are fixed and tested; the switch rule is revision 2 (three dimensions,
    confirmed findings only, per-mechanism veto, a floor). `docs/REFERENCE_V2.md`.
- Next, needs approval because it uses Freya: stages 1-4 of `docs/REFERENCE_V2.md` with runner 560ccfe (fresh
  reference build vs reference-v2 build, ~2 hours). If its rule fails or time runs out, the final uses `reference`.
- Known weak spots of `reference`: an item skipped after an out-of-turn refusal (V09), "this call is recorded" in the
  greeting judged as an early "recorded", the text-message sentence missing after several promises (5 of 9 official
  B calls of its blind build), 7 to 10 code hooks on bank tools (sandbox exposure). Not known: how it does on hidden
  briefs; "flawless" is not a claim any of this supports.
- Housekeeping left: the experiment worktree `.claude/worktrees/evre-graph-safety` (branch
  `worktree-evre-graph-safety`, merged) can be removed; local `main` is the stale initial import.

## Builders

Updated at 23:45 on 2026-10-10: every candidate skill now has its own directory under `builder/skills/`, with source commit,
sha256, status and measured results in `docs/BUILDERS.md`. Recommended: `--skill builder/skills/reference` with a
fresh `--state` directory per run. The blind comparison (raw A+B, no practice customers) and the experiments of the
evening are summarized there.

| Builder | How to run | Notes |
|---|---|---|
| Kit example builder, unchanged | `.venv/bin/python -m builder.kitrun BRIEF... --tools OPENAPI` | Reference from the kit |
| Candidate, reference skill (92a695a) | `--skill builder/skills/reference` | Terminal-tool ordering, static check, hidden-brief-safe testing. Blind test 11/13 (one build). The official 12/13 is from its practice-test variant `reference-fb88831`. |
| Candidate, counted rules (d4bc3c1) | `--skill builder/skills/counted-rules` | Rejected for the final: the build hit the 30-minute limit. Its policy effect stays inconclusive (tested during a platform outage). |

Every `kitrun` run: isolated Claude config, only the input briefs in the workspace, practice customers only for kit
briefs identical to an input, static checks of the exports (exit 3 on errors), trace in `runs/<stamp>-<label>/`.

## Agents on Freya and their measured results

| Agent | From | Official result |
|---|---|---|
| A 6a9597ac (workflow fbf21573 v2) | candidate skill of fb88831 (`builder/skills/reference-fb88831`; = `reference` except step 6), clean clone | Brief A: clean runs 9/10 (PUB-07) and 8/10 (PUB-05, PUB-07), third run stalled (excluded), rerun 3 runs 10/10 with every customer 3/3. Over the five clean runs PUB-07 3/5, PUB-05 4/5 |
| B 3aa5a39a (workflow 0b8ba909 v2) | same build | Brief B 3 runs: 2/3 (PUB-12 0/3, attempt counting) |
| B 84719013 (workflow adf8b837 v3) | kit builder, A+B | Brief B 3 runs: 2/3 (PUB-12 2/3); 4 of 13 calls had calls overlapping close_call |
| A-raw 5313a08c (workflow ded64a3a) | candidate, hidden-brief mode, raw-material Brief A | Brief A 3 runs: 9/10, 5/10 (all failures with sandbox errors), 10/10 |
| A ec8d1752 (workflow d325c61a v4) | experiment | builder's last test 9/10; not measured outside |
| B 4f317fbf (workflow a9d0f98f v4) | experiment | builder's test 0/3, all sandbox errors; not measured outside |

## Platform

The Python sandbox (snekbox) failed at least three times on 2026-10-10; another team reported the same error. Runs
whose failed calls record sandbox errors are not agent results. Check with `builder/callaudit.py` and the call
events before drawing conclusions.

## Running builders in parallel: two things to know

1. One simulation at a time per Freya workspace. A second builder's self-test waits (`freya.run_simulation` retries
   every 30 s) and the wait counts against that build's 30-minute limit.
2. All `kitrun` runs share `state/freya-agents.json`, and the slot is the brief's file name. Two runs on the same
   brief update the same Freya workflow, so the later save replaces the earlier agent, and concurrent writes to the
   state file can race. Done since: `kitrun --state DIR` gives each run its own slot and persona ids; use a fresh
   directory for every experiment and every final run.

## Next steps

- Done on 2026-10-10 evening: sandbox-exposure count and the unbounded-loop error in the checker
  (`E-ENGINE-LOOP`), the per-customer merge of result files (`tools/evaluation/classify.py`), Persona Lab blind
  scenarios. See `docs/BUILDERS.md` and `docs/FINAL_RUNBOOK.md`.
- Done on 2026-10-11 night: Persona Lab P layer, independent audit and corrections, `reference-v2`, `policy_audit`.
- Still open: the `reference-v2` experiment (`docs/REFERENCE_V2.md`); brief-derived test scenarios to choose between
  runs of a hidden brief (no reliable selection signal exists without customer scores); one run of B 4f317fbf on the
  three B cases (an experiment agent, low priority).
