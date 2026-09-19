# Runs the crew plugin's `claude plugin eval` suite under plugin/crew/evals/.
# Matched pair of scripts/run-plugin-evals.sh -- change one, change the other.
#
# One case at a time: `--case <glob>` is a single-value filter (no documented
# comma-list or brace-expansion, and no "exclude" filter) -
# https://code.claude.com/docs/en/plugin-evals.
#
# developer-runs-command-in-foreground needs a Bash grant, which needs the OS
# sandbox backend. Confirmed on this machine, verbatim:
#   "sandbox required but unavailable: sandbox is enabled but the Windows
#    sandbox is not active on this session (feature gate off)"
# So that one case is skipped here with a loud notice; it runs under the
# Linux CI job and under WSL2, not on native Windows.
#
# pm-does-not-write-code is a KNOWN, CURRENTLY FAILING case, not a bug in the
# case: the PM still edits the tempting one-line fix itself instead of
# dispatching a developer (see plugin/crew/README.md#evals and the
# CHANGELOG entry for this suite). The case format has no expected-fail /
# xfail field, so it is tracked by name below: it always runs and always
# reports, but never flips this script's exit code for the ONE way it is
# meant to fail. Two things it does NOT swallow, both review-found:
#   - EVAL_EXPECTED_FAIL_CASES is comma-separated here (-split ","),
#     matching the .sh twin exactly - the .sh side used to split on spaces,
#     so the same env var value matched here and matched nothing at all
#     under bash, silently dropping the exemption on one platform only.
#   - An xfail-listed case that PASSES still fails this script (with a
#     "retire the xfail" warning) rather than passing quietly.
#   - The exemption applies to exactly ONE shape: exit code 1 (the
#     documented "a case scored below the threshold" code) with a scored
#     result THIS invocation actually wrote (a non-empty "cases" array in
#     the json this run just produced, not a leftover from a previous run -
#     the file is removed before every invocation for exactly that reason).
#     Every OTHER exit code means something else happened entirely and is
#     never exempted, xfail-listed or not; an exit-0 "pass" with no scored
#     result is caught the same way (Test-ScoredResult) and treated as a
#     failure.
#   - Xfail name matching is CASE-SENSITIVE here (-ccontains), matching the
#     .sh twin's plain `=` string comparison - PowerShell's default
#     `-contains` is case-INSENSITIVE, so EVAL_EXPECTED_FAIL_CASES=
#     "PM-DOES-NOT-WRITE-CODE" used to exempt the case here while the .sh
#     twin's case-sensitive match rejected the same value outright.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PluginDir = Join-Path $RepoRoot "plugin\crew"
$Threshold = if ($env:EVAL_THRESHOLD) { $env:EVAL_THRESHOLD } else { "1.0" }
$MaxCostUsd = if ($env:EVAL_MAX_COST_USD) { $env:EVAL_MAX_COST_USD } else { "15" }
$OutDir = if ($env:EVAL_OUTPUT_DIR) { $env:EVAL_OUTPUT_DIR } else { Join-Path $RepoRoot ".work\plugin-evals" }
$ExpectedFailCases = if ($env:EVAL_EXPECTED_FAIL_CASES) { $env:EVAL_EXPECTED_FAIL_CASES -split "," } else { @("pm-does-not-write-code") }

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    # Write-Error is a non-terminating error by default, but
    # $ErrorActionPreference = "Stop" above promotes EVERY Write-Error call
    # to terminating - including this one - so without -ErrorAction Continue
    # the script throws right here and the `exit 127` below is never reached.
    # PowerShell then reports its own uncaught-error exit code (1), not 127,
    # so a missing CLI was indistinguishable from every other failure mode.
    Write-Error "claude CLI not found on PATH" -ErrorAction Continue
    exit 127
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$script:ExitStatus = 0
$ResultFiles = @()

function Test-ScoredResult {
    # True only when $Path is a non-empty file holding a real
    # aggregate-result.json ("cases" present and non-empty) - i.e. claude
    # plugin eval actually evaluated the case, as opposed to erroring out
    # before producing anything to score.
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    if ((Get-Item $Path).Length -eq 0) { return $false }
    try {
        $doc = Get-Content $Path -Raw | ConvertFrom-Json
    } catch {
        return $false
    }
    return [bool]($doc.cases -and $doc.cases.Count -gt 0)
}

