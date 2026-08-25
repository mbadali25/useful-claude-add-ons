# PreCompact hook (native Windows). Mirrors handoff-write.sh: snapshots the
# transcript and makes sure a handoff exists before compaction discards detail.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { exit 0 }
$cwd = if ($d.cwd) { $d.cwd } elseif ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $cwd -ErrorAction SilentlyContinue
if (-not (Test-Path ".crew/config.json")) { exit 0 }

# No hook_once claim here on purpose: PreCompact can fire more than once per
# session, and both writes below are idempotent (the transcript copy is
# timestamped, the handoff skeleton only gets written if one doesn't already
# exist) -- duplication is safe, suppression of the only handoff is not.

$trigger = if ($d.trigger) { $d.trigger } else { "auto" }
New-Item -ItemType Directory -Path ".crew/transcripts", ".work" -Force | Out-Null

if ($d.transcript_path -and (Test-Path $d.transcript_path)) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  Copy-Item $d.transcript_path ".crew/transcripts/$stamp-$trigger.jsonl" -ErrorAction SilentlyContinue
  $keep = 5
  try {
    $k = (Get-Content .crew/config.json -Raw | ConvertFrom-Json).context.keepTranscripts
    if ($k -is [int] -and $k -ge 0) { $keep = $k }
  } catch { }
  Get-ChildItem ".crew/transcripts/*.jsonl" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

$cfg  = Get-Content .crew/config.json -Raw | ConvertFrom-Json
$path = if ($cfg.context.handoffPath) { $cfg.context.handoffPath } else { ".work/HANDOFF.md" }
if (Test-Path $path) { exit 0 }

# If no handoff exists, write a factual skeleton from the repo, not from memory.
$branch = (git rev-parse --abbrev-ref HEAD 2>$null)
$head   = (git rev-parse --short HEAD 2>$null)
$lines  = New-Object System.Collections.Generic.List[string]
$lines.Add("# Handoff")
$lines.Add("written: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) (auto, at $trigger compact)")
$lines.Add("branch: $branch")
$lines.Add("head: $head")
$lines.Add("")
$lines.Add("## Changed files")
(git diff --name-only HEAD 2>$null)                  | Select-Object -First 30 | ForEach-Object { $lines.Add($_) }
(git ls-files --others --exclude-standard 2>$null)   | Select-Object -First 10 | ForEach-Object { $lines.Add($_) }
$lines.Add("")
$lines.Add("## Open tickets")
$open = if (Test-Path .work/INDEX.md) { Select-String -Path .work/INDEX.md -Pattern '\| open \|' | Select-Object -First 5 } else { $null }
if ($open) { $open | ForEach-Object { $lines.Add($_.Line) } } else { $lines.Add("(none recorded)") }
$lines.Add("")
$lines.Add("## Next action")
$lines.Add("UNKNOWN - this skeleton was written automatically at compaction.")
$lines.Add("Verify against the diff before continuing.")

Set-Content -Path $path -Value $lines -Encoding UTF8
exit 0
