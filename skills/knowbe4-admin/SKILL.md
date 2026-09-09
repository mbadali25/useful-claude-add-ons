---
name: knowbe4-admin
description: Administer and troubleshoot a KnowBe4 KSAT (Security Awareness Training) account - diagnose SCIM user-sync problems with Microsoft Entra ID or Okta (users not provisioning, mass archiving, duplicate accounts, attribute drift, quarantined provisioning jobs), pull user/group/phishing/training data via the Reporting API, reconcile KnowBe4 against an IdP or HR export to find stale accounts, and route write operations to the correct surface (SCIM, ADI, or the console). Use this skill whenever the user mentions KnowBe4, KSAT, PhishER, phish-prone percentage, or security awareness training users, groups, campaigns or provisioning - even if they do not say "API". Also use it when they ask why a KnowBe4 change keeps reverting, why SCIM sync is not working, or how to automate KnowBe4 user lifecycle.
---

# KnowBe4 Admin

Help a KnowBe4 (KSAT) admin get data out, audit it, and make changes on the **correct surface**.

The single most important thing this skill does: stop the user writing a script against an
API that physically cannot do what they want. KnowBe4 splits reads and writes across
different systems with different credentials.

## Step 1 — Route the task before writing anything

Always classify the request against this table first, and tell the user which row they landed on.

| What they want | Correct surface | Credential | Notes |
|---|---|---|---|
| Export users / groups / risk scores | Reporting API `GET /v1/...` | Reporting API token | Read-only. See `references/reporting-api.md` |
| Phishing results, training enrollments | Reporting API | Reporting API token | Read-only |
| Create / update / archive a user | SCIM 2.0, or ADI sync, or console | SCIM token (separate!) | See `references/writes.md` |
| Bulk write / automate KSAT operations | **Graph API (GraphQL)** — supports mutations | Product API token, Read/Write scope | **Diamond only.** A fourth writer to the same records — see the drift warning in `references/writes.md` |
| **Diagnose why SCIM sync is wrong** | Entra logs + KSAT sync reports + Reporting API | Reporting API token to verify | See `references/scim-entra.md` — start there, it is symptom-indexed |
| Add/remove users from a group | SCIM `PATCH /Groups/{id}`, or console | SCIM token | Reporting API cannot write groups |
| Bulk offboard leavers | Unassign the app in the IdP → SCIM sets `active: false` | IdP | Archives, does not delete |
| Hard-delete a user (GDPR/DSAR) | Console only, manual | — | No API path. Plan for it |
| Smart Groups, campaigns, templates | Console only | — | Not creatable via SCIM |
| Push external security events onto a user | User Event API | User Event API key (a third key) | Different product |
| SecurityCoach / PhishER data | Graph API (GraphQL) / PhishER API | Product API token | Different product |

**If the request is a write and they only have a Reporting API token, say so immediately.**
That is the answer, not a workaround. Do not attempt to emulate writes by scripting the console.

## Step 2 — Check three things before running anything

Ask (or confirm from context) — these cause most of the wasted effort:

1. **Region.** The base URL is regional (`us.api.knowbe4.com`, `eu.api.knowbe4.com`, and other
   regional subdomains). Wrong region returns 401 or an empty array rather than a clear error,
   which reads exactly like "the token is broken". Match it to their console URL.
2. **Subscription tier.** The Reporting API is gated to higher tiers (Platinum/Diamond/
   SAT Foundations/SAT Advanced at time of writing). Silver/Gold admins get 401 forever.
3. **Is the account ADI- or SCIM-managed?** If users carry `adi_manageable: true`, edits made in
   the console get overwritten on the next sync. This is the root cause of most
   "my change keeps reverting" tickets. The fix is upstream in AD/the IdP, never in KnowBe4.

## Step 3 — Do the work

Use `scripts/kb4.py` for anything that reads data. It handles the parts that are tedious to get
right by hand: offset pagination to exhaustion, 429 backoff (KnowBe4 returns no `Retry-After`
header, so backoff must be manual), regional base URLs, and CSV/table/JSON output.

