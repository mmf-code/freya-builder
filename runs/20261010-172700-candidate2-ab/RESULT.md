# Experiment: "Counted and ordered rules" skill section (commit d4bc3c1), Brief A + B

Result: inconclusive for policy quality. Most of the builder's tests ran during a platform sandbox outage that
another team reported in the event channel with the same error ("Failed to reach snekbox: Cannot connect to host
snekbox-svc.staging.local:8060 ... Name or service not known"). Two findings stand regardless: the design is far
more exposed to sandbox outages (unbounded re-entry when code fails), and the build hit the 30-minute limit.

| | Previous candidate (fb88831 skill) | This run (d4bc3c1 skill) |
|---|---|---|
| Build time | 654 s | 1902 s, killed at the limit |
| Builder's own A tests | 7/10, then 10/10 | 5/10, 7/10, 5/10, 9/10 (the last, on v4, finished after the builder was killed; it never saw it) |
| Builder's own B tests | 3/3 | 0/3 (B first tested at 24 min) |
| Static checks | 0 errors | 0 errors |
| Cost | $1.83 | unknown (killed before the SDK result message) |

The builder moved per-product counting into a model-called code tool and every bank write into engine steps,
for A as well, which has one product per customer.

## Causes, from the error events of every failed call in the builder's tests

1. Platform sandbox failures during the test window (17:37 to 17:57 UTC+3). 15 of the 18 failed calls record
   `Failed to reach snekbox` or "Sandbox did not return a parseable result", on the state tool `update`, on code
   steps and on hooks. All 3 B failures are `update` sandbox errors (12, 26 and 7 per call).
2. The design multiplied that exposure. A code-tool call on every customer answer and code steps around every bank
   write mean one sandbox outage breaks most of the call. Where code failed, steps kept re-entering each other: one
   call logged 316 code_exec errors and "maximum recursion depth exceeded" (PUB-10, a1). No loop had a bound.
3. A fix by the builder itself caused silence: "call update with no text" led to "The model returned no speakable
   content" (PUB-04 and PUB-05 in a2).
4. Errors without any platform error: PUB-06 in a2 (floor offered twice).
5. Time: 9 min 40 s of design before the first test; then the builder spent its fix rounds on failures the outage
   caused, which it could not tell apart from its own, and tested B only at 24 min.

Agents saved (version 4, last versions not fully tested): brief-a workflow d325c61a, brief-b workflow a9d0f98f.
No outside evaluation was run on them.

Decision: keep the previous candidate (skill 92a695a; correction 2026-10-11: agents 6a9597ac and 3aa5a39a were built
with its predecessor fb88831, which differs only in step 6) as the reference, and keep
this experiment separate; nothing is reverted. Next, once the sandbox is healthy and without a new build: one run of
the existing B agent (agent 4f317fbf, workflow a9d0f98f v4) on the three B cases. A run whose failed calls record
sandbox errors does not count. That measures this agent only, not whether the builder reproduces it.
