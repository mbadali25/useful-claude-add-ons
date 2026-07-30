# Configuration reference

## Where the config file lives

`ticketctl.py` looks in this order and uses the first file it finds:

1. `$INFRA_TICKET_CONFIG` / `%INFRA_TICKET_CONFIG%` if set
2. `./.infra-ticket/config.json` - relative to the current directory
3. Windows only: `%APPDATA%\infra-ticket\config.json`
4. `~/.config/infra-ticket/config.json`

The project-local option (2) is there so a repo or runbook directory can carry its
own settings - a different Jira project key per repo, say. Just don't commit it if
it holds credentials.

`python scripts/ticketctl.py init` writes to the per-user location for your OS.
`doctor` always prints which file it actually loaded, which settles most "why is
it using the wrong project" questions.

## Where state lives

| Path | Contents |
| --- | --- |
| `<state>/tokens.json` | Cached access tokens, mode 0600 on Unix |
| `<state>/worklog.jsonl` | Append-only record of everything logged |
| `<state>/pending.jsonl` | Writes that failed and are awaiting `retry` |

`<state>` is `%LOCALAPPDATA%\infra-ticket` on Windows, otherwise
`$XDG_STATE_HOME/infra-ticket` or `~/.local/state/infra-ticket`.

`worklog.jsonl` is a local safety net, not a substitute for the ticket. It means
that even if the service desk was down all afternoon, there is still a timestamped
record of what was done.

## Full config schema

```json
{
  "provider": "zoho_sdp",
  "redact_secrets": true,

  "zoho_sdp": {
    "base_url": "https://ithelpdesk.solomoninsight.com",
    "portal": "",
    "accounts_url": "https://accounts.zoho.com",
    "client_id": "",
    "client_secret": "",
    "refresh_token": "",
    "defaults": {
      "request_type": "Incident",
      "mode": "Web Form",
      "priority": "Medium",
      "urgency": "",
      "impact": "",
      "category": "",
      "subcategory": "",
      "group": "",
      "site": "",
      "template": "",
      "requester_email": "",
      "technician_email": "",
      "assign_self": true
    }
  },

  "jira": {
    "site_url": "https://solomondevteam.atlassian.net",
    "auth_method": "api_token",
    "email": "",
    "api_token": "",
    "oauth": {
      "client_id": "",
      "client_secret": "",
      "refresh_token": "",
      "cloud_id": "",
      "redirect_uri": "http://localhost:8723/callback"
    },
    "defaults": {
      "project_key": "",
      "issue_type": "Task",
      "priority": "",
      "labels": ["infrastructure"],
      "components": [],
      "assign_self": true
    }
  }
}
```

Missing keys are filled from these defaults at load time, so a partial config
file is fine - you only need the keys you're changing.

### Top level

| Key | Meaning |
| --- | --- |
| `provider` | `zoho_sdp` or `jira`. Which platform writes go to. Aliases `zoho`, `sdp`, `atlassian` also work |
| `redact_secrets` | `true` (default) runs the secret scrubber on every body before sending |

Both providers can be configured at once; `provider` picks the active one and
`--provider` overrides it for a single command. That's handy during a migration,
or if change records go to one system and incidents to the other.

### Zoho ServiceDesk Plus

| Key | Notes |
| --- | --- |
| `base_url` | No trailing slash. Custom domains work as-is |
| `portal` | The `/app/<portal>/` segment from your UI URL. Required |
| `accounts_url` | Must match your Zoho data centre, or you get `invalid_client` |
| `defaults.*` | Names must exactly match values configured in your instance; blank means "let ServiceDesk Plus decide" |
| `defaults.technician_email` | Enables `--assign-self` and `search --mine` |
| `defaults.requester_email` | Who the request is filed on behalf of. Blank means the authenticating account |

### Jira

| Key | Notes |
| --- | --- |
| `site_url` | Used for auth in `api_token` mode, and always for building `/browse/KEY` links |
| `auth_method` | `api_token` or `oauth` |
| `email` + `api_token` | For `api_token` mode. `email` must be the token owner |
| `oauth.cloud_id` | Cached automatically; blank means look it up each run |
| `defaults.project_key` | Required to create issues |
| `defaults.labels` | Applied to every created issue. Spaces become hyphens |

## Environment variable overrides

Any of these override the config file, so credentials can stay out of files
entirely - useful in CI, on shared boxes, or where a secrets manager injects them.

