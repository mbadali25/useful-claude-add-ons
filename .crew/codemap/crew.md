anchor: useful-claude-add-ons@84976536
verified: 2026-09-22
Full re-derivation, not a re-anchor. 96 unique `path:line` citations were
re-read against the files they name at this anchor; 35 were byte-identical to
`ea8a014` and 61 had moved or changed subject. Every section below was
re-derived except the two named as carried forward in "Citation freshness".


# crew

The `crew` plugin: a virtual dev team of context-isolated agents, slash
commands, bundled skills, and deterministic hooks. Registered in
`.claude-plugin/marketplace.json` like every other entry here.

## Re-derivation provenance — ea8a014 -> 84976536, 2026-09-22

The per-path check `.crew/codemap/INDEX.md:41` prescribes, run over the 44 repo paths this
note cited at `ea8a014`:

```bash
git diff --name-only ea8a014..HEAD -- <the 44 paths the note cites>
```

returned 27 files. Excluding pure version-bump churn (`plugin/PLUGINS.md`,
the three `README.md`s, `.claude-plugin/marketplace.json`), 22 are
substantive. This is a re-derivation, not a re-point: three of the corrections
below are about the *subject* of a claim, not its line number.

**The anchor is a branch tip, and that is a deliberate trade.** `84976536` is
on `crew-0.19.96-docbuilder-install-fixes` only; `git merge-base HEAD
origin/main` is `d9da1409`, 29 commits back. `.crew/codemap/INDEX.md:25-27` says to record
the merge-base so the anchor survives a squash — but `crew_state.py`,
`_common.sh`, `run-tests.sh`, `check-marketplace.py` and `CONFIG.md` all moved
inside that 29-commit window, so anchoring at `d9da1409` would have made this
note mixed-base: citations taken at one commit, provenance claiming another,
and the path diff reporting "current" while every line number came from
somewhere else. That is the defect `.crew/codemap/INDEX.md:122-123` records against
`repo-docs.md`. An anchor that goes **unresolvable** after a squash is a
recoverable, self-announcing state (`.crew/codemap/INDEX.md:19`); an anchor that is silently
mixed-base is not. If this branch squash-merges, this note reads
`knowledge.unresolvable` and must be re-derived — that is the intended outcome,
not a mistake to repair by editing the sha.

**Corrections this pass made that are not line-number drift — read these even
if you skip the rest:**

1. **The note's Hooks section was wrong at its own anchor, and is now right
   again for a different reason.** It described `PreToolUse` as four entries
   with a command `guard` registered twice. At `ea8a014` that file held
   **18** hook entries across **9** scripts and `PreToolUse` had **two**
   (`promote-gate` only): `guard.sh`/`guard.ps1` were deleted by `3fe7287f`
   ("crew 0.19.54: remove the command guard"), which `git merge-base
   --is-ancestor 3fe7287f ea8a014` confirms is an ancestor of that anchor.
   At this anchor the file is back to **20** entries across **10** scripts —
   but the fourth `PreToolUse` pair is `role-write-guard`, matching
   `Write|Edit`, not a command guard matching `Bash`. A reader who trusted the
   old table would have gone looking for a Bash command inspector that has not
   existed for two releases. See "Hooks" and "The role-write guard" below.
2. **`AUTOCLEAR_CONSENT_KEYS` changed module.** The note cited
   `plugin/crew/hooks/scripts/crew_config.py:271`; the definition was actually
   at `plugin/crew/hooks/scripts/crew_config.py:276` at `ea8a014`, and is now
   at `plugin/crew/hooks/scripts/crew_state.py:682`.
   `plugin/crew/hooks/scripts/crew_config.py:473` consumes it as
   `crew_state.AUTOCLEAR_CONSENT_KEYS`, so a search of `crew_config.py` for the
   definition finds only the use.
3. **The config leaf counts were wrong at the previous anchor, and contradicted
   the file this note names as the authority.** The table said 102 / 59 / 43.
   Executing `leaf_paths` over both defaults gives **103 / 60 / 43**, and gave
   103 / 60 / 43 at `ea8a014` too — the leaf *sets* are identical between the
   two anchors, so this was never drift, it was a miscount. `plugin/crew/CONFIG.md:130-131`
   already stated 60 / 103 / 43. The note's own rule — CONFIG.md is the
   authority where the two disagree — was the one not applied.
4. **`TRIGGERS` is 15, not 12, and `_RATCHETED` is 10, not 9.** Three verify-map
   triggers and one role-write guard key landed. See the new sections below.
5. **The "every live count agrees" finding has inverted again.** It last read
   FIXED. At this anchor five sites state the agent/command/skill counts and
   three disagree with the directories on disk. See "Where the live counts of
   crew's shape disagree".
6. **The `run-tests.sh` PATH-scrub table protects a different binary now.** The
   proofs are intact and still run, but they guard `promote-gate.sh`'s no-jq
   fallback; there is no `guard()` helper in that file any more, only `pgate()`.
   All six of its coordinates moved.

**A measurement error this pass made, recorded because it nearly became a
finding.** A `grep -c jq` over `run-tests.sh` returned empty in this session's
shell on a file containing 65 matches, which read as "the jq PATH-scrub proofs
have been deleted along with the guard suite" — a large, plausible, entirely
false finding. It was caught by `sed -n 178p` printing a line containing
`NOJQ_PATH`, which `grep` had just claimed did not exist. Every count in this
note was re-taken with Python file reads rather than `grep` afterwards. This is
CLAUDE.md's "run the states; do not reason about them" in its other direction:
check what changed about the *measurement* before reporting a regression.

## Older provenance

Kept as an account of what earlier passes covered and did not, not as claims
about the current code.

**ea8a014 (narrow), 975480b7 -> f9bb78a6, 0a9d8937 -> 975480b7 — all
2026-09-14.** Three consecutive narrow passes, each re-reading only the
skill-count table and advancing the sha. The shape of the failure is visible in
hindsight and worth naming: three passes in a row touched the same table, and
none of them re-read the Hooks section, which had been wrong since `3fe7287f`
landed before the first of them. A narrow pass is honest about what it did not
read, but a run of them leaves everything else ageing while `verified:` keeps
moving forward.

