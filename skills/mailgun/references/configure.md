# Configuration cheat sheet

Always `describe "<METHOD> <path>"` before a write call to see field names.

| Task | Endpoint(s) |
|---|---|
| List / add / delete domain | GET/POST /v4/domains, DELETE /v3/domains/{name} (`find domain`) |
| Verify DNS, see records to add | `mg.py domain-check` (PUT /v4/domains/{name}/verify) |
| Open / click / unsubscribe tracking | GET /v3/domains/{name}/tracking, PUT .../tracking/open, /click, /unsubscribe |
| HTTPS tracking certificate | /v2/x509/{domain} |
| Event webhooks (delivered, failed, opened...) | /v3/domains/{domain}/webhooks (types: accepted, delivered, opened, clicked, unsubscribed, complained, permanent_fail, temporary_fail) |
| Account-wide webhooks | `find account webhook` |
| Inbound routes | /v3/routes |
| Simple forwarding | /v3/forwards |
| Templates (domain) | /v3/{domain_name}/templates (+ /versions) |
| Templates (account) | `find account templates` |
| Bounces / unsubscribes / complaints | /v3/{domain_name}/bounces, /unsubscribes, /complaints (+ /import for CSV) |
| Allowlist (never suppress) | /v3/{domain_name}/whitelists |
| Mailing lists + members | /v3/lists, /v3/lists/{list_address}/members |
| SMTP credentials | /v3/domains/{domain_name}/credentials |
| DKIM keys | /v1/dkim/keys, /v4/domains/{authority_name}/keys |
| IPs, pools, warmup | `find ips`, `find pool`, `find warmup` |
| API keys | `find keys` (tag Keys) |
| Subaccounts | /v5/accounts/subaccounts |
| Sending limits | `find limit` |
| Alerts (Slack/email) | `find alerts` |
| Users, IP allowlist for API | `find users`, `find "ip allowlist"` |

## Higher-risk actions (always confirm with the user)
- Removing a bounce/complaint/unsubscribe: re-enables mail to someone who refused it or
  whose address failed. Complaints especially: removing them can break anti-spam law.
- "Clear all" DELETEs on suppressions, templates, credentials.
- Deleting a domain, API key, or route that stores inbound mail.
- Changing DKIM keys (mail fails authentication until DNS matches).
