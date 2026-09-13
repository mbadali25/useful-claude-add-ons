anchor: useful-claude-add-ons@a573ca24
verified: 2026-09-13
re-verified, not re-derived: every claim below was re-read against the files it
cites at this anchor, and its citation re-pointed where the code had moved. One
section - the agent/command counts - was re-measured and has inverted for the
second consecutive anchor, in the opposite direction, and is corrected in place
rather than carried forward.

# Marketplace and registration

**DERIVED.** The root `.claude-plugin/marketplace.json` is the **only** marketplace
file in this repo. Stated as policy at `CLAUDE.md:5` and `CLAUDE.md:38`, and
enforced at `scripts/check-marketplace.py:94-119`, where `check_registration`
walks every on-disk entry directory and fails if
`<dir>/.claude-plugin/marketplace.json` exists — *"makes this directory look like
a second marketplace - the repo root's is the only one"*.

## Re-anchor provenance - 7b0d8f3a -> a573ca24, 2026-09-13

The per-path check ran over the eight repo paths this note cites. **Five
changed**: `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`,
`plugin/README.md`, `scripts/install-prerequisites.sh` and
`scripts/install-prerequisites.ps1`. **Three did not**:
`scripts/check-marketplace.py`, `_verify/smoke.sh` and `skills/README.md`.

**The three unchanged files are closed by that result, not re-read.** Every
`scripts/check-marketplace.py` and `_verify/smoke.sh` citation in this note —
which is most of them, including all nine function ranges and the smoke helper's
six groups — is current because the file is byte-identical to the anchor those
ranges were taken at. The AST walk was re-run anyway, because it costs nothing
and the note quotes ranges rather than bare line numbers: it agrees with every
one of them.

Re-measured at this anchor, because their files did change:

- `.claude-plugin/marketplace.json` in full (via `json.load`, counted by `source`
  prefix), plus the `crew` entry's `description` and every plugin's `version`.
- Both install scripts' catalog array boundaries, by matching the array openings
  rather than by eye.
- `plugin/PLUGINS.md` section headings and `plugin/README.md` catalog rows.
- The agent/command/skill counts, by `os.listdir` over the three directories, and
  a repo-wide sweep for every place that states one.

The gate was run read-only at this anchor. `python scripts/check-marketplace.py`
printed, in full:

```
marketplace: 34 skills, 5 plugins
all checks passed
```

exit 0, in **66 seconds** — and that number is a correction, see "Two
version-check paths" below.

**The byte-identical-line sweep, measured rather than asserted.** Diffing this
file against `git show a573ca24:.crew/codemap/marketplace-registration.md`: of
**397** lines, **197** survived byte-identical and **18** of those carry a
citation, 22 citations in all. Sixteen point into the three files that did not
change, so the per-path result closes them. The remaining six point into files
that *did* change — `CLAUDE.md:5` and `:38`,
`scripts/install-prerequisites.ps1:808` and `:854`, `plugin/README.md:370` and
`README.md:590` — and each was resolved independently against HEAD after this
file was written: **0 unresolvable, 0 blank, 0 past EOF.** The two
`install-prerequisites.ps1` citations are the interesting ones: that file *did*
change in this range and those two lines did not move, which is exactly the case
the per-path check cannot decide and the sweep can.

**Not re-verified at this anchor:** the bodies of `check_skill_manifests`
(`scripts/check-marketplace.py:122-147`), `check_plugin_manifests` (`:150-163`)
and `check_hook_commands` (`:331-374`) — they are listed from `main()` but not
read, the same gap the previous pass left, and the file has not changed since,
so it is the *same* gap rather than a new one. The historical `git diff --stat`
ranges in the worked example below were not re-run; they carry their own older
anchor. `.crew/verify.json` could not be read at all — see the section on it.

## The registration web

**DERIVED.** A skill (source path starting `./skills/`) and a plugin (source path
starting `./plugin/`) are registered in different, non-overlapping sets of
places. Confirmed by reading each file.

