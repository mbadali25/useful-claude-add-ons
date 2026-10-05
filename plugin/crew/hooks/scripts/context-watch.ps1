# Stop hook (native Windows). Mirrors context-watch.sh: reads how full the
# context window actually is and, once past the threshold, asks Claude to write a
# handoff note before ending the turn. Exit 2 returns control to the model with
# the reason on stderr.
#
# NOTHING HERE RUNS until a repository at least has a `.crew/` directory -
# crew is per-repository and its hooks are inert until something (`/crew:init`
# or a worktree copy) has made that much true.
#
# Two gates below, not one, since crew 1.0 F4: this hook's own handover to
# auto-clear.ps1 (the forced-continuation branch) reaches it on `.crew/`
# existing alone, matching auto-clear.ps1's own directory gate -
# `context.autoClear` is a machine-global switch and must work in any crew
# repo (CONFIG.md sec 14). This hook's OWN context-window measurement and
# nagging, further down, is a separate question and keeps requiring a real
# `.crew/config.json` underneath, unchanged.

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

function Get-CrewRepoConfigDir([string]$Root) {
  # @{ Dir; Source }: the `.crew/` the repo config is read from, and own, main
  # or unknown. Twin of crew_repo_config_dir in _common.sh and of
  # crew_common.repo_config_dir (T-0088, T-0096): own files win whole, never
  # merged; `unknown` inherits nothing and is never "absent". Copied verbatim
  # into each script that needs it (a dot-sourced function is invisible to
  # check-powershell.ps1); test_worktree_config_shell.py holds the copies equal.
  # 5.1 cannot resolve a symlink as realpath does, so on every PowerShell (7 too)
  # a symlink, a junction or an ancestor Get-Item cannot read (a UNC share's
  # root, likely) in either path compared below reads `unknown`, never `main`.
  if (-not $Root) { $Root = '.' }
  $own = Join-Path $Root '.crew'
  $result = @{ Dir = $own; Source = 'own' }
  foreach ($n in 'crew.json', 'config.json') {
    if (Get-Item -LiteralPath (Join-Path $own $n) -Force -ErrorAction SilentlyContinue) { return $result }
  }
  if (-not (Test-Path -LiteralPath (Join-Path $Root '.git') -PathType Leaf)) { return $result }
  $result.Source = 'unknown'
  # git prints paths as UTF-8; a native command's output is decoded with
  # [Console]::OutputEncoding (the OEM code page on Windows), so pin UTF-8 for
  # this one call and put the caller's back.
  $encoding = [Console]::OutputEncoding
  try {
    $base = (Resolve-Path -LiteralPath $Root -ErrorAction Stop).ProviderPath
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $lines = @(& git -C $base rev-parse --git-dir --git-common-dir 2>$null)
  } catch { return $result } finally { [Console]::OutputEncoding = $encoding }
  if ($LASTEXITCODE -ne 0 -or $lines.Count -ne 2) { return $result }
  $real = New-Object System.Collections.Generic.List[string]
  foreach ($p in $lines) {
    $full = [System.IO.Path]::GetFullPath($(if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $base $p }))
    for ($at = $full; $at; $at = Split-Path -Parent $at) {
      $item = Get-Item -LiteralPath $at -Force -ErrorAction SilentlyContinue
      if (-not $item -or $item.LinkType) { return $result }
    }
    $real.Add($full.TrimEnd('\', '/'))
  }
  $result.Source = 'own'
  $same = if ($env:OS -eq 'Windows_NT') { $real[0] -eq $real[1] } else { $real[0] -ceq $real[1] }
  if ($same -or (Split-Path -Leaf $real[1]) -cne '.git') { return $result }
  $main = Join-Path (Split-Path -Parent $real[1]) '.crew'
  foreach ($n in 'crew.json', 'config.json') {
    if (Get-Item -LiteralPath (Join-Path $main $n) -Force -ErrorAction SilentlyContinue) {
      return @{ Dir = $main; Source = 'main' }
    }
  }
  return $result
}

function Get-CrewHandoffPath($Value) {
  # The handoff note's path relative to the cwd (the checkout root):
  # context.handoffPath, or .work/HANDOFF.md when it is unset or leaves the
  # checkout -- absolute, `..`, or through a link -- or names a directory (the
  # checkout itself, `notes/`), with a warning on stderr. Forward slashes.
  # Twin of crew_state.handoff_path (crew_freshness.contained_path), stricter
  # on links: 5.1 cannot resolve one as realpath does, so any link between the
  # root and the target reads as leaving. In a linked worktree inheriting the
  # main checkout's config (L-0680) an absolute value would name the main
  # checkout's file. Copied verbatim into handoff-read.ps1, handoff-write.ps1
  # and context-watch.ps1; test_worktree_config_shell.py holds the copies equal.
  $default = '.work/HANDOFF.md'
  if (-not ($Value -is [string]) -or -not $Value.Trim()) { return $default }
  # PowerShell's file cmdlets read `\` as a separator on every OS (on POSIX
  # too, where the .NET path APIs do not), so the containment check below must
  # see the path those cmdlets will use: `..\main\x` is `../main/x`.
  $sep = [System.IO.Path]::DirectorySeparatorChar
  if ($sep -ne '\') { $Value = $Value.Replace('\', '/') }
  $inside = $false
  try {
    $base = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath).TrimEnd('\', '/')
    $full = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($base, $Value))
    $cmp = if ($env:OS -eq 'Windows_NT' -and $IsLinux -ne $true) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    $inside = $full.StartsWith($base + [System.IO.Path]::DirectorySeparatorChar, $cmp)
    for ($at = $full; $inside -and $at.Length -gt $base.Length; $at = Split-Path -Parent $at) {
      $item = Get-Item -LiteralPath $at -Force -ErrorAction SilentlyContinue
      if ($item -and $item.LinkType) { $inside = $false }
    }
  } catch { $inside = $false }
  if (-not $inside) {
    $script:CrewHandoffPathLeft = $true   # context-watch.ps1 says so in its message
    [Console]::Error.WriteLine("crew: context.handoffPath leaves this checkout - using $default")
    return $default
  }
  # A directory (`notes/`, an existing folder) cannot hold the note.
  if ($Value.EndsWith('/') -or $Value.EndsWith([string]$sep) -or (Test-Path -LiteralPath $full -PathType Container)) {
    [Console]::Error.WriteLine("crew: context.handoffPath names a directory - using $default")
    return $default
  }
  # Forward slashes on every OS, as the bash twin prints it. Only Windows can
  # have a `\` left here; converting after the check is safe because the check
  # above already saw `\` as the separator it is to the cmdlets.
  $rel = $full.Substring($base.Length + 1)
  if ($sep -eq '\') { $rel = $rel.Replace('\', '/') }
  return $rel
}

$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue

if (-not (Test-Path ".crew" -PathType Container)) { exit 0 }

# Every marker is keyed on this Stop's session. It used to be one
# .crew/.handoff-requested per REPOSITORY, so two terminals in one repo shared
# it. The key keeps only [A-Za-z0-9_-], matching context-watch.sh and
# crew_autocycle.session_key.
$sessionId  = if ($d.session_id) { [string]$d.session_id } else { "" }
$sessionKey = [regex]::Replace($sessionId, '[^A-Za-z0-9_-]', '_')
if ($sessionKey.Length -gt 100) { $sessionKey = $sessionKey.Substring(0, 100) }
if (-not $sessionKey) { $sessionKey = "nosession" }
$marker     = ".crew/.handoff-requested-$sessionKey"
$sentMarker = ".crew/.autoclear-sent-$sessionKey"
$escalated  = ".crew/.wrapup-escalated-$sessionKey"  # T-0017

# auto-clear.ps1 logs its own refusals/sends to .crew/.autoclear.log (see its
# own Write-CrewAutoClearNote) and writes the same line to [Console]::Error --
# but only on paths that reach that function, and [Console]::Error bypasses
# PowerShell's own error STREAM (stream 2) entirely, so the `2>$null` below
# never actually redirected it. What DID work, and what made a crash totally
# silent, was `| Out-Null` eating the success stream and the empty `catch {}`
# eating a genuine terminating exception -- together covering every remaining
# way out. `.crew/.autoclear.log` was reported to exist nowhere on the
# affected Windows host, which is what that total silence looks like.
#
# This captures both signals instead of discarding them: the PowerShell error
# stream (`2>&1`, for the rare case auto-clear ever emits through it) AND the
# raw Console error stream, by swapping [Console]::Error for a StringWriter
# for the DURATION of the call only, then independently appends a line to the
# SAME log whenever the child looks unhealthy -- exited non-zero, wrote
# anything to either stream, or threw. Deliberately unconditional rather than
# trying to detect whether auto-clear ALREADY logged the same thing; a
# duplicate line on an ordinary refusal costs nothing a human reading the log
# would notice, and a MISSING line is the whole defect this closes.
#
# Must never throw itself. auto-clear's stdout IS forwarded onto this hook's
# own stdout, which Claude Code reads as the Stop hook's protocol -- see
# `Invoke-ContextWatchAutoClear`'s own comment for why that is now safe; the
# fallback, if the log cannot be written (an unwritable .crew/), is this
# hook's own stderr.
function Write-ContextWatchAutoClearTrouble([string]$Message) {
  $clean = ($Message -replace "[`r`n`t]", " ")
  try {
    if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force -ErrorAction Stop | Out-Null }
    $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
    Add-Content -Path ".crew/.autoclear.log" -Value "$stamp`t$clean" -Encoding utf8 -ErrorAction Stop
  } catch {
    [Console]::Error.WriteLine("context-watch: $clean")
  }
}

function Invoke-ContextWatchAutoClear([string]$SessionId) {
  $origErr = [Console]::Error
  $sw = New-Object System.IO.StringWriter
  $threw = $null
  $rc = $null
  $stdout = $null
  try {
    [Console]::SetError($sw)
    try {
      $stdout = & "$PSScriptRoot/auto-clear.ps1" -Session $SessionId -Root (Get-Location).Path 2>&1 |
        ForEach-Object {
          if ($_ -is [System.Management.Automation.ErrorRecord]) { $sw.WriteLine($_.ToString()) }
          else { $_ }
        }
      $rc = $LASTEXITCODE
    } catch {
      $threw = $_.Exception.Message
    }
  } finally {
    [Console]::SetError($origErr)
  }
  $captured = $sw.ToString().Trim()
  # Forwarded, not discarded: `method notify` (and a `sendkeys` decline that
  # falls back to it) is the ONE real, non-dry-run path that writes anything
  # to auto-clear's stdout -- a single line of JSON, `{"systemMessage": ...}`
  # -- and this hook never writes to its OWN stdout on any other path, so
  # there is nothing here for it to collide with. Every other auto-clear
  # path still writes nothing to stdout, exactly as before.
  foreach ($line in @($stdout)) { if ($line) { Write-Output $line } }
  if ($threw) {
    Write-ContextWatchAutoClearTrouble "auto-clear threw: $threw"
  } elseif (($null -ne $rc -and $rc -ne 0) -or $captured) {
    $suffix = if ($captured) { " - stderr: $captured" } else { "" }
    Write-ContextWatchAutoClearTrouble "auto-clear exited $rc$suffix"
  }
}

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

# T-0017: the python that runs crew_autocycle's wrap-up verbs, or '' when the
# wrap-up is not configured here. Checked natively FIRST -- machine `wrapUp`
# and `enabled` exactly true, no repo `false` for either -- so an unarmed
# machine never probes for a python and its output is unchanged. No python:
# '' too, and the caller sends today's message (auto-clear.ps1 still refuses
# the clear: both are the refusing direction).
function Get-CrewWrapUpPython($RepoAutoClear) {
  $userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
  try {
    $machine = Get-Content -LiteralPath (Join-Path $userHome ".claude/crew/config.json") -Raw -ErrorAction Stop |
      ConvertFrom-Json -ErrorAction Stop
  } catch { return '' }
  $auto = if ($machine -is [System.Management.Automation.PSCustomObject]) { $machine.context.autoClear } else { $null }
  if ($auto -isnot [System.Management.Automation.PSCustomObject]) { return '' }
  if (-not (($auto.wrapUp -is [bool]) -and $auto.wrapUp -and ($auto.enabled -is [bool]) -and $auto.enabled)) { return '' }
  if ($RepoAutoClear -is [System.Management.Automation.PSCustomObject]) {
    if (($RepoAutoClear.wrapUp -is [bool]) -and -not $RepoAutoClear.wrapUp) { return '' }
    if (($RepoAutoClear.enabled -is [bool]) -and -not $RepoAutoClear.enabled) { return '' }
  }
  return (Resolve-CrewPython)
}

# The lines a crew_autocycle wrap-up verb prints; nothing on any failure.
function Invoke-CrewWrapUpVerb([string]$Py, [string[]]$VerbArgs) {
  try {
    & $Py (Join-Path $PSScriptRoot "crew_autocycle.py") @VerbArgs 2>$null |
      ForEach-Object { ([string]$_).TrimEnd("`r") }
  } catch { }
}

# Loop safety, layer 1: Claude Code is already continuing because of a stop
# hook -- do not pile on more feedback. Layer 2 is the once-per-crossing
# marker below. Layer 3 is Claude Code's own 8-consecutive-block backstop.
#
# This forced continuation is also the one turn on which auto-clear matters:
# it is the turn the handoff gets written. Exiting here unconditionally meant
# auto-clear only ran after the NEXT user turn. So hand over to it -- never
# block, never ask again -- when THIS session has a wrap-up marker.
if ($d.stop_hook_active -eq $true) {
  if (Test-Path $marker) {
    Invoke-ContextWatchAutoClear $sessionId
  }
  exit 0
}

# From here down: this hook's OWN context-window measurement and nagging --
# as distinct from the auto-clear handover above, which needed only `.crew/`
# -- still requires a fully initialised crew repo. Unchanged from before F4:
# a `.crew/` directory with no config.json gets no warnings and writes no
# marker, exactly as a repo that never ran `/crew:init` always has.
# L-0680: the resolved repo config (Get-CrewRepoConfigDir, T-0096): a linked
# worktree with none of its own reads the main checkout's, own files win whole,
# `unknown` reads only the own .crew/. The marker stays in this .crew/.
# $cfgShown is the name a message gives it: the main checkout's full path when
# it is inherited, `.crew/config.json` when it is this checkout's own.
$repoCfg  = Get-CrewRepoConfigDir '.'
$cfgPath  = Join-Path $repoCfg.Dir 'config.json'
$cfgShown = if ($repoCfg.Source -eq 'main') { $cfgPath } else { '.crew/config.json' }
if (-not (Test-Path -LiteralPath $cfgPath -PathType Leaf)) { exit 0 }

if (-not $d.transcript_path -or -not (Test-Path $d.transcript_path)) { exit 0 }

# No hook_once claim here on purpose: Stop fires once per TURN against a
# stable session id, so a session-scoped claim taken on turn 1 would suppress
# the context nag for the rest of the session. $marker above is the real
# once-per-crossing gate for this hook, reset by handoff-read.ps1 at this
# session's next SessionStart -- that stays.

$cfg = (Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json).context
if ($null -eq $cfg -or $cfg.enabled -eq $false) { exit 0 }
# $null test, not truthiness: warnAt 0 is a legal "always fire" and 0 is falsy.
$warnAt     = if ($null -ne $cfg.warnAt) { [double]$cfg.warnAt } else { 0.5 }
$configured = if ($cfg.budgetTokens) { [long]$cfg.budgetTokens } else { 0 }
$handoff    = Get-CrewHandoffPath $cfg.handoffPath
# Absent means TRUE since 0.19.52, so this cannot be a bare `-eq $true`:
# that reads an unset key as false and would put this flavour one
# behind the .sh on every config written before the change.
$autoWrapUp = if ($null -ne $cfg.autoWrapUp) { $cfg.autoWrapUp -eq $true } else { $true }
# reserveTokens: absolute headroom floor, in tokens. Absent -> 100k. null or
# <=0 -> off, i.e. the old pure-percentage behaviour. See the threshold below.
# PSObject.Properties, not truthiness: an explicit 0 means "off", and a missing
# key means 100k, and $cfg.reserveTokens is 0-ish for both.
[long]$reserve = 0
if ($cfg.PSObject.Properties['reserveTokens']) {
  $rt = $cfg.reserveTokens
  [long]$reserve = if ($null -eq $rt) { 0 } else { [long]$rt }
  if ($reserve -lt 0) { $reserve = 0 }
}

# Read the ACTUAL window occupancy, not a guess at it.
#
# Every assistant turn in the transcript carries message.usage, and the last one
# holds the real prompt size: input + cache_read + cache_creation. That IS the
# context window, measured by the thing that filled it.
#
# This replaced a file-size heuristic (bytes/4*0.75) that the bash flavour had
# already dropped. The transcript is cumulative - it keeps every turn ever
# written, including ones a compaction already discarded - so file size measures
# how much a session has produced, not how full the window is. Measured on real
# Windows sessions the heuristic read 195%, 158% and 664% of a 200k budget: it
# fired on turn one, every session.

# Known context windows, first match wins, so the specific keys sit above the
# generic ones. The Claude 5 family (fable, opus-5, sonnet-5) ships with 1M
# natively; the 4.x generation is 200k unless the id carries a "[1m]" suffix -
# and the transcript often records the base id without it, so this table is a
# starting point, not the last word. The observed high-water mark below
# corrects it.
$windows = @(
  @("[1m]",     1000000),
  @("fable",    1000000),
  @("opus-5",   1000000),
  @("sonnet-5", 1000000),
  @("haiku",     200000),
  @("opus",      200000),
  @("sonnet",    200000)
)
$tiers = @(200000, 500000, 1000000, 2000000)

$last = $null; $model = ""; [long]$peak = 0; [long]$mainBytes = 0
# A compaction writes a boundary record; a usage record from before it
# describes a window that no longer exists. See $why below.
[long]$lineNo = 0; [long]$lastAt = -1; [long]$boundaryAt = -1
try {
  foreach ($line in [System.IO.File]::ReadLines($d.transcript_path)) {
    if (-not $line) { continue }
    # Subagent turns are not main-window occupancy: the main window only ever
    # sees the agent's returned summary. Current builds keep them in
    # <session>/subagents/*.jsonl, which this never opens; older builds wrote
    # them inline flagged isSidechain. Skip those - from the byte count too, so
    # the size fallback below does not count them either.
    if ($line -match '"isSidechain"\s*:\s*true') { continue }
    $lineNo++
    $mainBytes += [System.Text.Encoding]::UTF8.GetByteCount($line) + 1
    if ($line -match '"compact_boundary"|"isCompactSummary"\s*:\s*true') { $boundaryAt = $lineNo }
    if ($line.IndexOf('"usage"') -lt 0) { continue }
    try { $rec = $line | ConvertFrom-Json -ErrorAction Stop } catch { continue }
    $msg = $rec.message
    if ($null -eq $msg) { continue }
    $usage = $msg.usage
    if ($null -eq $usage -or -not $usage.PSObject.Properties['cache_read_input_tokens']) { continue }
    $last = $usage; $lastAt = $lineNo
    if ($msg.model -and -not ([string]$msg.model).StartsWith("<")) { $model = [string]$msg.model }
    [long]$tot = [long]$usage.input_tokens + [long]$usage.cache_read_input_tokens + [long]$usage.cache_creation_input_tokens
    if ($tot -gt $peak) { $peak = $tot }
  }
} catch { }

if ($null -ne $last) {
  [long]$used = [long]$last.input_tokens + [long]$last.cache_read_input_tokens + [long]$last.cache_creation_input_tokens
  $source = "exact"
} else {
  [long]$used = [math]::Floor($mainBytes / 4 * 0.75)
  $source = "estimated"
}

function Next-Tier([long]$above) {
  foreach ($t in $tiers) { if ($t -gt $above * 1.05) { return [long]$t } }
  return [long]($above * 2)
}

$known = $false
if ($configured -gt 0) {
  [long]$budget = $configured; $how = "configured"; $known = $true
} else {
  $low = $model.ToLowerInvariant()
  [long]$budget = 200000
  foreach ($w in $windows) { if ($low.IndexOf($w[0]) -ge 0) { $budget = [long]$w[1]; $known = $true; break } }
  $label = if ($model) { $model } else { "unknown" }
  $how = "auto:$label"
}

# Self-correct. If this session has already held more tokens than the budget
# claims the window is, the budget is wrong: a "[1m]" variant records its base
# id, and an older /crew:init pinned budgetTokens: 200000 into every config
# before the 1M models arrived. Observed usage cannot exceed the real window,
# so it is the better source - but ONLY a peak the window could not hold proves
# that. An earlier 95% margin bumped a correct 1M entry to the 2M tier once a
# session passed 950k, and the gate then never fired at all.
if ($peak -gt $budget) { $budget = Next-Tier $peak; $how = "$how+observed" }

if ($budget -le 0) { exit 0 }

# The threshold is the LATER of two rules, and the second one is why a 1M
# session is no longer cut short.
#
#   percentage: warnAt * budget      - what this always did
#   headroom:   budget - reserve     - never nag while this much is still free
#
# warnAt was tuned when every window was 200k, where 0.8 leaves 40k - about
# enough to finish a thought and write a handoff. The same 0.8 on a 1M window
# leaves 200k, a whole 200k session's worth of room, and asking for a handoff
# there throws away a fifth of the window. Taking the later of the two rules
# means the reserve can only ever push the warning LATER, never earlier: on a
# 200k window the percentage still wins (40k < 100k) and nothing changes, while
# on 1M the floor wins and the gate moves from 80% to 90%.
#
# warnAt <= 0 stays an unconditional "fire now" - it is the documented override
# and a floor that quietly outranked it would make it a lie.
if ($warnAt -le 0) {
  [long]$threshold = 0
} else {
  [long]$threshold = [math]::Floor($budget * $warnAt)
  if ($reserve -gt 0 -and ($budget - $reserve) -gt $threshold) {
    [long]$threshold = $budget - $reserve
  }
}
# Whether this reading may license a /clear -- the same rules, in the same
# order, as context-watch.sh. It still drives the nag either way; auto-clear
# acts only on a measurement of THIS window. Unknown is its own value.
if ($source -ne "exact") { $why = "estimated-from-transcript-size" }
elseif (-not $known) { $why = "unknown-window" }
elseif ($boundaryAt -gt $lastAt) { $why = "stale-reading-before-compaction" }
elseif ($used -le 0 -or $used -gt $budget) { $why = "implausible-reading" }
else { $why = "measured" }
$trusted = ($why -eq "measured")

if (Test-Path $marker) {
  if ($used -lt $threshold -and $source -eq "exact") {
    # A measured reading back under the threshold: the window shrank since the
    # wrap-up, so that crossing is over. Re-arm for the next one.
    # -Force: pwsh on Linux/macOS treats dotfiles as hidden and will not
    # remove them without it; harmless on Windows.
    Remove-Item -LiteralPath $marker, $sentMarker, $escalated -Force -ErrorAction SilentlyContinue
    exit 0
  }
  # T-0017: an armed wrap-up whose results are not on disk is fed back to the
  # model ONCE, never on stop_hook_active (that exits above). CreateNew makes
  # exactly one flavour escalate when both run; a session whose clear was
  # already sent is not nagged about it. Same rules as context-watch.sh.
  if (-not (Test-Path -LiteralPath $sentMarker)) {
    $wrapPy = Get-CrewWrapUpPython $cfg.autoClear
    if ($wrapPy) {
      $armed = @(Invoke-CrewWrapUpVerb $wrapPy @("wrapup-armed", "--root=$((Get-Location).Path)", "--session=$sessionId"))
      if ($armed.Count -gt 0 -and $armed[0] -eq "on") {
        $wrapWhy = @(Invoke-CrewWrapUpVerb $wrapPy @("wrapup-check", "--root=$((Get-Location).Path)"))
        $wrapWhy = if ($wrapWhy.Count -gt 0 -and $wrapWhy[0]) { $wrapWhy[0] } else { "the wrap-up check gave no answer" }
        $escalate = $false
        if ($wrapWhy -ne "ok") {
          try {
            $claim = [System.IO.File]::Open((Join-Path (Get-Location).Path $escalated), [System.IO.FileMode]::CreateNew)
            $claim.Close()
            $escalate = $true
          } catch { }
        }
        if ($escalate) {
          [Console]::Error.WriteLine("crew wrap-up incomplete: $wrapWhy. Fix exactly that, run /crew:handoff --wrap-up again, end the turn.")
          exit 2
        }
      }
    }
  }
  # This crossing was already asked about. Never block twice for it; the
  # handoff may have been written since, which is all auto-clear wants to know.
  Invoke-ContextWatchAutoClear $sessionId
  exit 0
}
if ($used -lt $threshold) { exit 0 }

# Claim the once-per-crossing gate ATOMICALLY. Both flavours are registered for
# Stop and, on Windows with Git Bash installed, both actually run - a
# test-then-create would let both pass the check and emit the same warning
# twice. CreateNew throws for whichever loses. The marker records which
# session asked and the reading behind it, so auto-clear can refuse a reading
# nobody should trust.
# Absolute path deliberately: [System.IO.File] resolves a relative path against
# [Environment]::CurrentDirectory, which Set-Location does NOT update, so a
# relative claim would land in whatever directory the hook was spawned from.
try {
  $claimPath = Join-Path (Get-Location).Path $marker
  $claim = [System.IO.File]::Open($claimPath, [System.IO.FileMode]::CreateNew)
  $markerJson = [ordered]@{
    session_id   = $sessionId
    requested_at = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
    used = $used; budget = $budget; source = $source
    trusted = $trusted; why = $why
  } | ConvertTo-Json -Compress
  $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($markerJson + "`n")
  $claim.Write($bytes, 0, $bytes.Length)
  $claim.Close()
} catch { exit 0 }

# Truncate, not round, to match the bash flavour's int().
$pctH    = [math]::Floor($used / $budget * 100)
$inv     = [Globalization.CultureInfo]::InvariantCulture
$usedH   = $used.ToString("N0", $inv)
$budgetH = $budget.ToString("N0", $inv)
$remainH = ([long][math]::Max(0, $budget - $used)).ToString("N0", $inv)
$threshH = $threshold.ToString("N0", $inv)
$reserveH = $reserve.ToString("N0", $inv)
$warnPct = [long][math]::Floor($warnAt * 100)

# Report the absolute numbers, not only the percentage. A budgetTokens that does
# not match the model in use is otherwise invisible - it just makes the gate
# fire early forever, and a warning that is always on is one nobody reads.
$budgetNote = " Set context.budgetTokens in $cfgShown to pin it."
if ($how -eq "configured+observed") {
  $budgetNote = @"
 context.budgetTokens in $cfgShown says a smaller window,
but this session has already held more than that - and observed usage cannot
exceed the real window, so the larger figure wins. That pin is stale; set it to
null to let crew work the window out from the model.
"@.TrimEnd()
} elseif ($how -like "auto:*+observed") {
  $budgetNote = @"
 The model's id said a smaller window, but this session has
already held more than that - and observed usage cannot exceed the real window,
so the larger figure wins. A 1M variant reports its base model id, which is why
the id alone is not trusted. Pin it with context.budgetTokens if you prefer.
"@.TrimEnd()
} elseif ($how -eq "configured") {
  $budgetNote = @"
 That came from $cfgShown. Remove it to let crew work the
window out from the model and this session's own usage.
"@.TrimEnd()
}

$note = ""
if ($source -eq "estimated") {
  $note = @"

This figure is a fallback estimate from transcript size, not a measurement -
no usage record was found yet. It reads high after a compaction.
"@
}
$leftNote = ""
if ($script:CrewHandoffPathLeft) {
  $leftNote = @"

context.handoffPath in $cfgShown leaves this checkout, so the handoff goes
to $handoff here instead.
"@
}
$note += $leftNote

# Name the rule that fired. A percentage alone cannot explain why an 800k
# reading on a 1M window said nothing and 900k did.
if ($reserve -le 0) {
  $threshNote = @"
Threshold: $threshH tokens - warnAt $warnPct% of the window.
context.reserveTokens is off, so no headroom floor applies.
"@.TrimEnd()
} else {
  $threshNote = @"
Threshold: $threshH tokens - the later of warnAt $warnPct% and the
last $reserveH tokens (context.reserveTokens), so a large window is not cut
short by a percentage tuned for a small one.
"@.TrimEnd()
}

# T-0017: armed, the warning IS the wrap-up procedure, and supersedes both
# messages below; the text comes from crew_autocycle, as in the .sh flavour.
# Unarmed, no python, or any error: today's message, unchanged.
$wrapPy = Get-CrewWrapUpPython $cfg.autoClear
if ($wrapPy) {
  $wrapMsg = @(Invoke-CrewWrapUpVerb $wrapPy @("wrapup-message", "--root=$((Get-Location).Path)",
                                                "--session=$sessionId", "--pct=$pctH"))
  if ($wrapMsg.Count -gt 0 -and $wrapMsg[0]) {
    [Console]::Error.WriteLine(($wrapMsg -join "`n"))
    exit 2
  }
}

if ($autoWrapUp) {
[Console]::Error.WriteLine(@"
You are at roughly $pctH% of the context budget. Reach a stopping point
now: finish or safely abandon the change in flight, write $handoff per the
crew-context skill, update the ticket, then tell the user the session is
ready to clear. Do not start new work.$leftNote
"@)
} else {
[Console]::Error.WriteLine(@"
Context: $usedH of $budgetH tokens ($pctH%), read from the transcript's
last usage record. Headroom left: $remainH tokens.$note

Budget source: $how.$budgetNote

$threshNote

Before ending this turn, write the handoff note to $handoff following the
crew-context skill. Keep it to pointers and one short "next action" - do not
write a long narrative summary. A session this deep into its context is the
least reliable narrator of what it just did; the files are more trustworthy
than the recollection.

Then tell me the note is ready so I can /clear or /compact. Do not start new
work in this session.
"@)
}
exit 2
