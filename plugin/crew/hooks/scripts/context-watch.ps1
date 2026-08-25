# Stop hook (native Windows). Mirrors context-watch.sh: reads how full the
# context window actually is and, once past the threshold, asks Claude to write a
# handoff note before ending the turn. Exit 2 returns control to the model with
# the reason on stderr.
#
# NOTHING HERE RUNS until a repository has .crew/config.json - crew is
# per-repository and its hooks are inert until `/crew:init`.
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
# $null test, not truthiness: warnAt 0 is a legal "always fire" and 0 is falsy.
$warnAt     = if ($null -ne $cfg.warnAt) { [double]$cfg.warnAt } else { 0.8 }
$configured = if ($cfg.budgetTokens) { [long]$cfg.budgetTokens } else { 0 }
$handoff    = if ($cfg.handoffPath) { $cfg.handoffPath } else { ".work/HANDOFF.md" }
$autoWrapUp = $cfg.autoWrapUp -eq $true

$marker = ".crew/.handoff-requested"
if (Test-Path $marker) { exit 0 }

# Read the ACTUAL window occupancy, not a guess at it.
#
# Every assistant turn in the transcript carries message.usage, and the last one
# holds the real prompt size: input + cache_read + cache_creation. That IS the
# context window, measured by the thing that filled it.
#
# This replaced a file-size heuristic (bytes/4*0.75) that the bash flavour had
# already dropped. The transcript is cumulative - it keeps every turn ever
# written, including ones a compaction already discarded - so file size measures
# how much a session has produced, not how full the window is. Measured on real
# Windows sessions the heuristic read 195%, 158% and 664% of a 200k budget: it
# fired on turn one, every session.

# Known context windows, first match wins, so the specific keys sit above the
# generic ones. The Claude 5 family (fable, opus-5, sonnet-5) ships with 1M
# natively; the 4.x generation is 200k unless the id carries a "[1m]" suffix -
# and the transcript often records the base id without it, so this table is a
# starting point, not the last word. The observed high-water mark below
# corrects it.
$windows = @(
  @("[1m]",     1000000),
  @("fable",    1000000),
  @("opus-5",   1000000),
  @("sonnet-5", 1000000),
  @("haiku",     200000),
  @("opus",      200000),
  @("sonnet",    200000)
)
$tiers = @(200000, 500000, 1000000, 2000000)

$last = $null; $model = ""; [long]$peak = 0; [long]$mainBytes = 0
try {
  foreach ($line in [System.IO.File]::ReadLines($d.transcript_path)) {
    if (-not $line) { continue }
    # Subagent turns are not main-window occupancy: the main window only ever
    # sees the agent's returned summary. Current builds keep them in
    # <session>/subagents/*.jsonl, which this never opens; older builds wrote
    # them inline flagged isSidechain. Skip those - from the byte count too, so
    # the size fallback below does not count them either.
    if ($line -match '"isSidechain"\s*:\s*true') { continue }
    $mainBytes += [System.Text.Encoding]::UTF8.GetByteCount($line) + 1
    if ($line.IndexOf('"usage"') -lt 0) { continue }
    try { $rec = $line | ConvertFrom-Json -ErrorAction Stop } catch { continue }
    $msg = $rec.message
    if ($null -eq $msg) { continue }
    $usage = $msg.usage
    if ($null -eq $usage -or -not $usage.PSObject.Properties['cache_read_input_tokens']) { continue }
    $last = $usage
    if ($msg.model -and -not ([string]$msg.model).StartsWith("<")) { $model = [string]$msg.model }
    [long]$tot = [long]$usage.input_tokens + [long]$usage.cache_read_input_tokens + [long]$usage.cache_creation_input_tokens
    if ($tot -gt $peak) { $peak = $tot }
  }
} catch { }

if ($null -ne $last) {
  [long]$used = [long]$last.input_tokens + [long]$last.cache_read_input_tokens + [long]$last.cache_creation_input_tokens
  $source = "exact"
} else {
  [long]$used = [math]::Floor($mainBytes / 4 * 0.75)
  $source = "estimated"
}

