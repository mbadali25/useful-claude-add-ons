# PreToolUse deploy gate for the PowerShell tool. Mirrors promote-gate.sh.
# Fires only on a command matching a `deploy` entry in .crew/verify.json
# -> environments. Exit 2 blocks.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cmd = $d.tool_input.command
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $root -ErrorAction SilentlyContinue
if (-not (Test-Path .crew/verify.json)) { exit 0 }

try { $vm = Get-Content .crew/verify.json -Raw | ConvertFrom-Json } catch { exit 0 }
if (-not $vm.environments) { exit 0 }

# Which environment does this command deploy to?
$envName = $null
foreach ($p in $vm.environments.PSObject.Properties) {
  foreach ($dep in $p.Value.deploy) {
    if ($dep -and ($cmd -like "*$dep*" -or $dep -like "*$cmd*")) { $envName = $p.Name; break }
  }
  if ($envName) { break }
}
if (-not $envName) { exit 0 }

# --- Emergency lane -------------------------------------------------------
#
# Twin of crew_incident_active / crew_incident_log in _common.sh, inline for
# the same reason as in verify-gate.ps1: a dot-sourced function is invisible
# to scripts/check-powershell.ps1's static call check. See
# hooks/scripts/crew_incident.py for the file format.
function Test-CrewIncidentActive {
  if (-not (Test-Path ".crew/incident.json")) { return $false }
  try {
    $c = Get-Content .crew/config.json -Raw -ErrorAction Stop | ConvertFrom-Json
    if ($c.emergency -and $c.emergency.standDown -eq $false) { return $false }
  } catch { }
  try { $inc = Get-Content .crew/incident.json -Raw -ErrorAction Stop | ConvertFrom-Json }
  catch { return $false }
  if (-not $inc.expiresAtEpoch) { return $false }
  return ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -lt [long]$inc.expiresAtEpoch)
}

function Write-CrewIncidentSkip([string]$Gate, [string]$Detail) {
  if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force | Out-Null }
  $log = ".crew/incident-skips.log"
  # The log is tab-separated and line-oriented, and a detail can carry an
  # environment name, a rollback path or a rollbackReason straight out of
  # .crew/verify.json - a tab or a newline in one would forge a row. _common.sh
  # and crew_incident.py normalise the same way.
  $Gate = $Gate -replace "[`t`r`n]", " "
  $Detail = $Detail -replace "[`t`r`n]", " "
  $row = "$Gate`t$Detail"
  # One row per gate+detail per incident, not per turn: the closing report is a
  # debt list, and the same unrun check is one debt however many turns declined
  # to run it. _common.sh applies the same rule.
  if (Test-Path $log) {
    foreach ($line in (Get-Content $log -ErrorAction SilentlyContinue)) {
      $parts = $line -split "`t", 2
      if ($parts.Count -eq 2 -and $parts[1] -eq $row) { return }
    }
  }
  $epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  Add-Content -Path $log -Value "$epoch`t$row" -Encoding utf8
}

# An open incident turns every block below into a recorded skip. The checks
# still RUN - they are file reads, not test suites, and the debt list is worth
# far more when it names the precondition that was unmet.
$incident = Test-CrewIncidentActive

$cfg = $vm.environments.$envName
$sha = (git rev-parse --short HEAD 2>$null)
$problems = New-Object System.Collections.Generic.List[string]

if (-not $sha) {
  $why = "not a git repository - cannot establish what is being deployed."
  if ($incident) {
    Write-CrewIncidentSkip "promote" "$envName at unknown-sha: $why"
    exit 0
  }
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName): $why")
  exit 2
}
if ((git status --porcelain 2>$null)) {
  $why = "the working tree is dirty. You would be deploying $sha plus changes that are in no commit and no review."
  if ($incident) {
    Write-CrewIncidentSkip "promote" "$envName at ${sha}: $why"
    exit 0
  }
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName): $why")
  exit 2
}

