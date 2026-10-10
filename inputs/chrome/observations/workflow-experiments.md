# Workflow Experiments

## Setup

- **Source** (never modified): `92c0e02d-6f5f-4d2e-89a8-a3d46df01a40`, "Freya Bank Collections Base (2 nodes)". Published v2 is active.
- **Test copy** (created with the UI "duplicate" button): workflow `a92db54a-dddb-4cdf-9d56-646b824a3bd0`, agent `eb60ff29-7431-4303-91ce-883d47e781e1`, named "… (2)". Note that the duplicate's **v1 was auto-published by the platform on creation**. I did not request this.
- **All mutations** went to the draft branch `exp-branch` (`8a53c262-37d1-4076-8b80-0e22b9ed0077`), base v1 `13ae3692-…`. The branch is **open, not merged, not published**. The mainline working copy was confirmed unchanged after every step (canonical compare = true).
- **Mechanism**: `POST /api/v2/branches` (first change), then `POST /api/v2/branches/{id}/commit` with `{config, name}`. Evidence for each step: `GET /api/v2/versions/workflow/{wf}/{versionId}` → `configSnapshot` and `configDiff`.
- **Snapshots** are in `experiments/*.json`. They were rebuilt locally from the baseline. The final local file is **hash-identical** (SHA-256 of canonical JSON `6fe6175b…`) to the server's v10 `configSnapshot`.

## General serialization findings (VERIFIED)

