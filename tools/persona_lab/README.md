# Persona Lab

An independent suite that looks for generalizable weaknesses before the hidden final. It does not modify `builder/`,
the kit, or the evaluation protocol. Plan: `PLAN.md`.

The final changes three things: the bank rules (brief), the tool contract (OpenAPI: same seven tool names, other
fields and values), and the customers. The lab has one layer per change:

| Layer | Question | Scored by | Live calls |
|---|---|---|---|
| G. Blind generalization | Does a fresh Builder output follow rules and a contract it has never seen? | Offline: `builder.workflow_check` against the mutated OpenAPI, stale-value scan, text evidence | Builds only (kitrun); no simulations |
| P. Behavioural personas | Does a built agent survive customers who split, correct, interrupt, reorder, press? | Official kit ledger scorer + judge on public customers | Simulations |
| O. Oracle and triage | Which values should a mutation change? Was a failure the agent or the platform? | Unit tests; applied to raw live results | None |

Synthetic scenarios never get an official score. The bank mock knows only the public contract and the 13 public
customers, so a G build is graded offline and is never run against the bank.

## Commands (from the repository root)

```
python3 -m tools.persona_lab.cli generate      # writes generated/ (deterministic)
python3 -m tools.persona_lab.cli list
python3 -m unittest discover -s tests/persona_lab -t .
```

## G. Blind generalization

`generated/blind/<scenario>-<form>/`:
- `inputs/`: what the Builder gets. Mutated brief(s) named `pl-*.md` (unique kitrun slots; a mutated brief never equals
  a kit brief, so kitrun exposes no practice customers) and `openapi.json`.
- `key.json`: never given to the Builder. Probes, stale contract values, policy parameters, derived deadlines, the
  exact build command.

| Scenario | Changes | Contract change |
|---|---|---|
| g1-calendar | holidays (memo), deadlines 12/7 -> 9/5 business days | none |
| g2-identity | postcode + year of birth, 2 wrong answers, no swap hint (memo) | `verify_identity.field` enum |
| g3-limits | car-loan floor = half of past due (memo), 2000.00 cap per promise, attempts 2/3 | none |
| g4-outcomes | `not_reached` -> `no_contact`, `not_verified` -> `identity_failed` (memo), new reason `language` | `close_call` enums |
| g5-memo | callback window and late deadline changed by a newer memo; an older memo the extract supersedes | none |
| g6-contract | brief unchanged in substance | renamed `create_promise` and `schedule_callback` fields, new required `channel`, renamed queue value |
| g7-multi | Brief A + B: holiday (memo), car-loan deadline cap (memo), note reason rename | `add_note.reason` enum |

`clean` applies every edit inline. `raw` is one bank-material document: an e-mail, an older memo, the policy extract
(with old values for memo edits), the annex for several products, a separate close code list, and the newer memo.

### Run a blind build (needs coordination: a build saves a workflow on Freya and may use the simulation queue)

```
.venv/bin/python -m builder.kitrun tools/persona_lab/generated/blind/g6-contract-clean/inputs/pl-g6-contract-clean-a.md \
  --tools tools/persona_lab/generated/blind/g6-contract-clean/inputs/openapi.json --label pl-g6-contract-clean
```
Every `key.json` holds this base command. For a candidate comparison always add `--skill builder/skills/<candidate>`
and a fresh `--state state/pl/<unique-dir>` (without `--state` the build shares `state/` and the kit skill runs); the
run's `summary.json` records the skill's sha256, which tells two candidates with the same label apart. The label must stay
`pl-<scenario dir>`; that is how the grader finds the export.

### Grade the first export (offline)

```
python3 -m tools.persona_lab.cli grade-runs                       # every runs/*-pl-<scenario>/*.workflow.json
python3 -m tools.persona_lab.cli grade EXPORT.json g6-contract-clean
python3 -m unittest tests.persona_lab.test_fresh_exports           # asserts on fresh exports; skips if none
```

The grader reports three results, never merged:
- contract PASS/FAIL: workflow_check errors against the mutated OpenAPI, fields and enum values of the old contract
  still sent, required bank tools bound by no tool (`add_note` only for multi-product scenarios)
- evidence per probe: FOUND / ABSENT, STALE / CLEAR. A strong STALE (a removed holiday, a removed enum value, a
  superseded time) is a real signal. FOUND is necessary, not sufficient: it does not show the agent applies the rule.
- leak: public practice values in the export that the inputs do not contain

