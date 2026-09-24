# PreToolUse gate on Write/Edit, keyed on `agent_type`. PowerShell twin of
# role-write-guard.sh -- both delegate to role_write_guard.py so neither can
# drift from the other. See role-write-guard.sh for why this is NOT branched
# by tool_name the way promote-gate.ps1 is.
param(
  # Probe seam, the twin of verify-gate.ps1's -PrintPython and
  # pm-pulse.ps1's: prints the interpreter Resolve-CrewPython would use and
  # exits 0 without touching stdin or running the guard. This hook's only
  # consumer is Claude Code's PreToolUse hook, which pipes JSON on stdin and
  # has no interactive path to probe resolution.
  [switch]$PrintPython
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

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Resolve-CrewPython {
  # NOT byte-for-byte with verify-gate.ps1's/pm-pulse.ps1's copies any more
  # -- see tests/test_role_write_guard.py for why the parity discipline
  # changed shape rather than being dropped. Those two files' resolver only
  # needs to match `_common.sh`'s bare `crew_py()`; this one needs to match
  # role-write-guard.sh's OWN resolver, which does more than `crew_py()`
  # does, so this copy has to as well.
  #
  # Two bugs, reported together 2026-09-19 by a PowerShell-focused review of
  # THIS file specifically, on top of the WindowsApps/profile-shadow guards
  # this function already had:
  #
  #   1. Metadata alone (`.CommandType` / `.Source`) is exactly what a
  #      WindowsApps stub already passes -- `Get-Command` reports it as a
  #      real Application with a real Source. role-write-guard.sh's own
  #      resolver does not trust that either: it EXECUTES the candidate
  #      (`$cand -c "import sys;print(sys.executable)"`) and reads back
  #      what actually ran. This copy now does the same, rejecting a
  #      candidate that produces no output when actually launched.
  #   2. `Get-Command $name -All` walked every match for ONE name before
  #      moving to the next name -- so on `PATH=WindowsApps;RealDir` with
  #      only `python3` present anywhere (no `python`/`py` at all), the old
  #      code walked PAST the WindowsApps `python3` stub and found
  #      RealDir's `python3` further down PATH. Bash's `command -v
  #      python3` (role-write-guard.sh's resolver) takes only the FIRST
  #      match for a name; rejecting it moves to the NEXT NAME, never a
  #      second search of the same one -- so the .sh abandoned `python3`
  #      after the stub and never found a `python`/`py` that did not
  #      exist either. Same PATH, same machine: one shell flavour
  #      enforced `guards.roleWrites: block` and the other silently
  #      allowed the write unjudged. This copy now takes only the first
  #      match per name too, mirroring the .sh's name-order exactly.
  #
  # A third bug, reported 2026-09-24: this function used to ALSO reject any
  # candidate whose `.Source` (pre-execution) or resolved `sys.executable`
  # (post-execution) merely contained the substring "WindowsApps", untested.
  # That is not a stub detector, it is a location guess, and on a host where
  # Python is installed through the Microsoft Store, EVERY candidate's real
  # interpreter genuinely lives under
  # `...\WindowsApps\PythonSoftwareFoundation.Python.3.x_<hash>\python.exe`
  # -- so the blanket reject fired on all three names, `Resolve-CrewPython`
  # returned '', and the caller's "no usable python" fallback let every write
  # through unjudged on a machine where python plainly works (confirmed here:
  # all three names launch fine, reporting Python 3.14.6). role-write-
  # guard.sh's OWN resolver hit and fixed this exact bug on 2026-09-22 (see
  # its comment on `_resolve_role_write_python`); this copy had not been
  # brought back into parity until now. The execute-and-probe checks below
  # already prove real-vs-stub without needing to know WHERE the interpreter
  # lives: a placeholder App Execution Alias run non-interactively via `-c`
  # produces no usable stdout (rejected below) rather than a real
  # interpreter path, and `Test-Path -PathType Leaf` further down still
  # requires whatever path IS printed to be a real, existing file. Trust
  # that proof instead of a path substring that happens to reject the
  # working case too.
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd -or $cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
    $real = $null
    $global:LASTEXITCODE = $null
    try {
      # Captured WHOLE, not piped through `Select-Object -First 1` --
      # that cmdlet can stop reading (and signal the pipeline to close)
      # as soon as it has one object, which races the native process's
      # own exit and can leave `$LASTEXITCODE` reflecting an early
      # termination rather than the candidate's real exit status. Letting
      # the candidate run to completion first is what makes the exit-code
      # check below trustworthy.
      $output = & $cmd.Source -c 'import sys; print(sys.executable)' 2>$null
      # NOT just "did it print something" -- a wrapper that prints a
      # plausible interpreter path and then exits nonzero must be
      # rejected too, matching role-write-guard.sh's own
      # `real=$(...) || continue`, which checks the candidate's exit
      # status. Reported 2026-09-19: this check was absent, so a
      # candidate bash correctly rejected (nonzero exit) was still
      # ACCEPTED here on output alone.
      if ($LASTEXITCODE -eq 0 -and $output) {
        $real = @($output)[0]
      }
    } catch {
      $real = $null
    }
    if ($real) { $real = $real.ToString().Trim() }
    if (-not $real) { continue }
    # Exit 0 and non-empty output is still not proof: a wrapper could print a
    # plausible-looking path to something that is not actually there. Confirm
    # the path EXISTS as a file before trusting it -- the bash-side parity
    # check is `[ -x "$real" ]`; Test-Path has no executable-bit concept on
    # Windows (an .exe's "executability" is its extension, not a mode bit),
    # so -PathType Leaf is the equivalent proof here.
    if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
    return $real
  }
  return ''
}

