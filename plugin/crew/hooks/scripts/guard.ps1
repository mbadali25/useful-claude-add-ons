# PowerShell command guard for native Windows sessions.
# Mirrors guard.sh. Exit 2 blocks the command and returns the message to Claude.
$input_raw = [Console]::In.ReadToEnd()
try { $cmd = ($input_raw | ConvertFrom-Json).tool_input.command } catch { exit 0 }
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

function Block($msg) { [Console]::Error.WriteLine("BLOCKED: $msg"); exit 2 }

# --- configurable guardrails ----------------------------------------------
#
# Mirrors guard.sh exactly, and shells out to the SAME resolver rather than
# reimplementing config layering in PowerShell. These two files drift
# independently -- three bypasses fixed in #132 were open in both -- and the
# layering rule whose whole point is that a cloned repo cannot widen it must
# not have two implementations, either of which could be the one that forgets
# to ratchet. `Test-EnvArgHit` below is a deliberate reimplementation (it is a
# tokenizer, run on every command); this is not that.
#
# FAIL CLOSED, loudly. No python, a crew_config that raises, an unparseable
# line -- each is `block`, with the reason said out loud. "Could not check" is
# its own outcome and never collapses into "checked, and fine".
$guardDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$guardPy = (Get-Command python3, python, py -ErrorAction SilentlyContinue |
            Select-Object -First 1).Source

function Invoke-Guard([string]$name, [string]$msg) {
  if (-not $guardPy) {
    Block "$msg [guards.$name stays ``block``: no python to read the config]"
  }
  $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
  $line = & $guardPy (Join-Path $guardDir 'crew_config.py') `
            --root $root --guard $name --command $cmd --record 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $line) {
    Block "$msg [guards.$name stays ``block``: crew could not read it]"
  }
  # `-is [array]` because a multi-line stdout arrives as string[]; the payload
  # is one line, so take the first and let a second line be ignored rather
  # than concatenated into a field.
  if ($line -is [array]) { $line = $line[0] }
  $parts = ([string]$line).TrimEnd("`r", "`n") -split "`t"
  if ($parts.Count -lt 5) {
    Block "$msg [guards.$name stays ``block``: unreadable decision from crew_config]"
  }
  $decision = $parts[0]; $policy = $parts[1]; $marker = $parts[2]
  # `-` is the producer's spelling of an empty field -- see the note beside the
  # print in crew_config.py's --guard branch. `-split` does not collapse runs
  # the way bash's `read` does, so this flavour would be correct without the
  # convention; it follows it anyway, because two flavours reading one line by
  # different rules is how they come to disagree about what it said.
  $target = if ($parts[3] -eq '-') { '' } else { $parts[3] }
  $reason = if ($parts[4] -eq '-') { '' } else { $parts[4] }
  # Field 6, `access`, is read by Invoke-ProdGuard and ignored here. Reading it
  # by index in both places keeps the two flavours agreeing about a line they
  # take from the same producer.
  switch ($decision) {
    'allow' {
      # Under `allow` nothing is silent. crew_config.py --record wrote the
      # durable row to .crew/guard.log; this is the half the user sees now.
      [Console]::Error.WriteLine("crew guard: guards.$name is ``$policy`` - ALLOWED: $reason")
      [Console]::Error.WriteLine("  command: $cmd")
      if ($target) { [Console]::Error.WriteLine("  target branch: $target") }
      return
    }
    'ask' {
      # A PreToolUse hook has no interactive stdin, so "stop for a yes at that
      # moment" is a refusal naming the file that approves THIS command. The
      # marker is keyed on a digest of the command, so approving one force
      # push does not approve the next one.
      [Console]::Error.WriteLine("BLOCKED (guards.${name} = ask): $msg")
      [Console]::Error.WriteLine("The exact command:")
      [Console]::Error.WriteLine("  $cmd")
      if ($target) { [Console]::Error.WriteLine("Target branch: $target") }
      [Console]::Error.WriteLine("To approve THIS command and nothing else, then re-run it:")
      [Console]::Error.WriteLine("  New-Item -ItemType File $marker")
      # The window, and whether a marker already there has fallen outside it,
      # come from $reason rather than being spelled here: the bound is
      # GUARD_APPROVAL_TTL in crew_guards.py, and a number restated in two
      # shells is a number that will disagree with itself.
      if ($reason) { [Console]::Error.WriteLine($reason) }
      exit 2
    }
    'block'  { Block $msg }
    default  { Block "$msg [guards.$name stays ``block``: unreadable decision from crew_config]" }
  }
}

