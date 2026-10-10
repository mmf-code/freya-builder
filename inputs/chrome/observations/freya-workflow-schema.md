# Freya Workflow Schema Map

Investigation date: 2026-10-10, staging (`staging-app.freyavoice.ai`), workspace `6c95e075-4591-465a-8f61-bb37955c533d`.

Confidence tags:
- **VERIFIED**: directly observed, or accepted/rejected by the server's validator.
- **DOCUMENTED**: stated in docs.freyavoice.ai.
- **INFERRED**: reasoned from evidence but not tested.
- **UNKNOWN**: not established.

Important: "accepted by the validator" means the shape is valid. It does **not** prove how the runtime behaves. Runtime semantics are marked INFERRED unless a call was executed.

This map is **partial**. It covers the `conversation` node type in depth. The other nine node types are only known to be valid with minimal fields.

---

## 1. Where the workflow JSON lives

| Thing | Location | Tag |
|---|---|---|
| Editor JSON ("JSON İş Akışı Editörü", Monaco model) | Exactly equal to `GET /workflow/{id}` → `data.result.workflow.workflow` (canonical compare) | VERIFIED |
| Baseline sample | 638 lines pretty-printed, which matches the organizers' "~638 lines" | VERIFIED |
| Version snapshot | `GET /versions/workflow/{id}/{versionId}` → `version.configSnapshot` uses the same 7 top-level keys | VERIFIED |
| Branch commit / branch create `config` | Same object | VERIFIED |
| Canvas positions | Stored **outside** the workflow JSON in `workflow.nodePositions` (map name→{x,y}). Each node also has a `position` field inside the JSON | VERIFIED |

## 2. Envelope (workflow record, not the definition)

`GET /api/v2/workflow/{id}` → `data.result.workflow` (VERIFIED):

```
id, name, description, version ("2.0.0"), tags[], workspaceId, template (bool),
canvasViewport (null|{x,y,zoom}), nodePositions {name:{x,y}}, workflow {…definition…},
previewImage (str|null), isImported, executionCount, createdAt, updatedAt, createdBy, updatedBy, agentId
```

Every workflow has a paired **Agent** record (`agentId`, entityType `"workflow"`, `workflowId`). The server creates it automatically when a workflow is created (VERIFIED). The Agent record's `config` holds **platform defaults** (openai/gpt-4o, cartesia, deepgram, `en`). That config does **not** match `workflow.agent_config` (Freya YC LLM / Freya TTS "leyla" / `tr`). The workflow UI displays `workflow.agent_config`. Which config wins at runtime is **UNKNOWN**, though INFERRED to be `workflow.agent_config`. See open-questions.

## 3. Root definition

```jsonc
{
  "initial_node": "identity",        // string, required (VERIFIED: missing → 422)
  "nodes": { "<key>": Node, ... },   // map; key == node.name in all observed data
  "global_nodes": { "<key>": GlobalNode },  // {} in baseline
  "system_prompt": "",               // string
  "test_variables": { "k": "v" },    // string values in baseline; default chat/test variables
  "agent_config": AgentConfig,       // LLM/TTS/STT/call settings (see §8)
  "tools": [ Tool, ... ]             // workflow-level ("Global Araçlar") tools
}
```

- Only these 7 keys appear in the definition (VERIFIED).
- The validator does **NOT** check that `initial_node` or `target_node` reference real nodes. A transition to `"does_not_exist"` was accepted (VERIFIED, branch v3), and so was `initial_node:"nowhere"` (VERIFIED, branch v11; reverted in v12). **The Builder must check references itself.**
- Reserved name: a node named `__exit__` must have `node_type: "exit"` (VERIFIED). INFERRED: the exit node must be keyed `__exit__`. A probe with an exit node keyed differently produced the "Reserved canonical name" error.

## 4. Node (strict schema: unknown keys rejected)

The schema is strict. `nodes.identity: Unrecognized key: "bogus_key2"` returned 422 (VERIFIED). All node types appear to share **one** key set, because `agent_id` is recognized on an `api_request` node.

### 4.1 `node_type` enum (VERIFIED from validator message)

`conversation | api_request | transfer_call | end_call | integration | reschedule_call | knowledge_base | code | invoke_agent | exit`

A node of every type with only `{name, node_type}` was accepted (VERIFIED, v5). The server stores nodes as sent and fills no defaults (VERIFIED). Runtime defaults are UNKNOWN.

### 4.2 Known node fields

