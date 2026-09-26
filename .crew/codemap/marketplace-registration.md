anchor: useful-claude-add-ons@6f96e627
verified: 2026-09-26
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
`rule-of-two`. `crew` is now **1.0.41** (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json`
and the `plugin-version:crew` claim at `plugin/PLUGINS.md:14` all agree, re-read at `07ca3972`; it
was 1.0.40 at `a0c0847e`, 1.0.39 at `8ebbdedc`, 1.0.38 at `c35edda5`, 1.0.37 at `768a747a`, 1.0.36 at `adf8d1dd`, 1.0.28 at `f2bb919b`, 1.0.25 at `6c497a14` and 0.20.11 at `5d1fc5fd`);
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
