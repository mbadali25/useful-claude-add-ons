# PreToolUse plan-approval + scope guard on Write|Edit|MultiEdit|NotebookEdit,
# and the approval-forgery check on Bash|PowerShell. PowerShell twin of
# scope-guard.sh -- both delegate to scope_guard.py, so neither can drift from
# the other. Exit 0 allows, exit 2 refuses. No python, or python not reaching
# a decision, fails CLOSED unless the config provably sets scope.mode off.
param(
  # Probe seam, the twin of role-write-guard.ps1's -PrintPython.
  [switch]$PrintPython
)

# Flavour guard, first executable statement: `$env:OS` is 'Windows_NT' on
# both Windows PowerShell 5.1 and PowerShell 7 and unset elsewhere. Not
# `$IsWindows`, which does not exist in 5.1.
if ($env:OS -ne 'Windows_NT') { exit 0 }

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

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
  # L-0690: how the probe ended, for the caller to print. Set on every return
  # with the result and memoized with it; this function writes nothing.
  #   $script:CrewPythonOutcome  found | not-found | rejected | timed-out
  #   $script:CrewPythonTrail    a summary line, then one line per candidate
  # timed-out is "could not tell": a candidate was killed at its bound, its
  # stdout was not read in time, or the 8s budget ran out with a candidate
  # untried. rejected: every candidate launched (or failed to launch) and
  # answered inside its bound, and none was a python. not-found: nothing on
  # PATH reached a launch.
  $crewPythonRows = New-Object System.Collections.Generic.List[string]
  $crewPythonTimedOut = $false
  $crewPythonLaunched = $false
  $crewPythonSpent = $false
  $crewPythonFound = ''
  # ONE probe, byte for byte in the four review/gate harness .ps1 hooks, with
  # its outcome and trail (L-0690); the other carriers keep the pre-L-0690
  # copy until a follow-up rejoins them. Both groups are asserted by
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
    if ($crewPythonFound -or $crewPythonSpent) { break }
    $candidates = @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)
    foreach ($cmd in $candidates) {
      if (-not $cmd.Source) { continue }
      $crewPythonBegan = [int]$crewPythonDeadline.Elapsed.TotalMilliseconds
      if ($crewPythonRealWindows) {
        $crewPythonExt = [System.IO.Path]::GetExtension($cmd.Source)
        if ($crewPythonNativeExts -notcontains $crewPythonExt) {
          Write-Verbose "Resolve-CrewPython: skipping '$($cmd.Source)' - not natively launchable on Windows (extension '$crewPythonExt' outside .exe/.com/.cmd/.bat)"
          $crewPythonRows.Add("$name $($cmd.Source) 0 ms skipped-extension")
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
        # The walk stops here; later candidates are not enumerated.
        $crewPythonRows.Add("$name $($cmd.Source) 0 ms not-tried-budget-spent")
        $crewPythonTimedOut = $true
        $crewPythonSpent = $true
        break
      }
      $crewPythonWaitMs = [Math]::Min(3000, $crewPythonRemainingMs)
      $real = $null
      $crewPythonVerdict = 'start-failed'
      $crewPythonLaunched = $true
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
          $crewPythonVerdict = "killed-at-bound $crewPythonWaitMs ms"
          $crewPythonTimedOut = $true
        } elseif ($proc.ExitCode -ne 0) {
          $crewPythonVerdict = "exit-nonzero $($proc.ExitCode)"
        } elseif (-not $outTask.Wait(1000)) {
          $crewPythonVerdict = 'output-read-timeout'
          $crewPythonTimedOut = $true
        } else {
          $crewPythonVerdict = 'not-python-proof'
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
      if ($real -and -not (Test-Path -LiteralPath $real -PathType Leaf)) {
        $crewPythonVerdict = 'exe-missing'
        $real = $null
      }
      if ($real) { $crewPythonVerdict = 'accepted' }
      $crewPythonTook = [int]$crewPythonDeadline.Elapsed.TotalMilliseconds - $crewPythonBegan
      $crewPythonRows.Add("$name $($cmd.Source) $crewPythonTook ms $crewPythonVerdict")
      if (-not $real) { continue }
      $crewPythonFound = $real
      break
    }
  }
  $crewPythonOutcome = if ($crewPythonFound) { 'found' } elseif ($crewPythonTimedOut) { 'timed-out' } elseif ($crewPythonLaunched) { 'rejected' } else { 'not-found' }
  $crewPythonTrail = New-Object System.Collections.Generic.List[string]
  $crewPythonTrail.Add("python probe: $crewPythonOutcome after $([int]$crewPythonDeadline.Elapsed.TotalMilliseconds) ms (budget 8000 ms, 3000 ms per candidate)")
  for ($i = 0; $i -lt [Math]::Min(8, $crewPythonRows.Count); $i++) {
    $crewPythonTrail.Add('python probe:   ' + $crewPythonRows[$i])
  }
  if ($crewPythonRows.Count -gt 8) { $crewPythonTrail.Add("python probe:   (+$($crewPythonRows.Count - 8) more)") }
  $script:CrewPythonOutcome = $crewPythonOutcome
  $script:CrewPythonTrail = $crewPythonTrail.ToArray()
  $script:CrewPythonMemoDone = $true
  $script:CrewPythonMemoResult = $crewPythonFound
  return $crewPythonFound
}

