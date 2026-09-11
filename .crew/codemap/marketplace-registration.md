anchor: useful-claude-add-ons@d61342c3

# Marketplace and registration

**DERIVED.** The root `.claude-plugin/marketplace.json` is the **only** marketplace
file in this repo. Stated as policy at `CLAUDE.md:5` and `CLAUDE.md:38`, and
enforced at `scripts/check-marketplace.py:113-119`, where `check_registration`
walks every on-disk entry directory and fails if
`<dir>/.claude-plugin/marketplace.json` exists — *"makes this directory look like
a second marketplace - the repo root's is the only one"*.

## Re-anchor provenance - 3167721f -> 1f97e51c, 2026-09-06

The per-path check was done by the caller: five cited paths moved —
`.claude-plugin/marketplace.json`, `CLAUDE.md`, `README.md`, `plugin/PLUGINS.md`,
`plugin/README.md`.

Re-read at this anchor, in full, not merely re-resolved:

- `scripts/check-marketplace.py` — `main()`, and the bodies of
  `check_registration`, `check_catalogs`, `check_docs`, `check_versions`.
- `_verify/smoke.sh` — the header, `run_marketplace_check()`, the `check` roster,
  and `version_agreement_check`'s registration.
- `scripts/install-prerequisites.sh:803-872` and
  `scripts/install-prerequisites.ps1:805-848` — the skill and plugin catalogs.
- `.claude-plugin/marketplace.json` in full (via `json.load`, counted by `source`
  prefix), plus the `crew` entry's `description`.
- `skills/README.md` (table head), `plugin/README.md` (catalog rows),
  `plugin/PLUGINS.md` (section headings), `README.md` (menu-item 19 prose).

The gate was run read-only at this anchor. `python3 scripts/check-marketplace.py`
printed, in full:

```
marketplace: 25 skills, 4 plugins
all checks passed
```

exit 0 — after running for over 120s, consistent with the ~160s the
`check_versions` walk is documented to cost.

`git diff --stat 3167721f..HEAD -- scripts/check-marketplace.py _verify/smoke.sh
scripts/install-prerequisites.sh scripts/install-prerequisites.ps1
skills/README.md` produces **no output** — none of those five moved. That matters
for the corrections below: three of them were already false at the previous
anchor and survived a re-anchor that only re-resolved line numbers. The lines
resolved; the sentences built on them did not hold.

**Corrected at this anchor** (details in place): the count of check functions
`main()` runs (eight -> nine), what `_verify/smoke.sh`'s fast path actually
skips, seven `path:line` citations that were off by one to four lines, and two
new sections — on descriptive text, which no check reads, and on
`.crew/verify.json`, which git cannot diff.

Every function range in this note was re-derived by AST
(`ast.parse` over `scripts/check-marketplace.py`, printing `lineno`-`end_lineno`
per `FunctionDef`) rather than by eye, after two rounds of hand-counted ranges
each landed one to two lines off.

**Not re-verified at this anchor:** the bodies of `check_skill_manifests`
(`scripts/check-marketplace.py:122-147`), `check_plugin_manifests` (`:150-163`)
and `check_hook_commands` (`:331-374`) — they were listed from `main()` but not
read. The historical `git diff --stat` ranges in the worked example below were
not re-run; they carry their own older anchor.

## The registration web

**DERIVED.** A skill (source path starting `./skills/`) and a plugin (source path
starting `./plugin/`) are registered in different, non-overlapping sets of
places. Confirmed by reading each file.

| | Skill | Plugin |
|---|---|---|
| Marketplace entry | `.claude-plugin/marketplace.json` (one flat `plugins` array — the file does not distinguish skills from plugins by field, only by `source` prefix) | same file |
| Catalog doc | `skills/README.md` — table header at `skills/README.md:36`, first entry row at `:38` | `plugin/PLUGINS.md` (a `## \`name\`` section) **and** `plugin/README.md` (a table row) |
| Root README | linked via `README.md` under `skills/{name}` | linked via `README.md` under `plugin/{name}` |
| `.sh` install script | `SKILL_KEYS`/`SKILL_NAME`/`SKILL_SPEC` arrays, `scripts/install-prerequisites.sh:803` (`SKILL_KEYS=(`) through `:845` (`unset _i` after `SKILL_STATE`) | `PLUGIN_KEYS`/`PLUGIN_NAME`/`PLUGIN_SPEC`, `scripts/install-prerequisites.sh:852` (`PLUGIN_KEYS=(`) through `:872` |
| `.ps1` install script | `$script:SkillCatalog`, `scripts/install-prerequisites.ps1:805` | `$script:PluginCatalog`, `scripts/install-prerequisites.ps1:842` |
| Own manifest version | none (skills have no `plugin.json`) | `plugin/<name>/.claude-plugin/plugin.json`, bumped in lockstep with the marketplace entry |

### Counts: measure, do not read them here