**a573ca24 -> 0a9d8937, 2026-09-14.** The pass that first traced the
`crew_state.py` split into `crew_freshness.py` and `crew_guards.py`, corrected
`_widens` from "two special-cased keys" to a registry, and corrected the
`--worktree-path` branch's imports.

**d61342c3 -> 7b0d8f3a, 2026-09-12.** Six merged PRs rewrote the config
layering, the consent-key carve-out, and the codemap anchor mechanism itself,
so that pass re-derived rather than re-pointed. `d61342c3` named no object in
this repository — the head of a squash-merged branch, discarded by the merge.

**b56d41f -> 3167721f, 2026-09-05.** Declined to re-verify `crew_state.py`'s
internals because the file had not moved in its diff window, and said the
guarantee was spent the moment `plugin/crew/hooks/scripts/` appeared in a
future diff. It has, four times since.

**What the first re-derivation (2026-09-12) got wrong, kept as the lesson.**
That pass's header claimed full re-derivation; a post-hoc diff against its own
predecessor found 33 citations carried forward on untouched lines, 12 of them
wrong. The reusable rule, still followed here: a re-derivation cannot be
verified by the thing doing the re-deriving.

## Inventory

**DERIVED at this anchor**, counted by walking the directories:

| | Count | How counted |
|---|---|---|
| Agents | 54 | `.md` files in `plugin/crew/agents/` |
| Commands | 28 | `.md` files in `plugin/crew/commands/` |
| Skills | 20 | subdirectories of `plugin/crew/skills/` |

Commands went 26 -> 28 (`plugin/crew/commands/debug.md` and
`plugin/crew/commands/split.md`, both added since `ea8a014`). Skills went
**19 -> 20**, not 18 -> 20: `git ls-tree --name-only ea8a014
plugin/crew/skills/` returns 19 directories, so the previous note's stated 18
was already one short **at its own anchor** — `crew-lint` had landed and the
three narrow passes that followed all re-read the count table without
re-walking the directory it describes. The 20th is `crew-debugging`.

The 54 agents still decompose exactly, re-counted at this anchor by importing
the module: `ROLE_TIERS` has **13** entries
(`plugin/crew/hooks/scripts/crew_state.py:1205-1222`), `SPECIALIST_ROLES` has
**40** (`plugin/crew/hooks/scripts/crew_state.py:1253-1294`), and
`plugin/crew/agents/pm.md` is the standing manager on neither list.
13 + 40 + 1 = 54, and the two-way check holds — same membership as the previous
anchor.

### Where the live counts of crew's shape disagree — REGRESSED since f9bb78a6

**Re-derived at this anchor.** The previous version of this table was headed
FIXED and recorded five live sites all reading the same figures. That no longer
holds: two new commands and one new skill landed and three of the sites were
not swept.

| Place | Says | Against disk (54 / 28 / 20, 20 hook entries, 10 scripts) |
|---|---|---|
| `plugin/PLUGINS.md:17` | 54 agents, 28 commands, 20 skills, 20 hook entries (10 scripts × `.sh`/`.ps1`) across 5 events | **fully correct** — the only site that is |
| `plugin/README.md:414` | 54 agents, 28 commands, 20 skills, **18** hook entries | hook count stale |
| `README.md:168` | 54 subagents, 28 commands, 20 skills, **18** hook entries (**9** scripts × `.sh`/`.ps1`) across 5 events | hook count and script count stale |
| `README.md:889` | 54 agents, 28 commands, 20 skills, **18** hook entries | hook count stale |
| `INSTALLATION.md:252` | 54 subagents, 28 commands, 20 skills, **18** hook entries across 5 events | hook count stale |
| `.claude-plugin/marketplace.json:229` | 54 agents, **27** commands, **19** skills | commands and skills stale; carries no `plugin-skills` marker of its own |
| `scripts/install-prerequisites.sh:1322`, `.ps1:1089` | 54 agents, **26** commands | commands stale in both, identical text in each so `pick_fit` / `Format-PickerLine` stay unaffected |
| `plugin/crew/skills/crew-best-practices/SKILL.md:29` | "54 agents or **26** commands" | commands stale |

**JUDGEMENT — why the marker did not catch this.** `check_self_claims`
(`scripts/check-marketplace.py:579-722`, the `plugin-skills:<name>` branch at
`:665-681`) verifies a marked *skills* number against `plugin/<name>/skills/`
on disk, and the four sites carrying that marker all read 20 and all pass.
Nothing marks an agent count, a command count or a hook-entry count, so those
three quantities drift with the gate green. That is consistent with CLAUDE.md's
rule — an unmarked number is deliberately not checked — and it means the fix
for this row set is markers, not edits. `python3 scripts/check-marketplace.py`
passes at this anchor with five of the eight rows above wrong.

Two changelog entries under versioned release headings
(`plugin/README.md:370`, `README.md:591`) still read 17 and are correctly
untouched — they are history, true when written.

**JUDGEMENT, unchanged reasoning from the previous anchor:** this note does not
list specialists by name. `SPECIALIST_ROLES` is the authority and cheap to
print; a reproduced list is a second copy that can only rot.

Structural facts about the roster, re-derived:

- Every specialist sits off the tier ladder — `roles_for_tier`
  (`plugin/crew/hooks/scripts/crew_state.py:1309-1311`) reads only `ROLE_TIERS`.
- `known_role` (`plugin/crew/hooks/scripts/crew_state.py:1297-1306`) is what
  keeps a deliberately-onboarded specialist from being reported as a typo on
  upgrade.

## Hooks

`plugin/crew/hooks/hooks.json` (38 lines) registers **five** events and **20**
hook entries across **10** distinct scripts, re-derived at this anchor by
parsing the JSON rather than counting lines:

| Event | Entries | Line |
|---|---|---|
| `SessionStart` | 6 | `plugin/crew/hooks/hooks.json:3` |
| `PreToolUse` | 4 | `plugin/crew/hooks/hooks.json:11` |
| `PreCompact` | 2 | `plugin/crew/hooks/hooks.json:21` |
| `Notification` | 2 | `plugin/crew/hooks/hooks.json:25` |
| `Stop` | 6 | `plugin/crew/hooks/hooks.json:29` |

Every count is even because each bash `command` has a `shell: "powershell"`
sibling on the same event — CLAUDE.md's rule that a bare `command` goes to Git
Bash on Windows, so each event is registered once per flavour.

