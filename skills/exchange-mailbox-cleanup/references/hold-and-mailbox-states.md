# Holds and mailbox states

Identical copies of this file ship in `exchange-mailbox-cleanup` and `exchange-mailbox-restore`
(each skill is standalone; change both). Read this whenever a hold
column or a `MailboxState` needs interpreting for the operator.

## Hold is four things, not one

"Is this user on hold?" cannot be answered **no** until all four say no. Each preserves content by
a different mechanism, has a different removal path, and shows up in a different place.

| # | Hold | Set by | Shows as | Removed by | Session |
|---|---|---|---|---|---|
| 1 | **Litigation Hold** | `Set-Mailbox -LitigationHoldEnabled $true -LitigationHoldDuration 2555` | `LitigationHoldEnabled = True`, `LitigationHoldDate`, `LitigationHoldDuration`, `LitigationHoldOwner`, `RetentionComment` | `Set-Mailbox -LitigationHoldEnabled $false` | EXO |
| 2 | **Purview retention policy or label** | Purview > Data lifecycle management, or `New-RetentionCompliancePolicy` | `InPlaceHolds` entry prefixed `mbx` (or `-mbx` = *excluded* from an org-wide policy); `ComplianceTagHoldApplied = True` for a label | Remove the mailbox from the policy in Purview; a label hold clears when the labelled item's period ends | IPPS |
| 3 | **eDiscovery case hold** | Purview eDiscovery (Premium) case > Holds | `InPlaceHolds` entry prefixed `UniH` | Release the hold inside the case | IPPS (portal) |
| 4 | **In-Place Hold remnant** | Legacy `New-MailboxSearch -InPlaceHoldEnabled` - retired feature | `InPlaceHolds` entry with **no** `mbx`/`UniH`/`grp`/`skp` prefix (a bare GUID) | `Set-Mailbox -RemoveDelayHoldApplied` does *not* clear it; open a Microsoft support case - the cmdlets that created it are gone | - |

Plus two things that are not holds but behave like them for 30 days after the last hold comes off:

| Property | Meaning |
|---|---|
| `DelayHoldApplied = True` | Exchange keeps content preserved for ~30 days after the last hold is removed. Cleared with `Set-Mailbox -RemoveDelayHoldApplied` |
| `DelayReleaseHoldApplied = True` | Same, for eDiscovery/retention releases. Cleared with `Set-Mailbox -RemoveDelayReleaseHoldApplied` |

Verify both `-RemoveDelayHold*` parameters against current Microsoft Learn before printing them for
a destruction path. Hold behaviour changes, and this is the step where being wrong is unrecoverable
in one direction.

### The command that starts the answer

```powershell
Get-Mailbox -Identity '{User}' | Format-List DisplayName, LitigationHoldEnabled, LitigationHoldDate,
    LitigationHoldDuration, LitigationHoldOwner, RetentionComment, RetentionPolicy,
    InPlaceHolds, ComplianceTagHoldApplied, DelayHoldApplied, DelayReleaseHoldApplied
```

For an inactive mailbox add `-InactiveMailboxOnly` and identify by `ExchangeGuid`, never by address
(see "Three states" below). `Get-Mailbox | fl *hold*` is the starting point, not the answer - it
does not show `InPlaceHolds` decoded and it does not show `RetentionComment`.

### Decoding `InPlaceHolds`

| Prefix | Meaning | Where to release it |
|---|---|---|
| `mbx` | Mailbox is **included** in a Purview retention policy | Purview > Data lifecycle management > the policy |
| `-mbx` | Mailbox is **excluded** from an org-wide retention policy. Not a hold | Nothing to release |
| `UniH` | eDiscovery (Premium) case hold | The case > Holds |
| `grp` | Microsoft 365 Group hold (rare on a user mailbox) | The group's policy |
| `skp` | Skype for Business retention (legacy) | Purview |
| bare GUID | Legacy In-Place Hold remnant | Microsoft support |

A `RetentionPolicy` value (e.g. `Default MRM Policy`) is **not** a hold. It is the MRM tag set that
governs Deleted Items ageing. Do not report it as one.

### What this process stamps

`Invoke-M365OffboardingHold.ps1` writes:

| Property | Value |
|---|---|
| `LitigationHoldEnabled` | `True` |
| `LitigationHoldDuration` | `2555` days - seven years, measured from each item's **received date**, not from the hold date |
| `RetentionComment` | `{DisplayName}-{yyyy-MM-dd}-Termination` - Litigation Hold has no "name" property, so the tag lives here |
| `LitigationHoldOwner` | The account the script ran as |

The `-Termination` suffix is what the confirmation report (`runbook-steps.md` Step 35) filters on.
Clearing `RetentionComment` when a hold is removed (`restore` Path 1) is what stops the mailbox
reappearing in that report.

## Three states (and a fourth that means "too late")

