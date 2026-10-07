# Cloud handoff: T-0071

**T-0021 accepted-findings follow-up: repo identity keeps case (priority), `file://` origins, moves converge on INDEX, quote and checkbox reads, `fix.md` under Jira/SDP**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent with one child, L-0669 (the sabotage mutations for these fixes, a tooling PR).
- **INDEX status:** direction, priority high (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0071-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0071/direction.md`, `docs/tickets/T-0071/spec.md`
- **Size:** about 95 production lines: `plugin/crew/hooks/scripts/crew_tracker.py` about 85, `plugin/crew/commands/fix.md` about 10. No harness path: a feature PR. `scripts/check-tooling-pr.py` must print `tooling-pr: no harness path changed`.

Six of the seven accepted findings are in scope (#1 to #6). #7 (Windows-only tests) already merged with T-0077 and is dropped. The INDEX title still lists it.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0021 | merged | The Obsidian tracker these findings were accepted on. |
| T-0077 | merged | Fixed finding #7 and added the Windows directory holds; the spec's line numbers are after it. |
| T-0087 | merged | The tooling-PR rule that moves the sabotage mutations to L-0669. |
| T-0019 | in progress; its mint code is on main | Second caller of `crew_tracker._card_owner` and `repo_id`. No order forced, but both signatures are frozen by this spec. |

Nothing unmerged must land first. This ticket can be worked now.

Same file, no order forced; merge main before review if one lands first: T-0081 (vault walk identity), L-0530 and L-0571 (`LANE_FOR_STATUS` rows), T-0022 (autopilot tracker phase calls `move`), T-0052 (split through mint). PR #394 (T-0037, open on 2026-10-04) also edits `crew_tracker.py`: its body says it adds status rows and a `--reopen` rule for moves out of closed statuses. That is not in the spec or the facts; it is added here because fix #3 edits the same move code.

This ticket blocks L-0669.

Family order: T-0071 (this feature PR) -> L-0669 (tooling PR).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md exists for this ticket. The implementing session writes the plan.
- The spec lists lines that must stay byte-identical because `plugin/crew/tests/sabotage_tracker.py` anchors on them, and that file may not be edited in this PR. Before editing, grep `sabotage_tracker.py` for every string it anchors in `crew_tracker.py`, `fix.md` and `brainstorm.md` and re-check the list. In fix 3, keep the name `key` bound to the lane in use on the anchored line.
- `crew_ticket.py` is harness and calls `_card_owner` and `repo_id`. Do not change `_card_owner`'s signature or 3-tuple, or `repo_id`'s signature.
- Fix #1 is breaking for notes written with a mixed-case origin: they are refused until their `repo-id:` line is edited by hand. The CHANGELOG entry must flag it. No automatic acceptance of the old lowercased id.
- Each new test is seen failing before its fix; quote the red line in the evidence.
- The Windows drive-letter branch runs only on Windows in production. It is tested through a pure helper with the platform passed in; if no native Windows CI job runs on the PR, say so in the PR body.
- direction.md's two "Owner decision 2026-09-30" notes (merge main in, never rebase; run suites in parallel capped at 4) describe the owner's local setup. The merge-not-rebase rule still applies. Whether the parallel-run setup exists in the cloud session: could not tell.
- The new must-block tests are not mutation-proven until L-0669 lands.

## Open questions for the owner (recommended option taken)

1. #1 compatibility: old notes for a mixed-case origin are refused until edited by hand, and the refusal names the fix. Alternative: a one-time compatibility read, which keeps finding #1 open for existing notes.
2. #1 scope: fold the URL path for named case-insensitive hosts? Taken: no, only scheme and host are folded.
3. #2 on Windows: a `file://` origin with a non-`localhost` authority keeps today's common-dir identity, because git for Windows was not measured. Acceptable until measured?
4. #5 (`fix.md` Jira/SDP create) stays in this ticket rather than its own. Taken: yes.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0071/` in the final PR unless the owner wants it kept.
