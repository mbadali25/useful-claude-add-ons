# PowerShell command guard for native Windows sessions.
# Mirrors guard.sh. Exit 2 blocks the command and returns the message to Claude.
$input_raw = [Console]::In.ReadToEnd()
try { $cmd = ($input_raw | ConvertFrom-Json).tool_input.command } catch { exit 0 }
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

function Block($msg) { [Console]::Error.WriteLine("BLOCKED: $msg"); exit 2 }

# destructive operations
if ($cmd -match '(?i)\bterraform\s+(apply|destroy)')            { Block "terraform apply/destroy is manual. Run plan and show it." }
if ($cmd -match '(?i)\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)') { Block "destructive DDL. Write a migration with a rollback." }
# Mirrors guard.sh: the git rules used to require the subcommand to sit
# immediately after `git`, so `git -C /path push --force`, `git -c a=b push -f`
# and `git --git-dir=... reset --hard` all sailed through. $gitPre swallows any
# run of leading git options (each optionally followed by its value token).
$gitPre = '(?i)\bgit\s+(-\S+\s+([^-]\S*\s+)?)*'
if ($cmd -match "${gitPre}push\b.*(--force|-f)\b")               { Block "force push." }
# `git push origin +main` is a force push with no --force token in it.
if ($cmd -match "${gitPre}push\b[^;&|]*\s\+[^\s;&|]")            { Block "force push (leading-plus refspec)." }
if ($cmd -match "${gitPre}(reset\s+--hard|clean\s+-[a-z]*f)")    { Block "destroys uncommitted work." }
if ($cmd -match '(?i)Remove-Item\s+.*-Recurse.*-Force.*[A-Z]:\\?\s*$') { Block "recursive delete of a drive root." }
# Argument-position match, not substring presence. Mirrors guard.sh: the old
# check matched "prod"/"production" as a whole word ANYWHERE in the command
# text, plus an infra CLI name ANYWHERE in that same text - so it blocked
# prose (e.g. `gh pr comment ... --body "...the prod outage..."`, where "gh"
# is not an infra CLI) and unrelated resource names (e.g. `aws events
# describe-rule --name thd-prod-inventory-created`, where "prod" is a middle
# segment). Now: the infra CLI must be the actual program invoked, and the
# environment name must be the whole argument or the first/last hyphen-joined
# segment of one - never a message-flag value, a web URL, or a token with
# whitespace (only a quoted string can carry one).
function Test-EnvArgHit([string]$c) {
  $tools = @('psql', 'mysql', 'sqlcmd', 'mongo', 'az', 'aws', 'gcloud')
  $envs = @('prod', 'production')
  $proseFlags = @('-m', '--message', '--body', '--comment', '--title', '--description', '--subject', '-F')
  $dq = [char]34
  $tokRegex = "$dq([^$dq]*)$dq|(\S+)"
  foreach ($part in [regex]::Split($c, '&&|\|\||[|;]')) {
    $p = $part.Trim()
    if (-not $p) { continue }
    $toks = @([regex]::Matches($p, $tokRegex) | ForEach-Object {
      if ($_.Groups[1].Success) { $_.Groups[1].Value } else { $_.Groups[2].Value }
    })
    if (-not $toks -or $toks.Count -eq 0) { continue }
    $prog = ($toks[0] -split '[\\/]')[-1].ToLower()
    if ($tools -notcontains $prog) { continue }
    $skipNext = $false
    for ($i = 1; $i -lt $toks.Count; $i++) {
      $tok = $toks[$i]
      if ($skipNext) { $skipNext = $false; continue }
      if ($proseFlags -contains $tok) { $skipNext = $true; continue }
      if ($tok -match '(?i)^https?://') { continue }
      if ($tok -match '\s') { continue }
      $rest = $tok -replace '^[A-Za-z][A-Za-z0-9+.\-]*://', ''
      # @(...) forces an array even when exactly one segment survives the
      # filter - PowerShell otherwise unwraps a single-item pipeline result
      # to a bare string, and $segs[0] would then index a character, not
      # the segment.
      $segs = @(($rest -split '[^\p{L}\p{N}]+') | Where-Object { $_ -ne '' })
      if ($segs.Count -gt 0 -and ($envs -contains $segs[0].ToLower() -or $envs -contains $segs[-1].ToLower())) {
        return $true
      }
    }
  }
  return $false
}
if (Test-EnvArgHit $cmd) {
  Block "command targets production. If this is not production, rename the argument or run it yourself."
}

# secrets: never let values reach the transcript
$secretRead = '(?i)(secretsmanager\s+get-secret-value|ssm\s+get-parameter|keyvault\s+secret\s+show|vault\s+kv\s+get|kubectl\s+get\s+secret)'
if ($cmd -match $secretRead) {
  # Writing a secret to a file is worse than printing one, not an exemption.
  if ($cmd -match '>\s*[^|&\s]') {
    Block "this writes a secret value to a file. Capture it into a variable instead: `$env:DB_PASS = (...)"
  }
  if ($cmd -match '\|\s*(Tee-Object|Set-Content|Out-File|Add-Content)') {
    Block "this pipes a secret value to a file cmdlet, which persists it. Capture it into a variable instead: `$env:DB_PASS = (...)"
  }
  # The one safe shape: assign the output to a variable.
  if ($cmd -notmatch '(^|\s|;)\$(env:)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*\(') {
    Block "this prints a secret value into the transcript. Capture it instead, e.g. `$env:DB_PASS = (aws secretsmanager get-secret-value --secret-id NAME --query SecretString --output text)"
  }
}
if ($cmd -match '(?i)\b(Get-Content|cat|type|echo|Write-Host)\b[^|]*\.env(\.[a-z]+)?(\s|$)') {
  Block "prints a .env file. Reference variable names, never values."
}
exit 0
