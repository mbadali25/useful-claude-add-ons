# Cloud handoff: T-0083

**vault recall relevance: prefer this repo's project and concept/decision notes, skip archived sessions, no off-topic hits (owner: Obsidian-first recall)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent ticket. Its children are L-0675 (child 1) and L-0676 (child 2). This ticket is itself slice 1 of 3: the obsidian-vault recall CLI.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Priority med.
- **Branch:** `T-0083-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0083/direction.md`, `docs/tickets/T-0083/spec.md`
- **Size:** about 135 production lines, all in `plugin/obsidian-vault/hooks/scripts/vault_recall.py`.
- **Harness:** no. No path in the spec's Touch list is a review/gate harness path. This is a feature PR in the obsidian-vault plugin; no file under `plugin/crew/` changes.

## Dependencies and work order

Must land first: none open.

| Ticket | State | Why |
|---|---|---|
| T-0021 | merged | Obsidian support in crew. Context only, nothing to wait for. |
| T-0087 | merged | The tooling-PRs-land-alone rule. It forces the crew sabotage mutations into their own PR (L-0676). |
| T-0088 | merged | Linked worktrees read the main checkout's repo config, where L-0675's `memory.recall.projects` key lives. |

The ticket facts list T-0088 for this ticket; the spec lists it only under L-0675, and names the crew 1.0.25 redesign (commit `6c497a14`, on main) instead. The spec wins: T-0088 matters to L-0675, not to this slice. All of these have landed, so nothing is waiting.

Nothing blocks this ticket. It can be worked now.

This ticket blocks:
- L-0675 (child 1): needs the CLI's `--project` option.
- L-0676 (child 2): through L-0675.

Family order:
1. T-0083 (this ticket, feature PR, obsidian-vault only)
2. L-0675 (feature PR, crew), after T-0083 has merged
3. L-0676 (tooling-only PR), after L-0675 has merged

Related, no order forced:
- T-0084 (direction): native memories become pointers into vault notes. It does not need this ticket first.
- T-0507 (direction): refreshes `.crew/codemap/obsidian-vault.md`. Whichever lands second re-anchors.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- A stale plan.md is not published. No plan.md existed for this ticket; the implementing session writes the plan.
- The spec was not approved by the owner in person. Every open choice takes the recommended option; see the open questions.
- This changes default recall results for every caller of the CLI. The CHANGELOG entry must say "behaviour change: default recall results", and obsidian-vault takes a version bump (minor, 0.5.0, is the default taken).
- The shape of `userIgnoreFilters` was not checked against a real `.obsidian/app.json`. The spec makes that an implement-time check. If the shape differs, only the built-in `wiki/sessions/archive/` prefix ships. Whether a cloud session has a real vault to read: could not tell.
- The floor thresholds (1, 2, 3) are a judgement. The spec asks for a hand run over a real vault with five recent prompts, recorded in the PR body. Whether a cloud session can do that: could not tell.
- The existing `_t_recall` checks must pass with no edit to their expectations.
- Recall stays read-only: no write to any vault, and no edit to a vault's `.obsidian/app.json`.
- Sabotage for this slice is by hand; the spec says to record it in `.work/tickets/T-0083/sabotage.md`. `.work/` is not tracked, so where a cloud session records it: could not tell. The PR body is the safe place.
- `.crew/verify.json` has no rule for the obsidian-vault suite on a `vault_recall.py` change; the spec adds one.
- The direction file's "Note for publishing" and the spec's open question 5 ask for two other projects' names to be replaced. That is already done in the published copy.
- The direction file carries two older owner decisions that still apply: catch up with main by merge, never rebase; and run the suites with `-n 4` through the heavy-run wrapper.

## Open questions for the owner (recommended option taken)

1. Another project's notes when `--project` is given: rank last (taken), or drop them?
2. Excluded folders: the built-in archive prefix plus the vault's plain `userIgnoreFilters` entries (taken), or the built-in prefix only?
3. Relevance floor: 1 matched term for a query of one or two terms, 2 for three to five, 3 for six or more (taken), or a stricter or looser rule?
4. obsidian-vault version: minor bump to 0.5.0 because default results change (taken), or a patch bump?
5. Replace the two other projects' names in direction.md before publishing? Taken: yes, done in this copy.

The children's questions are in their own HANDOFF.md files (L-0675: default project name, retry on an older CLI; L-0676: bump crew for a tests-only change).

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0083/` in the final PR unless the owner wants it kept.
