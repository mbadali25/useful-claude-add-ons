# Cloud handoff: T-0084

**crew memory writer: native memories become one-line pointers into the vault note, portable across hosts and shells, full text kept when no vault (owner: build #2 into crew)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent ticket. Its children are L-0677 (child 1), L-0678 (child 2) and L-0679 (child 3). This ticket is itself slice 1 of 4: the pointer format and the read-only `resolve` and `check`.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Priority med.
- **Branch:** `T-0084-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0084/direction.md`, `docs/tickets/T-0084/spec.md`
- **Size:** about 180 production lines, all in a new `plugin/crew/hooks/scripts/crew_memory.py`. The whole family is about 560.
- **Harness:** no. This slice touches no review/gate harness path; it is an ordinary feature PR. The sabotage entries are L-0679, a separate tooling-only PR.

## Dependencies and work order

Must land first: none open.

| Ticket | State | Why |
|---|---|---|
| T-0021 | merged | Put vault handling and the `memory.vaultPath` fallback in crew; the resolver reuses the same config sources. |
| T-0077 | merged | Atomic, pinned vault writes in `crew_tracker`: the in-crew precedent the later writer slices follow. |
| T-0087 | merged | The harness-lands-alone rule; it is why the sabotage entries are a separate child. |

Nothing blocks this ticket. It can be worked now.

This ticket blocks L-0677, L-0678 and L-0679. Each needs this slice's format and resolver on main.

Family order:
1. T-0084 (parent: pointer format, `resolve`, `check`; feature PR)
2. L-0677 (`save`; feature PR), after T-0084 has merged
3. L-0678 (`migrate` and `restore`; feature PR), after L-0677 has merged
4. L-0679 (sabotage entries; tooling-only PR), after L-0678 has merged. Its direction allows the entries for T-0084 and L-0677 to land first in one tooling PR, and L-0678's in a second, if L-0678 is delayed.

Related, no order forced:
- T-0083 (direction): recall relevance. No shared file.
- T-0048 (spec) and T-0054 (ready): the full crew guide. If T-0048 lands first, the memory chapter text moves to wherever it puts it.
- T-0046 (in-progress): BUDGETS.md bookkeeping. Until it lands, the BUDGETS.md count edit is in this ticket's Touch list.
- T-0081 (direction): per-component identity checks in `crew_tracker`'s vault walk. Same idea as the containment rule here, different module.

The ticket facts list T-0083, T-0048 and T-0046 as related; the spec adds T-0054 and T-0081. The spec wins.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- A stale plan.md is not published. No plan.md existed for this ticket; the implementing session writes the plan.
- The owner was not available for the brainstorm; each open choice takes the recommended option.
- This slice is read-only. It writes no vault note, no native memory file and no `MEMORY.md`. No hook, no config key, no import from the obsidian-vault plugin.
- The frontmatter of a native memory file is never parsed as YAML and never rewritten: split on the `---` lines only.
- An unavailable named vault is never replaced by another vault. A config file that exists but does not parse is not "no vaults".
- No machine name, account name or absolute vault path in any tracked file. The spec has a grep for this in its acceptance checks.
- A new rule in `.crew/verify.json` is needed for the new script and its test.
- The tests use fixtures only. No real vault or real memory directory is read, so a cloud session can run them.
- One line of the direction's Ask was already reworded before publication to remove machine names and absolute vault paths. The owner's name and a local wrapper path in the older owner-decision sections were replaced mechanically in this copy.
- The direction file carries two older owner decisions that still apply: catch up with main by merge, never rebase; and run the suites with `-n 4` through the heavy-run wrapper.

## Open questions for the owner (recommended option taken)

1. Crew writes the vault note itself (taken), or delegates to an obsidian-vault CLI subcommand?
2. No hook and no SessionStart nudge (taken): sessions use the writer only because the `crew-memory` skill says to. Is a default-OFF PostToolUse hook or a one-line SessionStart reminder wanted as a follow-up?
3. Default note folder when no `--note` is passed: `memories/<project>/<title>.md` (taken); the vault's own CLAUDE.md still wins.
4. Default note type: `concept` (taken), or `meta` as obsidian-vault's `templates/memory.md` ships?
5. Updating an existing note for the same memory appends a dated `## Update` passage (taken), or replaces the body?
6. `OBSIDIAN_VAULT_PATH` is ignored by both resolver and writer so they always agree (taken); should it relocate the vault as it does in obsidian-vault?
7. Unverified: whether Claude Code keeps a native memory whose body is one pointer line, or rewrites it on a later update. L-0677 requires a manual check on a real session before the writer ships.
8. L-0679 puts the mutations in the existing `sabotage_context.py` because `sabotage.py` is at the 3400-line pylint limit; a separate `sabotage_memory.py` needs lines freed there first.
9. The facts asked whether the owner's name and a local wrapper path in direction.md's owner-decision sections should be removed before publication. Taken: yes, replaced in this copy.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0084/` in the final PR unless the owner wants it kept.
