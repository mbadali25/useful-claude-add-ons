# Cloud handoff: L-0677

**crew_memory.py save - write the vault note, then turn the native memory into a pointer**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

Blocked until T-0084 has merged: it needs the pointer grammar and `resolve` on main.

- **Role:** child ticket, split from T-0084, child 1 of 3 (slice 2 of the family's 4, counting the parent's own slice).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0677-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0677/direction.md`, `docs/tickets/L-0677/spec.md`
- **Size:** about 230 production lines in `plugin/crew/hooks/scripts/crew_memory.py`.
- **Harness:** no. Feature PR; no harness path may be in it. Its sabotage entries are L-0679.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0084 | direction, spec ready, not built | Must merge first. The pointer grammar, `resolve`, the test module and the verify rule this child extends. |
| T-0021 | merged | Vault handling in crew. |
| T-0077 | merged | The atomic-write precedent in crew. |

The ticket facts name only T-0084; the spec adds T-0021 and T-0077, both merged. The spec wins; nothing extra is waiting.

This ticket blocks:
- L-0678: migration calls `save`'s plan and apply functions.
- L-0679: its mutations h to m target this code.

Family order:
1. T-0084 (parent: pointer format, `resolve`, `check`; feature PR)
2. L-0677 (`save`; feature PR), after T-0084 has merged
3. L-0678 (`migrate` and `restore`; feature PR), after L-0677 has merged
4. L-0679 (sabotage entries; tooling-only PR), after L-0678 has merged. Its direction allows the entries for T-0084 and L-0677 to land first in one tooling PR, and L-0678's in a second, if L-0678 is delayed.

Related, no order forced: T-0083 (direction), T-0048 (spec), T-0046 (in-progress), as in the parent spec.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. Line numbers in `crew_memory.py` do not exist until T-0084 merges and are read at plan time.
- A stale plan.md is not published. The implementing session writes the plan.
- Order is the whole point: the vault note is written and read back first, and only then is the native body replaced. Every refusal leaves the native file byte-identical. A dangling pointer is never written.
- Compute the full note text before any file is opened for write, and pass `newline="\n"` on every write (repo CLAUDE.md, Landmines).
- Never overwrite an existing note body. Never write to a `recall` or `ignore` vault, or substitute for an unavailable primary.
- A script write does not pass through the vault guard hook, so the note must conform to the vault's frontmatter contract on its own.
- Two checks need a real session and are recorded in the PR body: whether Claude Code keeps a memory whose body is one pointer line, and one real `save --apply` on a scratch memory followed by a new session. Whether a cloud session can do either: could not tell. The spec says the first is resolved before review.
- No edit to `MEMORY.md`, no hook, no config key, no change under `plugin/obsidian-vault/`.

## Open questions for the owner (recommended option taken)

The questions are the parent's (see T-0084's HANDOFF.md). The ones that decide this slice:

1. Crew writes the note itself (taken), or delegates to an obsidian-vault CLI subcommand?
2. Default note folder `memories/<project>/<title>.md` (taken).
3. Default note type `concept` (taken), or `meta`?
4. An existing note for the same memory gets a dated `## Update` passage (taken), or its body is replaced?
5. `OBSIDIAN_VAULT_PATH` is ignored by writer and resolver (taken). If the owner reverses it, both change together.
6. Unverified: whether Claude Code keeps or rewrites a one-line memory body.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0677/` in the final PR unless the owner wants it kept.