**DERIVED, and stated as a method rather than a number that rots.** The split is
by `source` prefix and nothing else, so the invariant is: *every entry's `source`
starts with `./skills/` or `./plugin/`, and the two sets partition the array.*
`scripts/check-marketplace.py:396-397` derives `plugins` as `len(entries) -
skills` — so an entry whose `source` matched neither prefix would be silently
counted as a plugin, and no check catches that.

Re-measure with:

```
python3 -c "import json;p=json.load(open('.claude-plugin/marketplace.json'))['plugins'];\
print(len(p),sum(s.startswith('./skills/') for s in (e['source'] for e in p)))"
```

or just run the gate, which prints `marketplace: N skills, M plugins`.

At this anchor that is **29 entries — 25 skills, 4 plugins** (`crew`, `gizmoduck`,
`localgpu`, `obsidian-vault`), unchanged from the previous anchor: no entry has
been added or removed since `3167721f` despite `marketplace.json` appearing in
the moved-path list. What moved there were version and description fields on
existing entries.

### A worked example: adding an agent is not a registration

**DERIVED (historical, verified at anchor `b56d41f`; `crew` is now 0.16.25).**
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

**The asymmetry stated plainly, because it is a trap:** skills register in
`skills/README.md`; plugins register in `plugin/PLUGINS.md` **and**
`plugin/README.md`. There is no single doc both kinds share except the root
`README.md`. Registering a skill's entry in `plugin/PLUGINS.md`, or a plugin's
entry only in `plugin/PLUGINS.md` without the `plugin/README.md` row, both pass a
naive read of "did I add a doc row" while failing the actual check.

## What the checker reads — and the two things it does not

**DERIVED, verified against source at this anchor.** `check_docs`
(`scripts/check-marketplace.py:263-277`) reads exactly three files —
`skills/README.md`, `plugin/README.md`, and root `README.md` — testing each entry
for the literal substring `` [`name`](link) ``. It **never opens
`plugin/PLUGINS.md`**; `grep -rn 'PLUGINS.md' scripts/check-marketplace.py
_verify/` returns nothing. So a plugin whose `PLUGINS.md` section was never
written, or drifted out of sync with reality, fails no automated check.

### Descriptive text is unchecked, and has drifted

**DERIVED.** `check_catalogs` (`scripts/check-marketplace.py:166-191`) compares
*keys* — `SKILL_KEYS`, `PLUGIN_KEYS`, `SkillCatalog`, `PluginCatalog` — against
the marketplace name lists, for equality including order. It never looks at
`SKILL_NAME` / `PLUGIN_NAME` or the `Name` property, which hold the human-readable
menu text. `check_docs` likewise tests only for the presence of a link substring,
not the surrounding cell. **Nothing in the gate reads descriptive prose anywhere.**

The consequence is live today. `plugin/crew/agents/` holds 29 files and
`plugin/crew/commands/` holds 24 (`ls plugin/crew/agents/*.md | wc -l`). Four
places state those counts correctly — `.claude-plugin/marketplace.json`'s `crew`
`description`, `plugin/PLUGINS.md:17`, `plugin/README.md:370`, `README.md:773`.
Four state them wrongly, and every check passes:

| Location | Says | Actual |
|---|---|---|
| `scripts/install-prerequisites.sh:859` | `11 agents, 21 commands` | 29 agents, 24 commands |
| `scripts/install-prerequisites.ps1:843` | `11 agents, 21 commands` | 29 agents, 24 commands |
| `plugin/PLUGINS.md:153` (heading) | `Agents — 14, tiered plus the manager` | 29 |
| `README.md:162` (menu-item 19 prose) | `17 subagents, 24 slash commands` | 29 subagents |

`check_menu_parity` (`scripts/check-marketplace.py:194-230`) and
`check_group_parity` (`:233-260`) were read too, and compare the same way: menu
**keys** in order, plus the default-ticked booleans (`MENU_DEFAULT` against each
`Default = $true/$false`). No descriptive string is compared anywhere in either.
So the two install-script lines being *consistently* wrong means the matched-pair
rule passes cleanly — the pair agrees, it is simply agreeing on a stale sentence. The installer's understatement
is tracked in `TODO.md` under "The installer menu undersells crew by eighteen
agents and three commands"; the `PLUGINS.md:153` and `README.md:162` figures are
the same class of drift and are recorded here because they were found while
verifying it.

**JUDGEMENT:** treat "the gate is green" as a statement about structure only —
which directories are registered, which keys line up in which order, which links
exist, whether a version was bumped. Any number written in prose is unverified by
construction, and re-measuring it from the filesystem is the only way to know.

## Two version-check paths, not one

**DERIVED, corrected at this anchor.**

- `scripts/check-marketplace.py`'s own `main()`
  (`scripts/check-marketplace.py:377-405`) calls **nine** check functions in
  order at `:386-394`, **including** `check_versions` at `:394`. Running
  `python3 scripts/check-marketplace.py` — the exact command `CLAUDE.md` names as
  the gate — executes `check_versions`. *(This note previously said "eight". That
  was wrong at the previous anchor too; the file has not changed since. The
  ninth is `check_hook_commands` at `:393`. The miscount matters because it was
  the premise for "six of its eight", below, which was also wrong.)*
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
- The header (`_verify/smoke.sh:10-15`) gives the cost verbatim: the drift walk
  *"reads 58 revisions of marketplace.json and runs a git diff per entry, which
  costs ~160s on its own"* — against smoke's stated ~90s budget, so it is
  deferred to `run-all.sh`. Confirmed by observation: a direct
  `python3 scripts/check-marketplace.py` at this anchor did not finish inside a
  120s timeout.
