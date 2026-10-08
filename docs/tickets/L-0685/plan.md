# L-0685 plan

Written by the implementing session, 2026-10-05, on `rush/g5-platform` after L-0684 (gizmoduck
0.5.9 there). `bootstrap.sh` had moved since the spec (C-0008: `BIN_DIR`/`OPT_DIR` overrides,
`resolve_latest_tag` with a git fallback, checksum checks for Nuclei and trivy, a sourced-mode guard
and `test_bootstrap_version.py`), so the plan works on that shape.

1. Privilege as one array, `PRIV`, used through `as_root`; every `sudo` call site becomes
   `as_root`. Sourced, `PRIV=(sudo)` so the C-0008 suite's stub still sees `sudo ...`;
   `decide_privilege` (run only when executed) sets it from `id -u` and `command -v sudo`.
2. `--user`: `set_user_dirs` points `BIN_DIR`, `OPT_DIR`, `STAGE_DIR` (`.download`) and `ZAP_ROOT`
   (`zap/`) into the tool home, whose rule is a bash copy of `scanners/base.py tool_home()`.
   Package-only tools go through `user_package_tool` (present or SKIPPED); Java tools through
   `user_needs_java17` (FAILED naming the package). Prerequisites checked before anything runs.
3. `--dry-run`: `print_plan`, builtins and `command -v` only, after the privilege and
   prerequisite decisions so their refusals show the same in a dry run.
4. `github_api` sends `GITHUB_TOKEN` as `-H @<(...)`; `finish` prints the summary and returns the
   status, called last so the script exits with it.
5. Tests in `test_bootstrap.py` by the spec's names; `test_bootstrap_version.py` follows the
   `env DEBIAN_FRONTEND=noninteractive` prefix, and its `sudo` stub must treat `env ... apt-get`
   as apt so no test can reach a real apt-get.
6. README "CI and containers", SKILL.md and doctor.md lines, CHANGELOG, TODO follow-ups,
   gizmoduck 0.5.10. The real container runs are not made here (shared host).
