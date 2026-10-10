# Builder candidates (state at 2026-10-10, 23:45 UTC+3)

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
| `reference-fb88831` | fb88831 | 8b8e4ba58d1f | `reference` without the no-practice rule of step 6: always runs the practice test. Built the best official agents (A 6a9597ac) | Kept to reproduce run 161811 |
| `counted-rules` | d4bc3c1 | 5d6669717e9e | Counted and ordered rules kept in code steps | Rejected: timed out; design multiplied sandbox exposure |
| `lowering` | 959453c | ad17c5b808d7 | Endings declared in a plan and written by `tools/lower.py` | Experimental |
| `lowering-precedence` | 4e8f616 | c401cbfb82b2 | `lowering` + endings decided by tool results (`precedence`) | Experimental, strongest lowering variant |
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

## Measured results

Official = the kit's practice customers with `tools/run_cases.py`; a customer counts only when all three runs pass.
Blind = built from `briefs/mutations/brief-a-raw.md` + `brief-b-raw.md` with no practice customers, then the final
export evaluated on the official customers (valid because the raw briefs keep the official policy and contract).

| Run | Skill | Inputs | Build | Customers 3/3 |
|---|---|---|---|---|
| 20261010-161811-candidate-ab | fb88831 | official A+B | 654 s | A 10/10, B 2/3 |
| 20261010-185544-lowering-ab | lowering | official A+B | 1382 s | A 10/10, B 2/3 |
| 20261010-172700-candidate2-ab | counted-rules | official A+B | 1902 s, timed out | not measured (outage) |
| 20261010-201333-ladder-ab | ladder | official A+B | 1882 s, timed out | not measured |
| 20261010-171132-candidate-a-raw | reference | raw A | 348 s | A 5/10 raw (9/10, 10/10 in runs without sandbox errors) |
| 20261010-212550-blind-ref-ab | reference | raw A+B | 887 s | **A 8/10, B 3/3 (11/13)**; one combined agent |
| 20261010-212547-blind-prec-ab | lowering-precedence | raw A+B | 501 s | A 8/10, B 1/3 (9/13) |
| 20261010-204555-blind-raw-ab | lowering | raw A+B | 404 s | A 6/10, B 2/3 (8/13) |
| 20261010-223940-blind-selfcheck-ab | selfcheck | raw A+B | 856 s | A 3/10, B 3/3 (6/13) |

One build per row. Builds of the same skill differ widely, so a gap of one or two customers between rows is within
build-to-build variation. The runs of the evening have a `RESULT.md` with the failures and their evidence; the
earlier ones keep their notes in `eval/` (`candidate-ab/eval/OUTAGE.md`, `candidate-a-raw/eval/RESULT.md`), in
`docs/STATUS.md` and in the commit messages. `kit-builder-brief-a` predates kitrun and has no `summary.json`.

## Tools the skills use

| File | Used by | What it does |
|---|---|---|
| `builder/workflow_check.py` | all skills (as `tools/check_workflow.py`), kitrun | Static checks: tool contract against the OpenAPI file, terminal ordering, unbounded engine loops (`E-ENGINE-LOOP`), unreachable steps, sandbox exposure count |
| `builder/lower.py` | lowering, lowering-precedence, ladder | Writes terminal steps, routes and precedence routers from a closing plan |
| `builder/dryrun.py` | selfcheck | Runs a workflow's code steps on sample variables |
| `tools/persona_lab/` | evaluation only | Blind scenarios g1-g7 with answer keys, offline export grader, persona variants |
| `tools/evaluation/` | evaluation only | Official runs, per-customer merge with infrastructure labels, re-export, semantic checks |
