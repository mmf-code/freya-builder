# Blind comparison (2026-10-10, 21:25): lowering + closing precedence vs the reference skill

Same inputs for both: `briefs/mutations/brief-a-raw.md` + `brief-b-raw.md`, the kit's tool API, no practice
customers in the workspace, separate isolated states. Untouched first exports (version 1), evaluated on the kit's
official customers, three runs each. No failed call records a sandbox, DNS or backend error.

| Arm | Build | A customers 3/3 | B customers 3/3 | Total |
|---|---|---|---|---|
| Reference skill 92a695a (`runs/20261010-212550-blind-ref-ab`) | 887 s, $2.50, one agent for both briefs | 8/10 (PUB-06 1 fail, PUB-10 2 fails) | 3/3 | **11/13** |
| Lowering + precedence, commit 4e8f616 (this run) | 501 s, $1.99, two agents | 8/10 (PUB-07 3 fails, PUB-10 1 fail) | 1/3 (PUB-12 2 fails, PUB-13 1 fail) | **9/13** |
| Lowering only, commit 2bfad75 (`runs/20261010-204555-blind-raw-ab`) | 404 s, $1.76, two agents | 6/10 | 2/3 | 8/13 |

Per run: reference A 10, 9, 8 and B 3, 3, 3; precedence A 8, 9, 9 and B 2, 2, 2.

## What the comparison shows

- Closing precedence removed the wrong close codes: 0 in the precedence arm's 39 calls, against 7 of 11 failed calls
  in the lowering-only arm. The builder declared sensible rules from the briefs (transfers, then a recorded promise,
  then no identity attempts left).
- The reference arm had no wrong close code either, and passed PUB-07 (holiday date) and PUB-12 (attempts per product)
  in all three runs; both lowering arms failed PUB-07 in every run.
- One build per arm. Builds of the same skill differ a lot, so 11 against 9 does not separate the skill from the
  build. It is the best evidence there is tonight, and it does not favour the lowering.
- The reference builder made one agent for both briefs ("single-product calls follow Brief A, two or three products
  follow Brief B"), from the raw B e-mail's wording; its B result comes from that combined agent.
- PUB-10 fails in every arm on the same judge reading: "this call is recorded" in the required opening counted as
  saying "recorded" before the write. The official-brief lowering build said "we keep a recording of this call" and
  passed PUB-10 in all three runs.

Agents (version 1): precedence A-raw workflow 289052df, agent e3359c81; B-raw workflow 5282da09, agent 5d427dc4.
Reference: one workflow 910582e9, agent 9bd08f14 (slot brief-b-raw).
