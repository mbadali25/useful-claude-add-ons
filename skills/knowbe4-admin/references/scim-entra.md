# Troubleshooting SCIM sync: Microsoft Entra ID → KnowBe4

Contents: [Start here](#start-here-order-matters) · [Symptom index](#symptom-index) ·
[Default mappings](#default-attribute-mappings) · [Known limitations](#known-limitations) ·
[Verifying with the Reporting API](#verifying-with-the-reporting-api)

Entra is the SCIM client, KnowBe4 is the service provider. Sync is one-way. There are
**two independent log surfaces** and most people only look at one:

| Log | Where | Shows |
|---|---|---|
| Entra provisioning logs | Entra admin center → the enterprise app → Provisioning logs | Whether Entra decided to send anything, per-user skip reasons, HTTP errors from KnowBe4 |
| KSAT sync reports | KSAT console → Account Settings → **User Provisioning** tab | What KnowBe4 actually did with what it received, plus its own errors |

A user "missing" in KnowBe4 is almost always **skipped by Entra scoping** rather than rejected
by KnowBe4. Check the Entra log first; it will say `Skipped` with a reason.

## Start here (order matters)

Four checks resolve the large majority of cases. Do them before reading logs line by line.

| # | Check | Why it comes first |
|---|---|---|
| 1 | **Is Test Mode still on in KSAT?** Account Settings → User Management → User Provisioning | In Test Mode the sync runs and reports look healthy, but users are **not** added or archived. This is the single most common "sync runs but nothing happens" cause |
| 2 | **Is the account still on the ADI toggle?** Same page — toggle defaults to ADI, not SCIM | If ADI is enabled, ADI is authoritative and will overwrite SCIM-set fields on its own schedule |
| 3 | **Is the user actually in scope in Entra?** Enterprise app → Users and groups, plus any scoping filter | Assignment is required unless scope is set to "Sync all users and groups" |
| 4 | **Is the app in quarantine?** Entra → Provisioning → status banner | After repeated failures Entra quarantines the job and stops syncing entirely. It needs an explicit **Restart provisioning**, not just a save |

## Symptom index

### "Sync says success but nothing changes in KnowBe4"
Test Mode is on (check 1 above). Turn it off in KSAT, then force a sync.

### "I clicked Provision on demand and it fails / does nothing"
**On-demand provisioning is not supported by the KnowBe4 integration.** Do not use it as a
diagnostic — a failure there tells you nothing about the real sync. This breaks the normal Entra
troubleshooting habit, so state it before the user burns time on it.

Instead, force a cycle from the KnowBe4 side: KSAT Account Settings → SCIM Settings →
**Force Sync Now**. Otherwise Entra checks for changes every **40 minutes** on its own.

### "A specific user never appears"
Work through in this order:

| Cause | How to confirm |
|---|---|
| Not assigned to the enterprise app | Entra → app → Users and groups |
| Filtered out by a scoping filter | Entra → Provisioning → scoping filters |
| In a **nested** group | Nested groups are not supported. Only direct members of the assigned group sync |
| `userPrincipalName` is null or malformed | Entra provisioning log shows the skip reason |
| Uses an **email alias** | Aliases are not supported by SCIM provisioning. The alias is dropped |

### "We assigned one group of N users but far more than N synced"

Split this before diagnosing — the two causes need opposite fixes:

| Fork | Test | Meaning |
|---|---|---|
| **A. Extras are pre-existing records** | KSAT sync report shows them as untouched, not "added". Their created date predates the SCIM cutover | Not an over-sync. Leftovers from ADI/CSV import awaiting archive |
| **B. Extras were created by the sync** | Entra provisioning log shows `Create` for them | Genuine scope problem — Entra is sending more than the assigned group |

Fork A is common right after an ADI → SCIM cutover. Out-of-scope users are archived rather than
deleted, and on large accounts that archival is staged across several cycles, so the console
total stays inflated for a while. Confirm the count is trending down across cycles before
treating it as a fault.

For fork B, in order of likelihood:

| Cause | Check |
|---|---|
| **Scope set to "Sync all users and groups"** | Entra → Provisioning → Settings → Scope. This ignores assignment entirely and sends the whole directory. It is also what KnowBe4's own FAQ tells you to set if you want everyone, so it gets enabled by accident |
| **Other principals still assigned to the app** | Entra → the app → Users and groups. Provisioning scope is *every* assigned principal, not just the group most recently added |
| **The SSO app was reused for provisioning** | If SSO already had users or an "all staff" group assigned, enabling provisioning on that same app inherits those assignments. KnowBe4 recommends a separate app while testing for this reason |
| **A second provisioning app is still running** | An older enterprise app pointed at the same SCIM tenant URL keeps syncing independently |
| **The group is dynamic and its rule is broader than expected** | Check membership type and the live member count in Entra, not the count from another tool |

Identify the extras rather than guessing — export the assigned group's members and diff:

```bash
python scripts/kb4.py reconcile --source assigned_group_members.csv \
    --email-column userPrincipalName --format csv --out extras.csv
```

Then look at what the extras have in common (department, licence, another group). The shared
attribute names the real scope that is in effect.

## Migrating from ADI to SCIM

This cutover produces its own distinct failure, separate from ordinary scope problems. Check it
before anything else when the user says they moved from ADI.

**The core risk is identity matching.** SCIM matches existing users on `userName`, whose default
source is `userPrincipalName`. ADI populated records from on-prem AD, commonly using primary
SMTP. Wherever UPN ≠ mail — a legacy `.local` domain, a `.onmicrosoft.com` fallback, a merged
tenant, any UPN suffix change — SCIM cannot match the ADI record and **creates a second account
for the same person** instead of updating the first.

The symptom is an account population close to *double* the in-scope group, with two records per
person on different email domains.

```bash
python scripts/kb4.py duplicates
```

Reports merged clusters (matching on employee number, email local part, and name), flags when
the pairs span multiple email domains, and flags when a cluster pairs an `adi_manageable` record
with a non-ADI one — old ADI record plus new SCIM record for the same human.

Treat name-only matches as candidates, not conclusions; two real people can share a name.
Clusters that also match on employee number are near-certain.

### What to fix, and in what order

| Step | Action | Why this order |
|---|---|---|
| 1 | Turn **Test Mode back on** in KSAT | Stops further creation and archival while diagnosing. Cheap and reversible |
| 2 | Align the SCIM `userName` **source attribute** with the address ADI used | Fixing this first means subsequent syncs match rather than duplicate |
| 3 | Align the **SAML SSO** source attribute to the same value | Otherwise users log in and land on whichever record SSO resolves to |
| 4 | Deal with the duplicate records in the console | See the data-loss note below before choosing |
| 5 | Re-enable Test Mode off, one cycle, verify counts | Confirm before opening the scope wider |

### Data loss to warn about explicitly

- **Phishing and training history stays on the old record.** A user with a fresh duplicate has a
  reset phish-prone percentage and no completion history. Merging in the console, not deleting
  the old record, is what preserves the reporting. Point this out before anyone bulk-deletes.
- **Email aliases are removed.** KnowBe4 documents that alias addresses are not supported by SCIM
  and the alias information is dropped once Test Mode is disabled and a sync runs. If ADI relied
  on aliases, those users need a different primary address decided before the next sync.
- **Unmapped fields get blanked.** SCIM overwrites existing KnowBe4 values. Anything ADI
  populated that is not mapped in the provisioning config — Division and Organization are
  unmapped by default — is cleared.
- **Out-of-scope users are archived**, and on large accounts that archival is staged across
  several cycles, so totals stay inflated for a while before settling.

### Distinguishing duplicates from leftovers

Both inflate the total, and they need opposite fixes.

| | Duplicates | Un-archived leftovers |
|---|---|---|
| Detect with | `duplicates` | `reconcile --source in_scope_group.csv` |
| Pattern | Two records per person, different domains | One record per person, extras not in the IdP scope |
| Fix | Correct the matching attribute, then merge | Wait for archival cycles, or widen scope if the exclusion was unintended |

### "Users got mass-archived after we enabled SCIM"
Expected behaviour, and the reason Test Mode exists: **any user not included in the sync scope is
automatically archived.** Enabling SCIM with a narrow scope archives everyone outside it.

For large tenants the initial sync is staged across several cycles, so an early cycle looks like
a huge deletion. Keep Test Mode on until consecutive sync reports show only a few changes, then
turn it off. Archived users retain their history and can be restored, so this is recoverable —
say so, then fix the scope.

### "Duplicate users, or SSO logins land on a second account"
The SCIM `userName` source attribute and the SAML SSO source attribute must be **the same
attribute**. Both default to `user.userprincipalname`. If SSO was changed to `user.mail` (common
where UPN ≠ primary SMTP) and SCIM was left on UPN, SSO creates or matches a different record.
Align them, then merge in the console.

### "Sync works but fields are wrong or empty"
| Field | Cause |
|---|---|
| Manager Email blank | The manager must also be in the sync scope, or the reference cannot resolve |
| Manager Name odd | `displayName` maps to **Manager Name**, sourced from the manager's Entra profile — it deliberately does not show on the user's own KSAT profile |
| Division / Organization blank | **Unmapped by default.** Must be added manually |
| Custom field blank | The target attribute URN is case-sensitive. `customField1`, not `customfield1` |
| Time Zone, Extension, Comment, Employee Start Date | Not mappable via Entra defaults |

Existing KnowBe4 values are **overwritten** by SCIM once enabled. Anything previously curated in
the console and not mapped in Entra will be blanked.

### "It worked, then stopped weeks later"
Quarantine (check 4), an expired SCIM token, or someone edited a mapping and saved without
restarting provisioning. Check the Entra provisioning status banner for the quarantine reason
and the last successful cycle timestamp.

### "Changes I make in the KSAT console keep reverting"
Sync is one-way, IdP → KnowBe4. The console is not a source of truth for any mapped field. Fix
the value in Entra. If the users show `adi_manageable: true` in the Reporting API, ADI is also
running — resolve that conflict first (see `writes.md`).

## Default attribute mappings

| Entra attribute | SCIM / KSAT attribute | KSAT field |
|---|---|---|
| `userPrincipalName` | `userName` | Email |
| `givenName` | `name.givenName` | First Name |
| `surname` | `name.familyName` | Last Name |
| `employeeId` | `...enterprise:2.0:User:employeeNumber` | Employee Number |
| `jobTitle` | `title` | Job Title |
| `department` | `...enterprise:2.0:User:department` | Department |
| `manager` | `...enterprise:2.0:User:manager.value` | Manager Email |
| manager's `displayName` | `displayName` | Manager Name |

Unmapped by default but available: `...enterprise:2.0:User:division`,
`...enterprise:2.0:User:organization`, and KnowBe4 extensions under
`urn:ietf:params:scim:schemas:extension:knowbe4:kmsat:2.0:User:` — `customField1`–`4`,
`customDate1`–`2` (ISO 8601, e.g. `2026-04-04T04:23:30Z`), `outOfOfficeEnd`,
`phishingLanguage`, `trainingLanguage`, `userRole`, `companyName`, `country`, `hostname`,
`mailNickName`, `onPremisesSamAccountName`, `onPremisesSecurityIdentifier`,
`userPrincipalName`, `lastPasswordChangeDateTime` (target type must be DateTime).

Also available: `physicalDeliveryOfficeName` → `addresses[type eq "work"].formatted` (Location),
`telephoneNumber` → `phoneNumbers[type eq "work"].value`, `mobile` →
`phoneNumbers[type eq "mobile"].value`.

When editing a mapping, change only the **Source attribute**. Altering matching precedence or
mapping type is a common way to break the connection.

## Known limitations

State these up front rather than letting the user discover them mid-incident:

- Provision on demand is **not supported**
- Nested groups are **not supported** — only direct members sync
- Email aliases are **not supported**, and are removed when switching from ADI to SCIM
- Sync is one-way; KnowBe4 never pushes back to Entra
- SAML SSO must be configured before SCIM will work
- Users outside the sync scope are archived, not ignored
- Group membership sync lags user sync on large accounts
- Requires a Microsoft Entra subscription

## Verifying with the Reporting API

Entra tells you what it *sent*. The Reporting API tells you what KnowBe4 *has*. Comparing the two
is how you distinguish "Entra never sent it" from "KnowBe4 rejected it" — and it works even while
Test Mode hides the effect of a sync.

```bash
# Which scoped users are missing from KnowBe4 entirely, and which KnowBe4 users
# are no longer in the Entra scope (i.e. next non-test sync will archive them)
python scripts/kb4.py reconcile --source entra_scope_export.csv --email-column userPrincipalName
python scripts/kb4.py reconcile --source entra_scope_export.csv --show missing

# Field-level drift: sync ran, but did the attributes actually land?
python scripts/kb4.py drift --source entra_export.csv \
    --email-column userPrincipalName \
    --map department=department,jobTitle=job_title,employeeId=employee_number
```

Export the Entra side from the enterprise app's assigned users, or via Graph /
`Get-MgUser`, with the same attributes that are mapped in the provisioning config. Comparing
against unmapped attributes produces noise, not findings.

Before running a drift check, confirm the last sync actually completed — a cycle in progress
looks identical to a broken mapping.
