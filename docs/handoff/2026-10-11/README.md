# Crew PR chain handoff, 2026-10-11 (public, redacted)

This directory carries the state of the crew PR chain on 2026-10-11, so that work can resume from another
computer with only a clone. It is a redacted copy of records that normally live only in git-ignored places on the
owner's laptop (`.work/` and `.git/crew/review/`). It was cut from `main` at
`a656ef84f6dca94a4abc73934eab6e886bd54e0d` (merge of PR #605) on branch `handoff/crew-2026-10-11`.

Where something sensitive was removed, the text reads `[redacted: <class>]`. The classes are listed under
"What is NOT here".

## Contents

| Path | What it is |
|---|---|
| `HANDOFF.md` | The TRANSFER HANDOFF section of the laptop's `.work/HANDOFF.md` (written 15:02 CDT), redacted. Start here. |
| `INDEX.md` | Copy of `.work/INDEX.md`, the ticket index, redacted. |
| `tickets/<id>/` | The Markdown and JSON records (direction, spec, plan, notes, done-waiver, selfcheck, review receipts) for L-0709, L-0753, L-0764, L-0766, L-0768, L-0777, L-0778, L-0787, L-0789, L-0791, L-0792 and L-0793. |
| `review-ledgers/` | The review ledgers from `.git/crew/review/` for L-0709, L-0753, L-0768, L-0770, L-0777 and L-0790. |
| `artifacts/` | The sources of the published status pages, redacted. |

## Published pages

| Title | Link | File here |
|---|---|---|
| Overnight Crew Watch | https://claude.ai/artifact/9uoFWWde7i2BhUg9ftDDsp | `artifacts/overnight-status.html` |
| Crew Fix Board | https://claude.ai/artifact/NbP6MHm5nuBez7mstsAHB2 | `artifacts/crew-fix-board.html` |
| Crew 1.2.0 Review | https://claude.ai/artifact/KBp989cfCq1Uh6iurcUh1i | `artifacts/crew-review.html` |
| QA Pipeline Speed-ups | https://claude.ai/artifact/AAt9EmhAn68dqYSVEWhi9W | `artifacts/qa-pipeline-report.html` |

Republished Sun Oct 11 04:01:38 PM CDT 2026 after the earlier links stopped resolving; the old links are dead.

Only the owner's claude.ai account can open these links. The status pages were last published at 14:10 CDT
(Update 11), before #605 merged. The copies here are redacted, so they differ from the published pages where a
redaction applied.

## How to resume

1. Clone the repo, run `git fetch origin`, and check out or read branch `handoff/crew-2026-10-11`.
2. Start a session in the repo with: "Read docs/handoff/2026-10-11/README.md and HANDOFF.md on branch
   handoff/crew-2026-10-11 and resume the crew PR chain from the TRANSFER HANDOFF: start with #584."
3. `.work/` is git-ignored, and so is `.git/crew/`. On the new machine, before running any crew command, the
   session should copy `docs/handoff/2026-10-11/tickets/` to `.work/tickets/`, `INDEX.md` to `.work/INDEX.md`,
   and `review-ledgers/*.json` to `.git/crew/review/`. Without the ledgers, `/crew:done` check 1 refuses on every
   PR. Do NOT do this on the laptop: the originals there are newer than these copies.
4. Several ticket records were left off or redacted (listed below). On the new machine L-0772's review ledger is
   missing, so #603's review receipt does not exist there. Its review must be recorded again, or the file fetched
   from the laptop.

## Pending at transfer

- The L-0790 lane's post-merge cleanup was not finished. Its worktree is still registered on the laptop, its
  ticket folder was not copied here, and its INDEX row still reads `review` although #605 merged as `a656ef84`.
- Main's Pytest result on `a656ef84` was not seen. Main's push CI was still running when the handoff was
  written.
- Everything listed in HANDOFF.md sections 2, 3 and 8.

## What is NOT here

Redaction classes used:

- **a**: credential or secret variable names, and any token, key or token hash. This includes the names involved
  in this morning's incident.
- **b**: IP addresses, hostnames, machine names, runner labels, usernames and network ranges.
- **c**: how any unfixed guard gap or bypass works. Allowed neutral statements:
  - "W-0132: cloud guard has a must-block miss and over-blocks some prose; detail in the ticket"
  - "W-0131: the hook's python resolver can exhaust its time budget on Windows, so an armed guard refuses; detail
    in the ticket"
  - For another repo's report: "a fail-open reported in another repo's own guard; not a crew defect"
- **d**: verbatim guard refusal texts and trigger phrases.
- **e**: journal lines, firewall rule contents and incident detail.

Not on this branch at all:

- The full notes. They are in `.work/HANDOFF.md` on the laptop named in the owner's own records. That includes
  its LOCAL ONLY part and every section below the TRANSFER HANDOFF.
- Lane worktrees, gate logs and status files, the per-project Claude memory directory, and the Kanban vault.
  These are laptop-only.

## Files left off, and why

| Path (relative to the laptop's main checkout) | Why |
|---|---|
| `.work/tickets/L-0772/` (whole folder, including `security.md` and `notes.md`) | Classes a and c. Stays on the laptop. |
| `.git/crew/review/L-0772.json` | Classes a and c. The ledger stays on the laptop; the review must be re-recorded or the file fetched from the laptop. |
| `.work/tickets/L-0788/` (whole folder) | Class c. |
| `.work/tickets/L-0790/direction.md` | Classes b and e. The handoff's local part lists it as not public-safe. |
| `.work/tickets/L-0768/done-waiver.md` | Classes b, d and e. Stays on the laptop; #597's done-waiver must be read there or re-measured. |
| `.work/tickets/L-0768/evidence/` | Class e, plus logs. |
| `.work/tickets/L-0709/gate-bc7e5924/`, `gate-bdc7bc55/`, `check4-bdc7bc55.txt` | Gate logs and status files, not records. Some are over 300 KB. |
| `.work/tickets/L-0777/gate-46d015a35/`, `gate-ee19528bf/`, `evidence/`, `lane-worktree-copy/` | Gate logs, CI logs and a duplicate copy. |
| `.work/tickets/L-0789/evidence/`, `main-repro-987ea4fb.log` | Logs and review scratch bundles. |
| `.work/tickets/L-0793/evidence/` | CI job logs, up to about 1 MB. |
| `.work/tickets/L-0753/worktree-records/`, `sabotage-by-hand.py` | Review scratch bundles (some over 500 KB) and a script. |
| `.work/tickets/L-0770/` | Does not exist. Only its ledger is copied. |

These tickets have no review ledger on the laptop, so none is copied: L-0764, L-0766, L-0778, L-0787, L-0789,
L-0791, L-0792 and L-0793.

The 64-character hex values left in `tickets/*/review.json`, `tickets/*/selfcheck.md`,
`tickets/L-0787/direction.md` and `review-ledgers/*.json` are review bundle, plan, standards and receipt digests.
They are not token hashes, and the ledgers need them to match receipts.

## Added 2026-10-12

- The artifact links above were republished on 2026-10-12; the 2026-10-11 links are dead. The pages are unchanged (status as of 14:10 CDT 2026-10-11).
- Unfiled defect, not yet ticketed: four crew messages advise "commit or stash" (`plugin/crew` `crew_train.py:1102`, `promote-gate.sh:734`, `promote-gate.ps1:962`, `commands/promote.md:110`). `git stash` is shared across worktrees, so a lane that stashes can lose or cross work with another lane. Suggested: a ticket to reword them, and "never git stash in a worktree; use WIP commits" in the lane brief.
