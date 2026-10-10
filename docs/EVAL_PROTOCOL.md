# Staged evaluation of a candidate agent

Builds now take 6 to 30 minutes and each simulation 1 to 3 minutes, and only one simulation runs per workspace at a
time. A customer counts in the final only when all three runs pass, so one failed run already rules out 3/3 for that
customer. Measure in stages and stop early.

| Stage | What | Time | Go on when |
|---|---|---|---|
| 0 | `builder/workflow_check.py` on the exported workflow, with the build's contract | seconds | 0 errors |
| 1 | One run of the agent's own brief cases (`run_cases.py <agent> --brief X --out ...`) | ~2 min for 10 cases | score at least the current best |
| 2 | Two more runs (`--reps 2`), combined with stage 1 per customer | ~4 to 6 min | gives the 3-run result |

- A run whose failed calls record platform errors (`Failed to reach snekbox`, or a stall with no model output) is
  not counted; repeat that run only.
- Keep official Brief A and Brief B scores separate. Combined or mutated-policy runs are diagnostics, reported apart.
- Builder self-tests inside the 30-minute build stay at one run.
- Still missing: a small script that merges a stage-1 result file with a `--reps 2` file into per-customer 3-run counts.
