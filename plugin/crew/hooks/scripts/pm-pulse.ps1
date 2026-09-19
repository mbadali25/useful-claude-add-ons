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

$ErrorActionPreference = 'SilentlyContinue'

# No platform check here on purpose, for the same reason as pm-brief.ps1: Stop
# has no matcher, so this and pm-pulse.sh both fire wherever both interpreters
# exist, and deciding by interpreter is unsound. pm_pulse.py de-duplicates on
# the state fingerprint, so exactly one of us speaks per changed state
# regardless of which arrives first or how many of us there are.
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

$py = Resolve-CrewPython
if (-not $py) { exit 0 }

# NOT `exit 0` like pm-brief.ps1. This hook exits 2 to block the stop and hand
# its findings back to the model; swallowing that code turns every pulse into a
# silently-dropped finding. hooks.json appends `; exit $LASTEXITCODE` for the
# same reason one level up -- `& script.ps1` inside -Command does not propagate
# it either.
& $py (Join-Path $dir 'pm_pulse.py')
exit $LASTEXITCODE