**`PreToolUse` matches on tool, and what it matches changed.** `promote-gate`
is registered `matcher: "Bash"` (`plugin/crew/hooks/hooks.json:12`) and
`matcher: "PowerShell"` (`:14`). `role-write-guard` is registered twice under
`matcher: "Write|Edit"` (`:16`, `:18`) — bash at `:17`, PowerShell at `:19`.
**There is no longer any hook that inspects a Bash or PowerShell command before
it runs**; `plugin/README.md:414` states the removal in prose ("The PreToolUse
command guard was REMOVED in 0.19.52").

## The role-write guard — new since this note's previous anchor

`plugin/crew/hooks/scripts/role_write_guard.py` (938 lines) with
`role-write-guard.sh` (128) and `role-write-guard.ps1` (244) is the new
`PreToolUse` pair. It classifies a `Write`/`Edit` target against the acting
role and can refuse it.

- **It can block, so it defaults off.** `ROLE_WRITE_POLICIES`
  (`plugin/crew/hooks/scripts/crew_guards.py:147`) is
  `("block", "report", "off")` and `ROLE_WRITE_DEFAULT`
  (`plugin/crew/hooks/scripts/crew_guards.py:164`) is `"off"` —
  `default_config()["guards"]["roleWrites"]` resolves to `off`, confirmed by
  executing the module. This is the one guard whose **default is not its
  floor**: the floor is `block`, so `role_writes_rank`
  (`plugin/crew/hooks/scripts/crew_guards.py:400-411`) ranks an absent value at
  `off`'s position rather than at the floor, and a repo cloned with
  `guards.roleWrites: off` therefore cannot silently widen a machine-global
  `block`. `normalise_role_writes` is at
  `plugin/crew/hooks/scripts/crew_guards.py:374-397`.
- **It carries the committed regression suite CLAUDE.md requires of a blocking
  hook**: `plugin/crew/tests/test_role_write_guard.py`, 2158 lines. Confirmed
  present and sized; **not read, and not sabotage-tested as part of this pass**
  — see "Unverified at this anchor".
- `classify` (`plugin/crew/hooks/scripts/role_write_guard.py:587`) is the
  decision function. The path-resolution helpers around it split by platform —
  `_resolve_real_target_posix` (`:441`) and `_resolve_real_target_windows`
  (`:480`) — and `_is_extended_length_prefix_path` (`:338`) exists because a
  `\\?\` prefixed target is a real Windows spelling that a naive repo-relative
  check reads as outside the repo.
- `ALL_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:170`) is now
  `GUARD_NAMES + PROD_GUARD_NAMES + ROLE_WRITE_GUARD_NAMES` — seven guards in
  three vocabularies, which is why `guard_tiers`
  (used by `RATCHETED_KEYS`, `plugin/crew/hooks/scripts/crew_guards.py:446-450`)
  dispatches on which tuple a name belongs to rather than assuming
  `block`/`ask`/`allow`.

## The verify map's three new triggers

**Not covered by any previous version of this note.** `read_verify_health`
(`plugin/crew/hooks/scripts/crew_state.py:530`) feeds three triggers added
since `ea8a014`, all three gated on `verify_map_present`
(`plugin/crew/hooks/scripts/crew_state.py:2993`):

| Trigger | Set at | Fires when |
|---|---|---|
| `verifyMarkerStale` | `plugin/crew/hooks/scripts/crew_state.py:3016-3020` | no marker, **or** its distance from HEAD could not be computed, **or** that distance exceeds `VERIFY_MARKER_STALE_COMMITS` (`:527`, = 50) |
| `verifyRulesUnpriced` | `plugin/crew/hooks/scripts/crew_state.py:3021-3024` | `unpricedRules` is `None` **or** greater than zero |
| `verifyReachUndeclared` | `plugin/crew/hooks/scripts/crew_state.py:3025-3028` | `undeclaredReachRules` is `None` **or** greater than zero |

**DERIVED, and the reason it is worth its own row:** all three treat `None` —
"could not tell" — exactly as they treat a known-bad value. The comment at
`plugin/crew/hooks/scripts/crew_state.py:3011-3015` states the rule in the
file's own words ("UNKNOWN NEVER RESOLVES TO HEALTHY"). This is CLAUDE.md's
recurring-bug lesson implemented rather than described: the unknown does not
collapse into the safe-looking value. The backing modules are
`verify_fingerprint.py` (399 lines), `verify_price.py` (182) and
`verify_record.py` (682), all new since `ea8a014` and **not read this pass**.

## The promote-gate PATH-scrub proofs in run-tests.sh

**Re-derived; the proofs are unchanged in kind and all six coordinates moved.**
`plugin/crew/hooks/scripts/_test/run-tests.sh` is **1030** lines at this anchor,
up from 923 at `ea8a014`. The previous note recorded 1180, which the file has
never been.

**What these proofs now protect is `promote-gate.sh`, not the command guard.**
The file's section headers are `verify-gate.sh` (`:200`), `promote-gate.sh`
(`:418`), the emergency lane (`:555`), `claude-md-audit.sh` (`:660`),
`resolve-tools.sh` (`:673`), `pm_pulse.py` (`:709`) and `crew_state.py`
diagrams (`:933`). There is no `guard()` helper — only `pgate()` (`:448`).

| Check | Line | What a silent failure would look like |
|---|---|---|
| the jq mirror (`$JQ_SHADOW`) still resolves `jq` | `:123-127` | a scrub that does nothing, so every case takes the jq fast path |
| the scrubbed real `PATH` still resolves `jq` | `:164-169` | the same, one layer out |
| no working python survives the scrub | `:178-194` | `promote-gate.sh` prints "no jq and no python" and exits 0, so every must-BLOCK case passes against a gate that never ran |

The third proof walks `crew_py`'s own order (`python3`, `python`, `py`,
`:179`) and *executes* the first name that resolves (`:185-186`), exactly as
`crew_py` does — checking the rest of the list would pass where `crew_py`
fails. Every `jq` spelling the mirror must exclude (`jq`, `jq.exe`, `jq.bat`, …)
is enumerated at `:119`. Resolved-directory comparison (`cd … && pwd -P`, the
fix for the merged-`/usr` Linux false-refusal) is at `:79` for jq's own
directory and `:134` for each `PATH` entry.

### `crew_py` is no longer the whole story — `crew_py_strict` exists

**Corrected at this anchor; the previous note called this "known open issue,
still open".** It is now half-closed, and the half that closed is the one that
matters for a hook that `exec`s the interpreter.

- `crew_py()` (`plugin/crew/hooks/scripts/_common.sh:52-57`) still returns the
  first of `python3`/`python`/`py` that `command -v` **resolves**, not the
  first that runs. That is now documented as deliberate at
  `plugin/crew/hooks/scripts/_common.sh:42-51`: most callers check the status
  of the python they invoked and fail closed, and widening this function would
  change every hook that calls it.
- `crew_py_strict()` (`plugin/crew/hooks/scripts/_common.sh:82-98`) is new. It
  executes each candidate (`"$candidate" -c 'import sys; print(sys.executable)'`)
  and rejects any whose path or resolved `sys.executable` lands under
  `WindowsApps` — the App Execution Alias stub that opens the Microsoft Store.
- **Exactly one caller uses the strict form today:**
  `plugin/crew/hooks/scripts/pm-pulse.sh:30`, whose own comment at `:14-16`
  records the reason and the date (2026-09-22). Every other `.sh` hook
  (`context-watch`, `handoff-read`, `handoff-write`, `platform-sync`,
  `pm-brief`, `notify`, `promote-gate`, `verify-gate`) still calls plain
  `crew_py`. `plugin/crew/hooks/scripts/role-write-guard.sh:17-27` uses neither and says so in a comment.
- **`TODO.md:383-413` is now stale in two ways**, out of this note's scope to
  fix but worth naming so nobody re-derives it: it cites
  `plugin/crew/hooks/scripts/_common.sh:38-43` (the function is at `:52-57`),
  and its reproduction describes the stub being handed to `guard.sh`, a file
  deleted in 0.19.54.

## `crew_state.py`'s two splits — `crew_freshness.py` and `crew_guards.py`

`plugin/crew/hooks/scripts/crew_state.py` is **3379** lines at this anchor, up
from 2858. Both split-off modules are still in place and both re-export sets
grew:

- `plugin/crew/hooks/scripts/crew_freshness.py` (**541** lines, **byte-identical
  to `ea8a014`** — every citation into it below is current by the per-path
  check, not by re-reading) owns telling a stale codemap, diagram, or graph
  from a current one. `plugin/crew/hooks/scripts/crew_state.py:122-144`
  re-imports **21** names from it, up from 15.
- `plugin/crew/hooks/scripts/crew_guards.py` (**974** lines, up from 888) owns
  the guard and install-policy vocabulary.
  `plugin/crew/hooks/scripts/crew_state.py:68-110` re-imports **41** names from
  it, up from 22 — which is why `crew_config.py` reaches them as
  `crew_state.GUARD_NAMES` and why a grep of `crew_state.py` alone for
  `def guard_policy_rank` finds nothing.

- `read_knowledge(root, cfg)` (`plugin/crew/hooks/scripts/crew_freshness.py:375-459`)
  lists every file directly under `.crew/codemap/`. A file counts as a
  subsystem if its name ends in `.md` **and** is not in `_NOT_SUBSYSTEMS`
  (`plugin/crew/hooks/scripts/crew_freshness.py:69` —
  `frozenset({"INDEX.md", "UPGRADE.md", "MIGRATION.md"})`). This codemap
  contributes **10** subsystems out of 12 `.md` files at this anchor (unchanged;
  `INDEX.md` and `UPGRADE.md` are the two present exclusions, `MIGRATION.md`
  does not exist here).

- Each counted file is checked against `_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_freshness.py:64-66`):
  `^anchor:\s*(?:\S*@)?([0-9a-f]{7,40})\s*$`. The `\s*$` is still load-bearing:
  anything after the sha on that line stops the match and the file reads as
  having no anchor at all.

- **The three-state anchor logic (current / behind / unresolvable) lives
  entirely inside `read_knowledge`.** Read in order at
  `plugin/crew/hooks/scripts/crew_freshness.py:405-459`:

  | State | Test | What the reader does |
  |---|---|---|
  | current | `sha[:7] == head[:7]` (`:430`, truncating both sides — 8- and 40-char anchors compare exactly as 7-char ones do) | nothing |
  | unresolvable | no anchor at all (`:421-428`), OR the sha does not resolve via `git cat-file -e <sha>^{commit}` (`:437-439`) | re-derive: the per-path diff cannot run at all |
  | behind | anchor resolves, is not HEAD, **and** `_moved_since(root, sha, head, _cited_paths(root, body))` is not `False` (`:451-452`) | re-check: the per-path diff already ran as part of this test and said something moved |

  `behind` is gated on the fixpoint check, not on "resolves but is not HEAD" —
  the 0.19.34 fix (`1767790`). Folding an old-but-untouched map into "behind"
  wastes a re-check; the current code does not do that.

- `read_diagrams(root, cfg)`
  (`plugin/crew/hooks/scripts/crew_freshness.py:473-541`) mirrors the same
  structure for `docs/diagrams/*.mmd`, using `_DIAGRAM_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_freshness.py:128-132`) and its own
  `_moved_since` gate at `:522`. A diagram with no anchor header counts as
  `behind` outright (`:509-511`) — unknown provenance resolves to stale, the
  same direction `_read_graph` takes for a graph with no `built_at_commit`.

- **`TRIGGERS` is now 15 entries, not 12**
  (`plugin/crew/hooks/scripts/crew_state.py:959-996`), a flat tuple of trigger
  names in presentation order: `incidentActive` (`:963`), `incidentUnclosed`
  (`:964`), `upgradeNeeded` (`:965`), `handoffPending` (`:966`),
  `endpointUnscanned` (`:974`), `graphStale` (`:975`), `verifyMarkerStale`
  (`:980`), `verifyRulesUnpriced` (`:981`), `verifyReachUndeclared` (`:982`),
  `knowledgeUnverifiable` (`:987`), `knowledgeBehind` (`:988`), `diagramsStale`
  (`:992`), `diagramsMissing` (`:993`), `reviewNotWorking` (`:994`),
  `ticketsTooLarge` (`:995`). `knowledgeUnverifiable` still sits above
  `knowledgeBehind` — a map that cannot be verified outranks one that merely
  needs re-checking — and both diagram findings still rank below both codemap
  findings. The three verify triggers now sit between `graphStale` and the
  codemap pair.

- `evaluate_triggers(state)`
  (`plugin/crew/hooks/scripts/crew_state.py:2972-3046`) sets a **fifteen**-entry
  `fired` dict at `:2996-3044`, not the sixteen the previous note recorded.
  **Correction to the previous note's characterisation, not just its numbers:**
  it said evaluation order "is the reverse of `TRIGGERS`' presentation order".
  It is not, and was not — comparing the two lists at this anchor, they are
  identical except that `knowledgeBehind` (`:3029`) and `knowledgeUnverifiable`
  (`:3030`) are transposed relative to `TRIGGERS` (`:987-988`). One transposed
  pair is not a reversal, and a reader who believed it would expect the last
  trigger to be evaluated first. `diagramsMissing` (`:3036-3040`) still fires
  only once `knowledge.subsystems` is truthy.

- `_DIAGRAM_ANCHORS_RE` and `_diagram_paths` — the machinery reading the
  hand-written `%% Anchors: <paths>` line out of a diagram so `_moved_since`
  has something to diff — are both in `crew_freshness.py` and used at
  `plugin/crew/hooks/scripts/crew_freshness.py:519`.

**`SCHEMA_CURRENT` is still 7** (`plugin/crew/hooks/scripts/crew_state.py:173`).
Schema 6 added the four guards, two production guards and
`github.mergeGate.{enabled,branch}`; schema 7 added `/crew:change`'s six
`change.*` keys. `crew_upgrade.py` is not under `plugin/crew/hooks/scripts/` —
it lives at `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py` — noted
because a reader chasing `SCHEMA_CURRENT`'s consumer would otherwise look in
the wrong directory. **`guards.roleWrites` arrived without a schema bump**; see
the config section.

## The endpoint ledger and `endpointUnscanned`

`plugin/crew/hooks/scripts/crew_endpoints.py` is **979** lines, up one from 978
— a single-line insertion near the top shifted every citation below it by
exactly +1, and all of them were re-taken rather than offset.

`.crew/endpoints.json` (`_ENDPOINTS_PATH_PARTS` at
`plugin/crew/hooks/scripts/crew_endpoints.py:34`) holds only **declared**
records, written only by `declare_endpoint`
(`plugin/crew/hooks/scripts/crew_endpoints.py:255`) — the only writer of the
file, and the entry point named in `plugin/crew/agents/pm.md` and
`plugin/crew/commands/work.md:63-64` for turning a researched candidate into a
fact. The file does not exist in this checkout; `.gitignore` un-ignores it
(`!.crew/endpoints.json`), so a repo that creates one would have it tracked,
but nothing in this checkout has yet — `git ls-files .crew/` returns the twelve
`.crew/codemap/*.md` files plus `.crew/verify.json`, and nothing else.

Ids are minted from a sequence counter (`nextSeq`), sanitised against a
conservative allowlist at mint and read time
(`plugin/crew/hooks/scripts/crew_endpoints.py:51-79`), and the file is written
via temp-file-then-`os.replace`
(`plugin/crew/hooks/scripts/crew_endpoints.py:131-183`, the `os.replace` at
`:173`) under an advisory lock
(`plugin/crew/hooks/scripts/crew_endpoints.py:205-253`). That temp-then-replace
shape is the one construction CLAUDE.md names as immune to the
`open(p, "w")`-truncates-before-the-payload trap.

**Candidates are computed, never persisted.** `infer_endpoints`
(`plugin/crew/hooks/scripts/crew_endpoints.py:411`) scans `git diff HEAD` fresh
on every call; `read_endpoints` (`:915`) merges declared records on disk with
that fresh output. An inferred hit's id is a deterministic sha1 of
`(signal, location)`, stable across repeated reads of the same diff state but
NOT across an edit that shifts the cited line.

The scan-artifact path is decided once per record (`scan_artifact_path`, `:668`):
single repo -> `docs/security-scans/<id>.md`; mono-repo (`_is_monorepo`, `:581`)
-> `<package-dir>/docs/security-scans/<id>.md`. `_artifact_confirms_scan`
(`:830`) requires three things, in order: non-empty, carries `_SCAN_MARKER_RE`'s
marker (`:792`), and — when the record is specific enough (`_endpoint_needle`,
`:795`) — mentions it.

`endpointUnscanned` fires when a record needs an artifact it does not have,
evaluated in `evaluate_triggers` at
`plugin/crew/hooks/scripts/crew_state.py:3008`, gated on `gizmoduck_installed`
(`plugin/crew/hooks/scripts/crew_endpoints.py:499`) — checked across four
config scopes, project outranking global and each scope's own `.local.json`
outranking its `.json`, deferred to rather than read as `false` on any parse
failure or missing key.

`pm_brief.FINDINGS` (`plugin/crew/hooks/scripts/pm_brief.py:103` — unchanged
position) interpolates `"{endpointSummary}"` / `"{endpointAction}"`
(`:143-144`, also unchanged), composed in `_endpoint_fields`
(`plugin/crew/hooks/scripts/pm_brief.py:389-470`, moved from `:321-398`). The
"candidates are NOT confirmed endpoints until researched" literal is at `:443`
(moved from `:375`). The declared/candidate split is keyed on `status`, not
`source` (`:421-422`, moved from `:353-354`), for the same reason as before: a
record whose two fields disagree still renders as a candidate, and the
docstring at `:400` names that bug shape explicitly.

Gizmoduck's own `plugin/gizmoduck/commands/report.md:29,37` and
`plugin/gizmoduck/commands/scan.md:27` (both byte-identical to `ea8a014`) still
document the seam: a scan targeting a declared endpoint lands at that record's
computed path and freezes it there afterward.

## Config, and what a machine-global file may supply

**DERIVED at this anchor by importing `crew_config` and executing both default
functions.** The full reference is `plugin/crew/CONFIG.md` (**1809** lines, up
from 1327); this section records only the shape and the one invariant that is
easy to break.

Two layers, unchanged in kind: `~/.claude/crew/config.json` is machine-global,
`.crew/config.json` is per-repo and wins where both speak, `schema` is exempt
from global inheritance.

| | Leaves | Source |
|---|---|---|
| `default_config()` | **103** | `plugin/crew/hooks/scripts/crew_config.py:239-346` |
| `default_global_config()` | **60** | `plugin/crew/hooks/scripts/crew_config.py:349-506` |
| repo-only | **43** | the difference |

**These are not new figures, and the previous note's 102 / 59 / 43 was a
miscount rather than drift.** Extracting `crew_config.py` at `ea8a014` into a
temp directory and executing its `default_config()` / `default_global_config()`
gives the identical leaf *sets* as HEAD — nothing added, nothing removed, 103
and 60 at both ends. `plugin/crew/CONFIG.md:130-131` stated 60 / 103 / 43 the
whole time. Re-measure rather than trusting this table:
`leaf_paths` is at `plugin/crew/hooks/scripts/crew_config.py:509-522` and the
measurement is three lines.

**A consequence worth stating: `guards.roleWrites` is a new leaf that did not
move the totals**, because it replaced nothing and the sets match at both
anchors — meaning it was already present at `ea8a014` and the previous note
simply never counted it. `upgradeNeeded` is still `schema < SCHEMA_CURRENT` and
compares no key sets, so a key arriving without a schema bump produces no
migration prompt. **That is the gap, and it is not hypothetical here.**

**Consent is not capability.** `context.autoClear.unsafeFocus` is still the one
`autoClear` leaf held out of the global layer by `AUTOCLEAR_CONSENT_KEYS` —
**which now lives at `plugin/crew/hooks/scripts/crew_state.py:682`, not in
`crew_config.py`**; `plugin/crew/hooks/scripts/crew_config.py:473` consumes it
as `crew_state.AUTOCLEAR_CONSENT_KEYS`. The other six `autoClear` leaves
(`command`, `delaySeconds`, `enabled`, `method`, `minHandoffLines`,
`windowTitle`) are globally settable — re-derived by differencing the two leaf
sets at this anchor, not assumed.

**The invariant, enforced in two places that must agree:** what the global file
may *write* is what the global layer may *supply*. Reading is pruned by
`filter_global` (`plugin/crew/hooks/scripts/crew_config.py:620-640`); writing is
refused by `plan_global_write`
(`plugin/crew/hooks/scripts/crew_config.py:2296-2380`) against the same object.

### The ratchet registry — ten keys, not nine

`_widens(dotted, before, after)`
(`plugin/crew/hooks/scripts/crew_config.py:2078-2098`) ranks `after` against
`before` and reports a widening only when the rank rises, driven by a lookup
table `_RATCHETED`. **That table is built in four steps, and reading only its
literal is how the count gets missed:** the literal at
`plugin/crew/hooks/scripts/crew_config.py:2214-2225` holds just two keys, and
three `_RATCHETED.update(...)` calls plus one direct assignment add the rest.
Executing the module gives **ten**:

| Key(s) | Rank fn | Added at |
|---|---|---|
| `pm.authority` | `authority_rank` — `plugin/crew/hooks/scripts/crew_state.py:1340-1349`, the one exception that really does live outside `crew_guards.py` | `plugin/crew/hooks/scripts/crew_config.py:2215-2219` |
| `install.policy` | `install_policy_rank` (`plugin/crew/hooks/scripts/crew_guards.py:309-317`) | `plugin/crew/hooks/scripts/crew_config.py:2220-2224` |
| `guards.terraformApply`, `guards.forcePush`, `guards.adminMerge`, `guards.mergeGate` | `guard_policy_rank` (`plugin/crew/hooks/scripts/crew_guards.py:335-344`), names from `GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:104`) | `plugin/crew/hooks/scripts/crew_config.py:2229-2236` |
| `guards.prodDatabase`, `guards.prodServer` | `prod_level_rank` (`plugin/crew/hooks/scripts/crew_guards.py:364-371`), names from `PROD_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:125`); vocabulary is `PROD_LEVELS` (`:122`) `none`/`read`/`full`, deliberately different words for a different meaning | `plugin/crew/hooks/scripts/crew_config.py:2242-2249` |
| `guards.roleWrites` | `role_writes_rank` (`plugin/crew/hooks/scripts/crew_guards.py:400-411`), vocabulary `block`/`report`/`off` — **new since the previous anchor** | `plugin/crew/hooks/scripts/crew_config.py:2253-2260` |
| `change.requireForProduction` | `require_change_rank` (`plugin/crew/hooks/scripts/crew_guards.py:253-261`), keyed on bool; `False` is the widening direction and the one value only the global file may set (`_CHANGE_WIDENING_NOTES`, `plugin/crew/hooks/scripts/crew_config.py:2272-2287`) | `plugin/crew/hooks/scripts/crew_config.py:2289-2293` |

**JUDGEMENT — why the guard tables are generated rather than written out.** The
comments at `plugin/crew/hooks/scripts/crew_config.py:2226-2228` say it plainly:
the notes table is built by comprehension over `crew_state.GUARD_NAMES` so a
fifth guard added there cannot arrive here with no widening note, which would be
a `KeyError` on the one line that exists to warn about a grant. The same
reasoning produced `RATCHETED_KEYS`
(`plugin/crew/hooks/scripts/crew_guards.py:446-450`) iterating `ALL_GUARD_NAMES`.

### `pm.authority`

Three values, `normalise_authority`
(`plugin/crew/hooks/scripts/crew_state.py:1326-1337`) and `authority_rank`
(`:1340-1349`). Default is `report-only` (`AUTHORITY_DEFAULT`, `:1025`).

| Value | The PM may |
|---|---|
| `report-only` | read and report; dispatch nothing |
| `act` | dispatch roles and do the work, putting open decisions to the user |
| `autonomous` | everything `act` does, and settle its own open decisions |

`AUTONOMOUS_STOPS` (`plugin/crew/hooks/scripts/crew_state.py:1038-1045`) still
enumerates the same four things `autonomous` may never do unasked, re-read at
this anchor: `offboard-role`, `delete-map`, `rewrite-metrics`,
`git-destruction`.

## The `.crew/` ignore policy

The policy, read directly from `.gitignore`: `.crew/*` is ignored (`:292`), and
exactly three paths are un-ignored — `!.crew/codemap/` (`:301`),
`!.crew/endpoints.json` (`:308`), `!.crew/verify.json` (`:330`). The stanza's
authority comment begins at `:279`. Everything else under `.crew/` —
`config.json`, `STATUS.md`, `metrics.md`, `transcripts/`, `state.json` — is
machine-local. All four of those line numbers are byte-identical to `ea8a014`.

`check_crew_ignore_policy` (`scripts/check-marketplace.py:929-1091`, moved from
`:780-944`) is the enforcer: it treats `.gitignore` as the authority and checks
that every file carrying the opt-in marker states the identical set. **Six files
carry it**, per the function's own docstring at `:948-958`: `.gitignore` and
`plugin/crew/skills/crew-setup/SKILL.md` (required), plus `CLAUDE.md`,
`plugin/crew/README.md`, `plugin/crew/skills/crew-setup/phases.md` and
`plugin/crew/skills/crew-verification/SKILL.md`. `.crew/codemap/` — this
directory — is **explicitly out of scope** (`:952-955`): it is a derived map
with its own anchor-staleness mechanism, and a generated artefact failing the
gate would be fixed by regenerating it, not by hand-editing it. So this note
restates the policy in prose without carrying the marker, and the policy can
still drift here without the checker noticing — the tradeoff the check's own
author documented, not an oversight this note is flagging as new.

**A trap this note sits inside.** `git grep -l` for the marker string returns
ten files, not six: the four extra are the two `POLICY_SELF` entries
(`scripts/check-marketplace.py`, `scripts/_test/crew-ignore-policy.py`,
declared at `scripts/check-marketplace.py:737`), `CHANGELOG.md`, and **this
file**, which matches only because the paragraph above names the marker in
prose. A future reader counting marker files with grep will get ten and
conclude the docstring is stale. It is not; grep is the wrong instrument.

A regression suite exists at `scripts/_test/crew-ignore-policy.py` (confirmed
present, not read this pass).

## Citation freshness

Every `path:line` in this file was resolved at this anchor by one of two
mechanisms:

1. **Re-derived** — located by AST walk or direct read at `84976536`. This is
   what every citation into `crew_state.py`, `crew_config.py`, `crew_guards.py`,
   `crew_endpoints.py`, `pm_brief.py`, `_common.sh`, `run-tests.sh`,
   `hooks.json`, `check-marketplace.py` and the count sites got.
2. **Closed by the per-path check** — the file is byte-identical between
   `ea8a014` and this anchor. This is what `crew_freshness.py`, `.gitignore`'s
   four cited lines, `plugin/crew/commands/work.md` and the two gizmoduck
   command files got.

**The byte-identical-line sweep was run this pass**, and is the source of the
35 / 61 split in the header: each unique `(path, range)` citation the previous
version carried was extracted, and the cited lines compared between
`git show ea8a014:<path>` and `git show HEAD:<path>`. 35 came back identical
and 61 differed. That sweep is what caught the Hooks section being wrong at its
own anchor, which no amount of re-reading HEAD would have found — at HEAD the
entry count is 20 again.

**Re-measure rather than trusting any figure here.** The invariant this
directory holds, per `.crew/codemap/INDEX.md:55-58`, is that every `path:line` resolves to an
existing file with the cited line in range; every citation in this file was
checked against that at this anchor. No total is stated, for the reason
`.crew/codemap/INDEX.md:60-66` gives.

**What is not claimed:** that the behaviour behind these lines was re-tested.
No hook was run and no test suite was executed as part of this pass.

## Why this note has no Landmines section

**Asked and answered twice before, so recorded here rather than left to be
re-asked.** `.crew/codemap/INDEX.md:137-139` assigns landmines to `CLAUDE.md` explicitly:
"These files do not restate `CLAUDE.md`. That file holds the judgement calls
and the landmines already earned by past incidents; this directory holds the
map." A `## Landmines` heading here would either duplicate `CLAUDE.md` — two
documents that disagree by the next commit — or invent incidents that have not
happened. Where a landmine and a mapped fact coincide (the `open(p, "w")`
truncation trap and `crew_endpoints.py`'s temp-then-replace write; the
bash-versus-PowerShell hook registration rule and `hooks.json`'s even counts),
this note cites `CLAUDE.md`'s rule at the place in the map it applies, rather
than restating it in a section of its own.

## What this file does not cover

Agent role definitions and command bodies are not traced here. `crew:reference`
and `crew:roster` are the tools for the finer grain. Config is covered here
only in outline — `plugin/crew/CONFIG.md` is the full reference and the
authority where the two disagree. The other subsystem notes in `.crew/codemap/`
cover their own areas; `INDEX.md` is the table of contents.

## Entry points

- `plugin/crew/hooks/scripts/crew_state.py:2891` - `worktree_root(cfg, repo_root)`, the one resolver for `worktree.root`.
- `plugin/crew/hooks/scripts/crew_state.py:2921` - `worktree_path(cfg, repo_root, branch)`, `<worktree_root>/<repo>-<branch>`, flattening every separator so a branch name cannot add a directory level.
- `plugin/crew/hooks/scripts/crew_state.py:3158` - `main`, carrying the `--worktree-path BRANCH` flag.
- `plugin/crew/hooks/scripts/crew_state.py:3049` - `collect`, the one function that assembles the whole state a SessionStart brief renders.
- `plugin/crew/hooks/scripts/crew_state.py:2972` - `evaluate_triggers`, the fifteen-entry `fired` dict.
- `plugin/crew/hooks/scripts/crew_state.py:530` - `read_verify_health`, the source of the three verify triggers.
- `plugin/crew/hooks/scripts/crew_config.py:715` - `resolve_config`, and `:1476` `explain_config`. They share `null_shadows` (`:525`) and `without_null_shadows` (`:571`) so the run and the report cannot disagree about a repo `null` shadowing a global value.
- `plugin/crew/hooks/scripts/crew_config.py:620` - `filter_global`, the read-side gate; `:2296` `plan_global_write`, the write-side gate.
- `plugin/crew/hooks/scripts/crew_freshness.py:375` - `read_knowledge`; `:473` `read_diagrams` - both called from `crew_state.collect`.
- `plugin/crew/hooks/scripts/role_write_guard.py:732` — `main()`; `:587` `classify`, the decision function.
- `plugin/crew/hooks/scripts/crew_change.py:278` — module entry point (`main()`)
- `plugin/crew/hooks/scripts/crew_incident.py:416` — module entry point (`main()`)
- `plugin/crew/hooks/scripts/crew_platform.py:481` — module entry point (`main()`)
- `plugin/crew/hooks/scripts/hook_once.py:94` — module entry point (`main()`)
- `plugin/crew/hooks/scripts/pm_brief.py:718` — module entry point (`main()`), moved from `:657`
- `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:1018` — cited as a `main()` entry point by the previous anchor; at this anchor that line is inside a string literal. The module's real entry point was **not re-located** this pass.
- `scripts/_test/crew-ignore-policy.py:560` — module entry point (`main()`)
- `scripts/_test/version-drift.py:296` — module entry point (`main()`)
- `scripts/check-marketplace.py:1006` — cited as `main()` by the previous anchor; at this anchor that line is inside `check_crew_ignore_policy` (`:929-1091`). `main` was **not re-located** this pass.
- `plugin/crew/hooks/scripts/_test/validate-prompts.py:283` and `plugin/crew/hooks/scripts/pm_pulse.py:247` — both cited as `main()` by the previous anchor; both lines now hold other code. **Not re-located** this pass.

## Owns data

- `.crew/codemap/` - this directory. Read by `read_knowledge`
  (`plugin/crew/hooks/scripts/crew_freshness.py:375-459`); ten subsystem files
  at this anchor, out of twelve `.md` files.
- `worktree.root` in `.crew/config.json` and `~/.claude/crew/config.json`,
  defaulting from `crew_state.WORKTREE_DEFAULTS`
  (`plugin/crew/hooks/scripts/crew_state.py:1138-1140`).
- `crew_state.ROLE_TIERS` (`plugin/crew/hooks/scripts/crew_state.py:1205-1222`) -
  13 tiered roles.
- `crew_state.SPECIALIST_ROLES`
  (`plugin/crew/hooks/scripts/crew_state.py:1253-1294`) - 40 domain specialists.
- `crew_state.AUTONOMOUS_STOPS`
  (`plugin/crew/hooks/scripts/crew_state.py:1038-1045`) - the four things
  `autonomous` may not do unasked.
- `crew_state.AUTOCLEAR_CONSENT_KEYS`
  (`plugin/crew/hooks/scripts/crew_state.py:682`) - the one key held out of the
  global layer. **Moved here from `crew_config.py` since the previous anchor.**
- `crew_guards.GUARD_DEFAULTS` (`plugin/crew/hooks/scripts/crew_guards.py:172-175`) -
  seven guards in three vocabularies, `roleWrites` defaulting to `off`.
- `crew_config._RATCHETED` (built at
  `plugin/crew/hooks/scripts/crew_config.py:2214-2293`) - the ten keys whose
  widening is marked, printed on the dry run and printed again on the write.
- `.crew/verify.json` - tracked; the un-ignore list itself lives in
  `.gitignore:279-330`, restated (not authoritatively) by the six marker-carrying
  files named above.

## Calls out to

- `crew_config.resolve_config`, from `crew_state.main`'s
  `--archive-stale-handoff` branch, imported INSIDE the function to keep the
  import direction one-way. **Not** from the `--worktree-path` branch, which
  calls plain `load_config(root)` — the previous note's correction on this point
  still holds in substance, but **both of its line citations
  (`plugin/crew/hooks/scripts/crew_state.py:2767-2772` and `:2780-2782`) now land on unrelated code** and
  the branches were **not re-located** this pass.
- `git cat-file -e <sha>^{commit}` from `read_knowledge`
  (`plugin/crew/hooks/scripts/crew_freshness.py:437`), to tell a resolvable
  anchor from one this repository does not contain. `git_out` returns `None` on
  any failure, so a missing git lands as "cannot tell" rather than raising out
  of a SessionStart hook.
- `crew_state._repo_digest` (`plugin/crew/hooks/scripts/crew_state.py:1156-1182`)
  hashes `normcase(realpath(repo_root))` with `blake2b`, degrading to `abspath`
  when `realpath` raises.
- `_SEPARATORS` (`plugin/crew/hooks/scripts/crew_state.py:1151-1153`) is derived
  from `os.sep`/`os.altsep` rather than written as a regex character class.
- `plugin/crew/tests/sabotage.py` — via the `verification-harness` subsystem.
  **Not run, and must not be run against the live tree**: it edits real source
  in place.

## Unverified at this anchor

- No hook was executed and no pytest run was made part of this pass; every claim
  about *behaviour* is read from source or from executing the config and guard
  modules in isolation, not observed running under Claude Code.
- **Six previous-anchor entry-point citations were found landing on unrelated
  code and were deliberately NOT re-located**, rather than quietly dropped or
  guessed: `plugin/crew/hooks/scripts/_test/validate-prompts.py:283`, `plugin/crew/hooks/scripts/pm_pulse.py:247`, `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:1018`,
  `scripts/check-marketplace.py:1006`, and both `crew_state.py` worktree/archive branch
  ranges. They are flagged in place above. Re-locating them is the cheapest
  available next pass.
- `plugin/crew/tests/test_role_write_guard.py` was confirmed present and its
  length measured; it was **not read**, and the sabotage test CLAUDE.md requires
  of a blocking hook ("reintroduce a bug it should catch and confirm the suite
  goes red") was **not performed**.
- `verify_fingerprint.py`, `verify_price.py` and `verify_record.py` were
  located and sized but **not read**; the three verify triggers above are
  derived from their consumer in `crew_state.py`, not from the producers.
- `role_write_guard.py`'s `classify` was located but its decision table
  (`_DENY_ROLES`, `_UNRESTRICTED_ROLES`, `_PM_ALLOWED_PATTERNS` at `:229`,
  `:247`, `:298`) was **not traced**.
- `crew_upgrade.py`'s schema-6 and schema-7 migration paths were not read; only
  the fact that `SCHEMA_CURRENT` is 7 was re-derived.
- Agent and command bodies were counted, not read.
- `scripts/_test/crew-ignore-policy.py` was confirmed to exist and was not read;
  the six-marker-file list is taken from `check_crew_ignore_policy`'s docstring,
  not from the test file.
- **The three narrow passes preceding this one left everything outside the
  skill-count table unread for eight days.** This pass re-derived all of it, but
  no claim is made that the intervening `verified:` dates were meaningful for
  any section other than that table.
