# crew-hook.ps1 <Event> [-Harness codex]: the PowerShell launcher behind every
# crew hook registration (L-0727). hooks.json registers it once per event; it
# runs crew_hook.py, which picks the event's hook scripts, runs them
# concurrently (the `.sh` ones through a strictly resolved Git Bash) and merges
# their results. On Windows this is the single path: crew-hook.sh exits 0 there.
#
# It SUPERVISES crew_hook.py, it does not hand over to it. Exit 0 and 2 pass
# through. Anything else (no exit code, a launch failure, the deadline passing)
# means the dispatcher never reached a decision, and PreToolUse,
# UserPromptSubmit and Stop are events where a hook may block: in an ARMED repo
# that is exit 2 naming the cause, otherwise exit 0 (spec A7, B8). One deadline,
# taken here and exported as CREW_HOOK_DEADLINE (epoch ms), covers the python
# probe, the stdin read, the dispatcher and the cleanup: the registration
# timeout in hooks.json minus 5 s.
#
# No python: an armed repo gets exit 2 on those three events, naming python
# (B10); an unarmed one exit 0, except a PreToolUse write by a restricted (or
# unreadable) role, which is role-write-guard.ps1's config-independent fallback,
# kept.
# The empty catch blocks are deliberate: a failed cleanup of a probe or a child
# must not replace the decision being reported, and Resolve-CrewPython's own are
# the shared copy the tests hold byte-identical.
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingEmptyCatchBlock', '')]
param(
  [Parameter(Position = 0)][string]$HookEvent = '',
  [string]$Harness = 'claude',
  # Probe seam, the twin of the other carriers' -PrintPython.
  [switch]$PrintPython,
  # Not for callers. A default value runs before the first statement, which the flavour
  # guard below must stay (tests/test_flavour_guard.py holds it to that, exactly). On a REAL
  # Windows host -- told by the platform, which an environment variable cannot change -- this
  # puts `$env:OS` back to 'Windows_NT', so a settings `env` block that unsets or changes OS
  # cannot make the guard stand this launcher down: it is the only launcher that runs on
  # Windows (security pass, L-0850). Elsewhere it does nothing.
  [string]$CrewPlatformMarker = $(if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) { $env:OS = 'Windows_NT' })
)

