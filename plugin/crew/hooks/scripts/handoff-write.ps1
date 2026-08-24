# PreCompact hook (native Windows). Mirrors handoff-write.sh: snapshots the
# transcript and makes sure a handoff exists before compaction discards detail.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue

# PreCompact has no matcher, so this and handoff-write.sh both fire wherever
# both interpreters exist. Same hook name as handoff-write.sh so the two race
# for the same marker; only the winner does any work.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'hook_once.py') 'handoff-write' $d.session_id
if ($LASTEXITCODE -ne 0) { exit 0 }

if (-not (Test-Path ".crew/config.json")) { exit 0 }

$trigger = if ($d.trigger) { $d.trigger } else { "auto" }
$transcript = $d.transcript_path

New-Item -ItemType Directory -Force -Path ".crew/transcripts", ".work" | Out-Null
if ($transcript -and (Test-Path $transcript)) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  Copy-Item $transcript ".crew/transcripts/$stamp-$trigger.jsonl" -ErrorAction SilentlyContinue
  # keep the last 5 only
  Get-ChildItem ".crew/transcripts/*.jsonl" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 5 |
    Remove-Item -ErrorAction SilentlyContinue
}

$cfg = Get-Content .crew/config.json -Raw | ConvertFrom-Json
$path = if ($cfg.context.handoffPath) { $cfg.context.handoffPath } else { ".work/HANDOFF.md" }

# If no handoff exists, write a factual skeleton from the repo, not from memory.
if (-not (Test-Path $path)) {
  $branch = (git branch --show-current 2>$null)
  $head = (git rev-parse --short HEAD 2>$null)
  $changed = @()
  $changed += (git diff --name-only HEAD 2>$null) | Select-Object -First 30
  $changed += (git ls-files --others --exclude-standard 2>$null) | Select-Object -First 10
  $tickets = if (Test-Path .work/INDEX.md) {
    Select-String -Path .work/INDEX.md -Pattern '\| open \|' | Select-Object -First 5 | ForEach-Object { $_.Line }
  } else { $null }
  if (-not $tickets) { $tickets = "(none recorded)" }

  $lines = @(
    "# Handoff"
    "written: $(Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ') (auto, at $trigger compact)"
    "branch: $branch"
    "head: $head"
    ""
    "## Changed files"
  ) + $changed + @(
    ""
    "## Open tickets"
    $tickets
    ""
    "## Next action"
    "UNKNOWN - this skeleton was written automatically at compaction."
    "Verify against the diff before continuing."
  )
  $lines | Set-Content $path
}
exit 0
