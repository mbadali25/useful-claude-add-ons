# Native-Windows twin of auto-clear.sh: sends "/clear" to the terminal that owns
# this session, once this session's handoff note is written and verified.
# Opt-in per machine; off by default.
#
# ## What this does NOT do
#
# It does not clear the conversation. A hook runs as a child process and cannot
# reset its parent's state - that part of the crew-context skill is still true.
# What it does, for method `sendkeys`, is drive the TERMINAL, typing `/clear`
# at the prompt the way a human would. Different mechanism, different failure
# mode, and the reason that one can work at all.
#
# `method: "notify"` -- the default `auto` resolves to on native Windows --
# does neither. It never identifies a window and never types anything: it
# prints a systemMessage saying the handoff is written and verified and it is
# safe to run the configured command yourself. This is an OWNER DECISION, not
# a capability gap -- `sendkeys` still works and is still here, opt in to it
# by name. Nothing in this script may say "cleared" or "compacted" unless a
# keystroke was actually sent and its delivery verified; the notify path says
# only what it did.
#
# ## What has to be true before `sendkeys` types anything
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
#   5. At send time, after the delay, that exact window handle has focus, AND
#      -- when that window is Windows Terminal -- it still has exactly one
#      tab. Both are checked in the DETACHED CHILD, not the parent: the
#      parent's own tab check runs before Start-Sleep, and the user can
#      switch tabs inside the SAME window during the delay without the
#      window handle ever changing, so only a check made at send time,
#      after the delay, in the process that is about to type, can catch it.
#
# `notify` needs none of #4/#5 -- it identifies no window, so it is never
# refused for lack of one.
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

# Gated on the `.crew/` DIRECTORY, not on `.crew/config.json`. OWNER DECISION
# (crew 1.0 F4, reversing the previous file-based gate -- see CONFIG.md sec
# 14): `context.autoClear` is a MACHINE-global switch (`crew_config.py`), so
# it must work in any crew repo without a per-repo config of its own -- and
# "crew repo" is read the same way both senders now agree: `.crew/` exists.
# `context-watch.sh`/`.ps1` gate their OWN handover to this script the same
# way, while their OWN context-window warnings keep requiring a real
# `.crew/config.json` underneath -- that is a separate question, unaffected
# here. A repo with NO `.crew/` at all -- a fresh checkout, since the
# directory itself is git-ignored in this very repo -- must stay completely
# silent and must NEVER get `.crew/` or `.crew/.autoclear.log` created as a
# side effect of this hook running, so this check runs before
# Write-CrewAutoClearNote ever gets a chance to call Add-Content.
if (-not (Test-Path ".crew" -PathType Container)) { exit 0 }

$log = ".crew/.autoclear.log"

