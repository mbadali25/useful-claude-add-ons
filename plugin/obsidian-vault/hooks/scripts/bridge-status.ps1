# SessionStart hook. PowerShell twin of bridge-status.sh -- both delegate to
# bridge_status.py so neither can drift from the other.
#
# This hook cannot block: SessionStart has no exit code that stops anything
# the way PostToolUse's exit 2 does, so there is no fail-open/fail-closed
# choice to make here - only a loud/silent one. See vault-guard.ps1's header
# for the WindowsApps reproduction this PROVED-interpreter resolver defends
# against (the same defect, on the hook that CAN block).

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
$script:BridgeStatusRejected = @()

function Resolve-BridgeStatusPython {
  # Memoized within this process: a resolved (or exhausted) answer is not
  # re-derived by a second call in the same run, which would otherwise
  # re-walk and re-probe PATH from scratch. Cached only for the life of
  # THIS process -- a fresh hook invocation gets a fresh probe.
  if ($script:BridgeStatusPyMemoDone) {
    $script:BridgeStatusRejected = $script:BridgeStatusPyMemoRejected
    return $script:BridgeStatusPyMemoResult
  }
  # The PowerShell twin of bridge-status.sh's resolver, and the same algorithm as
  # crew's one shared Resolve-CrewPython: EVERY PATH match of every name is a
  # candidate, and each is EXECUTED (bounded, 3s) before it is believed.
  # Where it lives never decides. A WindowsApps App Execution Alias is tried
  # like anything else: it forwards to a working interpreter when Python is
  # installed and fails the probe when it is not. crew 1.0's Windows burn-in
  # found the old path rule plus first-match-per-name discarding three
  # WORKING aliases and never reaching the real python.exe behind them.
  #
  # Launched as a Process, not `& $cmd.Source -c ...`: the argument string
  # reaches the OS as written, so legacy native-argument passing (5.1, pwsh
  # <=7.2) has nothing to strip, and the probe can be timed out. The python
  # literal stays single-quoted all the same (_test/test_ps1_legacy_args.sh).
  # No `continue` inside try/catch: loop control across that boundary
  # differs between PowerShell versions, so the verdict leaves in variables.
  #
  # An OVERALL deadline on top of each candidate's own 3s probe bound: a
  # PATH with several hung candidates would otherwise cost 3s EACH, adding
  # up past this hook's own 10s timeout even though every individual probe
  # is bounded. Kept well inside that.
  $deadline = [System.Diagnostics.Stopwatch]::StartNew()
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    # hooks.json registers this hook with no -NoProfile, so a `function
    # python { ... }` in a user profile is loaded. It is reported, never run;
    # the executables behind it are still candidates.
    foreach ($shadow in @(Get-Command $name -All -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -ne 'Application' })) {
      $script:BridgeStatusRejected += "$name (resolved to a $($shadow.CommandType), not an executable - a profile function or alias is shadowing it)"
    }
    foreach ($cmd in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
      if (-not $cmd.Source) { continue }
      if ($deadline.Elapsed.TotalSeconds -ge 8) {
        $script:BridgeStatusRejected += "PATH walk stopped: the overall resolver deadline was reached before every candidate could be probed"
        $script:BridgeStatusPyMemoDone = $true
        $script:BridgeStatusPyMemoResult = ''
        $script:BridgeStatusPyMemoRejected = $script:BridgeStatusRejected
        return ''
      }
      $probe = $null
      $reason = ''
      try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $cmd.Source
        $psi.Arguments = '-c "import sys; v = sys.version_info; sys.stdout.write(''bridge-status-python:'' + ''%d:%d:%s:'' % (v[0], v[1], sys.implementation.name) + sys.executable)"'
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $null = $proc.StandardError.ReadToEndAsync()
        if (-not $proc.WaitForExit(3000)) {
          # The whole tree, not the candidate: a py.exe-style launcher's child
          # inherits the redirected handles and outlives a plain Kill().
          # Kill($true) is PowerShell 7 (.NET Core 3+); 5.1 has no such
          # overload and falls back to taskkill /T /F.
          try {
            $proc.Kill($true)
          } catch {
            try { & taskkill.exe /T /F /PID $proc.Id 2>&1 | Out-Null } catch { }
            try { $proc.Kill() } catch { }
          }
          $reason = "$($cmd.Source) (did not answer the interpreter probe within 3s, and was killed)"
        } elseif ($proc.ExitCode -ne 0) {
          $reason = "$($cmd.Source) (ran, but exited $($proc.ExitCode) instead of answering the interpreter probe)"
        } elseif ($outTask.Wait(1000)) {
          $probe = $outTask.Result
        }
      } catch {
        $reason = "$($cmd.Source) (could not be launched: $($_.Exception.Message))"
      }
      if ($reason) {
        $script:BridgeStatusRejected += $reason
        continue
      }
      if ($probe) { $probe = $probe.ToString().Trim() }
      if (-not $probe -or -not $probe.StartsWith('bridge-status-python:')) {
        $script:BridgeStatusRejected += "$($cmd.Source) (ran, but did not answer the interpreter probe)"
        continue
      }
      # `<major>:<minor>:<implementation>:<executable>` after the prefix, and
      # all four are checked: Python 3.8 or later, CPython or PyPy, and an
      # executable that exists -- the proof crew's Resolve-CrewPython
      # demands, and the one bridge-status.sh applies to the same answer.
      $answer = $probe.Substring('bridge-status-python:'.Length)
      if ($answer -notmatch '^(\d{1,4}):(\d{1,4}):([^:]*):(.*)$') {
        $script:BridgeStatusRejected += "$($cmd.Source) (answered the probe without a version, implementation and executable)"
        continue
      }
      $major = [int]$Matches[1]
      $minor = [int]$Matches[2]
      $impl = $Matches[3]
      $real = $Matches[4]
      if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
        $script:BridgeStatusRejected += "$($cmd.Source) (answered the probe as Python $major.$minor; 3.8 or later is required)"
        continue
      }
      if ($impl -notin @('cpython', 'pypy')) {
        $script:BridgeStatusRejected += "$($cmd.Source) (answered the probe as implementation '$impl', not cpython or pypy)"
        continue
      }
      if (-not $real) {
        # An embedded or frozen interpreter can report an empty sys.executable.
        # It answered honestly, and the answer is still unusable here.
        $script:BridgeStatusRejected += "$($cmd.Source) (answered the probe with an empty sys.executable)"
        continue
      }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) {
        $script:BridgeStatusRejected += "$($cmd.Source) (answered the probe with a sys.executable that does not exist: $real)"
        continue
      }
      # sys.executable, not Source: the PATH-found name may be a shim that
      # re-execs elsewhere, and the probe already asked python where it lives.
      $script:BridgeStatusPyMemoDone = $true
      $script:BridgeStatusPyMemoResult = $real
      $script:BridgeStatusPyMemoRejected = $script:BridgeStatusRejected
      return $real
    }
  }
  $script:BridgeStatusPyMemoDone = $true
  $script:BridgeStatusPyMemoResult = ''
  $script:BridgeStatusPyMemoRejected = $script:BridgeStatusRejected
  return ''
}

$py = Resolve-BridgeStatusPython

if (-not $py) {
    # Two answers, not one. "Found nothing named python" and "found something
    # named python that is not an interpreter" send the reader to different
    # places - the first to install python, the second to a shadowed PATH.
    if ($script:BridgeStatusRejected.Count -gt 0) {
        [Console]::Error.WriteLine("obsidian-vault bridge-status.ps1: python was found on PATH but no candidate is a usable interpreter [" + ($script:BridgeStatusRejected -join '; ') + "] - bridge status cannot run this session.")
    } else {
        [Console]::Error.WriteLine("obsidian-vault bridge-status.ps1: no python3/python/py interpreter found on PATH - bridge status cannot run this session.")
    }
    exit 0
}

try {
    & $py (Join-Path $dir 'bridge_status.py')
} catch {
    [Console]::Error.WriteLine("obsidian-vault bridge-status.ps1: the interpreter ($py) could not be launched ($($_.Exception.Message)) - bridge status did not run this session.")
}
exit 0
