# PreToolUse deploy gate for the PowerShell tool. Mirrors promote-gate.sh.
# Fires only on a command matching a `deploy` entry in .crew/verify.json
# -> environments. Exit 2 blocks.

# L-0703: Resolve-CrewPython below is the byte-identical copy every crew .ps1
# carries (test_ps1_python_probe.py asserts it), and its best-effort cleanup
# catches are empty by design (a kill or dispose that fails changes nothing the
# probe decides). The suppression is script-wide because PSScriptAnalyzer reads
# it only from a param block, and the copy may not be edited to carry its own.
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingEmptyCatchBlock', '', Justification = 'Resolve-CrewPython copy: best-effort cleanup catches')]
param()

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

# L-0703: one deadline for the whole gate, 16s, under the 20s hook timeout
# (hooks.json) with room for the helper's 2s reap. Measured from this
# process's own start, so PowerShell's start-up (seconds on a cold, scanned
# host) and Resolve-CrewPython's probe (up to 8s) both count against it. The
# review search below gets only what is left.
$gateDeadline = 16
try { $gateStart = [DateTimeOffset](Get-Process -Id $PID -ErrorAction Stop).StartTime }
catch { $gateStart = [DateTimeOffset]::Now }
$gateDeadlineEpoch = $gateStart.ToUnixTimeSeconds() + $gateDeadline

$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cmd = $d.tool_input.command
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root -ErrorAction SilentlyContinue

# L-0664: the workflow-dispatch read below runs T-0062's _promote_dispatch.py,
# so this flavour resolves python with the one probe every crew .ps1 carries
# (test_ps1_python_probe.py holds the copies byte-identical).
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


# T-0505, the twin of promote-gate.sh's block: "no map" means none in the
# working copy AND none committed; an uncommitted change to the map (edit,
# deletion, untracked file) is found by comparing `git hash-object` with HEAD's
# blob, which skip-worktree/assume-unchanged cannot silence, and a dirty map is
# matched against the committed one too, so renaming the deploy command in an
# uncommitted edit cannot make it match nothing.
# L-0703 review r2, the twin of promote-gate.sh's block: a map that exists but
# is neither a regular file nor a directory (a FIFO, a socket, a device) would
# hold `git hash-object` below, and Get-Content after it, past the hook timeout
# - which is not a block. Refuse it here, before anything opens it. This hook
# runs for the PowerShell tool on any OS, so the check is on the item, not on
# the OS: UnixStat (pwsh 7.4+) is $null on Windows, which has no such files in
# the tree. A link is judged by what it points at, as the .sh's `-f` does.
$mapItem = Get-Item -LiteralPath .crew/verify.json -Force -ErrorAction SilentlyContinue
if ($mapItem -and $mapItem.LinkTarget) {
  $mapTarget = try { $mapItem.ResolveLinkTarget($true) } catch { $null }
  $mapItem = if ($mapTarget -and $mapTarget.Exists) { Get-Item -LiteralPath $mapTarget.FullName -Force -ErrorAction SilentlyContinue } else { $null }
}
$mapStat = if ($mapItem) { $mapItem.PSObject.Properties['UnixStat'] } else { $null }
if ($mapStat -and $mapStat.Value -and @('File', 'Directory') -notcontains "$($mapStat.Value.ItemType)") {
  [Console]::Error.WriteLine("PROMOTION BLOCKED: .crew/verify.json is not a regular file (it is a $($mapStat.Value.ItemType)), so crew cannot read the deployment map without hanging. This is not a pass. Replace it with the map file.")
  exit 2
}
$headMap = (git rev-parse -q --verify "HEAD:./.crew/verify.json" 2>$null)
$mapDirty = $null
$mapPresent = Test-Path .crew/verify.json
if (-not $mapPresent) {
  if (-not $headMap) { exit 0 }
  $mapDirty = "deleted, and committed at HEAD"
} elseif ($headMap) {
  $workMap = (git hash-object -- .crew/verify.json 2>$null)
  if (-not $workMap) { $mapDirty = "could not be hashed to compare with HEAD" }
  elseif ($workMap -ne $headMap) { $mapDirty = "differs from HEAD" }
} elseif ((git ls-files --others --exclude-standard -- .crew/verify.json 2>$null)) {
  $mapDirty = "untracked - in no commit"
}

# Every way the map can be unreadable ends here, in one message, because the
# reader's next action is the same for all of them: look at the file.
function Deny-UnreadableMap([string]$Why) {
  [Console]::Error.WriteLine("PROMOTION BLOCKED: $Why")
  [Console]::Error.WriteLine("  This is NOT a pass. Crew cannot tell whether this command deploys, so it")
  [Console]::Error.WriteLine("  cannot tell whether a pre-deploy gate applies to it. Fix .crew/verify.json,")
  [Console]::Error.WriteLine("  or delete it if this repo should not be gated.")
  exit 2
}

