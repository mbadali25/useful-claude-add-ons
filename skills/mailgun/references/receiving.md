# Receiving mail with Mailgun

## How it works
1. The domain's MX records point to Mailgun (`mxa.mailgun.org`, `mxb.mailgun.org`, priority 10).
   Check: `mg.py domain-check` -> "receiving dns records" must all be OK.
2. A **route** matches incoming mail and runs actions. Up to 3 actions per route.
3. Mailgun keeps stored messages for about 3 days. Save anything important before then.

## Route expressions (filters)
| Expression | Matches |
|---|---|
| `match_recipient(".*@mg.example.com")` | anything to the domain |
| `match_recipient("support@mg.example.com")` | one address |
| `match_header("subject", ".*invoice.*")` | header regex |
| `catch_all()` | anything no other route caught |
Combine with `and`. Lower `priority` number runs first.

## Route actions
| Action | Effect |
|---|---|
| `store()` | keep ~3 days, readable with `inbox` / `read` |
| `store(notify="https://x.com/in")` | keep + POST to URL |
| `forward("me@gmail.com")` | forward to an address |
| `forward("https://x.com/in")` | POST parsed message to URL |
| `stop()` | don't evaluate lower-priority routes |

Manage routes: `find routes` -> list/update/delete via `call`. Test which route an address hits:
`call GET /v3/routes/match -q address=someone@mg.example.com`.

Simpler forward-only rules also exist (Forwards API): `find forwards`.

## Stored message fields (from `read --full`)
`From`, `To`, `Subject`, `body-plain`, `stripped-text` (reply without quoted history),
`body-html`, `stripped-html`, `attachments` (list with `url`, `name`, `size`), `message-headers`.
`read --mime` returns the raw RFC 2822 message.

## Spam
Domain setting `spam_action`: disabled / block / tag. With tag, headers `X-Mailgun-Sflag: Yes`
and `X-Mailgun-Sscore` show up. Set with `call PUT /v4/domains/{name} -f spam_action=tag`
(check with `describe` first).

## Verifying webhook/forward POSTs (for the user's own server)
Each POST includes `timestamp`, `token`, `signature`. Valid if
`signature == HMAC_SHA256(key=webhook_signing_key, msg=timestamp+token)` (hex).
Get the signing key in the Mailgun dashboard (Webhooks -> signing key). Reject old timestamps
and reused tokens.
