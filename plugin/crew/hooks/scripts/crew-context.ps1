# crew's context hook, PowerShell twin of crew-context.sh. SessionStart,
# UserPromptSubmit, PostToolUse and SubagentStart; `-Harness codex` when Codex
# runs it through `.codex/hooks.json`'s `commandWindows`. stdout is an
# additionalContext payload or nothing, and this hook NEVER blocks: every
# path below exits 0. Both flavours delegate to crew_context.py, which also
# holds the one-flavour-per-event claim, so neither can drift from the other.
param(
  # Probe seam, the twin of role-write-guard.ps1's -PrintPython.
  [switch]$PrintPython,
  [string]$Harness = 'claude'
)

# Flavour guard, first executable statement: `$env:OS` is 'Windows_NT' on
# both Windows PowerShell 5.1 and PowerShell 7 and unset elsewhere. Not
# `$IsWindows`, which does not exist in 5.1 (see test_flavour_guard.py).
if ($env:OS -ne 'Windows_NT') { exit 0 }

$ErrorActionPreference = 'SilentlyContinue'

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# The resolver in role-write-guard.ps1 byte for byte EXCEPT its probe, which
# is time-bounded here (see the probe comment), asserted by
# tests/test_crew_context_wrappers.py.
function Resolve-CrewPython {
  # NOT byte-for-byte with verify-gate.ps1's/pm-pulse.ps1's copies any more
  # -- see tests/test_role_write_guard.py for why the parity discipline
  # changed shape rather than being dropped. Those two files' resolver only
  # needs to match `_common.sh`'s bare `crew_py()`; this one needs to match
  # role-write-guard.sh's OWN resolver, which does more than `crew_py()`
  # does, so this copy has to as well.
  #
  # Two bugs, reported together 2026-09-19 by a PowerShell-focused review of
  # THIS file specifically, on top of the WindowsApps/profile-shadow guards
  # this function already had:
  #
  #   1. Metadata alone (`.CommandType` / `.Source`) is exactly what a
  #      WindowsApps stub already passes -- `Get-Command` reports it as a
  #      real Application with a real Source. role-write-guard.sh's own
  #      resolver does not trust that either: it EXECUTES the candidate
  #      (`$cand -c "import sys;print(sys.executable)"`) and reads back
  #      what actually ran. This copy now does the same, rejecting a
  #      candidate that produces no output when actually launched.
  #   2. `Get-Command $name -All` walked every match for ONE name before
  #      moving to the next name -- so on `PATH=WindowsApps;RealDir` with
  #      only `python3` present anywhere (no `python`/`py` at all), the old
  #      code walked PAST the WindowsApps `python3` stub and found
  #      RealDir's `python3` further down PATH. Bash's `command -v
  #      python3` (role-write-guard.sh's resolver) takes only the FIRST
  #      match for a name; rejecting it moves to the NEXT NAME, never a
  #      second search of the same one -- so the .sh abandoned `python3`
  #      after the stub and never found a `python`/`py` that did not
  #      exist either. Same PATH, same machine: one shell flavour
  #      enforced `guards.roleWrites: block` and the other silently
  #      allowed the write unjudged. This copy now takes only the first
  #      match per name too, mirroring the .sh's name-order exactly.
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd -or $cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
    if ($cmd.Source -match 'WindowsApps') { continue }
    $real = $null
    $global:LASTEXITCODE = $null
    try {
      # BOUNDED probe -- the one deliberate difference from
      # role-write-guard.ps1's copy (tests/test_crew_context_wrappers.py
      # asserts it is the only one). `& $cmd.Source` waits forever, so a
      # shim that hangs stalled this hook until the harness killed it.
      # Run to completion or killed at 3s; stdout and stderr are both read
      # asynchronously so a chatty candidate cannot deadlock on a full pipe.
      $psi = New-Object System.Diagnostics.ProcessStartInfo
      $psi.FileName = $cmd.Source
      $psi.Arguments = '-c "import sys; print(sys.executable)"'
      $psi.UseShellExecute = $false
      $psi.RedirectStandardOutput = $true
      $psi.RedirectStandardError = $true
      $psi.CreateNoWindow = $true
      $proc = [System.Diagnostics.Process]::Start($psi)
      $outTask = $proc.StandardOutput.ReadToEndAsync()
      $null = $proc.StandardError.ReadToEndAsync()
      if (-not $proc.WaitForExit(3000)) {
        try { $proc.Kill() } catch { }
        continue
      }
      $output = ($outTask.Result -split "`r?`n") | Where-Object { $_ }
      # NOT just "did it print something" -- a wrapper that prints a
      # plausible interpreter path and then exits nonzero must be
      # rejected too, matching role-write-guard.sh's own
      # `real=$(...) || continue`, which checks the candidate's exit
      # status. Reported 2026-09-19: this check was absent, so a
      # candidate bash correctly rejected (nonzero exit) was still
      # ACCEPTED here on output alone.
      if ($proc.ExitCode -eq 0 -and $output) {
        $real = @($output)[0]
      }
    } catch {
      $real = $null
    }
    if ($real) { $real = $real.ToString().Trim() }
    if (-not $real -or $real -match 'WindowsApps') { continue }
    # Exit 0 and non-empty output is still not proof: a wrapper could print a
    # plausible-looking path to something that is not actually there. Confirm
    # the path EXISTS as a file before trusting it -- the bash-side parity
    # check is `[ -x "$real" ]`; Test-Path has no executable-bit concept on
    # Windows (an .exe's "executability" is its extension, not a mode bit),
    # so -PathType Leaf is the equivalent proof here.
    if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
    return $real
  }
  return ''
}

