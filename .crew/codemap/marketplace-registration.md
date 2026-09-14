anchor: useful-claude-add-ons@975480b7
verified: 2026-09-14
Narrow pass, not a full re-verification: only the agent/command/skill-count
table below (the one this note itself flagged as a live inversion) was
re-read against its cited files at this anchor, because `f12003e2` (#166,
"fix three stale self-describing counts") landed since `0a9d8937` and fixed
part of that inversion. Everything else in this note — including the
"Re-anchor provenance" section immediately below, which describes the pass
that produced `0a9d8937` — carries forward from `0a9d8937` unread.

# Marketplace and registration

**DERIVED.** The root `.claude-plugin/marketplace.json` is the **only** marketplace
file in this repo. Stated as policy at `CLAUDE.md:5` and `CLAUDE.md:38`, and
enforced at `scripts/check-marketplace.py:95-120` (moved from `:94-119`), where
`check_registration` walks every on-disk entry directory and fails if
`<dir>/.claude-plugin/marketplace.json` exists — *"makes this directory look like
a second marketplace - the repo root's is the only one"* (`:118-120`).

## Re-anchor provenance - 0a9d8937 -> 975480b7, 2026-09-14

Narrow pass, not a full per-path check: this pass did not diff the eight
repo paths this note cites against `975480b7`. It re-read only the
agent/command/skill-count table (below, in "This section has now inverted
four times...") because `f12003e2` (#166) is known to have touched
`marketplace.json` and `plugin/PLUGINS.md` since `0a9d8937`, and confirmed by
targeted diff that `README.md` and `INSTALLATION.md` were not touched. The
rest of this note — including the `a573ca24 -> 0a9d8937` section immediately
below — is retained as history from the previous pass and was not re-checked.

## Re-anchor provenance - a573ca24 -> 0a9d8937, 2026-09-14

The per-path check ran over the eight repo paths this note cites. **Six
changed**: `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`,
`plugin/README.md`, `scripts/install-prerequisites.sh`,
`scripts/install-prerequisites.ps1` and `scripts/check-marketplace.py`. **Two did
not**: `_verify/smoke.sh` and `skills/README.md`.

**`scripts/check-marketplace.py` is the file that flipped from unchanged to
changed at this anchor, and it changed a great deal** (+584/-21 lines across
three commits: `3374e8e0` #139 added `check_self_claims`, `357338cb` #144 fixed
the version-drift walk across a merge, `0a9d8937` #161 added
`check_crew_ignore_policy`). Every function range this note cites into it was
re-read directly from the file, not offset from the previous anchor - the
insertions are not evenly spaced through the file, so an offset would have been
wrong in different directions in different sections.

`_verify/smoke.sh` and `skills/README.md` did not change, so citations into them
are closed by that result and were not re-read.

Re-measured at this anchor, because their files did change:

- `.claude-plugin/marketplace.json` in full (via `json.load`, counted by `source`
  prefix), plus the `crew` entry's `description` and every plugin's `version`.
- Both install scripts' catalog array boundaries, by matching the array openings
  rather than by eye - `github` was inserted as a new skill, mid-array, in both.
- `plugin/PLUGINS.md` section headings and `plugin/README.md` catalog rows.
- The agent/command/skill counts, by `os.listdir` over the three directories, and
  a repo-wide sweep for every place that states one.
- Every function in `scripts/check-marketplace.py`'s `main()`, by reading the
  function definitions directly rather than trusting the previous pass's line
  numbers.

The gate was run read-only at this anchor. `python3 scripts/check-marketplace.py`
was not re-executed in this pass (the previous pass's 66s figure and the
`.crew/verify.json`-recorded 8s post-cache figure are both left as history
below, neither re-measured here); `marketplace: 35 skills, 5 plugins` is
re-derived directly from `.claude-plugin/marketplace.json` by the same rule the
gate uses (`source` prefix), not from running the gate.

**Not re-verified at this anchor:** the bodies of `check_skill_manifests`
(`:123-150`) and `check_plugin_manifests` (`:151-166`) — listed from `main()`
but not traced line by line here; see `verification-harness.md`, which traces
`check_versions` and `main()` itself. `check_registration` (`:95-120`) *was*
re-read, because this note quotes its failure string directly (see "Marketplace
and registration" above). The historical `git diff --stat` ranges in the worked
example below were not re-run; they carry their own older anchor.
`.crew/verify.json` **was** read in full at this anchor - it is tracked and
present in this checkout - and the section below is rewritten from that read
rather than left as unverifiable.

## The registration web

**DERIVED.** A skill (source path starting `./skills/`) and a plugin (source path
starting `./plugin/`) are registered in different, non-overlapping sets of
places. Confirmed by reading each file.

| | Skill | Plugin |
|---|---|---|
| Marketplace entry | `.claude-plugin/marketplace.json` (one flat `plugins` array — the file does not distinguish skills from plugins by field, only by `source` prefix) | same file |
| Catalog doc | `skills/README.md` — table header at `skills/README.md:87`, first entry row at `skills/README.md:89` | `plugin/PLUGINS.md` (a `## \`name\`` section) **and** `plugin/README.md` (a table row) |
| Root README | linked via `README.md` under `skills/{name}` | linked via `README.md` under `plugin/{name}` |
| `.sh` install script | `SKILL_KEYS`/`SKILL_NAME`/`SKILL_SPEC` arrays, `scripts/install-prerequisites.sh:807` (`SKILL_KEYS=(`) through `scripts/install-prerequisites.sh:887` (`unset _i` after `SKILL_STATE` at `:885`) | `PLUGIN_KEYS`/`PLUGIN_NAME`/`PLUGIN_SPEC`, `scripts/install-prerequisites.sh:894` (`PLUGIN_KEYS=(`) through `scripts/install-prerequisites.sh:917` |
| `.ps1` install script | `$script:SkillCatalog`, `scripts/install-prerequisites.ps1:808` | `$script:PluginCatalog`, `scripts/install-prerequisites.ps1:855` |
| Own manifest version | none (skills have no `plugin.json`) | `plugin/<name>/.claude-plugin/plugin.json`, bumped in lockstep with the marketplace entry |

**Every `.sh` line in this row moved at this anchor**, because `github` was
inserted as a new skill mid-array in `SKILL_KEYS`/`SKILL_NAME` - a +2-line shift
that carries through the rest of the file below it (see `install-scripts.md`,
which validated the offset at five separate constructs before applying it). The
skill block's *start* (`:807`) did not move; everything from `SKILL_NAME` on did.
`TEAM_KEYS` and `COMMUNITY_KEYS` moved with it — see "Two catalogs the
marketplace does not govern".

### Counts: measure, do not read them here

**DERIVED, and stated as a method rather than a number that rots.** The split is
by `source` prefix and nothing else, so the invariant is: *every entry's `source`
starts with `./skills/` or `./plugin/`, and the two sets partition the array.*
`scripts/check-marketplace.py:959-960` derives `plugins` as `len(entries) -
skills` — moved from `:396-397` at the previous anchor now that `main()` sits
much further down the file (see "Two version-check paths" below) — so an entry
whose `source` matched neither prefix would be silently
counted as a plugin, and no check catches that. DERIVED at this anchor by
counting both prefixes independently: the "neither" set is empty, so the
partition holds today and the latent hole is latent.

Re-measure with:

```
python -c "import json;p=json.load(open('.claude-plugin/marketplace.json'))['plugins'];\
print(len(p),sum(s.startswith('./skills/') for s in (e['source'] for e in p)))"
```

or just run the gate, which prints `marketplace: N skills, M plugins`.

At this anchor that is **40 entries — 35 skills, 5 plugins**. One skill,
`github`, was added since the previous anchor (`0.19.46`'s range; the skill
itself ships branch-protection export/restore, unrelated to the ignore-policy
work in the same release). The plugin set did not change at this anchor - it is
still `crew`, `gizmoduck`, `localgpu`, `obsidian-vault` and `rule-of-two`, five
total, with `rule-of-two` still the most recent addition (registered at
`9fde7d82`, #128). Plugin versions at this anchor: `crew` 0.19.50, `gizmoduck`
0.5.2, `localgpu` 0.1.18, `obsidian-vault` 0.3.8, `rule-of-two` 0.1.2.

### A worked example: adding an agent is not a registration

**DERIVED (historical, verified at anchor `b56d41f`; `crew` is now 0.19.50).**
crew 0.16.7 added three agents (`node-developer`, `power-automate-specialist`,
`sharepoint-developer`) inside `plugin/crew/agents/`. `git diff --stat
2b0972d..b56d41f -- .claude-plugin/marketplace.json` showed exactly one entry
touched, 2 lines changed: the existing `crew` row's `description` and `version`.
No new `plugins` array entry was added; `plugin/PLUGINS.md` and
`plugin/README.md` gained prose rather than new catalog rows; both install
scripts were byte-identical across that range.

So the registration web did **not** change shape — an agent is not a unit this
table's rows describe at all. It ships as a file inside a plugin's own directory
(`plugin/crew/agents/*.md`), the same way a command or a bundled skill does; the
plugin's *one* marketplace entry, *one* `PLUGINS.md` section, *one*
`plugin/README.md` row and *one* `plugin.json` cover every agent, command and
skill it bundles, at whatever count they currently sum to. Adding an agent is a
content change to an existing plugin — bump its version, per `CLAUDE.md`'s
stop-and-ask rule, and update the prose that states the count — not a new
registration. Correspondingly, neither `PLUGIN_KEYS`/`PLUGIN_SPEC` nor
`SKILL_KEYS`/`SKILL_SPEC` in either install script needs a new entry: those
arrays register installable *plugins* and *skills* (top-level marketplace units),
not the agents/commands/skills bundled inside one.

**`rule-of-two` is the contrasting case, and it landed in this range.** A new
plugin *is* a unit every row of that table describes, and `9fde7d82` touched all
of them at once: a `plugins` array entry, a `## \`rule-of-two\`` section at
`plugin/PLUGINS.md:753`, a `plugin/README.md:418` row, a root `README.md` link,
`PLUGIN_KEYS`/`PLUGIN_NAME`/`PLUGIN_SPEC` in the `.sh` and `$script:PluginCatalog`
in the `.ps1`, and its own `plugin.json`. That is what a registration looks like,
against the agent case above, and it is why the install URLs had to be re-pinned
afterwards (`91a7aab1`) while crew 0.19.20's agent-count fix needed no re-pin.

**The asymmetry stated plainly, because it is a trap:** skills register in
`skills/README.md`; plugins register in `plugin/PLUGINS.md` **and**
`plugin/README.md`. There is no single doc both kinds share except the root
`README.md`. Registering a skill's entry in `plugin/PLUGINS.md`, or a plugin's
entry only in `plugin/PLUGINS.md` without the `plugin/README.md` row, both pass a
naive read of "did I add a doc row" while failing the actual check.

## What the checker reads — and the two things it does not

**DERIVED; re-read at this anchor because `check-marketplace.py` changed, though
this function's body did not.** `check_docs`
(`scripts/check-marketplace.py:264-278`) reads exactly three files —
`skills/README.md`, `plugin/README.md`, and root `README.md` — testing each entry
for the literal substring `` [`name`](link) ``. It **never opens
`plugin/PLUGINS.md`**: the string `PLUGINS.md` appears nowhere in
`scripts/check-marketplace.py` or under `_verify/`. So a plugin whose
`PLUGINS.md` section was never written, or drifted out of sync with reality,
fails no automated check.

### Descriptive text is unchecked — and the drift it allowed has been repaired

**DERIVED.** `check_catalogs` (`scripts/check-marketplace.py:167-192`) compares
*keys* — `SKILL_KEYS`, `PLUGIN_KEYS`, `SkillCatalog`, `PluginCatalog` — against
the marketplace name lists, for equality including order. It never looks at
`SKILL_NAME` / `PLUGIN_NAME` or the `Name` property, which hold the human-readable
menu text. `check_docs` likewise tests only for the presence of a link substring,
not the surrounding cell. **Nothing in the gate reads descriptive prose anywhere.**

On disk at this anchor: `plugin/crew/agents/` holds **54** `.md` files,
`plugin/crew/commands/` holds **26** (was 24), `plugin/crew/skills/` holds **18**
directories, every one of them shipping a `SKILL.md` (was 17 - `crew-cloud` was
added since the previous anchor).

**This section has now inverted four times across five anchors. The third
inversion (recorded below as "at 0a9d8937") is partly repaired as of this
anchor, not fully — `f12003e2` (#166, "fix three stale self-describing
counts") fixed the skill count in `marketplace.json` and `plugin/PLUGINS.md`,
but left `README.md:166` and `INSTALLATION.md:251` (both root-level, distinct
from `plugin/PLUGINS.md` and `plugin/README.md`) still saying 17.** The
command count remains correct everywhere checked (24 -> 26, following
`5d2e2950` #124's earlier agent-count fix and a later, unlogged commands
bump).

| Location | Two anchors ago said | At 0a9d8937 | At 975480b7 |
|---|---|---|---|
| `.claude-plugin/marketplace.json:223` | `29 context-isolated agents` | `54 ... 26 slash commands, 17 bundled skills` — skills still wrong (18 on disk) | `54 ... 26 slash commands, 18 bundled skills` — **fixed by `f12003e2`** |
| `plugin/PLUGINS.md:17` | `29 agents, 24 commands, 17 skills` | `54 agents, 26 commands, 17 skills, 20 hook entries` — same defect | `54 agents, 26 commands, 18 skills, 20 hook entries` — **fixed by `f12003e2`** |
| `plugin/PLUGINS.md:153` | `Agents — 14, tiered plus the manager` | `### Agents — one per agents/*.md` — no number, `:157` names `crew_state.SPECIALIST_ROLES` as the register | not re-read this pass; out of scope for this correction |
| `README.md:166` (root, was `:165`) | `50 subagents, ...` | `54 subagents, 26 slash commands, 17 bundled skills` | `54 subagents, 26 slash commands, 17 bundled skills` — **unchanged; `f12003e2` did not touch this file** (`git diff --name-only 0a9d8937..975480b7 -- README.md` returns nothing) |
| `INSTALLATION.md:251` | not previously tracked in this table | not previously tracked in this table | `54 subagents, 26 slash commands, 17 bundled skills, 20 hook entries` — same untouched defect as `README.md:166`, now added to this table |
| `scripts/install-prerequisites.sh:902` (was `:900`) | `11 agents, 21 commands` | `54 agents, 26 commands` — correct, does not mention skills | not re-read this pass; nothing about it changed shape at the previous anchor |
| `scripts/install-prerequisites.ps1:856` (was `:855`) | `11 agents, 21 commands` | `54 agents, 26 commands` — correct, same as above | not re-read this pass |

`5d2e2950` ("crew 0.19.20: correct the agent count everywhere it is claimed",
#124) repaired the *agent* count at the previous inversion; the *commands*
figure moved in two later, ordinary command-adding commits rather than a
dedicated fix — `68c1f93a` (0.19.30) took it 24→25 and `53294344` (0.19.31)
took it 25→26 (`git log -S'25 commands' -- plugin/PLUGINS.md README.md` and
the same for `'26 commands'`), each incidentally correct because each new
`/crew:*` command's registration touched this line along with everything else.
`f12003e2` fixed the *skills* figure in two of the (now) four prose locations
that state it — `marketplace.json` and `plugin/PLUGINS.md` — plus
`plugin/README.md`, a fifth location this table has never carried a row for
because it duplicates `plugin/PLUGINS.md`'s figure rather than adding a
distinct one. It left `README.md` (root) and `INSTALLATION.md` (root)
untouched, and neither carries a `<!-- claim: -->` marker (only
`plugin/PLUGINS.md:14`'s version line does), so `check_self_claims` does not
catch the two that remain wrong — the exact unchecked-prose gap this section
already documents, now demonstrated a fourth time, half-fixed instead of left
whole. **This is a finding for the report, not a fix made in this note:**
bringing `README.md:166` and `INSTALLATION.md:251` to 18 is a source-file
edit; `crew.md` and this note only record the state of that prose.

**The two structural observations survive both inversions, and they are the part
worth keeping:**

- `plugin/README.md:370` and its twin `README.md:591` (was `:590`, +1) sit under
  the heading `### crew 0.15.1` and read "Three new agents and a skill, taking
  crew to 14 agents and 17 bundled skills." That is a **changelog entry**:
  correct as history, and never a statement about the current build. Counting it
  as a place that states the count correctly, as a pass two anchors back did, was
  a misclassification rather than drift — and it is still not fixable by editing
  a number.
- `README.md:774` (was `:773`, +1) is a PowerShell code fence about
  `vault-automation/` (re-confirmed at this anchor: `:774` is the literal
  ` ```powershell `). The citation that once pointed at a count points at nothing
  to do with counts, and a "wrong number" reading of it would be looking for a
  number that is not there.

JUDGEMENT, and it is stronger now than when it was first written: **nothing
re-checks a claim that something is correct.** This section has been wrong in
both directions inside a week — first asserting four places were right after they
had gone wrong, then asserting none was right after they had been fixed — and
each time the gate was green throughout. A finding that records which places are
RIGHT acquires an expiry date the moment it is written, and this repo enforces
none. The correction rots faster than the thing it corrects, because a wrong
number is trivially detectable and a wrong *assessment* is not.

**The related TODO entry is CLOSED and its citation here has moved again.** It
is now `TODO.md:634-761` (was `:558-681`; `TODO.md` grew by 349 lines in this
range from unrelated entries above it), headed *"Crew's agent count is wrong in
seven places and right in none — CLOSED 2026-09-12"*, and it records the fix,
the measurement (54 = 13 `ROLE_TIERS` + 40 `SPECIALIST_ROLES` + `pm`, both set
differences against the filenames empty) and — at `TODO.md:644-652` (was
`:568-575`) — the answer no earlier pass had: **where the `29` came from.**
`plugin/PLUGINS.md`'s agent table has exactly 29 data rows (13 tiered + 15
specialists + `pm`), written when there were 15 specialists and never grown;
`marketplace.json`'s "29 ... (13 tiered, 15 domain specialists)" is that table
transcribed. So correcting only the `29` would have shipped a sentence asserting
`13 + 15 + 1 = 54`. This CLOSED entry covers the *agent* count only, filed before
the *commands* figure (24 -> 26) drifted again, or the *skills* figure (17 ->
18) drifted and was then half-fixed by `f12003e2` — it is not evidence any of
those is tracked anywhere. TODO.md itself is outside this note's scope and was
not re-read this pass to confirm whether it carries a skills-count entry now.

`check_menu_parity` (`scripts/check-marketplace.py:195-231`) and
`check_group_parity` (`:234-261`) compare the same way: menu **keys** in order,
plus the default-ticked booleans (`MENU_DEFAULT`, `scripts/install-prerequisites.sh:728`,
against each `Default = $true/$false`). No descriptive string is compared
anywhere in either. So when the two install-script lines were *consistently*
wrong, the matched-pair rule passed cleanly — the pair agreed, it was simply
agreeing on a stale sentence. That is still true; the pair now agrees on a
correct one, and the gate cannot tell those two states apart.

**JUDGEMENT:** treat "the gate is green" as a statement about structure only —
which directories are registered, which keys line up in which order, which links
exist, whether a version was bumped. Any number written in prose is unverified by
construction, and re-measuring it from the filesystem is the only way to know.

## Two version-check paths, not one

**DERIVED. `_verify/smoke.sh` is unchanged since the previous anchor, so its own
citations are current by the per-path check. `scripts/check-marketplace.py`
changed substantially (+584/-21 lines, three commits - see the re-anchor
provenance above), and `main()`'s check count moved as a direct result: this
section's headline finding at the previous anchor ("nine, not eight") is now
itself out of date - it is eleven.**

- `scripts/check-marketplace.py`'s own `main()`
  (`scripts/check-marketplace.py:938-968`) calls **eleven** check functions in
  order at `:947-957` — the same nine as before, plus two added since the
  previous anchor: `check_self_claims` (added by `3374e8e0` #139) and
  `check_crew_ignore_policy` (added by `0a9d8937` #161, the release this pass is
  anchored to). `check_versions` is still among them, at `:955`. Running
  `python3 scripts/check-marketplace.py` — the exact command `CLAUDE.md` names as
  the gate — executes all eleven.
- `_verify/smoke.sh` was **not** updated when either function was added. Its
  `run_marketplace_check()` (`_verify/smoke.sh:54-80`) still re-imports
  `check-marketplace.py` as a Python module and exposes the same **six named
  groups** (`registration`, `skills`, `plugins`, `catalogs`, `menus`, `hooks`,
  `_verify/smoke.sh:65-72`) it always did, calling the same **eight** functions.
  Eight of eleven is a different fraction than eight of nine, and the header
  comment's claim - *"Same calls main() makes, in the same order, minus
  check_versions"* (`_verify/smoke.sh:64`) - is now false in a way it was not at
  the previous anchor: `_verify/smoke.sh` misses **three** functions
  `main()` runs, not one. `check_self_claims` and `check_crew_ignore_policy` are
  both absent from every one of the six groups, so `bash _verify/smoke.sh`
  passing says nothing about either - not "self-claims" numeric drift, and not
  the `.crew/` ignore-policy invariant `check_crew_ignore_policy` exists to
  guard. Two groups call two functions each: `catalogs` runs `check_catalogs`
  *and* `check_docs` (`:69`), `menus` runs `check_menu_parity` *and*
  `check_group_parity` (`:70`).
- **The header's cost figures (both stale as of the previous anchor) were not
  re-measured this pass** - `_verify/smoke.sh` did not change, so its
  `58 revisions` / `~160s` claim is carried forward as still-stale rather than
  re-timed. The previous anchor's direct measurement (135 revisions, 66s for the
  full run) stands as the last real number; `.crew/verify.json:36`, now readable,
  independently records a THIRD figure for the same command - "8s (it was 95s
  until the history walk's blob reads were cached on 2026-09-13; re-time it
  rather than trusting either figure)" - which neither this note nor `verify.json`
  itself treats as settled. Three different timings for the same command across
  three sources, none re-measured against each other, is itself the finding:
  whatever the true cost is, nobody has pinned it down twice the same way.
  Whether smoke.sh should still skip `check_versions` is a question for the
  verification-harness note, which owns that file; recorded here because this is
  where the claim was being repeated.
- `_verify/smoke.sh`'s check 10 (`version_agreement_check`, body at
  `_verify/smoke.sh:261-355`, registered at `:356-357`) is **a different check
  entirely**, not a stand-in for the one it skips. It confirms that
  `pyproject.toml`, `plugin.json`, `marketplace.json`, and every hardcoded
  `VERSION`/`__version__` literal in a plugin's Python source all name the *same*
  version number right now. `check_versions`
  (`scripts/check-marketplace.py:369-402`, moved from `:298-328` now that
  `main()` sits at `:938` instead of `:377`) instead asks whether a plugin's
  `source/` directory changed *since* the commit where its current version was
  first declared — it walks `git log` over `marketplace.json` (via
  `version_set_at`, now `:323-331`) and runs `git diff --quiet <bump> HEAD --
  <source>` per entry. Also new since the previous anchor: `check_versions` now
  walks the history two ways, first-parent and full (`:379`, `:385`), because
  `357338cb` (#144) found the single-parent walk goes blind across a merge -
  `bump_candidates` (`:334-368`, new) tries candidates from both. That is a
  temporal / git-history question the point-in-time consistency check cannot
  answer and does not try to.

**JUDGEMENT:** there genuinely are two version-related gates that do not
substitute for one another. The correction is narrower than it sounds: it is
*`_verify/smoke.sh`'s internal fast path* that skips `check_versions`, not
`check-marketplace.py` as a program. A change that only runs `bash
_verify/smoke.sh` and treats a clean run as proof `check_versions` also passed is
trusting a check that never ran there. Anyone citing "check-marketplace.py never
checks version drift" should say "smoke.sh's fast subset doesn't" instead — the
full script does, on every direct invocation.

**The practical consequence, seen twice in this repo:** because the rule is
history-based rather than content-based, a pre-commit run of the gate cannot tell
you that a version bump is *missing*. `check_versions` compares the commit that
last set a version against the commit that last touched the plugin directory, and
neither exists yet while the change is uncommitted. CI is the first place it can
fail, and it has.

**Noted while reading, not this note's subject:** `_verify/smoke.sh:3` says
`# 9 checks`, and the file has ten lines beginning `check "` (`:82`, `:84`,
`:86`, `:88`, `:90`, `:92`, `:124`, `:127`, `:239`, `:356`). Re-confirmed at this
anchor. The verification-harness note owns that file; recorded here only so the
next reader does not derive a count from the header comment — which, together
with the stale `58 revisions` and `~160s` on line 12, makes three wrong numbers
in that one header block.

## The gate's own invocation is now inside git's reach

**Retitled at this anchor - the previous heading is now wrong and the body
already said why.** `.crew/verify.json` was gitignored via the `.crew/*` stanza
until 2026-09-14, when `!.crew/verify.json` joined the named un-ignore list
alongside `!.crew/codemap/` and `!.crew/endpoints.json`. It is tracked and
**present in this checkout** - read in full at this anchor, not carried forward
as UNVERIFIABLE.

**DERIVED, from an actual read.** `.crew/verify.json` is 176 lines and carries
**21** `rules` (counted via `json.load`, not `grep -c '"paths"'`) - not 15, and
not the 13 an even earlier codemap pass recorded; both older figures describe a
file-shape this one has moved past. Its own `_note` array
(`.crew/verify.json:4-29`) states, at `:7-8`, that the file "is TRACKED as of
2026-09-14" and travels with the repo - the file documents its own tracking
status inline. Its own `anchor` field (`.crew/verify.json:3`) reads
`"repo@5238be3d"`, which is **22 commits behind** this note's anchor as of
the previous pass (`0a9d8937`) - `git merge-base --is-ancestor 5238be3d HEAD` confirms it is an
ancestor, so the file is stale relative to the code it maps, not wrong about a
divergent branch. Concretely: it predates both `check_self_claims` and
`check_crew_ignore_policy` being added to `check-marketplace.py`'s `main()`, so
none of its `why` fields mention either — but the gate invocation itself is
`python3 scripts/check-marketplace.py` wholesale (`.crew/verify.json:35` and
again at `:53`), so both new checks still run wherever those two rules fire,
regardless of whether verify.json's author knew about them.

**A real coverage gap, found by reading the file rather than assuming it:** the
`scripts/**` rule (`.crew/verify.json:52-60`) matches
`scripts/_test/crew-ignore-policy.py` by path, but its `run` list
(`check-marketplace.py`, `self-claims.py`, `version-drift.py`,
`sync-updates.py --check`, `menu-groups.sh`, `check-powershell.sh`,
`bash -n install-prerequisites.sh`) does **not** include running
`crew-ignore-policy.py` itself. A local edit to that 34-case sabotage suite
matches a rule, and the rule runs seven other things, but not the suite that
was just edited. `.github/workflows/marketplace.yml:41-42` does run it in CI, so
the gap is local-only - but `.crew/verify.json`'s own `_note`
(`.crew/verify.json:9-11`) says this map "only makes the LOCAL Stop gate
selective" and that CI is "the gate everyone else gets", which is exactly the
qualifier that makes this gap survive review: the local gate goes green on a
change CI would still catch, and nothing here claims otherwise.

**The "only rule carrying an `agents` key" claim from an earlier pass is wrong,
and it is wrong about which rule.** An earlier version of `verification-harness.md`
(this note's neighbour) said the hooks rule required a `security` review agent.
Reading the current file: exactly one rule carries an `"agents"` key
(`.crew/verify.json:130`), and it is the `**/*.ps1`/`**/*.psm1` rule, naming
`powershell-security-hardening` — not `security`, and not the hooks rule. The
hooks-related rules (`.crew/verify.json:62-70` for the gate scripts, `:72-77`
for `guard.sh`) carry no `agents` key at all in the current file. Flagged here
because this note found it while reading `.crew/verify.json` for its own
purposes; `verification-harness.md` owns the correction.

`default` is `["bash _verify/smoke.sh"]` and `unmapped` is `"fail"`
(`.crew/verify.json:174-175`) - a change matching no rule's `paths` fails the
gate rather than passing silently, which is the file's own stated purpose for
`unmapped` (`_note`, `:12-20`, which also concedes the catch-all `plugin/**` /
`skills/**` rule means `unmapped` rarely fires - "0 of 790 tracked files are
unmapped" is not proof a new check would be noticed). `default` is a narrower
promise, stated separately (`_note`, `:21-26`): it is reached only when the
matched rules contribute no commands at all, not a general floor under every
turn.

## Two catalogs the marketplace does not govern

**DERIVED.** `check_group_parity` (`scripts/check-marketplace.py:234-261`)
enumerates **four** sub-picker groups, not two: `own-skills`
(`SKILL_KEYS`/`SkillCatalog`), `repo-plugins` (`PLUGIN_KEYS`/`PluginCatalog`),
and also `team` (`TEAM_KEYS`/`TeamCatalog`, `scripts/install-prerequisites.sh:923`
and `scripts/install-prerequisites.ps1:870`) and `community`
(`COMMUNITY_KEYS`/`CommunityCatalog`, `scripts/install-prerequisites.sh:939` and
`scripts/install-prerequisites.ps1:880`). All four install-script citations moved
by one to two lines at this anchor too, from the `github` skill insertion (see
`install-scripts.md`'s uniform-offset note); the `check_group_parity` range moved
by one line, because `check-marketplace.py` gained a line somewhere above it even
though this function's own body did not change.

The last two hold plugins from *other people's* marketplaces. They are checked
for `.sh`/`.ps1` agreement, and for being non-empty — but `check_catalogs`
(`:181-186`) cross-references only `SKILL_KEYS`, `PLUGIN_KEYS`, `SkillCatalog`
and `PluginCatalog` against `marketplace.json`. Nothing ties `TEAM_KEYS` or
`COMMUNITY_KEYS` to anything in this repo, because there is nothing here to tie
them to. **JUDGEMENT:** so "the two install scripts are a matched pair" is a
weaker guarantee for those two groups than for the repo's own — matched to each
other, matched to no source of truth.

## What was not re-verified

Listed under "Re-anchor provenance" above rather than repeated here: two check
function bodies (`check_skill_manifests`, `check_plugin_manifests` — not traced
line by line at this anchor; `check_registration` *was* re-read), and the
worked example's historical git ranges. `.crew/verify.json` **was** re-verified
this pass, for the first time — it is no longer in the "not re-verified" list.

## Entry points

- `.claude-plugin/marketplace.json` — **35 skills and 5 plugins**, 40 entries. `github` was added this release; `rule-of-two` (added `9fde7d82`, #128) is still the newest plugin; `crew` is 0.19.50.
- `scripts/check-marketplace.py:167` — `check_catalogs`, which requires `SKILL_KEYS` (.sh) and `$script:SkillCatalog` (.ps1) to match marketplace.json in the same ORDER, not merely as sets.
- `scripts/check-marketplace.py:234` — `check_group_parity`, which hardcodes exactly four sub-picker groups. Reusing `COMMUNITY` for VoltAgent rather than adding a fifth group is why this file needed no change.
- `scripts/check-marketplace.py:323` — `version_set_at`, the git walk that makes the version rule history-based, and therefore un-runnable against an uncommitted change. Moved from `:280`; as of `357338cb` (#144) it is one of two history walks `check_versions` tries (`bump_candidates`, `:334`, is the other), added to fix the walk going blind across a merge.
- `scripts/check-marketplace.py:727` — `check_crew_ignore_policy`, new at this anchor (`0a9d8937` #161): asserts the `.crew/` ignore un-ignore list is one set stated consistently across `.gitignore` and five other marker-carrying files. `.crew/codemap/` is explicitly out of scope for it (`:750-753`) — a generated map that fails this gate would be fixed by regenerating it, not editing it.
- `.crew/verify.json:35` and `:53` — both invocations of `python3 scripts/check-marketplace.py` from the now-tracked verification map; see "The gate's own invocation" above.

## Owns data

- `skills/power-automate-api/.gitignore` — ignores `scripts/pa-snapshots/` wholesale. `pa.py` NO LONGER writes there: since the SNAPSHOT_DIR fix it writes live-tenant flow dumps to `~/.pa-api-cache/snapshots`, outside any checkout. The rule is kept as a net for checkouts that ran an earlier version, not as a description of current behaviour — one such dump was committed and pushed to this public repo before a review caught it.

## Calls out to

- Nothing at runtime. Registration is a set of files that must agree; `_verify/smoke.sh` runs the checker as its first gate.
