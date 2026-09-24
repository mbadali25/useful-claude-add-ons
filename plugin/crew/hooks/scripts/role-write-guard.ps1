# PreToolUse gate on Write/Edit, keyed on `agent_type`. PowerShell twin of
# role-write-guard.sh -- both delegate to role_write_guard.py so neither can
# drift from the other. See role-write-guard.sh for why this is NOT branched
# by tool_name the way promote-gate.ps1 is.
param(
  # Probe seam, the twin of verify-gate.ps1's -PrintPython: prints the interpreter Resolve-CrewPython would use and
  # exits 0 without touching stdin or running the guard. This hook's only
  # consumer is Claude Code's PreToolUse hook, which pipes JSON on stdin and
  # has no interactive path to probe resolution.
  [switch]$PrintPython
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

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

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

if ($PrintPython) {
  Write-Output (Resolve-CrewPython)
  exit 0
}

# Read stdin as raw BYTES, not `[Console]::In.ReadToEnd()` -- that decodes
# using the OEM codepage (Windows PowerShell 5.1) or a pwsh-7.x-version-
# dependent default, silently mangling anything outside plain ASCII
# (an accented character reaching this script mangles into `?` on 5.1 or
# multi-byte garbage on pwsh 7.6.6, verified with the test suite's own
# accented-character case) and turning a leading
# UTF-8 BOM into garbage bytes that make the decoded JSON unparseable at
# byte zero -- role_write_guard.py's own `except ValueError` then silently
# allows the call UNJUDGED. role-write-guard.sh (`INPUT=$(cat)`) is
# byte-transparent, so the two shell flavours diverged on byte-identical
# input. Reported and fixed 2026-09-19.
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$stdinBytes = $memStream.ToArray()

# Strip a leading UTF-8 BOM (EF BB BF) before decoding -- a BOM surviving
# into the decoded string is itself invalid JSON at position 0, which
# would fail role_write_guard.py's parse for a different reason than an
# encoding mismatch, and either way the payload must decode clean.
if ($stdinBytes.Length -ge 3 -and $stdinBytes[0] -eq 0xEF -and
    $stdinBytes[1] -eq 0xBB -and $stdinBytes[2] -eq 0xBF) {
  if ($stdinBytes.Length -gt 3) {
    $stdinBytes = $stdinBytes[3..($stdinBytes.Length - 1)]
  } else {
    $stdinBytes = [byte[]]@()
  }
}
$raw = [System.Text.Encoding]::UTF8.GetString($stdinBytes)

# Deny-list mirror of role_write_guard.py's `_DENY_ROLES`, plus `pm` (that
# module's other restricted role) -- used both when NO python resolves at
# all (below) and by the BLOCK-1 fallback further down, when
# role_write_guard.py could not be launched. `tests/test_role_write_guard.py`'s
# parity test re-derives the python side from `agents/*.md` on every run
# and asserts this list matches it.
$RestrictedRolesForFallback = @(
  'explorer', 'researcher', 'reviewer', 'security', 'pm'
)

function Get-FallbackRole {
  # Consulted whenever python cannot be used to reach a real decision --
  # either no candidate resolves at all, or a resolved candidate fails to
  # launch role_write_guard.py. Never throws: an unparseable payload
  # answers $null, the same permissive fallback role_write_guard.py itself
  # gives one.
  param([string]$RawJson)
  try {
    $obj = $RawJson | ConvertFrom-Json -ErrorAction Stop
  } catch {
    return $null
  }
  $agentType = $obj.agent_type
  if (-not $agentType) { return $null }
  $role = ([string]$agentType).Trim().ToLowerInvariant()
  if ($role.StartsWith('crew:')) { $role = $role.Substring(5).Trim() }
  if (-not $role) { return $null }
  return $role
}

$py = Resolve-CrewPython
if (-not $py) {
  # No candidate resolved at all -- a DIFFERENT failure than BLOCK-1 below
  # (which is a candidate that resolved, was proven executable, and then
  # still failed to launch). Reported 2026-09-24 alongside the WindowsApps
  # resolver fix: fixing the resolver alone still leaves a genuinely
  # python-less host (or any other total-resolution failure) falling
  # through to an unconditional "allow it unjudged" -- which for a role
  # this table ALREADY knows is restricted (`pm`, or a `_DENY_ROLES`
  # member) throws away a decision that needed no python at all. A
  # `_DENY_ROLES` role may not write ANY file regardless of path; `pm` is
  # refused for anything outside its own patterns often enough that
  # collapsing "cannot judge" into "allow" for either is exactly CLAUDE.md's
  # named recurring bug ("an unknown collapsing into the safe-looking
  # value"), not a neutral default. Mirrors BLOCK-1's own
  # $RestrictedRolesForFallback / Get-FallbackRole exactly, so both failure
  # modes agree on which roles fail closed.
  $fallbackRole = Get-FallbackRole $raw
  if ($RestrictedRolesForFallback -contains $fallbackRole) {
    [Console]::Error.WriteLine("role-write-guard: no usable python found - cannot judge this write; failing closed for role ``$fallbackRole``.")
    exit 2
  }
  [Console]::Error.WriteLine("role-write-guard: no usable python found - cannot judge this write; allowing it unjudged.")
  exit 0
}

$scriptPath = Join-Path $dir 'role_write_guard.py'
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
  # Without this check, a missing/broken role_write_guard.py reaches
  # python as a bare file-not-found error and exits 2 -- indistinguishable
  # from an actual `guards.roleWrites: block` refusal by exit code alone,
  # so an installation defect reads as a policy decision nobody made.
  # Still fails closed (exit 2): a broken install is not evidence a write
  # is safe. Reported and fixed 2026-09-19.
  [Console]::Error.WriteLine("role-write-guard: role_write_guard.py is missing at $scriptPath; failing closed.")
  exit 2
}

