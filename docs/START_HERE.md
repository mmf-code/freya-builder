# Freya Build the Builder — current source of truth (2026-10-10)

> **Update 2026-10-11:** builds now run through `builder/kitrun.py` with a skill from `builder/skills/` and a fresh
> `--state` directory; see `docs/BUILDERS.md` (candidates, results) and `docs/FINAL_RUNBOOK.md` (final day). The
> "First commands" and "Immediate implementation plan" below are the plan of the morning of 2026-10-10.
> Known failures, their causes and the engineering preference that follows: `docs/FAILURE_MODES.md`. The one open
> candidate and its switch rule: `docs/REFERENCE_V2.md`. Current state: `docs/STATUS.md`.

> **Read this first.** The original pre-kit README, FINDINGS and INTEGRATION_CHECKLIST capture a useful earlier stage. Their claims that the official materials have not yet arrived are historical, not the current project state.

## The authority order

1. **Official event kit v3:** `docs/build-the-builder/README.md`, `docs/build-the-builder/docs/{api,workflow-format,tools-and-code}.md`, `docs/build-the-builder/tools/openapi.json`, the supplied briefs and tests. This is the event-specific contract. Do not edit the vendored originals.
2. **Observed Chrome staging evidence:** `inputs/chrome/observations/`. These files establish a few browser/API experiments, NOT a complete v3 runtime contract. The 638-line browser baseline is NOT the official kit base-agent template.
3. **Secondary audit:** `docs/research/FREYA_V3_KIT_VERIFIED_REVIEW.md` and `docs/PREKIT_AUDIT.md` summarize the preceding sources. Neither overrides a source file.
4. **Original pre-kit implementation:** `builder/{ingest,model,extract,validate,jsondiff}.py` and its tests. This is supporting tooling, not an end-to-end Freya workflow generator.

If the sources disagree, prefer the official event docs, verify in the team's API-key workspace, and record the discrepancy. Do not treat server schema validation as proof of runtime behavior.

## Keep, adapt, do not promote

| Current file | Decision | Why |
|---|---|---|
| `builder/ingest.py` | **KEEP, EXTEND** | Source references and Markdown/JSON segmentation are useful. It does not semantically interpret policy tables or conflicting memos. |
| `builder/model.py` | **KEEP AS AUXILIARY IR** | Traceability is useful; current IR cannot express calendar calculation, full table semantics, product-scoped state and precedence without extension. |
| `builder/extract.py` + `lexicon.py` | **KEEP AS A SECONDARY HEURISTIC / GAP FINDER** | In official Brief B, 5 of 11 numbered rules are unclassified; do not compile workflow directly from its output. |
| `builder/validate.py` | **KEEP FOR SOURCE/AUDIT CHECKS** | Doesn't establish full rule coverage or Freya schema validity. |
| `builder/jsondiff.py` | **KEEP** | Can compare official/staging structures and generated versions. |
| `briefs/synthetic/`, `tests/` | **KEEP** | 89 unit tests pass; these do not test runtime behavior or correctness on official briefs. |
| `docs/build-the-builder/` | **LEAVE UNEDITED** | Official v3 reference client, SDK builder, skills, workflow specification, mock API and practice test runner. |
| `inputs/chrome/observations/` | **ARCHIVAL REFERENCE ONLY** | Browser experiments and raw baseline, not templates to deploy. |
| `docs/INTEGRATION_CHECKLIST.md`, `docs/FINDINGS.md` | **HISTORICAL** | Some assumptions and unchecked tasks are superseded by this document. |

**Do not copy** the older Chrome `validate_workflow.py` to the active code path: its operator/node-key whitelist predates the v3 kit (e.g. lacks `always`, `matches_intent`, `terminal`, `routing_prompt`, `loop_condition`). **Do not use** `v10_E6.json` as a baseline: it is an isolated experiment and its `all_verified == false` exit is not proven safe.

## Official kit specifics that override Chrome investigation

