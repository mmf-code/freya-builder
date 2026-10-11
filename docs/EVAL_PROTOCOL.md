# Staged evaluation of a candidate agent

Builds now take 6 to 30 minutes and each simulation 1 to 3 minutes, and only one simulation runs per workspace at a
time. A customer counts in the final only when all three runs pass, so one failed run already rules out 3/3 for that
customer. Measure in stages and stop early.

| Stage | What | Time | Go on when |
|---|---|---|---|
| 0 | `builder/workflow_check.py` on the exported workflow, with the build's contract | seconds | 0 errors |
| 1 | One run of the agent's own brief cases (`run_cases.py <agent> --brief X --out ...`) | ~2 min for 10 cases | score at least the current best |
| 2 | Two more runs (`--reps 2`), combined with stage 1 per customer (`tools/evaluation/classify.py`) | ~4 to 6 min | gives the 3-run result |
| 3 | `tools/evaluation/policy_audit.py` on every call of stages 1 and 2 (`--fetch REPO RESULTS.json`, read-only) and on Persona Lab raw records | ~2 min | read each finding; a PASS with a finding is a rule deviation the judge did not see |

- Keep official Brief A and Brief B scores separate. Combined or mutated-policy runs are diagnostics, reported apart.
- Builder self-tests inside the 30-minute build stay at one run.

## Excluding a run

- Exclude only on evidence named here, before the run: a failed call that records a platform error event
  (`Failed to reach snekbox`, a sandbox or connection error, an API 5xx), a simulation that did not complete, or a
  stall with no tool call and no model output in most calls of the run. Repeat that run only.
- A finished run that the dashboard later shows as "inconclusive" is not excluded: read the call's own
  `successCriteriaResult` (`docs/PERSONA_LAB_P_RESULTS.md`, platform observations).
- Never drop a clean failure. Report every clean run; when a rerun replaces an excluded run, say so next to the
  result (`docs/STATUS.md`, agent A 6a9597ac, is the example).

## Comparing two candidates

- Build both in the same session at the same commit, each with a fresh `--state`, and measure them on the same
  customers with the same judge. A fresh build of the baseline is one of the two arms.
- Write the decision rule before the first run (`docs/REFERENCE_V2.md` is the current one).
- With 13 customers a one- or two-customer gap is noise (Wilson 95% intervals of 11/13 and 9/13 overlap widely). Use
  the official runs as a non-inferiority check and decide on mechanisms: a `policy_audit` finding present in one arm
  and gone in the other, on the personas that trigger it.