function Next-Tier([long]$above) {
  foreach ($t in $tiers) { if ($t -gt $above * 1.05) { return [long]$t } }
  return [long]($above * 2)
}

if ($configured -gt 0) {
  [long]$budget = $configured; $how = "configured"
} else {
  $low = $model.ToLowerInvariant()
  [long]$budget = 200000
  foreach ($w in $windows) { if ($low.IndexOf($w[0]) -ge 0) { $budget = [long]$w[1]; break } }
  $label = if ($model) { $model } else { "unknown" }
  $how = "auto:$label"
}

# Self-correct. If this session has already held more tokens than the budget
# claims the window is, the budget is wrong: a "[1m]" variant records its base
# id, and an older /crew:init pinned budgetTokens: 200000 into every config
# before the 1M models arrived. Observed usage cannot exceed the real window,
# so it is the better source - but ONLY a peak the window could not hold proves
# that. An earlier 95% margin bumped a correct 1M entry to the 2M tier once a
# session passed 950k, and the gate then never fired at all.
if ($peak -gt $budget) { $budget = Next-Tier $peak; $how = "$how+observed" }

if ($budget -le 0 -or ($used / $budget) -lt $warnAt) { exit 0 }

New-Item -ItemType File -Path $marker -Force | Out-Null
# Truncate, not round, to match the bash flavour's int().
$pctH    = [math]::Floor($used / $budget * 100)
$inv     = [Globalization.CultureInfo]::InvariantCulture
$usedH   = $used.ToString("N0", $inv)
$budgetH = $budget.ToString("N0", $inv)

try { & "$PSScriptRoot/notify.ps1" waiting "context $pctH% - writing handoff" 2>$null | Out-Null } catch { }

# Report the absolute numbers, not only the percentage. A budgetTokens that does
# not match the model in use is otherwise invisible - it just makes the gate
# fire early forever, and a warning that is always on is one nobody reads.
$budgetNote = " Set context.budgetTokens in .crew/config.json to pin it."
if ($how -eq "configured+observed") {
  $budgetNote = @"
 context.budgetTokens in .crew/config.json says a smaller window,
but this session has already held more than that - and observed usage cannot
exceed the real window, so the larger figure wins. That pin is stale; set it to
null to let crew work the window out from the model.
"@.TrimEnd()
} elseif ($how -like "auto:*+observed") {
  $budgetNote = @"
 The model's id said a smaller window, but this session has
already held more than that - and observed usage cannot exceed the real window,
so the larger figure wins. A 1M variant reports its base model id, which is why
the id alone is not trusted. Pin it with context.budgetTokens if you prefer.
"@.TrimEnd()
} elseif ($how -eq "configured") {
  $budgetNote = @"
 That came from .crew/config.json. Remove it to let crew work the
window out from the model and this session's own usage.
"@.TrimEnd()
}

$note = ""
if ($source -eq "estimated") {
  $note = @"

This figure is a fallback estimate from transcript size, not a measurement -
no usage record was found yet. It reads high after a compaction.
"@
}

if ($autoWrapUp) {
[Console]::Error.WriteLine(@"
You are at roughly $pctH% of the context budget. Reach a stopping point
now: finish or safely abandon the change in flight, write $handoff per the
crew-context skill, update the ticket, then tell the user the session is
ready to clear. Do not start new work.
"@)
} else {
[Console]::Error.WriteLine(@"
Context: $usedH of $budgetH tokens ($pctH%), read from the transcript's
last usage record.$note

Budget source: $how.$budgetNote

Before ending this turn, write the handoff note to $handoff following the
crew-context skill. Keep it to pointers and one short "next action" - do not
write a long narrative summary. A session this deep into its context is the
least reliable narrator of what it just did; the files are more trustworthy
than the recollection.

Then tell me the note is ready so I can /clear or /compact. Do not start new
work in this session.
"@)
}
exit 2
