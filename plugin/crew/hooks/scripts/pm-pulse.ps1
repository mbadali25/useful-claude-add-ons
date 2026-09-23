# Stop hook. Re-engages the crew PM when the project state actually changed.
# PowerShell twin of pm-pulse.sh -- both delegate to pm_pulse.py so neither can
# drift from the other.
param(
  # Probe seam, the twin of verify-gate.ps1's -PrintPython: prints the
  # interpreter Resolve-CrewPython would use and exits 0 without running the
  # pulse. This hook's only consumer is Claude Code's Stop hook, so without
  # a switch the resolver can only be tested by running the whole thing.
  [switch]$PrintPython
)

# Flavour guard. Both flavours are registered for every event, so on a host
# that has BOTH interpreters both would otherwise run. Stand down only when
# we can positively prove this is not Windows.
#
# $env:OS is 'Windows_NT' on BOTH Windows PowerShell 5.1 and PowerShell 7,
# and unset on Linux/macOS. A bare `if (-not $IsWindows)` is WRONG: $IsWindows
# does not exist in 5.1, so it is $null there, `-not $null` is $true, and the
# hook stands down on the one platform it exists for. crew has already shipped
# that bug once - the guard stood down on Windows and blocked nothing there.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$ErrorActionPreference = 'SilentlyContinue'

# pm_pulse.py's state-fingerprint de-duplication STAYS, and is not made
# redundant by the flavour guard above. The guard decides which FLAVOUR runs;
# the fingerprint decides which TURN speaks, and Stop fires once per turn, so
# without it every turn would get a pulse whether the state changed or not.
#
# Note what the guard does NOT do: decide by interpreter. That would be unsound
# (on Windows, `bash` on PATH is normally the WSL launcher), which is why it
# tests the OS instead. pm-pulse.sh carries a hook_once claim; this file does
# not, and that asymmetry is now harmless because the two never both run.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-CrewPython {
  # BYTE-FOR-BYTE the resolver in verify-gate.ps1, and duplicated inline for
  # the reason that file's own header gives: a function arriving by
  # dot-source is invisible to scripts/check-powershell.ps1's static check,
  # and a mis-named function once shipped and killed every menu on Windows.
  # Ten duplicated lines is the cheaper mistake. A parity test asserts the two
  # copies still agree, because a hand-copy with no guard is this repository's
  # most repeated defect.
  #
  # Windows audit wave 3, 2026-09-22: widened from metadata-only to the same
  # execute-and-verify probe role-write-guard.ps1 and verify-gate.ps1 already
  # carry, per TODO.md's own entry filed against this file -- this was the
  # weaker of the two, having neither the execute-to-verify probe nor the
  # third `py` name. What the gap cost HERE is worse than in verify-gate:
  # this hook exits 2 to block the stop and hand the PM's findings back to
  # the model. hooks.json registers it with no -NoProfile, so a
  # `function python { }` in a user profile used to be returned AHEAD of any
  # python.exe with an empty .Source; that empty value then failed
  # `if (-not $py)` and the hook exited 0. The PM's findings, including the
  # blocking ones, were dropped in silence on a machine with python
  # installed -- the gate wearing the exit code of a pass.
  #
  # NOT a blanket "reject anything containing WindowsApps" -- see
  # verify-gate.ps1's copy of this function, or `_common.sh`'s
  # `crew_py_strict` header, for why that also rejected a genuine Microsoft
  # Store Python install. The execute-and-verify probe below proves the
  # difference instead of guessing from the path.
  #
  # Review, 2026-09-22: widened again, from `Select-Object -First 1` back
  # to `Get-Command -All`, walking and probing EVERY match for a name
  # before giving up on it. `-First 1` cannot see a real interpreter
  # shadowed by a same-named profile function -- confirmed directly,
  # `Get-Command python3 -All` against a PATH carrying both returns
  # `[Function, Application]` in that order every time, and `-First 1`
  # keeps only the function -- which is EXACTLY the profile-function-python
  # failure mode this file's history already names, now reintroduced by a
  # different mechanism: the function fails the CommandType check and the
  # loop moves to the NEXT NAME rather than trying a further match for the
  # SAME one. The identical shape applies to a WindowsApps stub ahead of a
  # real interpreter under the SAME name further down PATH. Every
  # candidate is still proved by execution before being trusted, so
  # walking every match for a name costs nothing in safety.
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    $candidates = Get-Command $name -All -ErrorAction SilentlyContinue
    foreach ($cmd in $candidates) {
      if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
      $global:LASTEXITCODE = $null
      $output = $null
      try {
        $output = & $cmd.Source -c 'import sys; print(sys.executable)' 2>$null
      } catch {
        $output = $null
      }
      if ($LASTEXITCODE -ne 0 -or -not $output) { continue }
      $lines = @($output)
      if ($lines.Count -ne 1) { continue }
      $real = $lines[0]
      if ([string]::IsNullOrEmpty($real)) { continue }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
      if ($env:OS -ne 'Windows_NT') {
        $item = Get-Item -LiteralPath $real -ErrorAction SilentlyContinue
        if (-not $item -or $item.UnixMode -notmatch 'x') { continue }
      }
      return $real
    }
  }
  return ''
}

if ($PrintPython) {
  Write-Output (Resolve-CrewPython)
  exit 0
}

$py = Resolve-CrewPython
if (-not $py) { exit 0 }

# NOT `exit 0` like pm-brief.ps1. This hook exits 2 to block the stop and hand
# its findings back to the model; swallowing that code turns every pulse into a
# silently-dropped finding. hooks.json appends `; exit $LASTEXITCODE` for the
# same reason one level up -- `& script.ps1` inside -Command does not propagate
# it either.
& $py (Join-Path $dir 'pm_pulse.py')
exit $LASTEXITCODE
