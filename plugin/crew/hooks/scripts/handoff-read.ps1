# SessionStart hook (native Windows). Prints the handoff note on clear/compact/resume.
# stdout from SessionStart is injected as context.

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

$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue

Remove-Item ".crew/.handoff-requested" -ErrorAction SilentlyContinue
# Auto-clear's own once-per-session claim. Without this reset it fires once per
# repository rather than once per session, which for a /clear is the difference
# between a feature and a one-shot.
Remove-Item ".crew/.autoclear-sent" -ErrorAction SilentlyContinue

# SessionStart fires once per SOURCE EVENT (startup, clear, compact, resume,
# fork), not once per session -- claiming on session id alone would let the
# `startup` firing burn the claim, exit here on the filter having done
# nothing, and make the `clear` firing lose the race: the handoff would never
# be read after /clear, which is the entire point of this hook. So the claim
# comes AFTER the filter and is keyed on session+source together. Same hook
# name and key shape as handoff-read.sh so the two race for the same marker.
if ($d.source -notin @("clear","compact","resume","fork")) { exit 0 }
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
# `memory.inject` on (the default since 1.0.0) hands the handoff to
# crew-context.ps1, which injects it inside its own SessionStart budget --
# printing it here too would put it in the session twice. Same reader as that hook (crew_context.inject_enabled).
# No double quotes in the -c text: 5.1 strips them from native arguments.
& $py -c 'import sys; sys.path.insert(0, sys.argv[1]); import crew_context as c; sys.exit(0 if c.inject_enabled(c.find_root(sys.argv[2])) else 1)' $dir (Get-Location).Path 2>$null
if ($LASTEXITCODE -eq 0) { exit 0 }
& $py (Join-Path $dir 'hook_once.py') 'handoff-read' "$($d.session_id)-$($d.source)"
if ($LASTEXITCODE -ne 0) { exit 0 }

if (-not (Test-Path ".crew/config.json")) { exit 0 }
$cfg = Get-Content .crew/config.json -Raw | ConvertFrom-Json

$path = if ($cfg.context.handoffPath) { $cfg.context.handoffPath } else { ".work/HANDOFF.md" }
if (-not (Test-Path $path)) { exit 0 }

# Stale-handoff check, right before this note would be injected as though it
# were current -- the concrete failure this exists to catch: a note still
# saying "at the spec-review gate" hours after the gate closed and more
# commits landed past it. Delegates to crew_state.archive_stale_handoff
# rather than reimplementing its signals here; see that function and
# crew_state.handoff_staleness for what each signal catches and why. Fails
# open: any error below (bad JSON, python raising, git absent) leaves
# $archivedPath empty and falls through to printing the note unchanged,
# exactly like every session before this feature existed -- a hook that
# breaks startup over a staleness check is worse than one honestly-stale
# note.
$verdictRaw = & $py (Join-Path $dir 'crew_state.py') '--archive-stale-handoff' 2>$null
$archivedPath = ""
if ($LASTEXITCODE -eq 0 -and $verdictRaw) {
    try {
        $verdict = ($verdictRaw -join "`n") | ConvertFrom-Json
        if ($verdict.archived -eq $true) { $archivedPath = $verdict.archivedPath }
    } catch { $archivedPath = "" }
}
if ($archivedPath) {
    Write-Output "## Handoff from the previous session ($($d.source))"
    Write-Output ""
    Write-Output "A handoff note was here, but it described a state this repository has"
    Write-Output "since moved past. It has been archived, not deleted, at"
    Write-Output "$archivedPath for the record -- nothing from it is being treated"
    Write-Output "as current this session."
    exit 0
}

Write-Output "## Handoff from the previous session ($($d.source))"
Write-Output ""
Get-Content $path
Write-Output ""
Write-Output "The working tree is the source of truth. Verify the notes above against git diff before acting on them."
exit 0
