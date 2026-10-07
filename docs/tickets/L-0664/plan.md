# L-0664 plan (implementing session, 2026-10-05, rush/g4-deploy)

Built on T-0062 (this branch): `_promote_dispatch.py` and the Bash flavour's dispatch block.

1. RED: `test_promote_gate_dispatch.py` runs every T-0062 case on both flavours (`tree.FLAVOURS`:
   the `ps1` cases are `slow` and skip without PowerShell 7), plus the no-python cases (PATH holding
   git only). `test_ps1_python_probe.py`'s carrier list (a list, U1) gains `promote-gate`.
2. `_promote_dispatch.py` takes `--shell powershell -` (the command on stdin, read as PowerShell).
   Without the option it behaves exactly as before; promote-gate.sh is unchanged.
3. `promote-gate.ps1`: the shared `Resolve-CrewPython`, copied byte for byte; every declared deploy
   string is collected while matching; when containment matches nothing, the helper is called with
   the map's dirty/blob environment, `block` stops (incident lane included), `env` names the
   environments, a failing helper blocks. The committed map is read for a dispatch when the working
   map is deleted, as the .sh does. No python: a command naming `gh` with `workflow` or `dispatches`
   blocks when a declared deploy names them too; otherwise exit 0 as before.
4. Mutations in `promote_tree_mutations.py` (helper call removed, could-not-tell read as no match,
   no-python exiting 0, helper failure read as empty); docs drop "containment-only".

Not done here: a native Windows run (the pwsh cases ran on Linux with PowerShell 7). Found: T-0009's
PowerShell reading does not follow text piped into `bash` (`echo gh workflow run ... | bash` is
"none" on PowerShell, could-not-tell on Bash); reported as a reader follow-up.