- **Starting template:** `docs/build-the-builder/examples/base-agent.json`, then use the event's `freya.py` and sample SDK builder. Omit `agent_config` from builder-authored JSON; preserve the event-mandated Freya model managed by `freya.py`.
- **Auth/host:** API key from the dashboard; staging base and required browser-like User-Agent are explained in kit `docs/api.md`. Never put secrets in Git or traces.
- **Creation and publishing:** `freya.save_workflow(slot, workflow)` creates or updates and publishes. `PUT` alone leaves an unpublished version; simulations can still use an earlier one. Use `freya.validate_workflow(...)` / API dry-run, but read back the saved workflow to detect fields stripped silently.
- **Tool placement:** conversation `tools` (LLM chooses), `api_request`/`code` node `pre_actions` (engine runs). Some wrong-node fields can be silently dropped. For tools, `default` (not `const`) bakes request parameters. Tool response mappings differ by placement.
- **Tool outcome:** HTTP 200 may contain `ok:false`. Do not equate HTTP success with business success. Only allowed mock-bank API tools may be called by the Phone Agent.
- **Hard invariants:** no account disclosure before identity; `close_call` once and last; product-scoped date/attempt logic; no unsupported payment promises; recorded only after tool success.
- **Testing:** `run_cases.py` is the official scorer, one concurrent simulation per workspace, ~3–11 minutes for 10 cases. Three repeat runs are needed to approximate final stability; avoid spending the 30-minute per-brief Builder limit on uncontrolled loops.
- **Submission:** two hidden briefs, one generated phone agent per brief, exported workflow JSON, Git commit with runnable Builder and one sanitized trace per brief. No hand-edited hidden workflows and no hidden-brief-specific rules embedded in the Builder. Final event times: check official site and organizer announcements; site shows 17:00–20:00 UTC on Sunday.

## First commands (no speculative integrations)

Run from **the vendored kit directory**; the sample code and its skill assume that working directory:

```bash
cd docs/build-the-builder
cp env.example env.sh
# Add own credentials to env.sh; keep it ignored and never print keys.
source env.sh
python3 -c "import freya,json; print(freya.save_workflow('base', json.load(open('examples/base-agent.json'))))"
python3 tools/run_cases.py <agent_id> --brief A --out results/baseline-a.json
pip install claude-agent-sdk
python3 examples/agent_builder.py briefs/brief-a.md
python3 examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md
```

Use `--reps 3` for important reliability tests once the agent functions. **Do not run overlapping simulations** in the same workspace. `AGENT_LLM` in the kit is fixed for the event: never change the Phone Agent model.

From the **repo root**, the older prep code remains independently runnable:

```bash
python3 -m unittest
python3 -m builder validate docs/build-the-builder/briefs/brief-a.md docs/build-the-builder/briefs/brief-b.md
python3 -m builder diff inputs/chrome/observations/workflow-baseline.json docs/build-the-builder/examples/base-agent.json --shape
```

The last validation command is a *heuristic audit*, not a production-ready policy specification; `I-UNCLASSIFIED` lines need explicit resolution.

## Immediate implementation plan (Claude Code)

1. **Reproduce the official baseline and sample builder** with a real Freya API key and capture one observed practice score, agent ID, published version and trace. This is the first priority; no fresh framework until it runs.
2. **Build a new entrypoint** (e.g. `builder/build.py`) that reads all provided brief paths plus the supplied OpenAPI file. For this step you may reuse the example SDK builder and skill under the kit. Ensure one-command execution with no manual agent edits.
3. **Semantic policy extraction:** extract *all* numbered clauses AND table rows, resolve Brief B overrides and memo precedence, parse fields/enums from the input OpenAPI. Record the source of every rule. Treat old regex extractor as an independent gap checklist, not the truth.
4. **Workflow generation:** derive nodes/prompts/routes/code from verified event docs. Enforce identity, product-scoped business-day deadlines, action precedence and outcome mapping. Guard against silent `pre_actions` removal, invalid node references and missing branch fallbacks.
5. **Validate/execute:** local graph invariants -> Freya dry-run -> save/publish -> read back -> official practice cases -> inspect failing ledger/transcript/tool sequence -> targeted fix. Preserve previous best working export before each update.
6. **Generalization:** change the inputs (Brief A alone vs A+B; transformed synthetic policy/table text) and verify the Builder adapts *without editing agent JSON manually*. Do not use official public case expectations to hardcode final workflow behavior.
7. **Final:** entrypoint accepts `{brief_path} {tool_api_path}`, each run <=30 minutes, logs model calls with short purposes and start/end time, exports the two workflows and sanitized traces, records repo commit and exact run command.

## Acceptance gates

- [ ] Baseline uploaded by API key and actual test conversation completed (not only JSON validated).
- [ ] Reference SDK Builder runs; measured score and trace exist.
- [ ] A+B inheritance and per-product exceptions are represented; no skipped table clauses.
- [ ] No debt disclosure before verified tool state; no success claim before `ok:true`.
- [ ] `close_call` exactly once and as the last bank tool call.
- [ ] Correct real-time `now` handling, business-day calculations and retry safeguards.
- [ ] Workflow saved/published then read back; validation includes reference integrity.
- [ ] Three-run reliability results recorded for representative cases.
- [ ] Clean Git commit can reproduce workflow creation from inputs, with no manual modification.
- [ ] Traces are complete and contain no secrets.
