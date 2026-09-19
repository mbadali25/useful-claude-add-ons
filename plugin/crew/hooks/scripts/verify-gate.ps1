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
  [switch]$PrintBash,

  # The same probe for the python interpreter the scope report runs on.
  # Resolve-CrewPython has the identical failure modes to Resolve-CrewBash
  # (a profile function shadowing the real thing, a WindowsApps stub), and
  # an unprobeable resolver is one whose regression suite has to run the
  # whole gate to see it.
  [switch]$PrintPython,

  # Runs the WHOLE map with no Stop budget. /crew:verify is the caller that
  # wants it; the Stop hook never passes it. The twin of verify-gate.sh's
  # --all.
  [switch]$All
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

function Resolve-CrewPython {
  # THE SAME GUARD AS Resolve-CrewBash ABOVE, and it is here because this
  # file already contained that guard and the scope report's resolver did
  # not -- one file, two resolvers, one of them hardened.
  #
  # Two live failure modes, both of which `Get-Command python3, python |
  # Select-Object -First 1` walks straight into:
  #
  #   1. A `function python { ... }` in a PowerShell profile is returned
  #      AHEAD of any python.exe and its .Source is empty. hooks.json passes
  #      no -NoProfile, so the profile is loaded and this is a live vector
  #      rather than a theoretical one. The empty .Source then failed the
  #      `if ($scopePy)` test and the gate reported "no python" on a machine
  #      with python installed -- an unknown wearing the label of a check.
  #   2. The Store's python.exe App Execution Alias in WindowsApps is a real
  #      Application with a real .Source, so it resolves and is INVOKED; the
  #      stub opens the Store instead of running the script.
  #
  # Only real executables, never the WindowsApps shim. Unlike the bash
  # resolver there is no System32 shim to exclude -- WSL ships a bash
  # launcher there, nothing ships a python one -- so that filter is
  # deliberately absent rather than forgotten.
  $names = @('python3', 'python')
  foreach ($name in $names) {
    $candidates = Get-Command $name -All -ErrorAction SilentlyContinue
    foreach ($cmd in $candidates) {
      if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
      if ($cmd.Source -match 'WindowsApps') { continue }
      return $cmd.Source
    }
  }
  return ''
}

if ($PrintBash) {
  Write-Output (Resolve-CrewBash)
  exit 0
}

