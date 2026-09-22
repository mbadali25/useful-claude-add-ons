anchor: useful-claude-add-ons@2b337296
verified: 2026-09-22
**Full re-derivation of every DERIVED claim below, not a re-anchor.** The
per-path diff from the previous anchor was not empty, so nothing carried
forward on the strength of the anchor alone. See "Re-anchor provenance —
ea8a014 -> 84976536" for the command, its output, and what changed.

**This sha is a branch commit** (`crew-0.19.96-docbuilder-install-fixes`), not
a trunk one — `git merge-base HEAD origin/main` is `d9da1409`, and a squash
merge of this branch would discard `84976536` and put this note into
`knowledge.unresolvable`. The merge-base was not used as the anchor because
`.crew/verify.json`, `scripts/check-marketplace.py` and `_verify/smoke.sh` all
changed between `d9da1409` and here, so anchoring at `d9da1409` would have
claimed a reading of a tree these claims do not describe. If the anchor stops
resolving, re-derive from `d9da1409` and treat those three files as the ones
certain to have moved.

History, from the `ea8a014` pass, superseded above and retained as a record of
what was believed then: narrow pass. `f9bb78a6` (#169, "Finish the crew
skill-count sweep") touched
`scripts/check-marketplace.py` (+53 lines, inside/after `check_versions` and
inside `check_self_claims`) and `scripts/_test/self-claims.py`, both paths
this note cites. Verified directly: `main()` still calls the same **eleven**
check functions, in the same order — the release added a new claim type
(`plugin-skills:<name>`) inside `check_self_claims`'s existing body, not a
twelfth function call. Every citation into `check-marketplace.py` below that
fell after the insertion point was re-read and re-pointed; citations at or
above line 402 (`check_versions` and everything before it) did not move.
`scripts/_test/self-claims.py` is cited nowhere in this note by name or line,
so its growth (+111 lines, new test cases for the marker) needed no citation
fix. Everything else in this note, including `_verify/`, `.crew/verify.json`
and `plugin/crew/`, was not re-diffed this pass and carries forward from
`975480b7` unread.

History, from the `0a9d8937` pass, not re-verified at this anchor: that pass
was "re-verified, not re-derived: every claim below was re-read against the
files it cites at this anchor and its citation re-pointed where the code had
moved." Its big structural change was `.crew/verify.json` becoming tracked
(`!.crew/verify.json` joined the gitignore un-ignore list in crew 0.19.46,
`0a9d8937`) and present in that checkout, so every UNVERIFIABLE HERE mark the
previous four passes carried was confirmed, corrected, or replaced with an
actual reading. Separately, `scripts/check-marketplace.py`'s `main()` grew
from nine check functions to eleven (`check_self_claims` and
`check_crew_ignore_policy`, both added between the anchor before that one and
`0a9d8937`), and `_verify/run-all.sh`'s own citations turned out to be wrong
independent of any code change — they were never correctly re-derived after
an earlier insertion, and that pass fixed them from a full read rather than
an offset.

# Verification harness

Three *scripted* layers, fastest to slowest: `_verify/smoke.sh` (seconds), the
direct `scripts/check-marketplace.py` invocation (all checks, including the slow
one — see `marketplace-registration.md`), and `_verify/run-all.sh` (minutes).

**JUDGEMENT, backed by a full read at this anchor.** `.crew/verify.json` holds
**21** `rules` (counted via `json.load`) — unchanged in count since the previous
anchor, though the file grew +120/-32 lines in the interval. Its own `anchor`
field (`.crew/verify.json:3`) still reads `"repo@5238be3d"` and was **not**
advanced by any of this session's edits to it, so it is now further behind its
own contents than it was. Most rules name one of the three scripted layers
above, but plenty do not: `python3 -m pytest
plugin/crew/tests/test_verify_gate_baseline.py ...` (`.crew/verify.json:99`,
the hooks-gate suite, moved from `:69`), `python3 -m pytest
plugin/crew/tests/ -q` (`:150`, moved from `:114`), `npm --prefix mcp-servers
test` (now wrapped in a tool-probe at `:191`, moved from `:143`), `bash
skills/bitbucket/scripts/_test/merge_gate.sh` (`:197`, moved from `:147`), and
several more listed in the "What `.crew/verify.json` actually maps" section
below. The accurate statement remains: `.crew/verify.json` maps a changed path
to the commands that verify it, and those commands are *often but not always*
one of the three scripted layers.

## Re-anchor provenance — ea8a014 -> 84976536, 2026-09-22

**Full re-derivation.** The prescribed per-path check, run verbatim:

```bash
git diff --name-only ea8a014..HEAD -- \
  .claude-plugin/marketplace.json .crew/verify.json .github/workflows/marketplace.yml \
  .gitignore CLAUDE.md INSTALLATION.md README.md plugin/PLUGINS.md plugin/README.md \
  _verify/smoke.sh _verify/run-all.sh \
  scripts/check-marketplace.py scripts/install-prerequisites.sh \
  scripts/_test/self-claims.py scripts/_test/crew-ignore-policy.py \
  scripts/_test/menu-groups.sh scripts/_test/check-powershell.sh scripts/_test/drift-detection.sh \
  plugin/crew/hooks/scripts/_test/run-tests.sh plugin/crew/hooks/scripts/crew_platform.py \
  plugin/crew/hooks/scripts/crew_state.py plugin/crew/skills/crew-graph/scripts/crew_upgrade.py \
  plugin/crew/skills/crew-setup/scripts/_test/round-trip.sh \
  plugin/crew/tests/conftest.py plugin/crew/tests/context.py plugin/crew/tests/sabotage.py \
  plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_crew_state.py \
  plugin/crew/tests/test_verify_gate_baseline.py plugin/crew/tests/test_verify_gate_bash_resolver.py \
  skills/bitbucket/scripts/_test/merge_gate.sh
```

**Twenty paths returned**, so a re-anchor alone would have been wrong:

```
.claude-plugin/marketplace.json                         plugin/crew/tests/sabotage.py
.crew/verify.json                                       plugin/crew/tests/test_crew_config.py
.github/workflows/marketplace.yml                       plugin/crew/tests/test_crew_state.py
.gitignore                                              plugin/crew/tests/test_verify_gate_baseline.py
INSTALLATION.md                                         scripts/_test/menu-groups.sh
README.md                                               scripts/check-marketplace.py
_verify/smoke.sh                                        scripts/install-prerequisites.sh
plugin/PLUGINS.md                                       skills/bitbucket/scripts/_test/merge_gate.sh
plugin/README.md
plugin/crew/hooks/scripts/_test/run-tests.sh
plugin/crew/hooks/scripts/crew_state.py
plugin/crew/skills/crew-graph/scripts/crew_upgrade.py
```

Five are version-bump churn (`marketplace.json`, `README.md`,
`INSTALLATION.md`, `plugin/PLUGINS.md`, `plugin/README.md`) — **fifteen are
substantive**. `_verify/run-all.sh` is the one cited file in the list that did
**not** move: `git diff --stat ea8a014..HEAD -- _verify/run-all.sh` is empty,
so its ten-step account below is carried forward, with each cited line
re-resolved by hand anyway rather than trusted.

**Every DERIVED claim below was re-read against the file it cites.** The three
that changed most, and the shape of the change in each:

- `scripts/check-marketplace.py` (+193 lines): `main()` now calls **fourteen**
  check functions, not eleven. Three were added.
- `_verify/smoke.sh` (+53 lines): an eleventh check exists, and the header
  comment the previous pass flagged as stale is stale no longer.
- `.crew/verify.json` (+120/-32): `reach` is now declared on all 21 rules, two
  rules gained `sh -c` tool-presence probes exiting **77**, and `rules[2]`
  gained `check-marketplace.py` as its first command after its previous pair
  was proven unable to go red on any of its own paths.

**No suite was executed except one**, run because this repo's gate requires it:
`python3 scripts/check-marketplace.py` → `marketplace: 36 skills, 5 plugins`,
`all checks passed`, rc 0, on the Linux host at `84976536` with
`graphify-out/` dirty from another lane. `_verify/smoke.sh`,
`_verify/run-all.sh`, every pytest suite and `scripts/_test/crew-ignore-policy.py`
were **not** run; `ruff` and `pylint` are absent on this host (PEP 668) and were
not installed. Every other claim below is read from source.

## Re-anchor provenance — 975480b7 -> f9bb78a6, 2026-09-14

`git diff --name-only 975480b7..f9bb78a6 -- _verify/ .crew/verify.json
scripts/check-marketplace.py plugin/crew/tests/ plugin/crew/hooks/` (the same
five paths the previous pass checked) returns one:
`scripts/check-marketplace.py`. Also touched by `f9bb78a6` but outside this
note's cited-path list: `README.md`, `INSTALLATION.md`, `plugin/PLUGINS.md`,
`plugin/README.md`, `scripts/_test/self-claims.py` — none of which this note
cites.

**Re-read directly rather than assumed:** `main()`
(`scripts/check-marketplace.py:991-1021`, moved from `:938-968`) still calls
the same eleven functions in the same order, at `:1000-1010` (moved from
`:947-957`). The count did not change. What changed is internal to
`check_self_claims` (`:430-777`, moved from `:412-...`): a new claim type,
`plugin-skills:<name>`, recognised alongside the existing `skills-count` and
`plugin-version:<name>` types, backed by a new helper `count_plugin_skills`
(`:413-427`) that counts `SKILL.md`-bearing subdirectories of
`plugin/<name>/skills/` directly from disk. This is a behavior change to one
existing check, not an addition to `main()`'s eleven — see "`check_self_claims`
gained a marker type" below for what it fixes and how it was proven.

Every citation into `check-marketplace.py` at or below the insertion point
(module-level regexes and everything inside/after `check_self_claims`) moved
by a uniform **+53 lines**; everything at or above `check_versions`'s end
(`:402`) did not move. Confirmed by reading `git show f9bb78a6 -- scripts/check-marketplace.py`'s
three hunks, all opening at old line 405 or later, before applying the offset.

## Re-anchor provenance — 0a9d8937 -> 975480b7, 2026-09-14

Re-anchor only: this pass diffed only the five paths this note's own
"History" section names (`_verify/`, `.crew/verify.json`,
`scripts/check-marketplace.py`, `plugin/crew/tests/`, `plugin/crew/hooks/`)
against `975480b7`, prompted by an unrelated skills-count correction made
elsewhere in the codemap. The diff was empty, so nothing below was re-read.
The rest of this note, including the `7b0d8f3a -> 0a9d8937` section
immediately below, is retained as history and was not re-checked.

## Re-anchor provenance — 7b0d8f3a -> 0a9d8937, 2026-09-14

The per-path check ran over the 13 paths this note cites. **Seven changed**:
`plugin/crew/hooks/scripts/_test/run-tests.sh`, `plugin/crew/tests/sabotage.py`,
`plugin/crew/tests/test_crew_config.py`, `plugin/crew/tests/test_crew_state.py`,
`scripts/_test/menu-groups.sh`, `scripts/check-marketplace.py` and
`scripts/install-prerequisites.sh`. This note cites no *specific line* inside
`run-tests.sh`, `sabotage.py` or `menu-groups.sh` — only their names, as
commands other files invoke — so those three changing does not move any
citation here; only the two test files with named test functions
(`test_crew_config.py`, `test_crew_state.py`) needed re-pointing, below.

`_verify/smoke.sh` and `_verify/run-all.sh` did **not** change in this range
(confirmed by `git diff --stat`, empty for both) — but their citations still
needed correcting, because a full read this pass found several were already
wrong at the previous anchor, independent of anything moving since. See
"`_verify/run-all.sh` — what the deep suite actually runs" below.

**What was re-read, in full, at this anchor:** `.crew/verify.json` (176 lines,
now tracked and present — the first time this note could read it directly),
`_verify/run-all.sh` (all 159 lines, line by line against the note's own
numbered list), `scripts/check-marketplace.py`'s `main()` and `check_versions`,
and the two changed test files for their cited function names.

`scripts/check-marketplace.py` changed substantially (+584/-21 lines across
three commits: `3374e8e0` #139 added `check_self_claims`, `357338cb` #144 fixed
the version-drift walk across a merge, `0a9d8937` #161 added
`check_crew_ignore_policy`) — every citation into it below was re-read directly
rather than offset.

**Test-function citations, re-pointed by name, not by offset:**
`test_resolve_config_inherits_a_global_through_the_init_template` moved from
`plugin/crew/tests/test_crew_config.py:1483` to `:1488`;
`test_a_backslash_in_a_branch_name_is_flattened_too` moved from
`plugin/crew/tests/test_crew_state.py:968` to `:1016`; and
`test_two_repos_with_the_same_basename_do_not_share_a_leaf` moved from `:1002`
to `:1050`.

**`.crew/verify.json` is no longer gitignored and untracked.** `!.crew/verify.json`
joined the named un-ignore list in crew 0.19.46 (`0a9d8937`, this note's
anchor as of the previous pass), and the file is tracked and present in this
checkout. Every citation
into it below was written from an actual read this pass, not carried forward.
Several turned out to need correction rather than confirmation - see "What
`.crew/verify.json` actually maps", which replaces the previous history-only
section of the same name.

That absence-then-presence is a fact about the harness worth stating plainly:
`CLAUDE.md` calls `.crew/verify.json` "the mechanism" for per-path verify
commands, and `/crew:review` reads it to decide which specialist reviewers a
diff requires. On a machine where the file was absent, that routing selected
nobody and produced output indistinguishable from a diff that needed no
specialist - the same fail-open shape this repo keeps re-encountering. That risk
is gone for any checkout made from this commit onward, because the file now
travels with a clone.

**Explicit unknowns at this anchor** — recorded rather than resolved into a
confident value:

- **Exactly one command was executed**: `python3 scripts/check-marketplace.py`
  (rc 0, `marketplace: 36 skills, 5 plugins`, `all checks passed`), because
  this repo's gate requires it of any change. No other suite ran — not
  `_verify/smoke.sh`, not `_verify/run-all.sh`, not any pytest module, not
  `scripts/_test/crew-ignore-policy.py`. Every other behavioural claim below
  is read from source.
- **`ruff` and `pylint` are absent on this host and were not installed**
  (PEP 668 marks the interpreter externally-managed). `.crew/verify.json`'s
  `**/*.py` rule now exits 77 rather than 1 for exactly this, so a turn here
  records `skipped` for it. Nothing in this note is linted.
- **`plugin/crew/tests/sabotage.py` was not run**, by instruction and by
  policy: it edits real source in place. The counts quoted for it were read by
  AST from the file and from `git show`, never by executing it.
- `.crew/verify.json`'s stated *rationales* (its `why` fields) make historical
  claims — timing figures "measured on this machine", commit-specific sabotage
  proofs — that cannot be checked by reading today's tree. They are quoted here
  as what the file says, never asserted as fact. The file's own `anchor`
  (`.crew/verify.json:3`, `"repo@5238be3d"`) was **not advanced** by the edits
  that produced the state read here, so the gap between that field and the
  file's contents is wider than at any previous anchor. Three `why` fields now
  contradict the `seconds` on their own rule — see "Two defects in the gate
  this map feeds" below.
- **What the three extra `main()` checks actually assert was not derived.**
  `check_argument_hint_frontmatter`, `check_license_consistency` and
  `check_command_backtick_spans` are recorded here by name, definition range
  and call position only. Their behaviour, their sabotage coverage and whether
  any `.crew/verify.json` rule reaches them were **not** investigated this
  pass. That is a known hole, not a claim of absence.

## `_verify/smoke.sh` — 11 checks, and the header is no longer stale

**DERIVED, fully re-read at this anchor; the previous heading ("10 checks, not
9") is superseded.** Two things changed in the interval. The header comment now
reads *"11 checks, target is under 90 seconds"* (`_verify/smoke.sh:3`), and an
eleventh check was added — so the discrepancy the previous four passes carried
is closed, and this note should no longer be cited as evidence of it.

**The count only reconciles if you count both registration helpers.** There are
**10** `check "..."` invocations and **1** `check_optional "..."`
(`check()` is `_verify/smoke.sh:28`, `check_optional()` is `:42`), for 11. A
reader who greps `^check "` alone gets 10 and will conclude the header is stale
again in the other direction. It is not.

| # | Line | What it runs |
|---|---|---|
| 1 | `_verify/smoke.sh:100-101` | `run_marketplace_check registration` — every dir registered, every source resolves, no nested marketplace |
| 2 | `_verify/smoke.sh:102-103` | `run_marketplace_check skills` — `SKILL.md` present, frontmatter name matches directory |
| 3 | `_verify/smoke.sh:104-105` | `run_marketplace_check plugins` — `plugin.json` version agrees with `marketplace.json` |
| 4 | `_verify/smoke.sh:106-107` | `run_marketplace_check catalogs` — calls **two** different checks (`_verify/smoke.sh:87`): `check_catalogs`, which compares the install scripts' key arrays against the marketplace, and `check_docs`, which is the one that looks for catalog rows in the three READMEs |
| 5 | `_verify/smoke.sh:108-109` | `run_marketplace_check menus` — `.sh`/`.ps1` menus are a matched pair (`check_menu_parity` + `check_group_parity`, `_verify/smoke.sh:88`) |
| 6 | `_verify/smoke.sh:110-111` | `run_marketplace_check hooks` — hook command quoting and `; exit $LASTEXITCODE` |
| 7 | `_verify/smoke.sh:117-141` (registered `:142`) | `ps_check` — every `.ps1`/`.psm1` parses, tracked via CI mode plus one pass per untracked file |
| 8 | `_verify/smoke.sh:145-146` | `plugin/crew/skills/crew-setup/scripts/_test/round-trip.sh` — the audit's `canon()` contract |
| 9 | `_verify/smoke.sh:159-256` (registered `:257-258`) | `localgpu_cli_check` — localgpu CLI console script on the *persistent* PATH (profile files and the Windows User-scope registry, not the live shell). Reports "nothing to check" rather than failing when no venv exists (`:239-241`); **fails** when a venv exists at more than one root (`:248-253`) |
| 10 | `_verify/smoke.sh:279-373` (registered `:374-375`) | `version_agreement_check` — `pyproject.toml`/`plugin.json`/`marketplace.json`/hardcoded version literals all agree, plus any `_version.py` **executed** in an isolated subprocess (`-I`, 15s timeout) so a derivation bug is caught, not just a stale literal (`:339-367`) |
| 11 | `_verify/smoke.sh:385-402` (registered `:403-404`) | **New at this anchor.** `claude_validate_check` — `claude plugin validate --strict` over the marketplace root and five `plugin/*` directories, loading each manifest through the CLI's own parser. Registered with `check_optional`, not `check`: it returns 2 (SKIP) when the `claude` binary is absent (`:386-389`), because smoke.sh must not require an interactive login to run at all. Its own comment (`:378-383`) says it is the check that caught the argument-hint bug rows 2 and 3 did not |

**Row 11 is a fail-open shape worth naming.** On any host without the `claude`
CLI on PATH — this Linux one included — check 11 reports SKIP and the suite's
tail still reads as a clean run. The stricter manifest parse simply does not
happen locally; `.github/workflows/marketplace.yml` installs the CLI and is the
only place it reliably runs. A green `smoke.sh` is therefore not evidence that
`claude plugin validate --strict` passed.

**History, from the `7b0d8f3a` pass. The line numbers in the five bullets below
are the ones that pass corrected and are now themselves superseded by the table
above — read them for *which* rows were historically mis-cited and why, never as
current citations.** Five of these rows moved:

- Row 4 cited `_verify/smoke.sh:65` for "calls both `check_catalogs` and
  `check_docs`". Line 65 is `groups = {`. The `"catalogs"` lambda is at `:69`.
  The row's *description* was also wrong: it said the group checks "catalog rows
  in all three READMEs", which describes `check_docs`
  (`scripts/check-marketplace.py:264-278`, moved from `:263-277`) only.
  `check_catalogs` (`scripts/check-marketplace.py:167-192`, moved from
  `:166-191`) reads `SH` and `PS1` and compares
  install-script key arrays — nothing to do with READMEs. Merging the two into
  one label loses the install-script half entirely.
- Row 5 cited `:66` for the `"menus"` lambda, which is at `:70`. (`:66` is the
  `"registration"` lambda — a plausible-looking wrong line.)
- Row 7 cited `:97-124`. `:97-98` are comment lines; `ps_check` is `:99-123`.
- Row 8 cited `:126-127`. `:126` is the `# --- check 8` banner; the `check`
  invocation is `:127-128`.
- Row 9 cited `:239 (context)` with no function range. The function is
  `:141-238` and the invocation spans `:239-240`.

Rows 1-3, 6 and 10 re-resolved exactly as written.

**Fixed in the source between `ea8a014` and this anchor.** Four consecutive
passes of this note recorded "the 9 checks header comment is still stale"; it
now reads 11 and is correct. Kept visible rather than deleted, because a reader
carrying the old finding forward would go looking for a defect that is gone —
and because the correction landed in `_verify/smoke.sh`, which this note does
not own, so nothing here caused it.

## `scripts/check-marketplace.py` — the direct gate

**DERIVED, re-read in full at this anchor. The "eleven functions" figure this
note carried through four passes is wrong at HEAD — it is now fourteen.**
`main()` is `scripts/check-marketplace.py:1196-1229`, moved from `:991-1021`
(and `:938-968`, and `:377-405`, before that). Its check calls are
`:1205-1218` (moved from `:1000-1010`), in this order:

`check_registration`, `check_skill_manifests`, `check_plugin_manifests`,
**`check_argument_hint_frontmatter`**, **`check_license_consistency`**,
`check_catalogs`, `check_menu_parity`, `check_group_parity`, `check_docs`,
`check_hook_commands`, **`check_command_backtick_spans`**, `check_versions`,
`check_self_claims`, `check_crew_ignore_policy`.

**Three are new since `ea8a014`**, shown in bold, and the relative order of the
eleven that existed before is unchanged — the additions are insertions, not a
reordering. Definitions, by AST rather than by grep:
`check_argument_hint_frontmatter` (`:176-265`),
`check_license_consistency` (`:268-298`),
`check_command_backtick_spans` (`:1094-1147`).

**Re-measure this figure, do not cite it.** Three of the four passes recorded in
this note's history state a different number (nine, then eleven, now fourteen),
and every one of them was correct on the day. The durable form is the command:
`python3 -c "import ast; t=ast.parse(open('scripts/check-marketplace.py').read());
print([n.name for n in t.body if isinstance(n, ast.FunctionDef)])"` for the
definitions, and reading `main()`'s body for what is actually *called* — the two
differ, because `count_plugin_skills` and the `_`-prefixed ignore-policy helpers
are module-level functions that `main()` never calls directly.

All fourteen run every time this script is invoked directly. `_verify/smoke.sh`'s
internal fast-path helper (`_verify/smoke.sh:72-98`, the `groups` map at
`:83-90`) still covers the same **eight** it always did — `check_registration`,
`check_skill_manifests`, `check_plugin_manifests`, `check_catalogs`,
`check_docs`, `check_menu_parity`, `check_group_parity`, `check_hook_commands`.
That is now eight of fourteen, so the fast path misses **six**:
`check_versions`, `check_self_claims`, `check_crew_ignore_policy`,
`check_argument_hint_frontmatter`, `check_license_consistency` and
`check_command_backtick_spans` — up from three at the previous anchor. The
helper's own comment (`:82`) still reads "Same calls main() makes, in the same
order, minus check_versions", which names one omission and now understates the
gap by five. See `marketplace-registration.md` for the related correction to the
"runs everything except `check_versions`" claim, which was only ever true of
this helper, not of the script.

`check_versions` (`scripts/check-marketplace.py:518-551`, moved from `:369-402`)
is skipped entirely, with a printed note, outside a git checkout
(`scripts/check-marketplace.py:524-526`) or when `marketplace.json` has no
commit history (`scripts/check-marketplace.py:529-531`) — both written out
rather than abbreviated, because the intervening `marketplace.json` makes a
bare `:529-531` bind to the wrong file by eye. The full history walk is
`scripts/check-marketplace.py:528` and the first-parent walk `357338cb` (#144)
added beside it is `:534` (moved from `:379`, `:385`); `bump_candidates` is
`:483-515` (moved from `:334-368`).

### `check_self_claims` gained a marker type, not a new check

**DERIVED, re-read at this anchor; every citation below moved.** `f9bb78a6`
(#169) added a third claim type to `check_self_claims`
(`scripts/check-marketplace.py:579-722`, moved from `:430-777` — note the body
*shrank*, so an offset would have mis-pointed it): alongside `skills-count`
(the marketplace-wide total) and `plugin-version:<name>` (`:693`), it
recognises `plugin-skills:<name>` (`:665-691`, moved from `:516-542`), which
counts `SKILL.md`-bearing subdirectories of `plugin/<name>/skills/` on disk via
`count_plugin_skills` (`:562-576`, moved from `:413-427`) and fails if a marked
number disagrees. `BIND_WINDOW` is 12 lines (`:559`), which is the marker's
binding rule CLAUDE.md states.

The commit's own message states why: `skills-count` only ever verified the
marketplace's total skill-plugin count, which is a different quantity from a
bundled plugin's own skill count, so crew's bundle drifting from 17 to 18 on
disk went uncaught through two correction passes (`f12003e2` #166, `b76ad19a`
#168) even with the gate green throughout.

Five sites carry `<!-- claim: plugin-skills:crew -->`. **Three of the five
citations this note recorded are now wrong** — re-derived with
`grep -rn "claim: plugin-skills:crew"` rather than offset:
`README.md:168` (from `:166`), `README.md:889` (from `:885`),
`INSTALLATION.md:252` (from `:251`), `plugin/PLUGINS.md:17` (unchanged) and
`plugin/README.md:414` (unchanged). All five currently state 20 bundled skills.
See `marketplace-registration.md` for what each said before and after.
`scripts/_test/self-claims.py` did **not** change between `ea8a014` and this
anchor and is still not read line by line here.

`main()`'s *order* is unaffected, but its **call count is not** — it went from
eleven to fourteen in this interval for unrelated reasons. See the section
above. This claim type remains a behavior change inside one existing check.

## `scripts/_test/crew-ignore-policy.py` — new sabotage suite, not yet wired locally

**DERIVED, re-read at this anchor.** `check_crew_ignore_policy`
(`scripts/check-marketplace.py:929-1091`, moved from `:780-942`) is no longer
the newest of the checks `main()` runs — `check_command_backtick_spans`
(`:1094-1147`) is defined after it. Its own sabotage suite,
`scripts/_test/crew-ignore-policy.py`, asserts it three ways rather than one -
counted by AST, not by trusting a header comment: **29** entries in `CASES`
(`:182`), **4** in `PROBE_CASES` (`:470`), and one more result from
`no_other_suite_contradicts_us()` (`:498`, scored in `main()` at `:562-570`).
29 + 4 + 1 = **34**, matching the suite's own summary line
(`crew-ignore-policy: {passed} passed, {failed} failed`, `:602`).

**Correcting a figure this note has carried since the suite was first
documented: the file is 607 lines, not 755.** It did not change in this
interval — `git diff --stat ea8a014..HEAD -- scripts/_test/crew-ignore-policy.py`
is empty and `git show ea8a014:scripts/_test/crew-ignore-policy.py | wc -l`
is also 607 — so the figure was wrong when it was written, not rotted since.
Every `path:line` citation into the file in the same paragraph re-resolved
exactly, which is the useful shape of the error: the line anchors were derived
and the length was not.

The suite builds a throwaway git repo per case and points the checker's `ROOT`
at it - nothing touches this repository's own files (`:4-5`). It exists because
the policy - `.crew/*` ignored, a named list un-ignored, restated in prose in
several places - had drifted into three different stated policies at once
before this check existed, including a `.gitignore` comment claiming nothing
under `.crew/` is ever committed while two negations two lines below it
committed exactly two paths. Three fail-open shapes each earned their own case:
an empty extraction (a doc that stops using the `!.crew/x` form), every marker
deleted, and `.crew/` written with a trailing slash (git then refuses to
descend, so every negation below is silently dead while the file still reads as
policy-compliant).

**Run locally with `python3 scripts/_test/crew-ignore-policy.py`.** It is
wired into CI (`.github/workflows/marketplace.yml:50-51`, moved from `:41-42`)
but **still not** into `.crew/verify.json`'s `scripts/**` rule
(`.crew/verify.json:73-86`, moved from `:52-59`), which matches this file by
path but does not run it. That gap survived this interval even though the
rule's `run` list *grew from seven commands to nine* — `ps-install-keys.sh` and
`uv-install.sh` were added and this suite was not. See "What `.crew/verify.json`
actually maps" below. It is also not one of `_verify/smoke.sh`'s eight covered
functions, since `check_crew_ignore_policy` itself is not.

`.crew/codemap/` is explicitly out of the check's scope
(`scripts/check-marketplace.py:952`, moved from `:803-806`): a generated map restating the policy
would be fixed by regenerating it, not by editing it, so this note's own
citations of the policy elsewhere (see `CLAUDE.md`'s `## Memory` section) are
never something this gate checks.

## What `.crew/verify.json` actually maps

**DERIVED, re-read in full at this anchor. Every line citation in this section
moved** — the file grew +120/-32 lines since `ea8a014`, so nothing here is
carried forward. Still **21** `rules` (via `json.load`, not a `grep -c`
estimate), each an ordered `paths`/`run` pair, plus a `default`
(`["bash _verify/smoke.sh"]`, `:235`) and an `unmapped: "fail"` (`:236`). One
rule still carries a review `agents` entry.

**All 21 rules now declare a `reach`, and every one reads `"local"`.** Three
did not at the previous anchor; the field is now uniform, including on the two
rules whose `run` is empty, whose `why` fields argue explicitly that `local` is
the only honest value for running nothing and that
`verify_record.scan_reach([])` already returns it.

**The file's own `anchor` (`.crew/verify.json:3`) still reads
`"repo@5238be3d"` and was not advanced by any of the edits that produced the
state read here** — so it is further behind its own contents than at the
previous anchor, not closer. Treat every `why` field as what the file says,
never as fact about today's tree, and see the declared-timings warning below
for a case where that distinction bites.

Notable rules, relevant to subsystems covered elsewhere in this codemap:

- `.claude-plugin/marketplace.json`, `**/.claude-plugin/plugin.json`,
  `**/pyproject.toml`, `plugin/**`, `skills/**`, `MARKETPLACE.md`,
  `skills-lock.json` → `python3 scripts/check-marketplace.py`
  (`.crew/verify.json:46-53`, moved from `:32-36`; three of the seven globs are
  new) — the full gate, including version drift, on the broadest glob in the
  file. Its `why` (`:52`) calls this "the ONLY check that catches a content
  change shipped with no version bump" and cites main red from `12e43eee` to
  `5238be3d` on exactly that defect. This is also the catch-all the file's own
  `_note` warns about (`:4-20`, moved from `:12-15`): because the glob is this
  broad, `unmapped` rarely fires, which is a fact about coverage breadth, not
  proof every new check gets noticed. The `_note` now puts a number on it —
  "0 of 790 tracked files are unmapped" — and says in the same breath that this
  is not proof a new check would be noticed.
- `plugin/PLUGINS.md`, `plugin/README.md`, `plugin/*/README.md`, `**/SKILL.md`,
  both install scripts, `plugin/localgpu/**` → `bash _verify/smoke.sh`
  (`.crew/verify.json:54-61`, moved from `:38-42`) — declared `seconds: 5`
  (was 7), sabotage-proven by setting crew's `marketplace.json` version to
  `9.9.9` and confirming exit 1. Its `why` still describes smoke.sh as covering
  "ten registration invariants"; there are now eleven, one of which SKIPs
  without the `claude` CLI. See the smoke.sh section above.
- **`rules[2]`, the doc rule, and the one change in this file most worth
  reading the code for.** `README.md`, `CLAUDE.md`, `AGENTS.md`, `TODO.md`,
  `CHANGELOG.md`, `INSTALLATION.md`, `plugin/PLUGINS.md`, `plugin/README.md`,
  `plugin/*/README.md`, `docs/**`, `MARKETPLACE.md`, `SECURITY.md`,
  `Skill-Authoring-Standard.md`, `Skill-Pipeline.md` → three commands
  (`.crew/verify.json:62-72`), of which `python3 scripts/check-marketplace.py`
  is now **first**. It was not there at all before. Its `why` (`:72`) records
  the demonstration: appending a marked `999 skills` claim to `README.md` left
  *both* of the rule's two original commands at rc 0, while
  `check-marketplace.py` reported `README.md:918: claims 999 skills, but
  marketplace.json registers 36` and exited 1. The checker that reads this
  repo's own docs is `check_self_claims` **inside** `check-marketplace.py`,
  which walks `git ls-files *.md`; `scripts/_test/self-claims.py` is the suite
  that tests that checker against synthetic fixtures and never reads this
  repo's docs at all. So for all thirteen paths the rule claimed, the pairing
  could not go red. `AGENTS.md` joined the path list in the same edit.
  **This is the exact fail-open shape CLAUDE.md's lessons name — a rule that
  matches, runs, and passes without being able to fail** — and it survived
  every prior pass of this note, which recorded the rule's existence and never
  asked whether its commands could go red on its paths.
- `scripts/**` → **nine** commands run together (`.crew/verify.json:73-86`,
  moved from `:52-59`; was seven): `check-marketplace.py`, `self-claims.py`,
  `version-drift.py`, `sync-updates.py --check`, `menu-groups.sh`,
  `check-powershell.sh`, **`ps-install-keys.sh`**, **`uv-install.sh`**, and
  `bash -n install-prerequisites.sh`. **This rule still matches
  `scripts/_test/crew-ignore-policy.py` by path and still does not run it** —
  the 34-case sabotage suite is absent from a list that grew by two commands in
  this interval. CI (`.github/workflows/marketplace.yml:50-51`) does run it
  directly; locally, editing that suite and running only the matched rule would
  not exercise the change.
- The hooks-gate suite → `python3 -m pytest
  plugin/crew/tests/test_verify_gate_baseline.py ... -q`
  (`.crew/verify.json:87-102`, moved from `:62-70`; the `run` string is `:99`)
  — declared `seconds: 96` (was 29), nine test files, sabotage-proven by
  reverting the Stop gate's baseline to the original `git diff --name-only
  HEAD` bug. **This rule carries no `agents` key** — still true, re-checked.
  The one rule that carries `agents` (`.crew/verify.json:172`, moved from
  `:130`) sits on the `**/*.ps1`/`**/*.psm1` rule at `.crew/verify.json:169-175`
  and names
  `powershell-security-hardening`, not `security`, and has nothing to do with
  hooks. Its `why` is by a wide margin the longest field in the file and reads
  as a review log across eight rounds; treat it as history, not as a statement
  about HEAD.
- `plugin/crew/tests/conftest.py`, `crew_fixtures.py`, `context.py`,
  `sabotage.py` → `python3 -m pytest plugin/crew/tests/ -q`
  (`.crew/verify.json:147-153`, moved from `:112-115`) — declared
  `seconds: 185`, while the `why` text immediately beside it still opens "245s".
  Deliberately over the ~3-minute guidance, because these four files are
  imported by every test module and a change here can make the whole suite
  vacuous while every module still reports green. `plugin/crew/tests` and
  `sabotage.py` are still **not** run by `_verify/run-all.sh` (confirmed below,
  unchanged), so this is the *only* local rule that reaches them.
- `**/*.py`, `.pylintrc`, `ruff.toml` → ruff and pylint
  (`.crew/verify.json:176-182`) — **each command is now wrapped in an `sh -c`
  tool-presence probe that exits 77** (`:178-179`) rather than exiting 1 when
  the module is absent. On this Linux host both are absent (PEP 668 marks the
  interpreter externally-managed), so this rule records `skipped` every turn.
- `mcp-servers/**` → `npm --prefix mcp-servers test`, likewise wrapped in a
  probe exiting 77 for a missing `npm` **and** for an absent
  `mcp-servers/node_modules` (`.crew/verify.json:189-194`, moved from
  `:142-144`; the `run` string is `:191`) — declared `seconds: 196`, `why` says
  21s. The precondition that used to sit in prose ("`npm --prefix mcp-servers
  install` must have been run once") is now enforced by the probe, because
  nothing parses a `why` field. Still judge it by exit code, never the visible
  tail: a workspace script prints a later package's PASS after an earlier
  package's failure.
- `.github/workflows/**` → `run: []`, deliberately
  (`.crew/verify.json:220-225`, moved from `:163-165`) — nothing on this
  machine validates workflow YAML; GitHub is the only validator.
- `graphify-out/**`, `.crew/codemap/**`, `.crew/**`, `.serena/**` and several
  more → `run: []`, deliberately (`.crew/verify.json:226-232`, moved from
  `:167-171`) — `graphify-out/` is regenerated by a post-commit hook and must
  never be hand-edited; `.crew/codemap/` is prose re-checked by `/crew:onboard`,
  not by a gate. Listed explicitly so `unmapped: fail` still fires on anything
  genuinely new. **This is the rule that covers this note**, which is why
  editing it requires no version bump and triggers no command.

### Two defects in the gate this map feeds

**DERIVED, read from the gate's own source, and recorded here because they
decide what a green `.crew/.verify-verified-at` is worth.**

1. **FIXED, not yet committed as of this note.** *(Was: "One failing command
   discards the evidence for every rule that passed", open at the previous
   anchor `84976536` and every one before it. Kept below, marked stale,
   rather than deleted — a reader who saw the old finding should see it was
   actually addressed, not wonder whether this note simply dropped it.)*
   `plugin/crew/hooks/scripts/verify-gate.sh:1563` (moved; was `:1403`) is
   still `[ "$FAILED" -eq 0 ] || exit 2`, but the per-rule record sync now
   runs BEFORE it, on every turn, not only when nothing FAILED — see the
   comment immediately above that line for the reasoning, and
   `plugin/crew/hooks/scripts/verify-gate.ps1`'s twin (`if ($failed) { exit
   2 }`, also moved after its own sync call). `verify_record.py` gained a
   `"fail"` branch in `_sync` that deliberately does **not** persist the
   failing rule's own outcome (a first version of this fix that DID persist
   it was itself reviewed BLOCK: the entry orphaned the moment the failing
   rule was edited to fix it, since `rule_key()` hashes `run` — see
   `plugin/crew/tests/test_verify_gate_partial_failure_recording.py`, whose
   docstring and
   `test_editing_a_failing_rule_to_pass_does_not_orphan_the_marker`
   reproduce and guard both shapes of this fix). This map's own anchor is
   **not** advanced by this note — no commit exists yet for this change —
   so treat this paragraph as ahead of the anchor below it until the next
   full pass reconciles them; the per-path diff check
   (`git diff --name-only 2b337296..HEAD -- plugin/crew/hooks/scripts/verify-gate.sh
   plugin/crew/hooks/scripts/verify-gate.ps1
   plugin/crew/hooks/scripts/verify_record.py`) will show these three files
   once that commit lands.
   `.crew/verify.json:193`'s `why` field described the OLD, still-broken
   shape and has been corrected in the same change.
2. **A declared `seconds` can never be corrected by measurement.**
   `plugin/crew/hooks/scripts/verify_record.py:609` (moved from `:558` by
   this same uncommitted change — see item 1 above) gates the measured-cost
   cache on `if rule.get("unknown"):` — only a rule with **no** declared
   `seconds` gets its elapsed time stored (`:616-617`; the comment at
   `:610-615` explains a different, already-fixed bug about discarding
   sub-second measurements). So a stale declared figure is permanent until
   someone edits the JSON by hand. Three rules are reported wrong in that
   direction: `rules[3]` declares 81s, `rules[4]` 96s and `rules[8]` 185s,
   against 16s, 15s and 161s. **The three declared figures were read from
   `.crew/verify.json` at this anchor; the three measured ones were not taken
   by this pass** — they are carried from the session that filed the defect,
   and no suite was run here to reproduce them. Re-time before acting on the
   gap. Any such measurement is in any case a fact about **one** host, not
   about the Windows / Git Bash machine every other number in the file was
   timed on — `rules[2]`'s
   `why` argues that point explicitly and deliberately declares a Windows-priced
   12 over a Linux-measured 2. Re-time before treating any of the three as an
   error rather than a platform difference; what is *not* platform-dependent is
   that the mechanism to self-correct does not exist.

## `_verify/run-all.sh` — what the deep suite actually runs

**DERIVED. Still byte-identical at `84976536`** — `git diff --stat
ea8a014..HEAD -- _verify/run-all.sh` is empty, as it was over the previous
interval too, so this file has now gone unchanged across two anchors. Every
cited line below was nonetheless re-resolved by hand this pass rather than
trusted: `:17`, `:46`, `:49-50`, `:58-59`, `:81-82`, `:100-101`, `:112-113`,
`:119-120`, `:149`, `:150` and `:153` all land on what the list says they do.

The original warning, still the reason this section is worth its length: the
file being unchanged is **exactly** why the citations below once needed
correcting. **Most of them were already wrong before that pass**, not rotted by
a code change. They were carried from an
older revision of the file (150 lines) without being re-derived after an
8-line step was inserted before them, and every later "re-read in full"
claim in this note's own history repeated the same wrong numbers instead of
catching it. In order, as the file reads today:

1. `check-marketplace.py`, full gate including version drift (`:46`). Correct
   at every previous anchor too - this step sits above the insertion point.
2. `scripts/_test/menu-groups.sh` (`:49-50`). Also correct at every anchor.
3. **Missing from every previous version of this list.** `scripts/_test/check-powershell.sh`
   (`:52-59`) - the exemption-list suite that pins the checker's cmdlet-exemption
   scope to individual files rather than globally, sabotage-proven both
   directions per its own comment. This step exists at the *previous* anchor
   too (the file did not change); it was never counted.
4. localgpu `mcp/_test` under the install venv (`:81-85`, not `:72-76` as every
   prior version of this note said - `:72-76` is the venv-candidate-building
   loop above it) — skipped when no venv.
5. localgpu `cli/_test` under the same venv (`:100-104`, not `:91-95` - that
   range is comment text) — skipped when no venv.
6. gizmoduck's `tickets` confirmation-gate suite, `pytest
   plugin/gizmoduck/scripts/_test/` (`:111-116`, correct at the previous
   anchor - the one row that was), gated on `import pytest` succeeding for the
   resolved interpreter rather than on a venv.
7. `crew-setup` round-trip (`:119-120`, not `:110-111` - that range is inside
   the gizmoduck conditional above).
8. Every PowerShell artifact, tracked then untracked (`:124-137`, not
   `:115-128`), with the untracked loop fed by `< <(...)` rather than a pipe so
   a `FAIL` recorded inside it reaches the parent shell (`:131-134`, not
   `:117-121`).
9. `plugin/crew/hooks/scripts/_test/run-tests.sh`, 900s budget, **run by
   default** (`:150`, not `:141`). `--with-hooks` is parsed (`:17`, correct) but
   is a documented no-op (`:149`, not `:140`).
10. `scripts/_test/drift-detection.sh` — permanently `skip`ped (`:153-154`, not
    `:144-145`), never automatic, because it drives the real Claude Code CLI.

That is **ten** steps, not nine - the missing check-powershell.sh step is why
every citation from item 4 onward was off by exactly nine lines in every prior
version of this note. `_verify/run-all.sh` is byte-identical between the
previous anchor (`7b0d8f3a`) and this one (`git diff --stat 7b0d8f3a 0a9d8937
-- _verify/run-all.sh` is empty), so the growth predates both and cannot be
this pass's change. `git show 2b095452` ("Scope the PowerShell exemptions to
paths, and give them a suite that fails") is the commit: `+9 -0` at exactly
this insertion point, adding the six-line comment, the two-line `run` call and
the blank line that follow it - a single insertion the numbered list was never
updated to include, not a series of small drifts.

**Not run by `run-all.sh`, and worth knowing:** `plugin/crew/tests` and
`plugin/crew/tests/sabotage.py`. `.crew/verify.json:112-115` (now readable, not
UNVERIFIABLE) maps them to `python3 -m pytest plugin/crew/tests/ -q` instead -
see "What `.crew/verify.json` actually maps" above. Reading `_verify/run-all.sh`
at this anchor confirms the durable wiring an earlier `why` field once wanted
still has not landed there: neither `plugin/crew/tests` nor `sabotage.py`
appears in the file. Since `.crew/verify.json` now travels with the repo, this
is no longer "nothing runs them anywhere but here" - the verify.json rule
reaches them on any clone, even though `run-all.sh` still does not.

## History — what a *previous* task ran (not this one)

**This refresh ran one command and no suite.** `python3
scripts/check-marketplace.py` at `84976536` on the Linux host:
`marketplace: 36 skills, 5 plugins`, `all checks passed`, rc 0 — run because
the repo's gate requires it, with `graphify-out/` dirty from a concurrent lane
and no other path modified. Everything else above is read from source.

Retained for reference, as a claim about the 3167721f-era tree rather than
about HEAD: that task ran `python scripts/check-marketplace.py` →
`marketplace: 25 skills, 4 plugins`, `all checks passed`, and
`bash _verify/smoke.sh` → 10 passed, 0 failed. The first figure is now
superseded by the run above (25/4 → 36/5); the `smoke.sh` result has **not**
been reproduced at any anchor since and should be treated as unverified — and
note that a 10-pass total predates the eleventh check existing, so it cannot
be compared to a run made today without accounting for the SKIP.

`_verify/run-all.sh` was not run then and has not been run now — it drives
pytest suites against a bootstrapped localgpu venv and a real PowerShell, and
its own header estimates minutes, not seconds (`_verify/run-all.sh:3`).
## Entry points

**Every line below was re-pointed by name this pass** — `grep -n "def <name>"`
and an AST walk, never an offset. All six moved, three of them by hundreds of
lines, so an offset applied to any one of them would have been wrong.

- `plugin/crew/tests/test_crew_config.py:1491` (moved from `:1488`) — `test_resolve_config_inherits_a_global_through_the_init_template`, the END-TO-END null-shadow test. The helper-level tests above it pass with the call site deleted from `resolve_config`; this one does not. That gap was found by sabotage, not by review.
- `plugin/crew/tests/test_crew_state.py:1291` (moved from `:1016`) — `test_a_backslash_in_a_branch_name_is_flattened_too`, which catches the `[\/]+` character class that matched `/` alone.
- `plugin/crew/tests/test_crew_state.py:1325` (moved from `:1050`) — `test_two_repos_with_the_same_basename_do_not_share_a_leaf`, the cross-repo worktree collision the security review raised.
- `scripts/check-marketplace.py:929` (moved from `:780`) — `check_crew_ignore_policy`: the `.crew/` ignore-policy gate, sabotage-tested by `scripts/_test/crew-ignore-policy.py` (see above).
- `scripts/check-marketplace.py:579` (moved from `:430`) — `check_self_claims`, whose scope is unchanged beyond the `plugin-skills:<name>` marker type `f9bb78a6` (#169) added (see above).
- `plugin/crew/tests/sabotage.py:3265` (moved from `:2484`) — module entry point (`main()`).

**`sabotage.py`'s mutation count is deliberately not stated here.** A figure of
188 has circulated; the measured values are 179 at `d9da1409` and 190 at this
anchor, so any number written down is stale by the next mutation added. The
invariant instead: `MUTATIONS` is a module-level list at
`plugin/crew/tests/sabotage.py:175`, and its length is
`python3 -c "import ast; t=ast.parse(open('plugin/crew/tests/sabotage.py').read());
print(next(len(n.value.elts) for n in t.body if isinstance(n, ast.Assign)
and n.targets[0].id == 'MUTATIONS'))"`. Re-measure; do not cite.

## Owns data

- `.work/PROMOTIONS.md` — machine-local (`.gitignore:273`, unchanged this pass and re-resolved: line 273 is `.work/`), so it is THIS machine's promotion history and never travels to another clone. `plugin/crew/hooks/scripts/promote-gate.sh:171` reads it; `plugin/crew/hooks/scripts/verify-gate.sh:77` greps it for an environment/sha row and `:80` refuses to end a turn after a deploy that wrote none. Those three citations were unanchored in every previous version of this note — they are added here, not corrected.

## Calls out to

- `pwsh` from `plugin/crew/tests/test_verify_gate_bash_resolver.py`. The file did **not** change since `ea8a014` (`git diff --stat` empty). **The failure it describes was not reproduced at this anchor and should not be read as current:** "two tests fail on this machine — they replace `PATH` and `SystemRoot` with fake trees and pwsh cannot then initialise (`Win32Exception 126`), environmental and pre-existing, confirmed identical at `1f97e51c`" is a claim about a **Windows** host. This pass ran on Linux, ran no pytest at all, and `Win32Exception` cannot arise here. Retained as the last measurement anyone made, with its platform now stated — which it was not before, and which is the difference between a finding and a rumour.
- `plugin/crew/hooks/scripts/crew_platform.py` — via the `crew` subsystem
- `plugin/crew/hooks/scripts/crew_state.py` — via the `crew` subsystem
- `plugin/crew/skills/crew-graph/scripts/crew_upgrade.py` — via the `crew` subsystem
- `plugin/crew/tests/context.py` — via the `crew` subsystem

## Re-verification pass, 2026-09-12

**Re-verified, not re-derived.** Every claim above is the previous pass's. What changed: eleven
citations were re-pointed after re-reading the files they name, `_verify/run-all.sh`'s length was
re-measured (150 -> 159), and every claim resting on `.crew/verify.json` was marked UNVERIFIABLE
HERE rather than re-anchored silently.

The previous anchor, `useful-claude-add-ons@d61342c3`, does not resolve in this repository - a
squash merge discarded the branch commit its writer recorded. Fixed for future passes in crew
0.19.13, which records `git merge-base HEAD origin/main` instead. See
`.crew/codemap/install-scripts.md` for the full account.

Citations were re-pointed by aligning each cited file between revisions with `difflib` and matching
on **content**, not by applying an offset. Every citation outside `.crew/verify.json` mapped
cleanly: **zero** needed a full re-read, which is why this note required less correction than its
neighbours despite being the one with the largest unverifiable block.

Count at this anchor: 31 of this note's `path:line` citations point into `.crew/verify.json`. None
of them could be checked. That is the single largest concentration of unverifiable claims in the
codemap, and it is structural rather than accidental - the file is machine-local by design, so no
clone of this repository can ever verify them.

**Superseded 2026-09-14.** The 31-citation UNVERIFIABLE block described above no longer exists as
described: `.crew/verify.json` is tracked as of crew 0.19.46 (`0a9d8937`), "the file is machine-local
by design" is no longer true of it, and every `.crew/verify.json` citation elsewhere in this note was
rewritten from a direct read at that anchor rather than carried forward. This section is left in
place as a record of what the constraint used to be, not as a current statement of it.

## Re-anchor provenance — 84976536 -> 2b337296, 2026-09-22

Re-anchor only. The whole-repo diff between the two commits
(`git diff --name-only 84976536..2b337296`) touches
`.claude-plugin/marketplace.json` (doc-builder's version only — this note's
`marketplace.json` citations are all about `check_versions`/`check_self_claims`
mechanism, or the sabotage-proof version bump to `9.9.9`/`999 skills`, none of
which rest on doc-builder's actual version), `CHANGELOG.md`, `README.md`,
three `docs/diagrams/*.mmd` files, `graphify-out/*`, two
`skills/doc-builder/*` files, and eight `.crew/codemap/*.md` files (concurrent
re-anchor edits by this and other sessions, not code, and not cited by this
note). **`README.md` is one exception — it IS one of this note's own tracked
paths** (listed by name in the `ea8a014 -> 84976536` per-path check's
`git diff` command, above) and it IS in the
`84976536..2b337296` diff; the next paragraph gives it the re-check that
requires. `.claude-plugin/marketplace.json` is likewise tracked and present in
the diff, but only doc-builder's version changed — none of this note's
`marketplace.json` claims rest on that. Every other cited path is absent from
the diff.

Grepped with `grep -noE '(^|[^/A-Za-z])README\.md:[0-9]+'` and for
`CHANGELOG.md:<n>`: **`CHANGELOG.md:<n>` does not appear in this note.**
**`README.md:<n>` DOES appear, three times, and a previous version of this
paragraph wrongly said neither did** — corrected here. `:407` cites
`README.md:168` (moved from `:166`) and `README.md:889` (moved from `:885`)
**inside a prose paragraph** (re-checked with `sed -n 403,409p`: it continues
"Five sites carry `<!-- claim: plugin-skills:crew -->` ... re-derived with
`grep -rn ...`", not a table — a previous version of this correction wrongly
called it a "quoted table cell", which describes `marketplace-registration.md`'s
history table, not this citation); `:521` cites `README.md:918` inside a
quoted sabotage-test error message ("`README.md:918: claims 999 skills, but
marketplace.json registers 36`"). The conclusion drawn from the earlier, wrong
count still holds: `README.md`'s only change in this range (the install-URL
re-pin, `2cc73a1e`) touched lines 12 and 18 in place with no line count
change, so none of these three citations shifted or needed re-reading.
Nothing else was re-read.