| Field | Type / values | Tag | Notes |
|---|---|---|---|
| `name` | string | VERIFIED | Equals map key in all observed data |
| `node_type` | enum above | VERIFIED | |
| `role_message` | string | VERIFIED (present) | "" in baseline. INFERRED: persona/role prompt |
| `task_message` | string | VERIFIED | UI "DİYALOG PROMPTLARI" = node instruction |
| `on_enter` | discriminated union on `type`: `silent`, `tts` {text}, `llm` {…optional}, `audio` {asset_id required} | VERIFIED | UI "GİRİŞ". `tts.text` supports `{{var}}` |
| `on_enter_first_entry_only` | bool | VERIFIED (present) | |
| `passthrough` | bool | VERIFIED (present) | INFERRED: node runs without waiting for user turn |
| `passthrough_default_transition` | string\|null | VERIFIED (present) | INFERRED: target when passthrough |
| `interruptible` | bool | VERIFIED (present) | identity=false, collection=true |
| `return_to_previous_on_interrupt` | bool | VERIFIED (present) | |
| `disable_inactivity_monitor` | bool | VERIFIED (present) | |
| `max_node_turns` | number | VERIFIED (set 80→12 accepted) | INFERRED: turn cap in node |
| `max_turn_transition` | string\|null | VERIFIED (string accepted) | INFERRED: target node when cap hit. Runtime UNVERIFIED |
| `truncation_strategy` | `keep_all \| keep_recent \| summarize` | VERIFIED enum | |
| `truncation_window_size` | number | VERIFIED (present) | |
| `position` | {x,y} | VERIFIED (present) | Canvas only |
| `assertions` | string[] | VERIFIED (object → "expected string") | INFERRED: assertion IDs (`/api/v2/assertions`) |
| `extraction_schema` | [{name: string, type: `string\|integer\|float\|boolean\|date\|datetime\|enum\|name\|phone_number\|object`, …}] | VERIFIED (required name, type enum) | Other item fields (description, enum values) UNKNOWN |
| `response_mapping` | [{path: string, variable: string}] | VERIFIED (both required; extra key was accepted in a mixed probe) | INFERRED: map tool-response JSON path → state variable |
| `suppress_tool_results` | bool | VERIFIED (present) | |
| `tools` | Tool[] | VERIFIED | Tools available to the LLM in this node |
| `pre_actions` | Tool-shaped items (`type:"function"`, `function` object required) | VERIFIED shape | INFERRED: run on node entry before LLM |
| `transitions` | Transition[] | VERIFIED | |
| `agent_id` | string | VERIFIED (recognized) | INFERRED: for `invoke_agent` |

Checked and **not** valid node keys: url, method, headers, body, tool, function, request, transfer_number, phone_number, destination, code, python_code, kb_ids, knowledge_base_id, integration_id, message, timeout, variables, condition, prompt, description, config, handler, and about 40 more (VERIFIED "Unrecognized keys"). **How `api_request`, `transfer_call`, `code`, and `knowledge_base` nodes get their payload is UNKNOWN.**

## 5. Transition

```jsonc
{
  "target_node": "collection",              // string, REQUIRED (VERIFIED)
  "description": "both security answers verified",  // string; shown on canvas edge label
  "condition": Condition                    // OPTIONAL: key may be omitted (VERIFIED); null is INVALID (VERIFIED)
}
```

A transition with no `condition` passes validation. INFERRED: the routing LLM then decides from `description`. Runtime UNVERIFIED.

### 5.1 Condition (VERIFIED by validator probes)

Group form:
```jsonc
{ "logic": "and" | "or" | "not", "conditions": [ Leaf | Group, ... ] }   // nesting allowed
```
Leaf form (also valid directly as `condition`):
```jsonc
{ "variable": "verify_identity_response.data.all_verified",
  "operator": "equals",
  "operand": "true",          // string or number accepted
  "mode": "exact" }           // optional
```

| Item | Accepted | Rejected |
|---|---|---|
| `operator` | `equals, not_equals, contains, greater_than, less_than, is_set, is_not_set` | not_contains, gte/lte/gt/lt, greater_than_or_equal(s), exists, is_empty, is_not_empty, starts_with, ends_with, regex, matches, in, not_in, is_true, is_false, equal, not_equal |
| `mode` | `exact`, `llm` | fuzzy, semantic, case_insensitive, contains, regex, numeric |
| `logic` | `and`, `or`, `not` | xor |

- `mode: "exact"`: INFERRED to be a deterministic comparison. The baseline compares against both `"true"` and `"True"` with `or`, which suggests string comparison of a stringified Python/JSON value. INFERRED: values are stringified Python-side.
- `mode: "llm"`: INFERRED to be an LLM-judged condition, so it is **not deterministic**.
- `variable` path: `<tool_name>_response.<json path>` is used in the baseline (`verify_identity_response.data.all_verified`). INFERRED: every api_call tool's response is stored as `<tool_name>_response`. Mock response body shape is UNKNOWN (mock host unreachable from sandbox and browser CSP).
- No ≥/≤ operators. Express `x >= 3` as `not (x less_than 3)` (INFERRED to be equivalent).

