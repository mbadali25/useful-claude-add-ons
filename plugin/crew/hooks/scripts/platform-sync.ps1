# SessionStart hook. PowerShell twin of platform-sync.sh -- both delegate to
# crew_platform.py so neither can drift from the other. A hook that WRITES
# config is the last place two implementations should be allowed to disagree.
$ErrorActionPreference = 'SilentlyContinue'

# No platform check here on purpose. SessionStart has no matcher, so this and
# platform-sync.sh both fire wherever both interpreters exist -- but deciding by
# interpreter is unsound (on Windows, `bash` on PATH is normally the WSL
# launcher, which would detect Linux for a native-Windows session). crew_platform
# claims the session once and the loser does nothing, and the winner detects from
# python's own view of the machine, not from which shell reached it.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'crew_platform.py')
exit 0
