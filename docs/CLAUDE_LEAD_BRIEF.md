# Claude Code — Freya hackathon lead instructions

You are the technical lead for the Freya Build the Builder hackathon. Do not invent platform behavior; the official v3 kit is already vendored in `docs/build-the-builder/`.

**First read, in order:**
1. `docs/START_HERE.md` and `docs/PREKIT_AUDIT.md`.
2. `docs/build-the-builder/README.md`, `docs/build-the-builder/docs/api.md`, `docs/build-the-builder/docs/workflow-format.md`, `docs/build-the-builder/docs/tools-and-code.md`.
3. `docs/build-the-builder/tools/openapi.json`, `docs/build-the-builder/briefs/brief-a.md`, `docs/build-the-builder/briefs/brief-b.md`.
4. `docs/build-the-builder/examples/agent_builder.py`, `.claude/skills/build-phone-agent/SKILL.md`, `freya.py`, and `tools/run_cases.py` within the vendored kit.
5. Consult `inputs/chrome/observations/` **only if** a specific question remains. Those are dated staging observations, not the source of truth. Read the earlier `docs/FINDINGS.md` only as historical prep notes.

**Current repo:** the pre-kit `builder/` already contains a schema-independent ingestion, heuristic requirements extractor, validator and JSON diff. Its 89 tests pass. Do not discard them, but do not mistake them for a Freya Builder. Current extractor misses high-impact real rules and does not interpret tables/override semantics reliably.

**Primary objective:** establish one working end-to-end example through the actual event `freya.py` and practice scorer first. Do not spend hours rewriting the example builder or building a dashboard.

**Then:** build an entrypoint that reads all given brief(s) and the supplied OpenAPI, extracts sourced business rules with table/memo precedence, generates a valid Freya workflow using the kit's current syntax, uses deterministic code for date/counter/amount calculations and identity/tool-result gates, validates and publishes via the reference client, evaluates selected cases and exports a traceable workflow. Freya Phone Agent may call ONLY the bank API in the supplied tool spec. Do not change the fixed agent model.

**Required feedback loop:** show what was executed, real score (if any), exact failures, underlying ledger/tool/transcript evidence, changes, regressions and next highest-impact fix. Keep versioned best exports.

**Final contract:** for EACH hidden brief, a reproducible one-command Builder run <=30 minutes; two exported workflows, one sanitized trace per brief, exact git commit. No manual phone-agent edits after Builder output, and never write hidden-brief rules/values into Builder code or prompts. Practice evaluations are serial per workspace.

**Start:** Verify docs + API key setup, initialize Git (if absent), reproduce official sample in the vendored kit's own working directory, run 1 actual practice test, record findings. Only then propose minimal integration diffs. You can delegate independent test-analysis and workflow-compiler work, but keep ownership of integration. Never claim live verification without credentials/results.
