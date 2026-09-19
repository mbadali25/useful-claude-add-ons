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
# reports, but never flips this script's exit code.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PluginDir = Join-Path $RepoRoot "plugin\crew"
$Threshold = if ($env:EVAL_THRESHOLD) { $env:EVAL_THRESHOLD } else { "1.0" }
$MaxCostUsd = if ($env:EVAL_MAX_COST_USD) { $env:EVAL_MAX_COST_USD } else { "15" }
$OutDir = if ($env:EVAL_OUTPUT_DIR) { $env:EVAL_OUTPUT_DIR } else { Join-Path $RepoRoot ".work\plugin-evals" }
$ExpectedFailCases = if ($env:EVAL_EXPECTED_FAIL_CASES) { $env:EVAL_EXPECTED_FAIL_CASES -split "," } else { @("pm-does-not-write-code") }

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "claude CLI not found on PATH"
    exit 127
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$script:ExitStatus = 0
$ResultFiles = @()

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
    if ($code -ne 0) {
        if ($ExpectedFailCases -contains $CaseName) {
            Write-Warning "exit $code, but $CaseName is in EVAL_EXPECTED_FAIL_CASES - not failing the gate."
        } else {
            Write-Warning "claude plugin eval exited $code for $CaseName"
            $script:ExitStatus = 1
        }
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
