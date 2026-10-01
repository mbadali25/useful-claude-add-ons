# Mailgun API — full endpoint index

258 operations, generated from Mailgun's official OpenAPI spec (Sept 2026).
Base URL: `https://api.mailgun.net` (US) or `https://api.eu.mailgun.net` (EU). Auth: HTTP Basic, user `api`, password = API key.
For parameters of any operation run: `python3 scripts/mg.py describe "<METHOD> <path>"`.

## Contents
- Messages (6)
- Domains (6)
- Domain Webhooks (8)
- Domain Tracking (7)
- Domain Keys (8)
- Account Webhooks (6)
- DKIM Security (2)
- Delegated DIPPs (1)
- openapi-tower_other (2)
- IPs (16)
- Dynamic IP Pools (15)
- IP Pools (11)
- IP Address Warmup (4)
- Events (1)
- Tags (7)
- openapi-scout_other (3)
- Stats (7)
- Metrics (2)
- Logs (1)
- Tags New (4)
- Send Alerts (6)
- Limits (5)
- Alerts (14)
- Unsubscribe (6)
- Bounces (6)
- Complaints (6)
- Allowlist (6)
- Routes (6)
- Mailing Lists (14)
- Domain Templates (14)
- Account Templates (14)
- Account Management (8)
- Subaccounts (10)
- Custom Message Limit (4)
- Keys (4)
- Credentials (5)
- IP Allowlist (4)
- Bounce Classification (1)
- Forwards (5)
- Users (3)

## Messages

| Method | Path | What it does |
|---|---|---|
| POST | `/v3/{domain_name}/messages` | Send an email |
| POST | `/v3/{domain_name}/messages.mime` | Send an email in MIME format |
| GET | `/v3/domains/{domain_name}/messages/{storage_key}` | Retrieve a stored email |
| POST | `/v3/domains/{domain_name}/messages/{storage_key}` | Resend an email |
| GET | `/v3/domains/{name}/sending_queues` | Get messages queue status |
| DELETE | `/v3/{domain_name}/envelopes` | Delete scheduled and undelivered mail |

## Domains

| Method | Path | What it does |
|---|---|---|
| GET | `/v4/domains` | Get domains |
| POST | `/v4/domains` | Create a domain |
| GET | `/v4/domains/{name}` | Get domain details |
| PUT | `/v4/domains/{name}` | Update domain |
| PUT | `/v4/domains/{name}/verify` | Verify Domain |
| DELETE | `/v3/domains/{name}` | Delete a domain |

## Domain Webhooks

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/domains/{domain}/webhooks` | Get domain webhooks |
| POST | `/v3/domains/{domain}/webhooks` | Create a domain webhook |
| GET | `/v3/domains/{domain_name}/webhooks/{webhook_name}` | Get domain webhooks by type |
| PUT | `/v3/domains/{domain_name}/webhooks/{webhook_name}` | Update domain webhook |
| DELETE | `/v3/domains/{domain_name}/webhooks/{webhook_name}` | Delete domain webhooks by type |
| PUT | `/v4/domains/{domain}/webhooks` | Update domain webhooks (v4) |
| POST | `/v4/domains/{domain}/webhooks` | Create domain webhooks (v4) |
| DELETE | `/v4/domains/{domain}/webhooks` | Delete domain webhooks (v4) |

## Domain Tracking

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/domains/{name}/tracking` | Get tracking settings |
| PUT | `/v3/domains/{name}/tracking/click` | Update click tracking settings |
| PUT | `/v3/domains/{name}/tracking/open` | Update open tracking settings |
| PUT | `/v3/domains/{name}/tracking/unsubscribe` | Update unsubscribe tracking settings |
| GET | `/v2/x509/{domain}/status` | Tracking Certificate: Get certificate and status |
| PUT | `/v2/x509/{domain}` | Tracking Certificate: Regenerate expired certificate |
| POST | `/v2/x509/{domain}` | Tracking Certificate: Generate |

## Domain Keys

| Method | Path | What it does |
|---|---|---|
| GET | `/v1/dkim/keys` | List keys for all domains |
| POST | `/v1/dkim/keys` | Create a domain key |
| DELETE | `/v1/dkim/keys` | Delete a domain key |
| PUT | `/v4/domains/{authority_name}/keys/{selector}/activate` | Activate a domain key |
| GET | `/v4/domains/{authority_name}/keys` | List domain keys |
| PUT | `/v4/domains/{authority_name}/keys/{selector}/deactivate` | Deactivate a domain key |
| PUT | `/v3/domains/{name}/dkim_authority` | Update DKIM authority |
| PUT | `/v3/domains/{name}/dkim_selector` | Update a DKIM selector |

