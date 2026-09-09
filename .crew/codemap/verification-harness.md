anchor: useful-claude-add-ons@1f97e51c

# Verification harness

Three *scripted* layers, fastest to slowest: `_verify/smoke.sh` (seconds), the
direct `scripts/check-marketplace.py` invocation (all checks, including the slow
one — see `marketplace-registration.md`), and `_verify/run-all.sh` (minutes).

**JUDGEMENT, corrected at this anchor:** this note previously said
`.crew/verify.json` "maps a changed path to which of these to run". That
overstates it, and in the direction that hides work — it implies the three
scripts are the whole harness. **DERIVED:** of the 15 rules in
`.crew/verify.json:5-168`, six name commands that are *not* one of those three
scripts: `python -m pytest plugin/crew/tests plugin/gizmoduck/scripts/_test -q`
(`:12`), `bash scripts/_test/menu-groups.sh` (`:54`),
`bash plugin/crew/hooks/scripts/_test/run-tests.sh` (`:64`),
`npm --prefix mcp-servers test` (`:76`), `python3 -m pytest plugin/crew/tests -q`
plus `python3 plugin/crew/tests/sabotage.py` (`:101-102`), and `ruff check .`
(`:111`, `:137`). The accurate statement is: `.crew/verify.json` maps a changed
path to the commands that verify it, and those commands are *usually* one of the
three scripts.

## Re-anchor provenance — 3167721f -> 1f97e51c, 2026-09-06

The per-path check was performed by the dispatching session, not repeated here.
It returned two moved paths: `.claude-plugin/marketplace.json` and
`_verify/run-all.sh`.

**What was re-read, in full, at this anchor:** `_verify/smoke.sh` (all 362
lines), `_verify/run-all.sh` (all 150 lines), `.crew/verify.json` (all 200
lines), `scripts/check-marketplace.py:166-191`, `:263-277`, `:298-328`,
`:377-405`, and the function index of the whole file. `git diff` of both moved
paths across the anchor range.

**Every `path:line` in this note was re-resolved by reading the line, not by
grep.** Six citations were wrong at the previous anchor and are corrected below;
`_verify/smoke.sh` did not move in the anchor range, so those six were already
wrong when they were written, not rotted by a code change. Four of them resolved
to *plausible* neighbouring lines inside the right function — the failure mode
that survives a citation check and does not survive reading.

**The one claim the moved files could have invalidated:**
`.claude-plugin/marketplace.json` changed only version numbers and two
descriptions (`git diff 3167721f..1f97e51c -- .claude-plugin/marketplace.json`),
so `25 skills, 4 plugins` still holds — **DERIVED**, re-counted directly from
`.claude-plugin/marketplace.json` by the same rule
`scripts/check-marketplace.py:396-397` uses (`source` starting `./skills/`):
25 skills, 4 plugins, 29 entries. `check-marketplace.py` was **not executed**
at this anchor (~163s, and this was a read-only refresh).

**`.crew/verify.json` is gitignored and untracked** (`git ls-files
--error-unmatch` reports it as unknown to git; `.crew/verify.json:104` says so
too). So `git diff --name-only <anchor>..HEAD` can *never* list it, and the
per-path check can never show it moving. Any claim about it has to be re-read
from disk every time. Its own `anchor:` field reads
`useful-claude-add-ons@1c899d7` (`.crew/verify.json:4`), which is behind this
note's — that is a fact about that file's bookkeeping, not evidence about the
rules.

**Explicit unknowns at this anchor** — recorded rather than resolved into a
confident value:

- No suite was executed. Every behavioural claim below is read from source. A
  claim that a check *passes* is nowhere in this note any more; the previous
  version carried run results and they are now marked as history (see the last
  section).
- `.crew/verify.json`'s stated *rationales* (its `why` fields) make historical
  claims — "until 2026-09-05 nothing ran cli/_test", "the wedge was chocolatey
  jq's handle leak" — that cannot be checked by reading today's tree. They are
  quoted here as what the file says, never asserted as fact.

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

**Corrected at this anchor.** Five of these rows moved:

- Row 4 cited `_verify/smoke.sh:65` for "calls both `check_catalogs` and
  `check_docs`". Line 65 is `groups = {`. The `"catalogs"` lambda is at `:69`.
  The row's *description* was also wrong: it said the group checks "catalog rows
  in all three READMEs", which describes `check_docs`
  (`scripts/check-marketplace.py:263-277`) only. `check_catalogs`
  (`scripts/check-marketplace.py:166-191`) reads `SH` and `PS1` and compares
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

**DERIVED.** `main()` is `scripts/check-marketplace.py:377-405`. Its check calls
are `:386-394`, in this order: `check_registration`, `check_skill_manifests`,
`check_plugin_manifests`, `check_catalogs`, `check_menu_parity`,
`check_group_parity`, `check_docs`, `check_hook_commands`, `check_versions`.

That is **nine** functions. This note previously said "All eight run every time"
while listing nine names — an internal contradiction, and the same figure
appears in `marketplace-registration.md`, which says `main()` "calls all eight
check functions in order, **including** `check_versions`". Counting `:386-394`
gives nine. Corrected here; **not** corrected in `marketplace-registration.md`,
which is outside this note's scope — flag it to whoever refreshes that file.

