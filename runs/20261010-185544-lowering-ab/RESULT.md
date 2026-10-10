# Experiment: closing lowering (skill build-phone-agent-lowering), Brief A + B

Result: the builder wrote the closing plan itself and used `tools/lower.py` on every save. Brief A matched the best
measured agent (every customer 3/3). Brief B: 2 of 3 customers passed all three runs; PUB-12 passed 2 of 3 runs, where
the reference B agent passed 0 of 3. The build took twice as long as the reference build, mostly in simulations.

## Setup

- Code: commit 959453c on branch `worktree-evre-graph-safety`. Skill: the reference skill of 92a695a with steps 4, 5
  and 7 and the terminal-tool section replaced by "Endings" (declare a closing plan, lower it, never write the
  terminal steps).
- Isolated state `state/exp-lowering-ab/` (fresh slot and persona ids). The shared `state/freya-agents.json` was
  unchanged before and after; its `brief-a`/`brief-b` slots (candidate2 agents ec8d1752, 4f317fbf) were not touched.
- Agents (created by this run, version 4 published at 16:15:32Z and 16:15:34Z, before every official run):
  A workflow 2bf37061, agent b2df668d; B workflow 01369047, agent d6e35cf9.

## Did the builder use the lowering?

- `summary.json` checks: "endings: matches: every ending step, value and route of the saved workflow comes from the
  lowering", for both slots. The check lowers `out/<slot>.body.json` with `out/<slot>.closing.json` again and compares
  the result with the file saved and with the export.
- `trace.jsonl`: 6 Bash calls ran `tools/lower.py`. The only file written with Write was `out/gen_agents.py`, with 37
  `close:` targets, no `end_call` and `close_call` only in the plan's terminal declaration.
- Plans: 16 closings per brief (every outcome/reason pair of the outcome table), each quoted from the briefs, each
  with a fixed farewell.

## Official runs (run_cases.py, same published version 4 for all runs)

| Customer | Run 1 | Runs 2-3 | All 3 |
|---|---|---|---|
| PUB-01 .. PUB-10 (A) | 10/10 | 10/10, 10/10 | 10/10 customers 3/3 |
| PUB-11 | pass | pass, pass | 3/3 |
| PUB-12 | FAIL (agent) | pass, pass | 2/3 |
| PUB-13 | pass | pass, pass | 3/3 |

- PUB-12 run 1: "required one attempt on the car loan (early band), but the assistant made two attempts". No sandbox,
  DNS or backend error event in the call (`eval/classified.json`), so it counts as an agent failure. The run printed
  the slow-agent warning (median slowest turn 17 s); the failure reason is policy, not time.
- No call in the 39 official calls ended other than with one `close_call` as the last bank call.
- Raw files: `eval/a-official-1.json`, `eval/a-official-reps2.json`, `eval/b-official-1.json`,
  `eval/b-official-reps2.json`, with their logs.

## Compared with the reference build (skill 92a695a, run 20261010-161811-candidate-ab)

| | Reference | This run |
|---|---|---|
| A, 3 runs | 10/10, every customer 3/3 | 10/10, every customer 3/3 |
| B, 3 runs | 2/3 customers (PUB-12 0/3) | 2/3 customers (PUB-12 2/3) |
| Build time | 654 s | 1382 s |
| Simulation time inside the build | 259 s, 3 tests | about 829 s, 5 tests (first A test alone 330 s) |
| First save | 331 s | 372 s |
| Cost | $1.83 | $2.89 |
| Hooks on bank tools (sandbox) | 9 (A), 10 (B) | 10 (A), 10 (B) |

The PUB-12 gain cannot be credited to the lowering: PUB-12 fails on per-product attempt counting in the negotiation
prompt, which the lowering does not touch, and the bodies differ from the reference in other ways. What the lowering
verifiably did: a model-written build produced the measured-best closing structure from a declared plan, checked
against the tool API and the briefs, with no closing failure in 39 official calls.

Not changed by this skill: 10 code hooks on bank tools per agent, the sandbox exposure seen in the 2026-10-10 outage.
