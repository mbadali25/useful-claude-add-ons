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
#     "retire the xfail" warning) rather than passing quietly, and an
#     xfail-listed case that never produced a scored result at all (the run
#     errored before evaluating anything) is never exempted either - see
#     Test-ScoredResult below.

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
    Write-Host "== $CaseName =="
    $claudeArgs = @($PluginDir, "--case", $CaseName, "--trust-plugin",
        "--threshold", $Threshold, "--max-cost-usd", $MaxCostUsd,
        "--no-publish", "--json", $outJson) + $ExtraArgs
    & claude plugin eval @claudeArgs
    $code = $LASTEXITCODE
    $script:ResultFiles += $outJson
    $isXfail = $ExpectedFailCases -contains $CaseName

    if ($code -eq 0) {
        if ($isXfail) {
            Write-Warning "$CaseName is listed in EVAL_EXPECTED_FAIL_CASES but PASSED - retire the xfail (drop it from EVAL_EXPECTED_FAIL_CASES / this script's default) so a future regression is caught again instead of staying silently exempted."
            $script:ExitStatus = 1
        }
        return
    }

    if ($isXfail -and (Test-ScoredResult $outJson)) {
        Write-Warning "exit $code, but $CaseName is in EVAL_EXPECTED_FAIL_CASES and produced a real (scored) result - not failing the gate."
    } elseif ($isXfail) {
        Write-Warning "claude plugin eval exited $code for $CaseName, and produced no scored result - a runner error is never exempted, even for a listed xfail."
        $script:ExitStatus = 1
    } else {
        Write-Warning "claude plugin eval exited $code for $CaseName"
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
