# SessionStart hook (native Windows). Prints the handoff note on clear/compact/resume.
# stdout from SessionStart is injected as context.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue

Remove-Item ".crew/.handoff-requested" -ErrorAction SilentlyContinue

# SessionStart fires once per SOURCE EVENT (startup, clear, compact, resume,
# fork), not once per session -- claiming on session id alone would let the
# `startup` firing burn the claim, exit here on the filter having done
# nothing, and make the `clear` firing lose the race: the handoff would never
# be read after /clear, which is the entire point of this hook. So the claim
# comes AFTER the filter and is keyed on session+source together. Same hook
# name and key shape as handoff-read.sh so the two race for the same marker.
if ($d.source -notin @("clear","compact","resume","fork")) { exit 0 }
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'hook_once.py') 'handoff-read' "$($d.session_id)-$($d.source)"
if ($LASTEXITCODE -ne 0) { exit 0 }

if (-not (Test-Path ".crew/config.json")) { exit 0 }
$cfg = Get-Content .crew/config.json -Raw | ConvertFrom-Json

# When context.autoResume is exactly true, pm_brief._resume_context() owns
# the handoff in this mode: it folds the same text plus the extracted next
# action into its additionalContext payload. Standing down here keeps the
# handoff to a single emitter -- printing it here too would inject it twice.
if ($cfg.context.autoResume -is [bool] -and $cfg.context.autoResume -eq $true) { exit 0 }

$path = if ($cfg.context.handoffPath) { $cfg.context.handoffPath } else { ".work/HANDOFF.md" }
if (-not (Test-Path $path)) { exit 0 }

Write-Output "## Handoff from the previous session ($($d.source))"
Write-Output ""
Get-Content $path
Write-Output ""
Write-Output "The working tree is the source of truth. Verify the notes above against git diff before acting on them."
exit 0
