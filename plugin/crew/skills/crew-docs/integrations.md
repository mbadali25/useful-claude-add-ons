# Integrations reference: what this repo CALLS

`/crew:reference --integrations` writes `docs/reference/integrations.md`. `api.md` lists the routes a
repo exposes; this file lists the calls it makes: a partner API, a payment or shipping provider, a
cloud SDK, another internal service. Enumerate from the code (HTTP clients, SDK constructors, queue
publishers aimed at another system), never from existing docs.

## The format

```
> Generated from <repo>@<short-sha> on <YYYY-MM-DD>. Every entry is anchored to a
> file and line - re-verify the anchor before trusting the entry.

# Integrations

## ShipStation

### POST https://ssapi.shipstation.com/orders/createorder
`src/shipping/client.py:42`

Auth: basic, key from env `SHIPSTATION_API_KEY`, secret from secret name shipstation/prod
Request: order JSON (`src/shipping/models.py:10-30`)
Response: 200 `{ orderId }` | 400 validation | 429 rate limited
Retries: 3 with exponential backoff, 10s timeout (`src/shipping/client.py:18`)
Errors: a 4xx is logged and dropped; a 5xx is retried, then queued for the nightly reconcile
Call sites: `src/jobs/order_sync.py:88`, `src/admin/resend.py:12`
```

- One `##` per external system, one `###` per call: the method and the endpoint as the code builds it.
- Every entry carries one or more backticked `path:line` (or `path:start-end`) anchors, and every
  anchor must name an existing file inside the repo and a line within it.
- `Auth:` is required. It names WHERE the credential comes from (an env var, a secret-manager name, a
  config key), `none`, or `undocumented - needs a human`. Never the value.
- Request, response, retries, timeouts, rate limits and error handling: as far as the code shows
  them. What you could not find is `undocumented - needs a human`, never inferred from a name.
- A backticked `host:port` reads as an anchor and fails the lint as a missing file: write a host
  unquoted or as a URL. An absolute (`/x:1`) or parent-relative (`../x:1`) anchor is refused.
- The Generated header is the first non-blank line. A header-shaped line further down (inside a
  fenced example) is not the header, and the lint and the refresh check both say so.

## Draft, lint, then copy

1. Write the draft to `${TMPDIR:-/tmp}/crew-reference/integrations.md`, never straight into the repo.
2. Send every `Auth:` line and credential source to `crew:security` with the draft before it lands.
3. Run
   `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_reference.py lint --root . --kind integrations <draft>`.
   Exit 0 is clean, 1 lists `<doc>:<line>` problems, 2 is a usage error or an unreadable file.
4. Copy into `docs/reference/integrations.md` only on exit 0.

A secret-shaped string stops the write: an AWS access key id or secret access key, a private-key
block, a GitHub, Slack, Stripe, Google, npm or SendGrid key, an `sk-` key, a Slack webhook URL, a JWT,
a password in a URL (`scheme://user:pass@host`), an `Authorization: Bearer|Basic ...` value, or a
literal assigned to a password, secret, token or API-key name (quoted, or unquoted with a letter and
a digit). The lint names the pattern and the line, never the value - nor the text of an anchor on
that line; do not print the value either. Replace it with where the credential comes from. A
documented example key is refused too: write a placeholder such as `"${API_KEY}"` or `<token>`.

**Known gap.** The check is a list of known shapes. A token format not on it, or a bare
high-entropy string with no credential-named key beside it, passes the lint. It is a backstop, not
a guarantee: `crew:security`'s review of every `Auth:` line is the second line, and the author's
rule stays "write where the credential comes from, never the value".

## No outbound calls

A repo that calls nothing writes no `integrations.md`, and the report says so. An empty file would
read as "checked, none found" to the refresh check and to the next reader.

## Kept current

The Generated header's sha is what `crew_refresh_check.py` judges the doc against: when a path it
cites changes, `/crew:implement` step 6 prints `reference integrations: stale ... refresh with
/crew:reference --integrations`, and `/crew:done` check 4 refuses until it is refreshed. No header or
no citation is `unknown`. `docs/reference/integrations.md` (that one file, not the rest of
`docs/reference/`) is a refresh artifact, so an approved ticket may write it without a Touch entry. `--audit` reports calls with no entry and entries whose anchor no longer
holds.
