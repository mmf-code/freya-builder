# Freya Build the Builder — Verified v3 Kit Review

**Reviewed:** 2026-10-10  
**Source:** User-uploaded `/mnt/data/build-the-builder-v2.zip`  
**Result:** Despite its `v2` filename, it is byte-for-byte identical to the official v3 package hosted at `https://www.freyavoice.ai/hackathon/build-the-builder-v3.zip`.  
**SHA-256 (both):** `655cbe581b0b0a7fba1f62ebd7d8c806edcfcc43f4d4fd47a27dca1e2534413a`  
**Version file:** `3`. README calls it v3, October 10, 2026.

## 1. What was actually inspected

All named contents were listed; all Python sources were syntax-parsed, and all JSON files were parsed successfully. The main implementation files and both briefs were read. No authenticated Freya test call or simulation was performed during this review: no API key was supplied.

| Source | Role / findings |
|---|---|
| `README.md` and `VERSION` | Event-specific runtime contract; v3 fixes example-builder waiting for test completion. Claims the example builder passed 10/10 Brief A cases in one run. |
| `briefs/brief-a.md` | 47 numbered rules; single-product collections; identity, privacy, business-day calculations, persuasion and outcome policies. |
| `briefs/brief-b.md` | 11 overriding/additive multi-product rules; up to 3 products, per-product dates and attempts, split promise/note outcomes. |
| `tools/openapi.json` | Seven allowed bank endpoints and their request/response JSON schemas. |
| `public-test-set.json` | 13 actual synthetic cases: 10 A and 3 B; 1 easy, 7 medium, 5 hard. |
| `freya.py` | Working reference client for creating/updating/publishing/exporting workflows and running simulations. Standard library only. |
| `examples/base-agent.json` | Two conversation nodes (`identity`, `collection`), 4 node-local tools and root `close_call`; no `agent_config`. Baseline is intentionally weak. |
| `examples/agent_builder.py` | Claude Agent SDK reference Builder; project-local skill; trace in `traces/<timestamp>.jsonl`; foreground tool execution. |
| `.claude/skills/build-phone-agent/SKILL.md` | Sample read → compile → save → simulate → revise skill; at most three revision loops. |
| `tools/run_cases.py`, `tools/score.py` | Create practice sessions, run chat-mode simulations, score the mock-bank ledger and transcript judge, emit per-case failure reasons. |
| `docs/api.md` | Event-specific workflow REST client paths, dry-run, publish, chat, simulations, call-log routes, required browser-like User-Agent. |
| `docs/workflow-format.md` | Current v3 node types, transitions, loops, extraction, code, global nodes, end-call and runtime limits. |
| `docs/tools-and-code.md` | Tool parameter binding, result variables, pre-actions, hooks, lifecycle tools, code sandbox, retries, common failure patterns. |
| `env.example` | `FREYA_API_KEY`, `FREYA_API_URL`, `FREYA_BANK_TEAM_KEY`; keep secrets out of commits and traces. |

## 2. The definitive task and scoring contract

The entrant submits a **builder**, not a hand-edited phone agent. It must take the provided brief(s) and their OpenAPI description and produce a Freya workflow **without manual changes**. The organizer scores the exported workflows and reruns leading builders from the submitted Git commit to verify reproducibility. Each hidden brief gets a builder trace.

Final: 2 unseen briefs, 30 cases each, 3 runs per case; a case passes only if all 3 runs meet **outcome + policy + honesty**, no partial credit. Outcome is verified against the bank's actual ledger (not the assistant's claims); policy and honesty are checked by a model against the conversation. Tie-breakers: promised sum from passing cases, then builder time, then earlier submission.

A Builder run must finish within **30 minutes per brief, including its own tests**. Freya supports 200 workflows per workspace and only 1 active practice simulation per workspace. Update an existing slot instead of creating a new workflow per iteration. Calls are English; dates use call variable `now`, not machine time.

**Calendar ambiguity:** Official public page states hidden briefs open Sun Oct 11 **17:00 UTC = 20:00 Istanbul** and close 20:00 UTC = 23:00 Istanbul. Kickoff notes used a conflicting local time; reconfirm in organizer chat.

## 3. OpenAPI contract: exact seven names

`verify_identity(customer_id, field, answer)`: `field` enum `date_of_birth | phone_last4`. Response may have `ok`, `error`, `verified`, `wrong_answers_left`, `all_verified`, `hint`. `hint` may be `day_month_swapped`. An invalid date format is not necessarily a counted wrong answer.

`get_account(customer_id)`: may return `ok`, `error`, `products[]` including `product_id`, `type`, `past_due`, `days_late`, `minimum_payment` (credit card), `instalment_amount` (loan), `card_last4`.

`create_promise(customer_id, product_id, amount, date)`: `date` ISO date, response may include `ok`, `error`, `promise_id`.

`add_note(customer_id, product_id, reason, text?)`: `reason` enum `refused | hardship | dispute | paid | service_error`.