| Variable | Overrides |
| --- | --- |
| `INFRA_TICKET_CONFIG` | Config file path |
| `INFRA_TICKET_PROVIDER` | `provider` |
| `ZOHO_SDP_BASE_URL` | `zoho_sdp.base_url` |
| `ZOHO_SDP_PORTAL` | `zoho_sdp.portal` |
| `ZOHO_SDP_CLIENT_ID` | `zoho_sdp.client_id` |
| `ZOHO_SDP_CLIENT_SECRET` | `zoho_sdp.client_secret` |
| `ZOHO_SDP_REFRESH_TOKEN` | `zoho_sdp.refresh_token` |
| `JIRA_SITE_URL` | `jira.site_url` |
| `JIRA_EMAIL` | `jira.email` |
| `JIRA_API_TOKEN` | `jira.api_token` |
| `JIRA_OAUTH_CLIENT_ID` | `jira.oauth.client_id` |
| `JIRA_OAUTH_CLIENT_SECRET` | `jira.oauth.client_secret` |
| `JIRA_OAUTH_REFRESH_TOKEN` | `jira.oauth.refresh_token` |
| `JIRA_CLOUD_ID` | `jira.oauth.cloud_id` |

One caveat: Jira OAuth rotates refresh tokens, and a rotated token can only be
persisted to the config file. If you supply `JIRA_OAUTH_REFRESH_TOKEN` from a
secrets manager, whatever wrote it there needs updating too, or auth breaks after
the first refresh. For OAuth, letting the tool own the config file is simpler.

### Setting them

Linux/macOS, current shell:
```bash
export JIRA_API_TOKEN='ATATT...'
```
Persist in `~/.bashrc` or `~/.zshrc`.

Windows PowerShell, current session:
```powershell
$env:JIRA_API_TOKEN = 'ATATT...'
```
Persist for your user:
```powershell
[Environment]::SetEnvironmentVariable('JIRA_API_TOKEN','ATATT...','User')
```
(Reopen the terminal afterwards.)

## Protecting the config file

On Linux/macOS the tool sets `0600` on files it writes. If you created the file by
hand:

```bash
chmod 600 ~/.config/infra-ticket/config.json
```

Windows doesn't inherit that, so restrict it explicitly:

```powershell
icacls "$env:APPDATA\infra-ticket\config.json" /inheritance:r /grant:r "$env:USERNAME:F"
```

If the directory is synced to OneDrive or Dropbox, move it or use environment
variables instead - a refresh token in a synced folder ends up in cloud backups.

## Cross-platform command notes

The script is identical on both platforms; only shell syntax differs.

| | Linux/macOS | Windows PowerShell |
| --- | --- | --- |
| Interpreter | `python3` (or `python`) | `python` |
| Path separator | `scripts/ticketctl.py` | `scripts\ticketctl.py` |
| Line continuation | `\` | backtick `` ` `` |
| Pipe text in | `cat n.md \| python3 ... --body-file -` | `Get-Content n.md \| python ... --body-file -` |
| Here-doc a note | `cat > n.md <<'EOF' ... EOF` | `@'` ... `'@ \| Set-Content n.md` |

Two Windows-specific things worth knowing:

- **PowerShell mangles multi-line strings passed as arguments.** This is the main
  reason `--body-file` exists. Write the note to a file and pass the path.
- **`Get-Content` piping is line-by-line**, which is fine here, but if you see
  encoding oddities use `Get-Content -Raw n.md` or just pass `--body-file n.md`
  directly, which sidesteps the shell entirely.

Forward slashes work in paths on Windows too, so `--body-file notes/work.md` is
fine in PowerShell.

## Verifying without touching the service desk

Every write command takes `--dry-run`, which needs no credentials and makes no
network calls - it prints the exact request that would be sent:

```
python scripts/ticketctl.py create --title "test" --body "test" --dry-run
```

This is the fastest way to check that defaults, labels, and field names are being
assembled the way you expect.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `no config file found` | Run `init`, or set `INFRA_TICKET_CONFIG` |
| `config at ... is not valid JSON` | A trailing comma or unquoted key. JSON allows no comments |
| Wrong project/portal being used | A `./.infra-ticket/config.json` in the current directory is shadowing the user-level one. `doctor` prints which file loaded |
| Credentials look right but auth fails | An environment variable is overriding the file. Check the table above |
| `provider ... is not supported` | Typo in `provider`; use `zoho_sdp` or `jira` |
| Queued writes never clear | `retry` prints why each one still fails; fix that, then re-run |
| Secret scrubber flags a false positive | Add `--no-redact` for that one command, or set `redact_secrets: false` to disable it entirely (not recommended) |
