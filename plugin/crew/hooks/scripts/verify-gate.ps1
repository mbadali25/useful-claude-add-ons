# PowerShell end-of-turn gate for native Windows. Mirrors verify-gate.sh.
# Runs the checks the CHANGED FILES require, from .crew/verify.json. Exit 2 = not done.
#
# No hook_once claim here on purpose: Stop fires once per TURN against a
# stable session id, so a session-scoped claim taken on turn 1 would suppress
# every later turn's gate -- a 600-second gate that silently never runs again
# reads as "the work passed", which is worse than the double-run a claim
# would prevent. Both flavours are registered for every Stop; which one runs
# is decided by the flavour guard below, on the OS, so a Windows box with Git
# Bash installed - nearly all of them - still reaches THIS file and its
# incident/config lane stays testable.
#
# The short-lived per-turn lock right before the expensive part below STAYS.
# The cross-flavour race it was written for cannot happen any more, but the
# same-flavour one can: a hand-run `pwsh verify-gate.ps1 -All` against a repo
# whose Stop hook is already running the map, or a settings file that
# registers this hook twice, both put two pwsh processes on one turn. Neither
# is addressed by the flavour guard. (`/crew:verify --all` runs the BASH
# flavour - commands/verify.md:72 - so it is not one of these cases; only
# -Price names the .ps1, at commands/verify.md:114.)
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
  [switch]$All,

  # Operator-only. Times every rule with no budget and writes `seconds` for
  # the ones that have none. The twin of verify-gate.sh's --price, and NEVER
  # reachable from the Stop hook: hooks.json invokes this script with no
  # switch or with -All, never -Price. .crew/verify.json is TRACKED in this
  # repo, so an unattended --price would dirty a committed file on every
  # Stop - this switch existing at all, gated the same way -All is, is what
  # keeps that impossible by construction rather than by convention.
  [switch]$Price,
  [string]$PriceTarget = ".crew/verify.json",
  [switch]$PriceForce
)

# Flavour guard. Both flavours are registered for every event, so on a host
# that has BOTH interpreters both would otherwise run. Stand down only when
# we can positively prove this is not Windows.
#
# $env:OS is 'Windows_NT' on BOTH Windows PowerShell 5.1 and PowerShell 7,
# and unset on Linux/macOS. A bare `if (-not $IsWindows)` is WRONG: $IsWindows
# does not exist in 5.1, so it is $null there, `-not $null` is $true, and the
# hook stands down on the one platform it exists for. crew has already shipped
# that bug once - the guard stood down on Windows and blocked nothing there.
if ($env:OS -ne 'Windows_NT') { exit 0 }

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
  # Every python3/python/py candidate found anywhere on PATH is executed
  # once against one fixed -c probe below; cwd is never searched unless it
  # is itself on PATH. No behaviour change from this comment.
  # Memoized within this process: verify-gate.ps1 alone calls this up to
  # seven times in one run, and each call would otherwise re-walk and
  # re-probe PATH from scratch. Cached only for the life of THIS process --
  # a fresh hook invocation gets a fresh probe.
  if ($script:CrewPythonMemoDone) {
    return $script:CrewPythonMemoResult
  }
  # ONE probe, byte for byte in every crew .ps1 that runs python, asserted by
  # tests/test_ps1_python_probe.py. Inline rather than dot-sourced for the
  # reason verify-gate.ps1's emergency-lane note gives: a dot-sourced
  # function is invisible to scripts/check-powershell.ps1's static check.
  #
  # EVERY PATH match of every name is a candidate, and each is EXECUTED
  # before it is believed; where it lives never decides. A WindowsApps App
  # Execution Alias is tried like anything else: it forwards to a working
  # interpreter when Python is installed and fails the probe when it is not.
  # Windows burn-in 2026-09-23 (docs/review/06-windows-burn-in.md, 2c): the
  # previous copy skipped WindowsApps by path and took only the first match
  # per name, so on a host whose python, python3 and py were all working
  # WindowsApps aliases it discarded all three untested, never reached the
  # real python.exe further down PATH, and completion-audit.ps1 blocked
  # every Stop while its bash twin proceeded.
  #
  # PROOF, not a printed line. The candidate must answer one JSON object
  # only a Python can build: {"v": [major, minor], "exe": sys.executable,
  # "impl": sys.implementation.name}. Accepted only when it exits 0, the
  # JSON parses, impl is cpython or pypy (the two implementations the hooks
  # are run under; anything else is rejected rather than guessed at), v is
  # at least [3, 8] (the floor crew's python targets), and exe exists as a
  # file. A program that ignores -c and prints some existing path -- which
  # the previous "print(sys.executable)" probe accepted -- fails the parse.
  #
  # The probe is bounded: it runs to completion or its WHOLE PROCESS TREE is
  # killed at 3s, with stdout and stderr read asynchronously so a chatty
  # candidate cannot fill a pipe and hang. The tree, not the candidate: a
  # py.exe-style launcher starts a child interpreter that inherits the
  # redirected handles, and killing only the launcher leaves that child
  # running. Kill($true) is the tree kill on PowerShell 7 (.NET Core 3+);
  # Windows PowerShell 5.1 has no such overload, so it falls back to
  # taskkill /T /F. No `continue` inside try/catch: loop control across that
  # boundary differs between PowerShell versions, so the verdict is carried
  # out in $real and acted on after it.
  # An OVERALL deadline on top of each candidate's own 3s probe bound: a
  # PATH with several hung candidates would otherwise cost 3s EACH, adding
  # up past the shortest hook timeout that calls this (bridge-status.ps1's
  # twin, 10s) even though every individual probe is bounded. Kept well
  # inside that.
  #
  # REAL Windows only, never the flavour-guard seam: $env:OS -eq 'Windows_NT'
  # is also true in this suite's own fixtures, which run REAL pwsh on Linux
  # with that variable set to get past the guard at the top of this file --
  # their candidates are ordinary extensionless Linux shim scripts, valid
  # executables here, and gating on the seam would reject every one of them
  # and break the fixtures that exist to prove this resolver works. $IsWindows
  # (PowerShell 6+) reports the actual OS regardless of $env:OS; it does not
  # exist in Windows PowerShell 5.1, which never runs anywhere but Windows, so
  # its absence is itself a true answer.
  $crewPythonRealWindows = if (Test-Path variable:IsWindows) { $IsWindows } else { $true }
  # Only .exe/.com/.cmd/.bat (PATHEXT's launchable core) can be started
  # without going through shell association. An extensionless file --
  # anything else, including no extension at all -- CreateProcess cannot
  # launch directly, and reaching it here is the same failure mode this
  # probe's own bounded wait/kill exists to survive from a HUNG candidate,
  # not from one Windows cannot start in the first place. Skipped before
  # Process.Start is ever called, not caught after: a WindowsApps alias
  # already carries `.exe`, so it is untouched by this and still tried like
  # any other candidate, per the comment above.
  $crewPythonNativeExts = @('.exe', '.com', '.cmd', '.bat')
  $crewPythonDeadline = [System.Diagnostics.Stopwatch]::StartNew()
  foreach ($name in @('python3', 'python', 'py')) {
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
      if ($crewPythonRealWindows) {
        $crewPythonExt = [System.IO.Path]::GetExtension($cmd.Source)
        if ($crewPythonNativeExts -notcontains $crewPythonExt) {
          Write-Verbose "Resolve-CrewPython: skipping '$($cmd.Source)' - not natively launchable on Windows (extension '$crewPythonExt' outside .exe/.com/.cmd/.bat)"
          continue
        }
      }
      # The remaining budget, not a flat 3000ms, bounds THIS candidate's
      # wait: checking the deadline only before launch and then waiting the
      # full 3s regardless can still overrun the deadline by up to 3s once
      # a candidate is entered, which on a run of several near-8s-but-under
      # candidates followed by one hung one can overrun both this deadline
      # and the 10s hook timeout it exists to stay inside.
      $crewPythonRemainingMs = 8000 - [int]$crewPythonDeadline.Elapsed.TotalMilliseconds
      if ($crewPythonRemainingMs -le 0) {
        $script:CrewPythonMemoDone = $true
        $script:CrewPythonMemoResult = ''
        return ''
      }
      $crewPythonWaitMs = [Math]::Min(3000, $crewPythonRemainingMs)
      $real = $null
      try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $probeArgs = '-c "import sys,json;print(json.dumps({''v'':list(sys.version_info[:2]),''exe'':sys.executable,''impl'':sys.implementation.name}))"'
        if ($cmd.Source -match '\.(cmd|bat)$') {
          # UseShellExecute=false hands FileName straight to CreateProcess,
          # which can only launch a real PE executable -- not a .cmd/.bat
          # shim (a pyenv-win install is exactly this shape). Route it
          # through cmd.exe /d /c instead of flipping UseShellExecute to
          # $true, which would resolve by shell file association rather
          # than run it as a command. Wrapping the whole command line in
          # one more pair of quotes defeats cmd's "exactly two quotes"
          # special case, so both the quoted shim path and the quoted -c
          # argument survive intact.
          $psi.FileName = Join-Path $env:SystemRoot 'System32\cmd.exe'
          $psi.Arguments = '/d /c "' + '"' + $cmd.Source + '" ' + $probeArgs + '"'
        } else {
          $psi.FileName = $cmd.Source
          $psi.Arguments = $probeArgs
        }
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $null = $proc.StandardError.ReadToEndAsync()
        if (-not $proc.WaitForExit($crewPythonWaitMs)) {
          try {
            $proc.Kill($true)
          } catch {
            try { & taskkill.exe /T /F /PID $proc.Id 2>&1 | Out-Null } catch { }
            try { $proc.Kill() } catch { }
          }
          # Reap the killed tree with its own bound, rather than leaving it
          # torn down but never waited on for however long that takes.
          try { $null = $proc.WaitForExit(2000) } catch { }
        } elseif ($proc.ExitCode -eq 0 -and $outTask.Wait(1000)) {
          $line = @(($outTask.Result -split "`r?`n") | Where-Object { $_.Trim() })[-1]
          $probe = $line | ConvertFrom-Json
          $v = @($probe.v)
          if ($probe.impl -in @('cpython', 'pypy') -and $v.Count -ge 2 -and
              ($v[0] -is [long] -or $v[0] -is [int]) -and ($v[1] -is [long] -or $v[1] -is [int]) -and
              ([int]$v[0] -gt 3 -or ([int]$v[0] -eq 3 -and [int]$v[1] -ge 8)) -and
              $probe.exe -is [string]) {
            $real = $probe.exe
          }
        }
        try { $proc.Dispose() } catch { }
      } catch {
        $real = $null
      }
      if ($real) { $real = $real.ToString().Trim() }
      if (-not $real) { continue }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
      $script:CrewPythonMemoDone = $true
      $script:CrewPythonMemoResult = $real
      return $real
    }
  }
  $script:CrewPythonMemoDone = $true
  $script:CrewPythonMemoResult = ''
  return ''
}

