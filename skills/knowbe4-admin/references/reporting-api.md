# KnowBe4 Reporting API (read-only)

Contents: [Auth](#auth) · [Endpoints](#endpoints) · [User object](#user-object) ·
[Pagination](#pagination) · [Rate limits](#rate-limits) · [Failure modes](#failure-modes)

Verify anything surprising against `developer.knowbe4.com`. Details below reflect the API as
documented at time of writing.

## Auth

| Item | Value |
|---|---|
| Base URL | Regional - see the table below |
| Header | `Authorization: Bearer <token>` |
| Token created at | KSAT console → Account Settings → Account Integrations → API → Reporting API |
| Scope | Account-wide read. **No granular permissions** — any holder reads all user data |
| Tier gate | Platinum, Diamond, SAT Foundations, SAT Advanced |
| Shares a key with User Event API? | **No.** Separate keys per API |

Set an expiry date on the token when creating it. Unused long-lived tokens are the most common
finding in a KnowBe4 access review.

### Regional base URLs

Match the console URL the admin logs into. A mismatch returns 401 or an empty array, which reads
exactly like a bad token.

| Console URL | API base URL | `KB4_REGION` |
|---|---|---|
| `training.knowbe4.com` | `https://us.api.knowbe4.com` | `us` |
| `eu.knowbe4.com` | `https://eu.api.knowbe4.com` | `eu` |
| `ca.knowbe4.com` | `https://ca.api.knowbe4.com` | `ca` |
| `uk.knowbe4.com` | `https://uk.api.knowbe4.com` | `uk` |
| `de.knowbe4.com` | `https://de.api.knowbe4.com` | `de` |

Note the US console is `training.knowbe4.com`, not `us.knowbe4.com` - the console and API
hostnames do not follow the same pattern.

Some accounts also require **Enable API Access** to be ticked in Account Settings before any
token works.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /v1/account` | Account metadata, subscription level, seat counts |
| `GET /v1/account/risk_score_history` | Account-level risk score over time |
| `GET /v1/users` | All users. Supports `?status=active` / `archived` |
| `GET /v1/users/{id}` | Single user incl. per-user risk score |
| `GET /v1/groups` | Console groups and smart groups |
| `GET /v1/groups/{id}/members` | Members of a group |
| `GET /v1/phishing/campaigns` | Phishing campaign definitions + rollup stats |
| `GET /v1/phishing/security_tests` | Individual phishing tests (PSTs) |
| `GET /v1/phishing/security_tests/{pst_id}/recipients` | Per-user results: clicked, replied, reported, attachment opened |
| `GET /v1/training/campaigns` | Training campaigns |
| `GET /v1/training/enrollments` | Per-user enrollment + completion status |

Per-user phishing detail lives under `security_tests/{pst_id}/recipients`, not under the
campaign. Getting "who clicked" means listing security tests first, then recipients per test.

## User object

| Field | Notes |
|---|---|
| `id` | Internal KnowBe4 integer ID. Immutable. Use for per-user calls |
| `email` | Login identity. Unique per account. Best cross-system join key |
| `employee_number` | Second-best join key if email churns (name changes, domain migrations) |
| `first_name`, `last_name` | |
| `status` | `active` or `archived` |
| `phish_prone_percentage` | Computed. Cannot be set |
| `current_risk_score` | Computed. Cannot be set |
| `adi_manageable` | **Read this before advising any edit.** True = AD Integration owns this record and will overwrite console changes |
| `groups` | Array of group IDs |
| `department`, `division`, `location`, `organization`, `job_title`, `manager_name`, `manager_email` | Directory attributes, populated by whatever syncs the user |
| `phone_number`, `extension`, `mobile_phone_number` | |

For cross-system reconciliation, join on `email` (lowercased, trimmed) and fall back to
`employee_number`. Never join on display name.

## Pagination

Offset-based only. No cursors.

- Params: `?page=1&per_page=500`
- `per_page` maximum is **500** — asking for more does not error, it silently caps
- There is no total count and no `next` link. Detect the end by an **empty array response**
- A page returning fewer than `per_page` records is also the end, but check for the empty
  array rather than relying on it

## Rate limits

| Item | Value |
|---|---|
| Limit | ~1,000 requests/minute per API key |
| Exceeded | HTTP 429 |
| `Retry-After` header | **Not sent** — implement exponential backoff manually |
| Informational headers | `X-RateLimit-Limit`, `X-RateLimit-Remaining` |

Watch the remaining-count header on long enrollment pulls rather than waiting to be throttled.

## Failure modes

| Symptom | Most likely cause |
|---|---|
| 401 with a token you just made | Wrong regional base URL, or subscription tier below Platinum |
| Empty array, no error | Wrong region, or a `status` filter that matches nothing |
| Works then 429s mid-pull | No backoff on a large enrollment or recipients pull |
| Field missing vs. docs | Never populated for this account — the field exists but nothing syncs into it |
| Group member count ≠ member list length | Smart group evaluated at read time; expected |

## User Event API (a separate surface)

Distinct product, distinct key. It pushes **events onto existing users** — it is not a user
management API and does not provision identities.

| Item | Value |
|---|---|
| Purpose | Import security-related events or training activity from external sources into KSAT |
| Key | Account Settings → Account Integrations → **User Event API**. Does **not** share a key with the Reporting API |
| Tier gate | Platinum, Diamond, or SAT Advanced for the management console |
| Docs | `developer.knowbe4.com/rest/userEvents` (JavaScript app — not fetchable, direct the user there) |
| Main use | Driving Smart Groups from external telemetry, so training and simulation targeting adapts to real threat data |

The management console has three tabs: **Call History**, Stats, and API Key.

**Call History is an underused diagnostic.** It shows what has actually been posting events and
when. If an account contains users nobody can account for, or risk scores are moving without an
obvious cause, check it before assuming provisioning is responsible.

### Interaction with duplicate user records

Events attach to users by identifier. Where an account has duplicate records for the same person
— the classic ADI-to-SCIM matching failure — inbound events land on whichever record matches,
so Smart Group membership and risk scoring split across the duplicates too. After merging
duplicates, re-check the identifier every external integration posts against, or events will
keep arriving for a record that no longer exists.

## No webhooks

KnowBe4 does not offer outbound webhooks from KSAT. Event-driven integrations must poll
(`/v1/training/enrollments`, `/v1/phishing/campaigns`). Before building a poller, ask what
latency is genuinely required — a daily pull usually satisfies the actual requirement and
costs a fraction of the rate limit.