if ($PrintPython) {
  Write-Output (Resolve-CrewPython)
  exit 0
}

# Read stdin as raw BYTES, not `[Console]::In.ReadToEnd()` -- that decodes
# using the OEM codepage (Windows PowerShell 5.1) or a pwsh-7.x-version-
# dependent default, silently mangling anything outside plain ASCII
# (an accented character reaching this script mangles into `?` on 5.1 or
# multi-byte garbage on pwsh 7.6.6, verified with the test suite's own
# accented-character case) and turning a leading
# UTF-8 BOM into garbage bytes that make the decoded JSON unparseable at
# byte zero -- role_write_guard.py's own `except ValueError` then silently
# allows the call UNJUDGED. role-write-guard.sh (`INPUT=$(cat)`) is
# byte-transparent, so the two shell flavours diverged on byte-identical
# input. Reported and fixed 2026-09-19.
$stdinStream = [Console]::OpenStandardInput()
$memStream = New-Object System.IO.MemoryStream
$stdinStream.CopyTo($memStream)
$stdinBytes = $memStream.ToArray()

# Strip a leading UTF-8 BOM (EF BB BF) before decoding -- a BOM surviving
# into the decoded string is itself invalid JSON at position 0, which
# would fail role_write_guard.py's parse for a different reason than an
# encoding mismatch, and either way the payload must decode clean.
if ($stdinBytes.Length -ge 3 -and $stdinBytes[0] -eq 0xEF -and
    $stdinBytes[1] -eq 0xBB -and $stdinBytes[2] -eq 0xBF) {
  if ($stdinBytes.Length -gt 3) {
    $stdinBytes = $stdinBytes[3..($stdinBytes.Length - 1)]
  } else {
    $stdinBytes = [byte[]]@()
  }
}
$raw = [System.Text.Encoding]::UTF8.GetString($stdinBytes)

# Deny-list mirror of role_write_guard.py's `_DENY_ROLES`, plus `pm` (that
# module's other restricted role) -- used both when NO python resolves at
# all (below) and by the BLOCK-1 fallback further down, when
# role_write_guard.py could not be launched. `tests/test_role_write_guard.py`'s
# parity test re-derives the python side from `agents/*.md` on every run
# and asserts this list matches it.
$RestrictedRolesForFallback = @(
  'analyst', 'compliance-auditor', 'dba', 'explorer',
  'infrastructure-architect', 'kimi-consult', 'penetration-tester',
  'planner', 'qa-researcher', 'qa-reviewer', 'researcher', 'security',
  'pm'
)

function Get-FallbackRole {
  # Consulted whenever python cannot be used to reach a real decision --
  # either no candidate resolves at all, or a resolved candidate fails to
  # launch role_write_guard.py. Never throws: an unparseable payload
  # answers $null, the same permissive fallback role_write_guard.py itself
  # gives one.
  param([string]$RawJson)
  try {
    $obj = $RawJson | ConvertFrom-Json -ErrorAction Stop
  } catch {
    return $null
  }
  $agentType = $obj.agent_type
  if (-not $agentType) { return $null }
  $role = ([string]$agentType).Trim().ToLowerInvariant()
  if ($role.StartsWith('crew:')) { $role = $role.Substring(5).Trim() }
  if (-not $role) { return $null }
  return $role
}

$py = Resolve-CrewPython
if (-not $py) {
  # No candidate resolved at all -- a DIFFERENT failure than BLOCK-1 below
  # (which is a candidate that resolved, was proven executable, and then
  # still failed to launch). Reported 2026-09-24 alongside the WindowsApps
  # resolver fix: fixing the resolver alone still leaves a genuinely
  # python-less host (or any other total-resolution failure) falling
  # through to an unconditional "allow it unjudged" -- which for a role
  # this table ALREADY knows is restricted (`pm`, or a `_DENY_ROLES`
  # member) throws away a decision that needed no python at all. A
  # `_DENY_ROLES` role may not write ANY file regardless of path; `pm` is
  # refused for anything outside its own patterns often enough that
  # collapsing "cannot judge" into "allow" for either is exactly CLAUDE.md's
  # named recurring bug ("an unknown collapsing into the safe-looking
  # value"), not a neutral default. Mirrors BLOCK-1's own
  # $RestrictedRolesForFallback / Get-FallbackRole exactly, so both failure
  # modes agree on which roles fail closed.
  $fallbackRole = Get-FallbackRole $raw
  if ($RestrictedRolesForFallback -contains $fallbackRole) {
    [Console]::Error.WriteLine("role-write-guard: no usable python found - cannot judge this write; failing closed for role ``$fallbackRole``.")
    exit 2
  }
  [Console]::Error.WriteLine("role-write-guard: no usable python found - cannot judge this write; allowing it unjudged.")
  exit 0
}