| | Skill | Plugin |
|---|---|---|
| Marketplace entry | `.claude-plugin/marketplace.json` (one flat `plugins` array — the file does not distinguish skills from plugins by field, only by `source` prefix) | same file |
| Catalog doc | `skills/README.md` — table header at `skills/README.md:87`, first entry row at `skills/README.md:89` | `plugin/PLUGINS.md` (a `## \`name\`` section) **and** `plugin/README.md` (a table row) |
| Root README | linked via `README.md` under `skills/{name}` | linked via `README.md` under `plugin/{name}` |
| `.sh` install script | `SKILL_KEYS`/`SKILL_NAME`/`SKILL_SPEC` arrays, `scripts/install-prerequisites.sh:807` (`SKILL_KEYS=(`) through `scripts/install-prerequisites.sh:885` (`unset _i` after `SKILL_STATE` at `:883`) | `PLUGIN_KEYS`/`PLUGIN_NAME`/`PLUGIN_SPEC`, `scripts/install-prerequisites.sh:892` (`PLUGIN_KEYS=(`) through `scripts/install-prerequisites.sh:915` |
| `.ps1` install script | `$script:SkillCatalog`, `scripts/install-prerequisites.ps1:808` | `$script:PluginCatalog`, `scripts/install-prerequisites.ps1:854` |
| Own manifest version | none (skills have no `plugin.json`) | `plugin/<name>/.claude-plugin/plugin.json`, bumped in lockstep with the marketplace entry |

The `.sh` plugin block ran to `:912` at the previous anchor and now ends at
`:915`; the skill block's boundaries did not move. `TEAM_KEYS` and
`COMMUNITY_KEYS` moved with it — see "Two catalogs the marketplace does not
govern".

### Counts: measure, do not read them here

**DERIVED, and stated as a method rather than a number that rots.** The split is
by `source` prefix and nothing else, so the invariant is: *every entry's `source`
starts with `./skills/` or `./plugin/`, and the two sets partition the array.*
`scripts/check-marketplace.py:396-397` derives `plugins` as `len(entries) -
skills` — so an entry whose `source` matched neither prefix would be silently
counted as a plugin, and no check catches that. DERIVED at this anchor by
counting both prefixes independently: the "neither" set is empty, so the
partition holds today and the latent hole is latent.

Re-measure with:

```
python -c "import json;p=json.load(open('.claude-plugin/marketplace.json'))['plugins'];\
print(len(p),sum(s.startswith('./skills/') for s in (e['source'] for e in p)))"
```

or just run the gate, which prints `marketplace: N skills, M plugins`.

