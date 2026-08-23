# PowerShell command guard for native Windows sessions.
# Mirrors guard.sh. Exit 2 blocks the command and returns the message to Claude.
$input_raw = [Console]::In.ReadToEnd()
try { $cmd = ($input_raw | ConvertFrom-Json).tool_input.command } catch { exit 0 }
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

function Block($msg) { [Console]::Error.WriteLine("BLOCKED: $msg"); exit 2 }

# destructive operations
if ($cmd -match '(?i)\bterraform\s+(apply|destroy)')            { Block "terraform apply/destroy is manual. Run plan and show it." }
if ($cmd -match '(?i)\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)') { Block "destructive DDL. Write a migration with a rollback." }
if ($cmd -match '(?i)\bgit\s+push\b.*(--force|-f)\b')            { Block "force push." }
if ($cmd -match '(?i)\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f)') { Block "destroys uncommitted work." }
if ($cmd -match '(?i)Remove-Item\s+.*-Recurse.*-Force.*[A-Z]:\\?\s*$') { Block "recursive delete of a drive root." }
if ($cmd -match '(?i)(prod|production)' -and $cmd -match '(?i)\b(psql|mysql|sqlcmd|mongo|az|aws|gcloud)\b') {
  Block "command targets production."
}

# secrets: never let values reach the transcript
$secretRead = '(?i)(secretsmanager\s+get-secret-value|ssm\s+get-parameter|keyvault\s+secret\s+show|vault\s+kv\s+get|kubectl\s+get\s+secret)'
if ($cmd -match $secretRead) {
  if ($cmd -notmatch '(\$env:|\$\(|>\s*[^|&]|\|\s*(Tee-Object|Set-Content))') {
    Block "this prints a secret value into the transcript. Capture it instead, e.g. `$env:DB_PASS = (aws secretsmanager get-secret-value --secret-id NAME --query SecretString --output text)"
  }
}
if ($cmd -match '(?i)\b(Get-Content|cat|type|echo|Write-Host)\b[^|]*\.env(\.[a-z]+)?(\s|$)') {
  Block "prints a .env file. Reference variable names, never values."
}
exit 0