# requires: an all-pass row for THIS sha
function Test-Promoted([string]$name, [string]$sha) {
  if (-not (Test-Path .work/PROMOTIONS.md)) { return $false }
  foreach ($line in Get-Content .work/PROMOTIONS.md) {
    if ($line -notmatch '\|') { continue }
    $cells = ($line.Trim().Trim('|') -split '\|') | ForEach-Object { $_.Trim() }
    if ($cells.Count -lt 6) { continue }
    if ($cells[1] -eq $name -and $cells[2].StartsWith($sha.Substring(0, [Math]::Min(7, $sha.Length)))) {
      return ($cells[3] -ieq 'pass' -and $cells[4] -ieq 'pass' -and $cells[5] -ieq 'pass')
    }
  }
  return $false
}
foreach ($up in $cfg.requires) {
  if (-not (Test-Promoted $up $sha)) {
    $problems.Add("'$up' has no all-pass row for sha $sha in .work/PROMOTIONS.md. Run /crew:promote $up first, and let it record the result.")
  }
}

# rollback runbook: required for every gated environment. Fail CLOSED - an
# absent key used to mean "no rollback needed"; now it blocks the deploy. The
# only way to opt out is rollback: "none" plus a rollbackReason.
if (-not ($cfg.PSObject.Properties.Name -contains 'rollback')) {
  $problems.Add("'$envName' has no 'rollback' key in .crew/verify.json. Add rollback: `"<path to a runbook>`", or rollback: `"none`" plus a rollbackReason string explaining why $envName does not need one. Fix: edit the '$envName' block in .crew/verify.json.")
} elseif ($cfg.rollback -eq 'none') {
  $reason = "$($cfg.rollbackReason)".Trim()
  if (-not $reason) {
    $problems.Add("'$envName' sets rollback: `"none`" but has no rollbackReason. State why $envName does not need a rollback plan. Fix: add a rollbackReason string next to rollback in .crew/verify.json.")
  }
} elseif (-not $cfg.rollback) {
  $problems.Add("'$envName' has an invalid rollback value. Fix: set rollback to a runbook path, or to the literal string `"none`" plus a rollbackReason.")
} elseif (-not (Test-Path $cfg.rollback)) {
  $problems.Add("the rollback runbook '$($cfg.rollback)' does not exist. No verified rollback, no deploy.")
} else {
  $txt = Get-Content $cfg.rollback -Raw
  $m = [regex]::Match($txt, 'last[ _-]?verified\s*[:=]\s*(\d{4}-\d{2}-\d{2})', 'IgnoreCase')
  if (-not $m.Success) {
    $problems.Add("'$($cfg.rollback)' has no 'last verified: YYYY-MM-DD' line. An unverified rollback is not a rollback.")
  } else {
    $age = (Get-Date).Date - [datetime]::ParseExact($m.Groups[1].Value, 'yyyy-MM-dd', $null)
    if ($age.Days -gt 90) {
      $problems.Add("'$($cfg.rollback)' was last verified $($age.Days) days ago (ceiling is 90). Re-run it against a real environment first.")
    }
  }
}

if ($cfg.requireHuman) {
  $marker = ".crew/.approved-$envName-$sha"
  if (-not (Test-Path $marker)) {
    $problems.Add("this environment requires explicit human approval. Show the sha, the diff summary and the last promotion, get a yes, then create the marker: New-Item -ItemType File $marker")
  }
}

if ($problems.Count -gt 0 -and $incident) {
  # One row per unmet precondition, so the closing report names them all.
  $problems | ForEach-Object { Write-CrewIncidentSkip "promote" "$envName at ${sha}: $_" }
  $problems.Clear()
}

if ($problems.Count -gt 0) {
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName, sha $sha):")
  $problems | ForEach-Object { [Console]::Error.WriteLine("  - $_") }
  [Console]::Error.WriteLine("")
  [Console]::Error.WriteLine("These are the pre-deploy gates from .crew/verify.json. Fix them, or set")
  [Console]::Error.WriteLine("verifyGate:false in .crew/config.json if this repo should not be gated.")
  exit 2
}

New-Item -ItemType Directory -Path .crew -Force -ErrorAction SilentlyContinue | Out-Null
Set-Content -Path .crew/.deploy-in-flight -Value "$envName $sha" -Encoding ASCII
exit 0
