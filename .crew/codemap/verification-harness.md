anchor: useful-claude-add-ons@05413bbe
verified: 2026-09-28
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

## `.crew/verify.json` — 31 rules, up from 30

**DERIVED, read in full via `json.load` on T-0010-solo's merge of `e878cc31` (T-0075 landed as
crew 1.0.59), where T-0010's policy rule and T-0075's five rule-7 paths make it 345 lines.** 345 lines,
**32** rules (32 and 339 lines on T-0010-solo at `50a275ea`, 31 and 330 at `c817782f`, 29 and 311 before its first merge; 31 and 337 lines at `7d217751` on T-0075's branch; 31 and 335 lines on T-0075's merge of `d2fbd408`, 31 and 332 lines at `d2fbd408`, 30 and 326 on T-0075's branch at `763eaeff`, 30 and 323 lines at `67caa4b8`, 28 and 302 on T-0024's branch at `45345812`, 325 on T-0075's branch at `f7163410`, 30 and 322 lines at `bebbb97f`, 29 at `db14619c` and on T-0023's merge of `502cb137`, 28 on the T-0005 landing `2b18f7ab` and at T-0023's `eba11657`, 27 at `07ca3972`, 26 at `a0c0847e`, 25 at `8ebbdedc`, at T-0006's `2bb92f32` and at T-0005's
`a26ad8c0`, 24 at `c35edda5`, 23 at `f2bb919b`, 22 at `6c497a14`, 21 at `5d1fc5fd`) plus a `default`
(`["bash _verify/smoke.sh"]`, `:342`) and `unmapped: "fail"` (`:343`). Rule 6 (T-0005, the
cloud-guard suites) and rule 11 (T-0026, the approval digest) were each inserted mid-list, so every
rule after them is one or two higher than at `c35edda5`; rule 24 (#228), rule 25 (T-0008), rule 26
(T-0006), rule 27 (T-0004), rule 29 (T-0021), rule 30 (T-0023) and rule 31 (T-0024; rule 30 on main, rule 27 on its branch) were each appended last, and T-0010's rule 28 went in
right after rule 27 when T-0010-solo merged `67caa4b8`. Those ten are the only additions since
`6c497a14`; see below. The rule set was restructured, not
just grown: the broad `plugin/crew/hooks/**` / `plugin/crew/tests/**` shape
this note previously described is gone, replaced by per-subsystem rules that
name a handful of test files each — `crew_guards.py` (rule 5, and rule 6 since T-0005 Step 8),
`cloud_guard.py` (rule 6, T-0005), `crew_config.py` (rule 7, `.crew/verify.json:129-144`; since T-0075 also `crew_config_menu.py`,
`test_config_menu.py`, `sabotage_config.py`, `crew_config_files.py` and `test_config_files.py`,
`:136-140`, whose `run` adds `test_config_menu.py` and `test_config_files.py`; the 50
`CONFIG_MENU_MUTATIONS` (by `len()` at `7d217751`) are imported at `plugin/crew/tests/sabotage.py:80`
and appended at `:3055`), the `crew_state.py` cluster (rule 8,
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
- **Rule 11**, new at `8ebbdedc` (`.crew/verify.json:184-189`, T-0026; rule 10 until T-0005's rule 6
  merged in above it): `paths`
  `plugin/crew/hooks/scripts/crew_ticket.py` and `plugin/crew/tests/test_approval_digest.py`
  → `python3 -m pytest plugin/crew/tests/test_approval_digest.py
  plugin/crew/tests/test_crew_ticket.py -q`, priced 20s. Its `why` says the scope guard and the
  completion audit act on nothing but `crew_ticket.py`'s approval answer, so a status-value
  normalisation one byte too wide lets a scope or risk change through unapproved, and names the
  `APPROVAL DIGEST` entries in `plugin/crew/tests/sabotage_scope.py` as the mutations proving
  the tests can fail. Both paths also match rule 0 and rule 15 (`**/*.py`) by `fnmatch`.
  Since T-0004, `crew_ticket.py` also carries `header_line`/`parse_risk` (`:500-519`, the spec
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
- **Rule 24**, new at `f2bb919b` (`.crew/verify.json:268`, #228; rule 23 until T-0005's rule 6 merged in): `paths`
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
- **Rule 25**, new at `adf8d1dd` (`.crew/verify.json:269-285`, T-0008; rule 24 until T-0005's rule 6 merged in): `paths`
  `plugin/crew/hooks/scripts/crew_refresh_check.py`, its three test files,
  `plugin/crew/tests/sabotage_refresh.py`, and `plugin/crew/commands/implement.md`
  / `done.md`, and since T-0008's review round 3 `scope_guard.py`,
  `completion_audit.py`, `crew_freshness.py` and `scope_base.py` with
  `test_scope_guard.py`, `test_completion_audit.py` and `test_scope_base.py`
  → `python3 -m pytest` over those six test files, priced 32s (its `why`,
  `:283`, records 31.8s measured on the authoring host — a claim read, not
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
  `:3053` (in the `MUTATIONS +=` statement at `:3052-3055`) — the same sibling-module pattern as the other `sabotage_*.py`
  lists, because `sabotage.py` sits at `.pylintrc`'s max-module-lines. Every
  rule-25 path also matches rule 0 and either rule 15 (the `.py` files) or
  rule 12 (the two commands), by `fnmatch`, the primitive `matches()` uses
  (`verify-gate.sh:869-876`) — so an edit there runs more than rule 25.
- **Rule 26**, new at `6d35ef8c` (`.crew/verify.json:287-297`, T-0006; rule 24 on its branch,
  25 once T-0026's rule 10 moved every later index up by one, 26 once T-0005's rule 6 did the
  same): `paths`
  `crew_resume.py`, `crew_context.py`, both `handoff-write` flavours,
  `test_crew_resume.py`, `test_crew_resume_hook.py` and `sabotage_resume.py` →
  `python3 -m pytest` over the two resume test files plus `test_auto_cycle.py`, priced 62s (its
  `why` records 62s, 398 passed / 13 skipped / 68 deselected, measured at `52778dd1` before T-0042
  review round 2 - a claim read, not re-timed here; 87s / 391 after review round 1, 73s / 388 before it, 89s / 348 / 12 after T-0006
  review round 3 under load, 60s after round 2; the 13th skip is a root-only skip). Its
  mutations live in `plugin/crew/tests/sabotage_resume.py` (`RESUME_MUTATIONS`, 72 since the
  partial-state fix before T-0042 review round 2, 69 after round 1, 66 before it, 44 before T-0042;
  counted with `len()` at `53f5482c`), imported by
  `plugin/crew/tests/sabotage.py:76` and appended to `MUTATIONS` at `:3054`.
- **Rule 27**, new at `07ca3972` (`.crew/verify.json:298-306` since T-0075's rule-7 paths, `:293-301` on main, `:296-304` before, T-0004, widened by T-0018 and
  T-0072; rule 26 until T-0005's rule 6 merged in):
  `paths` `crew_autopilot.py`, `commands/autopilot.md`, `test_crew_autopilot.py`,
  `test_crew_autopilot_status.py`, `sabotage_autopilot.py` and `test_crew_autopilot_deploy.py` →
  `python3 -m pytest plugin/crew/tests/test_crew_autopilot.py
  plugin/crew/tests/test_crew_autopilot_deploy.py plugin/crew/tests/test_crew_autopilot_status.py
  plugin/crew/tests/test_lifecycle_commands.py -q`, priced 18s (its `why` records 18.0s, 541 passed,
  measured 2026-09-28 on T-0072's landing merge under heavy-run; on T-0010-solo's merge at `d7c7c75c`
  the same four files ran 551 passed in 13.4s under heavy-run, so the price stands).
  `test_lifecycle_commands.py` rides along for `autopilot.md`'s line budget (100 since T-0018, 110
  since T-0010) and exact-CLI checks. Its mutations live in
  `plugin/crew/tests/sabotage_autopilot.py` (`AUTOPILOT_MUTATIONS`, `:28`, with T-0072's
  `DEPLOY_MUTATIONS` appended at `:473` and T-0018's `STATUS_MUTATIONS` at `:674`), imported by
  `plugin/crew/tests/sabotage.py:77` and appended at `:3054`; `test_crew_autopilot.py` asserts
  every `STATUS_MUTATIONS` entry reaches `sabotage.MUTATIONS`. The rule's `why` states no
  mutation count (it said "six" until the refresh commit after `07ca3972`, while the tuple
  held more); count them in the tuple. One of them targets `crew_ticket.py`'s `parse_risk`, a path rule 27
  does not name (see rules 11 and 31). `crew_autopilot.py` also matches rules 0, 15 and 28, `autopilot.md`
  rules 0, 12 and 28.
- **Rule 28**, new on T-0010-solo (`.crew/verify.json:307-313` since T-0010-solo merged `e878cc31`, `:302-308` since it merged
  `67caa4b8`, `:301-306` on its branch before, T-0010): `paths` `crew_autopilot.py`, `commands/autopilot.md`
  (since review round 2's FIX) and `test_crew_autopilot_policy.py` → `python3 -m pytest
  plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_scope_guard.py -q`,
  priced 21s (its `why` records 20.9s, 260 passed, measured 2026-09-28 on T-0010-solo's
  merge of `6387ab49` under heavy-run). `test_scope_guard.py` rides along for the
  `crew_autopilot.py approve` must-block/must-allow cases. Its mutations are `POLICY_MUTATIONS` at
  the end of `plugin/crew/tests/sabotage_autopilot.py` (`:687`, 55 entries: 39 after the first merge's six, then review round 3's eight, then the successor's two ported owner-only refusals and five round-4 fixes, then `deploy-allowed` writing on the merge of `6387ab49`),
  imported beside `AUTOPILOT_MUTATIONS` by `plugin/crew/tests/sabotage.py:77` and appended at
  `:3055`; `test_crew_autopilot_policy.py` asserts each reaches `sabotage.MUTATIONS`. Several
  target `crew_ticket.py` and `scope_guard.py`, paths this rule does not name (rules 11, 25 and
  31 do), and two (review round 3) target `plugin/crew/README.md`'s approve-exception sentence and
  phase-table row, which `test_crew_autopilot_policy.py` reads; the six from the merge name tests in `test_crew_autopilot_status.py` and
  `test_crew_route.py`, which rules 27 and 30 run, and one (round 4's `_one_line`) names
  `test_crew_autopilot.py`, which rule 27 runs.
- **Rule 29**, new at `7b667587` (`.crew/verify.json:314-321` since T-0010's merge of `e878cc31` (T-0075's rule-7 paths), `:309-316` since T-0010's rule 28 went in above it, `:307-314` on main at `3648f59a`, `:302-309` after T-0018 widened rule 27, `:301-308` before, T-0021; rule 24 on its branch
  until the merge of main at `86ea912f` put it after rule 27, rule 28 until T-0010's merge): `paths`
  `plugin/crew/hooks/scripts/crew_tracker.py`, `plugin/crew/tests/test_crew_tracker.py`,
  `plugin/crew/tests/sabotage_tracker.py` and `plugin/crew/tests/tracker_fixtures/**` →
  `python3 -m pytest plugin/crew/tests/test_crew_tracker.py -q`, priced 4s (its `why` records
  3.3s measured 2026-09-26 — a claim read, not re-timed here). Its mutations live in
  `plugin/crew/tests/sabotage_tracker.py` (`TRACKER_MUTATIONS`, 87 by `len()` at `8cabe586`: 81 after review rounds 3 and 4, six more net from T-0077),
  imported by `plugin/crew/tests/sabotage.py:78` and appended at `:3054`.
- **Rule 30**, new at `eba11657` (`.crew/verify.json:322-330` since T-0010's merge of `e878cc31`, `:317-325` since T-0018 landed on T-0010-solo, `:315-323` on main at `3648f59a`, `:309-317` before, T-0023; rule 27 until T-0005's
  rule 6 merged in, rule 28 until T-0021's tracker rule landed ahead of it, rule 29 until T-0010's merge): `paths`
  `crew_route.py`, `crew_context.py`, `test_crew_route.py`, `test_crew_route_hook.py` and
  `sabotage_route.py` → `python3 -m pytest plugin/crew/tests/test_crew_route.py
  plugin/crew/tests/test_crew_route_hook.py plugin/crew/tests/test_crew_context.py -q`, priced
  10s (its `why` records 8.5s, 180 passed, measured 2026-09-27 after review round 1 and the merge,
  with bash and pwsh present).
  `crew_context.py` is also a rule-26 path (the auto-resume suite), so an edit to it runs both suites. Its mutations
  live in `plugin/crew/tests/sabotage_route.py` (`ROUTE_MUTATIONS`), imported by
  `plugin/crew/tests/sabotage.py:79` and appended at `:3054`; the rule's `why` states no count.
  The config half of T-0023 is not on rule 30: `crew_config.py`, the two templates and
  `CONFIG.md` ride rule 7, whose suite (`test_crew_config.py`) carries the leaf count and the
  template-drift tests. `plugin/crew/skills/crew-setup/SKILL.md`, whose inline config copy
  `test_crew_config.py` also checks, matches rules 0, 1 and 12 but not 7, so an edit to that copy
  alone runs no suite that compares it - a gap that predates T-0023 (T-0004 edited the same block)
  and is recorded here, not fixed.
- **Rule 31**, new at `a2802526` (`.crew/verify.json:332-339` since T-0010's merge of `e878cc31`, `:327-334` since its merge of `f96e9ec9` put
  T-0010's rule 28 above it; `:325-332` on T-0075's branch; rule 30 at `:320-327` on main since T-0024's landing merge; rule 27 at
  `:290-297` on its branch until the merge of main put it after rule 29, T-0024): `paths`
  `approval_hook.py`, `approval-hook.sh`, `approval-hook.ps1`, `crew_ticket.py`,
  `test_approval_hook.py`, `test_approval_group.py` and `sabotage_approval.py` → `python3 -m
  pytest plugin/crew/tests/test_approval_hook.py plugin/crew/tests/test_approval_group.py
  plugin/crew/tests/test_crew_ticket.py -q`, priced 18s (its `why` records 18.1s, 290 passed and
  16 slow deselected, measured 2026-09-26 — a claim read, not re-timed by this note). The
  `FLAVOUR_MATRIX` `sh`/`ps1` cases are `slow`, so this rule does not run the wrappers; the
  whole-suite rule and CI's `-m slow` job do. Its mutations live in
  `plugin/crew/tests/sabotage_approval.py` (`APPROVAL_MUTATIONS`, `:32`; 65 entries by
  `len()` at `45345812` — count them there, the `why` states no number), imported by
  `plugin/crew/tests/sabotage.py:81` and appended at `:3055` (`:80` and `:3054` before T-0075's `sabotage_config` import). `crew_ticket.py` is named by
  rules 11 and 31 both (T-0010's owner-only refusal in `crew_ticket.approve` runs under both).

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
  `verify-gate.sh:1493-1502` and `plugin/crew/CONFIG.md:2373-2380` both state
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
(`CLAUDE.md:250`). See
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

- `.crew/verify.json:169-174` (rule 9) — the whole-suite pytest rule and its
  377s pricing.
- `.crew/verify.json:117-127` (rule 6) — the T-0005 cloud-guard suites.
- `.crew/verify.json:184-189` (rule 11) — the T-0026 approval-digest suite.
- `.crew/verify.json:198-202` (rule 13) — the crew-diagrams `render.sh`
  exit-77 port.
- `plugin/crew/hooks/scripts/verify-gate.sh:63-66` — the bounded single-read
  stdin gate.
- `plugin/crew/hooks/scripts/verify-gate.sh:1600-1705` /
  `verify-gate.ps1:1655-1789` — temp-file rule-output capture, 1 MiB tail cap,
  no-pipe fallback refusal.
- `.crew/verify.json:268` (rule 24) — the `.claude/rules/` sync check.
- `.crew/verify.json:269-285` (rule 25) — the T-0008 refresh-check suite;
  `plugin/crew/tests/sabotage.py:75`, `:3053` — `sabotage_refresh.py`'s
  registration.
- `.crew/verify.json:287-297` (rule 26) — the T-0006 auto-resume suite;
  `plugin/crew/tests/sabotage.py:76`, `:3054` — `sabotage_resume.py`'s registration.
- `.crew/verify.json:298-306` (rule 27) — the T-0004/T-0018/T-0072 autopilot suite;
  `plugin/crew/tests/sabotage.py:77`, `:3054` — `sabotage_autopilot.py`'s registration.
- `.crew/verify.json:307-313` (rule 28) — the T-0010 policy suite; `plugin/crew/tests/sabotage.py:77`,
  `:3055` register its `POLICY_MUTATIONS`.
- `.crew/verify.json:314-321` (rule 29) — the T-0021 tracker suite;
  `plugin/crew/tests/sabotage.py:78`, `:3054` — `sabotage_tracker.py`'s registration.
- `.crew/verify.json:322-330` (rule 30) — the T-0023 plain-text routing suite;
  `plugin/crew/tests/sabotage.py:79`, `:3054` — `sabotage_route.py`'s registration.
- `.crew/verify.json:332-339` (rule 31) — the T-0024 group-approval suite;
  `plugin/crew/tests/sabotage.py:81`, `:3055` — `sabotage_approval.py`'s registration.
- `plugin/crew/hooks/scripts/verify-gate.sh:1493-1502` /
  `plugin/crew/CONFIG.md:2373-2380` — the descoped per-rule process-group kill,
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

## Re-anchor provenance - `6f96e627` -> `068db4ff`, 2026-09-26 (T-0042)

`6f96e627` is T-0004's landing and `git diff --name-only 6f96e627 1e0706ac` returns refresh
artifacts only. Of the paths this note cites, `git diff --name-only 1e0706ac 068db4ff` returns
`.crew/verify.json`, `plugin/crew/CONFIG.md`, `plugin/crew/tests/sabotage_resume.py`,
`CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md` and the version files. `sabotage.py`,
`verify-gate.sh`/`.ps1`, `verify_record.py`, `scripts/check-marketplace.py`,
`scripts/check_instructions.py`, `_verify/*`, `CLAUDE.md` and the CI workflows did not change, so
their citations stand unread.

- `.crew/verify.json` - one hunk, rule 25's `seconds` (89 -> 74) and `why` rewritten in place; it
  still spans `:270-280`, and every other cited range stands. `json.load`/`wc -l`: 27 rules, 293
  lines, unchanged.
- `CONFIG.md` - T-0042's wait-reason prose in §14a sits above the descope limitation, so
  `:2029-2036` -> `:2077-2084`, re-read (same "Limitation (1.0)" paragraph).
- `sabotage_resume.py` - 22 mutations added, 66 in all (`len(RESUME_MUTATIONS)`);
  `sabotage.py:76` and `:3049` still import and append them.
- `marketplace.json`, `CHANGELOG.md`, `TODO.md`, `BUDGETS.md` - cited by name only.

No suite was executed by this note; the suite results T-0042 reports belong to its build, not
to this refresh.

## Re-anchor provenance - `068db4ff` -> `07eefac5`, 2026-09-26 (T-0042 review round 1)

Of the paths this note cites, `git diff --name-only 068db4ff 07eefac5` returns
`.crew/verify.json`, `plugin/crew/tests/sabotage_resume.py`, `CHANGELOG.md` and the version files
(stepped to 1.0.41 and back, unchanged at `07eefac5`). `sabotage.py`, `verify-gate.sh`/`.ps1`,
`verify_record.py`, `scripts/check-marketplace.py`, `CONFIG.md` and the rest did not change, so
their citations stand unread.

- `.crew/verify.json` - one hunk, rule 25's `seconds` (74 -> 87) and `why` rewritten in place; it
  still spans `:270-280`; `wc -l` 293, unchanged, so every other cited range stands.
- `sabotage_resume.py` - one mutation reworded and three added for round 1's guard branches, 69 in
  all (`len(RESUME_MUTATIONS)`); `sabotage.py:76` and `:3049` unchanged, still import and append.
- `CHANGELOG.md` - cited by name only.

No suite was executed by this note; the figures in rule 25's `why` belong to the fix, not to this
refresh.

## Re-anchor provenance - `2b18f7ab` + `07eefac5` -> `53f5482c`, 2026-09-27 (T-0042 merges main)

`53f5482c` is T-0042's rule-26 re-measure on top of the merge of origin/main `502cb137` into its
branch (`b7727a88`), `03cfab27` (a partial `resume-state.json` is an unknown) and the crew 1.0.43
bump. Of the paths this note cites, `git diff --name-only 2b18f7ab 53f5482c` returns
`.crew/verify.json`, `plugin/crew/CONFIG.md`, `plugin/crew/tests/sabotage_resume.py`,
`CHANGELOG.md`, `TODO.md`, `plugin/crew/BUDGETS.md` and the version files. `sabotage.py`,
`verify-gate.sh`/`.ps1`, `verify_record.py`, `scripts/check-marketplace.py`, `_verify/*` and the CI
workflows did not change on T-0042's side, so main's citations into them stand.

- `.crew/verify.json` - rule 26's `seconds` and `why` rewritten in place; `:282-292` holds, and
  every other cited range stands (28 rules, 305 lines, `json.load` and `wc -l`).
- `CONFIG.md` - T-0042's §14a prose (+50) sits above the descope limitation: main's `:2201-2208`
  is `:2249-2256`, set in the merge and re-read (same "Limitation (1.0)" paragraph).
- `sabotage_resume.py` - 72 mutations by `len(RESUME_MUTATIONS)`; `sabotage.py:76` and `:3049`
  still import and append them.
- `marketplace.json`, `CHANGELOG.md`, `TODO.md`, `BUDGETS.md` - cited by name only.

No suite was executed by this note; the figures in rule 26's `why` belong to that commit.

## Re-anchor provenance - T-0010-solo's branch line, `2b18f7ab` -> `50e67586`, 2026-09-27 (crew 1.0.43 on its branch)

T-0010's code commit was cherry-picked off `origin/main` (`502cb137`) as `0fc5b069`, apart from
T-0018 and T-0024, and the version set in `50e67586`. Every `path:line` citation this note makes into
a path T-0010 changed was mapped from the `2b18f7ab` tree with `difflib`; each one that moved
was re-pointed and compared line for line with the anchor tree at `50e67586`.

- `.crew/verify.json` - rule 28 appended at `:301-306`; rule 27 `:293-300` holds; `default`/
  `unmapped` `:303`/`:304` -> `:309`/`:310`; 29 rules, 311 lines (`json.load`/`wc -l`).
- `sabotage.py` - `:77` imports `POLICY_MUTATIONS` and `:3049` appends it, both in place.
- `sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` `:19` (31); `POLICY_MUTATIONS` `:167` (27).
- `crew_ticket.py` - `header_line`/`parse_risk` `:496-515` -> `:500-519`.
- `plugin/crew/CONFIG.md` - `:2201-2208` -> `:2203-2210` (T-0010's §20 rows above), same text.
- `CHANGELOG.md`, `BUDGETS.md` - cited by name only.

## Re-anchor provenance - `53f5482c` + `50e67586` -> `89c9ee9a`, 2026-09-27 (T-0010-solo merges main, crew 1.0.44)

`89c9ee9a` is T-0010's crew 1.0.44 version commit on top of `132c1758`, the merge of origin/main
`f0b12ee6` (T-0042 landed at 1.0.43) into T-0010-solo. Both lines' provenance is above. Main-side
citations were mapped through `git diff origin/main 89c9ee9a`, the branch-side ones through
`git diff 708db116 89c9ee9a`, with `difflib` over every repo-relative `path:line` citation, and
every moved or merge-set one re-read with `sed -n` at `89c9ee9a`:

- `.crew/verify.json` - both sides' rules merged without conflict: 29 rules, 311 lines
  (`json.load`/`wc -l`); rule 26 `:282-292`, rule 27 `:293-300`, rule 28 `:301-306`, `default`
  `:309`, `unmapped` `:310`.
- `plugin/crew/CONFIG.md` - T-0042's §14a prose and T-0010's §20 rows both sit above the descope
  limitation: `:2251-2258`, set in the merge and re-read (same "Limitation (1.0)" paragraph).
- `sabotage.py` - `:76` imports `RESUME_MUTATIONS`, `:77` `AUTOPILOT_MUTATIONS` and
  `POLICY_MUTATIONS`, and `:3049` appends all three. `len(RESUME_MUTATIONS)` 72,
  `len(AUTOPILOT_MUTATIONS)` 31, `len(POLICY_MUTATIONS)` 27.
- `marketplace.json`, `CHANGELOG.md`, `TODO.md`, `BUDGETS.md` - cited by name only.

The suite results for this merge are T-0010's implement report's, not this note's.

## Re-anchor provenance - `89c9ee9a` -> `8314d670`, 2026-09-27 (T-0010 review round 1 fixes)

`8314d670` fixes the four FIX findings of T-0010's review round 1. Its citations were checked
per path through `git diff 89c9ee9a 8314d670`, every moved one re-read with `grep -n`/`sed -n`
at `8314d670`:

- `plugin/crew/CONFIG.md` - the §20 edit is below the descope limitation, so `:2251-2258` holds.
- `sabotage_autopilot.py` - `len(POLICY_MUTATIONS)` 27 -> 33 (corrected above),
  `len(AUTOPILOT_MUTATIONS)` 31; `sabotage.py` did not change (`:77`, `:3049` hold).
- `.crew/verify.json` did not change; rules 27 and 28 still map the changed files.
- `test_crew_autopilot.py`, `test_crew_autopilot_policy.py`, `test_scope_guard.py` - cited by
  name only.
- `35fcebcb` (the guard's `_reading_refusal` split) changed one `POLICY_MUTATIONS` anchor string in
  `sabotage_autopilot.py` in place; `:167` and the 33 / 31 counts hold. Re-anchored there.

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

## Re-anchor provenance - `f0b12ee6` + `74f52fae` -> `12682e41`, 2026-09-27 (T-0021 lands on T-0042's main)

`6df1231a` merges T-0021's reviewed head `74f52fae` into main `f0b12ee6` (T-0042 landed as crew
1.0.43, PR #242), and `12682e41` bumps crew to 1.0.44. The two sides share no source file: the
paths both changed since `502cb137` are `CHANGELOG.md`, `TODO.md`, `.crew/verify.json`,
`plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, the version files and
the refresh artifacts. The conflicting provenance sections keep both sides, T-0042's first. Every
`path:N` citation in the body, and every bare `:N` that follows a path, was mapped from the side
its line came from onto the merged tree with a line diff (`git show <side>:<path>` against the
merge); each one that moved was re-read with `sed -n` on the merge and corrected: the
resume registration in `plugin/crew/tests/sabotage.py` is appended at `:3050` (was `:3049` on
T-0042's side; the `MUTATIONS +=` statement at `:3048-3050` now ends with `TRACKER_MUTATIONS`),
and the descoped process-group limitation is `plugin/crew/CONFIG.md:2254-2261` (was `:2249-2256`
on T-0042's side, `:2200-2207` on T-0021's). The resume rule's description keeps T-0042's
figures (62s, 72 mutations), which is what the merged `.crew/verify.json` records.
`.crew/verify.json` is 313 lines and 29 rules, T-0021's tracker rule last at `:301-308`. No test
suite was executed for this note.

## Re-anchor provenance - `6f96e627` -> `eba11657`, 2026-09-26 (T-0023)

`6f96e627` -> `1e0706ac` touched only refresh artifacts. Of the cited paths,
`git diff --name-only 1e0706ac eba11657` returns `.crew/verify.json`, `plugin/crew/CONFIG.md`,
`plugin/crew/tests/sabotage.py`, `.claude-plugin/marketplace.json` and `CHANGELOG.md`:

- `.crew/verify.json` - rule 27 (T-0023) appended at `:289-297`, the closing `}` of rule 26 at
  `:288` gaining the comma; `:3`, `:39-49`, `:69-78`, `:152-157`, `:167-172`, `:181-185`, `:251`,
  `:252-268`, `:270-280` and `:281-288` stand; `default`/`unmapped` `:291`/`:292` ->
  `:300`/`:301`. Re-measured with `json.load`/`wc -l` (28, 302).
- `plugin/crew/tests/sabotage.py` - `ROUTE_MUTATIONS` imported at `:78`, pushing the
  `MUTATIONS +=` statement from `:3047-3049` to `:3048-3050`; `REFRESH_MUTATIONS` is on `:3049`,
  `RESUME_MUTATIONS`, `AUTOPILOT_MUTATIONS` and `ROUTE_MUTATIONS` on `:3050`. `:71`, `:75`, `:76`,
  `:77` hold.
- `plugin/crew/CONFIG.md` - one table row inserted above it moved the process-group-kill
  limitation `:2029-2036` -> `:2030-2037` (mapped by line diff and re-read); §21 was appended at
  the end.
- `marketplace.json`, `CHANGELOG.md` - cited by name only.

Rule 27's suite was run for its `why` figure (168 passed, 9.9s); `sabotage.py` restricted to
`ROUTE_MUTATIONS` ran 19 mutations, all `RED (good)`. Nothing else was executed for this note.

## Re-anchor provenance - `2b18f7ab` + `488053fc` -> `a1acd9b7`, 2026-09-27 (T-0023 merge of main)

`3c968175` merges main at `502cb137` (T-0005 landed, its notes anchored `2b18f7ab`) into T-0023 at
`488053fc` (review round 1's fixes); `f6abe8c1` re-sets crew to 1.0.43 and `a1acd9b7` re-prices
`.crew/verify.json` rule 28 in place. Both lines' provenance is above. A citation can only be
wrong at the merge when its file changed on both sides, or when a line from one side cites a file
the other side changed. Each line of this note was classified by origin (main's text or
T-0023's), its citations into such files re-mapped with a line diff from that side's revision to
the merged tree (`502cb137` or `fa4d8cd5`), and each moved one re-read by content with
`grep -n`/`sed -n`; citations the line diff attributed to the wrong file were discarded, not
applied. `.crew/verify.json` changed on both sides: T-0005's cloud-guard rule is rule 6, so T-0023's routing rule is **rule 28** at `:301-309` and the file is 29 rules, 314 lines (`default` `:312`, `unmapped` `:313`); rule 28's `why` was re-priced in `a1acd9b7` (8.5s, 180 passed), in place. `plugin/crew/tests/sabotage.py` changed on T-0023's side only: `:75`-`:78` imports, `MUTATIONS +=` at `:3048-3050` with `REFRESH_MUTATIONS` on `:3049` and the resume, autopilot and route tuples on `:3050`. `plugin/crew/CONFIG.md` changed on both sides and again in `f6abe8c1` (section 10 grew one line), so the process-group-kill limitation is `:2203-2210`. The crew-setup skill is cited by rule membership only.

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
an unrelated path) were discarded rather than applied: `.crew/verify.json` is
322 lines and 30 rules - T-0021's tracker rule 28 at `:301-308`, T-0023's routing rule 29 at
`:309-317`, `default` `:320`, `unmapped` `:321`. `plugin/crew/tests/sabotage.py` imports both
sibling tuples (`:78` tracker, `:79` route) and its `MUTATIONS +=` statement moved
`:3048-3050` -> `:3050-3052` (refresh at `:3051`; resume, autopilot, tracker and route at
`:3052`); the sibling-module comment above it names T-0023's route mutations and grew by one
line (3381 lines, under `.pylintrc`'s 3400). The descoped process-group limitation is
`plugin/crew/CONFIG.md:2256-2263` (`:2248-2255` on main's side, `:2203-2210` on T-0023's).
The resume rule keeps T-0042's figures (62s, 72 mutations), which is what the merged
`.crew/verify.json` records. The route and tracker suites ran on the merge (part of the 588
passed above); the sabotage runner was not executed for this note.

## Re-anchor provenance - `6f96e627` -> `5536c2c8`, 2026-09-26 (T-0018)

`crew_refresh_check.py --root . --ticket T-0018` named this note. Of the paths it cites,
`git diff --name-only 6f96e627 5536c2c8` returns `.crew/verify.json`, `CHANGELOG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/tests/sabotage_autopilot.py` and
`plugin/crew/tests/test_crew_autopilot.py`; `plugin/crew/tests/sabotage.py` did not change, so
`:71`, `:75`-`:77` and `:3047-3049` stand. Each changed file, re-read:

- `.crew/verify.json` - rule 26 gained `test_crew_autopilot_status.py` in `paths` and `run`, 5s ->
  6s, and a new `why`: `:281-288` -> `:281-289`, `default`/`unmapped` `:291`/`:292` ->
  `:292`/`:293`. Rules 0-25 did not move. Re-measured with `json.load`/`wc -l` (27, 294).
- `sabotage_autopilot.py` - a module-docstring paragraph moved `AUTOPILOT_MUTATIONS` `:19` ->
  `:25`; `STATUS_MUTATIONS` (eight) follows it and is appended to it on the file's last line.
- `test_crew_autopilot.py` - the anchor test accepts either autopilot test file, and
  `test_status_sabotage_is_registered_with_sabotage_py` is new.
- `CHANGELOG.md`, `BUDGETS.md` - cited by name only.

No suite or gate was executed by this note; rule 26's suite and `sabotage.py` were run for the
ticket, not for this refresh.

## Re-anchor provenance - `5536c2c8` -> `4ff7e764`, 2026-09-26 (T-0018 review round 1)

`crew_refresh_check.py --root . --ticket T-0018` named this note. Of the paths it cites,
`git diff --name-only 5536c2c8 4ff7e764` returns `CHANGELOG.md`, `plugin/crew/tests/sabotage_autopilot.py`
and `plugin/crew/tests/test_crew_autopilot.py`; `plugin/crew/tests/sabotage.py` and
`.crew/verify.json` did not change, so `sabotage.py:77`, `:3049` and rule 26 `:281-289` stand.

- `sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`; `STATUS_MUTATIONS` (`:164`) grew
  from eight to 22 entries, one per round-1 guard branch, and is still appended to
  `AUTOPILOT_MUTATIONS` on the file's last line (`:256`).
- `test_crew_autopilot.py` - `test_status_sabotage_is_registered_with_sabotage_py` now expects 22.
- `CHANGELOG.md` - cited by name only.

The 22 `STATUS_MUTATIONS` were run through `sabotage.py`'s harness for the ticket, not for this
refresh.

Re-verified per-path from `4ff7e764` to `29a987b0` (T-0018 review round 2).
`git diff --name-only 4ff7e764 29a987b0` returns `.crew/verify.json`, `CHANGELOG.md`,
`plugin/crew/tests/sabotage_autopilot.py`, `plugin/crew/tests/test_crew_autopilot.py` and
`plugin/crew/tests/test_crew_autopilot_status.py`; `plugin/crew/tests/sabotage.py` did not change,
so `sabotage.py:77` and `:3049` stand.

- `.crew/verify.json` - rule 26's `seconds` (6 -> 9) and `why` changed in place; `:281-289` holds,
  294 lines, 27 rules. The price line in the rule-26 paragraph above is rewritten to match.
- `sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`, `STATUS_MUTATIONS` still `:164`;
  it grew from 22 to 28 entries, one per round-2 guard branch, and is still appended to
  `AUTOPILOT_MUTATIONS` on the file's last line (`:256` -> `:281`).
- `test_crew_autopilot.py` - `test_status_sabotage_is_registered_with_sabotage_py` now expects 28.
- `test_crew_autopilot_status.py` and `CHANGELOG.md` - cited by name only.

The 28 `STATUS_MUTATIONS` were run through `sabotage.py`'s harness for the ticket, not for this
refresh.

Re-verified per-path from `29a987b0` to `c87ac3f4` (T-0018 review round 3).
`git diff --name-only 29a987b0 c87ac3f4` returns `.crew/verify.json`, `CHANGELOG.md`,
`plugin/crew/commands/autopilot.md`, `plugin/crew/hooks/scripts/crew_autopilot.py`,
`plugin/crew/tests/sabotage_autopilot.py`, `plugin/crew/tests/test_crew_autopilot.py` and
`plugin/crew/tests/test_crew_autopilot_status.py`; `plugin/crew/tests/sabotage.py` did not change,
so `sabotage.py:77` and `:3049` stand.

- `.crew/verify.json` - rule 26's `seconds` (9 -> 11) and `why` changed in place; `:281-289` holds,
  294 lines, 27 rules. The price line in the rule-26 paragraph above is rewritten to match.
- `sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`, `STATUS_MUTATIONS` still `:164`;
  it grew from 28 to 37 entries, one per round-3 guard branch, and is still appended to
  `AUTOPILOT_MUTATIONS` on the file's last line (`:281` -> `:318`).
- `test_crew_autopilot.py` - `test_status_sabotage_is_registered_with_sabotage_py` now expects 37.
- `test_crew_autopilot_status.py`, `autopilot.md`, `crew_autopilot.py` and `CHANGELOG.md` - cited
  by name only.

The 37 `STATUS_MUTATIONS` were run through `sabotage.py`'s harness for the ticket, not for this
refresh.

Re-verified per-path from `c87ac3f4` to `4755ae1a` (T-0018 round-3 mutation retarget).
`git diff --name-only c87ac3f4 4755ae1a` returns `plugin/crew/tests/sabotage_autopilot.py` and
`plugin/crew/tests/test_crew_autopilot_status.py`. `sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS`
still `:25`, `STATUS_MUTATIONS` still `:164`, still 37 entries; one round-1 entry was relabelled
and pointed at a new test (a three-line comment added), so the append on the file's last line
moved `:318` -> `:321`. `.crew/verify.json` and `sabotage.py` did not change.

## Re-anchor provenance - `2b18f7ab` + `4755ae1a` -> `b1ae1500`, 2026-09-27 (T-0018 round 4, main merge)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `550aa306`, the merge of
main (`502cb137`, crew 1.0.42) into the T-0018 branch, and `b1ae1500`, the crew 1.0.43 bump. The
merge's conflicts here were resolved by keeping main's rule numbering (T-0005's rule 6 moved every
later rule up by one) and T-0018's widened autopilot rule. Re-read on `git show b1ae1500:<path>`:

- `.crew/verify.json` - 28 rules, 306 lines (main's 305 plus the autopilot rule's added
  `test_crew_autopilot_status.py` path line): `default` `:304`, `unmapped` `:305`, the
  `.claude/rules/` sync rule 24 `:263`, refresh-check rule 25 `:264-280`, auto-resume rule 26
  `:282-292`, autopilot rule 27 `:293-301` (`seconds` 11, `why` unchanged since `4755ae1a`).
- `plugin/crew/tests/sabotage.py` - unchanged by T-0018: `:76`, `:77` and `:3049` hold.
- `plugin/crew/tests/sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still at `:25`; round 4
  appended three entries to `STATUS_MUTATIONS` (40 now), which
  `test_crew_autopilot.py::test_status_sabotage_is_registered_with_sabotage_py` counts.
- `plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/README.md`, `CHANGELOG.md` and the
  version files changed too; this note cites them by name or rule only.

No suite or gate was executed by this note.

## Re-anchor provenance - `b1ae1500` -> `9e21a0d9`, 2026-09-27 (T-0018 sabotage retarget, version re-set)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `a0158b3d`, which pointed
`sabotage_autopilot.py`'s route and status `-B` mutations at
`test_every_autopilot_invocation_in_command_skips_bytecode` (the behavioural test they named stayed
green once round 4's `__main__` guard landed), then `9a1394ef` / `9e21a0d9`, which stepped the crew
version back and re-set it to 1.0.43 last. Re-read on `git show 9e21a0d9:<path>`:

- `plugin/crew/tests/sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`,
  `STATUS_MUTATIONS` still `:164`, still 40 entries (two retargeted, none added or removed), the
  `+=` at `:340`.
- The version files and `CHANGELOG.md` are byte-identical to `b1ae1500`'s.

No suite was run by this note.

## Re-anchor provenance - `9e21a0d9` -> `89f73d79`, 2026-09-27 (T-0018 review round 5)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `96d4fa1c` (review round
5's three FIX lines) touched `crew_autopilot.py`, `sabotage_autopilot.py` and both autopilot test
files, then `a943f361` / `89f73d79` stepped the crew version back and re-set it to 1.0.43 last.
Re-read at `89f73d79`:

- `plugin/crew/tests/sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`,
  `STATUS_MUTATIONS` still `:164`, now 44 entries (four added, one re-anchored onto the moved
  `_takes` call), still appended to `AUTOPILOT_MUTATIONS` on the file's last line (`:358`).
- `plugin/crew/tests/sabotage.py` did not change: the import at `:77` and the append at `:3049`
  hold.
- `test_crew_autopilot.py` - `test_status_sabotage_is_registered_with_sabotage_py` now expects 44.
- `.crew/verify.json` did not change; rule 27's paths and command hold.

No suite was run by this note.

## Re-anchor provenance - `89f73d79` -> `0834aaf9`, 2026-09-27 (T-0018 plan step 7)

`crew_refresh_check.py --root . --ticket T-0018` named this note after `88f52aa6`. That commit
added one must-block test to `plugin/crew/tests/test_crew_autopilot_status.py` and pointed one
`STATUS_MUTATIONS` entry at it, a one-line change in place in
`plugin/crew/tests/sabotage_autopilot.py`. After it, `5c6cadee` / `0834aaf9` stepped the crew
version back and set 1.0.43 again as the last change. Re-read at `0834aaf9`:

- `plugin/crew/tests/sabotage_autopilot.py` - `AUTOPILOT_MUTATIONS` still `:25`,
  `STATUS_MUTATIONS` still `:164`, still 44 entries (one retargeted, none added), the `+=` still
  at `:358`, 358 lines.
- `plugin/crew/tests/test_crew_autopilot_status.py` - cited by name only, so no line citation
  moved.
- `crew_autopilot.py`, `plugin/crew/tests/sabotage.py`, `.crew/verify.json` and the version files
  are byte-identical to `89f73d79`'s.

No suite was run by this note.

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
Corrected here: `.crew/verify.json` is 314 lines and 29 rules (rule 27 `:293-301` with T-0018's
price and test file, rule 28 `:302-309`, `default` `:312`, `unmapped` `:313`), read with
`json.load`; `sabotage.py`'s `MUTATIONS +=` statement is `:3048-3050`, imports `:76-78`;
`sabotage_autopilot.py` holds `AUTOPILOT_MUTATIONS` `:25`, `STATUS_MUTATIONS` `:164`, appended at
`:358`. No suite was executed for this note; the landing's suite runs are reported in its PR.

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
Corrected here: `.crew/verify.json` is 323 lines and 30 rules (rule 27 `:293-301`, rule 28
`:302-309`, rule 29 `:310-318`, `default` `:321`, `unmapped` `:322`), read with `json.load`;
`sabotage.py`'s `MUTATIONS +=` statement is `:3050-3052`, imports `:76-79`. No suite was executed
for this note; the landing's suite runs are reported in its PR.

## Re-verify provenance - `6f96e627` -> `a2802526`, 2026-09-26 (T-0024)

`git diff --name-only 6f96e627..a2802526 -- <the paths this note cites>` returns
`.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`,
`plugin/crew/hooks/scripts/crew_ticket.py` and `plugin/crew/tests/sabotage.py`, plus the new
`sabotage_approval.py`/`test_approval_group.py`. `verify-gate.sh`/`.ps1`, `verify_record.py`,
`scripts/check-marketplace.py`, `scripts/check_instructions.py`, `plugin/crew/CONFIG.md`,
`_verify/*`, `CLAUDE.md` and the CI workflows did not change, so their citations stand unread.

- `.crew/verify.json` - rule 27 appended at `:290-297`; rule 26 `:281-288` holds (its last line
  gained only the separating comma); `:3`, `:39-49`, `:152-157`, `:167-172`, `:181-185`, `:251`,
  `:252-268` and `:270-280` stand; `default`/`unmapped` `:291`/`:292` -> `:300`/`:301`.
  Re-measured with `json.load`/`wc -l` (28, 302).
- `plugin/crew/tests/sabotage.py` - `APPROVAL_MUTATIONS` imported at `:78`, pushing the
  `MUTATIONS +=` statement from `:3047-3049` to `:3048-3050`: `REFRESH_MUTATIONS` is now on
  `:3049`, `RESUME_MUTATIONS`/`AUTOPILOT_MUTATIONS`/`APPROVAL_MUTATIONS` on `:3050`. `:71`, `:75`,
  `:76`, `:77` hold.
- `crew_ticket.py` - `approve(..., expect=None)` at `:686` and `precheck` at `:765`; `parse_risk`
  `:505` holds. Now named by rules 10 and 27.
- `marketplace.json`, `CHANGELOG.md`, `BUDGETS.md` - cited by name only.

Executed for this note: `python3 scripts/check-marketplace.py` at `a2802526` (`all checks
passed`). Rule 27's suite and `sabotage.py` were run by the T-0024 lane's verification, not by this
note; their results are in that ticket's review record, not restated here.

Re-verified per-path from `a2802526` to `32223b8a` for T-0024's review round 1: of the cited paths
only `plugin/crew/tests/sabotage_approval.py` (nine mutations added for the round-1 fixes,
three re-anchored, one re-targeted to the test that holds its single-id case, the expanded-form
break-check mutation deleted with its code; 52 by `len()`,
`APPROVAL_MUTATIONS` still at `:32`), `marketplace.json` and `CHANGELOG.md` (cited by name only)
changed. `sabotage.py`'s registration `:78`/`:3050` and `.crew/verify.json` did not change.

Re-verified per-path from `32223b8a` to `f8671fdc` for T-0024's successor step 6: of the cited paths
`plugin/crew/tests/sabotage_approval.py` (ten mutations added for the round-2 fixes, four
re-anchored; 61 by `len()`, `APPROVAL_MUTATIONS` still at `:32`), `crew_ticket.py` (`precheck`
`:765` -> `:793`; `approve` `:686` and `parse_risk` `:505` hold; still rules 10 and 27),
`marketplace.json`, `CHANGELOG.md` and `BUDGETS.md` (cited by name only) changed. `sabotage.py`'s
registration `:78`/`:3050` and `.crew/verify.json` did not change.

Re-verified per-path from `f8671fdc` to `45345812` for T-0024's review round 3: of the cited paths
`plugin/crew/tests/sabotage_approval.py` (four mutations added, three re-anchored, one retargeted;
65 by `len()`, still at `:32`), `crew_ticket.py` (`precheck` `:793` -> `:810`; `approve` `:686`,
`parse_risk` `:505` hold), `marketplace.json` and `CHANGELOG.md` (by name only) changed.
`sabotage.py` `:78`/`:3050`, `.crew/verify.json` and `BUDGETS.md` did not change.

## Re-anchor provenance - `65bb3330` + `474aea8b` -> `8de3c669`, 2026-09-27 (T-0024 lands on T-0018's main)

`affa22a5` merges T-0024's reviewed head `474aea8b` (review round 4 FINDINGS, owner-accepted) into
main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245), and `8de3c669` bumps crew to 1.0.48.
The two sides share no source file: T-0024 changed `approval_hook.py`, both approval-hook wrappers,
`crew_ticket.py`, `commands/approve.md` and their tests; both sides changed `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md` (merged cleanly), `plugin/crew/tests/sabotage.py`,
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's first.
Corrected here: `.crew/verify.json` is 31 rules and 332 lines (`default` `:330`, `unmapped`
`:331`); T-0024's rule is rule 30 at `:320-327` (rule 27 on its branch); `crew_ticket.py` is named
by rules 11 and 30. `sabotage.py` imports `sabotage_approval` at `:80`, after main's tracker `:78`
and route `:79`, so the `MUTATIONS +=` statement is `:3051-3053`: `REFRESH_MUTATIONS` on `:3052`,
and resume, autopilot, tracker, route and approval on `:3053`. Every other body citation was
checked against both sides' content by script and holds. No test suite was executed for this note.

**Re-anchored `53f5482c` -> `d3a1c77e` on 2026-09-27 (T-0072, crew 1.0.44).** `d3a1c77e` is T-0072's version commit on `T-0072-build`, after it merged origin/main `f0b12ee6` (T-0042's landing) with a merge commit. `git diff --name-only 53f5482c d3a1c77e` over the cited paths returns only T-0072's changes and the version files. T-0072 edited in place, with no line added or removed, `crew_state.py` (`:1084-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,612 lines across 121 files), `plugin/PLUGINS.md` (`:14` 1.0.44, the `/crew:autopilot` row), `.claude-plugin/marketplace.json` (`:218` 1.0.44), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It added lines to `crew_autopilot.py` (the `deploy-allowed` docstring section and functions, 694 -> 837 lines), `CONFIG.md` (+1 at the leaf paragraph, +1 in the key table, +1 in §20's table, a closing §20 section), `CHANGELOG.md` (+32 at the top) and the autopilot tests. Of the paths this note cites, `.crew/verify.json` (rule 27 in place: `paths` and `run` gained `test_crew_autopilot_deploy.py`, `seconds` 5 -> 6, a new `why`; still `:293-300`, 28 rules), `plugin/crew/CONFIG.md` (the process-group-kill limitation `:2249-2256` -> `:2251-2258`, same text by checksum), `plugin/crew/tests/sabotage_autopilot.py` (`AUTOPILOT_MUTATIONS` `:19` -> `:21`; `DEPLOY_MUTATIONS`, 24, appended at `:264`) and `plugin/crew/tests/test_crew_autopilot.py` changed; corrected above. The restricted sabotage run over `AUTOPILOT_MUTATIONS` (55 mutations) printed `SABOTAGE SUITE: PASS` on T-0072's branch at `c1eb45b7`'s code, which the merge did not change.

**Re-anchored `d3a1c77e` -> `e30af7f9` on 2026-09-27 (T-0072 review round 1).** `e30af7f9` is T-0072's review-round-1 fix commit on `T-0072-build`. `git diff --name-only d3a1c77e e30af7f9` returns `.crew/verify.json` (rule 27's `why` re-measured in place, still `:293-300`), `CHANGELOG.md` (the 1.0.44 entry, four lines reworded, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, now 18,615 lines across 121 files; `check-marketplace.py` prints `all checks passed`), `plugin/crew/CONFIG.md` (+3 lines in §20's closing section, at `:2317`; nothing cited above it moved, `:2251-2258` holds), `plugin/crew/hooks/scripts/crew_autopilot.py` (+24 lines: the docstring gains a line at `:88`, `_deploy_verdict` moves its `cloud_guard` import below the incident check, `_safe_text` and `_crash_reason` are new), `plugin/crew/tests/sabotage_autopilot.py` (+32: `CLOUD` at `:18`, six mutations) and `plugin/crew/tests/test_crew_autopilot_deploy.py`, plus the refresh artifacts of the previous pass. No crew version change (1.0.44). Corrected above: `sabotage_autopilot.py`'s `AUTOPILOT_MUTATIONS` `:21` -> `:22` and the `DEPLOY_MUTATIONS` append `:264` -> `:296`; rule 27's measured figure (5.3s, 283 passed, under the heavy lock). Every `.crew/verify.json` line citation holds (28 rules, rule 27 `:293-300`). The restricted sabotage run over `AUTOPILOT_MUTATIONS` (61, 30 of them `DEPLOY_MUTATIONS`) printed `SABOTAGE SUITE: PASS`.

**Re-anchored `e463ca53` -> `715a8c2f` on 2026-09-27 (T-0072 merged onto `bebbb97f`, crew 1.0.47).** `715a8c2f` is T-0072's crew 1.0.47 version commit on `T-0072-build`, on top of `e658bb04`, its merge of origin/main `bebbb97f` (T-0021 and T-0023 landed; this note was anchored at T-0023's `e463ca53`). `git diff --name-only e463ca53 715a8c2f` over the cited paths returns only T-0072's changes, the neighbour test T-0072 added after the merge, and the version files. Against main, T-0072 edits in place, with no line added or removed, `crew_state.py` (`:1086-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (`:825`, the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,910 lines across 126 files), `plugin/PLUGINS.md` (`:14` 1.0.47, `:128` the `/crew:autopilot` row), `plugin/crew/skills/crew-setup/SKILL.md` (`:170`), `.claude-plugin/marketplace.json` (`:218` 1.0.47), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It adds lines to `crew_autopilot.py` (694 -> 861), `CONFIG.md` (+3 at the leaf paragraph `:130`, +1 at `:803`, +1 at `:2282`, and the closing §20 section at `:2297`, 41 lines, with T-0023's §21 after it), `CHANGELOG.md` (+31 at `:7`, T-0072's entry above T-0023's), `config.template.json` (+1 at `:205`), `test_crew_config.py` (+3; the count assertion is `:282`, 123), `test_crew_autopilot.py` (+2), `sabotage_autopilot.py` (+140) and the new `test_crew_autopilot_deploy.py`. Corrected above: `sabotage_autopilot.py`'s `AUTOPILOT_MUTATIONS` is `:22`, with `DEPLOY_MUTATIONS` (`:164`) appended at `:296`; `sabotage.py` imports it at `:77` and appends it at `:3052`; the descoped process-group limitation is `plugin/crew/CONFIG.md:2254-2261` (`:2250-2257` on main, +4 from T-0072's leaf-paragraph and key-table lines). `.crew/verify.json` rule 27 `:293-300` holds, with T-0072's `why`, `seconds` 6 and `test_crew_autopilot_deploy.py` in its paths and run line; rules 28 and 29 `:301-317` hold. No suite was executed for this note.

**Re-anchored `65bb3330` -> `21429244` on 2026-09-27 (T-0072 merged onto `67caa4b8`, crew 1.0.48).** `21429244` is T-0072's crew 1.0.48 version commit on `T-0072-build`, on top of `80d4073b`, its merge of origin/main `67caa4b8` (T-0018 landed; this note was anchored at T-0018's `65bb3330`, and nothing outside the refresh artifacts changed between `65bb3330` and `67caa4b8`). Main's side of this note was taken in the merge and T-0072's earlier refresh replayed on top (`git apply --3way` of `bebbb97f..b1ec6877`); every citation into a file either side changed was mapped with a line diff (main -> merged for main's text, `b1ec6877` -> merged for T-0072's) and each one that moved was re-read with `sed -n`. `git diff --name-only 65bb3330 21429244`, outside the refresh artifacts, returns only T-0072's files: `crew_autopilot.py` (1063 -> 1230 lines: the `deploy-allowed` docstring section and functions, and its parser at `:1140`), `CONFIG.md` (+56), `CHANGELOG.md` (+31 at the top), `commands/autopilot.md` (the settings sentence rewrapped at `:44-47`, still 100 lines), `crew_state.py` (line-neutral at `:1086-1090`), `config.template.json`, `crew-setup/SKILL.md` (`:170`), `.crew/verify.json` (rule 27 `:293-301`, same lines: `test_crew_autopilot_deploy.py` joins its paths and run), the version files (1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), `plugin/crew/BUDGETS.md:11` (18,905 lines across 126 files, re-measured on the merge), and the autopilot tests. Corrected here: rule 27 now names `test_crew_autopilot_deploy.py` and `test_crew_autopilot_status.py` together, priced 16s from its re-measured `why`; `sabotage_autopilot.py`'s `AUTOPILOT_MUTATIONS` is `:28`, with `DEPLOY_MUTATIONS` appended at `:302` and `STATUS_MUTATIONS` at `:498`. `.crew/verify.json` is still 323 lines and 30 rules (`json.load`). No suite was executed for this note; the suite runs are reported with the build.

**Re-anchored `21429244` -> `53855ea5` on 2026-09-27 (T-0072 review round 3).** `53855ea5` is T-0072's review-round-3 fix commit on `T-0072-build`. `git diff --name-only 21429244 53855ea5`, outside the refresh artifacts, returns only T-0072's files: `.crew/verify.json` (rule 27's `seconds` 16 -> 20 and its `why`, in place, still `:293-301`), `CHANGELOG.md` (T-0072's 1.0.48 entry, +4 lines, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, in place: 18,908 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (one §20 table row edited in place at `:2309`, +3 lines after `:2327`), `plugin/crew/hooks/scripts/crew_autopilot.py` (1230 -> 1252 lines: +2 in the docstring at `:90-97`, `_cannot_exclude` and `_incident(root)` at `:702-718`, `_cli_value` at `:1132`, the `deploy-allowed` printing at `:1214-1219`), `plugin/crew/tests/sabotage_autopilot.py` (+36 at `:300-335`: eight `DEPLOY_MUTATIONS`; one re-anchored in place at `:256`) and `plugin/crew/tests/test_crew_autopilot_deploy.py`. No crew version change (1.0.48). Of the paths this note cites, `.crew/verify.json` (rule 27's price and `why`, in place; 30 rules, `:293-301` holds), `plugin/crew/tests/sabotage_autopilot.py` and `plugin/crew/BUDGETS.md:11` changed; `plugin/crew/CONFIG.md`'s cited `:2248-2261` sit above the change and hold. Corrected above: rule 27 priced 20s from its re-measured `why` (19.5s, 483 passed, measured for this fix under heavy-run); `DEPLOY_MUTATIONS` appended at `:338` and `STATUS_MUTATIONS` at `:534` (`AUTOPILOT_MUTATIONS` still `:28`). The restricted sabotage run over `AUTOPILOT_MUTATIONS` (113) printed `SABOTAGE SUITE: PASS` at `53855ea5`'s code.

**Re-anchored `8de3c669` -> `80326b1d` on 2026-09-27 (T-0072 merged onto `d2fbd408`, then review round 4's redesign, crew 1.0.49).** `ba7d5c52` merged origin/main `d2fbd408` (T-0024 landed as crew 1.0.48 at `8de3c669`) into `T-0072-build` and took main's side of every code map; T-0072's earlier refresh (`git diff 67caa4b8 2fa75f79 -- .crew/codemap/`) was replayed on top with `git apply --3way`, conflicting provenance sections keeping both sides, main's first. `80326b1d` is T-0072's crew 1.0.49 version commit, after the redesign `35733d76` (one root per answer, a tri-state path probe, a two-stage CLI fallback), its sabotage `fa4c8397`, its docs `8a40dd2c` and the rule-27 re-price `37fa7c97`. `git diff --name-only 8de3c669 80326b1d`, outside the refresh artifacts, returns only T-0072's files: `.claude-plugin/marketplace.json` (`:218` 1.0.49), `.crew/verify.json` (rule 27 in place, `:293-301`, `seconds` 16), `CHANGELOG.md` (T-0072's entry, +45 at the top), `plugin/PLUGINS.md` (`:14` 1.0.49, `:128` the `/crew:autopilot` row in place), `plugin/crew/.claude-plugin/plugin.json` (`:3`), `plugin/crew/BUDGETS.md` (`:11`, 18,939 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (2328 -> 2382 lines: the leaf paragraph `:130`, the key table `:803`, the `prodUnattended` row `:1261`, `:2282`, and section 20's closing "Production without asking" block from `:2297`), `plugin/crew/README.md` (`:848` in place), `plugin/crew/commands/autopilot.md` (`:45-48` in place, 100 lines), `crew_autopilot.py` (1312 lines), `crew_state.py` (line-neutral at `:1086-1090`), `crew-setup/SKILL.md` and `config.template.json` (the leaf), `test_crew_config.py` (`:282` asserts 123), `sabotage_autopilot.py`, `test_crew_autopilot.py` and `test_crew_autopilot_deploy.py`. Rule 27's price is 16s (15.5s wall, 527 passed, after the round-4 redesign), in place at `.crew/verify.json:293-301`; `sabotage_autopilot.py` now defines `AUTOPILOT_MUTATIONS` at `:28`, appends `DEPLOY_MUTATIONS` (`:170`, 59 entries) at `:443` and `STATUS_MUTATIONS` at `:639`, and `sabotage.py` still imports it at `:77` and appends it at `:3053` (main's line; T-0072's side had said `:3052`). The body is corrected to those lines. The restricted sabotage run over `AUTOPILOT_MUTATIONS` (133 RED) is recorded in the PR, not executed for this note.

**Re-anchored `80326b1d` -> `1b5b6560` on 2026-09-27 (T-0072 test fix).** `git diff --name-only 80326b1d 1b5b6560`, outside the refresh artifacts, returns only `plugin/crew/tests/test_crew_autopilot_deploy.py` (the layer_state repro now patches `crew_config.layer_state`, not `crew_state.read_text`, which `test_module_split.py` forbids) and the three version files, stepped back to 1.0.48 and re-set to 1.0.49 so the version stays the last `plugin/crew/` commit (same content as at `80326b1d`). This note cites that test file by name only. No citation moved. Nothing was executed for this note.

**Re-anchored `1b5b6560` -> `a4eb2f55` on 2026-09-28 (T-0072 merged onto `5050ea3b`, crew 1.0.50).** `a4eb2f55` is T-0072's crew 1.0.50 version commit on top of its merge of origin/main `5050ea3b` (T-0077 landed as crew 1.0.49 at `fc289446`; shipstation 1.1.1). The merge was clean. `git diff --name-only 1b5b6560 a4eb2f55`, outside the refresh artifacts, returns main's T-0077 and shipstation files - `crew_tracker.py` (+123: Windows now holds a vault write's directories by handle, `_hold_dirs` / `_held_check` replace `_parent_check`), `crew_autopilot.py` (`_rel` +6 at `:170`, so every later line moves by 6), `sabotage_autopilot.py` (+5 inside `STATUS_MUTATIONS`; the `+=` append moved `:639` -> `:644`), `sabotage_tracker.py` (87 `TRACKER_MUTATIONS`, was 81), `plugin/crew/README.md` (`:1493-1495` in place), `test_crew_tracker.py`, `test_crew_autopilot.py`, `test_crew_autopilot_status.py`, `skills/shipstation/*` - and the version files (1.0.50 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) and `CHANGELOG.md` (T-0077's and shipstation's entries under T-0072's). `sabotage_autopilot.py`'s `STATUS_MUTATIONS` append is `:644`, and `TRACKER_MUTATIONS` counts 87; `sabotage.py` `:77-78` and `:3053` hold, as do `.crew/verify.json`'s rule lines (it did not change). The body is corrected to those. The merged tree's restricted sabotage run over `AUTOPILOT_MUTATIONS` and `TRACKER_MUTATIONS` (221 RED) is recorded in the PR, not executed for this note.

**Re-anchored `a4eb2f55` -> `0f488706` on 2026-09-28 (T-0072 review round 5).** `0f488706` is T-0072's review-round-5 fix commit. `git diff --name-only a4eb2f55 0f488706`, outside the refresh artifacts (`0282cb5c`, `37fa2322`), returns only T-0072's files: `plugin/crew/hooks/scripts/crew_autopilot.py` (`_resolve_root` +4 at `:729`, refusing a root that is not text, so every line after it moves by 4: `_layer_problem` `:744`, `_decide` `:759`, `deploy_allowed` `:836`, `_failure` `:1170`, `_cli_deploy` `:1194`, `main` `:1225`; `--json` dumps without indent, in place; the module docstring re-worded in place, `:87-104`), `plugin/crew/tests/sabotage_autopilot.py` (+30 inside `DEPLOY_MUTATIONS`, 64 entries by `len()`: the `AUTOPILOT_MUTATIONS + DEPLOY_MUTATIONS` append moved `:443` -> `:473`, `STATUS_MUTATIONS`' `:644` -> `:674`), `plugin/crew/tests/test_crew_autopilot_deploy.py`, `plugin/crew/CONFIG.md` (one sentence in section 20 re-worded in place, `:2331-2333`, no line added) and `CHANGELOG.md`. Rule 27's `DEPLOY_MUTATIONS` and `STATUS_MUTATIONS` append lines were re-mapped (`:473`, `:674`) and re-read; `sabotage.py` did not change, so `:77` and `:3053` hold. The `CONFIG.md` citations sit above `:2331` and did not move. No suite was executed for this note.

## Re-anchor provenance - `65bb3330` + `35fcebcb` -> `c817782f`, 2026-09-27 (T-0010-solo merges `67caa4b8`)

`c817782f` is T-0010's crew 1.0.48 version commit on top of `d1e119d2`, T-0010-solo's merge of
origin/main `67caa4b8` (T-0018 landed as 1.0.47; its code maps anchored `65bb3330`), and
`3e2c9962`, the reconciliation under the owner's approve carve-out. Main's side of this note was
mapped from `65bb3330`, T-0010's side from its own anchor (`35fcebcb`), to `c817782f` with `difflib`
over every cited file, a bare `:N` taken as the last path named in its section; sections headed
provenance (and localgpu's re-derivation record) were left as written. The two mapped texts were
then merged three-way from `f0b12ee6`. Between `65bb3330` and `c817782f` the cited paths that
changed are T-0010's: `crew_autopilot.py`, `crew_ticket.py`, `scope_guard.py`, `crew_state.py`
(four `AUTOPILOT_DEFAULTS` lines at `:1094`, so every later line moved by 4), `commands/autopilot.md`,
the version files, `BUDGETS.md`, README, CONFIG.md, the tests and sabotage modules, and
`.crew/verify.json` (rule 28 inserted at `:302-308`, so rules 29 and 30 moved down by 7).

Re-read by hand: `.crew/verify.json` (330 lines, 31 rules, `default` `:328`,
`unmapped` `:329`), rules 27-30 with their prices (rule 27 13s, rule 28 20s, both re-measured
for T-0010's merge), and `plugin/crew/tests/sabotage.py`'s registration (`:77-79`, the
`MUTATIONS +=` statement at `:3050-3053`, `POLICY_MUTATIONS` on `:3053`).

## Re-anchor provenance - `c817782f` -> `926443d8`, 2026-09-27 (T-0010 review round 3 fixes)

`git diff --name-only c817782f 926443d8` is T-0010's round-3 fix (`caabb005`), the BUDGETS.md
count, the version step-back and re-set, and this refresh. `sabotage_autopilot.py`'s `POLICY_MUTATIONS` `:370` -> `:371` and 39 -> 47 entries,
two of them targeting `plugin/crew/README.md`; the rule-28 paragraph says so. `.crew/verify.json`
did not change, so no rule number or line moved. No test was run by this note.

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

Re-read by hand: `.crew/verify.json` (339 lines, 32 rules, `default` `:337`, `unmapped`
`:338`), rules 27-31 and their line ranges, and `plugin/crew/tests/sabotage.py`'s registration
(`:77-80`, the `MUTATIONS +=` statement at `:3051-3054`: refresh on `:3052`, resume, autopilot,
tracker and route on `:3053`, `POLICY_MUTATIONS` and `APPROVAL_MUTATIONS` on `:3054`).
`POLICY_MUTATIONS` is 54 entries at `plugin/crew/tests/sabotage_autopilot.py:376` (two ported
owner-only refusals and five round-4 fixes added, one anchor moved to the new `elif`); one names
`test_crew_autopilot.py`. `crew_ticket.py` is named by rules 11 and 31. No test was run by this
note.

## Re-anchor provenance - `8de3c669` -> `a6e81869`, 2026-09-27 (T-0079 on its branch)

`T-0079-read` was cut from `67caa4b8`, merged main `d2fbd408` (T-0024 landed; its refresh `fdc54ce9`
changed refresh artifacts only) in `f034ef5c`, and carries T-0079's commits through `a6e81869`
(crew 1.0.49). `git diff --name-only 8de3c669 a6e81869`, refresh artifacts aside, returns T-0079's
files only: `review_verdict.py`, `review_prompt.py`, `review_run.py`, their tests and
`sabotage_review.py`, `agents/reviewer.md`, `plugin/crew/README.md` (line-neutral), `CHANGELOG.md`
and the three version files. Every body citation into those files was compared by script between
`8de3c669` and `a6e81869` at the same line.
Of the cited paths, `.claude-plugin/marketplace.json` (`:218` 1.0.49, in place) and
`plugin/PLUGINS.md` (`:14` 1.0.49, in place) changed; no citation moved. No test suite was executed
for this note.

## Re-anchor provenance - `a6e81869` -> `81685adf`, 2026-09-27 (T-0079 merges main, Step 7, re-bump)

`T-0079-read` gained T-0079's Step 7 (`8f7c62dd`, one `find` string in
`plugin/crew/tests/sabotage_webtest.py`), merged main `f96e9ec9` (T-0077 landed, crew 1.0.49) in
`548ee44e`, and re-bumped crew to 1.0.50 in `81685adf`. `git diff --name-only a6e81869 81685adf`,
refresh artifacts aside, returns that `sabotage_webtest.py`, T-0077's files (`crew_tracker.py`,
`crew_autopilot.py`, `sabotage_tracker.py`, `sabotage_autopilot.py`, `test_crew_tracker.py`,
`test_crew_autopilot.py`, `test_crew_autopilot_status.py`), `plugin/crew/README.md` (line-neutral
on both sides), `CHANGELOG.md` and the three version files. Every body citation of the form
`path:line` into those files was compared by script between `a6e81869` and `81685adf`.
Rule 28's `TRACKER_MUTATIONS` count moves to 87 (read from the tuple, T-0077 added six); the
`sabotage.py:77`, `:78` and `:3053` registrations and `AUTOPILOT_MUTATIONS` `:25` did not move.
Nothing was executed for this note.

**Re-anchored `0f488706` -> `9631c707` on 2026-09-28 (T-0072 landing, crew 1.0.51).** `9631c707` is T-0072's landing bump on `T-0072-land`, after `34af80ef` merged the reviewed `T-0072-build` (`a0978df6`) onto main `e6e10432` (T-0079 landed as crew 1.0.50) and `bf0c513a` re-priced verify rule 27. `git diff --name-only 0f488706 9631c707`, refresh artifacts aside, returns T-0079's files, the three version files, `CHANGELOG.md` and `.crew/verify.json`. The two this note's citations reach changed in place: `.crew/verify.json` `:298` and `:301` (rule 27's `seconds` 16 -> 18 and its `why`, still `:293-301`) and `plugin/crew/README.md` `:735` and `:739` (T-0079's verdict table, line-neutral); no citation moved. The version sentence moves to 1.0.51. No suite was executed for this note.

## Re-anchor provenance - `12682e41` + `d2444be9` -> `e95e5964`, 2026-09-27 (T-0075 merges main)

`e95e5964` is T-0075's crew 1.0.46 bump on top of `e94ce6ce`, the merge of origin/main `db14619c`
(T-0021 landed as 1.0.45) into T-0075's branch; the merge took main's copy of this note and
T-0075's edits were re-applied. Of the cited paths, `git diff --name-only 12682e41 e95e5964`
returns `.crew/verify.json` (rule 7 gained `crew_config_menu.py`, `test_config_menu.py` and
`sabotage_config.py`, +3 lines at `:136-138`, and its `run` adds `test_config_menu.py`; every later
citation moved +3 and was re-read with `sed -n`: rule 9 `:164-169` -> `:167-172`, rule 11
`:179-184` -> `:182-187`, rule 13 `:193-197` -> `:196-200`, rule 24 `:263` -> `:266`, rule 25
`:264-280` -> `:267-283` (its `why` `:280` -> `:283`), rule 26 `:282-292` -> `:285-295`, rule 27
`:293-300` -> `:296-303`, rule 28 `:301-308` -> `:304-311`, `default`/`unmapped` `:311-312` ->
`:314-315`; 29 rules, 316 lines; `:117-127` and `:69-78` hold), `plugin/crew/tests/sabotage.py`
(both sides' sibling imports kept, `CONFIG_MENU_MUTATIONS` at `:79` after `TRACKER_MUTATIONS` at
`:78`, 12 by `len()`; the comment above the `MUTATIONS +=` statement grew a line, so it moved
`:3048-3050` -> `:3050-3052`; `:67`, `:75-78` hold; 3381 lines, under `.pylintrc`'s 3400),
`plugin/crew/CONFIG.md` (T-0075's repo-layer write section and enum note above the limitation, so
`:2248-2255` -> `:2282-2289`, re-read), `README.md` and `CHANGELOG.md` (cited by name only here).
`verify-gate.sh`/`.ps1` and `scripts/check-marketplace.py` did not change. No suite was run for
this note; the suites T-0075 ran are in its ticket evidence.

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
discarded rather than applied. `.crew/verify.json` is 325 lines and 30 rules: T-0075's three rule-7
paths (`:136-138`) push every later rule 3 lines down from main's numbering - rule 24 `:266`, 25
`:267-283`, 26 `:285-295`, 27 `:296-303`, 28 `:304-311`, 29 (routing) `:312-320`, `default`
`:323`, `unmapped` `:324`. `sabotage.py` imports `ROUTE_MUTATIONS` at `:79` and
`CONFIG_MENU_MUTATIONS` at `:80`; the `MUTATIONS +=` statement is `:3051-3053`, so every "appended
at `:3052`" moved to `:3053` and REFRESH's `:3051` to `:3052`. `plugin/crew/CONFIG.md`'s
descoped process-group kill is `:2284-2291` (`:2250-2257` on main's side, `:2282-2289` on
T-0075's). `verify-gate.sh` changed on neither side.

## Re-anchor provenance - `f7163410` + `65bb3330` -> `23371afb`, 2026-09-27 (T-0075 merges T-0018's main)

`34b5f368` merges origin/main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245; its notes anchored
`65bb3330`) into T-0075's branch at `b5ef35df` (notes anchored `f7163410`), and `23371afb` bumps crew
to 1.0.48. The source files both sides changed since `bebbb97f` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md` and the version files;
`crew_autopilot.py`, `commands/autopilot.md` and the autopilot tests changed on main's side only,
`crew_config.py`, `crew_config_menu.py`, `CONFIG.md` and `sabotage.py` on T-0075's only. The
conflicting provenance sections keep both sides, main's first; each body citation into a file both
sides changed was mapped from the side its line came from onto the merged tree and re-read with
`sed -n`/`grep -n`. `.crew/verify.json` is 326 lines and 30 rules: main's rule-27 widening (+1) and T-0075's three
rule-7 paths (`:136-138`, +3) give rule 24 `:266`, 25 `:267-283`, 26 `:285-295`, 27 `:296-304`, 28
`:305-312`, 29 `:313-321`, `default` `:324`, `unmapped` `:325` (read with `json.load` and a brace
walk). `sabotage.py` did not change on main's side: imports `:75-80`, the `MUTATIONS +=` statement
`:3051-3053` (REFRESH on `:3052`, the rest on `:3053`). `plugin/crew/CONFIG.md`'s descoped
process-group kill stays `:2284-2291`. `verify-gate.sh` changed on neither side. No suite was run for
this note; the suites T-0075 ran are in its ticket evidence.

## Re-anchor provenance - `23371afb` -> `764f6018`, 2026-09-27 (T-0075 review round 1)

`764f6018` fixes T-0075's review round 1. `git diff --name-only 23371afb 764f6018` is `CHANGELOG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_config_menu.py`,
`plugin/crew/skills/crew-setup/config-menu.md` and three crew test files. Each citation into one
of them was mapped with a line diff from `87627d86` (the tree `23371afb` describes for those
files) and re-read with `sed -n`/`grep -n`. `plugin/crew/CONFIG.md` gained 6 lines in the repo-writer section, so
`CONFIG.md:2248-2257` / `:2284-2291` citations became `:2254-2263` / `:2290-2297` (same text, diffed).
`.crew/verify.json` did not change: rule 7 already maps the three T-0075 files. The rule-7 suites
ran on the fix commit (550 passed). Nothing else was executed for this note.

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
at `7d217751` with `sed -n`/`grep -n`; `.crew/verify.json` is 337 lines, 31 rules: rule 7 `:129-144` gained
`crew_config_files.py` and `test_config_files.py` (`:139-140`) and runs `test_config_files.py`;
every rule below it moved +2 (rule 9 `:169-174`, 11 `:184-189`, 13 `:198-202`, 24 `:268`, 25
`:269-285`, 26 `:287-297`, 27 `:298-306`, 28 `:307-314`, 29 `:315-323`, 30 `:325-332`, `default`
`:335`, `unmapped` `:336`); `sabotage.py`'s `MUTATIONS +=` is `:3052-3055` (refresh `:3053`, the
next five `:3054`, config `:3055`; approval imported at `:81`); `CONFIG.md:2290-2297` ->
`:2328-2335`. The 50 `CONFIG_MENU_MUTATIONS` counted with `len()`. Suites are reported in
T-0075's implement result, not executed for this note.

## Re-anchor provenance - `7d217751` + `f96e9ec9` -> `8cabe586`, 2026-09-27 (T-0075 post-merge fixes, merges T-0077's main)

`8cabe586` is T-0075's crew 1.0.50 bump. Between `7d217751` and it: `ed7cb36c` (the stray line
step 6 left in `crew_config_menu.py:940`, a restore-line test's assertion, and the widening-warning
mutation re-anchored in `sabotage.py`, each found by the first full suite run after the build), a
1.0.48/1.0.49 step-back and re-set (`b80db8e1`, `81ed193c`), `3ebddc74` merging origin/main
`f96e9ec9` (T-0077 landed as 1.0.49: Windows directory handles in `crew_tracker.py`,
`crew_autopilot._rel`, their tests and mutations, three `plugin/crew/README.md` lines and its
`CHANGELOG.md` entry; main's notes were not refreshed for it) and the bump. Citations into the
paths `git diff --name-only 7d217751 8cabe586` names were mapped with `git diff -U0` and each
moved one checked by content at `8cabe586`; `.crew/verify.json` did not change (337 lines, 31 rules); `sabotage.py`
kept its line count, so `:80`, `:81` and `:3052-3055` hold; `TRACKER_MUTATIONS` is 87 by `len()`
(T-0077 added its own). Suites are reported in T-0075's implement result, not executed for this note.

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

`plugin/crew/CONFIG.md:2328-2335` (the descoped per-rule process-group kill, cited twice) moves to
`:2350-2357` (round 3's CONFIG.md lines above it); re-read with `sed -n`. No other citation moved
(script over every explicit `path:N`); `.crew/verify.json` and `sabotage.py` did not change
(`:80`, `:3055` hold). `CONFIG_MENU_MUTATIONS` is 81 by `len()`. Suites are reported in T-0075's
fix result, not executed for this note.

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

`plugin/crew/CONFIG.md:2354-2361` (the descoped per-rule process-group kill, cited twice) moves to
`:2363-2370`: T-0072's §20 and the round-4 writer paragraph sit above it. `.crew/verify.json` rule 7
(`:129-144`), rule 27 (`:298-306`) and rule 28 (`:307-314`) hold. No other citation moved.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N`
carried from the last path named in its paragraph, from both `3724731b` and `9631c707` to the tree
at `938e3b11` (difflib equal blocks); every citation neither base maps to itself was read with `sed
-n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `crew_autopilot.py`
citation after an `autopilot.md` mention, a `plugin.json:3` in another plugin); those were read and
hold. Nothing else was executed for this note.

**Re-anchored `9631c707` -> `051f9e85` on 2026-09-28 (T-0091).** `051f9e85` is T-0091's one commit on `T-0091-build`, off main `f54af3fa`. `git diff --name-only 9631c707 f54af3fa -- <every tracked path this note cites>` is empty; `f54af3fa..051f9e85` changes only `CLAUDE.md` (the Landmines truncating-`open` entry's measurement paragraph, now `:185-212`, +28/-18, so every later line moves +10) and `TODO.md` (one entry closed at `:4473`, three lines appended at `:4480-4482`). **One citation moved:** the "unknown collapsing into the safe-looking value" Lessons bullet went `CLAUDE.md:233` -> `:243` (the +10 shift; re-read with `grep -n`), corrected in place above. No other claim moved. Nothing was executed.

**Re-anchored `051f9e85` -> `c192b83d` on 2026-09-28 (T-0091 review round 1).** `c192b83d` is T-0091's review-round-1 fix on `T-0091-build`. `git diff --name-only 051f9e85 c192b83d` returns only `CLAUDE.md`: the same Landmines truncating-`open` measurement paragraph, now `:185-219` (+16/-9, so every later line moves +7; lines above `:192` are byte-identical). **One citation moved:** the "unknown collapsing into the safe-looking value" Lessons bullet went `CLAUDE.md:243` -> `:250` (the +7 shift; re-read with `grep -n`), corrected in place above. No other claim moved. Nothing was executed.

**Re-anchored `9631c707` -> `c99e31f6` on 2026-09-28 (T-0092, crew 1.0.52).** `c99e31f6` is T-0092's crew 1.0.52 version commit on `T-0092-build`, cut from main `f54af3fa` (T-0072's landing merge, whose only commit past `9631c707` is the refresh `f1f118de`). `git diff --name-only 9631c707 c99e31f6`, refresh artifacts aside, returns T-0092's files: `plugin/crew/hooks/scripts/review_patch.py` (+8: the docstring paragraph on `graphify-out/` and one comment line; `EXCLUDED` / `_EXCLUDE_SPEC` now at `:104-105`), `plugin/crew/hooks/scripts/review_prompt.py` (+4: one docstring line and the `excluded` line at `:89-91`, so `:84` -> `:85` and `:239` -> `:243`), `test_review_patch.py`, `test_review_prompt.py`, `sabotage_review.py`, line-neutral edits to `plugin/crew/README.md` (`:723`, `:842`), `plugin/crew/commands/review.md` (`:328-332` reflowed in place), `crew_autopilot.py` (`:55-56`), `completion_audit.py` (`:74-75`) and `TODO.md` (`:5048`), `CHANGELOG.md` (+26 at the top) and the three version files (1.0.52 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`). Every body citation of the form `path:line` into those files was compared by script between `9631c707` and `c99e31f6`. The only differing citations are the version-file lines, changed in place, which the provenance notes cite with the value at their own commit. No citation moved. Nothing was executed for this note.

**Re-anchored `c99e31f6` -> `3c4f1a68` on 2026-09-28 (T-0092 merged onto `c426c018`, crew 1.0.53).** `95cc12cf` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52 at `e329eb8f`) into `T-0092-build`; the merge was clean (both sides had set the version files to 1.0.52). `3c4f1a68` re-bumps crew to 1.0.53 and moves T-0092's four `1.0.52` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:842`, `TODO.md:5048`, the two test-file comments) to 1.0.53, all in place. `git diff --name-only c99e31f6 3c4f1a68`, refresh artifacts aside, returns T-0076's files - `plugin/crew/hooks/scripts/crew_context.py` (+4 inside `emit`, so `sys.stdout.write` moves `:1086` -> `:1090`), `plugin/crew/README.md` (`:1673` in place), `scripts/_test/uv-install.sh` and twelve test files - plus `CHANGELOG.md` (T-0076's entry merged below T-0092's) and the version files. Every body citation of the form `path:line` into those files was compared by script between `c99e31f6` and `3c4f1a68`: the only differences are version-file lines changed in place and `CHANGELOG.md` lines inside dated provenance notes, left as history; nothing here cites `crew_context.py` at or below `:1086`. Nothing was executed for this note.

**Re-anchored `c192b83d` / `3c4f1a68` -> `25d2de63` on 2026-09-28 (T-0092 merged onto `f8b6c8d7`, T-0091, crew 1.0.53).** `25d2de63` merges origin/main `f8b6c8d7` (T-0091 landed at `c192b83d`: `CLAUDE.md`'s Landmines paragraph and a `TODO.md` entry, no plugin bumped) into `T-0092-build`. The code-map, INDEX, rules, diagram and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor taken from this note. Every body citation of the form `path:line` was compared by script twice: `c192b83d` -> `25d2de63` differs only on T-0092's own lines (the exclusion, the re-pointed `review_prompt.py` lines, `plugin/crew/README.md:842` in place, the version lines), and `3c4f1a68` -> `25d2de63` only on T-0091's `CLAUDE.md` lines, which T-0091's own notes above cite at `c192b83d`, and on `TODO.md:5048`, cited in T-0092's notes above as that commit's line: T-0091's three added lines move the bullet to `:5051`. Nothing was executed for this note.

**Re-anchored `25d2de63` -> `136f4b33` on 2026-09-28 (T-0092 merged onto `ff59160f`, T-0089, crew 1.0.54).** `e2220836` merges origin/main `ff59160f` (T-0089 landed as crew 1.0.53 at `0f526a8c`: `plugin/crew/tests/test_role_write_guard.py` fixtures and a `CHANGELOG.md` entry) into `T-0092-build`; the merge was clean. `136f4b33` re-bumps crew to 1.0.54 and moves T-0092's `1.0.53` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:842`, `TODO.md:5051`, the two test-file comments, its `CHANGELOG.md` heading) to 1.0.54, all in place. Every body citation of the form `path:line` into a file changed between `25d2de63` and `136f4b33` was compared by script: the only differences are version-file lines changed in place, `plugin/crew/README.md:842` in place, and lines cited inside dated provenance notes (`CHANGELOG.md`, which T-0089's entry shifts by 12 lines below `:80`, and `TODO.md:5048`), left as history at their own commit. No citation into `test_role_write_guard.py` exists here. Nothing was executed for this note.

## Re-anchor provenance - `938e3b11` + `136f4b33` -> `3648f59a`, 2026-09-28 (T-0075 review round 5, merge of `6387ab49`)

`9420bc16` merges origin/main `6387ab49` into `T-0075-build`: T-0076 (crew 1.0.52, `crew_context.py`'s byte-exact LF), T-0091 (`CLAUDE.md`'s Landmines paragraph, a `TODO.md` entry), T-0089 (crew 1.0.53, `test_role_write_guard.py` fixtures), T-0090 (mcp-servers 0.2.1, `SECURITY.md`) and T-0092 (crew 1.0.54: `review_patch.py` / `review_prompt.py` leave `graphify-out/` out of the review bundle), whose notes above are anchored `136f4b33`, `2442d367`, `c192b83d` or `b2553d26`. `faf4b0db`, `e7825a0e`, `04e3a01c`, `517628b9` and `d1460d77` are T-0075's review-round-5 steps 18-22 (`crew_config.py`, `crew_config_files.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `3648f59a` re-bumps crew to 1.0.55 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's conflicting provenance kept both sides, T-0075's `## Re-anchor provenance` sections first and main's `**Re-anchored ...**` paragraphs after them; the anchor line kept T-0075's and is replaced here.

`plugin/crew/CONFIG.md:2363-2370` (the descoped per-rule process-group kill, cited twice) moves to `:2371-2378` (round 5's eight CONFIG.md lines above it). `.crew/verify.json` rule 7 (`:129-144`) is unchanged. No other body citation moved.

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

## Re-anchor provenance - `360c4029` + `136f4b33` -> `d7c7c75c`, 2026-09-28 (T-0010-solo merges `6387ab49`)

`597a62b0` merges origin/main `6387ab49` into T-0010-solo `dbb22712`: T-0072 landed as crew
1.0.51, T-0076 as 1.0.52, T-0089 as 1.0.53 and T-0092 as 1.0.54, with T-0090 (mcp-servers 0.2.1)
and T-0091 (`CLAUDE.md`) beside them; main's code maps were anchored `136f4b33`. After it,
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

The autopilot rule's paragraph was resolved by hand and T-0010's policy rule re-read: 21s
(20.9s, 260 passed, measured on this tree under heavy-run) and 55 `POLICY_MUTATIONS` (the
merge's `deploy-allowed` entry added one), registered at `plugin/crew/tests/sabotage.py:77` and
appended at `:3054`. The autopilot rule ran 551 passed in 13.4s under heavy-run on this tree.

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

`.crew/verify.json` was read in full via `json.load` at `cd106b8b`: 345 lines, 32 rules, `default` `:342`,
`unmapped` `:343`; each rule range this note cites (`:287-297`, `:298-306`, `:307-313`, `:314-321`,
`:322-330`, `:332-339`) re-derived by brace depth. `plugin/crew/tests/sabotage.py` imports `:76-81` and
the `MUTATIONS +=` statement `:3052-3055` were re-read; `plugin/crew/CONFIG.md:2373-2380` is the descoped
process-group-kill paragraph (main's `:2371-2378` plus T-0010's two lines above it).

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

## Re-anchor provenance - `bbd9a66d` -> `05413bbe`, 2026-09-29 (T-0503, bitbucket 1.2.3)

`git diff --name-only bbd9a66d..05413bbe` over this note's cited paths returns only `README.md`, where T-0503 rewrote the `bitbucket` catalog row's Use cases cell in place (one line each, `README.md:815`, `skills/README.md:76`); no line count changed, so no `README.md` citation here moved. `skills/bitbucket/scripts/_test/merge_gate.sh` gained an eight-case documentation-invariants section before its summary line and two header-comment edits; this note cites it by path only (the `shell-suites.yml` paragraph), so no citation moved. The rest of T-0503 is `skills/bitbucket/SKILL.md`, `skills/bitbucket/references/api.md`, `CHANGELOG.md` (one Unreleased entry at the top) and the `bitbucket` version line in `.claude-plugin/marketplace.json`. Re-anchor only, under the refresh-artifact standing rule (owner 2026-09-28); nothing was executed for this note.