# THE RULE (L-1503), shared word for word with promote-gate.sh so both
# flavours choose the same environment for the same command:
#   - normalise the command: drop every CR, then trailing newlines; a command
#     that is then empty or whitespace deploys nothing (the
#     IsNullOrWhiteSpace exit above);
#   - a declared command matches when the command CONTAINS it (L-0689: a
#     fragment of a declared command is no deploy),
#     literally, ignoring case (OrdinalIgnoreCase; the .sh folds each
#     character's simple upper case, which agrees on ASCII and all but 29 BMP
#     characters - its fold() names them);
#   - every key the gate reads (`environments`, `deploy`, `requires`,
#     `rollback`, `rollbackReason`, `requireHuman`) is read ignoring case
#     (PowerShell property access does), and a map holding two keys that
#     differ only by case is refused (ConvertFrom-Json throws; the .sh refuses
#     it the same way, and now reads those keys ignoring case too). An EXACT
#     duplicate key is refused too (Find-DuplicateJsonKey): ConvertFrom-Json
#     keeps the last, so `"requireHuman": true, "requireHuman": false` read as
#     gated and applied as not gated;
#   - in the working map, `"deploy": null` and a `requireHuman` that is a list
#     or an object are malformed and refuse the map; `"deploy": []` and
#     `[""]` declare nothing;
#   - when more than one environment matches, ALL of them apply: their names
#     are joined (`staging,prod`) for every message and the in-flight marker,
#     and every one's `requires`, `rollback` and `requireHuman` is checked -
#     the union of their requirements. First-match made qa `target=Prod` and
#     production `target=prod` resolve differently per flavour and gated
#     prod's command as staging; blocking as ambiguous locked `git push` out
#     of a map with `git push staging main` and `git push prod main`.
# Case is ignored because on Windows `./Deploy.ps1` and `./deploy.ps1` are
# one file: a case-sensitive gate fails open there.
#
# Test-DeployMatch is the per-pair test. It used to be
# `$cmd -like "*$dep*"`, and `-like` reads `*`, `?` and `[set]` in a deploy as
# wildcards: `jq .items[0]` never matched itself, `deploy-*` claimed another
# environment's command, and `[`, `[]`, `[z-a]` or `[!-[]` threw
# WildcardPatternException, which skipped that environment and exited 0.
#
# Fail CLOSED when the comparison itself throws (a command that is not a
# string has no IndexOf, for one): that environment cannot be ruled out, and
# skipping it is the bug. Like the .sh's traceback path this is above the
# emergency lane - which environment is the very thing not known.
# The first key in $Json that repeats within one object - exactly, or ignoring
# case - or $null. ConvertFrom-Json cannot report an exact duplicate (it keeps
# the last), and Windows PowerShell 5.1's may not refuse case twins at all, so
# this walks the text itself: strings are skipped as units (a brace inside a
# value is not structure), and a key's escapes are decoded so `"a"` and
# `"\u0061"` are one key, as they are to python's json. Only called on text
# ConvertFrom-Json has already parsed, so it need not judge validity - except
# for what pwsh 7's ConvertFrom-Json reads and python's json refuses (#489
# N2): outside a string, a `/` (a comment) or a `'` (a single-quoted string),
# and in a key position anything but `"` or `}` (an unquoted key). Those
# return a refusal too, so both flavours refuse the same maps. A TRAILING
# COMMA is the one such form still read here and refused by the .sh (see
# the note at the parse below). Returns the predicate for "the map ...".
function Find-DuplicateJsonKey([string]$Json) {
  $stack = New-Object System.Collections.Stack
  $i = 0
  $n = $Json.Length
  while ($i -lt $n) {
    $ch = $Json[$i]
    if ($ch -ceq '"') {
      $sb = New-Object System.Text.StringBuilder
      $i++
      while ($i -lt $n -and $Json[$i] -cne '"') {
        if ($Json[$i] -ceq '\' -and $i + 1 -lt $n) {
          $e = [string]$Json[$i + 1]
          if ($e -ceq 'u') {
            [void]$sb.Append([char][Convert]::ToInt32($Json.Substring($i + 2, 4), 16)); $i += 6
          } else {
            if ($e -ceq 'n') { [void]$sb.Append("`n") }
            elseif ($e -ceq 't') { [void]$sb.Append("`t") }
            elseif ($e -ceq 'r') { [void]$sb.Append("`r") }
            elseif ($e -ceq 'b') { [void]$sb.Append([char]8) }
            elseif ($e -ceq 'f') { [void]$sb.Append([char]12) }
            else { [void]$sb.Append($e) }
            $i += 2
          }
        } else { [void]$sb.Append($Json[$i]); $i++ }
      }
      $i++
      if ($stack.Count -gt 0) {
        $top = $stack.Peek()
        if ($top -is [hashtable] -and $top.ExpectKey) {
          $key = $sb.ToString()
          $seen = $top.Seen
          if ($seen.ContainsKey($key)) {
            $first = $seen[$key]
            if ($first -ceq $key) { return "contains the duplicate key ``$key``, so which value is policy cannot be told" }
            return "contains keys with different casing (``$first`` and ``$key``), so which value is policy cannot be told"
          }
          $seen[$key] = $key
          $top.ExpectKey = $false
        }
      }
      continue
    }
    if ($ch -ceq '/') { return "contains a comment, which is not JSON (promote-gate.sh's parser refuses it)" }
    if ($ch -ceq "'") { return "contains a single-quoted string, which is not JSON (promote-gate.sh's parser refuses it)" }
    if ($stack.Count -gt 0 -and $ch -cne '}' -and " `t`r`n".IndexOf($ch) -lt 0) {
      $top = $stack.Peek()
      if ($top -is [hashtable] -and $top.ExpectKey) {
        return "contains an unquoted key, which is not JSON (promote-gate.sh's parser refuses it)"
      }
    }
    if ($ch -eq '{') {
      $stack.Push(@{ ExpectKey = $true; Seen = (New-Object 'System.Collections.Generic.Dictionary[string,string]' ([StringComparer]::OrdinalIgnoreCase)) })
    } elseif ($ch -eq '[') {
      $stack.Push('array')
    } elseif ($ch -eq '}' -or $ch -eq ']') {
      if ($stack.Count -gt 0) { [void]$stack.Pop() }
    } elseif ($ch -eq ',' -and $stack.Count -gt 0) {
      $top = $stack.Peek()
      if ($top -is [hashtable]) { $top.ExpectKey = $true }
    }
    $i++
  }
  return $null
}

# An environment name the gate cannot carry refuses the map (#489 F1): empty,
# holding a control character, or holding `,`, which joins a union's names in
# messages and the in-flight marker. The .sh split matched names on newlines,
# so `"a\nb"` became the lax environments `a` and `b`. promote-gate.sh
# applies the same test.
function Assert-EnvironmentName([string]$Name, [string]$Where) {
  $bad = ($Name.Length -eq 0) -or $Name.Contains(',')
  foreach ($c in $Name.ToCharArray()) { if ([char]::IsControl($c)) { $bad = $true } }
  if ($bad) {
    $shown = ($Name -replace "[\x00-\x1f\x7f-\x9f]", '?')
    Deny-UnreadableMap "$Where has the environment name ``$shown``, which is empty, holds a control character or holds a comma - a name the gate cannot report or record."
  }
}

function Test-DeployMatch($Cmd, [string]$Dep, [string]$EnvName) {
  try {
    $c = $Cmd.Replace("`r", "").TrimEnd("`n")
    return ($c.IndexOf($Dep, [StringComparison]::OrdinalIgnoreCase) -ge 0)
  } catch {
    [Console]::Error.WriteLine("PROMOTION BLOCKED: could not compare the command with environment ``$EnvName``'s deploy in .crew/verify.json: $($_.Exception.Message)")
    [Console]::Error.WriteLine("  This is NOT a pass. Crew cannot tell whether this command deploys to")
    [Console]::Error.WriteLine("  ``$EnvName``, so it will not skip that environment's pre-deploy gate.")
    exit 2
  }
}

