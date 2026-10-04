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

# Raw BYTES, not [Console]::In.ReadToEnd(): event_claim.py hashes the payload,
# and the bash twin hands it the bytes as received.
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
  # checkout -- absolute, `..`, or through a link -- with a warning on stderr.
  # Twin of crew_state.handoff_path (crew_freshness.contained_path), stricter
  # on links: 5.1 cannot resolve one as realpath does, so any link between the
  # root and the target reads as leaving. In a linked worktree inheriting the
  # main checkout's config (L-0680) an absolute value would name the main
  # checkout's file. Copied verbatim into handoff-read.ps1, handoff-write.ps1
  # and context-watch.ps1; test_worktree_config_shell.py holds the copies equal.
  $default = '.work/HANDOFF.md'
  if (-not ($Value -is [string]) -or -not $Value.Trim()) { return $default }
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
  if ($inside) { return $full.Substring($base.Length + 1) }
  [Console]::Error.WriteLine("crew: context.handoffPath leaves this checkout - using $default")
  return $default
}

$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$stdinBytes = $memStream.ToArray()
$raw = [System.Text.Encoding]::UTF8.GetString($stdinBytes).TrimStart([char]0xFEFF)
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue
# .crew/crew.json alone is enough for the T-0006 PreCompact record below
# (/crew:migrate may retire .crew/config.json); the transcript copy and the
# skeleton handoff further down still need .crew/config.json, as before.
# L-0680: the resolved repo config (Get-CrewRepoConfigDir, T-0096): a linked
# worktree with none of its own reads the main checkout's; own files win whole;
# `unknown` reads only the own .crew/. The transcripts, the record and the
# handoff skeleton are still written here, in this checkout.
$repoCfg = Get-CrewRepoConfigDir '.'
$cfgPath = Join-Path $repoCfg.Dir 'config.json'
# Own or unknown, the resolved directory IS this checkout's .crew/, so that
# branch keeps the literal gate (tests/sabotage_resume.py anchors on its text).
if ($repoCfg.Source -eq 'main') {
  if (-not (Test-Path -LiteralPath $cfgPath -PathType Leaf) -and
      -not (Test-Path -LiteralPath (Join-Path $repoCfg.Dir 'crew.json') -PathType Leaf)) { exit 0 }
} else {
  if (-not (Test-Path ".crew/config.json") -and -not (Test-Path ".crew/crew.json")) { exit 0 }
}

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

# T-0006: record how this compaction started, keyed on the session, so a
# SessionStart `compact` may auto-resume only after a typed /compact (an
# automatic one can continue the in-flight turn). crew_resume.py writes it
# from the raw payload bytes, so both flavours record the same thing. No
# python, no record -- and no record means the compact waits. The previous
# record for this session is removed FIRST, without python, so a compact
# whose own record never lands cannot inherit an earlier `manual`; an
# unreadable session id removes every record.
$precompactKey = ([string]$d.session_id) -replace '[^A-Za-z0-9_-]', '_'
if ($precompactKey.Length -gt 100) { $precompactKey = $precompactKey.Substring(0, 100) }
$precompactCommon = (git rev-parse --git-common-dir 2>$null)
$precompactDir = if ($precompactCommon) { Join-Path $precompactCommon 'crew' } else { '.work/crew' }
if ($precompactKey) {
  Remove-Item -LiteralPath (Join-Path $precompactDir "precompact-$precompactKey.json") -Force -ErrorAction SilentlyContinue
  # T-0042: a record Remove-Item could not remove says nothing about THIS
  # compact. Mark it, so decide refuses it even when python never runs.
  if (Test-Path -LiteralPath (Join-Path $precompactDir "precompact-$precompactKey.json")) {
    New-Item -ItemType File -Force -Path (Join-Path $precompactDir "precompact-$precompactKey.stuck") -ErrorAction SilentlyContinue | Out-Null
  }
} else {
  Remove-Item -Path (Join-Path $precompactDir 'precompact-*.json') -Force -ErrorAction SilentlyContinue
}
$resumePy = Resolve-CrewPython
if ($resumePy) {
  try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $resumePy
    Set-CrewProcessArguments $psi @((Join-Path $PSScriptRoot 'crew_resume.py'), 'precompact', '--root', '.')
    $psi.WorkingDirectory = (Get-Location).Path
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $null = $proc.StandardOutput.ReadToEndAsync()
    $null = $proc.StandardError.ReadToEndAsync()
    $proc.StandardInput.BaseStream.Write($stdinBytes, 0, $stdinBytes.Length)
    $proc.StandardInput.BaseStream.Flush()
    $proc.StandardInput.Close()
    if (-not $proc.WaitForExit(10000)) { try { $proc.Kill() } catch { } }
  } catch { }
}
if (-not (Test-Path -LiteralPath $cfgPath -PathType Leaf)) {
  # A crew.json-only repo: the record above is all this hook does there.
  Complete-CrewEventClaim $claim
  exit 0
}
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
    $k = (Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json).context.keepTranscripts
    # [long] too: PowerShell 7's ConvertFrom-Json reads a JSON integer as Int64,
    # clamped to Int32.MaxValue -- a bare [int] cast throws past it, which left
    # 5 and deleted what the user kept. An integer only, as documented: a digit
    # string, a bool or a negative keeps 5, the same as handoff-write.sh.
    if (($k -is [int] -or $k -is [long]) -and $k -ge 0) { $keep = [int][math]::Min([long]$k, [long][int]::MaxValue) }
  } catch { }
  Get-ChildItem ".crew/transcripts/*.jsonl" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

$cfg  = Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json
$path = Get-CrewHandoffPath $cfg.context.handoffPath
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