if ($PrintPython) {
  Write-Output (Resolve-CrewPython)
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
# Absolute from here on: the rule loop returns to $root before every rule, and
# a "." that was correct at this line points somewhere else once a rule has cd'd.
$root = (Get-Location).Path

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

# Records the commit this gate has proven clean. Mirrors record_verified in
# verify-gate.sh; called on every exit-0 path and on none that exit nonzero.
function Write-CrewVerified {
  $verified = (git rev-parse HEAD 2>$null)
  if ($verified) {
    if (-not (Test-Path .crew)) { New-Item -ItemType Directory .crew -Force | Out-Null }
    Set-Content -Path .crew/.verify-verified-at -Value $verified.Trim() -Encoding ascii
  }
}

# SCOPE. Mirrors verify-gate.sh exactly; the long rationale lives there. In
# short: diffing the working tree against HEAD made a COMMIT enough to end a
# turn this gate would otherwise have blocked, so the baseline is now the last
# commit the gate actually verified, falling back to the merge-base with the
# default branch, falling back to HEAD. Unknown resolves to checking MORE.
$base = ""
if (Test-Path .crew/.verify-verified-at) {
  $cand = (Get-Content .crew/.verify-verified-at -TotalCount 1 -ErrorAction SilentlyContinue)
  if ($cand) { $cand = $cand.Trim() }
  if ($cand) {
    git cat-file -e "$cand^{commit}" 2>$null
    if ($LASTEXITCODE -eq 0) { $base = $cand }
  }
}
if (-not $base) {
  $def = (git symbolic-ref --short refs/remotes/origin/HEAD 2>$null)
  if ($def) { $def = $def -replace '^origin/', '' } else { $def = "main" }
  $base = (git merge-base HEAD $def 2>$null)
}
if (-not $base) { $base = "HEAD" }

$changed = @()
$changed += (git diff --name-only $base 2>$null)
$changed += (git ls-files --others --exclude-standard 2>$null)
$changed = $changed | Where-Object { $_ -and $_.Trim() } | Sort-Object -Unique
if (-not $changed) { Write-CrewVerified; exit 0 }

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
# Absolute, not relative: the Exiting handler below runs after every rule has
# executed, and a rule is allowed to `cd`. With a relative path the handler
# looked for the token under wherever the last rule left the cwd, found
# nothing, and kept the lock -- so a failing gate was followed by a Stop that
# exited 0 silently for up to $lockTtl seconds (aws-managed-services, 2026-09-13).
#
# BACKING OFF IS NOT PASSING, so every path that exits 0 here has to have seen
# an actual holder, and a failed New-Item is not that evidence on its own -- it
# fails for a lock path that is a FILE, for an unwritable .crew and for a
# read-only tree exactly as it fails for "the directory is already there".
# Mirrors verify-gate.sh, where the same collapse was measured: with `.crew`
# present as a file the gate exited 0 in 0.65s on every turn, for ever, with
# nothing on stderr. Three questions, kept apart, and only the first may back
# off: a lock DIRECTORY is there (a holder plausibly exists); no directory is
# there (nobody to wait for -- run unlocked and say so); a directory whose
# stamp cannot be read (undatable, so a live holder cannot be told from a
# corpse -- run unlocked and say so).
#
# WHAT THIS DOES NOT FIX is the same as over there: a lock directory left by a
# hard-killed holder still backs later gates off for the rest of the age
# window. See verify-gate.sh for the measurement that rules out a pid-based
# narrowing.
$lock = Join-Path (Get-Location).Path ".crew/.verify-gate.lock"
# 700 until crew 0.19.65. Cut in lockstep with verify-gate.sh, and for the
# same reason: the lock now has a heartbeat (Update-CrewLock, called after each
# rule), so its age means "no rule has finished in this long" rather than "this
# is when the run began". The TTL therefore only has to exceed the slowest
# single rule (72s measured here) instead of the slowest whole run (125s).
# Line 216 above already recorded that a killed holder makes this gate exit 0
# silently for up to $lockTtl seconds; 180 bounds that at three minutes, and
# the back-off now says so out loud.
$lockTtl = 180

function Update-CrewLock {
  # Heartbeat. Only the token holder touches it, and a failure is ignored: a
  # lock we cannot refresh is not worth failing a gate over, it just ages.
  param($LockPath, $Token)
  if (-not $Token) { return }
  try {
    if ((Get-Content -Raw -ErrorAction Stop (Join-Path $LockPath 'token')).Trim() -eq $Token) {
      Set-Content -Path (Join-Path $LockPath 'token') -Value $Token -Encoding utf8 -ErrorAction Stop
    }
  } catch { }
}
# --- the unchanged-turn skip ---------------------------------------------
#
# The twin of the block in verify-gate.sh, using the SAME
# verify_fingerprint.py so the two flavours cannot disagree about whether a
# turn changed anything. Stop fires once per TURN; the event is not the gate,
# the state is. See that script's header for what the digest covers and what
# it deliberately does not.
#
# The marker is written ONLY after a clean, complete run (see the bottom of
# this file), so a skip can only mean "this exact tree was fully checked and
# passed". And it SAYS it skipped: 0.19.65 had to fix a silent exit 0 that was
# byte-identical to a pass, and a silent skip would reintroduce exactly that.
# No python means no fingerprint and no skip -- the safe direction.
$fpFile = ".crew/.verify-gate.fingerprint"
$fingerprint = ""
if (-not $All) {
  try {
    $fpPy = Resolve-CrewPython
    $fpScript = Join-Path $PSScriptRoot 'verify_fingerprint.py'
    if ($fpPy -and (Test-Path $fpScript)) {
      $fingerprint = ($changed -join "`n" | & $fpPy $fpScript $PWD.Path) | Out-String
      $fingerprint = $fingerprint.Trim()
      if ($fingerprint -and (Test-Path $fpFile) -and
          ((Get-Content -Raw $fpFile).Trim() -eq $fingerprint)) {
        [Console]::Error.WriteLine("verify-gate: nothing the gate depends on has changed since the last CLEAN run (fingerprint $fingerprint) - checks were SKIPPED, not re-run. Edit a file, or run the gate with -All, to force them.")
        exit 0
      }
    }
  } catch { $fingerprint = "" }
}
$global:LASTEXITCODE = 0

$reclaimed = $false
# Set when the checks run with no lock held. Nothing is cleaned up on that
# path -- no token is written, so the exit handler has nothing to match and
# another process's lock is never removed on a guess.
$unlocked = $false
if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force -ErrorAction SilentlyContinue | Out-Null }
try {
  New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
} catch {
  if (-not (Test-Path $lock -PathType Container)) {
    [Console]::Error.WriteLine("VERIFY GATE: could not create the lock at $lock and nothing is holding it (is .crew a file, read-only, or is the lock path not a directory?). No other gate can be waited for, so the checks are running WITHOUT the lock - at worst they run twice this turn.")
    $unlocked = $true
  } else {
    $holderAt = $null
    # Date by the TOKEN, not the directory -- rewriting a file inside a
    # directory does not move that directory's mtime (measured 2026-09-18),
    # so reading the directory makes the heartbeat a no-op. Same fix as
    # verify-gate.sh's lock_age_source; the pair must agree or one flavour
    # reclaims a lock the other is still holding.
    $ageSrc = Join-Path $lock 'token'
    if (-not (Test-Path $ageSrc)) { $ageSrc = $lock }
    try { $holderAt = (Get-Item $ageSrc -Force -ErrorAction Stop).LastWriteTimeUtc } catch { }
    if ($null -eq $holderAt) {
      [Console]::Error.WriteLine("VERIFY GATE: a lock directory is present at $lock but its age cannot be read, so a live holder cannot be told from one that was killed. The checks are running WITHOUT the lock rather than standing down for a holder that may not exist.")
      $unlocked = $true
    } else {
      $age = ([DateTimeOffset]::UtcNow - [DateTimeOffset]::new($holderAt, [TimeSpan]::Zero)).TotalSeconds
      if ($age -le $lockTtl) {
        # Backing off is not passing. Silent stand-down made the two
        # byte-identical -- see verify-gate.sh for the 2026-09-18 measurement
        # (474ms, rc=0, no output) and line 216 above for the 2026-09-13
        # observation of the same thing in another repo.
        $held = try { (Get-Content -Raw -ErrorAction Stop (Join-Path $lock 'token')).Trim() } catch { 'an unreadable token' }
        [Console]::Error.WriteLine(
          "verify-gate: backed off, lock held by $held ($([int]$age)s old, ttl ${lockTtl}s); NOTHING WAS VERIFIED this turn.")
        exit 0
      }
      Remove-Item -Recurse -Force $lock -ErrorAction SilentlyContinue
      try {
        New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
      } catch { exit 0 }
      $reclaimed = $true
    }
  }
}
if (-not $unlocked) {
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
}

