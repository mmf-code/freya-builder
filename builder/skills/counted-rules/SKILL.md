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
6. Test it on practice customers, if your brief has any. `public-test-set.json` lists only the practice customers of the brief files you were given. If it is empty, your brief has none: do not run `tools/run_cases.py`, and do not take customers, rules or expected results from anywhere else. Then the check in step 4 and a reading of your workflow against every rule of the brief are your tests. Otherwise test each agent on the listed customers of its own brief: `python3 tools/run_cases.py <agent_id> --brief <letter>`, where `<letter>` is the `brief` field of those customers. A run takes 3 to 11 minutes. Run it in the foreground and wait for it to finish. Never start it in the background and never end your turn while a test is running: the builder stops when you stop.
7. Read each FAIL line and its reason. Change the workflow file, save it again, test again. Do this at most three times.
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

## Counted and ordered rules

When the brief limits or orders what the agent may do for each item (attempts per product, offers that come in a
set order, a question that may be asked again only once), do not leave the counting to the model. It loses count,
adds offers and repeats questions.

- Keep the state in variables written by code: for each item, what has happened and the next action the brief
  allows. Take the limits, the order, the amounts and the dates from the brief and from tool results.
- Give the model one `code_exec` tool in the conversation step to move the state. Declare what the model fills in
  (for example the item, and how the customer answered as an `enum`) as top-level properties without `default`, and
  the code as a baked `default`. Inside the code the model's arguments are in the dict `params`, not in `vars`. The
  code writes the new state and the next allowed action to `vars`.
- Show the model the state and the next allowed action in the prompt with `{{variable}}`. The prompt is filled in
  again after the tool result. Tell the model to offer only that action and to call the tool after every answer
  that changes the state.
- The model can still skip the tool. Where a bank tool acts on an item, check the state again in that tool's
  pre-hook when the brief makes the check possible.

## Rules

- Never edit the agent on the platform by hand. Change the file and save it.
- When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not.
- A customer that passes once can fail the next time. Prefer rules in routes and code over rules in prompts.
