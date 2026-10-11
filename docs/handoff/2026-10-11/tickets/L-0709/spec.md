# L-0709: Hermetic tests, then a green main          status: in-progress   risk: medium
Written against origin/main `c25ef990` (crew 1.2.0, 2026-10-08). Direction: `direction.md` (review plan item 1.1).
Depends on L-0704 / PR #545. Owned by the crew [8102fe] session.

## Intent
No crew test reads or writes the operator's real home. After L-0704 / PR #545 merges, an autouse fixture in
`plugin/crew/tests/conftest.py` points `HOME`, `USERPROFILE`, every `XDG_*` directory, `CLAUDE_CONFIG_DIR` and
`CLAUDE_PROJECT_DIR` at per-test directories under `tmp_path`, so spawned scripts inherit the isolation as well as
in-process readers. A meta-test fails any test that opens a path under the real home. Known timing flakes are
quarantined behind a marker that names an owner and a ticket, and are excluded from the default Stop/CI selection
only through that marker. Result: the Stop hook stops failing on this machine's `~/.claude/crew/config.json`, and
main's pytest-crew stays green.

## Exclusions
- No production code change: hook scripts, `crew_config.py` and `crew_state.py` are untouched.
- No change to `plugin/crew/tests/sabotage*.py` (HARNESS, `scripts/check-tooling-pr.py`); if a sabotage entry is
  needed for the meta-test it goes in a follow-up tooling PR on the next free L- id (tooling-PR rule).
- Not a fix for the flaky behaviour itself (`test_review_checks.py:2245-2261`); quarantine with an owner only.
- Does not redo L-0704's single-test fix; builds on it.

## Evidence
- `plugin/crew/tests/test_crew_autopilot_status.py:228-230` - `_lines` runs `crew_autopilot.py status` in a
  subprocess that inherits the caller's HOME (the review artifact cites `:225`; `.work/HANDOFF.md:36`).
- `plugin/crew/tests/conftest.py:30-54` - `_no_real_global_config` patches `GLOBAL_CONFIG_PATH` on two modules
  and sets `CREW_BACKUP_DIR`; it does not move HOME, so a subprocess still resolves the real global config.
- `plugin/crew/tests/conftest.py:118`, `:175-193` - `XDG_CACHE_HOME` is already isolated for pwsh; the new
  fixture extends that pattern rather than adding a second mechanism.
- `plugin/crew/tests/test_review_checks.py:2245-2261` - `test_a_clean_linter_s_detached_leftover_is_ended`, the
  timing flake in the last red pytest-crew run on main (`scratchpad/eval/opus-eval.md:159-162`).
- `.github/workflows/pytest-crew.yml` - the main-branch job whose 7-day green run is the done-when.

## Unknowns
- U1: whether PR #545 is merged and what fixture shape it settled on; read it first and extend, do not duplicate.
- U2: tests that deliberately exercise the real-home path resolution (`crew_config.read_global_config`,
  `CLAUDE_CONFIG_DIR` handling). They must opt out explicitly with a named marker, never silently.
- U3: how the meta-test detects "opened the real home" portably (audit hook `sys.addaudithook` on `open`, plus
  subprocess env inspection); Windows `USERPROFILE` must be covered too.
- U4: other timing flakes on main besides `test_review_checks.py:2261`; list them from `gh run list` for
  pytest-crew before choosing the quarantine set.

## Touch
- `plugin/crew/tests/conftest.py`
- `plugin/crew/tests/crew_fixtures.py`
- `plugin/crew/tests/test_hermetic_home.py`
- `plugin/crew/tests/test_conftest_git_isolation.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/tests/test_review_checks.py`
- `.github/workflows/pytest-crew.yml`
- `.crew/verify.json`
- `plugin/crew/README.md`
- `plugin/crew/skills/crew-qa-standards/references/harness.md`
- `plugin/PLUGINS.md`
- `.crew/codemap/crew.md`
- `.crew/codemap/verification-harness.md`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/tests/test_ps1_python_probe.py` (amended 2026-10-09 at the round-4 successor plan: the PR already carries it, step 3's quarantine)
- `plugin/crew/tests/test_upgrade.py` (amended 2026-10-09: gate fix 3, both GLOBAL_CONFIG_PATH names)
- `plugin/crew/tests/test_crew_autopilot_stop_contract.py` (amended 2026-10-09: gate fix 1's subject, read-only unless the fix needs it)
- `VERIFYING.md` (amended 2026-10-09: step 5's doc line the PR already carries)
- `README.md` (amended 2026-10-09: the PR's existing one-line edit)
- `.claude/rules/verification-harness.md` (amended 2026-10-09: regenerated from the code map)
- `.crew/codemap/` (amended 2026-10-09: refresh artifacts)

## Acceptance checks
1. With `~/.claude/crew/config.json` setting `autopilot.mode=plan` (or any non-default), the full crew suite
   passes; `test_status_mode_line_reads_off_by_default` passes.
2. Inside any test, `os.environ["HOME"]`, `USERPROFILE`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`,
   `XDG_STATE_HOME` and `XDG_CACHE_HOME` resolve to that test's own directories under pytest's basetemp
   (beside `tmp_path`, never the real home); `CLAUDE_CONFIG_DIR` and `CLAUDE_PROJECT_DIR` are UNSET, so they
   resolve under that home / the test's cwd (amended 2026-10-08: pointing CLAUDE_PROJECT_DIR anywhere changes
   `pm_brief`'s root for every test). `XDG_RUNTIME_DIR` (sockets, not configuration) is left alone. A spawned
   `python3 -c` sees the same values.