# Flavour guard, first executable statement: `$env:OS` is 'Windows_NT' on both Windows PowerShell
# 5.1 and PowerShell 7 and unset elsewhere (see the parameter above for a real Windows host).
# Not `$IsWindows`, which does not exist in 5.1.
if ($env:OS -ne 'Windows_NT') { exit 0 }
$null = $CrewPlatformMarker

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# BYTE-FOR-BYTE the resolver in the review/gate harness carriers, asserted by
# tests/test_ps1_python_probe.py.
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
  # L-0690: how the probe ended, for the caller to print. Set on every return
  # with the result and memoized with it; this function writes nothing.
  #   $script:CrewPythonOutcome  found | not-found | rejected | timed-out
  #   $script:CrewPythonTrail    a summary line, then one line per candidate
  # timed-out is "could not tell": a candidate was killed at its bound, its
  # stdout was not read in time, or the 8s budget ran out with a candidate
  # untried. rejected: every candidate launched (or failed to launch) and
  # answered inside its bound, and none was a python. not-found: nothing on
  # PATH reached a launch.
  $crewPythonRows = New-Object System.Collections.Generic.List[string]
  $crewPythonTimedOut = $false
  $crewPythonLaunched = $false
  $crewPythonSpent = $false
  $crewPythonFound = ''
  # ONE probe, byte for byte in the four review/gate harness .ps1 hooks, with
  # its outcome and trail (L-0690); the other carriers keep the pre-L-0690
  # copy until a follow-up rejoins them. Both groups are asserted by
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
    if ($crewPythonFound -or $crewPythonSpent) { break }
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
      $crewPythonBegan = [int]$crewPythonDeadline.Elapsed.TotalMilliseconds
      if ($crewPythonRealWindows) {
        $crewPythonExt = [System.IO.Path]::GetExtension($cmd.Source)
        if ($crewPythonNativeExts -notcontains $crewPythonExt) {
          Write-Verbose "Resolve-CrewPython: skipping '$($cmd.Source)' - not natively launchable on Windows (extension '$crewPythonExt' outside .exe/.com/.cmd/.bat)"
          $crewPythonRows.Add("$name $($cmd.Source) 0 ms skipped-extension")
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
        # The walk stops here; later candidates are not enumerated.
        $crewPythonRows.Add("$name $($cmd.Source) 0 ms not-tried-budget-spent")
        $crewPythonTimedOut = $true
        $crewPythonSpent = $true
        break
      }
      $crewPythonWaitMs = [Math]::Min(3000, $crewPythonRemainingMs)
      $real = $null
      $crewPythonVerdict = 'start-failed'
      $crewPythonLaunched = $true
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
        $psi.RedirectStandardInput = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        # Closed at once: the probe never reads stdin, and an OPEN inherited
        # stdin parks a child forever, which would make a healthy candidate
        # look dead and get it rejected.
        $proc.StandardInput.Close()
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
          $crewPythonVerdict = "killed-at-bound $crewPythonWaitMs ms"
          $crewPythonTimedOut = $true
        } elseif ($proc.ExitCode -ne 0) {
          $crewPythonVerdict = "exit-nonzero $($proc.ExitCode)"
        } elseif (-not $outTask.Wait(1000)) {
          $crewPythonVerdict = 'output-read-timeout'
          $crewPythonTimedOut = $true
        } else {
          $crewPythonVerdict = 'not-python-proof'
          $line = @(($outTask.Result -split "`r?`n") | Where-Object { $_.Trim() })[-1]
          # An empty answer leaves $line null, and piping $null into ConvertFrom-Json is a
          # NON-terminating binding error this try never catches: it reached stderr as a red
          # error block on every hook, though the candidate was rightly rejected (T-0097).
          $probe = if ($line) { $line | ConvertFrom-Json } else { $null }
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
      if ($real -and -not (Test-Path -LiteralPath $real -PathType Leaf)) {
        $crewPythonVerdict = 'exe-missing'
        $real = $null
      }
      if ($real) { $crewPythonVerdict = 'accepted' }
      $crewPythonTook = [int]$crewPythonDeadline.Elapsed.TotalMilliseconds - $crewPythonBegan
      $crewPythonRows.Add("$name $($cmd.Source) $crewPythonTook ms $crewPythonVerdict")
      if (-not $real) { continue }
      $crewPythonFound = $real
      break
    }
  }
  $crewPythonOutcome = if ($crewPythonFound) { 'found' } elseif ($crewPythonTimedOut) { 'timed-out' } elseif ($crewPythonLaunched) { 'rejected' } else { 'not-found' }
  $crewPythonTrail = New-Object System.Collections.Generic.List[string]
  $crewPythonTrail.Add("python probe: $crewPythonOutcome after $([int]$crewPythonDeadline.Elapsed.TotalMilliseconds) ms (budget 8000 ms, 3000 ms per candidate)")
  for ($i = 0; $i -lt [Math]::Min(8, $crewPythonRows.Count); $i++) {
    $crewPythonTrail.Add('python probe:   ' + $crewPythonRows[$i])
  }
  if ($crewPythonRows.Count -gt 8) { $crewPythonTrail.Add("python probe:   (+$($crewPythonRows.Count - 8) more)") }
  $script:CrewPythonOutcome = $crewPythonOutcome
  $script:CrewPythonTrail = $crewPythonTrail.ToArray()
  $script:CrewPythonMemoDone = $true
  $script:CrewPythonMemoResult = $crewPythonFound
  return $crewPythonFound
}

function Write-CrewPythonTrail {
  # L-0690: the probe's trail (Resolve-CrewPython's $script:CrewPythonTrail) on
  # stderr, once per process, after the message about the probe's outcome.
  if ($script:CrewPythonTrailShown) { return }
  $script:CrewPythonTrailShown = $true
  foreach ($crewTrailLine in @($script:CrewPythonTrail)) {
    if ($crewTrailLine) { [Console]::Error.WriteLine($crewTrailLine) }
  }
}

if ($PrintPython) {
  $crewPrinted = Resolve-CrewPython
  Write-Output $crewPrinted
  if (-not $crewPrinted) { Write-CrewPythonTrail }
  exit 0
}

# Registration timeout (s) per event, from hooks.json: the largest hook in the
# event plus 10. A test asserts this equals crew_hook.event_timeout.
$crewTimeouts = @{
  SessionStart = 30; UserPromptSubmit = 30; PreToolUse = 30; PostToolUse = 20
  SubagentStart = 25; PreCompact = 40; Notification = 25; Stop = 610
}
if (-not $crewTimeouts.ContainsKey($HookEvent)) { exit 0 }

$crewDeadlineMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() + ($crewTimeouts[$HookEvent] - 5) * 1000
# An inherited deadline may only bring the deadline forward (the fault tests).
$crewInherited = 0L
if ([long]::TryParse([string]$env:CREW_HOOK_DEADLINE, [ref]$crewInherited) -and $crewInherited -lt $crewDeadlineMs) {
  $crewDeadlineMs = $crewInherited
}
$env:CREW_HOOK_DEADLINE = [string]$crewDeadlineMs

$crewBlocking = @('PreToolUse', 'UserPromptSubmit', 'Stop') -contains $HookEvent

function Get-RemainingMs {
  return [int][Math]::Max(0, $crewDeadlineMs - [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
}

# True when the path is there, or cannot be told: an error stat'ing it counts as
# there. A superset of crew_hook.armed(); tests/test_crew_hook_faults.py asserts
# that every case armed() calls armed, this calls armed too.
function Test-CrewPresent([string]$Path) {
  try {
    if (Test-Path -LiteralPath $Path) { return $true }
    $parent = Split-Path -Parent $Path
    while ($parent -and -not (Test-Path -LiteralPath $parent)) { $parent = Split-Path -Parent $parent }
    if (-not $parent) { return $true }
    $null = Get-ChildItem -LiteralPath $parent -Force -ErrorAction Stop | Select-Object -First 1
    return $false
  } catch {
    return $true
  }
}

function Test-CrewArmed {
  try {
    $root = $env:CLAUDE_PROJECT_DIR
    if (-not $root) { $root = (Get-Location).Path }
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { return $true }
    foreach ($rel in @('.crew\config.json', '.crew\crew.json', '.crew')) {
      if (Test-CrewPresent (Join-Path $root $rel)) { return $true }
    }
    $git = Join-Path $root '.git'
    if (Test-Path -LiteralPath $git -PathType Leaf) { return $true }
    if (-not (Test-Path -LiteralPath $git -PathType Container) -and (Test-CrewPresent $git)) { return $true }
    $home1 = $env:USERPROFILE
    if (-not $home1) { $home1 = $env:HOME }
    if (-not $home1) { return $true }
    return (Test-CrewPresent (Join-Path $home1 '.claude\crew\config.json'))
  } catch {
    return $true
  }
}

function Exit-Fault([string]$Message) {
  if ($crewBlocking -and (Test-CrewArmed)) {
    [Console]::Error.WriteLine("crew-hook: $Message; failing closed (armed repo).")
    exit 2
  }
  [Console]::Error.WriteLine("crew-hook: $Message; the repo is not armed, or this event cannot block, so nothing is blocked.")
  exit 0
}

# Raw BYTES, not [Console]::In.ReadToEnd(), which decodes with the OEM codepage
# on 5.1; nothing stripped (a BOM reaches the dispatcher as it came).
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$readTask = $stdinStream.CopyToAsync($memStream)
if (-not $readTask.Wait((Get-RemainingMs))) {
  Exit-Fault 'stdin did not close before the deadline'
}
$stdinBytes = $memStream.ToArray()

# role-write-guard.ps1's no-python contract, kept: only a restricted role, or a
# role that cannot be read, is refused. The list is asserted equal to
# role-write-guard's by the tests.
$crewRestrictedRoles = @('explorer', 'researcher', 'reviewer', 'security', 'pm')
$crewWriteTools = @('Write', 'Edit', 'MultiEdit', 'NotebookEdit')

function Test-RestrictedWrite([byte[]]$Bytes) {
  try {
    $text = [System.Text.Encoding]::UTF8.GetString($Bytes).TrimStart([char]0xFEFF)
    $obj = $text | ConvertFrom-Json -ErrorAction Stop
  } catch {
    return $true
  }
  if ($obj -isnot [System.Management.Automation.PSCustomObject]) { return $true }
  $hasTool = Get-Member -InputObject $obj -Name 'tool_name' -MemberType NoteProperty -ErrorAction SilentlyContinue
  if (-not $hasTool -or $obj.tool_name -isnot [string]) { return $false }
  if ($crewWriteTools -notcontains $obj.tool_name) { return $false }
  $hasRole = Get-Member -InputObject $obj -Name 'agent_type' -MemberType NoteProperty -ErrorAction SilentlyContinue
  if (-not $hasRole) { return $false }
  if ($obj.agent_type -isnot [string]) { return $true }
  $role = $obj.agent_type.Trim().ToLowerInvariant()
  if ($role.StartsWith('crew:')) { $role = $role.Substring(5).Trim() }
  if (-not $role) { return $false }
  return ($crewRestrictedRoles -contains $role)
}

$py = Resolve-CrewPython
if (-not $py) {
  $crewWhy = if ($script:CrewPythonOutcome -eq 'timed-out') { 'the python probe timed out, so python could not be found' } else { 'no usable python was found' }
  if ($crewBlocking -and (Test-CrewArmed)) {
    [Console]::Error.WriteLine("crew-hook: $crewWhy and crew governs this repo; failing closed. Install python 3.8 or later.")
    Write-CrewPythonTrail
    exit 2
  }
  if ($HookEvent -eq 'PreToolUse' -and (Test-RestrictedWrite $stdinBytes)) {
    [Console]::Error.WriteLine("crew-hook: $crewWhy; a write by a restricted or unreadable role is refused without python (role-write-guard's fallback).")
    Write-CrewPythonTrail
    exit 2
  }
  [Console]::Error.WriteLine("crew-hook: $crewWhy; no hook ran.")
  Write-CrewPythonTrail
  exit 0
}

$crewScript = Join-Path $dir 'crew_hook.py'
if (-not (Test-Path -LiteralPath $crewScript -PathType Leaf)) {
  Exit-Fault "crew_hook.py is missing at $crewScript"
}
if ((Get-RemainingMs) -le 0) { Exit-Fault 'the python probe used the whole deadline' }

$crewArgs = '"' + $crewScript + '" ' + $HookEvent
if ($Harness -eq 'codex') { $crewArgs += ' --harness codex' }

$crewOut = New-Object System.IO.MemoryStream
$crewErr = New-Object System.IO.MemoryStream
$crewCode = $null
$crewProc = $null
try {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $py
  $psi.Arguments = $crewArgs
  $psi.UseShellExecute = $false
  $psi.RedirectStandardInput = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true
  $psi.EnvironmentVariables['PYTHONUTF8'] = '1'
  $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
  $psi.EnvironmentVariables['CREW_HOOK_DEADLINE'] = [string]$crewDeadlineMs
  $crewProc = [System.Diagnostics.Process]::Start($psi)
  $outTask = $crewProc.StandardOutput.BaseStream.CopyToAsync($crewOut)
  $errTask = $crewProc.StandardError.BaseStream.CopyToAsync($crewErr)
  try {
    $crewProc.StandardInput.BaseStream.Write($stdinBytes, 0, $stdinBytes.Length)
    $crewProc.StandardInput.BaseStream.Flush()
  } catch {
    # python exited before it read everything: its exit code says what happened
  }
  try { $crewProc.StandardInput.Close() } catch { }
  if (-not $crewProc.WaitForExit((Get-RemainingMs) + 2000)) {
    try {
      $crewProc.Kill($true)
    } catch {
      try { & taskkill.exe /T /F /PID $crewProc.Id 2>&1 | Out-Null } catch { }
      try { $crewProc.Kill() } catch { }
    }
    try { $null = $crewProc.WaitForExit(2000) } catch { }
    Exit-Fault 'crew_hook.py ran past the deadline and was killed'
  }
  $null = $outTask.Wait(3000)
  $null = $errTask.Wait(3000)
  $crewCode = $crewProc.ExitCode
} catch {
  Exit-Fault "crew_hook.py could not be run ($($_.Exception.Message))"
}

$stdoutStream = [Console]::OpenStandardOutput()
$crewBytes = $crewOut.ToArray()
if ($crewBytes.Length -gt 0) { $stdoutStream.Write($crewBytes, 0, $crewBytes.Length); $stdoutStream.Flush() }
$stderrStream = [Console]::OpenStandardError()
$crewBytes = $crewErr.ToArray()
if ($crewBytes.Length -gt 0) { $stderrStream.Write($crewBytes, 0, $crewBytes.Length); $stderrStream.Flush() }

# crew_hook.py only ever exits 0 or 2. Anything else, including no exit code at
# all (which `exit $LASTEXITCODE` would turn into a silent 0), means it never
# reached a decision.
if ($null -eq $crewCode -or ($crewCode -ne 0 -and $crewCode -ne 2)) {
  Exit-Fault "crew_hook.py failed (exit $crewCode)"
}
exit $crewCode