## Account Webhooks

| Method | Path | What it does |
|---|---|---|
| GET | `/v1/webhooks` | List account-level webhooks |
| POST | `/v1/webhooks` | Create an account-level webhook |
| DELETE | `/v1/webhooks` | Delete account-level webhooks |
| GET | `/v1/webhooks/{webhook_id}` | Get account-level webhook by ID |
| PUT | `/v1/webhooks/{webhook_id}` | Update an account-level webhook |
| DELETE | `/v1/webhooks/{webhook_id}` | Delete account-level webhook by ID |

## DKIM Security

| Method | Path | What it does |
|---|---|---|
| PUT | `/v1/dkim_management/domains/{name}/rotation` | Update Automatic Sender Security DKIM key rotation for a domain |
| POST | `/v1/dkim_management/domains/{name}/rotate` | Rotate Automatic Sender Security DKIM key for a domain |

## Delegated DIPPs

| Method | Path | What it does |
|---|---|---|
| GET | `/v5/accounts/subaccounts/ip_pools/all` | List DIPPs delegated to subaccounts |

## openapi-tower_other

| Method | Path | What it does |
|---|---|---|
| PUT | `/v5/accounts/subaccounts/{subaccountId}/ip_pool` | Delegate a DIPP to a subaccount **(deprecated)** |
| DELETE | `/v5/accounts/subaccounts/{subaccountId}/ip_pool` | Revoke a DIPP delegated to a subaccount **(deprecated)** |

## IPs

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/ips/domain/{name}` | Get the dedicated IP pool used for spillover for a domain |
| PATCH | `/v3/ips/domain/{name}` | Set or modify the dediciated IP pool used for spillover for a domain |
| DELETE | `/v3/domains/{name}/ips/{ip}` | Remove an IP from the domain pool, unlink a DIPP or remove the domain pool |
| DELETE | `/v3/domains/{name}/pool/{ip}` | Remove an IP from the domain pool, unlink a DIPP or remove the domain pool |
| GET | `/v3/ips/account/settings` | Get DIPP spillover settings for an account |
| PATCH | `/v3/ips/account/settings` | Set or Modify the dedicated IP pool used for IP spillover |
| GET | `/v3/ips` | List account IPs |
| GET | `/v3/ips/{ip}` | Get details about account IP |
| GET | `/v3/ips/{ip}/domains` | Get all domains of an account where a specific IP is assigned |
| POST | `/v3/ips/{ip}/domains` | Assign an IP to all account domains |
| DELETE | `/v3/ips/{ip}/domains` | Remove an IP from all account domains |
| POST | `/v3/ips/{addr}/ip_band` | Place account IP into a dedicated IP band |
| GET | `/v3/ips/request/new` | Return the number of IPs available to the account per its billing plan |
| POST | `/v3/ips/request/new` | Add a new dedicated IP to the account |
| GET | `/v3/ips/details/all` | List account IPs - detailed view |
| PATCH | `/v3/ips/subaccounts` | Update subaccount IP assignments |

## Dynamic IP Pools

| Method | Path | What it does |
|---|---|---|
| POST | `/v3/domains/{name}/dynamic_pools` | Enroll domain |
| DELETE | `/v3/domains/{name}/dynamic_pools` | Remove domain from dynamic IP pools |
| GET | `/v3/domains/dynamic_pools/assignable` | List assignable domains |
| POST | `/v3/domains/all/dynamic_pools/enroll` | Enroll all account domains |
| GET | `/v3/dynamic_pools` | List all Dynamic IP pools |
| POST | `/v3/dynamic_pools/all` | Initialize/set IPs for all pools |
| DELETE | `/v3/dynamic_pools/all` | Remove all dynamic IP pools |
| POST | `/v3/dynamic_pools/{pool_name}/{ip}` | Add IP to Dynamic IP Pool |
| PATCH | `/v3/dynamic_pools/{pool_name}` | Update pool IPs |
| GET | `/v1/dynamic_pools/domains` | List all domains assigned to dynamic IP pools |
| GET | `/v1/dynamic_pools/domains/{name}/preview` | Preview domain assignment |
| GET | `/v1/dynamic_pools/domains/{name}/history` | List domain history |
| PUT | `/v1/dynamic_pools/domains/{name}/override` | Override domain assignment |
| DELETE | `/v1/dynamic_pools/domains/{name}/override` | Remove override |
| GET | `/v1/dynamic_pools/history` | List account history |

## IP Pools

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/ip_pools` | List dedicated IP pools of the account |
| POST | `/v3/ip_pools` | Add a new DIPP to the account |
| GET | `/v3/ip_pools/{pool_id}` | Get DIPP details |
| DELETE | `/v3/ip_pools/{pool_id}` | Delete the DIPP |
| PATCH | `/v3/ip_pools/{pool_id}` | Edit DIPP |
| GET | `/v3/ip_pools/{pool_id}/domains` | Get domains linked to DIPP |
| PUT | `/v3/ip_pools/{pool_id}/ips/{ip}` | Add an IP to a DIPP |
| DELETE | `/v3/ip_pools/{pool_id}/ips/{ip}` | Remove an IP from a DIPP |
| POST | `/v3/ip_pools/{pool_id}/ips.json` | Add multiple IPs to the DIPP |
| PUT | `/v3/ip_pools/{pool_id}/delegate` | Delegate DIPP to Subaccount |
| DELETE | `/v3/ip_pools/{pool_id}/delegate` | Revoke DIPP from Subaccount |

