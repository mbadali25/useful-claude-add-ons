# SessionEnd / PreCompact hook. PowerShell twin of vault-capture.sh -- both
# delegate to vault_capture.py so neither can drift from the other.
param([string]$Trigger = 'unknown')

# This hook cannot block: neither SessionEnd nor PreCompact has an exit code
# that stops anything the way PostToolUse's exit 2 does, so there is no
# fail-open/fail-closed choice to make here - only a loud/silent one. See
# vault-guard.ps1's header for the WindowsApps reproduction this
# PROVED-interpreter resolver defends against (the same defect, on the hook
# that CAN block).

# Flavour guard. Both flavours are registered for every event, so on a host
# that has BOTH interpreters both would otherwise run. Stand down only when
# we can positively prove this is not Windows.
#
# $env:OS is 'Windows_NT' on BOTH Windows PowerShell 5.1 and PowerShell 7,
# and unset on Linux/macOS. A bare `if (-not $IsWindows)` is WRONG: $IsWindows
# does not exist in 5.1, so it is $null there, `-not $null` is $true, and the
# hook stands down on the one platform it exists for. crew has already shipped
# that bug once - the guard stood down on Windows and blocked nothing there.
#
# It sits immediately after param() because param() must be the first
# statement.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:VaultCaptureRejected = @()

