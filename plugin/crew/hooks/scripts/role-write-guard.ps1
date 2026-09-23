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
  # Review round, 2026-09-22, on top of the 2026-09-19 execute-and-verify
  # fix below: `Get-Command $name -ErrorAction SilentlyContinue |
  # Select-Object -First 1` (the shape this function briefly carried)
  # PROVED TWO REGRESSIONS, both against real, previously-reported failure
  # modes this file exists to prevent:
  #
  #   1. A PowerShell FUNCTION always outranks an Application of the SAME
  #      name in Get-Command's own result order -- confirmed directly:
  #      `Get-Command python3 -All` against a PATH carrying both a
  #      `function python3 {}` (hooks.json passes no -NoProfile, so a
  #      profile-defined wrapper is live) and a real `python3` executable
  #      returns `[Function, Application]`, in that order, every time.
  #      `-First 1` therefore NEVER sees the Application: it keeps only the
  #      function, which fails the `CommandType -ne 'Application'` check
  #      and moves to the NEXT NAME -- so a profile function shadowing
  #      `python3`/`python` silently loses the real interpreter under
  #      those names even when one is sitting right there. `-All` returns
  #      BOTH entries in that same rank order, letting the loop below skip
  #      the function and reach the real one for the SAME name.
  #   2. The identical shape applies to a WindowsApps alias stub sitting
  #      ahead of a genuine interpreter under the SAME name further down
  #      PATH (`PATH=WindowsApps\python3;RealDir\python3`, no `python`/`py`
  #      anywhere): `-First 1` tries only the stub, the stub fails the
  #      execute-probe, and the loop moves to the NEXT NAME rather than
  #      trying `RealDir`'s `python3` -- exactly the "one shell flavour
  #      enforces guards.roleWrites: block, the other allows unjudged"
  #      failure this file's history already names, reintroduced by a
  #      different mechanism. `-All`, walking and PROBING every match for
  #      a name before giving up on it, finds `RealDir`'s `python3`.
  #
  # `-All` was the shape here until the 2026-09-19 fix (see below)
  # deliberately narrowed it to `-First 1` to match bash's `command -v`,
  # which can only ever report ONE match. That narrowing is what
  # reintroduced both regressions above: PowerShell's Get-Command CAN
  # enumerate every match for a name, bash's `command -v` structurally
  # cannot, and giving that capability up to imitate a shell that does not
  # have it made this resolver WORSE at its one job -- finding a working
  # interpreter -- for a guard whose failure mode is allowing a write
  # unjudged. Every candidate is still PROVED by execution before being
  # trusted (below), so walking every match for a name costs nothing in
  # safety and fixes both regressions above.
  #
  # The 2026-09-19 fix itself stays: metadata alone (`.CommandType` /
  # `.Source`) is exactly what a WindowsApps stub already passes --
  # `Get-Command` reports it as a real Application with a real Source.
  # role-write-guard.sh's own resolver does not trust that either: it
  # EXECUTES the candidate (`$cand -c "import sys;print(sys.executable)"`)
  # and reads back what actually ran, rejecting one that produces no
  # output when actually launched, or that exits nonzero despite printing
  # something plausible (matching `real=$(...) || continue` on the bash
  # side).
  #
  # NOT a blanket "reject anything containing WindowsApps" -- that used to
  # sit here (on both the candidate's own Source and its reported $real)
  # and rejected a genuine Microsoft Store Python install, which resolves
  # through EXACTLY that shape: `Get-Command python3` finds the alias at
  # `...\Microsoft\WindowsApps\python3.exe`, and when Python IS actually
  # installed through the Store that alias relays to a REAL working
  # interpreter whose own `sys.executable` is
  # `...\WindowsApps\PythonSoftwareFoundation.Python.3.x_<hash>\python.exe`
  # -- also WindowsApps-rooted, so the substring match caught it too. The
  # execute-and-verify probe below already proves the difference without
  # needing to know WHERE the interpreter lives. See `_common.sh`'s
  # `crew_py_strict` header for the bash-side twin of this correction.
  #
  # Three further proofs, matching `crew_py_strict` exactly rather than
  # just its outcome (review, 2026-09-22): MULTI-LINE stdout is rejected,
  # not silently truncated to its first line -- bash's `$(...)` captures
  # the WHOLE output as one string, so an embedded newline can never equal
  # a real file's path and `-x` fails structurally; PowerShell instead
  # splits multi-line native output into an array, so that has to be
  # checked explicitly (`$lines.Count -ne 1`) to reject the same shape.
  # LEADING WHITESPACE is never trimmed away -- bash does not trim it
  # either (only a trailing newline, consumed by `$(...)` itself, and any
  # `\r`, which PowerShell's own per-line output capture already discards
  # -- confirmed directly, a `\r\n`-terminated stub's captured line carries
  # no trailing `\r`), so a leading space prepended to an otherwise-real
  # path fails the existence check below exactly as it fails bash's `-x`,
  # and that implicit rejection is the correct parity, not a dedicated
  # whitespace check. NON-EXECUTABLE TARGET: `Test-Path -PathType Leaf` on
  # Windows only proves EXISTENCE (there is no POSIX-style executable bit
  # there; an .exe's "executability" is its extension, matching this
  # file's original proof), but on a POSIX host -- the Linux test harness,
  # or a genuine WSL/Linux run -- existence is not enough, so `UnixMode` is
  # also checked there for the same reason bash's `-x` requires it.
  $names = @('python3', 'python', 'py')
  foreach ($name in $names) {
    $candidates = Get-Command $name -All -ErrorAction SilentlyContinue
    foreach ($cmd in $candidates) {
      if ($cmd.CommandType -ne 'Application' -or -not $cmd.Source) { continue }
      $global:LASTEXITCODE = $null
      $output = $null
      try {
        # Captured WHOLE, not piped through `Select-Object -First 1` --
        # that cmdlet can stop reading (and signal the pipeline to close)
        # as soon as it has one object, which races the native process's
        # own exit and can leave `$LASTEXITCODE` reflecting an early
        # termination rather than the candidate's real exit status.
        $output = & $cmd.Source -c 'import sys; print(sys.executable)' 2>$null
      } catch {
        $output = $null
      }
      # NOT just "did it print something" -- a wrapper that prints a
      # plausible interpreter path and then exits nonzero must be
      # rejected too, matching role-write-guard.sh's own
      # `real=$(...) || continue`, which checks the candidate's exit
      # status.
      if ($LASTEXITCODE -ne 0 -or -not $output) { continue }
      $lines = @($output)
      if ($lines.Count -ne 1) { continue }
      $real = $lines[0]
      if ([string]::IsNullOrEmpty($real)) { continue }
      if (-not (Test-Path -LiteralPath $real -PathType Leaf)) { continue }
      if ($env:OS -ne 'Windows_NT') {
        $item = Get-Item -LiteralPath $real -ErrorAction SilentlyContinue
        if (-not $item -or $item.UnixMode -notmatch 'x') { continue }
      }
      return $real
    }
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

$py = Resolve-CrewPython
if (-not $py) {
  [Console]::Error.WriteLine("role-write-guard: no usable python - cannot judge this write, allowing it unjudged.")
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

# Deny-list mirror of role_write_guard.py's `_DENY_ROLES`, plus `pm` (that
# module's other restricted role) -- used ONLY by the BLOCK-1 fallback
# below, when role_write_guard.py could not be launched at all and there
# is no real decision to defer to. `tests/test_role_write_guard.py`'s
# parity test re-derives the python side from `agents/*.md` on every run
# and asserts this list matches it.
$RestrictedRolesForFallback = @(
  'analyst', 'compliance-auditor', 'dba', 'explorer',
  'infrastructure-architect', 'kimi-consult', 'penetration-tester',
  'planner', 'qa-researcher', 'qa-reviewer', 'researcher', 'security',
  'pm'
)

function Get-FallbackRole {
  # Only consulted when python could not run at all -- see below. Never
  # throws: an unparseable payload answers $null, the same permissive
  # fallback role_write_guard.py itself gives one.
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