function Write-CrewPythonTrail {
  # L-0690: the probe's trail (Resolve-CrewPython's $script:CrewPythonTrail) on
  # stderr, once per process, after the message about the probe's outcome.
  if ($script:CrewPythonTrailShown) { return }
  $script:CrewPythonTrailShown = $true
  foreach ($crewTrailLine in @($script:CrewPythonTrail)) {
    if ($crewTrailLine) { [Console]::Error.WriteLine($crewTrailLine) }
  }
}

if ($PrintPython) {
  $crewPrinted = Resolve-CrewPython
  Write-Output $crewPrinted
  # L-0690: stdout is the path or an empty line, as before; the trail of a
  # probe that found nothing goes to stderr.
  if (-not $crewPrinted) { Write-CrewPythonTrail }
  exit 0
}

# Raw BYTES, not [Console]::In.ReadToEnd(), which decodes with the OEM
# codepage on 5.1 -- the reason role-write-guard.ps1 reads this way.
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$stdinBytes = $memStream.ToArray()
if ($stdinBytes.Length -ge 3 -and $stdinBytes[0] -eq 0xEF -and
    $stdinBytes[1] -eq 0xBB -and $stdinBytes[2] -eq 0xBF) {
  if ($stdinBytes.Length -gt 3) {
    $stdinBytes = $stdinBytes[3..($stdinBytes.Length - 1)]
  } else {
    $stdinBytes = [byte[]]@()
  }
}
$raw = [System.Text.Encoding]::UTF8.GetString($stdinBytes)

# BYTE-FOR-BYTE the copy in the other scope wrapper (asserted by the tests);
# the twin of the .sh `_scope_provably_off`. True only when
# `.crew/config.json` PROVABLY leaves the scope hooks off: the file is absent,
# or System.Text.Json (strict: no trailing commas, comments, single quotes or
# bare keys) parses it as one object with exactly one "scope" property, whose
# object has exactly one "mode" property, and that mode is the string "off".
# NOT ConvertFrom-Json: on PowerShell 7 it accepts `{"scope":{"mode":"off"},}`,
# which python reads as corrupt and therefore block. Where System.Text.Json is
# not loadable (Windows PowerShell 5.1) nothing is provable, so a present
# config fails closed until python is available. Every shape it cannot prove
# is NOT off: corrupt, an unknown mode, report, auto, block, or no scope key.
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