At this anchor that is **39 entries — 34 skills, 5 plugins**. Nine skills and one
plugin have been added since `7b0d8f3a`. The new plugin is `rule-of-two`
(registered at `9fde7d82`, #128), joining `crew`, `gizmoduck`, `localgpu` and
`obsidian-vault` — the first change to the *plugin* set this note has recorded
across four anchors, and the reason the previous version's "4 plugins" appears
in three places here as a corrected figure rather than a re-pointed one. Plugin
versions at this anchor: `crew` 0.19.23, `gizmoduck` 0.5.1, `localgpu` 0.1.18,
`obsidian-vault` 0.3.6, `rule-of-two` 0.1.2.

### A worked example: adding an agent is not a registration

**DERIVED (historical, verified at anchor `b56d41f`; `crew` is now 0.19.23).**
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

**DERIVED; the file is unchanged since the previous anchor, so these ranges are
current by the per-path check and were re-confirmed by AST.** `check_docs`
(`scripts/check-marketplace.py:263-277`) reads exactly three files —
`skills/README.md`, `plugin/README.md`, and root `README.md` — testing each entry
for the literal substring `` [`name`](link) ``. It **never opens
`plugin/PLUGINS.md`**: the string `PLUGINS.md` appears nowhere in
`scripts/check-marketplace.py` or under `_verify/`. So a plugin whose
`PLUGINS.md` section was never written, or drifted out of sync with reality,
fails no automated check.

### Descriptive text is unchecked — and the drift it allowed has been repaired

**DERIVED.** `check_catalogs` (`scripts/check-marketplace.py:166-191`) compares
*keys* — `SKILL_KEYS`, `PLUGIN_KEYS`, `SkillCatalog`, `PluginCatalog` — against
the marketplace name lists, for equality including order. It never looks at
`SKILL_NAME` / `PLUGIN_NAME` or the `Name` property, which hold the human-readable
menu text. `check_docs` likewise tests only for the presence of a link substring,
not the surrounding cell. **Nothing in the gate reads descriptive prose anywhere.**

On disk at this anchor: `plugin/crew/agents/` holds **54** `.md` files,
`plugin/crew/commands/` holds **24**, `plugin/crew/skills/` holds **17**.

**This section has now inverted twice, in opposite directions, at consecutive
anchors — and the second inversion is the more dangerous one to leave standing.**
Two anchors ago it named four places as stating the count correctly. The previous
pass re-measured, found all four wrong, and wrote: *"No place in the repo now
states the agent count correctly."* At this anchor that sentence is false, and
every row of the six-row table under it is false:

| Location | Previous version said | At this anchor |
|---|---|---|
| `.claude-plugin/marketplace.json:217` | `29 context-isolated agents` | `54 context-isolated agents (13 tiered, 40 domain specialists, and the standing manager), 24 slash commands, 17 bundled skills` |
| `plugin/PLUGINS.md:17` | `29 agents, 24 commands, 17 skills` | `54 agents, 24 commands, 17 skills, 20 hook entries (10 scripts × .sh/.ps1) across 5 events` |
| `plugin/PLUGINS.md:153` | `Agents — 14, tiered plus the manager` | `### Agents — one per agents/*.md` — **no number at all**, with `:157` saying the table below is abridged and naming `crew_state.SPECIALIST_ROLES` as the register |
| `README.md:165` | `50 subagents, ...` | `54 subagents, 24 slash commands, 17 bundled skills, 20 hook entries across 5 events` |
| `scripts/install-prerequisites.sh:899` | `11 agents, 21 commands` | `:900` — `54 agents, 24 commands` |
| `scripts/install-prerequisites.ps1:855` | `11 agents, 21 commands` | `:855` — `54 agents, 24 commands` |

`5d2e2950` ("crew 0.19.20: correct the agent count everywhere it is claimed",
#124) is what repaired them. DERIVED by sweeping every tracked
`.md`/`.json`/`.sh`/`.ps1` for a number adjacent to "agent"/"subagent" on a line
mentioning crew: every live, present-tense claim now reads 54, and the thirteen
non-54 hits are each correct where they sit — other plugins' counts sharing a
line, the `### crew 0.15.1` release note, `TODO.md` quoting the strings #124
replaced, and dated session records.

**The two structural observations survive both inversions, and they are the part
worth keeping:**

- `plugin/README.md:370` and its twin `README.md:590` sit under the heading
  `### crew 0.15.1` and read "Three new agents and a skill, taking crew to 14
  agents and 17 bundled skills." That is a **changelog entry**: correct as
  history, and never a statement about the current build. Counting it as a place
  that states the count correctly, as a pass two anchors back did, was a
  misclassification rather than drift — and it is still not fixable by editing a
  number.
- `README.md:773` is a PowerShell code fence about `vault-automation/`
  (re-confirmed at this anchor: `:773` is the literal ` ```powershell `). The
  citation that once pointed at a count points at nothing to do with counts, and
  a "wrong number" reading of it would be looking for a number that is not there.

JUDGEMENT, and it is stronger now than when it was first written: **nothing
re-checks a claim that something is correct.** This section has been wrong in
both directions inside a week — first asserting four places were right after they
had gone wrong, then asserting none was right after they had been fixed — and
each time the gate was green throughout. A finding that records which places are
RIGHT acquires an expiry date the moment it is written, and this repo enforces
none. The correction rots faster than the thing it corrects, because a wrong
number is trivially detectable and a wrong *assessment* is not.

**The related TODO entry is CLOSED and its citation here has moved.** It is now
`TODO.md:558-681`, headed *"Crew's agent count is wrong in seven places and right
in none — CLOSED 2026-09-12"*, and it records the fix, the measurement (54 = 13
`ROLE_TIERS` + 40 `SPECIALIST_ROLES` + `pm`, both set differences against the
filenames empty) and — at `TODO.md:568-575` — the answer no earlier pass had:
**where the `29` came from.** `plugin/PLUGINS.md`'s agent table has exactly 29
data rows (13 tiered + 15 specialists + `pm`), written when there were 15
specialists and never grown; `marketplace.json`'s "29 ... (13 tiered, 15 domain
specialists)" is that table transcribed. So correcting only the `29` would have
shipped a sentence asserting `13 + 15 + 1 = 54`. The previous version of this
note cited that entry as `TODO.md:558-600` with the heading *"wrong in three
places, right in four"*, which is the pre-close text.

`check_menu_parity` (`scripts/check-marketplace.py:194-230`) and
`check_group_parity` (`:233-260`) compare the same way: menu **keys** in order,
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

**DERIVED. `scripts/check-marketplace.py` and `_verify/smoke.sh` are both
unchanged since the previous anchor, so every citation here is current by the
per-path check; the timing figure is what was re-measured.**

- `scripts/check-marketplace.py`'s own `main()`
  (`scripts/check-marketplace.py:377-405`) calls **nine** check functions in
  order at `:386-394`, **including** `check_versions` at `:394`. Running
  `python scripts/check-marketplace.py` — the exact command `CLAUDE.md` names as
  the gate — executes `check_versions`.
- The exclusion is real, but it lives one layer down, inside `_verify/smoke.sh`'s
  own helper. `run_marketplace_check()` (`_verify/smoke.sh:54-80`) re-imports
  `check-marketplace.py` as a Python module and exposes **six named groups**
  (`registration`, `skills`, `plugins`, `catalogs`, `menus`, `hooks`,
  `_verify/smoke.sh:65-72`) that between them call **eight of the nine** check
  functions — every one except `check_versions`. Two groups call two functions
  each: `catalogs` runs `check_catalogs` *and* `check_docs` (`:69`), `menus` runs
  `check_menu_parity` *and* `check_group_parity` (`:70`). Its own comment says
  why, verbatim: *"Same calls main() makes, in the same order, minus
  check_versions (slow: see header)"* (`_verify/smoke.sh:64`).
- **Corrected at this anchor: the header's cost figures are both stale, and the
  direction is counter-intuitive.** `_verify/smoke.sh:10-15` says the drift walk
  *"reads 58 revisions of marketplace.json and runs a git diff per entry, which
  costs ~160s on its own"*. Measured here: `git log --oneline --
  .claude-plugin/marketplace.json` returns **135** revisions, more than twice the
  stated 58, and the full `check-marketplace.py` completed in **66 seconds** —
  where the previous pass recorded it failing to finish inside a 120s timeout.
  More history, less time. This note does not claim to know why (a warm object
  cache and `version_set_at` short-circuiting per entry are both plausible and
  neither was measured), and that is the point: **the deferral is justified by a
  cost nobody has re-measured, and one direct measurement now contradicts it.**
  Whether smoke.sh should still skip `check_versions` is a question for the
  verification-harness note, which owns that file; recorded here because this is
  where the claim was being repeated.
- `_verify/smoke.sh`'s check 10 (`version_agreement_check`, body at
  `_verify/smoke.sh:261-355`, registered at `:356-357`) is **a different check
  entirely**, not a stand-in for the one it skips. It confirms that
  `pyproject.toml`, `plugin.json`, `marketplace.json`, and every hardcoded
  `VERSION`/`__version__` literal in a plugin's Python source all name the *same*
  version number right now. `check_versions`
  (`scripts/check-marketplace.py:298-328`) instead asks whether a plugin's
  `source/` directory changed *since* the commit where its current version was
  first declared — it walks `git log` over `marketplace.json` (via
  `version_set_at`, `:280-295`) and runs `git diff --quiet <bump> HEAD --
  <source>` per entry. That is a temporal / git-history question the
  point-in-time consistency check cannot answer and does not try to.

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

## The gate's own invocation lives outside git's reach

**DERIVED.** `.crew/verify.json` — which `CLAUDE.md` names as "the mechanism" for
per-path verify commands, and which invokes this gate as
`python scripts/check-marketplace.py` — is **gitignored** via `.gitignore:282`
(`.crew/*`), with `!.crew/codemap/` at `:291` and `!.crew/endpoints.json` at
`:298` re-admitting two paths beside it and nothing else.

**UNVERIFIABLE HERE, and stated as its own value rather than carried forward as
though it had been checked:** the file is absent from this checkout. The previous
version cited `.crew/verify.json:11` for the gate invocation and recorded 15
`rules` entries. **Neither could be re-read at this anchor.** They are not
contradicted — they are unmeasured, which is a different thing, and a reader who
needs either must run the re-measure command below rather than trusting this
line. Crew 0.19.21 made exactly this absence a reported outcome in `/crew:review`
step 0b rather than a silent skip, for the same reason.

Two consequences for anyone re-anchoring a note that cites it:

- `git diff --name-only <anchor>..HEAD -- .crew/verify.json` can **never** list
  it, whatever changed. Empty output there means "untracked", not "current" — the
  opposite of what the empty-output convention means for every tracked path.
- Nothing in the repo can surface drift in it. A codemap elsewhere once recorded
  13 `rules` where another recorded 15, and no check anywhere could have caught
  the difference.

**JUDGEMENT:** so the registration gate's *content* is checkable and version-
controlled, while the contract that decides *when it runs* is neither. Re-measure
from the working tree — `python -c "import json;
print(len(json.load(open('.crew/verify.json'))['rules']))"` — never from a diff,
and expect it to fail outright on a checkout like this one, which is the honest
outcome.

## Two catalogs the marketplace does not govern

**DERIVED.** `check_group_parity` (`scripts/check-marketplace.py:233-260`)
enumerates **four** sub-picker groups, not two: `own-skills`
(`SKILL_KEYS`/`SkillCatalog`), `repo-plugins` (`PLUGIN_KEYS`/`PluginCatalog`),
and also `team` (`TEAM_KEYS`/`TeamCatalog`, `scripts/install-prerequisites.sh:921`
and `scripts/install-prerequisites.ps1:869`) and `community`
(`COMMUNITY_KEYS`/`CommunityCatalog`, `scripts/install-prerequisites.sh:937` and
`scripts/install-prerequisites.ps1:879`). All four install-script citations moved
by one to three lines in this range; the `check_group_parity` range did not move
at all, because that file did not change.

The last two hold plugins from *other people's* marketplaces. They are checked
for `.sh`/`.ps1` agreement, and for being non-empty — but `check_catalogs`
(`:180-185`) cross-references only `SKILL_KEYS`, `PLUGIN_KEYS`, `SkillCatalog`
and `PluginCatalog` against `marketplace.json`. Nothing ties `TEAM_KEYS` or
`COMMUNITY_KEYS` to anything in this repo, because there is nothing here to tie
them to. **JUDGEMENT:** so "the two install scripts are a matched pair" is a
weaker guarantee for those two groups than for the repo's own — matched to each
other, matched to no source of truth.

## What was not re-verified

Listed under "Re-anchor provenance" above rather than repeated here: three check
function bodies (unchanged since the previous anchor, so this is the same gap
rather than a new one), the worked example's historical git ranges, and
`.crew/verify.json`, which is absent from this checkout.

## Entry points

- `.claude-plugin/marketplace.json` — **34 skills and 5 plugins**, 39 entries. `rule-of-two` was added this release (`9fde7d82`, #128); `crew` is 0.19.23.
- `scripts/check-marketplace.py:166` — `check_catalogs`, which requires `SKILL_KEYS` (.sh) and `$script:SkillCatalog` (.ps1) to match marketplace.json in the same ORDER, not merely as sets.
- `scripts/check-marketplace.py:233` — `check_group_parity`, which hardcodes exactly four sub-picker groups. Reusing `COMMUNITY` for VoltAgent rather than adding a fifth group is why this file needed no change.
- `scripts/check-marketplace.py:280` — `version_set_at`, the git walk that makes the version rule history-based, and therefore un-runnable against an uncommitted change.

## Owns data

- `skills/power-automate-api/.gitignore` — ignores `scripts/pa-snapshots/` wholesale. `pa.py` NO LONGER writes there: since the SNAPSHOT_DIR fix it writes live-tenant flow dumps to `~/.pa-api-cache/snapshots`, outside any checkout. The rule is kept as a net for checkouts that ran an earlier version, not as a description of current behaviour — one such dump was committed and pushed to this public repo before a review caught it.

## Calls out to

- Nothing at runtime. Registration is a set of files that must agree; `_verify/smoke.sh` runs the checker as its first gate.
