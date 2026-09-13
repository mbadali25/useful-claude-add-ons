# Upgrade report
status: upgraded
to schema: 7
graph build compared against: 8c088ab
  (not an anchor: this file is a one-time report, not a subsystem map,
   and nothing re-verifies it. The sha records what this run read; it
   may not resolve later, and a squash merge is enough to kill it.)

Nothing below was applied automatically. Conflicts are the map and
the graph disagreeing, and either can be wrong: the graph misses
generated call sites, reflection, and dynamic dispatch.

## Config
- roles added: none
- tier: 2 (unchanged)
- roles are added only up to the tier this config already declares. Moving UP a tier is `/crew:scale`; removing a role is `/crew:pm offboard`, which still stops for an explicit yes.
- schema 5 -> 7, which added the `guards` block and `github.mergeGate`: guards.terraformApply, guards.forcePush, guards.adminMerge, guards.mergeGate, guards.prodDatabase, guards.prodServer, github.mergeGate.enabled, github.mergeGate.branch, production.databases, production.hosts. Each guard is `block` | `ask` | `allow` and arrives as `block`. **This migration is NOT entirely behaviour-neutral, and the two places it is not are these.** `guards.adminMerge` refuses `gh pr merge --admin`, which no crew guard refused before, and `guards.terraformApply` now also covers `tofu` — so a command that ran yesterday can be refused today. Both were bypasses, not features; if you need one back, set that guard to `ask` (crew prints the exact command and stops until you approve THAT command) or `allow` (crew runs it and writes a row to `.crew\guard.log` — under `allow` nothing is silent). `guards.terraformApply` and `guards.forcePush` at `block` are exactly what the guard already did. A repo may only NARROW what the global crew config allows, never widen it — the same ratchet as `install.policy` (CONFIG.md §16). Set them with `/crew:config` — nothing here chose anything but the floor for you.
- schema 5 -> 7, which added the `change` block for `/crew:change`: change.requester, change.implementor, change.requireForProduction, change.sdpTemplate, change.jiraIssueType, change.category. **This one IS behaviour-neutral, with no exception to declare.** `change.requireForProduction` arrives `false`, which is what every promotion already did — `/crew:promote production` asks for no change request, exactly as before. The other five are null or a default template name and are read only by `/crew:change`, which you have to invoke. Set `change.requester` and `change.implementor` once with `/crew:config` and every repo on this machine files under them. Note the direction `change.requireForProduction` ratchets, because it is the opposite of the other ratcheted keys and it is easier to read than to discover: a repo may turn the requirement ON and never off, so a machine-global `true` cannot be defeated by a `false` in a repo you cloned (CONFIG.md §17).

## Contradictions — kept in the map, verify by hand
- none

## Added by the graph
- none

## Anchors left stale on purpose
- none

---

**Read the three `none`s above as NOT CHECKED, not as nothing found.** This
run was `crew_upgrade.py --root .` with no `--derived`, so the reconcile had
no graph facts to compare the maps against and did not run at all. A `none`
produced by a check that did not happen is indistinguishable, in this file,
from one produced by a check that found nothing — which is this repo's named
recurring bug, so it is written down rather than left to the reader.

Each run also OVERWRITES this file. The previous run's findings are at
`git show 5b2e1a7a:.crew/codemap/UPGRADE.md` (62 contradictions, 5 added by
the graph, 1 anchor left stale on purpose). Whether any of them still stands
is unmeasured here; this run did not look.

Why no `--derived`: the derived facts were built and measured first. This
marketplace's subsystems barely call each other — the graph finds 0 to 3
cross-subsystem files per subsystem, and 6 of 10 have none at all — so a
reconcile would have added a handful of low-value lines. It would also have
BUMPED THE ANCHOR on each map it touched, and `crew.md` has 15 changed files
among the paths it cites. Marking it re-verified on the strength of one added
"calls out to" line would have converted a real, measurable staleness into a
false freshness claim. Left stale on purpose, at the file level, for the same
reason the section above exists.

