# Setting up Zoho ServiceDesk Plus Cloud

Target instance: **https://ithelpdesk.solomoninsight.com** (ServiceDesk Plus
Cloud on a custom domain).

Two things trip people up before they start, so get them straight first:

1. **Authentication is handled by Zoho Accounts, not by ManageEngine.** You
   register the app at `api-console.zoho.com` and exchange tokens against
   `accounts.zoho.com`, even though the API calls themselves go to your
   ServiceDesk Plus domain.
2. **The API path includes your portal name**, in the form
   `https://ithelpdesk.solomoninsight.com/app/<portal>/api/v3/requests`. A custom
   domain does not remove the `/app/<portal>` segment. Getting this wrong is the
   most common cause of a mysterious 404.

---

## Step 1 - find your portal name

Sign in to https://ithelpdesk.solomoninsight.com and look at the address bar
while viewing any request. The URL looks like:

```
https://ithelpdesk.solomoninsight.com/app/PORTALNAME/ui/requests/12345/details
                                           ^^^^^^^^^^
```

That segment is your portal name (often the org short name, e.g. `itdesk` or
`solomoninsight`). Copy it exactly, including case.

## Step 2 - confirm your data centre

The accounts URL must match the data centre your Zoho org lives in. US orgs use
`accounts.zoho.com`. If you sign in at `zoho.eu`, `zoho.in`, `zoho.com.au`, or
`zohocloud.ca`, use the matching accounts host:

| Region | Accounts URL |
| --- | --- |
| United States | `https://accounts.zoho.com` |
| Europe | `https://accounts.zoho.eu` |
| India | `https://accounts.zoho.in` |
| Australia | `https://accounts.zoho.com.au` |
| Canada | `https://accounts.zohocloud.ca` |
| Japan | `https://accounts.zoho.jp` |
| UK | `https://accounts.zoho.uk` |

A data centre mismatch surfaces as `invalid_client` rather than anything helpful,
so it's worth checking rather than assuming. Solomon Insight is US-based, so
`https://accounts.zoho.com` is the expected value.

## Step 3 - register a Self Client

A **Self Client** is the right choice here: it's designed for back-end jobs with
no interactive user, which is exactly what a CLI logging tool is. There's no
redirect URI and no browser consent screen to host.

1. Go to https://api-console.zoho.com (use the regional equivalent if you're not
   on the US data centre) and sign in with an account that has technician rights
   in ServiceDesk Plus.
2. Click **ADD CLIENT** and choose **Self Client**.
3. Confirm in the popup. The console shows a **Client ID** and **Client Secret**
   under the *Client Secret* tab. Copy both.

> The token inherits the permissions of the account that created it. Use a
> service/automation account with technician rights rather than a personal
> account, so the integration doesn't break when someone changes roles or leaves.

## Step 4 - generate a grant code

1. In your Self Client, open the **Generate Code** tab.
2. Enter these scopes, comma separated and no spaces:

   ```
   SDPOnDemand.requests.ALL,SDPOnDemand.setup.READ
   ```

   `requests.ALL` covers creating requests, reading them, and adding notes.
   `setup.READ` lets the tool resolve names like categories and priorities. Add
   `SDPOnDemand.changes.ALL` only if you plan to log change records too - keep
   the scope list as small as the job needs.
3. Set **Time Duration** to 10 minutes. The code is single-use and expires fast;
   you need to complete step 5 within that window.
4. Enter any scope description, click **CREATE**.
5. If prompted, select the **ServiceDesk Plus** app and the portal from step 1,
   then **CREATE** again.
6. Copy the generated code.

## Step 5 - exchange the code for a refresh token

Create the config first if you haven't:

```
python scripts/ticketctl.py init --provider zoho_sdp
```

Edit the file it names and fill in `base_url`, `portal`, and `accounts_url`. Then
exchange the code - this stores the refresh token in the config for you:

```
python scripts/ticketctl.py zoho-token --code PASTE_CODE_HERE \
  --client-id 1000.YOURCLIENTID --client-secret YOURSECRET
```

Windows PowerShell uses a backtick for line continuation, or just put it on one
line:

```powershell
python scripts\ticketctl.py zoho-token --code PASTE_CODE_HERE --client-id 1000.YOURCLIENTID --client-secret YOURSECRET
```

If the exchange fails, the code almost certainly expired - regenerate it in step
4 and move faster. Codes last 3-10 minutes and cannot be reused.

The refresh token itself does not expire, but it is invalidated if you change the
scope list or revoke it in the API console. Zoho also caps refresh tokens at 20
per user, so avoid generating them repeatedly for no reason.

## Step 6 - verify

```
python scripts/ticketctl.py doctor
```

Then a real end-to-end check with a throwaway ticket:

```
python scripts/ticketctl.py create --title "Test - ticketctl integration check" \
  --body "Created by ticketctl during setup. Safe to close." --dry-run
```

Drop `--dry-run` to actually create it, confirm it appears in the web UI, add a
note to it, then close it out.

---

## Configuration reference for this provider

```json
{
  "provider": "zoho_sdp",
  "zoho_sdp": {
    "base_url": "https://ithelpdesk.solomoninsight.com",
    "portal": "PORTALNAME",
    "accounts_url": "https://accounts.zoho.com",
    "client_id": "1000....",
    "client_secret": "....",
    "refresh_token": "1000....",
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
      "technician_email": "you@solomoninsight.com",
      "assign_self": true
    }
  }
}
```

Every value under `defaults` must match a name that already exists in your
ServiceDesk Plus configuration, exactly - the API matches on the display name and
rejects unknown values with a field-level error. Leave a field empty to let
ServiceDesk Plus apply its own default. Good starting point: set
`technician_email` to yourself, `request_type` to `Incident`, and leave the rest
blank until you know which category names your instance uses.

`technician_email` is what makes `--assign-self` and `search --mine` work.

## Notes and email behaviour

Notes are posted to `/requests/{id}/notes`. The flags map like this:

| ticketctl flag | ServiceDesk Plus field | Effect |
| --- | --- | --- |
| *(default)* | `show_to_requester: false` | Internal technician note |
| `--public` | `show_to_requester: true` | Requester can see it in the portal |
| `--notify-technician` | `notify_technician: true` | Emails the assigned technician |
| `--email a@b` | `email_ids_to_notify` on the request | Adds recipients, then posts a visible note |

Because `email_ids_to_notify` is a property of the *request*, addresses added via
`--email` keep receiving updates on that request afterwards. That's usually what
someone wants when they say "email my manager about this", but it's worth
mentioning to the user so it isn't a surprise.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| 404 on every call | `portal` is wrong or missing. Re-check step 1; the path must be `/app/<portal>/api/v3/...` |
| `invalid_client` on token refresh | Wrong `accounts_url` for your data centre, or client id/secret mismatch |
| `invalid_code` on `zoho-token` | The grant code expired or was already used. Generate a fresh one |
| 401 after months of working | Refresh token was revoked, or the scope list changed. Regenerate from step 4 |
| `field: request_type` style errors | A `defaults` value doesn't match a name configured in your instance |
| Note posts but nobody is emailed | Notes only email when `--email` or `--notify-technician` is passed |
| Works for you, 403 for a colleague | Their account lacks technician rights on that request's site or group |
