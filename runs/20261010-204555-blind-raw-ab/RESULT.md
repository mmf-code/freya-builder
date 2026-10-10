# Blind generalization test: lowering skill, raw-form Brief A + Brief B, no practice customers

Result: the untouched first exports pass 8 of 13 official customers in all three runs (A 6/10, B 2/3). The builder saw
no practice customer and ran no test (404 s, $1.76). It applied the memo overrides and the `add_note` exception. Seven
of the 11 failed calls closed with the wrong close code although the deciding fact was a tool result.

## Setup

- Code and skill: commit 2bfad75, skill `builder/skills/build-phone-agent-lowering` (lowering only, as in 959453c).
- Inputs: `briefs/mutations/brief-a-raw.md` and `briefs/mutations/brief-b-raw.md` (written in this session; checked
  rule by rule against the official Brief B; one known wording issue: its e-mail scopes the `add_note` change to
  "two or three products" while notice C2 and the official brief cover one to three; no official case is affected).
- `public-test-set.json` in the workspace was `[]`. Isolated state `state/exp-blind-ab/`.
- Agents, version 1 (first export, never changed): A-raw workflow fde335be, agent 52366f05; B-raw workflow 64aefe3a,
  agent c2749f5c. Endings provenance: matches for both. Static check: 0 errors.

## Official customers (run_cases.py with the kit's public-test-set.json)

| Customer | Runs | All 3 |
|---|---|---|
| PUB-01, 02, 05, 06, 08, 09 | pass, pass, pass | yes |
| PUB-03 Identity | fail, fail, pass | no: closed `not_verified/declined`, expected `failed`; no app/branch sentence |
| PUB-04 Dates | pass, fail, fail | no: promise recorded, closed `no_promise/refused` |
| PUB-07 Dates | fail, fail, fail | no: 26 October (memo holiday) answered with the deadline 2 November instead of 27 October; closed `no_promise/refused` after the promise |
| PUB-10 Tool failure | fail, pass, pass | no: judge counted "this call is recorded" in the required opening as saying "recorded" too early |
| PUB-11, PUB-13 | pass, pass, pass | yes |
| PUB-12 Multi-product | fail, fail, fail | no: two attempts on the early-band car loan |

No failed call records a sandbox, DNS or backend error (`eval/classified.json`). The PUB-10 bank error
"service unavailable, nothing was recorded" is the case's scripted tool failure, not infrastructure.

## Offline checks of the same exports

- Memo precedence (`memo_check.py` run on the builder's code steps): late deadline on the 7th business day and
  26 October as a holiday, in both briefs.
- `add_note`: not offered in A-raw (Document 4 forbids it), offered in B-raw (the change notice allows it).
- Tool API mutations: 11 of 11 applicable caught by the lowering or the checker.
- Sandbox: 3 hooks on bank tools per agent (the official-brief lowering build had 10).

## Compared with

| | Customers 3/3 |
|---|---|
| This blind build (no practice customers) | 8/13 |
| Lowering build on the official briefs (5 test rounds on the practice customers) | 12/13 |
| Earlier blind raw-A build, reference skill, A only (runs/20261010-171132-candidate-a-raw) | A 5/10 raw; 9/10 and 10/10 in its two runs without sandbox errors |

Next, as proposed: closings decided by tool results (a recorded promise, no identity attempts left) routed
deterministically by the lowering, from rules quoted from the brief.
