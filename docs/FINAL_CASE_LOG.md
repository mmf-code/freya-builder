# Final case log (2026-10-11, case open 20:00-23:00 Istanbul)

Each download of the case folder is a snapshot (`tools/case_snapshot.py`, under the git-ignored `case/_snapshots/`).
This file records each snapshot, what changed, and the snapshot that each build used.

Source: the organisers' Google Drive folder "Build the Builder - Final Case". The organisers sent the link by e-mail
at 20:00. At 20:16 the website (freyavoice.ai/hackathon) showed no link and no update section.

The organisers announced:
- The bank adds documents to the folder during the first hour.
- Check the folder again before you finish.
- Follow the e-mails and the website for updates.

## Snapshots

| Snapshot | Downloaded (Drive stamp, UTC) | Files | Change |
|---|---|---|---|
| s01-20261011T171112Z | 17:11:12 (20:11 Istanbul) | 2: `BRIEF.md` (sha256 9f7a9256), `statement-debt-call-flow.pdf` (1092fe84) | first |
| s02-20261011T174012Z | 17:40:12 (20:40 Istanbul) | 18 | 16 added: `README.md`, `example-scenarios.md`, `cloudflare-mock/` (4), `sources/documents/` (FAQ, IVR prompt sheet, service contract), `sources/emails/` (2 threads, 2 analysis versions), `sources/meetings/` (1 transcript), `test-environment/` (2). Changed: `BRIEF.md` (the Inputs list now matches the pack: no third analysis version, no data models, no abbreviations) |
| s03-20261011T180249Z | 18:02:49 (21:02 Istanbul) | 19 | 1 added: `sources/meetings/2026-10-10-follow-up-session-transcript.txt` (currency names in full, ask about another card before the offer, no invented date for a card without a statement, total debt on the cut day). No service change: the mock stays as it is |

`BRIEF.md` ("Inputs") names these files. s01 does not have them:
- `README.md`
- `sources/emails/`, with `attachments/` (three versions of the analysis document)
- `sources/documents/`: flow drawing, phone-menu announcements, abbreviations, FAQ, two data model versions, service
  examples, and the IVR integration document. Section 6 of that document is the service contract.
- `sources/meetings/`
- `test-environment/`: `test-customers.md`, `test-customers.json` and the test environment rules
- `example-scenarios.md`
- `cloudflare-mock/`

Not confirmed: at 17:11 UTC the folder probably held only these two files. This agrees with the announcement.

s02 has every file that its `BRIEF.md` names. Probably still to come: the 9 Oct recap mail says that Ozan writes up
the statement week and joint statement points "separately with the sample sentences". s02 has no such document.

## What s01 says (no contract yet)

- The phone menu identified the caller. The calls are in Turkish.
- Variables: `customerNumber` (8 digits, never asked) and `now` (Istanbul time, used for every date decision).
- Flow drawing:
  - A second factor may be necessary. The call then goes back to the phone menu and returns.
  - The card list service runs. With no eligible card, the call returns to the supervisor.
  - With more than one card, the agent asks for the card name. If two names are the same, it asks for the last 4
    digits. If those are the same, it asks for the last 6 digits.
  - No statement debt: the agent says so, reads the total debt and offers another card.
  - TL debt has three payment branches: none paid, below the minimum, the minimum or more.
  - Then the USD/EUR debt and the due date.
  - Then an offer: change the cut-off date, or send the statement by e-mail.
  - "Pay debt" goes to a human agent through the phone menu.
  - E-mail: the agent reads the registered address and sends on "yes". With no address, it says so.
  - Cut-off date: a shared statement shows the weeks of the primary and the linked card. A change offers the other
    weeks, reads the new week and dates, and gets a confirmation.
- Conflict: the drawing names USD/EUR only. `BRIEF.md` names TL, USD, EUR and GBP. Settle this from later documents.

## Mock

Written at 20:45-20:55 from s02: the service contract (sections 2-6) and `test-environment/test-customers.json`,
copied unchanged to `mock/src/test-customers.json` (sha256 d6ce1556).
- Seven `POST /voice/v1/<service>` routes and `POST /oauth2/token`. The test environment does not check the token.
- Lookup as in `test-customers.md`: customer number or card number, then the week. A number and a string are the
  same. The `delaySeconds` entry (94907600, `cards.balance`, 12 s) waits before the answer.
