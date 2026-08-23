# Stop hook (native Windows). Estimates context use from transcript size and asks
# for a handoff once per session. Exit 2 returns control to the model.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue
if (-not (Test-Path ".crew/config.json")) { exit 0 }
if (-not $d.transcript_path -or -not (Test-Path $d.transcript_path)) { exit 0 }

$cfg = (Get-Content .crew/config.json -Raw | ConvertFrom-Json).context
if ($null -eq $cfg -or $cfg.enabled -eq $false) { exit 0 }
$warnAt = if ($cfg.warnAt) { $cfg.warnAt } else { 0.8 }
$budget = if ($cfg.budgetTokens) { $cfg.budgetTokens } else { 200000 }
$path   = if ($cfg.handoffPath) { $cfg.handoffPath } else { ".work/HANDOFF.md" }

$marker = ".crew/.handoff-requested"
if (Test-Path $marker) { exit 0 }

$bytes = (Get-Item $d.transcript_path).Length
$est = [int]($bytes / 4 * 0.75)
$pct = $est / $budget
if ($pct -lt $warnAt) { exit 0 }

New-Item -ItemType File -Path $marker -Force | Out-Null
$pctH = [int]($pct * 100)
[Console]::Error.WriteLine(@"
Context is at roughly $pctH% of budget (estimated from transcript size).

Before ending this turn, write the handoff note to $path following the
crew-context skill. Keep it to pointers and one short "next action" - do not
write a long narrative summary. A session this deep into its context is the
least reliable narrator of what it just did.

Then tell me the note is ready so I can /clear or /compact. Do not start new
work in this session.
"@)
exit 2
