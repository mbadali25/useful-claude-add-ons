# L-0644 plan (implementing session, 2026-10-05, rush/g4-deploy)

Built on release/1.2.0 with T-0045 slice 1 (main) and the T-0009 port (this branch). T-0009's
classifier lives in `crew_dispatch.py` on this branch, not `crew_guards.py`: `prepare` calls
`crew_dispatch.dispatch_scopes` and `dispatch_environment` read-only, and the environment name's
own class through the same module's nonProd glob test. No edit to `cloud_guard.py`,
`crew_guards.py` or `crew_dispatch.py`.

1. RED: `test_crew_ghdeploy.py` gains the shared sequence fixtures (`FakeGh` at the `_run_gh`
   seam, a stubbed `_clock`/`_sleep`, the machine config pointed at an empty file) and one case
   per acceptance bullet; scenarios register for `test_helper_never_dispatches`.
2. `check`'s entry validation becomes `validated(envs, env)`, shared with `prepare` (one validator).
3. `prepare`: the refusal order of the spec, then the state file through a temp file and
   `os.replace`, then the dispatch printed as the last line before `result=`. `dispatch()` takes
   the correlation id so the state file and the command carry the same one.
4. One `ghdeploy_mutations.py` entry per refusing branch prepare adds, plus must-allow entries.
5. Docs: crew-verification section 4, README, CHANGELOG.