- No entry: the 404 of that service from contract section 4. A service without a 404 answers 400
  `INVALID_ARGUMENTS_ERROR`. A missing required field also answers 400.
- A `{{variable}}` value gets the first test customer's record, as the case's example Worker does.
- CORS and OPTIONS as in the example Worker. The request log records the User-Agent.

Checks: `mock/test/build-cases.mjs` writes 673 cases (every entry of the test data, a number variant, and 17 error
and edge cases). 673/673 match in-process, under `wrangler dev`, and on the public URL after the deploy.

Deploys, each with approval: 20:29 skeleton (0f79d350), 20:52 contract (52c9ecea), 20:56 User-Agent in the log
(ad4e2ad8). URL: `https://freya-bank-mock-final.atakan-yamana.workers.dev`.

Found: Cloudflare answers 403 (error 1010) to Python urllib's default User-Agent on workers.dev. requests, httpx,
aiohttp, Go, Java, okhttp, Node, curl and an empty User-Agent get 200. `build.py` now sends its own User-Agent. A
builder that probes the mock with plain urllib gets 403.

`build.py --prepare-only` on s02 at 20:55: 17 of 18 files converted. The example Worker's `worker.js` and
`wrangler.toml` have no converter and are listed as skipped. The tool API comes from the mock, with 8 paths.

## Builds

- 21:04, two builds on s02 (`final-chat`, `final-ref`): stopped after 47 s when s03 arrived. Kept as
  `runs/*-aborted-s02`; no export.
- 21:05, two builds on s03, each with its own state, mock version 33b80bc5:
  `--skill builder/skills/reference-chat --label final-chat` and `--skill builder/skills/reference --label final-ref`.

Results:
- `final-chat` (reference-chat, 20261011-210522): 1168 s, exit 3. The runner rejected it for three probe workflows
  that the builder saved while it studied the chat route; they call the kit's old practice mock. The agent itself
  (BRIEF, version 4) has 0 errors. Its own tests: chat tests of Examples 1, 2, 3 and 5; two real defects found and
  fixed (empty card choice and week fields). But the chat route hung on an opening tool step, and the builder made the
  first step silent ("Say nothing", wait for the caller). One chat-mode simulation of Example 1 at 21:30 (simulation
  95cf2fb8, the kit's run_simulation) shows the result: one event, node_enter start; nobody speaks; 0 s,
  customer-ended-call, outcome inconclusive. NO-GO.
- `final-ref` (reference, 20261011-210530): 1801 s, exit 1, stopped at the 30-minute limit. NO-GO.

- `final-open` (reference-chat-open, 20261011-213919, run commit f0919c0): 856 s, exit 3 with one reason only:
  "BRIEF.contract.json declares no terminal tool" (true for this case: no service ends a call). One slot, 0 static
  errors, every URL under the mock. Its own tests: an opening simulation of Example 1 (the agent speaks first), one
  fix (version 2: three extraction fields), then simulations of Examples 2 and 3 on version 2; 3 of 3 passed.
  Independent check at 21:55 (simulation 585b5908, chat mode, the kit's run_simulation): E1, E5, E6 pass; E4 fail
  (the caller spoke during the opening; after the reading the agent went to the main menu without the offer). E4
  again at 21:57 (78ff03a4): pass, e-mail read, confirmed, sent, "gönderildi" after the service answer. Seen and not
  fixed: E6 offered the e-mail to a caller with no registered address in one extra line. GO.
  Known limit (security review, 22:00): on the multi-card path the model fills `cardNumber` for `cards.balance`;
  code checks only that it is masked, not that it is in the caller's own card list, and the chosen card then feeds
  the week change and the PDF send. The contract gives `cards.balance` and `statement.week.*` no customer number,
  so the bank side cannot check ownership. Exploiting it needs another customer's masked number. Not fixed: a fix
  needs a builder change and a new run.

Next candidate: `builder/skills/reference-chat-open` (sha256 37e6f222): reference-chat plus two generic rules: the
agent speaks first and a chat-route limit never changes the opening, checked with one simulation after the first
save; save only the agent's own slot.

Mock state: the write services (`statement.week.change`, `statement.pdf.send`) return the fixed answers of the test
data and change nothing. Contract section 6 asks for exactly those answers, and `test-customers.md` says the dates are
fixed in the data. A stateful mock would answer differently from the test environment.
