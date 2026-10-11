---
name: build-phone-agent
description: Build a Freya phone agent from a bank's brief, test it on the practice customers and fix what fails. Use when asked to build or improve a phone agent from a brief.
---

# Build a phone agent from a brief

Work from the kit folder. Use only what the brief and the tool API file say. Do not copy rules from another brief.

## Steps

1. Read the brief files you were given, then `tools/openapi.json`.
2. Read `docs/workflow-format.md` and `docs/tools-and-code.md`.
3. Read `examples/base-agent.json`. It is a small working agent with two steps. Use it as the pattern for the JSON, not as the answer.
4. Write the workflow to `out/<slot>.workflow.json`. `<slot>` is the brief's file name without `.md`.
   - One step per stage of the call. Identity comes first.
   - Move to the next step on a tool result, not on what the customer says.
   - Take every tool field and allowed value from `tools/openapi.json`.
   - Leave `agent_config` out.
   - Build terminal tools as described in "Terminal tools" below.
   Then check it: `python3 tools/check_workflow.py out/<slot>.workflow.json --tools tools/openapi.json --contract out/<slot>.contract.json`. Fix every ERROR before you save. Do this before every save.
5. Save it: `python3 -c "import freya,json,sys; print(json.dumps(freya.save_workflow(sys.argv[1], json.load(open(sys.argv[2])))))" <slot> out/<slot>.workflow.json`
   It prints `workflow_id` and `agent_id`. The same slot updates the same workflow.
   Save only your agent's slot. Every saved slot is exported and checked like your agent, so never save a probe or a variant under another slot.
6. Test it on practice customers, if your brief has any. `public-test-set.json` lists only the practice customers of the brief files you were given. If it is empty, your brief has none: do not run `tools/run_cases.py`, and do not take customers, rules or expected results from anywhere else. Then the check in step 4, a reading of your workflow against every rule of the brief and the chat tests below are your tests. Otherwise test each agent on the listed customers of its own brief: `python3 tools/run_cases.py <agent_id> --brief <letter>`, where `<letter>` is the `brief` field of those customers. A run takes 3 to 11 minutes. Run it in the foreground and wait for it to finish. Never start it in the background and never end your turn while a test is running: the builder stops when you stop.
   Chat tests, when there are no practice customers: talk to the saved agent through the chat API (`docs/api.md`, "Talk to your workflow turn by turn").
   - Write 4 to 6 short test conversations from the brief files only: the example conversations they contain, and the test customers they list, with those customers' own data (the bank's tool API answers for them). Cover a success, a refusal, a failed identity check, a failed tool call if the files describe one, and the call with the most items.
   - Start a call with `freya.api("POST", "/api/v2/chat/message", {"workflowId": <workflow_id>, "message": <first customer line>, "customerVariables": {<the call variables the brief defines>}})`. It returns `response` and `callId`. Send each next line with that `callId`, written from the agent's last reply as that customer would answer. End with `freya.api("POST", "/api/v2/chat/end", {"callId": <callId>})`.
   - After each call read `freya.get_call(<callId>)["messages"]`: the steps entered, the tool calls with their arguments and results. Check them against the brief: identity before anything else, the right records with the right amounts and dates, every required note and confirmation, nothing called recorded before its write succeeded, every line the brief wants before the terminal tool said before it, no silence after a tool result.
   - An HTTP error or a timeout of the chat route is a platform problem, not a test result: try that call once more, then go on. If the first step is a code step the chat route may skip it (`docs/api.md`), so a value it computes can be empty in a chat test.
   - The chat route starts with a customer line. A real call starts with the agent: the platform's simulated customer waits for the agent to speak first. Keep an opening in which the agent speaks first. Never make the first step silent, and never make the agent wait for the customer, to get a chat test through. If the chat route hangs or times out on the opening, that is a limit of the chat route: test the later steps in chat, and check the opening with the simulation below.
   - Opening check, once, right after the first save, in the foreground: create one persona from an example conversation of the brief files with `freya.create_personas([{"name": ..., "prompt": ..., "successCriteria": ..., "tags": ["builder-check"]}])`, then run `freya.run_simulation(<agent_id>, <name>, {<persona_id>: {<the call variables the brief defines>}}, max_seconds=240)`. It returns the simulation id, the iteration id and the status. Read the call with `freya.get_call(freya.get_iteration(<simulation_id>, <iteration_id>)["runs"][0]["callId"])["messages"]`. The agent must speak first and the call must go on past the first exchange. If it does not, fix the opening before any other test.
   - These tests are not the bank's scoring. Before the first one, look at the start time on the first line of `traces/*.jsonl`; stop testing 20 minutes after it and finish.
7. Read each FAIL line and its reason, or each chat test finding. Change the workflow file, save it again, test again. Do this at most three times.
8. Finish with one line: the `workflow_id`, the `agent_id` and how many customers passed in the last run.

## Terminal tools

A terminal tool is one after which the bank accepts no other call, for example a call that ends the conversation.

1. Find every terminal tool in `tools/openapi.json` and the brief. Write `out/<slot>.contract.json`:
   `{"terminal_tools": [{"tool": "<path name in the tool API>", "evidence": [{"source": "<file>", "quote": "<exact sentence>"}]}], "every_call_ends_with_terminal": <true|false>}`
   Each quote must be copied exactly from the file it names (`tools/openapi.json` or `briefs/<file>`). Set `every_call_ends_with_terminal` to true only when the brief says every call ends with that tool.
2. The platform runs all tool calls of one model message at the same time, so their order inside a message is lost. A prompt rule cannot fix that. Build the order into the graph:
   - Offer a terminal tool in its own step, where no other bank tool is offered. Every other step reaches that step with a tool-call transition (`is_tool_call: true`), once its own bank calls are done.
   - From that step, go only to `end_call` steps. No step after it may offer or run a bank tool. Exclude it from global steps that offer bank tools.
   - When `every_call_ends_with_terminal` is true, enter `end_call` steps only from that step, including `max_turn_transition` targets.
   - Give the terminal step what it needs to choose the tool's arguments: the variables, and the rules from the brief that decide them.
3. The check proves these graph properties. It does not prove what the model will say or call during a call. The test run shows that.

## Rules

- Never edit the agent on the platform by hand. Change the file and save it.
- When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not.
- A customer that passes once can fail the next time. Prefer rules in routes and code over rules in prompts.
