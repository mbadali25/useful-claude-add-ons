# T-0055 plan

Written by the implementing session, 2026-10-05, on `rush/g5-platform` (base `origin/release/1.2.0`).

1. `scripts/_test/crew-docs.py` first: every must-fail, must-pass and could-not-tell case in the
   spec's acceptance list, each in a throwaway git repo with a fake `refs/remotes/origin/main`, the
   output checks (exit-1 names the code paths, the DOCS globs and both declaration forms; exit-0 by
   declaration prints the reason and its source), and the seven mutation cases (a)-(g), each of
   which must flip a named case.
2. `scripts/check-crew-docs.py`: `changed_paths` copied from `check-tooling-pr.py` (not imported,
   not edited: harness), `crew_ticket.path_matches` for CODE / DOCS, trailers from
   `origin/main..HEAD`, the PR body from `--pr-body-file` or the `pull_request` event, the verdict
   order of the spec (77 missing ref or git failure; 0 no code; 0 docs; 0 valid declaration; 77
   unreadable body that was needed; else 1).
3. CI: two `marketplace.yml` steps after "Windows shard fan-in suite"; two `gate-runner.py` table
   entries so `--check-ci` stays green. `.crew/verify.json`: one rule for the checker and its suite
   that runs the suite only, with a measured `seconds`.
4. Docs: the `CLAUDE.md` "Scope discipline" paragraph plus the sentence naming the check and the
   trailer; `.crew/standards.md` GEN-09 names the trailer; `docs/claude-md-evidence.md` "From Scope
   discipline" holds the 31 / 4 measurement and how to re-measure; `CHANGELOG.md` and the README
   sync. The code-map line and refresh are left to the coordinator (reported).
