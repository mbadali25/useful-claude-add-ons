# SessionStart hook. PowerShell twin of platform-sync.sh -- both delegate to
# crew_platform.py so neither can drift from the other. A hook that WRITES
# config is the last place two implementations should be allowed to disagree.
param(
  # Probe seam, the twin of role-write-guard.ps1's -PrintPython: prints the
  # interpreter Resolve-CrewPython would use and exits 0 without touching
  # config.
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

$ErrorActionPreference = 'SilentlyContinue'

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-CrewPython {
  # BYTE-FOR-BYTE the resolver in role-write-guard.ps1 -- see that file's own
  # header for why a dot-sourced shared copy is not used, and for the full
  # history: metadata-only -> execute-and-verify (Windows audit wave 3) ->
  # `-All`-walk-every-match restored (review, 2026-09-22) after `-First 1`
  # proved unable to see a real interpreter shadowed by a same-named
  # profile function or sitting behind a same-named WindowsApps stub. A
  # hook that WRITES `.crew/config.json`'s platform block is the last place
  # that should run on an unverified interpreter.
  # `tests/test_pm_brief_platform_sync_python_resolver.py` asserts this
  # copy still agrees with role-write-guard.ps1's.
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    $candidates = Get-Command $name -All -ErrorAction SilentlyContinue
    foreach ($cmd in $candidates) {
      if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
      $global:LASTEXITCODE = $null
      $output = $null
      try {
        $output = & $cmd.Source -c 'import sys; print(sys.executable)' 2>$null
      } catch {
        $output = $null
      }
      if ($LASTEXITCODE -ne 0 -or -not $output) { continue }
      $lines = @($output)
      if ($lines.Count -ne 1) { continue }
      $real = $lines[0]
      if ([string]::IsNullOrEmpty($real)) { continue }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
      if ($env:OS -ne 'Windows_NT') {
        $item = Get-Item -LiteralPath $real -ErrorAction SilentlyContinue
        if (-not $item -or $item.UnixMode -notmatch 'x') { continue }
      }
      return $real
    }
  }
  return ''
}

if ($PrintPython) {
  Write-Output (Resolve-CrewPython)
  exit 0
}

# crew_platform.py's own session claim STAYS, and is not made redundant by the
# flavour guard above. The guard decides which FLAVOUR runs; the claim decides
# which SessionStart FIRING does the work, and SessionStart fires once per
# source event (startup, clear, compact, resume, fork), not once per session.
#
# Note what the guard does NOT do: decide by interpreter. That would be unsound
# (on Windows, `bash` on PATH is normally the WSL launcher, which would detect
# Linux for a native-Windows session), which is why it tests the OS instead --
# and why crew_platform detects from python's own view of the machine, not from
# which shell reached it.
$py = Resolve-CrewPython
if (-not $py) {
  # Non-blocking hook -- still exit 0, but LOUD: a silent exit 0 here reads
  # as "nothing to repair", not as "the interpreter is broken".
  [Console]::Error.WriteLine("crew platform-sync: no usable python (stub or unusable interpreter) - the platform config will not be repaired")
  exit 0
}
& $py (Join-Path $dir 'crew_platform.py')
exit 0
