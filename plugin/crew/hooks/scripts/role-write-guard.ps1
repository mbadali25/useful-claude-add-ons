# PreToolUse gate on Write/Edit, keyed on `agent_type`. PowerShell twin of
# role-write-guard.sh -- both delegate to role_write_guard.py so neither can
# drift from the other. See role-write-guard.sh for why this is NOT branched
# by tool_name the way promote-gate.ps1 is.
param(
  # Probe seam, the twin of verify-gate.ps1's -PrintPython and
  # pm-pulse.ps1's: prints the interpreter Resolve-CrewPython would use and
  # exits 0 without touching stdin or running the guard. This hook's only
  # consumer is Claude Code's PreToolUse hook, which pipes JSON on stdin and
  # has no interactive path to probe resolution.
  [switch]$PrintPython
)

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-CrewPython {
  # BYTE-FOR-BYTE the resolver in verify-gate.ps1 and pm-pulse.ps1, and
  # duplicated inline for the reason those files' own headers give: a
  # function arriving by dot-source is invisible to
  # scripts/check-powershell.ps1's static check, and a mis-named function
  # once shipped and killed every menu on Windows. Ten duplicated lines is
  # the cheaper mistake. `tests/test_role_write_guard.py` asserts this copy
  # still agrees with the other two, because a hand-copy with no guard is
  # this repository's most repeated defect.
  #
  # The first draft of this file used the un-hardened one-liner
  # `(Get-Command python3, python | Select-Object -First 1).Source` -- the
  # exact code pm-pulse.ps1's own header names as the bug that dropped the
  # PM's blocking findings in silence. Here the failure is a different shape
  # again: this hook FAILS OPEN (allows, unjudged) when it cannot resolve an
  # interpreter at all, by design -- see role-write-guard.sh -- but the
  # un-hardened one-liner does not fail that way. It either returns an empty
  # `.Source` (a profile function named `python`), which the caller already
  # treats as "no usable python", OR it returns the WindowsApps stub's real
  # `.Source` and INVOKES it, opening the Store instead of running
  # role_write_guard.py -- silently skipping the write-scope check under
  # `guards.roleWrites: block` on any machine where that alias resolves
  # first, with no error and no log row.
  $names = @('python3', 'python')
  foreach ($name in $names) {
    $candidates = Get-Command $name -All -ErrorAction SilentlyContinue
    foreach ($cmd in $candidates) {
      if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
      if ($cmd.Source -match 'WindowsApps') { continue }
      return $cmd.Source
    }
  }
  return ''
}

if ($PrintPython) {
  Write-Output (Resolve-CrewPython)
  exit 0
}

$raw = [Console]::In.ReadToEnd()

$py = Resolve-CrewPython
if (-not $py) {
  [Console]::Error.WriteLine("role-write-guard: no usable python - cannot judge this write, allowing it unjudged.")
  exit 0
}

$raw | & $py (Join-Path $dir 'role_write_guard.py')
exit $LASTEXITCODE