# Fail CLOSED on a map that will not parse. An ABSENT verify.json (line 11) is
# a repo that opted out of gating; an UNPARSEABLE one is corruption, and the
# two are not the same fact. `catch { exit 0 }` treated them identically, so a
# single stray comma in verify.json silently removed every pre-deploy check
# while the deploy went ahead looking gated.
#
# `-ErrorAction Stop` is what makes the catch cover UNREADABLE as well as
# unparseable, and it is not decoration: Get-Content's failure is a
# NON-TERMINATING error, so without it a directory named .crew/verify.json left
# $vm null, the catch never fired, and `-not $vm.environments` two lines down
# read the corruption as "nothing declared" and exited 0. Measured, on Windows:
# exit 0 with a red Get-Content error on stderr and the deploy allowed.
#
# What this flavour CANNOT match is bash's strictness, and the difference is
# worth knowing rather than assuming away: PowerShell 7's ConvertFrom-Json
# ACCEPTS a trailing comma, which python's json rejects. So the stray comma
# that motivated this block is caught by promote-gate.sh and parses cleanly
# here. That asymmetry is safe in the direction that matters - this flavour
# still runs every check below on a map it could read. Comments and
# single-quoted or unquoted keys, which ConvertFrom-Json also reads, ARE
# refused here, by Find-DuplicateJsonKey's scan (L-1503).
# A dirty map is matched against the committed one too. A committed map that
# cannot be read or has no readable environments is could-not-tell: with the
# working map dirty, "matched nothing" would be a guess.
$envNames = @()
$allDeploys = @()
if ($mapDirty -and $headMap) {
  $blob = (git cat-file blob $headMap 2>$null)
  if ($LASTEXITCODE -ne 0) { Deny-UnreadableMap "the committed .crew/verify.json could not be read (git cat-file exited $LASTEXITCODE)." }
  try { $committed = ($blob -join "`n") | ConvertFrom-Json -ErrorAction Stop }
  catch { Deny-UnreadableMap "the committed .crew/verify.json does not parse: $($_.Exception.Message)" }
  $dup = Find-DuplicateJsonKey ($blob -join "`n")
  if ($dup) { Deny-UnreadableMap "the committed .crew/verify.json $dup." }
  $committedEnvs = $committed.PSObject.Properties['environments']
  if (-not $committedEnvs -or $committedEnvs.Value -isnot [System.Management.Automation.PSCustomObject]) {
    Deny-UnreadableMap "the committed .crew/verify.json holds no object of environments."
  }
  $hits = @()
  foreach ($p in $committedEnvs.Value.PSObject.Properties) { Assert-EnvironmentName $p.Name "the committed .crew/verify.json" }
  foreach ($p in $committedEnvs.Value.PSObject.Properties) {
    $declared = @($p.Value.deploy) | Where-Object { $_ -is [string] -and $_ }
    $allDeploys += $declared
    foreach ($dep in $declared) {
      if (Test-DeployMatch $cmd $dep $p.Name) { $hits += $p.Name; break }
    }
  }
  $envNames = $hits
  # With no working map, nothing more is read from it: a dispatch is still
  # read against the committed map below (L-0664), as promote-gate.sh does.
}

if ($mapPresent) {
try {
  $vmText = Get-Content .crew/verify.json -Raw -ErrorAction Stop
  $vm = $vmText | ConvertFrom-Json
} catch {
  Deny-UnreadableMap ".crew/verify.json could not be read or parsed, so no pre-deploy check ran. $($_.Exception.Message)"
}
$dup = Find-DuplicateJsonKey $vmText
if ($dup) { Deny-UnreadableMap ".crew/verify.json $dup." }
# The same absent/malformed split, one level in. `environments` ABSENT gates
# nothing, exactly like the bash flavour's `.get("environments", {})`.
# `environments` PRESENT and not an object is corruption: the property
# enumeration below finds no environment in it, so every deploy sailed through
# on "this command deploys nothing".
if ($vm -isnot [System.Management.Automation.PSCustomObject]) {
  Deny-UnreadableMap ".crew/verify.json does not hold a JSON object."
}
$envProperty = $vm.PSObject.Properties['environments']
# With the map dirty, a working map that lost `environments` still has the
# committed map's dispatches read below (L-0664 r1), as the .sh does.
if (-not $envProperty -and $envNames.Count -eq 0 -and -not $mapDirty) { exit 0 }
if ($envProperty -and $envProperty.Value -isnot [System.Management.Automation.PSCustomObject]) {
  Deny-UnreadableMap "``environments`` in .crew/verify.json is not an object, so no environment can be read out of it."
}

# Which environment does this command deploy to? Every one is checked, so a
# second match is found and refused as ambiguous rather than shadowed.
$hits = @()
if ($envNames.Count -eq 0) {
foreach ($p in $vm.environments.PSObject.Properties) { Assert-EnvironmentName $p.Name ".crew/verify.json" }
foreach ($p in $vm.environments.PSObject.Properties) {
  if ($p.Value -isnot [System.Management.Automation.PSCustomObject]) {
    Deny-UnreadableMap "environment ``$($p.Name)`` in .crew/verify.json is not an object."
  }
  # L-0648: the gate reads a `github` entry's sha rule, so a `github` that is
  # not an object or a non-empty list of objects is malformed (as in the .sh).
  $ghProp = $p.Value.PSObject.Properties['github']
  if ($ghProp) {
    $ghVal = $ghProp.Value
    $ghOk = ($null -ne $ghVal) -and ($ghVal -is [System.Management.Automation.PSCustomObject]) -or
            ($ghVal -is [array] -and $ghVal.Count -gt 0 -and
             @($ghVal | Where-Object { $_ -isnot [System.Management.Automation.PSCustomObject] }).Count -eq 0)
    if (-not $ghOk) {
      Deny-UnreadableMap "environment ``$($p.Name)`` in .crew/verify.json has a ``github`` that is not an object or a non-empty list of objects."
    }
  }
  $rhProp = $p.Value.PSObject.Properties['requireHuman']
  if ($rhProp -and ($rhProp.Value -is [array] -or $rhProp.Value -is [System.Management.Automation.PSCustomObject])) {
    Deny-UnreadableMap "environment ``$($p.Name)`` in .crew/verify.json has a ``requireHuman`` that is a list or an object, not true or false."
  }
  # A plain assignment, not `$declared = if (...) { $deployProp.Value }`: an
  # if-expression's output is pipeline output, which unrolls `[]` to $null, so
  # `"deploy": []` read as null and refused the map - every PowerShell command
  # in the repo blocked (#489 B1).
  $deployProp = $p.Value.PSObject.Properties['deploy']
  $declared = $null
  if ($deployProp) { $declared = $deployProp.Value }
  if ($deployProp -and $null -eq $declared) {
    Deny-UnreadableMap "environment ``$($p.Name)`` in .crew/verify.json has a ``deploy`` that is not a command or a list of commands (it is null)."
  }
  if ($null -ne $declared) {
    # A bare string is ONE command. Stated rather than left to the `foreach`,
    # which already treats it that way, because promote-gate.sh has to
    # normalise it explicitly (it iterated the string's characters) and the two
    # flavours must be reading the same shape for the same reason.
    if ($declared -is [string]) { $declared = @($declared) }
    if ($declared -isnot [array] -or @($declared | Where-Object { $_ -isnot [string] }).Count -gt 0) {
      Deny-UnreadableMap "environment ``$($p.Name)`` in .crew/verify.json has a ``deploy`` that is not a command or a list of commands."
    }
    $allDeploys += @($declared | Where-Object { $_ })
    foreach ($dep in $declared) {
      if ($dep -and (Test-DeployMatch $cmd $dep $p.Name)) { $hits += $p.Name; break }
    }
  }
}
$envNames = $hits
}
}
# Several matching environments are named together, `staging,prod`, in every
# message, skip row and the in-flight marker (`,`: verify-gate.sh greps the
# marker's name as an ERE, where `+` is a quantifier); their requirements are
# checked one by one below.
$envName = $envNames -join ','

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