## IP Address Warmup

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/ip_warmups` | Retrieves the list of in-flight IP address warmup statuses. |
| GET | `/v3/ip_warmups/{addr}` | Retrieves the status of an in-flight IP warmup |
| POST | `/v3/ip_warmups/{addr}` | Creates a warmup plan for an IP Address |
| DELETE | `/v3/ip_warmups/{addr}` | Cancels the warmup plan for an IP address |

## Events

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/{domain_name}/events` | Retrieves a paginated list of events |

## Tags

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/{domain}/tags` | List all tags **(deprecated)** |
| GET | `/v3/{domain}/tag` | Get a tag **(deprecated)** |
| PUT | `/v3/{domain}/tag` | Update tag  **(deprecated)** |
| DELETE | `/v3/{domain}/tag` | Delete tag **(deprecated)** |
| GET | `/v3/{domain}/tag/stats/aggregates` | Get aggregate stat types by tag **(deprecated)** |
| GET | `/v3/{domain}/tag/stats` | Get stats by tag **(deprecated)** |
| GET | `/v3/domains/{domain}/limits/tag` | Get tag limits **(deprecated)** |

## openapi-scout_other

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/domains/{domain}/tag/devices` | List of supported devices **(deprecated)** |
| GET | `/v3/domains/{domain}/tag/providers` | List of supported providers **(deprecated)** |
| GET | `/v3/domains/{domain}/tag/countries` | List of supported country codes **(deprecated)** |

