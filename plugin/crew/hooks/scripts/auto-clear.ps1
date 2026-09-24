# Native-Windows twin of auto-clear.sh: sends "/clear" to the terminal that owns
# this session, once this session's handoff note is written and verified.
# Opt-in per machine; off by default.
#
# ## What this does NOT do
#
# It does not clear the conversation. A hook runs as a child process and cannot
# reset its parent's state - that part of the crew-context skill is still true.
# What it does is drive the TERMINAL, typing `/clear` at the prompt the way a
# human would. Different mechanism, different failure mode, and the reason this
# can work at all.
#
# ## What has to be true before it types anything
#
# The same rules as crew_autocycle.py, carried natively so this flavour needs no
# python to refuse. Every one is a refusal:
#
#   1. The MACHINE opted in: context.autoClear.enabled is true in
#      ~/.claude/crew/config.json. A repo may switch it off, never on.
#   2. This session asked for a wrap-up (.crew/.handoff-requested-<session>)
#      and the reading behind it was trustworthy. The zero-byte marker behind
#      the Windows low-context /clear is exactly the case this refuses.
#   3. The handoff was written after that request, is not a stub, and is not
#      PreCompact's automatic skeleton.
#   4. The target window is UNIQUELY identified: the one window owned by the
#      nearest ancestor of this hook, or -- only when that finds nothing -- the
#      one window whose title contains windowTitle. Zero or several: refuse.
#   5. At send time, after the delay, that exact window handle has focus.
#
# If you run Claude Code inside a tmux pane in WSL, use auto-clear.sh instead.
#
# ## Usage
#
#   pwsh -File auto-clear.ps1 -Session ID           # apply the conditions, then send
#   pwsh -File auto-clear.ps1 -Session ID -DryRun   # print the plan, send nothing
#   pwsh -File auto-clear.ps1 -Force                # skip the handoff conditions
param(
  [switch]$DryRun,
  [switch]$Force,
  [string]$Session = "",
  [string]$Root = ""
)

# Native Windows only, and this check is not cosmetic. The send path is
# System.Windows.Forms.SendKeys against a Win32 foreground window: on Linux or
# macOS pwsh there is no such window, so without this the script would claim
# the one-per-session attempt, report "sent", and deliver nothing. The TEST is
# `$env:OS`, not `$IsWindows`: `$IsWindows` does not exist in Windows
# PowerShell 5.1, so `-not $IsWindows` is $true there and this would stand
# down on the one platform it exists for.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$where = if ($Root) { $Root } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $where -ErrorAction SilentlyContinue
if (-not (Test-Path ".crew/config.json")) { exit 0 }

$log = ".crew/.autoclear.log"

function Write-CrewAutoClearNote([string]$Message) {
  # A Stop hook's stderr is invisible on exit 0, so the log is the only place
  # anybody can find out why nothing happened.
  if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force | Out-Null }
  $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
  Add-Content -Path $log -Value "$stamp`t$Message" -Encoding utf8 -ErrorAction SilentlyContinue
  [Console]::Error.WriteLine("autoclear: $Message")
}

function Stop-CrewAutoClear([string]$Reason) {
  Write-CrewAutoClearNote "refusing - $Reason"
  exit 0
}

function Read-CrewJsonFile([string]$Path) {
  try {
    $parsed = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    if ($parsed -is [System.Management.Automation.PSCustomObject]) { return $parsed }
  } catch { }
  return $null
}

function Get-CrewChild($Node, [string]$Name) {
  if ($null -eq $Node -or -not ($Node -is [System.Management.Automation.PSCustomObject])) { return $null }
  if (-not $Node.PSObject.Properties[$Name]) { return $null }
  return $Node.$Name
}

# `-is [bool]`, never `-eq $true`: PowerShell coerces the right side to the
# left's type, so the STRING "true" -eq $true is $true. Hand-edited config
# saying "true" means someone was confused, not yes.
function Test-CrewTrue($Value) { return ($Value -is [bool]) -and $Value }
function Test-CrewFalse($Value) { return ($Value -is [bool]) -and -not $Value }

