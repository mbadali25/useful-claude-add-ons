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
# Whole-token match. A substring match blocks "s3://my-product-images" and
# "select * from products", which trains you to work around the guard.
if ($cmd -match '(?i)(^|[^\p{L}\p{N}])(prod|production)([^\p{L}\p{N}]|$)' -and
    $cmd -match '(?i)(^|[^\p{L}\p{N}])(psql|mysql|sqlcmd|mongo|az|aws|gcloud)([^\p{L}\p{N}]|$)') {
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
