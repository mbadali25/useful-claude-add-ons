# PowerShell end-of-turn gate for native Windows. Mirrors verify-gate.sh.
# Runs the checks the CHANGED FILES require, from .crew/verify.json. Exit 2 = not done.
#
# No hook_once claim here on purpose: Stop fires once per TURN against a
# stable session id, so a session-scoped claim taken on turn 1 would suppress
# every later turn's gate -- a 600-second gate that silently never runs again
# reads as "the work passed", which is worse than the double-run a claim
# would prevent. Both flavours are registered for every Stop so a
# single-shell machine always gets exactly one; on a machine with both
# shells they race for the same turn's gate. Rather than statically deferring
# to one flavour (which would leave this script permanently unreachable on
# any Windows box with Git Bash installed - nearly all of them - and its
# incident/config lane untestable), a short-lived per-turn lock lets
# whichever process gets there first do the real work while the other backs
# off; see the lock right before the expensive part below.
param(
  # Prints the bash path Resolve-CrewBash would use and exits 0 without
  # touching stdin, .crew/, or running any check. This script's only
  # consumer is Claude Code's Stop hook, which pipes JSON on stdin and has
  # no interactive path to probe resolution -- this switch is that probe,
  # for the test suite (ANEWINF-756) and for a human confirming the fix.
  [switch]$PrintBash
)

# Resolve a real bash.exe, not WSL's launcher. With WSL installed, unqualified
# `bash` on PATH normally resolves to C:\Windows\System32\bash.exe or the
# WindowsApps shim ahead of Git for Windows' bash -- inside WSL none of a
# Windows repo's tools exist (terraform, tflint, rustup, ...), so every smoke
# check reports "command not found" on a tree that is actually fine.
# ANEWINF-756.
function Resolve-CrewBash {
  # A git wrapper defined as a PowerShell function/alias (real in corporate
  # profiles) has no usable .exe path -- Get-Command still returns it ahead
  # of any git.exe on PATH, but its .Source is empty (or, for an alias,
  # points at whatever the alias targets). Only trust .Source when it is a
  # real Application entry, and wrap the whole walk-up in try/catch so any
  # surprise (e.g. Split-Path on an unexpected value) falls through to the
  # PATH-based fallback below instead of throwing out of the hook entirely.
  try {
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if ($gitCmd -and $gitCmd.CommandType -eq 'Application' -and $gitCmd.Source) {
      # git.exe's Source is `...\Git\cmd\git.exe` or `...\Git\mingw64\bin\git.exe`
      # depending on install/PATH shape; bash.exe sits at `Git\bin\bash.exe` or
      # `Git\usr\bin\bash.exe` either way. Walk up from git.exe's directory
      # (bounded) rather than assume a fixed depth.
      $dir = Split-Path $gitCmd.Source -Parent
      for ($i = 0; $i -le 3; $i++) {
        foreach ($rel in @('bin\bash.exe', 'usr\bin\bash.exe')) {
          $candidate = Join-Path $dir $rel
          if (Test-Path $candidate) { return $candidate }
        }
        $parent = Split-Path $dir -Parent
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
      }
    }
  } catch { }

  # No usable git, or no bash found near it: fall back to PATH, filtering out
  # the WSL launcher and the WindowsApps App Execution Alias shim.
  $sysRoot = $env:SystemRoot
  $candidates = Get-Command bash -All -ErrorAction SilentlyContinue
  foreach ($cmd in $candidates) {
    # Same guard as the git walk-up above, for the same reason. A `bash`
    # function or alias defined in a PowerShell profile is returned here ahead
    # of any bash.exe and its .Source is empty: .StartsWith() on that throws,
    # and returning it hands the caller an empty interpreter, so the gate
    # reports a smoke failure that is really a resolution failure. Only real
    # executables are candidates.
    if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
    $src = $cmd.Source
    if ($sysRoot -and $src.StartsWith($sysRoot, [System.StringComparison]::OrdinalIgnoreCase)) { continue }
    if ($src -match 'WindowsApps') { continue }
    return $src
  }

  # Nothing better found (non-Windows, or no WSL/WindowsApps shadowing):
  # unchanged behaviour, let the shell resolve it.
  return 'bash'
}

if ($PrintBash) {
  Write-Output (Resolve-CrewBash)
  exit 0
}