# Force the string back OUT as UTF-8 when it is piped to the native python
# process below -- PowerShell's pipe-to-native-command path re-encodes a
# .NET string using `[Console]::OutputEncoding` (and, on Windows PowerShell
# 5.1, the legacy `$OutputEncoding` preference variable too), which
# otherwise defaults to the OEM codepage and would reintroduce the exact
# mangling the read above just avoided.
$prevConsoleEncoding = [Console]::OutputEncoding
$prevOutputEncodingVar = $OutputEncoding
$prevPythonUtf8 = $env:PYTHONUTF8
$prevPythonIoEncoding = $env:PYTHONIOENCODING
$exitCode = $null
$launchFailure = $null
try {
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  # Force these in the CHILD's environment regardless of what the CALLER's
  # environment already set -- reported 2026-09-19: a caller that
  # explicitly set PYTHONUTF8=0 and left PYTHONIOENCODING unset could
  # still reach python with a correctly-UTF8-encoded pipe (the encoding
  # fix immediately above) and have PYTHON'S OWN decoding of it go wrong
  # regardless, since `sys.stdin.read()`'s text-mode decoding depends on
  # these. role_write_guard.py's `sys.stdin.buffer` read no longer
  # depends on them for INPUT either way, but its stdout/stderr writes of
  # a non-ASCII path still do, so this stays load-bearing for those.
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  $global:LASTEXITCODE = $null
  $raw | & $py $scriptPath
  $exitCode = $LASTEXITCODE
} catch {
  $launchFailure = $_
} finally {
  [Console]::OutputEncoding = $prevConsoleEncoding
  $OutputEncoding = $prevOutputEncodingVar
  $env:PYTHONUTF8 = $prevPythonUtf8
  $env:PYTHONIOENCODING = $prevPythonIoEncoding
}

if ($null -eq $exitCode) {
  # The python process never reported an exit code -- either the launch
  # itself threw (caught above) or, on some PowerShell/OS combinations, a
  # failed-to-start native command leaves $LASTEXITCODE untouched with NO
  # catchable exception at all. `exit $LASTEXITCODE` on a null value
  # silently evaluates to 0 (allow) -- CLAUDE.md's own named recurring bug
  # in a new shape: the header comment above promised this hook fails
  # closed for a restricted role, and a silent 0 here broke that promise
  # with no diagnostic at all beyond a generic native-command error on
  # stderr. Reported and fixed 2026-09-19. `$global:LASTEXITCODE = 0` is
  # NOT the fix -- that would make this exact failure look identical to an
  # explicit `allow`, which is the same silent-collapse shape with extra
  # steps. `$py` was already proven to be a real, executable interpreter
  # by Resolve-CrewPython's own execute-to-verify probe, so reaching here
  # means something changed between resolution and this launch (deleted,
  # permissions, antivirus, ...) -- rare, but not nonexistent, and not
  # evidence a write from a role this table already knows is restricted
  # is safe to let through.
  $fallbackRole = Get-FallbackRole $raw
  if ($RestrictedRolesForFallback -contains $fallbackRole) {
    [Console]::Error.WriteLine("role-write-guard: could not launch the python interpreter ($py) to judge this write; failing closed for role ``$fallbackRole``. $launchFailure")
    exit 2
  }
  [Console]::Error.WriteLine("role-write-guard: could not launch the python interpreter ($py) to judge this write; allowing it unjudged. $launchFailure")
  exit 0
}

exit $exitCode