# MOVED HERE from before the lock, in lockstep with verify-gate.sh.
# Before the lock it printed on every Stop including the backing-off
# flavour, so one Stop emitted two scope reports and the lock suite's
# silence assertions went red in BOTH flavours. The .sh moved first and
# this file has to move with it: root CLAUDE.md records a .ps1 drifting
# from its .sh as how crew once shipped a guard that blocked nothing on
# Windows.
# --- scope report: REPORT-ONLY, and it must never touch the exit code ------
# Mirrors verify-gate.sh exactly, and calls the SAME scope_report.py so the
# pair cannot drift. root CLAUDE.md records that a .ps1 drifting from its .sh
# is how crew once shipped a guard that stood down on Windows and blocked
# nothing there. try/catch because this gate can exit 2 and the scope layer
# must not be able to.
try {
  # Same resolver pm-pulse.ps1 uses. verify-gate.ps1 had NO python dependency
  # before this -- it reads verify.json with ConvertFrom-Json -- so the
  # resolver is introduced here rather than assumed. An invented
  # Resolve-CrewPython would have thrown into the catch below and printed
  # "scope not checked" forever, which is precisely the .sh/.ps1 drift root
  # CLAUDE.md records as how crew once blocked nothing on Windows.
  $scopePy = Resolve-CrewPython
  # BOTH preconditions, and they are reported apart. verify-gate.sh tests
  # `-n "$SCOPE_PY"` AND `-f "$SCOPE_DIR/scope_report.py"`; this flavour
  # tested only the interpreter, so a missing scope_report.py reached python
  # and the gate printed a raw "can't open file" traceback line as its scope
  # report. Two different causes with two different fixes must not arrive as
  # one sentence -- and neither may be silent.
  $scopeScript = Join-Path $PSScriptRoot 'scope_report.py'
  if (-not $scopePy) {
    [Console]::Error.WriteLine('outside-scope: (no python; scope not checked)')
  } elseif (-not (Test-Path $scopeScript)) {
    [Console]::Error.WriteLine("outside-scope: (scope_report.py not found at $scopeScript; scope not checked)")
  } else {
    $changed -join "`n" | & $scopePy $scopeScript $PWD.Path
  }
} catch {
  [Console]::Error.WriteLine("outside-scope: (scope not checked: $_)")
}
$global:LASTEXITCODE = 0

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

