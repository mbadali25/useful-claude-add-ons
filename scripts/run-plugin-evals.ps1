# Runs the crew plugin's `claude plugin eval` suite under plugin/crew/evals/.
# Matched pair of scripts/run-plugin-evals.sh -- change one, change the other.
#
# The cases are DISCOVERED, not listed here (L-0713): every folder under
# plugin/crew/evals/ holding a case.yaml, in name order. With no case at all
# the script says "no eval cases" and exits 0 before it looks for the claude
# CLI: nothing ran, and it says so rather than reporting a pass.
#
# One case at a time: `--case <glob>` is a single-value filter (no documented
# comma-list or brace-expansion, and no "exclude" filter) -
# https://code.claude.com/docs/en/plugin-evals. Each case is granted Write and
# Edit, plus `--scaffold` when its case.yaml names a scaffold_script.
#
# A case passes only with a scored result THIS invocation wrote: the result
# file is removed before every invocation, an exit-0 run with an empty or
# errored "cases" array fails (Test-ScoredResult), and every non-zero exit
# fails. EVAL_PLUGIN_DIR points the runner at another plugin directory (its
# suite, scripts/_test/plugin-evals-runner.py, uses it).

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PluginDir = if ($env:EVAL_PLUGIN_DIR) { $env:EVAL_PLUGIN_DIR } else { Join-Path $RepoRoot "plugin\crew" }
$Threshold = if ($env:EVAL_THRESHOLD) { $env:EVAL_THRESHOLD } else { "1.0" }
$MaxCostUsd = if ($env:EVAL_MAX_COST_USD) { $env:EVAL_MAX_COST_USD } else { "15" }
$OutDir = if ($env:EVAL_OUTPUT_DIR) { $env:EVAL_OUTPUT_DIR } else { Join-Path $RepoRoot ".work\plugin-evals" }

$EvalsDir = Join-Path $PluginDir "evals"
# A plugin directory that is not there is a wrong EVAL_PLUGIN_DIR, not an
# empty suite. An absent evals/ is (git keeps no empty folder once the last
# case is deleted); one that is there but cannot be listed is could-not-tell.
if (-not (Test-Path -LiteralPath $PluginDir -PathType Container)) {
    Write-Error "plugin directory $PluginDir does not exist" -ErrorAction Continue
    exit 2
}
if ((Test-Path -LiteralPath $EvalsDir) -and -not (Test-Path -LiteralPath $EvalsDir -PathType Container)) {
    Write-Error "$EvalsDir exists but is not a directory - could not tell which cases it holds" -ErrorAction Continue
    exit 2
}
$Cases = @()
if (Test-Path -LiteralPath $EvalsDir -PathType Container) {
    $Cases = @(Get-ChildItem -LiteralPath $EvalsDir -Directory -ErrorAction Stop |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "case.yaml") -PathType Leaf } |
        Sort-Object -Property Name -CaseSensitive |
        ForEach-Object { $_.Name })
}
if ($Cases.Count -eq 0) {
    Write-Host "no eval cases under $EvalsDir - nothing ran (not a pass)"
    exit 0
}

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    # Write-Error is a non-terminating error by default, but
    # $ErrorActionPreference = "Stop" above promotes EVERY Write-Error call
    # to terminating - including this one - so without -ErrorAction Continue
    # the script throws right here and the `exit 127` below is never reached.
    Write-Error "claude CLI not found on PATH" -ErrorAction Continue
    exit 127
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$script:ExitStatus = 0
$script:ResultFiles = @()

function Test-ScoredResult {
    # True only when $Path is a non-empty file holding a real
    # aggregate-result.json ("cases" present, AND no individual run in it
    # recorded an error) - a run that started but ended badly is still graded
    # on what it produced, so a non-empty result with an error inside it is
    # NOT the same thing as a genuine scored result.
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    if ((Get-Item $Path).Length -eq 0) { return $false }
    try {
        $doc = Get-Content $Path -Raw | ConvertFrom-Json
    } catch {
        return $false
    }
    if (-not ($doc.cases -and $doc.cases.Count -gt 0)) { return $false }
    foreach ($c in $doc.cases) {
        foreach ($armName in @("with", "without")) {
            $runs = $c.arms.$armName
            if ($runs) {
                foreach ($run in $runs) {
                    if ($run.error) { return $false }
                }
            }
        }
    }
    return $true
}

function Invoke-EvalCase {
    param([string]$CaseName, [string[]]$ExtraArgs)
    $outJson = Join-Path $OutDir "$CaseName.json"
    # Never let a result file from a PREVIOUS run count as evidence for THIS one.
    if (Test-Path $outJson) { Remove-Item -Force $outJson }
    Write-Host "== $CaseName =="
    $claudeArgs = @($PluginDir, "--case", $CaseName, "--trust-plugin",
        "--threshold", $Threshold, "--max-cost-usd", $MaxCostUsd,
        "--no-publish", "--json", $outJson) + $ExtraArgs
    & claude plugin eval @claudeArgs
    $code = $LASTEXITCODE
    $script:ResultFiles += $outJson
    if ($code -ne 0) {
        Write-Warning "claude plugin eval exited $code for $CaseName"
        $script:ExitStatus = 1
    } elseif (-not (Test-ScoredResult $outJson)) {
        Write-Warning "$CaseName exited 0 but produced no scored result (empty or missing 'cases') - a runner error (e.g. a --case filter that matched nothing), not a pass."
        $script:ExitStatus = 1
    }
}

foreach ($case in $Cases) {
    $caseYaml = Get-Content -LiteralPath (Join-Path (Join-Path $EvalsDir $case) "case.yaml")
    if ($caseYaml -match '^\s*scaffold_script:') {
        Invoke-EvalCase -CaseName $case -ExtraArgs @("--scaffold", "--allow-tools", "Write", "Edit")
    } else {
        Invoke-EvalCase -CaseName $case -ExtraArgs @("--allow-tools", "Write", "Edit")
    }
}

Write-Host ""
Write-Host "== Delta table =="
"{0,-38} {1,6} {2,6} {3,7}  {4}" -f "CASE", "WITH", "W/OUT", "D", "COST"
foreach ($f in $script:ResultFiles) {
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