# --- Emergency lane -------------------------------------------------------
#
# Twin of crew_incident_active / crew_incident_log in _common.sh. Inline
# rather than dot-sourced from a shared _common.ps1 on purpose: PowerShell
# resolves command names at call time, so a function that arrives by
# dot-source is invisible to scripts/check-powershell.ps1's static check -
# and that check exists because a mis-named function once shipped and killed
# every menu on Windows. Ten duplicated lines is the cheaper mistake.
#
# See hooks/scripts/crew_incident.py for the file format.
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
  # One row per gate+detail per incident, not per turn. Stop fires every turn
  # and on Windows BOTH flavours of this hook run on the same Stop, so without
  # this a ten-turn incident reports forty skipped gates - a number that
  # measures the incident's length, not what is owed. _common.sh matches.
  if (Test-Path $log) {
    foreach ($line in (Get-Content $log -ErrorAction SilentlyContinue)) {
      $parts = $line -split "`t", 2
      if ($parts.Count -eq 2 -and $parts[1] -eq $row) { return }
    }
  }
  $epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  Add-Content -Path $log -Value "$epoch`t$row" -Encoding utf8
}

$raw = [Console]::In.ReadToEnd()

# Claude Code re-fires Stop after a blocking Stop hook. Without this check the
# gate blocks its own retry forever and a failing check becomes a stuck session.
try { if (($raw | ConvertFrom-Json).stop_hook_active) { exit 0 } } catch { }

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $root

if (Test-Path .crew/config.json) {
  $cfg = Get-Content .crew/config.json -Raw | ConvertFrom-Json
  if ($cfg.verifyGate -eq $false) { exit 0 }
}

# Emergency lane. An incident is open, so this turn is not blocked and the
# checks do not run - that is the entire point of declaring one, since these
# are the checks that take minutes. What would have run is written down
# instead, and /crew:emergency end reports the debt.
if (Test-CrewIncidentActive) {
  $n = @(
    (git diff --name-only HEAD 2>$null)
    (git ls-files --others --exclude-standard 2>$null)
  ) | Where-Object { $_ -and $_.Trim() }
  Write-CrewIncidentSkip "verify" "stop gate stood down with $($n.Count) changed file(s) unverified"
  exit 0
}

$changed = @()
$changed += (git diff --name-only HEAD 2>$null)
$changed += (git ls-files --others --exclude-standard 2>$null)
$changed = $changed | Where-Object { $_ -and $_.Trim() }
if (-not $changed) { exit 0 }

