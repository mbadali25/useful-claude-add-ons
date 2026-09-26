anchor: useful-claude-add-ons@8ebbdedc
verified: 2026-09-26
paths: plugin/crew/**, _verify/smoke.sh, scripts/check-marketplace.py

**Re-derive provenance.** Full re-derivation, not a re-verify. The previous
anchor (`5d1fc5fd`) predates crew 1.0's role/PM-removal rewrite
(`c3bd8dfd`, "crew 1.0 (T2): remove the PM agent, pulse, journal and retired
roles") and the harness-pricing pass folded into `6c497a14`
("crew 1.0.25: lifecycle redesign, 4-role roster, Windows burn-in and native
PowerShell fixes"). Per the assigning task's own per-path check, most of this
note's citations moved. Every claim below was re-read directly against the
file it cites at `6c497a14`, by line number taken fresh (`grep -n`/`json.load`,
never an offset). One previously-cited file is confirmed deleted:
`plugin/crew/tests/test_pm_brief_platform_sync_python_resolver.py` (removed in
`6c497a14` itself, per `git log --diff-filter=D`) — every claim this note made
about it is dropped, not carried forward. No other previously-cited path was
found missing from the working tree at this anchor (checked by existence,
every citation this note now makes). `.crew/verify.json`'s own `anchor` field
(`.crew/verify.json:3`) still reads `"repo@5238be3d"`, unmoved since at least
the previous pass — this note's anchor is the codemap's own, not that field's,
and the gap between them is a fact this note records, not a bug in the note.
Two commands were actually run this pass, both read-only and against fixtures
or tracked files only: `python3 scripts/check-marketplace.py` (`marketplace: 34
skills, 5 plugins`, `all checks passed`, rc 0) and `python3
scripts/_test/instruction-budgets.py` (`61 passed, 0 failed`) and `python3
scripts/check_instructions.py` (`instruction budgets: all checks passed`, rc
0). No suite under `plugin/crew/tests/` was executed this pass; every claim
about it below is read from source or from `.crew/verify.json`'s own recorded
measurements, named as such.

# Verification harness

Three *scripted* layers, fastest to slowest: `_verify/smoke.sh` (seconds), a
direct `python3 scripts/check-marketplace.py` invocation (every check,
including the slow version-drift walk `_verify/smoke.sh` skips), and
`_verify/run-all.sh` (minutes). A fourth, narrower script exists alongside
them and is wired into CI but not into the local Stop gate: see
"`scripts/check_instructions.py`" below.

## `.crew/verify.json` — 25 rules, up from 24

**DERIVED, read in full via `json.load` at this anchor.** 285 lines, **26**
rules (25 at `8ebbdedc` and at T-0006's `2bb92f32`, 24 at `c35edda5`, 23 at `f2bb919b`, 22 at
`6c497a14`, 21 at `5d1fc5fd`) plus a `default` (`["bash _verify/smoke.sh"]`, `:283`) and
`unmapped: "fail"` (`:284`). Rule 10 (T-0026, inserted mid-list, so every later rule's index is
one higher than at `c35edda5`), rule 23 (#228), rule 24 (T-0008) and rule 25 (T-0006, appended
last so no earlier index moved) are the only additions since `6c497a14`; see below. The rule set was restructured, not
just grown: the broad `plugin/crew/hooks/**` / `plugin/crew/tests/**` shape
this note previously described is gone, replaced by per-subsystem rules that
name a handful of test files each — `crew_guards.py` (rule 5), `crew_config.py`
(rule 6), the `crew_state.py` cluster (rule 7, eleven test modules), the
whole-suite rule (rule 8), `crew_upgrade.py` (rule 9), `crew_ticket.py`'s approval digest
(rule 10) and command/agent/skill frontmatter (rule 11) are each their own entry now, where the previous anchor
folded several of these together. Every rule now carries a `"reach": "local"`
field, unchanged in shape from the previous anchor.

Notable rules, re-read directly:

- **Rule 0** (`paths`: `.claude-plugin/marketplace.json`, `plugin/**`,
  `skills/**`, …) → `python3 scripts/check-marketplace.py`. `why` still calls
  this "the ONLY check that catches a content change shipped with no version
  bump" and prices it 8-9s.
- **Rule 4** — the verify-gate/promote-gate/role-write-guard cluster — now
  runs nine named pytest files directly (`test_verify_gate_baseline.py`,
  `test_verify_gate_bash_resolver.py`, `test_verify_gate_lock.py`,
  `test_verify_gate_lock_sh.py`, `test_verify_gate_lock_concurrent.py`,
  `test_promote_gate_fails_closed.py`, `test_promote_merge_gate.py`,
  `test_gates_powershell.py`, `test_role_write_guard.py`), priced at 96s. Its
  `why` field is the longest in the file by a wide margin — an eight-round
  review log on `role-write-guard.sh`/`.ps1` and `role_write_guard.py`,
  ending "check-marketplace.py reports exactly one finding on this branch …
  version not bumped … confirmed by team-lead as the known squash-merge
  artefact." Read as history of that review series, not as a claim about
  HEAD's current version state (re-run separately above and clean).
- **Rule 5**, new since the previous anchor's account: `crew_guards.py` +
  `test_guard*.py` → `python3 -m pytest plugin/crew/tests/test_guards.py
  plugin/crew/tests/test_malformed_production_never_permits.py -q`. Its own
  `why` documents that the *command guard* was removed in 0.19.52 along with
  `test_guard_bypasses.py`, `test_guard_powershell.py` and
  `test_guard_command_spelling.py` — `crew_guards.py` itself survives because
  `guards.mergeGate` and `change.requireForProduction` still resolve through
  it. This is the second confirmed deletion this pass found, though it
  predates `5d1fc5fd` and was never previously cited by this note, so it is
  new information here, not a correction.
- **Rule 8**, the whole-suite rule (`plugin/crew/tests/conftest.py`,
  `crew_fixtures.py`, `context.py`, `sabotage.py` → `python3 -m pytest
  plugin/crew/tests/ -q`) — priced **377s**, re-measured 2026-09-24 ("crew 1.0
  F4") from an intermediate, unannotated 1928s figure the file's own `_note`
  explicitly says was superseded rather than reconciled (no host/load record,
  so not comparable). The 377s figure carries a full host record (Linux, 20
  logical CPUs, `uptime` 1.01/1.63/1.54, 64% CPU utilisation) and a clean
  result: "2814 passed, 202 skipped, 827 deselected, exit 0." **This is the
  rule the `_note` at `.crew/verify.json:39-49` names as the origin of
  "--all-only": there is no separate schema field for it** — a rule priced
  above `verify.stopBudgetSeconds` (default 60) is classified CHRONIC by
  `verify-gate.sh`'s own budget accounting and deferred every Stop turn until
  `/crew:verify --all` runs it. 377s is ~6x that budget on its own.
- **Rule 10**, new at `8ebbdedc` (`.crew/verify.json:167-172`, T-0026): `paths`
  `plugin/crew/hooks/scripts/crew_ticket.py` and `plugin/crew/tests/test_approval_digest.py`
  → `python3 -m pytest plugin/crew/tests/test_approval_digest.py
  plugin/crew/tests/test_crew_ticket.py -q`, priced 20s. Its `why` says the scope guard and the
  completion audit act on nothing but `crew_ticket.py`'s approval answer, so a status-value
  normalisation one byte too wide lets a scope or risk change through unapproved, and names the
  `APPROVAL DIGEST` entries in `plugin/crew/tests/sabotage_scope.py` as the mutations proving
  the tests can fail. Both paths also match rule 0 and rule 14 (`**/*.py`) by `fnmatch`.
- **Rule 12**, `plugin/crew/skills/crew-diagrams/**` → `bash
  plugin/crew/skills/crew-diagrams/scripts/_test/render.sh`, priced 8s. Its
  `why` records that this rule's exit-77 SKIP convention was **ported from PR
  #212** (origin/item8-ps1-parity): the suite used to exit 0 (a silent pass)
  when `mmdc` was absent, which the Stop gate then recorded as a rule that
  *passed* rather than one that never ran. Verified both paths on the
  authoring host: 12 passed / 0 failed with `mmdc` on PATH (7.6s), `TOOL
  MISSING` on stderr and exit 77 with PATH stripped to `/usr/bin:/bin`. No CI
  workflow runs this suite — CI runners typically carry no `mmdc` — so this
  Stop-gate rule is where it actually executes, on whichever machine happens
  to have the tool.
- **Rules 13-14**, the `.ps1`/`.psm1` lint and the `ruff`/`pylint` pair, are
  unchanged in shape from the previous anchor: both wrap their command in an
  `sh -c` tool-presence probe exiting 77 rather than 1 when the interpreter or
  module is absent, and rule 13 is the one rule carrying an `"agents"` key
  (`["powershell-security-hardening"]`).
- **Rules 21-22**, the two `run: []` catch-alls (`.github/workflows/**`
  deliberately unchecked; `graphify-out/**`, `.crew/codemap/**`, `.crew/**`,
  `.serena/**` and others deliberately unchecked) are unchanged. Both declare
  `"reach": "local"` on the reading that an empty `run` cannot reach off this
  machine — `verify_record.scan_reach([])` already returns that.
- **Rule 23**, new at `f2bb919b` (`.crew/verify.json:251`, #228): `paths`
  `.claude/rules/**` and `.crew/codemap/**` → `python3
  plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check`, priced
  1s. Its `why` calls it a SYNC check between the two artifacts, not a
  correctness check on the codemap prose: it passes whenever the rules match
  the codemap, even a stale codemap. **`.crew/codemap/**` is now in two rules**
  - rule 22's deliberately-unchecked `run: []` and rule 23 - and the gate runs
  every matched rule (`verify-gate.sh:920`, `rule_order`, "matched rule
  indices"), so rule 22's "DELIBERATELY UNCHECKED" `why` no longer describes
  what happens to a codemap edit: any `.crew/codemap/` change without a
  regenerated `.claude/rules/` now fails the Stop gate.
- **Rule 24**, new at `adf8d1dd` (`.crew/verify.json:252-268`, T-0008): `paths`
  `plugin/crew/hooks/scripts/crew_refresh_check.py`, its three test files,
  `plugin/crew/tests/sabotage_refresh.py`, and `plugin/crew/commands/implement.md`
  / `done.md`, and since T-0008's review round 3 `scope_guard.py`,
  `completion_audit.py`, `crew_freshness.py` and `scope_base.py` with
  `test_scope_guard.py`, `test_completion_audit.py` and `test_scope_base.py`
  → `python3 -m pytest` over those six test files, priced 32s (its `why`,
  `:268`, records 31.8s measured on the authoring host — a claim read, not
  re-timed here). `crew_freshness.py` is on rule 7 too. At the default 60s
  Stop budget rule 24 (32s) plus rule 14 (38s) no longer fit together, so a
  `.py` edit on these paths has one of them deferred at Stop (JUDGEMENT,
  from the two `seconds` values, not observed). A test,
  `test_every_module_the_refresh_allowance_touches_runs_a_pytest_rule` in
  `plugin/crew/tests/test_refresh_check.py`, fails if any of the five
  modules stops matching a pytest rule. The check can refuse `/crew:done`, so its `why`
  names must-refuse and must-allow cases, and says `implement.md`/`done.md` are
  mapped here because these tests carry their ordering checks. Its mutations
  live in `plugin/crew/tests/sabotage_refresh.py` (`REFRESH_MUTATIONS`, `:51`),
  imported by `plugin/crew/tests/sabotage.py:75` and appended to `MUTATIONS` at
  `:3046` — the same sibling-module pattern as the other `sabotage_*.py`
  lists, because `sabotage.py` sits at `.pylintrc`'s max-module-lines. Every
  rule-24 path also matches rule 0 and either rule 14 (the `.py` files) or
  rule 11 (the two commands), by `fnmatch`, the primitive `matches()` uses
  (`verify-gate.sh:869-876`) — so an edit there runs more than rule 24.
- **Rule 25**, new at `6d35ef8c` (`.crew/verify.json:270-280`, T-0006; rule 24 on its branch,
  before T-0026's rule 10 moved every later index up by one): `paths`
  `crew_resume.py`, `crew_context.py`, both `handoff-write` flavours,
  `test_crew_resume.py`, `test_crew_resume_hook.py` and `sabotage_resume.py` →
  `python3 -m pytest` over the two resume test files plus `test_auto_cycle.py`, priced 89s (its
  `why` records 89s, 348 passed / 12 skipped / 68 deselected after review round 3, under load;
  60s after round 2). Its
  mutations live in `plugin/crew/tests/sabotage_resume.py` (`RESUME_MUTATIONS`, 44), imported by
  `plugin/crew/tests/sabotage.py:76` and appended to `MUTATIONS` at `:3048`.

**Still unresolved at this anchor:** a declared `seconds` figure is only
overwritten by measurement when the rule carries *no* `seconds` at all
(`plugin/crew/hooks/scripts/verify_record.py`, gated on `if
rule.get("unknown")`) — a stale declared number is otherwise permanent until
someone edits the JSON by hand. This pass did not audit every rule's `seconds`
against a fresh timing; it re-read the file's own `_note` and each `why` field
for what they claim and reports those claims as claims, not as independent
measurements, except where a command was actually re-run above.

## `verify-gate.sh` / `verify-gate.ps1` — the rule runner

**DERIVED, read directly at this anchor.** 1863 lines (`.sh`) / 1956 lines
(`.ps1`, 1917 at `6c497a14`; the +39 is T-0002's three fixes below), both grown
substantially since `5d1fc5fd`. Landmarks
that changed shape or are newly documented here:

- **Bounded stdin, not unbounded.** The Stop hook's JSON payload is read with
  `IFS= read -r -t 5 -d ''` (`verify-gate.sh:63-66`) — a *single* read with one
  5-second deadline for the whole operation, not a per-line timeout. The
  comment at `:52-60` explains why that distinction matters: a `while read -t
  5` loop gives each line its own fresh 5s, so a producer that trickles bytes
  slowly enough to keep beating the timeout on every individual read — without
  ever closing the pipe — resets the clock forever and hangs the script
  anyway, the same failure the bound exists to prevent. `[ -t 0 ]` (`:64`)
  skips the read entirely for an interactive terminal.
- **Rule output goes through a temp FILE, never a pipe, with a 1 MiB tail
  cap.** `verify-gate.sh:1600-1696`: `RULE_OUT_FILE=$(mktemp)`, falling back to
  a `.crew/.verify-rule-out.XXXXXX` file if `mktemp` itself fails (`:1600-1603`
  — refusing the rule outright, `RC=1`, only if *neither* location is
  writable, `:1697-1705`). The comment at `:1574-1599` explains the reason: the
  old `$(...)` pipe form only reports EOF once *every* process holding its
  write end has closed it, so a rule that backgrounds something and does not
  itself wait on it (`long-thing &`) hands the write end to the grandchild
  too, and that grandchild holding it open wedges the gate's own shell
  forever — not fixable by an external timeout, since the grandchild, not the
  rule, holds the pipe. A regular-file read has no such property: it returns
  whatever bytes are on disk at the size `stat` reports right now. The size is
  snapshotted the instant the rule's own subshell exits (`:1642-1661`), capped
  at `RULE_OUT_CAP` (env-overridable for tests only, clamped to `1..1048576`,
  `:1663-1682`), and read with `tail -c`, not `head -c` (`:1684-1695`) — a
  failing rule's diagnostic is at the *end* of its output, and the old
  `head -c` form discarded exactly that. `verify-gate.ps1:1655-1789` (through
  its `Remove-Item` cleanup; cited as `:1655-1712` at `6c497a14`) is the
  documented twin: `[System.IO.Path]::GetTempFileName()`, the same `.crew/`
  fallback, a `Length` snapshot instead of a streaming `Get-Content` (which the
  comment at `:1624-1637` says was measured to grow past 1 GiB in five seconds
  against a `sh -c 'yes &'` rule before this fix), and the same 1 MiB cap
  (`:1704-1709`, was `:1691-1696`). **Three fixes landed in this block in crew
  1.0.28 (T-0002, `f2bb919b`)**, each with its own new test file: the bash
  wrapper now copies `CREW_VERIFY_RULE_CMD`/`CREW_VERIFY_RULE_OUT` into shell
  locals and `unset`s both before `eval` (`:1699`, reasoning `:1687-1698`), so
  the rule no longer sees its own source text and capture path in its
  environment (`plugin/crew/tests/test_verify_gate_rule_env_leak.py`); the
  capped tail read seeks from `Begin` by `$size - $readLen` instead of from
  the live `End` (`:1746`, reasoning `:1735-1745`), so a rule still writing
  after the size snapshot cannot move the window; and a 0-byte read is its own
  branch (`:1771`, reasoning `:1760-1770`), because `0..($totalRead - 1)` is
  the descending range `0,-1` in PowerShell, not an empty one
  (`plugin/crew/tests/test_verify_gate_rule_out_tail_read.py`). Neither new
  test file is named in rule 4's `run`; only rule 8's whole suite runs them.
- **Per-rule process-group tracking and kill-on-signal was DESCOPED from crew
  1.0, and it is a documented limitation, not a silent gap.**
  `verify-gate.sh:1493-1502` and `plugin/crew/CONFIG.md:2022-2029` both state
  it: a third registry stage (`_crew_gate_cleanup_rule_pgid`) shipped, then was
  removed after five consecutive review rounds each found the previous
  round's fix one case short (disk fill by an orphan writer, escape on gate
  kill, an unlocked registry, pid/pgid reuse in both p- and g-mode, a
  session-id proof that is not ownership, a leader-exited group — see
  CHANGELOG 1.0.21). What remains is only the isolation the temp-file capture
  above already guarantees; **a rule that backgrounds work and does not wait
  on it is no longer reaped by this gate**, and `CONFIG.md` states that as the
  limitation to design rules around, not as a bug ticket.
- **`crew_py_strict`, not plain `crew_py`, resolves the interpreter that reads
  `.crew/verify.json`.** `verify-gate.sh:737`. The comment at `:723-736`
  records why: plain `crew_py` (`command -v` alone) happily resolves a
  WindowsApps App Execution Alias stub — a real, executable file that prints
  nothing and exits 0 — and the matcher's own empty-output check
  (`:1248-1273`, unchanged in shape from the previous anchor) is the second,
  independent line of defence in case some *other* broken-but-resolvable
  interpreter slips past `crew_py_strict` the same way.
- **`.ps1`'s own stdin guard: `$null |` on every subprocess call.**
  `verify-gate.ps1:1638-1641` and repeated at every `git`/interpreter-probe
  call site (`:452-523`, `:1434`, `:1700`, `:1898`; the last two
  were `:1687`, `:1859` at `6c497a14`) — a closed stdin
  handed to the child, the PowerShell twin of `verify-gate.sh`'s `</dev/null`
  redirect (`:1571-1572`, `:1640`). Without it, a rule or a git call that reads
  stdin parks the whole gate the same way an unclosed pipe does.
  Not `:1907` (the record sync): it pipes `$payloadJson` into
  `verify_record.py sync`, which reads it, so its stdin is the payload,
  not `$null` — a `grep '\$null |'` hit there is the `2>$null |` redirect.
- **`Resolve-CrewBash` refuses rather than invoking a name that would
  re-resolve to the same rejected shim.** `verify-gate.ps1:822-832` (the smoke
  step) and `:1665-1674` (per-rule): when `Resolve-CrewBash` finds no
  natively-launchable candidate, the gate prints "no usable bash resolved …
  refusing rather than invoking a name that would re-resolve to the same
  rejected shim and hang" and fails that step/rule with `rc=1`, through the
  same branch every other rule failure goes through — never a hang with no
  output. `--diagnose-bash` (`:22-30`) prints the path `Resolve-CrewBash` would
  use and exits 0 without touching stdin, `.crew/`, or any check, for exactly
  this debugging need.
- **`--price` is an operator-only escape hatch**, dispatched before the stdin
  read (`verify-gate.sh:5-30`) so a terminal invocation of the flag is never
  blocked on it, and never reachable from the Stop hook itself (`hooks.json`
  invokes this script with no argument or `--all`, never `--price`).

## `scripts/check-marketplace.py` — the direct gate

**DERIVED, re-read at this anchor; `main()` is unchanged in shape from
`5d1fc5fd`.** `main()` (`scripts/check-marketplace.py:1639-1674`) still calls
**sixteen** checks, in the same order, at `:1648-1663`:

`check_registration`, `check_skill_manifests`, `check_plugin_manifests`,
`check_argument_hint_frontmatter`, `check_license_consistency`,
`check_catalogs`, `check_menu_parity`, `check_group_parity`, `check_docs`,
`check_hook_commands`, `check_command_backtick_spans`, `check_versions`,
`check_self_claims`, `check_description_claims`, `check_catalog_claims`,
`check_crew_ignore_policy`.

The one change in this range is internal to `check_self_claims`
(`:673-903`, moved +24 from `5d1fc5fd`'s `:649`): a new claim type,
`crew-markdown-lines`, backed by `count_crew_markdown_lines`
(`:564-586`) — total `splitlines()`-counted lines across every tracked
`plugin/crew/*.md` file. The function returns `None`, not `0`, when
`_tracked_files` cannot answer, and the caller (`:826-840`) reports that as an
explicit UNVERIFIED finding rather than comparing `None` against a real count
— named in its own docstring as the same "unknown collapsing into the
safe-looking value" bug CLAUDE.md's Lessons section calls out
(`CLAUDE.md:233`). See
`marketplace-registration.md` for what this marker checks and where it is
used; this note owns the mechanism, not the claim.

`check_versions` (`:518-551`, unmoved from `5d1fc5fd`) still asks the same
question in the same words: *"has `{source}/` changed since version {version}
was set … but the version was not bumped"* — a history-based check
(`version_set_at`, `:472-480`; `bump_candidates`, `:483-515`, walking both
first-parent and full history) that cannot answer for an uncommitted change,
only for one already in git.

Re-run this pass: `python3 scripts/check-marketplace.py` → `marketplace: 34
skills, 5 plugins`, `all checks passed`, rc 0.

## `scripts/check_instructions.py` — new since the previous anchor, CI-only

**DERIVED, read in full at this anchor.** 721 lines, absent at `5d1fc5fd`.
Gates crew 1.0's instruction-surface budgets file by file, per its own module
docstring (`:1-59`): a 120-line command-file budget
(`COMMAND_MAX_LINES`, `:76`) with `plugin/crew/.budget-allowance.json` as the
only sanctioned exception; no file outside that allowance may grow past its
recorded line count, and no listed ceiling may be *raised* in the same change
that grows the file unless its `reason` is rewritten to an explicit
`"raised: <why>"` string (`RAISED_REASON_RE`, `:97`) — checked against the
allowance file as committed at the merge-base with the default branch, or
`--base <ref>` (`check_allowance_no_silent_raise`, `:334`); frontmatter
presence; generated-file drift (a no-op today — none is committed in this
repo, per its own docstring, but tested against fixtures); a maintained
**stale-name scan**, inverted from the pattern the marketplace checker uses —
`STALE_NAMES` (`:98-106`, eight pre-1.0 names: `qa-reviewer`, `/crew:work`,
`/crew:ticket`, `/crew:pm`, `/crew:roster`, `/crew:scale`, `pm-journal`,
`pm-pulse`) is scanned across **every** `plugin/crew/*.md` file (and
`AGENTS.md`) by default, and `LEGACY_STALE_NAME_FILES` (`:118-...`, a
maintained allowlist of pre-1.0 or held files permitted to mention one) is
what is *exempt* — a new 1.0 file nobody remembers to list is checked, not
silently skipped, which the comment at `:109-117` states was the opposite of
the previous convention's failure mode; broken `${CLAUDE_PLUGIN_ROOT}` /
Markdown-link references; and typed policy IDs — every `guards.<name>`
reference is checked against `crew_guards.ALL_GUARD_NAMES` (`:653`, the one
place those names are declared).

`rel()` (`:195-202`) is POSIX-relative by construction: `os.path.relpath`
joined with the OS separator and then `.replace(os.sep, "/")`, because every
path-keyed lookup this script does (`.budget-allowance.json`'s keys,
`LEGACY_STALE_NAME_FILES`) is committed with `/` — a bare `os.path.relpath` on
Windows would silently miss every lookup rather than raise, per the
function's own docstring.

**Not wired into `.crew/verify.json` or the local Stop gate at all.** Its only
entry point is `.github/workflows/instruction-budgets.yml`, a dedicated
3.11/3.12/3.13 matrix job. Re-run this pass, read-only against this
checkout: `python3 scripts/check_instructions.py` → `instruction budgets: all
checks passed`, rc 0; `python3 scripts/_test/instruction-budgets.py` (its
sabotage suite, which builds throwaway fixtures under a temp dir and never
touches this repo's own files, per its own docstring) → `61 passed, 0
failed`.

## `.github/workflows/instruction-budgets.yml` — the base-sha fix

**DERIVED, read in full.** `fetch-depth: 0` on checkout (`:29`), not the
default shallow clone — `check_allowance_no_silent_raise` needs a
`origin/main` ref to diff `.budget-allowance.json` against, and a 1-commit
shallow checkout gives it neither `origin/main` nor `main`, so it fails
closed with "could not resolve a default branch." On a `push` to `main`
specifically, `--base` is passed explicitly as `github.event.before` (falling
back to `HEAD~1` for a new branch's first push, where `before` is reported as
all zeros) rather than left to the checker's own merge-base default — the
comment at `:40-53` explains why the default would otherwise never fail: by
the time this job's checkout has fetched refs, the push has already advanced
the remote's `main`, so `origin/main` *is* this same commit, its own
merge-base is HEAD itself, and a raised ceiling compares against a copy of
the allowance file that already carries the same raise. `pull_request` runs
are untouched — there `origin/main` genuinely has not merged the PR's commits
yet.

## `.github/workflows/` — seven other workflows, one of them new

**DERIVED.** Eight workflow files total now (`instruction-budgets.yml`,
`marketplace.yml`, `mcp-servers.yml`, `plugin-evals.yml`,
`publish-mcp-servers.yml`, `pylint.yml`, `pytest-crew.yml`,
`shell-suites.yml`). `shell-suites.yml` is new since `5d1fc5fd`, per its own
comment (`:7-11`): before it, no workflow in this repo ran a bash-driven
suite at all — `pytest-crew.yml` runs pytest and cannot collect a `.sh` file
— so `skills/bitbucket/scripts/_test/merge_gate.sh`,
`skills/doc-builder/scripts/_test/checklist.sh`,
`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh` and
`skills/jira-manager/scripts/_test/jq_absence.sh` had never once been
executed by CI despite being committed and green. Each is its own step
deliberately, so a failure names which suite went red rather than collapsing
into one line. `pytest-crew.yml` gained a `crew-shell-matrix` job
(`:112-161`) that runs on **both** `ubuntu-latest` and `windows-latest` — the
`-m slow` full per-shell hook matrix on both, plus a Windows-only run of
crew's default (parity-sample) set, since the `test` job above only runs that
set on Ubuntu.

## Entry points

- `.crew/verify.json:152-157` (rule 8) — the whole-suite pytest rule and its
  377s pricing.
- `.crew/verify.json:167-172` (rule 10) — the T-0026 approval-digest suite.
- `.crew/verify.json:181-185` (rule 12) — the crew-diagrams `render.sh`
  exit-77 port.
- `plugin/crew/hooks/scripts/verify-gate.sh:63-66` — the bounded single-read
  stdin gate.
- `plugin/crew/hooks/scripts/verify-gate.sh:1600-1705` /
  `verify-gate.ps1:1655-1789` — temp-file rule-output capture, 1 MiB tail cap,
  no-pipe fallback refusal.
- `.crew/verify.json:251` (rule 23) — the `.claude/rules/` sync check.
- `.crew/verify.json:270-280` (rule 25) — the T-0006 auto-resume suite;
  `plugin/crew/tests/sabotage.py:76`, `:3048` — `sabotage_resume.py`'s registration.
- `.crew/verify.json:252-268` (rule 24) — the T-0008 refresh-check suite;
  `plugin/crew/tests/sabotage.py:75`, `:3046` — `sabotage_refresh.py`'s
  registration.
- `plugin/crew/hooks/scripts/verify-gate.sh:1493-1502` /
  `plugin/crew/CONFIG.md:2022-2029` — the descoped per-rule process-group kill,
  documented as a standing limitation.
- `plugin/crew/hooks/scripts/verify-gate.ps1:822-832`, `:1665-1674` —
  `Resolve-CrewBash` refusal rather than a re-resolving hang.
- `scripts/check-marketplace.py:1639` — `main()`, sixteen checks.
- `scripts/check-marketplace.py:518` — `check_versions`.
- `scripts/check-marketplace.py:564`, `:673` — `count_crew_markdown_lines`,
  `check_self_claims`.
- `scripts/check_instructions.py:685` — `main()`, nine checks.
- `.github/workflows/instruction-budgets.yml:40-62` — the `github.event.before`
  base-sha fix for a `push` to `main`.

## Owns data

- `.crew/verify.json` — tracked (`!.crew/verify.json` in `.gitignore`, unchanged
  policy), read by `verify-gate.sh`/`.ps1` every Stop turn. Its own `anchor`
  field (`:3`) is stale (`"repo@5238be3d"`) independent of this codemap note's
  own anchor.
- `plugin/crew/.budget-allowance.json` — read by `scripts/check_instructions.py`
  only; the sanctioned exception list to `COMMAND_MAX_LINES`.
- `.crew/.verify-verified-at` — written by `verify-gate.sh`'s `record_verified`
  (`:119-123`) on every all-pass turn; absent in a fresh checkout, as expected
  of a machine-local marker.

## Calls out to

- `pwsh` — resolved by absolute path first (`.crew/verify.json`'s rule 13 `sh
  -c` probe list), never a bare `pwsh`, per CLAUDE.md's landmine about Git
  Bash's PATH.
- `bash` on Windows — `Resolve-CrewBash` in `verify-gate.ps1`, refusing rather
  than re-resolving on failure (above).
- `ruff` / `pylint` / `npm` / `mmdc` — each behind a tool-presence probe that
  exits 77 (this repo's SKIP convention) rather than failing when the tool is
  absent.

## Unverified at this anchor

- No `plugin/crew/tests/` suite was executed this pass. Every claim about
  test counts, pass/fail totals, or timing inside `.crew/verify.json`'s `why`
  fields (the 377s whole-suite figure, the role-write-guard review-round
  history in rule 4) is read from that file or from `CHANGELOG`/`TODO.md`
  cross-references, not independently re-measured here.
- `.crew/verify.json`'s per-rule `seconds` values were read, not re-timed,
  except where a command was actually re-run above (`check-marketplace.py`,
  `check_instructions.py`, `instruction-budgets.py`).
- `_verify/smoke.sh` and `_verify/run-all.sh` are confirmed byte-identical to
  `5d1fc5fd` (`git diff --stat` empty for both), so their citations in the
  previous version of this note are closed by that result rather than
  re-read line by line this pass. Their own content was spot-checked (header,
  `check`/`check_optional` line positions) and matches.
- `plugin/crew/tests/test_verify_gate_bash_resolver.py`'s Windows-only failure
  mode this note once carried ("two tests fail on this machine … pwsh cannot
  then initialise") was not reproduced at this anchor either — this pass also
  ran on Linux and ran no pytest. Not restated as current; dropped rather than
  carried forward unread.
- `scripts/_test/crew-ignore-policy.py`, `scripts/_test/self-claims.py`,
  `scripts/_test/menu-groups.sh`, `scripts/_test/check-powershell.sh` and
  `scripts/_test/drift-detection.sh` were confirmed to exist and unchanged
  since `5d1fc5fd` (`git diff --stat` empty for each) but were not executed
  this pass.
- Whether any other rule besides `test_pm_brief_platform_sync_python_resolver.py`
  was silently dropped from `.crew/verify.json`'s `paths` lists during the
  crew 1.0 restructuring (as opposed to renamed/consolidated) was not traced
  commit by commit — only the current file's shape was read.

## Re-anchor provenance - `6c497a14` -> `f2bb919b`, 2026-09-25 (T-0015)

`git diff --name-only 6c497a14 f2bb919b -- <the 31 tracked paths this note cites>` returns
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `TODO.md` and
`plugin/crew/hooks/scripts/verify-gate.ps1`; the bare `crew_fixtures.py` (rule 8's `paths`) also
changed. `verify-gate.sh`, `_verify/*`, `scripts/check-marketplace.py`,
`scripts/check_instructions.py` and the CI workflows did not, so their citations stand unread.

- `.crew/verify.json` - one rule appended (`:243`); every earlier line keeps its number, so
  `:3`, `:39-49`, `:69-78`, `:151-156` and `:173-178` stand (re-read); `default`/`unmapped` moved
  `:245`/`:246` -> `:246`/`:247`. Rule count and the rule-21/22 overlap corrected above.
- `verify-gate.ps1` - three hunks, all inside the rule-output block (`:1686`, `:1721`, `:1736` at
  `6c497a14`). Every citation before `:1686` is unmoved (`:22-30`, `:452-523`, `:822-832`, `:1434`,
  `:1624-1641`, `:1665-1674`, each re-read); the ones after it were re-taken by content and
  corrected above.
- `crew_fixtures.py` - +219 lines of new fixture helpers; this note cites it only as a rule 8
  path, which it still is.
- `.claude-plugin/marketplace.json` - crew's `version` only (`:218`); cited here as a rule 0 path.
- `TODO.md` - cited only as a cross-reference in Unverified.

Commands run at this pass: `python3 scripts/check-marketplace.py` (`marketplace: 34 skills, 5
plugins`, `all checks passed`). The two new verify-gate test files were not executed; they
exercise the `.ps1` flavour and need `pwsh`.

## Re-anchor provenance - `f2bb919b` -> `adf8d1dd`, 2026-09-25 (T-0008)

Re-verified per-path from `f2bb919b` to `adf8d1dd` for T-0008. `git diff --name-only f2bb919b
adf8d1dd -- <the paths this note cites>` returns `.claude-plugin/marketplace.json`,
`.crew/verify.json`, `CHANGELOG.md`, `CLAUDE.md`, `TODO.md`, `plugin/crew/tests/crew_fixtures.py`
and `plugin/crew/tests/sabotage.py`. `verify-gate.sh`/`.ps1`, `plugin/crew/CONFIG.md`,
`_verify/*`, `scripts/check-marketplace.py`, `scripts/check_instructions.py` and the CI workflows
did not change, so their citations stand unread.

- `.crew/verify.json` - rule 23 appended at `:244-253`; every earlier line keeps its number, so
  `:3`, `:39-49`, `:151-156`, `:173-178` and `:243` stand (re-read); `default`/`unmapped` moved
  `:246`/`:247` -> `:256`/`:257`. Rule count and line count re-measured with `json.load`/`wc -l`.
- `plugin/crew/tests/sabotage.py` - `REFRESH_MUTATIONS` registered, plus T-0003's endpoint-lock
  mutations; cited here as a rule 8 path and for that registration.
- `CLAUDE.md` - re-read; the "unknown collapsing" lesson is in its Lessons section, not Memory
  (wrong since before `f2bb919b`), corrected above.
- `.claude-plugin/marketplace.json` - `:218` is still crew's `version`; `crew_fixtures.py` is
  still a rule 8 path; `CHANGELOG.md` still carries the 1.0.21 descoping entry; `TODO.md` is cited
  only as a cross-reference.

No command or suite was executed at this pass; rule 23's suite and `sabotage.py` were not run.

## Re-anchor provenance - `adf8d1dd` -> `8d447a7d`, 2026-09-25 (T-0008 review round 3)

`git diff --name-only adf8d1dd 8d447a7d -- <the paths this note cites>` returns `.crew/verify.json`,
`CHANGELOG.md`, `TODO.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py` and
`plugin/crew/tests/sabotage_refresh.py`. `verify-gate.sh`/`.ps1`, `sabotage.py`, `CLAUDE.md`,
`plugin/crew/CONFIG.md` and `_verify/*` did not change, so their citations stand unread.

- `.crew/verify.json` - one path added to rule 7 (`crew_freshness.py`), so every later line moved
  by one: rule 8 `:151-156` -> `:152-157`, rule 11 -> `:174-178` (it was cited `:173-178`, one
  line past its end), rule 22 `:243` -> `:244`. Rule 23 gained four script and three test paths (and three test files in its `run`), now
  `:245-261`; `default`/`unmapped` `:256`/`:257` -> `:264`/`:265`. `:3` and `:39-49` hold.
  Re-measured with `json.load`/`wc -l`.
- `sabotage_refresh.py` - `REFRESH_MUTATIONS` moved `:37` -> `:51` (constants added above it);
  round-3 mutations appended.
- `crew_refresh_check.py`, `CHANGELOG.md`, `TODO.md` - cited by name only.

No suite was executed by this note; the round-3 suite results live in the commit, not here.

## Re-anchor provenance - `8d447a7d` -> `c35edda5`, 2026-09-25 (T-0034)

`8d447a7d` was rebase-merged to `main` as `95120430`; `git diff --name-only 8d447a7d 768a747a`
returns only code-map, diagram, rule and graph files plus the crew 1.0.37 release bookkeeping, so
`768a747a` stands in for it. `git diff --name-only 768a747a c35edda5` returns
`.claude-plugin/marketplace.json`, `.gitattributes`, `CHANGELOG.md`, `plugin/PLUGINS.md`,
`plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/hooks/scripts/crew_refresh_check.py` and
`plugin/crew/tests/test_completion_audit.py`.

- `marketplace.json` - `:218` is still crew's `version` (now 1.0.38); still a rule 0 path.
- `crew_refresh_check.py` - one line reworded in place at `:363`; cited by name only.
- `test_completion_audit.py` - one `skipif` line added at `:375`, above
  `test_a_mode_change_with_the_same_content_is_a_change` (skipped when `os.name == "nt"`); cited
  by name only, as a rule 23 test file. `.crew/verify.json` did not change, so rule 23's paths,
  `run` and `seconds` stand.
- `CHANGELOG.md` - a 1.0.38 entry added at the top; the 1.0.21 descoping entry is still there.
- `.gitattributes` - three lines added (`.crew/verify.json text eol=lf` and its comment); not
  cited by this note.

No suite was executed by this note.

## Re-anchor provenance - `c35edda5` -> `8ebbdedc`, 2026-09-26 (T-0026 landing)

`8ebbdedc` is the crew 1.0.39 bump on top of the T-0026 merge (`563f54c3`). `git diff --name-only
c35edda5 8ebbdedc -- <the paths this note cites>` returns `.claude-plugin/marketplace.json`,
`.crew/verify.json`, `CHANGELOG.md`, `TODO.md` and `plugin/crew/**` files, among them
`crew_ticket.py`, four command files and three test files.

- `.crew/verify.json` - one rule inserted at `:167-172` as rule 10 (T-0026's approval-digest
  suite), so every later rule's index rose by one and every later line by seven: rule 11 ->
  12 (`:181-185`), 12-13 -> 13-14, 20-21 -> 21-22, 22 -> 23 (`:251`), 23 -> 24 (`:252-268`,
  its `why` at `:268`); `default` `:271`, `unmapped` `:272`, 273 lines. Rules 0-9 and rule 8's
  `:152-157` did not move. Re-measured with `json.load` and `grep -n`; corrected above.
- `marketplace.json` - `:218` is still crew's `version` (now 1.0.39); still a rule 0 path.
- `sabotage.py`, `verify-gate.sh`, `verify-gate.ps1`, `check-marketplace.py` - unchanged in
  this range, so `sabotage.py:75`/`:3046` and every `verify-gate` citation stand.
- `CHANGELOG.md`, `TODO.md` - cited by name only.

No suite was executed by this note; the landing's suite results are in its PR.

## Re-anchor provenance - `8d447a7d` -> `6d35ef8c`, 2026-09-26 (T-0006)

`8d447a7d` is T-0008's pre-rebase commit; its tree matches `origin/main` `768a747a` for every path
this note cites. `git diff --name-only 8d447a7d 6d35ef8c -- <the paths this note cites>` returns
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `TODO.md`,
`plugin/crew/CONFIG.md` and `plugin/crew/tests/sabotage.py`. Each citation was re-mapped with a
line diff and re-read with `grep -n`:

- `.crew/verify.json` - rule 24 appended after rule 23, which still ends at `:261`; `:3`, `:39-49`,
  `:151-156`, `:173-178`, `:244` and `:245-261` stand; `default`/`unmapped` `:264`/`:265` ->
  `:276`/`:277`. Rule and line counts re-measured with `json.load`/`wc -l` (25, 278).
- `plugin/crew/tests/sabotage.py` - `RESUME_MUTATIONS` imported at `:76` and appended on a new
  line `:3048`; `:75` and `:3046` hold.
- `plugin/crew/CONFIG.md` - the auto-resume rows moved the descoped process-group-kill
  limitation `:1959-1966` -> `:2016-2023`.
- `.claude-plugin/marketplace.json` - `:218` is still crew's `version` (1.0.40); `CHANGELOG.md`
  and `TODO.md` are cited by name only.

The suites named above were run for T-0006's code commit, not by this note.

## Re-anchor provenance - `6d35ef8c` -> `2bb92f32`, 2026-09-26 (T-0006 review round 3)

`git diff --name-only 6d35ef8c 2bb92f32 -- <the paths this note cites>` returns
`.crew/verify.json`, `CHANGELOG.md`, `plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md` and
`plugin/crew/tests/sabotage_resume.py` (plus the version files, stepped to 1.0.37 and back, which
end byte-identical). Each citation was re-mapped with a line diff and re-read with `grep -n`:

- `.crew/verify.json` - rule 24's `seconds` (61 -> 89) and `why` changed in place; `:263-273`,
  every other rule's lines and `default`/`unmapped` `:276`/`:277` stand. Rule and line counts
  re-measured with `json.load`/`wc -l` (25, 278).
- `plugin/crew/tests/sabotage_resume.py` - eight round-3 mutations appended, 44 in all; the
  `sabotage.py` registration `:76`, `:3048` did not change.
- `plugin/crew/CONFIG.md` - six lines added in §10 and §14's auto-resume paragraph moved the
  descoped process-group-kill limitation `:2016-2023` -> `:2022-2029`.
- `CHANGELOG.md`, `BUDGETS.md` - cited by name only here.

The suites named above were run for the round-3 code commits, not by this note.
