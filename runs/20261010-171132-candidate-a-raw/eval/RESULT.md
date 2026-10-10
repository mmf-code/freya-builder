# Form-mutation test: Brief A as raw bank material, hidden-brief mode

Build: candidate skill, input `briefs/mutations/brief-a-raw.md` only. The workspace had no practice customers; the
builder ran no practice test. 348 s, $1.50, static check 0 errors. It applied all three memo overrides
(26 October holiday, next-business-day callback, late deadline on the 7th business day).

Evaluation outside the build: official Brief A cases, agent 5313a08c, 3 runs.

| Run | Result | Failed |
|---|---|---|
| 1 | 9/10 | PUB-10 (judge: a negative wording constraint; ledger correct). No sandbox errors. |
| 2 | 5/10 | PUB-02, PUB-05, PUB-08, PUB-09, PUB-10. Every failed call records `function_call_error` "Failed to reach snekbox" (6 to 42 per call). |
| 3 | 10/10 | none |

Official 3-run score (a customer counts with 3/3): **5/10**. Every run-2 failure carries a recorded platform sandbox
error; the one failure without one is PUB-10 in run 1 (1 of 2 clean runs).
