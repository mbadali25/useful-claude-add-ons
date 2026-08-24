# Outbound-only notifier (native Windows). Mirrors notify.sh.
# Never reads from chat, never accepts instructions.
# Usage: notify.ps1 <event> <one-line message>
#   events: phase | gate | review | waiting | done
param(
  [string]$Event = "info",
  [string]$Msg = ""
)
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { "." }
Set-Location $root -ErrorAction SilentlyContinue

# Notification has no matcher, so this and notify.sh both fire wherever both
# interpreters exist when invoked as a hook. Same hook name as notify.sh so
# the two race for the same marker.
$raw = [Console]::In.ReadToEnd()
try { $d = $raw | ConvertFrom-Json } catch { $d = $null }
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python3, python -ErrorAction SilentlyContinue |
       Select-Object -First 1).Source
if (-not $py) { exit 0 }
& $py (Join-Path $dir 'hook_once.py') 'notify' $d.session_id
if ($LASTEXITCODE -ne 0) { exit 0 }

if (-not (Test-Path .crew/config.json)) { exit 0 }

$cfg = (Get-Content .crew/config.json -Raw | ConvertFrom-Json).notify
if ($null -eq $cfg) { exit 0 }
$provider = $cfg.provider
if (-not $provider -or $provider -eq "none") { exit 0 }
$events = $cfg.events
if ($events) {
  $eventList = $events -split ","
  if ($eventList -notcontains $Event) { exit 0 }
}

$repo = Split-Path -Leaf (git rev-parse --show-toplevel 2>$null)
if (-not $repo) { $repo = Split-Path -Leaf (Get-Location) }
$branch = (git branch --show-current 2>$null)

# One line. No diffs, no findings text, no ticket bodies, no secrets.
# A chat channel is a less controlled place than the repo; keep payloads dull.
$msgTrunc = if ($Msg.Length -gt 280) { $Msg.Substring(0, 280) } else { $Msg }
$repoPart = if ($branch) { "$repo/$branch" } else { $repo }
$text = "[$repoPart] ${Event}: $msgTrunc"

switch ($provider) {
  "teams" {
    $urlEnv = $cfg.urlEnv
    $url = if ($urlEnv) { [Environment]::GetEnvironmentVariable($urlEnv) } else { $null }
    if (-not $url) { [Console]::Error.WriteLine("notify: `$$urlEnv not set"); exit 0 }
    $body = @{
      type = "message"
      attachments = @(@{
        contentType = "application/vnd.microsoft.card.adaptive"
        content = @{
          type = "AdaptiveCard"
          version = "1.4"
          body = @(@{ type = "TextBlock"; text = $text; wrap = $true })
        }
      })
    } | ConvertTo-Json -Depth 10
    try {
      Invoke-RestMethod -Uri $url -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 10 | Out-Null
    } catch {}
  }
  "telegram" {
    $tokEnv = $cfg.tokenEnv
    $tok = if ($tokEnv) { [Environment]::GetEnvironmentVariable($tokEnv) } else { $null }
    $chat = $cfg.chatId
    if (-not $tok -or -not $chat) { [Console]::Error.WriteLine("notify: telegram token or chatId missing"); exit 0 }
    $disableNotif = if ($Event -eq "waiting") { "false" } else { "true" }
    $tgBody = @{
      chat_id = $chat
      text = $text
      disable_notification = $disableNotif
    }
    try {
      Invoke-RestMethod -Uri "https://api.telegram.org/bot$tok/sendMessage" -Method Post -Body $tgBody -TimeoutSec 10 | Out-Null
    } catch {}
  }
}
exit 0