## Stats

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/stats/total` | Totals for entire account **(deprecated)** |
| GET | `/v3/{domain}/stats/total` | Totals for entire domain **(deprecated)** |
| GET | `/v3/stats/total/domains` | Totals for account domains for a single time resolution **(deprecated)** |
| GET | `/v3/stats/filter` | Filtered/grouped totals for entire account **(deprecated)** |
| GET | `/v3/{domain}/aggregates/providers` | Aggregate counts by ESP **(deprecated)** |
| GET | `/v3/{domain}/aggregates/devices` | Aggregate counts by devices triggering events  **(deprecated)** |
| GET | `/v3/{domain}/aggregates/countries` | Aggregate counts by country **(deprecated)** |

## Metrics

| Method | Path | What it does |
|---|---|---|
| POST | `/v1/analytics/metrics` | Query account metrics |
| POST | `/v1/analytics/usage/metrics` | Query account usage metrics |

## Logs

| Method | Path | What it does |
|---|---|---|
| POST | `/v1/analytics/logs` | List logs |

## Tags New

| Method | Path | What it does |
|---|---|---|
| PUT | `/v1/analytics/tags` | Update account tag |
| POST | `/v1/analytics/tags` | Post query to list account tags or search for single tag |
| DELETE | `/v1/analytics/tags` | Delete account tag |
| GET | `/v1/analytics/tags/limits` | Get account tag limit information |

## Send Alerts

| Method | Path | What it does |
|---|---|---|
| GET | `/v1/thresholds/alerts/send` | List send alerts |
| POST | `/v1/thresholds/alerts/send` | Create a send alert for an account |
| GET | `/v1/thresholds/alerts/send/{name}` | Get a send alert |
| PUT | `/v1/thresholds/alerts/send/{name}` | Update a send alert |
| DELETE | `/v1/thresholds/alerts/send/{name}` | Delete a send alert |
| GET | `/v1/thresholds/hits` | List account hits |

## Limits

| Method | Path | What it does |
|---|---|---|
| GET | `/v1/thresholds/limits` | List limit thresholds for an account |
| POST | `/v1/thresholds/limits` | Create a limit threshold for an account |
| GET | `/v1/thresholds/limits/{name}` | Get a limit threshold for an account |
| PUT | `/v1/thresholds/limits/{name}` | Update a limit threshold for an account |
| DELETE | `/v1/thresholds/limits/{name}` | Delete a limit threshold for an account |

## Alerts

| Method | Path | What it does |
|---|---|---|
| GET | `/v1/alerts/events` | List events |
| POST | `/v1/alerts/settings/events` | Add Alert |
| PUT | `/v1/alerts/settings/events/{id}` | Update Alert |
| DELETE | `/v1/alerts/settings/events/{id}` | Remove Alert |
| GET | `/v1/alerts/settings` | List Alerts |
| PUT | `/v1/alerts/settings/slack` | Update Slack settings |
| DELETE | `/v1/alerts/settings/slack` | Delete Slack settings |
| PUT | `/v1/alerts/settings/webhooks/signing_key` | Reset Webhook Signing Key |
| POST | `/v1/alerts/webhooks/test` | Test webhook |
| POST | `/v1/alerts/email/test` | Test message |
| POST | `/v1/alerts/slack/test` | Test message |
| DELETE | `/v1/alerts/slack/oauth` | Revoke Slack access token |
| GET | `/v1/alerts/slack/channels/{id}` | Get Slack channel |
| GET | `/v1/alerts/slack/channels` | List Slack channels |

## Unsubscribe

| Method | Path | What it does |
|---|---|---|
| POST | `/v3/{domain_name}/unsubscribes/import` | Import unsubscribe list |
| GET | `/v3/{domain_name}/unsubscribes/{address}` | Lookup unsubscribe record |
| DELETE | `/v3/{domain_name}/unsubscribes/{address}` | Remove unsubscribe |
| GET | `/v3/{domain_name}/unsubscribes` | List all unsubscribes |
| POST | `/v3/{domain_name}/unsubscribes` | Add unsubscribes |
| DELETE | `/v3/{domain_name}/unsubscribes` | Clear all unsubscribes |

## Bounces

| Method | Path | What it does |
|---|---|---|
| POST | `/v3/{domain_name}/bounces/import` | Import list of bounces |
| GET | `/v3/{domain_name}/bounces/{address}` | Lookup bounce record |
| DELETE | `/v3/{domain_name}/bounces/{address}` | Remove bounce |
| GET | `/v3/{domain_name}/bounces` | List all bounces |
| POST | `/v3/{domain_name}/bounces` | Add bounces |
| DELETE | `/v3/{domain_name}/bounces` | Clear all bounces |

## Complaints

| Method | Path | What it does |
|---|---|---|
| POST | `/v3/{domain_name}/complaints/import` | Import complaint list |
| GET | `/v3/{domain_name}/complaints/{address}` | Lookup complaint record |
| DELETE | `/v3/{domain_name}/complaints/{address}` | Remove complaint |
| GET | `/v3/{domain_name}/complaints` | List all complaints |
| POST | `/v3/{domain_name}/complaints` | Add complaints |
| DELETE | `/v3/{domain_name}/complaints` | Clear all complaints |

## Allowlist

| Method | Path | What it does |
|---|---|---|
| POST | `/v3/{domain_name}/whitelists/import` | Import allowlist |
| GET | `/v3/{domain_name}/whitelists/{value}` | Lookup allowlist record |
| DELETE | `/v3/{domain_name}/whitelists/{value}` | Remove entry from allowlist |
| GET | `/v3/{domain_name}/whitelists` | List allowlist records for domain |
| POST | `/v3/{domain_name}/whitelists` | Add allowlist record |
| DELETE | `/v3/{domain_name}/whitelists` | Clear allowlist |

## Routes

| Method | Path | What it does |
|---|---|---|
| POST | `/v3/routes` | Create a route |
| GET | `/v3/routes` | Get all routes |
| GET | `/v3/routes/{id}` | Get a route |
| PUT | `/v3/routes/{id}` | Update a route |
| DELETE | `/v3/routes/{id}` | Delete a route |
| GET | `/v3/routes/match` | Match address to route |

## Mailing Lists

| Method | Path | What it does |
|---|---|---|
| POST | `/v3/lists` | Create a mailing list |
| GET | `/v3/lists` | Get mailing lists |
| GET | `/v3/lists/{list_address}/members` | Get mailing lists members |
| POST | `/v3/lists/{list_address}/members` | Create a mailing list member |
| POST | `/v3/lists/{list_address}/members.json` | Bulk upload members to a mailing list (JSON) |
| POST | `/v3/lists/{list_address}/members.csv` | Bulk upload members to a mailing list (CSV) |
| GET | `/v3/lists/{list_address}/members/{member_address}` | Get a member |
| PUT | `/v3/lists/{list_address}/members/{member_address}` | Update a mailing list member |
| DELETE | `/v3/lists/{list_address}/members/{member_address}` | Delete a member |
| PUT | `/v3/lists/{list_address}` | Update a mailing list |
| DELETE | `/v3/lists/{list_address}` | Delete a mailing list |
| GET | `/v3/lists/{list_address}` | Get a mailing list by address |
| GET | `/v3/lists/pages` | Get mailing lists by page |
| GET | `/v3/lists/{list_address}/members/pages` | Get members by page |

## Domain Templates

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/{domain_name}/templates` | Get templates |
| POST | `/v3/{domain_name}/templates` | Create a template |
| DELETE | `/v3/{domain_name}/templates` | Delete all templates |
| GET | `/v3/{domain_name}/templates/{template_name}/versions` | Get all template versions |
| POST | `/v3/{domain_name}/templates/{template_name}/versions` | Create a template version |
| GET | `/v3/{domain_name}/templates/{template_name}` | Get template |
| PUT | `/v3/{domain_name}/templates/{template_name}` | Update template |
| DELETE | `/v3/{domain_name}/templates/{template_name}` | Delete a template |
| GET | `/v3/{domain_name}/templates/{template_name}/versions/{version_name}` | Get a version |
| PUT | `/v3/{domain_name}/templates/{template_name}/versions/{version_name}` | Update a version |
| DELETE | `/v3/{domain_name}/templates/{template_name}/versions/{version_name}` | Delete a version |
| PUT | `/v3/{domain_name}/templates/{template_name}/copy` | Copy a template |
| PUT | `/v3/{domain_name}/templates/{template_name}/versions/{version_name}/copy/{new_version_name}` | Copy a version |
| PUT | `/v3/{domain_name}/templates/{template_name}/rename/{new_template_name}` | Rename a template |

