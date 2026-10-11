# Live final (2026-10-11, 20:00-23:00 Istanbul)

Source: https://www.freyavoice.ai/hackathon (read 19:38 and 20:16). It replaces the two-brief plan in
`FINAL_RUNBOOK.md`.

- The case is in Turkish. It is one zip with a folder of bank documents (Markdown, Word, PDF, Excel), a service
  contract, test customers and six example conversations. Read `BRIEF.md` first. `README.md` lists the documents.
- The bank adds documents to the folder during the first hour. Check the folder again before the submission.
- We write the bank mock on Cloudflare Workers (`mock/`). We deploy it before the builder runs and keep it up until
  the results. The phone agent may call only that mock.
- Run command: `python3 builder/build.py {case_folder} https://freya-bank-mock-final.atakan-yamana.workers.dev --skill <skill> --label <label>`.
  The organisers replace only `{case_folder}`, so the mock URL is written out.
- Submit one exported agent, the trace of its run, the commit, the mock URL and `submission.json`
  (`submission.template.json`) by e-mail before 23:00. The same files must be in the repository at the named commit.
- The builder works alone. Nothing from the case goes into it. The mock is not part of the builder.

## Order

1. Snapshot every download of the case: `python3 -I tools/case_snapshot.py <zip>`. The snapshot goes to the
   git-ignored `case/_snapshots/`, with an inventory and a diff against the previous snapshot. Log every snapshot in
   `docs/FINAL_CASE_LOG.md`. Read `BRIEF.md`, `README.md` and the service contract.
2. Mock: write `mock/src/routes.js`, `data.js` and `openapi.js` from the contract and the test customers. Check with
   `node test/check.mjs <cases.json>` in `mock/`, then with `npx wrangler dev`. Deploy (`npx wrangler deploy`) only
   with approval. Then run the same check against the public URL.
3. Run `python3 builder/build.py case/_snapshots/<latest>/extracted/<folder> <mock_url> --prepare-only`. Read
   `runs/inputs-*/manifest.json`: every document is converted, the tool API comes from the mock, `servers` is the
   mock.
4. Start two builds side by side. build.py gives each build its own state.
   - `--skill builder/skills/reference-chat --label final-chat`
   - `--skill builder/skills/reference --label final-ref` (the rollback)
5. For each accepted run, run `closing_check.py` and `tools/evaluation/graph_report.py`, and read the agent against
   the brief. Pick with evidence. Start a third run only if neither run is safe and time allows.
6. Do the submission checks from `FINAL_RUNBOOK.md`: acceptance, export sha256, paths, secret scan. Commit and push.
   The organisers must be able to read the repository. Then send the e-mail.