$scriptPath = Join-Path $dir 'role_write_guard.py'
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
  # Without this check, a missing/broken role_write_guard.py reaches
  # python as a bare file-not-found error and exits 2 -- indistinguishable
  # from an actual `guards.roleWrites: block` refusal by exit code alone,
  # so an installation defect reads as a policy decision nobody made.
  # Still fails closed (exit 2): a broken install is not evidence a write
  # is safe. Reported and fixed 2026-09-19.
  [Console]::Error.WriteLine("role-write-guard: role_write_guard.py is missing at $scriptPath; failing closed.")
  exit 2
}

# Force the string back OUT as UTF-8 when it is piped to the native python
# process below -- PowerShell's pipe-to-native-command path re-encodes a
# .NET string using `[Console]::OutputEncoding` (and, on Windows PowerShell
# 5.1, the legacy `$OutputEncoding` preference variable too), which
# otherwise defaults to the OEM codepage and would reintroduce the exact
# mangling the read above just avoided.
$prevConsoleEncoding = [Console]::OutputEncoding
$prevOutputEncodingVar = $OutputEncoding
$prevPythonUtf8 = $env:PYTHONUTF8
$prevPythonIoEncoding = $env:PYTHONIOENCODING
$exitCode = $null
$launchFailure = $null
try {
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  # Force these in the CHILD's environment regardless of what the CALLER's
  # environment already set -- reported 2026-09-19: a caller that
  # explicitly set PYTHONUTF8=0 and left PYTHONIOENCODING unset could
  # still reach python with a correctly-UTF8-encoded pipe (the encoding
  # fix immediately above) and have PYTHON'S OWN decoding of it go wrong
  # regardless, since `sys.stdin.read()`'s text-mode decoding depends on
  # these. role_write_guard.py's `sys.stdin.buffer` read no longer
  # depends on them for INPUT either way, but its stdout/stderr writes of
  # a non-ASCII path still do, so this stays load-bearing for those.
  $env:PYTHONUTF8 = '1'
  $env:PYTHONIOENCODING = 'utf-8'
  $global:LASTEXITCODE = $null
  $raw | & $py $scriptPath
  $exitCode = $LASTEXITCODE
} catch {
  $launchFailure = $_
} finally {
  [Console]::OutputEncoding = $prevConsoleEncoding
  $OutputEncoding = $prevOutputEncodingVar
  $env:PYTHONUTF8 = $prevPythonUtf8
  $env:PYTHONIOENCODING = $prevPythonIoEncoding
}

if ($null -eq $exitCode) {
  # The python process never reported an exit code -- either the launch
  # itself threw (caught above) or, on some PowerShell/OS combinations, a
  # failed-to-start native command leaves $LASTEXITCODE untouched with NO
  # catchable exception at all. `exit $LASTEXITCODE` on a null value
  # silently evaluates to 0 (allow) -- CLAUDE.md's own named recurring bug
  # in a new shape: the header comment above promised this hook fails
  # closed for a restricted role, and a silent 0 here broke that promise
  # with no diagnostic at all beyond a generic native-command error on
  # stderr. Reported and fixed 2026-09-19. `$global:LASTEXITCODE = 0` is
  # NOT the fix -- that would make this exact failure look identical to an
  # explicit `allow`, which is the same silent-collapse shape with extra
  # steps. `$py` was already proven to be a real, executable interpreter
  # by Resolve-CrewPython's own execute-to-verify probe, so reaching here
  # means something changed between resolution and this launch (deleted,
  # permissions, antivirus, ...) -- rare, but not nonexistent, and not
  # evidence a write from a role this table already knows is restricted
  # is safe to let through.
  $fallbackRole = Get-FallbackRole $raw
  if ($RestrictedRolesForFallback -contains $fallbackRole) {
    [Console]::Error.WriteLine("role-write-guard: could not launch the python interpreter ($py) to judge this write; failing closed for role ``$fallbackRole``. $launchFailure")
    exit 2
  }
  [Console]::Error.WriteLine("role-write-guard: could not launch the python interpreter ($py) to judge this write; allowing it unjudged. $launchFailure")
  exit 0
}

exit $exitCode
