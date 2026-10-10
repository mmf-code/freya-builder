# Freya platform behaviour observed on 2026-10-10

Field observations from this repository's runs, with their evidence. They add to the official kit docs
(`docs/build-the-builder/docs/`), which stay the primary source. Each item says what was seen and where.

## Tool calls of one model message run concurrently

- Seen: the model emitted `add_note` and `close_call` in one message, `add_note` first. Both started within 8 ms and
  the bank recorded `close_call` first, then rejected `add_note` with "the call is already closed".
- Evidence: B agent 84719013, 13-case run (`runs/20261010-154045-kit-ab/eval/b-agent-all13.json`), PUB-05, PUB-08,
  PUB-12; also PUB-02, where `schedule_callback` overlapped `close_call` and the case passed by luck.
  `builder/callaudit.py` measures this per call.
- Consequence: order inside one message is not kept. A terminal tool must be offered in a step of its own
  (`builder/workflow_check.py` proves the graph property; see the candidate skill).

## Routing waits for all tool calls of a message

- Seen: in PUB-12 above, `close_call` completed at 38.88 s, the last `add_note` at 39.16 s, and the engine entered
  the next step at 39.17 s, after the whole batch.

## A model-called `code_exec` tool works; its arguments are in `params`

- Seen (chat route, probe workflow d507580f): a `code_exec` tool in a conversation step's `tools`, with a
  model-filled top-level property and the code as a baked `default`, ran when the model called it. The arguments
  reached the code as the dict `params` (`params["item"] == "apple"`), not in `vars`. Values the code wrote to
  `vars` were filled into the next reply's prompt (`{{fruit_count}}` showed the new value). After the call the
  variable table also held `<tool>_args.<field>`.
- Also seen: on the next turn the model answered without calling the tool again and repeated the old value. A
  model-called state tool can be skipped; check state again where it matters (for example in a bank tool's hook).
- Globals in the sandbox: `params`, `vars`, `_result`, `_tools`, `_json`, `_sys`, `_error`, `_traceback`, and two
  crypto helpers.

## When the Python sandbox is unreachable, successful bank calls look failed

- Seen: in the 13-case rerun of B agent 3aa5a39a (`runs/20261010-161811-candidate-ab/eval/b-agent-all13-diagnostic-rerun.json`)
  every failed call logged `function_call_error` "Failed to reach snekbox" while the bank answered `ok` to the
  same request. The agent then treated a passed identity check as failed and sent `create_promise` again after it
  had succeeded.
- Seen again at 17:37 to 17:57 (UTC+3), in 15 of 18 failed calls of a build's own tests. Another team reported
  the same error text in the event channel at about that time, so the outage was platform-wide, not ours.
- Consequence: an agent whose every tool depends on a hook inherits the sandbox's availability. A design that runs
  code on every customer answer, with steps that re-enter each other when code fails, turned one outage into
  hundreds of errors per call (316 in one call, then "maximum recursion depth exceeded"). Bound every loop.

## Silent stalls at the first model turn

- Seen: 23 calls between 13:41 and 13:47 UTC produced no model output after the customer's first answer and no
  error event; the same agent version passed before and after. Classified as infrastructure-suspected, not
  confirmed (`runs/20261010-161811-candidate-ab/eval/OUTAGE.md`).