`schedule_callback(customer_id, date, time)`: `date` ISO date; `time` HH:MM.

`transfer_to_agent(customer_id, queue)`: `queue` enum `restructuring | general | support`.

`close_call(customer_id, outcome, reason?)`: `outcome` enum `promise | paid | transferred | no_promise | not_verified | not_reached`. Reason depends on the brief, not an arbitrary model invention.

**All banking tools may return HTTP 200 with `ok:false`, and 500 for failure. The API does not enforce brief-specific business rules.** A successful HTTP call is not proof that the business action was accepted.

Hidden OpenAPI files keep these tool **names**, but parameter names, enums and allowed values may change: parse their exact schema each run rather than hardcode these public values.

## 4. Brief A: important rules the generated agent must enforce

- Opening explicitly identifies the bank's *recorded digital-assistant call*, but never mentions collections, debt, payment or product before identity verification.
- Confirm it is the intended person (up to 2 asks); third-party callbacks only today/next business day between 10:00 and 19:00, later than `now`. No protected information or identity tool calls with relatives.
- Verify DOB and phone last-four, **one question and API call at a time**; up to 3 wrong answers total, with `day_month_swapped` handled specially. No account lookup before both checks pass.
- Early (1–7 days late) deadline: 12th business day after now, 1 persuasion attempt. Late (8–45) deadline: 7th business day after now, 2 persuasion attempts. Business days exclude weekends and the provided holiday set.
- Amount floor is `minimum_payment` or `instalment_amount`, depending on product. Never ask the customer to invent a payable amount; offer full amount then authorized floor.
- Customer-proposed dates/amounts are **not refusals**. Handle vague dates with one clarification; holiday/weekend and deadline issues using code and `now`.
- Hardship (illness, bereavement, job loss) supersedes persuasion: empathy, offer support transfer once; otherwise close hardship. No invented discounts or payment plans.
- `create_promise` only after exact product/amount/date read-back and clear confirmation. On failure, explicitly retry once; no success claim before `ok:true`. Send prescribed SMS confirmation sentence after success.
- Already-paid, dispute, restructuring, human-request and fraud-concern each have distinct outcomes and procedures.
- Every call must end in **exactly one `close_call`**, as the last bank tool call; outcome and reason must match the brief.

## 5. Brief B: rule overrides, not an independent brief

- Inherits all A rules unless overridden; 1–3 products, per-product floors, delinquency bands, dates and persuasion counters.
- State all products before the first payment question. Ask about paying *all* today once; then go product-by-product if necessary.
- One proposed date can be valid for one product but outside another's deadline; split dates and disclose them on the shared read-back.
- Ask for **one confirmation** of all agreed promises, then `create_promise` once per promised product.
- Record `add_note` for non-promised products, but **never add notes on a transfer**; preserve already-recorded promises; do not record agreed-but-unrecorded ones on transfer.
- A `create_promise` failure twice creates a `service_error` note for that product without discarding successful promises for others.
- Closing outcome priority: transferred on transfer; otherwise promise if any promise recorded; with none, paid only if all products paid; otherwise no_promise with the first non-paid product's reason in account order.

## 6. Practice test index

| Case | Source | Main assertion family |
|---|---|---|
| PUB-01 | A | Verified happy path, exactly one promise and SMS statement |
| PUB-02 | A | Third-party secrecy and next-day callback; no identity tool |
| PUB-03 | A | Three incorrect identity answers, terminate without disclosure |
| PUB-04 | A | Out-of-deadline date, correct deadline and digital-assistant honesty |
| PUB-05 | A | Hardship, sympathy, support offer, no pressure or discount |
| PUB-06 | A | Full-to-floor payment without 'how much can you pay' |
| PUB-07 | A | Vague date, public holiday and next valid business day |
| PUB-08 | A | Already paid, no promise |
| PUB-09 | A | Restructuring handoff, no invented plan |
| PUB-10 | A | First promise tool failure, retry and one recorded entry |
| PUB-11 | B | Three products, single confirmation, 3 promise writes |
| PUB-12 | B | Verification retry, one promise, two refusal notes, per-product attempts |
| PUB-13 | B | Different allowed dates by product, both read back |

**Static checks performed:** all 4 `.py` files syntax-parse; all 3 `.json` files parse. **Not performed:** any API-key authenticated workflow create, chat interaction or live practice simulation. README's 10/10 example score is the organizer's report, not an independently rerun result.

## 7. Changes relative to Claude-in-Chrome handoff (do not copy its assumptions unchanged)

