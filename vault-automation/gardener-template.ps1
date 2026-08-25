# Vault gardener - nightly reflection pipeline for a claude-memories-style Obsidian vault.
# Installed to <vault>\.claude\gardener.ps1 by setup-vault-automation.ps1 (placeholders
# rewritten at install). Registered as scheduled task "Claude Vault Gardener".
# Logs to <vault>\.claude\gardener-logs\.
#
# What it does: runs a headless Claude session that processes inbox/pending-reflect.md,
# distills queued session transcripts into wiki/concepts + wiki/daily (with sources),
# checks entries off, and - when the vault is a git repo - commits (and pushes if a
# remote exists). Vaults relying on Obsidian Sync alone work fine: git steps are skipped.

$ErrorActionPreference = 'Continue'
$vault = '__VAULT_PATH__'
$claudeExe = '__CLAUDE_EXE__'
# Consent to the git layer (git add -A && commit && push) is decided ONCE, at
# `setup-vault-automation.ps1 -UseGit` time, and baked in here. It must never be
# re-derived at nightly run time: if this vault later becomes a git repo (or grows
# a remote) for reasons unrelated to this pipeline, that alone must not turn on an
# unattended `git add -A && push`, since -A stages untracked files that were never
# meant to be committed. Runtime checks below may only narrow this (still skip
# push if there is in fact no repo/remote), never widen it.
$gitEnabled = __GIT_ENABLED__
$logDir = Join-Path $vault '.claude\gardener-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("gardener-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

Get-ChildItem $logDir -Filter 'gardener-*.log' |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Git is optional: Obsidian Sync users may have no repo and no remote. $gitEnabled
# (baked in above) is the consent gate; the Test-Path/remote checks below can only
# narrow it further, e.g. -UseGit was set but this particular vault isn't (yet) a
# repo, never widen it beyond what was consented to at setup time.
Set-Location $vault
$hasGit = $gitEnabled -and (Test-Path (Join-Path $vault '.git'))
$hasRemote = $false
if ($hasGit) {
    git remote get-url origin 2>$null | Out-Null
    $hasRemote = ($LASTEXITCODE -eq 0)
}
$gitStep = if ($hasGit -and $hasRemote) {
    '6. Commit everything: git add -A && git commit -m "gardener: nightly reflection <date>" && git push. If nothing changed, no commit.'
} elseif ($hasGit) {
    '6. Commit everything locally: git add -A && git commit -m "gardener: nightly reflection <date>". No remote is configured - do NOT push.'
} else {
    '6. This vault is not a git repository (it relies on Obsidian Sync) - skip all git operations.'
}

$prompt = @"
You are the vault gardener for this Obsidian vault (the current directory). Work autonomously, no questions.

1. Read inbox/pending-reflect.md. Take up to 5 UNCHECKED entries (oldest first). If none, skip to step 5.
2. For each entry: read its transcript file (the transcript= path; if missing, check the entry off with a "transcript gone" note and move on). Distill per the reflect skill's conventions: create or update wiki/concepts pages for durable knowledge (decisions, root causes, runbooks, gotchas - not routine chatter), each with proper frontmatter (type, title, created/updated, status, tags, project) AND a populated sources: list linking the session; append a digest section for the day to wiki/daily/<date>.md (create if needed). Never store credentials or secrets in any note.
3. Check off each processed entry in inbox/pending-reflect.md.
4. If any distilled work changed infrastructure topology or process structure, update the matching canvas in wiki/maps/ per the canvas skill (surgical edits only).
5. Provenance pass: pick up to 5 concepts with empty sources: whose subject matches session pages that exist in wiki/sessions/, and link them. Promote status developing -> established for concepts referenced by 3+ sessions.
$gitStep

Be economical: this is maintenance, not research. Summarize what you did in your final message.
"@

"[$(Get-Date -Format s)] gardener start (gitEnabled=$gitEnabled git=$hasGit remote=$hasRemote)" | Out-File $log -Encoding utf8
& $claudeExe -p $prompt --dangerously-skip-permissions --max-turns 80 2>&1 |
    Out-File $log -Append -Encoding utf8
"[$(Get-Date -Format s)] gardener done (claude exit: $LASTEXITCODE)" | Out-File $log -Append -Encoding utf8
