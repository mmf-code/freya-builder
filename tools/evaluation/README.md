# Evaluation scripts

The scripts behind the run records of 2026-10-10. Each reads credentials from `docs/build-the-builder/env.sh` with
`builder.kitrun.load_env` and never prints them. Run them from the repository root with `python3 -I`. They do not
build and do not save workflows; the ones marked "simulation" start Freya simulations, one at a time.

| Script | Use | Calls Freya |
|---|---|---|
| `evaluate.py REPO RUN_DIR AGENT_ID A\|B NAME [--reps N] [--cases FILE]` | Official practice customers against one agent, from the run's workspace; raw output to `RUN_DIR/eval/NAME.json` and `.log`. Pass `--cases docs/build-the-builder/public-test-set.json` for a build that had no practice customers | simulation |
| `classify.py REPO RESULTS.json ... [--json OUT]` | Combines result files per customer (a customer counts when every run passes) and labels each failed call from its own error events: infrastructure only for sandbox, DNS or connection errors | read only |
| `reexport.py REPO RUN_DIR STATE_DIR` | Exports the run's saved workflows again (for example after an API outage) and reruns kitrun's post-build checks | read only |
| `pl_semantic.py REPO RUN_DIR SCENARIO` | Persona Lab blind builds: runs the export's code steps with the key's `now` and compares the deadlines and callback window the code computes with the key | none |
| `api_mutations.py REPO RUN_DIR [SLOT ...]` | Lowering runs: re-lowers the builder's body and plan against mutated tool APIs and reports which mutations the lowering or the checker catch | none |
| `transcript.py REPO CALL_ID` | Dialogue of one simulated call with tool calls and step changes | read only |
| `policy_audit.py PATH ... \| --fetch REPO RESULTS.json ...` | Public-brief rules the ledger cannot see and the judge has missed (goodbye after `close_call`, "recorded" too early, text-message sentence, "today?" again, skipped product or attempt, product order, weekday), per call with the sentence it fired on. PATH: Persona Lab raw records or their directories | none; read only with `--fetch` |
| `api_probe.py REPO` | One read call to see whether the API answers | read only |
| `secret_scan.py REPO < FILE_LIST` | Fails loudly if any env.sh secret value occurs in the listed files; prints only names | none |

What each proves: `classify.py` gives per-customer counts and infrastructure labels, not causes; read the transcript.
`policy_audit.py` is a set of text heuristics for Brief A and B: a finding is a pointer to a sentence, confirm it by
reading; no finding does not prove compliance with the rest of the brief.
`pl_semantic.py` shows what the code computes for one `now`, not what the model says. `api_mutations.py` tests the
static contract layer, not whether a builder adapts to a changed API.