```bash
export KB4_TOKEN='...'            # Reporting API token
export KB4_REGION=us              # or eu, or a full base URL via KB4_BASE_URL

python scripts/kb4.py users --format csv --out users.csv
python scripts/kb4.py users --status active --fields email,status,phish_prone_percentage
python scripts/kb4.py groups
python scripts/kb4.py members 789
python scripts/kb4.py enrollments --format csv --out enrollments.csv
python scripts/kb4.py get /v1/account            # raw path escape hatch

# Diamond only: what can the Graph API actually do? Introspect before planning a bulk write.
export KB4_PRODUCT_TOKEN='...'                   # Product API token, a different credential
python scripts/kb4.py schema --show mutations --grep archive

# The high-value one for legacy cleanup: who is in KnowBe4 but not in the IdP export?
python scripts/kb4.py reconcile --source idp_users.csv --email-column mail

# Moved from ADI to SCIM and the user count is inflated? Check for double records first.
python scripts/kb4.py duplicates

# SCIM sync ran clean but the data is wrong - did the attributes actually land?
python scripts/kb4.py drift --source entra_export.csv \
    --map department=department,jobTitle=job_title
```

Run `python scripts/kb4.py --help` for the full surface. Read `references/reporting-api.md`
before hand-rolling a request the script does not cover.

## Troubleshooting SCIM sync

When the task is "sync is broken", read `references/scim-entra.md` — it is indexed by symptom.
Run these four checks before reading any logs line by line, because they resolve most cases:

1. **Test Mode still on in KSAT?** Sync reports look healthy but nothing is added or archived.
2. **Account still on the ADI toggle?** It defaults to ADI, and ADI overwrites SCIM.
3. **User actually in scope in the IdP?** Assignment plus any scoping filter.
4. **App in quarantine?** Entra stops syncing entirely and needs an explicit restart.

If they migrated from **ADI to SCIM** and the sync is live and wrong, work
`references/adi-to-scim-recovery.md` in order - it is a runbook with verification gates, and
Phase 0 (enable Test Mode) should be stated in the first reply because every 40-minute cycle
compounds the damage. For background on the failure mode, see the migration section of
`references/scim-entra.md`. SCIM matches on `userName` (default `userPrincipalName`) while ADI usually populated from
primary SMTP, so wherever UPN differs from mail the sync creates a second record per person
rather than updating the existing one. Run `duplicates` before investigating scope.

Say early that **Provision on demand is not supported** by the KnowBe4 integration. It is the
reflex diagnostic for Entra admins and it will mislead them. Force a cycle from KSAT
(SCIM Settings → Force Sync Now) instead; the automatic cadence is 40 minutes.

Then use the Reporting API as ground truth. Entra logs say what was *sent*; only the Reporting
API says what KnowBe4 actually *has*, which is how you separate "the IdP never sent it" from
"KnowBe4 rejected it".

## Step 4 — Report back

The user is an infra admin scanning for what to act on, not reading prose. Structure output as:

1. **One-line headline** — the number that matters.
2. **A table** of findings, most actionable first.
3. **Caveats** as a short bullet list, only where they change what to do.

Prefer a table plus a saved CSV over a wall of records. When a result set is large, show the
top 10 rows and point at the full file.

## Judgement calls worth making out loud

Push back rather than complying silently when:

- **They ask to script user creation against the Reporting API.** It cannot write. The real
  answer is SCIM or ADI, which also fixes the drift problem permanently instead of per-run.
- **They want a nightly polling job.** KnowBe4 has no outbound webhooks, so polling is the only
  option — but check whether hourly or daily is genuinely needed before building a poller that
  burns rate limit for no reason.
- **They want to store the token in a script.** The Reporting API token is account-scoped with no
  granular permission model: whoever holds it can read every user's phishing results and risk
  scores. That is a real access-control problem in a shared repo. Push for a secret store or,
  at minimum, an env var and a token expiry date.
- **The task is really an IdP task.** Offboarding, joiner flows, and group membership all belong
  upstream. Solving them inside KnowBe4 creates a second source of truth that will drift.

## Reference files

| File | Read it when |
|---|---|
| `references/adi-to-scim-recovery.md` | A live ADI to SCIM cutover has gone wrong. Ordered runbook |
| `references/scim-entra.md` | Any other SCIM/Entra/Okta sync problem. Symptom-indexed |
| `references/reporting-api.md` | Building any read request; need fields, endpoints, limits |
| `references/writes.md` | Anything that changes data: SCIM, ADI, console-only operations |

Endpoint details change. When something 404s or a field is missing, check
`developer.knowbe4.com` and the KnowBe4 knowledge base rather than assuming the reference
file is current — then tell the user what changed.
