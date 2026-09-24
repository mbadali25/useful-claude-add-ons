# Outbound-only notifier (native Windows). Mirrors notify.sh.
# Never reads from chat, never accepts instructions.
# Usage: notify.ps1 <event> <one-line message>
#   events: phase | gate | review | waiting | done
param(
  [string]$Event = "info",
  [string]$Msg = ""
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

# BYTE-FOR-BYTE the resolver in role-write-guard.ps1, asserted by the tests.
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
  $crewPythonDeadline = [System.Diagnostics.Stopwatch]::StartNew()
  foreach ($name in @('python3', 'python', 'py')) {
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
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

function Format-CrewProcessArgument([string]$Value) {
  # BYTE-FOR-BYTE in notify.ps1 and handoff-write.ps1. The Win32 argv
  # quoting rule (the one CommandLineToArgvW documents): used only as the
  # fallback below, on a runtime whose ProcessStartInfo has no ArgumentList
  # to build the command line correctly for us. A value with none of the
  # characters that need quoting is passed through untouched; otherwise it
  # is wrapped in quotes, with each run of backslashes doubled only where it
  # immediately precedes a literal quote -- its own, or the closing one this
  # function adds.
  if ($Value -and $Value -notmatch '[\s"]') { return $Value }
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.Append('"')
  $backslashes = 0
  foreach ($ch in $Value.ToCharArray()) {
    if ($ch -eq '\') { $backslashes++; continue }
    if ($ch -eq '"') {
      [void]$sb.Append('\' * (2 * $backslashes + 1))
      [void]$sb.Append('"')
      $backslashes = 0
      continue
    }
    if ($backslashes -gt 0) { [void]$sb.Append('\' * $backslashes); $backslashes = 0 }
    [void]$sb.Append($ch)
  }
  if ($backslashes -gt 0) { [void]$sb.Append('\' * (2 * $backslashes)) }
  [void]$sb.Append('"')
  return $sb.ToString()
}

function Set-CrewProcessArguments([System.Diagnostics.ProcessStartInfo]$Psi, [string[]]$ArgList) {
  # BYTE-FOR-BYTE in notify.ps1 and handoff-write.ps1. Replaces building
  # $psi.Arguments by string concatenation -- fragile even where nothing on
  # this path is attacker-controlled today (a hex nonce, a path under our
  # own claims directory): one stray space or quote in an argument used to
  # need hand escaping at every call site, and a call site that forgot was
  # invisible until it broke. ArgumentList exists on this runtime's
  # ProcessStartInfo everywhere .NET builds argv for us; the manual fallback
  # is only for a PowerShell 5.1 host old enough to predate it.
  if ($Psi.PSObject.Properties['ArgumentList']) {
    foreach ($a in $ArgList) { $Psi.ArgumentList.Add($a) }
  } else {
    $Psi.Arguments = (($ArgList | ForEach-Object { Format-CrewProcessArgument $_ }) -join ' ')
  }
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
    Set-CrewProcessArguments $psi @((Join-Path $PSScriptRoot 'event_claim.py'), $Hook, '.', 'ps1')
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
    Set-CrewProcessArguments $psi @((Join-Path $PSScriptRoot 'event_claim.py'), '--sent', $parts[0])
    $psi.UseShellExecute = $false
    $proc = [System.Diagnostics.Process]::Start($psi)
    if (-not $proc.WaitForExit(10000)) { try { $proc.Kill() } catch { } }
  } catch { }
}

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $root -ErrorAction SilentlyContinue
if (-not (Test-Path .crew/config.json)) { exit 0 }

# No hook_once claim here on purpose: Notification can fire many times per
# session, and a duplicate ping is a safe failure -- a suppressed one is not.
# The per-EVENT claim below is a different thing: on Windows both flavours
# of this hook run for one Notification, and event_claim.py lets exactly one
# of them send it (keyed on the payload, so the next Notification is new).
# Called in-process by context-watch.ps1, whose stdin is already read: an
# empty payload is not a hook event and always sends.

$cfg = (Get-Content .crew/config.json -Raw | ConvertFrom-Json).notify
if ($null -eq $cfg) { exit 0 }
$provider = $cfg.provider
if (-not $provider -or $provider -eq "none") { exit 0 }
$events = $cfg.events
if ($events) {
  $eventList = $events -split ","
  if ($eventList -notcontains $Event) { exit 0 }
}

# Raw BYTES, not [Console]::In.ReadToEnd(): event_claim.py hashes the payload,
# and the bash twin hands it the bytes as received.
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$stdinBytes = $memStream.ToArray()
$claim = Test-CrewEventClaim 'notify' $stdinBytes
if ($null -eq $claim) { exit 0 }

$repo = Split-Path -Leaf (git rev-parse --show-toplevel 2>$null)
if (-not $repo) { $repo = Split-Path -Leaf (Get-Location) }
$branch = (git branch --show-current 2>$null)

# One line. No diffs, no findings text, no ticket bodies, no secrets.
# A chat channel is a less controlled place than the repo; keep payloads dull.
$msgTrunc = if ($Msg.Length -gt 280) { $Msg.Substring(0, 280) } else { $Msg }
$repoPart = if ($branch) { "$repo/$branch" } else { $repo }
$text = "[$repoPart] ${Event}: $msgTrunc"

switch ($provider) {
  "teams" {
    $urlEnv = $cfg.urlEnv
    $url = if ($urlEnv) { [Environment]::GetEnvironmentVariable($urlEnv) } else { $null }
    if (-not $url) { [Console]::Error.WriteLine("notify: `$$urlEnv not set"); Complete-CrewEventClaim $claim; exit 0 }
    $body = @{
      type = "message"
      attachments = @(@{
        contentType = "application/vnd.microsoft.card.adaptive"
        content = @{
          type = "AdaptiveCard"
          version = "1.4"
          body = @(@{ type = "TextBlock"; text = $text; wrap = $true })
        }
      })
    } | ConvertTo-Json -Depth 10
    try {
      Invoke-RestMethod -Uri $url -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 10 | Out-Null
      Complete-CrewEventClaim $claim
    } catch {}
  }
  "telegram" {
    $tokEnv = $cfg.tokenEnv
    $tok = if ($tokEnv) { [Environment]::GetEnvironmentVariable($tokEnv) } else { $null }
    $chat = $cfg.chatId
    if (-not $tok -or -not $chat) { [Console]::Error.WriteLine("notify: telegram token or chatId missing"); Complete-CrewEventClaim $claim; exit 0 }
    $disableNotif = if ($Event -eq "waiting") { "false" } else { "true" }
    $tgBody = @{
      chat_id = $chat
      text = $text
      disable_notification = $disableNotif
    }
    try {
      Invoke-RestMethod -Uri "https://api.telegram.org/bot$tok/sendMessage" -Method Post -Body $tgBody -TimeoutSec 10 | Out-Null
      Complete-CrewEventClaim $claim
    } catch {}
  }
  default {
    # Parity with notify.sh: an unrecognised provider used to fall through
    # this switch with no arm running at all, so Complete-CrewEventClaim was
    # never called -- the claim stayed "claimed" forever, the bash twin
    # waited out the grace on every notification and then took over,
    # hitting the same unknown provider and orphaning another generation.
    # Nothing can be sent for an unknown provider, so release the claim.
    [Console]::Error.WriteLine("notify: unknown provider '$provider'")
    Complete-CrewEventClaim $claim
  }
}
exit 0