# A command is ONE LINE, and a command that is not is REJECTED. The matched
# twin of the rejection in verify-gate.sh, and the reason it is here as well
# is that WITHOUT it the pair disagrees: over there a multi-line entry moved
# the record boundary and the rest of the rule silently never ran, while here
# `bash -c` would happily run both halves. A map that blocks the turn on one
# flavour and passes it on the other is worse than either answer, so both
# refuse it and both name the entry. This script never serialises the two
# lists through a text channel, so the separator half of that fix has no twin
# here - only the rejection does.
function Get-CrewUnrepresentable($Entries, [string]$Where) {
  if ($null -eq $Entries) { return $null }
  $framing = [ordered]@{
    "`n" = "a newline"; "`r" = "a carriage return"
    [string][char]0x1d = "an ASCII group separator (0x1d)"
    [string][char]0x1e = "an ASCII record separator (0x1e)"
  }
  $i = 0
  foreach ($c in @($Entries)) {
    if ($c -is [string]) {
      foreach ($ch in $framing.Keys) {
        if ($c.Contains([string]$ch)) {
          $head = $c.Split([string]$ch)[0].Trim()
          if ($head.Length -gt 60) { $head = $head.Substring(0, 60) }
          return ("PARSE_ERROR: .crew/verify.json $Where[$i] contains " +
                  "$($framing[$ch]), so crew cannot represent it as one " +
                  "command. The entry begins: '$head'. Split it into separate " +
                  "entries, or move it into a script and call that.")
        }
      }
    }
    $i++
  }
  return $null
}

$bad = $null
$ri = 0
foreach ($r in @($vm.rules)) {
  if ($null -eq $bad -and $null -ne $r) { $bad = Get-CrewUnrepresentable $r.run "rules[$ri].run" }
  $ri++
}
if ($null -eq $bad) { $bad = Get-CrewUnrepresentable $vm.always "always" }
if ($null -eq $bad) { $bad = Get-CrewUnrepresentable $vm.default "default" }
if ($null -ne $bad) {
  [Console]::Error.WriteLine($bad)
  [Console]::Error.WriteLine("VERIFY GATE: .crew/verify.json names a command crew cannot represent (see the PARSE_ERROR above for which one and why). Verification did NOT run. Work is not complete.")
  exit 2
}

$cmds = [System.Collections.ArrayList]@()
$unmapped = [System.Collections.ArrayList]@()
# Cost per COMMAND, not per rule, and the MAX where several rules contribute
# the same command. Matches verify-gate.sh's note_cost exactly: under-running
# the budget costs a deferral, over-running it costs the thing the budget
# exists to bound. A bool is NOT a number here -- PowerShell will happily
# compare $true with -ge, which is how a `"seconds": true` typo would become
# a cost of 1.
$cost = @{}
function Test-CrewSeconds($Value) {
  if ($null -eq $Value) { return $false }
  if ($Value -is [bool]) { return $false }
  if (-not ($Value -is [int] -or $Value -is [long] -or $Value -is [double] -or $Value -is [decimal])) { return $false }
  return ($Value -ge 0)
}

