# Final runbook (hidden briefs, Sunday 2026-10-11)

Rules from the kit (`docs/build-the-builder/README.md`, "The final" and "Rules"): each final brief comes with its own
tool API file; one is a clean specification, one raw bank material. A builder run on one brief may take 30 minutes
at most. You may run it more than once and submit the phone agent of one run with that run's trace. No manual step,
no edit of the agent, nothing from a final brief written into the builder. Ties are ranked by promised amount, then
shorter build time, then earlier submission. A workspace holds 200 workflows.

## Builder

`builder/skills/reference` (92a695a, sha256 `7659a7bd2e6c`), run through `builder/kitrun.py`. Why: the best blind
result (raw A+B, no practice customers: 11/13 from one build), no timeout, and none of the deterministic defects in
`docs/FAILURE_MODES.md`. The official 12/13 came from its practice-test variant `reference-fb88831`, not from this
exact skill. `reference-v2` replaces it only if the switch rule in `docs/REFERENCE_V2.md` passes before the freeze;
then this one path changes and nothing else.

The configuration is the skill plus what kitrun copies into the workspace (`builder/workflow_check.py`,
`builder/lower.py`, `builder/dryrun.py`) plus `builder/kitrun.py` itself, all at the agreed commit. Do not change any
of them between the runs of the final. Runner from commit 560ccfe on: what the builder sees is the same as before
(helpers and workspace unchanged since fe8bd5b); only the runner's acceptance decision is stricter.

## Before the briefs open

1. `cd` to the repository root on the agreed commit; `git status` must show no tracked changes.
2. `docs/build-the-builder/env.sh` holds the keys (never print it). `.venv` has `claude-agent-sdk` (`scripts/setup.sh`).
3. API answers: `python3 -I tools/evaluation/api_probe.py "$PWD"` prints `OK`. If not, wait; do not start a build.
4. Nobody else runs simulations or builds on the workspace during the final runs.

## For each final brief, one run

Put the files where the run can name them, unchanged, with distinct file names (the file name is the Freya slot):

```
mkdir -p briefs/final
cp <downloaded brief>.md briefs/final/<name>.md          # e.g. final-1.md
cp <downloaded tool API>.json briefs/final/<name>.openapi.json
.venv/bin/python -m builder.kitrun briefs/final/<name>.md --tools briefs/final/<name>.openapi.json \
    --label final-<name> --skill builder/skills/reference --state state/final-<name>-1 --minutes 30
```

- One brief per run, with its own tool API. If a final brief says it extends the other one, pass both brief files
  to that run (as Brief A + B were), still with that brief's own tool API.
- A hidden brief gets no practice customers; the builder then runs no practice test. Expect 6 to 15 minutes.
- The run's acceptance is at the end of `trace.txt` and under `acceptance` in `summary.json`, with every reason.
  Exit 0: accepted. Exit 1: the builder failed, its SDK result was an error or missing, it was stopped at the limit, or
  build, export and checks together took over 30 minutes. Exit 3: a check failed (static errors, no export, no or
  empty contract, a contract quote that is not in the input files, a changed input or trace). Exit 2: a secret in the
  output. Only an exit-0 run is submitted.
- After an API outage, `python3 -I tools/evaluation/reexport.py "$PWD" runs/<run> state/final-<name>-1` exports
  the saved workflows again and reruns the checks (exit 0 or 3). It does not undo another reason of the original run.
- A second run of the same brief uses a new `--state` (`state/final-<name>-2`) so it cannot update the first run's
  agent. Run again only when a run failed (timeout, check errors, no export). There is no reliable signal for
  choosing between two successful runs without customer scores.

## What to submit, per brief

From `runs/<stamp>-final-<name>/`:
- `<name>.workflow.json`: the export kitrun took with `freya.export_workflow` (what the organisers load and score). Its
  sha256 is in `summary.json` (`freya[].export_sha256`); check that the file you submit has it.
- `trace.txt`: start and end, every model call with a one-line purpose, what was created on Freya, tests run. Before
  submitting, search it for paths outside the run's `workspace/` (for example `cd ..` or the repository root): nothing
  stops a builder from leaving its workspace, and a final trace should show that it did not.
- The repository commit: `summary.json` records `repo_commit` and the skill's sha256.

Commit the run record, including the ignored `out/` and `written/` folders, and check for secrets first:

```
git ls-files --others --ignored --exclude-standard runs/<run> | grep -v /workspace/ > /tmp/run-files.txt
git ls-files --others --exclude-standard runs/<run> >> /tmp/run-files.txt
python3 -I tools/evaluation/secret_scan.py "$PWD" < /tmp/run-files.txt      # must print 0 hits
git add runs/<run> && git add -f runs/<run>/out runs/<run>/written
git commit -m "Final run <name>"
```

## When the platform misbehaves (seen 2026-10-10 and -11)

- The final build runs no simulation (a hidden brief has no practice customers); it needs the API for saving and for
  kitrun's export. Start a run only after `api_probe.py` prints `OK` in a few seconds; an `OK` after 30 s or more means
  the platform is struggling, so wait and probe again.
- A failed export after an accepted build: `reexport.py` (above). A run rejected for an SDK error or the time limit:
  run again with a new `--state`.
- A simulation started by anyone that hangs: `GET /api/v2/simulations?limit=10` shows it; `POST
  /api/v2/simulations/{id}/cancel` stops it (worked twice on 2026-10-11).
- Our evaluation tools retry 5xx errors (`tools/evaluation/freya_retry.py`); the kit's `freya.py`, which the builder
  uses, does not, and stays unchanged.

## Do not

- Do not edit the exported workflow or the agent on Freya.
- Do not run the public practice customers against a final agent to "fix" it: a fix needs a new builder run.
- Do not reuse `state/` or another run's `--state` directory.