if ($PrintPython) {
  Write-Output (Resolve-CrewPython)
  exit 0
}

if ($Harness -ne 'codex') { $Harness = 'claude' }

# Raw BYTES, not [Console]::In.ReadToEnd(), which decodes with the OEM
# codepage on 5.1 -- the reason role-write-guard.ps1 reads this way. The
# python side hashes these bytes for the one-flavour claim, so the .sh and
# .ps1 flavours must hand it the SAME bytes: they go to python's stdin
# untouched below (no BOM strip -- crew_context.py decodes utf-8-sig -- and
# no PowerShell pipe, which re-encodes a string and appends a newline, so
# the two flavours hashed different keys and both emitted).
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$stdinBytes = $memStream.ToArray()

$py = Resolve-CrewPython
if (-not $py) {
  [Console]::Error.WriteLine("crew context: no usable python (stub or unusable interpreter) - no code-map or recall context this event")
  exit 0
}

$prevConsoleEncoding = [Console]::OutputEncoding
$prevOutputEncodingVar = $OutputEncoding
$prevPythonUtf8 = $env:PYTHONUTF8
$prevPythonIoEncoding = $env:PYTHONIOENCODING
try {
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  # A Process, not `$bytes | & $py`: only a stream write hands python the
  # bytes as received. stdout is not redirected, so python's payload goes
  # straight to the hook's own stdout.
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $py
  $psi.Arguments = '"' + (Join-Path $dir 'crew_context.py') + '" --harness ' + $Harness
  $psi.UseShellExecute = $false
  $psi.RedirectStandardInput = $true
  $proc = [System.Diagnostics.Process]::Start($psi)
  $proc.StandardInput.BaseStream.Write($stdinBytes, 0, $stdinBytes.Length)
  $proc.StandardInput.BaseStream.Flush()
  $proc.StandardInput.Close()
  $proc.WaitForExit()
} catch {
  [Console]::Error.WriteLine("crew context: python could not be launched - no context this event")
} finally {
  [Console]::OutputEncoding = $prevConsoleEncoding
  $OutputEncoding = $prevOutputEncodingVar
  $env:PYTHONUTF8 = $prevPythonUtf8
  $env:PYTHONIOENCODING = $prevPythonIoEncoding
}
exit 0
