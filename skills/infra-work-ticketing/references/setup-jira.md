# Setting up Jira Cloud

Target instance: **https://solomondevteam.atlassian.net** (Jira Cloud).

There are two supported authentication methods. Pick deliberately:

| | API token (Basic auth) | OAuth 2.0 (3LO) |
| --- | --- | --- |
| Setup effort | 2 minutes | 15 minutes |
| Needs a browser redirect | No | Yes, once |
| Acts as | The token owner | The consenting user |
| Best for | One person's own machine | Shared tooling, several users, tighter scoping |
| Maintenance | Rotate before the token expires | Refresh token rotates automatically |

**Start with the API token.** It is fully supported, and moving to OAuth later is
a config change plus one browser round-trip - nothing else in the setup changes.

---

# Option A - API token (recommended to start)

## Step 1 - create the token

1. Sign in to Jira, then go to
   https://id.atlassian.com/manage-profile/security/api-tokens
2. **Create API token**, give it a label like `ticketctl`, and choose an expiry.
   Atlassian now requires an expiry date on API tokens (up to one year), so note
   the date somewhere - the failure mode when it lapses is a bare 401.
3. Copy the token immediately; it is shown once.

## Step 2 - find your project key

Open any issue in the project you'll log against. The key is the prefix of the
issue key: `OPS-412` means the project key is `OPS`. You can also see it under
**Project settings → Details**.

## Step 3 - configure

```
python scripts/ticketctl.py init --provider jira
```

Edit the file it names:

```json
{
  "provider": "jira",
  "jira": {
    "site_url": "https://solomondevteam.atlassian.net",
    "auth_method": "api_token",
    "email": "you@solomoninsight.com",
    "api_token": "ATATT...",
    "defaults": {
      "project_key": "OPS",
      "issue_type": "Task",
      "priority": "",
      "labels": ["infrastructure"],
      "components": [],
      "assign_self": true
    }
  }
}
```

`email` must be the Atlassian account the token belongs to. A mismatch produces a
401 that looks identical to an expired token, so double-check it.

If you'd rather not have the token sitting in a file, leave `api_token` empty and
set an environment variable instead - see `configuration.md`.

## Step 4 - verify

```
python scripts/ticketctl.py doctor
python scripts/ticketctl.py create --title "Test - ticketctl integration check" --body "Setup check." --dry-run
```

---

# Option B - OAuth 2.0 (3LO)

Use this when the integration is shared, when you want scoped rather than
account-wide access, or when policy forbids long-lived Basic credentials.

Two structural differences from the API token path, both of which cause confusion
if you don't expect them:

- OAuth requests go to `https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/...`,
  **not** to `solomondevteam.atlassian.net`. The tool handles this, but it's why
  the config still needs `site_url` (to build browse links and identify which
  site to use).
- Atlassian uses **rotating refresh tokens**: every refresh returns a new refresh
  token and invalidates the previous one. The tool writes the new one back to the
  config file automatically. If that file is read-only or on a shared volume where
  writes get clobbered, authentication will break after an hour - so make sure the
  config is writable by the account running the tool.

## Step 1 - create the app

1. Go to https://developer.atlassian.com/console/myapps/ and sign in.
2. **Create → OAuth 2.0 integration**, name it (e.g. `ticketctl`), accept the
   terms, **Create**.

## Step 2 - add the Jira API and scopes

1. In the app, open **Permissions**, find **Jira API**, click **Add**, then
   **Configure**.
2. Add these classic scopes:

   | Scope | Why |
   | --- | --- |
   | `read:jira-work` | Read issues, search, read comments |
   | `write:jira-work` | Create issues, add comments, send notifications |
   | `read:jira-user` | Resolve email addresses to accounts for `--email` |

3. `offline_access` is not listed in the console - it is added to the authorize
   URL instead, and the tool does that for you. Without it you get an access
   token that dies in an hour and no refresh token.

## Step 3 - set the callback URL