3. Meta-test must-block: a test that opens a file under the real home (through a symlink too), or spawns a
   process with a real HOME or a directory inside one, fails, naming the test and the path; module fixtures set
   up for a test are audited with it. A spawned process is covered by its HOME, not audited inside: the audit
   is in-process, and the real home's path is not handed to a test's environment.
   Sabotage by hand: remove the HOME override and confirm check 1 and this check go red.
4. Every quarantined test carries a marker naming an owner and a ticket; an unmarked skip of a timing test fails
   collection.
5. The Stop hook on this host no longer blocks because of the operator's own config.
6. main's pytest-crew is green for 7 consecutive days after merge (tracked, closes the ticket).
7. `python3 scripts/check-marketplace.py` passes after the commit.

## Amendments 2026-10-08 (implementing lane, before code)
- **U1 resolved.** PR #545 (L-0704) is merged (1c0b53d8, crew 1.2.1). Its shape is a per-call helper,
  `crew_fixtures.isolated_home_env`, used by `test_crew_autopilot_status.py::_lines`. Kept as is; the new
  autouse fixture is the suite-wide layer beneath it.
- **Where the home lives.** Per test, `tmp_path_factory.mktemp("home")`: beside `tmp_path` under the same
  basetemp, not inside it, for the reason conftest already gives for the XDG cache (tests assert exactly what
  `tmp_path` holds). A session-wide home is set at `pytest_configure` for spawns outside any test. The Python
  user base and pwsh's CurrentUser module directory are carried over (`PYTHONUSERBASE`, `PSModulePath`):
  they hold installed code, not configuration, and moving HOME must not hide pytest or PSScriptAnalyzer.
- **CLAUDE_CONFIG_DIR and CLAUDE_PROJECT_DIR** stay UNSET (conftest already deletes both), so they resolve
  under the isolated home / the test's cwd. Pointing CLAUDE_PROJECT_DIR at a directory would change
  `pm_brief`'s root resolution for every test. Check 2 reads "unset or under the test's own home".
- **U2 resolved.** No test needs the real home; every global-layer test already plants its own. No opt-out
  marker is added (it would be unused code); a test that wants another home sets HOME after the fixture.
- **U3 resolved.** `crew_fixtures.home_audit` (`sys.addaudithook`) refuses and records, while a test runs,
  an `open` under a real home (HOME, USERPROFILE and the password-database home, carried to xdist workers in
  `CREW_TEST_REAL_HOME`) and a `subprocess.Popen` handed the real HOME/USERPROFILE. Not the whole home: a CI
  checkout, the interpreter, its import path and the temp dir can sit under it, so those prefixes are allowed.
  The fixture's teardown fails the test naming every path, even when the code swallowed the exception.
- **U4 resolved.** pytest-crew on main, 2026-10-06..08: 7 red runs. 4 failed on
  `test_review_checks.py::test_a_clean_linter_s_detached_leftover_is_ended` alone (37477273668, 37642924232,
  37721327069, 37725772665); 1 on `test_ps1_python_probe.py::test_near_deadline_candidates_then_a_hang_stay_
  within_the_hook_timeout` (37718549059, serial wallclock step, ps1=10.43s vs 10s); 1 Windows matrix job
  (37637725328) and 1 with no retrievable log (37653831653). Both named tests are quarantined, owner
  `mbadali25`, ticket L-0737 (the fix).
- **Quarantine marker.** `@pytest.mark.quarantine(owner=..., ticket=..., reason=...)`; deselected unless a
  `-m` expression names `quarantine`. A quarantine without owner or ticket, or a skip/skipif/xfail whose
  reason says flaky/timing/intermittent without the marker, is a usage error at collection.
- **L-0729 folded in** (owner order 2026-10-08): its two `test_crew_context_wrappers.py` cases are fixed by
  the shared fixture with no edit to that file. Its "sabotage suite entry" acceptance needs
  `plugin/crew/tests/sabotage*.py` (HARNESS), so it moves to a follow-up tooling PR, L-0738, after this lands.
  This PR's own regression case (`test_hermetic_home.py`) was sabotaged by hand and the results recorded.
- **Touch added:** `plugin/crew/tests/test_ps1_python_probe.py` (quarantine), `VERIFYING.md` (the
  `-m quarantine` line), `README.md` (root "What's new", generated from CHANGELOG).
- **Version.** Test files live under `plugin/crew/`, so `check-marketplace.py`'s drift check needs a bump:
  crew 1.2.2.
