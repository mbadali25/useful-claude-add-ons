# SessionStart hook. Prints the crew PM's brief; stdout is injected as context.
# PowerShell twin of pm-brief.sh -- both delegate to pm_brief.py so neither can
# drift from the other.
$ErrorActionPreference = 'SilentlyContinue'

# No platform check here on purpose. SessionStart has no matcher, so this and
# pm-brief.sh both fire wherever both interpreters exist -- but deciding by
# interpreter is unsound (on Windows, `bash` on PATH is normally the WSL
# launcher, which cannot resolve this script's own directory). pm_brief.py
# claims the session once and the loser prints nothing, so it does not matter
# which of us arrives first or how many of us there are.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'pm_brief.py')
exit 0
