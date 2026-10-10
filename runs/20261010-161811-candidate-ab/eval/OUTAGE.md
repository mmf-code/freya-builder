# Two 0% runs at 13:41 and 13:44 UTC (16:41 and 16:44 local): what the records show

`a-official-3reps` run 3 (0/10) and `b-agent-all13-diagnostic` (0/13) are excluded from the scores. The cause is most
likely on the platform side, but the call records do not prove it. This note separates what was recorded from what is
inferred.

## Recorded in each call (all 23 calls checked)

None of the 23 call records contains an HTTP 503 or an `error` event. Every call has the same events:

1. `setup` code step runs, routing goes to `opening`.
2. The fixed opening line is spoken (`on_enter` tts, no model call).
3. The customer answers ("Yes, this is Daniel Reyes." or similar).
4. `route_evaluated`: "No transition matched".
5. Nothing else: no assistant message, no tool call, no `tool_call_routing`, no `error`. The customer hangs up
   61 to 63 s after the start (`endedReason: customer-ended-call`).

Iteration records: `turnCount` 1 and `avgLatencyMs` null for every run of both simulations.

| Simulation | Window (UTC) | Agent version | Calls |
|---|---|---|---|
| e8419e4a-3049-4314-abc0-aaa2efde0578 (A, run 3) | 13:41:18 to 13:43:42 | brief-a v2 | 9c785c1e-9ad9-4a1f-bc2d-ab58aa8d887b, de95f3fd-f828-4be2-bf9e-5add0b50814c, 5f844a61-6f33-4853-8f67-728997a4c7d0, 91bf4bc3-8df2-499e-8952-e0677d908819, 0dcfd2c8-09d2-4262-9bc7-f1dc4f314943, c93b0fde-f6e1-4975-a772-885e5a240789, a7768d48-75c1-4b5c-a4fb-1c5c612c9ff5, e08b5d41-62c8-449a-8e07-acb3bd368674, 0a97b6fd-2ba3-47ab-90ef-89f7c839fd79, 94ed525c-94c5-4097-8a7d-d349d26d1d6a |
| a888c6ff-6bef-43ff-8151-325f9775a33e (diagnostic) | 13:44:01 to 13:47:30 | brief-b v2 | 90a9396c-a833-459d-b01d-1a94c62429ab, 5c536584-5ce3-412e-90c1-1a66e18bf3d6, 288881a9-60e5-411a-bc51-7e05248b09ad, dec13a15-8839-4dc7-84f0-dd6d1da46f4d, 3c543db1-5a92-4c97-b630-dc984b9e7a3d, 18fd664e-5a13-4881-9bbc-76d9ffd0cef0, 01bf96b1-65a5-4b71-9306-15a5267ae840, 2776eefe-9980-4335-b197-84e76abaec05, 60aeebbe-ac1a-4a93-9c29-8b988aa71eb9, 88dd1652-26f9-4945-90e9-c3ea2a7e3a97, b9093a88-16e5-4042-8760-8dab55454345, b421507d-abf2-4259-8860-e050a68081ec, 74dc77b3-7e61-4f9f-a84b-811522e7abba |

## Why the agent is the less likely cause (inference, not proof)

- Same agent version. brief-a v2 was published at 13:26:11 UTC and not changed. Runs 1 (13:37) and 2 (13:39) of
  the same version passed 9/10 and 8/10. Run 3 (13:41) of the same version stalled in every call.
- Same step, different result. In run 1, PUB-01 (call 04840798-2cda-40a6-984a-a47b76309b12) is identical up to
  "No transition matched"; 0.44 s later `tool_call_routing` fires and the model's `transition_to_identity` call moves
  the call on. In run 3 the same step produces nothing. That step is the first dialogue-model call of the call.
- Same time, other workflows. At about 13:48 UTC, `POST /api/v2/chat/message` returned HTTP 503 "Internal server
  error" for this agent (requestIds c632a1a6-bdb0-4476-8ff4-06fa42d61b4c, dbd6f5e5-d15f-4643-9728-1cae05811912),
  for the unchanged kit example agent, workflow 5c6a92dd (0bf87d82-97f1-424a-a498-0e62c29e2ef4), and for the older
  brief-b agent, workflow adf8b837 (3fb96a00-cff4-4437-aba8-59685519caf0). These 503s are from chat requests after
  the simulations, not from the simulated calls themselves.
- Recovery. A chat probe to the kit example agent answered at 13:59:17 UTC (1.9 s).

## Not established

- No Freya-side log or status page was checked; the 503 requestIds above are the handle to ask Freya.
- Whether the dialogue model timed out, returned nothing, or was never called cannot be read from the call records.

Classification becomes firm only if the same agent version, rerun after recovery, gets past this step. The reruns
are `a-official-3reps-rerun` and `b-agent-all13-diagnostic-rerun`, next to this file.
