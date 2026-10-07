# SessionStart hook. Prints the crew PM's brief; stdout is injected as context.
# PowerShell twin of pm-brief.sh -- both delegate to pm_brief.py so neither can
# drift from the other.
param(
  # Probe seam, the twin of role-write-guard.ps1's -PrintPython: prints the
  # interpreter Resolve-CrewPython would use and exits 0 without printing a
  # brief. Lets the resolver be tested without needing a whole crew repo.
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
  # BYTE-FOR-BYTE the resolver in role-write-guard.ps1 -- see that file's
  # own header for why a dot-sourced shared copy is not used (invisible to
  # scripts/check-powershell.ps1's static check), and for the full history:
  # metadata-only -> execute-and-verify (Windows audit wave 3) ->
  # `-All`-walk-every-match restored (review, 2026-09-22) after `-First 1`
  # proved unable to see a real interpreter shadowed by a same-named
  # profile function or sitting behind a same-named WindowsApps stub.
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

# pm_brief.py's own session claim STAYS, and is not made redundant by the
# flavour guard above. The guard decides which FLAVOUR runs; the claim decides
# which SessionStart FIRING prints, and SessionStart fires once per source
# event (startup, clear, compact, resume, fork), not once per session -- so
# without the claim one session could still print several briefs.
#
# Note what the guard does NOT do: decide by interpreter. That would be unsound
# (on Windows, `bash` on PATH is normally the WSL launcher, which cannot
# resolve this script's own directory), which is why it tests the OS instead.
$py = Resolve-CrewPython
if (-not $py) {
  # Non-blocking hook -- still exit 0, but LOUD: a silent exit 0 here reads
  # as "crew has nothing to say", not as "the interpreter is broken".
  [Console]::Error.WriteLine("crew pm-brief: no usable python (stub or unusable interpreter) - the PM's brief will not print")
  exit 0
}
& $py (Join-Path $dir 'pm_brief.py')
exit 0