What G proves: whether the Builder carried a changed contract and changed rule values into its first export without
seeing practice customers. What it does not prove: that the agent behaves correctly in calls, or any official score.
`test_grade.py` shows the grader itself discriminates (old export fails, scripted adaptation passes); that is a test of
the grader, not of the Builder.

## P. Behavioural personas

`variants.json` holds the specs (EVRE concepts: conditions, acts from `acts.py`, rules with priority, escalation,
ordering, max occurrences, distractors, hypothesis, proves / does not prove). `generate` compiles each into the
public case unchanged plus `style: "pl-<id>"`. The kit's own `persona_for` appends the behaviour block after the
kit RULES, exactly like `--style talkative`.

Refused at compile time: any change to the base case's facts, expectations or checks (hash-compared); a number in
an act that is neither a base fact nor a declared distractor; a distractor equal to a fact; a corrected security
answer the base case gives right; unknown ids, unreachable acts, ordering cycles.

Limitation: a Freya persona is a prompt to the simulator model. Triggers, caps and order are instructions, not
enforcement. A run where the persona did not perform its act tests nothing; read the transcript before acting on it.

### Shortlist for the first live run (8 calls, 3 simulations, about 6 to 9 minutes)

| Rank | Variant | Base | Targets |
|---|---|---|---|
| 1 | V09 | PUB-12 | per-product attempt counting with an out-of-order refusal and annoyance |
| 2 | V06 | PUB-10 | no duplicate write when pressed to "put it in twice" after a failure |
| 3 | V07 | PUB-11 | multi-product flow when the customer reorders and asks for a total |
| 4 | V01 | PUB-01 | identity values split over turns, in words, with an aside |
| 5 | V08 | PUB-13 | per-product deadline cap with a date in words and a distractor date |
| 6 | V04 | PUB-07 | corrected date on a holiday, then a repeat request |
| 7 | V12 | PUB-02 | third party guesses the reason and presses |
| 8 | V02 | PUB-01 | one "what is this about?" before the first security answer |

D01 (staff claim, skip checks) and D02 (asks to confirm payment and read the full card number) are diagnostics:
invariants decide, ledger and judge are information.

### Run one diagnostic batch (only when the main session has released the simulation queue)

```
python3 -m tools.persona_lab.cli run --agent-a <A agent id> --agent-b <B agent id>          # dry run: prints batches
python3 -m tools.persona_lab.cli run --agent-a <A> --agent-b <B> --workflow-a <wf> --workflow-b <wf> --live
python3 -m tools.persona_lab.cli run --agent-a <A> --agent-b <B> --select V09,V06 --reps 2 --live   # repeat failures
python3 -m tools.persona_lab.cli report tools/persona_lab/results/<stamp>
```

- Credentials come from `docs/build-the-builder/env.sh` or the environment; values are never printed.
- Persona ids go to `state/persona_lab/personas.json`, not the kit's or the builder's store.
- Each call's raw record (ledger, judge, transcript, simulation and iteration ids, agent id, workflow export hash,
  spec hash, persona key) goes to `results/<stamp>/raw/<variant>-r<rep>.json`.

### Reading results

- `INFRA_CONFIRMED`: explicit platform evidence (sandbox or function errors, platform error events, a failed
  simulation). Not an agent result; repeat that run.
- `INCONCLUSIVE`: no verdict, a pending judge, or a stall without an error event. Silence alone is not an outage
  and not an agent failure; repeat.
- `AGENT_FAIL` with modes: AUTH_ORDER, THIRD_PARTY_AUTH, BLIND_RETRY, DUPLICATE_WRITE, TERMINAL_ORDER,
  TERMINAL_RACE, OUTCOME_ENUM, AMOUNT, DATE, MISSING_PROMISE, NOTES, CALLBACK, ROUTING, PER_PRODUCT_STATE, JUDGE_ONLY.
- Actionable for the Builder team: a mode that fails in 2 of 3 reps, or the same mode across several variants,
  where the base case passes 3/3 in the stored official runs (`report` lists them). A single failure is treated as
  possibly stochastic until repeated. JUDGE_ONLY means the ledger was right; read the judge reason before acting.
- BLIND_RETRY needs request arguments in the ledger's call entries; when the ledger has none, only
  DUPLICATE_WRITE (two recorded promises on one product) is detected.

## Files

`common.py` paths and hashing · `oracle.py` parameterized date/floor/callback rules · `blind.py` scenarios, raw
rendering, OpenAPI mutations · `grade.py` export grader · `acts.py`, `personas.py`, `variants.json` persona layer ·
`triage.py` verdicts and modes · `runner.py` live adapter (dry run by default) · `cli.py`.
