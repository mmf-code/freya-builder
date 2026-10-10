# Experiment: attempt ladder in the lowering skill (commit 8fc6afc), Brief A + B

Result: failed. The build hit the 30-minute limit (1882 s, killed), its first tests were far below the previous
build, and PUB-12 still got two attempts on an early-band product with the ladder in place. Not evaluated outside the
build: a build over the limit is not a valid builder result. The skill's ladder section was removed again; the
lowering-only skill of 959453c stays the candidate.

| | Lowering build (20261010-185544) | This run |
|---|---|---|
| Build time | 1382 s | 1882 s, timed out |
| Builder's first A test | 8/10 | 5/10 |
| Builder's first B test | 2/3 | 0/3 (no call closed) |
| Builder tests, in order | 8/10, 2/3, 9/10, 3/3, 10/10 | 5/10, 4/10, 9/10, 0/3, 2/3, 2/3, 3/3, (A on v7 killed) |
| Hooks on bank tools | 10 | 0 |
| Steps (A / B) | 25 / 24 | 36 / 58 |

## Causes, from the builder's own test results

1. The builder went beyond the ladder: it moved recording into engine steps gated on extracted amounts. The amount
   was never extracted, so `create_promise` never ran and confirmed promises closed as `no_promise/refused` (a1: 5
   of the failures; b1: no call reached `close_call`).
2. Identity regressed in one version (PUB-03 passed three wrong answers, a2).
3. With the ladder, PUB-12 still had "two attempts to collect on the car loan" (b2, v5). The ladder moves on only when
   the extraction model marks the answer a refusal; when it does not, the model offers again inside the same step.
   The guarantee is only as strong as that extraction.
4. Design took longer (first save at 11:26 against 6:12), and each fix round re-tested both briefs.

Agents (version 7, not measured outside the build): A workflow 73df092f, agent b7c84f99; B workflow 6263394c, agent
05d116e1. Isolated state `state/exp-ladder-ab/`; no other slot was touched.