1. **Follow the v3 event docs and `freya.py` first.** Browser-observed staging behavior is useful evidence but does not cover all valid schema/runtime combinations.
2. **Leave `agent_config` out of Builder-authored JSON.** The event's `freya.py` controls the mandated Freya model and publish flow. Do not change `AGENT_LLM`.
3. **Use `freya.save_workflow`**, which creates once, then updates and publishes. Plain `PUT` leaves a nonpublished version; a simulation then continues to run the previous version.
4. **Use documented dry-run validation:** `POST /api/v2/workflow?dryRun=true` / `freya.validate_workflow`. It tests structural validity, not policy correctness. Read the saved workflow back where field stripping may occur.
5. **Update the local validator** before using it with generated v3 workflows: it lacks `always`, `matches_intent`, `routing_prompt`, `loop_condition`, `loop_prompt`, `terminal`, `context_variables`, among other v3 keys. It may incorrectly reject valid workflows.
6. **Tool placement matters:** `tools` on conversation nodes, `pre_actions` on api_request/code nodes. The server may silently strip incorrectly placed fields.
7. **For HTTP tools, use `default` not `const`** for baked URL/method/header/customer_id; model-filled body fields reside under `body.properties` with `default:"{{field}}"`, field schema and enum. `response_mapping` of model-invoked tools belongs on the tool, whereas pre_actions mapping belongs on the node, and paths normally start with `data.`.
8. **Condition precedence:** deterministic branches and their order matter. `always` exists; `matches_intent` uses routing LLM. A bare `all_verified:false` is *not* by itself proof of final verification failure. Build based on documented `wrong_answers_left` and field-level success semantics, then verify in runtime.
9. **Use code nodes / pre/post-hooks for deterministic dates, amounts, state and helpful tool-result instructions**, not only LLM prompts. Tool returns can cause the model to be silent or ignore negative results; docs report better behavior when a post-hook adds an explicit `what_to_do_next` field.
10. **Writes must not use blind automatic retries.** `connect_retries` covers failures before the request reaches the bank; automatic retry of a non-idempotent write can duplicate ledger entries. Follow brief-specific retry rules and inspect `ok`.
11. `end_call` terminal, goodbye text, and workflow-level `close_call` lifecycle deserve an actual test: speaking goodbye is not enough for the ledger to close correctly.
12. The official API docs identify **`GET /api/v2/call/{callId}` singular**, not `/calls/{id}` used in the Chrome handoff. It yields assistant/user/system events with `node_enter`, `function_call_*`, `route_evaluated`, and `error`.
13. Avoid searching for or depending on unsupported UI-internal calls now that the official kit documents workflow creation, validation, publish and export.

## 8. First-run commands from the official README

From the extracted kit root (Python >= 3.10; only mock data):

```bash
cp env.example env.sh
# Edit env.sh locally: FREYA_API_KEY and FREYA_BANK_TEAM_KEY
source env.sh
python3 -c "import freya,json; print(freya.save_workflow('base', json.load(open('examples/base-agent.json'))))"
python3 tools/run_cases.py <agent_id> --brief A --out results/baseline-a.json
pip install claude-agent-sdk
python3 examples/agent_builder.py briefs/brief-a.md
python3 examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md
```

Example Builder requires Claude login or `ANTHROPIC_API_KEY`. Its trace is `traces/<timestamp>.jsonl`. The kit's default `BUILDER_MODEL` should be tested against the team's actual Claude SDK access; avoid silently changing the Freya phone agent model.

For final-style testing after a working agent exists:

```bash
python3 tools/run_cases.py <agent_id> --brief A --reps 3 --style pieces --out results/a-pieces.json
python3 tools/run_cases.py <agent_id> --brief B --reps 3 --style corrects --out results/b-corrects.json
```

`--reps 3` requires all three passes; `--style` can be `pieces`, `corrects`, `talkative`, `asks_back`, or `in_words`.

## 9. Recommended execution order

1. **Do not build a new Freya framework.** Run the existing v3 example; verify key, workspace, agent creation, published version and at least one actual simulated case.
2. Clone the example skill and builder in a working branch, retaining its trace and foreground test execution.
3. Add a brief merger/compiler that can interpret Brief B *as an override to A*, then handle new hidden OpenAPI enum/schema values from files, not from hardcoded public examples.
4. Generate code-backed calendar and amount decisions with `now`; isolate privacy gates, tool failures and outcome finalization. Use pure unit tests to test dates/amounts without consuming simulator time.
5. After each tested revision run a targeted set, then full `--reps 3` on both briefs when worthwhile. Keep the best published workflow and export trace-linked JSON.
6. Budget at most 30 minutes for each final brief Builder invocation, including tests. Ensure a trace records model calls, elapsed time, output workflow/agent IDs, and results.

## 10. Verified vs still outstanding

**Verified locally:** ZIP version/hash, file syntax/JSON validity, contents and published API contracts, sample Builder and scoring logic as source code.  
**Documented by Freya / organizers, not independently re-run here:** staging API working behavior, 10/10 Brief A example claim, actual simulator and model behavior.  
**Still required with team's Freya key:** server-side dry-run; save + publish; at least one chat/test case and call log; success/failure routing; file export; three-run reliability.  

**Priority principle:** For this competition, a pleasant conversation that leaves the wrong bank ledger state is a failing conversation. Design workflow tool actions, correctness checks and closing first; optimize wording second.