## 6. Tool (node `tools[]`, root `tools[]`, `pre_actions[]`)

```jsonc
{
  "type": "function",                       // literal (VERIFIED)
  "function": {
    "name": "verify_identity",              // required (VERIFIED)
    "handler": "__function__:api_call",     // required; observed values: __function__:api_call, __function__:end_call
    "description": "…",                      // required
    "parameters": {                          // required object (JSON-Schema-like)
      "type": "object",
      "properties": {
        "url":     {"type":"string","default":"https://…/v1/verify_identity"},
        "method":  {"type":"string","default":"POST"},
        "headers": {"type":"object","properties":{"Content-Type":{"type":"string","default":"application/json"}}},
        "body":    {"type":"object","required":["field","answer"],
                    "properties":{
                      "field":{"type":"string","enum":["date_of_birth","phone_last4"],"default":"{{field}}","description":"…"},
                      "answer":{"type":"string","default":"{{answer}}"},
                      "customer_id":{"type":"string","default":"{{customer_id}}"}}}
      }
    }
  },
  "config": {
    "timeoutMs": 12000, "maxRetries": 0,    // VERIFIED editable (E4)
    "alwaysRunsAt": ["end_of_call"]         // enum each_turn | start_of_call | end_of_call (VERIFIED)
  },
  "pre_process_code": "python source"       // root tool close_call; Python with `config` dict in scope (VERIFIED present)
}
```

`api_call` convention (INFERRED from the baseline and the UI warnings):
- `url`, `method`, and `headers` are fixed through `default`.
- `body.properties.*.default: "{{x}}"` is a template. If `x` is a known variable (for example `customer_id` from test/customer variables), the value is injected. Otherwise the LLM supplies the argument (the `description` and `enum` guide it).
- The editor warns "Çözülmeyecek değişkenler" (unresolvable variables) for `field`, `answer`, `date`, `amount`, `product_id`, `reason`, and `outcome`. It says these are warnings that never block a call. Exact wording was not captured.

`end_call` handler parameters (baseline): `message_mode` ("none"), `interruptible`, `trigger_pattern` (regex, "Have a good day|have a good day"), `trigger_timeout`, `trigger_pattern_both`. INFERRED: the call ends automatically when the agent says a phrase that matches `trigger_pattern`.

Root `tools[]` (`close_call`, with `alwaysRunsAt:["end_of_call"]`) = "Global Araçlar". INFERRED: it runs once at call end and records the outcome.

## 7. GlobalNode

A Node plus a required `condition` (same Condition schema) and required `name`. Unknown keys are rejected (VERIFIED). INFERRED: it can be entered from any node when its condition matches, for example escalation or opt-out. Runtime UNVERIFIED.

## 8. agent_config (VERIFIED present; abbreviated)

`llmConfig{provider:"experimental-5", model, systemPrompt, firstMessage, firstMessageMode:"assistant-speaks-first", disableInterruptionsDuringFirstMessage, maxTokens, temperature, tools[end_call], additionalSettings}`,
`ttsConfig{provider:"Freya", model:"freya-tts", voiceId:"leyla", language:"tr", startSpeakingPlan, stopSpeakingPlan, textSubstitutions, speechNormalization, additionalSettings}`,
`sttConfig{provider:"Freya", model:"freya-stt", language:"tr", additionalSettings, confidenceReask}`,
`complianceConfig`, `callTimeoutSettings{silenceTimeout:10, maximumDuration:600, maxRetries:2,…}`, `voicemailDetection`, `dtmfConfig`, `postConversationAnalysis`, `privacyConfig`, `piiRedactionConfig`, `routingLlmConfig:null`, `extractionLlmConfig:null`, `backgroundSoundUrl`, `backgroundSoundVolume`, `syncSource`.

⚠ The baseline prompts say "Speak English", but TTS and STT `language` are `"tr"` with Turkish backchannel phrases. This is probably a template quirk. Check it before voice evaluation (open question Q4).

`routingLlmConfig` / `extractionLlmConfig` (null = default). INFERRED: separate models for transition routing and extraction.

## 9. Variables

- `{{name}}` interpolation in `task_message`, `on_enter.text`, and tool defaults (VERIFIED present).
- Sources (INFERRED): `test_variables`, or `customerVariables` per call (chat API, DOCUMENTED); tool responses as `<tool>_response`; `response_mapping` outputs; `extraction_schema` outputs; `{{now}}`.
- The UI shows "Değişkenler 29 / 7". INFERRED: 29 known variables and 7 unresolved.
