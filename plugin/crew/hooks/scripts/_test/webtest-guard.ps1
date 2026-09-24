# PowerShell driver for webtest_guard.py -- the twin of run-tests.sh's webtest
# section. Same fixture, same must-block / must-allow cases, driven from pwsh
# the way a Windows session calls it. Builds a throwaway repository under the
# temp directory and removes it; touches no real config.
#
#   pwsh -NoProfile -File hooks/scripts/_test/webtest-guard.ps1
#
# Exit 0 = all pass. Exit 1 = something regressed. Exit 77 = no python or git.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$guard = Join-Path (Split-Path -Parent $here) 'webtest_guard.py'

$py = $null
foreach ($name in 'python3', 'python', 'py') {
    $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py -or -not (Get-Command git -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine('SKIP: webtest-guard.ps1 needs python and git on PATH')
    exit 77
}

$script:pass = 0
$script:fail = 0
$wt = Join-Path ([System.IO.Path]::GetTempPath()) ("webtest-guard-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $wt | Out-Null

function Write-Text([string]$rel, [string]$text) {
    $path = Join-Path $wt $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    [System.IO.File]::WriteAllText($path, $text, [System.Text.UTF8Encoding]::new($false))
}

function Invoke-Git {
    & git -C $wt @args 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "git $args failed" }
}

function Expect([int]$want, [string]$label, [string]$root, [string[]]$guardArgs) {
    & $py $guard @guardArgs --root $root 2>&1 | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -eq $want) { $script:pass++ }
    else { $script:fail++; Write-Output "  FAIL  webtest-guard want=$want got=$rc  $label" }
}

try {
    Invoke-Git init -q -b main
    Invoke-Git config user.email t@example.invalid
    Invoke-Git config user.name t
    Write-Text '.gitignore' ".work/`n/playwright/.auth/`n/nogit/`n"
    Write-Text 'tests/a.spec.ts' "test('a', async () => {});`n"
    Write-Text 'playwright/.auth/user.json' '{}'
    Write-Text '.work/tickets/T-0007/spec.md' "# s`n`n## Exclusions`n- none`n"
    New-Item -ItemType Directory -Force -Path (Join-Path $wt 'nogit') | Out-Null
    Invoke-Git add -A
    Invoke-Git commit -qm base
    $base = (& git -C $wt rev-parse HEAD).Trim()
    $skips = @('skips', '--ticket', 'T-0007', '--base', $base)

    Expect 0 'skips: no change allows' $wt $skips
    Write-Text 'tests/a.spec.ts' "test('a', async () => {});`ntest.skip('flaky', async () => {});`n"
    Expect 1 'skips: added test.skip blocks' $wt $skips
    Write-Text '.work/tickets/T-0007/spec.md' "# s`n`n## Exclusions`n- skip: tests/a.spec.ts `"flaky`"`n"
    Expect 0 'skips: skip named in Exclusions allows' $wt $skips
    Write-Text 'tests/b.spec.ts' "test.fixme();`n"
    Expect 1 'skips: fixme in a new untracked spec blocks' $wt $skips
    Expect 0 'auth-leak: ignored .auth allows' $wt @('auth-leak')
    Invoke-Git add -f playwright/.auth/user.json
    Expect 1 'auth-leak: tracked .auth blocks' $wt @('auth-leak')
    Remove-Item Env:CREW_PLAYWRIGHT_IMAGE -ErrorAction SilentlyContinue
    Expect 77 'visual: off the pinned image is SKIP' $wt @('visual')
    $env:CREW_PLAYWRIGHT_IMAGE = 'mcr.microsoft.com/playwright:v1.62.0-noble'
    Expect 77 'visual: a different image is SKIP' $wt @('visual')
    Remove-Item Env:CREW_PLAYWRIGHT_IMAGE
    $env:GIT_CEILING_DIRECTORIES = $wt
    Expect 2 'auth-leak outside git is UNKNOWN, not a pass' (Join-Path $wt 'nogit') @('auth-leak')
    Remove-Item Env:GIT_CEILING_DIRECTORIES
}
finally {
    Remove-Item -Recurse -Force $wt -ErrorAction SilentlyContinue
}

Write-Output "RESULT: $script:pass passed, $script:fail failed"
if ($script:fail -ne 0) { exit 1 }
exit 0