# `guards.prodDatabase` / `guards.prodServer`, mirroring guard.sh's
# `prod_guarded` line for line. A separate function from Invoke-Guard for the
# reason stated there: these two fire on ORDINARY commands, so an `allow` line
# printed unconditionally would put a crew banner above every remote shell in
# the session. Silent when no declared pattern matched; loud on every decision
# a declared pattern actually produced.
$script:ProdTarget = ''
function Invoke-ProdGuard([string]$name, [string]$msg) {
  $script:ProdTarget = ''
  # NO PYTHON is a stand-down; a FAILED RESOLVER is a refusal. Without python
  # crew can read no config at all, so blocking here would refuse every `ssh`
  # in every repo on the machine, and Test-EnvArgHit below still blocks on its
  # own regex with no python. A python that IS here and then fails is crew
  # broken on the question of whether this targets production, which blocks.
  if (-not $guardPy) { return }
  $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
  $line = & $guardPy (Join-Path $guardDir 'crew_config.py') `
            --root $root --guard $name --command $cmd --record 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $line) {
    Block "$msg [guards.$name`: crew could not read it, and could not tell whether this targets production]"
  }
  if ($line -is [array]) { $line = $line[0] }
  $parts = ([string]$line).TrimEnd("`r", "`n") -split "`t"
  if ($parts.Count -lt 6) {
    Block "$msg [guards.$name`: unreadable decision from crew_config]"
  }
  $decision = $parts[0]; $policy = $parts[1]
  $target = if ($parts[3] -eq '-') { '' } else { $parts[3] }
  $reason = if ($parts[4] -eq '-') { '' } else { $parts[4] }
  $access = if ($parts[5] -eq '-') { '' } else { $parts[5] }
  # An empty target means NO DECLARED PATTERN MATCHED -- not that the guard
  # passed. Returning silently keeps `ssh` to an undeclared host as quiet as it
  # was before schema 6.
  if (-not $target) { return }
  $script:ProdTarget = $target
  switch ($decision) {
    'allow' {
      [Console]::Error.WriteLine("crew guard: guards.$name is ``$policy`` - ALLOWED: $reason")
      [Console]::Error.WriteLine("  command: $cmd")
      if ($access) { [Console]::Error.WriteLine("  classified as: $access") }
      return
    }
    'block'  { Block "$msg [$reason]" }
    default  { Block "$msg [guards.$name stays ``none``: unreadable decision from crew_config]" }
  }
}

