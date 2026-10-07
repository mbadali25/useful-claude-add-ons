# L-0645 plan (implementing session, 2026-10-05, rush/g4-deploy)

Built on L-0644's `prepare` (this branch): the state file `.crew/.ghdeploy/<env>-<N>.json` holds the
workflow, ref, actor, `t0`, the snapshot of run ids, the correlation id and `identifySeconds`.
`gh run list --json` fields re-checked on gh 2.89.0 (2026-10-05): `databaseId`, `createdAt`,
`headBranch`, `event`, `displayTitle` and `url` are all there; still no actor and no inputs field.

1. RED: `test_crew_ghdeploy.py` gains one case per acceptance bullet, at the `_run_gh` seam with a
   clock that each 5-second `_sleep` advances; every scenario registers for
   `test_helper_never_dispatches`.
2. `read_state`: missing is `state-file-missing`, unparseable or missing a key `prepare` writes is
   `state-file-unreadable`; `t0` more than 600 seconds ago is `stale-prepare`.
3. `pick_run` returns the candidates of one `run list` answer and never chooses: not in the
   snapshot, `workflow_dispatch`, on the ref, `createdAt` at or after `t0 - 30`, and with a
   correlation id its display title holds it (no fallback). An unreadable `createdAt` on a new run
   is `created-unparseable`.
4. `identify` polls every 5 seconds until `identifySeconds` (by the clock, and at most
   `identifySeconds // 5 + 1` polls): one candidate is written into the state file (`runId`,
   `runUrl`) through `write_state`; two is `two-candidates` at once; at the timeout it is
   `run-list-fails` (every poll failed), `correlation-not-found` (new runs in the window lacked the
   id) or `none-in-timeout`. All exit 3 and write nothing.
5. One `ghdeploy_mutations.py` entry per refusing branch, plus must-allow entries.
6. Docs: crew-verification section 4, README, CHANGELOG.
