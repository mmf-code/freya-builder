# Blind comparison arm: reference skill 92a695a, raw A + B, no practice customers

Result: 11 of 13 official customers pass all three runs (A 8/10, B 3/3), from one combined agent for both briefs.
The full comparison with the lowering arms is in `runs/20261010-212547-blind-prec-ab/RESULT.md`.

- Build: 887 s, $2.50, skill sha256 7659a7bd2e6c (the skill was a scratchpad copy of 92a695a; the hash matches
  `builder/skills/reference`). Agent 9bd08f14, workflow 910582e9, slot `brief-b-raw`, version 1.
- Per run: A 10/10, 9/10, 8/10 (PUB-10 twice: the judge counted "this call is recorded"; PUB-06 once: floor offered
  twice); B 3/3 three times. No sandbox, DNS or backend error in any failed call (`eval/classified.json`).
- The builder made one agent: "single-product calls follow Brief A, and two or three products follow Brief B's
  change notice", from the raw B e-mail's wording. A single-product call under Brief B would then get no `add_note`,
  which the official Brief B requires; no official case tests that.
