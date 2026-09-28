anchor: useful-claude-add-ons@c192b83d
verified: 2026-09-28
paths: scripts/**, plugin/PLUGINS.md

**Re-derive provenance.** Full re-derivation, not a re-verify. The previous
anchor (`5d1fc5fd`) predates crew 1.0's four-role rewrite
(`c3bd8dfd` "remove the PM agent, pulse, journal and retired roles" through
`6c497a14` "crew 1.0.25: lifecycle redesign, 4-role roster …"), which changed
every one of this note's headline counts: crew went from 54 agents / 28
commands / 20 skills / 34 hook entries to **4 agents / 34 commands / 29
skills / 34 hook entries**. Per the assigning task's own per-path check, 13 of
this note's 16 tracked paths moved. Every claim below was re-read directly
against the file it cites at `6c497a14` — every function line number was
re-taken by grepping the definition, every count re-measured from disk or by
running the gate, not carried forward or offset. `python3
scripts/check-marketplace.py` was executed this pass: `marketplace: 34
skills, 5 plugins`, `all checks passed`, rc 0, on the Linux host. No cited
path in this note was found deleted at this anchor (checked by existence for
every citation below); the count divergences the previous version of this
note tracked across five anchors are, for the first time this note has
recorded, **all resolved** — every stated count matches the disk count it
claims to state, everywhere this pass checked.

# Marketplace and registration

**DERIVED.** The root `.claude-plugin/marketplace.json` is the only
marketplace file in this repo — stated as policy at `CLAUDE.md:5` and `:47`,
enforced at `scripts/check-marketplace.py:104-131` (`check_registration`,
unmoved from the previous anchor), which walks every on-disk entry directory
and fails if `<dir>/.claude-plugin/marketplace.json` exists.

## Counts, measured fresh: 39 entries, 34 skills, 5 plugins

**DERIVED**, by the same method the previous anchor used — partition
`marketplace.json`'s flat `plugins` array by `source` prefix
(`./skills/` vs `./plugin/`) — and independently confirmed by running the
gate. `scripts/check-marketplace.py:1665-1666` still derives `plugins` as
`len(entries) - skills`, so an entry matching neither prefix would silently
count as a plugin; the "neither" set is empty at this anchor, same as at
`5d1fc5fd`.

The **skill** count *dropped*, from 36 at `5d1fc5fd` to **34** — the first
decrease this note has recorded; every previous change was a net addition.
Not traced commit by commit this pass (out of scope: this note tracks the
registration mechanism, not the skill catalog's own history), but the drop is
consistent with `web-testing-playwright` and other single-skill entries
either being removed or consolidated during the crew 1.0 rewrite; flagged as
an open question rather than asserted either way. The **plugin** count is
unchanged at **5**: `crew`, `gizmoduck`, `localgpu`, `obsidian-vault`,
`rule-of-two`. `crew` is now **1.0.51** (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json`
and the `plugin-version:crew` claim at `plugin/PLUGINS.md:14` all agree, re-read at `9631c707`, T-0072's landing bump after its merge of `e6e10432`; it was 1.0.50 at `a4eb2f55`, T-0072's bump after its merge of `5050ea3b`, and at main `e6e10432`, T-0079's landing, bumped on T-0079's branch at `81685adf`, where it was 1.0.49 at `78215930`; it was 1.0.49 at `fc289446` (T-0077's landing bump) and on T-0072's branch at `80326b1d`, 1.0.48 at `8de3c669` (T-0024's landing bump) and on T-0072's branch at `21429244` and `996a0a9e`, 1.0.47 at `67caa4b8` after T-0018's re-bump `65bb3330` on its merge of
main `bebbb97f` (`f458e752`), 1.0.47 on T-0072's branch at `715a8c2f`, 1.0.46 at `bebbb97f` and at that merge (T-0023's bump `e463ca53`) and at T-0018's first landing bump `fbc27b49`, 1.0.45 at `db14619c` (T-0021, bumped again for a CI fix), 1.0.44 on T-0018's branch at `0c7f6b84`, 1.0.43 on T-0023's branch at `a1acd9b7` and on T-0018's at `39f8f59f`, 1.0.44 at `12682e41`, 1.0.43 at `f0b12ee6` (T-0042) and on T-0021's branch at `c2ae46ab`, 1.0.42 at `2b18f7ab` (1.0.46 on T-0021's branch until its merge of main), 1.0.41 at `07ca3972` and on T-0005's branch, 1.0.40 at `a0c0847e`, 1.0.39 at `8ebbdedc`, 1.0.38 at `c35edda5`, 1.0.37 at `768a747a`, 1.0.36 at `adf8d1dd`, 1.0.28 at `f2bb919b`, 1.0.25 at `6c497a14` and 0.20.11 at `5d1fc5fd`);
`obsidian-vault` is **0.4.14** (was 0.3.14); `gizmoduck` (0.5.3) and
`rule-of-two` (0.1.3) are unchanged; `localgpu` moved to 0.1.20.

## Crew's own description agrees with disk, one site excepted

**DERIVED, re-measured at `07ca3972`.**
`.claude-plugin/marketplace.json:217` — crew's `description` — reads "4
context-isolated agents (explorer, reviewer, security, researcher) …, 35
slash commands, 29 bundled skills … 34 hook entries." Measured independently
against disk:

| Claim | Stated | On disk | Where |
|---|---|---|---|
| agents | 4 | `ls plugin/crew/agents/*.md` → 4 | `.claude-plugin/marketplace.json:217`, `plugin/PLUGINS.md:17`, `README.md:168`/`:874`, `INSTALLATION.md:252`, `plugin/README.md:414` |
| commands | 35 | `find plugin/crew/commands -name '*.md'` → 35 (T-0004 added `autopilot.md`) | same sites **except `INSTALLATION.md:252`, which still reads "34 slash commands"** — unmarked, so no check catches it |
| skills | 29 | `find plugin/crew/skills -maxdepth 1 -mindepth 1 -type d` → 29 | same sites, each `<!-- claim: plugin-skills:crew -->`-marked |
| hook entries | 34 | walking `plugin/crew/hooks/hooks.json`'s 8 events → 34 command entries | same sites |

Both install scripts' own crew catalog row (`scripts/install-prerequisites.sh:1391`,
`scripts/install-prerequisites.ps1:1174`) states "4 agents, 35 commands" and
matches too — `CATALOG_CLAIMS` (below) checks exactly this pair for exactly
this reason. Every number in the table above was re-derived from the
filesystem this pass, not read off a previous version of this note or off the
gate's own claim that it passed.

## `check_self_claims` — three marker types now, not two

**DERIVED, re-read at this anchor.** `check_self_claims`
(`scripts/check-marketplace.py:673-903`, moved +24 lines from `5d1fc5fd`'s
`:649` because `count_crew_markdown_lines` — new, `:564-586` — was inserted
ahead of it) still recognises `skills-count` (marketplace-wide total),
`plugin-version:<name>`, and `plugin-skills:<name>` (counting
`plugin/<name>/skills/` directly from disk, `count_plugin_skills:587-602`),
`plugin-commands:<name>` (`count_plugin_commands:643-671`), and now also
**`crew-markdown-lines`** — new this pass, matching `MARKDOWN_LINES_RE`
(`:561`) within a 12-line `BIND_WINDOW` (unchanged) and comparing against
`count_crew_markdown_lines()`. `plugin/crew/BUDGETS.md` is the site that
carries this marker (not one of the five `plugin-skills:crew` sites above);
this note's own citation of `BUDGETS.md`'s marked figure was not re-derived
this pass — see "Unverified at this anchor." `check_self_claims`'s handling
of an *unresolvable* count is worth restating because it is a recurring
pattern in this repo's own checks: `count_crew_markdown_lines` returns
`None`, not `0`, when git cannot answer, and the caller reports that as its
own UNVERIFIED failure message rather than comparing `None` to a real count —
see `verification-harness.md`, which owns the mechanism.

## `check_description_claims` and `check_catalog_claims` — unchanged in shape

**DERIVED, re-read.** `DESCRIPTION_CLAIMS` (`:904-906`) still checks exactly
`{"crew": ("commands", "skills")}` against `marketplace.json`'s own JSON
`description` string (`check_description_claims:918-...`) — the one place
`check_self_claims` structurally cannot reach, since that function scans
tracked `*.md` files for an HTML comment and a JSON string cannot carry one.
`CATALOG_CLAIMS` (`:1026-1029`) still checks the opposite pair — `("agents",
"commands")` — against each install script's own crew catalog label
(`check_catalog_claims:1081-...`, `_catalog_name_text:1032`). Neither table
checks skills for the catalog labels or agents for the description, by
design (comment at `:1020-1025`): a count that is not named in one of these
two tables is, like an unmarked number anywhere else, not checked.

## The registration web — skill vs. plugin, re-confirmed at this anchor

**DERIVED.** Unchanged in shape from `5d1fc5fd`; every cited line re-taken.

| | Skill | Plugin |
|---|---|---|
| Marketplace entry | `.claude-plugin/marketplace.json` (one flat array, split by `source` prefix only) | same file |
| Catalog doc | `skills/README.md` — header `:73`, first row `:75` (both moved from `:87`/`:89`) | `plugin/PLUGINS.md` (a `## \`name\`` section) **and** `plugin/README.md` (a table row) |
| Root README | linked under `skills/{name}` | linked under `plugin/{name}` |
| `.sh` install script | `SKILL_KEYS`/`SKILL_NAME`/`SKILL_SPEC`, `scripts/install-prerequisites.sh:1298-...` | `PLUGIN_KEYS`/`PLUGIN_NAME`/`PLUGIN_SPEC`, `scripts/install-prerequisites.sh:1383-1393` |
| `.ps1` install script | `$script:SkillCatalog`, `scripts/install-prerequisites.ps1:1127` | `$script:PluginCatalog`, `scripts/install-prerequisites.ps1:1173` |
| Own manifest version | none | `plugin/<name>/.claude-plugin/plugin.json`, bumped in lockstep with the marketplace entry |

Both install-script catalog rows for `crew` (`scripts/install-prerequisites.sh:1391`,
`scripts/install-prerequisites.ps1:1174`) both read "4 agents, 35 commands,
safety hooks", matching `PLUGIN_KEYS` order
(`crew`, `gizmoduck`, `localgpu`, `obsidian-vault`, `rule-of-two`) against
`marketplace.json`'s own plugin ordering — `check_catalogs`
(`scripts/check-marketplace.py:301-327`) compares that ordering, not merely
set membership.

**What the checker never opens.** `check_docs`
(`scripts/check-marketplace.py:413-428`) still reads exactly three files —
`skills/README.md`, `plugin/README.md`, root `README.md` — for the literal
substring `` [`name`](link) ``, and never opens `plugin/PLUGINS.md`: the
string `PLUGINS.md` appears nowhere in `scripts/check-marketplace.py` or
under `_verify/`. A plugin whose `PLUGINS.md` section drifted out of sync
with reality fails no automated check. `check_catalogs` and
`check_menu_parity`/`check_group_parity` (`:329-380`, `:383-410`) still
compare only **keys**, in order — never the descriptive `SKILL_NAME` /
`PLUGIN_NAME` text or the `Name` property, so a menu label can be
consistently *wrong* on both platforms and the matched-pair check still
passes.

## Two catalogs the marketplace does not govern

**DERIVED, re-measured.** `check_group_parity` still enumerates four
sub-picker groups: `own-skills`, `repo-plugins`, and two the marketplace
never touches — `team` (`TEAM_KEYS`/`$script:TeamCatalog`) and `community`
(`COMMUNITY_KEYS`/`$script:CommunityCatalog`).

- **`TEAM_KEYS`** (`scripts/install-prerequisites.sh:1422`) is unchanged at
  **four**: `superpowers`, `frontend-design`, `excalidraw-generator`,
  `github` — all four resolving through `claude-plugins-official`.
- **`COMMUNITY_KEYS`** (`scripts/install-prerequisites.sh:1448-1450`) is
  **eight**: `adhd-output-style`, `azure-tools`, `anthropic-office-skills`,
  `agent-browser`, `ppt-master`, `voltagent-infra`, `voltagent-qa-sec`,
  `eli5` — resolving through **five** distinct marketplace names
  (`claude-settings`, `agent-browser`, `ppt-master`, `voltagent-subagents`,
  `claude-community`), confirmed by reading `COMMUNITY_SPEC`
  (`:1461-1470`). The comment at `scripts/install-prerequisites.sh:1440-1441`
  still states explicitly that the local name is `claude-community`, not
  `claude-plugins-community`.

`$script:CommunityCatalog` (`scripts/install-prerequisites.ps1:1205`) and
`$script:TeamCatalog` (`:1188`) agree with the `.sh` arrays — the matched-pair
check (`check_group_parity`) still passes, and still says nothing about
whether either array's *content* is accurate, since nothing in
`marketplace.json` describes a plugin from someone else's marketplace.
`README.md` no longer states a specific community-plugin or marketplace
count in prose (the previous anchor's "seven community plugins across four
marketplaces" line is gone from `README.md:231`, which now points to
`MARKETPLACE.md` for the details instead of restating a number) — the
specific defect this note tracked across two anchors is gone because the
claim it was wrong about was removed, not because it was corrected in place.
`MARKETPLACE.md` itself was not re-read this pass for a competing claim.

## Two version-check paths, still not one

**DERIVED, unchanged in shape.** `scripts/check-marketplace.py`'s own
`main()` (`:1639-1674`) calls all sixteen checks, `check_versions` included,
at `:1659` in call order. `_verify/smoke.sh` is confirmed byte-identical to
`5d1fc5fd` (`git diff --stat` empty) — its `run_marketplace_check()`
(`:72-98`) still exposes the same six named groups calling the same eight
functions (`registration`, `skills`, `plugins`, `catalogs`, `menus`,
`hooks`), so the gap is still **eight of sixteen**: `check_versions`,
`check_self_claims`, `check_crew_ignore_policy`,
`check_argument_hint_frontmatter`, `check_license_consistency`,
`check_command_backtick_spans`, `check_description_claims` and
`check_catalog_claims` are all invisible to `bash _verify/smoke.sh`. The
practical consequence is unchanged: `check_versions` is history-based
(`version_set_at`, `bump_candidates` walking both first-parent and full
history) and cannot answer for an uncommitted change, so a pre-commit run of
the fast path proves nothing about a missing version bump either way.

## `.crew/verify.json`'s doc rule still runs the marked-claim checker first

**DERIVED, re-read.** The rule matching `README.md`, `CLAUDE.md`, `AGENTS.md`,
`TODO.md`, `CHANGELOG.md`, `INSTALLATION.md`, `plugin/PLUGINS.md`,
`plugin/README.md`, `plugin/*/README.md`, `docs/**`, `MARKETPLACE.md`,
`SECURITY.md`, `Skill-Authoring-Standard.md`, `Skill-Pipeline.md`
(`.crew/verify.json:69-78`) runs `python3 scripts/check-marketplace.py` as
its **first** command, unchanged from the previous anchor's fix — see
`verification-harness.md`, which owns this file. This is what makes the
count table above a real, gate-enforced invariant rather than prose nobody
re-derives: a marked claim drifting on any of these fourteen paths fails this
rule, not merely `scripts/_test/self-claims.py`, which tests the checker
against synthetic fixtures and never reads this repo's own docs.

## Owns data

- `skills/power-automate-api/.gitignore` — ignores `scripts/pa-snapshots/`
  wholesale. Not re-verified this pass (confirmed unchanged in the per-path
  diff: `git diff --stat 5d1fc5fd..6c497a14 -- skills/power-automate-api/.gitignore`
  is empty).

## Calls out to

- Nothing at runtime. Registration is a set of files that must agree;
  `_verify/smoke.sh` runs the checker as its first gate, and `.crew/verify.json`'s
  doc rule runs the full `check-marketplace.py` directly as its first command.

## Entry points

- `.claude-plugin/marketplace.json:217` — crew's `description`, now correct
  against disk on every measured count.
- `scripts/check-marketplace.py:1639` — `main()`, sixteen checks in the same
  order as `verification-harness.md` records.
- `scripts/check-marketplace.py:104` — `check_registration`.
- `scripts/check-marketplace.py:301`, `:329`, `:383` — `check_catalogs`,
  `check_menu_parity`, `check_group_parity`.
- `scripts/check-marketplace.py:413` — `check_docs`, the three-file,
  link-substring-only check.
- `scripts/check-marketplace.py:673`, `:904`, `:918`, `:1026`, `:1081` —
  `check_self_claims`, `DESCRIPTION_CLAIMS`, `check_description_claims`,
  `CATALOG_CLAIMS`, `check_catalog_claims`.
- `scripts/install-prerequisites.sh:1298`, `:1383`, `:1422`, `:1448` —
  `SKILL_KEYS`, `PLUGIN_KEYS`, `TEAM_KEYS`, `COMMUNITY_KEYS`.
- `scripts/install-prerequisites.ps1:1127`, `:1173`, `:1188`, `:1205` — the
  four PowerShell catalog arrays, in the same order.

## Unverified at this anchor

- **Why the skill count dropped from 36 to 34** was not traced commit by
  commit. Recorded as a measured fact (39 total entries, 34 skills, 5
  plugins), not reasoned about further — this note tracks the registration
  mechanism, not the skill catalog's editorial history.
- **`plugin/crew/BUDGETS.md`'s own `<!-- claim: crew-markdown-lines -->` site**
  was not opened at `6c497a14`. Closed at `f2bb919b`: the marker is `:10`, the
  figure on `:11` reads 17,811 lines across 120 files, and
  `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 17811 over 120
  files, matching; `check-marketplace.py` passes it. Re-measured for T-0008: the marker
  is still `:10`, the figure on `:11` reads 17,841 lines across 120 files, and the
  same measurement returns 17841 over 120 files, matching. Re-measured at `8ebbdedc`: `:11`
  reads 17,847 lines across 120 files, and `count_crew_markdown_lines()`'s `splitlines()` total
  over `git ls-files 'plugin/crew/*.md'` returns 17847 over 120 files, matching. On T-0006's
  branch, re-measured at `6d35ef8c`: 17,959 on `:11`, and the measurement returns 17959 over 120 files, matching. Re-measured for
  T-0006 review round 3 at `2bb92f32`: 17,967 on `:11`, and the measurement returns 17967 over
  120 files, matching. Re-measured at the T-0006 landing `a0c0847e`: 17,973 on `:11` (recomputed
  from the merged tree, not taken from either side), and the measurement returns 17973 over 120
  files, matching. Re-measured at `07ca3972` (T-0004): 18,176 across 121 files on `:11`, and
  `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18176 over 121 files, matching.
  Re-measured at `5536c2c8` (T-0018): 18,170 across 121 files on `:11`, and the measurement
  returns 18170 over 121 files, matching.
  Re-measured at `068db4ff` (T-0042): 18,253 across 121 files on `:11`, and the same measurement
  returns 18253 over 121 files, matching; the ticket's docs had left it at 18,176 and
  `check-marketplace.py` failed on it until `25f94459` re-measured it.
  On T-0021's branch, re-measured at `7b667587`:
  the figure on `:11` reads 17,989 lines across 125 files (T-0021 added five tracked board
  fixtures under `plugin/crew/tests/tracker_fixtures/`), and the measurement returns 17989 over
  125, matching. Re-measured at `385eadd5` (T-0021 review round 1): the figure reads 18,007
  lines across 125 files and the measurement returns 18007 over 125, matching. Re-measured at
  `bcb77ce2` (T-0021 review round 2): the figure reads 18,044 lines across 125 files and the
  measurement returns 18044 over 125, matching. Re-measured on T-0021's merge of main
  (`86ea912f`, unchanged at `c2ae46ab`): 18,713 across 126 files on `:11`, recomputed from the
  merged tree rather than taken from either side (main's `2b18f7ab` read 18,494 across 121), and
  the measurement returns 18713 over 126 files, matching; `check-marketplace.py` passes it.
  Re-measured at `d9cdb54c` (T-0021 review round 4): 18,723 across 126 files on `:11`, and the
  measurement returns 18723 over 126, matching. Re-measured on T-0021's landing merge `6df1231a`
  (unchanged at `12682e41`): 18,800 across 126 files on `:11`, recomputed from the merged tree
  (main's `f0b12ee6` read 18,571 across 121), and the measurement returns 18800 over 126, matching.
  Re-measured on T-0023's merge of `db14619c` (`c68b40bd`, unchanged at `e463ca53`): 18,864 across
  126 files on `:11`, recomputed from the merged tree (T-0023's `a1acd9b7` read 18,558 across 121,
  main's `db14619c` 18,800 across 126), and the measurement returns 18864 over 126, matching.
  On T-0018's branch, re-measured on the merge of origin/main `f0b12ee6` into T-0018-router: 18,566 across 121 files
  on `:11` (recomputed from the merged index with `count_crew_markdown_lines()`, not taken from
  either side: 18,489 on T-0018, 18,571 on main), matching.
  Re-measured on T-0018's landing merge of `e6b696fb` into main `db14619c`: 18,795 across 126
  files on `:11`, recomputed from the merged index rather than taken from either side (main's
  `db14619c` read 18,800 across 126; T-0018's `e6b696fb` read 18,566 across 121), matching.
  Re-measured on T-0018's merge of main `bebbb97f` into T-0018-land: 18,859 across 126 files on
  `:11`, recomputed from the merged index rather than taken from either side (main's `bebbb97f`
  read 18,864 across 126; T-0018-land's `55f59b04` read 18,795 across 126), matching.
  Re-measured on T-0024's landing merge of `474aea8b` into main `67caa4b8`: 18,885 across 126 files
  on `:11`, recomputed from the merged index rather than taken from either side (main's `67caa4b8`
  read 18,859 across 126; T-0024's `474aea8b` read 18,202 across 121), matching.
- **`MARKETPLACE.md`** was not re-read for a community-plugin or marketplace
  count of its own; only `README.md:231`'s prose was checked and found to no
  longer state a specific number.
- **`check_skill_manifests`, `check_plugin_manifests`, `check_argument_hint_frontmatter`,
  `check_license_consistency`, `check_command_backtick_spans` and
  `check_hook_commands`** were confirmed present, in the same call position,
  by name only — their bodies were not re-traced line by line this pass
  (`check_hook_commands`'s quoting/exit-code rules were spot-read for
  `verification-harness.md`'s purposes, not re-verified here).
- **The install scripts' full array contents** (every `SKILL_KEYS` entry, not
  just the crew/plugin rows) were not diffed line by line against `5d1fc5fd`;
  only the catalog *mechanism* and the crew-specific rows were re-measured.

## Re-anchor provenance - `6c497a14` -> `f2bb919b`, 2026-09-25 (T-0015)

`git diff --name-only 6c497a14 f2bb919b -- <the 23 tracked paths this note cites>` returns eight:
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `README.md`, `TODO.md`,
`plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`. `scripts/check-marketplace.py` and both install
scripts are not in it, so every function line number and catalog-array citation above stands.
Each changed file, re-read:

- `.claude-plugin/marketplace.json` - crew's `version` on `:218` only (`1.0.25` -> `1.0.28`),
  corrected above. `:217`, the description this note's count table checks, is unchanged; the
  4/34/29/34 figures were re-measured from disk at `f2bb919b` and still hold.
- `plugin/crew/.claude-plugin/plugin.json` - `version` only (`1.0.25` -> `1.0.28`); the crew
  version statement above already reads 1.0.28 from it.
- `plugin/PLUGINS.md` - crew's version row `:14` only; the `:17` count row is unchanged.
- `plugin/crew/BUDGETS.md` - `:11` figure moved (17,788 -> 17,811); now checked, see Unverified.
- `.crew/verify.json` - one new rule appended at `:243` (the `.claude/rules/` sync check,
  `verification-harness.md` owns it). The doc rule cited at `:69-78` is unchanged and still runs
  `check-marketplace.py` first.
- `README.md` - the two install-URL pins (`:12`, `:18`) only; `:168`, `:231` and `:874` did not
  move. `CHANGELOG.md` and `TODO.md` appear here only as members of the doc rule's path list.

`python3 scripts/check-marketplace.py` at `f2bb919b`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

Re-verified per-path from `f2bb919b` to `adf8d1dd` for T-0008: of the cited paths, `.claude-plugin/marketplace.json` (`:218` version only), `plugin/PLUGINS.md` (`:14` version only), `plugin/crew/.claude-plugin/plugin.json` (version only), `plugin/crew/BUDGETS.md` (`:11` figure, re-measured and matching), `.crew/verify.json` (a new `crew_refresh_check` rule appended after the `.claude/rules/` rule; the doc rule at `:69-78` is unchanged), `CLAUDE.md` (lines `:5` and `:47` unchanged), `CHANGELOG.md`, `TODO.md` and two `plugin/crew/commands/` files changed, and the crew command count re-measured unchanged at 34.

Re-verified per-path from `adf8d1dd` to `8d447a7d` for T-0008's review round 3: of the cited paths
only `.crew/verify.json` changed (one path added to rule 7, rule 23 grown); the doc rule at `:69-78`
is above both and unchanged. `python3 scripts/check-marketplace.py` at `8d447a7d` reports one
problem, the version-drift check: `plugin/crew/` changed after `1.0.36` was set at `adf8d1dd`, with
no bump.

Re-verified per-path from `8d447a7d` to `8ebbdedc` for T-0034 and T-0026's landing (`8ebbdedc` is
the crew 1.0.39 bump on top of the T-0026 merge `563f54c3`): of the cited paths,
`.claude-plugin/marketplace.json` (`:218` version only, now 1.0.39), `plugin/PLUGINS.md` (`:14`
version only), `plugin/crew/.claude-plugin/plugin.json` (version only), `plugin/crew/BUDGETS.md`
(`:11` figure, re-measured and matching), `.crew/verify.json` (T-0026's rule inserted at
`:167-172`; the doc rule at `:69-78` is above it and unchanged), `CHANGELOG.md`, `TODO.md` and four
`plugin/crew/commands/` files changed; the crew command count is still 34, and
`scripts/check-marketplace.py`, both install scripts, `CLAUDE.md`, `README.md` and
`skills/README.md` did not change. The version-drift problem recorded above is gone:
`python3 scripts/check-marketplace.py` at `8ebbdedc` prints `all checks passed`. The merge
`563f54c3` carries main's 1.0.38 and `8ebbdedc` alone sets 1.0.39, because the reviewed branch
had declared 1.0.39 at `ee7babde`, before main's `plugin/crew/` changes reached it.
Re-verified per-path from `8d447a7d` to `6d35ef8c` for T-0006 (`8d447a7d` is T-0008's pre-rebase
commit, tree-identical to `origin/main` `768a747a` for these paths): of the cited paths,
`.claude-plugin/marketplace.json` (`:218` version only, 1.0.40), `plugin/PLUGINS.md` (`:14` version
only), `plugin/crew/.claude-plugin/plugin.json` (version only), `plugin/crew/BUDGETS.md` (`:11`
figure, re-measured and matching), `.crew/verify.json` (rule 24 appended after rule 23; the doc
rule at `:69-78` is unchanged), `CHANGELOG.md` and `TODO.md` changed. `CLAUDE.md` did not.
`python3 scripts/check-marketplace.py` at `6d35ef8c`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

Re-verified per-path from `6d35ef8c` to `2bb92f32` for T-0006's review round 3: of the cited
paths, `plugin/crew/BUDGETS.md` (`:11` figure, re-measured and matching), `.crew/verify.json`
(rule 24's `seconds` and `why` only; the doc rule at `:69-78` is unchanged) and `CHANGELOG.md`
changed. `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md` and
`plugin/crew/.claude-plugin/plugin.json` were stepped back to 1.0.37 (`3ba9f727`) and re-set to
1.0.40 (`2bb92f32`) so the version is set after the last `plugin/crew/` change, which is what
`check_versions`' `version_set_at` walk needs; they end byte-identical to `6d35ef8c`. `CLAUDE.md`
did not change. `python3 scripts/check-marketplace.py` at `2bb92f32`:
`marketplace: 34 skills, 5 plugins`, `all checks passed`.

Re-verified per-path to `a0c0847e` for T-0006's landing (`a0c0847e` is the crew 1.0.40 bump on top of
`1cec9572`, the merge of T-0006 `cb125d51` into main `d3844c76`, joining this note's `8ebbdedc`
and `2bb92f32` lines): of the cited paths, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`
and `plugin/crew/.claude-plugin/plugin.json` (version only: the merge carries main's 1.0.39,
`a0c0847e` alone sets 1.0.40), `plugin/crew/BUDGETS.md` (`:11` figure, 17,973, re-measured and
matching), `.crew/verify.json` (26 rules; the doc rule at `:69-78` is above both sides' changes
and unchanged), `CHANGELOG.md` and `TODO.md` changed. `CLAUDE.md` and `README.md` did not.
`python3 scripts/check-marketplace.py` at `a0c0847e`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

Re-verified per-path from `a0c0847e` to `07ca3972` for T-0004 (`/crew:autopilot`): of the cited
paths, `.claude-plugin/marketplace.json` (`:217` description 34 -> 35 slash commands, `:218` version
1.0.41), `plugin/PLUGINS.md` (`:14` version, `:17` 35 commands), `plugin/README.md` and `README.md`
(`:414`, `:168`, `:874` - 35 commands; no line moved), `plugin/crew/.claude-plugin/plugin.json`
(version only), `plugin/crew/BUDGETS.md` (`:11`, 18,176 / 121, re-measured and matching), both
install scripts (the crew catalog row only, `:1391` / `:1174`, now 35 commands; every other array
citation unmoved), `.crew/verify.json` (T-0004's rule appended, 27 rules; the doc rule at `:69-78`
is unchanged), `CHANGELOG.md`, `TODO.md`, and `plugin/crew/commands/`/`plugin/crew/skills/` files
changed. `INSTALLATION.md` did not, so its `:252` still states 34 commands against 35 on disk.
`scripts/check-marketplace.py`, `CLAUDE.md` and `skills/README.md` did not change.
`python3 scripts/check-marketplace.py` at `07ca3972`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

Re-verified per-path from `8d447a7d` to `fc54def6` for T-0005 (`8d447a7d` is T-0008's pre-rebase
commit; T-0008 landed as `95120430`/`768a747a`): of the cited paths `.claude-plugin/marketplace.json`
(`:218` version only; `:217`'s counts unchanged), `plugin/PLUGINS.md` (`:14` version only),
`plugin/crew/.claude-plugin/plugin.json` (version only), `plugin/crew/BUDGETS.md` (`:11` figure,
re-measured: 18,006 lines, 120 files), `.crew/verify.json` (a cloud-guard rule inserted at index 6,
`:117-126`, below the doc rule at `:69-78`, which is unchanged), `CHANGELOG.md` and `TODO.md`
changed, as did files under `plugin/crew/`, which this note cites as a directory for its counts:
agents 4, commands 34, skills 29 and hook entries 34 re-counted from disk and unchanged. The other
plugins' versions were re-read from `marketplace.json` and are unchanged.
`python3 scripts/check-marketplace.py` at `fc54def6`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

## Re-anchor provenance - `fc54def6` -> `3a57b2d2`, 2026-09-26 (T-0005 Step 8)

`git diff --name-only fc54def6 3a57b2d2 -- <the paths this note cites>` returns `.crew/verify.json`
(one path added to the cloud-guard rule at `:118`, below the doc rule, which stays at `:69-78`,
re-read), `plugin/crew/BUDGETS.md` (the `:11` figure re-measured, now 18,050 lines, 120 files)
and `CHANGELOG.md` (cited by name only). The version files are byte-identical to `fc54def6`'s
crew entry.

## Re-anchor provenance - `6f96e627` + `3a57b2d2` -> `2b18f7ab`, 2026-09-26 (T-0005 landing)

`2b18f7ab` is the crew 1.0.42 bump on top of `4ed4b763`, the merge of T-0005 (`4e0abc8f`) into
main at `1e0706ac`. Both lines' provenance is above, side by side. A citation can only be wrong at
the merge when its file changed on both sides, or when a line from one side cites a file the other
side changed; each such citation was re-mapped with a line diff of the cited file and re-read with
`grep -n`/`sed -n` on the merged tree. The bump commit replaced `1.0.41` with `1.0.42` in place in
the version files and in T-0005's own version statements (no line added or removed, except one
line in `CHANGELOG.md`'s T-0005 bump note).

Of the paths this note cites, the version files, `plugin/PLUGINS.md`, `.crew/verify.json`,
`CHANGELOG.md`, `TODO.md` and `plugin/crew/BUDGETS.md` changed on both sides.

- `.claude-plugin/marketplace.json` - `:217` keeps main's description (35 slash commands, which
  `ls plugin/crew/commands/*.md` confirms); `:218` is 1.0.42, and `plugin/PLUGINS.md:14`'s
  `plugin-version:crew` claim agrees. Corrected above.
- `.crew/verify.json` - the doc rule stays at `:69-78` (rule 2); T-0005's cloud-guard rule is rule 6
  at `:117-127`. 28 rules.
- `plugin/crew/BUDGETS.md` - marker still `:10`; the figure re-measured on the merge, 18,494 lines
  across 121 files, which `check-marketplace.py` verifies (`all checks passed`).
- `CHANGELOG.md`, `TODO.md` - cited by name only.

## Re-anchor provenance - T-0042's branch line, `6f96e627` -> `068db4ff` -> `07eefac5`, 2026-09-26

Re-verified per-path from `6f96e627` to `068db4ff` for T-0042 (auto-resume round 4, crew 1.0.42).
`6f96e627` is T-0004's landing and `git diff --name-only 6f96e627 1e0706ac` returns refresh
artifacts only. Of the cited paths, `git diff --name-only 1e0706ac 068db4ff` returns
`.claude-plugin/marketplace.json` (`:218` version only, 1.0.42; `:217` unchanged),
`plugin/PLUGINS.md` (`:14` version only; `:17` unchanged), `plugin/crew/.claude-plugin/plugin.json`
(version only), `plugin/crew/BUDGETS.md` (`:11`, 18,253 / 121, re-measured and matching),
`.crew/verify.json` (rule 25's `seconds` and `why` in place; the doc rule at `:69-78` is unchanged),
`CHANGELOG.md` and `TODO.md`. `scripts/check-marketplace.py`, both install scripts, `README.md`,
`plugin/README.md`, `INSTALLATION.md`, `CLAUDE.md` and `skills/README.md` did not change, so
`INSTALLATION.md:252` still states 34 commands against 35 on disk.
`python3 scripts/check-marketplace.py` at `068db4ff`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

Re-verified per-path from `068db4ff` to `07eefac5` for T-0042 review round 1. Of the cited paths,
`git diff --name-only 068db4ff 07eefac5` returns `.crew/verify.json` (rule 25's `seconds` and `why`
in place, `:277` and `:280`; 293 lines, so the doc rule at `:69-78` and every other cited range hold) and `CHANGELOG.md` (seven lines inside
the 1.0.42 entry; cited without a line). The version files were stepped to 1.0.41 and back and
diff empty against `068db4ff`. `python3 scripts/check-marketplace.py` at `07eefac5`:
`marketplace: 34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `2b18f7ab` + `07eefac5` -> `53f5482c`, 2026-09-27 (T-0042 merges main)

`53f5482c` is T-0042's rule-26 re-measure on top of the merge of origin/main `502cb137` into its
branch (`b7727a88`) and the crew 1.0.43 bump (`52778dd1`). Of the cited paths,
`git diff --name-only 2b18f7ab 53f5482c` returns `.claude-plugin/marketplace.json` (`:218` 1.0.43;
`:217` unchanged), `plugin/PLUGINS.md` (`:14` 1.0.43; `:17` unchanged),
`plugin/crew/.claude-plugin/plugin.json` (version only), `plugin/crew/BUDGETS.md` (`:11`, 18,571
lines across 121 files, re-measured on the merge), `.crew/verify.json` (rule 26's `seconds` and
`why` in place; the doc rule at `:69-78` holds), `CHANGELOG.md` and `TODO.md` (cited by name
only). `scripts/check-marketplace.py`, both install scripts, `README.md`, `INSTALLATION.md`,
`CLAUDE.md` and `skills/README.md` did not change on either side since `2b18f7ab`, so
`INSTALLATION.md:252` still states 34 commands against 35 on disk.
`python3 scripts/check-marketplace.py` at `53f5482c`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

Re-verified per-path from `8d447a7d` to `7b667587` for T-0021 (T-0034's `c35edda5` and T-0021's
own commits in between): of the cited paths, `.claude-plugin/marketplace.json` (`:218` version
only, now 1.0.46; `:217` unchanged), `plugin/PLUGINS.md` (`:14` version only; `:17` unchanged),
`plugin/crew/.claude-plugin/plugin.json` (version only), `plugin/crew/BUDGETS.md` (`:11` figure,
re-measured and matching, see Unverified), `.crew/verify.json` (one tracker rule appended at the
end; the doc rule at `:69-78` is unchanged), `CHANGELOG.md` and `TODO.md` changed. The root
`README.md` this note cites (`:12`, `:168`, `:231`) is not in the diff; `plugin/crew/README.md`
changed (section 13c) but this note does not cite it.
`python3 scripts/check-marketplace.py` at `7b667587`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

Re-verified per-path from `7b667587` to `385eadd5` for T-0021's review round 1. `git diff --name-only 7b667587 385eadd5` returns T-0021's refresh (`bc6432b1`), the version step-back (`764c2244`) and review round 1's fix commit (`385eadd5`): `CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `brainstorm.md`, `obsidian-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set).
Of the cited paths: `plugin/crew/BUDGETS.md` (`:11` figure, re-measured and matching, see
Unverified), `CHANGELOG.md` and `TODO.md` changed; `.claude-plugin/marketplace.json`,
`plugin/PLUGINS.md` and `plugin/crew/.claude-plugin/plugin.json` were stepped back to 1.0.45 in
`764c2244` and re-set to 1.0.46 in `385eadd5`, so the version-drift check's bump commit for
1.0.46 is now `385eadd5`. The root `README.md` this note cites is not in the diff.
`python3 scripts/check-marketplace.py` was run for this refresh; its result is in the refresh
commit's message.

Re-verified per-path from `385eadd5` to `bcb77ce2` for T-0021's review round 2. `git diff --name-only 385eadd5 bcb77ce2` returns the round-1 refresh (`59de6d56`), the version step-back (`f11c72d0`) and review round 2's fix commit (`bcb77ce2`): `CHANGELOG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `fix.md`, `implement.md`, `jira-sync.md`, `sdp-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set).
Of the cited paths: `plugin/crew/BUDGETS.md` (`:11` figure, re-measured and matching, see
Unverified) and `CHANGELOG.md` changed; `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md` and
`plugin/crew/.claude-plugin/plugin.json` were stepped back to 1.0.45 in `f11c72d0` and re-set to
1.0.46 in `bcb77ce2`, so the version-drift check's bump commit for 1.0.46 is now `bcb77ce2`. The
root `README.md` this note cites is not in the diff. `python3 scripts/check-marketplace.py` at
`bcb77ce2`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `2b18f7ab` + `bcb77ce2` -> `c2ae46ab`, 2026-09-27 (T-0021 review round 3 and its merge of main)

The merge `86ea912f` joins main's `2b18f7ab` with T-0021's `bcb77ce2`; review round 3's fix commit
`629fb518` sits under it and the crew 1.0.43 bump `c2ae46ab` on top. `git diff --name-only 2b18f7ab
c2ae46ab` returns only T-0021's files (its code, commands, tests, fixtures, release files,
`.crew/verify.json`, `CHANGELOG.md`, `TODO.md`). Every citation in this note's body into those files
was re-mapped from the side of the merge its line came from (`git blame`: main's lines against
`2b18f7ab`, T-0021's against `bcb77ce2`) with a line diff, and each one whose line moved or changed
was re-read at `c2ae46ab`. Corrected here: crew's version is 1.0.43 at all three sites;
`plugin/crew/BUDGETS.md:11` reads 18,713 lines across 126 files, recomputed on the merged tree and
matching `check-marketplace.py`. No test suite was executed for this note.

## Re-anchor provenance - `c2ae46ab` -> `d276b268`, 2026-09-27 (T-0021 review round 4)

`git diff --name-only c2ae46ab d276b268` returns T-0021's test-escape and round-4 files:
`crew_tracker.py`, `brainstorm.md`, `fix.md`, three test files, `plugin/crew/README.md`,
`CHANGELOG.md`, `TODO.md` (one follow-up appended at `:5080`), two crew guides with their built
outputs, and the version files (stepped to 1.0.42 and re-set to 1.0.43 twice, net unchanged, so
crew's `version` at `.claude-plugin/marketplace.json:218` and `plugin/PLUGINS.md:14` still read
1.0.43). This note cites `plugin/crew/README.md` by name only, and `:217`, `:218`, `:14` and
`:17` were re-read and hold. `scripts/check-marketplace.py`, both install scripts, `CLAUDE.md`,
the root `README.md` and `skills/README.md` did not change. No test suite was executed for this
note.

## Re-anchor provenance - `d276b268` -> `d9cdb54c`, 2026-09-27 (T-0021 round-4 suite fixes)

`git diff --name-only d276b268 d9cdb54c` returns `plugin/crew/tests/sabotage_tracker.py`,
`plugin/crew/BUDGETS.md` and the version files (stepped to 1.0.42 and re-set to 1.0.43, net
unchanged). Corrected here: `plugin/crew/BUDGETS.md:11` reads 18,723 lines across 126 files, after
`check-marketplace.py` at `0384afc7` reported "plugin/crew/BUDGETS.md:10: claims 18,713 plugin/crew
Markdown lines, but plugin/crew/*.md currently totals 18723" (round 4 grew `plugin/crew/README.md`
by 9 lines and `fix.md` by 1); re-measured with `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l`.
crew's `version` at `.claude-plugin/marketplace.json:218` and `plugin/PLUGINS.md:14` read 1.0.43.
No test suite was executed for this note.

## Re-anchor provenance - `f0b12ee6` + `74f52fae` -> `12682e41`, 2026-09-27 (T-0021 lands on T-0042's main)

`6df1231a` merges T-0021's reviewed head `74f52fae` into main `f0b12ee6` (T-0042 landed as crew
1.0.43, PR #242), and `12682e41` bumps crew to 1.0.44. The two sides share no source file: the
paths both changed since `502cb137` are `CHANGELOG.md`, `TODO.md`, `.crew/verify.json`,
`plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, the version files and
the refresh artifacts. The conflicting provenance sections keep both sides, T-0042's first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on the merge and corrected: crew's
`version` at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json` and
`plugin/PLUGINS.md:14` read 1.0.44; `plugin/crew/BUDGETS.md:11` reads 18,800 lines across 126
files, and `git ls-files -z 'plugin/crew/*.md' | xargs -0 cat | wc -l` returns 18800 over 126.
`.crew/verify.json` is 29 rules; the doc rule at `:69-78` holds. `scripts/check-marketplace.py`
did not change. `python3 scripts/check-marketplace.py` at `12682e41`: `marketplace: 34 skills,
5 plugins`, `all checks passed`.

## Re-anchor provenance - `6f96e627` -> `eba11657`, 2026-09-26 (T-0023)

Re-verified per-path from `6f96e627` to `eba11657` for T-0023 (plain-text lifecycle routing);
`6f96e627` -> `1e0706ac` touched only refresh artifacts. Of the cited paths,
`git diff --name-only 1e0706ac eba11657` returns `.claude-plugin/marketplace.json` (`:218` version
1.0.42 only; the `:217` description is unchanged), `plugin/PLUGINS.md` (`:14` version; `:17`
unchanged; the `crew-context` hook row `:39` gained one sentence in place),
`plugin/crew/.claude-plugin/plugin.json` (version only), `.crew/verify.json` (rule 27 appended at
`:289-297`, 28 rules; the doc rule at `:69-78` is unchanged) and `CHANGELOG.md`. No command,
agent, skill or hook entry was added, so the count table stands. `plugin/crew/BUDGETS.md` did NOT
change, and `python3 scripts/check-marketplace.py` at `eba11657` reports `marketplace: 34 skills,
5 plugins` and one problem: `plugin/crew/BUDGETS.md:10: claims 18,176 plugin/crew Markdown lines,
but plugin/crew/*.md currently totals 18239` - the marked claim moved because T-0023's README and
CONFIG.md sections grew, and BUDGETS.md is outside T-0023's Touch, so it is left for the owner.

## Re-anchor provenance - `2b18f7ab` + `488053fc` -> `a1acd9b7`, 2026-09-27 (T-0023 merge of main)

`3c968175` merges main at `502cb137` (T-0005 landed, its notes anchored `2b18f7ab`) into T-0023 at
`488053fc` (review round 1's fixes); `f6abe8c1` re-sets crew to 1.0.43 and `a1acd9b7` re-prices
`.crew/verify.json` rule 28 in place. Both lines' provenance is above. A citation can only be
wrong at the merge when its file changed on both sides, or when a line from one side cites a file
the other side changed. Each line of this note was classified by origin (main's text or
T-0023's), its citations into such files re-mapped with a line diff from that side's revision to
the merged tree (`502cb137` or `fa4d8cd5`), and each moved one re-read by content with
`grep -n`/`sed -n`; citations the line diff attributed to the wrong file were discarded, not
applied. Of the paths this note cites, the version files moved to 1.0.43 in place, `.crew/verify.json` has 29 rules (T-0023's routing rule is rule 28 at `:301-309`; the doc rule at `:69-78` is unchanged), `plugin/PLUGINS.md` `:14`/`:17` hold, and `plugin/crew/BUDGETS.md` `:11` is re-measured (18,558 lines, 121 files). No command, agent, skill or hook entry was added. `python3 scripts/check-marketplace.py` on `a1acd9b7`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `db14619c` + `ad74ed35` -> `e463ca53`, 2026-09-27 (T-0023 lands on T-0021's main)

`c68b40bd` merges origin/main `db14619c` (T-0042 landed as crew 1.0.43, PR #242; T-0021 as
1.0.45, PR #243) into T-0023's `ad74ed35`, and `e463ca53` bumps crew to 1.0.46. The files both
sides changed since `502cb137` are `CHANGELOG.md`, `.crew/verify.json`, `plugin/crew/README.md`,
`plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_context.py`,
`plugin/crew/tests/sabotage.py`, the version files and the refresh artifacts. The conflicting
provenance sections keep both sides, main's first. Every `path:N` citation in the body, and every
bare `:N` that follows a path, was mapped from the side its line came from onto the merged tree
with a line diff (`git show <side>:<path>` against the merge); each one that moved was re-read
with `sed -n` and corrected, and hits the diff attributed to the wrong file (a bare `:N` after
an unrelated path) were discarded rather than applied: crew's
`version` at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json` and
`plugin/PLUGINS.md:14` read 1.0.46; `plugin/crew/BUDGETS.md:11` reads 18,864 lines across 126
files, and `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18864 over 126 (the
unresolved merge index briefly held three stages of `BUDGETS.md`, and `check-marketplace.py`
counted 18,936 until they were staged - a count to take from a clean index only).
`.crew/verify.json` is 30 rules; the doc rule at `:69-78` holds. `scripts/check-marketplace.py`
did not change. `python3 scripts/check-marketplace.py` at `e463ca53`: `marketplace: 34 skills,
5 plugins`, `all checks passed`.

Re-verified per-path from `6f96e627` to `5536c2c8` for T-0018 (`/crew:autopilot status`, crew
1.0.42): of the cited paths, `.claude-plugin/marketplace.json` (`:218` version 1.0.42; `:217`
unchanged), `plugin/PLUGINS.md` (`:14` version; `:17` unchanged),
`plugin/crew/.claude-plugin/plugin.json` (version only), `plugin/crew/BUDGETS.md` (`:11`, 18,170 /
121, re-measured and matching), `.crew/verify.json` (rule 26 gained one path and its `why`; 27
rules; the doc rule at `:69-78` is unchanged) and `CHANGELOG.md` changed. Both install scripts,
`README.md`, `plugin/README.md`, `INSTALLATION.md`, `scripts/check-marketplace.py`, `CLAUDE.md` and
`skills/README.md` did not. No command, agent or skill was added or removed.
`python3 scripts/check-marketplace.py` at `5536c2c8`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

Re-verified per-path from `5536c2c8` to `29a987b0` for T-0018's review rounds 1 and 2: of the
cited paths, `git diff --name-only 5536c2c8 29a987b0` returns `.crew/verify.json` (rule 26's
`seconds` and `why` only; 27 rules; the doc rule at `:69-78` is unchanged) and `CHANGELOG.md`. The
version files (`.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`,
`plugin/crew/.claude-plugin/plugin.json`) are at 1.0.42 on both sides. Both install scripts,
`README.md`, `plugin/README.md`, `INSTALLATION.md`, `scripts/check-marketplace.py`, `CLAUDE.md`
and `skills/README.md` did not change. No command, agent or skill was added or removed.

Re-verified per-path from `29a987b0` to `c87ac3f4` for T-0018's review round 3: of the cited
paths, `git diff --name-only 29a987b0 c87ac3f4` returns `.crew/verify.json` (rule 26's `seconds`
and `why` only; 27 rules; the doc rule at `:69-78` is unchanged) and `CHANGELOG.md`. The version
files (`.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`,
`plugin/crew/.claude-plugin/plugin.json`) are at 1.0.42 on both sides. Both install scripts,
`README.md`, `plugin/README.md`, `INSTALLATION.md`, `scripts/check-marketplace.py`, `CLAUDE.md`
and `skills/README.md` did not change. No command, agent or skill was added or removed.

Re-verified per-path from `2b18f7ab` (main) and `c87ac3f4` (the T-0018 branch) to `b1ae1500`, the
T-0018 round-4 fixes, the merge of main `502cb137` (crew 1.0.42) and the crew 1.0.43 bump: of the
cited paths, `.crew/verify.json` (the merged file: main's 28 rules with T-0018's autopilot rule
widened in place, 306 lines; the doc rule at `:69-78` is unchanged), `CHANGELOG.md` and the version
files changed. `.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14` and
`plugin/crew/.claude-plugin/plugin.json` read 1.0.43, and `:217` and `PLUGINS.md:17` still state 4
agents, 35 commands, 29 skills. `git diff --name-only 2b18f7ab b1ae1500 -- scripts/ README.md
plugin/README.md INSTALLATION.md CLAUDE.md skills/README.md` is empty. No command, agent or skill
was added or removed. `check-marketplace.py` passed at `b1ae1500`.

## Re-anchor provenance - main's `53f5482c` -> `0c7f6b84`, 2026-09-27 (T-0018, merge of origin/main `f0b12ee6`)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `11e8afe3` merged origin/main
`f0b12ee6` (T-0042, crew 1.0.43) into T-0018-router and `0c7f6b84` set crew 1.0.44 last. The merge
took main's anchor, so the check measured T-0018's own paths against it. The two sides changed no
source file in common. The files both sides changed are `.crew/verify.json`, `plugin/crew/README.md`,
`CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the three version files. Every `path:line` citation into
them in this note was compared with the same line on each side and at `0c7f6b84`:

- `.crew/verify.json` - 28 rules, 306 lines. Against T-0018's side nothing moved (main's rule 26
  `seconds` and `why` changed in place), so rule 27 is still `:293-301`. Against main's side the
  autopilot rule adds one line after `:295`.
- `plugin/crew/README.md` - main added 14 lines at `:1762`, and T-0018 added 15 lines after `:790`.
  The only citation that moved, the runbook-index line, was recomputed in the merge (`:1959`).
- `CHANGELOG.md` - cited by name, apart from one historical citation that was already recorded as
  out of scope. `plugin/crew/BUDGETS.md:11` is 18,566 over 121 files, re-measured in the merge.
- Version files - `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json`
  and `plugin/PLUGINS.md:14` read 1.0.44 at `0c7f6b84`. They were 1.0.43 on both sides of the merge.

No suite was run by this note.

## Re-anchor provenance - `db14619c` + `e6b696fb` -> `fbc27b49`, 2026-09-27 (T-0018 lands on T-0021's main)

`515346b1` merges T-0018's reviewed head `e6b696fb` (review round 6 CLEAN) into main `db14619c`
(T-0021 landed as crew 1.0.44 and 1.0.45, PR #243), and `fbc27b49` bumps crew to 1.0.46. The two
sides share no source file: the paths both changed since `f0b12ee6` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`,
`plugin/crew/tests/test_lifecycle_commands.py` (merged cleanly), the version files and the refresh
artifacts. The conflicting provenance sections keep both sides, main's (T-0021's) first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on `fbc27b49` and corrected.
Corrected here: crew is 1.0.46 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`
and `plugin/PLUGINS.md:14`; `plugin/crew/BUDGETS.md:11` reads 18,795 lines across 126 files, and
`count_crew_markdown_lines()`'s measurement (`git ls-files 'plugin/crew/*.md'`, `splitlines()` per
file) returns 18795 over 126. `python3 scripts/check-marketplace.py` at `fbc27b49`: `marketplace:
34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `55f59b04` + `bebbb97f` -> `65bb3330`, 2026-09-27 (T-0018 lands on T-0023's main)

`f458e752` merges main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244) into T-0018-land,
which had merged T-0018's reviewed head `e6b696fb` into `db14619c` and been refreshed at
`55f59b04`; `65bb3330` re-bumps crew to 1.0.47. The two sides share no source file: T-0023
changed `crew_route.py`, `crew_context.py`, `crew_config.py`, `sabotage.py` and their tests, T-0018
`crew_autopilot.py`, `autopilot.md` and theirs; both changed `CHANGELOG.md`, `.crew/verify.json`
(merged cleanly: 30 rules, 323 lines), `plugin/crew/README.md` (merged cleanly),
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's (T-0023's) first. Every `path:N` citation in the body was mapped
from the side its line came from onto the merged tree with a line diff, and each one that moved was
re-read with `sed -n` on `65bb3330` and corrected.
Corrected here: crew is 1.0.47 at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14`; `plugin/crew/BUDGETS.md:11`
reads 18,859 lines across 126 files, and the measurement (`git ls-files 'plugin/crew/*.md'`,
`splitlines()` per file) returns 18859 over 126. `python3 scripts/check-marketplace.py` at
`65bb3330`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

Re-verified per-path from `6f96e627` to `a2802526` for T-0024 (group approval, crew 1.0.42): of the
cited paths, `.claude-plugin/marketplace.json` (`:218` version 1.0.42; `:217`'s counts unchanged),
`plugin/PLUGINS.md` (`:14` version only), `plugin/crew/.claude-plugin/plugin.json` (version only),
`plugin/crew/BUDGETS.md` (`:11`, 18,200 / 121, re-measured with `git ls-files 'plugin/crew/*.md'`
and `splitlines()` per file, matching), `.crew/verify.json` (rule 27 appended, 28 rules; the doc
rule at `:69-78` is unchanged), `CHANGELOG.md` and `plugin/crew/README.md` changed. No install
script, `scripts/check-marketplace.py`, `CLAUDE.md`, `README.md` or `INSTALLATION.md` changed.
`python3 scripts/check-marketplace.py` at `a2802526`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

Re-verified per-path from `a2802526` to `32223b8a` for T-0024's review round 1 (crew 1.0.43): of the
cited paths only `.claude-plugin/marketplace.json` (`:218` 1.0.43), `plugin/PLUGINS.md` (`:14`),
`plugin/crew/.claude-plugin/plugin.json` and `CHANGELOG.md` changed; `BUDGETS.md` did not (no
`plugin/crew/*.md` changed). `python3 scripts/check-marketplace.py` at `32223b8a`: `all checks
passed`.

Re-verified per-path from `32223b8a` to `f8671fdc` for T-0024's successor step 6 (crew 1.0.44): of
the cited paths `.claude-plugin/marketplace.json` (`:218` 1.0.44), `plugin/PLUGINS.md` (`:14`),
`plugin/crew/.claude-plugin/plugin.json`, `CHANGELOG.md`, `plugin/crew/README.md` (group-approval
prose only; the `35 commands` claim `:2263` and `4 agents` `:2274` did not move) and
`plugin/crew/BUDGETS.md` (`:11`, 18,202 / 121, re-measured and matching) changed.
`python3 scripts/check-marketplace.py` at `f8671fdc`: `all checks passed`.

Re-verified per-path from `f8671fdc` to `45345812` for T-0024's review round 3 (crew 1.0.45): of the
cited paths `.claude-plugin/marketplace.json` (`:218` 1.0.45), `plugin/PLUGINS.md` (`:14`),
`plugin/crew/.claude-plugin/plugin.json`, `CHANGELOG.md` and `plugin/crew/README.md` (two
group-approval sentences, in place; `:2263`/`:2274` hold) changed; `BUDGETS.md` did not (18,202
still measures). `python3 scripts/check-marketplace.py` at `45345812`: `all checks passed`.

## Re-anchor provenance - `65bb3330` + `474aea8b` -> `8de3c669`, 2026-09-27 (T-0024 lands on T-0018's main)

`affa22a5` merges T-0024's reviewed head `474aea8b` (review round 4 FINDINGS, owner-accepted) into
main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245), and `8de3c669` bumps crew to 1.0.48.
The two sides share no source file: T-0024 changed `approval_hook.py`, both approval-hook wrappers,
`crew_ticket.py`, `commands/approve.md` and their tests; both sides changed `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md` (merged cleanly), `plugin/crew/tests/sabotage.py`,
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's first.
Corrected here: `crew` is 1.0.48 (`.claude-plugin/marketplace.json:218`, changed in place, so
`:217`'s counts hold); `plugin/crew/BUDGETS.md:11` is 18,885 across 126, recomputed from the
merged index and re-measured by `check-marketplace.py` (`all checks passed`). No other body citation
moved. No test suite was executed for this note.

**Re-anchored `53f5482c` -> `d3a1c77e` on 2026-09-27 (T-0072, crew 1.0.44).** `d3a1c77e` is T-0072's version commit on `T-0072-build`, after it merged origin/main `f0b12ee6` (T-0042's landing) with a merge commit. `git diff --name-only 53f5482c d3a1c77e` over the cited paths returns only T-0072's changes and the version files. T-0072 edited in place, with no line added or removed, `crew_state.py` (`:1084-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,612 lines across 121 files), `plugin/PLUGINS.md` (`:14` 1.0.44, the `/crew:autopilot` row), `.claude-plugin/marketplace.json` (`:218` 1.0.44), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It added lines to `crew_autopilot.py` (the `deploy-allowed` docstring section and functions, 694 -> 837 lines), `CONFIG.md` (+1 at the leaf paragraph, +1 in the key table, +1 in §20's table, a closing §20 section), `CHANGELOG.md` (+32 at the top) and the autopilot tests. Of the paths this note cites, the version files (1.0.44, corrected above), `plugin/crew/BUDGETS.md` (18,612 across 121 files, which `check-marketplace.py` verifies: `all checks passed` at `d3a1c77e`), `.crew/verify.json` (rule 27 in place) and `CHANGELOG.md` (cited without a line) changed. No marketplace entry was added, renamed or removed.

**Re-anchored `d3a1c77e` -> `e30af7f9` on 2026-09-27 (T-0072 review round 1).** `e30af7f9` is T-0072's review-round-1 fix commit on `T-0072-build`. `git diff --name-only d3a1c77e e30af7f9` returns `.crew/verify.json` (rule 27's `why` re-measured in place, still `:293-300`), `CHANGELOG.md` (the 1.0.44 entry, four lines reworded, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, now 18,615 lines across 121 files; `check-marketplace.py` prints `all checks passed`), `plugin/crew/CONFIG.md` (+3 lines in §20's closing section, at `:2317`; nothing cited above it moved, `:2251-2258` holds), `plugin/crew/hooks/scripts/crew_autopilot.py` (+24 lines: the docstring gains a line at `:88`, `_deploy_verdict` moves its `cloud_guard` import below the incident check, `_safe_text` and `_crash_reason` are new), `plugin/crew/tests/sabotage_autopilot.py` (+32: `CLOUD` at `:18`, six mutations) and `plugin/crew/tests/test_crew_autopilot_deploy.py`, plus the refresh artifacts of the previous pass. No crew version change (1.0.44). Of the paths this note cites, only `.crew/verify.json` changed, in place inside rule 27's `why`; every line it cites holds. Nothing else this note cites changed.

**Re-anchored `e463ca53` -> `715a8c2f` on 2026-09-27 (T-0072 merged onto `bebbb97f`, crew 1.0.47).** `715a8c2f` is T-0072's crew 1.0.47 version commit on `T-0072-build`, on top of `e658bb04`, its merge of origin/main `bebbb97f` (T-0021 and T-0023 landed; this note was anchored at T-0023's `e463ca53`). `git diff --name-only e463ca53 715a8c2f` over the cited paths returns only T-0072's changes, the neighbour test T-0072 added after the merge, and the version files. Against main, T-0072 edits in place, with no line added or removed, `crew_state.py` (`:1086-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (`:825`, the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,910 lines across 126 files), `plugin/PLUGINS.md` (`:14` 1.0.47, `:128` the `/crew:autopilot` row), `plugin/crew/skills/crew-setup/SKILL.md` (`:170`), `.claude-plugin/marketplace.json` (`:218` 1.0.47), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It adds lines to `crew_autopilot.py` (694 -> 861), `CONFIG.md` (+3 at the leaf paragraph `:130`, +1 at `:803`, +1 at `:2282`, and the closing §20 section at `:2297`, 41 lines, with T-0023's §21 after it), `CHANGELOG.md` (+31 at `:7`, T-0072's entry above T-0023's), `config.template.json` (+1 at `:205`), `test_crew_config.py` (+3; the count assertion is `:282`, 123), `test_crew_autopilot.py` (+2), `sabotage_autopilot.py` (+140) and the new `test_crew_autopilot_deploy.py`. Of the paths this note cites, the version files (1.0.47 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3` and the `plugin-version:crew` claim at `plugin/PLUGINS.md:14`, corrected above), `plugin/crew/BUDGETS.md` (`:11` now 18,910 lines across 126 files; the marker `:10` holds; the older `:11` figures below are history at their own anchors), `CHANGELOG.md` (T-0072's entry above T-0023's) and `.crew/verify.json` (rule 27 in place; `:69-78` holds) changed. `scripts/check-marketplace.py` printed `all checks passed` on the merge.

**Re-anchored `65bb3330` -> `21429244` on 2026-09-27 (T-0072 merged onto `67caa4b8`, crew 1.0.48).** `21429244` is T-0072's crew 1.0.48 version commit on `T-0072-build`, on top of `80d4073b`, its merge of origin/main `67caa4b8` (T-0018 landed; this note was anchored at T-0018's `65bb3330`, and nothing outside the refresh artifacts changed between `65bb3330` and `67caa4b8`). Main's side of this note was taken in the merge and T-0072's earlier refresh replayed on top (`git apply --3way` of `bebbb97f..b1ec6877`); every citation into a file either side changed was mapped with a line diff (main -> merged for main's text, `b1ec6877` -> merged for T-0072's) and each one that moved was re-read with `sed -n`. `git diff --name-only 65bb3330 21429244`, outside the refresh artifacts, returns only T-0072's files: `crew_autopilot.py` (1063 -> 1230 lines: the `deploy-allowed` docstring section and functions, and its parser at `:1140`), `CONFIG.md` (+56), `CHANGELOG.md` (+31 at the top), `commands/autopilot.md` (the settings sentence rewrapped at `:44-47`, still 100 lines), `crew_state.py` (line-neutral at `:1086-1090`), `config.template.json`, `crew-setup/SKILL.md` (`:170`), `.crew/verify.json` (rule 27 `:293-301`, same lines: `test_crew_autopilot_deploy.py` joins its paths and run), the version files (1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), `plugin/crew/BUDGETS.md:11` (18,905 lines across 126 files, re-measured on the merge), and the autopilot tests. Corrected here: crew is 1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14`; `plugin/crew/BUDGETS.md:11` reads 18,905 lines across 126 files, and `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18905 over 126. `python3 scripts/check-marketplace.py` at `21429244`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

**Re-anchored `21429244` -> `53855ea5` on 2026-09-27 (T-0072 review round 3).** `53855ea5` is T-0072's review-round-3 fix commit on `T-0072-build`. `git diff --name-only 21429244 53855ea5`, outside the refresh artifacts, returns only T-0072's files: `.crew/verify.json` (rule 27's `seconds` 16 -> 20 and its `why`, in place, still `:293-301`), `CHANGELOG.md` (T-0072's 1.0.48 entry, +4 lines, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, in place: 18,908 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (one §20 table row edited in place at `:2309`, +3 lines after `:2327`), `plugin/crew/hooks/scripts/crew_autopilot.py` (1230 -> 1252 lines: +2 in the docstring at `:90-97`, `_cannot_exclude` and `_incident(root)` at `:702-718`, `_cli_value` at `:1132`, the `deploy-allowed` printing at `:1214-1219`), `plugin/crew/tests/sabotage_autopilot.py` (+36 at `:300-335`: eight `DEPLOY_MUTATIONS`; one re-anchored in place at `:256`) and `plugin/crew/tests/test_crew_autopilot_deploy.py`. No crew version change (1.0.48). Of the paths this note cites, `plugin/crew/BUDGETS.md:11` (in place, marker still `:10`), `.crew/verify.json` (in place; the doc rule `:69-78` did not move) and `CHANGELOG.md` (a member of the doc rule's path list only) changed. No marketplace entry was added, renamed or removed; `python3 scripts/check-marketplace.py` at `53855ea5`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

**Re-anchored `8de3c669` -> `80326b1d` on 2026-09-27 (T-0072 merged onto `d2fbd408`, then review round 4's redesign, crew 1.0.49).** `ba7d5c52` merged origin/main `d2fbd408` (T-0024 landed as crew 1.0.48 at `8de3c669`) into `T-0072-build` and took main's side of every code map; T-0072's earlier refresh (`git diff 67caa4b8 2fa75f79 -- .crew/codemap/`) was replayed on top with `git apply --3way`, conflicting provenance sections keeping both sides, main's first. `80326b1d` is T-0072's crew 1.0.49 version commit, after the redesign `35733d76` (one root per answer, a tri-state path probe, a two-stage CLI fallback), its sabotage `fa4c8397`, its docs `8a40dd2c` and the rule-27 re-price `37fa7c97`. `git diff --name-only 8de3c669 80326b1d`, outside the refresh artifacts, returns only T-0072's files: `.claude-plugin/marketplace.json` (`:218` 1.0.49), `.crew/verify.json` (rule 27 in place, `:293-301`, `seconds` 16), `CHANGELOG.md` (T-0072's entry, +45 at the top), `plugin/PLUGINS.md` (`:14` 1.0.49, `:128` the `/crew:autopilot` row in place), `plugin/crew/.claude-plugin/plugin.json` (`:3`), `plugin/crew/BUDGETS.md` (`:11`, 18,939 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (2328 -> 2382 lines: the leaf paragraph `:130`, the key table `:803`, the `prodUnattended` row `:1261`, `:2282`, and section 20's closing "Production without asking" block from `:2297`), `plugin/crew/README.md` (`:848` in place), `plugin/crew/commands/autopilot.md` (`:45-48` in place, 100 lines), `crew_autopilot.py` (1312 lines), `crew_state.py` (line-neutral at `:1086-1090`), `crew-setup/SKILL.md` and `config.template.json` (the leaf), `test_crew_config.py` (`:282` asserts 123), `sabotage_autopilot.py`, `test_crew_autopilot.py` and `test_crew_autopilot_deploy.py`. crew's version in the body now reads 1.0.49 (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), and the version history names T-0072's 1.0.49 bump and main's 1.0.48; `:217`'s 4/35/29 counts are unchanged. The skill and plugin counts (34 / 5, `check-marketplace.py`) hold. Nothing was executed for this note beyond `python3 scripts/check-marketplace.py`.

**Re-anchored `80326b1d` -> `1b5b6560` on 2026-09-27 (T-0072 test fix).** `git diff --name-only 80326b1d 1b5b6560`, outside the refresh artifacts, returns only `plugin/crew/tests/test_crew_autopilot_deploy.py` (the layer_state repro now patches `crew_config.layer_state`, not `crew_state.read_text`, which `test_module_split.py` forbids) and the three version files, stepped back to 1.0.48 and re-set to 1.0.49 so the version stays the last `plugin/crew/` commit (same content as at `80326b1d`). This note cites that test file by name only. No citation moved. Nothing was executed for this note.

**Re-anchored `1b5b6560` -> `a4eb2f55` on 2026-09-28 (T-0072 merged onto `5050ea3b`, crew 1.0.50).** `a4eb2f55` is T-0072's crew 1.0.50 version commit on top of its merge of origin/main `5050ea3b` (T-0077 landed as crew 1.0.49 at `fc289446`; shipstation 1.1.1). The merge was clean. `git diff --name-only 1b5b6560 a4eb2f55`, outside the refresh artifacts, returns main's T-0077 and shipstation files - `crew_tracker.py` (+123: Windows now holds a vault write's directories by handle, `_hold_dirs` / `_held_check` replace `_parent_check`), `crew_autopilot.py` (`_rel` +6 at `:170`, so every later line moves by 6), `sabotage_autopilot.py` (+5 inside `STATUS_MUTATIONS`; the `+=` append moved `:639` -> `:644`), `sabotage_tracker.py` (87 `TRACKER_MUTATIONS`, was 81), `plugin/crew/README.md` (`:1493-1495` in place), `test_crew_tracker.py`, `test_crew_autopilot.py`, `test_crew_autopilot_status.py`, `skills/shipstation/*` - and the version files (1.0.50 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) and `CHANGELOG.md` (T-0077's and shipstation's entries under T-0072's). crew's version in the body reads 1.0.50 and the version history names T-0077's 1.0.49 and T-0072's 1.0.50; `shipstation` is not cited here. `check-marketplace.py`: 34 skills, 5 plugins, all checks passed. Nothing else was executed for this note.

**Re-anchored `a4eb2f55` -> `0f488706` on 2026-09-28 (T-0072 review round 5).** `0f488706` is T-0072's review-round-5 fix commit. `git diff --name-only a4eb2f55 0f488706`, outside the refresh artifacts (`0282cb5c`, `37fa2322`), returns only T-0072's files: `plugin/crew/hooks/scripts/crew_autopilot.py` (`_resolve_root` +4 at `:729`, refusing a root that is not text, so every line after it moves by 4: `_layer_problem` `:744`, `_decide` `:759`, `deploy_allowed` `:836`, `_failure` `:1170`, `_cli_deploy` `:1194`, `main` `:1225`; `--json` dumps without indent, in place; the module docstring re-worded in place, `:87-104`), `plugin/crew/tests/sabotage_autopilot.py` (+30 inside `DEPLOY_MUTATIONS`, 64 entries by `len()`: the `AUTOPILOT_MUTATIONS + DEPLOY_MUTATIONS` append moved `:443` -> `:473`, `STATUS_MUTATIONS`' `:644` -> `:674`), `plugin/crew/tests/test_crew_autopilot_deploy.py`, `plugin/crew/CONFIG.md` (one sentence in section 20 re-worded in place, `:2331-2333`, no line added) and `CHANGELOG.md`. This note cites those files by name or at lines above the change; no citation moved. No suite was executed for this note.

## Re-anchor provenance - `8de3c669` -> `a6e81869`, 2026-09-27 (T-0079 on its branch)

`T-0079-read` was cut from `67caa4b8`, merged main `d2fbd408` (T-0024 landed; its refresh `fdc54ce9`
changed refresh artifacts only) in `f034ef5c`, and carries T-0079's commits through `a6e81869`
(crew 1.0.49). `git diff --name-only 8de3c669 a6e81869`, refresh artifacts aside, returns T-0079's
files only: `review_verdict.py`, `review_prompt.py`, `review_run.py`, their tests and
`sabotage_review.py`, `agents/reviewer.md`, `plugin/crew/README.md` (line-neutral), `CHANGELOG.md`
and the three version files. Every body citation into those files was compared by script between
`8de3c669` and `a6e81869` at the same line.
Corrected here: `crew` is 1.0.49 (`.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14`, each changed in place), in the
body's version sentence too. No other citation moved. Nothing was executed for this note.

## Re-anchor provenance - `a6e81869` -> `81685adf`, 2026-09-27 (T-0079 merges main, Step 7, re-bump)

`T-0079-read` gained T-0079's Step 7 (`8f7c62dd`, one `find` string in
`plugin/crew/tests/sabotage_webtest.py`), merged main `f96e9ec9` (T-0077 landed, crew 1.0.49) in
`548ee44e`, and re-bumped crew to 1.0.50 in `81685adf`. `git diff --name-only a6e81869 81685adf`,
refresh artifacts aside, returns that `sabotage_webtest.py`, T-0077's files (`crew_tracker.py`,
`crew_autopilot.py`, `sabotage_tracker.py`, `sabotage_autopilot.py`, `test_crew_tracker.py`,
`test_crew_autopilot.py`, `test_crew_autopilot_status.py`), `plugin/crew/README.md` (line-neutral
on both sides), `CHANGELOG.md` and the three version files. Every body citation of the form
`path:line` into those files was compared by script between `a6e81869` and `81685adf`.
The version sentence moves to 1.0.50; no other citation moved. Nothing was executed for this note.

**Re-anchored `0f488706` -> `9631c707` on 2026-09-28 (T-0072 landing, crew 1.0.51).** `9631c707` is T-0072's landing bump on `T-0072-land`, after `34af80ef` merged the reviewed `T-0072-build` (`a0978df6`) onto main `e6e10432` (T-0079 landed as crew 1.0.50) and `bf0c513a` re-priced verify rule 27. `git diff --name-only 0f488706 9631c707`, refresh artifacts aside, returns T-0079's files, the three version files, `CHANGELOG.md` and `.crew/verify.json`. The two this note's citations reach changed in place: `.crew/verify.json` `:298` and `:301` (rule 27's `seconds` 16 -> 18 and its `why`, still `:293-301`) and `plugin/crew/README.md` `:735` and `:739` (T-0079's verdict table, line-neutral); no citation moved. The version sentence moves to 1.0.51. No suite was executed for this note.

**Re-anchored `9631c707` -> `051f9e85` on 2026-09-28 (T-0091).** `051f9e85` is T-0091's one commit on `T-0091-build`, off main `f54af3fa`. `git diff --name-only 9631c707 f54af3fa -- <every tracked path this note cites>` is empty; `f54af3fa..051f9e85` changes only `CLAUDE.md` (the Landmines truncating-`open` entry's measurement paragraph, now `:185-212`, +28/-18, so every later line moves +10) and `TODO.md` (one entry closed at `:4473`, three lines appended at `:4480-4482`). This note's `CLAUDE.md` citations, `:5` and `:47`, sit above the changed paragraph and still read as quoted (re-read). No claim moved. Nothing was executed.

**Re-anchored `051f9e85` -> `c192b83d` on 2026-09-28 (T-0091 review round 1).** `c192b83d` is T-0091's review-round-1 fix on `T-0091-build`. `git diff --name-only 051f9e85 c192b83d` returns only `CLAUDE.md`: the same Landmines truncating-`open` measurement paragraph, now `:185-219` (+16/-9, so every later line moves +7; lines above `:192` are byte-identical). This note's `CLAUDE.md` citations, `:5` and `:47`, sit above the paragraph and still read as quoted (re-read). No claim moved. Nothing was executed.

**Re-anchored `9631c707` -> `79127fa1` on 2026-09-28 (T-0090 on `T-0090-build`, no crew change).** `git diff --name-only 9631c707 79127fa1`, refresh artifacts aside, returns T-0090's files only: `SECURITY.md` (a Scope bullet for `mcp-servers/` and one "what counts" bullet for the Graph token origin pin), `CHANGELOG.md` (T-0090's Security entry at the top of `[Unreleased]`) and eleven files under `mcp-servers/` (the pin and the npm packages' 0.2.1 bump). This note names `SECURITY.md` and `CHANGELOG.md` only as members of `.crew/verify.json`'s doc-rule path list (`:69-78`, unchanged), and cites nothing under `mcp-servers/`; no citation moved. No marketplace entry, version or install script changed: `grep -c mcp-servers .claude-plugin/marketplace.json` is 0 and `python3 scripts/check-marketplace.py` at `79127fa1` printed `marketplace: 34 skills, 5 plugins`, `all checks passed`.
