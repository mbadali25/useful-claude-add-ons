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
#      PreCompact's automatic skeleton. With context.autoClear.wrapUp armed
#      (T-0017), the wrap-up's results are on disk too -- decided by
#      crew_autocycle.py wrapup-check, so this one needs a python.
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
#
# -Force skips the handoff conditions AND the T-0017 wrap-up check. It is for
# testing by hand only: hooks.json and context-watch.ps1 never pass it, and no
# repo or machine config key can turn it on.
#   pwsh -File auto-clear.ps1 -Resume -Session ID -Source clear -Python PY [-DryRun]
#
# `-Resume` (T-0013) is started by the context hook on SessionStart: it types
# T-0006's rendered resume prompt instead of /clear. Consent is `resume.auto`
# (decided in python, `crew_autocycle.py resume-plan --flavour ps1`, which is
# why the hook hands over -Python); the window, focus and tab rules below are
# the same ones, unchanged. It claims a per-handoff marker instead of the
# per-session one, records the run before spawning, and prints one
# `autoresume:` line for the hook. No probe exists here: the child's delay is
# a guess, and the focus and tab rechecks after it cover the wrong window,
# not an input box that is not ready yet.
param(
  [switch]$DryRun,
  [switch]$Force,
  [string]$Session = "",
  [string]$Root = "",
  [switch]$Resume,
  [string]$Source = "",
  [string]$Python = ""
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
  if ($Resume) {
    # The context hook names this line in the session's context.
    Write-CrewAutoClearNote "refusing - auto-resume: $Reason"
    Write-Output "autoresume: refused - $Reason"
    exit 0
  }
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
  #
  # REAL Windows only, never the flavour-guard seam: $env:OS -eq 'Windows_NT'
  # is also true in this suite's own fixtures, which run REAL pwsh on Linux
  # with that variable set to get past the guard at the top of this file --
  # their candidates are ordinary extensionless Linux shim scripts, valid
  # executables here, and gating on the seam would reject every one of them
  # and break the fixtures that exist to prove this resolver works. $IsWindows
  # (PowerShell 6+) reports the actual OS regardless of $env:OS; it does not
  # exist in Windows PowerShell 5.1, which never runs anywhere but Windows, so
  # its absence is itself a true answer.
  $crewPythonRealWindows = if (Test-Path variable:IsWindows) { $IsWindows } else { $true }
  # Only .exe/.com/.cmd/.bat (PATHEXT's launchable core) can be started
  # without going through shell association. An extensionless file --
  # anything else, including no extension at all -- CreateProcess cannot
  # launch directly, and reaching it here is the same failure mode this
  # probe's own bounded wait/kill exists to survive from a HUNG candidate,
  # not from one Windows cannot start in the first place. Skipped before
  # Process.Start is ever called, not caught after: a WindowsApps alias
  # already carries `.exe`, so it is untouched by this and still tried like
  # any other candidate, per the comment above.
  $crewPythonNativeExts = @('.exe', '.com', '.cmd', '.bat')
  $crewPythonDeadline = [System.Diagnostics.Stopwatch]::StartNew()
  foreach ($name in @('python3', 'python', 'py')) {
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
      if ($crewPythonRealWindows) {
        $crewPythonExt = [System.IO.Path]::GetExtension($cmd.Source)
        if ($crewPythonNativeExts -notcontains $crewPythonExt) {
          Write-Verbose "Resolve-CrewPython: skipping '$($cmd.Source)' - not natively launchable on Windows (extension '$crewPythonExt' outside .exe/.com/.cmd/.bat)"
          continue
        }
      }
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
        $psi.RedirectStandardInput = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        # Closed at once: the probe never reads stdin, and an OPEN inherited
        # stdin parks a child forever, which would make a healthy candidate
        # look dead and get it rejected.
        $proc.StandardInput.Close()
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
          # An empty answer leaves $line null, and piping $null into ConvertFrom-Json is a
          # NON-terminating binding error this try never catches: it reached stderr as a red
          # error block on every hook, though the candidate was rightly rejected (T-0097).
          $probe = if ($line) { $line | ConvertFrom-Json } else { $null }
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
# Resume mode's consent is `resume.auto`, not this switch: the python plan
# below decides it, and is silent when it is off.
if ($Resume) { $enabled = $true }
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

function Get-CrewAutoClearInt($Value, [int]$Default, [switch]$RejectNegative) {
  if ($null -eq $Value -or $Value -is [bool]) { return $Default }
  # Castable is not usable: [int]-1 succeeds, so a bare try/catch here would
  # accept a negative delaySeconds, hand it straight to Start-Sleep in the
  # detached sender, and kill that process AFTER the parent has already
  # logged "sent" for a send that can never happen. -RejectNegative is
  # opt-in, not a blanket floor on every caller: minHandoffLines has no
  # Start-Sleep, and a negative there has always meant "disable the minimum
  # line count" (`$lines -lt -1` is never true) -- flooring it to the
  # default here would silently turn that off-switch into an enabled gate
  # at 5, with no warning path covering minHandoffLines to say so.
  try {
    $n = [int]$Value
    if ($RejectNegative -and $n -lt 0) { return $Default }
    return $n
  } catch { return $Default }
}

$method      = [string](Get-CrewAutoClearValue "method" "auto")
$delay       = Get-CrewAutoClearInt (Get-CrewAutoClearValue "delaySeconds" 3) 3 -RejectNegative
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
# The probe below reads $repoAuto/$globalAuto directly with `.delaySeconds`,
# NOT via Get-CrewAutoClearValue/Get-CrewChild: those use `return`, and
# PowerShell unrolls an EMPTY ARRAY through a function's output stream into
# zero pipeline objects, so `delaySeconds: []` comes back as plain $null --
# indistinguishable from the key never having been set, and this guard would
# never fire for it. Direct property access does not go through that
# stream, so an empty array stays a present (and unusable) empty array. A
# $null result here still means "absent" in either layer -- absence, and an
# explicit JSON `null`, are still the ordinary, silent default path.
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
$_crewDelayRaw = $null
if ($null -ne $repoAuto) { $_crewDelayRaw = $repoAuto.delaySeconds }
if ($null -eq $_crewDelayRaw -and $null -ne $globalAuto) { $_crewDelayRaw = $globalAuto.delaySeconds }
if ($null -ne $_crewDelayRaw) {
  $_crewDelayOk = $false
  if (-not ($_crewDelayRaw -is [bool])) {
    # Castable is not usable: [int]-1 succeeds, so this must reject negative
    # the same way Get-CrewAutoClearInt now does above -- otherwise the
    # warning text below ("using the default $delay") would lie about a
    # $delay that actually went through unchanged and is still negative.
    try {
      $_crewDelayInt = [int]$_crewDelayRaw
      if ($_crewDelayInt -ge 0) { $_crewDelayOk = $true }
    } catch { }
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

if ($Resume) {
  # T-0006's decide, onlyRepos/onlySessions, the typed text, the delay and
  # the per-handoff marker, from the one place they are decided. The method
  # is resolved natively below: `sendkeys` is this flavour's.
  if (-not $Python) { Stop-CrewAutoClear "no python was handed to resume mode, so nothing was decided" }
  $planLines = @(& $Python (Join-Path $PSScriptRoot "crew_autocycle.py") resume-plan "--root=$((Get-Location).Path)" `
                   "--session=$Session" "--source=$Source" --flavour ps1 2>$null |
                 ForEach-Object { ([string]$_).TrimEnd("`r") })
  if ($planLines.Count -lt 12) { Stop-CrewAutoClear "could not read the resume plan from crew_autocycle.py" }
  # Off is silent, as for /clear.
  if ($planLines[0] -eq "off") { exit 0 }
  if ($planLines[0] -ne "send") { Stop-CrewAutoClear $planLines[1] }
  $command = $planLines[5]
  $delay = Get-CrewAutoClearInt $planLines[6] 2 -RejectNegative
  $sentMarker = $planLines[9]
  $decisionJson = $planLines[10]
} elseif (-not $Force) {
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

# T-0017: armed, the clear also waits for the wrap-up's results on disk --
# after the handoff checks, before the method, the binding and any claim.
# Decided by crew_autocycle.py wrapup-check (the same check the .sh flavour's
# plan runs), so this needs a python; none is "could not tell": refuse.
$wrapUp = (Test-CrewTrue (Get-CrewChild $globalAuto "wrapUp")) -and
          -not (Test-CrewFalse (Get-CrewChild $repoAuto "wrapUp"))
if ($wrapUp -and -not $Resume -and -not $Force) {
  $wrapPy = if ($Python) { $Python } else { Resolve-CrewPython }
  if (-not $wrapPy) {
    $wrapWhy = "no usable python, so the wrap-up results could not be checked"
  } else {
    $wrapWhy = @(& $wrapPy (Join-Path $PSScriptRoot "crew_autocycle.py") wrapup-check "--root=$((Get-Location).Path)" 2>$null |
                 ForEach-Object { ([string]$_).TrimEnd("`r") })
    $wrapWhy = if ($wrapWhy.Count -gt 0 -and $wrapWhy[0]) { $wrapWhy[0] } else { "the wrap-up check gave no answer" }
  }
  if ($wrapWhy -ne "ok") {
    # Shown as well as logged: context-watch.ps1 forwards this stdout.
    Write-Output (@{ systemMessage = "crew wrap-up: not clearing - $wrapWhy" } | ConvertTo-Json -Compress)
    Stop-CrewAutoClear "wrap-up: $wrapWhy"
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

# --- T-0016: bind this session to its OWN process ---------------------------
#
# The same rules as crew_autocycle.session_owner / classify / prove_target,
# carried natively. The session is the nearest ancestor of this hook named by
# a Claude Code session record (${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/
# <pid>.json) whose sessionId is this session's and whose procStart matches
# wherever a start time can be read. Native Windows has no tty, so
# "terminal" rests on kind "interactive" plus an entrypoint on the measured
# allowlist; Windows' entrypoint is unmeasured, so anything else is unknown
# and never typed into. CREW_AUTOCLEAR_PROC_STUB, when set, is the WHOLE
# process table (the suite's only way in, like the window stub): a pid it
# does not name does not exist; `{"gone": true}` is a pid that has exited,
# null one that cannot be read. Both stubs are read ONLY while
# CREW_AUTOCLEAR_INHIBIT is set (review round 1): a repo's settings env
# reaches this hook, and with the inhibit set nothing is ever typed. No
# environment variable is evidence of which process is this session. With no
# tty on Windows, a parent session is told apart only by its record and its
# process name (claude, or a version-named native binary) -- a stated limit.
$script:crewTerminalEntrypoints = @("cli")
$script:crewProcStub = $null
$script:crewProcStubRead = $false

function Get-CrewProcStub {
  if ($script:crewProcStubRead) { return $script:crewProcStub }
  $script:crewProcStubRead = $true
  if (-not $env:CREW_AUTOCLEAR_PROC_STUB -or -not $env:CREW_AUTOCLEAR_INHIBIT) { return $null }
  # Unreadable: an empty table whose scans fail -- nothing in it is proven.
  $table = @{}; $fails = $true; $self = [long]0
  try {
    $data = Get-Content -LiteralPath $env:CREW_AUTOCLEAR_PROC_STUB -Raw -ErrorAction Stop |
      ConvertFrom-Json -ErrorAction Stop
    if ($data -is [System.Management.Automation.PSCustomObject]) {
      foreach ($prop in $data.PSObject.Properties) {
        if ($prop.Name -match '^\d+$') { $table[[long]$prop.Name] = $prop.Value }
      }
      $fails = Test-CrewTrue (Get-CrewChild $data "scanFails")
      $first = Get-CrewChild $data "self"
      if ($first -is [ValueType] -and -not ($first -is [bool])) { $self = [long]$first }
    }
  } catch { }
  $script:crewProcStub = @{ Table = $table; ScanFails = $fails; Self = $self }
  return $script:crewProcStub
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

function Get-CrewProcLookup([long]$Id) {
  # @{ Info = @{ Ppid; Start; Comm } or $null; Gone = $true when the process
  # provably no longer exists, never merely because it could not be read }.
  $stub = Get-CrewProcStub
  if ($null -ne $stub) {
    if (-not $stub.Table.ContainsKey($Id)) { return @{ Info = $null; Gone = $false } }
    $entry = $stub.Table[$Id]
    if ($null -eq $entry) { return @{ Info = $null; Gone = $false } }
    if (Test-CrewTrue (Get-CrewChild $entry "gone")) { return @{ Info = $null; Gone = $true } }
    $ppid = Get-CrewChild $entry "ppid"
    return @{ Gone = $false; Info = @{
      Ppid = $(if ($ppid -is [ValueType] -and -not ($ppid -is [bool])) { [long]$ppid } else { [long]0 })
      Start = (Get-CrewChild $entry "start"); Comm = [string](Get-CrewChild $entry "comm") } }
  }
  try { $proc = Get-Process -Id $Id -ErrorAction Stop } catch {
    # Only "no such process" is an exit; access denied or anything else is
    # an unreadable process, never the top of the chain (review round 1).
    return @{ Info = $null; Gone = ([string]$_.FullyQualifiedErrorId -like "NoProcessFoundForGivenId*") }
  }
  # Get-CrewParentId says 0 when it could not read the parent: unreadable.
  $parent = [long](Get-CrewParentId ([int]$Id))
  if ($parent -le 0) { return @{ Info = $null; Gone = $false } }
  # No start time: none is comparable to a record's procStart here, so a
  # record is bound by pid and session id only (a stated limit).
  return @{ Gone = $false; Info = @{ Ppid = $parent; Start = $null; Comm = [string]$proc.ProcessName } }
}

function Get-CrewProcInfo([long]$Id) {
  # @{ Ppid; Start; Comm }, or $null when the process cannot be read or is gone.
  return (Get-CrewProcLookup $Id).Info
}

function Get-CrewChain([long]$Start) {
  # @{ Chain; Complete; Why }: $Start and its ancestors, nearest first.
  $chain = New-Object System.Collections.Generic.List[long]
  $walk = $Start
  while ($true) {
    if ($chain.Contains($walk)) { return @{ Chain = $chain; Complete = $false; Why = "the process chain loops back to pid $walk" } }
    if ($chain.Count -ge 16) { return @{ Chain = $chain; Complete = $false; Why = "the process chain is deeper than 16 processes" } }
    $chain.Add($walk)
    $lookup = Get-CrewProcLookup $walk
    $info = $lookup.Info
    if ($null -eq $info) {
      # On native Windows a process's recorded parent has routinely exited:
      # that is the top of the chain. A process that exists but cannot be
      # read, and the walk's own first process, are failures.
      if ($lookup.Gone -and $chain.Count -gt 1) {
        $chain.RemoveAt($chain.Count - 1)
        return @{ Chain = $chain; Complete = $true; Why = "" }
      }
      return @{ Chain = $chain; Complete = $false; Why = "the parent of pid $walk could not be read" }
    }
    $walk = $info.Ppid
    if ($walk -le 1) { return @{ Chain = $chain; Complete = $true; Why = "" } }
  }
}

function Get-CrewConfigDir {
  if ($env:CLAUDE_CONFIG_DIR) { return $env:CLAUDE_CONFIG_DIR }
  return (Join-Path $userHome ".claude")
}

function Get-CrewSessionOwner {
  # @{ Pid; Record; Info } or @{ Unknown = reason }.
  if (-not $Session) { return @{ Unknown = "no session id, so no session record can be matched" } }
  $sessions = Join-Path (Get-CrewConfigDir) "sessions"
  $stub = Get-CrewProcStub
  $start = if ($null -ne $stub -and $stub.Self -gt 0) { $stub.Self } else { [long]$PID }
  $walk = Get-CrewChain $start
  foreach ($candidate in $walk.Chain) {
    $path = Join-Path $sessions "$candidate.json"
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $record = Read-CrewJsonFile $path
    if ($null -eq $record) { return @{ Unknown = "the session record for pid $candidate is unreadable or not a JSON object" } }
    # -cne: a session id is case-sensitive.
    if ([string](Get-CrewChild $record "sessionId") -cne $Session) {
      return @{ Unknown = "the session record for pid $candidate names another session" }
    }
    $info = Get-CrewProcInfo $candidate
    $started = if ($null -ne $info) { $info.Start } else { $null }
    if ($null -ne $started -and [string](Get-CrewChild $record "procStart") -cne [string]$started) {
      return @{ Unknown = ("the session record for pid $candidate has procStart '$(Get-CrewChild $record "procStart")' " +
                           "but that process started at $started - a reused pid is a different process") }
    }
    return @{ Pid = [long]$candidate; Record = $record; Info = $info }
  }
  if (-not $walk.Complete) { return @{ Unknown = "no session record names a process above this hook, and $($walk.Why)" } }
  return @{ Unknown = "no session record under $sessions names a process above this hook" }
}

function Get-CrewSessionClass($Owner) {
  # @{ Class = terminal|headless|unknown; Evidence }.
  if ($Owner.ContainsKey("Unknown")) { return @{ Class = "unknown"; Evidence = $Owner.Unknown } }
  $kind = Get-CrewChild $Owner.Record "kind"
  $entry = Get-CrewChild $Owner.Record "entrypoint"
  if ($entry -is [string] -and $entry.StartsWith("sdk", [StringComparison]::Ordinal)) {
    return @{ Class = "headless"; Evidence = "entrypoint $entry" }
  }
  if ($kind -is [string] -and $kind -cne "interactive") { return @{ Class = "headless"; Evidence = "kind $kind" } }
  if (-not ($kind -is [string])) {
    return @{ Class = "unknown"; Evidence = "the session record for pid $($Owner.Pid) has no usable kind ($kind)" }
  }
  if (-not ($entry -is [string]) -or -not ($script:crewTerminalEntrypoints -ccontains $entry)) {
    return @{ Class = "unknown"; Evidence = ("entrypoint '$entry' is not one measured to have a terminal (" +
                                             ($script:crewTerminalEntrypoints -join ", ") + ")") }
  }
  return @{ Class = "terminal"; Evidence = "kind interactive, entrypoint $entry" }
}

function Get-CrewOtherSessions([long]$OwnerPid) {
  # Pids of every OTHER live session record, or $null when they cannot be listed.
  $sessions = Join-Path (Get-CrewConfigDir) "sessions"
  try { $files = @(Get-ChildItem -LiteralPath $sessions -File -ErrorAction Stop) } catch { return $null }
  $out = New-Object System.Collections.Generic.List[long]
  foreach ($file in $files) {
    if ($file.Name -notmatch '^(\d+)\.json$') { continue }
    $other = [long]$Matches[1]
    if ($other -eq $OwnerPid) { continue }
    $record = Read-CrewJsonFile $file.FullName
    $info = Get-CrewProcInfo $other
    if ($null -eq $info) { continue }
    # A live process whose record cannot be read may be a session, so no
    # other session can be ruled out (review round 1).
    if ($null -eq $record) { return $null }
    if ($null -ne $info.Start -and [string](Get-CrewChild $record "procStart") -cne [string]$info.Start) { continue }
    $out.Add($other)
  }
  return ,$out
}

function Get-CrewHeadlessNotice([string]$Evidence) {
  # The same text crew_autocycle.headless_notice builds: the handoff, its
  # resume: line read as text, and that the starting process must restart.
  $line = "(none in the handoff)"
  try {
    $base = (Get-Location).Path
    $full = [System.IO.Path]::GetFullPath((Join-Path $base $handoffRel))
    $text = Get-Content -LiteralPath $full -Raw -ErrorAction Stop
    foreach ($row in ($text -split "`r?`n")) {
      if ($row -cmatch '^resume:[ \t]*(.*?)[ \t]*$') {
        if ($Matches[1]) { $line = $Matches[1] }
        break
      }
    }
  } catch { }
  $written = if ($Force) { "Its handoff at $handoffRel was not checked (--force)" } else { "Its handoff is written and verified at $handoffRel" }
  return ("crew: this session has no terminal of its own ($Evidence), so nothing was cleared or typed. " +
          "$written; resume: $line. The process that started this session must start a new one to continue.")
}

# After the handoff checks and the method, before any claim (T-0017's order).
$crewOwner = Get-CrewSessionOwner
$crewClass = Get-CrewSessionClass $crewOwner
if ($crewClass.Class -eq "headless" -and -not $Resume) {
  # Whatever the method: nothing is typed, one notice is printed, claimed
  # like notify so it fires once per session, and logged in full -- a
  # `claude -p` parent may never show the systemMessage.
  $msg = Get-CrewHeadlessNotice $crewClass.Evidence
  if ($DryRun) {
    Write-Output "autoclear: would send"
    Write-Output "  method: notify-headless"
    Write-Output "  command: $command"
    Write-Output "  delay: n/a (nothing is typed)"
    Write-Output "  message: $msg"
    exit 0
  }
  if (-not $Force) {
    try {
      $claim = [System.IO.File]::Open(
        (Join-Path (Get-Location).Path $sentMarker), [System.IO.FileMode]::CreateNew)
      $claim.Close()
    } catch { exit 0 }
  }
  Write-Output (@{ systemMessage = $msg } | ConvertTo-Json -Compress)
  Write-CrewAutoClearNote "sent - method notify-headless: $msg"
  exit 0
}
if ($method -ne "notify" -and $crewClass.Class -ne "terminal") {
  $why = if ($crewClass.Class -eq "headless") {
    "this session has no terminal of its own ($($crewClass.Evidence))"
  } elseif ($crewOwner.ContainsKey("Unknown")) {
    "could not identify this session's process ($($crewClass.Evidence))"
  } else {
    "could not tell whether this session has a terminal of its own ($($crewClass.Evidence))"
  }
  if ($Resume) { Stop-CrewAutoClear "auto-resume types only into this session's own terminal: $why" }
  Stop-CrewAutoClear $why
}

if ($method -eq "notify" -and $Resume) {
  # Types nothing, so it neither claims the handoff nor records a run: the
  # human starts the command, and decide still sees the note as unused.
  if ($DryRun) {
    Write-Output "autoresume: would send"
    Write-Output "  method: notify"
    Write-Output "  command: $command"
    Write-Output "  delay: n/a (notify types nothing)"
    exit 0
  }
  Write-CrewAutoClearNote "auto-resume: method notify - run $command yourself (nothing typed)"
  Write-Output "autoresume: notify - run $command yourself"
  exit 0
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
  if ($env:CREW_AUTOCLEAR_WINDOW_STUB -and $env:CREW_AUTOCLEAR_INHIBIT) {
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

try { $windows = @(Get-CrewWindows) } catch { Stop-CrewAutoClear "cannot list windows: $($_.Exception.Message)" }

# T-0016: walked up from this SESSION's own process, not from this hook, and
# excluding that process itself (claude owns no window). The walk stops at
# the first process that owns a window; reaching another Claude Code session
# first -- a child under its parent's window -- refuses, and so does a chain
# that could not be read to the end with no window found on it.
$crewOthers = Get-CrewOtherSessions $crewOwner.Pid
if ($null -eq $crewOthers) { Stop-CrewAutoClear "the session records could not be listed or read, so another session cannot be ruled out" }
$crewOwnerChain = Get-CrewChain $crewOwner.Pid
$ancestors = @()
$crewFoundOwner = $false
foreach ($crewStep in @($crewOwnerChain.Chain | Select-Object -Skip 1)) {
  $crewStepInfo = Get-CrewProcInfo $crewStep
  if ($crewOthers -contains $crewStep -or ($null -ne $crewStepInfo -and
      ($crewStepInfo.Comm -eq "claude" -or $crewStepInfo.Comm -match '^\d+\.\d+\.\d+$'))) {
    Stop-CrewAutoClear "the way from this session (pid $($crewOwner.Pid)) up to its window passes through another Claude Code session (pid $crewStep)"
  }
  $ancestors += $crewStep
  if (@($windows | Where-Object { $_.Pid -eq $crewStep }).Count -gt 0) { $crewFoundOwner = $true; break }
}
if (-not $crewFoundOwner -and -not $crewOwnerChain.Complete) {
  Stop-CrewAutoClear "no window belongs to a process above this session (pid $($crewOwner.Pid)), and $($crewOwnerChain.Why)"
}

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
    Stop-CrewAutoClear "no window belongs to any ancestor of this session's process (pid $($crewOwner.Pid)), and no context.autoClear.windowTitle is set to fall back on"
  }
  $hits = @($windows | Where-Object { $_.Title.ToLowerInvariant().Contains($needle) })
  if ($hits.Count -ne 1) {
    Stop-CrewAutoClear "$($hits.Count) windows have a title containing '$windowTitle' - refusing to guess which one is this session"
  }
  # T-0016: a title cannot tell two sessions apart, and a window with no
  # owning process is tied to nothing -- either refuses while another
  # session is live.
  if ($crewOthers.Count -gt 0) {
    $crewSibling = ($crewOthers | Measure-Object -Minimum).Minimum
    if ($hits[0].Pid -le 1) {
      Stop-CrewAutoClear "window $($hits[0].Id) has no owning process, and another Claude Code session is live (pid $crewSibling), so nothing ties that window to this session"
    }
    Stop-CrewAutoClear "window $($hits[0].Id) was found by its title alone, and another Claude Code session is live (pid $crewSibling) - a title cannot tell two sessions apart"
  }
  $target = $hits[0]; $how = "title fallback"
} else {
  # T-0016: one console host can serve more than one session. A window whose
  # owner is also above another live session is not provably this one's.
  foreach ($crewOther in $crewOthers) {
    if ((Get-CrewChain $crewOther).Chain -contains [long]$target.Pid) {
      Stop-CrewAutoClear "the window's owner (pid $($target.Pid)) also hosts another Claude Code session (pid $crewOther)"
    }
  }
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
function Get-CrewSendKeysTabDecision([bool]$UiaAvailable, $TabCount, [bool]$SelectedMatches, $TitleMatches = $null) {
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
  # at all" without re-deriving it from the UIA probe. $SelectedMatches alone
  # cannot distinguish THAT from "more than one tab's title matched, so no
  # single one could be proven active" -- both read as SelectedMatches=$false
  # -- which is why $TitleMatches (when the caller has it) picks the wording
  # for the ambiguous case instead; text only, same as $SelectedMatches this
  # plays no part in the DECISION.
  $selectedNote = if ($null -ne $TitleMatches -and $TitleMatches -gt 1) {
    "windowTitle matched $TitleMatches of the $TabCount tabs, so no single one could be proven active"
  } elseif ($SelectedMatches) {
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
      return @{ UiaAvailable = $false; TabCount = 0; SelectedMatches = $false; TitleMatches = 0 }
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
    return @{ UiaAvailable = $true; TabCount = $tabs.Count; SelectedMatches = [bool]$selectedMatches; TitleMatches = $titleMatches }
  } catch {
    return @{ UiaAvailable = $false; TabCount = 0; SelectedMatches = $false; TitleMatches = 0 }
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
# Under the process stub (the suite), the stub names the owner, as it does
# every other process; a pid the stub does not name keeps the real answer.
$crewStubOwner = if ($null -ne (Get-CrewProcStub)) { Get-CrewProcInfo $target.Pid } else { $null }
if ($null -ne $crewStubOwner) { $ownerProcessName = $crewStubOwner.Comm; $ownerKnown = $true }

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
                -TabCount $tabState.TabCount -SelectedMatches $tabState.SelectedMatches `
                -TitleMatches $tabState.TitleMatches
  if ($decision.Decision -ne "send") { $declineReason = $decision.Reason }
}
# else: a non-Windows-Terminal console host (conhost) has no tabs to
# disambiguate -- falls straight through to sendkeys below, unchanged.

if ($declineReason) {
  # Resume mode declines without claiming: nothing was typed or recorded.
  if ($Resume) { Stop-CrewAutoClear "declined sendkeys - $declineReason" }
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
if ($Resume) {
  # T-0013: the per-handoff marker (an absolute path from the plan), claimed
  # LAST, after every refusal above. Then the run is recorded BEFORE anything
  # is spawned: a run the loop guard cannot see is never typed.
  try {
    $claim = [System.IO.File]::Open($sentMarker, [System.IO.FileMode]::CreateNew)
    $claim.Close()
  } catch { Stop-CrewAutoClear "this handoff was already typed once (marker $(Split-Path -Leaf $sentMarker) exists)" }
  $recordOut = $decisionJson | & $Python (Join-Path $PSScriptRoot "crew_resume.py") record `
                 "--root=$((Get-Location).Path)" --decision-json - 2>$null
  $recorded = $null
  try { $recorded = ($recordOut | Out-String) | ConvertFrom-Json -ErrorAction Stop } catch { }
  if ($null -eq $recorded -or -not (Test-CrewTrue (Get-CrewChild $recorded "ok"))) {
    $why = [string](Get-CrewChild $recorded "reason"); if (-not $why) { $why = "no answer from crew_resume.py" }
    Stop-CrewAutoClear "could not record the run ($why) - nothing typed"
  }
} elseif (-not $Force) {
  try {
    $claim = [System.IO.File]::Open(
      (Join-Path (Get-Location).Path $sentMarker), [System.IO.FileMode]::CreateNew)
    $claim.Close()
  } catch { exit 0 }
}

$sendRoot = (Get-Location).Path
$child = @'
param([long]$Hwnd, [string]$Text, [int]$Delay, [string]$Root, [string]$WindowTitle = "",
      [int]$IsWindowsTerminal = 1)
# [int], not [bool]: this parameter is bound by the CHILD PROCESS's OWN
# command-line parser under `-File`, not by an in-process function call --
# and measured directly (both engines, real `-File` invocations, see
# auto-clear.ps1 tests), [bool] parameter binding under `-File` REJECTS
# every string form tried, "True", "1", and even the colon-attached
# PowerShell-literal syntax `-IsWindowsTerminal:$true` -- on Windows
# PowerShell 5.1. pwsh 7 accepts the colon+literal form but not `:1`/`:0`
# or a space-separated value either. [int] with a plain "1"/"0" argv value
# is the one form that binds on BOTH engines, so the child casts it back to
# [bool] itself ($IsWindowsTerminal -ne 0) wherever a boolean is needed.
# IsWindowsTerminal defaults to 1 (true), not 0: an argv that somehow omits
# it must recheck rather than skip the recheck -- the unknown collapsing into
# the PERMISSIVE value is exactly the bug this file exists to fix. The real
# parent below always passes it explicitly; this default only matters to a
# caller that does not.
$IsWindowsTerminalBool = ($IsWindowsTerminal -ne 0)
# Delete self next, right after binding: every exit below is an early
# return, and a temp script left in %TEMP% on each of them accumulates one
# file per session forever. The file is already open and read by the
# interpreter, so removing it now is safe. The one statement ahead of this
# (casting IsWindowsTerminal to bool) cannot throw, so it does not change
# which exit paths still leave the file behind.
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
      return @{ UiaAvailable = $false; TabCount = 0; SelectedMatches = $false; TitleMatches = 0 }
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
    return @{ UiaAvailable = $true; TabCount = $tabs.Count; SelectedMatches = [bool]$selectedMatches; TitleMatches = $titleMatches }
  } catch {
    return @{ UiaAvailable = $false; TabCount = 0; SelectedMatches = $false; TitleMatches = 0 }
  }
}
function Get-CrewSendKeysTabDecision([bool]$UiaAvailable, $TabCount, [bool]$SelectedMatches, $TitleMatches = $null) {
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
  # at all" without re-deriving it from the UIA probe. $SelectedMatches alone
  # cannot distinguish THAT from "more than one tab's title matched, so no
  # single one could be proven active" -- both read as SelectedMatches=$false
  # -- which is why $TitleMatches (when the caller has it) picks the wording
  # for the ambiguous case instead; text only, same as $SelectedMatches this
  # plays no part in the DECISION.
  $selectedNote = if ($null -ne $TitleMatches -and $TitleMatches -gt 1) {
    "windowTitle matched $TitleMatches of the $TabCount tabs, so no single one could be proven active"
  } elseif ($SelectedMatches) {
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
           -TabCount $tabState.TabCount -SelectedMatches $tabState.SelectedMatches `
           -TitleMatches $tabState.TitleMatches
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
# $fg -eq 0 is its own decline, not folded into the -ne comparison: a
# locked or headless session makes GetForegroundWindow() return 0, which
# would otherwise equal an unresolved/placeholder $Hwnd of 0 and read as
# "still focused" when nothing is actually in the foreground to be typed
# into. Unknown must decline here exactly as it does for the parent's
# owner-pid check, earlier in this file and outside this heredoc (FIX 1's
# "cannot determine the process" case) -- this is the same shape of bug,
# not a new one.
$fg = [CrewAC.Win]::GetForegroundWindow().ToInt64()
if ($fg -eq 0 -or $fg -ne $Hwnd) {
  Write-CrewChildNote "declined sendkeys - the target window lost focus during the ${Delay}s delay, so nothing was typed - run $Text yourself"
  exit 0
}
# Re-run the SAME tab-count == 1 predicate the parent ran before Start-Sleep,
# immediately before typing -- the window handle above proves the FOCUSED
# window is still this session's Windows Terminal window, not which TAB in
# it is showing. A tab switch inside that window during the delay changes
# nothing GetForegroundWindow can see, so this is the only check left that
# can catch it. Decline exactly like the focus check: log, never type.
$recheck = Get-CrewChildTabRecheck -Hwnd $Hwnd -Title $WindowTitle -IsWindowsTerminal $IsWindowsTerminalBool
if ($recheck.Decision -ne "send") {
  Write-CrewChildNote "declined sendkeys - $($recheck.Reason), re-checked after the ${Delay}s delay - run $Text yourself"
  exit 0
}
# A test suite must never drive the real keyboard -- see the parent's own
# CREW_AUTOCLEAR_INHIBIT check below this heredoc, right before
# Start-Process. That
# check only stops the PARENT from ever reaching this file: a test that
# spawns this heredoc directly via `-File` (the argv-binding regression
# tests, which must drive a REAL `-File` invocation of this exact script to
# prove [int]-not-[bool] binds under both engines) never passes through the
# parent at all, and nothing above this line is guaranteed to decline in
# every host environment -- see the $fg -eq 0 comment just above. This gate
# is placed as the LAST check before SendWait, after every decision branch
# above it, specifically so it cannot be bypassed by whichever branch a
# test happens to take.
if ($env:CREW_AUTOCLEAR_INHIBIT) {
  Write-CrewChildNote "declined sendkeys - CREW_AUTOCLEAR_INHIBIT is set, no keystroke sent"
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
#
# Review (Codex round 2|auto-clear.ps1:~1057): a SPACE-separated
# "-IsWindowsTerminal", "$IsWindowsTerminal" pair stringifies the bool to
# the literal text "True"/"False" as its OWN argv entry. Under `-File`
# (the real parent invocation below, and the only one that matters -- the
# child is always launched via `-File`), PowerShell's parameter binder
# does NOT accept that bare word for a [bool] parameter and throws
# "Cannot convert value System.String to type System.Boolean". The
# child's `param()` block never finishes binding, so NOTHING in its body
# runs: not the self-delete (`Remove-Item -LiteralPath $PSCommandPath`,
# the first statement in the body -- the temp script leaks), not
# `Get-CrewChildTabRecheck`, not `SendWait`. The parent has already
# exited 0 and already claimed the one-shot marker before spawning, so
# this fails completely silently.
#
# Measured directly on BOTH engines with real `-File` child processes
# (not merely inspected as strings) before picking a fix: NO string form
# of a [bool] parameter binds on Windows PowerShell 5.1 under `-File` --
# not "True", not "1", not even the colon-attached PowerShell-literal
# syntax `-IsWindowsTerminal:$true`, which pwsh 7 alone accepts (pwsh 7
# also rejects `:1`/`:0` and any space-separated form). There is no
# single-argv-token spelling of a BOOLEAN value that binds on both
# engines. An [int] parameter with a plain "1"/"0" value, by contrast,
# binds on both engines in every form tried (space-separated included),
# so the child parameter is [int] and casts itself back to [bool]
# (`$IsWindowsTerminal -ne 0`, see the param block above) wherever a
# boolean is actually needed. "1"/"0" contain no spaces, so there is
# nothing for Start-Process's plain-space join to split apart either.
function Get-CrewSendKeysChildArgs([string]$ChildPath, [long]$Hwnd, [string]$Command,
                                    [int]$Delay, [string]$Root, [string]$WindowTitle = "",
                                    [bool]$IsWindowsTerminal = $true) {
  $isWindowsTerminalArg = if ($IsWindowsTerminal) { "1" } else { "0" }
  return @(
    "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    "-File", (ConvertTo-CrewWin32Arg $ChildPath), "-Hwnd", "$Hwnd",
    "-Text", (ConvertTo-CrewWin32Arg $Command),
    "-WindowTitle", (ConvertTo-CrewWin32Arg $WindowTitle),
    "-IsWindowsTerminal", $isWindowsTerminalArg,
    "-Delay", "$Delay", "-Root", (ConvertTo-CrewWin32Arg $Root)
  )
}

# Hidden so it does not steal the focus the child is about to check for.
Start-Process -FilePath $exe -WindowStyle Hidden -ArgumentList (Get-CrewSendKeysChildArgs `
  -ChildPath $childPath -Hwnd $target.Id -Command $command -Delay $delay -Root $sendRoot `
  -WindowTitle $windowTitle -IsWindowsTerminal $isWindowsTerminal) | Out-Null

Write-CrewAutoClearNote "sent - method sendkeys, target $label, command '$command' in ${delay}s (only if that window still has focus)"
if ($Resume) { Write-Output "autoresume: typing $command in ${delay}s (method sendkeys)" }
exit 0
