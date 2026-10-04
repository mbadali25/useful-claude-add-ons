# T-0080 sabotage harness bounds each entry: a memory cap and a wall-clock limit per test run          status: spec   risk: med
## Refreshed 2026-10-04
First spec for this ticket; there was no earlier spec.md and there is no plan.md. Written against origin/main `155fe6d8` (crew 1.0.322) from direction.md and its "Direction check 2026-10-04". The owner was not available, so the recommended option (1) is taken; the three defaults are listed under Unknowns as owner questions.
## Intent
One uninterrupted `python3 plugin/crew/tests/sabotage.py` run cannot take the machine down. Each entry's test process runs under an address-space cap and a wall-clock limit set by the harness itself, so a mutation that turns a bounded read into an unbounded one is stopped at a small ceiling without the host's heavy-run wrapper. The two cloud guard entries stay as they are and go `RED (good)` by a real test failure. A timeout is reported as unproven and fails the suite.
## Exclusions
- No change to `plugin/crew/hooks/scripts/cloud_guard.py` or any other production script. The two mutations at `plugin/crew/tests/sabotage_cloud.py:544` and `:565` are kept unchanged.
- No new outcome that counts as a pass. An entry passes only when pytest exits 1, as today (`sabotage.py:3085`). No parsing of test output for `MemoryError`.
- No resident-memory watchdog, no `/proc` walker, no cgroup or `systemd-run` call, no Windows job object.
- No change to `scripts/gate-runner.py`, its step table or its timeout for the sabotage step, and nothing of L-0570.
- None of L-0525's other 14 entries (13 vacuous, 1 unproven). This ticket only removes the reason the run stops.
- No net growth of `plugin/crew/tests/sabotage.py`: it is at the pylint limit (3400 lines). `.pylintrc` is not edited.
- No filter, resume or `--only` option for `sabotage.py`.
- Nothing of T-0082 (the verify gate's own killed-rule handling).
## Design
- New module `plugin/crew/tests/sabotage_bound.py` (matches the `sabotage*.py` harness glob). It holds:
  - `limits(environ)` -> `(mem_mib, timeout_s)`. Defaults 4096 and 600. Read from `CREW_SABOTAGE_MEM_MB` and `CREW_SABOTAGE_TIMEOUT_S`. `0` for memory means no cap, and the run says so. Anything that is not a non-negative integer (memory) or a positive integer (timeout) raises `ValueError`; it never falls back to a default or to no cap.
  - `describe(mem_mib, timeout_s)` -> the one line `main` prints before the first mutation: `bound: memory 4096 MiB per process (RLIMIT_AS), 600 s per entry`, or `bound: memory cap absent (<why>), 600 s per entry`. The cap is reported as set only where it is enforced: Linux with the `resource` module. Elsewhere, or with `CREW_SABOTAGE_MEM_MB=0`, it reads `absent` with the reason.
  - `run(argv, cwd, env, mem_mib, timeout_s)` -> `(code, output)`. Starts the child in its own session/process group, applies `RLIMIT_AS` in the child before exec on Linux (so every process the test spawns inherits it), and waits at most `timeout_s`. On a timeout it stops the whole group (SIGTERM, a short grace, SIGKILL; on Windows the process tree) and returns `TIMED_OUT` (124). A child that dies of a signal returns the negative code `subprocess` gives. Output is stdout plus stderr, as today.
  - On harness exit by signal or `atexit`, a child group still running is stopped too, so no test process outlives the harness.
- `plugin/crew/tests/sabotage.py`: `run_test` keeps its signature and docstring facts (`PYTHONDONTWRITEBYTECODE=1`, `--run-slow`, `-x`) and calls `sabotage_bound.run`. `main` reads `limits` once, returns 2 with a one-line reason on `ValueError` before any mutation is applied, and prints the `describe` line. A `TIMED_OUT` code prints `RED BUT UNPROVEN -- timed out after <n>s` and fails the suite; every other code is classified exactly as today. Lines are freed inside the file (the classification block or a comment moved to the new module) so the file stays at or under 3400.
- Why the azureProfile entry goes red for real: over the cap the mutated guard raises `MemoryError` inside `evaluate`; `main`'s handler emits a deny whose reason is "internal error (MemoryError) ..." (`cloud_guard.py:3357-3366`); the test asserts `"unknown" in reason` (`test_cloud_guard_environments.py:1245-1246`) and fails; pytest exits 1.
- The `[plan-dev-zero]` test only asserts `deny`. If measurement shows the `:544` entry does grow and then comes back `STILL GREEN` under the cap (the internal-error deny satisfies the assertion), tighten `test_a_special_file_is_unknown_not_a_hang` to also assert the reason is not an internal error. That is a test change, in Touch.
## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/tests/sabotage.py:3088-3112 `run_test`: `subprocess.run([... "-m", "pytest", target, "-q", "--no-header", "-x", "--run-slow"], cwd=CREW, capture_output=True, text=True, check=False, env=env)`. No timeout, no limit, no group.
- plugin/crew/tests/sabotage.py:3073-3085 pytest exit codes; only 1 (`_REAL_TEST_FAILURE`) is proof. :3364-3393 the loop and the three outcome lines. :3216-3223 `_on_signal` restores, then `sys.exit(128 + signum)`. :3226-3246 `install_exit_handlers`.
- plugin/crew/tests/sabotage.py is 3400 lines; `.pylintrc:140` `max-module-lines=3400`. :67-90 the sibling imports; :3064-3071 `MUTATIONS +=`.
- plugin/crew/tests/sabotage_cloud.py:544-549 entry "a FIFO or device is opened as a plan", target `_SP + "[plan-dev-zero]"` (`_SP` at :433). :565-570 entry "azureProfile.json opened whatever it is", target `test_a_special_azure_profile_is_unknown_not_a_hang[zero]`.
- plugin/crew/hooks/scripts/cloud_guard.py:1726-1727 `_is_regular`. :1730-1748 `_open_regular`. :1751-1760 `_read_small`. :1766 `_AZ_PROFILE_MAX_BYTES`. :1842-1851 the plan is hashed in `1 << 20` blocks. :2471-2474 the profile read, catching only `(OSError, ValueError)`. :3357-3366 `except Exception` around `evaluate` emits a deny naming the exception type.
- plugin/crew/tests/test_cloud_guard_environments.py:1176-1183 `_special_file` (a symlink to `/dev/zero`). :1186-1205 `_run_bounded`, `timeout=30`, the guard run as a subprocess of the test. :1208-1230 the plan test, `assert decision == ("allow" if kind == "none" else "deny")`. :1233-1246 the azure test, `assert "unknown" in reason`. :1172-1173 both skip without `os.mkfifo`.
- plugin/crew/tests/test_sabotage_harness.py:235, :317, :336, :362 monkeypatch `sabotage.run_test` with a `(code, "")` lambda, so the signature must stay.
- scripts/check-tooling-pr.py:79 `"plugin/crew/tests/sabotage*.py"` in `HARNESS`; :99-118 `ALONGSIDE` (tests, README, CONFIG, BUDGETS, version files, CHANGELOG, `.claude/rules/**`, `docs/**`, `.crew/codemap/**`, `.crew/verify.json`, `graphify-out/**`).
- scripts/gate-runner.py:225 `Step("sabotage", "solo", (PY, "plugin/crew/tests/sabotage.py"), timeout=5400)`; :74 CI does not run it; :19-23 heavy-run absent means uncapped.
- .crew/verify.json:218-225 the rule that runs `test_sabotage_harness.py`; :455 the harness rule lists `plugin/crew/tests/sabotage*.py`.
- plugin/crew/README.md:2933-2940 the paragraph that describes `tests/sabotage.py`. `git grep -n -i sabotage origin/main -- 'docs/guides/crew/src/*.md'` prints nothing: no guide describes the runner.
- `.claude/rules/verification-harness.md:19-29` and `.crew/codemap/crew.md` cite `sabotage.py` by line; they move if an import line is added.
- Nothing on main bounds the harness: `git grep -nE "setrlimit|RLIMIT|killpg|start_new_session" origin/main -- 'plugin/crew/tests/sabotage*.py'` prints nothing.
- Measured 2026-10-04 on the Linux host (pwsh 7.6.5, python3 3.14.4): `ulimit -v 4194304`: pwsh exit 0, node and python start. `ulimit -v 2097152`: pwsh "Out of memory", exit 134; node and python start.
## Unknowns
- Which entry grows. By the code only `:565` does; the 2026-09-27 note measured `:544`. Resolve first at implement: run each of the two entries alone, under the heavy-run wrapper, before the change, with `/usr/bin/time -v`, and record peak resident memory and the outcome line. If `:544` grows, apply the test tightening in Design.
- Whether any unmutated test fails under a 4096 MiB address-space cap (a false RED for a vacuous entry). Resolved by the "clean under the cap" acceptance check. If it fails: raise the default to the smallest value that is clean and still under the wrapper's memory limit, or try `RLIMIT_DATA`; if neither is clean, stop and ask the owner. Do not exempt single tests from the cap.
- The slowest legitimate entry, which sets the timeout default. Resolved from the full run's per-entry times; the default must be at least three times the slowest. 600 s is the starting value.
- Owner question 1: real-assertion RED under the cap in place of a `RED BY LIMIT` pass outcome. Default taken: yes.
- Owner question 2: defaults of 4096 MiB and 600 s, overridable by environment. Default taken: yes.
- Owner question 3: Windows and macOS get the timeout only, cap reported `absent`. Default taken: yes. Accepted as risk: both cloud guard tests skip there anyway (no usable `/dev/zero` case on Windows).
- The next free crew patch version is set at implement time.
## Dependencies
- Must land first: none open. Built on T-0087 (merged, PR #281): the tooling-PR rule and the harness rule this PR lands under. L-0513 (done): the gate runner that runs the sabotage step and already kills a timed-out step's group.
- Related, not blocking: T-0082 (direction): the verify gate's killed-rule handling; separate code. L-0570 (direction): gate-runner fixes; separate file.
- Blocks: L-0525 (direction): its acceptance needs one uninterrupted full run, which needs this bound.
## Size and split
- Estimate: about 120 added lines of harness code in `plugin/crew/tests/sabotage_bound.py`, and a net change of zero or less in `sabotage.py`. Nothing is added under `plugin/crew/hooks/`, `scripts/` or `skills/`.
- One mechanism (a bounded child runner) and no new parser. Every code path is in `HARNESS` or `ALONGSIDE`, so it is one tooling-only PR with no feature work. No split.
## Touch
- `plugin/crew/tests/sabotage_bound.py` - new
- `plugin/crew/tests/sabotage.py` - run_test and main only, net zero lines or fewer
- `plugin/crew/tests/sabotage_tooling.py` - the mutations of the bound itself
- `plugin/crew/tests/test_sabotage_bound.py` - new
- `plugin/crew/tests/test_sabotage_harness.py`
- `plugin/crew/tests/test_cloud_guard_environments.py` - only if the plan-dev-zero assertion needs tightening
- `plugin/crew/tests/sabotage_cloud.py` - comments on the two entries only
- `.crew/verify.json` - add the two new files to the rule at 218-225
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `.crew/codemap/**`
- `.claude/rules/**`
- `docs/diagrams/**`
- `graphify-out/**`

Docs: guides none - no file under docs/guides/crew/src describes the sabotage runner (grep above). CONFIG.md none - the two environment variables are test-harness settings, not crew config keys; they are documented in the module docstring and README.
## Acceptance checks
Run heavy commands through the heavy-run wrapper where it exists.
- [ ] New tests pass: `python3 -m pytest plugin/crew/tests/test_sabotage_bound.py plugin/crew/tests/test_sabotage_harness.py -q` (rule at `.crew/verify.json:218-225`). By name, in `test_sabotage_bound.py`:
  - `test_a_child_over_the_memory_cap_fails_instead_of_growing` (Linux; a child allocating past a 256 MiB cap exits non-zero)
  - `test_the_memory_cap_reaches_a_grandchild`
  - `test_a_child_under_the_cap_is_unaffected` (must-allow: exit 0 and its output returned)
  - `test_a_timeout_stops_the_whole_group_and_returns_124` (the grandchild's pid is gone afterwards)
  - `test_an_unreadable_limit_refuses_and_never_means_no_cap` (parametrized: `abc`, `-1`, empty, `1.5`, timeout `0`)
  - `test_zero_memory_is_no_cap_and_the_line_says_absent`
  - `test_the_bound_line_says_absent_where_no_cap_is_enforced`
  and in `test_sabotage_harness.py`:
  - `test_main_reports_a_timed_out_entry_as_unproven_and_fails`
  - `test_main_refuses_an_unreadable_limit_before_any_mutation`
  - `test_run_test_hands_pytest_to_the_bounded_runner`
- [ ] The azureProfile entry alone is `RED (good)` and bounded, with no wrapper cap needed: from `plugin/crew/tests`, `/usr/bin/time -v python3 -c "import sabotage as s; s.MUTATIONS=tuple(m for m in s.MUTATIONS if 'azureProfile.json opened' in m[0]); raise SystemExit(s.main())"` prints the `bound:` line, `RED (good)`, `SABOTAGE SUITE: PASS`, exits 0, and "Maximum resident set size" is under 4.5 GiB. Run it inside the wrapper the first time.
- [ ] The same for the plan entry (filter `'FIFO or device is opened'`): `RED (good)`, exit 0, peak under 4.5 GiB.
- [ ] Clean under the cap: `bash -c 'ulimit -v 4194304; python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock" --run-slow'` gives the same pass and skip counts as the same command without the `ulimit`. Quote both counts.
- [ ] One uninterrupted full run: `python3 plugin/crew/tests/sabotage.py` reaches `SABOTAGE SUITE:` with no entry skipped and no kill. Its non-RED lines are exactly L-0525's 14 (13 `STILL GREEN`, 1 `RED BUT UNPROVEN -- exit 4`); every other entry is `RED (good)`. Diff the non-RED lines against a pre-change run at the same base and quote the diff. The suite still reports FAIL because of those 14; that is L-0525's.
- [ ] The bound's own mutations go red, each on its named test: the cap not applied, the timeout stopping only the leader, an unreadable limit read as the default. Run with `MUTATIONS` filtered to the new `sabotage_tooling.py` entries, as above.
- [ ] `wc -l plugin/crew/tests/sabotage.py` is at most 3400 and `python3 -m pylint plugin/crew/tests/sabotage.py plugin/crew/tests/sabotage_bound.py` scores 10.00.
- [ ] The anchors still resolve: `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py::test_every_shipped_anchor_is_present_in_its_target_exactly_once -q` passes.
- [ ] Tooling-only: `python3 scripts/check-tooling-pr.py` exits 0 and `python3 scripts/_test/tooling-pr.py` passes (the harness rule in `.crew/verify.json`).
- [ ] After the commit: `python3 scripts/check-marketplace.py` passes, with the crew version bumped in `plugin.json`, `marketplace.json`, `plugin/PLUGINS.md` and a CHANGELOG entry.
- [ ] `plugin/crew/README.md`'s sabotage paragraph states the per-entry cap, the timeout, the two environment variables and that the cap is `absent` off Linux. The code map and `.claude/rules` are refreshed and fresh.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
