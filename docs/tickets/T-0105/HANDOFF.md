# Cloud handoff: T-0105

**crew migrate carries a 0.20 `autopilot` key to crew.json's top-level `autopilot` instead of `unmapped.autopilot`, and says which file crew reads (item 6 of a report from another repository's session)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent ticket, narrowed to the feature PR. Child: L-0683 (two sabotage rows, tooling-only PR).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0105-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0105/direction.md`, `docs/tickets/T-0105/spec.md`
- **Size:** about 12 production lines, all in `plugin/crew/hooks/scripts/crew_migrate.py`. No harness path: this is a feature PR. Risk is marked low in the spec.

This ticket was first handed to the cloud on 2026-09-30 as a seed direction only (`docs/handoff/cloud/T-0105.md` on main, no branch, no PR). This handoff replaces that note: it adds the direction check and the spec. The spec requires this ticket's PR to delete `docs/handoff/cloud/T-0105.md` and its row in `docs/handoff/cloud/README.md`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0004 | merged | `/crew:autopilot` and the `autopilot` config block this ticket maps. |
| T-0010 | merged | `autopilot.approval` / `autopilot.questions`, and the CONFIG.md "Which file" paragraph this ticket extends. |
| T-0088 | merged | `crew_common.repo_config_file`, which the `settings` warning reads through. |

Nothing open blocks this ticket. It blocks L-0683.

Not a dependency, same file: T-0038 (approved, not started) also edits `crew_migrate.py` and adds the migrate verify rule. Either order; the second to land merges main and re-runs `test_migrate.py`. The spec also names T-0500 (approved), which leaves `crew_migrate.py` alone by design; the facts file does not list it, and it forces no order.

Siblings from the same report, independent: T-0104, T-0106, T-0107, T-0108.

Family order:

1. T-0105 (this ticket): the mapping row, the migrate note, tests, docs.
2. L-0683: two sabotage rows in `sabotage_migrate.py`, tooling-only, after this one merges.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published (none existed). The implementing session writes the plan.
- In direction.md and spec.md, `children/1` means L-0683.
- The report's premise is half wrong, and the spec is built on the correction: crew reads `autopilot` from `.crew/config.json` only, never from crew.json. A remap alone does not make a crew.json edit take effect, so the ticket adds a note naming `.crew/config.json` as the file to edit. `crew_autopilot.py` is not edited.
- No pytest, gate or sabotage run was made when the spec was written. The two measurements were direct calls to `to_crew` and `crew_autopilot.settings` at `155fe6d8`.
- Behaviour change to document: a crew.json written by an older crew keeps `unmapped.autopilot`, and a re-run of `/crew:migrate` there now reports a CONFLICT where it used to say "already migrated (identical)".
- No edit to `plugin/crew/tests/sabotage*.py` and no new verify rule here.
- direction.md holds two owner decisions from 2026-09-30 that still apply: catch up with main by merge, never rebase, force-push or squash; and the parallel-suite instructions. The heavy-run wrapper they name is a local tool of the original host; the cloud session uses its own equivalent.

## Open questions for the owner (recommended option taken)

1. Should crew read `autopilot` from crew.json after a migrate, instead of only saying it does not? Default taken: no (it changes which file arms a driver).
2. Seven other live 1.0 keys also land under `unmapped` (`resume`, `shellRoute`, `cloud`, `environments`, `scope`, `tickets`, `route`). Give them rows too? Default taken: not in this ticket; recommended as one follow-up that checks each key's reader first.
3. Migrate calls `.crew/config.json` "retireable" while crew still reads most settings from it. Change that line? Default taken: untouched here; recommended as part of the two-file follow-up.
4. Is L-0683 (two sabotage rows, tooling-only PR) wanted for a non-guard change? Default taken: yes, kept small.
5. The CONFLICT on re-run for repos migrated by an older crew is accepted and documented. Alternative: an in-place rewrite of the old shape. How many such repos exist: could not tell.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0105/` in the final PR unless the owner wants it kept.