foreach ($f in $changed) {
  $hit = $false
  foreach ($r in $vm.rules) {
    foreach ($p in $r.paths) {
      if (Test-CrewPath $f $p) {
        $hit = $true
        foreach ($c in $r.run) {
          if ($cmds -notcontains $c) { [void]$cmds.Add($c) }
          if (Test-CrewSeconds $r.seconds) {
            if (-not $cost.ContainsKey($c) -or $cost[$c] -lt [double]$r.seconds) {
              $cost[$c] = [double]$r.seconds
            }
          }
        }
      }
    }
  }
  if (-not $hit) { [void]$unmapped.Add($f) }
}
foreach ($c in $vm.always) { if ($cmds -notcontains $c) { [void]$cmds.Add($c) } }
if ($cmds.Count -eq 0) { foreach ($c in $vm.default) { [void]$cmds.Add($c) } }

# --- the Stop budget ------------------------------------------------------
#
# The twin of the block in verify-gate.sh, and the two are asserted to select
# the same commands over the same map by the parity case in the suite. See
# that file for why the field exists at all; the rule here is the same one:
# UNKNOWN COST IS NOT FREE. A rule with no `seconds` RUNS, is never deferred
# on the strength of a number nobody wrote down, is left OUT of the budget
# arithmetic rather than given a guessed value, and is named in the output.
$budget = 60.0
if ($All) {
  $budget = $null
} else {
  # A config that cannot be read falls back to the DEFAULT, never to "no
  # limit": "could not read the config" must not quietly become unbounded.
  try {
    if (Test-Path .crew/config.json) {
      $cc = Get-Content .crew/config.json -Raw | ConvertFrom-Json -ErrorAction Stop
      $v = $cc.verify.stopBudgetSeconds
      if (Test-CrewSeconds $v) { $budget = [double]$v }
    }
  } catch { }
}

$notices = [System.Collections.ArrayList]@()
if ($null -ne $budget) {
  $order = @{}
  for ($i = 0; $i -lt $cmds.Count; $i++) { $order[$cmds[$i]] = $i }
  $known   = @($cmds | Where-Object { $cost.ContainsKey($_) })
  $unknown = @($cmds | Where-Object { -not $cost.ContainsKey($_) })
  # Ascending cost, original order breaking ties -- same ordering as the .sh.
  $known = @($known | Sort-Object @{Expression = { $cost[$_] }}, @{Expression = { $order[$_] }})

  $spent = 0.0
  $keep = [System.Collections.ArrayList]@()
  $deferred = [System.Collections.ArrayList]@()
  foreach ($c in $known) {
    if (($spent + $cost[$c]) -le $budget) { [void]$keep.Add($c); $spent += $cost[$c] }
    else { [void]$deferred.Add($c) }
  }

  # Unknown-cost commands run FIRST, so a map with no `seconds` anywhere
  # behaves exactly as it did before this feature existed.
  $ordered = [System.Collections.ArrayList]@()
  foreach ($c in $unknown) { [void]$ordered.Add($c) }
  foreach ($c in $keep)    { [void]$ordered.Add($c) }
  $cmds = $ordered

  foreach ($c in $unknown) {
    [void]$notices.Add('verify-gate: ' + $c + ' has no `seconds` in verify.json - cost UNSTATED, ran anyway')
  }
  foreach ($c in $deferred) {
    [void]$notices.Add('deferred to /crew:verify: ' + $c + ' (' + [string][int]$cost[$c] + 's)')
  }
  if ($deferred.Count -gt 0) {
    $extra = ''
    if ($unknown.Count -gt 0) { $extra = ' plus ' + [string]$unknown.Count + ' of unstated cost' }
    [void]$notices.Add('verify-gate: stop budget ' + [string][int]$budget + 's; ran ' +
      [string][int]$spent + 's of stated cost' + $extra + ', deferred ' +
      [string]$deferred.Count + '. The deferred ones were NOT checked - run /crew:verify.')
  }
}
# Printed BEFORE the run, so a turn killed part-way still says what it was
# never going to check.
foreach ($n in $notices) { [Console]::Error.WriteLine($n) }

# .crew/verify.json rules are bash-flavoured strings - `bash _verify/smoke.sh`,
# `FDM_MODULE=x bash case.sh`, `cd e2e && npx playwright test --grep @flow`. So
# RUN them with bash rather than evaluating them as PowerShell. Resolve once;
# every rule in a repo shares one Windows install, and Resolve-CrewBash already
# routes around WSL's bash.exe.
$bashExe = $null

