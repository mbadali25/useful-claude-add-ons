# Stop hook. Re-engages the crew PM when the project state actually changed.
# PowerShell twin of pm-pulse.sh -- both delegate to pm_pulse.py so neither can
# drift from the other.
$ErrorActionPreference = 'SilentlyContinue'

# No platform check here on purpose, for the same reason as pm-brief.ps1: Stop
# has no matcher, so this and pm-pulse.sh both fire wherever both interpreters
# exist, and deciding by interpreter is unsound. pm_pulse.py de-duplicates on
# the state fingerprint, so exactly one of us speaks per changed state
# regardless of which arrives first or how many of us there are.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }

# NOT `exit 0` like pm-brief.ps1. This hook exits 2 to block the stop and hand
# its findings back to the model; swallowing that code turns every pulse into a
# silently-dropped finding. hooks.json appends `; exit $LASTEXITCODE` for the
# same reason one level up -- `& script.ps1` inside -Command does not propagate
# it either.
& $py (Join-Path $dir 'pm_pulse.py')
exit $LASTEXITCODE
