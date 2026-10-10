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
4. Write the workflow in two parts, as described in "Endings" below. `<slot>` is the brief's file name without `.md`.
   - `out/<slot>.closing.json`: the plan of every way a call ends.
   - `out/<slot>.body.json`: every other step. One step per stage of the call. Identity comes first.
   - Move to the next step on a tool result, not on what the customer says.
   - Take every tool field and allowed value from `tools/openapi.json`.
   - Leave `agent_config` out.
   Then lower it: `python3 tools/lower.py out/<slot>.body.json out/<slot>.closing.json --tools tools/openapi.json -o out/<slot>.workflow.json --contract out/<slot>.contract.json`.
   It writes `out/<slot>.workflow.json` and `out/<slot>.contract.json`. If it prints REJECTED, fix the body or the plan and lower again.
   Then check it: `python3 tools/check_workflow.py out/<slot>.workflow.json --tools tools/openapi.json --contract out/<slot>.contract.json`. Fix every ERROR in the body or the plan, and lower again before you save. Do this before every save.
5. Save the lowered file: `python3 -c "import freya,json,sys; print(json.dumps(freya.save_workflow(sys.argv[1], json.load(open(sys.argv[2])))))" <slot> out/<slot>.workflow.json`
   It prints `workflow_id` and `agent_id`. The same slot updates the same workflow.
6. Test it on practice customers, if your brief has any. `public-test-set.json` lists only the practice customers of the brief files you were given. If it is empty, your brief has none: do not run `tools/run_cases.py`, and do not take customers, rules or expected results from anywhere else. Then the check in step 4 and a reading of your workflow against every rule of the brief are your tests. Otherwise test each agent on the listed customers of its own brief: `python3 tools/run_cases.py <agent_id> --brief <letter>`, where `<letter>` is the `brief` field of those customers. A run takes 3 to 11 minutes. Run it in the foreground and wait for it to finish. Never start it in the background and never end your turn while a test is running: the builder stops when you stop.
7. Read each FAIL line and its reason. Change the body or the plan, lower, check, save it again, test again. Do this at most three times.
8. Finish with one line: the `workflow_id`, the `agent_id` and how many customers passed in the last run.

## Endings

A terminal tool is one after which the bank accepts no other call, for example a call that ends the conversation.
The platform runs all tool calls of one model message at the same time, so a terminal call offered next to another
bank tool can land first. You do not write the terminal tool, its steps or the `end_call` step. You declare the
endings, and `tools/lower.py` writes them. This is required: the lowering rejects a body that offers or runs the
terminal tool, or that has an `end_call` step.

1. Find the terminal tool in `tools/openapi.json` and the brief. Write `out/<slot>.closing.json`:
   ```json
   {"terminal": {"tool": "<path name in the tool API>", "evidence": [{"source": "<file>", "quote": "<exact text>"}]},
    "fields": {"<request field that is the same in every ending>": "{{<variable>}}"},
    "closings": {
      "<id>": {"set": {"<request field>": "<value>"}, "say": "<optional fixed farewell>",
               "evidence": [{"source": "<file>", "quote": "<exact text that gives these values>"}]}}}
   ```
   - One closing for every distinct way a call ends that the brief describes. If two endings send the same values but
     must say different things, they are two closings with different ids. Use short ids such as `no_promise/refused`.
   - Each value is one of the tool API's allowed values for that field, or appears in that closing's quote.
   - Copy each quote exactly from the file it names (`tools/openapi.json` or `briefs/<file>`).
   - Every required field of the terminal tool is set in each closing or mapped in `fields`.
2. In `out/<slot>.body.json`, route to an ending with the target `close:<id>`. Use it in `target_node`,
   `passthrough_default_transition` and `max_turn_transition`.
   - Choose the ending with a deterministic transition on a tool result where one decides it. Otherwise use a
     tool-call transition (`is_tool_call: true`) whose description says when that ending applies, from the brief.
   - Enter an ending only after the step's own bank calls are done.
   - Say goodbye in the conversation step before the ending, or give the fixed farewell in `say`.
   - Never edit `out/<slot>.workflow.json` by hand. Change the body or the plan and lower again.
3. The lowering writes one step per closing that runs the terminal tool with the declared values and then ends the
   call. The check proves these graph properties. It does not prove what the model will say or which ending it picks
   during a call. The test run shows that.

## Rules

- Never edit the agent on the platform by hand. Change the file and save it.
- When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not.
- A customer that passes once can fail the next time. Prefer rules in routes and code over rules in prompts.