function Resolve-VaultCapturePython {
  # Memoized within this process: a resolved (or exhausted) answer is not
  # re-derived by a second call in the same run, which would otherwise
  # re-walk and re-probe PATH from scratch. Cached only for the life of
  # THIS process -- a fresh hook invocation gets a fresh probe.
  if ($script:VaultCapturePyMemoDone) {
    $script:VaultCaptureRejected = $script:VaultCapturePyMemoRejected
    return $script:VaultCapturePyMemoResult
  }
  # The PowerShell twin of vault-capture.sh's resolver, and the same algorithm as
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
  # up past this hook's own timeout even though every individual probe is
  # bounded. Kept well inside the shortest hook timeout that resolves
  # python this way (bridge-status.ps1's twin, 10s).
  $deadline = [System.Diagnostics.Stopwatch]::StartNew()
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    # hooks.json registers this hook with no -NoProfile, so a `function
    # python { ... }` in a user profile is loaded. It is reported, never run;
    # the executables behind it are still candidates.
    foreach ($shadow in @(Get-Command $name -All -ErrorAction SilentlyContinue | Where-Object { $_.CommandType -ne 'Application' })) {
      $script:VaultCaptureRejected += "$name (resolved to a $($shadow.CommandType), not an executable - a profile function or alias is shadowing it)"
    }
    foreach ($cmd in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
      if (-not $cmd.Source) { continue }
      # The remaining budget, not a flat 3000ms, bounds THIS candidate's
      # wait: checking the deadline only before launch and then waiting the
      # full 3s regardless can still overrun the deadline by up to 3s once
      # a candidate is entered, which on a run of several near-8s-but-under
      # candidates followed by one hung one can overrun both this deadline
      # and the 10s hook timeout it exists to stay inside.
      $vaultCaptureRemainingMs = 8000 - [int]$deadline.Elapsed.TotalMilliseconds
      if ($vaultCaptureRemainingMs -le 0) {
        $script:VaultCaptureRejected += "PATH walk stopped: the overall resolver deadline was reached before every candidate could be probed"
        $script:VaultCapturePyMemoDone = $true
        $script:VaultCapturePyMemoResult = ''
        $script:VaultCapturePyMemoRejected = $script:VaultCaptureRejected
        return ''
      }
      $vaultCaptureWaitMs = [Math]::Min(3000, $vaultCaptureRemainingMs)
      $probe = $null
      $reason = ''
      try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $probeArgs = '-c "import sys; v = sys.version_info; sys.stdout.write(''vault-capture-python:'' + ''%d:%d:%s:'' % (v[0], v[1], sys.implementation.name) + sys.executable)"'
        if ($cmd.Source -match '\.(cmd|bat)$') {
          # UseShellExecute=false hands FileName straight to CreateProcess,
          # which can only launch a real PE executable -- not a .cmd/.bat
          # shim (a pyenv-win install is exactly this shape). Route it
          # through cmd.exe /d /c instead of flipping UseShellExecute to
          # $true, which would resolve by shell file association rather
          # than run it as a command. Wrapping the whole command line in
          # one more pair of quotes defeats cmd's "exactly two quotes"
          # special case, so both the quoted shim path and the quoted -c
          # argument survive intact. Ported from crew's role-write-guard.ps1
          # (commit a39ac347), which fixed the same gap on the same
          # machines first.
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
        if (-not $proc.WaitForExit($vaultCaptureWaitMs)) {
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
        $script:VaultCaptureRejected += $reason
        continue
      }
      if ($probe) { $probe = $probe.ToString().Trim() }
      if (-not $probe -or -not $probe.StartsWith('vault-capture-python:')) {
        $script:VaultCaptureRejected += "$($cmd.Source) (ran, but did not answer the interpreter probe)"
        continue
      }
      # `<major>:<minor>:<implementation>:<executable>` after the prefix, and
      # all four are checked: Python 3.8 or later, CPython or PyPy, and an
      # executable that exists -- the proof crew's Resolve-CrewPython
      # demands, and the one vault-capture.sh applies to the same answer.
      $answer = $probe.Substring('vault-capture-python:'.Length)
      if ($answer -notmatch '^(\d{1,4}):(\d{1,4}):([^:]*):(.*)$') {
        $script:VaultCaptureRejected += "$($cmd.Source) (answered the probe without a version, implementation and executable)"
        continue
      }
      $major = [int]$Matches[1]
      $minor = [int]$Matches[2]
      $impl = $Matches[3]
      $real = $Matches[4]
      if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
        $script:VaultCaptureRejected += "$($cmd.Source) (answered the probe as Python $major.$minor; 3.8 or later is required)"
        continue
      }
      if ($impl -notin @('cpython', 'pypy')) {
        $script:VaultCaptureRejected += "$($cmd.Source) (answered the probe as implementation '$impl', not cpython or pypy)"
        continue
      }
      if (-not $real) {
        # An embedded or frozen interpreter can report an empty sys.executable.
        # It answered honestly, and the answer is still unusable here.
        $script:VaultCaptureRejected += "$($cmd.Source) (answered the probe with an empty sys.executable)"
        continue
      }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) {
        $script:VaultCaptureRejected += "$($cmd.Source) (answered the probe with a sys.executable that does not exist: $real)"
        continue
      }
      # sys.executable, not Source: the PATH-found name may be a shim that
      # re-execs elsewhere, and the probe already asked python where it lives.
      $script:VaultCapturePyMemoDone = $true
      $script:VaultCapturePyMemoResult = $real
      $script:VaultCapturePyMemoRejected = $script:VaultCaptureRejected
      return $real
    }
  }
  $script:VaultCapturePyMemoDone = $true
  $script:VaultCapturePyMemoResult = ''
  $script:VaultCapturePyMemoRejected = $script:VaultCaptureRejected
  return ''
}

$py = Resolve-VaultCapturePython

if (-not $py) {
    # Two answers, not one. "Found nothing named python" and "found something
    # named python that is not an interpreter" send the reader to different
    # places - the first to install python, the second to a shadowed PATH.
    if ($script:VaultCaptureRejected.Count -gt 0) {
        [Console]::Error.WriteLine("obsidian-vault vault-capture.ps1: python was found on PATH but no candidate is a usable interpreter [" + ($script:VaultCaptureRejected -join '; ') + "] - session capture skipped.")
    } else {
        [Console]::Error.WriteLine("obsidian-vault vault-capture.ps1: no python3/python/py interpreter found on PATH - session capture skipped.")
    }
    exit 0
}

try {
    & $py (Join-Path $dir 'vault_capture.py') $Trigger
} catch {
    [Console]::Error.WriteLine("obsidian-vault vault-capture.ps1: the interpreter ($py) could not be launched ($($_.Exception.Message)) - session capture skipped.")
}
exit 0
