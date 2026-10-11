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
   - Every conversation step must give the model a line to say. Never write one whose prompt says to only call tools or to say nothing, and never route a bank write into such a step: in measured calls the model returned no speakable content after a write and the call went silent. Run a write whose arguments are already known as an engine step (`api_request` or `pre_actions`) and route on its result with variable conditions (its success and failure counts). When the model calls a write as a tool, its step says a sentence with each call, and its result routes to a step that speaks: on success the confirmation the brief requires, before any step toward the terminal step; on failure what the brief says to do. Never say a record is saved before the write succeeded. Keep every note, confirmation, transfer and terminal call the brief requires.
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
   - Say everything the brief wants said before the terminal tool (for example a confirmation sentence, thanks and goodbye) in a step before the terminal step, for example a passthrough step with a fixed `on_enter` line. Put no spoken line in the terminal step: in measured calls such a line was heard after the tool had run. A silent step must not wait for the customer: make a silent terminal step one the engine runs and routes on (for example a passthrough `api_request` step with `on_enter` `{"type": "silent"}` and an `always` transition), never a conversation step with a silent `on_enter`.
   - A line on a step the engine runs and passes through (an `api_request` or `code` step, or a passthrough step with `pre_actions`) can be heard after the tools of the steps that follow it: in measured calls a goodbye on such a step came after the terminal tool. When such a step leads to the terminal step with no conversation step in between, give it no spoken line. Say what the brief wants said after its tool (for example "I am connecting you now", thanks and goodbye) in a passthrough conversation step with a fixed `on_enter` line, entered only from that tool's successful result and leading to the terminal step. A failed result keeps its own route.
3. The check proves these graph properties. It does not prove what the model will say or call during a call. The test run shows that.

## Rules

- Never edit the agent on the platform by hand. Change the file and save it.
- When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not.
- A customer that passes once can fail the next time. Prefer rules in routes and code over rules in prompts.
