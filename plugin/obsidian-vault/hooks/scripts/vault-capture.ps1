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
  # Near-copy of vault-guard.ps1's Resolve-VaultGuardPython. Copied, not
  # shared, for the same reason recorded there: crew and obsidian-vault
  # install independently, and each wrapper's stand-down message needs to
  # name itself.
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { continue }
    if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) {
      # hooks.json registers this hook with no -NoProfile, so a
      # `function python { ... }` in a user profile is loaded and wins here.
      $script:VaultCaptureRejected += "$name (resolved to a $($cmd.CommandType), not an executable - a profile function or alias is shadowing it)"
      continue
    }
    if ($cmd.Source -match 'WindowsApps') {
      $script:VaultCaptureRejected += "$($cmd.Source) (WindowsApps App Execution Alias)"
      continue
    }
    # Metadata alone is exactly what the Store alias passes: Get-Command
    # reports it as a real Application with a real Source. Launch it and read
    # back a token this script chose - only a python that parsed and ran the
    # -c program can emit the prefix.
    $probe = $null
    $reason = ''
    $global:LASTEXITCODE = $null
    try {
      # Captured WHOLE, not piped through `Select-Object -First 1`: that
      # cmdlet can close the pipeline as soon as it has one object, racing
      # the native process's exit and leaving $LASTEXITCODE reflecting an
      # early termination rather than the candidate's real status.
      # Single-quoted python string literal, escaped for PowerShell's outer
      # single-quoted argument as `''...''` - see vault-guard.ps1's twin of
      # this comment for the legacy-native-argument-passing bug this avoids
      # (double quotes here got silently stripped before python saw them,
      # producing a SyntaxError and rejecting every real interpreter).
      $output = & $cmd.Source -c 'import sys; sys.stdout.write(''vault-capture-python:'' + sys.executable)' 2>$null
      if ($LASTEXITCODE -ne 0) {
        $reason = "$($cmd.Source) (ran, but exited $LASTEXITCODE instead of answering the interpreter probe)"
      } elseif ($output) {
        $probe = @($output)[0]
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
    $real = $probe.Substring('vault-capture-python:'.Length)
    if (-not $real) {
      # An embedded or frozen interpreter can report an empty sys.executable.
      # It answered honestly, and the answer is still unusable here.
      $script:VaultCaptureRejected += "$($cmd.Source) (answered the probe with an empty sys.executable)"
      continue
    }
    if ($real -match 'WindowsApps') {
      $script:VaultCaptureRejected += "$($cmd.Source) -> $real (WindowsApps App Execution Alias)"
      continue
    }
    # sys.executable, not Source: the PATH-found name may be a shim that
    # re-execs elsewhere, and the probe already asked python where it lives.
    return $real
  }
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
