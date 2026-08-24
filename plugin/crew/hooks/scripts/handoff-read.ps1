# SessionStart hook (native Windows). Prints the handoff note on clear/compact/resume.
# stdout from SessionStart is injected as context.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue

# Both flavours of this hook are registered on SessionStart, which has no
# matcher, so both fire wherever both interpreters exist. Only the winner of
# this claim does any work; the loser exits quietly. Same hook name as
# handoff-read.sh so the two race for the same marker.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'hook_once.py') 'handoff-read' $d.session_id
if ($LASTEXITCODE -ne 0) { exit 0 }

Remove-Item ".crew/.handoff-requested" -ErrorAction SilentlyContinue

if ($d.source -notin @("clear","compact","resume")) { exit 0 }
if (-not (Test-Path ".crew/config.json")) { exit 0 }
$cfg = Get-Content .crew/config.json -Raw | ConvertFrom-Json
$path = if ($cfg.context.handoffPath) { $cfg.context.handoffPath } else { ".work/HANDOFF.md" }
if (-not (Test-Path $path)) { exit 0 }

Write-Output "## Handoff from the previous session ($($d.source))"
Write-Output ""
Get-Content $path
Write-Output ""
Write-Output "The working tree is the source of truth. Verify the notes above against git diff before acting on them."
exit 0