# -Price resolves python with the same probe as everything else here, so it
# sits below Resolve-CrewPython rather than above it with a copy of its own.
if ($Price) {
  $root0 = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
  Set-Location $root0
  $py0 = Resolve-CrewPython
  if (-not $py0) {
    [Console]::Error.WriteLine("verify-gate -Price: no python available")
    exit 1
  }
  $script0 = Join-Path $PSScriptRoot 'verify_price.py'
  $priceArgs = @($script0, $PriceTarget)
  if ($PriceForce) { $priceArgs += '--force' }
  & $py0 @priceArgs
  exit $LASTEXITCODE
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

# Bounded, and the twin of verify-gate.sh's read above. A Stop hook always
# pipes JSON here, but nothing enforces that the pipe is ever actually
# closed, and an unconditional read blocks the WHOLE script on it -- the
# same parked-process shape a hung interpreter probe produces, for a
# different cause. IsInputRedirected is false for an interactive terminal
# (nothing was ever going to arrive), so nothing is read at all in that
# case.
#
# NOT [Console]::In (a TextReader): measured directly, `[Console]::In`'s
# lazy first access probes the stream synchronously (encoding/BOM
# detection) before `ReadToEndAsync()` returns a Task at all, so on a pipe
# with no data yet queued that probe itself blocks -- the bound below never
# gets a Task to wait on, and the process hangs exactly as before. Reading
# the RAW stream from `OpenStandardInput()` has no such lazy probe: opening
# it is synchronous and instant regardless of what has arrived, and only
# the actual byte copy is asynchronous, so the bound covers the one thing
# that can be slow. Confirmed both ways against a pipe that never sends
# anything: `[Console]::In.ReadToEndAsync()` itself never returns,
# `OpenStandardInput()` returns immediately every time.
#
# THE BOUND IS TOTAL, NOT "did it reach EOF". A complete
# `{"stop_hook_active":true}` payload sitting in the buffer, with the pipe
# held open past the 5s bound, used to be discarded outright -- the retry
# hook then ran the gate again and blocked again on a failing check it had
# already reported this turn. `CopyToAsync` still only completes at EOF, so
# `Wait(5000)` still times out on a held-open pipe; what changed is that the
# buffer is read regardless of whether the Task finished. Whatever arrived
# within the bound is what gets parsed -- a complete JSON object is enough,
# EOF is not required. Garbage or a half-written object still fails
# `ConvertFrom-Json` below and is caught exactly as an empty `$raw` always
# was, so a producer that never sends anything parseable keeps today's
# behaviour.
$raw = ""
if ([Console]::IsInputRedirected) {
  $crewStdinStream = [Console]::OpenStandardInput()
  $crewStdinBuffer = New-Object System.IO.MemoryStream
  $crewStdinTask = $crewStdinStream.CopyToAsync($crewStdinBuffer)
  $crewStdinTask.Wait(5000) | Out-Null
  $raw = [System.Text.Encoding]::UTF8.GetString($crewStdinBuffer.ToArray())
}

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
    (git -c core.quotePath=false diff --name-only HEAD 2>$null)
    (git -c core.quotePath=false ls-files --others --exclude-standard 2>$null)
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
# See verify-gate.sh for why core.quotePath is forced off here.
if ($All) {
  # -All does not diff against ANY commit - the twin of the same change in
  # verify-gate.sh. A commit-range diff, however wide, is still bounded by
  # SOME ancestor, and on a single-branch repo (or one sitting ON its own
  # default branch) merge-base(HEAD, main) IS HEAD - an empty diff. The sha
  # marker can now advance past a commit that added a CHRONIC/reach-
  # excluded/skipped rule's own files, so a commit-range fallback would
  # silently narrow -All's scope to match Stop's. -All instead sees every
  # tracked file plus every untracked one.
  #
  # `git ls-files` alone MISSES a path staged for deletion - the twin of
  # the same fix in verify-gate.sh, where the long rationale lives. Two
  # more sources close it: `--diff-filter=D` against the index for a
  # STAGED deletion, plain `diff --name-only HEAD` for an UNSTAGED one.
  #
  # A STAGED RENAME is separate again: default rename detection pairs
  # `old` into an R status, so --diff-filter=D never reports it either -
  # the twin of the same fix in verify-gate.sh. `--name-status -M
  # --diff-filter=R` names both columns per rename (status, old, new);
  # split each line on tab and take columns 1 and 2.
  $changed += (git -c core.quotePath=false ls-files 2>$null)
  $changed += (git -c core.quotePath=false diff --name-only --cached --diff-filter=D 2>$null)
  $changed += (git -c core.quotePath=false diff --name-only HEAD 2>$null)
  $renameLines = (git -c core.quotePath=false diff --name-status --cached -M --diff-filter=R 2>$null)
  foreach ($line in @($renameLines)) {
    $cols = $line -split "`t"
    if ($cols.Count -ge 3) { $changed += $cols[1]; $changed += $cols[2] }
  }
  $changed += (git -c core.quotePath=false ls-files --others --exclude-standard 2>$null)
} else {
  $changed += (git -c core.quotePath=false diff --name-only $base 2>$null)
  $changed += (git -c core.quotePath=false ls-files --others --exclude-standard 2>$null)
}
$changed = $changed | Where-Object { $_ -and $_.Trim() } | Sort-Object -Unique
if (-not $changed) {
  # A turn that changed nothing still owes a reminder for any rule this
  # tree has never actually been checked against - the twin of the same
  # block in verify-gate.sh. Best-effort and read-only.
  try {
    $reportPy = Resolve-CrewPython
    $reportScript = Join-Path $PSScriptRoot 'verify_record.py'
    if ($reportPy -and (Test-Path $reportScript)) {
      & $reportPy $reportScript report 2>$null | ForEach-Object { [Console]::Error.WriteLine($_) }
    }
  } catch { }
  Write-CrewVerified
  exit 0
}

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
# Overridable so the suite can exercise the boundary without burning the real
# window in wall-clock time. Environment, not config, and matching
# CREW_VERIFY_LOCK_TTL in verify-gate.sh: this is a TEST SEAM, and a repo
# setting it in .crew/config would quietly change how long one flavour waits
# for the other.
#
# NARROWS ONLY, matching verify-gate.sh: a value greater than the compiled
# default (or 0, or anything that fails to parse as a positive integer) is
# ignored and the default stands. Unparseable falls back to the compiled
# default, not to zero, which would make every lock look expired.
if ($env:CREW_VERIFY_LOCK_TTL -match '^[0-9]+$') {
  $envTtl = [int]$env:CREW_VERIFY_LOCK_TTL
  if ($envTtl -gt 0 -and $envTtl -le $lockTtl) { $lockTtl = $envTtl }
}

# HOW LONG THIS RUN MAY LEGITIMATELY GO QUIET. The twin of lock_window /
# lock_extend in verify-gate.sh, where the full reasoning lives: the heartbeat
# fires BETWEEN rules, so one rule longer than $lockTtl lets the other flavour
# reclaim a live lock and run concurrently. This repo's own map declares a
# 185s rule against a 180s TTL, so it is not hypothetical.
#
# max($lockTtl, 2 x the largest stated cost among the selected rules). A
# background heartbeat during the rule was the reviewer's stated preference
# and was NOT taken: an orphaned toucher outliving a SIGKILLed holder would
# refresh the lock forever and disable verification permanently, and bounding
# that needs machinery that differs between the two shells.
function Get-CrewLockWindow {
  param($Ttl, $MaxCost)
  $w = [int]$Ttl
  if ($MaxCost -and [int]$MaxCost -gt 0 -and (2 * [int]$MaxCost) -gt $w) { $w = 2 * [int]$MaxCost }
  return $w
}

# Publishes the deadline. Only the token holder writes it, as with the token.
function Write-CrewLockDeadline {
  param($LockPath, $Token, $Ttl, $MaxCost)
  if (-not $Token) { return }
  try {
    if ((Get-Content -Raw -ErrorAction Stop (Join-Path $LockPath 'token')).Trim() -eq $Token) {
      $epoch = [int][double]::Parse((Get-Date -UFormat %s))
      $deadline = $epoch + (Get-CrewLockWindow -Ttl $Ttl -MaxCost $MaxCost)
      Set-Content -Path (Join-Path $LockPath 'deadline') -Value $deadline -Encoding ascii -ErrorAction Stop
    }
  } catch { }
}

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
        # The fingerprint only proves nothing changed; it says nothing about
        # a rule that was chronic/skipped/reach-excluded on a PRIOR run and
        # has not been touched since. Read-only reminder.
        try {
          $reportScript2 = Join-Path $PSScriptRoot 'verify_record.py'
          if (Test-Path $reportScript2) {
            & $fpPy $reportScript2 report 2>$null | ForEach-Object { [Console]::Error.WriteLine($_) }
          }
        } catch { }
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
      # A published deadline wins over the age window: it is the holder
      # saying how long THIS run may take, from the map's own numbers. Absent
      # or unreadable falls back to the age window, so a lock written by a
      # version that never published one ages exactly as it used to.
      # Matched to verify-gate.sh: an unparseable deadline means NOT HELD, and
      # the value is REJECTED rather than repaired. The regex is the whole
      # guard -- a cast alone is not, and the two flavours disagreed because
      # of it. Measured on an aged token with a deadline of 9999999999: bash
      # backed off and PowerShell ran, because [int] overflows Int32 and the
      # catch silently produced 0. That is a real date, not a fabricated one:
      # every legitimate deadline crosses Int32 max on 2038-01-19, after which
      # this pair would have disagreed about every live lock. [long] removes
      # the cliff; the regex removes the coercion.
      $holdDeadline = 0
      try {
        $raw = (Get-Content -Raw -ErrorAction Stop (Join-Path $lock 'deadline')).Trim()
        if ($raw -match '^[0-9]+$') { $holdDeadline = [long]$raw }
      } catch { $holdDeadline = 0 }
      $nowEpoch = [int][double]::Parse((Get-Date -UFormat %s))
      if ($holdDeadline -gt 0 -and $nowEpoch -lt $holdDeadline) {
        $held = try { (Get-Content -Raw -ErrorAction Stop (Join-Path $lock 'token')).Trim() } catch { 'an unreadable token' }
        [Console]::Error.WriteLine(
          "verify-gate: backed off, lock held by $held (holder declared it may run for another $($holdDeadline - $nowEpoch)s); NOTHING WAS VERIFIED this turn.")
        exit 0
      }
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
  # Same resolver the other thin .ps1 wrappers use. verify-gate.ps1 had NO python dependency
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
    [string][char]0x1c = "an ASCII file separator (0x1c)"
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
# THE UNIT OF THE BUDGET IS THE RULE, AND `seconds` IS CHARGED ONCE. The twin
# of verify-gate.sh's note; that file carries the long form of why, including
# the two-command 40s rule that used to split under a 60s budget.
#
# $cost stays per COMMAND, and the MAX where several rules contribute the same
# command: it prices the deferral notices and sizes the lock window, both of
# which ask about a command rather than a rule. $ruleCmds / $ruleSecs are what
# the budget spends against. A bool is NOT a number here -- PowerShell will
# happily compare $true with -ge, which is how a `"seconds": true` typo would
# become a cost of 1.
#
# $mandatory is the OBLIGATION, which deduplication must not weaken -- see
# verify-gate.sh for the three levels and for the measured case where
# `"always": ["x"]` beside a 90s rule naming `x` deferred the mandatory check
# and this flavour exited 0 without running it, exactly as bash did.
#
# ORDINAL, not the PowerShell @{} default. `@{}` and `-contains` both compare
# strings CASE-INSENSITIVELY - Codex round 3 BLOCK: two rules running
# `test "$ENV" = dev` with env ENV=dev and ENV=DEV are two DIFFERENT
# commands (different env, different identity text), but `@{}`/`-contains`
# read their identities as the SAME key, so only the first was ever kept -
# the second silently vanished from $cmds and never ran, and this flavour
# exited 0 on a check bash correctly ran twice and failed. Every identity
# lookup below therefore uses an Ordinal-comparer Dictionary ($cost,
# $mandatory) or the case-sensitive `-ccontains`/`-cnotcontains` operators
# ($cmds, $keep, $deferred), never the PowerShell defaults.
$cost = [System.Collections.Generic.Dictionary[string,object]]::new([System.StringComparer]::Ordinal)
$mandatory = [System.Collections.Generic.Dictionary[string,object]]::new([System.StringComparer]::Ordinal)  # command -> $true, a set
$ruleCmds = @{}                                  # rule index -> its commands
$ruleSecs = @{}                                  # rule index -> stated cost
$ruleOrder = [System.Collections.ArrayList]@()   # first-match order
function Test-CrewSeconds($Value) {
  if ($null -eq $Value) { return $false }
  if ($Value -is [bool]) { return $false }
  if (-not ($Value -is [int] -or $Value -is [long] -or $Value -is [double] -or $Value -is [decimal])) { return $false }
  return ($Value -ge 0)
}

# --- reach --------------------------------------------------------------
# The twin of the same block in verify-gate.sh; the long rationale lives
# there. `local` (default when it matches no reach verb) | `network` |
# `host`. Stop runs ONLY local; -All runs everything regardless of reach.
# An UNDECLARED rule whose command matches a reach verb is treated the same
# as a declared non-local one at Stop time - an unknown must not collapse
# into "local", which is the safe-looking value TheSelectSource's SSM-over-
# an-inherited-ENV case proved is not actually safe.
$stopMode = -not $All
# Reach scanning is verify_record.scan_reach - ONE function, shared with
# verify-gate.sh (which imports it in-process) and verify_price.py. Round 2
# deleted the independent native-PowerShell copy that used to live here:
# it scanned only ONE LEVEL into a wrapper script and, on ANY read failure
# (`catch { $text = "" }`), silently treated the wrapper as clean - the
# powershell-security-hardening review named that exact line.
#
# REJECT-ONLY as of round 4 - see scan_reach's own module docstring in
# verify_record.py for the full rationale. Status is now "verb" | "wrapper"
# | "local"; there is no more "uninspected" middle ground, and a wrapper
# this scan cannot read is classified "wrapper" the same as one it reads
# and finds nothing in - it is never a softer, safer category.
function Get-CrewScanReach($Run, $Py, $Script, $Root) {
  if (-not $Py -or -not (Test-Path $Script)) {
    return @{ status = "wrapper"; detail = "the shared scanner (verify_record.py) is not reachable" }
  }
  $payload = ConvertTo-Json -Compress -InputObject ([ordered]@{ run = @($Run); root = $Root })
  $out = ($payload | & $Py $Script scan-reach) | Out-String
  $out = $out.Trim()
  if (-not $out) {
    return @{ status = "wrapper"; detail = "the shared scanner produced no output" }
  }
  $parts = $out -split "`t", 2
  return @{ status = $parts[0]; detail = $(if ($parts.Count -gt 1) { $parts[1] } else { "" }) }
}
$stopExcluded = @{}   # rule index -> @{kind=...; reason=...}

# Shared by per-rule classification AND the default/always fallback below -
# Codex round 4 BLOCK verify-gate.sh:950 (same bug, both flavours):
# default/always used to run with NO reach check at all, so a command a
# matching RULE had just been excluded from Stop for could still execute
# via the fallback. One function, called from both places.
function Get-CrewClassifyReach($Run, $Py, $Script, $Root) {
  $scan = Get-CrewScanReach $Run $Py $Script $Root
  if ($scan.status -eq "verb") {
    return @{ kind = "reach_undeclared";
      reason = "remote verb '$($scan.detail)' - declare ``reach`` or run /crew:verify --all" }
  }
  # Codex round 6: a command containing ANY shell metacharacter is deferred
  # unconditionally, before anything else about it is read - see
  # verify_record.py's module docstring for why this scan stopped trying
  # to model shell at all.
  if ($scan.status -eq "syntax") {
    return @{ kind = "reach_syntax";
      reason = "shell syntax in an undeclared rule - declare ``""reach"": ""local""`` (or network/host) to run it on Stop" }
  }
  if ($scan.status -eq "wrapper") {
    return @{ kind = "reach_wrapper";
      reason = "wrapper or inline shell ($($scan.detail)) - declare ``""reach"": ""local""`` (or network/host) to run it on Stop" }
  }
  return $null
}

# --- measure-and-cache ----------------------------------------------------
# The twin of the same block in verify-gate.sh. An unpriced rule that RUNS
# gets its wall time cached (by the caller below, after this loop) in
# .crew/.verify-gate.timings.json - machine-local, never verify.json. From
# the second Stop onward this folds the cached number into $ruleSecs as if
# declared, labelled "(measured, not declared)". No measurement: no change.
# CANONICAL, shared with verify-gate.sh via verify_record.py's rule_key -
# never hashed independently here. This used to run ConvertTo-Json
# -Compress (no spaces) through SHA1 natively, while the .sh matcher's own
# python heredoc used json.dumps(..., sort_keys=True) (python's default
# spaced separators) - two different byte strings for the same logical
# rule, so a key EITHER flavour wrote was invisible to the other: a timing
# one seeded never priced the other's Stop, and neither could ever clear
# the other's chronic record entry, because the keys never matched. Shells
# out to python (this script already does, for the fingerprint) rather
# than reimplementing json.dumps' separator behaviour in PowerShell, which
# is exactly the kind of thing that drifts again the next time either side
# changes independently.
function Get-CrewRuleKey($Rule, $Py, $Script) {
  if (-not $Py -or -not (Test-Path $Script)) {
    # Fail toward a key that will never match anything cached, rather than
    # toward one that might collide - an empty rule_cmds/cost/mandatory
    # entry is inert; a WRONG key that happens to match a stale one is not.
    return [System.Guid]::NewGuid().ToString("N").Substring(0, 16)
  }
  # MUST mirror every field verify_record.rule_key() hashes (paths, run,
  # env, reach, requiresCleanTree) - Codex round 2 added env/reach/
  # requiresCleanTree to the Python side's hash but this call still sent
  # only paths/run, so a rule declaring any of those three hashed to a
  # DIFFERENT key here than the one _current_rule_keys() computes reading
  # verify.json directly in-process. The mismatch is silent: the stale-
  # obligation prune in verify_record._sync() then deletes the entry this
  # very turn just wrote, because its key isn't in the "valid" set. Caught
  # by test_h_requires_clean_tree_...[ps1] going red with `rec == {"rules": {}}`.
  $blob = ConvertTo-Json -Compress -InputObject ([ordered]@{
    paths = @($Rule.paths); run = @($Rule.run); env = $Rule.env
    reach = $Rule.reach; requiresCleanTree = $Rule.requiresCleanTree })
  $out = ($blob | & $Py $Script rule-key) | Out-String
  $out = $out.Trim()
  if ($out) { return $out }
  return [System.Guid]::NewGuid().ToString("N").Substring(0, 16)
}
$ruleKeys = @{}
# Resolved ONCE, before the matching loop, and passed to every
# Get-CrewRuleKey / verify_record.py call rather than re-resolving per rule.
$matchPy = Resolve-CrewPython
$verifyRecordScript = Join-Path $PSScriptRoot 'verify_record.py'
$timings = @{}
try {
  if (Test-Path .crew/.verify-gate.timings.json) {
    # A structurally wrong cache (`[]`) parses fine and `$td.rules` on an
    # array is simply $null in PowerShell - no crash, unlike the .sh side's
    # `.get("rules")` on a python list (AttributeError). Confirmed rather
    # than assumed: this branch is already inert against that shape.
    $td = Get-Content .crew/.verify-gate.timings.json -Raw | ConvertFrom-Json -ErrorAction Stop
    if ($td.rules) {
      foreach ($p in $td.rules.PSObject.Properties) { $timings[$p.Name] = $p.Value }
    }
  }
} catch { $timings = @{} }
$measuredUsed = @{}   # rule index -> $true when cost came from the cache
$trulyUnknown = @{}   # rule index -> $true when it needs a fresh measurement
# COMMAND IDENTITY includes the rule's declared env - the twin of the same
# fix in verify-gate.sh, where the full rationale lives. Two rules running
# the same TEXT under different env used to collapse into one $cmds entry
# (deduped on bare text via -notcontains), so only the LAST rule's env ever
# actually ran and BOTH rules were recorded as verified against a command
# neither was individually shown to pass under its own environment.
function Get-CrewIdentity([string]$Cmd, [hashtable]$Env) {
  if (-not $Env -or $Env.Count -eq 0) { return $Cmd }
  $ordered = [ordered]@{}
  foreach ($k in ($Env.Keys | Sort-Object)) { $ordered[$k] = $Env[$k] }
  $envJson = ConvertTo-Json -Compress -InputObject $ordered
  return $Cmd + "`u{1c}" + $envJson
}
function Get-CrewIdentityText([string]$Identity) {
  # ORDINAL, explicitly. .NET's String.IndexOf(string) defaults to
  # CURRENT-CULTURE comparison (unlike Contains, which is ordinal by
  # default), and culture-aware comparison treats some control characters
  # as ignorable - measured: IndexOf("`u{1c}") on a string containing NO
  # such character returned 0, not -1, so every identity with no env
  # suffix at all had its command text truncated to "" right here. Ordinal
  # is what the .sh side's byte-for-byte str.partition already does.
  $idx = $Identity.IndexOf("`u{1c}", [System.StringComparison]::Ordinal)
  if ($idx -ge 0) { return $Identity.Substring(0, $idx) }
  return $Identity
}

foreach ($f in $changed) {
  $hit = $false
  $ri = -1
  foreach ($r in $vm.rules) {
    $ri++
    foreach ($p in $r.paths) {
      if (Test-CrewPath $f $p) {
        $hit = $true
        if (-not $ruleCmds.ContainsKey($ri)) {
          $ruleCmds[$ri] = [System.Collections.ArrayList]@()
          [void]$ruleOrder.Add($ri)
          $key = Get-CrewRuleKey $r $matchPy $verifyRecordScript
          $ruleKeys[$ri] = $key
          if (Test-CrewSeconds $r.seconds) {
            $ruleSecs[$ri] = [double]$r.seconds
          } elseif ($timings.ContainsKey($key)) {
            $cached = 0
            if ([int]::TryParse([string]$timings[$key], [ref]$cached) -and $cached -gt 0) {
              $ruleSecs[$ri] = [double]$cached
              $measuredUsed[$ri] = $true
            }
          }
          if ($stopMode) {
            # requiresCleanTree shares this exclusion with reach - the twin
            # of verify-gate.sh's block, where the full rationale lives.
            # Checked FIRST so a rule naming both gets the clean-tree
            # reason, the more specific of the two.
            if ($r.requiresCleanTree -eq $true) {
              $stopExcluded[$ri] = @{ kind = "clean_tree_required";
                reason = "requires a clean working tree - not run on Stop, run /crew:verify --all" }
            } else {
              $reach = $r.reach
              if ($reach -is [string] -and $reach -ne "local") {
                $stopExcluded[$ri] = @{ kind = "reach_declared";
                  reason = "declared reach: $reach - not run on Stop, run /crew:verify --all" }
              } elseif ($null -eq $reach) {
                $cls = Get-CrewClassifyReach $r.run $matchPy $verifyRecordScript $root
                if ($null -ne $cls) { $stopExcluded[$ri] = $cls }
              }
            }
          }
        }
        if ($stopExcluded.ContainsKey($ri)) { continue }
        $rEnv = @{}
        if ($r.env -and ($r.env -is [System.Management.Automation.PSCustomObject])) {
          foreach ($ep in $r.env.PSObject.Properties) {
            if ($ep.Value -is [string]) { $rEnv[$ep.Name] = $ep.Value }
          }
        }
        foreach ($c in $r.run) {
          $ident = Get-CrewIdentity $c $rEnv
          if ($cmds -cnotcontains $ident) { [void]$cmds.Add($ident) }
          if ($ruleCmds[$ri] -cnotcontains $ident) { [void]$ruleCmds[$ri].Add($ident) }
          if ($ruleSecs.ContainsKey($ri)) {
            if (-not $cost.ContainsKey($ident) -or $cost[$ident] -lt $ruleSecs[$ri]) {
              $cost[$ident] = $ruleSecs[$ri]
            }
          }
        }
      }
    }
  }
  if (-not $hit) { [void]$unmapped.Add($f) }
}
foreach ($ri in $ruleOrder) {
  if (-not $stopExcluded.ContainsKey($ri) -and -not $ruleSecs.ContainsKey($ri)) {
    $trulyUnknown[$ri] = $true
  }
}
# A matched rule that states no cost makes every command it names
# unconditional -- including commands a priced rule also names. A
# reach-excluded rule contributed no commands above, so it cannot make
# anything else mandatory.
foreach ($ri in $ruleOrder) {
  if (-not $ruleSecs.ContainsKey($ri)) {
    foreach ($c in $ruleCmds[$ri]) { $mandatory[$c] = $true }
  }
}
# `default`/`always` commands go through the SAME reach classification as
# a rule's `run` - the twin of the same fix in verify-gate.sh, where the
# full rationale lives: they used to run with no reach check at all, so a
# command a matching RULE had just been excluded from Stop for could still
# execute via the fallback. $fallbackNotices holds the reasons; $notices
# itself is not defined yet at this point in the file.
$fallbackNotices = [System.Collections.ArrayList]@()
foreach ($c in $vm.always) {
  $cls = if ($stopMode) { Get-CrewClassifyReach @($c) $matchPy $verifyRecordScript $root } else { $null }
  if ($null -ne $cls) {
    [void]$fallbackNotices.Add("``always`` command '$c' " + $cls.reason)
    continue
  }
  if ($cmds -cnotcontains $c) { [void]$cmds.Add($c) }
  $mandatory[$c] = $true
}
if ($cmds.Count -eq 0) {
  foreach ($c in $vm.default) {
    $cls = if ($stopMode) { Get-CrewClassifyReach @($c) $matchPy $verifyRecordScript $root } else { $null }
    if ($null -ne $cls) {
      [void]$fallbackNotices.Add("``default`` command '$c' " + $cls.reason)
      continue
    }
    [void]$cmds.Add($c); $mandatory[$c] = $true
  }
}

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
foreach ($ri in $ruleOrder) {
  if ($stopExcluded.ContainsKey($ri)) {
    [void]$notices.Add("verify-gate: rules[$ri] " + $stopExcluded[$ri].reason)
  }
}
foreach ($fn in $fallbackNotices) {
  [void]$notices.Add("verify-gate: $fn")
}
foreach ($ri in ($measuredUsed.Keys | Sort-Object)) {
  [void]$notices.Add("verify-gate: rules[$ri] priced from a cached measurement ($([int]$ruleSecs[$ri])s, measured not declared) - add ``seconds`` to verify.json to make this permanent")
}
$chronicRules = [System.Collections.ArrayList]@()
$acuteRules = [System.Collections.ArrayList]@()
# The deferred COUNT, kept apart from the notice TEXT. $notices mixes two
# different facts -- 'a rule was deferred' and 'a rule had no stated cost'
# -- and only the first means 'not verified', so the recording guard must
# not read it. Starts at 0 because the no-budget path defers nothing.
$deferredCount = 0
if ($null -ne $budget) {
  $unknown = @($cmds | Where-Object { -not $cost.ContainsKey($_) })
  # First-match index, so a tie on cost falls back to the order the map was
  # written in -- same tiebreak as the .sh.
  $seq = @{}
  for ($i = 0; $i -lt $ruleOrder.Count; $i++) { $seq[$ruleOrder[$i]] = $i }

  # MANDATORY-NESS IS A PROPERTY OF THE RULE -- see verify-gate.sh for the
  # two measured defects that came of attaching it to a command instead: the
  # hoisted command ran BEFORE the `prepare` its own rule put ahead of it, and
  # it was charged once on its own and again as part of its rule.
  $mustSet = @{}
  foreach ($ri in $ruleOrder) {
    if (-not $ruleSecs.ContainsKey($ri)) { continue }
    $isMust = $false
    foreach ($c in $ruleCmds[$ri]) { if ($mandatory.ContainsKey($c)) { $isMust = $true } }
    if ($isMust) { $mustSet[$ri] = $true }
  }
  $priced = @($ruleOrder | Where-Object { $ruleSecs.ContainsKey($_) })
  # Mandatory rules first, in first-match order; then the deferrable ones,
  # ascending cost with first-match order breaking ties. Same as the .sh.
  $must = @($priced | Where-Object { $mustSet.ContainsKey($_) })
  $may  = @(@($priced | Where-Object { -not $mustSet.ContainsKey($_) }) |
            Sort-Object @{Expression = { $ruleSecs[$_] }}, @{Expression = { $seq[$_] }})

  $spent = 0.0
  $keep = [System.Collections.ArrayList]@()
  $deferred = [System.Collections.ArrayList]@()
  $overrun = [System.Collections.ArrayList]@()
  foreach ($ri in (@($must) + @($may))) {
    # Only the commands this rule would ADD -- see the .sh for why a rule
    # whose work is already scheduled is charged nothing, and why that is
    # what holds each command to a single charge.
    $fresh = @($ruleCmds[$ri] | Where-Object { $cost.ContainsKey($_) -and $keep -cnotcontains $_ })
    if ($fresh.Count -eq 0) { continue }
    if ($mustSet.ContainsKey($ri)) {
      if (($spent + $ruleSecs[$ri]) -gt $budget) {
        foreach ($c in $fresh) { [void]$overrun.Add($c) }
      }
      foreach ($c in $fresh) { [void]$keep.Add($c) }
      $spent += $ruleSecs[$ri]
    } elseif (($spent + $ruleSecs[$ri]) -le $budget) {
      # WHOLE, in the rule's own `run` order. Half a rule is not a cheaper
      # rule; it is a rule nobody can say ran.
      foreach ($c in $fresh) { [void]$keep.Add($c) }
      $spent += $ruleSecs[$ri]
    } else {
      foreach ($c in $fresh) { if ($deferred -cnotcontains $c) { [void]$deferred.Add($c) } }
      # CHRONIC vs ACUTE -- the twin split in verify-gate.sh. A rule whose
      # own cost exceeds the whole budget can never fit regardless of
      # ordering (chronic); one that would fit alone but lost to this
      # turn's contention is acute and still blocks the baseline, same as
      # before this feature existed.
      if (-not $chronicRules.Contains($ri) -and -not $acuteRules.Contains($ri)) {
        if ($ruleSecs[$ri] -gt $budget) { [void]$chronicRules.Add($ri) }
        else { [void]$acuteRules.Add($ri) }
      }
    }
  }
  # A command deferred by one rule and kept by a later, cheaper one is not
  # deferred -- it runs.
  $deferred = [System.Collections.ArrayList]@(@($deferred | Where-Object { $keep -cnotcontains $_ }))

  # Unknown-cost commands run FIRST, so a map with no `seconds` anywhere
  # behaves exactly as it did before this feature existed.
  $ordered = [System.Collections.ArrayList]@()
  foreach ($c in $unknown) { [void]$ordered.Add($c) }
  foreach ($c in $keep)    { [void]$ordered.Add($c) }
  $cmds = $ordered

  foreach ($c in $unknown) {
    [void]$notices.Add('verify-gate: ' + (Get-CrewIdentityText $c) + ' has no `seconds` in verify.json - cost UNSTATED, ran anyway')
  }
  foreach ($c in $overrun) {
    [void]$notices.Add('verify-gate: ' + (Get-CrewIdentityText $c) + ' belongs to an unconditional rule (`always`, or no `seconds`) - it RAN past the budget; the cost is charged but cannot defer it')
  }
  foreach ($c in $deferred) {
    [void]$notices.Add('deferred to /crew:verify: ' + (Get-CrewIdentityText $c) + ' (' + [string][int]$cost[$c] + 's)')
  }
  foreach ($ri in $chronicRules) {
    [void]$notices.Add("verify-gate: rules[$ri] is permanently over budget ($([int]$ruleSecs[$ri])s > $([int]$budget)s stop budget) - deferred every Stop; the baseline still advances past it, but this rule stays UNVERIFIED until /crew:verify --all runs it.")
  }
  # deferredCount is now the ACUTE-only rule count (budget contention this
  # turn), not the deferred command count - the twin of the sh matcher's
  # `acute_count`. A CHRONIC or reach-excluded rule does not count here; see
  # verify_record.py for why the baseline may advance past one of those
  # while it still stays reported, forever, instead of reading as verified.
  $deferredCount = $acuteRules.Count
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

# Build the extras JSON blob once, for the env-pin lookup during the run
# loop and for the post-run record sync - the twin of record 6 in
# verify-gate.sh, in-process here rather than serialised through a pipe.
$matchedRules = [System.Collections.ArrayList]@()
foreach ($ri in $ruleOrder) {
  $kind = "normal"; $reason = ""
  if ($stopExcluded.ContainsKey($ri)) {
    $kind = $stopExcluded[$ri].kind; $reason = $stopExcluded[$ri].reason
  } elseif ($chronicRules.Contains($ri)) {
    $kind = "chronic"
    $b = if ($null -ne $budget) { [int]$budget } else { 0 }
    $reason = "permanently over budget ($([int]$ruleSecs[$ri])s > ${b}s) - run /crew:verify --all"
  }
  # rule_cmds[$ri] stays empty for a reach-excluded rule (it never runs), so
  # fall back to the rule's own `run` list. Either way, strip a possible
  # identity suffix - the label is for a human, not a lookup key.
  $firstCmd = if ($ruleCmds[$ri] -and $ruleCmds[$ri].Count -gt 0) { Get-CrewIdentityText $ruleCmds[$ri][0] }
              elseif ($vm.rules[$ri].run -and $vm.rules[$ri].run.Count -gt 0) { $vm.rules[$ri].run[0] }
              else { "" }
  if ($firstCmd.Length -gt 80) { $firstCmd = $firstCmd.Substring(0, 80) }
  [void]$matchedRules.Add([ordered]@{
    key = $(if ($ruleKeys.ContainsKey($ri)) { $ruleKeys[$ri] } else { [string]$ri })
    ri = $ri
    label = "rules[$ri]: $firstCmd"
    kind = $kind
    reason = $reason
    # IDENTITIES (text+env), not bare text - see Get-CrewIdentity above.
    # Kept exactly as $cmds carries them so cmd_log (built from the same
    # identities in the run loop) matches these one-to-one.
    cmds = @($ruleCmds[$ri])
    unknown = [bool]$trulyUnknown.ContainsKey($ri)
  })
}
$extrasObj = [ordered]@{ matched_rules = @($matchedRules) }

# The largest STATED cost among the commands actually selected. Sizes the
# lock deadline; 0 when nothing selected declared a cost, which leaves the
# window at $lockTtl -- the behaviour before the deadline existed.
$maxCost = 0
foreach ($c in $cmds) {
  if ($cost.ContainsKey($c) -and [int]$cost[$c] -gt $maxCost) { $maxCost = [int]$cost[$c] }
}

# .crew/verify.json rules are bash-flavoured strings - `bash _verify/smoke.sh`,
# `FDM_MODULE=x bash case.sh`, `cd e2e && npx playwright test --grep @flow`. So
# RUN them with bash rather than evaluating them as PowerShell. Resolve once;
# every rule in a repo shares one Windows install, and Resolve-CrewBash already
# routes around WSL's bash.exe.
# BEFORE the first rule, not only after it -- the first rule is as able to
# exceed the TTL as any later one.
Write-CrewLockDeadline -LockPath $lock -Token $lockToken -Ttl $lockTtl -MaxCost $maxCost
$bashExe = Resolve-CrewBash

# A rule's `run` string is bash-flavoured and most of .crew/verify.json's
# rules hardcode `python3` - but the bash EVERY rule command below runs
# under (Git for Windows' own bash, just resolved above) ships with no
# python3 at all, the same CLAUDE.md landmine the .sh gate carries. Twin fix
# to verify-gate.sh's, corrected after review:
#
#   - ONLY python3 is ever shimmed, and ONLY when python3 does not already
#     resolve under the SAME bash rule commands run in. `python` and `py`
#     are NEVER shadowed - review's reproduction: Windows' `py` launcher
#     accepts a `-3`/`-2` version-select flag, and the first version of
#     this fix shimmed python/py too, as a naive `exec $REAL "$@"` wrapper
#     that forwarded `-3` straight into a plain interpreter that does not
#     understand it ("Unknown option: -3"). Shimming a name that already
#     resolves to a real, working interpreter can only break something
#     that already worked.
#   - Built from Resolve-CrewPython, the PROVED resolver (it actually RUNS
#     the candidate and checks `sys.executable`, rejecting a WindowsApps
#     stub `Get-Command` alone cannot tell from a real interpreter - see
#     its own header comment above).
#   - The written shim is PROBED once (`python3 -c "import sys"`), through
#     the SAME bash rule commands run under, before it ever reaches PATH -
#     its stderr is surfaced, not discarded, so a shim that was built but
#     does not actually run is reported, not silently installed.
#
# NOT rewriting .crew/verify.json's `run` arrays to reference a $CREW_PY
# variable instead - see the twin comment in verify-gate.sh for why (other
# readers of `run`, enumerated in verification-harness.md, would see bash
# syntax naming a variable only this gate exports).
$shimDir = $null
if ($bashExe) {
  $global:LASTEXITCODE = 0
  & $bashExe -c 'command -v python3' 1>$null 2>$null
  $python3Already = ($LASTEXITCODE -eq 0)
  if (-not $python3Already) {
    $shimPy = Resolve-CrewPython
    if (-not $shimPy) {
      [Console]::Error.WriteLine("verify-gate: no python - python3, python and py all fail to resolve to a PROVED working interpreter; a rule hardcoding python3 will fail with 'command not found'")
    } elseif ($shimPy -notmatch '^([A-Za-z]:[\\/]|[\\/][\\/]?)') {
      # Defensive: Resolve-CrewPython is documented to return an absolute
      # path (sys.executable); refuse to shim from anything else rather
      # than trust a relative path into a single-quoted exec line.
      [Console]::Error.WriteLine("verify-gate: the resolved python ($shimPy) is not an absolute path - refusing to build a shim from it")
    } else {
      try {
        $candidateDir = Join-Path ([System.IO.Path]::GetTempPath()) ("crew-py-shim-" + [System.Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $candidateDir -Force -ErrorAction Stop | Out-Null
        # Single-quoted in the WRITTEN shim's own exec line, so it cannot
        # be tricked into expanding a `$` or backtick if the resolved path
        # ever contained one. Any embedded single quote in $shimPy is
        # itself escaped the standard POSIX way (close quote, backslash-
        # escaped quote, reopen quote) before being placed inside that
        # pair - the "quote it safely" guarantee, not an assumption that
        # Resolve-CrewPython never returns one.
        $shimPyEscaped = $shimPy -replace "'", "'\''"
        $shimBody = "#!/bin/sh`nexec '$shimPyEscaped' `"`$@`"`n"
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText((Join-Path $candidateDir "python3"), $shimBody, $utf8NoBom)
        # chmod through bash, not guessed from PowerShell - MSYS bash's
        # notion of "executable" on an NTFS mount is its own, and writing
        # the FILE from .NET while asking bash to set the bit (rather than
        # having bash write the content too) avoids the PowerShell/bash
        # path-quoting hazard CLAUDE.md's cygpath landmine warns about,
        # confined here to a single, simple command.
        $candidateForward = $candidateDir -replace '\\', '/'
        $global:LASTEXITCODE = 0
        $chmodOut = & $bashExe -c "chmod +x '$candidateForward/python3'" 2>&1
        if ($LASTEXITCODE -ne 0) {
          [Console]::Error.WriteLine("verify-gate: could not make the python3 shim executable: $chmodOut")
        } else {
          # PROBE before PATH - run it once and check it actually behaves
          # like python, through the same bash rule commands use.
          $global:LASTEXITCODE = 0
          $probeOut = & $bashExe -c "'$candidateForward/python3' -c 'import sys'" 2>&1
          if ($LASTEXITCODE -eq 0) {
            $shimDir = $candidateDir
          } else {
            [Console]::Error.WriteLine("verify-gate: the python3 shim did not pass its own probe (python3 -c 'import sys') - not installing it on PATH: $probeOut")
          }
        }
      } catch {
        [Console]::Error.WriteLine("verify-gate: could not build the python3 shim: $_")
      }
    }
  }
}
if ($shimDir) {
  $env:PATH = "$shimDir;$env:PATH"
  # Cleaned up on every exit path. Register-EngineEvent is ADDITIVE -
  # unlike bash's `trap`, a second registration does not replace the
  # first, so the lock's own PowerShell.Exiting handler (just above, when
  # locking succeeded) keeps firing alongside this one rather than being
  # silently dropped the way a naive re-`trap` would clobber it on the .sh
  # side (see that file's own comment on this same point).
  $shimDirForCleanup = $shimDir
  $null = Register-EngineEvent PowerShell.Exiting -Action ([scriptblock]::Create(@"
  Remove-Item -Recurse -Force '$shimDirForCleanup' -ErrorAction SilentlyContinue
"@))
}
# $shimPy being unresolvable (no python at all) is deliberately not a
# reason to stop here: unlike the .sh gate, this one parses .crew/verify.json
# with native ConvertFrom-Json and needs no python to reach this point. With
# no shim built, a rule that genuinely hardcodes `python3` on a machine with
# NO python anywhere fails loudly through the ordinary path below - bash
# reports "python3: command not found", that is a real (non-77) exit code,
# and the rule is recorded FAILED like any other failing command. That is
# the correct outcome for that case: there is no interpreter to substitute.
# Not changed here, deliberately, and for the same reason verify-gate.sh:630
# stays 0 rather than 2 for the analogous top-level case: see that comment.

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
# ANY SKIP (rc 77) must block both markers - the twin of the same tracking
# in verify-gate.sh, where the full rationale lives: a SKIP is neither a
# pass nor a fail, but it is also not a CHECK, and recording the tree as
# verified over one would let the fingerprint skip mechanism hide it from
# ever being attempted again.
$anySkipped = $false
# One entry per command actually run this turn - the twin of CMD_LOG in
# verify-gate.sh, fed to verify_record.py sync after the loop.
$cmdLog = [System.Collections.ArrayList]@()
foreach ($ident in $cmds) {
  # $ident is an IDENTITY (text, or text+`u{1c}+env JSON) - see
  # Get-CrewIdentity above. Split it in-process (PowerShell strings need no
  # subprocess round-trip the way bash's read loop does).
  $c = Get-CrewIdentityText $ident
  $envJson = if ($ident.Length -gt $c.Length) { $ident.Substring($c.Length + 1) } else { "" }
  $spec = @{}
  if ($envJson) {
    try {
      $parsed = $envJson | ConvertFrom-Json -ErrorAction Stop
      foreach ($prop in $parsed.PSObject.Properties) {
        if ($prop.Value -is [string]) { $spec[$prop.Name] = $prop.Value }
      }
    } catch { $spec = @{} }
  }
  # --- env pinning -------------------------------------------------------
  # Every PINNED_VARS name (verify_record.py) is unset
  # for every rule command unless its OWN rule declared "env" for it, in
  # which case exactly those values are set instead. The twin of the same
  # block in verify-gate.sh; see that file for why an inherited value must
  # not silently ride along into a check.
  $pinned = @()
  foreach ($v in @("ENV", "AWS_PROFILE", "AWS_DEFAULT_REGION", "KUBECONFIG", "TF_WORKSPACE",
                   "AWS_REGION", "AWS_DEFAULT_PROFILE", "AZURE_SUBSCRIPTION_ID",
                   "ARM_SUBSCRIPTION_ID", "TF_VAR_environment")) {
    if ($spec.ContainsKey($v)) {
      Set-Item -Path "env:$v" -Value $spec[$v]
      $pinned += "$v=(declared)"
    } else {
      Remove-Item -Path "env:$v" -ErrorAction SilentlyContinue
      $pinned += "$v=unset"
    }
  }
  [Console]::Error.WriteLine("verify-gate: env pinned - " + ($pinned -join ' '))

  $ruleStart = Get-Date
  if (-not $bashExe) { $bashExe = Resolve-CrewBash }
  # A native command leaves $LASTEXITCODE at its previous value when it fails
  # to start, so a stale 0 would read as a pass. Reset it first.
  $global:LASTEXITCODE = 0
  Push-Location $root
  try {
    # Captured through a REGULAR FILE, not `$out = & ... 2>&1` (kept as the
    # fallback below for the one case a temp file cannot be made) - the
    # twin of the same fix in verify-gate.sh, where the full rationale
    # lives. Capturing to a variable reads the child's output through a
    # pipe PowerShell itself manages, and a pipe only ever reports EOF once
    # EVERY process holding its write end has closed it - so a rule that
    # backgrounds something and does not itself wait for it inherits that
    # same write end, and the grandchild holding it open wedges THIS
    # process forever, the same way as the bash side. A file has no such
    # rule: `Get-Content` reads whatever is on disk right now and hits EOF
    # at the file's current size regardless of who else still has it open
    # for writing.
    $ruleOutFile = $null
    try { $ruleOutFile = [System.IO.Path]::GetTempFileName() } catch { $ruleOutFile = $null }
    if ($ruleOutFile) {
      & $bashExe -c $c > $ruleOutFile 2>&1
      $rc = $LASTEXITCODE
      $out = @(Get-Content -Path $ruleOutFile -ErrorAction SilentlyContinue)
      Remove-Item -Path $ruleOutFile -Force -ErrorAction SilentlyContinue
    } else {
      # No writable temp dir: fall back to the old capture form rather
      # than skipping the rule outright - a check that still runs,
      # carrying the original wedge risk, beats one silently skipped.
      $out = & $bashExe -c $c 2>&1
      $rc = $LASTEXITCODE
    }
  } finally {
    Pop-Location
  }
  # Exit 77 is SKIP -- the _verify/smoke.sh and GNU automake convention for
  # "skipped, environment absent". Not a pass, not a fail: it must not fail
  # the turn, and it must not be recorded as verified either (see
  # verify_record.py, which is what actually persists "skipped").
  $cmdStatus = "pass"
  if ($rc -eq 77) {
    [Console]::Error.WriteLine("verify-gate: SKIP (rc 77, environment absent): $c")
    $cmdStatus = "skip77"
    $anySkipped = $true
  } elseif ($rc -ne 0) {
    [Console]::Error.WriteLine("VERIFY FAILED: $c")
    [Console]::Error.WriteLine("bash: $bashExe")
    $out | Select-Object -Last 25 | ForEach-Object { [Console]::Error.WriteLine($_) }
    $failed = $true
    $cmdStatus = "fail"
  }
  $ruleElapsed = [int]((Get-Date) - $ruleStart).TotalSeconds
  $totalElapsed += $ruleElapsed
  [Console]::Error.WriteLine("verify-gate: ${ruleElapsed}s  $c")
  # $ident, not $c: matched_rules[...].cmds carries identities, so the
  # record-sync classification (matching THIS log against those lists) has
  # to key on the same thing, or two rules sharing command text under
  # different env would collide back into one entry.
  [void]$cmdLog.Add([ordered]@{ cmd = $ident; status = $cmdStatus; elapsed = $ruleElapsed })
  # Heartbeat AFTER the rule, matching verify-gate.sh exactly.
  Update-CrewLock -LockPath $lock -Token $lockToken
  # Re-publish the deadline after each rule, for the same reason the
  # heartbeat is here: it means 'measured from the last rule that finished'.
  Write-CrewLockDeadline -LockPath $lock -Token $lockToken -Ttl $lockTtl -MaxCost $maxCost
}
[Console]::Error.WriteLine("verify-gate: ${totalElapsed}s total across $($cmds.Count) rule command(s)")
Set-Location $root

if ($unmapped.Count -gt 0 -and $vm.unmapped -eq "fail") {
  [Console]::Error.WriteLine("UNMAPPED CHANGES - .crew/verify.json has no rule for:")
  $unmapped | ForEach-Object { [Console]::Error.WriteLine($_) }
  [Console]::Error.WriteLine("Add a rule (or mark it deliberately unchecked) before reporting this complete.")
  $failed = $true
}

# DELETE THE STALE FINGERPRINT BEFORE ANY EARLY EXIT, including the sync
# and the $failed check below it - the twin of the same fix in
# verify-gate.sh, where the full history lives: a turn where one command
# returned 77 (SKIP) and a DIFFERENT command failed outright used to exit
# before this delete ever ran, so a PASS fingerprint from an earlier turn
# survived a SKIP it should have invalidated.
if ($anySkipped) {
  Remove-Item -Path $fpFile -Force -ErrorAction SilentlyContinue
}

# Per-rule record sync now runs BEFORE the $failed early exit below, on
# EVERY turn - the twin of the same reordering in verify-gate.sh, where the
# full rationale lives. It used to sit AFTER `if ($failed) { exit 2 }`,
# reached "only on a turn where nothing FAILED", on the reasoning that "an
# unreliable run should not overwrite what a previous clean run recorded".
# That reasoning is right at the sha-marker/fingerprint granularity (a
# failed turn must never look fully verified) and wrong at the PER-RULE
# granularity the sync actually writes at: one failing rule among many
# discarded every OTHER rule's passing evidence too, because the whole sync
# call was skipped.
#
# What may now be written on a FAILED turn: per-rule PASS/SKIP/chronic/
# reach-excluded entries exactly as before. The FAILING rule's own outcome
# is deliberately NOT persisted - an earlier version of this fix DID write
# a "failed" entry, shared by both flavours, and was itself reviewed BLOCK:
# that entry orphaned the moment the rule was EDITED to fix the failure,
# because rule_key() hashes `run`, so the old "failed" key stopped matching
# _current_rule_keys() and the stale-obligation prune held the marker
# hostage behind a rule that was already fixed. See verify_record.py's
# `_sync`, the "fail" branch (the twin of this comment lives in
# verify-gate.sh) - the exit code (2) already carries the failure for THIS
# turn, and nothing needs to survive to the next one, because a FAILED turn
# never advances either marker anyway. What still may NOT happen on a
# FAILED turn: either whole-tree marker advancing. That guarantee does not
# come from anything in the sync call
# itself - it comes from `if ($failed) { exit 2 }` still running AFTER the
# sync, unconditionally on $failed, and BEFORE the marker-advance block
# further down. A sync write failure changes nothing about that:
# $syncStatus is not consulted by the exit-2 check, only by the
# marker-advance block a FAILED turn never reaches.
#
# SENTINEL, NOT 0. This used to start at 0 ("success") and only get
# reassigned inside the `$syncPy -and (Test-Path $syncScript)` guard AND
# the surrounding try/catch - so with no python resolvable, a missing
# verify_record.py, OR the invocation throwing, $syncStatus silently
# stayed 0 and $fullyVerified read "sync succeeded" from a sync that never
# ran at all. Found by the powershell-security-hardening review: hide
# python, add a reach-excluded rule, run Stop once - the notice printed,
# the record was never touched, and both markers advanced anyway. 99 means
# "not yet confirmed"; only a sync that actually completed sets it to 0.
$syncStatus = 99
try {
  $syncPy = Resolve-CrewPython
  $syncScript = Join-Path $PSScriptRoot 'verify_record.py'
  if ($syncPy -and (Test-Path $syncScript)) {
    $syncSha = (git rev-parse HEAD 2>$null)
    $payload = [ordered]@{
      sha = $syncSha
      all = [bool]$All
      matched_rules = $extrasObj.matched_rules
      cmd_log = @($cmdLog)
    }
    $payloadJson = ConvertTo-Json -InputObject $payload -Depth 10 -Compress
    $global:LASTEXITCODE = 0
    $payloadJson | & $syncPy $syncScript sync 2>$null | ForEach-Object { [Console]::Error.WriteLine($_) }
    $syncStatus = $LASTEXITCODE
  } else {
    [Console]::Error.WriteLine("verify-gate: could not sync the record (python or verify_record.py not found); NOT advancing the marker")
  }
} catch {
  [Console]::Error.WriteLine("verify-gate: could not sync the record ($_); NOT advancing the marker")
}

# A FAILED turn stops here, after its own evidence (and every passing
# rule's) has just been synced above - never before. $syncStatus plays no
# part in this decision on purpose: whether the record write succeeded or
# not, a turn with a real failure exits 2 either way.
if ($failed) { exit 2 }

# THREE things must ALL hold before either marker may advance - the twin of
# the same three-part guard in verify-gate.sh, where the full rationale
# lives: nothing was ACUTELY deferred ($deferredCount), nothing SKIPPED
# ($anySkipped - rc 77 is not a check), and the per-rule record actually
# made it to disk ($syncStatus). This guard used to read $notices.Count,
# which is prose and is also non-empty for an unstated COST -- so a rule
# that ran and passed suppressed recording -- while Write-CrewVerified, the
# sha baseline, had no guard at all. That is how a deferred rule still
# advanced the baseline and dropped a committed file out of $changed for
# every later run, including -All.
# The stale-fingerprint delete now happens BEFORE the $failed early exit,
# above - see that comment for the full history (round 2 put it in the
# elseif chain below, round 3 moved it above the elseif chain but still
# after `exit 2`, round 4 moved it again to before that exit too).

$fullyVerified = ($deferredCount -eq 0) -and (-not $anySkipped) -and ($syncStatus -eq 0)

if ($fullyVerified) {
  if ($fingerprint) {
    try {
      if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force -ErrorAction SilentlyContinue | Out-Null }
      Set-Content -Path $fpFile -Value $fingerprint -Encoding utf8 -ErrorAction Stop
    } catch { }
  }
  # Written ONLY on the fully-checked path, so the marker can never claim more
  # than was actually checked. See verify-gate.sh.
  Write-CrewVerified
} elseif ($syncStatus -ne 0) {
  # verify_record.py already printed why, on stderr, above.
} elseif ($anySkipped) {
  [Console]::Error.WriteLine("verify-gate: the verified baseline was NOT advanced - at least one command exited 77 (SKIP) and was not actually checked this turn.")
} else {
  [Console]::Error.WriteLine("verify-gate: the verified baseline was NOT advanced - $deferredCount rule command(s) were deferred and have not been checked against this tree.")
}
exit 0
