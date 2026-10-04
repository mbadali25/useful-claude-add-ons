# Cloud handoff: T-0054

**Full `/crew:autopilot` guide, its own document, with every owner-requested example**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** ready (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0054-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0054/direction.md`, `docs/tickets/T-0054/spec.md`
- **Size:** about 2 production lines (one step-table row in `scripts/gate-runner.py`). The guide source is about 350-450 lines of Markdown and the new suite about 150 lines. No harness path. No file under `plugin/` changes, so no crew version bump.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0010 | merged (PR #261) | The approval and questions policies the guide documents. |
| T-0018 | merged | The subcommand router and `/crew:autopilot status`. |
| T-0019 | on main (PR #379); INDEX still reads in-progress | `crew_ticket.py assign` and `mint`. The merge commit is the evidence; INDEX is behind. |
| T-0004 | merged | The autopilot run loop itself. |
| T-0006 | merged | The handoff `resume:` line used after `/clear`. |
| T-0023 | merged | Plain-text `continue` and `route.enabled`. |
| T-0024 | merged | Group approval (several ids, a range). |
| T-0072 | merged | The `autopilot.deploy` policy and `deploy-allowed`. |
| L-0510 | done | Final-round auto-accept, shown under review stops. |

Everything that must land first is already on main, so this ticket can be worked now.

Where the documents disagree: the ticket title and direction.md name T-0048 (INDEX: spec, not landed) as a dependency. The spec says it is no longer one, because the build pipeline it was wanted for is already on main. The spec wins. Whichever of T-0048 and this ticket lands second adds its `GUIDES` entry beside the other's.

This ticket blocks, softly: T-0048 (its crew guide links to this document) and T-0055 (its doc enforcement would count this guide among the built guides). L-0542 is related, not blocked.

Not dependencies: L-0611, T-0011, T-0012, L-0541, T-0013, T-0020, T-0029, T-0049, T-0051, T-0052, T-0053, T-0056, T-0057, T-0058, T-0059, T-0067 and T-0073 each add their own section to the guide in their own PR when they land.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (this branch's base is `ce235468`); re-check each anchor.
- No plan.md is published (the spec says none exists). The implementing session writes the plan.
- Re-read `AVAILABLE` and `ARRIVES` in `crew_autopilot.py` on origin/main and each "coming" ticket's state. If one has landed, move its row from coming to landed.
- If T-0048 has landed first, `build.py` has a `--check` mode and more `GUIDES` entries: add `autopilot` beside them and run `build.py --check`.
- No sample output for a feature that is not on origin/main, and nothing copied from an unlanded spec as if it were behaviour. Every sample of script output comes from running the script in a throwaway repo under a temp directory, never from memory or from a real `.work/`.
- This repository is public: no real ticket key, hostname, account, profile or customer id from any other repository. Sample ids are this repo's own `T-`/`L-` ids or the neutral `ABC-510`.
- The "Autopilot is armed ... Its first phase is spec" sentence is not printed by code; the guide presents it as the session's report, not as script output.
- Tooling: the build needs python-markdown and LibreOffice. If LibreOffice is missing, build with `--html-only`, commit the source and HTML, and report DOCX and PDF as not built so a local session builds them before merge. Never commit a DOCX or PDF made by another tool.
- The suite (`scripts/_test/autopilot-guide.py`) must not import crew code or `markdown`.
- The five existing guide sources and their built files are not edited or rebuilt.
- Open question Q3 answered the other way adds `plugin/crew/README.md`, the version files and `CHANGELOG.md` to Touch and needs a re-approval.
- direction.md mentions a memory note named `autopilot-guide-examples` as the running example list. That note is not published; the spec's example tables are the list to work from.

## Open questions for the owner (recommended option taken)

1. Q1. Land before T-0048, or wait for it? Taken: land before.
2. Q2. A static example list in the suite, or couple the test to the router's `AVAILABLE`/`ARRIVES` tables (stricter, but it reddens about ten in-flight tickets whose Touch lacks the guide)? Taken: static list.
3. Q3. No pointer from `plugin/crew/README.md` (so no crew version bump), or a one-line pointer plus a bump? Taken: no pointer.
4. Q4. Unlanded examples (goal walkthrough, sleep mode, Telegram, ship, split, focus, wave) appear only as "What is coming" rows with ticket ids and no sample output, or print intended output from the specs marked "not yet"? Taken: rows only.
5. Q5. The "armed, first phase is spec" example uses the neutral id `ABC-510` instead of another repository's real ticket key. Taken: yes, because the repo is public; direction.md's line was reworded to match.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0054/` in the final PR unless the owner wants it kept.