`Test-MailboxPreservation.ps1` returns exactly one `MailboxState` per identity. They are different
objects reached by different cmdlets, and an address can exist in more than one at once.

| `MailboxState` | What happened | Found by | Clock | Restore skill path |
|---|---|---|---|---|
| `Active` | Account exists, mailbox live | `Get-Mailbox` | None | Path 1 (remove hold) |
| `Inactive` | Account **deleted while a hold was in place**. Mailbox preserved for the hold, searchable in eDiscovery, consumes no seat | `Get-Mailbox -InactiveMailboxOnly` | None while any hold remains | Path 2 (restore a copy) or Path 3 (recover for a returning person) |
| `SoftDeleted` | Account deleted **with no hold**, or licence removed from a live mailbox | `Get-Mailbox -SoftDeletedMailbox` | **30 days** from `WhenSoftDeleted`, then purged with no support path | Path 4 - and hurry |
| `NotFound` | Purged, or the identity was wrong | none | - | Escalate. Check `Detail` for near-match suggestions first: `first@domain` vs `first.last@domain` reads exactly like "not preserved" |

**Identify an inactive mailbox by `ExchangeGuid`, never by SMTP address.** An inactive mailbox can
share an address with a live one (the person came back, or the address was reissued). The address
then resolves to the *wrong* mailbox without error. Microsoft Learn (*Delete an inactive mailbox*):
"the best way to do this is by using its Distinguished Name or Exchange GUID value. Using one of
these values instead of the SMTP address helps prevent accidentally specifying the wrong mailbox."
Record the GUID the first time you see it, pass `-InactiveMailbox` on every `Set-Mailbox` that
targets it, and use both for every later command.

**Auto-expanding archive blocks restore and recover.** Learn: "You can't recover or restore an
inactive mailbox that's configured with an auto-expanding archive." Check `AutoExpandingArchiveEnabled`
at triage; if `True`, the only route to the content is a Purview content search export.

**An inactive mailbox is not a deleted mailbox.** Re-licensing or restoring the *user* creates a
*new* mailbox and leaves the inactive one alone unless you explicitly recover it (Path 3).

### `Test-MailboxPreservation.ps1` verdicts

Read `Verdict` and `Detail` from the CSV at `C:\scripts\logs\MailboxPreservation-{timestamp}.csv`.

| `Verdict` | `SafeToDeleteAccount` | Meaning for the operator |
|---|---|---|
| `PreservedReadyToDelete` | `True` | Active, on hold, hold re-read and confirmed. Phase C may proceed for this mailbox |
| `NotPreserved` | `False` | Active, **no hold**. Deleting now soft-deletes it and starts the 30-day clock. Do not proceed |
| `InactivePreserved` | `False` | Already deleted, hold intact. This is the **success** state after Phase C, not a failure |
| `SoftDeletedAtRisk` | `False` | Deleted with no hold. Purge in 30 days. Go to `exchange-mailbox-restore` Path 4 |
| `NotFound` / `NotFoundWithSuggestions` | `False` | Identity did not resolve. Read `Detail` for the near-matches before concluding anything |

Columns the CSV actually carries (defect 3): `MailboxSizeGB` and `ItemCount` from mailbox
statistics; `SearchItemCount` and `SearchSizeGB` from the compliance search when
`-RunComplianceSearch` was passed. There is no `TotalItemSizeMB` column - the runbook is wrong.

**An empty search is not proof of an empty mailbox.** `SearchStatus` completed with
`SearchItemCount = 0` while the eDiscovery role is still propagating (or missing) is the expected
false negative. The script's log says "unproven", not "empty", for exactly this reason. Compare
`ItemCount` (mailbox statistics, needs only Exchange rights) against `SearchItemCount` (needs
Purview rights): a large gap between them is the propagation problem, not a preservation problem.

## The licence rule, stated once more

| Action | Under a hold | Without a hold |
|---|---|---|
| **Delete the account** | Mailbox becomes **inactive**. Preserved for the hold. Seat released | Mailbox is **soft-deleted**. Purged in 30 days |
| **Remove the licence from a live account** | Mailbox is **soft-deleted anyway**. Purged in 30 days. The hold does not save it | Same |

Hold-then-delete is the only safe sequence. `Get-M365OffboardingStatus.ps1` carries a
`SafeToRemoveLicense` column that always reads `No`; it exists solely to stop this mistake.

## Clocks you cannot stop

| Event | Clock |
|---|---|
| Licence removed from a live mailbox | 30 days to permanent purge |
| Account deleted with no hold | 30 days (Entra recycle bin and Exchange soft-delete run in parallel) |
| Last hold removed from an inactive mailbox | Delay hold ~30 days, then the mailbox is purged on the next retention pass |
| Hold removed from an active mailbox | Items already past their MRM age become eligible for deletion on the next pass - usually within days |