# --- Emergency lane -------------------------------------------------------
#
# Twin of crew_incident_active / crew_incident_log in _common.sh, inline for
# the same reason as in verify-gate.ps1: a dot-sourced function is invisible
# to scripts/check-powershell.ps1's static call check. See
# hooks/scripts/crew_incident.py for the file format.
function Test-CrewIncidentActive {
  if (-not (Test-Path ".crew/incident.json")) { return $false }
  try {
    # standDown from the resolved repo config (T-0096); incident.json stays own.
    $c = Get-Content -LiteralPath (Join-Path (Get-CrewRepoConfigDir '.').Dir 'config.json') -Raw -ErrorAction Stop | ConvertFrom-Json
    if ($c.emergency -and $c.emergency.standDown -eq $false) { return $false }
  } catch { }
  try { $inc = Get-Content .crew/incident.json -Raw -ErrorAction Stop | ConvertFrom-Json }
  catch { return $false }
  if (-not $inc.expiresAtEpoch) { return $false }
  return ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -lt [long]$inc.expiresAtEpoch)
}

function Write-CrewIncidentSkip([string]$Gate, [string]$Detail) {
  if (-not (Test-Path ".crew")) { New-Item -ItemType Directory -Path ".crew" -Force | Out-Null }
  $log = ".crew/incident-skips.log"
  # The log is tab-separated and line-oriented, and a detail can carry an
  # environment name, a rollback path or a rollbackReason straight out of
  # .crew/verify.json - a tab or a newline in one would forge a row. _common.sh
  # and crew_incident.py normalise the same way.
  $Gate = $Gate -replace "[`t`r`n]", " "
  $Detail = $Detail -replace "[`t`r`n]", " "
  $row = "$Gate`t$Detail"
  # One row per gate+detail per incident, not per turn: the closing report is a
  # debt list, and the same unrun check is one debt however many turns declined
  # to run it. _common.sh applies the same rule.
  if (Test-Path $log) {
    foreach ($line in (Get-Content $log -ErrorAction SilentlyContinue)) {
      $parts = $line -split "`t", 2
      if ($parts.Count -eq 2 -and $parts[1] -eq $row) { return }
    }
  }
  $epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  Add-Content -Path $log -Value "$epoch`t$row" -Encoding utf8
}

# An open incident turns every block below into a recorded skip. The checks
# still RUN - they are file reads, not test suites, and the debt list is worth
# far more when it names the precondition that was unmet.
$incident = Test-CrewIncidentActive

$problems = New-Object System.Collections.Generic.List[string]
$sha = $null

# One refusal path for the tree checks below: a recorded skip during an
# incident, a block otherwise. Twin of block() in promote-gate.sh.
function Stop-Promotion([string]$Why) {
  $at = if ($script:sha) { $script:sha } else { "unknown-sha" }
  if ($incident) {
    Write-CrewIncidentSkip "promote" "$envName at ${at}: $Why"
    exit 0
  }
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName): $Why")
  exit 2
}

# L-0664, the twin of promote-gate.sh's T-0062 block: read the command as a
# workflow dispatch with the same helper and the same reader, told the command
# is PowerShell. `env<TAB>name` gates it as that environment's deploy too,
# `block<TAB>why` blocks (could not tell, or a declared workflow fitting no
# single environment), nothing adds nothing. It runs whether or not
# containment matched (group review r2): `./deploy-dev.sh; gh api ...
# inputs[environment]=production` matched development only, and production's
# preconditions went unchecked. A helper that fails is never "nothing". With
# no python, a command naming gh with `workflow` or `dispatches` outside the
# declared deploys it contains blocks when any declared deploy names them
# too: an unknown does not become "not a deploy".
$envName = if ($envNames.Count -eq 0) { "workflow dispatch" } else { $envNames -join ',' }
$py = Resolve-CrewPython
if (-not $py) {
  $looksLike = { param($t) ($t -match '(?i)(^|[^A-Za-z0-9_.-])gh([^A-Za-z0-9_.-]|$)') -and ($t -match '(?i)workflow|dispatches') }
  $rest = $cmd
  foreach ($dep in $allDeploys) {
    if ($dep) { $rest = [regex]::Replace($rest, [regex]::Escape($dep), ' ', 'IgnoreCase') }
  }
  if ((& $looksLike $rest) -and @($allDeploys | Where-Object { & $looksLike $_ }).Count -gt 0) {
    Stop-Promotion "python could not be found, so the gate cannot read this command as a workflow dispatch, and the map declares a dispatch deploy. This is not a pass. Install python 3, or put it on PATH."
  }
  if ($envNames.Count -eq 0) { exit 0 }
} else {
  $prevConsoleEncoding = [Console]::OutputEncoding
  $prevOutputEncodingVar = $OutputEncoding
  $prevPythonIoEncoding = $env:PYTHONIOENCODING
  $prevHeadMap = $env:CREW_HEAD_MAP
  $prevMapDirty = $env:CREW_MAP_DIRTY
  $dispatch = $null
  $dispatchExit = $null
  try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $env:PYTHONIOENCODING = 'utf-8'
    $env:CREW_HEAD_MAP = if ($headMap) { "$headMap" } else { '' }
    $env:CREW_MAP_DIRTY = if ($mapDirty) { "$mapDirty" } else { '' }
    $global:LASTEXITCODE = $null
    $dispatch = @($cmd | & $py (Join-Path $scriptDir '_promote_dispatch.py') --shell powershell -)
    $dispatchExit = $LASTEXITCODE
  } catch {
    $dispatchExit = $null
  } finally {
    [Console]::OutputEncoding = $prevConsoleEncoding
    $OutputEncoding = $prevOutputEncodingVar
    $env:PYTHONIOENCODING = $prevPythonIoEncoding
    $env:CREW_HEAD_MAP = $prevHeadMap
    $env:CREW_MAP_DIRTY = $prevMapDirty
  }
  if ($dispatchExit -ne 0) {
    Stop-Promotion "the command could not be read as a workflow dispatch (_promote_dispatch.py failed). This is not a pass."
  }
  foreach ($line in $dispatch) {
    $parts = "$line".Replace("`r", "").Split("`t", 2)
    if ($parts.Count -lt 2) { continue }
    if ($parts[0] -ceq 'block') { Stop-Promotion $parts[1] }
    if ($parts[0] -ceq 'env' -and $envNames -cnotcontains $parts[1]) { $envNames += $parts[1] }
  }
}
if ($envNames.Count -eq 0) { exit 0 }
$envName = $envNames -join ','

# WHICH tree (T-0505). Twin of the block in promote-gate.sh, whose header
# carries the full reasoning: the sha and the clean-tree check come from the
# tree the deploy RUNS FROM - the payload `cwd` (else the project dir), moved
# by a leading `cd`/`Set-Location` chain, named by any `git -C <dir>` - which
# must be a worktree of the SAME repository. Policy and state (.crew/verify.json,
# .work/PROMOTIONS.md, .crew/.approved-*, the rollback runbook, the incident
# files, .crew/.deploy-in-flight) stay in the project dir: they are
# per-checkout, gitignored state that a fresh worktree lacks and a throwaway
# one can forge. The rules here are PowerShell's, because this flavour judges
# PowerShell-tool commands; the branch between the twins is the tool.
if ($mapDirty) {
  Stop-Promotion ".crew/verify.json in the project dir ($((Get-Location).ProviderPath)) has uncommitted changes: it $mapDirty. The deploy map is policy; commit the change (it is then reviewed like any other) or revert it."
}
$projectTop = (git rev-parse --show-toplevel 2>$null)
if (-not $projectTop) { Stop-Promotion "not a git repository - cannot establish what is being deployed." }

