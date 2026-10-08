# L-0647 plan (implementing session, 2026-10-05, rush/g4-deploy)

Built on L-0644 to L-0646 (this branch): the state file holds the run id (identify) and the verdict
(watch). promote-gate.sh's `passed()` (read 2026-10-05) needs a pipe and at least 6 cells and
returns on the first matching row; verify-gate.sh's Stop check greps `| <env> | <short sha>`.

1. RED: `test_crew_ghdeploy.py` record cases at the `_run_gh` seam (pass, fail, could-not-tell,
   unknown with no previous good, absent file, no verdict, atomic); `test_promote_gate_github.py`
   runs the REAL promote gates (sh and ps1, ps1 where pwsh resolves) on throwaway repos for
   forged-row-in-excerpt and fail-then-requires, plus a non-vacuity case.
2. `record`: read the state; a run id with no verdict is exit 3. Build the whole new text in memory
   (detail line; on non-pass the previous all-pass sha, the cleaned excerpt, the `not-run` row),
   then a temp file and `os.replace`. `_clean` removes ANSI and control characters and turns every
   pipe into a slash; only the `not-run` row carries pipes.
3. `previous_good`: the last all-pass row for the environment, read as `passed()` reads a row.
4. Docs: `github-deploy.md` (the five steps, exit codes, enforced versus prose), promote.md gate 2
   and `--dry-run` point to it with no net growth, crew-verification section 4 documents the detail
   line, the troubleshooting guide gains "The run could not be identified" (guide rebuilt).
5. Mutations per branch plus must-allow entries. The attended evidence run needs the owner and a
   consumer repository after merge and install: NOT done here.
