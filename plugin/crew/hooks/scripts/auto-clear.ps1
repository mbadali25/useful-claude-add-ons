# EXPERIMENTAL. Native-Windows twin of auto-clear.sh: sends "/clear" to the
# terminal that owns this session, once the handoff note is written.
#
# ## What this does NOT do
#
# It does not clear the conversation. A hook runs as a child process and cannot
# reset its parent's state - that part of the crew-context skill is still true.
# What it does is drive the TERMINAL, typing `/clear` at the prompt the way a
# human would. Different mechanism, different failure mode, and the reason this
# can work at all.
#
# ## Why Windows is the riskier half
#
# There is no tmux pane to address. SendKeys goes to whatever window has focus,
# full stop - so if you alt-tab during the delay, "/clear" is typed into
# whatever you alt-tabbed to. That is not a theoretical concern; it is the
# normal consequence.
#
# Three things keep it honest:
#
#   1. context.autoClear.windowTitle is REQUIRED. No title, no send.
#   2. The title is checked in the CHILD, immediately before sending - focus at
#      send time is what matters, not focus when the hook ran.
#   3. Nothing is sent if the foreground window's title does not match.
#
# If you run Claude Code inside a tmux pane in WSL, use auto-clear.sh instead.
# It targets a pane by id and never touches focus, which is strictly better.
#
# ## Usage
#
#   pwsh -File auto-clear.ps1                 # apply the conditions, then send
#   pwsh -File auto-clear.ps1 -DryRun         # print the plan, send nothing
#   pwsh -File auto-clear.ps1 -Force          # skip the handoff conditions
param(
  [switch]$DryRun,
  [switch]$Force
)

# Native Windows only, and this check is not cosmetic. The send path is
# System.Windows.Forms.SendKeys against a Win32 foreground window: on Linux or
# macOS pwsh the Add-Type fails and there is no foreground window to check, so
# without this the script runs every condition, claims the one-per-session
# attempt, reports "sent", and delivers nothing. auto-clear.sh is the flavour
# for those platforms - it is registered too, and tmux there is strictly better
# than anything this file could do.
if (-not $IsWindows) { exit 0 }

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $root -ErrorAction SilentlyContinue
if (-not (Test-Path ".crew/config.json")) { exit 0 }

$log = ".crew/.autoclear.log"
$sentMarker = ".crew/.autoclear-sent"

function Write-CrewAutoClearNote([string]$Message) {
  # A Stop hook's stderr is invisible on exit 0, so the log is the only place
  # anybody can find out why nothing happened.
  if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force | Out-Null }
  $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
  Add-Content -Path $log -Value "$stamp`t$Message" -Encoding utf8 -ErrorAction SilentlyContinue
  [Console]::Error.WriteLine("autoclear: $Message")
}

try { $cfg = (Get-Content .crew/config.json -Raw | ConvertFrom-Json).context }
catch { exit 0 }
if ($null -eq $cfg) { exit 0 }
$a = $cfg.autoClear
# Enabled is checked FIRST and silently: a repo that has not opted in must not
# even get a log file out of this.
if ($null -eq $a -or $a.enabled -ne $true) { exit 0 }

function Get-CrewAutoClearInt($Value, [int]$Default) {
  if ($null -eq $Value -or $Value -is [bool]) { return $Default }
  try { return [int]$Value } catch { return $Default }
}

$method      = if ($a.method) { [string]$a.method } else { "auto" }
$delay       = Get-CrewAutoClearInt $a.delaySeconds 3
$command     = if ($a.command) { [string]$a.command } else { "/clear" }
$windowTitle = if ($a.windowTitle) { [string]$a.windowTitle } else { "" }
$minLines    = Get-CrewAutoClearInt $a.minHandoffLines 5
$handoff     = if ($cfg.handoffPath) { [string]$cfg.handoffPath } else { ".work/HANDOFF.md" }

if (-not $Force) {
  # 1. The nag must have happened. context-watch writes this when it asks for
  #    the handoff; SessionStart clears it.
  if (-not (Test-Path ".crew/.handoff-requested")) { exit 0 }

  # 2. The handoff must exist, be NEWER than the request, and be more than a
  #    stub. Clearing on a three-line placeholder loses the session's work and
  #    leaves a note that says "continue the work".
  if (-not (Test-Path $handoff)) { exit 0 }
  $requested = (Get-Item ".crew/.handoff-requested").LastWriteTimeUtc
  if ((Get-Item $handoff).LastWriteTimeUtc -le $requested) { exit 0 }
  $lines = @(Get-Content $handoff -ErrorAction SilentlyContinue |
             Where-Object { $_ -match '\S' }).Count
  if ($lines -lt $minLines) {
    Write-CrewAutoClearNote "refusing - $handoff has $lines non-blank lines, minHandoffLines is $minLines"
    exit 0
  }

  # The once-per-session claim is NOT taken here. It is taken immediately before
  # the send, after every refusal path has had its say - otherwise a
  # misconfiguration burns the session's one attempt, and correcting the config
  # mid-session appears to change nothing.
}

