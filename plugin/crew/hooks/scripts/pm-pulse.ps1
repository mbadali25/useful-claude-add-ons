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

# A PATH entry matching a bare command name is not necessarily something
# Windows can actually launch. `Get-Command python3 -All` returns an
# EXTENSIONLESS file (a pyenv/conda/direnv-style POSIX shim, or - as
# verify-gate.ps1's regression test reproduces it - a shebang script planted
# ahead of the real interpreter) as `CommandType: Application` with a real
# `.Source`, exactly like a genuine python3.exe. Nothing before this point
# tells the two apart, and invoking one does not fail cleanly -- see
# verify-gate.ps1's own copy of this function for the measured hang. Only
# trust a candidate Windows' own CreateProcess can run directly: an extension
# listed in $env:PATHEXT. Duplicated inline rather than dot-sourced for the
# same reason Resolve-CrewPython below is: invisible to
# scripts/check-powershell.ps1's static check otherwise.
function Test-CrewWindowsExecutable([string]$Path) {
  if (-not $Path) { return $false }
  $ext = [System.IO.Path]::GetExtension($Path)
  if (-not $ext) { return $false }
  $pathExt = $env:PATHEXT -split ';' | Where-Object { $_ }
  return ($pathExt -contains $ext.ToUpperInvariant())
}

function Resolve-CrewPython {
  # BYTE-FOR-BYTE the resolver in verify-gate.ps1, and duplicated inline for
  # the reason that file's own header gives: a function arriving by
  # dot-source is invisible to scripts/check-powershell.ps1's static check,
  # and a mis-named function once shipped and killed every menu on Windows.
  # Ten duplicated lines is the cheaper mistake. A parity test asserts the two
  # copies still agree, because a hand-copy with no guard is this repository's
  # most repeated defect.
  #
  # What the old one-liner cost HERE is worse than in verify-gate. This hook
  # exits 2 to block the stop and hand the PM's findings back to the model.
  # hooks.json registers it with no -NoProfile, so a `function python { }` in
  # a user profile is returned AHEAD of any python.exe with an empty .Source;
  # that empty value then failed `if (-not $py)` and the hook exited 0. The
  # PM's findings, including the blocking ones, were dropped in silence on a
  # machine with python installed -- the gate wearing the exit code of a pass.
  # The WindowsApps App Execution Alias fails the other way: it is a real
  # Application with a real .Source, so it resolved and was INVOKED, and the
  # Store stub does not run pm_pulse.py.
  #
  # THIRD failure mode, added to restore parity with verify-gate.ps1 after
  # that file's own extensionless-PATH-shim guard (rule[8]'s non-terminating
  # hang) landed there without this copy -- the exact "one hook hardened, its
  # byte-pinned twin left behind" defect the parity test below exists to
  # catch. See Test-CrewWindowsExecutable above for the measurement.
  $names = @('python3', 'python')
  foreach ($name in $names) {
    $candidates = Get-Command $name -All -ErrorAction SilentlyContinue
    foreach ($cmd in $candidates) {
      if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
      if ($cmd.Source -match 'WindowsApps') { continue }
      if (-not (Test-CrewWindowsExecutable $cmd.Source)) { continue }
      return $cmd.Source
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
