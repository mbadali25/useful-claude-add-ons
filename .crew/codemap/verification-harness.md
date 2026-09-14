anchor: useful-claude-add-ons@975480b7
verified: 2026-09-14
Re-anchor only, no content change: this pass ran
`git diff --name-only 0a9d8937..975480b7 -- _verify/ .crew/verify.json
scripts/check-marketplace.py plugin/crew/tests/ plugin/crew/hooks/` (the
paths this note cites) and it returned nothing, so every claim below carries
forward from `0a9d8937` unverified-but-unchanged rather than re-read. That
per-path check was prompted by a skills-count correction made elsewhere in
the codemap (`crew.md`, `marketplace-registration.md`, `repo-docs.md`); this
note has no crew-bundle skill-count claim to correct.

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

**JUDGEMENT, and now backed by an actual read rather than history-only claims.**
`.crew/verify.json` is tracked and present at this anchor - the first time this
note could read it directly instead of carrying forward an older pass's
citations. It holds **21** `rules` (counted via `json.load`), not the 15 an
earlier pass recorded or the 13 an even earlier one did; its own `anchor` field
(`.crew/verify.json:3`) reads `"repo@5238be3d"`, 22 commits behind this note's
`0a9d8937`. Most rules name one of the three scripted layers above, but plenty
do not: `python3 -m pytest plugin/crew/tests/test_verify_gate_baseline.py ...`
(`.crew/verify.json:69`, the hooks-gate suite), `python3 -m pytest
plugin/crew/tests/ -q` (`:114`, the shared-fixture rule), `npm --prefix
mcp-servers test` (`:143`), `bash skills/bitbucket/scripts/_test/merge_gate.sh`
(`:147`), and several more listed in the "What `.crew/verify.json` actually
maps" section below, which replaces the previous, history-only account. The
accurate statement remains: `.crew/verify.json` maps a changed path to the
commands that verify it, and those commands are *often but not always* one of
the three scripted layers.

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

- No suite was executed. Every behavioural claim below is read from source. A
  claim that a check *passes* is nowhere in this note; the run results recorded
  at older anchors remain marked as history (see the last section).
- `.crew/verify.json`'s stated *rationales* (its `why` fields) make historical
  claims — timing figures "measured on this machine", commit-specific sabotage
  proofs — that cannot be checked by reading today's tree. They are quoted here
  as what the file says, never asserted as fact. The file's own `anchor`
  (`.crew/verify.json:3`, `"repo@5238be3d"`) is itself 22 commits behind this
  note's `0a9d8937`, so its `why` fields predate `check_self_claims` and
  `check_crew_ignore_policy` existing at all - see below for what that does and
  does not affect.

## `_verify/smoke.sh` — 10 checks, not 9

**DERIVED.** The file's own header comment says *"9 checks, target is under
90 seconds"* (`_verify/smoke.sh:3`). Counting the actual `check "..." ...`
invocations in the file finds **10**:

| # | Line | What it runs |
|---|---|---|
| 1 | `_verify/smoke.sh:82-83` | `run_marketplace_check registration` — every dir registered, every source resolves, no nested marketplace |
| 2 | `_verify/smoke.sh:84-85` | `run_marketplace_check skills` — `SKILL.md` present, frontmatter name matches directory |
| 3 | `_verify/smoke.sh:86-87` | `run_marketplace_check plugins` — `plugin.json` version agrees with `marketplace.json` |
| 4 | `_verify/smoke.sh:88-89` | `run_marketplace_check catalogs` — calls **two** different checks (`_verify/smoke.sh:69`): `check_catalogs`, which compares the install scripts' key arrays against the marketplace, and `check_docs`, which is the one that looks for catalog rows in the three READMEs |
| 5 | `_verify/smoke.sh:90-91` | `run_marketplace_check menus` — `.sh`/`.ps1` menus are a matched pair (`check_menu_parity` + `check_group_parity`, `_verify/smoke.sh:70`) |
| 6 | `_verify/smoke.sh:92-93` | `run_marketplace_check hooks` — hook command quoting and `; exit $LASTEXITCODE` |
| 7 | `_verify/smoke.sh:99-123` (registered `:124`) | `ps_check` — every `.ps1`/`.psm1` parses, tracked via CI mode plus one pass per untracked file |
| 8 | `_verify/smoke.sh:127-128` | `plugin/crew/skills/crew-setup/scripts/_test/round-trip.sh` — the audit's `canon()` contract |
| 9 | `_verify/smoke.sh:141-238` (registered `:239-240`) | `localgpu_cli_check` — localgpu CLI console script on the *persistent* PATH (profile files and the Windows User-scope registry, not the live shell). Reports "nothing to check" rather than failing when no venv exists (`:221-223`); **fails** when a venv exists at more than one root (`:230-236`) |
| 10 | `_verify/smoke.sh:356-357` | `version_agreement_check` — `pyproject.toml`/`plugin.json`/`marketplace.json`/hardcoded version literals all agree, plus any `_version.py` **executed** in an isolated subprocess so a derivation bug is caught, not just a stale literal (`:321-349`) |