# verify-gate.sh evals each rule inside `$(...)`, a subshell. This is the
# matched twin of that contract, and the only way to honour it is to hand the
# rule to the same interpreter the sh side uses. Invoke-Expression could not:
# it made the gate reimplement bash in PowerShell, and every hand-rolled piece
# was its own way to be wrong. Measured on two repos on 2026-09-13:
#
#   1. `cd <module> && npm test` moved THIS process's cwd, so every later rule
#      - `bash -n scripts/x.sh`, pytest, ruff - ran from the wrong directory
#      and reported files missing that exist (aws-managed-services T-0019; and
#      on TheSelectSource the next rule died on every Stop).
#   2. `$?` after Invoke-Expression is Invoke-Expression's OWN status, so a
#      failed `cd` and a nonexistent command both read as a pass. Six rules of
#      one run silently passed.
#   3. `FDM_MODULE=x bash case.sh` is bash syntax; to PowerShell it is a
#      command named `FDM_MODULE=x`.
#   4. `--grep @flow` parsed as a splat of an unset `$flow` ("The variable
#      '$flow' cannot be retrieved") - a rule failing on PowerShell's own
#      parse, before it was ever a command.
#
# A bash child gets the rule's own semantics, so 1, 3 and 4 stop existing
# rather than being worked around, and $LASTEXITCODE is the rule's real status.
# Push-Location/Pop-Location keeps the gate's own cwd correct for the marker
# and the unmapped report whatever the rule does to its own.
#
# The `bash -c` shape is from PR #151 (another session, measured on
# TheSelectSource); Resolve-CrewBash and findings 1-3 are from #153. Folded
# here so this function has one lineage rather than two.
$failed = $false
$totalElapsed = 0
foreach ($c in $cmds) {
  $ruleStart = Get-Date
  if (-not $bashExe) { $bashExe = Resolve-CrewBash }
  # A native command leaves $LASTEXITCODE at its previous value when it fails
  # to start, so a stale 0 would read as a pass. Reset it first.
  $global:LASTEXITCODE = 0
  Push-Location $root
  try {
    $out = & $bashExe -c $c 2>&1
    $ok = ($LASTEXITCODE -eq 0)
  } finally {
    Pop-Location
  }
  if (-not $ok) {
    [Console]::Error.WriteLine("VERIFY FAILED: $c")
    [Console]::Error.WriteLine("bash: $bashExe")
    $out | Select-Object -Last 25 | ForEach-Object { [Console]::Error.WriteLine($_) }
    $failed = $true
  }
  $ruleElapsed = [int]((Get-Date) - $ruleStart).TotalSeconds
  $totalElapsed += $ruleElapsed
  [Console]::Error.WriteLine("verify-gate: ${ruleElapsed}s  $c")
  # Heartbeat AFTER the rule, matching verify-gate.sh exactly.
  Update-CrewLock -LockPath $lock -Token $lockToken
}
[Console]::Error.WriteLine("verify-gate: ${totalElapsed}s total across $($cmds.Count) rule command(s)")
Set-Location $root

if ($unmapped.Count -gt 0 -and $vm.unmapped -eq "fail") {
  [Console]::Error.WriteLine("UNMAPPED CHANGES - .crew/verify.json has no rule for:")
  $unmapped | ForEach-Object { [Console]::Error.WriteLine($_) }
  [Console]::Error.WriteLine("Add a rule (or mark it deliberately unchecked) before reporting this complete.")
  $failed = $true
}

if ($failed) { exit 2 }

# The fingerprint, written ONLY where everything ran and everything passed.
# Deliberately NOT written when the Stop budget deferred a rule: a deferred
# rule was never checked, so recording it would turn "we ran out of budget"
# into "this tree is verified" and the deferred checks would never run again
# on an unchanged tree. $notices is non-empty exactly when the budget had
# something to say, which is the signal being tested. Matches verify-gate.sh.
if ($fingerprint -and $notices.Count -eq 0) {
  try {
    if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force -ErrorAction SilentlyContinue | Out-Null }
    Set-Content -Path $fpFile -Value $fingerprint -Encoding utf8 -ErrorAction Stop
  } catch { }
}

# Record what was just proven clean. Written ONLY on the pass path, so the
# marker can never claim more than was actually checked. See verify-gate.sh.
Write-CrewVerified
exit 0
