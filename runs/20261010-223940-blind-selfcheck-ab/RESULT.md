# Blind test: self-check skill (reference skill 92a695a + no-practice check loop + three rules), raw A + B

Result: worse than the reference skill. A 3/10 customers over three runs, B 3/3; total 6/13 against 11/13 for the
reference skill on the same inputs. The build's own late fixes, made on signals that do not reflect real calls,
are the likely cause of the A regression.

## Build (856 s, $1.63, commit 95d4d00, skill `builder/skills/build-phone-agent-selfcheck`)

The builder followed the new loop: noted its start, checked, dry-ran its code steps on its own samples (dates and
deadlines right), saved v1, sent chat turns with a made-up customer id, then
- added "a date fallback" to the account step after the chat test (v2), and
- added a human-transfer tool to the opening after a rule-by-rule review found CP-4 2.8 d not covered (v3).
kitrun's export failed on a platform outage (503 "API key validation is temporarily unavailable"); the export
taken after the outage is version 3 of both, saved before the outage. Static check 0 errors, contract present.

## Official customers, final export (version 3), three runs

| | Runs | Customers 3/3 |
|---|---|---|
| A | 7/10, 4/10, 6/10 | 3/10 |
| B | 3/3, 3/3, 3/3 | 3/3 |

Most A failures: right after `get_account`, the agent says "I cannot see your account details right now" and closes
`no_promise/service_error` (PUB-01, PUB-04, PUB-05, PUB-09), in some calls and not others. The account step's code
ran without an error event; its output sent the agent down the no-account path. PUB-09 twice ended after
`transfer_to_agent` without `close_call`; PUB-07 failed on the holiday date as in the lowering builds. No failed call
records a sandbox, DNS or backend error.

## What this says about an in-build check loop without customers

- The chat turn with a made-up id cannot reach real account data (the bank rejects the id), so it showed an account
  failure that real calls do not have, and the builder changed the account step in response.
- The dry-run used samples the builder wrote, which carry its own assumption about how tool results look in the
  variable table, so it could not catch a wrong assumption.
- The one fix found by reading the brief rule by rule (human transfer before verification) is a real gap.

Agents (version 3): A-raw workflow bc4bdb6a, agent c584abf9; B-raw workflow 71f82de3, agent b8f57aa1.