## Account Templates

| Method | Path | What it does |
|---|---|---|
| GET | `/v4/templates` | Get account-level templates |
| POST | `/v4/templates` | Create an account-level template |
| DELETE | `/v4/templates` | Delete all account-level templates |
| GET | `/v4/templates/{template_name}/versions` | Get all account-level template versions |
| POST | `/v4/templates/{template_name}/versions` | Create an account-level template version |
| GET | `/v4/templates/{template_name}` | Get an account-level template |
| PUT | `/v4/templates/{template_name}` | Update an account-level template |
| DELETE | `/v4/templates/{template_name}` | Delete an account-level template |
| GET | `/v4/templates/{template_name}/versions/{version_name}` | Get an account-level template version |
| PUT | `/v4/templates/{template_name}/versions/{version_name}` | Update an account-level template version |
| DELETE | `/v4/templates/{template_name}/versions/{version_name}` | Delete an account-level template version |
| PUT | `/v4/templates/{template_name}/copy` | Copy a template |
| PUT | `/v4/templates/{template_name}/versions/{version_name}/copy/{new_version_name}` | Copy an account-level template version |
| PUT | `/v4/templates/{template_name}/rename/{new_template_name}` | Rename a template |

## Account Management

| Method | Path | What it does |
|---|---|---|
| PUT | `/v5/accounts` | Update variable account settings |
| GET | `/v5/accounts/http_signing_key` | Get webhook signing key saved on the account |
| POST | `/v5/accounts/http_signing_key` | Create or regenerate webhook signing key on an account |
| GET | `/v5/sandbox/auth_recipients` | Get authorized email recipients for a sandbox domain |
| POST | `/v5/sandbox/auth_recipients` | Add authorized email recipient for a sandbox domain |
| DELETE | `/v5/sandbox/auth_recipients/{email}` | Remove an authorized sandbox domain email recipient |
| POST | `/v5/accounts/resend_activation_email` | Resend account activation email to the account owner |
| PUT | `/v5/accounts/features` | Update account feature |

