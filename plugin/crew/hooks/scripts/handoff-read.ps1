# SessionStart hook (native Windows). Prints the handoff note on clear/compact/resume.
# stdout from SessionStart is injected as context.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue

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
