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
if (-not (Test-CrewEventClaim 'notify' $stdinBytes)) { exit 0 }

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
    if (-not $url) { [Console]::Error.WriteLine("notify: `$$urlEnv not set"); exit 0 }
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
    } catch {}
  }
  "telegram" {
    $tokEnv = $cfg.tokenEnv
    $tok = if ($tokEnv) { [Environment]::GetEnvironmentVariable($tokEnv) } else { $null }
    $chat = $cfg.chatId
    if (-not $tok -or -not $chat) { [Console]::Error.WriteLine("notify: telegram token or chatId missing"); exit 0 }
    $disableNotif = if ($Event -eq "waiting") { "false" } else { "true" }
    $tgBody = @{
      chat_id = $chat
      text = $text
      disable_notification = $disableNotif
    }
    try {
      Invoke-RestMethod -Uri "https://api.telegram.org/bot$tok/sendMessage" -Method Post -Body $tgBody -TimeoutSec 10 | Out-Null
    } catch {}
  }
}
exit 0