All nine run every time this script is invoked directly — see
`marketplace-registration.md` for the correction to the "runs everything except
`check_versions`" claim, which is true only of `_verify/smoke.sh`'s internal
fast-path helper (`_verify/smoke.sh:64-72`), not of this script.

`check_versions` (`scripts/check-marketplace.py:298-328`) is skipped entirely,
with a printed note, outside a git checkout (`:304-306`) or when
`marketplace.json` has no commit history (`:308-310`). The previous citation
gave the function as `:298-326` and the branches as "306-311"; the body runs to
`:328` and the two `return` statements are at `:306` and `:310`.

## `.crew/verify.json` — the mechanism, path to command

**DERIVED**, read directly at this anchor: **15** rules (`grep -c '"paths"'`
over the file, cross-checked by reading `:5-168`), mapping a glob of changed
paths to shell commands, plus for one rule a required review agent. The previous
version of this note said 13; the file is untracked, so nothing but re-reading
it can catch that drifting. Notable ones relevant to subsystems covered
elsewhere in this codemap:

- `plugin/localgpu/cli/**`, `plugin/localgpu/mcp/**` → `bash _verify/run-all.sh`
  (`.crew/verify.json:16-25`) — its `why` field records that until 2026-09-05
  neither this file nor `_verify/smoke.sh` ran `cli/_test`'s pytest suite at
  all; `run-all.sh` now covers both `cli/_test` (`_verify/run-all.sh:91-95`) and
  `mcp/_test` (`:72-76`).
- `.claude-plugin/marketplace.json`, `skills/**`, `plugin/**` →
  `bash _verify/smoke.sh` (`.crew/verify.json:26-36`) — the
  one-script-covers-everything registration gate. **Caveat, and it is the whole
  point of the `marketplace-registration.md` correction:** smoke.sh does *not*
  run `check_versions`, so this rule does not cover version drift despite its
  `why` field claiming "and version drift (files changed since that version was
  last set)" (`.crew/verify.json:35`). Version drift is reached only through
  `_verify/run-all.sh:46`, which invokes `check-marketplace.py` directly.
- `plugin/*/hooks/**` → `bash _verify/smoke.sh` **and**
  `bash plugin/crew/hooks/scripts/_test/run-tests.sh`, with a required
  `security` review agent (`.crew/verify.json:58-70`) — **DERIVED:** the only
  rule in the file carrying an `agents` key (one match for `"agents"` in the
  whole file), because a hook runs unconditionally and this is the suite the
  file describes as "the only thing that proves a blocking guard still BLOCKS".
- `scripts/install-prerequisites.sh`, `.ps1` → `bash _verify/smoke.sh` **and**
  `bash scripts/_test/menu-groups.sh` (`.crew/verify.json:47-57`) — the
  matched-pair proof plus the sub-picker / group-flag behaviour smoke.sh's
  check 5 does not reach.
- `mcp-servers/**` → `npm --prefix mcp-servers test` (`.crew/verify.json:71-79`)
  — the TypeScript monorepo's own vitest/`node --test` suites. As of 4e2bfb78
  that command is gated on a freshness check: `mcp-servers/package.json:10-11`
  runs `check-dist-fresh.test.mjs` before the workspace suites, and each package
  carries `"pretest": "node ../../scripts/check-dist-fresh.mjs"` (e.g.
  `mcp-servers/packages/core/package.json:26`), so a per-package `npm test`
  against a stale `dist/` refuses rather than testing the previous build.

## `_verify/run-all.sh` — what the deep suite actually runs

**DERIVED**, re-read in full at this anchor because this file moved in the
anchor range. In order:

1. `check-marketplace.py`, full gate including version drift (`:46`).
2. `scripts/_test/menu-groups.sh` (`:49-50`).
3. localgpu `mcp/_test` under the install venv (`:72-76`) — skipped when no venv.
4. localgpu `cli/_test` under the same venv (`:91-95`) — skipped when no venv.
5. **New since the previous anchor** (added by `b7b7101d`, not by 4e2bfb78):
   gizmoduck's `tickets` confirmation-gate suite, `pytest
   plugin/gizmoduck/scripts/_test/` (`_verify/run-all.sh:102-107`), gated on
   `import pytest` succeeding for the resolved interpreter rather than on a
   venv. Its comment states nothing ran that suite before.
6. `crew-setup` round-trip (`:110-111`).
7. Every PowerShell artifact, tracked then untracked (`:115-128`), with the
   untracked loop fed by `< <(...)` rather than a pipe so a `FAIL` recorded
   inside it reaches the parent shell (`:117-121`).
8. `plugin/crew/hooks/scripts/_test/run-tests.sh`, 900s budget, **run by
   default** (`:141`). `--with-hooks` is parsed (`:17`) but is a documented
   no-op (`:140`).
9. `scripts/_test/drift-detection.sh` — permanently `skip`ped (`:144-145`),
   never automatic, because it drives the real Claude Code CLI.

**Not run by `run-all.sh`, and worth knowing:** `plugin/crew/tests` and
`plugin/crew/tests/sabotage.py`. `.crew/verify.json:96-105` maps them, and its
own `why` says the durable wiring "belongs in `_verify/run-all.sh` … both are
off this round's surface". Reading `_verify/run-all.sh` at this anchor confirms
that wiring still has not landed: neither command appears in the file. Since
`.crew/verify.json` is gitignored, on any other clone or in CI nothing runs
them.

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
