# Live final (2026-10-11, 20:00-23:00 Istanbul)

Source: https://www.freyavoice.ai/hackathon (read 19:38). It replaces the two-brief plan in `FINAL_RUNBOOK.md`.

- One case, in Turkish: a zip with a folder of bank documents (Markdown, Word, PDF, Excel), a service contract,
  test customers and six example conversations. `BRIEF.md` first, `README.md` lists the documents.
- We write the bank mock on Cloudflare Workers (`mock/`), deploy it before the builder runs and keep it up until the
  results. The phone agent may call only that mock.
- Run command: `python3 builder/build.py {case_folder} {mock_url}`. Submit one exported agent, that run's trace, the
  commit, the mock URL and `submission.json` (`submission.template.json`) by e-mail before 23:00.
- The builder must work alone; nothing from the case goes into it. The mock is not the builder.

## Order

1. Unzip into `case/` (git-ignored copy, unchanged). Read `BRIEF.md`, `README.md`, the service contract.
2. Mock: write `mock/src/routes.js`, `data.js`, `openapi.js` from the contract and the test customers. Test with
   `npx wrangler dev`, then deploy (`npx wrangler deploy`, with approval) and check every route on the public URL.
3. `python3 builder/build.py case/<folder> <mock_url> --prepare-only` and read `runs/inputs-*/manifest.json`: every
   document converted, the tool API found, `servers` the mock.
4. Builds, each its own state (build.py makes one): `--skill builder/skills/reference-chat --label final-chat` and,
   as the rollback, `--skill builder/skills/reference --label final-ref`, side by side.
5. Per accepted run: `closing_check.py`, `tools/evaluation/graph_report.py`, a reading against the brief. Pick with
   evidence; a third run only if neither is safe and time allows.
6. Submission checks from `FINAL_RUNBOOK.md` (acceptance, export sha256, paths, secret scan), commit, e-mail.
