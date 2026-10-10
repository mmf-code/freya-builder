# Invalid measurements: Freya platform outage, 2026-10-10 ~13:35-13:48 UTC

`a-official-3reps` run 3 (0/10) and `b-agent-all13-diagnostic` (0/13) are not agent results.

Evidence:
- Every call in both runs: the agent spoke its fixed opening line, the customer answered, routing logged
  "No transition matched", and no assistant message followed. The customer hung up after about 60 s
  (`endedReason: customer-ended-call`). run_cases.py reports median slowest turn 0 s and 10/10, 13/13 hang-ups.
- Runs 1 and 2 of the same agent version just before passed 9/10 and 8/10 with normal turn times.
- At 13:48 UTC, `POST /api/v2/chat/message` returned HTTP 503 "Internal server error" for this agent, for the
  unchanged kit example agent (workflow 5c6a92dd) and for the older brief-b agent (adf8b837).

These two runs are repeated once the platform answers again; the repeats are recorded next to them.
