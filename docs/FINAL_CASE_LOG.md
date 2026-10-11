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

No case-specific code exists until the contract and the test customers arrive. Prepared at 20:20-20:30:
- path parameters (`{name}` segments) in `mock/src/index.js`;
- handlers return `{ status, body }`, so a bank `status` field stays in the body;
- `mock/test/check.mjs` compares answers exactly, in-process or against a URL, and checks that `openapi.js` and
  `routes.js` name the same operations.

Deployed with approval at 20:29: `https://freya-bank-mock-final.atakan-yamana.workers.dev` (version 0f79d350,
skeleton only, no bank data). Checked on the public URL: `/`, `/health` and `/openapi.json` answer 200, an unknown
path answers 404. The `LOG_TOKEN` secret is set; `/_log` answers 200 with the token and 404 without it.

## Builds

None yet.