1. Open **Authorization**, then **Configure** next to OAuth 2.0 (3LO).
2. Set the **Callback URL** to:

   ```
   http://localhost:8723/callback
   ```

   Nothing needs to listen on that port. The browser will fail to load the page
   after you consent - that's expected and fine, because the authorization code
   you need is sitting in the address bar.
3. Save.

## Step 4 - copy the credentials

**Settings** shows the **Client ID** and **Secret**. Put them in the config:

```json
{
  "provider": "jira",
  "jira": {
    "site_url": "https://solomondevteam.atlassian.net",
    "auth_method": "oauth",
    "oauth": {
      "client_id": "...",
      "client_secret": "...",
      "refresh_token": "",
      "cloud_id": "",
      "redirect_uri": "http://localhost:8723/callback"
    },
    "defaults": { "project_key": "OPS", "issue_type": "Task", "assign_self": true }
  }
}
```

## Step 5 - consent and exchange

Generate the consent URL:

```
python scripts/ticketctl.py jira-auth-url
```

Open the printed URL in a browser, approve access, and choose
`solomondevteam.atlassian.net` if asked which site. You land on a
"can't reach this page" error at `localhost:8723` - look at the address bar:

```
http://localhost:8723/callback?code=eyJhbGciOi...&state=abc123
                                    ^^^^^^^^^^^^^^^ copy this, up to the & 
```

Exchange it straight away - authorization codes are single-use and expire in
minutes:

```
python scripts/ticketctl.py jira-token --code PASTE_CODE_HERE
```

That stores the refresh token and resolves your cloud ID. Then:

```
python scripts/ticketctl.py doctor
```

### Getting the code on a headless Linux server

If there's no browser on the machine, run `jira-auth-url` there, open the URL on
your laptop, and copy the code across - the code isn't tied to the machine that
generated the URL. Nothing has to listen on port 8723 on either side.

---

## How email notifications work in Jira

Jira has no "email an arbitrary address" API. `--email` and `notify` use
`POST /rest/api/3/issue/{key}/notify`, which sends to the reporter, watchers, and
named **Atlassian accounts**.

That means addresses only work if the person has an account on
`solomondevteam.atlassian.net`. The tool looks each address up and warns on
stderr about any it cannot resolve - pass that warning on to the user rather than
letting them assume the mail went out. Resolving addresses also needs the
**Browse users and groups** global permission; without it, lookups fail and only
watchers get notified.

For people outside the site, the reliable options are adding them as a watcher,
or a Jira automation rule that emails an external address on comment.

## Field notes

- **Labels cannot contain spaces.** The tool converts spaces to hyphens, so
  `--labels "after hours"` becomes `after-hours`.
- **`issue_type` and `priority` must exist in that project's scheme.** A project
  configured with `Task`/`Bug`/`Story` rejects `Incident`, and some Jira projects
  have priority disabled entirely - leave `priority` blank if you get a field
  error mentioning it.
- **Required custom fields will block creation.** If your project mandates
  fields the tool doesn't set, create returns a field-level error naming them.
  Options: make the field optional, give it a default in the project config, or
  create through a screen that defaults it.
- **Descriptions and comments use Atlassian Document Format** in API v3. The tool
  converts your plain text and light markdown for you; you never write ADF by
  hand.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| 401 with `api_token` | Token expired, or `jira.email` isn't the token owner. Check the token list page |
| 401 with `oauth` after an hour | Rotated refresh token couldn't be saved. Make the config file writable |
| `invalid_grant` on `jira-token` | Code expired or already used, or `redirect_uri` doesn't match the app exactly |
| No refresh token returned | `offline_access` missing from the authorize URL - use `jira-auth-url` to build it |
| 403 on create | Account lacks **Create issues** in that project |
| `project: ... is required` | `project_key` empty or the key doesn't exist. Check **Project settings → Details** |
| `issuetype: ... is not valid` | That type isn't in the project's issue type scheme |
| Site not in accessible list | You consented for a different site. Re-run consent and pick `solomondevteam` |
| `--email` silently reaches nobody | Addresses have no Atlassian account, or you lack Browse users permission |
