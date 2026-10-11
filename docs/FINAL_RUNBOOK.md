# Final runbook (hidden briefs, Sunday 2026-10-11)

Rules from the kit (`docs/build-the-builder/README.md`, "The final" and "Rules"): each final brief comes with its own
tool API file; one is a clean specification, one raw bank material. A builder run on one brief may take 30 minutes
at most. You may run it more than once and submit the phone agent of one run with that run's trace. No manual step,
no edit of the agent, nothing from a final brief written into the builder. Ties are ranked by promised amount, then
shorter build time, then earlier submission. A workspace holds 200 workflows.

## Builder

`builder/skills/reference` (92a695a, sha256 `7659a7bd2e6c`), run through `builder/kitrun.py`. Why: the best blind
result (raw A+B, no practice customers: 11/13 from one build), no timeout, and of the deterministic defects in
`docs/FAILURE_MODES.md` only #1, in 6 of its 11 stored builds, which the two-run pick below handles. The official 12/13 came from its practice-test variant `reference-fb88831`, not from this
exact skill. `reference-v2` and `reference-v3` did not pass the switch rule on the healthy platform of 2026-10-11
afternoon (`docs/REFERENCE_V2.md`, "Healthy rounds"), so this path stays.

The configuration is the skill plus what kitrun copies into the workspace (`builder/workflow_check.py`,
`builder/lower.py`, `builder/dryrun.py`) plus `builder/kitrun.py` itself, all at the agreed commit. Do not change any
of them between the runs of the final. Runner from commit 560ccfe on: what the builder sees is the same as before
(helpers and workspace unchanged since fe8bd5b); only the runner's acceptance decision is stricter.

## Before the briefs open

1. `cd` to the repository root on the agreed commit; `git status` must show no tracked changes.
2. `docs/build-the-builder/env.sh` holds the keys (never print it). `.venv` has `claude-agent-sdk` (`scripts/setup.sh`).
3. API answers: `python3 -I tools/evaluation/api_probe.py "$PWD"` prints `OK`. If not, wait; do not start a build.
4. Nobody else runs simulations or builds on the workspace during the final runs.

## For each final brief, two runs side by side, then pick one

Put the files where the run can name them, unchanged, with distinct file names (the file name is the Freya slot):

```
mkdir -p briefs/final
cp <downloaded brief>.md briefs/final/<name>.md          # e.g. final-1.md
cp <downloaded tool API>.json briefs/final/<name>.openapi.json
for i in 1 2; do
  .venv/bin/python -m builder.kitrun briefs/final/<name>.md --tools briefs/final/<name>.openapi.json \
      --label final-<name>-$i --skill builder/skills/reference --state state/final-<name>-$i --minutes 30 \
      > /tmp/final-<name>-$i.out 2>&1 &
  sleep 5                                                 # stagger the starts, as on 2026-10-11 12:00
done
wait
python3 -I tools/evaluation/closing_check.py "$PWD" briefs/final/<name>.openapi.json runs/*-final-<name>-1 runs/*-final-<name>-2
```

Why two (decided 2026-10-11 16:40): 6 of the 11 stored `reference` builds (both of 2026-10-11 among them, and the raw-A build of 2026-10-10)
speak their goodbye in the steps that run the terminal tool, so the line comes after it (`docs/FAILURE_MODES.md` #1,
Brief A rule 47). The defect is visible in the export. `closing_check.py` reads each run's acceptance, its exports
(sha256 checked) and its contract, and prints `pick:`: an accepted run whose terminal steps are silent, between
equals the shorter build. If both builds are independent with that rate, at least one is clean about 7 times in 10 (three builds: about 8 in 10).
On 2026-10-11 it said SPEAKS for v1-fresh (14 terminal steps and 3 transfer steps that pass into one) and the
rehearsal (17 terminal steps), CLEAN for the reference-v2 and reference-v3 builds; a farewell on the end_call step is
caught too (synthetic copy). In v1-fresh's official calls `policy_audit` found no goodbye before `close_call` in 39 of
39 (three rounds), v2 and v3 in none.

- The two runs of a brief run at the same time: a hidden-brief build starts no simulation, and each run has its own
  `--state`, so its own Freya slot (two parallel builds were accepted on 2026-10-11, 12:00). The two final briefs
  one after the other.
- Exit 0 with a `pick:` line: submit that run (below). If it says `no clean accepted run`, the pick is still an
  accepted run; submit it. Exit 1: no run was accepted; start a third run with `--state state/final-<name>-3`
  and run the check over all three.

- One brief per run, with its own tool API. If a final brief says it extends the other one, pass both brief files
  to that run (as Brief A + B were), still with that brief's own tool API.
- A hidden brief gets no practice customers; the builder then runs no practice test. Expect 6 to 18 minutes (the
  rehearsal of 2026-10-11 with one raw brief took 17 minutes on a slow platform day).
- The run's acceptance is at the end of `trace.txt` and under `acceptance` in `summary.json`, with every reason.
  Exit 0: accepted. Exit 1: the builder failed, its SDK result was an error or missing, it was stopped at the limit, or
  build, export and checks together took over 30 minutes. Exit 3: a check failed (static errors, no export, no or
  empty contract, a contract quote that is not in the input files, a changed input or trace). Exit 2: a secret in the
  output. Only an exit-0 run is submitted.
- After an API outage, `python3 -I tools/evaluation/reexport.py "$PWD" runs/<run> state/final-<name>-<n>` exports
  the saved workflows again and reruns the checks (exit 0 or 3). It does not undo another reason of the original run.
- Every run of a brief uses its own `--state` (`state/final-<name>-<n>`) so it cannot update another run's agent.
  The closing check is the only selection signal we have between accepted runs; there is none for the rest of the
  agent's behaviour without customer scores.

## What to submit, per brief

From `runs/<stamp>-final-<name>-<n>/`, the run `closing_check.py` picked:
- `<name>.workflow.json`: the export kitrun took with `freya.export_workflow` (what the organisers load and score). Its
  sha256 is in `summary.json` (`freya[].export_sha256`); check that the file you submit has it.
- `trace.txt`: start and end, every model call with a one-line purpose, what was created on Freya, tests run. Before
  submitting, search it for paths outside the run's `workspace/` (for example `cd ..` or the repository root): nothing
  stops a builder from leaving its workspace, and a final trace should show that it did not.
- The repository commit: `summary.json` records `repo_commit` and the skill's sha256.

Checks before submitting (rehearsed 2026-10-11 on an accepted run; `R=runs/<stamp>-final-<name>-<n>`, the picked run):

```
grep "^acceptance" -A5 $R/trace.txt                       # must say ACCEPTED (exit 0)
python3 -c "import json,hashlib,sys; s=json.load(open(sys.argv[1]+'/summary.json')); [print(f['slot'], 'MATCH' if f['export_sha256']==hashlib.sha256(open(sys.argv[1]+'/'+f['export'],'rb').read()).hexdigest() else 'DIFF') for f in s['freya']]" $R
grep -n "<repo>/" $R/trace.txt | grep -v "<repo>/$R/workspace" | grep -v ":builder:" | grep -v "<repo>/.claude-builder/"   # must print nothing
                                                          # (.claude-builder/ is the builder's own Claude Code config: large tool output is kept there)
grep -c "cd \.\." $R/trace.txt                             # must print 0
```

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
