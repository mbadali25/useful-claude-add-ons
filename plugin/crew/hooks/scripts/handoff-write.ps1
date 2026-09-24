# PreCompact hook (native Windows). Mirrors handoff-write.sh: snapshots the
# transcript and makes sure a handoff exists before compaction discards detail.

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

# BYTE-FOR-BYTE the resolver in role-write-guard.ps1, asserted by the tests.
function Resolve-CrewPython {
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
  # The probe is bounded: it runs to completion or is killed at 3s, with
  # stdout and stderr read asynchronously so a chatty candidate cannot fill a
  # pipe and hang. A candidate is accepted only when it exits 0, reports
  # Python 3 or later, and prints a sys.executable that exists as a file.
  # No `continue` inside try/catch: loop control across that boundary
  # differs between PowerShell versions, so the verdict is carried out in
  # $real and acted on after it.
  foreach ($name in @('python3', 'python', 'py')) {
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
      $real = $null
      try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $cmd.Source
        $psi.Arguments = '-c "import sys; sys.version_info[0] >= 3 or sys.exit(1); print(sys.executable)"'
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $null = $proc.StandardError.ReadToEndAsync()
        if (-not $proc.WaitForExit(3000)) {
          try { $proc.Kill() } catch { }
        } elseif ($proc.ExitCode -eq 0 -and $outTask.Wait(1000)) {
          $real = @(($outTask.Result -split "`r?`n") | Where-Object { $_.Trim() })[0]
        }
      } catch {
        $real = $null
      }
      if ($real) { $real = $real.ToString().Trim() }
      if (-not $real) { continue }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
      return $real
    }
  }
  return ''
}

function Test-CrewEventClaim([string]$Hook, [byte[]]$Payload) {
  # BYTE-FOR-BYTE in notify.ps1 and handoff-write.ps1, asserted by
  # tests/test_flavour_windows_direction.py. True means this flavour emits.
  # False ONLY when event_claim.py exits 10: the bash twin already emitted
  # this exact event. Every failure to decide -- no python, a launch error, a
  # timeout -- emits, because a duplicate is the safe side of this.
  if (-not $Payload -or $Payload.Length -eq 0) { return $true }
  $claimPy = Resolve-CrewPython
  if (-not $claimPy) { return $true }
  try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $claimPy
    $psi.Arguments = '"' + (Join-Path $PSScriptRoot 'event_claim.py') + '" ' + $Hook + ' .'
    $psi.WorkingDirectory = (Get-Location).Path
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $proc.StandardInput.BaseStream.Write($Payload, 0, $Payload.Length)
    $proc.StandardInput.BaseStream.Flush()
    $proc.StandardInput.Close()
    if (-not $proc.WaitForExit(10000)) {
      try { $proc.Kill() } catch { }
      return $true
    }
    return ($proc.ExitCode -ne 10)
  } catch {
    return $true
  }
}

# Raw BYTES, not [Console]::In.ReadToEnd(): event_claim.py hashes the payload,
# and the bash twin hands it the bytes as received.
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$stdinBytes = $memStream.ToArray()
$raw = [System.Text.Encoding]::UTF8.GetString($stdinBytes).TrimStart([char]0xFEFF)
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue
if (-not (Test-Path ".crew/config.json")) { exit 0 }

# No hook_once claim here on purpose: PreCompact can fire more than once per
# session, and both writes below are idempotent (the transcript copy is
# timestamped, the handoff skeleton only gets written if one doesn't already
# exist) -- duplication is safe, suppression of the only handoff is not.
#
# The per-EVENT claim is a different thing: on Windows both flavours run for
# ONE PreCompact, and "idempotent" held only when they did not overlap -- two
# transcript copies in one second race one name, and two skeleton writers can
# both see no handoff. event_claim.py lets exactly one flavour write for this
# event, keyed on the payload, so the next compaction is a new event.
if (-not (Test-CrewEventClaim 'handoff-write' $stdinBytes)) { exit 0 }

$trigger = if ($d.trigger) { $d.trigger } else { "auto" }
New-Item -ItemType Directory -Path ".crew/transcripts", ".work" -Force | Out-Null

if ($d.transcript_path -and (Test-Path $d.transcript_path)) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  Copy-Item $d.transcript_path ".crew/transcripts/$stamp-$trigger.jsonl" -ErrorAction SilentlyContinue
  $keep = 5
  try {
    $k = (Get-Content .crew/config.json -Raw | ConvertFrom-Json).context.keepTranscripts
    if ($k -is [int] -and $k -ge 0) { $keep = $k }
  } catch { }
  Get-ChildItem ".crew/transcripts/*.jsonl" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

$cfg  = Get-Content .crew/config.json -Raw | ConvertFrom-Json
$path = if ($cfg.context.handoffPath) { $cfg.context.handoffPath } else { ".work/HANDOFF.md" }
if (Test-Path $path) { exit 0 }

# If no handoff exists, write a factual skeleton from the repo, not from memory.
$branch = (git rev-parse --abbrev-ref HEAD 2>$null)
$head   = (git rev-parse --short HEAD 2>$null)
$lines  = New-Object System.Collections.Generic.List[string]
$lines.Add("# Handoff")
$lines.Add("written: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) (auto, at $trigger compact)")
$lines.Add("branch: $branch")
$lines.Add("head: $head")
$lines.Add("")
$lines.Add("## Changed files")
(git diff --name-only HEAD 2>$null)                  | Select-Object -First 30 | ForEach-Object { $lines.Add($_) }
(git ls-files --others --exclude-standard 2>$null)   | Select-Object -First 10 | ForEach-Object { $lines.Add($_) }
$lines.Add("")
$lines.Add("## Open tickets")
$open = if (Test-Path .work/INDEX.md) { Select-String -Path .work/INDEX.md -Pattern '\| open \|' | Select-Object -First 5 } else { $null }
if ($open) { $open | ForEach-Object { $lines.Add($_.Line) } } else { $lines.Add("(none recorded)") }
$lines.Add("")
$lines.Add("## Next action")
$lines.Add("UNKNOWN - this skeleton was written automatically at compaction.")
$lines.Add("Verify against the diff before continuing.")

Set-Content -Path $path -Value $lines -Encoding UTF8
exit 0
