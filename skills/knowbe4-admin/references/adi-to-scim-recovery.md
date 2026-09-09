# Runbook: recovering a broken ADI → SCIM cutover

For the situation where SCIM provisioning is live, wrong, and still running. Typical signature:
the synced population is far larger than the assigned group, some people appear twice on
different email domains, and fields ADI used to populate are going blank.

Two independent faults usually coexist. Fixing one alone still leaves a wrong result, so treat
them as a single change:

| Fault | Symptom it causes |
|---|---|
| Provisioning scope set to *Sync all users and groups* | Assignment is ignored; the whole directory syncs |
| `userName` sourced from an attribute ADI did not use | A second record is created per person instead of matching |

**Do not work through this on the live app if you can avoid it.** See Phase 5.

---

## Phase 0 — Stop the bleeding (do this first, takes a minute)

KSAT console → Account Settings → User Management → User Provisioning → **enable Test Mode**.

Sync cycles continue and reports keep generating, but users are no longer created or archived.
This is reversible and buys unlimited diagnostic time. Every 40 minutes it is left off is
another cycle of duplicate creation and field blanking.

Confirm the toggle is on **SCIM**, not ADI, while you are on this page.

## Phase 1 — Capture a baseline before changing anything

Do this before touching Entra. Once mappings change and cycles run, the evidence of what the
account looked like is gone, and archived users are hard to reason about after the fact.

```bash
python scripts/kb4.py users --format csv --out baseline_users.csv
python scripts/kb4.py groups --format csv --out baseline_groups.csv
python scripts/kb4.py duplicates --format csv --out baseline_duplicates.csv
```

Keep these. They serve three purposes: proving what the sync did, reconstructing group
membership if it is lost, and giving a before/after count to verify the fix actually worked.

Also record from the console: total active users, and the last three sync report summaries.

## Phase 2 — Establish the correct matching attribute

The fix depends on which address ADI populated. Determine it from the baseline rather than
assuming.

```bash
# What domains exist in the current population?
python scripts/kb4.py users --fields email,adi_manageable,status --format csv --out domains.csv
```

Records with `adi_manageable: true` carry the address ADI used. Records created by SCIM carry
the UPN. If duplicates span two domains, the ADI-side domain is the value `userName` should map
to — usually `mail` rather than `userPrincipalName`.

If UPN and mail are identical across the estate, matching is not your problem and the
duplicates have another cause; stop and re-diagnose.

## Phase 3 — Correct the Entra configuration

Make all of these before running another cycle. A partial fix produces another wrong result.

| # | Location | Change |
|---|---|---|
| 1 | Provisioning → Settings → **Scope** | Set to *Sync only assigned users and groups* |
| 2 | The app → **Users and groups** | Remove every assignment that should not be in scope, including any inherited from SSO use of the same app |
| 3 | Provisioning → Edit attribute mappings → `userName` | Change the **Source attribute** only, to the address identified in Phase 2 |
| 4 | Single sign-on → SAML source attribute | Set to the same attribute as `userName` |
| 5 | Provisioning → mappings | Re-add `division` and `organization` if ADI populated them — unmapped by default, so SCIM blanks them |
| 6 | Provisioning | **Restart provisioning** |

On step 3, change nothing but the source attribute. Altering mapping type or matching precedence
is a common way to break the connector outright.

On step 6, a mapping change needs a full re-evaluation. An incremental cycle will not
re-examine users it has already processed.

## Phase 4 — Verify before going live

Still in Test Mode. Let a full cycle complete, then:

```bash
python scripts/kb4.py duplicates
python scripts/kb4.py reconcile --source assigned_group_members.csv \
    --email-column userPrincipalName
python scripts/kb4.py drift --source entra_export.csv \
    --map department=department,jobTitle=job_title --ignore-blank-source
```

Gate on all three:

| Check | Pass condition |
|---|---|
| `duplicates` | No new duplicate sets since baseline |
| `reconcile --show missing` | Empty, or only genuinely new starters |
| `reconcile` (orphaned) | Matches the number you *intend* to archive, and you recognise the names |
| `drift` | Only fields you deliberately left unmapped |

The orphaned count is the important one. Turning Test Mode off archives every one of them. Read
the list before you do it.

## Phase 5 — Merge duplicates, then go live

Merge duplicate pairs in the console. **Do not delete the ADI-side record** — phishing results,
training completions and phish-prone history live on it and do not transfer to the newer record.
Deleting it destroys the compliance evidence for those users.

Then disable Test Mode and let one cycle run. Re-run the Phase 4 checks and compare active user
count against `baseline_users.csv`.

### The alternative worth proposing

If the live app has already run several bad cycles, building a **fresh enterprise application**
scoped to five test users is usually faster and safer than repairing the existing one:

- The bad app can be left with provisioning stopped rather than half-corrected
- Mapping errors are proven against five users instead of the whole directory
- No further mass-archival risk while iterating
- KnowBe4 explicitly recommends a separate app while testing the integration

Offer this before starting Phase 3, not after it fails.

## Escalation

Two things sit outside KnowBe4 and are worth naming rather than working around:

- **UPN ≠ mail across the estate** is a directory issue, not a KnowBe4 issue. Mapping `userName`
  to `mail` fixes this integration and leaves the same trap for the next SCIM app.
- **Seat counts.** A duplicated population may push the account over its licensed seats. Check
  before the finance conversation finds it first.

For provisioning behaviour on the Entra side, Microsoft support owns the connector; KnowBe4
support owns what the KSAT console does with what it receives. Sync reports from the
User Provisioning tab are what KnowBe4 support will ask for.