function Write-CrewAutoClearNote([string]$Message) {
  # A Stop hook's stderr is invisible on exit 0, so the log is the only place
  # anybody can find out why nothing happened. `.crew` is guaranteed to exist
  # by the gate above, which runs before this function is ever called -- no
  # New-Item needed, and none may run here.
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
# NOT [Environment]::GetFolderPath('UserProfile'): on native Windows that
# resolves the profile path via the Shell API from the user's token/registry
# and ignores an overridden $env:USERPROFILE entirely, unlike its Linux/.NET
# Core implementation, which does read $env:HOME. That asymmetry is invisible
# on a Linux-pwsh test run (the fixture's HOME override works there) and
# silent on native Windows: every test in this suite redirects HOME/
# USERPROFILE to an isolated fixture directory specifically so no case reads
# the developer's real ~/.claude/crew/config.json, and this API bypassed
# that, reading the REAL machine config instead on the one platform this
# script actually runs on. Matches cloud-guard.ps1's own
# `Test-CloudGuardArmed`, the existing convention in this directory.
$userHome   = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
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
# Total symlink SUBSTITUTIONS allowed across the whole walk -- not per
# component, and not the old per-component "8" this replaces. That bound
# resolved only a chain hanging off ONE original path component; it never
# re-checked a component that came from a SUBSTITUTED target (see the
# function's own comment), so raising it alone would not have been enough.
# 40 mirrors the common POSIX ELOOP bound (Linux's MAXSYMLINKS): generous
# for any real chain, and a fixed, known-terminating stand-in for the cycle
# detection crew_autocycle.py gets for free from `os.path.realpath`.
$script:_CREW_SYMLINK_HOP_LIMIT = 40

function Split-CrewRawComponents([string]$Text) {
  # Raw split only -- '.' and '..' tokens are NOT collapsed here. The walking
  # loop below resolves each one individually, in order, against whatever it
  # has actually reached so far, which is what lets a '..' that crosses a
  # symlinked component apply AFTER that component is resolved rather than
  # before. See "review round 3" below for why that distinction is the fix.
  return @($Text.Split([char[]]@('\', '/'), [StringSplitOptions]::RemoveEmptyEntries))
}

function Join-CrewParts([string]$RootPath, $Parts) {
  $joined = $RootPath
  foreach ($part in $Parts) { $joined = Join-Path $joined $part }
  return $joined
}

function Resolve-CrewLinkRoot([string]$LinkNorm) {
  # Classifies a symlink target (backslashes already replaced with slashes)
  # by REGEX, not [System.IO.Path]::GetPathRoot: that call's answer for a
  # drive letter or a UNC share depends on the ACTUAL OS the .NET runtime is
  # on -- Linux/macOS recognise neither -- so it cannot be driven from a
  # non-Windows test and cannot be reasoned about the same way on both.
  #
  # Review (Codex FIX|auto-clear.ps1:211): GetPathRoot answered a BARE "/"
  # (one character -- truthy in PowerShell) for a drive-root-relative target
  # like `\repo`, which the old code then treated as "already fully
  # qualified" and used AS the new root, throwing the alias's own drive away
  # -- `C:\alias -> \repo` resolved to `\repo`, not `C:\repo`. A target is
  # fully qualified only with a REAL drive letter or a UNC share; a single
  # leading slash is rooted, but only relative to WHATEVER drive the link
  # making the reference lives on.
  #
  # Returns $null for an ordinary relative target (no root at all --
  # unchanged by this fix). Otherwise a hashtable: `Remainder` is always the
  # component text still to walk; `Rootless` true means "keep the caller's
  # OWN current root, discard only what was resolved under it so far" (the
  # drive-root-relative case); `Rootless` false means `Root` names the new
  # root outright (a real drive letter, or a UNC share, which stays UNC).
  $uncMatch = [regex]::Match($LinkNorm, '^//[^/]+/[^/]+/?')
  if ($uncMatch.Success) {
    # The MATCHED length, not the (possibly longer, always-trailing-slash)
    # normalised root's length: a target that IS exactly the share with no
    # trailing slash ("//srv/share", nothing after it) matched without one,
    # and Substring on the normalised root's length would run past the end
    # of $LinkNorm.
    $root = $uncMatch.Value.TrimEnd('/') + '/'
    return @{ Root = $root; Remainder = $LinkNorm.Substring($uncMatch.Value.Length); Rootless = $false }
  }
  if ($LinkNorm -match '^[A-Za-z]:/') {
    $root = $LinkNorm.Substring(0, 3)
    return @{ Root = $root; Remainder = $LinkNorm.Substring($root.Length); Rootless = $false }
  }
  if ($LinkNorm.StartsWith('/')) {
    return @{ Root = $null; Remainder = $LinkNorm.Substring(1); Rootless = $true }
  }
  return $null
}

function Resolve-CrewRealPath([string]$Path) {
  # POSIX-style, one path component at a time. When a component is itself a
  # symlink, its OWN target components go back at the FRONT of the queue of
  # components still to walk, rather than the target string being spliced
  # in and left unexamined. That is what lets a symlinked component INSIDE
  # a substituted target resolve too -- `A\link -> ..\alias\inner\repo`
  # where `alias` is itself a symlink to `B`: the old version only re-chased
  # a symlink chain hanging off the ORIGINAL component ("link"), so "alias"
  # inside the substituted target was walked as an ordinary directory name
  # and the listed path stayed under `alias` instead of resolving to `B`.
  # Works on Windows PowerShell 5.1 (`.Target`) and 7 (`.LinkTarget`).
  #
  # Review round 3 (crew-1.0-r4-scope): a substituted target's raw components
  # used to be taken from `[System.IO.Path]::GetFullPath(...)`, which
  # collapses '..' PURELY LEXICALLY -- before anything asks whether the
  # component it is cancelling against is itself a symlink. `A\link ->
  # ..\alias\..\target`, with `alias` a symlink to `B\nested`, collapsed
  # "alias\.." to nothing and produced the lexical sibling `...\target`
  # instead of the real `...\B\target`, because `alias` was never actually
  # looked up. Fixed by never calling GetFullPath on anything that still has
  # unresolved components in it: every root is found with GetPathRoot (a
  # purely syntactic prefix that does not require -- or perform -- any '..'
  # collapse), and every remaining component, INCLUDING '.' and '..', is
  # pushed through the same per-component queue below, which resolves '..'
  # by popping the LAST COMPONENT THIS WALK HAS ACTUALLY RESOLVED SO FAR
  # (`$resolved`), never a string still waiting to be looked up.
  #
  # Returns $null, never a partially-resolved path, once
  # $_CREW_SYMLINK_HOP_LIMIT substitutions have happened without
  # terminating -- a cycle, or a chain too long to be legitimate. The
  # caller must treat $null as "this entry does not resolve" and fail it
  # CLOSED (normalise to "", which cannot match anything real), not fall
  # back to whatever partial value the walk had reached.
  $root = [System.IO.Path]::GetPathRoot($Path)
  $queue = New-Object System.Collections.Generic.List[string]
  if ($root) {
    foreach ($p in (Split-CrewRawComponents $Path.Substring($root.Length))) { $queue.Add($p) }
  } else {
    # Relative input: rooted against the current directory, which is taken
    # as already resolved -- the same assumption `os.path.realpath` makes
    # against `getcwd()`.
    $cwd = [System.IO.Directory]::GetCurrentDirectory()
    $root = [System.IO.Path]::GetPathRoot($cwd)
    foreach ($p in (Split-CrewRawComponents $cwd.Substring($root.Length))) { $queue.Add($p) }
    foreach ($p in (Split-CrewRawComponents $Path)) { $queue.Add($p) }
  }
  # Components of the CURRENT root this walk has confirmed real, in order --
  # never a string, so a '..' pop can never "un-collapse" something GetFullPath
  # already lexically cancelled.
  $resolved = New-Object System.Collections.Generic.List[string]
  $hops = 0
  while ($queue.Count -gt 0) {
    $part = $queue[0]
    $queue.RemoveAt(0)
    if ($part -eq '.') { continue }
    if ($part -eq '..') {
      if ($resolved.Count -gt 0) { $resolved.RemoveAt($resolved.Count - 1) }
      continue
    }
    $cur = Join-CrewParts $root $resolved
    $next = Join-Path $cur $part
    $item = Get-Item -LiteralPath $next -Force -ErrorAction SilentlyContinue
    $link = $null
    if ($null -ne $item) {
      if ($item.PSObject.Properties['LinkTarget']) { $link = $item.LinkTarget }
      elseif ($item.PSObject.Properties['Target']) { $link = @($item.Target)[0] }
    }
    if (-not $link) { $resolved.Add($part); continue }
    $hops++
    if ($hops -gt $script:_CREW_SYMLINK_HOP_LIMIT) { return $null }
    # THIS hop's parent -- $root/$resolved as they stand right now, i.e.
    # before $part (the symlink itself) is added -- not any earlier hop's,
    # so a chained relative symlink resolves each hop against the link that
    # names it.
    $linkNorm = $link.Replace('\', '/')
    $classified = Resolve-CrewLinkRoot $linkNorm
    $insertAt = 0
    if ($null -eq $classified) {
      foreach ($p in (Split-CrewRawComponents $linkNorm)) {
        $queue.Insert($insertAt, $p)
        $insertAt++
      }
    } else {
      # Rootless (drive-root-relative, e.g. `\repo`): $root is left exactly
      # as this hop's parent stood -- computed above, before $part (the
      # symlink itself) was added -- so a target with no drive/share of its
      # own inherits whichever one the link making the reference lives on,
      # rather than losing it. Otherwise Root names a real drive letter or a
      # UNC share, which fully replaces it.
      if (-not $classified.Rootless) { $root = $classified.Root }
      $resolved.Clear()
      foreach ($p in (Split-CrewRawComponents $classified.Remainder)) {
        $queue.Insert($insertAt, $p)
        $insertAt++
      }
    }
  }
  return Join-CrewParts $root $resolved
}

function ConvertTo-CrewScopePath($Path) {
  # Leading/trailing whitespace in $Path is significant and is NOT stripped
  # below -- it is a legal POSIX filename character, and trimming it
  # collapsed two distinct entries (a repo path and that same path plus a
  # trailing space) into one, letting a listed repo whose name happens to
  # end in a space authorise an unlisted, space-free repo of the same name.
  # Only whitespace-ONLY input is treated as absent (matches
  # crew_autocycle.normalise_repo_path's `not path.strip()` check).
  if (-not ($Path -is [string]) -or -not $Path.Trim()) { return "" }
  $text = $Path
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
  # $null (the symlink hop bound was exceeded -- a cycle, or a chain too
  # long to be legitimate) fails CLOSED: "" cannot match a real path, so
  # this entry narrows to nothing rather than being compared as whatever
  # partial value the walk had reached when it gave up.
  try { $resolved = Resolve-CrewRealPath $text } catch { $resolved = $text }
  if ($null -eq $resolved) { return "" }
  $text = $resolved.Replace('\', '/')
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

# Silent-default guard: an unknown collapsing into the default value with no
# record of it happened for real -- a config carrying `delay` (not
# `delaySeconds`) or a `delaySeconds` neither valid JSON int nor a numeric
# string reads as "nothing configured" and silently gets the compiled
# default, indistinguishable from an operator who genuinely wanted 3s. Two
# checks, both AFTER the enabled/onlyRepos/onlySessions gates above (an
# opted-out machine must still get no log file at all): every KEY in either
# layer that this resolver does not recognise, and `delaySeconds` present but
# not usable as a number. Both name the effective value actually used.
# `Get-CrewAutoClearValue ... $null` is the probe: it returns $null only when
# NEITHER layer set the key at all, so a $null result here means "absent",
# not "misconfigured" -- absence is the ordinary, silent default path.
$_crewAutoClearKnownKeys = @('method', 'windowTitle', 'command', 'delaySeconds',
                             'minHandoffLines', 'enabled', 'onlyRepos', 'onlySessions',
                             'unsafeFocus')
foreach ($layer in @(@{Label = 'repo'; Node = $repoAuto}, @{Label = 'machine'; Node = $globalAuto})) {
  if ($null -eq $layer.Node) { continue }
  foreach ($prop in $layer.Node.PSObject.Properties.Name) {
    if ($_crewAutoClearKnownKeys -notcontains $prop) {
      Write-CrewAutoClearNote ("context.autoClear.$prop in the $($layer.Label) layer is not a " +
        "recognised key and is ignored")
    }
  }
}
$_crewDelayRaw = Get-CrewAutoClearValue "delaySeconds" $null
if ($null -ne $_crewDelayRaw) {
  $_crewDelayOk = $false
  if (-not ($_crewDelayRaw -is [bool])) {
    try { [void][int]$_crewDelayRaw; $_crewDelayOk = $true } catch { }
  }
  if (-not $_crewDelayOk) {
    Write-CrewAutoClearNote ("context.autoClear.delaySeconds is set to '$_crewDelayRaw', not a " +
      "usable number - using the default $delay")
  }
}

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
#
# OWNER DECISION: `auto` resolves to `notify`, never to `sendkeys` -- typing
# into a window this hook found itself is a risk `auto` does not get to
# accept on your behalf. `sendkeys` (the SendKeys mechanism below, the
# renamed "windows" literal) is opt-in only: request it by name.
switch ($method) {
  "sendkeys" { }
  "notify"   { }
  "auto"     { $method = "notify" }
  "none"     { Stop-CrewAutoClear "method none" }
  "tmux"     { Stop-CrewAutoClear "method tmux is auto-clear.sh's job; this is the native-Windows flavour. Both are registered, so the bash one will have handled it" }
  default    { Stop-CrewAutoClear "method '$method' is not supported here (auto, notify, sendkeys, none)" }
}

if ($method -eq "notify") {
  # Types nothing anywhere, so none of the window-identification or focus
  # rules below apply: no window to find, no focus to keep, no delay to
  # wait out (there is no turn-ending race to lose, because nothing types).
  # Printed and logged synchronously, from THIS process, never a detached
  # child. Never claims the handoff was cleared or compacted -- only that
  # it is safe to run the configured command yourself.
  if ($DryRun) {
    Write-Output "autoclear: would send"
    Write-Output "  method: notify"
    Write-Output "  command: $command"
    # Never a number here: notify types nothing, so there is no wait to
    # report, and printing the configured delaySeconds (or a hardcoded 0)
    # would contradict context.autoClear.delaySeconds for no reason a reader
    # could infer from the figure alone. Same text as the .sh twin.
    Write-Output "  delay: n/a (notify sends no keystroke)"
    exit 0
  }
  if (-not $Force) {
    try {
      $claim = [System.IO.File]::Open(
        (Join-Path (Get-Location).Path $sentMarker), [System.IO.FileMode]::CreateNew)
      $claim.Close()
    } catch { exit 0 }
  }
  $msg = "crew: handoff written and verified for this session - it is safe to run $command now (auto-clear will not type it for you)."
  Write-Output (@{ systemMessage = $msg } | ConvertTo-Json -Compress)
  Write-CrewAutoClearNote "sent - method notify, command '$command'"
  exit 0
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

# `sendkeys` may still not be safe to use even once a window is uniquely
# identified: Windows Terminal hosts every tab in ONE window, so the
# foreground-window check above passes even when a DIFFERENT tab than this
# session's is the one showing. The decision is factored in two: a PURE
# function (below) that is unit-tested on Linux, and the real UI Automation
# probe that feeds it, which is NOT -- there is no live Windows Terminal
# window or UIAutomationClient assembly on the platform this suite runs on.
# "Could not tell" (UIA unavailable, an exception, zero tab elements found)
# must decline exactly like a KNOWN multi-tab window with no provable
# selection -- never folded into "safe to send" (the same rule CLAUDE.md
# states for a probe that can fail).
function Get-CrewSendKeysTabDecision([bool]$UiaAvailable, $TabCount, [bool]$SelectedMatches) {
  if (-not $UiaAvailable) {
    return @{ Decision = "decline"; Reason = (
      "cannot verify the active tab - Windows Terminal hosts multiple tabs in one window and " +
      "UI Automation could not be used to confirm which one is active") }
  }
  if ($null -eq $TabCount -or $TabCount -lt 1) {
    return @{ Decision = "decline"; Reason = (
      "cannot verify the active tab - Windows Terminal hosts multiple tabs in one window and " +
      "no tab elements could be found to confirm which one is active") }
  }
  if ($TabCount -eq 1) {
    # A window with exactly one tab has that tab selected by definition --
    # this is the ONLY case this function may ever return "send".
    return @{ Decision = "send"; Reason = "" }
  }
  # Multi-tab can NEVER be proven safe, however confidently $SelectedMatches
  # reads: tab names are shell-set text, there is no tab-to-pid mapping, and
  # a wrong guess types into a tab that is not this session's (measured
  # desktop: a 4-tab window whose tabs included two sessions under standing
  # orders not to disturb). $SelectedMatches plays no part in the DECISION --
  # decided 2026-09-24, narrower than an earlier draft of this function that
  # sent on a proven selection -- but it is still surfaced in the decline
  # Reason as diagnostic detail, so a log reader can tell "a tab's title
  # matched and was selected, and we STILL declined" from "nothing matched
  # at all" without re-deriving it from the UIA probe.
  $selectedNote = if ($SelectedMatches) {
    "a tab's title matched windowTitle and read as selected"
  } else {
    "no tab's title was both matched and selected"
  }
  return @{ Decision = "decline"; Reason = (
    "cannot verify the active tab - Windows Terminal has $TabCount tabs and the active one " +
    "could not be proven to be this session's ($selectedNote)") }
}

# Real IO against a live Windows Terminal window -- NOT unit-tested on Linux,
# for the reason above. Any failure (the assembly missing, FromHandle
# returning nothing, any other exception) reports UiaAvailable=$false rather
# than letting an exception propagate and crash the hook mid-decision.
# `Title` proves the selected tab is THIS session's only when it is the
# UNIQUE title match among all tabs found -- two tabs matching windowTitle
# singles out neither, whichever of them happens to be selected.
function Get-CrewWindowsTerminalTabState([IntPtr]$Hwnd, [string]$Title) {
  try {
    Add-Type -AssemblyName UIAutomationClient -ErrorAction Stop
    Add-Type -AssemblyName UIAutomationTypes -ErrorAction Stop
    $elem = [System.Windows.Automation.AutomationElement]::FromHandle($Hwnd)
    if ($null -eq $elem) {
      return @{ UiaAvailable = $false; TabCount = 0; SelectedMatches = $false }
    }
    $cond = New-Object System.Windows.Automation.PropertyCondition(
      [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
      [System.Windows.Automation.ControlType]::TabItem)
    $tabs = $elem.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
    $needle = if ($Title) { $Title.ToLowerInvariant() } else { "" }
    $titleMatches = 0
    $selectedName = $null
    foreach ($tab in $tabs) {
      $name = [string]$tab.Current.Name
      if ($needle -and $name.ToLowerInvariant().Contains($needle)) { $titleMatches++ }
      $pattern = $null
      if ($tab.TryGetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern) -and
          ([System.Windows.Automation.SelectionItemPattern]$pattern).Current.IsSelected) {
        $selectedName = $name
      }
    }
    $selectedMatches = $needle -and $titleMatches -eq 1 -and $selectedName -and
                       $selectedName.ToLowerInvariant().Contains($needle)
    return @{ UiaAvailable = $true; TabCount = $tabs.Count; SelectedMatches = [bool]$selectedMatches }
  } catch {
    return @{ UiaAvailable = $false; TabCount = 0; SelectedMatches = $false }
  }
}

# Review (Codex FIX|auto-clear.ps1:~582): a failure to determine the owning
# process (Get-Process throwing, e.g. the window's pid already exited) used
# to be swallowed by the empty catch and leave $ownerProcessName as "" --
# which is not "WindowsTerminal", so the check below read that as PROOF the
# owner is safe and let sendkeys proceed against an UNKNOWN safety predicate.
# Unknown must decline, exactly like a known-Windows-Terminal owner with no
# provable single tab, not fall through to the permissive branch. $ownerKnown
# distinguishes "confirmed some other process" from "could not confirm
# anything" so the two failure reasons are not conflated in the log a human
# reads afterward.
$ownerProcessName = $null
$ownerKnown = $false
try {
  $ownerProcessName = (Get-Process -Id $target.Pid -ErrorAction Stop).ProcessName
  $ownerKnown = $true
} catch { }

# Carried to the detached child below so IT can re-run the SAME tab-safety
# question at send time, after the delay -- this process's own answer, made
# before Start-Sleep, is only ever a pre-check. The window's owner does not
# change during the delay, so re-deriving it in the child would only add a
# second real IO call with no different answer; what CAN change underneath
# an unchanged window handle is which tab is showing, which is exactly what
# the child re-asks Windows Terminal about.
$isWindowsTerminal = $ownerKnown -and $ownerProcessName -eq "WindowsTerminal"

$declineReason = $null
if (-not $ownerKnown) {
  $declineReason = "cannot determine the process that owns window pid $($target.Pid) - an unknown owner must decline, not assume it is safe to type into"
} elseif ($isWindowsTerminal) {
  $tabState = Get-CrewWindowsTerminalTabState -Hwnd $target.Id -Title $windowTitle
  $decision = Get-CrewSendKeysTabDecision -UiaAvailable $tabState.UiaAvailable `
                -TabCount $tabState.TabCount -SelectedMatches $tabState.SelectedMatches
  if ($decision.Decision -ne "send") { $declineReason = $decision.Reason }
}
# else: a non-Windows-Terminal console host (conhost) has no tabs to
# disambiguate -- falls straight through to sendkeys below, unchanged.

if ($declineReason) {
  if ($DryRun) {
    Write-Output "autoclear: would decline sendkeys - $declineReason"
    Write-Output "  falling back to notify: would say it is safe to run $command yourself"
    exit 0
  }
  if (-not $Force) {
    try {
      $claim = [System.IO.File]::Open(
        (Join-Path (Get-Location).Path $sentMarker), [System.IO.FileMode]::CreateNew)
      $claim.Close()
    } catch { exit 0 }
  }
  $msg = "crew: declined to type into $label ($declineReason) - it is safe to run $command yourself."
  Write-Output (@{ systemMessage = $msg } | ConvertTo-Json -Compress)
  Write-CrewAutoClearNote "declined sendkeys - $declineReason - sent notify instead"
  exit 0
}

if ($DryRun) {
  # Deterministic, and the same shape auto-clear.sh prints. The suite reads it.
  Write-Output "autoclear: would send"
  Write-Output "  method: sendkeys"
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

$sendRoot = (Get-Location).Path
$child = @'
param([long]$Hwnd, [string]$Text, [int]$Delay, [string]$Root, [string]$WindowTitle = "",
      [bool]$IsWindowsTerminal = $true)
# IsWindowsTerminal defaults to $true, not $false: an argv that somehow omits
# it must recheck rather than skip the recheck -- the unknown collapsing into
# the PERMISSIVE value is exactly the bug this file exists to fix. The real
# parent below always passes it explicitly; this default only matters to a
# caller that does not.
# Delete self first: every exit below is an early return, and a temp script left
# in %TEMP% on each of them accumulates one file per session forever. The file
# is already open and read by the interpreter, so removing it now is safe.
try { Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue } catch { }
function Write-CrewChildNote([string]$Message) {
  # The parent has already exited by the time this runs, so its own
  # Write-CrewAutoClearNote is gone -- a Stop hook's stderr is invisible on
  # exit 0 regardless, and this is well past that exit. The log is the only
  # channel left, and never claims a keystroke was sent unless it was.
  try {
    $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
    Add-Content -Path (Join-Path $Root ".crew/.autoclear.log") -Value "$stamp`t$Message" `
      -Encoding utf8 -ErrorAction SilentlyContinue
  } catch { }
}
# Child-local copies of the parent's Get-CrewWindowsTerminalTabState and
# Get-CrewSendKeysTabDecision, byte-for-byte -- this script is a separate
# process (spawned via Start-Process into its own temp file) and has no
# access to functions defined in the parent's memory, the same reason
# Write-CrewChildNote above is a copy of Write-CrewAutoClearNote rather than
# a shared call. Needed here, not just in the parent, because the parent's
# own tab check runs BEFORE Start-Sleep: a tab switch inside the same
# Windows Terminal window during the delay leaves the window HANDLE
# unchanged, so only a check made in this process, after the sleep, can
# catch it.
function Get-CrewWindowsTerminalTabState([IntPtr]$Hwnd, [string]$Title) {
  try {
    Add-Type -AssemblyName UIAutomationClient -ErrorAction Stop
    Add-Type -AssemblyName UIAutomationTypes -ErrorAction Stop
    $elem = [System.Windows.Automation.AutomationElement]::FromHandle($Hwnd)
    if ($null -eq $elem) {
      return @{ UiaAvailable = $false; TabCount = 0; SelectedMatches = $false }
    }
    $cond = New-Object System.Windows.Automation.PropertyCondition(
      [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
      [System.Windows.Automation.ControlType]::TabItem)
    $tabs = $elem.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
    $needle = if ($Title) { $Title.ToLowerInvariant() } else { "" }
    $titleMatches = 0
    $selectedName = $null
    foreach ($tab in $tabs) {
      $name = [string]$tab.Current.Name
      if ($needle -and $name.ToLowerInvariant().Contains($needle)) { $titleMatches++ }
      $pattern = $null
      if ($tab.TryGetCurrentPattern(
            [System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern) -and
          ([System.Windows.Automation.SelectionItemPattern]$pattern).Current.IsSelected) {
        $selectedName = $name
      }
    }
    $selectedMatches = $needle -and $titleMatches -eq 1 -and $selectedName -and
                       $selectedName.ToLowerInvariant().Contains($needle)
    return @{ UiaAvailable = $true; TabCount = $tabs.Count; SelectedMatches = [bool]$selectedMatches }
  } catch {
    return @{ UiaAvailable = $false; TabCount = 0; SelectedMatches = $false }
  }
}
function Get-CrewSendKeysTabDecision([bool]$UiaAvailable, $TabCount, [bool]$SelectedMatches) {
  if (-not $UiaAvailable) {
    return @{ Decision = "decline"; Reason = (
      "cannot verify the active tab - Windows Terminal hosts multiple tabs in one window and " +
      "UI Automation could not be used to confirm which one is active") }
  }
  if ($null -eq $TabCount -or $TabCount -lt 1) {
    return @{ Decision = "decline"; Reason = (
      "cannot verify the active tab - Windows Terminal hosts multiple tabs in one window and " +
      "no tab elements could be found to confirm which one is active") }
  }
  if ($TabCount -eq 1) {
    # A window with exactly one tab has that tab selected by definition --
    # this is the ONLY case this function may ever return "send".
    return @{ Decision = "send"; Reason = "" }
  }
  # Multi-tab can NEVER be proven safe, however confidently $SelectedMatches
  # reads: tab names are shell-set text, there is no tab-to-pid mapping, and
  # a wrong guess types into a tab that is not this session's (measured
  # desktop: a 4-tab window whose tabs included two sessions under standing
  # orders not to disturb). $SelectedMatches plays no part in the DECISION --
  # decided 2026-09-24, narrower than an earlier draft of this function that
  # sent on a proven selection -- but it is still surfaced in the decline
  # Reason as diagnostic detail, so a log reader can tell "a tab's title
  # matched and was selected, and we STILL declined" from "nothing matched
  # at all" without re-deriving it from the UIA probe.
  $selectedNote = if ($SelectedMatches) {
    "a tab's title matched windowTitle and read as selected"
  } else {
    "no tab's title was both matched and selected"
  }
  return @{ Decision = "decline"; Reason = (
    "cannot verify the active tab - Windows Terminal has $TabCount tabs and the active one " +
    "could not be proven to be this session's ($selectedNote)") }
}
# Wraps the two functions above into the single question this child needs
# answered: is it STILL safe to type, right now, into $Hwnd? A non-Windows-
# Terminal owner (or IsWindowsTerminal never proven true) has no tabs to
# disambiguate, so it always answers "send" -- same fallthrough as the
# parent's own conhost case.
function Get-CrewChildTabRecheck([IntPtr]$Hwnd, [string]$Title, [bool]$IsWindowsTerminal) {
  if (-not $IsWindowsTerminal) { return @{ Decision = "send"; Reason = "" } }
  $tabState = Get-CrewWindowsTerminalTabState -Hwnd $Hwnd -Title $Title
  return Get-CrewSendKeysTabDecision -UiaAvailable $tabState.UiaAvailable `
           -TabCount $tabState.TabCount -SelectedMatches $tabState.SelectedMatches
}
Start-Sleep -Seconds $Delay
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Namespace CrewAC -Name Win -MemberDefinition @"
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
"@
# Checked HERE, not in the parent: focus at send time is the only focus that
# matters. The exact window handle resolved above, not a title: if the user
# alt-tabbed during the delay, this is what stops "/clear" being typed into
# their mail client. Logged, not silent: "nothing happened" and "it worked"
# must not look the same in the one place anybody can check afterwards.
if ([CrewAC.Win]::GetForegroundWindow().ToInt64() -ne $Hwnd) {
  Write-CrewChildNote "declined sendkeys - the target window lost focus during the ${Delay}s delay, so nothing was typed - run $Text yourself"
  exit 0
}
# Re-run the SAME tab-count == 1 predicate the parent ran before Start-Sleep,
# immediately before typing -- the window handle above proves the FOCUSED
# window is still this session's Windows Terminal window, not which TAB in
# it is showing. A tab switch inside that window during the delay changes
# nothing GetForegroundWindow can see, so this is the only check left that
# can catch it. Decline exactly like the focus check: log, never type.
$recheck = Get-CrewChildTabRecheck -Hwnd $Hwnd -Title $WindowTitle -IsWindowsTerminal $IsWindowsTerminal
if ($recheck.Decision -ne "send") {
  Write-CrewChildNote "declined sendkeys - $($recheck.Reason), re-checked after the ${Delay}s delay - run $Text yourself"
  exit 0
}
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

# Review (Codex FIX|auto-clear.ps1:~691): `-ArgumentList` here is an ARRAY,
# but `Start-Process` does not quote its elements individually -- it joins
# them into ONE command-line string with plain spaces
# (`[string]::Join(" ", $ArgumentList)`, the documented behaviour on both
# Windows PowerShell 5.1 and 7). An element that itself contains a space --
# $sendRoot (a `-Root` under a "Program Files"-shaped path, or any repo
# checked out under a directory with a space in its name) or a
# non-default $command most commonly -- then SPLITS into two argv entries
# once the child process's own CommandLineToArgvW parses that joined
# string back apart, and the detached child sees a `-Root` value that is
# not the real root (or none at all, depending on where the split lands)
# and exits before it can send anything or write to the log -- silently,
# because by this point the PARENT has already exited 0 to end the turn.
# Quoting each element ourselves, the same way CommandLineToArgvW parses
# it back apart, is what keeps one array element as one argv entry.
function ConvertTo-CrewWin32Arg([string]$Arg) {
  # The MS-documented C runtime argv-quoting algorithm (the same one every
  # child process on Windows -- pwsh, cmd, a .NET Main(string[]) -- uses to
  # split its own command line back into arguments), applied unconditionally
  # rather than only when $Arg "looks like" it needs it: quoting a token with
  # no special characters is a no-op once CommandLineToArgvW strips the
  # quotes back off, so there is no case where doing it always is wrong, and
  # no conditional to get wrong either.
  $sb = New-Object System.Text.StringBuilder
  [void]$sb.Append('"')
  for ($i = 0; $i -lt $Arg.Length; $i++) {
    $backslashes = 0
    while ($i -lt $Arg.Length -and $Arg[$i] -eq '\') { $backslashes++; $i++ }
    if ($i -eq $Arg.Length) {
      # A run of backslashes immediately before the CLOSING quote this
      # function is about to append: each one must become two, or the
      # parser reads the last one as escaping our own closing quote.
      [void]$sb.Append('\' * ($backslashes * 2))
      break
    } elseif ($Arg[$i] -eq '"') {
      # A run of backslashes before a LITERAL quote character: each becomes
      # two (so they still mean literal backslashes), plus one more to
      # escape the quote itself.
      [void]$sb.Append('\' * ($backslashes * 2 + 1))
      [void]$sb.Append('"')
    } else {
      # An ordinary character: the backslashes before it were not escaping
      # anything and pass through unchanged.
      [void]$sb.Append('\' * $backslashes)
      [void]$sb.Append($Arg[$i])
    }
  }
  [void]$sb.Append('"')
  return $sb.ToString()
}

# Pulled out so the DELAY value handed to the detached child is checkable
# directly -- the exact argv entry, not how long the child takes to run --
# without spawning anything. Pure: only calls the already-pure
# ConvertTo-CrewWin32Arg above.
function Get-CrewSendKeysChildArgs([string]$ChildPath, [long]$Hwnd, [string]$Command,
                                    [int]$Delay, [string]$Root, [string]$WindowTitle = "",
                                    [bool]$IsWindowsTerminal = $true) {
  return @(
    "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-File", (ConvertTo-CrewWin32Arg $ChildPath), "-Hwnd", "$Hwnd",
    "-Text", (ConvertTo-CrewWin32Arg $Command),
    "-WindowTitle", (ConvertTo-CrewWin32Arg $WindowTitle),
    "-IsWindowsTerminal", "$IsWindowsTerminal",
    "-Delay", "$Delay", "-Root", (ConvertTo-CrewWin32Arg $Root)
  )
}

# Hidden so it does not steal the focus the child is about to check for.
Start-Process -FilePath $exe -WindowStyle Hidden -ArgumentList (Get-CrewSendKeysChildArgs `
  -ChildPath $childPath -Hwnd $target.Id -Command $command -Delay $delay -Root $sendRoot `
  -WindowTitle $windowTitle -IsWindowsTerminal $isWindowsTerminal) | Out-Null

Write-CrewAutoClearNote "sent - method sendkeys, target $label, command '$command' in ${delay}s (only if that window still has focus)"
exit 0
