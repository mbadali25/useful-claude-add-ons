# T-0106 plan

Written by the implementing session (feature rush 1.2.0, branch rush/g3b-bridge, base release/1.2.0 a555ff37).

1. Tests first, in `plugin/crew/tests/test_autoclear_setup.py`, one per acceptance check, every repo
   under `tmp_path`.
2. `crew_autoclear_setup.py`, below `had_repo_local_opt_in`: `scan_opted_in_repos` (an explicit
   stack walk: depth 1 is a root's children, a candidate is not descended into, dot-directories,
   `node_modules` and symlinks are skipped, the current repo is skipped by realpath; a directory
   reached again through an overlapping root at a shallower level is walked again so the depth
   limit does not depend on root order), `_scan_candidate` (either file opted in -> found; a present
   file that is not a JSON object and no opt-in in the other -> unreadable, never "not opted in"),
   `check_scan_roots`, `_widening_message`, `widening_refusal`, `WideningRefused` (a `ValueError`,
   so `main`'s existing handler gives exit 1).
3. `detect_onlyRepos_widening` and `apply_migrate_to_repo` keep their positional parameters and
   gain keyword-only `scan_roots` / `scan_depth`. The roots are checked before anything is read; the
   refusals run before the machine write, so nothing is written on a refusal.
4. Notes are prefixed `.crew/<file>: ` in `apply_migrate_to_repo` only; `plan_migrate_context` and
   `plan-migrate` are unchanged.
5. `check_no_forbidden_words` reads `forbidden_word_samples()`, which adds a scan with a found and an
   unreadable entry and both refusals.
6. The config-reader count for `crew_autoclear_setup.py` goes 2 -> 3 (the scan's `.crew` join).
7. Docs: migrate.md (in place, stays at 115 lines), CONFIG.md's `onlyRepos` row, auto-cycle.md
   (troubleshooting guide rebuilt), the code map, the regenerated rules file; the cloud handoff
   file and its README row are removed.
