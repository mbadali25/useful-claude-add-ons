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
  $crewPythonDeadline = [System.Diagnostics.Stopwatch]::StartNew()
  foreach ($name in @('python3', 'python', 'py')) {
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
      if ($crewPythonDeadline.Elapsed.TotalSeconds -ge 8) {
        $script:CrewPythonMemoDone = $true
        $script:CrewPythonMemoResult = ''
        return ''
      }
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
        if (-not $proc.WaitForExit(3000)) {
          try {
            $proc.Kill($true)
          } catch {
            try { & taskkill.exe /T /F /PID $proc.Id 2>&1 | Out-Null } catch { }
            try { $proc.Kill() } catch { }
          }
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

function Test-CrewEventClaim([string]$Hook, [byte[]]$Payload) {
  # BYTE-FOR-BYTE in notify.ps1 and handoff-write.ps1, asserted by
  # tests/test_flavour_windows_direction.py. $null ONLY when event_claim.py
  # exits 10: the bash twin has this exact event. Otherwise a string, and
  # this flavour emits: a claim token to hand to Complete-CrewEventClaim once
  # the emission succeeded, or '' when there is nothing to report back. Every
  # failure to decide -- no python, a launch error, a timeout -- emits,
  # because a duplicate is the safe side of this. The 10s bound covers the
  # longest wait event_claim.py makes for a twin's "sent" (its grace, <= 5s).
  if (-not $Payload -or $Payload.Length -eq 0) { return '' }
  $claimPy = Resolve-CrewPython
  if (-not $claimPy) { return '' }
  try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $claimPy
    $psi.Arguments = '"' + (Join-Path $PSScriptRoot 'event_claim.py') + '" ' + $Hook + ' . ps1'
    $psi.WorkingDirectory = (Get-Location).Path
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $proc.StandardInput.BaseStream.Write($Payload, 0, $Payload.Length)
    $proc.StandardInput.BaseStream.Flush()
    $proc.StandardInput.Close()
    if (-not $proc.WaitForExit(10000)) {
      try { $proc.Kill() } catch { }
      return ''
    }
    if ($proc.ExitCode -eq 10) { return $null }
    if ($proc.ExitCode -ne 0 -or -not $outTask.Wait(1000)) { return '' }
    return ($outTask.Result.Trim() + '|' + $claimPy)
  } catch {
    return ''
  }
}

function Complete-CrewEventClaim([string]$Claim) {
  # BYTE-FOR-BYTE in notify.ps1 and handoff-write.ps1. Reports "sent" for a
  # claim Test-CrewEventClaim returned, so the twin stops waiting for it.
  # Best effort: failing here costs at most a duplicate from the twin.
  $parts = $Claim -split '\|', 2
  if ($parts.Count -lt 2 -or -not $parts[0] -or -not $parts[1]) { return }
  try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $parts[1]
    $psi.Arguments = '"' + (Join-Path $PSScriptRoot 'event_claim.py') + '" --sent "' + $parts[0] + '"'
    $psi.UseShellExecute = $false
    $proc = [System.Diagnostics.Process]::Start($psi)
    if (-not $proc.WaitForExit(10000)) { try { $proc.Kill() } catch { } }
  } catch { }
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
$claim = Test-CrewEventClaim 'handoff-write' $stdinBytes
if ($null -eq $claim) { exit 0 }

$trigger = if ($d.trigger) { $d.trigger } else { "auto" }
New-Item -ItemType Directory -Path ".crew/transcripts", ".work" -Force | Out-Null

# Whether either write below actually landed. Codex r1 finding 2 (parity
# with handoff-write.sh): this used to mark the claim "sent" unconditionally,
# so a write that silently failed (a bad handoffPath, a full disk) suppressed
# the bash twin's retry -- the twin sees "sent", stands down, and the
# handoff is lost for good. A failure here must leave the claim unmarked so
# the twin (or a later run of this same flavour) can still take over and
# try again.
$failed = $false
if ($d.transcript_path -and (Test-Path $d.transcript_path)) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $dest = ".crew/transcripts/$stamp-$trigger.jsonl"
  Copy-Item $d.transcript_path $dest -ErrorAction SilentlyContinue
  if (-not (Test-Path $dest)) { $failed = $true }
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
if (Test-Path $path) {
  if (-not $failed) { Complete-CrewEventClaim $claim }
  exit 0
}

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

Set-Content -Path $path -Value $lines -Encoding UTF8 -ErrorAction SilentlyContinue
if (-not (Test-Path $path)) { $failed = $true }
if (-not $failed) { Complete-CrewEventClaim $claim }
exit 0
