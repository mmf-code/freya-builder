# Status at the end of 2026-10-10

Branch `builder-integration` on GitHub. Read with `docs/START_HERE.md`, `docs/PLATFORM_NOTES.md` and
`docs/EVAL_PROTOCOL.md`.

## Builders

| Builder | How to run | Notes |
|---|---|---|
| Kit example builder, unchanged | `.venv/bin/python -m builder.kitrun BRIEF... --tools OPENAPI` | Reference from the kit |
| Candidate, reference skill (92a695a) | `git show 92a695a:builder/skills/build-phone-agent/SKILL.md` into a directory as `SKILL.md`, then `--skill DIR` | Terminal-tool ordering, static check, hidden-brief-safe testing. Best measured. |
| Candidate, current HEAD skill (with d4bc3c1 "Counted and ordered rules") | `--skill builder/skills/build-phone-agent` | Experiment. Inconclusive: tested during a platform outage. Build hit the 30-minute limit. |

Every `kitrun` run: isolated Claude config, only the input briefs in the workspace, practice customers only for kit
briefs identical to an input, static checks of the exports (exit 3 on errors), trace in `runs/<stamp>-<label>/`.

## Agents on Freya and their measured results

| Agent | From | Official result |
|---|---|---|
| A 6a9597ac (workflow fbf21573 v2) | candidate, reference skill, clean clone | Brief A 3 runs: 10/10, every customer 3/3 |
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
   state file can race. Before running builds in parallel, give each run its own state file or slot prefix (not
   implemented yet).

## Next steps already decided

- When the sandbox is healthy: one run of B 4f317fbf on the three B cases, without a new build.
- Generic fixes still open: sandbox-exposure warnings in the checker and a bound on every loop; a script that merges
  a one-run result with a `--reps 2` result; brief-derived test scenarios to choose between runs of a hidden brief.
