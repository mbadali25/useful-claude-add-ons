# Stop hook (native Windows). Estimates context use from transcript size and asks
# for a handoff once per session. Exit 2 returns control to the model.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue

if (-not (Test-Path ".crew/config.json")) { exit 0 }
if (-not $d.transcript_path -or -not (Test-Path $d.transcript_path)) { exit 0 }

# Loop safety, layer 1: Claude Code is already continuing because of a stop
# hook -- do not pile on more feedback. Layer 2 is the once-per-session
# marker below. Layer 3 is Claude Code's own 8-consecutive-block backstop.
if ($d.stop_hook_active -eq $true) { exit 0 }

# No hook_once claim here on purpose: Stop fires once per TURN against a
# stable session id, so a session-scoped claim taken on turn 1 would suppress
# the context nag for the rest of the session. $marker below (.handoff-requested)
# is the real once-per-session gate for this hook, reset by handoff-read.ps1 at
# the next SessionStart -- that stays.

$cfg = (Get-Content .crew/config.json -Raw | ConvertFrom-Json).context
if ($null -eq $cfg -or $cfg.enabled -eq $false) { exit 0 }
$warnAt = if ($cfg.warnAt) { $cfg.warnAt } else { 0.8 }
$budget = if ($cfg.budgetTokens) { $cfg.budgetTokens } else { 200000 }
$path   = if ($cfg.handoffPath) { $cfg.handoffPath } else { ".work/HANDOFF.md" }
$autoWrapUp = $cfg.autoWrapUp -eq $true

$marker = ".crew/.handoff-requested"
if (Test-Path $marker) { exit 0 }

$bytes = (Get-Item $d.transcript_path).Length
$est = [int]($bytes / 4 * 0.75)
$pct = $est / $budget
if ($pct -lt $warnAt) { exit 0 }

New-Item -ItemType File -Path $marker -Force | Out-Null
$pctH = [int]($pct * 100)
if ($autoWrapUp) {
[Console]::Error.WriteLine(@"
You are at roughly $pctH% of the context budget. Reach a stopping point
now: finish or safely abandon the change in flight, write $path per the
crew-context skill, update the ticket, then tell the user the session is
ready to clear. Do not start new work.
"@)
} else {
[Console]::Error.WriteLine(@"
Context is at roughly $pctH% of budget (estimated from transcript size).

Before ending this turn, write the handoff note to $path following the
crew-context skill. Keep it to pointers and one short "next action" - do not
write a long narrative summary. A session this deep into its context is the
least reliable narrator of what it just did; the files are more trustworthy
than the recollection.

Then tell me the note is ready so I can /clear or /compact. Do not start new
work in this session.
"@)
}
exit 2