function Test-ScopeProvablyOff {
  $projectDir = $env:CLAUDE_PROJECT_DIR
  if (-not $projectDir) { $projectDir = (Get-Location).Path }
  # L-0681: the resolved file (Get-CrewRepoConfigDir, T-0096), the one
  # scope_guard.py reads; `unknown` (git could not tell) is never proof.
  $repoCfg = Get-CrewRepoConfigDir $projectDir
  if ($repoCfg.Source -eq 'unknown') { return $false }
  $configPath = Join-Path $repoCfg.Dir 'config.json'
  $item = Get-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue
  if (-not $item -and -not (Test-Path -LiteralPath $configPath)) { return $true }
  if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { return $false }
  try {
    $text = [System.IO.File]::ReadAllText($configPath)
    if (([regex]::Matches($text, '"scope"')).Count -ne 1) { return $false }
    $doc = [System.Text.Json.JsonDocument]::Parse($text)
    try {
      $root = $doc.RootElement
      if ($root.ValueKind -ne [System.Text.Json.JsonValueKind]::Object) { return $false }
      $scopes = @($root.EnumerateObject() | Where-Object { $_.Name -ceq 'scope' })
      if ($scopes.Count -ne 1) { return $false }
      $scope = $scopes[0].Value
      if ($scope.ValueKind -ne [System.Text.Json.JsonValueKind]::Object) { return $false }
      $modes = @($scope.EnumerateObject() | Where-Object { $_.Name -ceq 'mode' })
      if ($modes.Count -ne 1) { return $false }
      $mode = $modes[0].Value
      if ($mode.ValueKind -ne [System.Text.Json.JsonValueKind]::String) { return $false }
      return ($mode.GetString() -ceq 'off')
    } finally {
      $doc.Dispose()
    }
  } catch {
    return $false
  }
}

$py = Resolve-CrewPython
if (-not $py) {
  # L-0690: a probe that ran out of time is "could not tell", never "no python".
  $crewTimedOut = $script:CrewPythonOutcome -eq 'timed-out'
  if (Test-ScopeProvablyOff) {
    if ($crewTimedOut) {
      [Console]::Error.WriteLine("scope-guard: the python probe timed out - not judged (scope.mode is off).")
    } else {
      [Console]::Error.WriteLine("scope-guard: no usable python - not judged (scope.mode is off).")
    }
    Write-CrewPythonTrail
    exit 0
  }
  if ($crewTimedOut) {
    [Console]::Error.WriteLine("SCOPE GUARD: the python probe timed out - could not tell whether python is usable; failing closed because .crew/config.json does not provably set scope.mode off.")
  } else {
    [Console]::Error.WriteLine("SCOPE GUARD: no usable python - failing closed because .crew/config.json does not provably set scope.mode off.")
  }
  Write-CrewPythonTrail
  exit 2
}

$prevConsoleEncoding = [Console]::OutputEncoding
$prevOutputEncodingVar = $OutputEncoding
$prevPythonUtf8 = $env:PYTHONUTF8
$prevPythonIoEncoding = $env:PYTHONIOENCODING
$exitCode = $null
try {
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  $global:LASTEXITCODE = $null
  $raw | & $py (Join-Path $dir 'scope_guard.py')
  $exitCode = $LASTEXITCODE
} catch {
  $exitCode = $null
} finally {
  [Console]::OutputEncoding = $prevConsoleEncoding
  $OutputEncoding = $prevOutputEncodingVar
  $env:PYTHONUTF8 = $prevPythonUtf8
  $env:PYTHONIOENCODING = $prevPythonIoEncoding
}

# scope_guard.py only ever exits 0 or 2. Anything else -- including no exit code
# at all, which `exit $LASTEXITCODE` would turn into a silent 0 -- means python
# never reached a decision.
if ($exitCode -ne 0 -and $exitCode -ne 2) {
  if (Test-ScopeProvablyOff) {
    [Console]::Error.WriteLine("scope-guard: scope_guard.py did not run to a decision (exit $exitCode); not judged (scope.mode is off).")
    exit 0
  }
  [Console]::Error.WriteLine("SCOPE GUARD: scope_guard.py did not run to a decision (exit $exitCode); failing closed because .crew/config.json does not provably set scope.mode off.")
  exit 2
}
exit $exitCode
