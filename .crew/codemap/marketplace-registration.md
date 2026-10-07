anchor: useful-claude-add-ons@5d1fc5fd
verified: 2026-09-22
Full per-path re-verification at `2b337296`, the first this note had since
`a573ca24`: the path diff was run, every one of its thirteen changed files was
re-read for the citations this note makes into it, and every line number was
re-taken from the file rather than offset. Four of that pass's headline
findings changed value. **This pass (`2b337296` -> `5d1fc5fd`) is narrower — a
per-path diff and a re-read of every citation into a changed file, not another
full re-derivation.** Nine of this note's seventeen tracked paths changed; the
headline result is that the fifth inversion this note tracked across five
consecutive passes is now FIXED, not merely reported. See `## Corrected at
5d1fc5fd` (below, at `:126` — it comes before the count-inversion history
itself, which lives in `## What the checker reads`, `:393+`) and the
bottom-most provenance section for this pass's command, its output, and what
was NOT re-read.

# Marketplace and registration

**DERIVED.** The root `.claude-plugin/marketplace.json` is the **only** marketplace
file in this repo. Stated as policy at `CLAUDE.md:5` and `CLAUDE.md:47` (**corrected
at this anchor — was cited as `CLAUDE.md:38`, which is a blank line in both this
revision and `2b337296`; the actual "second marketplace" bullet was always at
`:47` in both, so the previous citation was wrong when written, not made wrong by
this range's CLAUDE.md changes**), and
enforced at `scripts/check-marketplace.py:104-129` (unchanged position from
`84976536`, re-confirmed by direct read), where `check_registration` walks every on-disk
entry directory and fails if `<dir>/.claude-plugin/marketplace.json` exists —
*"makes this directory look like a second marketplace - the repo root's is the
only one"* (`:125-129`, re-read verbatim at this anchor).

## Re-anchor provenance - f9bb78a6 -> 84976536, 2026-09-22

Per-path check, run rather than skipped. The command, verbatim:

```
git diff --name-only f9bb78a6..HEAD -- <the 17 tracked paths this note cites>
```

**Thirteen changed**: `.claude-plugin/marketplace.json`, `.crew/verify.json`,
`.github/workflows/marketplace.yml`, `INSTALLATION.md`, `README.md`, `TODO.md`,
`_verify/smoke.sh`, `plugin/PLUGINS.md`, `plugin/README.md`,
`scripts/check-marketplace.py`, `scripts/install-prerequisites.ps1`,
`scripts/install-prerequisites.sh`, `skills/README.md`.

**Four did not**: `CLAUDE.md`, `scripts/_test/crew-ignore-policy.py`,
`scripts/_test/self-claims.py`, `skills/power-automate-api/.gitignore`.
Citations into those are closed by that result and were not re-read.

**On version-bump churn, because for this note it is not churn.** The usual
rule — discount `plugin/PLUGINS.md`, `*/README.md`, `plugin.json` and
`marketplace.json` as version-bump noise — was **not** applied here, and
applying it would have hidden three of this pass's four findings. Those files
are this note's actual subject: a catalog row moving is the event the note
exists to track, and "the version field changed" and "the description beside it
now states a wrong count" are the same diff hunk. Every one of them was
therefore read in full rather than skipped. The one thing genuinely treated as
noise is the `version` **value** itself, which is restated below as a measured
list rather than reasoned about.

**Four findings, in descending order of how much they cost to rediscover:**

1. **The count section has inverted a fifth time, and the site that is wrong is
   the one site with no marker.** `.claude-plugin/marketplace.json:229` (moved
   from `:223`) — crew's `description` — reads "27 slash commands, 19 bundled
   skills". On disk: **28 commands, 20 skills**. Both are off by one, in the
   same direction, and `python3 scripts/check-marketplace.py` passes. The five
   sites `f9bb78a6` marked with `<!-- claim: plugin-skills:crew -->` are all
   correct at 20, because the marker forces them to be. This one carries no
   marker — `check_self_claims` reads markers, and a number in a `description`
   string that nobody marked is invisible to it. **This is the note's standing
   JUDGEMENT arriving on schedule**: the previous pass wrote that a finding
   recording which places are RIGHT acquires an expiry date the moment it is
   written. It expired in eight days.
2. **A second, different count is wrong in three of four catalog docs.**
   Measured from `plugin/crew/hooks/hooks.json` by `json.load`: **20 hook
   entries, 10 scripts x `.sh`/`.ps1`, across 5 events.**
   `plugin/PLUGINS.md:17` states exactly that and is right. `README.md:168`
   ("18 hook entries (9 scripts x `.sh`/`.ps1`)"), `plugin/README.md:414` and
   `INSTALLATION.md:252` all say 18. Same mechanism as finding 1: the
   `plugin-skills:crew` marker sitting on those very lines covers the *skills*
   number only, so three wrong figures sit inside marked lines and the gate is
   green. A marker on a line is not a marker on the line's other numbers.
3. **`_verify/smoke.sh` now misses six of `main()`'s checks, not three.**
   `main()` (`scripts/check-marketplace.py:1196-1229`) calls **fourteen** check
   functions at `:1205-1218` — up from eleven. The four added in this range are
   `check_argument_hint_frontmatter`, `check_license_consistency`,
   `check_hook_commands` and `check_command_backtick_spans`. `run_marketplace_check`
   (`_verify/smoke.sh:72-98`) still exposes the same six groups calling the
   same **eight** functions. Missing: `check_versions`, `check_self_claims`,
   `check_crew_ignore_policy`, `check_argument_hint_frontmatter`,
   `check_license_consistency`, `check_command_backtick_spans`. Its in-function
   comment (`_verify/smoke.sh:82`) still claims "Same calls main() makes, in the
   same order, minus check_versions" — false by six, where it was false by one
   when written and false by three at the previous anchor. The drift is
   monotonic and nothing in the repo compares the two lists.
4. **`README.md:157`'s community row undercounts both its plugins and its
   marketplaces.** It lists seven community plugins and says "4 marketplaces".
   `COMMUNITY_KEYS` (`scripts/install-prerequisites.sh:1379-1382`) holds
   **eight**: the seven listed plus `eli5`, whose spec
   (`scripts/install-prerequisites.sh:1401`) resolves through a **fifth**
   marketplace, `claude-community`. `$script:CommunityCatalog`
   (`scripts/install-prerequisites.ps1:1120`) agrees with the `.sh`, so the
   matched pair holds and `check_group_parity` passes — which is precisely this
   note's "matched to each other, matched to no source of truth" finding, now
   with a live instance. **The local marketplace name is `claude-community`,
   not `claude-plugins-community`**, called out in a comment the scripts carry
   themselves (`scripts/install-prerequisites.sh:1371-1372`); passing the wrong
   one defeats the idempotency check silently.

**Not fixed, only recorded.** All four findings are defects in
`marketplace.json`, `README.md`, `INSTALLATION.md`, `plugin/README.md` or
`_verify/smoke.sh` — files this note reads and does not write. Fixing 1 or 2
also needs a crew version bump, which is a decision for whoever makes the fix,
not a side effect of re-anchoring a codemap note.

**Not re-read at this anchor**, and not claimed as fresh: the bodies of
`check_skill_manifests` (`scripts/check-marketplace.py:132-157`) and
`check_plugin_manifests` (`:160-173`) — listed from `main()` and range-checked
with `ast`, but not traced line by line; the four checks new in this range
beyond confirming their names and call order; `TODO.md`'s CLOSED agent-count
entry beyond confirming the file changed; the worked example's historical `git
diff --stat` ranges, which carry their own older anchor and were not re-run;
and the external community marketplaces themselves. `verification-harness.md`
owns `_verify/smoke.sh` and `check-marketplace.py` and should be read alongside
finding 3.

## Corrected at 5d1fc5fd — the fifth inversion is fixed, and two checks are new

**Finding 1 above ("the count section has inverted a fifth time") is FIXED at
this anchor, in `30173e99` ("check-marketplace: verify the command and skill
counts stated in descriptions and catalogs"), part of PR #208 / this note's
`5d1fc5fd` anchor.** `.claude-plugin/marketplace.json:229`'s `crew` description
now reads "28 slash commands, 20 bundled skills" (was "27 slash commands, 19
bundled skills"), re-read directly — `git diff 2b337296..5d1fc5fd --
.claude-plugin/marketplace.json` is a single hunk: that description string and
`version` "0.20.10" -> "0.20.11". `30173e99` itself is not a direct ancestor of
`5d1fc5fd` (its branch was squash-merged), so this is confirmed by reading the
file at `5d1fc5fd`, not by sha ancestry — see the bottom provenance section.

**The mechanism that was missing is also fixed, closing the actual gap finding
1 described** ("This one carries no marker — a number in a `description`
string that nobody marked is invisible to [`check_self_claims`]"). Two new
check functions exist and are wired into `main()`:
`check_description_claims` (`scripts/check-marketplace.py:867`, table
`DESCRIPTION_CLAIMS` at `:853-855`) reads `marketplace.json`'s own JSON
`description` field directly — the thing `check_self_claims` structurally
cannot reach, since that function scans tracked `*.md` files for an HTML
comment and a JSON string cannot carry one. `check_catalog_claims`
(`:1030`, table `CATALOG_CLAIMS` at `:975-978`) does the same for each install
script's own catalog label, scoped to one plugin's row via `_catalog_name_text`
(`:981`) rather than a whole-file scan. Both are opt-in tables, the same
contract `DESCRIPTION_CLAIMS`'s own leading comment states explicitly
(`:832-851`): `DESCRIPTION_CLAIMS = {"crew": ("commands", "skills")}` checks
*commands and skills* in the description — never agents, because no kind for
an agent-count phrase is implemented (`DESCRIPTION_CLAIM_KINDS`, `:861-864`).
`CATALOG_CLAIMS` checks the opposite pair — *agents and commands*, in both
install scripts' `crew` row — never skills, because neither catalog label
states one. `install-scripts.md` corrects an earlier draft of that same
sentence that conflated the two into "commands and agents" for both files at
once; the split above is what each table actually checks, re-read from source
at this anchor.

**`main()` now calls sixteen checks, not fourteen — two more than the previous
finding 3 measured**, and the gap in `_verify/smoke.sh` widened by the same
two. `main()` (`scripts/check-marketplace.py:1588-1623`, moved from
`:1196-1229`) calls all sixteen in order at `:1597-1612` (moved from
`:1205-1218`): the fourteen finding 3 counted, plus `check_description_claims`
and `check_catalog_claims`, both new in this range. `_verify/smoke.sh` did
**not** change in this range (absent from the nine-file diff below — closed by
the per-path check, not re-read), so its `run_marketplace_check()` still
exposes the same six named groups calling the same eight functions
(`registration`, `skills`, `plugins`, `catalogs`, `menus`, `hooks`); the gap is
now **eight of sixteen**, up from finding 3's "eight of fourteen." The two
newly missing are exactly `check_description_claims` and `check_catalog_claims`
— the two checks that closed the fifth inversion are themselves invisible to
`bash _verify/smoke.sh`, which is the same "divergence grows on every addition,
by default, with no corresponding edit required" pattern finding 3 already
named (JUDGEMENT, unchanged).

**Four other function citations moved in this range and are corrected here
rather than left pointing at the wrong code.** The new content in this range is
not one contiguous block, and "its own new insertions sit at `:853` onward" — a
previous version of this passage's framing — is false: two separate insertions
moved two separate groups of functions. `count_plugin_commands` (new, at
`:619` — confirmed absent from `check-marketplace.py` at `2b337296` by direct
grep) and the `plugin-commands:` branch inside `check_self_claims` (new,
`:765-800`, elif to its final closing paren per `grep -n ""
scripts/check-marketplace.py`) sit *before* `:853`, and between them they are what pushes
`check_self_claims` itself down: `scripts/check-marketplace.py:579` -> `:649`
(its counting helper `count_plugin_skills` moved `:562-576` -> `:563-577` for
the same reason). Separately, the block that genuinely does start at `:853` —
`DESCRIPTION_CLAIMS`/`check_description_claims` (`:853`, `:867`),
`count_plugin_agents` (`:936`) and `CATALOG_CLAIMS`/`check_catalog_claims`
(`:975`, `:1030`), all new — is what pushes the three functions defined after
all of it: `check_crew_ignore_policy` moved `:929` -> `:1321`, running to
`:1485` (was `:1091`); `check_command_backtick_spans` moved `:1094` -> `:1486`;
and **`check_hook_commands` also moved, `:1150` -> `:1542`** — a previous
version of this passage grouped `check_hook_commands` with the functions that
did not move, which was wrong; see `## Entry points` below for the corrected
line.
`check_registration`, `check_skill_manifests`, `check_plugin_manifests`,
`check_argument_hint_frontmatter`, `check_license_consistency`,
`check_catalogs`, `check_docs`, `check_menu_parity`, `check_group_parity`,
`check_versions`, `version_set_at` and
`bump_candidates` are all defined earlier in the file than the new insertions
and did **not** move — re-confirmed by grepping every `^def check_` and
`^def version_set_at`/`^def bump_candidates` at this anchor, not assumed.
These corrections are reflected in `## Entry points` below; the historical
provenance sections retain their original (now-superseded) line numbers as the
record of what was true when each was written.

## Re-anchor provenance - 975480b7 -> f9bb78a6, 2026-09-14

Narrow pass, not a full per-path check: this pass did not diff the eight
repo paths this note cites against `f9bb78a6`. It re-read only the
agent/command/skill-count table (below) and the `check_self_claims`/`main()`
citations that table's surrounding prose depends on, because `f9bb78a6`
(#169) is known to have touched `README.md`, `INSTALLATION.md`,
`plugin/PLUGINS.md`, `plugin/README.md`, `scripts/check-marketplace.py` and
`scripts/_test/self-claims.py` since `975480b7`. Confirmed by
`git show f9bb78a6 --stat`: exactly those six files, no others. The rest of
this note — including the `0a9d8937 -> 975480b7` section immediately below —
is retained as history from the previous pass and was not re-checked.

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
| `.sh` install script | `SKILL_KEYS`/`SKILL_NAME`/`SKILL_SPEC` arrays, `scripts/install-prerequisites.sh:1225` (`SKILL_KEYS=(`) through `scripts/install-prerequisites.sh:1307` (`unset _i` after `SKILL_STATE` at `:1305`) | `PLUGIN_KEYS`/`PLUGIN_NAME`/`PLUGIN_SPEC`, `scripts/install-prerequisites.sh:1314` (`PLUGIN_KEYS=(`) through `scripts/install-prerequisites.sh:1337` |
| `.ps1` install script | `$script:SkillCatalog`, `scripts/install-prerequisites.ps1:1040` | `$script:PluginCatalog`, `scripts/install-prerequisites.ps1:1088` |
| Own manifest version | none (skills have no `plugin.json`) | `plugin/<name>/.claude-plugin/plugin.json`, bumped in lockstep with the marketplace entry |

**Every install-script line in this row moved again at this anchor, and by far
more than last time — over 400 lines, not two.** Both scripts grew substantially
in this range (a skill-preflight step, an `mcp_launcher_resolves` check, a
community-marketplace row and two new catalog entries), so the previous anchor's
"+2 uniform offset" technique does **not** apply here and was not used: every
line above was re-taken by grepping for the array opening itself. A reader
carrying forward any `install-prerequisites` line number from an earlier version
of this note will be wrong by roughly 418 lines in the `.sh` and 232 in the
`.ps1`. `TEAM_KEYS` and `COMMUNITY_KEYS` moved with everything else — see "Two
catalogs the marketplace does not govern", re-measured there.

### Counts: measure, do not read them here

**DERIVED, and stated as a method rather than a number that rots.** The split is
by `source` prefix and nothing else, so the invariant is: *every entry's `source`
starts with `./skills/` or `./plugin/`, and the two sets partition the array.*
`scripts/check-marketplace.py:1614-1615` (moved from `:1220-1221` at `84976536`,
and from `:1012-1013`, `:959-960` and `:396-397` before that — two new checks,
`check_description_claims` and `check_catalog_claims`, landed above this point
in the `2b337296 -> 5d1fc5fd` range) derives `plugins` as
`len(entries) - skills` — so an entry
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

At this anchor that is **41 entries — 36 skills, 5 plugins**, confirmed both
ways: by the snippet above and by running the gate, which prints
`marketplace: 36 skills, 5 plugins`. The "neither prefix" set is still empty, so
the partition holds and the latent hole stays latent. One skill, `web-research`,
was added since the previous anchor — measured as a set difference over the
`plugins` array between `f9bb78a6` and HEAD (one added, none removed), not read
off a changelog. The plugin set did not change: still `crew`, `gizmoduck`,
`localgpu`, `obsidian-vault` and `rule-of-two`, five total, with `rule-of-two`
still the most recent addition (registered at `9fde7d82`, #128).

**Every plugin version moved in this range** — this is the churn the per-path
rule would normally discount, restated as a measured list because the note's
readers use it to date other claims: `crew` 0.20.10 (was 0.19.50), `gizmoduck`
0.5.3 (was 0.5.2), `localgpu` 0.1.20 (was 0.1.18), `obsidian-vault` 0.3.14 (was
0.3.8), `rule-of-two` 0.1.3 (was 0.1.2). Read from `marketplace.json` via
`json.load`. Five bumps across eight days is the rate this repo actually runs
at; treat any version number quoted elsewhere in this note as history.

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
(`scripts/check-marketplace.py:413-427`, moved from `:264-278`) reads exactly three files —
`skills/README.md`, `plugin/README.md`, and root `README.md` — testing each entry
for the literal substring `` [`name`](link) ``. It **never opens
`plugin/PLUGINS.md`**: the string `PLUGINS.md` appears nowhere in
`scripts/check-marketplace.py` or under `_verify/`. So a plugin whose
`PLUGINS.md` section was never written, or drifted out of sync with reality,
fails no automated check.

### Descriptive text is unchecked — and the drift it allowed has been repaired

**DERIVED.** `check_catalogs` (`scripts/check-marketplace.py:301-326`, moved
from `:167-192`) compares
*keys* — `SKILL_KEYS`, `PLUGIN_KEYS`, `SkillCatalog`, `PluginCatalog` — against
the marketplace name lists, for equality including order. It never looks at
`SKILL_NAME` / `PLUGIN_NAME` or the `Name` property, which hold the human-readable
menu text. `check_docs` likewise tests only for the presence of a link substring,
not the surrounding cell. **Nothing in the gate reads descriptive prose anywhere.**

On disk at the `84976536` anchor, re-counted at that pass: `plugin/crew/agents/` holds
**54** `.md` files (unchanged), `plugin/crew/commands/` holds **28** (was 26),
`plugin/crew/skills/` holds **20** directories (was 18). Unchanged again at
`5d1fc5fd`, re-confirmed above under `## Corrected at 5d1fc5fd`. The marked sites all
tracked those figures at `84976536`; `.claude-plugin/marketplace.json:229` did not — see
"finding 1" two provenance sections up.

**SUPERSEDED at `5d1fc5fd` — the sixth site is fixed. Read `## Corrected at
5d1fc5fd` above before the paragraph below, which is retained as the record of
the `84976536` pass and describes a state that no longer holds.** At
`84976536` it had inverted a FIFTH time, eight days after being declared FIXED:
the "now FIXED"
verdict recorded at `f9bb78a6` was true of the five *marked* sites and remained
true of them — all five tracked 20 skills because `check_self_claims`
forced them to. It was never true of the sixth site, which carried no marker:
`.claude-plugin/marketplace.json:229` (moved from `:223`) read "27 slash
commands, 19 bundled skills" against 28 and 20 on disk at `84976536`. So the correct reading
of this section's history at that pass was not "wrong four times, then fixed" but **"the
marked sites became self-correcting and the unmarked one carried on drifting"**
— which is a much more useful shape, because it says exactly what to do about
the next one: mark it, or expect it to rot. At `5d1fc5fd` the sixth site has now
been marked, by a different mechanism (`check_description_claims`, an explicit
table rather than an HTML-comment marker a JSON string cannot carry) — see
`## Corrected at 5d1fc5fd`. The `f9bb78a6` table below is
retained unedited as the record of what was believed then.

**The four-inversion history, as recorded at `f9bb78a6`:**
The third inversion (recorded below as "at 0a9d8937") was partly repaired by
`f12003e2` (#166): it fixed the skill count in `marketplace.json` and
`plugin/PLUGINS.md` but left `README.md:166`, `README.md:885` and
`INSTALLATION.md:251` still saying 17 — a defect this note's `975480b7` pass
found and reported but did not fix, per its own scope ("a finding for the
report, not a fix made in this note"). `f9bb78a6`, merged the same day,
brought all three to 18 and closed the gap `check_self_claims` could not see:
it added a `plugin-skills:<name>` claim type that counts
`plugin/<name>/skills/` directly from disk (`count_plugin_skills`,
`scripts/check-marketplace.py:413-427`), and marked all five live sites —
`README.md:166`, `README.md:885`, `INSTALLATION.md:251`, `plugin/PLUGINS.md:17`
and `plugin/README.md:414` — with `<!-- claim: plugin-skills:crew -->`.
Sabotage-tested by the author per the commit message: flipping
`plugin/PLUGINS.md`'s marked count to 99 makes `check-marketplace.py` fail
with `plugin/PLUGINS.md:17: claims 99 skills for plugin 'crew', but
plugin/crew/skills/ has 18`; restoring it returns exit 0 — reproduced
independently in this pass (see "Re-anchor provenance" above). The command
count remains correct everywhere checked (24 -> 26, following `5d2e2950`
#124's earlier agent-count fix and a later, unlogged commands bump).

| Location | Two anchors ago said | At 0a9d8937 | At 975480b7 | At f9bb78a6 |
|---|---|---|---|---|
| `.claude-plugin/marketplace.json:223` (now `:229`) | `29 context-isolated agents` | `54 ... 26 slash commands, 17 bundled skills` — skills still wrong (18 on disk) | `54 ... 26 slash commands, 18 bundled skills` — fixed by `f12003e2` | unchanged; not touched by `f9bb78a6`. **At `84976536`: `27 slash commands, 19 bundled skills`, both wrong against 28/20 on disk — the fifth inversion, and the only site here with no `claim:` marker** |
| `plugin/PLUGINS.md:17` | `29 agents, 24 commands, 17 skills` | `54 agents, 26 commands, 17 skills, 20 hook entries` — same defect | `54 agents, 26 commands, 18 skills, 20 hook entries` — fixed by `f12003e2` | same figure, now `<!-- claim: plugin-skills:crew -->`-marked by `f9bb78a6` |
| `plugin/PLUGINS.md:153` | `Agents — 14, tiered plus the manager` | `### Agents — one per agents/*.md` — no number, `:157` names `crew_state.SPECIALIST_ROLES` as the register | not re-read this pass; out of scope for this correction | not re-read this pass |
| `README.md:166` (root, was `:165`) | `50 subagents, ...` | `54 subagents, 26 slash commands, 17 bundled skills` | `54 subagents, 26 slash commands, 17 bundled skills` — unchanged; `f12003e2` did not touch this file | **18 bundled skills, marker-checked — fixed by `f9bb78a6`** |
| `README.md:885` | not previously tracked in this table | not previously tracked in this table | not previously tracked in this table | **18 skills, marker-checked — fixed by `f9bb78a6`**, in the same pass that fixed `:166` |
| `INSTALLATION.md:251` | not previously tracked in this table | not previously tracked in this table | `54 subagents, 26 slash commands, 17 bundled skills, 20 hook entries` — same untouched defect as `README.md:166` | **18 bundled skills, marker-checked — fixed by `f9bb78a6`** |
| `plugin/README.md:414` | not previously tracked in this table | not previously tracked in this table | `18 skills` (per `f12003e2`), no marker | same figure, now `<!-- claim: plugin-skills:crew -->`-marked by `f9bb78a6` |
| `scripts/install-prerequisites.sh:902` (was `:900`) | `11 agents, 21 commands` | `54 agents, 26 commands` — correct, does not mention skills | not re-read this pass; nothing about it changed shape at the previous anchor | not re-read this pass; unaffected — `f9bb78a6` did not touch either install script |
| `scripts/install-prerequisites.ps1:856` (was `:855`) | `11 agents, 21 commands` | `54 agents, 26 commands` — correct, same as above | not re-read this pass | not re-read this pass; unaffected, same reason |

`5d2e2950` ("crew 0.19.20: correct the agent count everywhere it is claimed",
#124) repaired the *agent* count at the previous inversion; the *commands*
figure moved in two later, ordinary command-adding commits rather than a
dedicated fix — `68c1f93a` (0.19.30) took it 24→25 and `53294344` (0.19.31)
took it 25→26 (`git log -S'25 commands' -- plugin/PLUGINS.md README.md` and
the same for `'26 commands'`), each incidentally correct because each new
`/crew:*` command's registration touched this line along with everything else.
The *skills* figure needed two fixes: `f12003e2` for `marketplace.json` and
`plugin/PLUGINS.md`, and `f9bb78a6` for the three it left — `README.md` (both
sites), `INSTALLATION.md` — plus `plugin/README.md`, a fifth location this
table has never carried a row for before now because it duplicates
`plugin/PLUGINS.md`'s figure rather than adding a distinct one. Every live
site is now 18 and every one of the five carries a `plugin-skills:crew`
marker, so a future drift on any of them fails `check-marketplace.py` rather
than waiting for a fourth hand-sweep. The two changelog lines that still read
"17 bundled skills" are correctly untouched by `f9bb78a6` — see the
structural observation immediately below, which already covers them.

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

`check_menu_parity` (`scripts/check-marketplace.py:329-380`, moved from
`:195-231`) and `check_group_parity` (`:383-410`, moved from `:234-261`) compare
the same way: menu **keys** in order, plus the default-ticked booleans
(`MENU_DEFAULT`, `scripts/install-prerequisites.sh:1145`, moved from `:728`,
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

**SUPERSEDED again at `5d1fc5fd`, this time in the direction of `_verify/smoke.sh`
staying still while `main()` moved.** At `84976536` this section's headline had
been wrong at three consecutive anchors as `main()`'s check count kept growing
("nine, not eight", "it is eleven", "fourteen"). At `5d1fc5fd` it is **sixteen** -
the fourth move - while `_verify/smoke.sh` is, for the first time in this
section's history, genuinely unchanged in the range (confirmed absent from the
nine-file diff in the bottom provenance section, so its own citations below are
closed by the per-path check rather than re-read). Only the `main()` bullet
below needed correcting at this pass.

- `scripts/check-marketplace.py`'s own `main()`
  (`scripts/check-marketplace.py:1588-1623`, moved from `:1196-1229`) calls
  **sixteen** check functions in order at `:1597-1612` (moved from
  `:1205-1218`). The fourteen from the previous anchor plus two new in this
  range: `check_description_claims` (`:867`) and `check_catalog_claims`
  (`:1030`) - see `## Corrected at 5d1fc5fd` above for what each does.
  `check_versions` is still among them, moved to `:1608` (was `:1216`).
  Running `python3 scripts/check-marketplace.py` — the exact command `CLAUDE.md`
  names as the gate — executes all sixteen; **not re-run at this pass** (see
  the bottom provenance section for what was and was not executed).
- `_verify/smoke.sh` is genuinely **unchanged** in the `2b337296 -> 5d1fc5fd` range - the
  first time this section can say that rather than "changed but not in this respect." Its
  `run_marketplace_check()` (`_verify/smoke.sh:72-98`) still re-imports `check-marketplace.py`
  as a Python module and exposes the
  same **six named groups** (`registration`, `skills`, `plugins`, `catalogs`,
  `menus`, `hooks`, `_verify/smoke.sh:83-90`) it always did, calling the same
  **eight** functions. So the gap is now **eight of sixteen** (was eight of fourteen), and the
  in-function
  comment - *"Same calls main() makes, in the same order, minus
  check_versions"* (`_verify/smoke.sh:82`) - is false by **eight**, not six: the six from the
  previous anchor plus `check_description_claims` and `check_catalog_claims`, both new at
  this anchor and both absent from every one of the six groups, alongside
  `check_versions`, `check_self_claims`, `check_crew_ignore_policy`,
  `check_argument_hint_frontmatter`, `check_license_consistency` and
  `check_command_backtick_spans`. `bash _verify/smoke.sh` passing says nothing
  about any of them - not numeric self-claim drift, not the `.crew/`
  ignore-policy invariant, and not the six newer checks, including the two that closed the
  fifth inversion this note tracked. Two groups call two
  functions each: `catalogs` runs `check_catalogs` *and* `check_docs` (`:87`),
  `menus` runs `check_menu_parity` *and* `check_group_parity` (`:88`).

  **JUDGEMENT, and the reason this keeps happening:** adding a check to
  `main()` requires no corresponding edit anywhere, so the fast subset silently
  falls further behind on every addition. The divergence has gone 1 -> 3 -> 6 -> 8
  across four anchors without anyone introducing a bug; it is the default
  behaviour of the arrangement, not an oversight by any one author.
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
- `_verify/smoke.sh`'s last check (`version_agreement_check`, body at
  `_verify/smoke.sh:279-373`, moved from `:261-355`; registered at `:374-375`)
  is **a different check entirely**, not a stand-in for the one it skips. It confirms that
  `pyproject.toml`, `plugin.json`, `marketplace.json`, and every hardcoded
  `VERSION`/`__version__` literal in a plugin's Python source all name the *same*
  version number right now. `check_versions`
  (`scripts/check-marketplace.py:518-551`, moved from `:369-402`) instead asks
  whether a plugin's
  `source/` directory changed *since* the commit where its current version was
  first declared — it walks `git log` over `marketplace.json` (via
  `version_set_at`, now `:472-480`, moved from `:323-331`) and runs `git diff
  --quiet <bump> HEAD -- <source>` per entry. It walks the history two ways,
  first-parent and full, because `357338cb` (#144) found the single-parent walk
  goes blind across a merge - `bump_candidates` (`:483-515`, moved from
  `:334-368`) tries candidates from both. That is a
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

**Noted while reading, not this note's subject — and the header is still wrong,
now in the opposite direction.** `_verify/smoke.sh:3` now says `# 11 checks`
(it said `# 9 checks` at the previous anchor), while the file has **ten** lines
beginning `check "` (`:100`, `:102`, `:104`, `:106`, `:108`, `:110`, `:142`,
`:145`, `:257`, `:374`). So the header overcounts by one where it used to
undercount by one; somebody corrected it past the right answer. The stale
`58 revisions` and `~160s` on `:12` are unchanged, so that header block still
carries three wrong numbers. The verification-harness note owns that file;
recorded here only so the next reader does not derive a count from the header.

## The gate's own invocation is now inside git's reach

**Retitled at this anchor - the previous heading is now wrong and the body
already said why.** `.crew/verify.json` was gitignored via the `.crew/*` stanza
until 2026-09-14, when `!.crew/verify.json` joined the named un-ignore list
alongside `!.crew/codemap/` and `!.crew/endpoints.json`. It is tracked and
**present in this checkout** - read in full at this anchor, not carried forward
as UNVERIFIABLE.

**DERIVED, from an actual read, re-done at the `84976536` anchor because the file changed there,
and re-confirmed unchanged in the `2b337296 -> 5d1fc5fd` range.**
`.crew/verify.json` is still **237 lines** and still carries **21**
`rules` (counted via `json.load` at `5d1fc5fd`, not `grep -c '"paths"'`) — the file's two-line diff
in this range (see the bottom provenance section) is wording only, inside the `pylint`/`ruff` rule's
`why` field and the `mcp-servers` rule's `why` field, and does not touch the rule count or the line
total. Its own `_note` array (`.crew/verify.json:4-29`)
still states, at `:7`, that the file "is TRACKED as of 2026-09-14". Its own
`anchor` field (`.crew/verify.json:3`) **still reads `"repo@5238be3d"`** — it
did not move in this range either, so the file is now further behind the code it maps
than at any previous pass. `git merge-base --is-ancestor 5238be3d HEAD` re-confirmed at `5d1fc5fd`:
it is an ancestor, so it is stale, not divergent. The gate invocation is
`python3 scripts/check-marketplace.py` wholesale and appears **three** times
(`.crew/verify.json:50`, `:67`, `:75`, position unchanged in this range), so every check `main()`
gained in this range runs wherever those rules fire regardless of whether
verify.json's author knew about them — which is the property that has kept this
file useful while its own anchor rots.

**That coverage gap is STILL OPEN at this anchor — re-checked, not assumed.**
The `scripts/**` rule (`.crew/verify.json:73`) matches
`scripts/_test/crew-ignore-policy.py` by path, and its `run` list has *grown* in
this range to nine commands (`check-marketplace.py`, `self-claims.py`,
`version-drift.py`, `sync-updates.py --check`, `menu-groups.sh`,
`check-powershell.sh`, `ps-install-keys.sh`, `uv-install.sh`,
`bash -n install-prerequisites.sh`) — and still does **not** include
`crew-ignore-policy.py` itself. Editing that sabotage suite matches a rule that
then runs nine other things but not the suite just edited.
`.github/workflows/marketplace.yml:51` (moved from `:41-42`) does run it in CI,
so the gap stays local-only, with the same qualifier as before: `_note`
(`.crew/verify.json:9-11`) says this map "only makes the LOCAL Stop gate
selective" and CI is "the gate everyone else gets".

**A different coverage hole in this file was closed in this range, and its own
`why` field is the best writeup of it.** `.crew/verify.json:71` records, at
length and dated 2026-09-22, that the **docs rule** (`rules[2]`, the one
matching `README.md`, `CLAUDE.md`, `TODO.md`, `CHANGELOG.md`, `INSTALLATION.md`,
`plugin/PLUGINS.md`, `plugin/README.md`, `docs/**` and others) had credited
itself with the marked-claim check while never running the program that
performs it: `check_self_claims` lives in `check-marketplace.py`, but the rule
ran only `scripts/_test/self-claims.py`, which tests that checker against
synthetic fixtures and never reads this repo's own docs. Demonstrated by
sabotage rather than argued — a marked `999 skills` claim appended to
`README.md` left both original commands at rc=0 while `check-marketplace.py`
reported `README.md:918: claims 999 skills, but marketplace.json registers 36`
and exited 1. `python3 scripts/check-marketplace.py` is now that rule's first
command. **This is directly load-bearing for this note**: for the entire period
the previous anchors were written, a marked-count drift in any of the thirteen
docs paths could not turn the local gate red — which is part of why this note's
count table kept inverting.

**The "only rule carrying an `agents` key" claim from an earlier pass is wrong,
and it is wrong about which rule.** An earlier version of `verification-harness.md`
(this note's neighbour) said the hooks rule required a `security` review agent.
Re-checked at this anchor by walking the parsed rules rather than grepping:
still exactly one rule carries an `"agents"` key
(`.crew/verify.json:172`, moved from `:130`), and it is still the
`**/*.ps1`/`**/*.psm1` rule, naming `powershell-security-hardening` — not
`security`, and not the hooks rule. The hooks-related rules carry no `agents`
key at all. Flagged here
because this note found it while reading `.crew/verify.json` for its own
purposes; `verification-harness.md` owns the correction.

`default` is `["bash _verify/smoke.sh"]` and `unmapped` is `"fail"`
(`.crew/verify.json:235-236`, moved from `:174-175`) - a change matching no rule's `paths` fails the
gate rather than passing silently, which is the file's own stated purpose for
`unmapped` (`_note`, `:12-20`, which also concedes the catch-all `plugin/**` /
`skills/**` rule means `unmapped` rarely fires - "0 of 790 tracked files are
unmapped" is not proof a new check would be noticed). `default` is a narrower
promise, stated separately (`_note`, `:21-26`): it is reached only when the
matched rules contribute no commands at all, not a general floor under every
turn.

## Two catalogs the marketplace does not govern

**DERIVED.** `check_group_parity` (`scripts/check-marketplace.py:383-410`, moved
from `:234-261`) enumerates **four** sub-picker groups, not two: `own-skills`
(`SKILL_KEYS`/`SkillCatalog`), `repo-plugins` (`PLUGIN_KEYS`/`PluginCatalog`),
and also `team` (`TEAM_KEYS`/`TeamCatalog`,
`scripts/install-prerequisites.sh:1353` and
`scripts/install-prerequisites.ps1:1103`) and `community`
(`COMMUNITY_KEYS`/`CommunityCatalog`, `scripts/install-prerequisites.sh:1379`
and `scripts/install-prerequisites.ps1:1120`). **All four install-script
citations were re-grepped rather than offset** — the previous anchor's
one-to-two-line shift is not what happened here; both files grew by hundreds of
lines (see "The registration web" above).

**Both catalogs gained an entry in this range, and the marketplace still
governs neither.** `TEAM_KEYS` is now four keys — `superpowers`,
`frontend-design`, `excalidraw-generator` and the new `github`, which resolves
via `claude-plugins-official` (`scripts/install-prerequisites.sh:1364`).
`COMMUNITY_KEYS` is now eight, gaining `eli5` through a fifth marketplace whose
**local name is `claude-community`, not `claude-plugins-community`** — the
scripts say so themselves in a comment at
`scripts/install-prerequisites.sh:1371-1372`, and using the wrong name defeats
the idempotency check silently rather than erroring. `README.md:157` still
describes seven community plugins across four marketplaces and is now wrong on
both counts; nothing checks it, which is this section's whole point.

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

Line numbers below are current at `5d1fc5fd`, re-taken by grepping each
function definition directly (`^def check_` etc.) rather than by offsetting —
the `2b337296 -> 5d1fc5fd` range added ~396 lines to `scripts/check-marketplace.py`
and the insertion is not evenly spaced, so an offset would be wrong in
different directions in different sections. Each entry names its `84976536`
figure too, since that is what the previous version of this section recorded.

- `.claude-plugin/marketplace.json` — **36 skills and 5 plugins**, 41 entries (re-counts unchanged
  in this range). `web-research` is still the newest skill; `rule-of-two` (added `9fde7d82`, #128)
  is still the newest plugin; `crew` is **0.20.11** (was 0.20.10 at `84976536`). **Its crew
  `description` at `:229` now states correct counts** — 28 commands, 20 skills — see `## Corrected
  at 5d1fc5fd` above; this replaces the previous "states counts that are wrong" line.
- `scripts/check-marketplace.py:301` — `check_catalogs` (unchanged position since `84976536`),
  which requires `SKILL_KEYS` (.sh) and `$script:SkillCatalog` (.ps1) to match marketplace.json in
  the same ORDER, not merely as sets.
- `scripts/check-marketplace.py:383` — `check_group_parity` (unchanged position), which hardcodes
  exactly four sub-picker groups.
- `scripts/check-marketplace.py:472` — `version_set_at` (unchanged position), the git walk that
  makes the version rule history-based, and therefore un-runnable against an uncommitted change.
  One of two history walks `check_versions` tries (`bump_candidates`, `:483`, is the other), added
  by `357338cb` (#144) to fix the walk going blind across a merge.
- `scripts/check-marketplace.py:649` (moved from `:579` at `84976536`) — `check_self_claims`, body
  `:649-830`; `count_plugin_skills` (`:563-577`, moved from `:562-576`) is its counting helper, and
  `count_plugin_commands` (`:619`, not previously cited by this note) is the helper for the
  `plugin-commands:` marker branch (`:765-800`).
- `scripts/check-marketplace.py:867` and `:1030` — new at this anchor, absent at `84976536`:
  `check_description_claims` (table `DESCRIPTION_CLAIMS` at `:853-855`) and `check_catalog_claims`
  (table `CATALOG_CLAIMS` at `:975-978`). See `## Corrected at 5d1fc5fd` for what each checks.
- `scripts/check-marketplace.py:1321` (moved from `:929`) — `check_crew_ignore_policy`, added by
  `0a9d8937` #161: asserts the `.crew/` ignore un-ignore list is one set stated consistently across
  `.gitignore` and five other marker-carrying files. It runs to `:1485` (was `:1091`).
- **Four checks were new at the `84976536` pass**: `check_argument_hint_frontmatter` (`:176`,
  unchanged), `check_license_consistency` (`:268`, unchanged), `check_command_backtick_spans`
  (moved `:1094` -> `:1486`) and `check_hook_commands` (moved `:1150` -> `:1542`). Listed from
  `main()`'s call order and re-located by grepping the function name; their bodies were **not**
  traced this pass, same as the `84976536` pass.
- `scripts/check-marketplace.py:1588` (moved from `:1196`) — `main()`, body `:1588-1623` (was
  `:1196-1229`), calling all **sixteen** checks (was fourteen) at `:1597-1612` (was `:1205-1218`).
- `.crew/verify.json:50`, `:67` and `:75` — still **three** invocations of `python3
  scripts/check-marketplace.py` from the tracked verification map; position unchanged in this
  range (the file's two-line diff in this range is wording only — see the bottom provenance
  section — not a line-count change).

## Owns data

- `skills/power-automate-api/.gitignore` — ignores `scripts/pa-snapshots/` wholesale. `pa.py` NO LONGER writes there: since the SNAPSHOT_DIR fix it writes live-tenant flow dumps to `~/.pa-api-cache/snapshots`, outside any checkout. The rule is kept as a net for checkouts that ran an earlier version, not as a description of current behaviour — one such dump was committed and pushed to this public repo before a review caught it.

## Calls out to

- Nothing at runtime. Registration is a set of files that must agree; `_verify/smoke.sh` runs the checker as its first gate.

## Re-anchor provenance — 84976536 -> 2b337296, 2026-09-22

Re-anchor only. Per-path check over the 17 tracked paths this note cites:

```
git diff --name-only 84976536..HEAD -- .claude-plugin/marketplace.json .crew/verify.json \
  .github/workflows/marketplace.yml INSTALLATION.md README.md TODO.md _verify/smoke.sh \
  plugin/PLUGINS.md plugin/README.md scripts/check-marketplace.py \
  scripts/install-prerequisites.ps1 scripts/install-prerequisites.sh skills/README.md CLAUDE.md \
  scripts/_test/crew-ignore-policy.py scripts/_test/self-claims.py skills/power-automate-api/.gitignore
```
```
.claude-plugin/marketplace.json
README.md
```

**A separate, wider diff was also run**, because this note's group name `skills`
(in "the group in `plugin/crew/skills/`," around the "descriptive text is
unchecked" section) is parsed by `_CITED_PATH_RE`
(`plugin/crew/hooks/scripts/crew_freshness.py`) as the bare directory
`skills/`, not as prose:

```
git diff --name-only 84976536..HEAD -- skills/
```
```
skills/doc-builder/scripts/resolve_brand.py
skills/doc-builder/scripts/_test/test_cross_os_paths.py
```

**Recorded as a known false-positive, not reworded away.** Per the assigned
task, the backticked group name `skills` is left as-is — it is prose in this
note, not a citation into `skills/doc-builder/`, and this note makes no claim
about `resolve_brand.py`. But because `_CITED_PATH_RE` cannot distinguish a
prose mention of the word `skills` from a real citation, **any future change
anywhere under `skills/` will flag this note's per-path check as changed**,
even when nothing this note actually cites moved. That is a standing false-positive
in this note's freshness check, not a defect in the doc-builder change. A
future pass seeing `skills/` in the diff output should check whether the
touched file is one this note actually names (it is not, for either file
above) before assuming a re-read is needed.

**Both real hits confirmed genuinely two-file, no add/remove.** `git diff
--name-status 84976536..HEAD -- skills/` shows `M` for both
`skills/doc-builder/scripts/resolve_brand.py` and its `_test` file — modified,
not added or removed, so the doc-builder skill's registration shape (one
`SKILL.md`, one marketplace entry) is unaffected regardless.

**The two real path-diff hits, checked against this note's actual claims:**

- `.claude-plugin/marketplace.json` — `git diff 84976536..HEAD --
  .claude-plugin/marketplace.json` shows exactly one hunk, `doc-builder`'s
  `version` field `1.5.2` -> `1.5.3`. The `crew` entry this note's count table
  cites (`.claude-plugin/marketplace.json:229`, "27 slash commands, 19 bundled
  skills") is untouched — re-diffed specifically to confirm. No claim in this
  note rests on `doc-builder`'s version.
- `README.md` — the change is the install-URL re-pin (`2cc73a1e`, PR #206),
  touching only lines 12 and 18 in place. **A previous version of this bullet
  undercounted this note's own `README.md:<n>` citations** (it listed five,
  omitting `:168` and `:918`); re-run with
  `grep -noE '(^|[^/A-Za-z])README\.md:[0-9]+' .crew/codemap/marketplace-registration.md`
  and corrected here. Seven distinct lines are cited: `README.md:157`
  (the community-plugin-count finding, cited twice in the body — `:85` and
  `:649`; a raw grep also matches this paragraph's own citation of it,
  which is self-reference, not a third body occurrence), `:166`, `:168`,
  `:774`, `:885`, `:591` and `:918` (the sabotage-test error message quoted
  verbatim). None is at 12 or 18, and the edit changed no line count, so none
  of these citations shifted or needed re-reading.
  `CHANGELOG.md` (which gained 10 lines at line 9 in this range per
  `repo-docs.md`) is not in this note's cited-path list and is not cited by
  line number anywhere in this note.

Nothing else in this note was re-read. `python3 scripts/check-marketplace.py`
was not re-run at this pass.

## Re-anchor provenance — 2b337296 -> 5d1fc5fd, 2026-09-22

Per-path check, run over the same seventeen tracked paths as the section above:

```
git diff --name-only 2b337296..5d1fc5fd -- .claude-plugin/marketplace.json .crew/verify.json \
  .github/workflows/marketplace.yml INSTALLATION.md README.md TODO.md _verify/smoke.sh \
  plugin/PLUGINS.md plugin/README.md scripts/check-marketplace.py \
  scripts/install-prerequisites.ps1 scripts/install-prerequisites.sh skills/README.md CLAUDE.md \
  scripts/_test/crew-ignore-policy.py scripts/_test/self-claims.py skills/power-automate-api/.gitignore
```
```
.claude-plugin/marketplace.json
.crew/verify.json
CLAUDE.md
TODO.md
plugin/PLUGINS.md
scripts/_test/self-claims.py
scripts/check-marketplace.py
scripts/install-prerequisites.ps1
scripts/install-prerequisites.sh
```

**Nine changed, eight did not**: `.github/workflows/marketplace.yml`,
`INSTALLATION.md`, `README.md`, `_verify/smoke.sh`, `plugin/README.md`,
`skills/README.md`, `scripts/_test/crew-ignore-policy.py`,
`skills/power-automate-api/.gitignore`. Citations into the eight unchanged
files are closed by that result.

**What each of the nine changed files turned out to contain, checked by
content rather than assumed from the diff:**

- `.claude-plugin/marketplace.json` — one hunk, crew's `description` (the
  fifth-inversion fix) and `version` bump. See `## Corrected at 5d1fc5fd`.
- `.crew/verify.json` — two lines, both inside `why` prose (the `pylint`/`ruff`
  rule and the `mcp-servers` rule), rewording an explanation of a
  `verify-gate.sh` ordering fix. Does not touch rule count, line total, or the
  `anchor` field — re-confirmed directly, see "The gate's own invocation"
  section above.
- `CLAUDE.md` — the `render.sh` regression-test citation was rewritten to name
  a case number instead of a file-total line count (`repo-docs.md` and
  `install-scripts.md` both own this citation; this note does not cite
  `render.sh` itself and was not affected). Confirmed by reading the diff: it
  touches only that one passage.
- `TODO.md` — +81/-5 lines, but not at or above the `:634-761` entry this note
  cites - re-confirmed that entry is still at the same lines, unmoved, by
  grepping its heading directly.
- `plugin/PLUGINS.md` — one hunk, the same version-bump line the marketplace.json
  entry carries (`<!-- claim: plugin-version:crew -->`).
- `scripts/_test/self-claims.py` — grew from 344 to 1382 lines; not cited by
  line number anywhere in this note (install-scripts.md owns that citation).
- `scripts/check-marketplace.py` — grew from 1233 to 1627 lines. Every function
  citation into it was re-grepped by name, not assumed unchanged; results are
  folded into `## Corrected at 5d1fc5fd` and the rewritten `## Entry points`
  and `## Two version-check paths` sections above.
- Both install scripts — one line each, the crew catalog row's command count
  (26 -> 28). No other citation into either script moved (both diffs are single
  in-place line replacements, no net line-count change).

**Not re-executed at this pass**: `python3 scripts/check-marketplace.py`. Not
re-read: the bodies of `check_skill_manifests` and `check_plugin_manifests`
beyond their unchanged line ranges (confirmed by direct grep, not `ast` this
time), the worked example's historical git ranges, and the external community
marketplaces. `verification-harness.md` and `install-scripts.md` should be
read alongside this pass's findings — the new checks and the pin-staleness
finding both recur there.
