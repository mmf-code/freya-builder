# Experiment: "Counted and ordered rules" skill section (commit d4bc3c1), Brief A + B

Result: worse than the previous candidate skill, and the build hit the 30-minute limit.

| | Previous candidate (fb88831 skill) | This run (d4bc3c1 skill) |
|---|---|---|
| Build time | 654 s | 1902 s, killed at the limit |
| Builder's own A tests | 7/10, then 10/10 | 5/10, 7/10, 5/10 |
| Builder's own B tests | 3/3 | 0/3 (B first tested at 24 min) |
| Static checks | 0 errors | 0 errors |
| Cost | $1.83 | unknown (killed before the SDK result message) |

The builder moved per-product counting into a model-called code tool and every bank write into engine steps,
for A as well, which has one product per customer. New failure kinds appeared in A (no `close_call` after a recorded
promise, identity stalls). Not checked: whether any of these calls also had sandbox errors.

Agents saved (version 4, last versions not fully tested): brief-a workflow d325c61a, brief-b workflow a9d0f98f.
No outside evaluation was run on them.

Recommendation: do not use the d4bc3c1 skill section as the default. The best measured skill is the one before it
(92a695a: terminal-tool ordering, static check, hidden-brief-safe testing).
