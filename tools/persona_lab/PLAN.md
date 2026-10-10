# Persona Lab plan (revised 2026-10-10)

The final tests unseen briefs and changed tool contracts more than unseen customer voices. The weight therefore
moves to a blind-generalization layer. The persona layer stays small.

## Layers and what they score

| Layer | Asset | Scored by | Never claims |
|---|---|---|---|
| G. Blind generalization (main) | Policy and OpenAPI mutations of the public briefs, as clean spec and as raw bank material; build commands in hidden-brief mode; an export grader | Offline contract validation (`builder.workflow_check`) and text evidence of policy adoption in the fresh export | A ledger score, or a prediction of the official score |
| P. Behavioural personas | 8 EVRE-style programs on public cases + 2 diagnostics | Official: kit ledger scorer + judge, unchanged. Diagnostics: invariants and judge reason only | That a persona performed its acts deterministically |
| O. Offline oracle and invariants | Parameterized date/deadline oracle; ledger/transcript invariants; triage | Unit tests; applied to live raw results | Anything about agents not yet run |

## G: blind generalization

- A scenario is a list of anchored edits to the public brief texts (each anchor must occur exactly once) plus an
  optional OpenAPI mutation. Edits cover identity questions and wrong-answer limits, per-product floors and attempts,
  deadlines, holidays, callback windows, outcome/reason tables, and memo precedence.
- Every scenario renders twice: `clean` (edits inline) and `raw` (bank material: e-mail, policy extract with page
  noise, an older superseded memo, and a newer memo that carries the edits marked `via: memo`).
- Inputs live in `generated/blind/<scenario>-<form>/inputs/` with unique file names (kitrun slots are file names;
  `brief-a.md` would overwrite the main session's agent). The key (`key.json`) lives outside `inputs/` and is never
  given to the Builder. Tests assert no input brief equals a kit brief, so kitrun exposes no practice customers.
- Fresh-build test: build with `python -m builder.kitrun <inputs> --tools <inputs>/openapi.json`, then
  `cli grade` the first export. The grader checks the export against the mutated contract, flags stale field names
  and enum values of the original contract, and reports policy evidence as FOUND / ABSENT / STALE.
  `tests/persona_lab/test_fresh_exports.py` asserts on every fresh export placed in `results/blind/`, and skips
  when there is none.
- The grader's discrimination is proven offline: the old kit export fails a mutated contract, and the same export
  adapted by a scripted rewrite passes. That proves the grader, not the Builder.

## P: personas

- Spec: conditions, acts (from `acts.py`), rules with priority, ordering, max occurrences, escalation, distractors,
  hypothesis, proves / does not prove. Compiled into the case `script`, rendered with the kit's own `persona_for`.
- Consistency: the base case's facts and expectations are hash-equal; every number in the program is a base fact or
  a declared distractor; security answers are never altered unless the base case does so.
- Live runner: dry run by default; `--live` reuses kit `run_once`, its own persona store, one variant per PUB id per
  simulation, raw ledger + transcript retained, triage per call.

## Not now

No remote Freya calls, no builds, no commits while the main session works.
