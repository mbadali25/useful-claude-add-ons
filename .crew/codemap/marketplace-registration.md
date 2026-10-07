anchor: useful-claude-add-ons@5479ac05
verified: 2026-10-01
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
marketplace file in this repo — stated as policy at `CLAUDE.md:5` and `:59`,
enforced at `scripts/check-marketplace.py:104-131` (`check_registration`,
unmoved from the previous anchor), which walks every on-disk entry directory
and fails if `<dir>/.claude-plugin/marketplace.json` exists.

## Counts, measured fresh: 39 entries, 34 skills, 5 plugins

**DERIVED**, by the same method the previous anchor used — partition
`marketplace.json`'s flat `plugins` array by `source` prefix
(`./skills/` vs `./plugin/`) — and independently confirmed by running the
gate. `scripts/check-marketplace.py:1705-1706` still derives `plugins` as
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
`rule-of-two`. `crew` is now **1.0.97** (L-0516's re-bump at its review round 1 fix commit `7904a4ba`, which changed `plugin/crew/` after 1.0.93 was set at `083cda66`, skipping 1.0.94 (L-0510), 1.0.95 (L-0558 #293) and 1.0.96 (L-0557, T-0110 #297); before that 1.0.93, L-0516's re-bump at the commit after merging main `64b04c6b` (W-0116 #292, main's 1.0.89), which changed `plugin/crew/` after 1.0.92 was set at `a9c0d9ab`, skipping 1.0.90 (T-0040 #290), 1.0.91 (T-0505 #296), 1.0.94 (L-0510), 1.0.95 (L-0558 #293) and 1.0.96 (L-0557); 1.0.92 was L-0516's re-bump at the commit after `e49eeceb`, the pylint R1732 fix in `plugin/crew/tests/test_poll_fixtures.py` that changed `plugin/crew/` after 1.0.91 was set at `7ecbdc7f`, and skipping 1.0.89 (L-0563, L-0557); 1.0.91 was L-0516's re-bump at the commit after `b00b90a8`, because the tooling-PR split changed `plugin/crew/` after 1.0.89 was set at `5ab63076`; past main's 1.0.86 (L-0520 #287), skipping 1.0.87 (L-0558), 1.0.88 (T-0040 #290) and 1.0.90 (L-0510); main's 1.0.86 is L-0520 PR 1's re-set at `14b52c91` after merging main `bd4b2f30`, past main's 1.0.85 and skipping 1.0.84, which T-0505 targets; 1.0.84 on L-0520's branch at `e60d88f2`; main's 1.0.85 is T-0028's re-set at `328fdf4a` after the round-7 fixes, first set at `f4adf923`, past main's 1.0.83 and skipping 1.0.84, which T-0505 targets; 1.0.84 at `c43a54c1`, one past main's 1.0.83, T-0099's landing #278, which this note on main still read as 1.0.82; 1.0.82 is L-0531's sabotage entries for L-0529's fixture, one past main's 1.0.81 after merging `42d5ef58`; main's 1.0.81 is T-0094's landing re-set, one past origin/main's 1.0.80 after T-0094 merged `d1462bbd`; main's 1.0.80 is L-0529's test-fixture fix, past main's 1.0.77 (T-0086) with 1.0.78 and 1.0.79 declared by open branches; before that 1.0.76, T-0087's re-set on `T-0087-build`, one past main's 1.0.75 after merging `9af34e57`, T-0085's landing; 1.0.70 at T-0087's re-set `90b71bbf`, one past main's 1.0.69 after merging `a61a6f38`; main's 1.0.75 is T-0085's landing: 1.0.70 at its merge of main's 1.0.69 at `a61a6f38`, 1.0.71 after one landing-branch sabotage anchor commit, 1.0.72 after rewrapping `commands/review.md` to its line allowance, 1.0.73 at its catch-up merge of main's 1.0.70 at `6813749b` (#268, T-0097), 1.0.74 for the Windows fail-open fix in `gate_applies` at `9b6b0da7`, 1.0.75 for re-targeting the sabotage entry that fix made vacuous; before that **1.0.61**, T-0010's landing re-set `bbd9a66d` after its landing-branch lint fixes; 1.0.60 at T-0010's re-set `cd106b8b`, one past main's 1.0.59 after T-0010-solo merged main `e878cc31`; on T-0010-solo it was 1.0.55 at `d7c7c75c`, 1.0.51 at `360c4029` and 1.0.50 at `50a275ea`; main's 1.0.59 is T-0075's landing bumps: 1.0.59 for the refused-probe F821 fix, 1.0.58 for re-anchored sabotage entries, 1.0.56 for the landing branch's pylint disable, 1.0.57 for the Windows path fix in the OS-error refusals; `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json`
and the `plugin-version:crew` claim at `plugin/PLUGINS.md:14` all agree, re-read at `cd106b8b` and again on T-0085's merge of main `8ab733d7`: T-0085's build branch declares main's version and carries no bump of its own until land, `.crew/standards.md` REPO-03; on T-0085's branch it was 1.0.59 from its merge of `2693d0fa` to `33521aa4`, 1.0.56 at `8abf7ffe`, reverted by `0fd1bdf8`, 1.0.55 at `8a084c6c`, 1.0.53 at `2aa49bb8` and `b82035e6`, and 1.0.52 at `22399a9c`); it was 1.0.55 at `3648f59a`, T-0075's re-bump one past main after its merge of `6387ab49`; on T-0075's branch it was 1.0.52 at `938e3b11` (its re-bump after its merge of `f54af3fa`), 1.0.51 at `3724731b`, 1.0.50 at `8cabe586`, 1.0.49 at `7d217751`, `81ed193c` and `ca667718`, 1.0.48 at `23371afb`, 1.0.47 at `f7163410`, 1.0.46 at `e95e5964` and 1.0.44 at `d2444be9`; on main it was 1.0.54 at `6387ab49` and `2442d367` (T-0092's landing merge onto main `311dab8c`, whose 1.0.54 is T-0092's re-bump `136f4b33` after merging main `ff59160f`); it was 1.0.53 at main `311dab8c` and `ff59160f` (T-0089's landing bump `0f526a8c`) and at `3c4f1a68`, T-0092's re-bump after merging main `c426c018`; it was 1.0.52 at `c426c018` (T-0076's landing, `e329eb8f`) and at `c99e31f6`, T-0092's first bump; it was 1.0.51 at `9631c707`, T-0072's landing bump after its merge of `e6e10432`; it was 1.0.50 at `a4eb2f55`, T-0072's bump after its merge of `5050ea3b`, and at main `e6e10432`, T-0079's landing, bumped on T-0079's branch at `81685adf`, where it was 1.0.49 at `78215930`; it was 1.0.49 at `fc289446` (T-0077's landing bump) and on T-0072's branch at `80326b1d`, 1.0.48 at `8de3c669` (T-0024's landing bump) and on T-0072's branch at `21429244` and `996a0a9e`, 1.0.47 at `67caa4b8` after T-0018's re-bump `65bb3330` on its merge of
main `bebbb97f` (`f458e752`), 1.0.47 on T-0072's branch at `715a8c2f`, 1.0.46 at `bebbb97f` and at that merge (T-0023's bump `e463ca53`) and at T-0018's first landing bump `fbc27b49`, 1.0.45 at `db14619c` (T-0021, bumped again for a CI fix), 1.0.44 on T-0018's branch at `0c7f6b84`, 1.0.43 on T-0023's branch at `a1acd9b7` and on T-0018's at `39f8f59f`, 1.0.44 at `12682e41`, 1.0.43 at `f0b12ee6` (T-0042) and on T-0021's branch at `c2ae46ab`, 1.0.42 at `2b18f7ab` (1.0.46 on T-0021's branch until its merge of main), 1.0.41 at `07ca3972` and on T-0005's branch, 1.0.40 at `a0c0847e`, 1.0.39 at `8ebbdedc`, 1.0.38 at `c35edda5`, 1.0.37 at `768a747a`, 1.0.36 at `adf8d1dd`, 1.0.28 at `f2bb919b`, 1.0.25 at `6c497a14` and 0.20.11 at `5d1fc5fd`);
`obsidian-vault` is **0.4.15** (L-0529's test-fixture fix; 0.4.14 before, was 0.3.14); `gizmoduck` (0.5.3) and
`rule-of-two` (0.1.3) are unchanged; `localgpu` moved to 0.1.20.

## Crew's own description agrees with disk, one site excepted

**DERIVED, re-measured at `07ca3972`; the command count re-measured at `e95e5964`; the skills count re-measured at `f5d0f1b1`.**
`.claude-plugin/marketplace.json:217` — crew's `description` — reads "4
context-isolated agents (explorer, reviewer, security, researcher) …, 36
slash commands, 33 bundled skills … 34 hook entries" (33 since L-0537 added `stack-node`, 32 since L-0533 added `stack-php`; 29 until T-0085 and #267, 30 on each branch alone). Measured independently
against disk:

| Claim | Stated | On disk | Where |
|---|---|---|---|
| agents | 4 | `ls plugin/crew/agents/*.md` → 4 | `.claude-plugin/marketplace.json:217`, `plugin/PLUGINS.md:17`, `README.md:168`/`:887`, `INSTALLATION.md:252`, `plugin/README.md:414` |
| commands | 36 | `find plugin/crew/commands -name '*.md'` → 36 (T-0004 added `autopilot.md`, T-0075 `config-setup.md`) | same sites **except `INSTALLATION.md:252`, which still reads "34 slash commands"** — unmarked, so no check catches it |
| skills | 33 | `find plugin/crew/skills -maxdepth 1 -mindepth 1 -type d` → 33 (L-0537 added `stack-node`, L-0533 `stack-php`; T-0085 added `crew-standards`, #267 `crew-qa-standards`; both read 30 on their own branches, 31 from T-0085's landing merge) | same sites, each `<!-- claim: plugin-skills:crew -->`-marked; **at `22399a9c` `INSTALLATION.md:252` and `plugin/README.md:414` still read 29** (outside T-0085's Touch), so `check_self_claims` fails on both; both read 30 from `b82035e6` (the Touch amendment) and the check passes |
| hook entries | 34 | walking `plugin/crew/hooks/hooks.json`'s 8 events → 34 command entries | same sites |

Both install scripts' own crew catalog row (`scripts/install-prerequisites.sh:1393`,
`scripts/install-prerequisites.ps1:1175`) states "4 agents, 36 commands" and
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
| `.sh` install script | `SKILL_KEYS`/`SKILL_NAME`/`SKILL_SPEC`, `scripts/install-prerequisites.sh:1298-...` | `PLUGIN_KEYS`/`PLUGIN_NAME`/`PLUGIN_SPEC`, `scripts/install-prerequisites.sh:1385-1395` |
| `.ps1` install script | `$script:SkillCatalog`, `scripts/install-prerequisites.ps1:1127` | `$script:PluginCatalog`, `scripts/install-prerequisites.ps1:1174` |
| Own manifest version | none | `plugin/<name>/.claude-plugin/plugin.json`, bumped in lockstep with the marketplace entry |

Both install-script catalog rows for `crew` (`scripts/install-prerequisites.sh:1393`,
`scripts/install-prerequisites.ps1:1175`) both read "4 agents, 36 commands,
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

- **`TEAM_KEYS`** (`scripts/install-prerequisites.sh:1424`) is unchanged at
  **four**: `superpowers`, `frontend-design`, `excalidraw-generator`,
  `github` — all four resolving through `claude-plugins-official`.
- **`COMMUNITY_KEYS`** (`scripts/install-prerequisites.sh:1450-1452`) is
  **eight**: `adhd-output-style`, `azure-tools`, `anthropic-office-skills`,
  `agent-browser`, `ppt-master`, `voltagent-infra`, `voltagent-qa-sec`,
  `eli5` — resolving through **five** distinct marketplace names
  (`claude-settings`, `agent-browser`, `ppt-master`, `voltagent-subagents`,
  `claude-community`), confirmed by reading `COMMUNITY_SPEC`
  (`:1461-1470`). The comment at `scripts/install-prerequisites.sh:1442-1443`
  still states explicitly that the local name is `claude-community`, not
  `claude-plugins-community`.

`$script:CommunityCatalog` (`scripts/install-prerequisites.ps1:1206`) and
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
`main()` (`:1679-1715`) calls all seventeen checks, `check_versions` included,
at `:1699` in call order (T-0048 added `check_config_reference` at `:1701`). `_verify/smoke.sh` is confirmed byte-identical to
`5d1fc5fd` (`git diff --stat` empty) — its `run_marketplace_check()`
(`:72-98`) still exposes the same six named groups calling the same eight
functions (`registration`, `skills`, `plugins`, `catalogs`, `menus`,
`hooks`), so the gap is now **nine of seventeen**: `check_versions`,
`check_self_claims`, `check_config_reference`, `check_crew_ignore_policy`,
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
(`.crew/verify.json:96-105`) runs `python3 scripts/check-marketplace.py` as
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
- `scripts/check-marketplace.py:1679` — `main()`, seventeen checks in the same
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
  Re-measured on T-0010-solo's merge of `f96e9ec9`, at `48b2820d`: 18,953 across 126 files on
  `:11`, recomputed from the merged tree with `git ls-files 'plugin/crew/*.md'` rather than taken
  from either side (main's `f96e9ec9` read 18,885 across 126; T-0010-solo's `216ee85f` read 18,923
  across 126), matching; `check-marketplace.py` passes it. On T-0010-solo's earlier merge of
  `67caa4b8`, at `c817782f`: 18,917 across 126. On T-0024's landing merge into `67caa4b8`: 18,885
  across 126 (main's `67caa4b8` read 18,859; T-0024's `474aea8b` 18,202 across 121).
  Re-measured at `ea764992` (T-0094): 19,432 across 128 files on `:11`, and
  `check-marketplace.py`'s `check_self_claims` passes it (exit 0, "all checks passed").
  Re-measured at `ef5b4c89` (T-0094 after merging `8ab733d7`, main's 19,494, and its round-2
  README edits): 19,500 across 128 files on `:11`, recomputed with `git ls-files 'plugin/crew/*.md'`
  rather than taken from either side; `check-marketplace.py` passes it at `fc348c89` ("all checks passed").
  Re-measured on T-0028 at `328fdf4a`: 21,515 lines across 137 files on `:11` (21,513 at `c43a54c1`) (T-0028's Kimi docs
  and the fixture README over main's `6a8c60b1`), matching; `check-marketplace.py` passes it.
  Re-measured on T-0094's merge of `a61a6f38` (main's 19,915 across 132): 19,921 across 132 files on
  `:11`, recomputed from the merged tree the same way; `check-marketplace.py` passes it at `f5d0f1b1`
  ("all checks passed").
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

## Re-anchor provenance - T-0010-solo's branch line, `2b18f7ab` -> `50e67586`, 2026-09-27 (crew 1.0.43 on its branch)

T-0010's code commit was cherry-picked off `origin/main` (`502cb137`) as `0fc5b069`, apart from
T-0018 and T-0024, and the version set in `50e67586`. Every `path:line` citation this note makes into
a path T-0010 changed was mapped from the `2b18f7ab` tree with `difflib`; each one that moved
was re-pointed and compared line for line with the anchor tree at `50e67586`.

Of the cited paths the version files (1.0.43 at `.claude-plugin/marketplace.json:218`,
`plugin/PLUGINS.md:14`, `plugin/crew/.claude-plugin/plugin.json`), `plugin/crew/BUDGETS.md`
(`:11`, 18,524 / 121, re-measured with `git ls-files 'plugin/crew/*.md'` and `splitlines()`),
`.crew/verify.json` (T-0010's rule 28 appended; 29 rules; the doc rule `:69-78` unchanged) and
`CHANGELOG.md` changed. No install script, `scripts/check-marketplace.py`, `CLAUDE.md`,
`README.md` or `INSTALLATION.md` changed; no command, agent or skill was added or removed.
`python3 scripts/check-marketplace.py`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `53f5482c` + `50e67586` -> `89c9ee9a`, 2026-09-27 (T-0010-solo merges main, crew 1.0.44)

`89c9ee9a` is T-0010's crew 1.0.44 version commit on top of `132c1758`, the merge of origin/main
`f0b12ee6` (T-0042 landed at 1.0.43) into T-0010-solo. Both lines' provenance is above. Main-side
citations were mapped through `git diff origin/main 89c9ee9a`, the branch-side ones through
`git diff 708db116 89c9ee9a`, with `difflib` over every repo-relative `path:line` citation, and
every moved or merge-set one re-read with `sed -n` at `89c9ee9a`:

Of the cited paths the version files (1.0.44 at `.claude-plugin/marketplace.json:218`,
`plugin/PLUGINS.md:14`, `plugin/crew/.claude-plugin/plugin.json`; corrected above),
`plugin/crew/BUDGETS.md` (`:11`, 18,601 / 121, re-measured on the merge), `.crew/verify.json`
(both sides' rules; 29 rules, 311 lines; the doc rule `:69-78` unchanged), `CHANGELOG.md` and
`TODO.md` (cited by name only) changed. No install script, `scripts/check-marketplace.py`,
`CLAUDE.md`, `README.md` or `INSTALLATION.md` changed on either side, so `INSTALLATION.md:252`
still states 34 commands against 35 on disk. `python3 scripts/check-marketplace.py` at
`89c9ee9a`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

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

**Re-anchored `e463ca53` -> `715a8c2f` on 2026-09-27 (T-0072 merged onto `bebbb97f`, crew 1.0.47).** `715a8c2f` is T-0072's crew 1.0.47 version commit on `T-0072-build`, on top of `e658bb04`, its merge of origin/main `bebbb97f` (T-0021 and T-0023 landed; this note was anchored at T-0023's `e463ca53`). `git diff --name-only e463ca53 715a8c2f` over the cited paths returns only T-0072's changes, the neighbour test T-0072 added after the merge, and the version files. Against main, T-0072 edits in place, with no line added or removed, `crew_state.py` (`:1086-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (`:843`, the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,910 lines across 126 files), `plugin/PLUGINS.md` (`:14` 1.0.47, `:128` the `/crew:autopilot` row), `plugin/crew/skills/crew-setup/SKILL.md` (`:170`), `.claude-plugin/marketplace.json` (`:218` 1.0.47), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It adds lines to `crew_autopilot.py` (694 -> 861), `CONFIG.md` (+3 at the leaf paragraph `:130`, +1 at `:803`, +1 at `:2282`, and the closing §20 section at `:2297`, 41 lines, with T-0023's §21 after it), `CHANGELOG.md` (+31 at `:7`, T-0072's entry above T-0023's), `config.template.json` (+1 at `:205`), `test_crew_config.py` (+3; the count assertion is `:282`, 123), `test_crew_autopilot.py` (+2), `sabotage_autopilot.py` (+140) and the new `test_crew_autopilot_deploy.py`. Of the paths this note cites, the version files (1.0.47 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3` and the `plugin-version:crew` claim at `plugin/PLUGINS.md:14`, corrected above), `plugin/crew/BUDGETS.md` (`:11` now 18,910 lines across 126 files; the marker `:10` holds; the older `:11` figures below are history at their own anchors), `CHANGELOG.md` (T-0072's entry above T-0023's) and `.crew/verify.json` (rule 27 in place; `:69-78` holds) changed. `scripts/check-marketplace.py` printed `all checks passed` on the merge.

**Re-anchored `65bb3330` -> `21429244` on 2026-09-27 (T-0072 merged onto `67caa4b8`, crew 1.0.48).** `21429244` is T-0072's crew 1.0.48 version commit on `T-0072-build`, on top of `80d4073b`, its merge of origin/main `67caa4b8` (T-0018 landed; this note was anchored at T-0018's `65bb3330`, and nothing outside the refresh artifacts changed between `65bb3330` and `67caa4b8`). Main's side of this note was taken in the merge and T-0072's earlier refresh replayed on top (`git apply --3way` of `bebbb97f..b1ec6877`); every citation into a file either side changed was mapped with a line diff (main -> merged for main's text, `b1ec6877` -> merged for T-0072's) and each one that moved was re-read with `sed -n`. `git diff --name-only 65bb3330 21429244`, outside the refresh artifacts, returns only T-0072's files: `crew_autopilot.py` (1063 -> 1230 lines: the `deploy-allowed` docstring section and functions, and its parser at `:1140`), `CONFIG.md` (+56), `CHANGELOG.md` (+31 at the top), `commands/autopilot.md` (the settings sentence rewrapped at `:44-47`, still 100 lines), `crew_state.py` (line-neutral at `:1086-1090`), `config.template.json`, `crew-setup/SKILL.md` (`:170`), `.crew/verify.json` (rule 27 `:293-301`, same lines: `test_crew_autopilot_deploy.py` joins its paths and run), the version files (1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), `plugin/crew/BUDGETS.md:11` (18,905 lines across 126 files, re-measured on the merge), and the autopilot tests. Corrected here: crew is 1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14`; `plugin/crew/BUDGETS.md:11` reads 18,905 lines across 126 files, and `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` returns 18905 over 126. `python3 scripts/check-marketplace.py` at `21429244`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

**Re-anchored `21429244` -> `53855ea5` on 2026-09-27 (T-0072 review round 3).** `53855ea5` is T-0072's review-round-3 fix commit on `T-0072-build`. `git diff --name-only 21429244 53855ea5`, outside the refresh artifacts, returns only T-0072's files: `.crew/verify.json` (rule 27's `seconds` 16 -> 20 and its `why`, in place, still `:293-301`), `CHANGELOG.md` (T-0072's 1.0.48 entry, +4 lines, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, in place: 18,908 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (one §20 table row edited in place at `:2309`, +3 lines after `:2327`), `plugin/crew/hooks/scripts/crew_autopilot.py` (1230 -> 1252 lines: +2 in the docstring at `:90-97`, `_cannot_exclude` and `_incident(root)` at `:702-718`, `_cli_value` at `:1132`, the `deploy-allowed` printing at `:1214-1219`), `plugin/crew/tests/sabotage_autopilot.py` (+36 at `:300-335`: eight `DEPLOY_MUTATIONS`; one re-anchored in place at `:256`) and `plugin/crew/tests/test_crew_autopilot_deploy.py`. No crew version change (1.0.48). Of the paths this note cites, `plugin/crew/BUDGETS.md:11` (in place, marker still `:10`), `.crew/verify.json` (in place; the doc rule `:69-78` did not move) and `CHANGELOG.md` (a member of the doc rule's path list only) changed. No marketplace entry was added, renamed or removed; `python3 scripts/check-marketplace.py` at `53855ea5`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

**Re-anchored `8de3c669` -> `80326b1d` on 2026-09-27 (T-0072 merged onto `d2fbd408`, then review round 4's redesign, crew 1.0.49).** `ba7d5c52` merged origin/main `d2fbd408` (T-0024 landed as crew 1.0.48 at `8de3c669`) into `T-0072-build` and took main's side of every code map; T-0072's earlier refresh (`git diff 67caa4b8 2fa75f79 -- .crew/codemap/`) was replayed on top with `git apply --3way`, conflicting provenance sections keeping both sides, main's first. `80326b1d` is T-0072's crew 1.0.49 version commit, after the redesign `35733d76` (one root per answer, a tri-state path probe, a two-stage CLI fallback), its sabotage `fa4c8397`, its docs `8a40dd2c` and the rule-27 re-price `37fa7c97`. `git diff --name-only 8de3c669 80326b1d`, outside the refresh artifacts, returns only T-0072's files: `.claude-plugin/marketplace.json` (`:218` 1.0.49), `.crew/verify.json` (rule 27 in place, `:293-301`, `seconds` 16), `CHANGELOG.md` (T-0072's entry, +45 at the top), `plugin/PLUGINS.md` (`:14` 1.0.49, `:128` the `/crew:autopilot` row in place), `plugin/crew/.claude-plugin/plugin.json` (`:3`), `plugin/crew/BUDGETS.md` (`:11`, 18,939 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (2328 -> 2382 lines: the leaf paragraph `:130`, the key table `:803`, the `prodUnattended` row `:1261`, `:2282`, and section 20's closing "Production without asking" block from `:2297`), `plugin/crew/README.md` (`:866` in place), `plugin/crew/commands/autopilot.md` (`:45-48` in place, 100 lines), `crew_autopilot.py` (1312 lines), `crew_state.py` (line-neutral at `:1086-1090`), `crew-setup/SKILL.md` and `config.template.json` (the leaf), `test_crew_config.py` (`:282` asserts 123), `sabotage_autopilot.py`, `test_crew_autopilot.py` and `test_crew_autopilot_deploy.py`. crew's version in the body now reads 1.0.49 (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), and the version history names T-0072's 1.0.49 bump and main's 1.0.48; `:218`'s 4/35/29 counts are unchanged. The skill and plugin counts (34 / 5, `check-marketplace.py`) hold. Nothing was executed for this note beyond `python3 scripts/check-marketplace.py`.

**Re-anchored `80326b1d` -> `1b5b6560` on 2026-09-27 (T-0072 test fix).** `git diff --name-only 80326b1d 1b5b6560`, outside the refresh artifacts, returns only `plugin/crew/tests/test_crew_autopilot_deploy.py` (the layer_state repro now patches `crew_config.layer_state`, not `crew_state.read_text`, which `test_module_split.py` forbids) and the three version files, stepped back to 1.0.48 and re-set to 1.0.49 so the version stays the last `plugin/crew/` commit (same content as at `80326b1d`). This note cites that test file by name only. No citation moved. Nothing was executed for this note.

**Re-anchored `1b5b6560` -> `a4eb2f55` on 2026-09-28 (T-0072 merged onto `5050ea3b`, crew 1.0.50).** `a4eb2f55` is T-0072's crew 1.0.50 version commit on top of its merge of origin/main `5050ea3b` (T-0077 landed as crew 1.0.49 at `fc289446`; shipstation 1.1.1). The merge was clean. `git diff --name-only 1b5b6560 a4eb2f55`, outside the refresh artifacts, returns main's T-0077 and shipstation files - `crew_tracker.py` (+123: Windows now holds a vault write's directories by handle, `_hold_dirs` / `_held_check` replace `_parent_check`), `crew_autopilot.py` (`_rel` +6 at `:170`, so every later line moves by 6), `sabotage_autopilot.py` (+5 inside `STATUS_MUTATIONS`; the `+=` append moved `:639` -> `:644`), `sabotage_tracker.py` (87 `TRACKER_MUTATIONS`, was 81), `plugin/crew/README.md` (`:1511-1513` in place), `test_crew_tracker.py`, `test_crew_autopilot.py`, `test_crew_autopilot_status.py`, `skills/shipstation/*` - and the version files (1.0.50 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) and `CHANGELOG.md` (T-0077's and shipstation's entries under T-0072's). crew's version in the body reads 1.0.50 and the version history names T-0077's 1.0.49 and T-0072's 1.0.50; `shipstation` is not cited here. `check-marketplace.py`: 34 skills, 5 plugins, all checks passed. Nothing else was executed for this note.

**Re-anchored `a4eb2f55` -> `0f488706` on 2026-09-28 (T-0072 review round 5).** `0f488706` is T-0072's review-round-5 fix commit. `git diff --name-only a4eb2f55 0f488706`, outside the refresh artifacts (`0282cb5c`, `37fa2322`), returns only T-0072's files: `plugin/crew/hooks/scripts/crew_autopilot.py` (`_resolve_root` +4 at `:729`, refusing a root that is not text, so every line after it moves by 4: `_layer_problem` `:744`, `_decide` `:759`, `deploy_allowed` `:836`, `_failure` `:1170`, `_cli_deploy` `:1194`, `main` `:1225`; `--json` dumps without indent, in place; the module docstring re-worded in place, `:87-104`), `plugin/crew/tests/sabotage_autopilot.py` (+30 inside `DEPLOY_MUTATIONS`, 64 entries by `len()`: the `AUTOPILOT_MUTATIONS + DEPLOY_MUTATIONS` append moved `:443` -> `:473`, `STATUS_MUTATIONS`' `:644` -> `:674`), `plugin/crew/tests/test_crew_autopilot_deploy.py`, `plugin/crew/CONFIG.md` (one sentence in section 20 re-worded in place, `:2331-2333`, no line added) and `CHANGELOG.md`. This note cites those files by name or at lines above the change; no citation moved. No suite was executed for this note.

## Re-anchor provenance - `65bb3330` + `89c9ee9a` -> `c817782f`, 2026-09-27 (T-0010-solo merges `67caa4b8`)

`c817782f` is T-0010's crew 1.0.48 version commit on top of `d1e119d2`, T-0010-solo's merge of
origin/main `67caa4b8` (T-0018 landed as 1.0.47; its code maps anchored `65bb3330`), and
`3e2c9962`, the reconciliation under the owner's approve carve-out. Main's side of this note was
mapped from `65bb3330`, T-0010's side from its own anchor (`89c9ee9a`), to `c817782f` with `difflib`
over every cited file, a bare `:N` taken as the last path named in its section; sections headed
provenance (and localgpu's re-derivation record) were left as written. The two mapped texts were
then merged three-way from `f0b12ee6`. Between `65bb3330` and `c817782f` the cited paths that
changed are T-0010's: `crew_autopilot.py`, `crew_ticket.py`, `scope_guard.py`, `crew_state.py`
(four `AUTOPILOT_DEFAULTS` lines at `:1094`, so every later line moved by 4), `commands/autopilot.md`,
the version files, `BUDGETS.md`, README, CONFIG.md, the tests and sabotage modules, and
`.crew/verify.json` (rule 28 inserted at `:302-308`, so rules 29 and 30 moved down by 7).

The crew version (1.0.48) at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14` changed in place, and
`plugin/crew/BUDGETS.md:11` was re-measured (18,917 across 126). `python3 scripts/check-marketplace.py`
at `c817782f`: `all checks passed`.

## Re-anchor provenance - `c817782f` -> `926443d8`, 2026-09-27 (T-0010 review round 3 fixes)

`git diff --name-only c817782f 926443d8` is T-0010's round-3 fix (`caabb005`), the BUDGETS.md
count, the version step-back and re-set, and this refresh. Of the paths this note cites, `plugin/crew/README.md`, `plugin/crew/CONFIG.md` and
`plugin/crew/BUDGETS.md` changed: README two lines rewritten in place (`:792`, `:818`),
CONFIG.md's §20 one-writer paragraph grew six lines, and `BUDGETS.md:11`'s count moved
18,917 -> 18,923 on the same line. No citation this note makes moved (checked with `difflib`
over every cited path). Nothing was executed.

## Re-anchor provenance - `926443d8` + `8de3c669` -> `50a275ea`, 2026-09-28 (T-0010's successor merges `f96e9ec9`)

`ab85880b` merges origin/main `f96e9ec9` (T-0024 landed as crew 1.0.48, its code maps anchored
`8de3c669`; T-0077 as 1.0.49) into T-0010-solo `216ee85f`; `a2f4db76` fixes review round 4's
three FIXes; `3438dc9a` merges `5050ea3b` (shipstation only); `48b2820d` re-measures
`plugin/crew/BUDGETS.md` and `50a275ea` sets crew 1.0.50. The merge took main's side of this
note; it was then re-merged three-way from `67caa4b8`, T-0010's side at `216ee85f` (anchor
`926443d8`) and main's at `f96e9ec9` (anchor `8de3c669`), both sides' provenance kept, main's
first. Every body citation into a file changed since its side's own anchor was mapped with
`difflib` (a bare `:N` taken as the last path named in its section) and each one that moved was
re-read at `50a275ea`.

The crew version (1.0.50) at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14` changed in place, and
`plugin/crew/BUDGETS.md:11` was re-measured on the merged tree (18,953 across 126).
`python3 scripts/check-marketplace.py` at `50a275ea`: `marketplace: 34 skills, 5 plugins`,
`all checks passed`.

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

**Re-anchored `0f488706` -> `9631c707` on 2026-09-28 (T-0072 landing, crew 1.0.51).** `9631c707` is T-0072's landing bump on `T-0072-land`, after `34af80ef` merged the reviewed `T-0072-build` (`a0978df6`) onto main `e6e10432` (T-0079 landed as crew 1.0.50) and `bf0c513a` re-priced verify rule 27. `git diff --name-only 0f488706 9631c707`, refresh artifacts aside, returns T-0079's files, the three version files, `CHANGELOG.md` and `.crew/verify.json`. The two this note's citations reach changed in place: `.crew/verify.json` `:298` and `:301` (rule 27's `seconds` 16 -> 18 and its `why`, still `:293-301`) and `plugin/crew/README.md` `:738` and `:742` (T-0079's verdict table, line-neutral); no citation moved. The version sentence moves to 1.0.51. No suite was executed for this note.

## Re-anchor provenance - `12682e41` + `d2444be9` -> `e95e5964`, 2026-09-27 (T-0075 merges main)

`e95e5964` is T-0075's crew 1.0.46 bump on top of `e94ce6ce`, the merge of origin/main `db14619c`
(T-0021 landed as 1.0.45) into T-0075's branch; the merge took main's copy of this note and
T-0075's edits were re-applied. Of the cited paths, `git diff --name-only 12682e41 e95e5964`
returns `.claude-plugin/marketplace.json` (`:217` 36 slash commands, `:218` 1.0.46, both in place),
`plugin/PLUGINS.md` (`:14` 1.0.46; `:17` 36 commands), `plugin/crew/.claude-plugin/plugin.json`
(version only), `plugin/README.md` (`:414`) and `README.md` (`:168`, `:874`), each 35 -> 36 in
place, both install scripts (the crew catalog label at `scripts/install-prerequisites.sh:1391` /
`scripts/install-prerequisites.ps1:1174`, 35 -> 36 in place, no line moved), `plugin/crew/BUDGETS.md`
(`:11`, 19,061 lines across 128 files, re-measured on the merged index as the checker counts),
`.crew/verify.json` (rule 7 gained three paths at `:136-138`; the doc rule at `:69-78` holds; 29
rules) and `CHANGELOG.md` (cited by name only). `ls plugin/crew/commands/*.md` is 36, agents 4,
skills 29. `INSTALLATION.md` did not change, so `INSTALLATION.md:252` still states 34 commands, now
against 36 on disk; it is outside T-0075's Touch list and unmarked, so no check catches it.
`python3 scripts/check-marketplace.py` at `e95e5964`: `marketplace: 34 skills, 5 plugins`, `all
checks passed`.

## Re-anchor provenance - `e95e5964` + `e463ca53` -> `f7163410`, 2026-09-27 (T-0075 merges T-0023's main)

`96b7e59c` merges origin/main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244; its notes anchored
`e463ca53`) into T-0075's branch at `0c6b5ecb` (notes anchored `e95e5964`), and `f7163410` bumps
crew to 1.0.47. The source files both sides changed since `db14619c` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/PLUGINS.md`, `plugin/crew/README.md`, `plugin/crew/CONFIG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_config.py`,
`plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/tests/sabotage.py`,
`plugin/crew/tests/test_crew_config.py` and the version files. The conflicting provenance sections
keep both sides, main's first. Each body line was classified by origin (in T-0075's copy only, in
main's only, or in both), its `path:N` citations - and bare `:N` after a path in the same
paragraph - into files the other side changed were mapped with a line diff (`git show
<side>:<path>` against the merged tree), each moved one re-read with `sed -n`, and hits the diff
attributed to the wrong file (a bare `:N` after an unrelated path, a same-named file elsewhere)
discarded rather than applied. Crew's `version` at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14` reads 1.0.47; `:218` and
`PLUGINS.md:17` state 36 commands (`ls plugin/crew/commands/*.md` is 36). `plugin/crew/BUDGETS.md:11`
reads 19,125 lines across 128 files, measured on the resolved index. `.crew/verify.json` is 325
lines, 30 rules; the doc rule at `:69-78` holds. `scripts/check-marketplace.py` did not change.
`python3 scripts/check-marketplace.py` at `f7163410`: `marketplace: 34 skills, 5 plugins`, `all
checks passed`.

## Re-anchor provenance - `f7163410` + `65bb3330` -> `23371afb`, 2026-09-27 (T-0075 merges T-0018's main)

`34b5f368` merges origin/main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245; its notes anchored
`65bb3330`) into T-0075's branch at `b5ef35df` (notes anchored `f7163410`), and `23371afb` bumps crew
to 1.0.48. The source files both sides changed since `bebbb97f` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md` and the version files;
`crew_autopilot.py`, `commands/autopilot.md` and the autopilot tests changed on main's side only,
`crew_config.py`, `crew_config_menu.py`, `CONFIG.md` and `sabotage.py` on T-0075's only. The
conflicting provenance sections keep both sides, main's first; each body citation into a file both
sides changed was mapped from the side its line came from onto the merged tree and re-read with
`sed -n`/`grep -n`. Crew's `version` at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14` reads 1.0.48; `:218` and
`PLUGINS.md:17` state 36 commands (`ls plugin/crew/commands/*.md` is 36). `plugin/crew/BUDGETS.md:11`
reads 19,120 lines across 128 files, measured on the resolved index. `.crew/verify.json` is 326
lines, 30 rules; the doc rule at `:69-78` holds. `scripts/check-marketplace.py` did not change.
`python3 scripts/check-marketplace.py` at `23371afb`: `marketplace: 34 skills, 5 plugins`, `all
checks passed`.

## Re-anchor provenance - `23371afb` -> `764f6018`, 2026-09-27 (T-0075 review round 1)

`764f6018` fixes T-0075's review round 1. `git diff --name-only 23371afb 764f6018` is `CHANGELOG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_config_menu.py`,
`plugin/crew/skills/crew-setup/config-menu.md` and three crew test files. Each citation into one
of them was mapped with a line diff from `87627d86` (the tree `23371afb` describes for those
files) and re-read with `sed -n`/`grep -n`. No marketplace entry, count or install-script line changed;
`plugin/crew/BUDGETS.md:11` now reads 19,145 lines across 128 files (the figures above are history at
their anchors). crew was still 1.0.48 at `764f6018`; `ca667718` then re-set it to 1.0.49 as the last
`plugin/crew/` commit (marketplace.json `:218`, plugin.json `:3`, PLUGINS.md `:14`, re-read). Nothing else was executed for this note; `scripts/check-marketplace.py`
reported `all checks passed` on the fix commit.

## Re-anchor provenance - `764f6018` + `8de3c669` -> `7d217751`, 2026-09-27 (T-0075 successor build, merges T-0024's main)

`7d217751` is T-0075's crew 1.0.49 bump. Between `764f6018` (T-0075 review round 1, this note's
last anchor) and it: the successor build's steps 1-9 (`4911b896`..`763eaeff`: `crew_config_files.py`
new, `crew_config.py` and `crew_config_menu.py` redesigned, their tests and sabotage entries, the
menu procedure, `commands/config.md`, `config-setup.md`, `global-config.md`, `plugin/crew/README.md`,
`CONFIG.md`, the troubleshooting guide and `CHANGELOG.md`), `748a823d` merging origin/main `d2fbd408`
(T-0024 landed as 1.0.48, notes anchored `8de3c669`), `af1ee7ef` adding two paths to
`.crew/verify.json` rule 7, `cb67a6ef` rebuilding the troubleshooting guide, `plugin/crew/BUDGETS.md`
re-measured (19,280 lines across 128 files) and the bump. The merge's provenance sections keep both
sides, main's first. Each citation into a path `git diff --name-only 764f6018 7d217751` names was
checked against the tree it was written for (`git blame` on this note gives the commit) and re-read
at `7d217751` with `sed -n`/`grep -n`; the crew version statement now reads 1.0.49 at `7d217751`
(`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`,
`plugin/PLUGINS.md:14`), 1.0.48 at `d2fbd408` and on the merge; `:218` still states 36 commands.
`.crew/verify.json`'s doc rule `:69-78` holds. `python3 scripts/check-marketplace.py` at `7d217751`:
`marketplace: 34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `7d217751` + `f96e9ec9` -> `8cabe586`, 2026-09-27 (T-0075 post-merge fixes, merges T-0077's main)

`8cabe586` is T-0075's crew 1.0.50 bump. Between `7d217751` and it: `ed7cb36c` (the stray line
step 6 left in `crew_config_menu.py:940`, a restore-line test's assertion, and the widening-warning
mutation re-anchored in `sabotage.py`, each found by the first full suite run after the build), a
1.0.48/1.0.49 step-back and re-set (`b80db8e1`, `81ed193c`), `3ebddc74` merging origin/main
`f96e9ec9` (T-0077 landed as 1.0.49: Windows directory handles in `crew_tracker.py`,
`crew_autopilot._rel`, their tests and mutations, three `plugin/crew/README.md` lines and its
`CHANGELOG.md` entry; main's notes were not refreshed for it) and the bump. Citations into the
paths `git diff --name-only 7d217751 8cabe586` names were mapped with `git diff -U0` and each
moved one checked by content at `8cabe586`; the crew version statement reads 1.0.50 at `8cabe586`; `:217` still
states 36 commands (main's T-0077 description said 35; the merge kept T-0075's). `python3
scripts/check-marketplace.py` at `8cabe586`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `8cabe586` + `81685adf` -> `3724731b`, 2026-09-28 (T-0075 review round 3, merge of `e6e10432`)

`3036dc02` is T-0075's review-round-3 fix (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, and `README.md`, `CONFIG.md`,
`commands/config.md`, `config-menu.md`, `global-config.md`, `CHANGELOG.md`); `6d5f0b61` merges
origin/main `e6e10432` (T-0079 landed as crew 1.0.50: `review_prompt.py`, `review_run.py`,
`review_verdict.py`, `agents/reviewer.md`, their tests, `sabotage_review.py`,
`sabotage_webtest.py`, `test_webtest_guard.py`, `README.md`, `CHANGELOG.md`; its notes anchored
`81685adf`); `3724731b` re-bumps crew to 1.0.51 (`plugin.json`, `marketplace.json`,
`plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`, `CHANGELOG.md`). The merge's conflicting provenance
sections kept both sides, main's first; anchor lines kept T-0075's and are replaced here.

The version sentence moves to 1.0.51 (`.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`,
`plugin/crew/.claude-plugin/plugin.json` agree); `:217` and `:17` still state 36 commands. No
other citation moved (script over every explicit `path:N`). `python3 scripts/check-marketplace.py`
at `3724731b`: `marketplace: 34 skills, 5 plugins`, `all checks passed`.

## Re-anchor provenance - `3724731b` + `9631c707` -> `938e3b11`, 2026-09-28 (T-0075 review round 4, merge of `f54af3fa`)

`7d473f24` merges origin/main `f54af3fa` (T-0072 landed as crew 1.0.51: `crew_autopilot.py`,
`commands/autopilot.md`, `crew_state.py`'s line-neutral `AUTOPILOT_DEFAULTS` hunk at `:1086-1090`,
`templates/config.template.json`, `skills/crew-setup/SKILL.md`, `CONFIG.md` §20, `README.md`, its
tests, `sabotage_autopilot.py`, `.crew/verify.json` rule 27's `seconds` and `why`; its notes
anchored `9631c707`); `07354a39`, `df419a55`, `7a206c8e`, `4112498e`, `1b31ed2f` and `7ef3c4f1` are
T-0075's review-round-4 steps 11-16 (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`,
`skills/crew-setup/config-menu.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `938e3b11` re-bumps
crew to 1.0.52 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's
conflicting provenance kept both sides; anchor lines kept T-0075's and are replaced here.

The version sentence moves to 1.0.52 (`.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`, all re-read).
`plugin/crew/BUDGETS.md:11` now reads 19,415 lines across 128 files (re-measured with `git ls-files
'plugin/crew/*.md' | xargs cat | wc -l`); this note's body states no current figure for it. No other
citation moved.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N`
carried from the last path named in its paragraph, from both `3724731b` and `9631c707` to the tree
at `938e3b11` (difflib equal blocks); every citation neither base maps to itself was read with `sed
-n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `crew_autopilot.py`
citation after an `autopilot.md` mention, a `plugin.json:3` in another plugin); those were read and
hold. Nothing else was executed for this note.

**Re-anchored `9631c707` -> `b5c37635` on 2026-09-28 (T-0087, crew 1.0.52).** `b5c37635` is T-0087's crew 1.0.52 bump on `T-0087-build`, after `d05727af` merged main `f54af3fa` (T-0072 landed as crew 1.0.51). `git diff --name-only 9631c707 b5c37635`, refresh artifacts aside, returns T-0087's files (the review/gate harness, its tests, the golden corpus, `scripts/check-tooling-pr.py`, rule 31 in `.crew/verify.json`, `CLAUDE.md`'s tooling-alone bullet, the docs and guides) plus the three version files and `CHANGELOG.md`. One body citation moved: `CLAUDE.md:47` -> `:54` (the tooling-alone bullet was inserted above it, +7). The version sentence above moves to 1.0.52. Nothing was executed for this note.

**Re-anchored `b5c37635` -> `1da1233d` on 2026-09-28 (T-0087, crew 1.0.52).** `1da1233d` is T-0087's crew 1.0.52 bump re-set after two reflow commits: `4648581a` rewrapped `plugin/crew/commands/review.md` to its 551-line allowance and `plugin/crew/commands/autopilot.md` to its 100-line budget, and `4304a9da` kept the sabotage anchor "are the human's. Go back" on one line (no rule changed in either). `git diff --name-only b5c37635 1da1233d`, refresh artifacts aside, returns those two command files and the three version files, which read 1.0.52 on both sides. This note cites neither file by line; the command count (35) is unchanged. Nothing was executed for this note.

**Re-anchored `1da1233d` -> `0d331967` on 2026-09-28 (T-0087, crew 1.0.52).** `0d331967` adds `plugin/crew/BUDGETS.md` to `scripts/check-tooling-pr.py`'s `ALONGSIDE` (its line count moves with every crew doc edit, and the checker refused this branch's own re-measure) and the `harness+budgets` must-allow case to `scripts/_test/tooling-pr.py`, red first (7 passed, 1 failed), then 8 passed. `git diff --name-only 1da1233d 0d331967`, refresh artifacts aside, returns those two scripts and `CHANGELOG.md`, plus the 1da1233d..08ed88a5 changes (`plugin/crew/BUDGETS.md`, `plugin/crew/tests/sabotage_refresh.py`, version files unchanged net). This note cites neither script by line (its `scripts/**` path scope covers them); `scripts/check-marketplace.py` did not change. Nothing was executed for this note.

**Re-anchored `0d331967` -> `c8cc69ec` on 2026-09-28 (T-0087, now crew 1.0.53).** Main moved: `c426c018` (T-0076, the crew suite on native Windows) landed as crew 1.0.52, so T-0087 merged it with a merge commit (no conflict) and re-bumped to 1.0.53 at `c8cc69ec`. `git diff --name-only 0d331967 c8cc69ec`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py` +4 at `:1086`, where `emit` now forces LF stdout; `plugin/crew/tests/crew_fixtures.py`, `review_fixtures.py`, `sabotage_context.py` and nine test files; `scripts/_test/uv-install.sh`; one `plugin/crew/README.md` table cell; its `CHANGELOG.md` entry), the README refund paragraph's version text, and the three version files. Every body `path:N` citation into those files was mapped by script (difflib over the two blobs) and every bare `:N` after one of their names was listed and read: none moved; the version sentence above moves to 1.0.53 (`.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`, re-read). Nothing was executed for this note.
**Re-anchored `9631c707` -> `22399a9c` on 2026-09-28 (T-0085, crew 1.0.52).** `22399a9c` is T-0085's version commit on `T-0085-build` (the change is `d02fe008`, from origin/main `f54af3fa`). T-0085 adds a crew-bundled skill, `crew-standards`, which is not a marketplace entry: `marketplace.json` gains no entry and neither install script changes. It edits in place, line-neutral, `.claude-plugin/marketplace.json` (`:217` 30 bundled skills, `:218` 1.0.52), `plugin/PLUGINS.md` (`:14` 1.0.52, `:17` 30 skills; one skills-table row added below `:213`), `README.md` (`:168`, `:874`, 30 skills) and `plugin/crew/.claude-plugin/plugin.json:3`. Every body citation into a changed file was compared by script at both commits; only the version and skills figures moved, corrected above. `python3 scripts/check-marketplace.py` at `22399a9c` reports exactly the two unchanged 29-skill sites named in the table. Nothing else was executed for this note.

**Re-anchored `22399a9c` -> `2aa49bb8` on 2026-09-28 (T-0085 merged onto main `c426c018`, crew 1.0.53).** `c49f3aca` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52) into `T-0085-build`, one mechanical conflict (the crew description's skills count in `.claude-plugin/marketplace.json`, kept at 30), and `2aa49bb8` bumped crew to 1.0.53. `git diff --name-only 22399a9c 2aa49bb8`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py`, four lines added inside `emit()` at `:1086-1089`; `plugin/crew/README.md`, one line in place; `scripts/_test/uv-install.sh`; eleven test files) and the version files. Every body citation into a changed file was compared by script at both commits; only the version moved (1.0.53, corrected above). No suite was executed for this note.

**Re-anchored `9631c707` -> `051f9e85` on 2026-09-28 (T-0091).** `051f9e85` is T-0091's one commit on `T-0091-build`, off main `f54af3fa`. `git diff --name-only 9631c707 f54af3fa -- <every tracked path this note cites>` is empty; `f54af3fa..051f9e85` changes only `CLAUDE.md` (the Landmines truncating-`open` entry's measurement paragraph, now `:185-212`, +28/-18, so every later line moves +10) and `TODO.md` (one entry closed at `:4473`, three lines appended at `:4480-4482`). This note's `CLAUDE.md` citations, `:5` and `:47`, sit above the changed paragraph and still read as quoted (re-read). No claim moved. Nothing was executed.

**Re-anchored `051f9e85` -> `c192b83d` on 2026-09-28 (T-0091 review round 1).** `c192b83d` is T-0091's review-round-1 fix on `T-0091-build`. `git diff --name-only 051f9e85 c192b83d` returns only `CLAUDE.md`: the same Landmines truncating-`open` measurement paragraph, now `:185-219` (+16/-9, so every later line moves +7; lines above `:192` are byte-identical). This note's `CLAUDE.md` citations, `:5` and `:47`, sit above the paragraph and still read as quoted (re-read). No claim moved. Nothing was executed.

**Re-anchored `9631c707` -> `79127fa1` on 2026-09-28 (T-0090 on `T-0090-build`, no crew change).** `git diff --name-only 9631c707 79127fa1`, refresh artifacts aside, returns T-0090's files only: `SECURITY.md` (a Scope bullet for `mcp-servers/` and one "what counts" bullet for the Graph token origin pin), `CHANGELOG.md` (T-0090's Security entry at the top of `[Unreleased]`) and ten files under `mcp-servers/` (the pin and the npm packages' 0.2.1 bump). This note names `SECURITY.md` and `CHANGELOG.md` only as members of `.crew/verify.json`'s doc-rule path list (`:69-78`, unchanged), and cites nothing under `mcp-servers/`; no citation moved. No marketplace entry, version or install script changed: `grep -c mcp-servers .claude-plugin/marketplace.json` is 0 and `python3 scripts/check-marketplace.py` at `79127fa1` printed `marketplace: 34 skills, 5 plugins`, `all checks passed`.

(Corrected at the T-0090 landing: the paragraph above first said "eleven files under `mcp-servers/`"; `git diff --name-only 9631c707 79127fa1 -- mcp-servers/ | wc -l` is 10. Review round 2 FIX, owner-accepted, fixed at this re-anchor.)

**Re-anchored `c192b83d` -> `b2553d26` on 2026-09-28 (T-0090 landing, no crew change).** `b2553d26` is `T-0090-land`'s merge of the reviewed `T-0090-build` (`631d3317`) onto main `ff59160f`. `git diff --name-only c192b83d b2553d26`, refresh artifacts aside, returns T-0090's files (`SECURITY.md`, `CHANGELOG.md`, ten under `mcp-servers/`) and main's own commits since `c192b83d`: T-0089's and T-0076's landings (`.claude-plugin/marketplace.json`, `plugin/crew/.claude-plugin/plugin.json` and `plugin/PLUGINS.md` version lines only, `plugin/crew/README.md` `:1691` one table cell, `scripts/_test/uv-install.sh`, `docs/diagrams/data-flow-crew-config.mmd`, and crew hook and test files). Of those, this note cites the three version lines (`.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`, `plugin/crew/.claude-plugin/plugin.json:3`, still at those lines, re-read: 1.0.53), so the version sentence moves to 1.0.53; `plugin/crew/README.md` by name only; `SECURITY.md` and `CHANGELOG.md` as members of `.crew/verify.json`'s doc-rule path list (`:69-78`, unchanged); nothing under `mcp-servers/` and not `uv-install.sh`. No other citation moved. Executed for this note: `python3 scripts/check-marketplace.py` at `b2553d26`.

**Re-anchored `9631c707` -> `c99e31f6` on 2026-09-28 (T-0092, crew 1.0.52).** `c99e31f6` is T-0092's crew 1.0.52 version commit on `T-0092-build`, cut from main `f54af3fa` (T-0072's landing merge, whose only commit past `9631c707` is the refresh `f1f118de`). `git diff --name-only 9631c707 c99e31f6`, refresh artifacts aside, returns T-0092's files: `plugin/crew/hooks/scripts/review_patch.py` (+8: the docstring paragraph on `graphify-out/` and one comment line; `EXCLUDED` / `_EXCLUDE_SPEC` now at `:104-105`), `plugin/crew/hooks/scripts/review_prompt.py` (+4: one docstring line and the `excluded` line at `:89-91`, so `:84` -> `:85` and `:239` -> `:243`), `test_review_patch.py`, `test_review_prompt.py`, `sabotage_review.py`, line-neutral edits to `plugin/crew/README.md` (`:726`, `:860`), `plugin/crew/commands/review.md` (`:328-332` reflowed in place), `crew_autopilot.py` (`:55-56`), `completion_audit.py` (`:74-75`) and `TODO.md` (`:5048`), `CHANGELOG.md` (+26 at the top) and the three version files (1.0.52 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`). Every body citation of the form `path:line` into those files was compared by script between `9631c707` and `c99e31f6`. The only differing citations are the version-file lines, changed in place; the version sentence moves to 1.0.52 and the older provenance notes keep the value they recorded. Nothing was executed for this note.

**Re-anchored `c99e31f6` -> `3c4f1a68` on 2026-09-28 (T-0092 merged onto `c426c018`, crew 1.0.53).** `95cc12cf` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52 at `e329eb8f`) into `T-0092-build`; the merge was clean (both sides had set the version files to 1.0.52). `3c4f1a68` re-bumps crew to 1.0.53 and moves T-0092's four `1.0.52` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:877`, `TODO.md:5048`, the two test-file comments) to 1.0.53, all in place. `git diff --name-only c99e31f6 3c4f1a68`, refresh artifacts aside, returns T-0076's files - `plugin/crew/hooks/scripts/crew_context.py` (+4 inside `emit`, so `sys.stdout.write` moves `:1090` -> `:1094`), `plugin/crew/README.md` (`:1695` in place), `scripts/_test/uv-install.sh` and twelve test files - plus `CHANGELOG.md` (T-0076's entry merged below T-0092's) and the version files. Every body citation of the form `path:line` into those files was compared by script between `c99e31f6` and `3c4f1a68`: the only differences are version-file lines changed in place and `CHANGELOG.md` lines inside dated provenance notes, left as history; nothing here cites `crew_context.py` at or below `:1108`. The version sentence moves to 1.0.53. Nothing was executed for this note.

**Re-anchored `c192b83d` / `3c4f1a68` -> `25d2de63` on 2026-09-28 (T-0092 merged onto `f8b6c8d7`, T-0091, crew 1.0.53).** `25d2de63` merges origin/main `f8b6c8d7` (T-0091 landed at `c192b83d`: `CLAUDE.md`'s Landmines paragraph and a `TODO.md` entry, no plugin bumped) into `T-0092-build`. The code-map, INDEX, rules, diagram and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor taken from this note. Every body citation of the form `path:line` was compared by script twice: `c192b83d` -> `25d2de63` differs only on T-0092's own lines (the exclusion, the re-pointed `review_prompt.py` lines, `plugin/crew/README.md:877` in place, the version lines), and `3c4f1a68` -> `25d2de63` only on T-0091's `CLAUDE.md` lines, which T-0091's own notes above cite at `c192b83d`, and on `TODO.md:5048`, cited in T-0092's notes above as that commit's line: T-0091's three added lines move the bullet to `:5051`. Nothing was executed for this note.

**Re-anchored `25d2de63` -> `136f4b33` on 2026-09-28 (T-0092 merged onto `ff59160f`, T-0089, crew 1.0.54).** `e2220836` merges origin/main `ff59160f` (T-0089 landed as crew 1.0.53 at `0f526a8c`: `plugin/crew/tests/test_role_write_guard.py` fixtures and a `CHANGELOG.md` entry) into `T-0092-build`; the merge was clean. `136f4b33` re-bumps crew to 1.0.54 and moves T-0092's `1.0.53` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:877`, `TODO.md:5051`, the two test-file comments, its `CHANGELOG.md` heading) to 1.0.54, all in place. Every body citation of the form `path:line` into a file changed between `25d2de63` and `136f4b33` was compared by script: the only differences are version-file lines changed in place, `plugin/crew/README.md:877` in place, and lines cited inside dated provenance notes (`CHANGELOG.md`, which T-0089's entry shifts by 12 lines below `:80`, and `TODO.md:5048`), left as history at their own commit. No citation into `test_role_write_guard.py` exists here. The crew version sentence moves to 1.0.54. Nothing was executed for this note.

**Re-anchored `b2553d26` / `136f4b33` -> `2442d367` on 2026-09-28 (T-0092 landing, crew 1.0.54).** `2442d367` is `T-0092-land`'s merge of the reviewed `T-0092-build` (`68d34203`) onto main `311dab8c` (T-0090's landing, no crew bump, so crew is 1.0.53 there and T-0092's 1.0.54 is one past it). The code-map, INDEX and rules conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor held at main's `b2553d26` in the merge and moved here. Every body citation of the form `path:line` was compared by script twice: `b2553d26` -> `2442d367` differs only on T-0092's own lines (the three version lines, 1.0.53 -> 1.0.54 in place, `plugin/crew/README.md:877` in place, and `TODO.md:5051`, T-0092's constraint bullet edited in place), and `136f4b33` -> `2442d367` touches no cited file (T-0090's files - `SECURITY.md`, `CHANGELOG.md`, ten under `mcp-servers/` - are named here without a line). The version sentence was re-read at `2442d367` (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`: 1.0.54) and at each commit it now names, by `git show <sha>:<path>`. Nothing else was executed for this note.

**Re-anchored `c99e31f6` -> `3c4f1a68` on 2026-09-28 (T-0092 merged onto `c426c018`, crew 1.0.53).** `95cc12cf` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52 at `e329eb8f`) into `T-0092-build`; the merge was clean (both sides had set the version files to 1.0.52). `3c4f1a68` re-bumps crew to 1.0.53 and moves T-0092's four `1.0.52` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:877`, `TODO.md:5048`, the two test-file comments) to 1.0.53, all in place. `git diff --name-only c99e31f6 3c4f1a68`, refresh artifacts aside, returns T-0076's files - `plugin/crew/hooks/scripts/crew_context.py` (+4 inside `emit`, so `sys.stdout.write` moves `:1086` -> `:1090`), `plugin/crew/README.md` (`:1691` in place), `scripts/_test/uv-install.sh` and twelve test files - plus `CHANGELOG.md` (T-0076's entry merged below T-0092's) and the version files. Every body citation of the form `path:line` into those files was compared by script between `c99e31f6` and `3c4f1a68`: the only differences are version-file lines changed in place and `CHANGELOG.md` lines inside dated provenance notes, left as history; nothing here cites `crew_context.py` at or below `:1104`. The version sentence moves to 1.0.53. Nothing was executed for this note.

**Re-anchored `c192b83d` / `3c4f1a68` -> `25d2de63` on 2026-09-28 (T-0092 merged onto `f8b6c8d7`, T-0091, crew 1.0.53).** `25d2de63` merges origin/main `f8b6c8d7` (T-0091 landed at `c192b83d`: `CLAUDE.md`'s Landmines paragraph and a `TODO.md` entry, no plugin bumped) into `T-0092-build`. The code-map, INDEX, rules, diagram and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor taken from this note. Every body citation of the form `path:line` was compared by script twice: `c192b83d` -> `25d2de63` differs only on T-0092's own lines (the exclusion, the re-pointed `review_prompt.py` lines, `plugin/crew/README.md:877` in place, the version lines), and `3c4f1a68` -> `25d2de63` only on T-0091's `CLAUDE.md` lines, which T-0091's own notes above cite at `c192b83d`, and on `TODO.md:5048`, cited in T-0092's notes above as that commit's line: T-0091's three added lines move the bullet to `:5051`. Nothing was executed for this note.

**Re-anchored `25d2de63` -> `136f4b33` on 2026-09-28 (T-0092 merged onto `ff59160f`, T-0089, crew 1.0.54).** `e2220836` merges origin/main `ff59160f` (T-0089 landed as crew 1.0.53 at `0f526a8c`: `plugin/crew/tests/test_role_write_guard.py` fixtures and a `CHANGELOG.md` entry) into `T-0092-build`; the merge was clean. `136f4b33` re-bumps crew to 1.0.54 and moves T-0092's `1.0.53` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:877`, `TODO.md:5051`, the two test-file comments, its `CHANGELOG.md` heading) to 1.0.54, all in place. Every body citation of the form `path:line` into a file changed between `25d2de63` and `136f4b33` was compared by script: the only differences are version-file lines changed in place, `plugin/crew/README.md:877` in place, and lines cited inside dated provenance notes (`CHANGELOG.md`, which T-0089's entry shifts by 12 lines below `:80`, and `TODO.md:5048`), left as history at their own commit. No citation into `test_role_write_guard.py` exists here. The crew version sentence moves to 1.0.54. Nothing was executed for this note.

**Re-anchored `b2553d26` / `136f4b33` -> `2442d367` on 2026-09-28 (T-0092 landing, crew 1.0.54).** `2442d367` is `T-0092-land`'s merge of the reviewed `T-0092-build` (`68d34203`) onto main `311dab8c` (T-0090's landing, no crew bump, so crew is 1.0.53 there and T-0092's 1.0.54 is one past it). The code-map, INDEX and rules conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor held at main's `b2553d26` in the merge and moved here. Every body citation of the form `path:line` was compared by script twice: `b2553d26` -> `2442d367` differs only on T-0092's own lines (the three version lines, 1.0.53 -> 1.0.54 in place, `plugin/crew/README.md:877` in place, and `TODO.md:5051`, T-0092's constraint bullet edited in place), and `136f4b33` -> `2442d367` touches no cited file (T-0090's files - `SECURITY.md`, `CHANGELOG.md`, ten under `mcp-servers/` - are named here without a line). The version sentence was re-read at `2442d367` (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`: 1.0.54) and at each commit it now names, by `git show <sha>:<path>`. Nothing else was executed for this note.

(Corrected at the T-0092 landing: the version sentence above first said 1.0.54 was "re-read at `3c4f1a68`, T-0092's re-bump after merging main `c426c018`", and its history skipped 1.0.53. `git show 3c4f1a68:plugin/crew/.claude-plugin/plugin.json | grep version` prints `"version": "1.0.53"`; the 1.0.54 re-bump is `136f4b33`. It now cites the landing merge `2442d367`, which holds 1.0.54, and records 1.0.53 at `3c4f1a68`, `ff59160f` and `311dab8c`. Review round 2 FIX, owner-accepted, fixed at this re-anchor.)

## Re-anchor provenance - `938e3b11` + `2442d367` -> `3648f59a`, 2026-09-28 (T-0075 review round 5, merge of `6387ab49`)

`9420bc16` merges origin/main `6387ab49` into `T-0075-build`: T-0076 (crew 1.0.52, `crew_context.py`'s byte-exact LF), T-0091 (`CLAUDE.md`'s Landmines paragraph, a `TODO.md` entry), T-0089 (crew 1.0.53, `test_role_write_guard.py` fixtures), T-0090 (mcp-servers 0.2.1, `SECURITY.md`) and T-0092 (crew 1.0.54: `review_patch.py` / `review_prompt.py` leave `graphify-out/` out of the review bundle), whose notes above are anchored `136f4b33`, `2442d367`, `c192b83d` or `b2553d26`. `faf4b0db`, `e7825a0e`, `04e3a01c`, `517628b9` and `d1460d77` are T-0075's review-round-5 steps 18-22 (`crew_config.py`, `crew_config_files.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `3648f59a` re-bumps crew to 1.0.55 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's conflicting provenance kept both sides, T-0075's `## Re-anchor provenance` sections first and main's `**Re-anchored ...**` paragraphs after them; the anchor line kept T-0075's and is replaced here.

The version sentence moves to 1.0.55 and now lists both lines' history (T-0075's re-bumps 1.0.44-1.0.52 on its branch; main's 1.0.51-1.0.54). `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14` re-read at `3648f59a`: all 1.0.55. `.claude-plugin/marketplace.json:217` keeps T-0075's 36 slash commands. No other body citation moved.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `938e3b11` for a line in T-0075's copy of this note and from `6387ab49` for a line only in main's, to the tree at `3648f59a` (difflib equal blocks); every citation that did not map to itself was read with `sed -n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `.crew/verify.json` range after a test-file mention, a `check-marketplace.py` range after a `PLUGINS.md` mention, a `SKILL.md` in another skill); those were read and hold. A citation inside a list of per-commit positions keeps its commit's line; only the current position is added. Nothing else was executed for this note.

## Re-anchor provenance - `50a275ea` + `81685adf` -> `360c4029`, 2026-09-28 (T-0010-solo merges T-0079's `e6e10432`)

`c312702b` merges origin/main `e6e10432` (T-0079 landed as crew 1.0.50, its code maps anchored
`81685adf`) into T-0010-solo `ac0b5151`; `360c4029` sets crew 1.0.51. The artifact conflicts were
anchor, version and provenance lines only: T-0010's side kept for anchors and body (its
`crew_autopilot.py` and `commands/autopilot.md` line numbers are this tree's), both sides'
provenance kept. `git diff --name-only 50a275ea 360c4029`, refresh artifacts aside, is T-0079's files
(`review_verdict.py`, `review_prompt.py`, `review_run.py`, `agents/reviewer.md`, their tests and
sabotage modules, identical to origin/main's), `plugin/crew/README.md` (two lines rewritten in
place, `:735` and `:739`, line-neutral), `CHANGELOG.md` and the version files. Every citation into
T-0079's files equals main's note at `81685adf` (compared by script). No test was run by this note.

## Re-anchor provenance - `360c4029` + `2442d367` -> `d7c7c75c`, 2026-09-28 (T-0010-solo merges `6387ab49`)

`597a62b0` merges origin/main `6387ab49` into T-0010-solo `dbb22712`: T-0072 landed as crew
1.0.51, T-0076 as 1.0.52, T-0089 as 1.0.53 and T-0092 as 1.0.54, with T-0090 (mcp-servers 0.2.1)
and T-0091 (`CLAUDE.md`) beside them; main's code maps were anchored `2442d367`. After it,
`bd066a97` moves `settings`' two policies to a second text line (T-0072's
`test_settings_line_names_deploy` pins the first line exactly), `ab85fed0` puts `deploy-allowed`
in T-0010's only-writer test, `250c6df7` rewraps one docstring line in place, `130bf67e` re-sets
crew 1.0.55 and `d7c7c75c` re-prices `.crew/verify.json` rule 29 in place (20 -> 21). The merge
took main's side of this note; it was then re-merged three-way from `e6e10432`, T-0010's side at
`dbb22712` (anchor `360c4029`) and main's at `6387ab49`, both sides' provenance kept, main's
first. Every body `path:line` citation into a file changed since its side's commit was mapped to
`d7c7c75c` with `difflib` (a bare `:N` taken as the last file named earlier in its paragraph);
a citation followed by `at <sha>`, `before` or `->`, and every provenance section, was left as
written. A citation inside a changed hunk cannot be mapped that way and was left as written unless
this section names it.

The crew version sentence was resolved by hand: 1.0.55 at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14`, re-read at `d7c7c75c`;
`plugin/crew/BUDGETS.md:11` reads 19,007 lines across 126 files. `python3
scripts/check-marketplace.py` at `d7c7c75c`: `all checks passed`.

## Re-anchor provenance - `d7c7c75c` + `3648f59a` -> `cd106b8b`, 2026-09-28 (T-0010-solo merges T-0075's `e878cc31`)

`acbb0fb2` merges origin/main `e878cc31` into T-0010-solo `07032fc7`: T-0075 (`/crew:config` menu mode and
`/crew:config-setup`) landed as crew 1.0.59, its code maps anchored `3648f59a`. `92e0717a` re-measures
`plugin/crew/BUDGETS.md` (19,494 lines across 128 files) and rebuilds the troubleshooting guide's DOCX and
PDF; `cd106b8b` re-sets crew 1.0.60, one past main. The code merged without a conflict (T-0010 and T-0075 change
disjoint scripts); the conflicts were this note's anchor, provenance and a few cited lines. Both sides'
provenance was kept, main's first. Every body `path:N` citation was traced to the side whose copy of this
note carries its line (`07032fc7` or `e878cc31`) and mapped to `cd106b8b` through a `difflib` line diff
(`/root/crew-tmp/t-0010/citemap.py`, machine-local); each line that did not map to itself was read with
`sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were
that misattribution (a `crew_ticket.py` or `review_ledger.py` line after another file's mention) and hold.

The crew version sentence was resolved by hand: 1.0.60 at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14`, re-read at `cd106b8b`, with both lines'
history kept. `python3 scripts/check-marketplace.py` at `cd106b8b`: `all checks passed`.

## Re-anchor provenance - `cd106b8b` -> `bbd9a66d`, 2026-09-29 (T-0010 landing branch)

`T-0010-land` merges T-0010-solo `6b89c1df` into origin/main `2693d0fa` (README re-pin only past `e878cc31`,
so the merged tree is `6b89c1df` plus that README change). `08eeaa3e` adds the ruff fix-at-land lint fixes
(owner standing rule 2026-09-28; owner decision 2026-09-29 "Fix at land"): ISC004 parentheses in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/tests/sabotage_autopilot.py` and
`plugin/crew/tests/test_scope_guard.py`; `# noqa: BLE001` on five fail-closed broad excepts in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_ticket.py` and
`plugin/crew/hooks/scripts/scope_guard.py`; an I001/RUF100/C0207 fix in
`plugin/crew/tests/test_crew_autopilot_policy.py`. `bbd9a66d` re-sets crew 1.0.61. Each edited line kept its
number (the parentheses and comments were added in place) except in `test_crew_autopilot_policy.py`, whose
import block lost one line; no note cites that file by line. Re-anchor only; nothing was executed for this note.

**Re-anchored `c8cc69ec` -> `c0768d0e` on 2026-09-28 (T-0087, crew 1.0.53).** `c0768d0e` is T-0087's merge of main `f8b6c8d7` (T-0091, no plugin version change) into `T-0087-build`; crew stays 1.0.53, one past main's 1.0.52, and `c8cc69ec` is still the last `plugin/crew` commit. `git diff --name-only c8cc69ec c0768d0e`, refresh artifacts aside, returns `CLAUDE.md` (T-0091's Landmines truncating-`open` measurement paragraph, +35/-18 at `:189`, so every later line moves +17) and `TODO.md`. Every other body `CLAUDE.md:N` citation here is at or above `:189`, or sits inside a dated re-anchor note that states the coordinates of its own commit, so none moved. Nothing was executed for this note.

**Re-anchored `2442d367` / `c0768d0e` -> `379ab5e6` on 2026-09-28 (T-0087 merged onto `6387ab49`, crew 1.0.55).** `01dd3854` merges origin/main `6387ab49` into `T-0087-build`: T-0089 (crew 1.0.53, `plugin/crew/tests/test_role_write_guard.py`), T-0090 (mcp-servers 0.2.1: `SECURITY.md`, ten files under `mcp-servers/`) and T-0092 (crew 1.0.54: `graphify-out/` left out of review bundles - `review_patch.py`, `review_prompt.py`, `completion_audit.py`'s comment, `crew_autopilot.py`'s docstring, `commands/review.md`, `plugin/crew/README.md`, `TODO.md`, three test files). `379ab5e6` re-bumps crew to 1.0.55, one past main's 1.0.54, and moves T-0087's `1.0.53` mentions (`plugin/crew/README.md:758`, its `CHANGELOG.md` entry) to 1.0.55 in place. The code-map, INDEX, diagram, rules and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the version sentence, `.claude/rules/` and `graphify-out/` taken from main and then refreshed. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from the anchor of the side `git blame` puts the note line on, both anchors for a line common to both, never guessed): none moved in this map. Citations the script could not map, or where the two sides' anchors disagree on a line common to both, were not re-read here and are unchanged; they predate this merge (for example `CHANGELOG.md`'s "117 -> 119" is cited at `:654-655` on both sides and sits at `:909-910`), and this pass only re-anchors.

**Re-anchored `379ab5e6` -> `17fa035e` on 2026-09-28 (T-0087 review round 1, crew 1.0.55 unchanged - not yet released).** `bbe68e85` fixes review round 1: autopilot lets a refunded round's `/crew:review` rerun past its no-progress stop, rule 31 triggers on its suites and seam consumers, `scripts/check-tooling-pr.py` admits no production code or prompt alongside the harness (a `SEAM` consumer only with a `Tooling-seam:` trailer), `golden_build.redact` bounds both sides of a match, a malformed `successors` loads as corrupt, `review_run.py`'s summary line counts charged rounds, a worktree rename is parsed, and the guides stop calling a post-refund rerun free; `17fa035e` re-prices rule 31. `git diff --name-only 379ab5e6 17fa035e`, refresh artifacts aside, returns those scripts, their tests, one golden fixture, `.crew/verify.json`, `CLAUDE.md`, `CHANGELOG.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, `commands/autopilot.md`, `commands/review.md` and the troubleshooting guide. Body citations of the form `path:line` into those files were re-mapped by script (difflib over each cited file from `379ab5e6` to `bbe68e85`, only for note lines committed before this pass, never guessed): one moved, `CLAUDE.md` `:54` -> `:56`. Nothing else here moved.

## Re-anchor provenance - `bbd9a66d` + `17fa035e` -> `9e38a891`, 2026-09-29 (`T-0087-build` merges T-0010's `8ab733d7`)

`0fc7f609` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored
`bbd9a66d`) into `T-0087-build` `674bc4e5` (T-0087's Windows-portability successor plan, Steps 1-5
built; its maps anchored `17fa035e`). After it, `ae448309` renames T-0087's harness rule to rule 32
in text and re-measures `plugin/crew/BUDGETS.md` (19,666 lines across 129 files), `167f69a0` says
the refund ships in 1.0.62 (README, CHANGELOG), `e537e4ce` re-sets crew 1.0.62, one past main, and
`9e38a891` rebuilds the daily-workflow and troubleshooting guides from their merged sources. The code
conflicts were `crew_autopilot.next_phase` (main's `policy` argument plus T-0087's refunded-rerun
pop), `sabotage.py`'s `MUTATIONS +=` line and `test_crew_autopilot.py` (both sides kept) and the
README's Stops line (main's text plus T-0087's refunded-review clause). The artifact conflicts took
main's side for body text and kept both sides' provenance, main's first. Every body `path:N`
citation was traced to the side whose copy of this note carries its line (`674bc4e5` or
`8ab733d7`) and mapped to this tree with a `difflib` line diff (`/root/crew-tmp/t-0010/citemap.py`
and `/root/crew-tmp/t-0087/citeapply.py`, machine-local). The script takes a bare `:N` as the last
path on its line; each misattribution it produced (a `crew_autopilot.py` line after a
`review_ledger.py` or `commands/autopilot.md` mention, a `.crew/verify.json` range after a
`sabotage.py` one, a historical `at <sha>` README line) was reverted or re-read by symbol with
`grep -n`. `crew_autopilot.py` is 1751 lines: T-0087's refund hunks add 16 lines from `:522`, so
main's citations at or past `:522` moved by 6 to 16 (`next_phase` `:556`, `settings` `:745`,
`deploy_allowed` `:943`, `main` `:1648`) and nothing above it moved. T-0087's `sabotage_tooling`
import at `plugin/crew/tests/sabotage.py:82` puts the `MUTATIONS +=` statement at `:3054-3057`
(refresh `:3054`; resume, autopilot, tracker and route `:3055`; policy, approval, config and tooling
`:3056`). `.crew/verify.json` is 33 rules and 370 lines: T-0087's harness rule is rule 32 at
`:340-365`, after T-0024's rule 31 at `:332-339`. Nothing was executed for this note; the suites ran
with the build.

In this note: the version sentence (1.0.62 at `.claude-plugin/marketplace.json:218`,
`plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) was re-read.

## Re-anchor provenance - `9e38a891` -> `78b7080a`, 2026-09-30 (`T-0087-build` merges T-0088's main `a61a6f38`)

`f702cb24` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68's CI ruff and xdist changes, gate-first review, the steward skill and `crew-qa-standards`) into `T-0087-build`, with a merge commit; its conflicts were mechanical and both sides were kept. `a9bc8877` moves T-0087's version text to 1.0.70 and its harness rule to `.crew/verify.json` rule 35, `90b71bbf` re-sets crew 1.0.70, one past main's 1.0.69, and `78b7080a` rebuilds two guides. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from T-0087's `cb9b79b1` for a note line both parents carry and from `a61a6f38` for a line only main carries, to this tree; a bare `:N` binds to the last path named on its line, with or without a line number): none moved in this map. The version sentence (1.0.70) and the skills count (30; `find plugin/crew/skills -maxdepth 1 -mindepth 1 -type d` re-run on this tree) were updated in place; `.claude-plugin/marketplace.json:217-218`, `plugin/PLUGINS.md:14` and `:17` changed in place, not in position. Citations the script could not attribute to a file that has that line (a bare `:N` after a different file's name, or a short name with no directory) predate this merge and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `78b7080a` -> `b142d8e3`, 2026-09-30 (T-0087 review round 4 fixes)

`dc412c5c` limits the refunded-rerun marker to the `review` phase in `crew_autopilot._review_phase` (+2 lines, so every `crew_autopilot.py` line from `_toward_review` on moves by 2), with a must-block test and sabotage entry (ac); `b5f87132` re-maps `plugin/crew/docs/external-tool-formats.md`'s citations and adds a test that pins them; `af7eccbe` re-times `.crew/verify.json` rule 35 in place (no line moved); `b142d8e3` corrects a CHANGELOG figure. Every body citation of the form `path:line` was re-mapped by script (difflib from `78b7080a` to `b142d8e3`; a bare `:N` binds to the last path named on its line), and the `crew_autopilot.py` citations whose path is on the line above were re-mapped by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.
**Re-anchored `2aa49bb8` -> `b82035e6` on 2026-09-28 (T-0085 merges main `f8b6c8d7`, T-0091).** `17b70570` merged origin/main `f8b6c8d7` into `T-0085-build` (mechanical conflicts only: anchors, provenance paragraphs, INDEX history cells, generated rules and graph); `b82035e6` moves the crew skills claim at `plugin/README.md:414` and `INSTALLATION.md:252` from 29 to 30 (spec Touch amendment). Of the paths this note cites, `git diff --name-only 2aa49bb8 b82035e6` returns `CLAUDE.md`, `INSTALLATION.md` and `plugin/README.md`. `CLAUDE.md`'s change is T-0091's Landmines truncating-`open` paragraph, whose citations were moved on main's side and merged in, plus T-0085's four-line ignore-policy reflow, which shifts no line. Every `CLAUDE.md:N`, `INSTALLATION.md:N` and `plugin/README.md:N` citation was compared by script against its text at `2aa49bb8`, `c192b83d` and HEAD; the skills row's note that both still read 29 is corrected in place. No suite was executed for this note.

**Re-anchored `2442d367` -> `8a084c6c` on 2026-09-28 (T-0085 merges main `6387ab49`, T-0089, T-0090, T-0092; crew 1.0.55).** `f97219dc` merged origin/main `6387ab49` into `T-0085-build` (mechanical conflicts only: crew version lines, CHANGELOG, anchors, provenance paragraphs, INDEX history cells, diagram headers, generated rules and graph); `8a084c6c` re-bumps crew to 1.0.55, one past main's 1.0.54. Each side had already re-verified its own changes (main's line to `136f4b33`/`2442d367`/`b2553d26`, T-0085's to `b82035e6`), so this pass checks the files BOTH sides changed: the crew version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`, value only, same line), `CHANGELOG.md` (both sections kept; release bookkeeping), `plugin/crew/README.md` and `plugin/crew/commands/review.md` (main's T-0092 edits are in place and line-neutral: 2883 and 551 lines, as on T-0085's side), `plugin/crew/hooks/scripts/review_prompt.py` (main's docstring line split in two at `:6-7` and three `excluded` lines added at `:96-98` shift T-0085's lines below them by 4) and `plugin/crew/tests/test_review_prompt.py`. Every `path:N` citation into those files was compared by script against its text on the side that wrote it (`f3ad630b` or `6387ab49`) and at the merged tree; none moved; the version sentence now reads 1.0.55 at `8a084c6c`. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `8a084c6c` -> `07bcaf3b` on 2026-09-28 (T-0085 review round 1 fixes).** `07bcaf3b` changes `plugin/crew/hooks/scripts/crew_standards.py` (`gate_applies`, `checklist_block`, `stamp`, `_plugin_sets`, the module docstring), its tests and sabotage entries, `.crew/standards.md` (REPO-03's rule text), `.crew/verify.json` (rule 31 gains two test files; its `seconds` and `why`), `CHANGELOG.md` (T-0085's bump bullet, two lines to three), `plugin/crew/BUDGETS.md:10-11` (the count, in place), `plugin/crew/README.md` (three table rows, in place), `plugin/crew/commands/implement.md` (two lines reflowed in place; still 120 lines), `plugin/crew/commands/review.md` (step 6's reviewer-cell line becomes three, so lines below `:530` move by 2), `plugin/crew/skills/crew-standards/SKILL.md`, ADR 0004 and the working-with-codex guide. Every `path:N` citation in this note into those files was compared by script between `8a084c6c` and `07bcaf3b`: every hit is a `plugin/crew/BUDGETS.md:11` citation inside an earlier dated provenance paragraph, left as history; no body claim moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `07bcaf3b` -> `8abf7ffe` on 2026-09-28 (T-0085 provisional re-bump, crew 1.0.56).** `8abf7ffe` moves crew's version 1.0.55 -> 1.0.56 in place (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), because the round-1 fixes changed `plugin/crew/` after 1.0.55 was set and `scripts/check-marketplace.py`'s version-drift check failed on it; it also rewords `.crew/standards.md` REPO-03 (the provisional bump) and T-0085's `CHANGELOG.md` heading and bump bullet (three lines to four). Every `path:N` citation in this note into those files was compared by script between `07bcaf3b` and `8abf7ffe`: the version-file citations hold (value changed in place, same line); the body sentence stating crew's version now reads 1.0.56 with this re-bump prepended to its history. Every other hit sits inside an earlier dated provenance paragraph, left as history. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `3648f59a` / `8abf7ffe` -> `e3f5fa49` on 2026-09-29 (T-0085 merges main `2693d0fa`, T-0075 landed as crew 1.0.59, and applies the owner-accepted round-1 standards amendments).** `0fd1bdf8` reverts T-0085's provisional crew 1.0.56 bump (`8abf7ffe`); `0fd92334` merges origin/main `2693d0fa` into `T-0085-build` (mechanical conflicts only: crew version lines take main's 1.0.59, crew counts take main's 36 commands with T-0085's 30 skills, `plugin/crew/tests/sabotage.py` registers both `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS`, anchors, provenance paragraphs, INDEX history cells, diagram notes, generated rules and graph); `e3f5fa49` amends GEN-01 and GEN-04 in `plugin/crew/skills/crew-standards/references/generic.md` and REPO-03 in `.crew/standards.md`, drops the version from T-0085's `CHANGELOG.md` heading and re-measures `plugin/crew/BUDGETS.md`. The build branch now declares main's 1.0.59 and carries no bump of its own (REPO-03 as amended). Every `path:N` citation outside provenance was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from the side that wrote it - `3648f59a` for a line in main's copy of this note, `0fd1bdf8` for a line only in T-0085's - to `e3f5fa49`, and every line that did not map to itself was read with `sed -n` / `grep -n`; the script attributes some bare `:N` to the wrong file, and those were read and hold. None moved; the version sentence now reads 1.0.59 with T-0085's branch history (1.0.56 reverted) and the counts 36 commands / 30 skills. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `e3f5fa49` -> `001f8a78` on 2026-09-29 (T-0085 successor plan, review round 2's fixes).** `bc3602df`..`001f8a78` change `plugin/crew/hooks/scripts/crew_standards.py` (`_scope` gains the merge-base fallback for a kept but unusable scope record, `_has_scope_entry` and `_noted` are new, so every definition from `_scope` down moves by +8 to +30 lines), its tests (`test_crew_standards.py`, `test_review_run_standards.py`, `test_lifecycle_commands.py`) and `plugin/crew/tests/sabotage_standards.py` (nineteen new entries; `STANDARDS_MUTATIONS` moves `:21` -> `:35`), `plugin/crew/skills/crew-standards/SKILL.md` (step 3, +5 lines), `plugin/crew/README.md` (one table row, in place), `CHANGELOG.md` (one bullet in T-0085's section, so every line below it moves +8) and `plugin/crew/BUDGETS.md:11` (the count, in place). Every `path:N` citation in this note into those files was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from `e3f5fa49` to `001f8a78`; none moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `001f8a78` / `bbd9a66d` -> `a7f9c5e4` on 2026-09-29 (T-0085 merges main `8ab733d7`, T-0010 landed as crew 1.0.61).** `a7f9c5e4` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61) into `T-0085-build` after T-0085's review round 3 fixes (`33521aa4`), with mechanical conflicts only: crew version lines take main's 1.0.61 with T-0085's 30 skills (the build branch carries no bump, REPO-03 as amended), `plugin/crew/tests/sabotage.py` registers `POLICY_MUTATIONS`, `APPROVAL_MUTATIONS`, `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS` on `:3056`, anchors, provenance (both sides kept, main's first), INDEX history cells, version sentences, diagram headers, generated rules and graph. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`33521aa4` or `8ab733d7`) and mapped from that side's anchor to `a7f9c5e4` through a difflib line diff (`/root/crew-tmp/t-0085/citemap.py`, machine-local; only cited files that changed; a bare file name resolved when unique in `git ls-files`); each citation that did not map to itself was read with `sed -n` / `grep -n`, and the script's misattributed bare `:N` (a `sabotage_autopilot.py` or `crew_ticket.py` line after another file's name, a history list's earlier positions) were read and hold. `plugin/README.md:414` and `INSTALLATION.md:252` changed in place on T-0085's side (29 -> 30 skills) and hold. The crew version sentence reads 1.0.61, main's, with T-0085's branch history and REPO-03's no-bump note; `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14` re-read. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `a7f9c5e4` / `b4f39fd3` -> `69c7edbd` on 2026-09-30 (T-0085's landing merge of main `a61a6f38`, crew 1.0.70).** `69c7edbd` merges T-0085's build head `0c6f01e0` (round 4, owner-accepted) onto origin/main `a61a6f38` (crew 1.0.69: #263-#267 and T-0088) on `T-0085-land`, and sets crew 1.0.70. Every body `path:N` citation was mapped by script (`difflib` equal blocks, from the anchor of whichever side's copy of this note carries the line - `a7f9c5e4` for T-0085's, main's own anchor for main's - to `69c7edbd`); each that mapped to one new line was moved, and each that did not map, or mapped differently from the two sides, was read with `sed -n` / `grep -n`. The script attributes a bare `:N` to the last path cited with a line number, so a bare `:N` after a path named without one (`.crew/verify.json` rule ranges, `crew_tfplan.py`, `sabotage_autopilot.py`, `crew_ticket.py`, `crew_standards.py`) was read against its real file and put back where the script moved it wrongly; `.crew/verify.json` lines up to `:339` did not move, and T-0085's rule is now `:361-373`, the last. A bare `review.md` citation is ambiguous since #267 added `crew-qa-standards/references/review.md`, so the script skipped those; `plugin/crew/commands/review.md` moved only below `:543` (+1, +3), and its cited lines above that were re-read. In this note crew's version reads 1.0.70 and the skills row 31; `CLAUDE.md:56` moved to `:57`; the marketplace, PLUGINS, README and INSTALLATION lines it cites changed in place. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `69c7edbd` -> `7c86bd13` on 2026-09-30 (T-0085 landing: one sabotage anchor re-taken).** `git diff --name-only 69c7edbd 7c86bd13`, refresh artifacts aside, returns only `plugin/crew/tests/sabotage_standards.py`: the find and replace text of "review.md loses the self-check refusal" now end at `rebuild.` / `provider.`, because the merge joined main's exit-5 sentence onto that line. No line was added or removed; no citation moved. No suite was executed for this note.

**Re-anchored `7c86bd13` (`obsidian-vault`: `69c7edbd`) -> `c04dd2ef` on 2026-09-30 (T-0085 landing: `commands/review.md` rewrapped to its 551-line allowance, crew 1.0.71 then 1.0.72).** `git diff --name-only 7c86bd13 c04dd2ef`, refresh artifacts aside, returns the crew version files, `CHANGELOG.md`, `plugin/crew/BUDGETS.md` (20,707 lines, in place) and `plugin/crew/commands/review.md`: step 3's item 3 gains its last line on `:511`, item 4 and its `gh pr comment` paragraph and steps 8-9 are rewrapped at 100 columns, and the closing sentence is joined, taking the file from 557 to 551 lines with no text changed. Every line this note cites in `review.md` is at or above `:511` and holds; the version this note states now reads 1.0.72. No suite was executed for this note.

**Re-anchored `c04dd2ef` -> `8a89a596` on 2026-09-30 (T-0085 landing: catch-up merge of main `6813749b`, #268 T-0097, crew 1.0.70; T-0085 now 1.0.73).** `git diff --name-only 54192270 8a89a596` returns the crew version files, `CHANGELOG.md` (T-0097's entry below T-0085's), the 11 `.ps1` hook carriers (one `Resolve-CrewPython` line each: an empty probe answer is no longer piped into `ConvertFrom-Json`), `plugin/crew/tests/sabotage_scope.py` and `plugin/crew/tests/test_ps1_python_probe.py`. Citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 11 moved, 0 unmapped); version-line citations (`marketplace.json:218`, `plugin.json:3`, `PLUGINS.md:14`) hold by line and now read 1.0.73. The `Resolve-CrewPython` copies stay byte-identical across all 11 carriers, so the copy-list claims hold. No suite was executed for this note.

**Re-anchored `8a89a596` -> `9b6b0da7` on 2026-09-30 (T-0085 landing: Windows fail-open fix, crew 1.0.74).** `git diff --name-only 58431f49 9b6b0da7` returns the crew version files, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_standards.py` (`import stat`, new `_ancestor_problem` before `gate_applies`, which now proves a receipt absent only when the nearest existing ancestor is a directory), `plugin/crew/tests/test_crew_standards.py` (new `test_gate_applies_when_a_file_parent_is_reported_as_not_found`) and `plugin/crew/tests/sabotage_standards.py` (one entry). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 10 moved, 0 unmapped); `crew.md`'s bare `crew_standards.py` citations in its standards section were moved by the same diff (27). No suite was executed for this note.

**Re-anchored `9b6b0da7` -> `5c9a9db2` on 2026-09-30 (T-0085 landing: sabotage entry re-targeted, crew 1.0.75).** `git diff --name-only 33da9c91 5c9a9db2` returns the crew version files, `CHANGELOG.md` and `plugin/crew/tests/sabotage_standards.py` (the "receipt that cannot be looked up" entry now flips `gate_applies`' `OSError` verdict). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 9 moved, 0 unmapped). No suite was executed for this note.

## Re-anchor provenance - `b142d8e3` / main `5c9a9db2`-`37f4e807` -> `2697bf67`, 2026-09-30 (T-0087 review round 5 successor, merge of main `9af34e57`)

`4e97588e` (golden leak check) and `2de03e41` (review ledger successors path) fix review round 5; `7b62e321` adds their sabotage entries. `7ccff1db` merges origin/main `9af34e57` (T-0085 landed as crew 1.0.75, with #268, #276, #277, #279) into `T-0087-build` with a merge commit, and `2697bf67` re-sets crew 1.0.76. The merge's map conflicts were mechanical: a hunk that differed only in numbers or in the anchor took main's side, and a provenance hunk kept both. Every body citation of the form `path:line` was then re-mapped by script (difflib from the parent the line came from - T-0087's `7b62e321` for a line T-0087 carries, main's `9af34e57` otherwise - to this tree; a bare `:N` binds to the last path named on its line). `.crew/verify.json` now holds T-0085's standards rule as rule 35 (`:361-373`) and T-0087's harness rule as rule 36 (`:374-399`); those descriptions were re-read by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `2697bf67` -> `45f32c3c`, 2026-09-30 (T-0087, after merging main `9af34e57`)

`5f52ba61` re-maps `plugin/crew/docs/external-tool-formats.md`'s `review_run.py` and `review.md` citations to the merged tree (in place; no line moved), and `2b7e7a05`/`45f32c3c` step crew back and re-set 1.0.76 as the last `plugin/crew` commit. No citation in this note points into a line that moved. Re-anchor only: no claim moved and nothing was executed for this note.

## Re-anchor provenance - `45f32c3c` -> `7c88bf3d`, 2026-09-30 (T-0087 review round 6 fix)

`cff30f72` makes the committed-corpus test in `plugin/crew/tests/test_review_golden.py` run `golden_build.leak` on every fixture (host name included), adds `test_corpus_leak_check_refuses_a_planted_host_name`, and adds sabotage entries (ah)-(ai) to `plugin/crew/tests/sabotage_tooling.py`; its CHANGELOG bullet moved later CHANGELOG lines by 4, and the CHANGELOG citations above were re-mapped by script (difflib `45f32c3c` -> `7c88bf3d`). `49ed9a29` / `7c88bf3d` step crew back and re-set 1.0.76. No other cited line moved. Re-anchor only: nothing was executed for this note.

## Re-anchor provenance - `7c88bf3d` -> `680e6783`, 2026-09-30 (T-0087 merges main `b601d450`, L-0521)

`680e6783` merges origin/main `b601d450` (L-0521: opt-in self-hosted runners for the crew pytest `test` job and the `crew-shell-matrix` ubuntu leg, #280) into `T-0087-build`. Of the paths this note cites, only `AGENTS.md` changed (L-0521's runner paragraph); a difflib re-map of every `path:line` citation from `7c88bf3d` to `680e6783` moved none. The `verification-harness` note's own L-0521 paragraph came from main's side cleanly. Re-anchor only: nothing was executed for this note.

**Re-anchored `5c9a9db2` -> `06cb9b51` on 2026-09-30 (T-0086 slice 1: the Python standards set, on main `301e478a`).** `git diff --name-only 5c9a9db2 06cb9b51` over this note's paths returns T-0086's files - `plugin/crew/skills/crew-standards/references/python.md` (new, set PYTHON), `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/test_crew_standards.py` (four new tests), `plugin/crew/tests/sabotage_standards.py` (three entries), `plugin/crew/README.md`, `plugin/PLUGINS.md` (rows only), `plugin/crew/BUDGETS.md` (count only) and `CHANGELOG.md` (T-0086's entry on top) - plus main's own commits since `5c9a9db2`. Path-qualified citations into changed files were moved by a line diff (`/root/crew-tmp/t-0086/remap.py`, 9 moved); `plugin/crew/BUDGETS.md:10-11` citations stay on the claim line, whose number changed in place. No suite was executed for this note.
**Re-anchored `06cb9b51` -> `35100955` on 2026-09-30 (T-0086's merge of main `9af34e57`, #279: CI triggers, concurrency, PR CI on Python 3.12 only).** `git diff --name-only 06cb9b51 35100955` returns, outside refresh artifacts, only `.github/workflows/*.yml`, `AGENTS.md` and `.crew/verify.json` (one line rewritten in place, line count unchanged). No `AGENTS.md:NN` citation exists in any map, and no claim outside verification-harness.md states the CI trigger shape (checked by grep for `push, pull_request`, `six workflows`, `three Python versions`, `windows-latest`), so no citation moved. No suite was executed for this note.

**Re-anchored `35100955` -> `fb292689` on 2026-09-30 (T-0086 review round 1's FIX: PYTHON-07's finding count).** `git diff --name-only 35100955 fb292689` returns only `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-07's Why, `6` -> `7` in place, line count unchanged), `plugin/crew/tests/test_crew_standards.py` (two tests and a pinned table inserted after `:302`) and `plugin/crew/tests/sabotage_standards.py` (four docstring lines after `:43`, two entries at the end; `STANDARDS_MUTATIONS` `:54` -> `:57`, 49 entries by `len()`). Every `path:N` citation into those files sits inside an earlier dated provenance paragraph, left as history. No suite was executed for this note.

**Re-anchored `fb292689` -> `f2cf0508` on 2026-09-30 (T-0086's merge of main `b601d450`, #280 L-0521: opt-in self-hosted runners).** `git diff --name-only fb292689 f2cf0508` returns, outside refresh artifacts, only `.github/workflows/pytest-crew.yml` (the `test` and `crew-shell-matrix` `runs-on` expressions) and `AGENTS.md` (one inserted paragraph after `:50`). No map cites `AGENTS.md:NN` or `.github/workflows/pytest-crew.yml:NN`; the one claim about those jobs' runner placement is verification-harness.md's, which main's own L-0521 commit already updated and the merge carries. No citation moved. No suite was executed for this note.

**Re-anchored `f2cf0508` -> `38b220cf` on 2026-09-30 (T-0086 review round 2's FIXes, merge of main `a7524aac` (T-0087, crew 1.0.76) as `142421d0`, crew 1.0.77).** `27387d83` fixes round 2: `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-01's EncodingWarning quote whole, +1 line; PYTHON-03's splitlines table escapes U+2028/U+2029), `plugin/crew/tests/test_crew_standards.py` (two tests before `test_python_set_applies_to_python_files_only`), `plugin/crew/tests/sabotage_standards.py` (four docstring lines, two entries; `STANDARDS_MUTATIONS` `:57` -> `:61`, 51 by `len()`), `plugin/crew/BUDGETS.md` and `CHANGELOG.md`. `142421d0` merges main's T-0087 with a merge commit; its map conflicts were mechanical: anchors took T-0086's side, provenance hunks kept both (main's first), and one-line hunks differing only in numbers took theirs plus T-0086's own shift (ours + theirs - base, per number); INDEX rows keep main's history cell plus T-0086's additions; `sabotage.py`'s import `:84` -> `:85` and append `:3061` -> `:3062` were set in the body. `38b220cf` sets crew 1.0.77 (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`). BUDGETS.md re-measured at 21,421 lines across 136 files. No suite was executed for this note.

## Re-anchor provenance - `3648f59a` -> `ea764992`, 2026-09-29 (T-0094)

T-0094 is built on origin/main `2693d0fa`: `3648f59a` plus T-0075's landing branch (crew 1.0.56-1.0.59) and `17d057db`, the README re-pin. T-0094's commits `be023596`..`ea764992` bump crew to 1.0.60 in `plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218` and `plugin/PLUGINS.md:14` (in place), re-measure `plugin/crew/BUDGETS.md:11` (19,426 -> 19,432 across 128 files, in place, under the owner's 2026-09-28 standing rule), and grow `.crew/verify.json` rule 25, which this note does not cite by line outside provenance (its doc rule `:69-78` did not move). Corrected here: the crew version sentence and the BUDGETS re-measure. No count this note states changed: 39 entries, 34 skills, 5 plugins (`check-marketplace.py`: "marketplace: 34 skills, 5 plugins").

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `3648f59a` to the tree at `ea764992` (difflib equal blocks); the only non-self mappings were the three version lines and `BUDGETS.md:11`, each changed in place and read with `sed -n`. Nothing else was executed for this note beyond `check-marketplace.py`.

## Re-anchor provenance - `ea764992` -> `f79e9f58`, 2026-09-29 (T-0094 review round 1)

`f79e9f58` ends T-0094's review-round-1 fixes (`abe87bc2`..`f79e9f58`). Of the paths this map cites, `.crew/verify.json` (rule 25's `seconds` and `why`, in place), `plugin/crew/README.md` (one refresh-admission paragraph reworded in place) changed; no citation here moved (checked by script, every `path:N` compared line by line from `ea764992` to `f79e9f58`, then the hits read). No claim changed.

## Re-anchor provenance - `bbd9a66d` + `f79e9f58` -> `6375524b`, 2026-09-29 (T-0094 merges `8ab733d7`; review round 2's successor)

`f050cd47` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored `bbd9a66d`) into T-0094-build at `ca5b1f35` (T-0094's side anchored `f79e9f58`, plus review round 2's FIX 1 `da1532d6` and FIX 2 `ca5b1f35`). The artifact conflicts were anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first; INDEX history columns joined; body hunks resolved to main's lines except T-0094's own refresh-admission paragraph and refresh-check entry point. After it, `157237c2` splits `.crew/verify.json` rule 25 (the admission suite is rule 32 at `:342-349`, rule 25 `:269-287`, every later rule moves by the merged and split lengths), restates the sabotage counts in `plugin/crew/tests/sabotage_refresh.py`, and edits `plugin/crew/README.md` and `docs/guides/crew/src/daily-workflow-scope.md` in place; `ef5b4c89` re-measures `plugin/crew/BUDGETS.md` (19,500 lines across 128 files); `fc348c89` sets crew 1.0.62; `6375524b` rebuilds the daily-workflow guide. `git diff --name-only bbd9a66d 6375524b`, refresh artifacts aside, is T-0094's files only: `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, the daily-workflow guide and its source, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `commands/done.md`, `commands/implement.md`, `completion_audit.py`, `crew_refresh_check.py`, `scope_guard.py` and T-0094's five test files. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`8ab733d7` or `ca5b1f35`) and mapped to HEAD with a `difflib` line diff (`/root/crew-tmp/t-0094/cite_map_merge.py`, machine-local); each that did not map to itself was read with `sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were that misattribution and hold; a history position ("before", "at <sha>", "since ...") was left as written. Re-derived here: the version sentence (1.0.62 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) and the BUDGETS re-measure (19,500 across 128 on `plugin/crew/BUDGETS.md:11`). `scripts/check-marketplace.py` passes at `fc348c89`. No install script, `README.md` or `INSTALLATION.md` changed; neither install script was executed.

## Re-anchor provenance - `6375524b` -> `f5d0f1b1`, 2026-09-30 (T-0094 merges `a61a6f38`, crew 1.0.70)

`0cd952b2` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68, the review gate `review_gate.py`, the `crew-qa-standards` skill, parallel CI and `CLAUDE.md`'s evidence moved to `docs/claude-md-evidence.md`) into T-0094-build at `d331c192`. Its conflicts were the version lines, `CHANGELOG.md` (both entries kept, T-0094's first), `.crew/verify.json` (T-0094's rule 32 kept, main's three new rules after it as 33-35), `crew_refresh_check.py`'s imports (both kept) and `plugin/crew/BUDGETS.md` (re-measured, 19,921 lines across 132 files); no code map, diagram or rule file conflicted (main's maps were still at `bbd9a66d`, but for `obsidian-vault.md`). `f5d0f1b1` sets crew 1.0.70, one past main's 1.0.69. Per-path: `git diff --name-only 6375524b f5d0f1b1 -- <the 52 tracked paths this note cites>` returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `CLAUDE.md`, `INSTALLATION.md`, `README.md`, `plugin/PLUGINS.md`, `plugin/README.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_context.py`, `plugin/crew/hooks/scripts/crew_ticket.py`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_autopilot.py`. Citations were re-mapped by a `difflib` line diff from each cited file's copy at the old anchor to `f5d0f1b1` (`/root/crew-tmp/t-0094/cite_apply2.py`, `cite_ident.py`, `cite_explicit.py`, machine-local): an explicit `path:N`, and a bare `:N` whose file is the one named before it in the paragraph, or the one whose old line carries the identifier beside the citation; every mapped line is text-identical at both ends. History positions ("at <sha>", "before", "on <branch>", "it was") and the provenance sections were left as written; a bare `:N` the scripts attributed to the wrong file was found by that identifier check and put back. Re-derived here: the version sentence (1.0.70 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), crew's skill count (30 on every marked site) and the BUDGETS re-measure (19,921 across 132 on `plugin/crew/BUDGETS.md:11`). `scripts/check-marketplace.py` did not change and passes at `f5d0f1b1` ("all checks passed"). `CLAUDE.md:48` is the "A `marketplace.json` inside a plugin directory" stop line after main's restructure. Neither install script was executed.

**Re-anchored `f5d0f1b1` -> `2255fb4d` on 2026-09-30 (T-0094 review round 3).** `2255fb4d` is T-0094's review-round-3 fix commit (Codex round 3 on `e0ccd3f7`: 0 BLOCK / 4 FIX). `git diff --name-only f5d0f1b1 2255fb4d` returns `.crew/codemap/crew.md`, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/sabotage_refresh.py` and `plugin/crew/tests/test_refresh_admission.py`; the two commits after `f5d0f1b1` before it are refresh artifacts only. This note cites those files by name or in its provenance only; no body citation moved.

**Re-anchored `2255fb4d` -> `0c19512c` on 2026-09-30 (T-0094 crew 1.0.71).** `0c19512c` sets crew 1.0.71 (review round 3's fixes changed `plugin/crew/` after 1.0.70 was set, and origin/main is 1.0.70 too, T-0097 #268). Per-path: `git diff --name-only 2255fb4d 0c19512c` over this note's cited paths returns only `plugin/crew/README.md` (two in-place "since 1.0.70" -> "since 1.0.71" edits, line count unchanged), beside the version files and `CHANGELOG.md` (release bookkeeping). Re-derived here: the crew version sentence (1.0.71, read at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3` and `plugin/PLUGINS.md:14`). No body citation moved.

**Re-anchored `0c19512c` (T-0094) / `5c9a9db2` (main) -> `1b9e4bfe` on 2026-09-30 (T-0094 merges main `9af34e57`, T-0085 landed as crew 1.0.75; review round 4's successor, crew 1.0.76).** `e1144866` merges origin/main `9af34e57` into T-0094-build at `7c261a19`; this map conflicted on anchor, version, provenance and cited-line text only (both sides' provenance kept, main's first; body hunks resolved to main's lines for files T-0094 does not change, T-0094's for its own). `c815bed8` and `f3fe692f` are the successor's code steps (`crew_refresh_check.py`: `_names_no_commit` new before `_moved_from`, `_rendered_verdict` pairs its source case-folded; `completion_audit.py`: `_default_artifacts` new after `_verdicts`; their tests, fixtures and sabotage entries), and `1b9e4bfe` sets crew 1.0.76 with the README, CHANGELOG and daily-workflow guide text. Per-path, `git diff --name-only 5c9a9db2..1b9e4bfe` over this note's 54 cited, existing paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/test_refresh_admission.py`; from T-0094's side, `0c19512c..1b9e4bfe` adds `.crew/standards.md`, `plugin/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_standards.py`, `plugin/crew/hooks/scripts/review_prompt.py`, `plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/generic.md`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_scope.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_lifecycle_commands.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/crew/tests/test_review_prompt.py` (main's T-0085, T-0097 and CI changes). Every body `path:N` citation was mapped by `/root/crew-tmp/t-0094/cite_map_merge.py` (difflib equal blocks, from the anchor of whichever side's copy carries the line; `MAIN_REV=origin/main`, `OURS_REV=7c261a19`) and each one it reported was read at HEAD. The crew version sentence now says 1.0.76 (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218` and `plugin/PLUGINS.md:14`, each in place). No other body citation moved. No suite was executed for this note.

**Re-anchored `1b9e4bfe` -> `8a15557b` on 2026-09-30 (T-0094: `implement.md` step 6 rewrapped to its 120-line budget).** `git diff --name-only 1b9e4bfe 8a15557b`, refresh artifacts aside, returns `plugin/crew/BUDGETS.md` (the count, in place: 20,711 lines) and `plugin/crew/commands/implement.md`: the merged step-6 paragraph (T-0094's admission sentence beside main's self-check paragraph) was 122 lines, over `test_lifecycle_commands.py`'s 120-line command budget, and is rewrapped to 104 columns with its wording unchanged, so every line from the self-check paragraph down sits where main has it again (tracker `:112`, step 7 `:116`); the refresh check is still `:93`. No other body citation moved. No suite was executed for this note beyond `test_lifecycle_commands.py`.

**Re-anchored `8a15557b` -> `a0c171c7` on 2026-09-30 (T-0094 review round 5).** `git diff --name-only 8a15557b a0c171c7` over this note's cited paths, refresh artifacts and release bookkeeping aside, returns `docs/guides/crew/src/daily-workflow-scope.md` (one could-not-tell sentence extended, +1 line at `:104-106`), `plugin/crew/README.md` (one sentence extended in place, line count unchanged), `plugin/crew/hooks/scripts/crew_refresh_check.py` (`_present` new at `:327`, everything below it +19 to +25 lines), `plugin/crew/tests/sabotage_refresh.py` (+4 docstring lines, five entries appended after the round-5 marker), `plugin/crew/tests/test_refresh_admission.py` (+1 import line, the round-5 tests appended). No body citation of this note names a moved line of those files. Citations checked with `/root/crew-tmp/t-0094/cite_apply3.py` (DRY, machine-local) and `grep -n`. No suite was executed for this note.

**Re-anchored `a0c171c7` (T-0094) / main -> `a0db0703` on 2026-09-30 (T-0094 merges origin/main `a7524aac`, T-0087 landed as crew 1.0.76, #281, and L-0521, #280; crew 1.0.77, before review round 6).** `f6f2c2f0` merges `a7524aac` into T-0094-build at `75565970`; `a0db0703` re-sets the version one past main's 1.0.76 (plugin.json, marketplace.json, `plugin/PLUGINS.md:14`, two README sentences, the CHANGELOG heading). The code maps conflicted on anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first. In body hunks a citation into a file only one side changed takes that side's number (`crew_autopilot.py`, `review_ledger.py`, `sabotage.py` and `CLAUDE.md` main's; `crew_refresh_check.py` T-0094's); positions in files both sides changed (`.crew/verify.json`, `plugin/crew/tests/sabotage_refresh.py`) were re-measured on the merged tree: T-0087's harness rule is rule 37 at `.crew/verify.json:431-457`, after T-0094's rule 32; `REFRESH_MUTATIONS` is at `plugin/crew/tests/sabotage_refresh.py:119`; the CLAUDE.md Lessons line is `:144`. Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from each side's anchor (`a0c171c7` and main's own) to `a0db0703` (difflib equal blocks): no citation outside those re-measured positions fails both mappings. Carried as main has them, not corrected here: main's own `crew_autopilot.py` body citations in `crew.md` that already lag main's tree by a few lines (e.g. `next_phase` `:556`, the def is at `:559`) - outside T-0094's change.

**Re-anchored `a0db0703` (T-0094) / `38b220cf` (main) -> `65abeb8d` on 2026-09-30 (T-0094 merges origin/main `549cda24`, T-0086 landed as crew 1.0.77, #282, as `44407f8e`; the owner's split moves the harness half to L-0540 at `c974f997`; review round 6's successor `6ecb6403`..`b17266ed`; crew 1.0.78 at `65abeb8d`).** Per-path, `git diff --name-only a0db0703 65abeb8d` over this note's 75 cited, tracked paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `CHANGELOG.md`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/python.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_refresh_admission.py`; from main's side, `git diff --name-only 38b220cf 65abeb8d` over the same paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `.crew/verify.json`, `CHANGELOG.md`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. The merge's conflicts in this map were the anchor and provenance only (both kept, main's first). No body citation in this map names a line the successor or the merge moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=b4d87187`, machine-local). No suite was executed for this note.

**Re-anchored `65abeb8d` -> `1f21f73b` on 2026-09-30 (T-0094 review round 7: `902fb96a`..`91da43bc` code and tests, docs, guide rebuilt, crew 1.0.78 un-set and re-set as `1f21f73b`).** `git diff --name-only 65abeb8d 1f21f73b` returns `CHANGELOG.md`, `docs/guides/crew/crew-1.0-daily-workflow.docx`, `docs/guides/crew/crew-1.0-daily-workflow.html`, `docs/guides/crew/crew-1.0-daily-workflow.pdf`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. No body citation in this map names a line that moved. No suite was executed for this note.

**Re-anchored `1f21f73b` (T-0094) / main -> `17d0b1d2` on 2026-09-30 (T-0094 merges origin/main `d1462bbd`, L-0529 landed as crew 1.0.80 (#283), and re-sets crew 1.0.81 in the merge commit).** `git diff --name-only 79ef56c4 17d0b1d2`, refresh artifacts aside, returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/README.md`, `plugin/crew/tests/crew_fixtures.py`, `plugin/crew/tests/test_context_watch_python_resolver.py`, `plugin/crew/tests/test_event_claim_crash_safety.py`, `plugin/crew/tests/test_path_link_farm.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/obsidian-vault/.claude-plugin/plugin.json`, `plugin/obsidian-vault/hooks/scripts/_test/test_python_probe_proof.py`: main's L-0529 files plus the version statements. The merge's conflicts were version lines and the generated rules' stamps; main's body lines kept. Re-derived here: the version sentence (1.0.81). No body citation moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=79ef56c4`; its only flags are history positions in verification-harness.md's per-commit lists, left as written). No suite was executed for this note.

## Re-anchor provenance - main `6a8c60b1` -> `c43a54c1`, 2026-09-30 (T-0028, feature half, crew 1.0.84)

T-0028 (the Kimi Code provider, feature half after the owner's split; the review launch is L-0527)
merged origin/main `6a8c60b1` (L-0531 #284 and T-0099 #278, crew 1.0.83) with rerere disabled, taking main's code
maps. The branch differs from main only in the Kimi provider's feature files (`crew_state.py`,
`crew_config.py` with the launch gate, `kimi_probe.py`, the templates, provider docs and tests,
`.crew/verify.json`, the release files). This note is main's copy; every body citation into a
changed file was mapped by a `difflib` line diff from `6a8c60b1` to `c43a54c1` with
`/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved citation landing on the
same line text. crew is 1.0.84 and BUDGETS.md reads 21,513 across 137, both re-read. T-0028's earlier branch provenance is in git history. Re-anchor
only (owner refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `c43a54c1` -> `f4adf923`, 2026-09-30 (T-0028 re-sets crew 1.0.85)

`f4adf923` changes only the release files (crew 1.0.84 -> 1.0.85: `plugin.json`, `marketplace.json`,
`PLUGINS.md`, the README's version mention and the CHANGELOG heading), because T-0505 targets
1.0.84. No cited line moved; the version sentences were re-read. Re-anchor only (owner
refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `f4adf923` -> `328fdf4a`, 2026-09-30 (T-0028 round-7 fixes, crew 1.0.85 re-set)

`233701d5` fixes review round 7's four FIXes in `kimi_probe.py` (the owner accepted round 7 and
ordered the fixes); `328fdf4a` re-sets crew 1.0.85. Body citations were mapped by `difflib` from
`ea90a4e4` to `328fdf4a` with `/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved
citation landing on the same line text. BUDGETS.md reads 21,515 across 137, re-read. Re-anchor only (owner refresh-artifact
standing rule, 2026-09-28); no test suite was executed for this note.

**Re-anchored `17d0b1d2` -> `c4e2eb98` on 2026-09-30 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)).** `git diff --name-only 17d0b1d2 c4e2eb98` adds L-0520's PR 1 outside refresh artifacts (crew_train.py, done.md, README, two guides, CHANGELOG, TODO, BUDGETS.md in place, verify.json, two tests); path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`, machine-local). No suite was executed for this note.

**Re-anchored `c4e2eb98` -> `0be97503` on 2026-09-30 (L-0520 PR 1 merges main 42af3fb7 (L-0531)).** `git diff --name-only c4e2eb98 0be97503` returns, outside refresh artifacts, only L-0531's `plugin/crew/tests/sabotage_qa.py`, `.crew/verify.json` and release bookkeeping; path-qualified citations were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `0be97503` -> `14bb59ef` on 2026-09-30 (L-0520 PR 1 merges main 6a8c60b1 (T-0099)).** `git diff --name-only 0be97503 14bb59ef` returns, outside refresh artifacts, T-0099's `review_prompt.py`, `sabotage_review.py`, `test_review_prompt.py` and release bookkeeping; path-qualified citations were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `14bb59ef` -> `8bf710ed` on 2026-09-30 (L-0520 PR 1 review round 1 fixes).** `git diff --name-only 14bb59ef 8bf710ed` returns crew_train.py, done.md and README.md (edits in place), BUDGETS.md, two tests and the version files; path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `8bf710ed` -> `14b52c91` on 2026-09-30 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86).**  No suite was executed for this note.

**Re-anchored `14b52c91` -> `0c3508e9` on 2026-09-30 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86).**  No suite was executed for this note.

**Re-anchored `0c3508e9` -> `fe524012` on 2026-09-30 (L-0513, the shared gate runner `scripts/gate-runner.py`; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 0c3508e9 fe524012` returns, outside refresh artifacts, `.crew/verify.json` (rule 22's `run`, `seconds` and `why` in place, and rule 40 appended after T-0028's Kimi rule 39 at `:426-430`), `CLAUDE.md` (a two-line gate-runner pointer in Commands, so every line from the old `:14` moved down 2), `CHANGELOG.md`, `README.md` (main's re-pin `767fa3ef`, in place), `scripts/gate-runner.py` and `scripts/_test/gate-runner.py`; no `plugin/crew` path. Every `CLAUDE.md:N` and `.crew/verify.json:N` body citation in this note was re-read with `grep -n`/`sed -n`. `CLAUDE.md:57` -> `:59` (the marketplace.json-inside-a-plugin rule). No suite was executed for this note.

**Re-anchored `fe524012` -> `4eacfacf` on 2026-09-30 (L-0513 step 6 fix: the inner gate runner exits 128+signum after a signal).** `git diff --name-only fe524012 4eacfacf` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py` and `.crew/verify.json` (rules 22 and 40: `why` text only, in place; line count unchanged, rule 40 still `:426-430`). No body citation in this note moved. No suite was executed for this note.

**Re-anchored `4eacfacf` -> `3437cbdd` on 2026-10-01 (L-0513 Fix phase: review round 1's 2 BLOCK and 6 FIX; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 4eacfacf 3437cbdd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `CHANGELOG.md` (the L-0513 Unreleased entry, +9 lines) and `.crew/verify.json` (rules 22 and 40: `seconds` 12 -> 20 and `why` text, in place; line count unchanged, rule 40 still `:426-430`). No body citation of this map points into those files' changed lines. No suite was executed for this note.

**Re-anchored `3437cbdd` -> `e41bc6fd` on 2026-10-01 (L-0513 successor plan: review round 2's six fixes, after `git -c rerere.enabled=false merge origin/main` at `1899c370`; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only 3437cbdd e41bc6fd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 20 -> 41, in place, line count unchanged), and from main's merge `.github/workflows/runner-autostart.yml`, `CHANGELOG.md` (+22 lines at `:31`, W-0116's entry), `plugin/PLUGINS.md:14`, `.claude-plugin/marketplace.json:224` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.86 -> 1.0.89, in place), `plugin/crew/hooks/scripts/crew_refresh_check.py` (+43 lines, inserted after `:686`, `:694` and `:713`) and `plugin/crew/tests/test_refresh_admission.py`. No body citation of this map points into a moved line of those files. No suite was executed for this note.

**Re-anchored `e41bc6fd` -> `4a48f594` on 2026-10-01 (L-0513 Fix phase: review round 3's BLOCK, five FIX and the NIT; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only e41bc6fd 4a48f594` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 41 -> 55 and their `why` text, in place, line count unchanged) and `CHANGELOG.md` (+7 lines inserted after `:29`, inside L-0513's own entry). No map cites a `scripts/gate-runner.py` line. The `CHANGELOG.md:N` figures inside earlier re-anchor notes describe the file at those notes' own anchors and are left as written; none is a body citation of current content. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `6e581365` on 2026-09-30 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91).** `git diff --name-only 0c3508e9 6e581365` outside the refresh artifacts returns W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` and `plugin/crew/tests/test_refresh_admission.py`, `.github/workflows/runner-autostart.yml` (#294), the repo README, and T-0505's files: `promote-gate.sh`/`.ps1`, the new `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md (+2 lines in section 16), the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` (rule 4 path), the troubleshooting guide and its builds, the cloud handoff note and README, CHANGELOG.md and the version files (crew 1.0.91, past main's 1.0.89). A difflib re-map of every path-qualified `path:line` citation in the eight maps (history sections skipped) moved four: `crew_refresh_check.py:970` -> `:1013` (W-0116) and three `plugin/crew/CONFIG.md:2422-2429` -> `:2412-2419` (T-0505's sentence); none was unmapped. Re-applied by hand in `crew.md`: `promote-gate.sh:79` is the plain `crew_py()` call (re-read with `grep -n`), and `promote-gate.sh` is not a `crew_config.py` user (no `crew_config` import or `.crew/config.json` read in either flavour). Bare `:N` continuations and `CHANGELOG.md` citations in history sections were left as written. No suite was executed for this note.

**Re-anchored `6e581365` -> `9580571e` on 2026-10-01 (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91).** `git diff --name-only 6e581365 9580571e` outside the refresh artifacts returns only `plugin/crew/.budget-allowance.json`: promote.md's entry edited in place (`lines` 335 -> 380, reason `T8: to trim` -> a `raised:` reason), line count unchanged. No note cites a line of that file; a difflib re-map of every path-qualified citation moved none. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `bf7ce780` on 2026-09-30 (L-0558: L-0520 round-2 fixes and the rerere rule, crew 1.0.87).**  No suite was executed for this note.

**Re-anchored `bf7ce780` -> `dbad6519` on 2026-09-30 (L-0558 self-review fixes, crew 1.0.87).** `git diff --name-only bf7ce780 dbad6519` touches only crew_train.py, its tests and CHANGELOG.md's top entry; nothing this map cites by line moved. No suite was executed for this note.

**Re-anchored `dbad6519` -> `c8118baf` on 2026-09-30 (L-0558 lint fix and version re-set).** `git diff --name-only dbad6519 c8118baf` returns, outside refresh artifacts, `plugin/crew/tests/test_crew_train.py` (one trailing blank line dropped) and the three version files (stepped back and re-set to 1.0.87 on the same lines); nothing any map cites by line moved. No suite was executed for this note.

**Re-anchored `c8118baf` -> `afd976ee` on 2026-09-30 (L-0558 review round 1 fix).** `git diff --name-only c8118baf afd976ee` returns, outside refresh artifacts: CHANGELOG.md plugin/crew/README.md plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py - see the merge-train section for crew_train.py citations, re-mapped by definition name; no other cited line moved. No suite was executed for this note.

**Re-anchored `afd976ee` -> `d21fa82d` on 2026-09-30 (L-0558 round-2 fixes and main merge, crew 1.0.95).** `git diff --name-only afd976ee d21fa82d` returns, outside refresh artifacts: .claude-plugin/marketplace.json CHANGELOG.md plugin/PLUGINS.md plugin/crew/.claude-plugin/plugin.json plugin/crew/README.md plugin/crew/hooks/scripts/crew_refresh_check.py plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py plugin/crew/tests/test_refresh_admission.py - crew_train.py citations in the merge-train section were re-mapped by definition name; W-0116's crew_refresh_check.py and test_refresh_admission.py are main's (merged with rerere disabled at 8935fc25), and no line this map cites in them is relied on here without re-reading; the version files moved value, not line. No suite was executed for this note.

**Re-anchored `9580571e` -> `b0ac0e1a` on 2026-09-30 (L-0558 merges main 6fe0e0db (T-0505), crew 1.0.95).** Both histories are kept above: main's T-0505 chain to 9580571e and L-0558's chain to d21fa82d, merged at f7118a04 with rerere disabled. `git diff --name-only 9580571e b0ac0e1a` outside refresh artifacts is L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, the two guide sources and their outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's W-0116 files already in 9580571e's ancestry; the merge-train section's crew_train.py citations were re-mapped at d21fa82d and crew_train.py has not changed since; no other cited line moved. No suite was executed for this note.

**Re-anchored `b0ac0e1a` (main) and `b0ac0e1a` (L-0558) -> `89ebda03` on 2026-10-01 (L-0558 merges main 52489039: T-0110 #297, T-0040 #290; crew 1.0.102).** Both histories are kept above; the merge (c481ada4) ran with rerere disabled. `git diff --name-only b0ac0e1a 89ebda03` outside refresh artifacts is 36 paths: L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, two guide sources and outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's commits since b0ac0e1a; the merge-train section's crew_train.py citations hold (crew_train.py unchanged since 7a71faff); no other line this map cites was re-checked beyond the merge. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `5ab63076` on 2026-09-30 (L-0516: deadline polls replace fixed sleeps in the flaky crew tests, crew 1.0.89; verify.json gains rule 10 so later rules shift by one and six lines).**  No suite was executed for this note.

**Re-anchored `5ab63076` -> `805b0a25` on 2026-09-30 (L-0516 split per the tooling-PR rule: sabotage_qa.py back to main's copy, its four entries move to L-0563; verify.json rule 10's why and CHANGELOG reworded in place).**  No suite was executed for this note.

**Re-anchored `805b0a25` -> `7ecbdc7f` on 2026-09-30 (L-0516 re-bumps crew to 1.0.91 after the split; version files, CHANGELOG heading and the two version sentences only).**  No suite was executed for this note.

**Re-anchored `7ecbdc7f` -> `a9c0d9ab` on 2026-09-30 (L-0516: pylint R1732 fix in test_poll_fixtures.py (with-blocks, no line this map cites moves) and crew re-bumped to 1.0.92; version files, CHANGELOG heading and the two version sentences in place).**  No suite was executed for this note.

**Re-anchored `a9c0d9ab` -> `083cda66` on 2026-10-01 (L-0516 merges main `64b04c6b` (W-0116 #292: `crew_refresh_check.py` gains the Windows `_FINAL_PATH` check, `test_refresh_admission.py` two Windows premises; runner-autostart.yml) and crew re-bumped to 1.0.93; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only a9c0d9ab 083cda66` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `083cda66` -> `908c03af` on 2026-10-01 (L-0516 review round 1 fixes: `poll_until` reads the clock before each probe after the first, `test_poll_fixtures.py` reaps its children with `wait(timeout=10)`, CHANGELOG corrected; crew re-bumped to 1.0.97; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only 083cda66 908c03af` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `908c03af` -> `11f476a2` on 2026-10-01 (L-0516 merges main `6fe0e0db` (T-0505 #296: promote-gate judges the deploy's tree, crew 1.0.92) without rerere and re-bumps crew to 1.0.98).** Conflicts were refresh artifacts, CHANGELOG, BUDGETS.md and the version files only; each map keeps both branches' history notes (main's first). `git diff --name-only 908c03af 11f476a2` outside the refresh artifacts returns T-0505's files (`promote-gate.sh`/`.ps1`, `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md, `.budget-allowance.json`, the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` rule 4's path, the troubleshooting guide and its builds, the cloud handoff note and README), CHANGELOG.md, BUDGETS.md (21,621 lines, still `:11`) and the version files. Main's own re-maps of those files (`CONFIG.md:2412-2419`, `promote-gate.sh:79`) arrived with the merge; a difflib re-map of every path-qualified citation from `908c03af` to `11f476a2` moved none outside history sections, where `CHANGELOG.md` and `CONFIG.md` citations are left as written. `crew_refresh_check.py`'s `main()` `:1406` and `artifact_verdicts` `:1013` keep this branch's values (re-read with `grep -n`; main's map still read `:1363`/`:970`). No suite was executed for this note.

**Re-anchored `11f476a2` -> `1390bb23` on 2026-10-01 (L-0516 merges main `52489039` (T-0110 #297 at crew 1.0.97, T-0040 #290 at 1.0.98) without rerere and re-bumps crew to 1.0.100).** Main moved while this lane's suites ran. Conflicts were refresh artifacts, CHANGELOG and BUDGETS.md only; maps, diagram notes and INDEX keep both histories (main's first). A citation re-map that follows each line's origin (this branch's lines from `e9375690`, main's from `52489039`, each to `1390bb23`; history skipped) moved nothing: main's own lines already carry T-0040's moves (`CONFIG.md`, `crew_config.py`, crew README). Re-read by hand: `crew.md`'s W-0116 `_FINAL_PATH` sentence keeps this branch's text (`crew_refresh_check.py:716`); `verification-harness.md`'s verify.json paragraph now reads 42 rules / 443 lines (T-0040's rule 42 at `.crew/verify.json:482-493`, `default` `:441`, `unmapped` `:442`), and rule 39 `:418-431` is unchanged. No suite was executed for this note.

**Re-anchored `1390bb23` -> `0027f794` on 2026-10-01 (L-0516 merges main `05a679bf` (L-0558 #293 at crew 1.0.102) without rerere and re-bumps crew to 1.0.103).** Main moved while this lane's required checks ran. Conflicts were refresh artifacts, CHANGELOG and the version files only; maps, diagram notes and INDEX keep both histories (main's first). Main's change outside refresh artifacts is `crew_train.py`, `test_crew_train.py`, crew README, the daily-workflow and troubleshooting guides, CHANGELOG, the version files and `.crew/verify.json` rule 37's line rewritten in place (443 lines at both `1390bb23` and `0027f794`, so no `.crew/verify.json:N` citation moves). Main's own lines already carry L-0558's `crew_train.py` moves; no line this branch added cites `crew_train.py`, `test_crew_train.py`, the crew README or either guide by line. `crew.md`'s version sentence names 1.0.103 in place. No suite was executed for this note.

**Re-anchored `9580571e` (main's side of the merge) and `4a48f594` (L-0513's side) -> `de32cb87` on 2026-10-01 (L-0513 merges origin/main `44d3dbc6` at `293b78a1` with `git -c rerere.enabled=false`, bringing T-0110 #297 and crew 1.0.97, then review round 4's five fixes; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept above. `git diff --name-only 9580571e de32cb87` outside refresh artifacts returns L-0513's `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 55 -> 57 and their `why`, in place, line count unchanged), `CLAUDE.md` (L-0513's two-line pointer in Commands) and `CHANGELOG.md`, and main's T-0110 files: `.github/workflows/pytest-crew.yml`, `AGENTS.md`, eight files under `plugin/crew/tests/` (`crew_fixtures.py`, `test_msys_tmp_pin.py` and six others) and the version files `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md:14` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.97, in place). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `de32cb87`, found every one mapping onto itself from at least one parent, except the in-place version lines and `CHANGELOG.md:N` figures inside history notes, left as written; `crew.md`'s version sentence now reads 1.0.97. No suite was executed for this note.

**Re-anchored `de32cb87` -> `f23b01b4` on 2026-10-01 (L-0513 Fix phase: review round 5's two FIX findings; repository tooling, no plugin version of its own, crew is main's 1.0.97).** `git diff --name-only de32cb87 f23b01b4` outside refresh artifacts returns `scripts/gate-runner.py` (`_valid_result` now takes the table step, requires phase/group/argv/cwd/timeout, and refuses a FAIL whose rc `classify()` would not call FAIL), `scripts/_test/gate-runner.py` (two new cases, `part_row`), `.crew/verify.json` (rules 22 and 40: `seconds` 57 -> 58 and their `why`, in place, line count unchanged) and `CHANGELOG.md` (+3 lines inside L-0513's entry, at :30-36). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped) from `de32cb87` found every one mapping onto itself except nine `CHANGELOG.md:N` citations in `crew.md`, shifted +3 to the lines they cited, and the in-place `.crew/verify.json:296`/`:430` lines. No suite was executed for this note.

**Re-anchored `f23b01b4` (L-0513's side) and main's side -> `71038cb9` on 2026-10-01 (L-0513 owner amendment for review round 6's BLOCK at `fbd48532`, then `git -c rerere.enabled=false merge origin/main` `52489039` (T-0040 #290, crew 1.0.98) at `74130bbd`, then rules 22 and 40 repriced at `71038cb9`; repository tooling, no plugin version of its own).** `git diff --name-only f23b01b4 71038cb9` outside refresh artifacts returns L-0513's `scripts/gate-runner.py` and `scripts/_test/gate-runner.py` (the BLOCK fix: no process-group signal once the leader is reaped, and its two cases), `CHANGELOG.md` (L-0513's entry +3 lines; T-0040's 1.0.98 entry now sits below it) and `.crew/verify.json` (rules 22 and 40 `seconds` 58 -> 60 and `why`, in place; T-0040's shell-route rule appended as rule 41 at `:432-437`), and T-0040's own paths, which main's side of this map already describes. Where the merge conflicted here it was the anchor header and these provenance notes: both sides kept, main's first. The `CHANGELOG.md:N` citations in older provenance notes name lines at the commits those notes name and were not shifted. Refresh artifacts per owner rule 2026-09-28; no test suite was executed for this note.

**Re-anchored `71038cb9` (L-0513's side) and `89ebda03` (main's side) -> `0d159692` on 2026-10-01 (L-0513 merges origin/main `05a679bf` - L-0558 #293, crew 1.0.102 - at `0d159692` with `git -c rerere.enabled=false`; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept, main's first. `git diff --name-only 71038cb9 0d159692` outside refresh artifacts is main's L-0558 change only: `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py`, `plugin/crew/README.md`, the daily-workflow and troubleshooting guide sources and their six builds, `.crew/verify.json`, `CHANGELOG.md` and the three version files (crew 1.0.102). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `0d159692`, found every one mapping onto itself from at least one parent except three `CHANGELOG.md:N` citations in `crew.md` from L-0513's side, moved to the lines they cited (`:485-486` -> `:519-520`, `:645-646` -> `:679-680`, `:274` -> `:308`); `crew.md`'s version sentence now reads 1.0.102. No suite was executed for this note.

**Re-anchored `0027f794` (L-0516's side) and `0d159692` (main's side) -> `ec95c8aa` on 2026-10-01 (L-0516 merges origin/main `cacf7ff0` - L-0513 #301, the gate runner; crew stays 1.0.102 on main - with `git -c rerere.enabled=false`; crew 1.0.104, re-bumped at `1f2114bc` past 1.0.103, which L-0510's worktree claimed first).** Conflicts were refresh artifacts and CHANGELOG only; each map keeps both re-anchor histories. `git diff --name-only 0027f794 ec95c8aa` outside refresh artifacts returns main's L-0513 paths (`.crew/verify.json` rule 22 rewritten in place at `:262-266` and its gate-runner rule appended at `:432-436`, `CLAUDE.md`, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`) and the three version files plus CHANGELOG; `git diff --name-only 0d159692 ec95c8aa` returns L-0516's own paths. A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor, found every one mapping onto itself from at least one parent except the version lines (changed in place) and nine `CHANGELOG.md:N` citations in `crew.md` from main's side, which L-0516's CHANGELOG entry above them moved by 35 (`:519-520` -> `:554-555`, `:679-680` -> `:714-715`, `:308` -> `:343`, `:676-677` -> `:711-712`, `:887-888` -> `:922-923`, `:898-899` -> `:933-934`, `:1114-1115` -> `:1149-1150`, `:1238` -> `:1273`, `:1134` -> `:1169`). `verification-harness.md`'s verify.json section now reads the merged tree (448 lines, 43 rules). No suite was executed for this note.

**Re-anchored `ec95c8aa` -> `5ffffbe3` on 2026-10-01 (L-0516 merges origin/main `ddcbf90d` - W-0115 #299, T-0040's shell-route sabotage mutations, crew 1.0.106 - with `git -c rerere.enabled=false` and re-bumps crew to 1.0.110, skipping 1.0.105 (L-0557), 1.0.107 (T-0504), 1.0.108 (L-0510) and 1.0.109 (T-0501)).** Conflicts were the three version files and CHANGELOG only. `git diff --name-only ec95c8aa 5ffffbe3` outside refresh artifacts returns W-0115's paths (`plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_shell.py`, `.crew/verify.json`'s last rule gaining one path line) plus the version files and CHANGELOG. A difflib re-map of every path-qualified citation (history notes skipped) moved two `plugin/crew/tests/sabotage.py` citations in `crew.md` by +2 (`:3055` -> `:3057`, `:3056` -> `:3058`; W-0115 adds an import at `:86` and a comment line at `:3055`), the nine main-side `CHANGELOG.md` citations in `crew.md` by +15 for W-0115's entry, and `verification-harness.md`'s verify.json header to 449 lines; every other citation maps onto itself. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `b1d8a4e8` on 2026-09-30 (L-0557: per-test XDG_CACHE_HOME for every pwsh the suites spawn, crew 1.0.89, obsidian-vault 0.4.16).** `git diff --name-only 0c3508e9 b1d8a4e8` returns, outside refresh artifacts, L-0557's test-only files (`plugin/crew/tests/conftest.py`, `plugin/crew/tests/crew_fixtures.py`, new `plugin/crew/tests/test_pwsh_cache_isolation.py`, both `test_flavour_guard.py` copies, the obsidian-vault `_test` suites, six `scripts/_test/*.sh`), `.crew/verify.json` (one new rule, appended after the Kimi rule), `plugin/crew/README.md` (one paragraph after the test-layer table), the harness reference's H4 table (one row), `CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the version files. Body `path:line` citations into those files were moved by difflib from `0c3508e9` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): 25 moved, in crew.md (CHANGELOG), obsidian-vault.md (its `_test` suites) and verification-harness.md (verify.json range unchanged). No hook or production script changed. No suite was executed for this note.

**Re-anchored `b1d8a4e8` -> `d9ccfd5a` on 2026-10-01 (L-0557 merges main 0c0275e8 (W-0116 #292, crew 1.0.89) and re-sets crew 1.0.95).** `git diff --name-only b1d8a4e8 d9ccfd5a` returns, outside refresh artifacts, W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` (a final-path check in `_read_regular`'s no-dir_fd branch, hunks from :684) and `plugin/crew/tests/test_refresh_admission.py`, `CHANGELOG.md` (both sides' Unreleased entries kept) and the version files (crew 1.0.95). Body `path:line` citations into those files were moved by difflib from `b1d8a4e8` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local), each onto the same line text. No suite was executed for this note.

**Re-anchored `d9ccfd5a` -> `97ace923` on 2026-10-01 (L-0557 review round 1 fixes, crew 1.0.96).** `git diff --name-only d9ccfd5a 97ace923` returns, outside refresh artifacts, L-0557's test-only `plugin/crew/tests/conftest.py` (the per-test cache dir is now `tmp_path_factory.mktemp("xdg-cache")`), `plugin/crew/tests/crew_fixtures.py` (one comment), `plugin/crew/tests/test_pwsh_cache_isolation.py` (the static guard judges values and returned environments, reports unreadable suites), `CHANGELOG.md` (L-0557's entry, five lines longer) and the version files (crew 1.0.96: 1.0.95 is also claimed by L-0558, #293). Body `path:line` citations into those files were moved by difflib from `d9ccfd5a` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): none in this map (all 10 are `CHANGELOG.md` in crew.md). No hook or production script changed. No suite was executed for this note.

**Re-anchored `97ace923` / `9580571e` -> `550c39cd` on 2026-10-01 (L-0557 merges main 6fe0e0db: T-0505 #296 crew 1.0.92, runner auto-start #294; crew stays 1.0.96).** `550c39cd` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files and CHANGELOG only. This side's notes were anchored `97ace923` and main's `9580571e`; `git diff --name-only 9580571e 6fe0e0db` outside the refresh artifacts returns only the 1.0.92 version files and CHANGELOG, so main's notes already describe every non-artifact change it brings, and this side's notes describe L-0557's. Body `path:line` citations were moved by difflib, each from the anchor of the side whose copy of this map carries the line (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 17 moved - 10 `CHANGELOG.md` in crew.md (T-0505's 1.0.92 entry now sits below L-0557's) and 7 `plugin/crew/CONFIG.md` in verification-harness.md (T-0505's CONFIG.md edit), every one an exact-text match. No suite was executed for this note.

**Re-anchored `550c39cd` -> `038d5d10` on 2026-10-01 (L-0557 merges main 44d3dbc6: T-0110 #297, crew 1.0.97; L-0557 re-sets crew 1.0.99 at `4fc11923`).** `038d5d10` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were version files, CHANGELOG and one generated rules file. `git diff --name-only 6fe0e0db 44d3dbc6` outside the refresh artifacts returns T-0110's `.github/workflows/pytest-crew.yml`, `AGENTS.md`, `plugin/crew/tests/crew_fixtures.py` (new helpers below L-0557's, auto-merged), seven crew test files, CHANGELOG and the 1.0.97 version files. T-0110 updated verification-harness.md's `pytest-crew.yml` sentence itself; the other files are cited by name only. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 10 moved, all `CHANGELOG.md` in crew.md (T-0110's 1.0.97 entry now sits below L-0557's), every one an exact-text match. No suite was executed for this note.

**Re-anchored `038d5d10` / `44d3dbc6` -> `90186613` on 2026-10-01 (L-0557 merges main 52489039 at `327e6ec1`: T-0040 #290, crew 1.0.98; L-0557 re-sets crew 1.0.101 at `90186613`).** `327e6ec1` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files, CHANGELOG, BUDGETS.md's count and `.crew/verify.json` (both sides appended one rule; both kept). Main's notes (anchor line `44d3dbc6`) were re-taken by T-0040 on its own merged tree `52489039`, so a line only in main's copy of a map is measured from `52489039`; a line in this side's copy is measured from `038d5d10`. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 73 moved, all from this side's lines - `plugin/crew/README.md` (+11 lines from T-0040 above :743), `plugin/crew/CONFIG.md` (+11 from T-0040), `CHANGELOG.md` (T-0040's 1.0.98 entry, then this side's below it), `plugin/crew/tests/test_crew_config.py` and `plugin/crew/hooks/scripts/crew_config.py` (T-0040); every one an exact-text match, none on a changed line. T-0040's own claims about crew_shell.py, crew_status.py and the shell-route config are main's notes above and were not re-derived here. No suite was executed for this note.

**Re-anchored `89ebda03` (main) and `90186613` (L-0557) -> `773ce841` on 2026-10-01 (L-0557 merges main `05a679bf`, L-0558 #293, crew 1.0.102, at `2169bd11` with rerere disabled; L-0557 re-sets crew 1.0.105 at `773ce841`).** Both provenance histories are kept above, main's first. Body citations were re-checked by mapping each one from the tree its line came from (`89ebda03` for main's lines, `74dd1aa5` for L-0557's) to this tree with difflib: no citation moved. Citations into the version lines of `plugin/crew/.claude-plugin/plugin.json`, `plugin/PLUGINS.md` and `.claude-plugin/marketplace.json` keep their line numbers (the value changed in place). No suite was executed for this note.

**Re-anchored `0d159692` (main, L-0513 #301) and `773ce841` (L-0557) -> `a9608aa5` on 2026-10-01 (L-0557 merges main `cacf7ff0`, L-0513 #301: `scripts/gate-runner.py`, no plugin version; rerere disabled; crew stays 1.0.105).** Both provenance histories are kept, main's first. Where both sides had re-mapped the same citation, main's line was taken, and each citation was then mapped with difflib from the tree its line came from (`cacf7ff0` for main's lines, `95036b4c` for L-0557's) to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `a9608aa5` -> `c43a9ce3` on 2026-10-01 (L-0557 merges main `ddcbf90d`, W-0115 #299, crew 1.0.106, at `0597e5c6` with rerere disabled, and re-sets crew 1.0.111 at `c43a9ce3`).** The merge touched no code map. `git diff --name-only a9608aa5 c43a9ce3` outside refresh artifacts is W-0115's `plugin/crew/tests/sabotage.py`, `sabotage_shell.py` and `.crew/verify.json` plus the version files and CHANGELOG; each citation into a changed file was mapped with difflib from `92448f1a` to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `5ffffbe3` (main, L-0516 #298) and `c43a9ce3` (L-0557) -> `6053b65d` on 2026-10-01 (L-0557 merges main `2906dcbd`, L-0516 #298, crew 1.0.110, at `2f3fb34c` with rerere disabled, and re-sets crew 1.0.114 at `6053b65d`).** Both provenance histories are kept, main's first, and main's body citations were taken where both sides had re-mapped the same one. Each citation into a changed file was then mapped with difflib from the tree its line came from (`2906dcbd` for main's lines, `a54ff87b` for L-0557's) to this tree: no body citation moved; the `.crew/verify.json:482-493` range in L-0516's provenance note was kept, because it describes that tree. No suite was executed for this note.

**Re-anchored `6053b65d` -> `f5cab1f9` on 2026-10-01 (T-0503 merges origin/main `ffd11270`, L-0557 #300, crew 1.0.114, at `f5cab1f9` with rerere disabled; bitbucket 1.2.3).** The merge took main's side of every code map. `git diff --name-only ffd11270 f5cab1f9` is T-0503's own change only: `.claude-plugin/marketplace.json` (bitbucket version), `CHANGELOG.md` (its entry, 33 lines at the top), the `bitbucket` catalog row in `README.md` and `skills/README.md` (edited in place, no line count changed), `docs/handoff/cloud/T-0503.md`, and `skills/bitbucket/` (`SKILL.md`, `references/api.md`, `scripts/_test/merge_gate.sh`). Every citation into those files was compared by script against `ffd11270` (158 checked across the eight maps); no other cited line moved. Re-anchor only, under the refresh-artifact standing rule (owner 2026-09-28); no suite was executed for this note.

**Re-anchored `f5cab1f9` -> `b4f04e23` on 2026-10-02 (L-0578 merges origin/main `8d84786d`, W-0117 #302, crew 1.0.115, at `b4f04e23` with rerere disabled; crew 1.0.119).** L-0578's own change is `review_metrics.py` (new), `review_run.py`, `review_patch.py`, `commands/review.md`, the README, BUDGETS.md, external-tool-formats.md, `.crew/verify.json` rule 38, its tests and sabotage entries, and the version files and CHANGELOG. Every full `path:line` citation into a changed file was compared by script (difflib) against the old anchor: none moved; the only citations whose line text changed are the version and count lines (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:224`, `plugin/PLUGINS.md:14`, `plugin/crew/BUDGETS.md:10-11`), which still sit on the lines they cite. No suite was executed for this note.

**Re-anchored `3648f59a` -> `0da787d3` on 2026-09-29 (T-0107, gizmoduck 0.5.4). Current despite the lag.** `crew_refresh_check.py` named README.md, plugin/README.md as changed since the anchor. T-0107 edits exactly one line of each, in place (`git diff --numstat 2693d0fa 0da787d3 -- README.md plugin/README.md` is `1 1` for both): the gizmoduck catalog row, `README.md:875` and `plugin/README.md:415`, gains one clause naming the routine. No line shifted, and a script over every `README.md:N[-M]` citation in `.crew/codemap/` found none covering either line. `plugin/PLUGINS.md` changes only at `:441`, `:446`, `:451` and `:470` (+2 lines after it), and no note cites a `PLUGINS.md` line at or after `:441`. No claim re-read; nothing was executed for this note.

**Re-anchored `bbd9a66d` -> `8730119f` on 2026-09-29 (T-0107 merges origin/main `8ab733d7`). Current despite the lag.** `8730119f` merges origin/main (T-0010 landed, crew 1.0.61, main's anchor `bbd9a66d`) into `T-0107-build`; the conflicts were this header and the provenance tail, resolved mechanically - main's anchor taken, both sides' provenance kept, main's first. `git diff --numstat bbd9a66d 8730119f -- README.md plugin/README.md` is `1 1` for each: T-0107's gizmoduck catalog row, still `README.md:875` and `plugin/README.md:415`, edited in place. No citation outside provenance covers either line, and `plugin/PLUGINS.md` changes only at `:441`, `:446`, `:451` and `:470` (+2 after it), where no note cites a line. Nothing was executed for this note.

**Re-anchored `6053b65d` -> `40292eca` on 2026-10-02 (T-0107 merges origin/main `ffd11270`, without rerere). Current despite the lag.** `40292eca` merges origin/main into `T-0107-build`; the header conflict took main's anchor and both sides' provenance notes were kept, main's first. `crew_refresh_check.py` named README.md and plugin/README.md: `git diff --numstat 6053b65d 40292eca -- README.md plugin/README.md` is `1 1` for each, T-0107's gizmoduck catalog row edited in place, now `README.md:876` (main's side added a line above it) and `plugin/README.md:415`. The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck is re-set to 0.5.4, one patch above main's 0.5.3, after the last content change. Nothing was executed for this note.

**Re-anchored `f5cab1f9` -> `e60394fd` on 2026-10-02 (T-0107 merges origin/main `8d84786d`, without rerere). Current despite the lag.** `e60394fd` merges origin/main (W-0117, crew 1.0.115) into `T-0107-build`; the header conflict took main's anchor and both sides' provenance notes were kept, main's first. Against the scope base `8d84786d`, `crew_refresh_check.py` named README.md and plugin/README.md: `git diff --numstat 8d84786d e60394fd -- README.md plugin/README.md` is `1 1` for each, T-0107's gizmoduck catalog row edited in place, still `README.md:876` and `plugin/README.md:415`. The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `b4f04e23` -> `56f28a16` on 2026-10-02 (T-0107 merges origin/main `04dde5a2`, without rerere). Current despite the lag.** The header conflict took main's anchor and both sides' provenance notes were kept, main's first. Against the scope base `04dde5a2`, `git diff --numstat 04dde5a2 56f28a16 -- README.md plugin/README.md` is `1 1` for each: T-0107's gizmoduck catalog row, edited in place (`README.md:889`, `plugin/README.md:415`). The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `56f28a16` -> `d6e51bb8` on 2026-10-02 (T-0107 merges origin/main `d2ec37d3`, W-0120's re-pin, without rerere; no conflict).** `git diff -U0 56f28a16 d6e51bb8 -- README.md` is main's two install-URL lines, `:12` and `:18`, re-pinned in place to `04dde5a2` (no line shifts); T-0107's gizmoduck catalog row is still `README.md:889` and `plugin/README.md:415`, unchanged. No body citation covers `:12` or `:18` here. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `6053b65d` -> `1066a28d` on 2026-10-01 (L-0575, the recurring-findings checklist for the implementer; `1066a28d` adds only refresh artifacts and the rebuilt daily-workflow guide HTML, DOCX and PDF to `dac06883`).** `git diff --name-only 6053b65d dac06883` returns `.crew/verify.json` (one rule appended, the last, `:454-464`), `CHANGELOG.md` (one Unreleased section, 18 lines), `docs/guides/crew/src/daily-workflow.md`, `plugin/crew/BUDGETS.md` (the count at `:11`), `plugin/crew/README.md` (one paragraph at `:727`), `plugin/crew/commands/fix.md` (step 4, one line), `plugin/crew/commands/implement.md` (step 2 and the method paragraph, still 120 lines), `plugin/crew/skills/crew-qa-standards/SKILL.md`, and three new files: `plugin/crew/hooks/scripts/recurring_findings.py`, `plugin/crew/skills/crew-qa-standards/references/recurring-findings.md` and `plugin/crew/tests/test_recurring_findings.py`. Each citation into a changed file was mapped with difflib from `6053b65d` to this tree; body citations are named below when one moved, and the citations inside earlier provenance notes were kept, because they describe their own trees. No suite was executed for this note.

**Re-anchored `1066a28d` -> `871c5043` on 2026-10-02 (L-0575 review round 1 fixes).** `git diff --name-only 1066a28d 871c5043` returns `.crew/verify.json` (the L-0575 rule's why, in place), `plugin/crew/BUDGETS.md` (the count at `:11`), `plugin/crew/README.md` (the L-0575 paragraph, in place), `plugin/crew/commands/implement.md` (step 2 re-wrapped in place, still 120 lines), `recurring_findings.py`, its data file and its suite. Each citation into a changed file was mapped with difflib from `1066a28d` to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `b4f04e23` (main) and L-0575's `871c5043` -> `2859ab05` on 2026-10-02 (L-0575 merges origin/main 8d84786d at f12f742c and d2ec37d3 at 2859ab05, rerere disabled; crew 1.0.123. Both provenance histories kept, main's first. Body citations were mapped with difflib from the tree each line came from (4234c443 for L-0575's lines, d2ec37d3 for main's): ten CHANGELOG.md citations in crew.md moved +19 (L-0575's entry above main's); verification-harness.md's two verify.json ranges were set by hand to :448-453 (rule 41) and :455-465 (L-0575's rule); crew.md's version sentence reads 1.0.123. History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `b4f04e23` (main) and L-0575's `2859ab05` -> `99c8f66e` on 2026-10-02 (L-0575 merges origin/main 7ba4f9ea (L-0572 #309 crew 1.0.126, L-0593 #312) at 99c8f66e, rerere disabled; crew 1.0.129 is set in the last commit. Body citations were mapped with difflib from the tree each line came from (9dad04ef for L-0575's lines, 7ba4f9ea for main's): ten CHANGELOG.md citations in crew.md moved +21 (L-0572's entry, below L-0575's); verification-harness.md's verify.json ranges were set by hand to :469-476 (rule 41) and :486-496 (L-0575's rule, after L-0572's at :478-485). History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `d6e51bb8` (main) and L-0575's `99c8f66e` -> `273ec0f6` on 2026-10-02 (L-0575 merges origin/main a9b4734d (L-0576 #306 crew 1.0.128, L-0577 #305, T-0107 #273) at 273ec0f6, rerere disabled; crew 1.0.129 is re-set in the last commit. Both provenance histories kept, main's first. Body citations were mapped with difflib from the tree each line came from (986c9ca5 for L-0575's lines, a9b4734d for main's): ten CHANGELOG.md citations in crew.md moved +113 (main's new entries sit below L-0575's), and ten plugin/crew/README.md citations in crew.md and repo-docs.md moved +2 (L-0575's README paragraph at :727 sits above them); verification-harness.md's verify.json ranges were set by hand to :474-481 (rule 41), :483-490 (L-0572) and :491-501 (L-0575, last). History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `6053b65d` -> `3a33161c` on 2026-10-01 (L-0555 PR 1: the diagnostic CI verify-gate receipt - `plugin/crew/hooks/scripts/ci_receipt.py`, `.github/workflows/verify-gate.yml` (mmdc pinned at 12.0.0), `plugin/crew/tests/test_ci_receipt.py` - merging origin/main `ffd11270` (L-0557 #300, crew 1.0.114) at `751d6d2a` with rerere disabled, crew 1.0.116, skipping 1.0.115 claimed by another lane).** Refresh-artifact conflicts were resolved by taking main's side and redoing this pass. `git diff --name-only 6053b65d 3a33161c` outside refresh artifacts returns L-0555's paths only: the three new files, `.crew/verify.json` (one rule appended last, at `.crew/verify.json:481`), `CHANGELOG.md` (+16 lines at the top), `plugin/crew/README.md` (+23 lines in section 17), `scripts/gate-runner.py` (+2 lines in EXCLUDED_WORKFLOWS), `plugin/crew/BUDGETS.md` (count only) and the version files. A difflib re-map of every path-qualified citation into those files (history notes skipped) moved nine `CHANGELOG.md` citations in `crew.md` by +16 and six `plugin/crew/README.md` citations in `repo-docs.md` by +23; every other citation maps onto itself. No suite was executed for this note.


**Re-anchored `3a33161c` -> `79c116b4` on 2026-10-01 (L-0555 gate fix: `ci_receipt.py` asks `review_gate.gate_state` for NO_GATE instead of reading `.crew/config.json` itself; `plugin/crew/BUDGETS.md` count corrected; crew 1.0.116 re-set at `79c116b4`).** `git diff --name-only 3a33161c 79c116b4` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/BUDGETS.md` (the count line only, changed in place, so the `plugin/crew/BUDGETS.md:10` and `:11` citations keep their lines; the version files net to no change). No note cites `ci_receipt.py` at a line, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `79c116b4` -> `8b21ecc3` on 2026-10-01 (L-0555 pre-review fix: `ci_receipt.py` resolves gh with shutil.which and folds the check reason onto one line; crew 1.0.116 re-set).** `git diff --name-only 79c116b4 8b21ecc3` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/tests/test_ci_receipt.py` (the version files net to no change). No note cites either at a line, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `8b21ecc3` -> `1e2762a0` on 2026-10-02 (L-0555 review round 1 fixes: `ci_receipt.py` requires the receipt's gate_impl to match HEAD's and its docstring says diagnostic; the verify.json rule is priced 10s from measured runs; crew 1.0.116 re-set).** `git diff --name-only 8b21ecc3 1e2762a0` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py`, `plugin/crew/tests/test_ci_receipt.py` and `.crew/verify.json` (the last rule's line edited in place, no line moved); the version files net to no change. Every citation maps onto itself. No suite was executed for this note.


**Re-anchored `1e2762a0` -> `b10e3895` on 2026-10-02 (L-0555 review round 2 fixes: `ci_receipt.py` treats an unreadable stand-down as UNKNOWN, re-reads the stand-down at the last look, and anchors the origin host to github.com; crew 1.0.116 re-set).** `git diff --name-only 1e2762a0 b10e3895` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/tests/test_ci_receipt.py`; the version files net to no change. No code map cites a line of either file, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `b4f04e23` -> `fa63852d` on 2026-10-02 (L-0555 merges origin/main `dd95135a`, L-0578 #304, crew 1.0.119, at `fa63852d` with rerere disabled; crew 1.0.127).** The merge took main's anchor and INDEX rows and kept both lanes' re-anchor notes. L-0555's own change against main is `ci_receipt.py`, `test_ci_receipt.py`, `.github/workflows/verify-gate.yml`, `scripts/gate-runner.py`, one `.crew/verify.json` rule (line 454 edited in place, 455 appended), `plugin/crew/README.md` (+23 lines after `:2167`), `CHANGELOG.md` (+17 lines at the top) and the version and count lines. Citations moved by difflib: `CHANGELOG.md` +17 in `crew.md`'s current-citation lines, `plugin/crew/README.md` +23 past `:2167` in `repo-docs.md` (nine). No suite was executed for this note.


**Re-anchored `fa63852d` -> `f937576e` on 2026-10-02 (L-0555 merges origin/main `04dde5a2`, W-0120 #307, the claude- prefix renames, at `f937576e` with rerere disabled; crew 1.0.127).** Only `CHANGELOG.md` conflicted. Citations moved by difflib: this lane's `CHANGELOG.md` lines in `crew.md` +26 (W-0120's entry), `README.md:736` -> `:749` (three, in `repo-docs.md` and `install-scripts.md`) and `skills/README.md:15` -> `:28`. No suite was executed for this note.


**Re-anchored `f937576e` -> `af59b237` on 2026-10-02 (L-0555 merges origin/main `d2ec37d3`, W-0120 #308, README install URLs re-pinned to `04dde5a2`).** The merge changed `README.md:12` and `:18` in place; no line moved. The install-URL pin landmines in `install-scripts.md` and `repo-docs.md` now state the `04dde5a2` pin, and `git log --oneline 04dde5a2..af59b237 -- scripts/install-prerequisites.sh scripts/install-prerequisites.ps1` is empty. No suite was executed for this note.


**Re-anchored `af59b237` -> `7e18daf8` on 2026-10-02 (L-0555 merges origin/main `c7a9e649`: L-0572 #309 (subset coverage under --all, crew 1.0.126), runner auto-start #295, L-0593 #312/#313; rerere disabled; crew 1.0.127).** Conflicts: version files, CHANGELOG (both entries, L-0555's on top), BUDGETS count, `.crew/verify.json` (L-0555's rule then L-0572's), `crew.md`'s version sentence, generated rules. Main's notes for L-0572 came in unchanged. Every main-side citation into a file this branch changes resolves to the same line (difflib), except one historical `CHANGELOG.md:1372` in a past-tense note, left as written. No suite was executed for this note.


**Re-anchored `d6e51bb8` (main) and `7e18daf8` (L-0555) -> `5467b110` on 2026-10-02 (L-0555 merges origin/main `75681fba`: L-0577 #305, T-0107 #273 (gizmoduck 0.5.5); rerere disabled; crew 1.0.127).** The header conflict took main's anchor and both sides' provenance notes, main's first; the install-URL pin bullet took main's equivalent wording. Citations moved by difflib: this lane's `CHANGELOG.md` lines in `crew.md` +86 (the entries main added). Main-side citations into files this branch changes resolve to the same text. No suite was executed for this note.


**Re-anchored `5467b110` -> `2594c90f` on 2026-10-02 (L-0555 merges origin/main `a9b4734d`, L-0576 #306, crew 1.0.128; rerere disabled; crew 1.0.132).** 10 citation(s) moved by difflib from `5467b110` to HEAD, each checked to cite the same line text (L-0576 shifted `plugin/crew/README.md` by two lines and `docs/guides/crew/src/troubleshooting.md` by five); citations written by L-0576 itself into this map are left as main has them.

**Re-anchored `2594c90f` (L-0555) and `273ec0f6` (main) -> `a81e4382` on 2026-10-02 (L-0555 merges origin/main `0487fc39`: L-0575 #311, crew 1.0.129, and L-0599 #315, gizmoduck 0.5.6; rerere disabled; crew 1.0.132 re-set after the merge).** The anchor, INDEX and provenance hunks conflicted: both sides' provenance was kept, main's first. Citation-number hunks took main's side. 10 citation(s) moved by difflib, each checked to cite the same line text: main-written lines mapped from `0487fc39`, L-0555-written lines from `c38be472`. A bare `:N` followed by "on <rev>" is history and was left alone, as were citations already stale on main.

**Re-anchored `a81e4382` -> `407f2b33` on 2026-10-02 (L-0587, repository tooling, no plugin version).** `git diff --name-only a81e4382 407f2b33` is main's own history to e0c70fc9 plus L-0587's three commits. L-0587 changes `scripts/install-prerequisites.sh:1675` and `scripts/_test/lsp-stack-tools.sh:7` in place (comment text only, no line added or removed), `.crew/verify.json` rules[3] in place (one command appended on the existing last `run` line, its `why` extended; no line added), adds `scripts/_test/shellcheck-directives.py`, one `_py_suite` TABLE row in `scripts/gate-runner.py` (after `version-drift`, +1 line at `:155`), one step in `.github/workflows/marketplace.yml` (+8 lines after the Shell syntax step) and a CHANGELOG entry (+23 lines near the top). No current citation in this map points into `scripts/gate-runner.py` or `marketplace.yml` past the insertion; the `CHANGELOG.md` line numbers in this map sit in past provenance paragraphs that record the tree they were read at, and are left as written. No claim in this note was re-derived; no suite was executed for this note.

**Re-anchored `407f2b33` -> `4fc93b19` on 2026-10-03 (L-0587 merges origin/main `ffeb0e2f`: L-0598 #321, crew 1.0.135; rerere disabled).** Main's side changes `plugin/crew/hooks/scripts/crew_standards.py` (one hunk at `:729`, +4 lines, in `proposals`) and `plugin/crew/skills/crew-qa-standards/references/review.md` (one hunk at `:40`, +2 lines), plus version files, CHANGELOG, BUDGETS and `crew.md`'s version sentence, which came in unchanged. The only current citations into `crew_standards.py` in these maps are `:145` and `:664`, above the hunk, so they stand; the larger numbers that mention it sit in past provenance paragraphs and are left as written. Only the generated `.claude/rules/crew.md` conflicted and was regenerated. No claim was re-derived; no suite was executed for this note.

**Re-anchored `a81e4382` -> `6475c41c` on 2026-10-02 (L-0592, L-0575's round-2 fixes to the recurring-findings checklist; origin/main `ffeb0e2f` merged first as a fast-forward, rerere disabled).** `git diff --name-only a81e4382 6475c41c` against this map's paths returns five files under the crew plugin: its README, the implement command, recurring_findings.py and two test modules (test_lifecycle_commands.py, test_recurring_findings.py). The README changes one line in place (727) and implement.md re-wraps step 2 in its same five lines (40-44), so no line moves; paths are named here without citation markup so this note does not shift the map's derived rule paths; no citation in this map points at a changed line or at recurring_findings.py or either test. No claim changed.

**Re-anchored `6475c41c` -> `35b9e6d9` on 2026-10-02 (L-0592 review round 1 fixes).** Of this map's paths only the test module test_recurring_findings.py changed (its render table made exhaustive); this map cites no line of it. No claim changed.

**Re-anchored `4fc93b19` (main, L-0587) and `35b9e6d9` (L-0592) -> `39ebbc18` on 2026-10-02 (L-0592 merges origin/main 6ac3b1b3, L-0587 #319 and #322; rerere disabled; crew 1.0.139).** Main's maps, INDEX and diagram were taken and L-0592's notes re-applied after main's. Since main's anchor, L-0592 changed five files under the crew plugin (README, the implement command, recurring_findings.py, two test modules) with no line moved, and main's re-pin changed two root README lines in place. No citation moved; no claim changed.

**Re-anchored `6053b65d` -> `17dc6d23` on 2026-10-01 (L-0574, built on origin/main `ffd11270`: `review_checks.py` and `review_run.py`'s `prereview_gate`, no plugin version yet).** Every citation into a file L-0574 changed (`review_run.py`, `commands/review.md`, `plugin/crew/README.md`, `.crew/verify.json` - which gained a top-level `preReview` block above `rules`, so every rule citation moved by 27 lines - `docs/external-tool-formats.md`, `tests/sabotage.py`, `tests/test_review_contracts.py`, `BUDGETS.md`, `CHANGELOG.md`, the lifecycle diagram) was mapped with difflib from `ffd11270` to `17dc6d23`; `BUDGETS.md:10-11` is the changed count line itself and keeps its number. The verify map still has 44 rules; `preReview` is read by `review_run.py`, not the Stop gate.

**Re-anchored `17dc6d23` -> `8177fdff` on 2026-10-01 (L-0574 review round 1 and pre-round fixes).** The commits since changed `review_checks.py`, its tests, `sabotage_prereview.py`, `docs/external-tool-formats.md`, `BUDGETS.md`'s count line and `CHANGELOG.md`; difflib found no citation in this map that moved.

**Re-anchored `8177fdff` -> `3afec6e6` on 2026-10-01 (L-0574: noqa BLE001 on two boundary catches, same lines; difflib moved no citation).**

**Re-anchored `3afec6e6` -> `d640eba3` on 2026-10-01 (L-0574 round-2 fixes and the crew 1.0.122 bump; ten CHANGELOG citations moved +2 by difflib, the crew map's version sentence now reads 1.0.122).**

**Re-anchored `d640eba3` -> `d41c2c94` on 2026-10-01 (L-0574: a sabotage anchor re-targeted and the graph rebuilt; no cited line moved).**

**Re-anchored `d41c2c94` -> `1f5400df` on 2026-10-01 (L-0574 round-3 fixes; ten CHANGELOG citations moved +6 by difflib).**

**Re-anchored `1f5400df` -> `5143dbcd` on 2026-10-02 (L-0574 round-4 fixes and the merge of origin/main d2ec37d3: this branch's map text kept, main's re-anchor notes restored, citations into the eight files round 4 changed re-mapped by difflib from 1f5400df and the rest from 846cc465 onto the merge).**

**Re-anchored `5143dbcd` -> `ded603a7` on 2026-10-02 (L-0574: the gate's pylint findings fixed; no cited line moved).**

**Re-anchored `ded603a7` -> `a4ffe1de` on 2026-10-02 (L-0574 merges origin/main 7ba4f9ea, crew 1.0.126: citations into files main changed re-mapped by difflib, two verify.json:418 read by hand as :439).**

**Re-anchored `a4ffe1de` -> `18b764dc` on 2026-10-02 (L-0574: merge of origin/main 22292d63 (rerere disabled, scope re-based to it) and the round-5 fixes; ten CHANGELOG citations moved by difflib).**

**Re-anchored `18b764dc` -> `22aeb5a8` on 2026-10-02 (L-0574 round-7 class sweep: fifteen citations moved by difflib (review_run.py, CHANGELOG.md), two bare review_run.py citations re-read by hand).**

**Re-anchored `22aeb5a8` -> `9581933e` on 2026-10-02 (L-0574: external-tool-formats.md citation fix and the crew 1.0.131 re-set; no cited line moved).**

**Re-anchored `9581933e` -> `34c9a8bc` on 2026-10-02 (L-0574 merges origin/main 0487fc39 at bd459af7 (rerere disabled; both provenance histories kept, main's first) and fixes review round 7 at 4a35e5d2; citations re-mapped by difflib, bare review_run.py citations re-read by hand).**

**Re-anchored `34c9a8bc` -> `370a7a5b` on 2026-10-02 (L-0574 merges origin/main e0c70fc9 (L-0555 #310, #317, L-0597 #316; crew 1.0.134) at 370a7a5b, rerere disabled: both provenance histories kept (main's first), citations into files either side changed re-mapped by difflib (67 moved), the verify.json heading corrected to 48 rules).**

**Re-anchored `370a7a5b` -> `e2c11c0b` on 2026-10-02 (L-0574 review round 8 fixes at 0f5d76e7 (review_checks.py, review_run.py, CHANGELOG, external-tool-formats.md; install-scripts.md gains an explicit paths: line); citations re-mapped by difflib, bare review_run.py citations re-read).**

**Re-anchored `e2c11c0b` -> `0891d6a6` on 2026-10-02 (L-0574 merges origin/main ffeb0e2f (L-0598 #321, crew 1.0.135; crew_standards.py proposals and references/review.md, which this map cites by name only) at 26d2c1c0, rerere disabled, then fixes review round 9 at c7e4c87f; citations re-mapped by difflib).**

**Re-anchored `0891d6a6` -> `4dcad808` on 2026-10-02 (L-0574 merges origin/main 6ac3b1b3 (L-0587 #319 ShellCheck directive fixes, README re-pin #322; crew 1.0.135) at 4dcad808, rerere disabled: both provenance histories kept (main's first), citations re-mapped by difflib).**

**Re-anchored `4dcad808` -> `819a2d2b` on 2026-10-02 (L-0574: three test_review_checks.py cases made to pass on a real Windows host (PR #323 CI); citations re-mapped by difflib).**

**Re-anchored `819a2d2b` -> `d95d8b25` on 2026-10-02 (L-0574 merges origin/main 2a2d6e07 (L-0592 #325, crew 1.0.139: recurring_findings.py, implement.md step 2 re-wrapped in place, README) at d95d8b25, rerere disabled: both provenance histories kept (main's first), citations re-mapped by difflib; crew is set to 1.0.140).**

**Re-anchored `0c3508e9` -> `963d2905` on 2026-09-30 (L-0510: review closure, a final 0-BLOCK round auto-accepts, crew 1.0.90).** `git diff --name-only 0c3508e9 963d2905` returns, outside refresh artifacts, main's L-0561 README repin and L-0510's files (review_ledger.py, review_run.py, crew_autopilot.py, review.md, done.md, autopilot.md, README.md, CONFIG.md, BUDGETS.md, PLUGINS.md, the troubleshooting guide, CHANGELOG.md, two tests, sabotage_review.py and the version files); path-qualified citations outside dated provenance checked by a line diff: no body citation moved: provenance paragraphs keep their dated numbers, and the only cited lines that changed are version lines (plugin.json, PLUGINS.md, BUDGETS.md), unchanged in place. No suite was executed for this note.

**Re-anchored `963d2905` -> `bee8b203` on 2026-09-30 (L-0510 suite fixes, crew re-bumped to 1.0.93).** `git diff --name-only 963d2905 bee8b203` returns, outside refresh artifacts, `sabotage_review.py` (one row's find string), `plugin/crew/docs/external-tool-formats.md` (four `review_run.py` citations), CHANGELOG.md and the version files; a body-only line diff moved no citation here (`docs/diagrams/data-flow-crew-config.mmd:1-2` is its re-written header, still lines 1-2). No suite was executed for this note.

**Re-anchored `bee8b203` -> `52e309cf` on 2026-10-01 (L-0510 review fix round, crew re-bumped to 1.0.94).** `git diff --name-only bee8b203 52e309cf` returns, outside refresh artifacts, `review_ledger.py` (the per-severity count check, the CLEAN receipt-kind check and `check_follow_up`'s kind allowlist, UTF-8 refusal and verbatim counted match), its tests and sabotage rows, `plugin/crew/README.md`, `plugin/crew/commands/done.md`, `plugin/crew/commands/review.md`, `plugin/crew/BUDGETS.md`, the troubleshooting guide and its rendered outputs, CHANGELOG.md and the version files. A body-only line diff moved no citation here. No suite was executed for this note.

**Merged `490f4ec1` (L-0510) + `52489039` (main) on L-0510-build, 2026-10-01 (merge `58fc8da8` of origin/main `52489039`: T-0040 #290, crew 1.0.98, with rerere off), then re-anchored to `5254bbfe` (L-0510 re-bumped to crew 1.0.103).** The code paths are disjoint: main touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, and L-0510 touched none of T-0040's files. The anchor and the provenance tail conflicted in every map (both sides' provenance kept, main's first); `crew.md`'s T-0087 refund paragraph keeps L-0510's `review_run.py` / `review_ledger.py` / `crew_autopilot.py` positions with main's `plugin/crew/hooks/scripts/crew_status.py:140`, and `repo-docs.md`'s runbooks-index citation was re-grepped on the merged tree (`plugin/crew/README.md:2288`). Every body `path:line` into a file either side changed was checked against the parent whose copy of the map carries that line verbatim, by a line diff of that file onto the merged tree (`/root/crew-tmp/l-0510/tools/merge_cites2.py`, machine-local): none moved. `5254bbfe` itself changes only release bookkeeping (version files, CHANGELOG, BUDGETS count). No suite was executed for this note.

**Re-anchored `5254bbfe` -> `a98be035` on 2026-10-01 (L-0510, owner decision 2026-10-01 #3: the family rule).** `git diff --name-only 5254bbfe a98be035` returns `review_ledger.py`, its two test files and `sabotage_review.py`, `commands/review.md`, README, CONFIG, PLUGINS.md, BUDGETS.md, CHANGELOG, the troubleshooting guide and its three outputs, and refresh artifacts. Line counts are unchanged in every file except `review_ledger.py` (+37, cited only in `crew.md`, re-read there), CONFIG.md (+1 at `:2510`, past every CONFIG citation in these maps) and CHANGELOG.md (+3 at `:21`; the CHANGELOG line numbers in these maps are history notes of earlier anchors, not re-cited).

**Merged `a98be035`/`8c82f974` (L-0510) + `5ffffbe3` (main) on L-0510-build, 2026-10-01 (merge `d4193b70` of origin/main `2906dcbd`, crew 1.0.110, rerere off), then re-anchored to `8f0df4ca` (L-0510 re-bumped to crew 1.0.112).** Both provenance blocks are kept above, main's first. Main touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, so every L-0510 citation reads as L-0510 drew it, except `review_ledger.py`, which L-0510's review round 3 FIX 2 (`8c82f974`: `_receipt_names_the_reviewer`) grew by 10 lines below `:590`; `crew.md`'s citations of it were re-read with `grep -n '^def '` on the merged tree and moved (`check_receipt` `:691`, `check_follow_up` `:620`, `continue_with_successor_plan` `:742`, `summary` `:781`). Main's citations are main's, unchanged by L-0510's side.

**Re-anchored `8f0df4ca` -> `39e1237a` on 2026-10-02 (L-0510 review round 4 fixes, owner decision 2026-10-01 #5).** `3181121c` changed `review_ledger.py` (`_auto_row_problem` +6 lines: the embedded line-break refusal; `check_follow_up` +3: newline-only split), `commands/autopilot.md` (one sentence extended in place, line count unchanged) and the L-0510 tests; `00450ce0` CHANGELOG and README text; `fb33f9dc`/`39e1237a` un-set and re-set crew 1.0.112. `crew.md`'s `review_ledger.py` citations were re-read with `grep -n '^def '` and moved (`receipt_stands` `:596`, `check_receipt` `:700`, `_receipt_names_the_reviewer` `:618`, `auto_accept_refusal` `:528`, `auto_accept` `:562`, `check_follow_up` `:626`, `continue_with_successor_plan` `:751`, `summary` `:790`, `load` `:787`). No other note cites a moved line.

**Merged `39e1237a`/`ecc76d10` (L-0510) + `6053b65d` (main, L-0557 #300) on L-0510-build, 2026-10-02 (merge `122fc10d` of origin/main `ffd11270`, crew 1.0.114, rerere off), then re-anchored to `6ffb589d` (L-0510 at crew 1.0.121).** Both provenance blocks are kept above, main's first. L-0557 touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`. L-0510's own changes since `39e1237a`: `156882d2` (decision #6: `_auto_row_problem` +12 lines, `_review_json_problem` new at `:578`, `auto_accept` +3) and `ecc76d10`/`7d32fbc6` (docs and the rebuilt troubleshooting guide); `crew.md`'s `review_ledger.py` citations were re-read with `grep -n '^def '` and moved (`receipt_stands` `:641`, `check_receipt` `:745`, `auto_accept` `:604`, `check_follow_up` `:671`, `continue_with_successor_plan` `:796`, `summary` `:835`). Main's citations are main's.

**Merged `979ea023` (L-0510) + `8d84786d` (main: T-0503 #270 bitbucket 1.2.3, W-0117 #302 crew 1.0.115) on L-0510-build, 2026-10-02 (merge `9f39dd61`, rerere off, owner decision #9), anchored at `9f39dd61`.** Both provenance blocks are kept above, main's first. Neither T-0503 nor W-0117 touched `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, so L-0510's citations read as L-0510 drew them at `e7227a2b` (`receipt_stands` `:644`, `check_receipt` `:748`, `auto_accept` `:607`, `_review_json_problem` `:578`, `check_follow_up` `:674`, `summary` `:838`). Main's citations are main's.

**Merged L-0510 (`553f4aa0`, the UTF-8 console fix) + `04dde5a2` (main: L-0578 #304 crew 1.0.119, W-0120 #307) on L-0510-build, 2026-10-02 (merge `41aa4e2a`, rerere off, standing go #9), anchored at `2b372b84`.** Both provenance blocks are kept above, main's first. L-0578 changed `review_run.py` (the metrics row) and `commands/review.md` step 6; every `review_run.py` citation in this note was re-derived on the merged file by difflib from each parent and read with `sed -n` (preflight `:555`, called at `:642`; `--provider` `:739`; `finish`'s parts `:438`/`:440`; `failure_class` `:458`; refund lines `:508`/`:511`; `_webtest_open` `:412`; `auto_accept_line` `:421`). `review_ledger.py` gained `utf8_stdio` after `summary` (`:838`), so no earlier citation moved.

**Re-anchored `2b372b84` -> `252dd5d4` on 2026-10-02 (L-0510 review round 6 fixes, owner decision #10; merge `24f3ec25` of origin/main `d2ec37d3`, README only).** `d551680c` changed `review_ledger.py` (`read_review_json` `:599` and `_receipt_binds_review_json` `:721` new, `receipt_stands` gained `root, ticket`, `hashlib` imported, docstring +5), `crew_autopilot.py` (one line edited in place), `commands/review.md` (step 3 quoted in place), the L-0510 tests, CHANGELOG and README. `crew.md`'s `review_ledger.py` citations were re-read with `grep -n` by name (`receipt_stands` `:695`, `check_receipt` `:819`, `auto_accept` `:655`, `check_follow_up` `:742`, `summary` `:909`, `BUDGET` `:132`, `REFUND_LIMIT` `:135`). No other note cites a moved line.

**Re-anchored `252dd5d4` -> `97b65952` on 2026-10-02 (L-0510, merge `48cf52dd` of origin/main `7ba4f9ea`, crew 1.0.126 -> 1.0.130).** Main brought L-0572's `verify-gate.sh`/`.ps1`, `verify_record.py`, CONFIG.md and its own codemap edits; it touched none of the files L-0510's citations name (`review_ledger.py`, `crew_autopilot.py`, `review_run.py`, `commands/review.md`, `commands/autopilot.md`), so no L-0510 citation moved; L-0572's citations were written against main and carried by the merge unchanged.

**Re-anchored `273ec0f6` (main) and L-0510's `97b65952` -> `d05b0211` on 2026-10-02 (L-0510 merges origin/main `0487fc39` (L-0599 #315, crew 1.0.129; L-0576, L-0577, T-0107, L-0575 before it) at `ec508e5e`, rerere off; crew 1.0.130 set last at `d05b0211`).** Both provenance histories kept, main's first. In `crew.md` the `review_ledger.py`, `review_run.py` and `review_verdict.py` citations were re-derived on the merged files by function name (`grep -n '^def '`) and difflib from the tree each line came from: L-0510's ledger lines moved +14 (L-0576's `_ignored_count` and `record` row above them), `review_run.py`'s preflight `:563`/`:650`, provider list `:747` and refund lines `:517`/`:520`, `review_verdict.py`'s `VERDICTS`/`FINDING_FORM`/class names `:90`/`:93`/`:95`; main's L-0576 paragraph's three stale lines set to `review_run.py:447`, `:467`, `:513` and `review_ledger.py:394`. One L-0510 sentence that said the field was not written now says L-0576 writes it. Other maps: no cited line moved. History notes were not re-mapped.

**Re-anchored `a81e4382` (main) and L-0510's `d05b0211` -> `77e8dcfd` on 2026-10-02 (L-0510 merges origin/main `e0c70fc9` (#317, L-0597 #316, L-0555 #310; crew 1.0.134) at `e6dc6b1b`, rerere off; crew 1.0.137 set last at `77e8dcfd`).** Both provenance histories kept, main's first. Main touched none of `review_ledger.py`, `review_run.py`, `review_verdict.py`, `crew_autopilot.py`, `review.md` or `autopilot.md`; `crew.md`'s `crew_autopilot.py` `questions_check` `:1246` / `QUESTIONS_SHAPE` `:1154` are L-0510's merged-file lines (main's side read `:1232` / `:1140` without L-0510's autopilot change); `repo-docs.md`'s README citation is `:2314` on the merged README (L-0555 +23). History notes were not re-mapped.

**Re-anchored `4fc93b19` (main) and L-0510's `77e8dcfd` -> `96a69068` on 2026-10-03 (L-0510 merges origin/main `bd3e9ad1` (L-0598 #321, L-0587 #319; crew 1.0.135) at `d3f26a4b`, rerere off; crew 1.0.137 set last at `96a69068`).** Both provenance histories kept, main's first. Main touched no file L-0510's citations name; L-0510's `c86365ee` (a test helper) moves no cited line. History notes were not re-mapped.

**Re-anchored `39ebbc18` (main) and L-0510's `96a69068` -> `a06dd790` on 2026-10-03 (L-0510 merges origin/main `2a2d6e07` (L-0592 #325, L-0587 re-pin #322; crew 1.0.139) at `39c290be`, rerere off; crew 1.0.142 set last at `a06dd790`).** Both provenance histories kept, main's first. Main touched no file L-0510's citations name (its README edit is one line, no cited line moved). History notes were not re-mapped.

**Re-anchored `d95d8b25` (main) and L-0510's `a06dd790` -> `b8d09685` on 2026-10-03 (L-0510 merges origin/main `8123fe74` (L-0574 #323; crew 1.0.140) at `8c04c783`, rerere off; crew 1.0.142 set last at `b8d09685`).** Both provenance histories kept, main's first. In `crew.md` main's L-0574 `review_run.py` citations were re-derived on the merged file (L-0510 adds 8 lines above `finish` and 28 through it): by difflib, and by name for `prereview_gate` `:731` (called `:857`), `standards_gate` `:699` (at `:859`) and `review_ledger.reserve` `:863`, which main's side had stale; L-0510's `review_ledger.py` citations are unchanged. `verification-harness.md`'s `sabotage.py` citations moved +1 (main's import at `:87`; main's side had them stale). History notes were not re-mapped.

**Re-anchored `b8d09685` -> `452b30cc` on 2026-10-03.** `204e813b` routes `review_run.finish`'s auto-accept line through `_out` (main's L-0574 one-writer test), one line, no line count change, so no citation moved; `452b30cc` re-sets crew 1.0.142 last.

**Re-anchored `39ebbc18` -> `238e326a` on 2026-10-03 (L-0601, the recurring-findings checklist in the review prompt).** Changed since the anchor: review_prompt.py (an import and a docstring bullet move every later line down five; the crew map's five current citations into it were moved by matching their text), verify.json (the recurring-findings rule, last in the file, grew two lines: 492-504), sabotage.py (an import after the cited ones), the new sabotage_recurring.py, test_review_prompt.py, review.md (one comment re-wrapped in place), the crew README (one line in place) and the working-with-codex guide. The crew map's Checklist bullet and the verification-harness map's rule line describe the new block; no other claim changed.

**Re-anchored `d95d8b25` (main, L-0574) and `238e326a` (L-0601) -> `6a2869bd` on 2026-10-03 (L-0601 merges origin/main 8123fe74, L-0574 #323; rerere disabled; crew 1.0.141).** Main's maps, INDEX and diagram were taken and L-0601's edits re-applied: the crew map's Checklist bullet and version sentence, its five review_prompt.py citations moved by five (an import and a docstring bullet above them), and the verification-harness map's recurring-findings rule line (now 519-530, two paths and one suite added). Other L-0601 changes (sabotage.py import after the cited lines, review.md and the crew README in place, the guide) move no cited line. No other claim changed.

**Re-anchored `6a2869bd` -> `38975c7a` on 2026-10-03 (L-0601: sabotage_recurring.py reads its data section with newline translation, the Windows CI fix).** Only that test helper changed; this map cites no line of it. No claim changed.

**Re-anchored `452b30cc` (main) and L-0601's `8d5134b5` -> `0620587f` on 2026-10-03 (L-0601 merges origin/main f808e5f0: L-0510 #318, #328, #329, #330, crew 1.0.154; rerere disabled; crew 1.0.162 set last).** Main's maps were anchored at `452b30cc` while main changed 34 more files after it; their citations into those files were moved by difflib from `452b30cc` to the merge (78 moved; 17 whose line itself changed were moved by the offset of the line above and each checked to cite the same construct, e.g. `verify_record.py` `tree_snapshot`, `review_run.py` `--provider`, the rules' `why` lines). L-0601's own edits were re-applied after main's text. Main's claims about #328-#330 were not re-derived; no suite was executed for this note.

**Re-anchored `0620587f` -> `5479ac05` on 2026-10-03 (T-0048 merges origin/main `4f6ef540` (L-0601 #327, crew 1.0.162) at `5479ac05`; crew 1.0.183 kept).** Main's maps were taken and T-0048's body edits re-applied at merged-tree lines: `scripts/check-marketplace.py` `main()` `:1679-1715` with seventeen checks (`check_config_reference` at `:1701`, defined `:1375`), the plugins derivation `:1705-1706`, `plugin/crew/CONFIG.md:2478-2485` (main's `:2451-2458`, moved by the generated key tables of sections 10 and 11), `scripts/_test/self-claims.py:1228`. Citations inside earlier re-anchor notes are history and were not moved. Re-anchor only; no claim was re-derived and no suite was executed for this note.

**Re-anchored to `51b2222b` on 2026-10-03 (T-0066, crew 1.0.185: `git.forbiddenTrailers` and the `/crew:done` trailer report; `51b2222b` merges origin/main `4f6ef540`, crew 1.0.162, into `T-0066-build`).** Main's maps were taken at the merge and T-0066's edits re-applied on them. T-0066 changes, among the paths these maps cite: `.crew/verify.json` (one rule appended, `:539-546`), `plugin/crew/CONFIG.md` (section 10/11 headings, one section 10 row, new section 22), `plugin/crew/commands/done.md` (a report section after check 4, `:68-79`), `plugin/crew/commands/implement.md` (step 2 `:46-52`; still 120 lines), `plugin/crew/hooks/scripts/crew_config.py` (the `git` block, +6 after main's `:380` and +4 after its `:595`), `plugin/crew/skills/crew-setup/SKILL.md`, the two templates, `plugin/crew/tests/test_crew_config.py`, the new `crew_trailers.py` and its suite, and release bookkeeping (`CHANGELOG.md`, `TODO.md` +11 at `:241`, `plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`, both version files). Body `path:N` citations into those files were re-mapped by a difflib line diff from main `4f6ef540` to the merged tree; a bare `:N` was re-mapped only where T-0066's earlier pass (`f7fd2e78`) had read the sentence and applied it. History notes were not re-mapped. No other claim was re-derived and no suite was executed for this note.