**Corrected at a previous anchor (`7b0d8f3a`), still true here — re-verified,
not re-done.** Five of these rows moved:

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

**Not fixed here** — the "9 checks" header comment is still stale in the source.
This note does not touch `_verify/`; recorded so the discrepancy is not mistaken
for a run-time failure by the next reader.

## `scripts/check-marketplace.py` — the direct gate

**DERIVED, re-read at this anchor because the file changed substantially.**
`main()` is now `scripts/check-marketplace.py:938-968`, moved from `:377-405`.
Its check calls are `:947-957`, in this order: `check_registration`,
`check_skill_manifests`, `check_plugin_manifests`, `check_catalogs`,
`check_menu_parity`, `check_group_parity`, `check_docs`, `check_hook_commands`,
`check_versions`, `check_self_claims`, `check_crew_ignore_policy`.

That is **eleven** functions, not the nine this note previously corrected
"eight" to. Two were added between the previous anchor and this one:
`check_self_claims` (`3374e8e0`, #139) and `check_crew_ignore_policy`
(`0a9d8937`, #161, this note's anchor as of the previous pass).
`marketplace-registration.md` has
been updated to the same figure in this pass — the two-notes disagreement this
note used to flag no longer exists.

All eleven run every time this script is invoked directly — see
`marketplace-registration.md` for the correction to the "runs everything except
`check_versions`" claim, which is true only of `_verify/smoke.sh`'s internal
fast-path helper (`_verify/smoke.sh:64-72`, unchanged, still covering the same
**eight** functions it always did — now eight of eleven, and missing
`check_self_claims` and `check_crew_ignore_policy` in addition to
`check_versions`), not of this script.

`check_versions` (`scripts/check-marketplace.py:369-402`, moved from `:298-328`)
is skipped entirely, with a printed note, outside a git checkout (`:375-377`) or
when `marketplace.json` has no commit history (`:380-382`). It also changed
behaviourally since the previous anchor: `357338cb` (#144) added a first-parent
history walk alongside the full one (`:379`, `:385`) and `bump_candidates`
(`:334-368`, new) to try version-bump candidates from both, because the
single-parent walk went blind across a merge commit.

## `scripts/_test/crew-ignore-policy.py` — new sabotage suite, not yet wired locally

**DERIVED, new at this anchor.** `check_crew_ignore_policy`
(`scripts/check-marketplace.py:727-889`) is the newest of the eleven checks
`main()` runs; its own sabotage suite,
`scripts/_test/crew-ignore-policy.py` (755 lines), asserts it three ways rather
than one - counted by AST, not by trusting a header comment: **29** entries in
`CASES` (`:182`), **4** in `PROBE_CASES` (`:470`), and one more result from
`no_other_suite_contradicts_us()` (`:498`, scored in `main()` at `:562-570`).
29 + 4 + 1 = **34**, matching the suite's own summary line
(`crew-ignore-policy: {passed} passed, {failed} failed`, `:602`).

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
wired into CI (`.github/workflows/marketplace.yml:41-42`) but **not** into
`.crew/verify.json`'s `scripts/**` rule (`.crew/verify.json:52-59`), which
matches this file by path but does not run it - see "What `.crew/verify.json`
actually maps" below. It is also not one of `_verify/smoke.sh`'s eight covered
functions, since `check_crew_ignore_policy` itself is not.

`.crew/codemap/` is explicitly out of the check's scope
(`scripts/check-marketplace.py:750-753`): a generated map restating the policy
would be fixed by regenerating it, not by editing it, so this note's own
citations of the policy elsewhere (see `CLAUDE.md`'s `## Memory` section) are
never something this gate checks.

## What `.crew/verify.json` actually maps

**DERIVED, from a full read - the first this note could do, now that the file is
tracked.** 21 `rules` (via `json.load`, not a `grep -c` estimate), each an
ordered `paths`/`run` pair, plus a `default` and an `unmapped: "fail"`. One rule
also carries a required review `agents` entry. The file's own `anchor`
(`.crew/verify.json:3`) is `"repo@5238be3d"`, 22 commits behind this note's
`0a9d8937` - so its `why` fields, which state timings and rationales as of
2026-09-13, predate `check_self_claims` and `check_crew_ignore_policy` existing
in `check-marketplace.py` at all. That does not break the rules that invoke
`check-marketplace.py` wholesale (both new checks still run wherever those rules
fire); it does mean nothing in the file's own prose explains either. Notable
rules, relevant to subsystems covered elsewhere in this codemap:

- `.claude-plugin/marketplace.json`, `**/pyproject.toml`, `plugin/**`,
  `skills/**` → `python3 scripts/check-marketplace.py` (`.crew/verify.json:32-36`)
  — the full gate, including version drift, on the broadest glob in the file.
  Its `why` (`:36`) calls this "the ONLY check that catches a content change
  shipped with no version bump" and cites main red from `12e43eee` to
  `5238be3d` on exactly that defect. This is also the catch-all the file's own
  `_note` warns about (`:12-15`): because the glob is this broad, `unmapped`
  rarely fires, which is a fact about coverage breadth, not proof every new
  check gets noticed.
- `plugin/PLUGINS.md`, `plugin/README.md`, `plugin/*/README.md`, `**/SKILL.md`,
  both install scripts, `plugin/localgpu/**` → `bash _verify/smoke.sh`
  (`.crew/verify.json:38-42`) — 7s for ten registration invariants per its
  `why`, sabotage-proven by setting crew's `marketplace.json` version to `9.9.9`
  and confirming exit 1.
- `scripts/**` → seven commands run together (`.crew/verify.json:52-59`):
  `check-marketplace.py`, `self-claims.py`, `version-drift.py`,
  `sync-updates.py --check`, `menu-groups.sh`, `check-powershell.sh`, and
  `bash -n install-prerequisites.sh`. **This rule matches
  `scripts/_test/crew-ignore-policy.py` by path but does not run it** - the
  34-case sabotage suite for the newest checker is not in this list, though
  `check-marketplace.py` (which contains the checker itself) is. CI
  (`.github/workflows/marketplace.yml:41-42`) does run
  `crew-ignore-policy.py` directly; locally, editing that suite and running only
  the matched rule would not exercise the change.
- The hooks-gate suite → `python3 -m pytest
  plugin/crew/tests/test_verify_gate_baseline.py ... -q`
  (`.crew/verify.json:62-70`) — 29s, sabotage-proven by reverting the Stop
  gate's baseline to the original `git diff --name-only HEAD` bug. **This rule
  carries no `agents` key.** An earlier version of this note said it did,
  requiring a `security` reviewer, "the only rule in the file carrying an
  `agents` key" - that was true of an older shape of this file and is false of
  the one read here. The one rule that carries `agents`
  (`.crew/verify.json:130`, on the `**/*.ps1`/`**/*.psm1` rule) names
  `powershell-security-hardening`, not `security`, and has nothing to do with
  hooks.
- `plugin/crew/tests/conftest.py`, `crew_fixtures.py`, `context.py`,
  `sabotage.py` → `python3 -m pytest plugin/crew/tests/ -q`
  (`.crew/verify.json:112-115`) — 245s, deliberately over the ~3-minute
  guidance, because these four files are imported by every test module and a
  change here can make the whole suite vacuous while every module still reports
  green. `plugin/crew/tests` and `sabotage.py` are still **not** run by
  `_verify/run-all.sh` (confirmed below, unchanged), so this is the *only*
  local rule that reaches them - and unlike at the previous anchor, that is now
  a fact about this file's actual mapping, not an inference from its absent
  `why` text.
- `mcp-servers/**` → `npm --prefix mcp-servers test`
  (`.crew/verify.json:142-144`) — 21s, with a stated precondition (`npm
  --prefix mcp-servers install` must have run once) and a warning to judge it by
  exit code, since a workspace script prints a later package's PASS after an
  earlier package's failure.
- `.github/workflows/**` → `run: []`, deliberately (`.crew/verify.json:163-165`)
  — nothing on this machine validates workflow YAML; GitHub is the only
  validator.
- `graphify-out/**`, `.crew/codemap/**`, `.crew/**`, `.serena/**` and several
  more → `run: []`, deliberately (`.crew/verify.json:167-171`) — `graphify-out/`
  is regenerated by a post-commit hook and must never be hand-edited;
  `.crew/codemap/` is prose re-checked by `/crew:onboard`, not by a gate. Listed
  explicitly so `unmapped: fail` still fires on anything genuinely new.

## `_verify/run-all.sh` — what the deep suite actually runs

**DERIVED, re-read line by line in full at this anchor.** The file is
byte-identical to the previous anchor (`git diff --stat` empty), which is
exactly why this matters: **most of the citations below were already wrong
before this pass**, not rotted by a code change. They were carried from an
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

**This refresh executed no suite.** Everything above is read from source.

Retained for reference, as a claim about the 3167721f-era tree rather than about
HEAD: that task ran `python scripts/check-marketplace.py` →
`marketplace: 25 skills, 4 plugins`, `all checks passed`, and
`bash _verify/smoke.sh` → 10 passed, 0 failed. Neither result has been
reproduced at 1f97e51c, and both should be treated as unverified here.

`_verify/run-all.sh` was not run then and has not been run now — it drives
pytest suites against a bootstrapped localgpu venv and a real PowerShell, and
its own header estimates minutes, not seconds (`_verify/run-all.sh:3`).
## Entry points

- `plugin/crew/tests/test_crew_config.py:1488` (moved from `:1483`) — `test_resolve_config_inherits_a_global_through_the_init_template`, the END-TO-END null-shadow test. The helper-level tests above it pass with the call site deleted from `resolve_config`; this one does not. That gap was found by sabotage, not by review.
- `plugin/crew/tests/test_crew_state.py:1016` (moved from `:968`) — `test_a_backslash_in_a_branch_name_is_flattened_too`, which catches the `[\/]+` character class that matched `/` alone.
- `plugin/crew/tests/test_crew_state.py:1050` (moved from `:1002`) — `test_two_repos_with_the_same_basename_do_not_share_a_leaf`, the cross-repo worktree collision the security review raised.
- `scripts/check-marketplace.py:727` — `check_crew_ignore_policy`, new at this anchor: the `.crew/` ignore-policy gate, sabotage-tested by `scripts/_test/crew-ignore-policy.py` (see below).

## Owns data

- `.work/PROMOTIONS.md` — machine-local (`.gitignore:273`, moved from `:268` — ignores `.work/`), so it is THIS machine's promotion history and never travels to another clone. `promote-gate.sh` reads it; `verify-gate.sh` refuses to end a turn after a deploy that wrote no row.

## Calls out to

- `pwsh` from `plugin/crew/tests/test_verify_gate_bash_resolver.py`, which is where two tests fail on this machine: they replace `PATH` and `SystemRoot` with fake trees and pwsh cannot then initialise (`Win32Exception 126`). Environmental and pre-existing — confirmed identical at `1f97e51c`.


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