1. **Round-trip**: every accepted commit's `configSnapshot` equals the sent config exactly. The server adds no IDs, timestamps, defaults, or reordering inside the definition.
2. **Server-generated data lives outside the definition**: version `id`, `versionNumber` (incrementing per entity, shared between branch and mainline numbering), `parentVersionId`, `branchId`, `createdAt`/`createdBy`, `isPublished=false`, `configDiff`.
3. **`configDiff`** is a sparse object relative to the **previous commit**:
   - Changed leaf → new value.
   - Removed key → `null` (for example, v6's diff deleted the probe nodes as `"p_code": null`).
   - Arrays are replaced whole (E2 and E4 diffs contain the full `transitions` / `tools` array).
4. **No-op is rejected**: creating a branch with config equal to the base returns 400 "No changes to branch — the edited config matches the base".
5. **Validation (422)** returns `data.result.issues[]` as `{path, message}`, Zod-style. This list appears to be capped at about 10 issues per response. Rejected commits create **no** version.
6. **Referential integrity is NOT validated**: a transition to `"does_not_exist"` was accepted (v3).

## Experiment log

| # | Change (exactly one) | Server version | Persisted | Diff (server `configDiff`) | Confidence |
|---|---|---|---|---|---|
| E1 | `nodes.identity.task_message` += `"\nEXP1: Never reveal account details before verification."` | v2 (branch create) | ✅ snapshot == sent; mainline unchanged | `{"nodes":{"identity":{"task_message":"…EXP1…"}}}` | VERIFIED |
| P1 | Probe: transition `target_node:"does_not_exist"` | v3 | ✅ accepted | — | VERIFIED (no ref check) |
| P2 | Probe: every node_type with `{name,node_type}` only (+`__exit__`) | v5 | ✅ stored as-is, no defaults | — | VERIFIED |
| E5 | Add node `verification_failed` (conversation, tts on_enter, end_call tool, empty transitions/pre_actions), unconnected | v6 | ✅ | `{"nodes":{…probe nodes:null…,"verification_failed":{…}}}` | VERIFIED |
| E2 | Append transition identity → verification_failed: `or`[`all_verified equals "false"`, `equals "False"`], `mode:"exact"` | v7 | ✅ | `{"nodes":{"identity":{"transitions":[<full array>]}}}` | VERIFIED (schema). Runtime routing UNVERIFIED |
| E3 | `test_variables.max_payment_attempts = "3"` | v8 | ✅ | `{"test_variables":{"max_payment_attempts":"3"}}` | VERIFIED |
| E4 | `nodes.identity.tools[0].config` → `timeoutMs:8000, maxRetries:1` (tool not invoked) | v9 | ✅ | `{"nodes":{"identity":{"tools":[<full array>]}}}` | VERIFIED |
| P3 | Probe: `initial_node:"nowhere"` | v11 | ✅ accepted (no ref check) | `{"initial_node":"nowhere"}` | VERIFIED |
| R | Re-commit the E6 config to undo P3 | v12 (head) | ✅ equals v10 | — | VERIFIED |
| E6 | `nodes.identity.max_node_turns 80→12`, `max_turn_transition null→"verification_failed"` | v10 | ✅ | `{"nodes":{"identity":{"max_node_turns":12,"max_turn_transition":"verification_failed"}}}` | VERIFIED (schema). Counter behavior UNVERIFIED |

E6 bundles two fields because they form one retry-limit rule: a cap plus its target.

### E2 transition as committed

```json
{"target_node":"verification_failed","description":"identity check failed",
 "condition":{"logic":"or","conditions":[
   {"variable":"verify_identity_response.data.all_verified","operator":"equals","operand":"false","mode":"exact"},
   {"variable":"verify_identity_response.data.all_verified","operator":"equals","operand":"False","mode":"exact"}]}}
```

Caveat: it is unknown whether `all_verified` becomes `false` after one wrong answer, or stays false or unset until both answers are given. If it is `false` after the first answer, this edge would fire too early. It needs a runtime test against the mock (open question Q2).

## Validator probes (all 422, nothing persisted)

| Probe | Issue returned |
|---|---|
| `node_type:"bogus_type"` | `expected one of "conversation"\|"api_request"\|"transfer_call"\|"end_call"\|"integration"\|"reschedule_call"\|"knowledge_base"\|"code"\|"invoke_agent"\|"exit"` |
| config `{foo:1}` | `initial_node: expected string, received undefined`, `nodes: …` |
| exit node not keyed `__exit__` | `Reserved canonical name "__exit__" must pair with node_type "exit"` |
| operators/modes/logic sweep | accepted / rejected sets are listed in the schema doc §5.1 (`issues[].path` = `nodes.identity.transitions.N.condition`) |
| `condition: null` | invalid; omitting `condition` is valid |
| transition without `target_node` | `target_node: expected string` |
| `on_enter.type:"bogus"` | `Expected 'silent' \| 'tts' \| 'llm' \| 'audio'`; `audio` requires `asset_id` |
| `truncation_strategy:"bogus"` | `expected one of "keep_all"\|"keep_recent"\|"summarize"` |
| `assertions:[{}]` | `expected string` |
| `extraction_schema:[{}]` | `name` required; `type` ∈ string, integer, float, boolean, date, datetime, enum, name, phone_number, object |
| `response_mapping:[{}]` | `path` and `variable` required strings |
| `tools[0].config.alwaysRunsAt:["bogus"]` | `expected one of "each_turn"\|"start_of_call"\|"end_of_call"` |
| `tools:[{}]` / `{type:"function",function:{}}` | `type` must be "function"; `function.name`, `handler`, `description` required strings; `parameters` required object |
| `pre_actions:[{}]` | `type` must be "function", `function` required (same as a tool) |
| `global_nodes:{g1:{}}` | `name` required, `condition` required, unknown keys rejected, `node_type` required |
| unknown key on node | `Unrecognized key: "bogus_key2"` (strict) |
| ~75 candidate keys on api_request node | Only `agent_id` recognized |

## Not done

- **Runtime test**: the UI "Metin Ajanı" (text agent) stuck on "Bağlanıyor…" for over 15 s (WebRTC). The documented `POST /chat/message` returned 403 "Authentication method 'access_token' is not allowed for this route. Allowed methods: api_key". Creating an API key was left to the team because I should not handle secrets. **No conversational behavior was verified.**
- **Restoring the baseline**: not needed. Mainline is untouched. To clean up, discard the branch (`POST /branches/{id}/discard`, DOCUMENTED, not executed) or delete the test workflow.
