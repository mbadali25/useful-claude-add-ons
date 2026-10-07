# Cloud handoff: L-0537

**Node.js development standards set (NODE) and a new `stack-node` skill, T-0086 slice**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** slice of T-0086 (done, PR #282); the Node.js stack in the direction's order.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0537-build`, new from origin/main `a555ff37`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0537/direction.md`, `docs/tickets/L-0537/spec.md`
- **Size:** 0 production lines. A new `stack-node/SKILL.md` (about 110 lines, 120 cap), a `node.md` set with the one provisionally admitted rule (NODE-08), about 40 test lines, and the crew skill count moved 31 to 32 at about ten sites.
- **Harness:** no. NODE sabotage entries go in a tooling-only follow-up, or ride along if L-0539 has merged.

## The finding that shapes this ticket

The research lane's "ten rules meet the bar" counted distinct packages and vault notes. Re-counted by the rule `python.md` ships (a commit counts only when its message records a review; one PR counts once), only **NODE-08** reaches three (4). NODE-06, -07 and -10 have two. The spec's Evidence has every count.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0086 | done, merged (#282) | The pattern and the tests. |
| L-0539 | direction, not merged | Would let the sabotage entries ride along. Not a blocker. |
| L-0533 (PHP) | direction / spec | Also adds a stack skill: whichever lands second takes the skill count to 33 and adds to `STACK_NAMES` after it. |
| L-0532..L-0536, L-0538 | direction / spec | Same doc lines; land one at a time. |
| (unminted) | to file | Tooling-only follow-up: the NODE sabotage entries. |

## Read before writing code

- The spec's evidence is at origin/main `a555ff37`. Re-find every line by content.
- The research is `.work/tickets/T-0086/research/node.md` on the owner's host (not in git). Ask the coordinator for a copy if the cloud session cannot read it.
- Re-count before writing `node.md`, including each cited PR's review thread where access allows; if no rule reaches three, ship `stack-node` with all eighteen as candidates and no set file (the loader refuses an empty set).
- `stack-node` is a skill inside the crew plugin: no marketplace entry, no install-script line; but every `plugin-skills:crew` count site moves.
- Keep `stack-node` within 120 lines; the stack-skill test requires a ```json verify rule whose every command has an `exit 77` / `TOOL MISSING` branch.
- Hand-sabotage each new test once and record it in the PR body.

## Open questions for the owner (recommended option taken)

- `applies-to`: all `.ts/.mts/.cts/.js/.mjs/.cjs`; an Angular `.ts` change also draws NODE (accepted).
- A doc MUST is not a third change set (T-0086's settled answer); NODE-01 stays a candidate.
- No `stack-angular` pointer here (L-0538's).
- The `mcp-servers` `graphClient.ts` bearer-on-absolute-URL observation needs its own ticket; not minted here.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), flag the behaviour change in CHANGELOG and the PR body (JS/TS changes now answer NODE rows; in-flight stamps go stale), and remove `docs/tickets/L-0537/` in the final PR unless the owner wants it kept.
