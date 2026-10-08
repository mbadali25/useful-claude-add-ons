# L-0646 plan (implementing session, 2026-10-05, rush/g4-deploy)

Built on L-0644 (`prepare`) and L-0645 (`identify`, the run id in the state file). `prepare` now also
records `shaInput` and `deployJob` in the state file, so `watch` judges the run against the entry
that was dispatched, not a map edited since.

1. RED: one case per acceptance bullet at the `_run_gh` seam, with a clock that a killed watch
   (exit 124) advances by its timeout; every scenario registers for `test_helper_never_dispatches`.
2. `_run_gh` takes a timeout and reports a killed `gh` as 124.
3. `judge(view, state)` is the verdict: unreadable view or not `completed` is unknown; a conclusion
   other than `success` is fail; with no `shaInput` a head sha mismatch is fail (unreadable is
   unknown); with `deployJob`, no matching job or a matching job that did not succeed is fail;
   otherwise pass (reason says whether the deploy job was checked).
4. `watch`: one `gh run watch <id> --exit-status --interval 15` bounded by the slice and the
   deadline; when it returns early and the run is unfinished, the view is polled every 15 seconds
   for the rest of the slice. Unfinished before the deadline is exit 75 with nothing written;
   otherwise the verdict, its reason and the watch exit code go into the state file.
   `--slice-seconds` is 1 to 570. No run id is could-not-tell (exit 3).
5. One mutation per refusing branch plus must-allow entries; docs (crew-verification section 4,
   README, CHANGELOG).
