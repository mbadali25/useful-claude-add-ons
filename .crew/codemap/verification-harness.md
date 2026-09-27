anchor: useful-claude-add-ons@d9cdb54c
verified: 2026-09-27
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

## `.crew/verify.json` — 29 rules, up from 28

**DERIVED, read in full via `json.load` on the T-0021 merge of main (`c2ae46ab`).** 313 lines,
**29** rules (28 on the T-0005 landing `2b18f7ab`, 27 at `07ca3972`, 26 at `a0c0847e`, 25 at `8ebbdedc`, at T-0006's `2bb92f32` and at T-0005's
`a26ad8c0`, 24 at `c35edda5`, 23 at `f2bb919b`, 22 at `6c497a14`, 21 at `5d1fc5fd`) plus a `default`
(`["bash _verify/smoke.sh"]`, `:311`) and `unmapped: "fail"` (`:312`). Rule 6 (T-0005, the
cloud-guard suites) and rule 11 (T-0026, the approval digest) were each inserted mid-list, so every
rule after them is one or two higher than at `c35edda5`; rule 24 (#228), rule 25 (T-0008), rule 26
(T-0006), rule 27 (T-0004) and rule 28 (T-0021) were each appended last. Those seven are the only additions since
`6c497a14`; see below. The rule set was restructured, not
just grown: the broad `plugin/crew/hooks/**` / `plugin/crew/tests/**` shape
this note previously described is gone, replaced by per-subsystem rules that
name a handful of test files each — `crew_guards.py` (rule 5, and rule 6 since T-0005 Step 8),
`cloud_guard.py` (rule 6, T-0005), `crew_config.py` (rule 7), the `crew_state.py` cluster (rule 8,
eleven test modules), the whole-suite rule (rule 9), `crew_upgrade.py` (rule 10), `crew_ticket.py`'s
approval digest (rule 11) and command/agent/skill frontmatter (rule 12) are each their own entry
now, where the previous anchor
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
- **Rule 9**, the whole-suite rule (`plugin/crew/tests/conftest.py`,
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
- **Rule 6**, new at `fc54def6` (`.crew/verify.json:117-127`, T-0005): `paths` `cloud_guard.py`,
  `crew_guards.py` (since T-0005 Step 8), both `cloud-guard` flavours, `crew_tfplan.py`,
  `test_cloud_guard*.py` and `test_crew_tfplan.py` → `python3 -m pytest` over
  `test_cloud_guard.py`, `test_cloud_guard_environments.py` and `test_crew_tfplan.py`, priced 41s
  (its `why` records 40.5s and 512 passed on 2026-09-25 — a claim read, not re-timed here). Its
  mutations live in `plugin/crew/tests/sabotage_cloud.py` (`CLOUD_GUARD_MUTATIONS`), imported by
  `plugin/crew/tests/sabotage.py:67`.
- **Rule 11**, new at `8ebbdedc` (`.crew/verify.json:179-184`, T-0026; rule 10 until T-0005's rule 6
  merged in above it): `paths`
  `plugin/crew/hooks/scripts/crew_ticket.py` and `plugin/crew/tests/test_approval_digest.py`
  → `python3 -m pytest plugin/crew/tests/test_approval_digest.py
  plugin/crew/tests/test_crew_ticket.py -q`, priced 20s. Its `why` says the scope guard and the
  completion audit act on nothing but `crew_ticket.py`'s approval answer, so a status-value
  normalisation one byte too wide lets a scope or risk change through unapproved, and names the
  `APPROVAL DIGEST` entries in `plugin/crew/tests/sabotage_scope.py` as the mutations proving
  the tests can fail. Both paths also match rule 0 and rule 15 (`**/*.py`) by `fnmatch`.
  Since T-0004, `crew_ticket.py` also carries `header_line`/`parse_risk` (`:496-515`, the spec
  header's `risk:`; unknown reads `high`, never `low`), which only
  `plugin/crew/tests/test_crew_autopilot.py` exercises — a rule 27 test, while rule 27's `paths`
  do not name `crew_ticket.py`. So an edit there runs rules 0, 11 and 15, none of which runs
  that test; only rule 9's whole suite does, and that is deferred at Stop (DERIVED from the
  `paths`/`run` lists and `grep -l parse_risk`, not observed in a gate run).
- **Rule 13**, `plugin/crew/skills/crew-diagrams/**` → `bash
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
- **Rules 14-15**, the `.ps1`/`.psm1` lint and the `ruff`/`pylint` pair, are
  unchanged in shape from the previous anchor: both wrap their command in an
  `sh -c` tool-presence probe exiting 77 rather than 1 when the interpreter or
  module is absent, and rule 14 is the one rule carrying an `"agents"` key
  (`["powershell-security-hardening"]`).
- **Rules 22-23**, the two `run: []` catch-alls (`.github/workflows/**`
  deliberately unchecked; `graphify-out/**`, `.crew/codemap/**`, `.crew/**`,
  `.serena/**` and others deliberately unchecked) are unchanged. Both declare
  `"reach": "local"` on the reading that an empty `run` cannot reach off this
  machine — `verify_record.scan_reach([])` already returns that.
- **Rule 24**, new at `f2bb919b` (`.crew/verify.json:263`, #228; rule 23 until T-0005's rule 6 merged in): `paths`
  `.claude/rules/**` and `.crew/codemap/**` → `python3
  plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check`, priced
  1s. Its `why` calls it a SYNC check between the two artifacts, not a
  correctness check on the codemap prose: it passes whenever the rules match
  the codemap, even a stale codemap. **`.crew/codemap/**` is now in two rules**
  - rule 23's deliberately-unchecked `run: []` and rule 24 - and the gate runs
  every matched rule (`verify-gate.sh:920`, `rule_order`, "matched rule
  indices"), so rule 23's "DELIBERATELY UNCHECKED" `why` no longer describes
  what happens to a codemap edit: any `.crew/codemap/` change without a
  regenerated `.claude/rules/` now fails the Stop gate.
- **Rule 25**, new at `adf8d1dd` (`.crew/verify.json:264-280`, T-0008; rule 24 until T-0005's rule 6 merged in): `paths`
  `plugin/crew/hooks/scripts/crew_refresh_check.py`, its three test files,
  `plugin/crew/tests/sabotage_refresh.py`, and `plugin/crew/commands/implement.md`
  / `done.md`, and since T-0008's review round 3 `scope_guard.py`,
  `completion_audit.py`, `crew_freshness.py` and `scope_base.py` with
  `test_scope_guard.py`, `test_completion_audit.py` and `test_scope_base.py`
  → `python3 -m pytest` over those six test files, priced 32s (its `why`,
  `:280`, records 31.8s measured on the authoring host — a claim read, not
  re-timed here). `crew_freshness.py` is on rule 8 too. At the default 60s
  Stop budget rule 25 (32s) plus rule 15 (38s) no longer fit together, so a
  `.py` edit on these paths has one of them deferred at Stop (JUDGEMENT,
  from the two `seconds` values, not observed). A test,
  `test_every_module_the_refresh_allowance_touches_runs_a_pytest_rule` in
  `plugin/crew/tests/test_refresh_check.py`, fails if any of the five
  modules stops matching a pytest rule. The check can refuse `/crew:done`, so its `why`
  names must-refuse and must-allow cases, and says `implement.md`/`done.md` are
  mapped here because these tests carry their ordering checks. Its mutations
  live in `plugin/crew/tests/sabotage_refresh.py` (`REFRESH_MUTATIONS`, `:51`),
  imported by `plugin/crew/tests/sabotage.py:75` and appended to `MUTATIONS` at
  `:3049` (in the `MUTATIONS +=` statement at `:3048-3050`) — the same sibling-module pattern as the other `sabotage_*.py`
  lists, because `sabotage.py` sits at `.pylintrc`'s max-module-lines. Every
  rule-25 path also matches rule 0 and either rule 15 (the `.py` files) or
  rule 12 (the two commands), by `fnmatch`, the primitive `matches()` uses
  (`verify-gate.sh:869-876`) — so an edit there runs more than rule 25.
- **Rule 26**, new at `6d35ef8c` (`.crew/verify.json:282-292`, T-0006; rule 24 on its branch,
  25 once T-0026's rule 10 moved every later index up by one, 26 once T-0005's rule 6 did the
  same): `paths`
  `crew_resume.py`, `crew_context.py`, both `handoff-write` flavours,
  `test_crew_resume.py`, `test_crew_resume_hook.py` and `sabotage_resume.py` →
  `python3 -m pytest` over the two resume test files plus `test_auto_cycle.py`, priced 89s (its
  `why` records 89s, 348 passed / 12 skipped / 68 deselected after review round 3, under load;
  60s after round 2). Its
  mutations live in `plugin/crew/tests/sabotage_resume.py` (`RESUME_MUTATIONS`, 44), imported by
  `plugin/crew/tests/sabotage.py:76` and appended to `MUTATIONS` at `:3050`.
- **Rule 27**, new at `07ca3972` (`.crew/verify.json:293-300`, T-0004; rule 26 until T-0005's
  rule 6 merged in): `paths`
  `crew_autopilot.py`, `commands/autopilot.md`, `test_crew_autopilot.py` and
  `sabotage_autopilot.py` → `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py
  plugin/crew/tests/test_lifecycle_commands.py -q`, priced 5s (its `why` records 4.6s measured
  2026-09-26 after the round-1 fixes — a claim read, not re-timed here). `test_lifecycle_commands.py` rides along for
  `autopilot.md`'s 120-line budget and exact-CLI checks. Its mutations live in
  `plugin/crew/tests/sabotage_autopilot.py` (`AUTOPILOT_MUTATIONS`, `:19`), imported by
  `plugin/crew/tests/sabotage.py:77` and appended at `:3050`. The rule's `why` states no
  mutation count (it said "six" until the refresh commit after `07ca3972`, while the tuple
  held more); count them in the tuple. One of them targets `crew_ticket.py`'s `parse_risk`, a path rule 27
  does not name (see rule 11). `crew_autopilot.py` also matches rules 0 and 15, `autopilot.md`
  rules 0 and 12.
- **Rule 28**, new at `7b667587` (`.crew/verify.json:301-308`, T-0021; rule 24 on its branch
  until the merge of main at `86ea912f` put it after rule 27): `paths`
  `plugin/crew/hooks/scripts/crew_tracker.py`, `plugin/crew/tests/test_crew_tracker.py`,
  `plugin/crew/tests/sabotage_tracker.py` and `plugin/crew/tests/tracker_fixtures/**` →
  `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q`, priced 4s (its `why` records
  3.3s measured 2026-09-26 — a claim read, not re-timed here). Its mutations live in
  `plugin/crew/tests/sabotage_tracker.py` (`TRACKER_MUTATIONS`, 81 after review rounds 3 and 4),
  imported by `plugin/crew/tests/sabotage.py:78` and appended at `:3050`.

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
  test file is named in rule 4's `run`; only rule 9's whole suite runs them.
- **Per-rule process-group tracking and kill-on-signal was DESCOPED from crew
  1.0, and it is a documented limitation, not a silent gap.**
  `verify-gate.sh:1493-1502` and `plugin/crew/CONFIG.md:2200-2207` both state
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

- `.crew/verify.json:164-169` (rule 9) — the whole-suite pytest rule and its
  377s pricing.
- `.crew/verify.json:117-127` (rule 6) — the T-0005 cloud-guard suites.
- `.crew/verify.json:179-184` (rule 11) — the T-0026 approval-digest suite.
- `.crew/verify.json:193-197` (rule 13) — the crew-diagrams `render.sh`
  exit-77 port.
- `plugin/crew/hooks/scripts/verify-gate.sh:63-66` — the bounded single-read
  stdin gate.
- `plugin/crew/hooks/scripts/verify-gate.sh:1600-1705` /
  `verify-gate.ps1:1655-1789` — temp-file rule-output capture, 1 MiB tail cap,
  no-pipe fallback refusal.
- `.crew/verify.json:263` (rule 24) — the `.claude/rules/` sync check.
- `.crew/verify.json:264-280` (rule 25) — the T-0008 refresh-check suite;
  `plugin/crew/tests/sabotage.py:75`, `:3049` — `sabotage_refresh.py`'s
  registration.
- `.crew/verify.json:282-292` (rule 26) — the T-0006 auto-resume suite;
  `plugin/crew/tests/sabotage.py:76`, `:3050` — `sabotage_resume.py`'s registration.
- `.crew/verify.json:293-300` (rule 27) — the T-0004 autopilot suite;
  `plugin/crew/tests/sabotage.py:77`, `:3050` — `sabotage_autopilot.py`'s registration.
- `.crew/verify.json:301-308` (rule 28) — the T-0021 tracker suite;
  `plugin/crew/tests/sabotage.py:78`, `:3050` — `sabotage_tracker.py`'s registration.
- `plugin/crew/hooks/scripts/verify-gate.sh:1493-1502` /
  `plugin/crew/CONFIG.md:2200-2207` — the descoped per-rule process-group kill,
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

- `pwsh` — resolved by absolute path first (`.crew/verify.json`'s rule 14 `sh
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

## Re-anchor provenance - `8ebbdedc` + `2bb92f32` -> `a0c0847e`, 2026-09-26 (T-0006 landing)

`a0c0847e` is the crew 1.0.40 bump on top of `1cec9572`, the merge of T-0006 (`cb125d51`, note anchor
`2bb92f32`) into main at `d3844c76` (note anchor `8ebbdedc`). The two lines' provenance is above,
side by side.

- `.crew/verify.json` - changed on both sides. Main inserted T-0026's rule at `:167-172` as rule
  10; T-0006 appended its rule last. Merged: **26 rules, 285 lines**; rule 23 `:251`, rule 24
  (T-0008) `:252-268`, **rule 25 (T-0006) `:270-280`**, `default` `:283`, `unmapped` `:284`.
  Both sides had called their newest rule "rule 24"; the T-0006 one is renumbered 25 here, in the
  rule list and in the entry points, so no index is claimed twice. Re-measured with `json.load`
  and `grep -n`.
- `plugin/crew/tests/sabotage.py` - changed on T-0006 only: `RESUME_MUTATIONS` imported at `:76`
  and appended at `:3048`; `SCOPE_MUTATIONS` (`:71`, carrying T-0026's `APPROVAL DIGEST` entries
  in `sabotage_scope.py`) and `REFRESH_MUTATIONS` (`:75`, `:3046`) hold.
- `plugin/crew/CONFIG.md` - changed on T-0006 only; the process-group-kill limitation stays at
  `:2022-2029`.
- `marketplace.json` - `:218` is crew's `version` (1.0.40); still a rule 0 path.

The landing's suite results are in its PR, not executed by this note.

## Re-anchor provenance - `a0c0847e` -> `07ca3972`, 2026-09-26 (T-0004)

`git diff --name-only a0c0847e..07ca3972 -- <the paths this note cites>` returns
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `TODO.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/hooks/scripts/crew_ticket.py` and
`plugin/crew/tests/sabotage.py`. `verify-gate.sh`/`.ps1`, `verify_record.py`,
`scripts/check-marketplace.py`, `scripts/check_instructions.py`, `_verify/*`, `CLAUDE.md` and the CI
workflows did not change, so their citations stand unread.

- `.crew/verify.json` - one hunk at `:277`: rule 26 appended after rule 25, which still spans
  `:270-280`; `:3`, `:39-49`, `:152-157`, `:167-172`, `:181-185`, `:251` and `:252-268` stand;
  `default`/`unmapped` `:283`/`:284` -> `:291`/`:292`. Re-measured with `json.load`/`wc -l`
  (27, 293).
- `plugin/crew/tests/sabotage.py` - `AUTOPILOT_MUTATIONS` imported at `:77` from
  `plugin/crew/tests/sabotage_autopilot.py`, pushing the `MUTATIONS +=` statement from
  `:3046-3048` to `:3047-3049`. `:71`, `:75`, `:76` hold; `REFRESH_MUTATIONS` is on `:3048`,
  `RESUME_MUTATIONS` and `AUTOPILOT_MUTATIONS` on `:3049`. (The previous `:3046` for
  `REFRESH_MUTATIONS` named the statement's first line, not the line carrying the name.)
- `plugin/crew/CONFIG.md` - three insertions above it moved the process-group-kill limitation
  `:2022-2029` -> `:2029-2036` (re-read by `grep -n`).
- `crew_ticket.py` - `header_line`/`parse_risk` added at `:491-515`; still rule 10's path, and
  the coverage gap it opens is recorded under rule 10 above.
- `marketplace.json`, `CHANGELOG.md`, `TODO.md`, `BUDGETS.md` - cited by name only.

No suite or command was executed by this note; rule 26's suite and `sabotage.py` were not run.

## Re-anchor provenance - `8d447a7d` -> `fc54def6`, 2026-09-25 (T-0005)

`8d447a7d` is T-0008's pre-rebase round-3 commit, not an ancestor of HEAD (T-0008 landed by
rebase-merge as `95120430`/`768a747a`). Of the paths this note cites, the ones T-0005 changed are
`.crew/verify.json`, `plugin/crew/CONFIG.md`, `CHANGELOG.md`, `TODO.md` and the version files;
`verify-gate.sh`/`.ps1`, `_verify/*`, `scripts/check-marketplace.py`,
`scripts/check_instructions.py` and the CI workflows did not change, so their citations stand
unread.

- `.crew/verify.json` - one rule INSERTED at index 6 (`:117-126`, the three cloud-guard suites,
  priced 41s), not appended, so every rule from the old 6 on is one higher and every line below
  `:116` moved by 11: whole-suite rule 9 `:163-168`, diagrams rule 12 `:185-189`, `.claude/rules/`
  rule 23 `:255`, refresh-check rule 24 `:256-272`, `default`/`unmapped` `:275`/`:276`. Corrected
  above wherever the note states a current number; the provenance sections keep the numbers true
  at their own anchors. `:3` and `:39-49` hold. Re-measured with `json.load` and `wc -l` (25 rules,
  277 lines).
- `plugin/crew/CONFIG.md` - the `environments.*` section added above the verify-gate chapter; the
  descoping limitation moved `:1959-1966` -> `:2081-2088` (re-read, same text).
- `CHANGELOG.md`, `TODO.md`, `.claude-plugin/marketplace.json` - cited by name or as rule paths only.

No suite was executed by this note; T-0005's suite results are in its commits and review, not here.

## Re-anchor provenance - `fc54def6` -> `2170d72e`, 2026-09-26 (T-0005 review round 2)

`git diff --name-only fc54def6 2170d72e -- <the paths this note cites>` returns only what round 2
changed: `plugin/crew/CONFIG.md`, three lines added at `:1368-1373` (the saved-plan paragraph), so the
descoping limitation moved `:2081-2088` -> `:2084-2091` (re-read, same text; corrected above).
`.crew/verify.json`, the gate scripts and `_verify/*` did not change.

## Re-anchor provenance - `2170d72e` -> `3a57b2d2`, 2026-09-26 (T-0005 rounds 3-4 and Step 8)

`git diff --name-only 2170d72e 3a57b2d2 -- <the paths this note cites>` returns `.crew/verify.json`
(one path, `crew_guards.py`, added to rule 6's `paths` at `:118`, so the file is 278 lines and
every later line moved +1: rule 9 `:164-169`, rule 12 `:186-190`, rule 23 `:256`, rule 24
`:257-273`, `default` `:276`, `unmapped` `:277`; corrected above), `plugin/crew/CONFIG.md` (the
allowlist paragraph and a table note, 20 lines above the verify-gate chapter, so the descoping
limitation moved `:2084-2091` -> `:2104-2111`, re-read, same text), and under `plugin/crew/**`
`cloud_guard.py`, `crew_guards.py`, `sabotage_cloud.py`, `test_cloud_guard.py`,
`test_cloud_guard_environments.py` and `README.md`. None of the gate scripts, `_verify/*` or
`scripts/check-marketplace.py` changed. Rule count still 25. No suite was executed by this note.

## Re-anchor provenance - `3a57b2d2` -> `1e210476`, 2026-09-26 (T-0005 Step 9)

`git diff --name-only 3a57b2d2 1e210476 -- <the paths this note cites>` returns
`plugin/crew/CONFIG.md` (four lines added to the `environments.*` section, above the verify-gate
chapter, so the descoping limitation moved `:2104-2111` -> `:2108-2115`, re-read, same text;
corrected above) and under `plugin/crew/**` `cloud_guard.py`, `crew_guards.py`,
`sabotage_cloud.py`, `test_cloud_guard.py`, `test_cloud_guard_environments.py`, `README.md`,
`BUDGETS.md` and the version files. `.crew/verify.json`, the gate scripts, `_verify/*` and
`scripts/check-marketplace.py` did not change; rule count still 25. No suite was executed by this
note.

## Re-anchor provenance - `1e210476` -> `aa7f9841`, 2026-09-26 (T-0005 review round 5)

`git diff --name-only 1e210476 aa7f9841 -- <the paths this note cites>` returns
`plugin/crew/CONFIG.md` (six lines added to the `environments.*` section, above the verify-gate
chapter, so the descoping limitation moved `:2108-2115` -> `:2114-2121`, re-read with `diff`, same
text; corrected above) and under `plugin/crew/**` `cloud_guard.py`, `crew_guards.py`,
`sabotage_cloud.py`, `test_cloud_guard.py`, `test_cloud_guard_environments.py`, `README.md`,
`BUDGETS.md` and the version files. `.crew/verify.json`, the gate scripts, `_verify/*` and
`scripts/check-marketplace.py` did not change; rule count still 25. No suite was executed by this
note.

## Re-anchor provenance - `aa7f9841` -> `a26ad8c0`, 2026-09-26 (T-0005 Step 10)

`git diff --name-only aa7f9841 a26ad8c0 -- <the paths this note cites>` returns
`plugin/crew/CONFIG.md` (the `environments.*` section's allowlist paragraph rewritten and a "What
the guard does not catch" paragraph added, 15 lines net, all above the verification chapter, so
the descoping limitation moved `:2114-2121` -> `:2129-2136`, re-read with `diff`, same text;
corrected above), the version files (stepped back and re-set, byte-identical to `aa7f9841`) and,
under `plugin/crew/**`, the Step 10 code, tests, README, BUDGETS and the crew-cloud skill, none
cited here at a line. `_verify/smoke.sh` and `scripts/check-marketplace.py` did not change.

## Re-anchor provenance - `6f96e627` + `a26ad8c0` -> `2b18f7ab`, 2026-09-26 (T-0005 landing)

`2b18f7ab` is the crew 1.0.42 bump on top of `4ed4b763`, the merge of T-0005 (`4e0abc8f`) into
main at `1e0706ac`. Both lines' provenance is above, side by side. A citation can only be wrong at
the merge when its file changed on both sides, or when a line from one side cites a file the other
side changed; each such citation was re-mapped with a line diff of the cited file and re-read with
`grep -n`/`sed -n` on the merged tree. The bump commit replaced `1.0.41` with `1.0.42` in place in
the version files and in T-0005's own version statements (no line added or removed, except one
line in `CHANGELOG.md`'s T-0005 bump note).

- `.crew/verify.json` - changed on both sides. Main inserted T-0026's rule at index 10 and appended
  T-0006's and T-0004's; T-0005 inserted the cloud-guard rule at index 6. Merged: **28 rules, 305
  lines**; rule 6 (T-0005) `:117-127`, whole-suite rule 9 `:164-169`, rule 11 (T-0026)
  `:179-184`, diagrams rule 13 `:193-197`, `.claude/rules/` rule 24 `:263`, refresh-check rule 25
  `:264-280` (its `why` at `:280`), auto-resume rule 26 `:282-292`, autopilot rule 27 `:293-300`,
  `default` `:303`, `unmapped` `:304`. Every rule both sides numbered from 11 on is one higher than
  either side said; renumbered in the rule list and the entry points above, not in the history
  sections. Re-measured with `json.load` and `grep -n`.
- `plugin/crew/tests/sabotage.py` - changed on main only; `:67` (`CLOUD_GUARD_MUTATIONS`, T-0005's
  sibling list), `:75`, `:76`, `:77` and `:3047-3049` hold.
- `plugin/crew/CONFIG.md` - changed on both sides; the process-group-kill limitation is at
  `:2201-2208` (re-read, same text).
- `crew_ticket.py` - changed on main only; `:496-515` holds.
- `.claude-plugin/marketplace.json` - `:218` is 1.0.42; still a rule 0 path.
- `CHANGELOG.md`, `TODO.md`, `BUDGETS.md` - cited by name only.

No suite or command was executed by this note; the landing's suite results are in its PR.

## Re-anchor provenance - `c35edda5` -> `7b667587`, 2026-09-26 (T-0021)

`git diff --name-only c35edda5 7b667587` returns T-0034's refresh (`5c59395d`) and T-0021's
commits. Of the paths this note cites with a line:

- `.crew/verify.json` - rule 24 appended after rule 23 (`:262-269`); rule 23 `:245-261` holds
  (only its closing line gained a comma); `:3`, `:39-49`, rules 8/11/22 hold; `default`/
  `unmapped` `:264`/`:265` -> `:272`/`:273`. Re-measured with `json.load`/`wc -l`.
- `plugin/crew/tests/sabotage.py` - one import added at `:76`, so `REFRESH_MUTATIONS`' append
  line moved `:3046` -> `:3047`; `:75` holds.
- `plugin/crew/CONFIG.md` - one table row removed in section 9, so `:1959-1966` -> `:1958-1965`
  (re-read: the per-rule process-group limitation).
- `plugin/crew/.budget-allowance.json` - `obsidian-sync.md`'s entry removed; cited by name only.
- `CHANGELOG.md`, `TODO.md`, `marketplace.json`, `implement.md`, `done.md` - cited by name only.

No suite was executed by this note; T-0021's suite results live in its commits.

Re-verified per-path from `7b667587` to `385eadd5` for T-0021's review round 1. `git diff --name-only 7b667587 385eadd5` returns T-0021's refresh (`bc6432b1`), the version step-back (`764c2244`) and review round 1's fix commit (`385eadd5`): `CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `brainstorm.md`, `obsidian-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set).
This note cites `crew_tracker.py`, `test_crew_tracker.py` and `sabotage_tracker.py` by name only,
as rule 24's paths; the rule itself (`.crew/verify.json:262-269`) and `sabotage.py:76`/`:3048`
did not change. `sabotage_tracker.py` now holds 42 mutations, two of which go RED only as root
(their tests skip, by name, without it). `CHANGELOG.md` and `TODO.md` are cited by name only.

Re-verified per-path from `385eadd5` to `bcb77ce2` for T-0021's review round 2. `git diff --name-only 385eadd5 bcb77ce2` returns the round-1 refresh (`59de6d56`), the version step-back (`f11c72d0`) and review round 2's fix commit (`bcb77ce2`): `CHANGELOG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `fix.md`, `implement.md`, `jira-sync.md`, `sdp-sync.md`, `crew_tracker.py` and three test files, plus the refresh's own artifacts. The version files net to no change (1.0.46 stepped back and re-set).
This note cites `crew_tracker.py`, `test_crew_tracker.py` and `sabotage_tracker.py` by name only,
as rule 24's paths; the rule itself (`.crew/verify.json:262-269`) and `sabotage.py:76`/`:3048`
did not change. `sabotage_tracker.py` now holds 63 mutations (counted from `TRACKER_MUTATIONS`),
two of which go RED only as root; one mutation now targets `plugin/crew/commands/fix.md` and
is checked by `test_lifecycle_commands.py`, which rule 24 does not map. `implement.md` (rule
23's path, cited by name only) moved its `--to review` call ahead of `/crew:review`.
`CHANGELOG.md` is cited by name only.

## Re-anchor provenance - `2b18f7ab` + `bcb77ce2` -> `c2ae46ab`, 2026-09-27 (T-0021 review round 3 and its merge of main)

The merge `86ea912f` joins main's `2b18f7ab` with T-0021's `bcb77ce2`; review round 3's fix commit
`629fb518` sits under it and the crew 1.0.43 bump `c2ae46ab` on top. `git diff --name-only 2b18f7ab
c2ae46ab` returns only T-0021's files (its code, commands, tests, fixtures, release files,
`.crew/verify.json`, `CHANGELOG.md`, `TODO.md`). Every citation in this note's body into those files
was re-mapped from the side of the merge its line came from (`git blame`: main's lines against
`2b18f7ab`, T-0021's against `bcb77ce2`) with a line diff, and each one whose line moved or changed
was re-read at `c2ae46ab`. Corrected here: `.crew/verify.json` is 313 lines and 29 rules, T-0021's
tracker rule last as rule 28 (`:301-308`), `default` `:311`, `unmapped` `:312`;
`plugin/crew/tests/sabotage.py` imports `sabotage_refresh`/`_resume`/`_autopilot`/`_tracker` at
`:75`-`:78` and the `MUTATIONS +=` statement is `:3048-3050` (refresh at `:3049`, the other three at
`:3050`); the `CONFIG.md` background-process limitation is `:2200-2207`. No test suite was executed for
this note.

## Re-anchor provenance - `c2ae46ab` -> `5832b32a`, 2026-09-27 (T-0021 test escape)

`git diff --name-only c2ae46ab 5832b32a` returns the version files (stepped to 1.0.42 and re-set to
1.0.43, net unchanged), `TODO.md` (one follow-up appended) and
`plugin/crew/tests/test_crew_tracker.py`, where three lines now spell U+2028/U+2029 as escapes
instead of raw characters (the same strings at run time). This note cites that test file by name
only, so no citation moved. No test suite was executed for this note.

## Re-anchor provenance - `5832b32a` -> `d276b268`, 2026-09-27 (T-0021 review round 4)

`git diff --name-only 5832b32a d276b268` returns T-0021's round-4 files: `crew_tracker.py`,
`brainstorm.md`, `fix.md`, `test_crew_tracker.py`, `test_lifecycle_commands.py`,
`sabotage_tracker.py`, `plugin/crew/README.md`, `CHANGELOG.md`, two crew guides and the version
files (net unchanged). This note cites the tracker files and `fix.md` by name only.
`TRACKER_MUTATIONS` still holds 81 (counted by importing `sabotage_tracker`); two of them were
re-aimed at moved lines, the userinfo mutation at `normal_url`'s new line and the
INDEX-refused-late mutation at `test_obsidian_create_writes_no_card_when_index_refuses_late`.
`plugin/crew/tests/sabotage.py` did not change, so `:75`-`:78` and `:3048-3050` hold. No test
suite was executed for this note.

## Re-anchor provenance - `d276b268` -> `d9cdb54c`, 2026-09-27 (T-0021 round-4 suite fixes)

`git diff --name-only d276b268 d9cdb54c` returns `plugin/crew/tests/sabotage_tracker.py`,
`plugin/crew/BUDGETS.md` and the version files (stepped to 1.0.42 and re-set to 1.0.43, net
unchanged). The serial run at `0384afc7` found "tracker rewrites an existing ticket note" STILL GREEN
(`test_note_created_once_never_overwritten` no longer reaches `_NOTE_FLAGS`' exclusive open, since
an existing note that is this repo's is not re-created); it now names
`test_create_loses_the_note_race_says_id_taken`, which goes red under it (checked in a
`git archive` copy with the mutation applied). `TRACKER_MUTATIONS` still holds 81; `sabotage.py`
did not change. No test suite was executed for this note.