# LOCK: mirrors verify-gate.sh. From here on is the real (possibly minutes-
# long) smoke/verify work, and both scripts fire for the same Stop event;
# whichever gets here first claims the lock (New-Item -Directory is atomic
# even across a bash/PowerShell pair), the other backs off.
#
# No PID is recorded, deliberately -- see the long note in verify-gate.sh.
# The two flavours do not share a PID namespace on Windows ($PID here is a
# Windows pid, $$ over there is an MSYS pid) and neither can test the other's
# for liveness, so a PID-based lock fails in exactly the cross-shell case it
# exists for, and fails silently the other way when the two id spaces happen
# to collide. Age comes from the lock DIRECTORY's own creation stamp instead,
# and the holder removes its own lock as the engine exits.
$lock = ".crew/.verify-gate.lock"
$lockTtl = 700
$reclaimed = $false
if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force -ErrorAction SilentlyContinue | Out-Null }
try {
  New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
} catch {
  $holderAt = $null
  try { $holderAt = (Get-Item $lock -Force -ErrorAction Stop).LastWriteTimeUtc } catch { }
  # Unreadable stamp: assume held rather than reclaim on a guess.
  if ($null -eq $holderAt) { exit 0 }
  $age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::new($holderAt, [TimeSpan]::Zero)).TotalSeconds
  if ($age -le $lockTtl) { exit 0 }
  Remove-Item -Recurse -Force $lock -ErrorAction SilentlyContinue
  try {
    New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
  } catch { exit 0 }
  $reclaimed = $true
}
# A token of our own, so a SECOND reclaimer that deleted our fresh lock and
# took its own is detectable: whoever's token is on disk once both have
# written owns the turn, and the other backs off instead of both running.
$lockToken = "ps1-$PID-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())-$(Get-Random)"
$tokenFile = Join-Path $lock "token"
# PowerShell.Exiting fires on `exit` from this script, which is every path
# below; it does not fire on a hard kill, which is what the age window above
# is for. Mirrors the sh trap on EXIT INT TERM.
$null = Register-EngineEvent PowerShell.Exiting -Action ([scriptblock]::Create(@"
  if ((Get-Content -Raw -ErrorAction SilentlyContinue '$tokenFile') -replace '\s','' -eq '$lockToken') {
    Remove-Item -Recurse -Force '$lock' -ErrorAction SilentlyContinue
  }
"@))
Set-Content -Path $tokenFile -Value $lockToken -Encoding utf8 -ErrorAction SilentlyContinue
# Only the reclaim path can race another reclaimer; the plain-New-Item winner
# cannot be clobbered, since its lock is far too young for anyone to reclaim.
# Do not tax the common path with the settle wait.
if ($reclaimed) {
  Start-Sleep -Seconds 1
  $onDisk = (Get-Content -Raw -ErrorAction SilentlyContinue $tokenFile) -replace '\s', ''
  if ($onDisk -ne $lockToken) { exit 0 }
}

if (-not (Test-Path .crew/verify.json)) {
  # _verify/ is the canonical home; scripts/smoke.sh is honoured as legacy.
  $smoke = @("_verify/smoke.sh", "scripts/smoke.sh") | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($smoke) {
    $bashExe = Resolve-CrewBash
    $out = & $bashExe $smoke 2>&1
    if ($LASTEXITCODE -ne 0) {
      [Console]::Error.WriteLine("Smoke FAILED. Work is not complete.")
      [Console]::Error.WriteLine("bash: $bashExe")
      $out | Select-String -Pattern '^(FAIL|SMOKE:)' | ForEach-Object { [Console]::Error.WriteLine($_) }
      exit 2
    }
  }
  exit 0
}

# -like's * spans '/', so '**/*.tf' demands a literal slash and silently skips
# every root-level file. Test the '**/'-stripped form as well.
function Test-CrewPath([string]$Path, [string]$Pattern) {
  $cands = New-Object System.Collections.Generic.HashSet[string]
  [void]$cands.Add($Pattern)
  if ($Pattern.StartsWith('**/')) { [void]$cands.Add($Pattern.Substring(3)) }
  [void]$cands.Add(($Pattern -replace '/\*\*/', '/'))
  [void]$cands.Add(($Pattern -replace '\*\*', '*'))
  foreach ($c in $cands) { if ($Path -like $c) { return $true } }
  return $false
}

try {
  $vm = Get-Content .crew/verify.json -Raw | ConvertFrom-Json -ErrorAction Stop
} catch {
  [Console]::Error.WriteLine("VERIFY GATE: .crew/verify.json could not be parsed. Verification did NOT run. Work is not complete.")
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 2
}
$cmds = [System.Collections.ArrayList]@()
$unmapped = [System.Collections.ArrayList]@()

foreach ($f in $changed) {
  $hit = $false
  foreach ($r in $vm.rules) {
    foreach ($p in $r.paths) {
      if (Test-CrewPath $f $p) {
        $hit = $true
        foreach ($c in $r.run) { if ($cmds -notcontains $c) { [void]$cmds.Add($c) } }
      }
    }
  }
  if (-not $hit) { [void]$unmapped.Add($f) }
}
foreach ($c in $vm.always) { if ($cmds -notcontains $c) { [void]$cmds.Add($c) } }
if ($cmds.Count -eq 0) { foreach ($c in $vm.default) { [void]$cmds.Add($c) } }

# .crew/verify.json rules are authored as literal "bash <script>" strings
# (see run-all.sh's own rule). Invoke-Expression resolves that leading `bash`
# through the same PATH lookup Resolve-CrewBash exists to route around, so
# every rule command needs the same substitution the legacy-smoke branch
# above gets. Resolve once; every rule in a repo shares one Windows install.
$bashExe = $null

$failed = $false
foreach ($c in $cmds) {
  $run = $c
  # Only resolves a leading literal `bash` token. A rule written as
  # `cd x && bash y.sh` (or any other form where `bash` isn't the first
  # word) skips this substitution entirely and still resolves bash via PATH.
  if ($c -match '^bash(\s|$)') {
    if (-not $bashExe) { $bashExe = Resolve-CrewBash }
    $run = "& '$bashExe'" + $c.Substring(4)
  }
  # A cmdlet leaves $LASTEXITCODE at its previous value, so a stale 0 reads as a
  # pass and a stale nonzero reads as a failure. Reset it, and check $? as well
  # - that is the only signal a failing cmdlet gives.
  $global:LASTEXITCODE = 0
  $out = Invoke-Expression $run 2>&1
  $ok = $?
  if (-not $ok -or $LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("VERIFY FAILED: $c")
    if ($bashExe -and $run -ne $c) { [Console]::Error.WriteLine("bash: $bashExe") }
    $out | Select-Object -Last 25 | ForEach-Object { [Console]::Error.WriteLine($_) }
    $failed = $true
  }
}

if ($unmapped.Count -gt 0 -and $vm.unmapped -eq "fail") {
  [Console]::Error.WriteLine("UNMAPPED CHANGES - .crew/verify.json has no rule for:")
  $unmapped | ForEach-Object { [Console]::Error.WriteLine($_) }
  [Console]::Error.WriteLine("Add a rule (or mark it deliberately unchecked) before reporting this complete.")
  $failed = $true
}

if ($failed) { exit 2 }
exit 0