# --- Resolve a method ------------------------------------------------------
#
# This script has exactly one: SendKeys against a title-matched foreground
# window. tmux is auto-clear.sh's business, and saying so is more useful than
# silently doing nothing on a machine where tmux was what the user wanted.
switch ($method) {
  "none"    { exit 0 }
  "windows" { }
  "auto"    { }
  "tmux"    {
    Write-CrewAutoClearNote "refusing - method tmux is auto-clear.sh's job; this is the native-Windows flavour. Both are registered, so the bash one will have handled it"
    exit 0
  }
  default {
    Write-CrewAutoClearNote "refusing - method '$method' is not supported here (windows, none, auto)"
    exit 0
  }
}

if (-not $windowTitle) {
  Write-CrewAutoClearNote "refusing - SendKeys types into whatever has focus, so context.autoClear.windowTitle is required. Set it to a substring or regex matching the terminal's title"
  exit 0
}

if ($DryRun) {
  # Deterministic, and the same shape auto-clear.sh prints. The suite reads it.
  Write-Output "autoclear: would send"
  Write-Output "  method: windows"
  Write-Output "  target: $windowTitle"
  Write-Output "  command: $command"
  Write-Output "  delay: ${delay}s"
  exit 0
}

# --- Send, after the turn has actually ended -------------------------------
#
# The delay and the detach are both load-bearing. This runs from a Stop hook and
# the prompt does not exist yet - Claude Code is still finishing the turn, so
# sending now types into nothing. The work goes to a detached child that sleeps
# first, and this process exits 0 immediately so the turn can end.
# Claim the one-per-session attempt HERE, not with the conditions above: every
# refusal path has now had its say, so a misconfiguration no longer burns the
# session's only attempt and correcting the config mid-session actually retries.
# Atomic because both flavours run on the same Stop, and two /clear keystrokes
# means the second lands in the fresh session. Absolute path: [System.IO.File]
# resolves a relative one against [Environment]::CurrentDirectory, which
# Set-Location does not update.
if (-not $Force) {
  try {
    $claim = [System.IO.File]::Open(
      (Join-Path (Get-Location).Path $sentMarker), [System.IO.FileMode]::CreateNew)
    $claim.Close()
  } catch { exit 0 }
}

$child = @'
param([string]$Title, [string]$Text, [int]$Delay)
# Delete self first: every exit below is an early return, and a temp script left
# in %TEMP% on each of them accumulates one file per session forever. The file
# is already open and read by the interpreter, so removing it now is safe.
try { Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue } catch { }
Start-Sleep -Seconds $Delay
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Namespace CrewAC -Name Win -MemberDefinition @"
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
[DllImport("user32.dll", CharSet=System.Runtime.InteropServices.CharSet.Unicode)]
public static extern int GetWindowText(System.IntPtr hWnd, System.Text.StringBuilder text, int count);
"@
$sb = New-Object System.Text.StringBuilder 1024
[void][CrewAC.Win]::GetWindowText([CrewAC.Win]::GetForegroundWindow(), $sb, 1024)
$front = $sb.ToString()
# Checked HERE, not in the parent: focus at send time is the only focus that
# matters. If the user alt-tabbed during the delay, this is what stops "/clear"
# being typed into their mail client.
if ($front -notmatch $Title) { exit 0 }
# SendKeys treats + ^ % ~ ( ) { } [ ] as syntax. Escape them so a configured
# command is sent as itself.
$escaped = [regex]::Replace($Text, '[+^%~(){}\[\]]', { param($m) "{$($m.Value)}" })
[System.Windows.Forms.SendKeys]::SendWait($escaped)
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
'@

$childPath = Join-Path ([System.IO.Path]::GetTempPath()) ("crew-autoclear-" + [guid]::NewGuid().ToString("N") + ".ps1")
Set-Content -Path $childPath -Value $child -Encoding utf8

$exe = (Get-Process -Id $PID).Path
if (-not $exe) { $exe = "pwsh" }
# Hidden so it does not steal the focus the child is about to check for.
Start-Process -FilePath $exe -WindowStyle Hidden -ArgumentList @(
  "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
  "-File", $childPath, "-Title", $windowTitle, "-Text", $command,
  "-Delay", "$delay"
) | Out-Null

Write-CrewAutoClearNote "sent - method windows, target '$windowTitle', command '$command' in ${delay}s (only if that window still has focus)"
exit 0