# destructive operations
# $tfPre is $gitPre's reason applied to the neighbour that never got it:
# `terraform -chdir=infra apply` sailed through a rule requiring `apply` to sit
# immediately after `terraform`, while the git rules below had already been
# fixed for that exact shape.
# `tofu` is here because OpenTofu is terraform's drop-in fork: same
# subcommands, same blast radius, a different binary name. A NEW refusal, not
# a preserved one -- the schema 6 upgrade note says so rather than letting
# "the default is block, so nothing changed" cover it.
$tfPre = '(?i)\b(terraform|tofu)(\s+-\S+)*\s+'
if ($cmd -match "${tfPre}(apply|destroy)")                      { Invoke-Guard terraformApply "terraform/tofu apply/destroy is manual. Run plan and show it." }
if ($cmd -match '(?i)\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)') { Block "destructive DDL. Write a migration with a rollback." }
# Mirrors guard.sh: the git rules used to require the subcommand to sit
# immediately after `git`, so `git -C /path push --force`, `git -c a=b push -f`
# and `git --git-dir=... reset --hard` all sailed through. $gitPre swallows any
# run of leading git options (each optionally followed by its value token).
$gitPre = '(?i)\bgit\s+(-\S+\s+([^-]\S*\s+)?)*'
# `[^;&|]*`, not `.*`: the greedy form spanned command separators, so an
# unrelated `-f` later in a compound command blocked an ordinary push.
# Observed: `git push -q origin br; echo done; [ -f $x ] && ...` was blocked
# because the `.*` reached the `-f` three commands later. The leading-plus
# check below already scoped itself this way; this line did not.
# `[^;&|]*` is why `git push 2>&1 --force origin main` passed: `2>&1` CONTAINS
# an `&`, so the scan stopped before `--force`. $arg allows `&` only as part of
# a redirection (`&` then a digit), so `2>&1` is crossed while `&&`, a trailing
# `&` and `|` still stop the scan exactly as before.
$arg = '([^;&|]|&[0-9])*'
if ($cmd -match "${gitPre}push\b${arg}(--force|-f)\b")           { Invoke-Guard forcePush "force push." }
# `git push origin +main` is a force push with no --force token in it.
if ($cmd -match "${gitPre}push\b${arg}\s\+[^\s;&|]")             { Invoke-Guard forcePush "force push (leading-plus refspec)." }
# `gh pr merge --admin` merges PAST a branch protection rule the repository's
# owner put there. No crew guard refused it before schema 6, in either
# flavour, so `guards.adminMerge` arriving at `block` is a NEW refusal.
#
# Scope, stated rather than implied: `gh pr merge` carrying `--admin`, in any
# argument position. NOT a hand-rolled `gh api -X PUT .../pulls/N/merge`,
# which reaches the same endpoint without the flag. A real gap, left open
# deliberately -- a rule wide enough to catch every `gh api` call to a merge
# URL is wide enough to block reading one.
$ghMerge = '(?i)\bgh\s+pr\s+merge\b'
if ($cmd -match "${ghMerge}${arg}--admin\b")                     { Invoke-Guard adminMerge "gh pr merge --admin merges past the repo's branch protection." }
# --- production access ----------------------------------------------------
# Which TOOLS could be aimed at production; whether they ARE is decided by
# `production.databases` / `production.hosts` in the repo config, through
# crew_config.py. Same two regexes as guard.sh, same deliberately wide list: a
# tool absent here never reaches the resolver.
#
# `([^\s;&|]*[\\/])?` is guard.sh's fix, for the same bypass in this flavour:
# both alternations required the executable to follow whitespace or a
# separator, so `/usr/bin/ssh prod-web-1 ...` and `C:\tools\ssh.exe ...`
# reached the resolver in neither flavour -- prodServer bypassed at `none` by
# typing a path. It cost the other direction too: `PROD_HIT` stayed false, so
# `/usr/bin/psql -h prod-db-1 ...` was refused by Test-EnvArgHit below even at
# `full`. `\b` after the name already allows the `.exe` suffix.
#
# The `aws` alternations are deliberately NOT given the prefix: `\baws` already
# matches inside `/usr/local/bin/aws`.
$dbTools = '(?i)(^|[\s;&|])([^\s;&|]*[\\/])?(psql|mysql|mariadb|sqlcmd|mongosh|mongo|redis-cli|cqlsh)\b|\baws\s+(rds|redshift|dynamodb|docdb)\b'
$srvTools = '(?i)(^|[\s;&|])([^\s;&|]*[\\/])?(ssh|scp|plink|rsync)\b|\baws\s+(ssm|ec2)\b'
$prodHit = $false
if ($cmd -match $dbTools) {
  Invoke-ProdGuard prodDatabase "this targets a database declared in production.databases."
  if ($script:ProdTarget) { $prodHit = $true }
}
if ($cmd -match $srvTools) {
  Invoke-ProdGuard prodServer "this targets a host declared in production.hosts."
  if ($script:ProdTarget) { $prodHit = $true }
}
# `git reset HEAD --hard` required `--hard` to follow `reset` immediately, so
# naming the ref bypassed it. `--soft HEAD~1` still does not match: no `--hard`.
if ($cmd -match "${gitPre}(reset(\s+[^\s;&|]+)*\s+--hard|clean\s+-[a-z]*f)") { Block "destroys uncommitted work." }
if ($cmd -match '(?i)Remove-Item\s+.*-Recurse.*-Force.*[A-Z]:\\?\s*$') { Block "recursive delete of a drive root." }
# Argument-position match, not substring presence. Mirrors guard.sh: the old
# check matched "prod"/"production" as a whole word ANYWHERE in the command
# text, plus an infra CLI name ANYWHERE in that same text - so it blocked
# prose (e.g. `gh pr comment ... --body "...the prod outage..."`, where "gh"
# is not an infra CLI) and unrelated resource names (e.g. `aws events
# describe-rule --name acme-prod-inventory-created`, where "prod" is a middle
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
# Skipped ONLY when a declared `production.*` pattern already matched this
# command, because then the configured level has answered the same question
# with better information. Leaving both in would mean `prodDatabase: full`
# still refused `prod-db-1` -- a key that reads as configurable and is not.
# With nothing declared, $prodHit is false and this behaves exactly as it did
# before schema 6.
if ((Test-EnvArgHit $cmd) -and (-not $prodHit)) {
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
  # The assignment must capture THIS read. The old test asked only whether an
  # assignment appeared anywhere, so `$unrelated = (Get-Date); aws
  # secretsmanager get-secret-value ...` satisfied it and printed the secret.
  # Requiring the secret read to sit INSIDE the parenthesised expression, with
  # no separator between, is the difference between "a capture happened" and
  # "this was captured".
  #
  # ...and that was still a question about ANY occurrence, in both flavours: a
  # command carrying two secret reads, the first captured and the second
  # printed, satisfied it and printed the second. So this COUNTS, exactly as
  # guard.sh does -- every occurrence must be carried by a capture, and one
  # uncaptured occurrence is a refusal. See guard.sh for why the gap excludes
  # `)` and why this is not done by splitting on separators.
  $secretHeld = "(^|\s|;)\`$(env:)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*\([^;&|)]*${secretRead}"
  $secretCount = [regex]::Matches($cmd, $secretRead).Count
  $heldCount = [regex]::Matches($cmd, $secretHeld).Count
  if ($heldCount -lt $secretCount) {
    Block "this prints a secret value into the transcript. Capture it instead, e.g. `$env:DB_PASS = (aws secretsmanager get-secret-value --secret-id NAME --query SecretString --output text)"
  }
}
if ($cmd -match '(?i)\b(Get-Content|cat|type|echo|Write-Host)\b[^|]*\.env(\.[a-z]+)?(\s|$)') {
  Block "prints a .env file. Reference variable names, never values."
}
exit 0