$repoCfg    = Read-CrewJsonFile ".crew/config.json"
$userHome   = [Environment]::GetFolderPath('UserProfile')
$globalCfg  = Read-CrewJsonFile (Join-Path $userHome ".claude/crew/config.json")
$repoAuto   = Get-CrewChild (Get-CrewChild $repoCfg "context") "autoClear"
$globalAuto = Get-CrewChild (Get-CrewChild $globalCfg "context") "autoClear"

# Off is checked FIRST and silently: a machine that has not opted in must not
# even get a log file out of this.
$enabled = (Test-CrewTrue (Get-CrewChild $globalAuto "enabled")) -and
           -not (Test-CrewFalse (Get-CrewChild $repoAuto "enabled"))
if (-not $enabled) { exit 0 }

# onlyRepos / onlySessions NARROW the machine opt-in, and are read from the
# machine file ONLY -- a repo's copy is never consulted, because a narrowing a
# repo could write for itself would be a widening. Absent or null: no
# narrowing. Present: this repo and/or session must be listed; an empty list,
# or a value that is not a list, arms nothing. Silent like "not opted in".
# Same rules as crew_autocycle.in_scope / normalise_repo_path.
function Resolve-CrewRealPath([string]$Path) {
  # Component by component, so a symlinked PARENT resolves the way python's
  # realpath does, not just a link at the leaf. Works on Windows PowerShell
  # 5.1 (`.Target`) and 7 (`.LinkTarget`).
  $full = [System.IO.Path]::GetFullPath($Path)
  $root = [System.IO.Path]::GetPathRoot($full)
  $cur = $root
  foreach ($part in $full.Substring($root.Length).Split([char[]]@('\', '/'), [StringSplitOptions]::RemoveEmptyEntries)) {
    $next = Join-Path $cur $part
    for ($hop = 0; $hop -lt 8; $hop++) {
      $item = Get-Item -LiteralPath $next -Force -ErrorAction SilentlyContinue
      if ($null -eq $item) { break }
      $link = $null
      if ($item.PSObject.Properties['LinkTarget']) { $link = $item.LinkTarget }
      elseif ($item.PSObject.Properties['Target']) { $link = @($item.Target)[0] }
      if (-not $link) { break }
      if ([System.IO.Path]::IsPathRooted($link)) { $next = [System.IO.Path]::GetFullPath($link) }
      else { $next = [System.IO.Path]::GetFullPath((Join-Path $cur $link)) }
    }
    $cur = $next
  }
  return $cur
}

function ConvertTo-CrewScopePath($Path) {
  if (-not ($Path -is [string]) -or -not $Path.Trim()) { return "" }
  $text = $Path.Trim()
  if ($text.StartsWith("~")) { $text = $userHome + $text.Substring(1) }
  $text = $text.Replace('\', '/')
  $native = [System.IO.Path]::DirectorySeparatorChar -eq '\'
  if ($native) {
    $text = [regex]::Replace($text, '^/([A-Za-z])(?=/|$)', '$1:')
    if ($text -match '^[A-Za-z]:$') { $text += "/" }
    if ($text -notmatch '^([A-Za-z]:/|//)') { return "" }
  } elseif (-not $text.StartsWith("/")) {
    return ""
  }
  try { $text = (Resolve-CrewRealPath $text).Replace('\', '/') } catch { }
  $text = $text.TrimEnd('/')
  if (-not $text) { $text = "/" }
  if ($text -match '^[A-Za-z]:$') { $text += "/" }
  # Case-folded: this flavour runs on Windows only, whose paths are.
  return $text.ToLowerInvariant()
}

function Get-CrewScopeList($Node, [string]$Name) {
  # $null: not narrowing. Otherwise the string entries -- a present value that
  # is not a list narrows to nothing, never to "no narrowing".
  if ($null -eq $Node -or -not $Node.PSObject.Properties[$Name]) { return $null }
  $value = $Node.$Name
  if ($null -eq $value) { return $null }
  if (-not ($value -is [System.Array])) { return ,@() }
  return ,@($value | Where-Object { $_ -is [string] })
}

$onlyRepos = Get-CrewScopeList $globalAuto "onlyRepos"
if ($null -ne $onlyRepos) {
  $here = ConvertTo-CrewScopePath (Get-Location).Path
  $listed = @($onlyRepos | ForEach-Object { ConvertTo-CrewScopePath $_ } | Where-Object { $_ })
  if (-not $here -or $listed -notcontains $here) { exit 0 }
}
$onlySessions = Get-CrewScopeList $globalAuto "onlySessions"
if ($null -ne $onlySessions) {
  # -ccontains: a session id is case-sensitive, as the marker check is.
  if (-not $Session -or -not ($onlySessions -ccontains $Session)) { exit 0 }
}

function Get-CrewAutoClearValue([string]$Key, $Default) {
  $value = Get-CrewChild $repoAuto $Key
  if ($null -eq $value) { $value = Get-CrewChild $globalAuto $Key }
  if ($null -eq $value) { return $Default }
  return $value
}

function Get-CrewAutoClearInt($Value, [int]$Default) {
  if ($null -eq $Value -or $Value -is [bool]) { return $Default }
  try { return [int]$Value } catch { return $Default }
}

$method      = [string](Get-CrewAutoClearValue "method" "auto")
$delay       = Get-CrewAutoClearInt (Get-CrewAutoClearValue "delaySeconds" 3) 3
$command     = [string](Get-CrewAutoClearValue "command" "/clear")
$windowTitle = [string](Get-CrewAutoClearValue "windowTitle" "")
$minLines    = Get-CrewAutoClearInt (Get-CrewAutoClearValue "minHandoffLines" 5) 5
$handoffRel  = [string](Get-CrewChild (Get-CrewChild $repoCfg "context") "handoffPath")
if (-not $handoffRel) { $handoffRel = ".work/HANDOFF.md" }

# Same key rule as context-watch.{sh,ps1} and crew_autocycle.session_key.
$sessionKey = [regex]::Replace($Session, '[^A-Za-z0-9_-]', '_')
if ($sessionKey.Length -gt 100) { $sessionKey = $sessionKey.Substring(0, 100) }
if (-not $sessionKey) { $sessionKey = "nosession" }
$sentMarker = ".crew/.autoclear-sent-$sessionKey"

if (-not $Force) {
  if (-not $Session) { Stop-CrewAutoClear "no session id, so no way to tell whose handoff this is" }
  $markerPath = ".crew/.handoff-requested-$sessionKey"
  if (-not (Test-Path -LiteralPath $markerPath)) { Stop-CrewAutoClear "no wrap-up was requested in this session" }
  $marker = Read-CrewJsonFile $markerPath
  if ($null -eq $marker) {
    Stop-CrewAutoClear "the wrap-up marker is empty or not JSON, so the context reading behind it is unknown"
  }
  # -cne: PowerShell's -ne is case-insensitive, and a session id is not.
  if ([string](Get-CrewChild $marker "session_id") -cne $Session) {
    Stop-CrewAutoClear "the wrap-up marker records a different session"
  }
  if (-not (Test-CrewTrue (Get-CrewChild $marker "trusted"))) {
    $why = [string](Get-CrewChild $marker "why"); if (-not $why) { $why = "unknown" }
    Stop-CrewAutoClear "the context reading behind the wrap-up was not trustworthy ($why) - a low or unknown reading never clears"
  }
  $requested = Get-CrewChild $marker "requested_at"
  if ($null -eq $requested -or $requested -is [bool] -or -not ($requested -is [ValueType])) {
    Stop-CrewAutoClear "the wrap-up marker has no request time"
  }
  $base = (Get-Location).Path
  $handoffFull = [System.IO.Path]::GetFullPath((Join-Path $base $handoffRel))
  $sep = [System.IO.Path]::DirectorySeparatorChar
  if (-not $handoffFull.StartsWith($base.TrimEnd($sep) + $sep, [StringComparison]::OrdinalIgnoreCase)) {
    Stop-CrewAutoClear "handoffPath points outside the repository"
  }
  if (-not (Test-Path -LiteralPath $handoffFull)) { Stop-CrewAutoClear "$handoffRel has not been written" }
  $written = ([DateTimeOffset](Get-Item -LiteralPath $handoffFull).LastWriteTimeUtc).ToUnixTimeMilliseconds() / 1000.0
  if ($written -le [double]$requested) { Stop-CrewAutoClear "$handoffRel predates this session's wrap-up request" }
  $text = Get-Content -LiteralPath $handoffFull -Raw -ErrorAction SilentlyContinue
  if ($text -and $text.Contains("UNKNOWN - this skeleton was written automatically")) {
    Stop-CrewAutoClear "$handoffRel is the automatic PreCompact skeleton, not a handoff"
  }
  $lines = @(($text -split "`r?`n") | Where-Object { $_ -match '\S' }).Count
  if ($lines -lt $minLines) {
    Stop-CrewAutoClear "$handoffRel has $lines non-blank lines, minHandoffLines is $minLines"
  }
}

# --- Resolve a method ------------------------------------------------------
switch ($method) {
  "windows" { }
  "auto"    { }
  "none"    { Stop-CrewAutoClear "method none" }
  "tmux"    { Stop-CrewAutoClear "method tmux is auto-clear.sh's job; this is the native-Windows flavour. Both are registered, so the bash one will have handled it" }
  default   { Stop-CrewAutoClear "method '$method' is not supported here (windows, none, auto)" }
}

# --- Resolve the target window ---------------------------------------------
#
# CREW_AUTOCLEAR_WINDOW_STUB names a JSON list of {id, pid, title} that
# replaces the real window system -- the suite's only way in, so no test ever
# enumerates, let alone types into, a real window.
function Get-CrewWindows {
  if ($env:CREW_AUTOCLEAR_WINDOW_STUB) {
    $stub = Get-Content -LiteralPath $env:CREW_AUTOCLEAR_WINDOW_STUB -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    return @($stub | ForEach-Object { [pscustomobject]@{ Id = [long]$_.id; Pid = [int]$_.pid; Title = [string]$_.title } })
  }
  if (-not ("CrewAC.Enum" -as [type])) {
    Add-Type -TypeDefinition @"
using System; using System.Collections.Generic; using System.Runtime.InteropServices; using System.Text;
namespace CrewAC {
  public static class Enum {
    delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] static extern int GetWindowThreadProcessId(IntPtr hWnd, out int pid);
    public static List<string> List() {
      var found = new List<string>();
      EnumWindows((h, l) => {
        if (!IsWindowVisible(h)) return true;
        var sb = new StringBuilder(1024); GetWindowText(h, sb, 1024);
        if (sb.Length == 0) return true;
        int pid; GetWindowThreadProcessId(h, out pid);
        found.Add(h.ToInt64() + "\t" + pid + "\t" + sb.ToString());
        return true;
      }, IntPtr.Zero);
      return found;
    }
  }
}
"@
  }
  return @([CrewAC.Enum]::List() | ForEach-Object {
    $f = $_ -split "`t", 3
    [pscustomobject]@{ Id = [long]$f[0]; Pid = [int]$f[1]; Title = $f[2] }
  })
}

function Get-CrewParentId([int]$Id) {
  # `.Parent` is PowerShell 6+. Windows PowerShell 5.1 has no such property,
  # so fall back to WMI through its type accelerator (no cmdlet, so nothing
  # the Linux static check cannot resolve).
  try {
    $parent = (Get-Process -Id $Id -ErrorAction Stop).Parent
    if ($parent) { return [int]$parent.Id }
  } catch { }
  try { return [int]([wmi]"Win32_Process.Handle='$Id'").ParentProcessId } catch { return 0 }
}

$ancestors = @()
$walk = $PID
while ($walk -gt 0 -and $ancestors.Count -lt 16 -and $ancestors -notcontains $walk) {
  $ancestors += $walk
  $walk = Get-CrewParentId $walk
}

try { $windows = @(Get-CrewWindows) } catch { Stop-CrewAutoClear "cannot list windows: $($_.Exception.Message)" }

$needle = $windowTitle.ToLowerInvariant()
$target = $null; $how = ""
foreach ($ancestor in $ancestors) {
  $owned = @($windows | Where-Object { $_.Pid -eq $ancestor })
  if ($owned.Count -eq 0) { continue }
  if ($needle) {
    $owned = @($owned | Where-Object { $_.Title.ToLowerInvariant().Contains($needle) })
    if ($owned.Count -eq 0) {
      Stop-CrewAutoClear "the terminal that owns this session (pid $ancestor) has no window whose title contains '$windowTitle'"
    }
  }
  if ($owned.Count -gt 1) {
    Stop-CrewAutoClear "the terminal that owns this session (pid $ancestor) has $($owned.Count) windows and nothing narrows them to one - set context.autoClear.windowTitle"
  }
  $target = $owned[0]; $how = if ($needle) { "owner pid + title" } else { "owner pid" }
  break
}
if ($null -eq $target) {
  if (-not $needle) {
    Stop-CrewAutoClear "no window belongs to any ancestor of this hook, and no context.autoClear.windowTitle is set to fall back on"
  }
  $hits = @($windows | Where-Object { $_.Title.ToLowerInvariant().Contains($needle) })
  if ($hits.Count -ne 1) {
    Stop-CrewAutoClear "$($hits.Count) windows have a title containing '$windowTitle' - refusing to guess which one is this session"
  }
  $target = $hits[0]; $how = "title fallback"
}
$label = "$($target.Title) [window $($target.Id), pid $($target.Pid), $how]"

if ($DryRun) {
  # Deterministic, and the same shape auto-clear.sh prints. The suite reads it.
  Write-Output "autoclear: would send"
  Write-Output "  method: windows"
  Write-Output "  target: $label"
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
param([long]$Hwnd, [string]$Text, [int]$Delay)
# Delete self first: every exit below is an early return, and a temp script left
# in %TEMP% on each of them accumulates one file per session forever. The file
# is already open and read by the interpreter, so removing it now is safe.
try { Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue } catch { }
Start-Sleep -Seconds $Delay
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Namespace CrewAC -Name Win -MemberDefinition @"
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
"@
# Checked HERE, not in the parent: focus at send time is the only focus that
# matters. The exact window handle resolved above, not a title: if the user
# alt-tabbed during the delay, this is what stops "/clear" being typed into
# their mail client.
if ([CrewAC.Win]::GetForegroundWindow().ToInt64() -ne $Hwnd) { exit 0 }
# SendKeys treats + ^ % ~ ( ) { } [ ] as syntax. Escape them so a configured
# command is sent as itself.
$escaped = [regex]::Replace($Text, '[+^%~(){}\[\]]', { param($m) "{$($m.Value)}" })
[System.Windows.Forms.SendKeys]::SendWait($escaped)
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
'@

# A test suite must never drive the real keyboard. Checked HERE, immediately
# before the spawn, and NOT earlier: every decision above is something the
# suite legitimately exercises. Only the keystroke is suppressed. See the .sh
# twin.
if ($env:CREW_AUTOCLEAR_INHIBIT) {
  Write-CrewAutoClearNote "would have sent, but CREW_AUTOCLEAR_INHIBIT is set"
  exit 0
}

$childPath = Join-Path ([System.IO.Path]::GetTempPath()) ("crew-autoclear-" + [guid]::NewGuid().ToString("N") + ".ps1")
Set-Content -Path $childPath -Value $child -Encoding utf8

$exe = (Get-Process -Id $PID).Path
if (-not $exe) { $exe = "pwsh" }
# Hidden so it does not steal the focus the child is about to check for.
Start-Process -FilePath $exe -WindowStyle Hidden -ArgumentList @(
  "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
  "-File", $childPath, "-Hwnd", "$($target.Id)", "-Text", $command,
  "-Delay", "$delay"
) | Out-Null

Write-CrewAutoClearNote "sent - method windows, target $label, command '$command' in ${delay}s (only if that window still has focus)"
exit 0