function Resolve-Dir([string]$Base, [string]$Tok) {
  $t = $Tok
  if ($t -eq '~') { $t = $HOME }
  elseif ($t.StartsWith('~/') -or $t.StartsWith('~\')) { $t = Join-Path $HOME $t.Substring(2) }
  $candidate = if ([System.IO.Path]::IsPathRooted($t)) { $t } else { Join-Path $Base $t }
  if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { return $null }
  return (Resolve-Path -LiteralPath $candidate).ProviderPath
}
# The common dir identifies the repository: every linked worktree shares it.
function Get-CommonDir([string]$Dir) {
  $c = (git -C $Dir rev-parse --git-common-dir 2>$null)
  if (-not $c) { return $null }
  $p = if ([System.IO.Path]::IsPathRooted($c)) { $c } else { Join-Path $Dir $c }
  if (-not (Test-Path -LiteralPath $p)) { return $null }
  return ((Resolve-Path -LiteralPath $p).ProviderPath).TrimEnd('\', '/')
}

$base = (Get-Location).ProviderPath
if (-not [string]::IsNullOrWhiteSpace($d.cwd)) {
  $base = Resolve-Dir $base "$($d.cwd)"
  if (-not $base) { Stop-Promotion "the command runs from '$($d.cwd)', which does not exist, so it is not inside a git worktree - cannot establish what is being deployed." }
}

# A token: double-quoted, single-quoted, or a word; `)` ends a word so
# `$(git -C dir rev-parse HEAD)` reads `dir`. `$` or a backtick in anything but
# single quotes is expanded by PowerShell, so the gate cannot know it.
$tokenRx = '(?:"([^"]*)"|''([^'']*)''|([^\s;&|()]+))'
function Get-TokenValue($m, [int]$first) {
  if ($m.Groups[$first + 1].Success) { return @($m.Groups[$first + 1].Value, $false) }
  $v = if ($m.Groups[$first].Success) { $m.Groups[$first].Value } else { $m.Groups[$first + 2].Value }
  return @($v, ($v.Contains('$') -or $v.Contains('`')))
}
$cdRx = New-Object System.Text.RegularExpressions.Regex(('\G\s*(?:cd|chdir|sl|Set-Location|pushd|Push-Location)(?:\s+-(?:Literal)?Path)?\s+' + $tokenRx + '\s*(?:&&|;)'), 'IgnoreCase')
$pos = 0
while ($true) {
  $m = $cdRx.Match($cmd, $pos)
  if (-not $m.Success) { break }
  $val = Get-TokenValue $m 1
  if ($val[1] -or $val[0] -eq '-') { Stop-Promotion "cannot tell which directory the deploy runs from: '$($val[0])' is expanded by the shell, and the gate will not guess what it names. Use a literal path." }
  $next = Resolve-Dir $base $val[0]
  if (-not $next) { Stop-Promotion "cannot tell which directory the deploy runs from: 'cd $($val[0])' does not resolve from '$base'." }
  $base = $next
  $pos = $m.Index + $m.Length
}
# A directory change AFTER the leading chain, or git pointed at a repository
# by --git-dir/--work-tree/GIT_DIR: the deploy may read a tree the chain does
# not name, so refuse rather than judge the wrong one.
# As a WORD, after a separator, whitespace, a quote or a brace - deliberately
# broad, the twin of _promote_tree.py's _MIDCD: a directory change the chain did
# not take is could-not-tell, whatever form it is in.
$mid = [regex]::Match($cmd.Substring($pos), '(?:^|(?<=[\s;&|(){}''"`]))(?:cd|chdir|sl|Set-Location|pushd|popd|Push-Location|Pop-Location)(?=$|[\s;&|)''"`])', 'IgnoreCase')
if ($mid.Success) {
  Stop-Promotion "cannot tell which directory the deploy runs from: the command changes directory after it starts ('$($mid.Value.Trim())'). Put the cd first - 'cd <dir>; <deploy>' - so the gate judges the tree the deploy runs in."
}
$gitDir = [regex]::Match($cmd, '--git-dir\b|--work-tree\b|\bGIT_DIR\b|\bGIT_WORK_TREE\b')
if ($gitDir.Success) {
  Stop-Promotion "cannot tell which tree the deploy reads: '$($gitDir.Value)' points git at a repository by a route the gate does not follow. Use 'cd <dir>;' or 'git -C <dir>'."
}
# Other tools that change directory for what they run - env -C/--chdir,
# make -C/--directory, Start-Process -WorkingDirectory - are could-not-tell,
# not the deploy's tree: the deploy process still runs in the chain's directory.
$toolDir = [regex]::Match($cmd, '(?:^|(?<=[\s(;&|/`''"]))(?:env\b[^;&|\n]*?\s(?:-C|--chdir\b)|g?make\b[^;&|\n]*?\s(?:-C|--directory\b))|-WorkingDirectory\b', 'IgnoreCase')
if ($toolDir.Success) {
  Stop-Promotion "cannot tell which directory the deploy runs from: the command changes directory after it starts ('$($toolDir.Value.Trim())'). Put the cd first - 'cd <dir>; <deploy>' - so the gate judges the tree the deploy runs in."
}

# Which characters does the shell EXECUTE? Unquoted text and `$(...)`, even
# inside double quotes; not single-quoted text nor the literal part of double
# quotes, where `git -C x` is only words (Codex r1). Twin of executed() in
# _promote_tree.py, with PowerShell's backtick as the escape character.
function Get-Executed([string]$s) {
  $out = New-Object bool[] $s.Length
  $sub = New-Object bool[] $s.Length
  $stack = New-Object System.Collections.Generic.List[string]
  $stack.Add('U')
  $i = 0
  while ($i -lt $s.Length) {
    $c = $s[$i]; $top = $stack[$stack.Count - 1]
    $out[$i] = ($top -eq 'U' -or $top -eq 'X')
    $sub[$i] = ($top -eq 'X')
    if ($top -eq 'S') {
      if ($c -eq "'") { $stack.RemoveAt($stack.Count - 1) }
    } elseif ($c -eq '`') {
      if ($i + 1 -lt $s.Length) { $out[$i + 1] = $out[$i] }
      $i += 2; continue
    } elseif ($top -eq 'D' -and $c -eq '"') {
      $stack.RemoveAt($stack.Count - 1)
    } elseif ($c -eq '$' -and $i + 1 -lt $s.Length -and $s[$i + 1] -eq '(') {
      $stack.Add('X'); $out[$i + 1] = $true; $i += 2; continue
    } elseif (($top -eq 'U' -or $top -eq 'X') -and $c -eq "'") {
      $stack.Add('S'); $out[$i] = $false
    } elseif (($top -eq 'U' -or $top -eq 'X') -and $c -eq '"') {
      $stack.Add('D'); $out[$i] = $false
    } elseif ($top -eq 'X' -and $c -eq ')') {
      $stack.RemoveAt($stack.Count - 1)
    }
    $i++
  }
  return @(, $out) + @(, $sub)
}
$scan = Get-Executed $cmd
$live = $scan[0]
$inSub = $scan[1]

# git's GLOBAL options after each `git` word: -C <dir> once, -c <k=v>, a short
# no-value allowlist; anything else before the subcommand is could-not-tell.
$gitFlags = @('--no-pager', '-P', '--paginate', '-p', '--no-replace-objects', '--literal-pathspecs', '--no-optional-locks', '--no-lazy-fetch')
$argRx = [regex]('\G\s+' + $tokenRx)
$trees = New-Object System.Collections.Generic.List[string]
$runDirs = New-Object System.Collections.Generic.List[string]
$bare = $false
$notSure = "is not a form the gate reads with certainty (a shell-expanded path, an unlisted git option, git inside quoted text), and it will not guess. Use a literal 'cd <dir>;' or 'git -C <dir>'."
foreach ($m in [regex]::Matches($cmd, '(?:^|(?<=[\s(;&|/`''"]))git(?:\.exe)?(?=$|[\s;&|)''"`])', 'IgnoreCase')) {
  if (-not $live[$m.Index]) { Stop-Promotion "cannot tell which directory the deploy runs from: 'git' inside quoted text $notSure" }
  $p2 = $m.Index + $m.Length
  $dirs = New-Object System.Collections.Generic.List[string]
  while ($true) {
    $a = $argRx.Match($cmd, $p2)
    if (-not $a.Success) { break }
    $v = Get-TokenValue $a 1
    if ($v[1]) { Stop-Promotion "cannot tell which directory the deploy runs from: 'git $($v[0])' $notSure" }
    if (-not $v[0].StartsWith('-')) { break }
    if ($v[0] -ceq '-C' -or $v[0] -ceq '-c') {
      $b = $argRx.Match($cmd, $a.Index + $a.Length)
      if (-not $b.Success) { Stop-Promotion "cannot tell which directory the deploy runs from: 'git $($v[0])' with no value $notSure" }
      $bv = Get-TokenValue $b 1
      if ($v[0] -ceq '-C') {
        if ($bv[1] -or $bv[0] -eq '-') { Stop-Promotion "cannot tell which directory the deploy runs from: '$($bv[0])' $notSure" }
        $dirs.Add($bv[0])
      }
      $p2 = $b.Index + $b.Length; continue
    }
    if ($v[0].StartsWith('--git-dir') -or $v[0].StartsWith('--work-tree')) { Stop-Promotion "cannot tell which tree the deploy reads: '$($v[0])' points git at a repository by a route the gate does not follow. Use 'cd <dir>;' or 'git -C <dir>'." }
    if ($gitFlags -cnotcontains $v[0]) { Stop-Promotion "cannot tell which directory the deploy runs from: 'git global option $($v[0])' $notSure" }
    $p2 = $a.Index + $a.Length
  }
  if ($dirs.Count -gt 1) { Stop-Promotion "cannot tell which directory the deploy runs from: git -C given more than once $notSure" }
  if ($dirs.Count -eq 0) { $bare = $true; continue }
  $dir = Resolve-Dir $base $dirs[0]
  if (-not $dir) { Stop-Promotion "cannot tell which directory the deploy runs from: 'git -C $($dirs[0])' does not resolve from '$base'." }
  # Outside `$(...)` a git -C feeds the deploy nothing, so it may only name the
  # tree the deploy runs in (checked below); inside, it names the sha.
  if ($inSub[$m.Index]) { $trees.Add($dir) } else { $runDirs.Add($dir) }
}
# The sha comes from git -C's tree when there is one; the chain's directory is
# ALSO where the deploy process runs, so it is checked for dirt and repository
# below whatever -C says (Codex r1).
if ($trees.Count -eq 0 -or $bare) { $trees.Add($base) }
$runTop = (git -C $base rev-parse --show-toplevel 2>$null)
if (-not $runTop) { Stop-Promotion "the deploy runs from '$base', which is not inside a git worktree - cannot establish what is being deployed." }
foreach ($dir in $runDirs) {
  if ((git -C $dir rev-parse --show-toplevel 2>$null) -ne $runTop) {
    Stop-Promotion "the command names 'git -C $dir' outside a command substitution, which is not the tree the deploy runs in ('$runTop'). Use 'cd <dir>;' so the deploy runs there, or '`$(git -C <dir> ...)' to feed it a sha."
  }
}

$tree = $null
foreach ($dir in $trees) {
  $top = (git -C $dir rev-parse --show-toplevel 2>$null)
  if (-not $top) { Stop-Promotion "the deploy runs from '$dir', which is not inside a git worktree - cannot establish what is being deployed." }
  if (-not $tree) { $tree = $top }
  elseif ($top -ne $tree) { Stop-Promotion "the deploy command names more than one tree ('$tree' and '$top'), so which sha is being deployed is ambiguous. Run it from one tree." }
}

$treeCommon = Get-CommonDir $tree
$projectCommon = Get-CommonDir $projectTop
# Two failed lookups compare equal as two nulls; that is "could not tell".
if (-not $treeCommon -or -not $projectCommon) {
  Stop-Promotion "could not read the git common dir of '$tree' or of '$projectTop', so the gate cannot tell whether the deploy runs from this repository."
}
if ($treeCommon -ne $projectCommon) {
  Stop-Promotion "the deploy runs from '$tree', which is a worktree of a different repository than this project ('$projectTop'). Its sha has no PASS row, marker or map here."
}
if ($runTop -ne $tree -and (Get-CommonDir $runTop) -ne $projectCommon) {
  Stop-Promotion "the deploy process runs in '$runTop', which is not a worktree of this project ('$projectTop')."
}

$sha = (git -C $tree rev-parse --short HEAD 2>$null)
$full = (git -C $tree rev-parse HEAD 2>$null)
if (-not $sha) { Stop-Promotion "'$tree' has no commit at HEAD - cannot establish what is being deployed." }

# L-0648, the twin of promote-gate.sh's: a matched environment's `github`
# entry with a `shaInput` must get that input exactly once, as 40 lowercase
# hex, equal to the full HEAD of the tree judged here. The same helper decides
# it, told the command is PowerShell. With no python and a matched `github`
# entry the rule cannot be checked, which blocks; a failing helper blocks.
$ghMatched = @($envNames | Where-Object {
  $vm -and $vm.environments -and $vm.environments.PSObject.Properties[$_] -and
  $null -ne $vm.environments.PSObject.Properties[$_].Value.PSObject.Properties['github'] })
if ($ghMatched.Count -gt 0) {
  $ghPy = Resolve-CrewPython
  if (-not $ghPy) {
    Stop-Promotion "python could not be found, so the github entry's sha rule cannot be checked. This is not a pass. Install python 3, or put it on PATH."
  }
  $prevConsoleEncoding = [Console]::OutputEncoding
  $prevOutputEncodingVar = $OutputEncoding
  $prevPythonIoEncoding = $env:PYTHONIOENCODING
  $ghRule = $null
  $ghExit = $null
  try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $env:PYTHONIOENCODING = 'utf-8'
    $global:LASTEXITCODE = $null
    $ghRule = @($cmd | & $ghPy (Join-Path $scriptDir '_promote_github.py') --shell powershell --full "$full" --envs $envName -)
    $ghExit = $LASTEXITCODE
  } catch {
    $ghExit = $null
  } finally {
    [Console]::OutputEncoding = $prevConsoleEncoding
    $OutputEncoding = $prevOutputEncodingVar
    $env:PYTHONIOENCODING = $prevPythonIoEncoding
  }
  if ($ghExit -ne 0) {
    Stop-Promotion "the github entry's sha rule could not be checked (_promote_github.py failed). This is not a pass."
  }
  foreach ($line in $ghRule) {
    $parts = "$line".Replace("`r", "").Split("`t", 2)
    if ($parts.Count -ge 2 -and $parts[0] -ceq 'block') { Stop-Promotion $parts[1] }
  }
}

# Clean: the tree deployed and the tree the deploy runs in. A status that
# FAILS is could-not-tell; untracked files are listed whatever config says;
# skip-worktree/assume-unchanged entries hide edits from status (Codex r1).
function Assert-Clean([string]$Dir) {
  $st = (git -C $Dir status --porcelain --untracked-files=all --ignore-submodules=none 2>$null)
  if ($LASTEXITCODE -ne 0) { Stop-Promotion "could not read git status in '$Dir', so the gate cannot tell whether it is clean. This is not a pass." }
  if ($st) { Stop-Promotion "the tree this deploy runs from ('$Dir') is dirty. You would be deploying $sha plus changes that are in no commit and no review. Commit or stash there first." }
  $flags = (git -C $Dir ls-files -v 2>$null)
  if ($LASTEXITCODE -ne 0) { Stop-Promotion "could not read the index of '$Dir', so the gate cannot tell whether it is clean. This is not a pass." }
  if (@($flags | Where-Object { $_ -cmatch '^[a-zS]' }).Count -gt 0) {
    Stop-Promotion "'$Dir' has index entries flagged skip-worktree or assume-unchanged, which hide changes from git status. Clear them (git update-index --no-skip-worktree / --no-assume-unchanged) before deploying."
  }
}
Assert-Clean $tree
if ($runTop -ne $tree) { Assert-Clean $runTop }

# A literal sha must be the tree's HEAD; a hex token naming no commit here is
# not a sha and is left alone.
foreach ($m in [regex]::Matches($cmd, '(?<![0-9A-Za-z])[0-9a-fA-F]{7,40}(?![0-9A-Za-z])')) {
  $h = $m.Value
  $resolved = (git -C $tree rev-parse -q --verify "$h^{commit}" 2>$null)
  if ($resolved -and $resolved -ne $full) {
    Stop-Promotion "the command names commit '$h', but the tree it runs from ('$tree') is at $sha. The gate checks the sha being deployed; run it from a tree at '$h', or drop the literal."
  }
}

# requires: an all-pass row for THIS sha, written out in full (L-0703)
# The NEWEST full-sha row for the environment decides (L-0665), as in the
# .sh's passed(): 'pass' / 'fail' for that row all-pass or not, 'none' when
# there is no full-sha row. A short row never decides; it is only named.
$script:shortRows = @{}
function Test-Promoted([string]$name, [string]$sha) {
  if (-not (Test-Path .work/PROMOTIONS.md)) { return 'none' }
  $newest = 'none'
  foreach ($line in Get-Content .work/PROMOTIONS.md) {
    if ($line -notmatch '\|') { continue }
    $cells = ($line.Trim().Trim('|') -split '\|') | ForEach-Object { $_.Trim() }
    if ($cells.Count -lt 6) { continue }
    if ($cells[1] -ne $name) { continue }
    # L-0703: only the full 40-hex sha is this commit's row (case ignored).
    # StartsWith(7 characters) admitted any commit sharing the prefix. A
    # strict prefix of the full sha is a short row: never counted, but named.
    $cell = $cells[2].ToLowerInvariant()
    if ($cell.Length -ge 1 -and $cell.Length -lt $sha.Length -and $sha.StartsWith($cell, [System.StringComparison]::Ordinal)) {
      if (-not $script:shortRows.ContainsKey($name)) { $script:shortRows[$name] = $cells[2] }
      continue
    }
    if ($cell -ceq $sha) {
      $newest = if ($cells[3] -ieq 'pass' -and $cells[4] -ieq 'pass' -and $cells[5] -ieq 'pass') { 'pass' } else { 'fail' }
    }
  }
  return $newest
}
# The union rule: every matched environment's requirements, each in its own
# terms (its upstreams, its runbook, its approval marker). With several, each
# reason names the environment it comes from.
foreach ($e in $envNames) {
  $cfg = $vm.environments.$e
  $before = $problems.Count
  foreach ($up in $cfg.requires) {
    $upVerdict = Test-Promoted $up $full.ToLowerInvariant()
    if ($upVerdict -ceq 'none') {
      $short = if ($script:shortRows.ContainsKey($up)) { " (.work/PROMOTIONS.md records the short sha $($script:shortRows[$up]) for '$up': a row counts only with the full 40-character sha - re-run the promotion, or rewrite the row with the full sha after checking it)" } else { "" }
      $problems.Add("'$up' has no all-pass row for sha $full in .work/PROMOTIONS.md$short. Run /crew:promote $up first, and let it record the result.")
    } elseif ($upVerdict -cne 'pass') {
      $problems.Add("'$up' has rows for sha $full in .work/PROMOTIONS.md, but the newest row is not all-pass: a later failure revokes an earlier pass. Run /crew:promote $up again, and let it record the result.")
    }
  }

  # rollback runbook: required for every gated environment. Fail CLOSED - an
  # absent key used to mean "no rollback needed"; now it blocks the deploy. The
  # only way to opt out is rollback: "none" plus a rollbackReason.
  if (-not ($cfg.PSObject.Properties.Name -contains 'rollback')) {
    $problems.Add("'$e' has no 'rollback' key in .crew/verify.json. Add rollback: `"<path to a runbook>`", or rollback: `"none`" plus a rollbackReason string explaining why $e does not need one. Fix: edit the '$e' block in .crew/verify.json.")
  } elseif ($cfg.rollback -eq 'none') {
    $reason = "$($cfg.rollbackReason)".Trim()
    if (-not $reason) {
      $problems.Add("'$e' sets rollback: `"none`" but has no rollbackReason. State why $e does not need a rollback plan. Fix: add a rollbackReason string next to rollback in .crew/verify.json.")
    }
  } elseif (-not $cfg.rollback) {
    $problems.Add("'$e' has an invalid rollback value. Fix: set rollback to a runbook path, or to the literal string `"none`" plus a rollbackReason.")
  } elseif (-not (Test-Path $cfg.rollback)) {
    $problems.Add("the rollback runbook '$($cfg.rollback)' does not exist. No verified rollback, no deploy.")
  } else {
    $txt = Get-Content $cfg.rollback -Raw
    $m = [regex]::Match($txt, 'last[ _-]?verified\s*[:=]\s*(\d{4}-\d{2}-\d{2})', 'IgnoreCase')
    if (-not $m.Success) {
      $problems.Add("'$($cfg.rollback)' has no 'last verified: YYYY-MM-DD' line. An unverified rollback is not a rollback.")
    } else {
      # A date-SHAPED string is not a date: the regex accepts `2026-99-99`, which
      # ParseExact throws on. Unhandled, that error left the deploy ALLOWED with
      # the in-flight marker written - the same fail-open as the bash twin, and
      # the reason both flavours are fixed in one change rather than one now and
      # the other when somebody next reads it.
      $verified = $null
      try {
        $verified = [datetime]::ParseExact($m.Groups[1].Value, 'yyyy-MM-dd', $null)
      } catch {
        $problems.Add("'$($cfg.rollback)' has 'last verified: $($m.Groups[1].Value)', which is date-shaped but not a real date. An unparseable verification date is not a verification.") | Out-Null
      }
      $age = if ($verified) { (Get-Date).Date - $verified } else { $null }
      if ($age -and $age.Days -gt 90) {
        $problems.Add("'$($cfg.rollback)' was last verified $($age.Days) days ago (ceiling is 90). Re-run it against a real environment first.")
      }
    }
  }

  if ($cfg.requireHuman) {
    $marker = ".crew/.approved-$e-$sha"
    if (-not (Test-Path $marker)) {
      $problems.Add("this environment requires explicit human approval. Show the sha, the diff summary and the last promotion, get a yes, then create the marker: New-Item -ItemType File $marker")
    }
  }
  if ($envNames.Count -gt 1) {
    for ($k = $before; $k -lt $problems.Count; $k++) { $problems[$k] = "[$e] " + $problems[$k] }
  }
}

# 5. Review evidence (L-0703): the twin of step 5 in promote-gate.sh. Both
# flavours run the SAME _promote_review.py, so they cannot decide it
# differently. No usable python, a helper that does not finish inside what is
# left of the gate's deadline, and a non-zero exit are all could-not-tell: a
# block, never a pass. Its reasons join $problems, so the emergency lane
# below records them like every other unmet precondition.
# During an open incident a review check that could not run is an unmet
# precondition like every other: it joins $problems, which the emergency lane
# below records as a skip. Exiting 2 here unconditionally blocked the very
# deploys an incident exists to let through (L-0703 Codex r1). The twin is the
# `crew_incident_active` branch after _promote_review.py in promote-gate.sh.
function Deny-ReviewUnknown([string]$Why) {
  if ($incident) {
    $problems.Add("the review-evidence check could not be evaluated: $Why This is not a pass.")
    return
  }
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName, sha $sha, tree ${tree}):")
  [Console]::Error.WriteLine("  - the review-evidence check could not be evaluated: $Why")
  [Console]::Error.WriteLine("    This is not a pass.")
  exit 2
}
# The helper's stdout, or $null once Deny-ReviewUnknown has recorded why not.
function Invoke-PromoteReview([string]$Python, [string]$Helper) {
  try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Python
    $quoted = @($Helper, $tree, $full, "$gateDeadlineEpoch") + @($envNames) | ForEach-Object { '"' + ($_ -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"' }
    $psi.Arguments = ($quoted -join ' ')
    $psi.WorkingDirectory = (Get-Location).Path
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $proc = [System.Diagnostics.Process]::Start($psi)
    $proc.StandardInput.Close()
    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $errTask = $proc.StandardError.ReadToEndAsync()
    # The helper kills its own search at the deadline; this wait is the backstop
    # for a helper that cannot even start its clock.
    $waitMs = [int][Math]::Max(1000, ($gateDeadlineEpoch - [DateTimeOffset]::Now.ToUnixTimeSeconds() + 1) * 1000)
    if (-not $proc.WaitForExit($waitMs)) {
      # Best effort: whatever is left running, the deploy is refused below.
      try { $proc.Kill($true) } catch {
        # Windows PowerShell 5.1 has no Kill($true). taskkill is waited on for at
        # most 2s, so a stalled one cannot outlive the hook timeout either.
        try {
          $tk = Start-Process -FilePath 'taskkill.exe' -ArgumentList '/T', '/F', '/PID', "$($proc.Id)" -NoNewWindow -PassThru -ErrorAction Stop
          $null = $tk.WaitForExit(2000)
        } catch { $null = $_ }
        try { $proc.Kill() } catch { $null = $_ }
      }
      Deny-ReviewUnknown "_promote_review.py did not finish inside the gate's deadline and was stopped."
      return $null
    }
    # Bounded too: a helper that exited while something it started still holds
    # its stdout or stderr would otherwise leave .Result waiting past the hook
    # timeout, and a timed-out hook is not a block.
    if (-not $outTask.Wait(2000) -or -not $errTask.Wait(2000)) {
      Deny-ReviewUnknown "_promote_review.py exited but its output did not close inside 2s."
      return $null
    }
    if ($proc.ExitCode -ne 0) {
      $errText = "$($errTask.Result)".Trim()
      if ($errText) { [Console]::Error.WriteLine($errText) }
      Deny-ReviewUnknown "_promote_review.py exited $($proc.ExitCode); its reason is above."
      return $null
    }
    return "$($outTask.Result)"
  } catch {
    Deny-ReviewUnknown "_promote_review.py could not be run ($($_.Exception.Message))."
    return $null
  }
}
$reviewOut = $null
$reviewPy = Resolve-CrewPython
$helper = Join-Path $PSScriptRoot '_promote_review.py'
if (-not $reviewPy) {
  Deny-ReviewUnknown "no usable python was found (python 3.8+ is required to read the review ledgers)."
} elseif (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
  Deny-ReviewUnknown "$helper is missing."
} else {
  $reviewOut = Invoke-PromoteReview $reviewPy $helper
}
foreach ($reason in ($reviewOut -split [char]0x1e)) {
  if ($reason) { $problems.Add($reason) }
}

if ($problems.Count -gt 0 -and $incident) {
  # One row per unmet precondition, so the closing report names them all.
  $problems | ForEach-Object { Write-CrewIncidentSkip "promote" "$envName at ${sha}: $_" }
  $problems.Clear()
}

if ($problems.Count -gt 0) {
  [Console]::Error.WriteLine("PROMOTION BLOCKED ($envName, sha $sha, tree $tree):")
  $problems | ForEach-Object { [Console]::Error.WriteLine("  - $_") }
  [Console]::Error.WriteLine("")
  [Console]::Error.WriteLine("These are the pre-deploy gates from .crew/verify.json. Fix them, or set")
  [Console]::Error.WriteLine("verifyGate:false in .crew/config.json if this repo should not be gated.")
  exit 2
}

New-Item -ItemType Directory -Path .crew -Force -ErrorAction SilentlyContinue | Out-Null
Set-Content -Path .crew/.deploy-in-flight -Value "$envName $sha" -Encoding ASCII
exit 0