function Invoke-EvalCase {
    param([string]$CaseName, [string[]]$ExtraArgs)
    $outJson = Join-Path $OutDir "$CaseName.json"
    # Never let a result file from a PREVIOUS run count as evidence for THIS
    # one - a run that errors out without writing anything must not inherit
    # a stale pass or a stale scored-failure sitting there from last time.
    if (Test-Path $outJson) { Remove-Item -Force $outJson }
    Write-Host "== $CaseName =="
    $claudeArgs = @($PluginDir, "--case", $CaseName, "--trust-plugin",
        "--threshold", $Threshold, "--max-cost-usd", $MaxCostUsd,
        "--no-publish", "--json", $outJson) + $ExtraArgs
    & claude plugin eval @claudeArgs
    $code = $LASTEXITCODE
    $script:ResultFiles += $outJson
    $isXfail = $ExpectedFailCases -ccontains $CaseName

    if ($code -eq 0) {
        if (-not (Test-ScoredResult $outJson)) {
            Write-Warning "$CaseName exited 0 but produced no scored result (empty or missing 'cases') - a runner error (e.g. a --case filter that matched nothing), not a pass."
            $script:ExitStatus = 1
            return
        }
        if ($isXfail) {
            Write-Warning "$CaseName is listed in EVAL_EXPECTED_FAIL_CASES but PASSED - retire the xfail (drop it from EVAL_EXPECTED_FAIL_CASES / this script's default) so a future regression is caught again instead of staying silently exempted."
            $script:ExitStatus = 1
        }
        return
    }

    # The exemption covers exactly ONE documented shape: exit 1 ("a case
    # scored below the threshold") with a result THIS run actually wrote,
    # holding real scored case data. Every other exit code (2 = cost
    # ceiling/partial, 127 = CLI missing, 130 = interrupted, 143 =
    # terminated, ...) is a runner error, never exempted regardless of xfail
    # listing or what a leftover json happens to contain.
    if ($code -eq 1 -and $isXfail -and (Test-ScoredResult $outJson)) {
        Write-Warning "exit 1, but $CaseName is in EVAL_EXPECTED_FAIL_CASES and produced a real (scored) result from THIS run - not failing the gate."
    } else {
        $extra = ""
        if ($code -ne 1) {
            $extra = " (exit $code is not the documented 'case scored below threshold' code - a runner error, never exempted regardless of xfail listing)"
        } elseif ($isXfail) {
            $extra = " (in EVAL_EXPECTED_FAIL_CASES, but no scored result was produced by this run - a runner error is never exempted)"
        }
        Write-Warning "claude plugin eval exited $code for $CaseName$extra"
        $script:ExitStatus = 1
    }
}

Write-Host "== Group A: Write/Edit only, no sandbox needed =="
Invoke-EvalCase -CaseName "pm-does-not-write-code" -ExtraArgs @("--scaffold", "--allow-tools", "Write", "Edit")
Invoke-EvalCase -CaseName "qa-reviewer-stays-read-only" -ExtraArgs @("--allow-tools", "Write", "Edit")
Invoke-EvalCase -CaseName "developer-defers-unrelated-bug" -ExtraArgs @("--scaffold", "--allow-tools", "Write", "Edit")
Invoke-EvalCase -CaseName "pm-answers-status-mid-pass" -ExtraArgs @("--allow-tools", "Write", "Edit")

Write-Host ""
$bwrap = Get-Command bwrap -ErrorAction SilentlyContinue
$socat = Get-Command socat -ErrorAction SilentlyContinue
if ($bwrap -and $socat) {
    Write-Host "== Group B: developer-runs-command-in-foreground (needs Bash + sandbox; backend present) =="
    Invoke-EvalCase -CaseName "developer-runs-command-in-foreground" -ExtraArgs @("--allow-tools", "Bash")
} else {
    Write-Warning "Group B SKIPPED: developer-runs-command-in-foreground needs Bash, which needs the OS sandbox (bubblewrap + socat). Neither is on PATH here. Native Windows has no backend at all; run this under WSL2 or the Linux CI job instead. Not a pass, not a fail - unverified on this machine."
}

Write-Host ""
Write-Host "== Delta table =="
"{0,-38} {1,6} {2,6} {3,7}  {4}" -f "CASE", "WITH", "W/OUT", "D", "COST"
foreach ($f in $ResultFiles) {
    if (-not (Test-Path $f)) {
        $name = [System.IO.Path]::GetFileNameWithoutExtension($f)
        "{0,-38} {1,6} {2,6} {3,7}" -f $name, "n/a", "n/a", "n/a"
        continue
    }
    $doc = Get-Content $f -Raw | ConvertFrom-Json
    foreach ($c in $doc.cases) {
        $score = $c.aggregates.score
        $delta = $c.aggregates.delta
        $without = if ($null -ne $score -and $null -ne $delta) { $score - $delta } else { $null }
        $cost = 0.0
        if ($c.arms.with) { foreach ($r in $c.arms.with) { $cost += [double]($r.costUsd) } }
        if ($c.arms.without) { foreach ($r in $c.arms.without) { $cost += [double]($r.costUsd) } }
        $sFmt = if ($null -ne $score) { "{0:N2}" -f $score } else { "n/a" }
        $wFmt = if ($null -ne $without) { "{0:N2}" -f $without } else { "n/a" }
        $dFmt = if ($null -ne $delta) { "{0:+0.00;-0.00}" -f $delta } else { "n/a" }
        "{0,-38} {1,6} {2,6} {3,7}  `${4:N2}" -f $c.name, $sFmt, $wFmt, $dFmt, $cost
    }
}

exit $script:ExitStatus
