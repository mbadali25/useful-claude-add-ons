# T-0037 ticket status vocabulary: needs-owner, cancelled and superseded, read the same by every reader and tracker          status: spec   risk: high
depends-on: none (T-0019's mint has landed). Depended on by T-0052, T-0058, T-0059; named by T-0039 and T-0040.
## Reconstructed
- Reconstructed in a cloud session on 2026-10-04 from downstream tickets, because the owner's `.work` copy was never published. The owner must approve direction and plan before build. `OWNER CHECK:` marks every reconstructed decision. Downstream cites this spec at `:9` and `:30`, and those two lines carry the cited rules.
## Intent
Crew gains three ticket statuses. Every status reader and every tracker backend treats each one the same way:
- The lifecycle words are unchanged: `direction`, `ready`, `spec`, `planned`, `in-progress`, `review` and `done` in INDEX and the tracker, plus `approved` and `merged` in a spec header.
- `needs-owner` is open: the ticket waits on an owner decision. It is an INDEX and tracker status only, and is never written to a spec header (OWNER CHECK). The question goes under the ticket's existing `## Open questions`.
- `cancelled` and `superseded` are closed words: they close a ticket in every reader (session brief, `resolve_active`, approval precheck, autopilot, route, status) and stale an approval on purpose when written to a spec header, because neither is in `crew_ticket.STATUS_VALUES`. `superseded` carries `split-into: <id>, <id>` (T-0052) or `superseded-by: <id>` on its own line under the header.
- The vocabulary has one owner, `crew_tracker.py`, where "a new status is a row here". The other readers' closed lists gain the two closed words, and a test holds every list to `crew_tracker`'s.
## Exclusions
- `crew_ticket.STATUS_VALUES` and `approval_digest` are unchanged. A blocking hook accepts nothing it did not accept before. OWNER CHECK: T-0059 says T-0037 "redefines `STATUS_VALUES`". It keeps its name and value here.
- `crew_ticket.py` itself is not edited (it is `HARNESS`). `mint`'s `MINT_STATUSES` stays `ready|direction`, and `_index_closed` picks up the closed words through `crew_state`.
- No `split` status, and no new command (no `/crew:cancel`). `crew_split.py`, `/crew:split` and the writer of `split-into:` belong to T-0052. `done.md`'s slice edit belongs to T-0059.
- Jira and SDP push none of the three words. `_PUSH_AT` stays `in-progress|done`.
- No new `obsidian.columns` key. No hook is added, registered or changed.
- A header `merged` keeps today's meaning: it is not a closed header word in autopilot.
## Evidence
Anchors are on origin/main edb2b8ff (crew 1.0.321).
- `STATUS_VALUES = ("spec", "planned", "approved", "in-progress", "review", "done", "merged")` is the approval digest's list (`plugin/crew/hooks/scripts/crew_ticket.py:163`, `_canonical` `:550-576`). A value outside it normalises nothing, so the edit stales the approval.
- The tracker table is `STATUS_ORDER` / `LANE_FOR_STATUS` (`plugin/crew/hooks/scripts/crew_tracker.py:86-100`). The backwards rule is `_backwards` `:654-664`, the no-lane refusal is `move` `:1489-1490`, and Jira/SDP push only `_PUSH_AT` (`:115`, `_push` `:1457-1462`).
- Closed for the session brief and `resolve_active`: `_DONE_RE` and `_TABLE_DONE_WORDS` (`plugin/crew/hooks/scripts/crew_state.py:218-221`, `:238-240`), read by `read_work` (`:370-401`). `crew_ticket.resolve_active` falls back to `read_work` (`crew_ticket.py:978-985`).
- Approval precheck refuses a closed ticket through `_index_closed`, which reads `crew_state._TABLE_DONE_WORDS` and `_DONE_RE` (`crew_ticket.py:831-872`, `:898-902`).
- Autopilot: `INDEX_DONE` and `DIRECTION_APPROVED` (`plugin/crew/hooks/scripts/crew_autopilot.py:181-183`). `_phase` closes on them (`:433-435`) and on a header of exactly `done` (`:442-446`), as `_closed` does (`:1442-1456`). `WAITING` is at `:1350-1354`, `_is_open` / `open_index_tickets` at `:266-280`, and `HEADER_STATUSES` at `:175`.
- `/crew:status` lists only `open|in-progress|in progress|review` rows (`plugin/crew/hooks/scripts/crew_status.py:116`).
- The Obsidian lane table is copied in `plugin/crew/commands/obsidian-sync.md:63-73`. `test_every_transition_status_maps_to_a_lane` holds the lifecycle commands to `LANE_FOR_STATUS` (`plugin/crew/tests/test_lifecycle_commands.py:269-276`).
- Approval keeps across header status edits: `/crew:done` writes `status: done` (`plugin/crew/commands/done.md:70-71`), and `approve.md:20-22` says "other than the header's status value". README states the rule at `plugin/crew/README.md:905`.
- Harness: `crew_ticket.py` and `plugin/crew/tests/sabotage*.py` are `HARNESS` (`scripts/check-tooling-pr.py:58-84`). `crew_autopilot.py`, `crew_status.py`, `status.md` and `autopilot.md` are `SEAM` (`:86-92`).
- The lifecycle commands' header edits keep the approval: `/crew:plan` writes `status: planned` and `/crew:implement` writes `status: review` (`plugin/crew/commands/plan.md:60-62`, `implement.md:110-111`).
- A header edit to `cancelled` or `superseded` stales the approval on purpose, and this ticket keeps it that way. `in-progress` (T-0059's non-final slice) and every other `STATUS_VALUES` word keep it. A `needs-owner` header is not a lifecycle edit: it stales the approval like any unknown word.
## Downstream contract
| # | Downstream expectation (quoted) | Source | Met by |
|---|---|---|---|
| 1 | "T-0037 adds statuses; `split` or `cancelled` with a pointer to the children? Settle it with T-0037" | `origin/T-0052-build:docs/tickets/T-0052/direction.md:81-82` | `superseded` + `split-into:` (Intent) |
| 2 | "No new ticket status. The parent becomes `superseded`, T-0037's word. No `split` or `cancelled` status is added here." | `origin/T-0052-build:docs/tickets/T-0052/spec.md:12` | `superseded` exists here; `cancelled` is T-0037's, not T-0052's |
| 3 | "`cancelled` and `superseded` become closed words that stale an approval on purpose (`.work/tickets/T-0037/spec.md:9` and `:30`). `STATUS_VALUES` is `plugin/crew/hooks/scripts/crew_ticket.py:143` on main." | `origin/T-0052-build:docs/tickets/T-0052/spec.md:27` | `:9`, `:30`; `STATUS_VALUES` is now `:163`, unchanged |
| 4 | "T-0037's `superseded`, with `split-into: <ids>` on its own line under the spec header. If T-0037 has not merged ... step 3 stops rather than inventing a status." | `origin/T-0052-build:docs/tickets/T-0052/spec.md:40` | grammar reserved (Intent); `move --to superseded` accepted |
| 5 | "sets the parent's spec header and INDEX status to `superseded` with a `split-into:` line" | `origin/T-0052-build:docs/tickets/T-0052/spec.md:64` | Acceptance 1, 2 |
| 6 | "stop if `mint` or `superseded` landed with a different contract" | `origin/T-0052-build:docs/tickets/T-0052/plan.md:3` | contract here |
| 7 | "`superseded` becomes a closed word" | `origin/T-0058-build:docs/tickets/T-0058/spec.md:20` | Acceptance 3, 4 |
| 8 | "`closed` once the parent is `superseded`"; test `test_superseded_parent_is_closed` | `origin/T-0058-build:docs/tickets/T-0058/spec.md:48`, `plan.md:21`, `:24` | Acceptance 4 (INDEX and header) |
| 9 | "INDEX rows `ready`, parent `superseded` with `split-into`" | `origin/T-0058-build:docs/tickets/T-0058/plan.md:15` | Acceptance 1 |
| 10 | "the status vocabulary and which header edits stale an approval" | `origin/T-0059-build:docs/tickets/T-0059/spec.md:18` | Evidence last bullet; Acceptance 5 |
| 11 | "It redefines `STATUS_VALUES` and which header edits keep an approval, and `/crew:done`'s non-final-slice edit (`in-progress`, not `done`) must use that vocabulary without staling the approval." | `origin/T-0059-build:docs/tickets/T-0059/spec.md:23` | `in-progress` keeps it (Acceptance 5). OWNER CHECK: `STATUS_VALUES` is not redefined |
| 12 | "No new ticket status. A non-final slice leaves the header at `in-progress`" | `origin/T-0059-build:docs/tickets/T-0059/spec.md:9` | unchanged word |
| 13 | "stop if `ship`, `merge_argv`, the status vocabulary or `crew_split` landed with a different contract"; "using T-0037's status vocabulary as merged" | `origin/T-0059-build:docs/tickets/T-0059/plan.md:3`, `:23` | contract here |
| 14 | "a proposal that needs the owner becomes a `needs-owner` item once T-0037 lands" | `origin/T-0039-build:docs/tickets/T-0039/direction.md:51`, `:59` | `needs-owner` (Acceptance 6, 7) |
| 15 | "Adds no ticket status. The needs-owner status belongs to T-0037"; "as a `needs-owner` item (T-0037)" | `origin/offload/win-repo-2-tickets:offload/T-0040/spec.md:15`, `direction.md:36` | `needs-owner`; mint `ready`, then move |
## Unknowns
- **How a non-ticket item becomes `needs-owner`** (T-0039's tracked secret, T-0040's WSL install). This ticket gives the status, not an item store. They mint a `ready` ticket and move it to `needs-owner`. OWNER CHECK: no separate needs-owner queue.
- **Obsidian lane for the closed words.** `done`, checked (OWNER CHECK). A cancelled card then looks finished on the board. The alternative is a new `obsidian.columns.closed` key, which is a config-key change.
- **Jira/SDP.** A cancelled or superseded ticket is not pushed. The owner closes the issue by hand. OWNER CHECK: this could instead extend `jira-sync`/`sdp-sync` `--to`.
- **Active ticket that is cancelled.** If `.crew` active-ticket pointer names a ticket whose header is set to `cancelled`, its approval goes stale, and the completion audit then refuses changes as "Touch is not approved". That is intended (a cancelled contract authorises nothing). It is stated so it is not mistaken for a bug.
- **Line 2 of the spec.** `split-into:`/`superseded-by:` sit on line 2, as `depends-on:` already does. Re-check at implement that `crew_ticket.validate` accepts a line between the header and the first `##`.
- **Order of the two PRs.** PR A (feature) cannot carry sabotage mutations, because `sabotage*.py` is `HARNESS`. Its sabotage is run by hand and recorded, and PR B registers it. OWNER CHECK: two PRs.
## Touch
- `plugin/crew/hooks/scripts/crew_tracker.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_status.py`
- `plugin/crew/commands/obsidian-sync.md`
- `plugin/crew/commands/status.md`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_tracker.py`
- `plugin/crew/tests/test_crew_state.py`
- `plugin/crew/tests/test_crew_ticket.py`
- `plugin/crew/tests/test_approval_digest.py`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/tests/test_status.py`
- `plugin/crew/tests/test_status_vocabulary.py`
- `plugin/crew/tests/sabotage_tracker.py`
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/tests/sabotage_scope.py`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `.crew/codemap/crew.md`
## Acceptance checks
- [ ] 1. `crew_tracker.py move --to superseded` and `--to cancelled` succeed from every open status (`direction` through `review`, and `needs-owner`) in files and Obsidian mode. INDEX shows the word. Obsidian puts the card in the `done` lane, checked. Moving back out of either needs `--reopen`, and without it the move is refused with nothing written (must-block). `done` -> `cancelled` also needs `--reopen` (tests in `test_crew_tracker.py`).
- [ ] 2. `move --to needs-owner` succeeds from every open status, and back to any open status, with no `--reopen`. From `done`, `cancelled` or `superseded` it needs `--reopen`. Obsidian puts it in `backlog`. Jira and SDP print "nothing to push" for all three words and exit 0 (must-allow).
- [ ] 3. `crew_state.read_work` skips a `cancelled` or `superseded` table row, and a prose `- cancelled: T-1` / `- Superseded: T-1` line, in any case. A `needs-owner` row is open (must-allow). A title cell saying "cancelled" does not close an open row (must-allow, the `test_crew_state.py:370` shape). `crew_ticket.precheck` refuses approval of a `cancelled` or `superseded` row ("is closed in .work/INDEX.md"), and `crew_autopilot.open_index_tickets` drops it (must-block; tests in `test_crew_state.py`, `test_crew_ticket.py`).
- [ ] 4. Autopilot `next` returns `closed` (`WAITING` `nobody`) for an INDEX row `cancelled` or `superseded`, and for a spec header `status: cancelled` or `status: superseded`. A header `merged` does not close (unchanged). The closed reason quotes a `split-into:` or `superseded-by:` line when there is one (`test_superseded_parent_is_closed`, `test_cancelled_header_is_closed`).
- [ ] 5. Approval: a header edit to `in-progress` (and to each other `STATUS_VALUES` word) keeps an approval. An edit to `cancelled`, `superseded` or `needs-owner` stales it (must-block). `STATUS_VALUES` is byte-identical to main's (`test_approval_digest.py`).
- [ ] 6. Autopilot `next` stops on an INDEX `needs-owner` row as phase `needs-owner` (`WAITING` `owner`), naming the ticket's unanswered `## Open questions`, or saying there are none. It never stops as "cannot tell whether direction is approved" (`test_crew_autopilot.py`, `test_crew_autopilot_status.py`).
- [ ] 7. `/crew:status` prints `owner    <ids> (needs-owner)` when any row is `needs-owner`. `cancelled` and `superseded` rows appear in neither line, and the output is byte-identical to today's when no row holds a new word (`test_status.py`).
- [ ] 8. One vocabulary: `test_status_vocabulary.py` asserts that `crew_tracker.CLOSED_STATUSES` is a subset of `crew_state._TABLE_DONE_WORDS`, of `crew_autopilot.INDEX_DONE` and of `crew_autopilot.HEADER_CLOSED`; that it shares nothing with `crew_ticket.STATUS_VALUES`; and that `obsidian-sync.md`'s table lists every `LANE_FOR_STATUS` key.
- [ ] 9. Sabotage (PR B, registered): `cancelled` added to `STATUS_VALUES`; `superseded` dropped from `_TABLE_DONE_WORDS`; `cancelled` dropped from `_DONE_RE`; `superseded` dropped from `INDEX_DONE`; `HEADER_CLOSED` reduced to `done`; `_backwards` letting a closed word move out without `--reopen`; `needs-owner` read as direction-unapproved. Each turns a named test red. In PR A, each is run by hand and its red test recorded.
- [ ] 10. README gains a "Ticket statuses" table (word, open/closed, header or INDEX, approval kept or staled, lane, Jira/SDP). `obsidian-sync.md` and `status.md` stay within their line budgets. `python3 scripts/check-marketplace.py` passes after the version is set last.
