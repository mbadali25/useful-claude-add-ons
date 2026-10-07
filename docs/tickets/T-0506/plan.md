# T-0506 plan

Written by the implementing session, 2026-10-05, on `rush/g5-platform`.

1. `scripts/_test/pwsh-isolated.sh` first, every case in the spec's acceptance list, against a
   stub pwsh under mktemp (it exports its own `XDG_CACHE_HOME` under that directory before the
   first launch, so L-0557's guard sees no shared-cache launch).
2. `scripts/pwsh-isolated.sh`, POSIX sh: resolve (`$PWSH`, `pwsh`, `pwsh.exe`, the four Windows
   paths the old `.ps1` rule tried), `mktemp -d` and an assigned `XDG_CACHE_HOME` inside it, pwsh
   in the background with stdin from /dev/null and `wait`, TERM/INT/HUP forwarded to the child,
   the directory removed on every path, `TOOL BROKEN: pwsh` added for a status of 128 or more.
3. The four launch sites: the `.ps1` rule's run entry, `_verify/smoke.sh` (three launches),
   `_verify/run-all.sh` (two, through `env PWSH=... sh` so `timeout` still signals a direct child),
   gate-runner's `check-powershell` step (`bash scripts/pwsh-isolated.sh ...`, needs bash and pwsh,
   ci unchanged) plus a table step and a `marketplace.yml` step for the suite, and
   `case_no_step_launches_pwsh_directly`.
4. `_verify/README.md` paragraph; delete `docs/handoff/cloud/T-0506.md` and its README row;
   CHANGELOG. The code-map refresh is left (see the report).