- `_verify/smoke.sh`'s check 10 (`version_agreement_check`, body at
  `_verify/smoke.sh:261-355`, registered at `:356-357`) is **a different check
  entirely**, not a stand-in for the one it skips. It confirms that
  `pyproject.toml`, `plugin.json`, `marketplace.json`, and every hardcoded
  `VERSION`/`__version__` literal in a plugin's Python source all name the *same*
  version number right now. `check_versions`
  (`scripts/check-marketplace.py:298-328`) instead asks whether a plugin's
  `source/` directory changed *since* the commit where its current version was
  first declared — it walks `git log` over `marketplace.json` and runs
  `git diff --quiet <bump> HEAD -- <source>` per entry. That is a temporal /
  git-history question the point-in-time consistency check cannot answer and does
  not try to.

**JUDGEMENT:** there genuinely are two version-related gates that do not
substitute for one another. The correction is narrower than it sounds: it is
*`_verify/smoke.sh`'s internal fast path* that skips `check_versions`, not
`check-marketplace.py` as a program. A change that only runs `bash
_verify/smoke.sh` and treats a clean run as proof `check_versions` also passed is
trusting a check that never ran there. Anyone citing "check-marketplace.py never
checks version drift" should say "smoke.sh's fast subset doesn't" instead — the
full script does, on every direct invocation.

**Noted while reading, not this note's subject:** `_verify/smoke.sh:3` says
`# 9 checks`, and `grep -n '^check "' _verify/smoke.sh` returns 10. The
verification-harness note owns that file; recorded here only so the next reader
does not derive a count from the header comment.

## The gate's own invocation lives outside git's reach

**DERIVED.** `.crew/verify.json` — which `CLAUDE.md` names as "the mechanism" for
per-path verify commands, and which invokes this gate as
`python scripts/check-marketplace.py` (`.crew/verify.json:11`) — is **gitignored**
via `.gitignore:282` (`.crew/*`). Two consequences for anyone re-anchoring a note
that cites it:

- `git diff --name-only <anchor>..HEAD -- .crew/verify.json` can **never** list
  it, whatever changed. Empty output there means "untracked", not "current" — the
  opposite of what the empty-output convention means for every tracked path.
- Nothing in the repo can surface drift in it. Its `rules` array holds 15 entries
  at this anchor; a codemap elsewhere had recorded 13, and no check anywhere could
  have caught the difference.

**JUDGEMENT:** so the registration gate's *content* is checkable and version-
controlled, while the contract that decides *when it runs* is neither. Re-measure
`.crew/verify.json` from the working tree — `python3 -c "import json;
print(len(json.load(open('.crew/verify.json'))['rules']))"` — never from a diff.

## Two catalogs the marketplace does not govern

**DERIVED.** `check_group_parity` (`scripts/check-marketplace.py:238-243`)
enumerates **four** sub-picker groups, not two: `own-skills`
(`SKILL_KEYS`/`SkillCatalog`), `repo-plugins` (`PLUGIN_KEYS`/`PluginCatalog`),
and also `team` (`TEAM_KEYS`/`TeamCatalog`, `scripts/install-prerequisites.sh:878`
and `scripts/install-prerequisites.ps1:856`) and `community`
(`COMMUNITY_KEYS`/`CommunityCatalog`, `:894` and `:866`).

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
function bodies, and the worked example's historical git ranges.
## Entry points

- `.claude-plugin/marketplace.json` — 28 skills and 4 plugins. `jira-manager`, `knowbe4-admin` and `power-automate-api` were added this release; `crew` is 0.16.27.
- `scripts/check-marketplace.py:166` — `check_catalogs`, which requires `SKILL_KEYS` (.sh) and `$script:SkillCatalog` (.ps1) to match marketplace.json in the same ORDER, not merely as sets.
- `scripts/check-marketplace.py:233` — `check_group_parity`, which hardcodes exactly four sub-picker groups. Reusing `COMMUNITY` for VoltAgent rather than adding a fifth group is why this file needed no change.

## Owns data

- `skills/power-automate-api/.gitignore` — ignores `scripts/pa-snapshots/` wholesale. `pa.py` NO LONGER writes there: since the SNAPSHOT_DIR fix it writes live-tenant flow dumps to `~/.pa-api-cache/snapshots`, outside any checkout. The rule is kept as a net for checkouts that ran an earlier version, not as a description of current behaviour — one such dump was committed and pushed to this public repo before a review caught it.

## Calls out to

- Nothing at runtime. Registration is a set of files that must agree; `_verify/smoke.sh` runs the checker as its first gate.