## Subaccounts

| Method | Path | What it does |
|---|---|---|
| GET | `/v5/accounts/subaccounts/{subaccount_id}` | Get a single subaccount |
| GET | `/v5/accounts/subaccounts` | List all subaccounts |
| POST | `/v5/accounts/subaccounts` | Create a subaccount |
| DELETE | `/v5/accounts/subaccounts` | Delete a subaccount |
| POST | `/v5/accounts/subaccounts/{subaccount_id}/disable` | Disable a subaccount |
| POST | `/v5/accounts/subaccounts/{subaccount_id}/enable` | Enable a subaccount |
| GET | `/v5/accounts/subaccounts/{subaccount_id}/limit/custom/monthly` | Get current custom sending limit |
| PUT | `/v5/accounts/subaccounts/{subaccount_id}/limit/custom/monthly` | Set a custom sending limit |
| DELETE | `/v5/accounts/subaccounts/{subaccount_id}/limit/custom/monthly` | Delete a custom sending limit |
| PUT | `/v5/accounts/subaccounts/{subaccount_id}/features` | Update subaccount feature |

## Custom Message Limit

| Method | Path | What it does |
|---|---|---|
| GET | `/v5/accounts/limit/custom/monthly` | Get current custom sending limit |
| PUT | `/v5/accounts/limit/custom/monthly` | Set a custom sending limit |
| DELETE | `/v5/accounts/limit/custom/monthly` | Delete a custom sending limit |
| PUT | `/v5/accounts/limit/custom/enable` | Re-enable account disabled for hitting send limit |

## Keys

| Method | Path | What it does |
|---|---|---|
| GET | `/v1/keys` | List Mailgun API keys |
| POST | `/v1/keys` | Create Mailgun API key |
| DELETE | `/v1/keys/{key_id}` | Delete Mailgun API key |
| POST | `/v1/keys/public` | Regenerate Mailgun Public API key |

## Credentials

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/domains/{domain_name}/credentials` | List Mailgun SMTP credential metadata for a given domain |
| POST | `/v3/domains/{domain_name}/credentials` | Create Mailgun SMTP credentials for a given domain |
| DELETE | `/v3/domains/{domain_name}/credentials` | Delete all Mailgun SMTP credentials for a domain |
| PUT | `/v3/domains/{domain_name}/credentials/{spec}` | Update Mailgun SMTP credentials |
| DELETE | `/v3/domains/{domain_name}/credentials/{spec}` | Delete Mailgun SMTP credentials |

## IP Allowlist

| Method | Path | What it does |
|---|---|---|
| GET | `/v2/ip_whitelist` | List Mailgun account IP allowlist entries |
| PUT | `/v2/ip_whitelist` | Update individual Mailgun account IP allowlist entry's description |
| POST | `/v2/ip_whitelist` | Add Mailgun account IP allowlist entry |
| DELETE | `/v2/ip_whitelist` | Delete Mailgun account IP allowlist entry |

## Bounce Classification

| Method | Path | What it does |
|---|---|---|
| POST | `/v2/bounce-classification/metrics` | List statistic v2 |

## Forwards

| Method | Path | What it does |
|---|---|---|
| GET | `/v3/forwards/{id}` | Get a single forward rule by ID |
| PUT | `/v3/forwards/{id}` | Update a single forward rule by ID |
| DELETE | `/v3/forwards/{id}` | Delete a single forward rule by ID |
| GET | `/v3/forwards` | List forward rules |
| POST | `/v3/forwards` | Create a forward rule |

## Users

| Method | Path | What it does |
|---|---|---|
| GET | `/v5/users` | Get users on an account |
| GET | `/v5/users/{user_id}` | Get a user's details |
| GET | `/v5/users/me` | Get one's own user details |
